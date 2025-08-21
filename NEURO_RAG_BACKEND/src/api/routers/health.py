import datetime
from fastapi import APIRouter
from config.memory import get_memory_checkpointer
from config.settings import JSON_SCHEMA_PATH


router = APIRouter()


@router.get("/")
async def root():
    return {"message": "Botcom API está funcionando correctamente", "version": "1.0.0"}


@router.get("/health")
async def health_check():
    memory_status = "active" if get_memory_checkpointer() is not None else "disabled"
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "memory_system": memory_status,
        "schema_loaded": JSON_SCHEMA_PATH is not None,
    }

