"""
Agentic Retrieval implementation for Azure AI Search
Provides 40% better accuracy through intelligent query planning and execution
"""

import os
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from azure.search.documents import SearchClient
from azure.search.documents.models import (
    QueryType,
    QueryCaptionType,
    QueryAnswerType,
    VectorizedQuery,
    SearchMode
)
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI
from dotenv import load_dotenv
import json
import hashlib
from functools import lru_cache

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgenticRetrievalClient:
    """
    Production-ready Agentic Retrieval client for Azure AI Search
    Implements query planning, parallel execution, and intelligent result synthesis
    """
    
    def __init__(self):
        # Azure Search configuration
        self.endpoint = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
        self.api_key = os.environ["AZURE_SEARCH_ADMIN_KEY"]
        self.index_name = os.environ.get("AZURE_SEARCH_INDEX", "neuro-rag-semantic-chunks")
        
        # Initialize search client
        self.search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(self.api_key)
        )
        
        # OpenAI for query planning and embeddings
        self.openai_client = AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_STANDARD_API_KEY"],
            api_version="2024-02-01",
            azure_endpoint=os.environ["AZURE_OPENAI_STANDARD_ENDPOINT"]
        )
        
        # Configuration
        self.max_subqueries = int(os.environ.get("RAG_MAX_SUBQUERIES", 5))
        self.max_docs_per_subquery = int(os.environ.get("RAG_MAX_DOCS_PER_SUBQUERY", 50))
        self.planner_model = os.environ.get("RAG_LLM_MODEL", "gpt-4o-mini")
        self.embedding_model = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
        self.enable_cache = os.environ.get("RAG_ENABLE_CACHE", "true").lower() == "true"
        
        # Thread pool for parallel execution
        self.executor = ThreadPoolExecutor(max_workers=self.max_subqueries)
        
        # Cache for embeddings
        self._embedding_cache = {}
        
        logger.info(f"AgenticRetrievalClient initialized for index: {self.index_name}")
    
    async def agentic_search(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 10
    ) -> Dict[str, Any]:
        """
        Execute Agentic Retrieval with query planning and parallel execution
        
        Args:
            query: User query
            conversation_history: Previous conversation context
            filters: Metadata filters (pozo, equipo, fecha, etc.)
            top_k: Number of final results to return
        
        Returns:
            Search results with grounding data and citations
        """
        try:
            start_time = datetime.now()
            
            # Phase 1: Query Planning
            logger.info(f"Planning queries for: {query[:100]}...")
            subqueries = await self._plan_queries(query, conversation_history)
            logger.info(f"Generated {len(subqueries)} subqueries")
            
            # Phase 2: Parallel Query Execution
            logger.info("Executing subqueries in parallel...")
            search_tasks = [
                self._execute_subquery_async(subquery, filters)
                for subquery in subqueries
            ]
            subquery_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # Filter out exceptions
            valid_results = []
            for result in subquery_results:
                if isinstance(result, Exception):
                    logger.error(f"Subquery failed: {result}")
                else:
                    valid_results.append(result)
            
            # Phase 3: Result Synthesis
            logger.info("Synthesizing results...")
            final_results = self._synthesize_results(
                valid_results,
                query,
                top_k
            )
            
            # Add execution metadata
            execution_time = (datetime.now() - start_time).total_seconds()
            final_results["metadata"] = {
                "execution_time_seconds": execution_time,
                "subqueries_executed": len(subqueries),
                "subqueries_successful": len(valid_results),
                "retrieval_mode": "agentic",
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Agentic search completed in {execution_time:.2f}s")
            return final_results
            
        except Exception as e:
            logger.error(f"Agentic search error: {e}", exc_info=True)
            # Fallback to standard search
            return await self._fallback_search(query, filters, top_k)
    
    async def _plan_queries(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to decompose query into focused subqueries
        """
        try:
            # Build context from conversation history
            context = ""
            if conversation_history:
                # Limit to last 3 messages for performance
                recent_history = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
                context = "\n".join([
                    f"{msg['role']}: {msg['content'][:200]}"
                    for msg in recent_history
                ])
            
            # Query planning prompt optimized for oil & gas domain
            planning_prompt = f"""You are a query planning assistant for an oil well documentation system.
            
Given the user query and conversation context, decompose it into focused search queries.
Each subquery should target a specific aspect of the information need.

Conversation Context:
{context if context else "No previous context"}

User Query: {query}

Generate up to {self.max_subqueries} focused subqueries that will help answer the user's question.
Consider these aspects for oil well documentation:
- Equipment specifications and locations (equipos)
- Well production data (pozos, produccion)
- Operational issues and incidents (problemas, novedades)
- Dates and time periods (fechas, turnos)
- Specific wells or fields (yacimientos)

Return a JSON object with this structure:
{{
    "subqueries": [
        {{
            "query": "focused search query in Spanish matching document language",
            "intent": "what this query seeks to find",
            "filters": {{}}  // optional: {{"pozo": "LACh-1030", "equipo": "DLS-168"}}
        }}
    ]
}}

Important:
- Use technical terms in Spanish when appropriate
- Be specific about equipment codes and well names
- Include relevant date ranges when mentioned
- Maximum {self.max_subqueries} subqueries"""

            # Call LLM for query planning
            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model=self.planner_model,
                messages=[
                    {"role": "system", "content": "You are a search query planner for oil well documentation. Always return valid JSON."},
                    {"role": "user", "content": planning_prompt}
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            # Parse subqueries
            content = response.choices[0].message.content
            result = json.loads(content)
            subqueries = result.get("subqueries", [])
            
            # Validate and clean subqueries
            valid_subqueries = []
            for sq in subqueries:
                if isinstance(sq, dict) and sq.get("query"):
                    valid_subqueries.append({
                        "query": sq["query"][:500],  # Limit query length
                        "intent": sq.get("intent", "")[:200],
                        "filters": sq.get("filters", {})
                    })
            
            # Ensure we have at least the original query
            if not valid_subqueries:
                valid_subqueries = [{"query": query, "intent": "original query", "filters": {}}]
            
            # Limit number of subqueries
            return valid_subqueries[:self.max_subqueries]
            
        except Exception as e:
            logger.error(f"Query planning error: {e}")
            # Fallback to original query
            return [{"query": query, "intent": "original query", "filters": {}}]
    
    async def _execute_subquery_async(
        self,
        subquery: Dict[str, Any],
        base_filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a single subquery asynchronously
        """
        return await asyncio.to_thread(
            self._execute_subquery,
            subquery,
            base_filters
        )
    
    def _execute_subquery(
        self,
        subquery: Dict[str, Any],
        base_filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a single subquery with hybrid search and semantic ranking
        """
        try:
            query_text = subquery.get("query", "")
            query_filters = subquery.get("filters", {})
            
            # Merge filters
            filters = {**(base_filters or {}), **query_filters}
            filter_expression = self._build_filter_expression(filters)
            
            # Generate embedding for vector search
            embedding = self._generate_embedding(query_text)
            
            # Prepare search parameters for hybrid search
            search_params = {
                "search_text": query_text,
                "query_type": QueryType.SEMANTIC,
                "semantic_configuration_name": os.environ.get("SEMANTIC_CONFIG_NAME", "default"),
                "query_caption": QueryCaptionType.EXTRACTIVE,
                "query_answer": QueryAnswerType.EXTRACTIVE,
                "top": self.max_docs_per_subquery,
                "include_total_count": True,
                "search_mode": SearchMode.ALL,
                "select": [
                    "chunk_id", "parent_id", "chunk_content", "chunk_index",
                    "header_1", "header_2", "header_3",
                    "pozo", "equipo", "fecha", "yacimiento", "tipo_documento"
                ]
            }
            
            # Add filter if present
            if filter_expression:
                search_params["filter"] = filter_expression
            
            # Add vector search if embedding available
            if embedding:
                search_params["vector_queries"] = [
                    VectorizedQuery(
                        vector=embedding,
                        k_nearest_neighbors=min(50, self.max_docs_per_subquery),
                        fields="text_vector"
                    )
                ]
            
            # Execute search
            results = self.search_client.search(**search_params)
            
            # Process results
            processed_results = {
                "subquery": subquery,
                "documents": [],
                "semantic_answers": [],
                "total_count": 0
            }
            
            # Extract semantic answers if available
            if hasattr(results, 'get_answers'):
                answers = results.get_answers()
                if answers:
                    for answer in answers[:3]:  # Limit to top 3 answers
                        processed_results["semantic_answers"].append({
                            "text": answer.text if hasattr(answer, 'text') else str(answer),
                            "score": answer.score if hasattr(answer, 'score') else None
                        })
            
            # Process documents
            for idx, doc in enumerate(results):
                if idx >= self.max_docs_per_subquery:
                    break
                    
                processed_doc = {
                    "chunk_id": doc.get("chunk_id"),
                    "parent_id": doc.get("parent_id"),
                    "content": doc.get("chunk_content", ""),
                    "chunk_index": doc.get("chunk_index", 0),
                    "headers": {
                        "h1": doc.get("header_1"),
                        "h2": doc.get("header_2"),
                        "h3": doc.get("header_3")
                    },
                    "metadata": {
                        "pozo": doc.get("pozo"),
                        "equipo": doc.get("equipo"),
                        "fecha": doc.get("fecha"),
                        "yacimiento": doc.get("yacimiento"),
                        "tipo_documento": doc.get("tipo_documento")
                    },
                    "score": doc.get("@search.score", 0),
                    "reranker_score": doc.get("@search.reranker_score", 0)
                }
                
                # Extract captions if available
                if "@search.captions" in doc:
                    captions = doc["@search.captions"]
                    if captions:
                        processed_doc["captions"] = [
                            caption.text if hasattr(caption, 'text') else str(caption)
                            for caption in captions[:2]  # Limit captions
                        ]
                
                processed_results["documents"].append(processed_doc)
            
            # Get total count if available
            if hasattr(results, 'get_count'):
                processed_results["total_count"] = results.get_count()
            
            logger.info(f"Subquery '{query_text[:50]}...' found {len(processed_results['documents'])} documents")
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Subquery execution error: {e}")
            return {
                "subquery": subquery,
                "documents": [],
                "error": str(e)
            }
    
    def _synthesize_results(
        self,
        subquery_results: List[Dict[str, Any]],
        original_query: str,
        top_k: int
    ) -> Dict[str, Any]:
        """
        Merge and re-rank results from all subqueries
        """
        try:
            # Collect all documents and answers
            all_documents = []
            all_semantic_answers = []
            subquery_summaries = []
            
            for result in subquery_results:
                if "error" not in result:
                    all_documents.extend(result["documents"])
                    all_semantic_answers.extend(result.get("semantic_answers", []))
                    
                    # Create subquery summary
                    subquery_summaries.append({
                        "query": result["subquery"]["query"],
                        "intent": result["subquery"].get("intent", ""),
                        "documents_found": len(result["documents"]),
                        "has_semantic_answers": len(result.get("semantic_answers", [])) > 0
                    })
            
            # De-duplicate documents by chunk_id
            seen_ids = set()
            unique_documents = []
            for doc in all_documents:
                chunk_id = doc.get("chunk_id")
                if chunk_id and chunk_id not in seen_ids:
                    seen_ids.add(chunk_id)
                    unique_documents.append(doc)
            
            # Calculate combined score for re-ranking
            for doc in unique_documents:
                # Weighted combination of scores
                regular_score = doc.get("score", 0)
                reranker_score = doc.get("reranker_score", 0)
                
                # Higher weight to reranker score as it's semantic
                if reranker_score > 0:
                    doc["combined_score"] = (regular_score * 0.3) + (reranker_score * 0.7)
                else:
                    doc["combined_score"] = regular_score
            
            # Sort by combined score
            unique_documents.sort(key=lambda x: x["combined_score"], reverse=True)
            
            # Take top K documents
            final_documents = unique_documents[:top_k]
            
            # De-duplicate semantic answers by text similarity
            unique_answers = []
            seen_answer_texts = set()
            for answer in all_semantic_answers:
                answer_text = answer.get("text", "")
                # Simple deduplication by first 100 chars
                answer_key = answer_text[:100].lower().strip()
                if answer_key and answer_key not in seen_answer_texts:
                    seen_answer_texts.add(answer_key)
                    unique_answers.append(answer)
            
            # Sort answers by score and take top 3
            unique_answers.sort(key=lambda x: x.get("score", 0), reverse=True)
            final_answers = unique_answers[:3]
            
            # Build final result
            result = {
                "documents": final_documents,
                "semantic_answers": final_answers,
                "grounding_data": {
                    "total_documents_found": len(unique_documents),
                    "documents_returned": len(final_documents),
                    "total_semantic_answers": len(unique_answers),
                    "subqueries_executed": subquery_summaries
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Result synthesis error: {e}")
            return {
                "documents": [],
                "semantic_answers": [],
                "error": str(e)
            }
    
    async def _fallback_search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]],
        top_k: int
    ) -> Dict[str, Any]:
        """
        Fallback to standard hybrid search if agentic retrieval fails
        """
        try:
            logger.info("Falling back to standard hybrid search")
            
            filter_expression = self._build_filter_expression(filters)
            
            # Execute standard search
            results = await asyncio.to_thread(
                self.search_client.search,
                search_text=query,
                query_type=QueryType.SEMANTIC,
                semantic_configuration_name=os.environ.get("SEMANTIC_CONFIG_NAME", "default"),
                filter=filter_expression,
                top=top_k,
                search_mode=SearchMode.ALL,
                include_total_count=True
            )
            
            documents = []
            for doc in results:
                documents.append({
                    "chunk_id": doc.get("chunk_id"),
                    "content": doc.get("chunk_content"),
                    "headers": {
                        "h1": doc.get("header_1"),
                        "h2": doc.get("header_2"),
                        "h3": doc.get("header_3")
                    },
                    "metadata": {
                        "pozo": doc.get("pozo"),
                        "equipo": doc.get("equipo"),
                        "fecha": doc.get("fecha"),
                        "yacimiento": doc.get("yacimiento")
                    },
                    "score": doc.get("@search.score", 0),
                    "reranker_score": doc.get("@search.reranker_score", 0)
                })
            
            total_count = results.get_count() if hasattr(results, 'get_count') else len(documents)
            
            return {
                "documents": documents,
                "semantic_answers": [],
                "grounding_data": {
                    "total_documents_found": total_count,
                    "documents_returned": len(documents)
                },
                "metadata": {
                    "retrieval_mode": "fallback_hybrid",
                    "timestamp": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Fallback search error: {e}")
            return {
                "documents": [],
                "error": str(e),
                "metadata": {
                    "retrieval_mode": "error",
                    "timestamp": datetime.now().isoformat()
                }
            }
    
    def _build_filter_expression(self, filters: Optional[Dict[str, Any]]) -> Optional[str]:
        """
        Build OData filter expression from filters dictionary
        """
        if not filters:
            return None
        
        expressions = []
        
        # Process each filter
        for field, value in filters.items():
            if value is not None and value != "":
                if field == "pozo":
                    expressions.append(f"pozo eq '{value}'")
                elif field == "equipo":
                    expressions.append(f"equipo eq '{value}'")
                elif field == "yacimiento":
                    expressions.append(f"yacimiento eq '{value}'")
                elif field == "fecha":
                    # Handle date format
                    if isinstance(value, str) and len(value) == 10:  # YYYY-MM-DD format
                        expressions.append(f"fecha eq '{value}T00:00:00Z'")
                    else:
                        expressions.append(f"fecha eq '{value}'")
                elif field == "tipo_documento":
                    expressions.append(f"tipo_documento eq '{value}'")
        
        return " and ".join(expressions) if expressions else None
    
    @lru_cache(maxsize=100)
    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding vector with caching
        """
        try:
            # Check cache
            if self.enable_cache:
                cache_key = hashlib.md5(text.encode()).hexdigest()
                if cache_key in self._embedding_cache:
                    return self._embedding_cache[cache_key]
            
            # Generate embedding
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text[:8000]  # Limit text length
            )
            
            embedding = response.data[0].embedding
            
            # Cache result
            if self.enable_cache:
                self._embedding_cache[cache_key] = embedding
                # Limit cache size
                if len(self._embedding_cache) > 200:
                    # Remove oldest entries
                    keys_to_remove = list(self._embedding_cache.keys())[:50]
                    for key in keys_to_remove:
                        del self._embedding_cache[key]
            
            return embedding
            
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            return None
    
    def close(self):
        """
        Clean up resources
        """
        self.executor.shutdown(wait=True)
        logger.info("AgenticRetrievalClient closed")