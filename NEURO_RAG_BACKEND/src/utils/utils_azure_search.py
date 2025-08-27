import os
import logging
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv
import time
import logging
try:
    from utils.util_logger import GetLogger
except:
    from util_logger import GetLogger
import requests

load_dotenv()
# Azure search Integration Settings
#AZURE_SEARCH_SERVICE_ENDPOINT = os.environ.get('AZURE_SEARCH_SERVICE_ENDPOINT')
#AZURE_SEARCH_ADMIN_KEY = os.environ.get("AZURE_SEARCH_ADMIN_KEY") 
#AZURE_SEARCH_API_VERSION = os.environ.get('AZURE_SEARCH_API_VERSION')
# Set up logging
LOGLEVEL = os.environ.get('LOGLEVEL', 'DEBUG').upper()
logging.basicConfig(level=LOGLEVEL)
AZURE_SEARCH_INDEX = "neuro-rag"  # Replace with your index name
AZURE_SEARCH_TOP_K = 5
logger = GetLogger(__name__, level=LOGLEVEL, log_file='data/app_logs.log').logger

class AzureSearch:
    def __init__(self):
        self.endpoint = os.environ.get("AZURE_SEARCH_SERVICE_ENDPOINT")
        self.api_version = os.environ.get('AZURE_SEARCH_API_VERSION')
        self.admin_key = os.environ.get("AZURE_SEARCH_ADMIN_KEY")
        self.search_index = os.environ.get("AZURE_SEARCH_INDEX")
        self.search_url = f"{self.endpoint}/indexes/{self.search_index}/docs/search?api-version={self.api_version}"

    def search_azure(self, search_word, fecha, pozo, equipo):
        """
        Realiza una búsqueda en Azure Search.
        
        Parámetros:
        - search_phrase (str): La frase a buscar.
        
        Retorna:
        - dict: Los resultados de la búsqueda en formato JSON.
        """
        # Construye la URL completa del índice
        search_url = self.search_url

        # Define el encabezado con la API Key
        headers = {
            'Content-Type': 'application/json',
            'api-key': self.admin_key
        }
        logger.info(f'search azure fecha, pozo {fecha}, {pozo}')
        if equipo != None:
            word_filter=f"headers/fecha eq '{fecha}' and headers/equipo eq '{equipo}'"
        elif pozo != None:
            word_filter= f"headers/fecha eq '{fecha}' and headers/pozo eq '{pozo}'"
        else:
            word_filter=f"headers/fecha eq '{fecha}''"
        # Especifica la consulta
        print('word_filter',word_filter)
        payload = {
            "search": search_word,
            "filter":word_filter,
            "queryType": "simple",  # Puedes usar "full" para búsquedas más avanzadas
            "top": 20,  # Cambia este valor para limitar el número de resultados
        }

        try:
            # Realiza la solicitud POST a Azure Search
            response = requests.post(search_url, json=payload, headers=headers)
            response.raise_for_status()  # Lanza una excepción si ocurre un error HTTP
            return response.json()  # Retorna la respuesta en formato JSON
        except requests.exceptions.RequestException as e:
            logging.warning(f"Error al realizar la búsqueda en Azure Search: {e}")
            return None 

    def delete_document(self, id):
        credential = AzureKeyCredential(self.admin_key)
        search_client = SearchClient(self.endpoint, self.index_name, credential)

        document = search_client.delete_documents({'id':id})
        return document

if __name__ == "__main__":

    input = "Que ofertas hubo en Julio?"
    filter = '07'
    azure=AzureSearch()
    result=azure.search_azure("", '2025-08-19',None,'DLS-168')
    print(result)