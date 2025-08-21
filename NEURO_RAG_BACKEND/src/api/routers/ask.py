import logging
import time
import traceback
import json
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from api.schemas.ask import QuestionRequest, QuestionResponse
from agents.supervisor import procesar_consulta_langgraph

# ===== CONFIGURACIÓN DE LOGGING EXHAUSTIVO =====
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Logger adicional para métricas
metrics_logger = logging.getLogger(f"{__name__}.metrics")
metrics_logger.setLevel(logging.DEBUG)

# Logger para trazabilidad de requests
trace_logger = logging.getLogger(f"{__name__}.trace")
trace_logger.setLevel(logging.DEBUG)

router = APIRouter()

# Contador de requests para tracking
request_counter = 0

def log_request_details(request_id: str, request: QuestionRequest, client_info: Optional[Dict] = None):
    """Log detallado de la request entrante"""
    logger.info("="*60)
    logger.info(f"📨 NUEVA REQUEST - ID: {request_id}")
    logger.info("="*60)
    logger.info(f"Question: {request.question}")
    logger.info(f"Question Length: {len(request.question)} chars")
    logger.info(f"Session ID: {request.session_id or 'default_session'}")
    
    if client_info:
        logger.info(f"Client Info: {json.dumps(client_info, indent=2)}")
    
    # Log de caracteres especiales o potencialmente problemáticos
    special_chars = [ch for ch in request.question if not ch.isalnum() and ch not in ' .,?!']
    if special_chars:
        logger.debug(f"Special characters found: {special_chars}")
    
    # Detectar idioma aproximado
    if any(char in request.question for char in 'ñáéíóúÑÁÉÍÓÚ'):
        logger.debug("Detected language: Spanish (special chars)")
    
    logger.info("="*60)

def log_response_details(request_id: str, response: Any, execution_time: float):
    """Log detallado de la response"""
    logger.info("="*60)
    logger.info(f"✅ RESPONSE READY - ID: {request_id}")
    logger.info("="*60)
    
    if isinstance(response, QuestionResponse):
        logger.info(f"Success: {response.success}")
        logger.info(f"Session ID: {response.session_id}")
        logger.info(f"Answer Preview: {response.answer[:200] if response.answer else 'None'}...")
        logger.info(f"Answer Length: {len(response.answer) if response.answer else 0} chars")
    else:
        logger.info(f"Response Type: {type(response)}")
        logger.info(f"Response: {str(response)[:500]}...")
    
    logger.info(f"⏱️ Execution Time: {execution_time:.3f} seconds")
    logger.info("="*60)

@router.post("/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest, raw_request: Request, response: Response):
    """
    Endpoint para procesar preguntas con logging exhaustivo
    
    Args:
        request: Objeto con la pregunta y session_id
        raw_request: Request de FastAPI para obtener metadata
        response: Response de FastAPI para setear headers
    
    Returns:
        QuestionResponse con la respuesta procesada
    """
    global request_counter
    request_counter += 1
    
    # Generar ID único para esta request
    request_id = f"ASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{request_counter:04d}"
    start_time = time.time()
    
    # Extraer información del cliente
    client_info = {
        "host": raw_request.client.host if raw_request.client else "unknown",
        "port": raw_request.client.port if raw_request.client else "unknown",
        "headers": dict(raw_request.headers),
        "method": raw_request.method,
        "url": str(raw_request.url),
        "path": raw_request.url.path,
        "query_params": dict(raw_request.query_params)
    }
    
    # Log inicial de la request
    log_request_details(request_id, request, client_info)
    
    # Setear headers de tracking en la response
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = "pending"
    
    try:
        logger.info(f"[{request_id}] 🔄 Iniciando procesamiento con procesar_consulta_langgraph")
        logger.debug(f"[{request_id}] Argumentos de entrada:")
        logger.debug(f"[{request_id}]   - question: '{request.question}'")
        logger.debug(f"[{request_id}]   - session_id: '{request.session_id or 'default_session'}'")
        
        # Medir tiempo de procesamiento del agente
        agent_start = time.time()
        
        # Llamar a la función de procesamiento
        answer, session_id = procesar_consulta_langgraph(
            request.question, 
            request.session_id or "default_session"
        )
        
        agent_time = time.time() - agent_start
        
        logger.info(f"[{request_id}] ✅ Procesamiento completado exitosamente")
        logger.info(f"[{request_id}] ⏱️ Tiempo del agente: {agent_time:.3f}s")
        logger.debug(f"[{request_id}] Respuesta del agente:")
        logger.debug(f"[{request_id}]   - answer type: {type(answer)}")
        logger.debug(f"[{request_id}]   - answer length: {len(answer) if answer else 0} chars")
        logger.debug(f"[{request_id}]   - session_id returned: {session_id}")
        
        # Validaciones de respuesta
        if not answer:
            logger.warning(f"[{request_id}] ⚠️ Respuesta vacía del agente")
            answer = "No se pudo generar una respuesta."
        
        if len(answer) > 10000:
            logger.warning(f"[{request_id}] ⚠️ Respuesta muy larga: {len(answer)} chars")
            logger.debug(f"[{request_id}] Truncando respuesta para logging...")
        
        # Crear objeto de respuesta
        response_obj = QuestionResponse(
            answer=answer, 
            success=True, 
            session_id=session_id
        )
        
        # Calcular tiempo total
        total_time = time.time() - start_time
        
        # Actualizar header con tiempo de procesamiento
        response.headers["X-Process-Time"] = f"{total_time:.3f}s"
        response.headers["X-Agent-Time"] = f"{agent_time:.3f}s"
        
        # Log de respuesta
        log_response_details(request_id, response_obj, total_time)
        
        # Métricas de performance
        metrics_logger.info(f"[{request_id}] METRICS:")
        metrics_logger.info(f"[{request_id}]   Total Time: {total_time:.3f}s")
        metrics_logger.info(f"[{request_id}]   Agent Time: {agent_time:.3f}s")
        metrics_logger.info(f"[{request_id}]   Overhead: {(total_time - agent_time):.3f}s")
        metrics_logger.info(f"[{request_id}]   Question Length: {len(request.question)}")
        metrics_logger.info(f"[{request_id}]   Answer Length: {len(answer)}")
        metrics_logger.info(f"[{request_id}]   Chars/Second: {len(answer)/agent_time:.1f}" if agent_time > 0 else "N/A")
        
        # Trace completo para debugging
        trace_logger.debug(f"[{request_id}] FULL TRACE:")
        trace_logger.debug(f"[{request_id}] Input: {json.dumps({'question': request.question, 'session_id': request.session_id}, ensure_ascii=False)}")
        trace_logger.debug(f"[{request_id}] Output: {json.dumps({'answer': answer[:1000], 'session_id': session_id, 'truncated': len(answer) > 1000}, ensure_ascii=False)}")
        
        return response_obj
        
    except HTTPException as http_exc:
        # HTTPExceptions ya formateadas, solo loguear y re-lanzar
        elapsed = time.time() - start_time
        logger.error(f"[{request_id}] ❌ HTTPException después de {elapsed:.3f}s")
        logger.error(f"[{request_id}] Status Code: {http_exc.status_code}")
        logger.error(f"[{request_id}] Detail: {http_exc.detail}")
        
        response.headers["X-Process-Time"] = f"{elapsed:.3f}s"
        response.headers["X-Error"] = "true"
        
        raise
        
    except ValueError as val_err:
        # Errores de validación o valores incorrectos
        elapsed = time.time() - start_time
        logger.error(f"[{request_id}] ❌ ValueError después de {elapsed:.3f}s")
        logger.error(f"[{request_id}] Error: {str(val_err)}")
        logger.error(f"[{request_id}] Stack trace:\n{traceback.format_exc()}")
        
        response.headers["X-Process-Time"] = f"{elapsed:.3f}s"
        response.headers["X-Error"] = "true"
        
        raise HTTPException(
            status_code=400,
            detail=f"Error de validación: {str(val_err)}"
        )
        
    except TimeoutError as timeout_err:
        # Errores de timeout
        elapsed = time.time() - start_time
        logger.error(f"[{request_id}] ⏱️ TIMEOUT después de {elapsed:.3f}s")
        logger.error(f"[{request_id}] Error: {str(timeout_err)}")
        
        response.headers["X-Process-Time"] = f"{elapsed:.3f}s"
        response.headers["X-Error"] = "timeout"
        
        raise HTTPException(
            status_code=504,
            detail="La operación excedió el tiempo límite. Por favor, intente con una consulta más simple."
        )
        
    except Exception as e:
        # Cualquier otro error no manejado
        elapsed = time.time() - start_time
        
        logger.error("="*60)
        logger.error(f"[{request_id}] 💥 ERROR NO MANEJADO después de {elapsed:.3f}s")
        logger.error("="*60)
        logger.error(f"[{request_id}] Tipo: {type(e).__name__}")
        logger.error(f"[{request_id}] Mensaje: {str(e)}")
        logger.error(f"[{request_id}] Stack trace completo:")
        logger.error(traceback.format_exc())
        
        # Log de variables locales para debugging
        logger.error(f"[{request_id}] Estado de variables locales:")
        local_vars = {
            "request_question": request.question[:100] if request.question else None,
            "request_session_id": request.session_id,
            "elapsed_time": elapsed,
            "request_counter": request_counter
        }
        logger.error(f"[{request_id}] {json.dumps(local_vars, indent=2, default=str)}")
        
        # Intentar obtener más información del error
        if hasattr(e, '__dict__'):
            logger.error(f"[{request_id}] Atributos del error: {json.dumps(e.__dict__, indent=2, default=str)}")
        
        response.headers["X-Process-Time"] = f"{elapsed:.3f}s"
        response.headers["X-Error"] = "true"
        response.headers["X-Error-Type"] = type(e).__name__
        
        # Determinar código de estado apropiado
        status_code = 500
        if "connection" in str(e).lower():
            status_code = 503  # Service Unavailable
        elif "not found" in str(e).lower():
            status_code = 404  # Not Found
        
        raise HTTPException(
            status_code=status_code,
            detail=f"Error al procesar tu pregunta: {str(e)}"
        )
        
    finally:
        # Log final con resumen de la operación
        final_time = time.time() - start_time
        logger.info(f"[{request_id}] 🏁 Request finalizada en {final_time:.3f}s")
        logger.info(f"[{request_id}] Total requests procesadas en esta sesión: {request_counter}")

# Endpoint adicional para obtener métricas
@router.get("/ask/metrics")
async def get_metrics():
    """Endpoint para obtener métricas del servicio"""
    logger.info("📊 Solicitadas métricas del servicio")
    
    metrics = {
        "total_requests": request_counter,
        "timestamp": datetime.now().isoformat(),
        "service": "ask_question",
        "status": "operational"
    }
    
    logger.info(f"Métricas actuales: {json.dumps(metrics, indent=2)}")
    return metrics

