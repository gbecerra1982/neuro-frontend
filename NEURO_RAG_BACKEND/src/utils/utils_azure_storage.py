
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from io import BytesIO
from docx import Document

def leer_docx(data):
    """
    Lee un archivo .docx en memoria (en formato bytes) y extrae solo su texto.

    :param data: Contenido en memoria del archivo .docx en formato `bytes`.
    :return: Texto extraído del archivo.
    """
    try:
        # Convertir los datos en bytes a un objeto de archivo en memoria

        archivo_memoria = BytesIO(data)

        # Cargar el documento utilizando python-docx
        documento = Document(archivo_memoria)

        # Leer y concatenar todo el texto del documento
        texto = "\n".join([parrafo.text for parrafo in documento.paragraphs])

        return texto
    except Exception as e:
        print(f"Ocurrió un error al leer el archivo .docx:{e}")
        return None
    
class AzureStorage:
    def __init__(self):
        self.connection_string = os.environ.get("AZURE_CONNECTION_STRING")
        self.container_name = os.environ.get("AZURE_CONTAINER_NAME")
        self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)

    def upload_to_azure_storage(self, file_path):
        try:
            ruta_relativa = os.path.relpath(file_path, 'docs')
            # Crear cliente para un container (asegúrate de que el contenedor exista)
            container_client =  self.blob_service_client.get_container_client(self.container_name)

            blob_client = container_client.get_blob_client(ruta_relativa)

            # Leer el archivo local y cargarlo al blob
            with open(file_path, "rb") as data:  # Abrir el archivo en modo binario
                blob_client.upload_blob(data, overwrite=True)  # Subir el archivo

            print(f"El archivo '{file_path}' se subió correctamente como '{ruta_relativa}'.")

        except Exception as e:
            print(f"Ocurrió un error: {e}")
    
    def upload_dir_to_azure_storage(self, docs):

        for root, dirs, files in os.walk(docs):
            # Crear cliente del contenedor
            container_client = self.blob_service_client.get_container_client(self.container_name)

            blobs_existentes = container_client.list_blobs(name_starts_with=dirs)
            for blob in blobs_existentes:
                if blob in dirs:
                    print(f"Eliminando blob existente: {blob.name}...")
                    container_client.delete_blob(blob.name)

            for file_name in files:
                # Ruta completa del archivo local
                archivo_local = os.path.join(root, file_name)
                storage.upload_to_azure_storage(archivo_local)

    def read_blob(self, nombre_blob):
        """
        Busca y descarga un archivo desde Azure Blob Storage.
        
        :param connection_string: Cadena de conexión para Azure Blob Storage.
        :param container_name: Nombre del contenedor donde buscar el archivo.
        :param nombre_blob: Nombre del archivo (blob) que se quiere descargar.
        :return: La ruta local del archivo descargado si existe; de lo contrario, None.
        """
        try:
            # Crear cliente para el contenedor
            container_client = self.blob_service_client.get_container_client(self.container_name)

            # Crear cliente para el blob específico
            blob_client = container_client.get_blob_client(blob=nombre_blob)

            # Verificar si el blob existe
            if blob_client.exists():
                print(f"Se encontró '{nombre_blob}'")
                dato_descargado = blob_client.download_blob().readall()
                dato_formateado = leer_docx(dato_descargado)
                return dato_formateado
            
            else:
                print(f"El archivo '{nombre_blob}' no existe en el contenedor '{self.container_name}'.")
                return None

        except Exception as e:
            print(f"Ocurrió un error: ({e})")
            return None
        
    def read_rango_fecha_pozo_blobs(self, fecha_inicio: str, fecha_fin: str, pozo: str):
        """
        Descarga y devuelve una lista de contenidos para un pozo entre dos fechas inclusive.
        Cada elemento es un dict {"fecha": str, "content": str} para fechas con blob existente.
        """
        try:
            resultados = []
            inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
            fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
 
            if fin < inicio:
                inicio, fin = fin, inicio
 
            current = inicio
            while current <= fin:
                fecha_str = current.strftime("%Y-%m-%d")
                contenido = self.read_fecha_pozo_blob(fecha_str, pozo)
                if contenido is not None:
                    resultados.append({"fecha": fecha_str, "content": contenido})
                current += timedelta(days=1)
 
            return resultados
        except Exception as e:
            print(f"Ocurrió un error al leer rango de fechas: ({e})")
            return []
        
    def _format_pozo_fecha(self, fecha, pozo):
        print('post params', fecha, pozo )
        url= f"rag_{fecha}/{pozo}_{fecha}.docx"
        return url

    def read_fecha_pozo_blob(self, fecha, pozo):
        """
        Busca y descarga un archivo desde Azure Blob Storage.
        
        :param connection_string: Cadena de conexión para Azure Blob Storage.
        :param container_name: Nombre del contenedor donde buscar el archivo.
        :param nombre_blob: Nombre del archivo (blob) que se quiere descargar.
        :return: La ruta local del archivo descargado si existe; de lo contrario, None.
        """
        try:
            # Crear cliente para el contenedor
            container_client = self.blob_service_client.get_container_client(self.container_name)

            # Crear cliente para el blob específico
            nombre_blob = self._format_pozo_fecha(fecha, pozo)
            blob_client = container_client.get_blob_client(blob=nombre_blob)
            # Verificar si el blob existe
            if blob_client.exists():
                print(f"Se encontró '{nombre_blob}'")
                dato_descargado = blob_client.download_blob().readall()
                dato_formateado = leer_docx(dato_descargado)
                return dato_formateado
            
            else:
                print(f"El archivo '{nombre_blob}' no existe en el contenedor '{self.container_name}'.")
                return None

        except Exception as e:
            print(f"Ocurrió un error: ({e})")
            return None

if __name__ == "__main__":
    load_dotenv()
    #directorio_de_docs = 'docs'
    storage = AzureStorage()
    #storage.upload_dir_to_azure_storage(directorio_de_docs)

    data = storage.read_blob('rag_doc_2025-08-05/AdCh-1117(h)_2025-08-05.docx')
    print(data)