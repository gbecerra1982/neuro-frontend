import json
import logging
import sys
import traceback
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage
from backend import build_agent
import time

# ===== CONFIGURACIÓN DE LOGGING EXHAUSTIVO =====
# Configurar el formato de logging con máximo detalle
log_format = (
    "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | "
    "%(filename)s:%(lineno)d | %(funcName)s | PID:%(process)d | "
    "Thread:%(thread)d | %(message)s"
)

# Configurar logging para archivo y consola
logging.basicConfig(
    level=logging.DEBUG,
    format=log_format,
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('neuro_rag_api_detailed.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Crear logger específico para esta aplicación
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Logger para mensajes de LangChain
langchain_logger = logging.getLogger("langchain")
langchain_logger.setLevel(logging.DEBUG)

# Logger para FastAPI
fastapi_logger = logging.getLogger("fastapi")
fastapi_logger.setLevel(logging.DEBUG)

# Logger para uvicorn
uvicorn_logger = logging.getLogger("uvicorn")
uvicorn_logger.setLevel(logging.DEBUG)

logger.info("="*80)
logger.info("INICIANDO APLICACIÓN NEURO RAG API")
logger.info(f"Timestamp: {datetime.now().isoformat()}")
logger.info(f"Python Version: {sys.version}")
logger.info("="*80)

# ===== CREAR APLICACIÓN FASTAPI =====
app = FastAPI(
    title="Neuro RAG API",
    description="API para procesamiento de consultas usando LangGraph",
    version="1.0.0",
    debug=True
)

# ===== CONFIGURAR CORS =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("FastAPI app creada con configuración CORS habilitada")

# ===== INICIALIZACIÓN DEL AGENTE MULTIAGENTE =====
react_graph = None
initialization_error = None

try:
    logger.info("Iniciando construcción del agente LangGraph...")
    start_time = time.time()
    
    react_graph = build_agent()
    
    elapsed_time = time.time() - start_time
    logger.info(f"✅ Agente LangGraph inicializado exitosamente en {elapsed_time:.3f} segundos")
    logger.debug(f"Tipo de objeto react_graph: {type(react_graph)}")
    logger.debug(f"Atributos disponibles: {dir(react_graph)[:10]}...")  # Primeros 10 atributos
    
except Exception as e:
    initialization_error = str(e)
    logger.error("❌ ERROR CRÍTICO al inicializar LangGraph")
    logger.error(f"Tipo de error: {type(e).__name__}")
    logger.error(f"Mensaje de error: {str(e)}")
    logger.error(f"Stack trace completo:\n{traceback.format_exc()}")
    
    # No lanzar excepción aquí para permitir que el servidor inicie
    # pero marcar que el agente no está disponible

# ===== MIDDLEWARE PARA LOGGING DE REQUESTS =====
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware para loguear todas las requests con máximo detalle"""
    request_id = f"{datetime.now().timestamp()}"
    start_time = time.time()
    
    # Log de request entrante
    logger.info(f"📥 REQUEST [{request_id}] - Inicio")
    logger.info(f"   Method: {request.method}")
    logger.info(f"   URL: {request.url}")
    logger.info(f"   Path: {request.url.path}")
    logger.info(f"   Query Params: {request.query_params}")
    logger.info(f"   Headers: {dict(request.headers)}")
    logger.info(f"   Client: {request.client}")
    
    # Procesar request
    response = await call_next(request)
    
    # Log de response
    process_time = time.time() - start_time
    logger.info(f"📤 RESPONSE [{request_id}] - Completado")
    logger.info(f"   Status Code: {response.status_code}")
    logger.info(f"   Process Time: {process_time:.3f}s")
    logger.info(f"   Response Headers: {dict(response.headers)}")
    
    return response

@app.get("/health")
async def health_check():
    """Endpoint de health check con información detallada del sistema"""
    logger.info("Health check solicitado")
    
    health_status = {
        "status": "healthy" if react_graph is not None else "degraded",
        "timestamp": datetime.now().isoformat(),
        "agent_initialized": react_graph is not None,
        "initialization_error": initialization_error,
        "uptime": time.time(),
        "python_version": sys.version
    }
    
    logger.info(f"Health check response: {json.dumps(health_status, indent=2)}")
    return health_status

@app.post("/ask/")
async def ask_langgraph(user_question: str):
    """
    API endpoint para consultar el agente de LangGraph con logging exhaustivo.

    :param user_question: Pregunta realizada por el usuario.
    :return: Respuesta final de LangGraph.
    """
    request_id = f"REQ_{datetime.now().timestamp()}"
    logger.info(f"{'='*60}")
    logger.info(f"🔍 NUEVA CONSULTA [{request_id}]")
    logger.info(f"Pregunta del usuario: '{user_question}'")
    logger.info(f"Longitud de la pregunta: {len(user_question)} caracteres")
    logger.info(f"{'='*60}")
    
    # Verificar si el agente está inicializado
    if react_graph is None:
        logger.error(f"[{request_id}] Intento de consulta con agente no inicializado")
        logger.error(f"Error de inicialización previo: {initialization_error}")
        raise HTTPException(
            status_code=503, 
            detail=f"El servicio no está disponible. Error de inicialización: {initialization_error}"
        )
    
    try:
        # Preparar input para el agente
        agent_input = {
            "question": user_question,
            "messages": [{"role": "user", "content": user_question}]
        }
        
        logger.debug(f"[{request_id}] Input preparado para el agente:")
        logger.debug(f"[{request_id}] {json.dumps(agent_input, indent=2, ensure_ascii=False)}")
        
        # Realizar consulta al agente con timing
        logger.info(f"[{request_id}] Invocando react_graph.invoke()...")
        invoke_start = time.time()
        
        output = react_graph.invoke(input=agent_input)
        
        invoke_time = time.time() - invoke_start
        logger.info(f"[{request_id}] ✅ Invocación completada en {invoke_time:.3f} segundos")
        
        # Log del output completo
        logger.debug(f"[{request_id}] Output completo del agente:")
        logger.debug(f"[{request_id}] Tipo: {type(output)}")
        logger.debug(f"[{request_id}] Keys disponibles: {output.keys() if isinstance(output, dict) else 'N/A'}")
        
        # Intentar serializar el output para logging (con manejo de errores)
        try:
            output_str = json.dumps(output, indent=2, ensure_ascii=False, default=str)
            logger.debug(f"[{request_id}] Contenido del output:\n{output_str[:2000]}...")  # Primeros 2000 chars
        except Exception as json_err:
            logger.warning(f"[{request_id}] No se pudo serializar output para logging: {json_err}")
            logger.debug(f"[{request_id}] Output (repr): {repr(output)[:500]}...")
        
        # Extraer mensajes del resultado
        mensajes = output.get("messages", [])
        logger.info(f"[{request_id}] Número de mensajes en output: {len(mensajes)}")
        
        if not mensajes:
            logger.error(f"[{request_id}] No hay mensajes disponibles en el output")
            logger.error(f"[{request_id}] Output keys: {output.keys()}")
            raise HTTPException(
                status_code=500, 
                detail="No se pudo obtener una respuesta: No hay mensajes disponibles."
            )
        
        # Log de todos los mensajes
        for idx, msg in enumerate(mensajes):
            logger.debug(f"[{request_id}] Mensaje {idx + 1}/{len(mensajes)}:")
            logger.debug(f"[{request_id}]   Tipo: {type(msg).__name__}")
            logger.debug(f"[{request_id}]   Role: {getattr(msg, 'role', 'N/A')}")
            
            # Log del contenido con manejo seguro
            try:
                content_preview = str(msg.content)[:500] if hasattr(msg, 'content') else 'Sin contenido'
                logger.debug(f"[{request_id}]   Contenido (preview): {content_preview}")
            except Exception as e:
                logger.debug(f"[{request_id}]   Error al obtener contenido: {e}")
        
        # Acceder al último mensaje
        ultimo_mensaje = mensajes[-1]
        logger.info(f"[{request_id}] Procesando último mensaje de tipo: {type(ultimo_mensaje).__name__}")
        
        # Verificar si el último mensaje contiene una respuesta
        if isinstance(ultimo_mensaje, AIMessage):
            logger.debug(f"[{request_id}] Último mensaje es AIMessage")
            logger.debug(f"[{request_id}] Contenido completo: {ultimo_mensaje.content}")
            
            try:
                # Intentar procesar el contenido como JSON
                logger.debug(f"[{request_id}] Intentando parsear contenido como JSON...")
                contenido = json.loads(ultimo_mensaje.content)
                logger.debug(f"[{request_id}] ✅ Contenido parseado exitosamente")
                logger.debug(f"[{request_id}] Keys en contenido: {contenido.keys()}")
                
                if "answer" in contenido:
                    answer = contenido["answer"]
                    logger.info(f"[{request_id}] ✅ Respuesta encontrada en campo 'answer'")
                    logger.info(f"[{request_id}] Respuesta: {answer[:200]}...")  # Primeros 200 chars
                    
                    response = {"answer": answer}
                    logger.info(f"[{request_id}] 📤 Enviando respuesta exitosa")
                    return response
                else:
                    logger.warning(f"[{request_id}] No se encontró campo 'answer' en el JSON")
                    logger.warning(f"[{request_id}] Keys disponibles: {list(contenido.keys())}")
                    
                    response = {"answer": "No se encontró un campo `answer` en el contenido del último mensaje."}
                    logger.info(f"[{request_id}] 📤 Enviando respuesta con advertencia")
                    return response
                    
            except json.JSONDecodeError as json_err:
                logger.warning(f"[{request_id}] El contenido no es JSON válido: {json_err}")
                logger.debug(f"[{request_id}] Contenido raw: {ultimo_mensaje.content}")
                
                # Si no es JSON válido, retornar el contenido directo
                response = {"answer": ultimo_mensaje.content}
                logger.info(f"[{request_id}] 📤 Enviando contenido directo como respuesta")
                return response
        else:
            logger.warning(f"[{request_id}] El último mensaje NO es de tipo AIMessage")
            logger.warning(f"[{request_id}] Tipo actual: {type(ultimo_mensaje)}")
            
            response = {"answer": "El último mensaje no es de tipo AIMessage."}
            logger.info(f"[{request_id}] 📤 Enviando respuesta de tipo incorrecto")
            return response
            
    except HTTPException as http_err:
        # Re-lanzar HTTPExceptions sin modificar
        logger.error(f"[{request_id}] HTTPException: {http_err.detail}")
        raise
        
    except Exception as e:
        # Log exhaustivo de errores inesperados
        logger.error(f"[{request_id}] ❌ ERROR NO MANEJADO en ask_langgraph")
        logger.error(f"[{request_id}] Tipo de error: {type(e).__name__}")
        logger.error(f"[{request_id}] Mensaje: {str(e)}")
        logger.error(f"[{request_id}] Stack trace completo:")
        logger.error(f"[{request_id}] {traceback.format_exc()}")
        
        # Información adicional de debugging
        logger.error(f"[{request_id}] Variables locales en el momento del error:")
        for var_name, var_value in locals().items():
            if var_name not in ['traceback', 'logger']:
                try:
                    logger.error(f"[{request_id}]   {var_name}: {repr(var_value)[:200]}")
                except:
                    logger.error(f"[{request_id}]   {var_name}: <no representable>")
        
        raise HTTPException(
            status_code=500, 
            detail=f"Error procesando la consulta: {str(e)}"
        )

# Log de finalización de carga del módulo
logger.info("="*80)
logger.info("MÓDULO api.py CARGADO COMPLETAMENTE")
logger.info("="*80)