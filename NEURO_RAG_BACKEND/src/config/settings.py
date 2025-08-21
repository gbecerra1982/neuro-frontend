import os
import datetime
from dotenv import load_dotenv

# Carga de variables de entorno
load_dotenv()

# Log level para util_logger
LOGLEVEL = os.environ.get('LOGLEVEL_UTIL', 'INFO').upper()

# Azure OpenAI
AZURE_OPENAI_STANDARD_API_KEY = os.environ.get('AZURE_OPENAI_STANDARD_API_KEY')
AZURE_OPENAI_STANDARD_ENDPOINT = os.environ.get('AZURE_OPENAI_STANDARD_ENDPOINT')

# Azure Search
AZURE_SEARCH_SERVICE_ENDPOINT = os.environ.get('AZURE_SEARCH_SERVICE_ENDPOINT')
AZURE_SEARCH_ADMIN_KEY = os.environ.get('AZURE_SEARCH_ADMIN_KEY')
AZURE_SEARCH_API_VERSION = os.environ.get('AZURE_SEARCH_API_VERSION')

# Teradata (placeholders si se usan en el futuro)
TD_HOST = os.environ.get('TD_HOST')
TD_USER = os.environ.get('TD_USER')
TD_PASS = os.environ.get('TERADATA_PASS')
LOGMECH = os.environ.get('LOGMECH')

# Cloudera
CLOUDERA_HOST = os.environ.get('CLOUDERA_HOST')
CLOUDERA_USER = os.environ.get('CLOUDERA_USER')
CLOUDERA_PASS = os.environ.get('CLOUDERA_PASS')
CLOUDERA_PORT = os.environ.get('CLOUDERA_PORT')
CLOUDERA_AUTH = os.environ.get('CLOUDERA_AUTH')

# Schema path
def _resolve_schema_path() -> str | None:
    try:
        primary = 'src/data/cloudera_schema.json'
        if os.path.exists(primary):
            return primary
        fallback = 'data/cloudera_schema.json'
        if os.path.exists(fallback):
            return fallback
        return None
    except Exception:
        return None

JSON_SCHEMA_PATH = _resolve_schema_path()

# Fechas dinámicas
TODAY = datetime.date.today()
CURRENT_DATE = TODAY.strftime('%Y-%m-%d')
CURRENT_DAY = TODAY.strftime('%A')

