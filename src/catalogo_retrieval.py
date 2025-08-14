from dotenv import load_dotenv

from langchain_openai import AzureOpenAIEmbeddings

import os
import requests
import time

load_dotenv()

TERM_SEARCH_APPROACH='term'
VECTOR_SEARCH_APPROACH='vector'
HYBRID_SEARCH_APPROACH='hybrid'
AZURE_SEARCH_USE_SEMANTIC=os.environ.get("SQL_SEARCH_USE_SEMANTIC") or "false"
AZURE_SEARCH_APPROACH=os.environ.get("SQL_SEARCH_APPROACH") or HYBRID_SEARCH_APPROACH
AZURE_SEARCH_ADMIN_KEY = os.environ.get("AZURE_SEARCH_ADMIN_KEY")

AZURE_SEARCH_SERVICE_ENDPOINT = os.environ.get('AZURE_SEARCH_SERVICE_ENDPOINT')
AZURE_SEARCH_INDEX = "pywo-catalogo-index"
AZURE_SEARCH_API_VERSION = "2024-03-01-preview"

OPENAI_EMBEDDING_DEPLOYMENT_NAME = "embeddingada003l"
AZURE_OPENAI_EMBEDDING_MODEL = "text-embedding-3-large"
AZURE_OPENAI_API_KEY  = os.environ.get("OPENAI-API-KEY")
AZURE_OPENAI_API_ENDPOINT = os.environ.get('AZURE_OPENAI_ENDPOINT')
AZURE_OPENAI_API_VERSION = os.environ.get('API_VERSION')

AZURE_SEARCH_OYD_USE_SEMANTIC_SEARCH = "false"
AZURE_SEARCH_OYD_USE_SEMANTIC_SEARCH = True if AZURE_SEARCH_OYD_USE_SEMANTIC_SEARCH == "true" else False
AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG = "my-semantic-config"
AZURE_SEARCH_SEMANTIC_SEARCH_LANGUAGE = "en-US"
AZURE_SEARCH_ENABLE_IN_DOMAIN = "true"
AZURE_SEARCH_ENABLE_IN_DOMAIN =  True if AZURE_SEARCH_ENABLE_IN_DOMAIN == "true" else False

AZURE_SEARCH_TOP_K = "15"


embeddings = AzureOpenAIEmbeddings(
    azure_deployment=OPENAI_EMBEDDING_DEPLOYMENT_NAME,
    azure_endpoint=AZURE_OPENAI_API_ENDPOINT,
    openai_api_version=AZURE_OPENAI_API_VERSION,
    api_key = AZURE_OPENAI_API_KEY,
    chunk_size=2048,
)

def catalogo_index_retrieval(input: str, embeddings_query=None) -> tuple:
    print('few_shot')
    search_query = input
    few_shot_queries = ""
    few_shot_tables = ""
    few_shot_columns = ""
    try:
        start_time = time.time()
        if embeddings_query is None:
            embeddings_query = embeddings.embed_query(search_query)
        response_time = round(time.time() - start_time,2)
        azure_search_key = AZURE_SEARCH_ADMIN_KEY

        # prepare body
        body = {
            "select": "question, query, selected_tables, selected_columns, reasoning",
            "top": AZURE_SEARCH_TOP_K
        }    
        if AZURE_SEARCH_APPROACH == TERM_SEARCH_APPROACH:
            body["search"] = search_query
        elif AZURE_SEARCH_APPROACH == VECTOR_SEARCH_APPROACH:
            body["vectorQueries"] = [{
                "kind": "vector",
                "vector": embeddings_query,
                "fields": "contentVector",
                "k": int(AZURE_SEARCH_TOP_K)
            }]
        elif AZURE_SEARCH_APPROACH == HYBRID_SEARCH_APPROACH:
            body["search"] = search_query
            body["vectorQueries"] = [{
                "kind": "vector",
                "vector": embeddings_query,
                "fields": "contentVector",
                "k": int(AZURE_SEARCH_TOP_K)
            }]

        if AZURE_SEARCH_USE_SEMANTIC == "true" and AZURE_SEARCH_APPROACH != VECTOR_SEARCH_APPROACH:
            body["queryType"] = "semantic"
            body["semanticConfiguration"] = AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG

        headers = {
            'Content-Type': 'application/json',
            'api-key': azure_search_key
        }
        search_endpoint = f"{AZURE_SEARCH_SERVICE_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/search?api-version={AZURE_SEARCH_API_VERSION}"
        
        start_time = time.time()
        response = requests.post(search_endpoint, headers=headers, json=body)
        status_code = response.status_code
        if status_code >= 400:
            error_message = f'Status code: {status_code}.'
            if response.text != "": error_message += f" Error: {response.text}."
            print(f"error {status_code} when searching documents. {error_message}")
        else:
            for i, doc in enumerate(response.json()['value'], start=1):
                question = doc.get('question', '')
                query = doc.get('query', '')
                selected_tables = doc.get('selected_tables', '')
                selected_columns = doc.get('selected_columns', '')
                reasoning = doc.get('reasoning', '')

                few_shot_queries += f"Ejemplo {i}\nPregunta: {question}\nRazonamiento: {reasoning}\nConsulta SQL: {query}\n\n"
                few_shot_tables += f"Ejemplo {i}\nPregunta: {question}\nRazonamiento: {reasoning}\nTablas seleccionadas: {selected_tables}\n\n"
                few_shot_columns += f"Ejemplo {i}\nPregunta: {question}\nRazonamiento: {reasoning}\nColumnas seleccionadas: {selected_columns}\n\n"

        response_time = round(time.time() - start_time, 2)
        print(f"finished querying azure ai search. {response_time} seconds")
    except Exception as e:
        error_message = str(e)
        print(f"error when getting the answer {error_message}")

    return few_shot_queries, few_shot_tables, few_shot_columns