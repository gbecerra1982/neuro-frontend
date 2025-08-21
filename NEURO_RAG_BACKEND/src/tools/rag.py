from langchain.tools import Tool, StructuredTool
from services.rag_retriever import retrieve_fn
from pydantic import BaseModel, Field
from typing import Optional
import logging
 
# Configurar logging
logger = logging.getLogger(__name__)
 
 
class RagToolInput(BaseModel):
    pozo: Optional[str] = Field(description="Nombre del pozo (ej: LACh-1030(h))")
    fecha: str = Field(description="Fecha en formato YYYY-MM-DD")
    equipo: Optional[str] = Field(default=None, description="Nombre del equipo (opcional)")
 
 
def rag_tool_wrapper(pozo, fecha: str, equipo= None) -> str:
    """Wrapper para logging de la herramienta RAG"""
    logger.info(f"  RAG_TOOL ejecutándose con parámetros:")
    logger.info(f"   - pozo: {pozo}")
    logger.info(f"   - fecha: {fecha}")
    logger.info(f"   - equipo: {equipo}")
   
    try:
        result = retrieve_fn(pozo, fecha, equipo)
        logger.info(f"RAG_TOOL ejecutado exitosamente")
        logger.info(f"   - resultado: {result[:200]}...")  # Primeros 200 chars
        return result
    except Exception as e:
        logger.error(f"Error en RAG_TOOL: {e}")
        raise
 
 
rag_tool = StructuredTool(
    name="rag_tool",
    description="Tool encargada de recuperar información sobre pozos petroleros. Parámetros: pozo (nombre del pozo), fecha (YYYY-MM-DD), equipo (opcional)",
    func=rag_tool_wrapper,
    args_schema=RagToolInput,
)