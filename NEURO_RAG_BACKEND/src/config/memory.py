from langgraph.checkpoint.memory import MemorySaver
from utils.util_logger import GetLogger
from config.settings import LOGLEVEL

logger = GetLogger(__name__, level=LOGLEVEL, log_file='data/app_logs.log').logger

# Inicializa un MemorySaver global y expone un getter seguro
try:
    memory_checkpointer = MemorySaver()
    logger.debug(f"Memory checkpointer inicializado: {type(memory_checkpointer)}")
except Exception as memory_error:
    logger.error(f"Error configurando MemorySaver: {str(memory_error)}")
    memory_checkpointer = None

def get_memory_checkpointer():
    return memory_checkpointer
