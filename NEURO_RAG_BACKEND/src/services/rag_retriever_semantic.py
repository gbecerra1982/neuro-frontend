"""
RAG Retriever Mejorado con Capacidades Semánticas
"""

import re
from typing import Optional, List, Dict, Any
import tiktoken
import os
from utils.utils_azure_search_semantic import AzureSearchSemantic
from utils.util_logger import GetLogger
import logging
from config.settings import LOGLEVEL, CURRENT_DATE

# Configuración
logging.basicConfig(level=logging.INFO)
logger = GetLogger(__name__, level=LOGLEVEL, log_file='data/app_logs.log').logger

class SemanticRAGRetriever:
    """
    Retriever mejorado con búsqueda semántica y re-ranking
    """
    
    def __init__(self):
        self.search_client = AzureSearchSemantic()
        self.max_tokens = int(os.environ.get("RAG_MAX_TOKENS", "10000"))
        self.encoding = "o200k_base"
        
    def retrieve_semantic(
        self,
        query: str,
        pozo: Optional[str] = None,
        fecha: Optional[str] = None,
        equipo: Optional[str] = None,
        search_mode: str = "hybrid"
    ) -> Dict[str, Any]:
        """
        Recupera información usando búsqueda semántica
        
        Args:
            query: Consulta del usuario
            pozo: Nombre del pozo
            fecha: Fecha específica
            equipo: Código del equipo
            search_mode: "semantic", "vector", "hybrid", o "keyword"
        """
        try:
            logger.info(f"[Semantic RAG] Query: {query}, Mode: {search_mode}")
            logger.info(f"[Semantic RAG] Filtros - Pozo: {pozo}, Fecha: {fecha}, Equipo: {equipo}")
            
            # Enriquecer query con contexto si está disponible
            enriched_query = self._enrich_query(query, pozo, equipo)
            
            # Determinar configuración según modo
            use_semantic = search_mode in ["semantic", "hybrid"]
            use_vector = search_mode in ["vector", "hybrid"]
            
            # Ejecutar búsqueda
            search_results = self.search_client.semantic_search(
                query=enriched_query,
                fecha=fecha,
                pozo=pozo,
                equipo=equipo,
                use_semantic=use_semantic,
                use_vector=use_vector,
                top_k=10  # Top 10 después de re-ranking
            )
            
            if not search_results.get("success"):
                return {
                    "error": True,
                    "message": search_results.get("error", "Error desconocido"),
                    "rag_result": []
                }
            
            # Procesar y formatear resultados
            formatted_results = self._format_results(search_results)
            
            # Construir respuesta contextual
            contextual_response = self._build_contextual_response(
                query=query,
                results=formatted_results,
                semantic_answers=search_results.get("semantic_answers", [])
            )
            
            return {
                "success": True,
                "rag_result": contextual_response,
                "metadata": {
                    "total_results": search_results.get("total_count", 0),
                    "search_type": search_results.get("search_type"),
                    "top_results": len(formatted_results),
                    "has_semantic_answers": len(search_results.get("semantic_answers", [])) > 0
                }
            }
            
        except Exception as e:
            logger.error(f"[Semantic RAG] Error: {e}")
            return {
                "error": True,
                "message": str(e),
                "rag_result": []
            }
    
    def _enrich_query(self, query: str, pozo: Optional[str], equipo: Optional[str]) -> str:
        """
        Enriquece la query con contexto adicional
        """
        enriched = query
        
        # Agregar contexto si no está explícito en la query
        if pozo and pozo.lower() not in query.lower():
            enriched = f"{query} pozo {pozo}"
        
        if equipo and equipo.lower() not in query.lower():
            enriched = f"{enriched} equipo {equipo}"
        
        logger.info(f"[Query Enrichment] Original: '{query}' -> Enriched: '{enriched}'")
        return enriched
    
    def _format_results(self, search_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Formatea los resultados para consumo del LLM
        """
        formatted = []
        
        for result in search_results.get("results", []):
            formatted_item = {
                "relevance_rank": result.get("rank"),
                "relevance_score": result.get("reranker_score", result.get("score", 0)),
                "pozo": result.get("pozo"),
                "equipo": result.get("equipo"),
                "fecha": result.get("fecha"),
                "contenido": result.get("content", ""),
                "resumen": None
            }
            
            # Agregar caption/highlight si está disponible
            if "caption" in result:
                formatted_item["resumen"] = result["caption"].get("text", "")
                formatted_item["highlights"] = result["caption"].get("highlights", [])
            
            formatted.append(formatted_item)
        
        return formatted
    
    def _build_contextual_response(
        self,
        query: str,
        results: List[Dict[str, Any]],
        semantic_answers: List[Dict[str, Any]]
    ) -> str:
        """
        Construye una respuesta contextual con los resultados
        """
        response_parts = []
        
        # 1. Respuestas semánticas directas (si existen)
        if semantic_answers:
            response_parts.append("## Respuestas Relevantes Encontradas:\n")
            for idx, answer in enumerate(semantic_answers, 1):
                response_parts.append(f"{idx}. {answer['text']}")
                if answer.get('score'):
                    response_parts.append(f"   (Confianza: {answer['score']:.2f})")
            response_parts.append("\n")
        
        # 2. Información detallada de documentos
        if results:
            response_parts.append("## Información Detallada:\n")
            
            # Agrupar por pozo/equipo para mejor organización
            by_entity = {}
            for result in results:
                key = result.get('pozo') or result.get('equipo') or 'General'
                if key not in by_entity:
                    by_entity[key] = []
                by_entity[key].append(result)
            
            for entity, entity_results in by_entity.items():
                response_parts.append(f"\n### {entity}:\n")
                
                for result in entity_results[:3]:  # Top 3 por entidad
                    fecha = result.get('fecha', 'Sin fecha')
                    score = result.get('relevance_score', 0)
                    
                    response_parts.append(f"**Fecha: {fecha}** (Relevancia: {score:.2f})")
                    
                    if result.get('resumen'):
                        response_parts.append(f"Resumen: {result['resumen']}")
                    
                    if result.get('contenido'):
                        # Limitar contenido a 200 caracteres
                        content = result['contenido'][:200]
                        if len(result['contenido']) > 200:
                            content += "..."
                        response_parts.append(f"Contenido: {content}\n")
        
        # 3. Metadata
        response_parts.append(f"\n---\n_Búsqueda: '{query}' | Resultados procesados: {len(results)}_")
        
        return "\n".join(response_parts)
    
    def count_tokens(self, text: str) -> int:
        """
        Cuenta tokens usando tiktoken
        """
        try:
            enc = tiktoken.get_encoding(self.encoding)
            return len(enc.encode(text))
        except Exception:
            # Fallback
            return len(text.split())


# Función de compatibilidad para reemplazar retrieve_fn
def retrieve_fn_semantic(
    pozo: Optional[str],
    fecha: str,
    equipo: Optional[str],
    query: Optional[str] = None
) -> str:
    """
    Función mejorada que reemplaza a retrieve_fn con capacidades semánticas
    """
    try:
        retriever = SemanticRAGRetriever()
        
        # Construir query si no se proporciona
        if not query:
            parts = []
            if pozo:
                parts.append(f"información del pozo {pozo}")
            if equipo:
                parts.append(f"equipo {equipo}")
            if fecha:
                parts.append(f"fecha {fecha}")
            
            query = " ".join(parts) if parts else "información disponible"
        
        # Ejecutar búsqueda semántica
        results = retriever.retrieve_semantic(
            query=query,
            pozo=pozo,
            fecha=fecha,
            equipo=equipo,
            search_mode="hybrid"  # Usar búsqueda híbrida por defecto
        )
        
        return str(results)
        
    except Exception as e:
        logger.error(f"Error en retrieve_fn_semantic: {e}")
        return str({"error": True, "rag_result": f"Error al buscar los datos: {e}"})


if __name__ == "__main__":
    # Test
    retriever = SemanticRAGRetriever()
    
    # Test 1: Búsqueda por equipo
    result = retriever.retrieve_semantic(
        query="En qué pozo se encuentra el equipo DLS-168",
        equipo="DLS-168",
        fecha="2025-08-21",
        search_mode="hybrid"
    )
    print(f"Test 1 - Equipo: {result['metadata']}")
    
    # Test 2: Búsqueda por pozo
    result = retriever.retrieve_semantic(
        query="novedades y producción",
        pozo="LACh-1030(h)",
        fecha="2025-08-21",
        search_mode="semantic"
    )
    print(f"Test 2 - Pozo: {result['metadata']}")