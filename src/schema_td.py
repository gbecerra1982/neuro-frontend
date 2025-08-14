import json
import os

# Ruta relativa al archivo schema.json
json_datos_db = r"src/schema.json"

# Obtener la ruta absoluta para asegurarnos de la ubicación correcta
json_datos_db = os.path.abspath(json_datos_db)

# Verificar si el archivo existe en la ruta especificada
if not os.path.isfile(json_datos_db):
    raise FileNotFoundError(f"El archivo {json_datos_db} no existe. Verifique la ruta.")

# Intentar abrir y cargar el archivo JSON
try:
    with open(json_datos_db, 'r', encoding='UTF-8') as json_file:
        datos_db = json.load(json_file)
except json.JSONDecodeError as e:
    raise ValueError(f"Error al analizar el archivo JSON: {e}")
except Exception as e:
    raise RuntimeError(f"Error inesperado al leer el archivo: {e}")
