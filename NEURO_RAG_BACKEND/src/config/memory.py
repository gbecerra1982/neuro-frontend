from langgraph.checkpoint.memory import MemorySaver
from utils.util_logger import GetLogger
from config.settings import LOGLEVEL
import os

# log_dir = '/tmp/addc3fe92e5eba2/data/'
# os.makedirs(log_dir, exist_ok=True)

log_dir = os.path.join(os.getcwd(), 'data')
 
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    print(f"Directorio creado: {log_dir}")
 
logger = GetLogger(__name__, level=LOGLEVEL, log_file=os.path.join(log_dir, 'app_logs.log')).logger

# logger = GetLogger(__name__, level=LOGLEVEL, log_file='data/app_logs.log').logger

# Inicializa un MemorySaver global y expone un getter seguro
try:
    memory_checkpointer = MemorySaver()
    logger.debug(f"Memory checkpointer inicializado: {type(memory_checkpointer)}")
except Exception as memory_error:
    logger.error(f"Error configurando MemorySaver: {str(memory_error)}")
    memory_checkpointer = None

def get_memory_checkpointer():
    return memory_checkpointer
