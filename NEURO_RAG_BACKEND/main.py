import uvicorn
from api import app  # Importamos la instancia de FastAPI desde api.py

if __name__ == "__main__":
    # Configuración de ejecución en modo debug
    uvicorn.run(
        "api:app",
        host="0.0.0.0", 
        port=8000,         
        reload=True       
    )