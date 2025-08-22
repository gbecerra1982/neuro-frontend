"""
Azure AI Search con Búsqueda Semántica y Re-ranking
Implementación mejorada para NEURO RAG Backend
"""

import os
import logging
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import (
    QueryType,
    QueryCaptionType,
    QueryAnswerType,
    SemanticErrorMode,
    SemanticSearchOptions,
    VectorizedQuery,
    VectorQuery,
    SearchMode
)
import requests
from openai import AzureOpenAI

try:
    from utils.util_logger import GetLogger
except:
    from util_logger import GetLogger

load_dotenv()

# Configuración
LOGLEVEL = os.environ.get('LOGLEVEL', 'DEBUG').upper()
logger = GetLogger(__name__, level=LOGLEVEL, log_file='data/app_logs.log').logger

class AzureSearchSemantic:
    """
    Clase mejorada para Azure AI Search con capacidades semánticas
    """
    
    def __init__(self):
        # Azure Search Config
        self.endpoint = os.environ.get("AZURE_SEARCH_SERVICE_ENDPOINT")
        self.api_version = os.environ.get('AZURE_SEARCH_API_VERSION', '2024-11-01-preview')
        self.admin_key = os.environ.get("AZURE_SEARCH_ADMIN_KEY")
        self.search_index = os.environ.get("AZURE_SEARCH_INDEX", "neuro-rag")
        
        # Azure OpenAI para embeddings
        self.openai_client = AzureOpenAI(
            api_key=os.environ.get("AZURE_OPENAI_STANDARD_API_KEY"),
            api_version="2024-02-01",
            azure_endpoint=os.environ.get("AZURE_OPENAI_STANDARD_ENDPOINT")
        )
        self.embedding_model = os.environ.get("EMBEDDING_MODEL", "text-embedding-ada-002")
        
        # Search Client
        self.search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.search_index,
            credential=AzureKeyCredential(self.admin_key)
        )
        
    def generate_embedding(self, text: str) -> List[float]:
        """
        Genera embeddings usando Azure OpenAI
        """
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generando embedding: {e}")
            return []
    
    def semantic_search(
        self,
        query: str,
        fecha: Optional[str] = None,
        pozo: Optional[str] = None,
        equipo: Optional[str] = None,
        use_semantic: bool = True,
        use_vector: bool = True,
        top_k: int = 20,
        semantic_config_name: str = "default"
    ) -> Dict[str, Any]:
        """
        Búsqueda semántica mejorada con múltiples capacidades
        
        Args:
            query: Consulta del usuario
            fecha: Fecha específica (YYYY-MM-DD)
            pozo: Nombre del pozo
            equipo: Código del equipo
            use_semantic: Habilitar re-ranking semántico
            use_vector: Habilitar búsqueda vectorial
            top_k: Número de resultados
            semantic_config_name: Configuración semántica a usar
        """
        try:
            logger.info(f"Búsqueda semántica - Query: {query}, Fecha: {fecha}, Pozo: {pozo}, Equipo: {equipo}")
            
            # 1. Construir filtros OData
            filters = []
            if fecha:
                filters.append(f"headers/fecha eq '{fecha}'")
            if pozo:
                filters.append(f"headers/pozo eq '{pozo}'")
            if equipo:
                filters.append(f"headers/equipo eq '{equipo}'")
            
            filter_expression = " and ".join(filters) if filters else None
            
            # 2. Preparar búsqueda vectorial si está habilitada
            vector_queries = []
            if use_vector and query:
                embedding = self.generate_embedding(query)
                if embedding:
                    vector_queries.append(
                        VectorizedQuery(
                            vector=embedding,
                            k_nearest_neighbors=top_k,
                            fields="contentVector"  # Campo con embeddings en el índice
                        )
                    )
            
            # 3. Configurar opciones semánticas
            semantic_options = None
            if use_semantic:
                semantic_options = SemanticSearchOptions(
                    configuration_name=semantic_config_name,
                    error_mode=SemanticErrorMode.PARTIAL,
                    max_wait_in_milliseconds=5000
                )
            
            # 4. Ejecutar búsqueda híbrida
            results = self.search_client.search(
                search_text=query if query else "*",
                filter=filter_expression,
                query_type=QueryType.SEMANTIC if use_semantic else QueryType.SIMPLE,
                semantic_search_options=semantic_options,
                vector_queries=vector_queries,
                query_caption=QueryCaptionType.EXTRACTIVE if use_semantic else None,
                query_answer=QueryAnswerType.EXTRACTIVE if use_semantic else None,
                top=top_k,
                include_total_count=True,
                search_mode=SearchMode.ALL
            )
            
            # 5. Procesar resultados
            output = {
                "success": True,
                "total_count": results.get_count() if hasattr(results, 'get_count') else 0,
                "search_type": self._get_search_type(use_semantic, use_vector),
                "results": [],
                "semantic_answers": [],
                "facets": results.get_facets() if hasattr(results, 'get_facets') else {}
            }
            
            # Extraer respuestas semánticas si están disponibles
            if hasattr(results, 'get_answers'):
                answers = results.get_answers()
                if answers:
                    for answer in answers:
                        output["semantic_answers"].append({
                            "text": answer.text,
                            "highlights": answer.highlights if hasattr(answer, 'highlights') else None,
                            "score": answer.score if hasattr(answer, 'score') else None
                        })
            
            # Procesar documentos
            for idx, result in enumerate(results):
                doc = {
                    "rank": idx + 1,
                    "score": result.get('@search.score', 0),
                    "id": result.get('id'),
                    "pozo": result.get('headers', {}).get('pozo'),
                    "equipo": result.get('headers', {}).get('equipo'),
                    "fecha": result.get('headers', {}).get('fecha'),
                    "content": result.get('content', '')[:500]  # Primeros 500 chars
                }
                
                # Agregar información semántica si está disponible
                if use_semantic:
                    doc["reranker_score"] = result.get('@search.reranker_score', 0)
                    
                    # Captions con highlights
                    if '@search.captions' in result:
                        captions = result['@search.captions']
                        if captions:
                            doc["caption"] = {
                                "text": captions[0].text if hasattr(captions[0], 'text') else str(captions[0]),
                                "highlights": captions[0].highlights if hasattr(captions[0], 'highlights') else None
                            }
                
                output["results"].append(doc)
            
            logger.info(f"Búsqueda completada: {output['total_count']} resultados, Tipo: {output['search_type']}")
            return output
            
        except Exception as e:
            logger.error(f"Error en búsqueda semántica: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": []
            }
    
    def hybrid_search(
        self,
        query: str,
        fecha: Optional[str] = None,
        pozo: Optional[str] = None,
        equipo: Optional[str] = None,
        alpha: float = 0.5
    ) -> Dict[str, Any]:
        """
        Búsqueda híbrida que combina BM25 + Vector + Semántico
        
        Args:
            alpha: Peso para búsqueda vectorial (0=solo texto, 1=solo vector)
        """
        logger.info(f"Búsqueda híbrida con alpha={alpha}")
        
        # La búsqueda híbrida se maneja automáticamente cuando se pasan
        # tanto search_text como vector_queries
        return self.semantic_search(
            query=query,
            fecha=fecha,
            pozo=pozo,
            equipo=equipo,
            use_semantic=True,
            use_vector=True
        )
    
    def create_semantic_configuration(self, index_name: str) -> bool:
        """
        Crea o actualiza la configuración semántica del índice
        NOTA: Debe ejecutarse una vez para configurar el índice
        """
        try:
            url = f"{self.endpoint}/indexes/{index_name}?api-version={self.api_version}"
            headers = {
                'Content-Type': 'application/json',
                'api-key': self.admin_key
            }
            
            # Configuración semántica para el índice
            semantic_config = {
                "semantic": {
                    "defaultConfiguration": "neuro-config",
                    "configurations": [
                        {
                            "name": "neuro-config",
                            "prioritizedFields": {
                                "titleField": {
                                    "fieldName": "headers/pozo"  # Campo principal
                                },
                                "prioritizedContentFields": [
                                    {
                                        "fieldName": "content"  # Contenido principal
                                    }
                                ],
                                "prioritizedKeywordsFields": [
                                    {
                                        "fieldName": "headers/equipo"
                                    },
                                    {
                                        "fieldName": "headers/fecha"
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
            
            # Obtener índice actual
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                index_def = response.json()
                
                # Actualizar con configuración semántica
                index_def.update(semantic_config)
                
                # Actualizar índice
                response = requests.put(url, json=index_def, headers=headers)
                if response.status_code in [200, 201]:
                    logger.info(f"Configuración semántica creada/actualizada para {index_name}")
                    return True
                else:
                    logger.error(f"Error actualizando configuración: {response.text}")
                    return False
            else:
                logger.error(f"Error obteniendo índice: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error creando configuración semántica: {e}")
            return False
    
    def _get_search_type(self, use_semantic: bool, use_vector: bool) -> str:
        """Determina el tipo de búsqueda realizada"""
        if use_semantic and use_vector:
            return "Híbrida (BM25 + Vector + Semántica)"
        elif use_semantic:
            return "Semántica con re-ranking"
        elif use_vector:
            return "Vectorial"
        else:
            return "Keyword (BM25)"


# Función de compatibilidad con código existente
def search_azure_semantic(search_word: str, fecha: str, pozo: str, equipo: str) -> Dict[str, Any]:
    """
    Función wrapper para mantener compatibilidad con código existente
    """
    search_client = AzureSearchSemantic()
    return search_client.semantic_search(
        query=search_word,
        fecha=fecha,
        pozo=pozo,
        equipo=equipo
    )


if __name__ == "__main__":
    # Test
    client = AzureSearchSemantic()
    
    # Test 1: Búsqueda semántica
    result = client.semantic_search(
        query="equipo de perforación DLS-168 en agosto",
        fecha="2025-08-21",
        equipo="DLS-168"
    )
    print(f"Resultados semánticos: {result['total_count']}")
    
    # Test 2: Búsqueda híbrida
    result = client.hybrid_search(
        query="novedades del pozo",
        pozo="LACh-1030(h)",
        fecha="2025-08-21"
    )
    print(f"Resultados híbridos: {result['total_count']}")