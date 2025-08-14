from dotenv import load_dotenv
from langchain_openai import AzureOpenAIEmbeddings
import os
import requests

from src.sqltool_aux_fun import fuzzy_search

load_dotenv()



TERM_SEARCH_APPROACH='term'
VECTOR_SEARCH_APPROACH='vector'
HYBRID_SEARCH_APPROACH='hybrid'
AZURE_SEARCH_USE_SEMANTIC=os.environ.get("SQL_SEARCH_USE_SEMANTIC") or "false"
AZURE_SEARCH_APPROACH=os.environ.get("SQL_SEARCH_APPROACH") or HYBRID_SEARCH_APPROACH
AZURE_SEARCH_ADMIN_KEY = os.environ.get("AZURE_SEARCH_ADMIN_KEY")

AZURE_SEARCH_SERVICE_ENDPOINT = os.environ.get('AZURE_SEARCH_SERVICE_ENDPOINT')
AZURE_SEARCH_INDEX = "pywo-columnas-index"
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

def call_azure_search(input: str, table_name: str, embeddings_query=None):
    search_query = input
    if embeddings_query is None:
        embeddings_query = embeddings.embed_query(search_query)
    azuresearchkey = AZURE_SEARCH_ADMIN_KEY

    # prepare body
    body = {
        "select": "metadata_storage_name, column",
        "filter": f"table_name eq '{table_name}'",
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
        'api-key': azuresearchkey
    }
   
    search_endpoint = f"{AZURE_SEARCH_SERVICE_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/search?api-version={AZURE_SEARCH_API_VERSION}"
    
    response = requests.post(search_endpoint, headers=headers, json=body)
    return response


def columns_index_retrieval(input: str, table_name: str, embeddings_query=None):
    search_results = []
    column_list = []
    search_query = input
    tablename = table_name
    response = call_azure_search(search_query, tablename, embeddings_query)

    if response.json()['value']:
        for doc in response.json()['value']:
            metadata_storage_name = doc.get('metadata_storage_name', '')
            table_name, column_name = '', ''
            if metadata_storage_name:
                table_column = metadata_storage_name.replace('.json', '').split('-')
                if len(table_column) == 2:
                    table_name, column_name = table_column
                column_list.append(column_name)

            # Agrego esta modificacion para poder cambiar las descripciones sin necedidad de actualizar embeddings
            from src.schema_td import datos_db
            if column_name in datos_db[table_name]['columns'].keys():
                result_block = (
                    f"/{column_name}: {datos_db[table_name]['columns'][column_name]}/"
                )
                search_results.append(result_block.strip() + "\n")
            else:
                # column_list.remove(column_name)
                res = fuzzy_search(list(datos_db[table_name]['columns'].keys()), column_name)
                column_name = res[0][0]
                result_block = (
                    f"/{column_name}: {datos_db[table_name]['columns'][column_name]}/"
                )
                search_results.append(result_block.strip() + "\n")
        
                print(f"Se reemplaza con fuzzy por: \'{column_name}\'")
    
    sources = ' '.join(search_results)
    return sources, column_list