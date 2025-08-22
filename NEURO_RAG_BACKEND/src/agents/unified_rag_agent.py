"""
Agente RAG Unificado - Arquitectura Simplificada
Elimina capas innecesarias de orquestación
"""

from typing import Dict, Any, Optional, Tuple
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from llm.llm import llm_gpt_4o_mini
from config.settings import CURRENT_DATE, CURRENT_DAY, LOGLEVEL
from config.memory import get_memory_checkpointer
from utils.util_logger import GetLogger
from utils.utils_azure_search_semantic import AzureSearchSemantic
import json
import logging

logger = GetLogger(__name__, level=LOGLEVEL, log_file='data/app_logs.log').logger

class UnifiedRAGAgent:
    """
    Agente RAG unificado que combina:
    1. Triage de relevancia
    2. Búsqueda semántica
    3. Formateo de respuesta
    
    Elimina las 3 capas de orquestación innecesarias
    """
    
    def __init__(self):
        self.llm = llm_gpt_4o_mini
        self.search_client = AzureSearchSemantic()
        self.memory = get_memory_checkpointer()
        
        # Prompt unificado para análisis y respuesta
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", """Eres un asistente especializado en pozos petroleros de Vaca Muerta.
            
CONTEXTO:
- Fecha actual: {current_date}
- Día: {current_day}
- Tienes acceso a información sobre pozos, equipos y yacimientos

CAPACIDADES:
1. Búsqueda semántica con re-ranking
2. Extracción de respuestas directas
3. Análisis contextual de documentos

INSTRUCCIONES:
1. Analiza la pregunta del usuario
2. Si es relevante a pozos/equipos/yacimientos, procede con la búsqueda
3. Si no es relevante, indica que está fuera del alcance
4. Presenta la información de forma clara y estructurada

FORMATO DE RESPUESTA:
- Resume los hallazgos principales
- Proporciona detalles específicos cuando estén disponibles
- Indica la fuente (pozo/equipo/fecha) de la información"""),
            ("user", "{question}\n\nInformación recuperada:\n{search_results}")
        ])
        
        # Prompt para triage rápido
        self.triage_prompt = ChatPromptTemplate.from_messages([
            ("system", """Determina si la pregunta es sobre pozos petroleros de Vaca Muerta.
Responde SOLO con JSON: {"relevant": true/false, "reason": "breve explicación"}"""),
            ("user", "{question}")
        ])
    
    def process_query(
        self,
        question: str,
        session_id: str = "default_session"
    ) -> Tuple[str, str]:
        """
        Procesa una consulta de principio a fin
        """
        logger.info(f"[UnifiedRAG] Procesando: {question}")
        
        # 1. Triage rápido
        if not self._is_relevant(question):
            return "Esta consulta está fuera del alcance. Solo puedo responder sobre pozos, equipos y yacimientos de Vaca Muerta.", session_id
        
        # 2. Extraer entidades de la pregunta
        entities = self._extract_entities(question)
        logger.info(f"[UnifiedRAG] Entidades detectadas: {entities}")
        
        # 3. Búsqueda semántica directa
        search_results = self._search(
            query=question,
            pozo=entities.get("pozo"),
            equipo=entities.get("equipo"),
            fecha=entities.get("fecha", CURRENT_DATE)
        )
        
        # 4. Generar respuesta contextual
        response = self._generate_response(question, search_results)
        
        # 5. Guardar en memoria si está disponible
        if self.memory:
            self._save_to_memory(session_id, question, response)
        
        return response, session_id
    
    def _is_relevant(self, question: str) -> bool:
        """
        Triage rápido de relevancia
        """
        try:
            # Heurística rápida por palabras clave
            keywords = ["pozo", "equipo", "yacimiento", "producción", "DLS", "LACh", 
                       "vaca muerta", "perforación", "extracción", "petrolero"]
            
            question_lower = question.lower()
            if any(kw in question_lower for kw in keywords):
                return True
            
            # Si no hay keywords obvias, usar LLM para decidir
            response = self.llm.invoke(
                self.triage_prompt.format(question=question)
            )
            
            try:
                result = json.loads(response.content)
                return result.get("relevant", False)
            except:
                # En caso de duda, permitir
                return True
                
        except Exception as e:
            logger.error(f"[UnifiedRAG] Error en triage: {e}")
            return True  # En caso de error, permitir
    
    def _extract_entities(self, question: str) -> Dict[str, Any]:
        """
        Extrae entidades (pozo, equipo, fecha) de la pregunta
        """
        import re
        
        entities = {}
        
        # Buscar códigos de equipo (ej: DLS-168)
        equipo_pattern = r'\b[A-Z]{2,4}-\d{2,4}\b'
        equipo_match = re.search(equipo_pattern, question)
        if equipo_match:
            entities["equipo"] = equipo_match.group()
        
        # Buscar nombres de pozos (ej: LACh-1030(h))
        pozo_pattern = r'\b[A-Z][A-Za-z]{2,4}-\d{3,4}\(?h?\)?'
        pozo_match = re.search(pozo_pattern, question)
        if pozo_match:
            entities["pozo"] = pozo_match.group()
        
        # Buscar fechas (YYYY-MM-DD o "agosto", "ayer", etc.)
        fecha_pattern = r'\d{4}-\d{2}-\d{2}'
        fecha_match = re.search(fecha_pattern, question)
        if fecha_match:
            entities["fecha"] = fecha_match.group()
        
        # Buscar referencias temporales
        if "hoy" in question.lower():
            entities["fecha"] = CURRENT_DATE
        elif "ayer" in question.lower():
            from datetime import datetime, timedelta
            yesterday = datetime.now() - timedelta(days=1)
            entities["fecha"] = yesterday.strftime('%Y-%m-%d')
        
        return entities
    
    def _search(
        self,
        query: str,
        pozo: Optional[str] = None,
        equipo: Optional[str] = None,
        fecha: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta búsqueda semántica con chunking inteligente
        """
        try:
            # Búsqueda semántica con re-ranking
            results = self.search_client.semantic_search(
                query=query,
                fecha=fecha,
                pozo=pozo,
                equipo=equipo,
                use_semantic=True,
                use_vector=True,
                top_k=5  # Solo top 5 después de re-ranking
            )
            
            if not results.get("success"):
                logger.error(f"[UnifiedRAG] Búsqueda falló: {results.get('error')}")
                return {"error": True, "message": "No se pudo realizar la búsqueda"}
            
            # Procesar resultados para chunking si son muy grandes
            processed_results = self._process_large_documents(results)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"[UnifiedRAG] Error en búsqueda: {e}")
            return {"error": True, "message": str(e)}
    
    def _process_large_documents(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Procesa documentos grandes dividiéndolos en chunks
        """
        MAX_CONTENT_LENGTH = 1000  # Caracteres por chunk
        
        processed = {
            "total_results": results.get("total_count", 0),
            "search_type": results.get("search_type"),
            "chunks": [],
            "semantic_answers": results.get("semantic_answers", [])
        }
        
        for doc in results.get("results", []):
            content = doc.get("content", "")
            
            if len(content) > MAX_CONTENT_LENGTH:
                # Dividir en chunks inteligentes
                chunks = self._smart_chunk(content, MAX_CONTENT_LENGTH)
                
                for idx, chunk in enumerate(chunks):
                    processed["chunks"].append({
                        "pozo": doc.get("pozo"),
                        "equipo": doc.get("equipo"),
                        "fecha": doc.get("fecha"),
                        "chunk_id": f"{doc.get('id')}_{idx}",
                        "content": chunk,
                        "relevance_score": doc.get("reranker_score", doc.get("score", 0))
                    })
            else:
                processed["chunks"].append({
                    "pozo": doc.get("pozo"),
                    "equipo": doc.get("equipo"),
                    "fecha": doc.get("fecha"),
                    "content": content,
                    "relevance_score": doc.get("reranker_score", doc.get("score", 0))
                })
        
        return processed
    
    def _smart_chunk(self, text: str, max_length: int) -> list:
        """
        Divide texto en chunks inteligentes preservando contexto
        """
        # Dividir por párrafos primero
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) < max_length:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _generate_response(self, question: str, search_results: Dict[str, Any]) -> str:
        """
        Genera respuesta final usando LLM con contexto
        """
        try:
            # Formatear resultados de búsqueda
            if search_results.get("error"):
                return f"No se pudo obtener información: {search_results.get('message')}"
            
            # Construir contexto desde chunks
            context_parts = []
            
            # Agregar respuestas semánticas si existen
            if search_results.get("semantic_answers"):
                context_parts.append("## Respuestas Directas:")
                for answer in search_results["semantic_answers"][:2]:
                    context_parts.append(f"- {answer['text']}")
                context_parts.append("")
            
            # Agregar chunks relevantes
            context_parts.append("## Información Detallada:")
            for chunk in search_results.get("chunks", [])[:5]:  # Top 5 chunks
                header = f"\n[{chunk.get('pozo', 'N/A')} | {chunk.get('equipo', 'N/A')} | {chunk.get('fecha', 'N/A')}]"
                context_parts.append(header)
                context_parts.append(chunk.get("content", "")[:500])
            
            search_context = "\n".join(context_parts)
            
            # Generar respuesta con LLM
            response = self.llm.invoke(
                self.prompt_template.format(
                    current_date=CURRENT_DATE,
                    current_day=CURRENT_DAY,
                    question=question,
                    search_results=search_context
                )
            )
            
            return response.content
            
        except Exception as e:
            logger.error(f"[UnifiedRAG] Error generando respuesta: {e}")
            return f"Se encontró información pero hubo un error al procesarla: {str(e)}"
    
    def _save_to_memory(self, session_id: str, question: str, response: str):
        """
        Guarda interacción en memoria si está disponible
        """
        try:
            if self.memory:
                # Implementar guardado en memoria
                pass
        except Exception as e:
            logger.error(f"[UnifiedRAG] Error guardando en memoria: {e}")


# Función de compatibilidad para reemplazar procesar_consulta_langgraph
def procesar_consulta_unificada(
    user_question: str,
    session_id: str = "default_session"
) -> Tuple[str, str]:
    """
    Reemplazo directo para procesar_consulta_langgraph con arquitectura simplificada
    """
    agent = UnifiedRAGAgent()
    return agent.process_query(user_question, session_id)


if __name__ == "__main__":
    # Test
    agent = UnifiedRAGAgent()
    
    # Test 1: Consulta sobre equipo
    response, session = agent.process_query(
        "En qué pozo se encuentra el equipo DLS-168?",
        "test_session"
    )
    print(f"Respuesta: {response[:200]}...")
    
    # Test 2: Consulta sobre pozo
    response, session = agent.process_query(
        "Novedades del pozo LACh-1030(h)",
        "test_session"
    )
    print(f"Respuesta: {response[:200]}...")