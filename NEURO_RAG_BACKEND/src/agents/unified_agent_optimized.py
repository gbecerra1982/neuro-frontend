"""
Optimized Unified RAG Agent for Production
Minimizes LLM calls and maximizes performance
"""

import os
import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import hashlib
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from dotenv import load_dotenv
from openai import AzureOpenAI
from utils.agentic_retrieval_client import AgenticRetrievalClient

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QueryType(Enum):
    """Query classification to avoid unnecessary LLM calls"""
    SIMPLE_LOOKUP = "simple_lookup"      # Direct search, no LLM needed
    COMPLEX_QUERY = "complex_query"      # Requires query planning
    AGGREGATION = "aggregation"          # Multiple data points
    CONVERSATIONAL = "conversational"    # Requires context understanding

@dataclass
class QueryIntent:
    """Structured query intent to guide processing"""
    query_type: QueryType
    entities: Dict[str, Any]
    requires_llm: bool
    search_strategy: str

class OptimizedUnifiedAgent:
    """
    Production-ready unified agent with minimal LLM calls
    Replaces 3-layer architecture with single intelligent agent
    """
    
    def __init__(self):
        # Azure OpenAI configuration
        self.openai_client = AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_STANDARD_API_KEY"],
            api_version="2024-02-01",
            azure_endpoint=os.environ["AZURE_OPENAI_STANDARD_ENDPOINT"]
        )
        
        # Model configuration - using faster model for efficiency
        self.model = os.environ.get("UNIFIED_AGENT_MODEL", "gpt-4o-mini")
        self.temperature = float(os.environ.get("UNIFIED_AGENT_TEMPERATURE", "0.7"))
        self.max_tokens = int(os.environ.get("UNIFIED_AGENT_MAX_TOKENS", "2000"))
        
        # Initialize Agentic Retrieval client
        self.search_client = AgenticRetrievalClient()
        
        # Cache configuration
        self.enable_cache = os.environ.get("RAG_ENABLE_CACHE", "true").lower() == "true"
        self.cache_ttl = int(os.environ.get("RAG_CACHE_TTL_SECONDS", "300"))
        self._response_cache = {}
        self._cache_timestamps = {}
        
        # Query patterns for classification (no LLM needed)
        self.simple_patterns = [
            "ubicacion", "donde esta", "equipo", "pozo",
            "fecha", "turno", "reporte", "documento"
        ]
        
        self.complex_patterns = [
            "problemas y", "comparar", "analizar", "tendencia",
            "ultimo mes", "evolucion", "correlacion"
        ]
        
        logger.info(f"OptimizedUnifiedAgent initialized with model: {self.model}")
    
    async def process_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Main entry point - processes query with minimal LLM calls
        
        Decision flow:
        1. Check cache first
        2. Classify query (no LLM)
        3. Extract entities (pattern matching when possible)
        4. Execute search (Agentic for complex, direct for simple)
        5. Generate response (LLM only when necessary)
        """
        try:
            start_time = datetime.now()
            
            # Step 1: Check cache
            if self.enable_cache:
                cached_response = self._get_cached_response(query, session_id)
                if cached_response:
                    logger.info(f"Cache hit for query: {query[:50]}...")
                    return cached_response
            
            # Step 2: Classify query intent (no LLM)
            query_intent = self._classify_query(query, conversation_history)
            logger.info(f"Query classified as: {query_intent.query_type.value}")
            
            # Step 3: Extract entities (minimize LLM usage)
            if query_intent.query_type == QueryType.SIMPLE_LOOKUP:
                # Use pattern matching for simple queries
                entities = self._extract_entities_pattern(query)
            else:
                # Use LLM only for complex entity extraction
                entities = await self._extract_entities_llm(query, conversation_history)
            
            query_intent.entities = entities
            
            # Step 4: Execute search based on query type
            search_results = await self._execute_search(
                query, 
                query_intent, 
                conversation_history
            )
            
            # Step 5: Generate response (optimize LLM usage)
            if query_intent.requires_llm:
                response = await self._generate_response_llm(
                    query,
                    search_results,
                    query_intent
                )
            else:
                # Direct response for simple queries (no LLM)
                response = self._generate_direct_response(
                    query,
                    search_results,
                    query_intent
                )
            
            # Add metadata
            execution_time = (datetime.now() - start_time).total_seconds()
            response["metadata"] = {
                "execution_time": execution_time,
                "query_type": query_intent.query_type.value,
                "llm_calls": 1 if query_intent.requires_llm else 0,
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            }
            
            # Cache response
            if self.enable_cache:
                self._cache_response(query, session_id, response)
            
            logger.info(f"Query processed in {execution_time:.2f}s with {response['metadata']['llm_calls']} LLM calls")
            return response
            
        except Exception as e:
            logger.error(f"Query processing error: {e}", exc_info=True)
            return {
                "answer": "I encountered an error processing your query. Please try again.",
                "error": str(e),
                "metadata": {
                    "error": True,
                    "timestamp": datetime.now().isoformat()
                }
            }
    
    def _classify_query(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> QueryIntent:
        """
        Classify query type without LLM calls using pattern matching
        """
        query_lower = query.lower()
        
        # Check for simple lookup patterns
        is_simple = any(pattern in query_lower for pattern in self.simple_patterns)
        is_complex = any(pattern in query_lower for pattern in self.complex_patterns)
        
        # Check for conversational context
        has_context = conversation_history and len(conversation_history) > 0
        has_pronouns = any(word in query_lower for word in ["el", "ella", "eso", "este", "cual"])
        
        # Determine query type
        if has_context and has_pronouns:
            query_type = QueryType.CONVERSATIONAL
            requires_llm = True
            search_strategy = "agentic"
        elif is_complex or ("y" in query_lower and len(query.split()) > 10):
            query_type = QueryType.COMPLEX_QUERY
            requires_llm = True
            search_strategy = "agentic"
        elif "todos" in query_lower or "listar" in query_lower:
            query_type = QueryType.AGGREGATION
            requires_llm = False
            search_strategy = "direct"
        else:
            query_type = QueryType.SIMPLE_LOOKUP
            requires_llm = False
            search_strategy = "direct"
        
        return QueryIntent(
            query_type=query_type,
            entities={},
            requires_llm=requires_llm,
            search_strategy=search_strategy
        )
    
    def _extract_entities_pattern(self, query: str) -> Dict[str, Any]:
        """
        Extract entities using pattern matching (no LLM)
        """
        import re
        
        entities = {}
        query_lower = query.lower()
        
        # Extract equipment codes (e.g., DLS-168, RIG-205)
        equipment_pattern = r'\b([A-Z]{2,4}-\d{2,4})\b'
        equipment_matches = re.findall(equipment_pattern, query, re.IGNORECASE)
        if equipment_matches:
            entities["equipo"] = equipment_matches[0]
        
        # Extract well names (e.g., LACh-1030, AdCh-1117)
        well_pattern = r'\b([A-Za-z]{2,4}[Cc]h-\d{3,4}(?:\([h]\))?)\b'
        well_matches = re.findall(well_pattern, query)
        if well_matches:
            entities["pozo"] = well_matches[0]
        
        # Extract dates (YYYY-MM-DD or DD/MM/YYYY)
        date_pattern1 = r'\b(\d{4}-\d{2}-\d{2})\b'
        date_pattern2 = r'\b(\d{2}/\d{2}/\d{4})\b'
        
        date_matches = re.findall(date_pattern1, query)
        if date_matches:
            entities["fecha"] = date_matches[0]
        else:
            date_matches = re.findall(date_pattern2, query)
            if date_matches:
                # Convert to YYYY-MM-DD format
                parts = date_matches[0].split('/')
                entities["fecha"] = f"{parts[2]}-{parts[1]}-{parts[0]}"
        
        # Extract field names
        if "vaca muerta" in query_lower:
            entities["yacimiento"] = "Vaca Muerta"
        
        # Extract time references
        if "hoy" in query_lower or "today" in query_lower:
            entities["fecha"] = datetime.now().strftime("%Y-%m-%d")
        elif "ayer" in query_lower or "yesterday" in query_lower:
            from datetime import timedelta
            entities["fecha"] = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        logger.info(f"Entities extracted (pattern): {entities}")
        return entities
    
    async def _extract_entities_llm(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Extract entities using LLM only for complex cases
        """
        try:
            context = ""
            if conversation_history:
                context = "\n".join([
                    f"{msg['role']}: {msg['content'][:100]}"
                    for msg in conversation_history[-3:]
                ])
            
            prompt = f"""Extract entities from this oil well operations query.
Return ONLY a JSON object with found entities.

Context: {context if context else "None"}
Query: {query}

Extract these entities if present:
- pozo: well name (e.g., LACh-1030, AdCh-1117)
- equipo: equipment code (e.g., DLS-168, RIG-205)
- fecha: date in YYYY-MM-DD format
- yacimiento: field name (e.g., Vaca Muerta)

Return JSON only, no explanation:"""

            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an entity extractor for oil well documents. Return only JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=200,
                response_format={"type": "json_object"}
            )
            
            entities = json.loads(response.choices[0].message.content)
            logger.info(f"Entities extracted (LLM): {entities}")
            return entities
            
        except Exception as e:
            logger.error(f"Entity extraction error: {e}")
            # Fallback to pattern matching
            return self._extract_entities_pattern(query)
    
    async def _execute_search(
        self,
        query: str,
        query_intent: QueryIntent,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Execute search based on query intent
        """
        try:
            if query_intent.search_strategy == "agentic":
                # Use Agentic Retrieval for complex queries
                logger.info("Using Agentic Retrieval")
                results = await self.search_client.agentic_search(
                    query=query,
                    conversation_history=conversation_history,
                    filters=query_intent.entities,
                    top_k=10
                )
            else:
                # Use direct search for simple queries (faster)
                logger.info("Using direct search")
                results = await self.search_client._fallback_search(
                    query=query,
                    filters=query_intent.entities,
                    top_k=5
                )
            
            return results
            
        except Exception as e:
            logger.error(f"Search execution error: {e}")
            return {"documents": [], "error": str(e)}
    
    async def _generate_response_llm(
        self,
        query: str,
        search_results: Dict[str, Any],
        query_intent: QueryIntent
    ) -> Dict[str, Any]:
        """
        Generate response using LLM for complex queries
        """
        try:
            # Prepare context from search results
            context_docs = []
            for doc in search_results.get("documents", [])[:5]:
                doc_text = f"[{doc.get('chunk_id', 'Unknown')}]\n"
                doc_text += f"Content: {doc.get('content', '')[:500]}\n"
                
                metadata = doc.get("metadata", {})
                if metadata:
                    doc_text += f"Metadata: Pozo={metadata.get('pozo')}, Equipo={metadata.get('equipo')}, Fecha={metadata.get('fecha')}\n"
                
                context_docs.append(doc_text)
            
            context = "\n---\n".join(context_docs) if context_docs else "No relevant documents found."
            
            # Include semantic answers if available
            semantic_answers = search_results.get("semantic_answers", [])
            if semantic_answers:
                context += "\n\nDirect Answers:\n"
                for ans in semantic_answers[:2]:
                    context += f"- {ans.get('text', '')}\n"
            
            # Generate response
            system_prompt = """You are an assistant for oil well operations documentation.
Answer questions based on the provided context.
Be concise and specific. Use technical terms in Spanish when appropriate.
If information is not in the context, say so clearly."""

            user_prompt = f"""Context Documents:
{context}

User Question: {query}

Provide a clear, concise answer based on the context. Include specific details like equipment codes, well names, and dates when relevant."""

            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            answer = response.choices[0].message.content
            
            return {
                "answer": answer,
                "sources": [doc.get("chunk_id") for doc in search_results.get("documents", [])[:3]],
                "confidence": "high" if len(search_results.get("documents", [])) > 3 else "medium"
            }
            
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return {
                "answer": "I couldn't generate a proper response. Please try rephrasing your question.",
                "error": str(e)
            }
    
    def _generate_direct_response(
        self,
        query: str,
        search_results: Dict[str, Any],
        query_intent: QueryIntent
    ) -> Dict[str, Any]:
        """
        Generate response without LLM for simple queries
        """
        documents = search_results.get("documents", [])
        
        if not documents:
            return {
                "answer": "No se encontraron documentos relevantes para su consulta.",
                "sources": [],
                "confidence": "low"
            }
        
        # Build response from search results directly
        response_parts = []
        
        # Add main finding
        top_doc = documents[0]
        content = top_doc.get("content", "")[:500]
        metadata = top_doc.get("metadata", {})
        
        # Format based on query type
        if query_intent.query_type == QueryType.SIMPLE_LOOKUP:
            if metadata.get("equipo"):
                response_parts.append(f"Equipo {metadata['equipo']}:")
            if metadata.get("pozo"):
                response_parts.append(f"Pozo {metadata['pozo']}:")
            
            response_parts.append(content)
            
            if metadata.get("fecha"):
                response_parts.append(f"Fecha: {metadata['fecha']}")
        
        elif query_intent.query_type == QueryType.AGGREGATION:
            response_parts.append(f"Se encontraron {len(documents)} resultados:")
            for i, doc in enumerate(documents[:5], 1):
                meta = doc.get("metadata", {})
                response_parts.append(f"{i}. {meta.get('pozo', 'N/A')} - {meta.get('equipo', 'N/A')} ({meta.get('fecha', 'N/A')})")
        
        answer = "\n".join(response_parts)
        
        return {
            "answer": answer,
            "sources": [doc.get("chunk_id") for doc in documents[:3]],
            "confidence": "high" if len(documents) > 2 else "medium",
            "direct_response": True
        }
    
    def _get_cached_response(self, query: str, session_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Get cached response if available and not expired
        """
        cache_key = self._generate_cache_key(query, session_id)
        
        if cache_key in self._response_cache:
            timestamp = self._cache_timestamps.get(cache_key)
            if timestamp:
                age = (datetime.now() - timestamp).total_seconds()
                if age < self.cache_ttl:
                    logger.info(f"Cache hit (age: {age:.1f}s)")
                    return self._response_cache[cache_key]
                else:
                    # Expired, remove from cache
                    del self._response_cache[cache_key]
                    del self._cache_timestamps[cache_key]
        
        return None
    
    def _cache_response(self, query: str, session_id: Optional[str], response: Dict[str, Any]):
        """
        Cache response with timestamp
        """
        cache_key = self._generate_cache_key(query, session_id)
        self._response_cache[cache_key] = response
        self._cache_timestamps[cache_key] = datetime.now()
        
        # Limit cache size
        if len(self._response_cache) > 100:
            # Remove oldest entries
            oldest_keys = sorted(
                self._cache_timestamps.keys(),
                key=lambda k: self._cache_timestamps[k]
            )[:20]
            
            for key in oldest_keys:
                del self._response_cache[key]
                del self._cache_timestamps[key]
    
    def _generate_cache_key(self, query: str, session_id: Optional[str]) -> str:
        """
        Generate cache key from query and session
        """
        key_parts = [query.lower().strip()]
        if session_id:
            key_parts.append(session_id)
        
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    async def close(self):
        """
        Clean up resources
        """
        await self.search_client.close()
        logger.info("OptimizedUnifiedAgent closed")