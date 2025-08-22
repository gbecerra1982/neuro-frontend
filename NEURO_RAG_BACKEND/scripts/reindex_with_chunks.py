"""
Script to re-index existing documents with proper chunking
This script reads existing documents, splits them into chunks, and re-indexes them
"""

import os
import sys
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    ComplexField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    SemanticSearch
)
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DocumentChunker:
    """
    Splits documents into searchable chunks with overlap
    """
    
    def __init__(self, 
                 chunk_size: int = 1000,
                 chunk_overlap: int = 200,
                 separator: str = "\n\n"):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separator = separator
        
    def create_chunks(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create overlapping chunks from text
        """
        chunks = []
        
        # Split by paragraphs first
        paragraphs = text.split(self.separator)
        
        current_chunk = ""
        current_length = 0
        chunk_index = 0
        
        for paragraph in paragraphs:
            paragraph_length = len(paragraph)
            
            # If single paragraph is too long, split it
            if paragraph_length > self.chunk_size:
                sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                for sentence in sentences:
                    if current_length + len(sentence) > self.chunk_size:
                        if current_chunk:
                            chunks.append(self._create_chunk_doc(
                                current_chunk, metadata, chunk_index, len(chunks)
                            ))
                            chunk_index += 1
                            # Keep overlap
                            overlap_text = current_chunk[-self.chunk_overlap:] if len(current_chunk) > self.chunk_overlap else current_chunk
                            current_chunk = overlap_text + " " + sentence
                            current_length = len(current_chunk)
                        else:
                            current_chunk = sentence
                            current_length = len(sentence)
                    else:
                        current_chunk += " " + sentence
                        current_length += len(sentence)
            else:
                # Try to add paragraph to current chunk
                if current_length + paragraph_length > self.chunk_size:
                    if current_chunk:
                        chunks.append(self._create_chunk_doc(
                            current_chunk, metadata, chunk_index, len(chunks)
                        ))
                        chunk_index += 1
                        # Keep overlap
                        overlap_text = current_chunk[-self.chunk_overlap:] if len(current_chunk) > self.chunk_overlap else current_chunk
                        current_chunk = overlap_text + self.separator + paragraph
                        current_length = len(current_chunk)
                    else:
                        current_chunk = paragraph
                        current_length = paragraph_length
                else:
                    if current_chunk:
                        current_chunk += self.separator + paragraph
                    else:
                        current_chunk = paragraph
                    current_length += paragraph_length
        
        # Add last chunk
        if current_chunk:
            chunks.append(self._create_chunk_doc(
                current_chunk, metadata, chunk_index, len(chunks)
            ))
        
        logger.info(f"Created {len(chunks)} chunks from document")
        return chunks
    
    def _create_chunk_doc(self, text: str, metadata: Dict[str, Any], index: int, total: int) -> Dict[str, Any]:
        """
        Create a chunk document with metadata
        """
        # Generate unique ID for chunk
        chunk_id = f"{metadata.get('id', 'unknown')}_{index}"
        
        return {
            'id': chunk_id,
            'content': text.strip(),
            'chunk_index': index,
            'total_chunks': total,
            'headers': {
                'pozo': metadata.get('pozo'),
                'equipo': metadata.get('equipo'),
                'fecha': metadata.get('fecha'),
                'source_document': metadata.get('id', 'unknown'),
                'chunk_info': f"Chunk {index + 1} of {total + 1}"
            },
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'chunk_size': len(text),
                'original_size': metadata.get('size', 0)
            }
        }

class AzureSearchIndexManager:
    """
    Manages Azure Search index creation and updates
    """
    
    def __init__(self):
        self.endpoint = os.environ.get("AZURE_SEARCH_SERVICE_ENDPOINT")
        self.api_key = os.environ.get("AZURE_SEARCH_ADMIN_KEY")
        self.index_name = os.environ.get("AZURE_SEARCH_INDEX", "neuro-rag-chunked")
        
        self.index_client = SearchIndexClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.api_key)
        )
        
        self.search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(self.api_key)
        )
        
        # Initialize OpenAI for embeddings
        self.openai_client = AzureOpenAI(
            api_key=os.environ.get("AZURE_OPENAI_STANDARD_API_KEY"),
            api_version="2024-02-01",
            azure_endpoint=os.environ.get("AZURE_OPENAI_STANDARD_ENDPOINT")
        )
        self.embedding_model = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
    
    def create_chunked_index(self):
        """
        Create a new index optimized for chunked documents
        """
        logger.info(f"Creating chunked index: {self.index_name}")
        
        # Define fields
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="standard.lucene"),
            SimpleField(name="chunk_index", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
            SimpleField(name="total_chunks", type=SearchFieldDataType.Int32, filterable=True),
            
            # Headers complex field
            ComplexField(name="headers", fields=[
                SimpleField(name="pozo", type=SearchFieldDataType.String, filterable=True, facetable=True),
                SimpleField(name="equipo", type=SearchFieldDataType.String, filterable=True, facetable=True),
                SimpleField(name="fecha", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SimpleField(name="source_document", type=SearchFieldDataType.String, filterable=True),
                SearchableField(name="chunk_info", type=SearchFieldDataType.String)
            ]),
            
            # Metadata complex field
            ComplexField(name="metadata", fields=[
                SimpleField(name="timestamp", type=SearchFieldDataType.String),
                SimpleField(name="chunk_size", type=SearchFieldDataType.Int32),
                SimpleField(name="original_size", type=SearchFieldDataType.Int32)
            ]),
            
            # Vector field for embeddings
            SearchableField(
                name="contentVector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=1536,  # text-embedding-ada-002 dimensions
                vector_search_profile_name="myHnswProfile"
            )
        ]
        
        # Configure vector search
        vector_search = VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(
                    name="myHnsw",
                    parameters={
                        "m": 4,
                        "efConstruction": 400,
                        "efSearch": 500,
                        "metric": "cosine"
                    }
                )
            ],
            profiles=[
                VectorSearchProfile(
                    name="myHnswProfile",
                    algorithm_configuration_name="myHnsw"
                )
            ]
        )
        
        # Configure semantic search
        semantic_search = SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="neuro-semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="headers/chunk_info"),
                        content_fields=[SemanticField(field_name="content")],
                        keywords_fields=[
                            SemanticField(field_name="headers/pozo"),
                            SemanticField(field_name="headers/equipo")
                        ]
                    )
                )
            ]
        )
        
        # Create index
        index = SearchIndex(
            name=self.index_name,
            fields=fields,
            vector_search=vector_search,
            semantic_search=semantic_search
        )
        
        try:
            self.index_client.create_or_update_index(index)
            logger.info(f"Index '{self.index_name}' created successfully")
            return True
        except Exception as e:
            logger.error(f"Error creating index: {e}")
            return False
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embeddings for text
        """
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text[:8000]  # Limit text length for embedding
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return [0.0] * 1536  # Return zero vector on error
    
    def index_chunks(self, chunks: List[Dict[str, Any]], batch_size: int = 100):
        """
        Index chunks in batches
        """
        logger.info(f"Indexing {len(chunks)} chunks in batches of {batch_size}")
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            # Add embeddings to each chunk
            for chunk in batch:
                chunk['contentVector'] = self.generate_embedding(chunk['content'])
            
            try:
                result = self.search_client.upload_documents(documents=batch)
                succeeded = sum(1 for r in result if r.succeeded)
                logger.info(f"Batch {i//batch_size + 1}: {succeeded}/{len(batch)} documents indexed")
            except Exception as e:
                logger.error(f"Error indexing batch: {e}")

class DocumentReindexer:
    """
    Main class to reindex existing documents with chunking
    """
    
    def __init__(self):
        self.chunker = DocumentChunker(
            chunk_size=int(os.environ.get("CHUNK_SIZE", "1000")),
            chunk_overlap=int(os.environ.get("CHUNK_OVERLAP", "200"))
        )
        self.index_manager = AzureSearchIndexManager()
        
        # Storage client for reading source documents
        self.blob_service = BlobServiceClient.from_connection_string(
            os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        )
        self.container_name = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "neuro-documents")
    
    def get_existing_documents(self) -> List[Dict[str, Any]]:
        """
        Retrieve existing documents from current index or storage
        """
        logger.info("Retrieving existing documents...")
        documents = []
        
        try:
            # Option 1: Read from existing Azure Search index
            old_index = os.environ.get("OLD_AZURE_SEARCH_INDEX", "neuro-rag")
            old_client = SearchClient(
                endpoint=self.index_manager.endpoint,
                index_name=old_index,
                credential=AzureKeyCredential(self.index_manager.api_key)
            )
            
            # Get all documents
            results = old_client.search(search_text="*", top=1000)
            for doc in results:
                documents.append({
                    'id': doc.get('id'),
                    'content': doc.get('content', ''),
                    'pozo': doc.get('headers', {}).get('pozo'),
                    'equipo': doc.get('headers', {}).get('equipo'),
                    'fecha': doc.get('headers', {}).get('fecha'),
                    'size': len(doc.get('content', ''))
                })
            
            logger.info(f"Retrieved {len(documents)} documents from existing index")
            
        except Exception as e:
            logger.error(f"Error retrieving documents from index: {e}")
            
            # Option 2: Read from blob storage
            try:
                container_client = self.blob_service.get_container_client(self.container_name)
                blobs = container_client.list_blobs()
                
                for blob in blobs:
                    blob_client = container_client.get_blob_client(blob.name)
                    content = blob_client.download_blob().readall().decode('utf-8')
                    
                    # Extract metadata from blob name or properties
                    metadata = self._extract_metadata_from_blob(blob.name, blob.properties)
                    
                    documents.append({
                        'id': blob.name,
                        'content': content,
                        'pozo': metadata.get('pozo'),
                        'equipo': metadata.get('equipo'),
                        'fecha': metadata.get('fecha'),
                        'size': len(content)
                    })
                
                logger.info(f"Retrieved {len(documents)} documents from blob storage")
                
            except Exception as e2:
                logger.error(f"Error retrieving documents from blob storage: {e2}")
        
        return documents
    
    def _extract_metadata_from_blob(self, blob_name: str, properties: Any) -> Dict[str, Any]:
        """
        Extract metadata from blob name or properties
        """
        metadata = {}
        
        # Extract from filename pattern (adjust based on your naming convention)
        # Example: "LACh-1030_2024-01-15_report.txt"
        parts = blob_name.split('_')
        if len(parts) >= 2:
            metadata['pozo'] = parts[0] if 'Ch' in parts[0] or 'Cav' in parts[0] else None
            
            # Extract date
            date_pattern = r'\d{4}-\d{2}-\d{2}'
            date_match = re.search(date_pattern, blob_name)
            if date_match:
                metadata['fecha'] = date_match.group()
        
        # Extract from blob metadata if available
        if hasattr(properties, 'metadata'):
            metadata.update(properties.metadata or {})
        
        return metadata
    
    def reindex_all_documents(self):
        """
        Main method to reindex all documents with chunking
        """
        logger.info("="*60)
        logger.info("DOCUMENT REINDEXING WITH CHUNKING")
        logger.info("="*60)
        
        # Step 1: Create new chunked index
        logger.info("\n1. Creating new chunked index...")
        if not self.index_manager.create_chunked_index():
            logger.error("Failed to create index. Aborting.")
            return False
        
        # Step 2: Get existing documents
        logger.info("\n2. Retrieving existing documents...")
        documents = self.get_existing_documents()
        
        if not documents:
            logger.warning("No documents found to reindex")
            return False
        
        logger.info(f"Found {len(documents)} documents to process")
        
        # Step 3: Process documents and create chunks
        logger.info("\n3. Creating chunks from documents...")
        all_chunks = []
        
        for doc in documents:
            logger.info(f"Processing document: {doc['id']} (size: {doc['size']} chars)")
            chunks = self.chunker.create_chunks(doc['content'], doc)
            all_chunks.extend(chunks)
            logger.info(f"  Created {len(chunks)} chunks")
        
        logger.info(f"\nTotal chunks created: {len(all_chunks)}")
        
        # Step 4: Index chunks
        logger.info("\n4. Indexing chunks...")
        self.index_manager.index_chunks(all_chunks)
        
        # Step 5: Verify
        logger.info("\n5. Verifying index...")
        try:
            # Test search
            results = self.index_manager.search_client.search(
                search_text="*",
                top=5
            )
            count = 0
            for _ in results:
                count += 1
            
            logger.info(f"Verification successful: {count} documents searchable")
            
            # Summary
            logger.info("\n" + "="*60)
            logger.info("REINDEXING COMPLETE")
            logger.info(f"Original documents: {len(documents)}")
            logger.info(f"Total chunks created: {len(all_chunks)}")
            logger.info(f"Average chunks per document: {len(all_chunks)/len(documents):.1f}")
            logger.info("="*60)
            
            return True
            
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False

def main():
    """
    Main entry point
    """
    reindexer = DocumentReindexer()
    
    # Confirm before proceeding
    print("\nThis script will:")
    print("1. Create a new Azure Search index with chunking support")
    print("2. Read all existing documents")
    print("3. Split documents into searchable chunks")
    print("4. Index chunks with embeddings")
    print("\nThis may take significant time depending on document volume.")
    
    response = input("\nProceed? (yes/no): ")
    
    if response.lower() != 'yes':
        print("Aborted.")
        return
    
    # Run reindexing
    success = reindexer.reindex_all_documents()
    
    if success:
        print("\nNext steps:")
        print("1. Update AZURE_SEARCH_INDEX in .env to use the new index")
        print("2. Restart the application")
        print("3. Test search functionality")
    else:
        print("\nReindexing failed. Check logs for details.")

if __name__ == "__main__":
    main()