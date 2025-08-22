"""
Production-ready Unified RAG Agent for NEURO RAG Backend
Combines triage, semantic search, and response generation in a single optimized flow
"""

from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from llm.llm import llm_gpt_4o_mini
from config.settings import CURRENT_DATE, CURRENT_DAY, LOGLEVEL
from config.memory import get_memory_checkpointer
from utils.util_logger import GetLogger
from utils.utils_azure_search_semantic import AzureSearchSemantic
import json
import re
import os
import hashlib
from enum import Enum

logger = GetLogger(__name__, level=LOGLEVEL, log_file='data/app_logs.log').logger

class SearchMode(Enum):
    SEMANTIC = "semantic"
    VECTOR = "vector"
    HYBRID = "hybrid"
    KEYWORD = "keyword"

class QueryType(Enum):
    POZO = "pozo"
    EQUIPO = "equipo"
    YACIMIENTO = "yacimiento"
    GENERAL = "general"

class ProductionRAGAgent:
    """
    Production-grade RAG agent with full error handling, monitoring, and optimization
    """
    
    def __init__(self):
        # Core components
        self.llm = llm_gpt_4o_mini
        self.search_client = AzureSearchSemantic()
        self.memory = get_memory_checkpointer()
        
        # Configuration from environment
        self.max_chunk_size = int(os.environ.get("RAG_CHUNK_SIZE", "1000"))
        self.max_search_results = int(os.environ.get("RAG_MAX_SEARCH_RESULTS", "10"))
        self.semantic_threshold = float(os.environ.get("RAG_SEMANTIC_THRESHOLD", "0.7"))
        self.enable_caching = os.environ.get("RAG_ENABLE_CACHE", "true").lower() == "true"
        self.search_mode = SearchMode(os.environ.get("RAG_SEARCH_MODE", "hybrid"))
        self.timeout_seconds = int(os.environ.get("RAG_TIMEOUT_SECONDS", "30"))
        
        # Cache for repeated queries
        self.cache = {} if self.enable_caching else None
        self.cache_ttl = int(os.environ.get("RAG_CACHE_TTL_SECONDS", "300"))
        
        # Initialize prompts
        self._initialize_prompts()
        
        # Load entity patterns
        self._load_entity_patterns()
        
        logger.info(f"ProductionRAGAgent initialized with search_mode={self.search_mode.value}, max_results={self.max_search_results}")
    
    def _initialize_prompts(self):
        """
        Initialize all prompt templates for production use
        """
        # Main response generation prompt
        self.response_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a specialized assistant for oil well operations in Vaca Muerta, Argentina.

CONTEXT:
- Current date: {current_date}
- Day of week: {current_day}
- Available information about wells, equipment, and fields

CAPABILITIES:
1. Semantic search with relevance ranking
2. Direct answer extraction from documents
3. Contextual analysis of operational data

INSTRUCTIONS:
1. Analyze the user's question carefully
2. Use the retrieved information to provide accurate answers
3. Structure your response clearly with relevant details
4. Always cite the source (well/equipment/date) of information
5. If information is incomplete, indicate what is missing

RESPONSE FORMAT:
- Start with a direct answer to the question
- Provide supporting details from the search results
- Include relevant metrics or operational data when available
- End with any important caveats or additional context"""),
            ("user", "Question: {question}\n\nRetrieved Information:\n{search_results}")
        ])
        
        # Triage prompt for relevance checking
        self.triage_prompt = ChatPromptTemplate.from_messages([
            ("system", """Determine if this question is about oil wells, equipment, or fields in Vaca Muerta.
Respond ONLY with valid JSON: {"relevant": true/false, "query_type": "type", "confidence": 0.0-1.0}
Query types: pozo, equipo, yacimiento, general"""),
            ("user", "{question}")
        ])
        
        # Entity extraction prompt
        self.entity_prompt = ChatPromptTemplate.from_messages([
            ("system", """Extract entities from the question. Return JSON with extracted values:
{
    "pozo": "well name if mentioned",
    "equipo": "equipment code if mentioned",
    "fecha": "date in YYYY-MM-DD format if mentioned",
    "temporal": "temporal reference (hoy, ayer, semana pasada, etc.)",
    "metrics": ["list of metrics mentioned"]
}
Return null for fields not found."""),
            ("user", "{question}")
        ])
    
    def _load_entity_patterns(self):
        """
        Load regex patterns for entity extraction
        """
        self.patterns = {
            'equipo': [
                r'\b[A-Z]{2,4}-\d{2,4}\b',  # DLS-168
                r'\bequipo\s+([A-Z0-9-]+)\b',
            ],
            'pozo': [
                r'\b[A-Z][A-Za-z]{1,4}-\d{3,4}\(?h?\)?',  # LACh-1030(h)
                r'\bpozo\s+([A-Za-z0-9-]+)\b',
            ],
            'fecha': [
                r'\d{4}-\d{2}-\d{2}',
                r'\d{1,2}/\d{1,2}/\d{4}',
                r'\d{1,2}\s+de\s+\w+\s+de\s+\d{4}',
            ],
            'temporal': {
                'hoy': 0,
                'ayer': -1,
                'anteayer': -2,
                'semana pasada': -7,
                'mes pasado': -30,
            }
        }
    
    def process_query(
        self,
        question: str,
        session_id: str = "default_session",
        force_search: bool = False
    ) -> Tuple[str, str]:
        """
        Main entry point for query processing
        
        Args:
            question: User's question
            session_id: Session identifier for memory
            force_search: Bypass cache if True
        
        Returns:
            Tuple of (response, session_id)
        """
        start_time = datetime.now()
        
        try:
            # Normalize session ID
            session_id = self._normalize_session_id(session_id)
            
            # Check cache first
            if not force_search and self.cache:
                cached_response = self._get_cached_response(question)
                if cached_response:
                    logger.info(f"Cache hit for question: {question[:50]}...")
                    return cached_response, session_id
            
            # Step 1: Triage for relevance
            triage_result = self._triage_question(question)
            if not triage_result['relevant']:
                response = "This query is outside the scope of this system. I can only answer questions about wells, equipment, and fields in Vaca Muerta oil operations."
                self._log_query(session_id, question, response, "out_of_scope", start_time)
                return response, session_id
            
            # Step 2: Extract entities
            entities = self._extract_entities_advanced(question)
            logger.info(f"Extracted entities: {entities}")
            
            # Step 3: Perform search
            search_results = self._execute_search(
                query=question,
                entities=entities,
                query_type=triage_result.get('query_type', 'general')
            )
            
            if search_results.get('error'):
                response = f"Unable to retrieve information: {search_results.get('message', 'Unknown error')}"
                self._log_query(session_id, question, response, "search_error", start_time)
                return response, session_id
            
            # Step 4: Generate response
            response = self._generate_response(question, search_results)
            
            # Step 5: Cache and log
            if self.cache:
                self._cache_response(question, response)
            
            # Step 6: Update memory
            if self.memory:
                self._update_memory(session_id, question, response, entities)
            
            self._log_query(session_id, question, response, "success", start_time)
            
            return response, session_id
            
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}", exc_info=True)
            error_response = "An error occurred while processing your query. Please try again or contact support."
            self._log_query(session_id, question, error_response, "system_error", start_time)
            return error_response, session_id
    
    def _normalize_session_id(self, session_id: str) -> str:
        """
        Normalize and validate session ID
        """
        if not session_id or session_id.strip() == "":
            return "default_session"
        
        # Remove potentially dangerous characters
        normalized = re.sub(r'[^a-zA-Z0-9_-]', '', session_id)
        
        # Limit length
        if len(normalized) > 50:
            normalized = normalized[:50]
        
        return normalized or "default_session"
    
    def _triage_question(self, question: str) -> Dict[str, Any]:
        """
        Determine if question is relevant and classify its type
        """
        try:
            # Quick keyword check first
            keywords = {
                'pozo': ['pozo', 'well', 'pozos'],
                'equipo': ['equipo', 'equipment', 'DLS', 'rig'],
                'yacimiento': ['yacimiento', 'field', 'campo', 'vaca muerta'],
                'general': ['produccion', 'production', 'petroleo', 'oil', 'gas']
            }
            
            question_lower = question.lower()
            query_type = None
            
            for qtype, words in keywords.items():
                if any(word in question_lower for word in words):
                    query_type = qtype
                    break
            
            if query_type:
                return {
                    'relevant': True,
                    'query_type': query_type,
                    'confidence': 0.8
                }
            
            # Use LLM for ambiguous cases
            response = self.llm.invoke(
                self.triage_prompt.format(question=question)
            )
            
            try:
                result = json.loads(response.content)
                return result
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse triage response: {response.content}")
                return {'relevant': False, 'query_type': 'unknown', 'confidence': 0.0}
                
        except Exception as e:
            logger.error(f"Error in triage: {str(e)}")
            # Default to allowing the query
            return {'relevant': True, 'query_type': 'general', 'confidence': 0.5}
    
    def _extract_entities_advanced(self, question: str) -> Dict[str, Any]:
        """
        Advanced entity extraction using patterns and LLM
        """
        entities = {
            'pozo': None,
            'equipo': None,
            'fecha': None,
            'temporal': None,
            'metrics': []
        }
        
        try:
            # Pattern-based extraction
            for pattern_type, patterns in self.patterns.items():
                if pattern_type == 'temporal':
                    continue
                    
                for pattern in patterns:
                    match = re.search(pattern, question, re.IGNORECASE)
                    if match:
                        entities[pattern_type] = match.group(0)
                        break
            
            # Temporal reference processing
            question_lower = question.lower()
            for temporal_key, days_offset in self.patterns['temporal'].items():
                if temporal_key in question_lower:
                    entities['temporal'] = temporal_key
                    target_date = datetime.now() + timedelta(days=days_offset)
                    entities['fecha'] = target_date.strftime('%Y-%m-%d')
                    break
            
            # If no date found, use current date
            if not entities['fecha']:
                entities['fecha'] = CURRENT_DATE
            
            # LLM-based extraction for complex cases
            if not entities['pozo'] and not entities['equipo']:
                try:
                    response = self.llm.invoke(
                        self.entity_prompt.format(question=question)
                    )
                    llm_entities = json.loads(response.content)
                    
                    # Merge LLM results with pattern results
                    for key, value in llm_entities.items():
                        if value and not entities.get(key):
                            entities[key] = value
                            
                except Exception as e:
                    logger.warning(f"LLM entity extraction failed: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error in entity extraction: {str(e)}")
        
        return entities
    
    def _execute_search(
        self,
        query: str,
        entities: Dict[str, Any],
        query_type: str
    ) -> Dict[str, Any]:
        """
        Execute optimized search based on query type and entities
        """
        try:
            # Determine search parameters based on query type
            use_semantic = self.search_mode in [SearchMode.SEMANTIC, SearchMode.HYBRID]
            use_vector = self.search_mode in [SearchMode.VECTOR, SearchMode.HYBRID]
            
            # Enhance query with context
            enhanced_query = self._enhance_query(query, entities, query_type)
            
            logger.info(f"Executing search: mode={self.search_mode.value}, query='{enhanced_query[:100]}...'")
            
            # Execute search
            search_results = self.search_client.semantic_search(
                query=enhanced_query,
                fecha=entities.get('fecha'),
                pozo=entities.get('pozo'),
                equipo=entities.get('equipo'),
                use_semantic=use_semantic,
                use_vector=use_vector,
                top_k=self.max_search_results,
                semantic_config_name="neuro-config"
            )
            
            if not search_results.get('success'):
                return {
                    'error': True,
                    'message': search_results.get('error', 'Search failed')
                }
            
            # Process and chunk large documents
            processed_results = self._process_search_results(search_results)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Search execution error: {str(e)}", exc_info=True)
            return {
                'error': True,
                'message': str(e)
            }
    
    def _enhance_query(self, query: str, entities: Dict[str, Any], query_type: str) -> str:
        """
        Enhance query with additional context for better search results
        """
        enhanced = query
        
        # Add entity context if not already in query
        if entities['pozo'] and entities['pozo'].lower() not in query.lower():
            enhanced = f"{enhanced} well {entities['pozo']}"
        
        if entities['equipo'] and entities['equipo'].lower() not in query.lower():
            enhanced = f"{enhanced} equipment {entities['equipo']}"
        
        # Add domain-specific keywords based on query type
        if query_type == 'pozo':
            enhanced = f"{enhanced} drilling production operations"
        elif query_type == 'equipo':
            enhanced = f"{enhanced} rig equipment operations status"
        elif query_type == 'yacimiento':
            enhanced = f"{enhanced} field reservoir vaca muerta"
        
        return enhanced
    
    def _process_search_results(self, search_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process search results with intelligent chunking and ranking
        """
        processed = {
            'total_results': search_results.get('total_count', 0),
            'search_type': search_results.get('search_type'),
            'chunks': [],
            'semantic_answers': search_results.get('semantic_answers', []),
            'metadata': {
                'sources': set(),
                'date_range': {'min': None, 'max': None},
                'entities_found': []
            }
        }
        
        # Process each document
        for doc in search_results.get('results', []):
            content = doc.get('content', '')
            
            # Update metadata
            if doc.get('pozo'):
                processed['metadata']['sources'].add(f"Pozo: {doc['pozo']}")
                processed['metadata']['entities_found'].append({'type': 'pozo', 'value': doc['pozo']})
            if doc.get('equipo'):
                processed['metadata']['sources'].add(f"Equipo: {doc['equipo']}")
                processed['metadata']['entities_found'].append({'type': 'equipo', 'value': doc['equipo']})
            
            # Update date range
            if doc.get('fecha'):
                if not processed['metadata']['date_range']['min'] or doc['fecha'] < processed['metadata']['date_range']['min']:
                    processed['metadata']['date_range']['min'] = doc['fecha']
                if not processed['metadata']['date_range']['max'] or doc['fecha'] > processed['metadata']['date_range']['max']:
                    processed['metadata']['date_range']['max'] = doc['fecha']
            
            # Chunk processing
            if len(content) > self.max_chunk_size:
                chunks = self._create_smart_chunks(content, self.max_chunk_size)
                
                for idx, chunk in enumerate(chunks):
                    chunk_data = {
                        'id': f"{doc.get('id', 'unknown')}_{idx}",
                        'pozo': doc.get('pozo'),
                        'equipo': doc.get('equipo'),
                        'fecha': doc.get('fecha'),
                        'content': chunk,
                        'relevance_score': doc.get('reranker_score', doc.get('score', 0)),
                        'chunk_index': idx,
                        'total_chunks': len(chunks)
                    }
                    
                    # Add caption if available
                    if 'caption' in doc and idx == 0:
                        chunk_data['caption'] = doc['caption']
                    
                    processed['chunks'].append(chunk_data)
            else:
                processed['chunks'].append({
                    'id': doc.get('id', 'unknown'),
                    'pozo': doc.get('pozo'),
                    'equipo': doc.get('equipo'),
                    'fecha': doc.get('fecha'),
                    'content': content,
                    'relevance_score': doc.get('reranker_score', doc.get('score', 0)),
                    'caption': doc.get('caption')
                })
        
        # Sort chunks by relevance score
        processed['chunks'].sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        # Convert sources set to list
        processed['metadata']['sources'] = list(processed['metadata']['sources'])
        
        return processed
    
    def _create_smart_chunks(self, text: str, max_size: int) -> List[str]:
        """
        Create intelligent chunks preserving semantic boundaries
        """
        chunks = []
        
        # Try to split by paragraphs first
        paragraphs = text.split('\n\n')
        current_chunk = ""
        
        for paragraph in paragraphs:
            # If paragraph itself is too long, split by sentences
            if len(paragraph) > max_size:
                sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 1 <= max_size:
                        current_chunk = f"{current_chunk} {sentence}".strip()
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = sentence
            else:
                # Try to add paragraph to current chunk
                if len(current_chunk) + len(paragraph) + 2 <= max_size:
                    current_chunk = f"{current_chunk}\n\n{paragraph}".strip()
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = paragraph
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _generate_response(self, question: str, search_results: Dict[str, Any]) -> str:
        """
        Generate final response using LLM with search context
        """
        try:
            # Check for errors
            if search_results.get('error'):
                return f"Unable to retrieve information: {search_results.get('message', 'Unknown error')}"
            
            # Build context from search results
            context_parts = []
            
            # Add semantic answers if available
            if search_results.get('semantic_answers'):
                context_parts.append("Direct Answers Found:")
                for idx, answer in enumerate(search_results['semantic_answers'][:3], 1):
                    score = answer.get('score', 0)
                    context_parts.append(f"{idx}. {answer['text']} (Confidence: {score:.2f})")
                context_parts.append("")
            
            # Add top chunks
            if search_results.get('chunks'):
                context_parts.append("Detailed Information:")
                
                # Group chunks by source
                chunks_by_source = {}
                for chunk in search_results['chunks'][:self.max_search_results]:
                    source_key = f"{chunk.get('pozo', 'N/A')}_{chunk.get('equipo', 'N/A')}_{chunk.get('fecha', 'N/A')}"
                    
                    if source_key not in chunks_by_source:
                        chunks_by_source[source_key] = []
                    chunks_by_source[source_key].append(chunk)
                
                # Format chunks by source
                for source_key, source_chunks in list(chunks_by_source.items())[:5]:
                    chunk = source_chunks[0]
                    header = f"\n[Source: Well={chunk.get('pozo', 'N/A')}, Equipment={chunk.get('equipo', 'N/A')}, Date={chunk.get('fecha', 'N/A')}]"
                    context_parts.append(header)
                    
                    # Add caption if available
                    if chunk.get('caption'):
                        context_parts.append(f"Summary: {chunk['caption'].get('text', '')}")
                    
                    # Add content (combine multiple chunks from same source)
                    combined_content = " ".join([c['content'][:500] for c in source_chunks[:2]])
                    context_parts.append(f"Content: {combined_content}")
            
            # Add metadata
            if search_results.get('metadata'):
                metadata = search_results['metadata']
                context_parts.append(f"\nInformation sources: {', '.join(metadata.get('sources', []))}")
                
                if metadata.get('date_range', {}).get('min'):
                    context_parts.append(f"Date range: {metadata['date_range']['min']} to {metadata['date_range']['max']}")
            
            search_context = "\n".join(context_parts)
            
            # Generate response
            response = self.llm.invoke(
                self.response_prompt.format(
                    current_date=CURRENT_DATE,
                    current_day=CURRENT_DAY,
                    question=question,
                    search_results=search_context
                )
            )
            
            return response.content
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            return "Information was found but there was an error processing it. Please try rephrasing your question."
    
    def _get_cached_response(self, question: str) -> Optional[str]:
        """
        Retrieve cached response if available and not expired
        """
        if not self.cache:
            return None
        
        # Generate cache key
        cache_key = hashlib.md5(question.lower().encode()).hexdigest()
        
        if cache_key in self.cache:
            cached_item = self.cache[cache_key]
            
            # Check if cache is still valid
            if datetime.now() - cached_item['timestamp'] < timedelta(seconds=self.cache_ttl):
                return cached_item['response']
            else:
                # Remove expired cache
                del self.cache[cache_key]
        
        return None
    
    def _cache_response(self, question: str, response: str):
        """
        Cache response for future use
        """
        if not self.cache:
            return
        
        cache_key = hashlib.md5(question.lower().encode()).hexdigest()
        
        self.cache[cache_key] = {
            'response': response,
            'timestamp': datetime.now()
        }
        
        # Limit cache size
        max_cache_size = int(os.environ.get("RAG_MAX_CACHE_SIZE", "100"))
        if len(self.cache) > max_cache_size:
            # Remove oldest entries
            sorted_cache = sorted(self.cache.items(), key=lambda x: x[1]['timestamp'])
            for key, _ in sorted_cache[:len(self.cache) - max_cache_size]:
                del self.cache[key]
    
    def _update_memory(self, session_id: str, question: str, response: str, entities: Dict[str, Any]):
        """
        Update conversation memory with interaction
        """
        try:
            if not self.memory:
                return
            
            # Store interaction in memory
            interaction = {
                'timestamp': datetime.now().isoformat(),
                'session_id': session_id,
                'question': question,
                'response': response[:500],  # Store truncated response
                'entities': entities
            }
            
            # Implementation depends on memory backend
            # This is a placeholder for actual memory update
            logger.info(f"Memory updated for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error updating memory: {str(e)}")
    
    def _log_query(self, session_id: str, question: str, response: str, status: str, start_time: datetime):
        """
        Log query for monitoring and analytics
        """
        try:
            duration = (datetime.now() - start_time).total_seconds()
            
            log_entry = {
                'timestamp': start_time.isoformat(),
                'session_id': session_id,
                'question_length': len(question),
                'response_length': len(response),
                'status': status,
                'duration_seconds': duration,
                'search_mode': self.search_mode.value
            }
            
            logger.info(f"Query processed: {json.dumps(log_entry)}")
            
        except Exception as e:
            logger.error(f"Error logging query: {str(e)}")


# Production-ready function to replace existing implementation
def process_query_production(
    user_question: str,
    session_id: str = "default_session",
    force_search: bool = False
) -> Tuple[str, str]:
    """
    Production endpoint for query processing
    
    Args:
        user_question: User's question
        session_id: Session identifier
        force_search: Bypass cache if True
    
    Returns:
        Tuple of (response, session_id)
    """
    agent = ProductionRAGAgent()
    return agent.process_query(user_question, session_id, force_search)