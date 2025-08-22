"""
Tool RAG mejorado con capacidades semánticas
"""

from langchain.tools import StructuredTool
from services.rag_retriever_semantic import retrieve_fn_semantic
from pydantic import BaseModel, Field
from typing import Optional
import logging

# Configurar logging
logger = logging.getLogger(__name__)

class RagSemanticToolInput(BaseModel):
    """Esquema de entrada para la herramienta RAG semántica"""
    query: Optional[str] = Field(
        default=None,
        description="Consulta en lenguaje natural (opcional, se construirá automáticamente si no se proporciona)"
    )
    pozo: Optional[str] = Field(
        default=None,
        description="Nombre del pozo (ej: LACh-1030(h))"
    )
    fecha: str = Field(
        description="Fecha en formato YYYY-MM-DD"
    )
    equipo: Optional[str] = Field(
        default=None,
        description="Nombre del equipo (opcional, ej: DLS-168)"
    )
    search_mode: str = Field(
        default="hybrid",
        description="Modo de búsqueda: 'hybrid', 'semantic', 'vector', o 'keyword'"
    )

def rag_semantic_tool_wrapper(
    query: Optional[str] = None,
    pozo: Optional[str] = None,
    fecha: str = None,
    equipo: Optional[str] = None,
    search_mode: str = "hybrid"
) -> str:
    """
    Wrapper mejorado para la herramienta RAG con búsqueda semántica
    """
    logger.info(f"[RAG_SEMANTIC_TOOL] Ejecutándose con parámetros:")
    logger.info(f"   - query: {query}")
    logger.info(f"   - pozo: {pozo}")
    logger.info(f"   - fecha: {fecha}")
    logger.info(f"   - equipo: {equipo}")
    logger.info(f"   - search_mode: {search_mode}")
    
    try:
        # Construir query automática si no se proporciona
        if not query:
            parts = []
            if equipo:
                parts.append(f"información sobre el equipo {equipo}")
            if pozo:
                parts.append(f"datos del pozo {pozo}")
            if not parts:
                parts.append("información disponible")
            
            query = " ".join(parts)
            logger.info(f"   - query generada: {query}")
        
        # Llamar a la función de retrieval semántico
        result = retrieve_fn_semantic(
            query=query,
            pozo=pozo,
            fecha=fecha,
            equipo=equipo
        )
        
        logger.info(f"[RAG_SEMANTIC_TOOL] Ejecutado exitosamente")
        
        # Log parcial del resultado para debugging
        result_str = str(result)
        logger.info(f"   - resultado (primeros 200 chars): {result_str[:200]}...")
        
        return result
        
    except Exception as e:
        logger.error(f"[RAG_SEMANTIC_TOOL] Error: {e}")
        raise

# Herramienta estructurada para LangChain
rag_semantic_tool = StructuredTool(
    name="rag_semantic_tool",
    description="""Herramienta mejorada para recuperar información sobre pozos petroleros usando búsqueda semántica y re-ranking.
    
    Capacidades:
    - Búsqueda semántica con comprensión del lenguaje natural
    - Re-ranking basado en relevancia semántica
    - Extracción automática de respuestas
    - Búsqueda híbrida (keyword + vectorial + semántica)
    
    Parámetros:
    - query: Consulta en lenguaje natural (opcional)
    - pozo: Nombre del pozo
    - fecha: Fecha en formato YYYY-MM-DD
    - equipo: Código del equipo
    - search_mode: Tipo de búsqueda ('hybrid', 'semantic', 'vector', 'keyword')
    """,
    func=rag_semantic_tool_wrapper,
    args_schema=RagSemanticToolInput,
)

# Herramienta de compatibilidad con el nombre anterior
rag_tool = rag_semantic_tool  # Alias para mantener compatibilidad


if __name__ == "__main__":
    # Test de la herramienta
    print("Testing RAG Semantic Tool...")
    
    # Test 1: Búsqueda por equipo
    result = rag_semantic_tool_wrapper(
        query="¿En qué pozo está trabajando?",
        equipo="DLS-168",
        fecha="2025-08-21",
        search_mode="hybrid"
    )
    print(f"Test 1 completado")
    
    # Test 2: Búsqueda por pozo
    result = rag_semantic_tool_wrapper(
        pozo="LACh-1030(h)",
        fecha="2025-08-21",
        search_mode="semantic"
    )
    print(f"Test 2 completado")