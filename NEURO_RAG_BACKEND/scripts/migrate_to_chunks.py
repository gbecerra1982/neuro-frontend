"""
Migration script to create semantic chunks index for NEURO RAG
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    SemanticSearch
)
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ChunkMigrator:
    """
    Migrate existing index to semantic chunks using Document Layout Skill
    """
    
    def __init__(self):
        # Azure Search configuration
        self.endpoint = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
        self.api_key = os.environ["AZURE_SEARCH_ADMIN_KEY"]
        self.old_index = os.environ.get("AZURE_SEARCH_INDEX_OLD", "neuro-rag")
        self.new_index = os.environ.get("AZURE_SEARCH_INDEX", "neuro-rag-semantic-chunks")
        
        # Initialize clients
        self.index_client = SearchIndexClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.api_key)
        )
        
        logger.info(f"Initialized migrator: {self.old_index} -> {self.new_index}")
    
    def create_chunk_index(self) -> bool:
        """
        Create new index with semantic chunk structure
        """
        try:
            logger.info(f"Creating index: {self.new_index}")
            
            # Define fields for chunked documents
            fields = [
                # Primary key
                SimpleField(
                    name="chunk_id",
                    type=SearchFieldDataType.String,
                    key=True,
                    filterable=True,
                    sortable=False
                ),
                
                # Document relationship
                SimpleField(
                    name="parent_id",
                    type=SearchFieldDataType.String,
                    filterable=True,
                    sortable=False
                ),
                
                # Chunk content
                SearchableField(
                    name="chunk_content",
                    type=SearchFieldDataType.String,
                    analyzer_name="standard.lucene"
                ),
                
                # Chunk metadata
                SimpleField(
                    name="chunk_index",
                    type=SearchFieldDataType.Int32,
                    sortable=True,
                    filterable=True
                ),
                
                # Hierarchical headers
                SearchableField(
                    name="header_1",
                    type=SearchFieldDataType.String,
                    facetable=True,
                    filterable=True
                ),
                SearchableField(
                    name="header_2",
                    type=SearchFieldDataType.String,
                    facetable=True,
                    filterable=True
                ),
                SearchableField(
                    name="header_3",
                    type=SearchFieldDataType.String,
                    facetable=True,
                    filterable=True
                ),
                
                # Domain-specific fields
                SearchableField(
                    name="pozo",
                    type=SearchFieldDataType.String,
                    facetable=True,
                    filterable=True
                ),
                SearchableField(
                    name="equipo",
                    type=SearchFieldDataType.String,
                    facetable=True,
                    filterable=True
                ),
                SimpleField(
                    name="fecha",
                    type=SearchFieldDataType.DateTimeOffset,
                    filterable=True,
                    sortable=True,
                    facetable=True
                ),
                SearchableField(
                    name="yacimiento",
                    type=SearchFieldDataType.String,
                    facetable=True,
                    filterable=True
                ),
                SimpleField(
                    name="tipo_documento",
                    type=SearchFieldDataType.String,
                    facetable=True,
                    filterable=True
                ),
                
                # Vector field for embeddings
                SearchField(
                    name="text_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=1536,
                    vector_search_profile_name="vector-profile-1536"
                ),
                
                # Additional metadata
                SimpleField(
                    name="metadata_json",
                    type=SearchFieldDataType.String,
                    retrievable=True
                )
            ]
            
            # Configure vector search
            vector_search = VectorSearch(
                algorithms=[
                    HnswAlgorithmConfiguration(
                        name="hnsw-algorithm",
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
                        name="vector-profile-1536",
                        algorithm_configuration_name="hnsw-algorithm"
                    )
                ]
            )
            
            # Configure semantic search
            semantic_search = SemanticSearch(
                default_configuration_name="neuro-semantic-config",
                configurations=[
                    SemanticConfiguration(
                        name="neuro-semantic-config",
                        prioritized_fields=SemanticPrioritizedFields(
                            title_field=SemanticField(field_name="header_1"),
                            content_fields=[
                                SemanticField(field_name="chunk_content")
                            ],
                            keywords_fields=[
                                SemanticField(field_name="pozo"),
                                SemanticField(field_name="equipo"),
                                SemanticField(field_name="header_2")
                            ]
                        )
                    )
                ]
            )
            
            # Create index
            index = SearchIndex(
                name=self.new_index,
                fields=fields,
                vector_search=vector_search,
                semantic_search=semantic_search
            )
            
            # Create or update index
            result = self.index_client.create_or_update_index(index)
            logger.info(f"Index created successfully: {result.name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create index: {e}", exc_info=True)
            return False
    
    def export_existing_documents(self) -> List[Dict[str, Any]]:
        """
        Export documents from existing index for re-processing
        """
        try:
            logger.info(f"Exporting documents from: {self.old_index}")
            
            old_client = SearchClient(
                endpoint=self.endpoint,
                index_name=self.old_index,
                credential=AzureKeyCredential(self.api_key)
            )
            
            documents = []
            
            # Export all documents
            results = old_client.search(
                search_text="*",
                select=["id", "content", "pozo", "equipo", "fecha", "yacimiento", "tipo_documento"],
                top=1000
            )
            
            for doc in results:
                documents.append({
                    "id": doc.get("id"),
                    "content": doc.get("content"),
                    "metadata": {
                        "pozo": doc.get("pozo"),
                        "equipo": doc.get("equipo"),
                        "fecha": doc.get("fecha"),
                        "yacimiento": doc.get("yacimiento"),
                        "tipo_documento": doc.get("tipo_documento")
                    }
                })
            
            logger.info(f"Exported {len(documents)} documents")
            
            # Save to file for backup
            export_file = f"export_{self.old_index}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(export_file, "w", encoding="utf-8") as f:
                json.dump(documents, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"Backup saved to: {export_file}")
            
            return documents
            
        except Exception as e:
            logger.error(f"Failed to export documents: {e}", exc_info=True)
            return []
    
    def validate_migration(self) -> Dict[str, Any]:
        """
        Validate the migration was successful
        """
        try:
            logger.info("Validating migration...")
            
            # Get document counts
            old_client = SearchClient(
                endpoint=self.endpoint,
                index_name=self.old_index,
                credential=AzureKeyCredential(self.api_key)
            )
            
            new_client = SearchClient(
                endpoint=self.endpoint,
                index_name=self.new_index,
                credential=AzureKeyCredential(self.api_key)
            )
            
            old_count = old_client.get_document_count()
            new_count = new_client.get_document_count()
            
            # Test queries
            test_queries = [
                "equipo DLS-168",
                "pozo LACh-1030",
                "yacimiento Vaca Muerta"
            ]
            
            test_results = []
            for query in test_queries:
                old_results = list(old_client.search(query, top=1))
                new_results = list(new_client.search(query, top=1))
                
                test_results.append({
                    "query": query,
                    "old_results": len(old_results),
                    "new_results": len(new_results)
                })
            
            validation = {
                "timestamp": datetime.now().isoformat(),
                "old_index": {
                    "name": self.old_index,
                    "document_count": old_count
                },
                "new_index": {
                    "name": self.new_index,
                    "chunk_count": new_count,
                    "estimated_documents": new_count // 20 if new_count > 0 else 0
                },
                "test_results": test_results,
                "status": "success" if new_count > 0 else "pending"
            }
            
            # Check chunk quality
            if new_count > 0:
                sample_chunks = list(new_client.search(
                    "*",
                    select=["chunk_id", "parent_id", "chunk_index"],
                    top=100
                ))
                
                parent_ids = set(chunk.get("parent_id") for chunk in sample_chunks)
                avg_chunks = len(sample_chunks) / len(parent_ids) if parent_ids else 0
                
                validation["chunk_quality"] = {
                    "unique_documents": len(parent_ids),
                    "average_chunks_per_doc": avg_chunks,
                    "sample_size": len(sample_chunks)
                }
            
            return validation
            
        except Exception as e:
            logger.error(f"Validation error: {e}", exc_info=True)
            return {
                "error": str(e),
                "status": "failed",
                "timestamp": datetime.now().isoformat()
            }
    
    def generate_migration_report(self, validation: Dict[str, Any]) -> str:
        """
        Generate migration report
        """
        report = []
        report.append("=" * 70)
        report.append("SEMANTIC CHUNK MIGRATION REPORT")
        report.append("=" * 70)
        report.append(f"Timestamp: {validation.get('timestamp', 'N/A')}")
        report.append(f"Status: {validation.get('status', 'unknown').upper()}")
        report.append("")
        
        # Old index info
        old_info = validation.get("old_index", {})
        report.append("SOURCE INDEX")
        report.append("-" * 40)
        report.append(f"Name: {old_info.get('name', 'N/A')}")
        report.append(f"Documents: {old_info.get('document_count', 0):,}")
        report.append("")
        
        # New index info
        new_info = validation.get("new_index", {})
        report.append("TARGET INDEX")
        report.append("-" * 40)
        report.append(f"Name: {new_info.get('name', 'N/A')}")
        report.append(f"Chunks: {new_info.get('chunk_count', 0):,}")
        report.append(f"Estimated Documents: {new_info.get('estimated_documents', 0):,}")
        report.append("")
        
        # Chunk quality
        if "chunk_quality" in validation:
            quality = validation["chunk_quality"]
            report.append("CHUNK QUALITY")
            report.append("-" * 40)
            report.append(f"Unique Documents: {quality.get('unique_documents', 0)}")
            report.append(f"Avg Chunks per Doc: {quality.get('average_chunks_per_doc', 0):.1f}")
            report.append(f"Sample Size: {quality.get('sample_size', 0)}")
            report.append("")
        
        # Test results
        if "test_results" in validation:
            report.append("SEARCH VALIDATION")
            report.append("-" * 40)
            for test in validation["test_results"]:
                report.append(f"Query: {test['query']}")
                report.append(f"  Old Results: {test['old_results']}")
                report.append(f"  New Results: {test['new_results']}")
            report.append("")
        
        # Next steps
        if validation.get("status") == "pending":
            report.append("NEXT STEPS")
            report.append("-" * 40)
            report.append("1. Go to Azure AI Foundry portal")
            report.append("2. Navigate to your project")
            report.append("3. Import documents using Document Layout Skill")
            report.append("4. Run this script again to validate")
        elif validation.get("status") == "success":
            report.append("MIGRATION SUCCESSFUL")
            report.append("-" * 40)
            report.append("1. Update .env to use new index")
            report.append("2. Test application thoroughly")
            report.append("3. Monitor performance metrics")
        
        report.append("")
        report.append("=" * 70)
        
        return "\n".join(report)

def main():
    """
    Main migration process
    """
    print("\n" + "=" * 70)
    print("NEURO RAG - SEMANTIC CHUNK MIGRATION")
    print("=" * 70)
    
    # Initialize migrator
    migrator = ChunkMigrator()
    
    # Step 1: Create new index
    print("\n[1/4] Creating semantic chunk index...")
    if not migrator.create_chunk_index():
        print("ERROR: Failed to create index. Check logs for details.")
        return 1
    print("SUCCESS: Index created")
    
    # Step 2: Export existing documents
    print("\n[2/4] Exporting existing documents...")
    documents = migrator.export_existing_documents()
    if documents:
        print(f"SUCCESS: Exported {len(documents)} documents")
    else:
        print("WARNING: No documents exported or index doesn't exist")
    
    # Step 3: Provide instructions
    print("\n[3/4] Manual steps required:")
    print("-" * 40)
    print("1. Go to Azure AI Foundry: https://ai.azure.com")
    print("2. Navigate to your project")
    print("3. Go to: Agents -> Setup -> Knowledge -> + Add")
    print("4. Select 'Azure AI Search' and choose your new index")
    print("5. Enable 'Document Layout' processing")
    print("6. Import your documents")
    print("7. Wait for indexing to complete")
    print("-" * 40)
    input("\nPress Enter after completing the above steps...")
    
    # Step 4: Validate migration
    print("\n[4/4] Validating migration...")
    validation = migrator.validate_migration()
    
    # Generate report
    report = migrator.generate_migration_report(validation)
    print("\n" + report)
    
    # Save report
    report_file = f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_file}")
    
    # Save validation JSON
    validation_file = f"migration_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(validation_file, "w") as f:
        json.dump(validation, f, indent=2, default=str)
    print(f"Validation data saved to: {validation_file}")
    
    return 0 if validation.get("status") == "success" else 1

if __name__ == "__main__":
    exit(main())