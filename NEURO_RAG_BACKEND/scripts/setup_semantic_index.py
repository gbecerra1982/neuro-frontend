"""
Script para configurar el índice de Azure AI Search con capacidades semánticas
Ejecutar una vez para configurar el índice correctamente
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.utils_azure_search_semantic import AzureSearchSemantic
import json

def setup_semantic_configuration():
    """
    Configura el índice con capacidades semánticas
    """
    print("=" * 60)
    print("CONFIGURACIÓN SEMÁNTICA DE AZURE AI SEARCH")
    print("=" * 60)
    
    client = AzureSearchSemantic()
    
    print(f"\n1. Configurando índice: {client.search_index}")
    print(f"   Endpoint: {client.endpoint}")
    print(f"   API Version: {client.api_version}")
    
    # Crear configuración semántica
    success = client.create_semantic_configuration(client.search_index)
    
    if success:
        print("\n✅ Configuración semántica creada exitosamente!")
        print("\nCaracterísticas habilitadas:")
        print("  • Re-ranking semántico")
        print("  • Extracción de respuestas")
        print("  • Generación de captions con highlights")
        print("  • Búsqueda híbrida (BM25 + Vector + Semántica)")
    else:
        print("\n❌ Error configurando índice semántico")
        print("   Revise los logs para más detalles")
    
    # Test de búsqueda
    print("\n" + "=" * 60)
    print("TEST DE BÚSQUEDA SEMÁNTICA")
    print("=" * 60)
    
    test_query = "información sobre equipos de perforación"
    print(f"\nEjecutando búsqueda de prueba: '{test_query}'")
    
    try:
        result = client.semantic_search(
            query=test_query,
            use_semantic=True,
            use_vector=False,  # Solo semántica por ahora
            top_k=5
        )
        
        if result.get("success"):
            print(f"\n✅ Búsqueda exitosa!")
            print(f"   Total resultados: {result.get('total_count', 0)}")
            print(f"   Tipo de búsqueda: {result.get('search_type')}")
            
            if result.get("semantic_answers"):
                print(f"\n   Respuestas semánticas encontradas:")
                for idx, answer in enumerate(result["semantic_answers"][:2], 1):
                    print(f"   {idx}. {answer['text'][:100]}...")
            
            if result.get("results"):
                print(f"\n   Top 3 resultados:")
                for doc in result["results"][:3]:
                    print(f"   - {doc.get('pozo', 'N/A')} | {doc.get('fecha', 'N/A')} | Score: {doc.get('reranker_score', 0):.2f}")
        else:
            print(f"\n⚠️ Búsqueda con advertencias: {result.get('error')}")
            
    except Exception as e:
        print(f"\n❌ Error en búsqueda de prueba: {e}")
    
    print("\n" + "=" * 60)
    print("RECOMENDACIONES")
    print("=" * 60)
    print("\n1. Actualizar el código para usar las nuevas funciones:")
    print("   - Reemplazar utils_azure_search.py con utils_azure_search_semantic.py")
    print("   - Usar rag_retriever_semantic.py en lugar de rag_retriever.py")
    print("\n2. Configurar variables de entorno adicionales:")
    print("   - EMBEDDING_MODEL=text-embedding-ada-002")
    print("   - AZURE_SEARCH_API_VERSION=2024-11-01-preview")
    print("\n3. Re-indexar documentos con embeddings para búsqueda vectorial")
    print("\n4. Ajustar la configuración semántica según los campos del índice")


if __name__ == "__main__":
    setup_semantic_configuration()