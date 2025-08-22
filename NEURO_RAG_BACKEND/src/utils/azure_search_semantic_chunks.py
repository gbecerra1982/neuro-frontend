"""
Azure AI Search client optimized for semantic chunks created by Document Layout Skill
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import (
    QueryType,
    QueryCaptionType,
    QueryAnswerType,
    SemanticErrorMode,
    VectorizedQuery,
    VectorQuery,
    SearchMode,
    VectorFilterMode
)
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SemanticChunkSearchClient:
    """
    Optimized search client for semantic chunks created by Document Layout Skill
    """
    
    def __init__(self):
        # Azure Search configuration
        self.endpoint = os.environ.get("AZURE_SEARCH_SERVICE_ENDPOINT")
        self.api_key = os.environ.get("AZURE_SEARCH_ADMIN_KEY")
        self.index_name = os.environ.get("AZURE_SEARCH_INDEX", "neuro-rag-semantic-chunks")
        
        # Initialize search client
        self.search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(self.api_key)
        )
        
        # OpenAI for query embeddings
        self.openai_client = AzureOpenAI(
            api_key=os.environ.get("AZURE_OPENAI_STANDARD_API_KEY"),
            api_version="2024-02-01",
            azure_endpoint=os.environ.get("AZURE_OPENAI_STANDARD_ENDPOINT")
        )
        self.embedding_model = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
        
        logger.info(f"SemanticChunkSearchClient initialized for index: {self.index_name}")
    
    def search_semantic_chunks(
        self,
        query: str,
        pozo: Optional[str] = None,
        equipo: Optional[str] = None,
        fecha: Optional[str] = None,
        yacimiento: Optional[str] = None,
        search_mode: str = "hybrid",
        top_k: int = 10,
        include_parent_context: bool = True
    ) -> Dict[str, Any]:
        """
        Search semantic chunks with hierarchical context preservation
        
        Args:
            query: Natural language query
            pozo: Well filter
            equipo: Equipment filter
            fecha: Date filter (YYYY-MM-DD)
            yacimiento: Field filter
            search_mode: "hybrid", "semantic", "vector", or "keyword"
            top_k: Number of chunks to retrieve
            include_parent_context: Include sibling chunks for context
        
        Returns:
            Search results with semantic chunks and metadata
        """
        try:
            logger.info(f"Searching semantic chunks: query='{query[:50]}...', mode={search_mode}")
            
            # Build OData filter expression
            filter_expression = self._build_filter(pozo, equipo, fecha, yacimiento)
            
            # Prepare search parameters based on mode
            search_params = self._prepare_search_params(query, search_mode, filter_expression, top_k)
            
            # Execute search
            results = self.search_client.search(**search_params)
            
            # Process results
            processed_results = self._process_chunk_results(results, include_parent_context)
            
            # If parent context requested, fetch sibling chunks
            if include_parent_context and processed_results['chunks']:
                processed_results = self._enrich_with_context(processed_results)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Search error: {str(e)}", exc_info=True)
            return {
                'error': True,
                'message': str(e),
                'chunks': []
            }
    
    def _build_filter(
        self,
        pozo: Optional[str],
        equipo: Optional[str],
        fecha: Optional[str],
        yacimiento: Optional[str]
    ) -> Optional[str]:
        """
        Build OData filter expression for metadata fields
        """
        filters = []
        
        if pozo:
            filters.append(f"pozo eq '{pozo}'")
        
        if equipo:
            filters.append(f"equipo eq '{equipo}'")
        
        if fecha:
            # Handle date format
            try:
                date_obj = datetime.strptime(fecha, '%Y-%m-%d')
                date_str = date_obj.strftime('%Y-%m-%dT00:00:00Z')
                filters.append(f"fecha ge {date_str} and fecha lt {date_obj.strftime('%Y-%m-%d')}T23:59:59Z")
            except:
                filters.append(f"fecha eq '{fecha}'")
        
        if yacimiento:
            filters.append(f"yacimiento eq '{yacimiento}'")
        
        return " and ".join(filters) if filters else None
    
    def _prepare_search_params(
        self,
        query: str,
        search_mode: str,
        filter_expression: Optional[str],
        top_k: int
    ) -> Dict[str, Any]:
        """
        Prepare search parameters based on search mode
        """
        params = {
            'search_text': query if query else "*",
            'filter': filter_expression,
            'top': top_k,
            'include_total_count': True,
            'search_mode': SearchMode.ALL
        }
        
        # Configure based on search mode
        if search_mode in ["hybrid", "semantic"]:
            # Semantic search configuration
            params.update({
                'query_type': QueryType.SEMANTIC,
                'semantic_configuration_name': 'neuro-semantic-config',
                'query_caption': QueryCaptionType.EXTRACTIVE,
                'query_answer': QueryAnswerType.EXTRACTIVE
            })
        
        if search_mode in ["hybrid", "vector"]:
            # Vector search configuration
            embedding = self._generate_embedding(query)
            if embedding:
                params['vector_queries'] = [
                    VectorizedQuery(
                        vector=embedding,
                        k_nearest_neighbors=top_k,
                        fields="text_vector"
                    )
                ]
                
                # For hybrid, use vector filter mode
                if search_mode == "hybrid":
                    params['vector_filter_mode'] = VectorFilterMode.PRE_FILTER
        
        # Select specific fields to return
        params['select'] = [
            'chunk_id', 'parent_id', 'chunk_content', 'chunk_index',
            'header_1', 'header_2', 'header_3',
            'pozo', 'equipo', 'fecha', 'yacimiento',
            'tipo_documento', 'metadata_json'
        ]
        
        return params
    
    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding vector for query
        """
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text[:8000]  # Limit text length
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            return None
    
    def _process_chunk_results(
        self,
        results: Any,
        include_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Process search results with chunk hierarchy preservation
        """
        processed = {
            'total_count': 0,
            'chunks': [],
            'semantic_answers': [],
            'hierarchical_structure': {},
            'metadata': {
                'unique_pozos': set(),
                'unique_equipos': set(),
                'date_range': {'min': None, 'max': None}
            }
        }
        
        # Get total count if available
        if hasattr(results, 'get_count'):
            processed['total_count'] = results.get_count()
        
        # Extract semantic answers if available
        if hasattr(results, 'get_answers'):
            answers = results.get_answers()
            if answers:
                for answer in answers:
                    processed['semantic_answers'].append({
                        'text': answer.text if hasattr(answer, 'text') else str(answer),
                        'score': answer.score if hasattr(answer, 'score') else None,
                        'highlights': answer.highlights if hasattr(answer, 'highlights') else []
                    })
        
        # Process each chunk
        for idx, result in enumerate(results):
            chunk = {
                'rank': idx + 1,
                'chunk_id': result.get('chunk_id'),
                'parent_id': result.get('parent_id'),
                'content': result.get('chunk_content', ''),
                'chunk_index': result.get('chunk_index', 0),
                'headers': {
                    'h1': result.get('header_1'),
                    'h2': result.get('header_2'),
                    'h3': result.get('header_3')
                },
                'metadata': {
                    'pozo': result.get('pozo'),
                    'equipo': result.get('equipo'),
                    'fecha': result.get('fecha'),
                    'yacimiento': result.get('yacimiento'),
                    'tipo_documento': result.get('tipo_documento')
                },
                'score': result.get('@search.score', 0),
                'reranker_score': result.get('@search.reranker_score', 0)
            }
            
            # Add captions if available
            if '@search.captions' in result:
                captions = result['@search.captions']
                if captions and len(captions) > 0:
                    chunk['caption'] = {
                        'text': captions[0].text if hasattr(captions[0], 'text') else str(captions[0]),
                        'highlights': captions[0].highlights if hasattr(captions[0], 'highlights') else []
                    }
            
            # Parse additional metadata if available
            if result.get('metadata_json'):
                try:
                    import json
                    chunk['extended_metadata'] = json.loads(result['metadata_json'])
                except:
                    pass
            
            processed['chunks'].append(chunk)
            
            # Update metadata aggregations
            if chunk['metadata']['pozo']:
                processed['metadata']['unique_pozos'].add(chunk['metadata']['pozo'])
            if chunk['metadata']['equipo']:
                processed['metadata']['unique_equipos'].add(chunk['metadata']['equipo'])
            
            # Build hierarchical structure
            parent_id = chunk['parent_id']
            if parent_id not in processed['hierarchical_structure']:
                processed['hierarchical_structure'][parent_id] = []
            processed['hierarchical_structure'][parent_id].append(chunk)
        
        # Convert sets to lists
        processed['metadata']['unique_pozos'] = list(processed['metadata']['unique_pozos'])
        processed['metadata']['unique_equipos'] = list(processed['metadata']['unique_equipos'])
        
        return processed
    
    def _enrich_with_context(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich results with sibling chunks for better context
        """
        try:
            # Get unique parent IDs
            parent_ids = set()
            for chunk in results['chunks']:
                if chunk['parent_id']:
                    parent_ids.add(chunk['parent_id'])
            
            if not parent_ids:
                return results
            
            # Fetch all chunks from same parents
            filter_expr = " or ".join([f"parent_id eq '{pid}'" for pid in parent_ids])
            
            context_results = self.search_client.search(
                search_text="*",
                filter=filter_expr,
                top=50,  # Get more chunks for context
                order_by=['parent_id', 'chunk_index']
            )
            
            # Group by parent
            context_map = {}
            for doc in context_results:
                parent_id = doc.get('parent_id')
                if parent_id not in context_map:
                    context_map[parent_id] = []
                context_map[parent_id].append({
                    'chunk_id': doc.get('chunk_id'),
                    'chunk_index': doc.get('chunk_index', 0),
                    'content': doc.get('chunk_content', ''),
                    'headers': {
                        'h1': doc.get('header_1'),
                        'h2': doc.get('header_2'),
                        'h3': doc.get('header_3')
                    }
                })
            
            # Add context to results
            results['context_chunks'] = context_map
            
            logger.info(f"Enriched with context from {len(parent_ids)} parent documents")
            
        except Exception as e:
            logger.error(f"Error enriching context: {e}")
        
        return results
    
    def get_document_reconstruction(self, parent_id: str) -> Dict[str, Any]:
        """
        Reconstruct full document from chunks
        """
        try:
            # Get all chunks for parent document
            results = self.search_client.search(
                search_text="*",
                filter=f"parent_id eq '{parent_id}'",
                order_by=['chunk_index'],
                top=1000
            )
            
            chunks = []
            metadata = None
            
            for chunk in results:
                chunks.append({
                    'index': chunk.get('chunk_index', 0),
                    'content': chunk.get('chunk_content', ''),
                    'headers': {
                        'h1': chunk.get('header_1'),
                        'h2': chunk.get('header_2'),
                        'h3': chunk.get('header_3')
                    }
                })
                
                # Get metadata from first chunk
                if not metadata:
                    metadata = {
                        'pozo': chunk.get('pozo'),
                        'equipo': chunk.get('equipo'),
                        'fecha': chunk.get('fecha'),
                        'yacimiento': chunk.get('yacimiento'),
                        'tipo_documento': chunk.get('tipo_documento')
                    }
            
            # Sort by index
            chunks.sort(key=lambda x: x['index'])
            
            # Reconstruct content
            full_content = "\n\n".join([c['content'] for c in chunks])
            
            return {
                'parent_id': parent_id,
                'content': full_content,
                'chunks': chunks,
                'metadata': metadata,
                'total_chunks': len(chunks)
            }
            
        except Exception as e:
            logger.error(f"Error reconstructing document: {e}")
            return None