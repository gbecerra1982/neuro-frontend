import json
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
# from langgraph_supervisor import create_supervisor    # Cambiado de langgraph_supervisor
from agents.rag_agent import rag_agent
#from workflows.states import OverallState
#from agents.rag_doc_agent import rag_doc_agent, create_rag_doc_agent
from agents.rag_agent import rag_agent
from tools.rag import rag_tool
from llm.llm import llm_gpt_4o_mini, llm_gpt_4o, llm_gpt_4_1_mini
from prompt_engineering.query_prompts import prompt_supervisor
from config.memory import get_memory_checkpointer
from config.settings import CURRENT_DATE, CURRENT_DAY
from utils.util_logger import GetLogger
from config.settings import LOGLEVEL
from datetime import datetime
import os
# from utils.utils import get_connection_to_td
from config.settings import (
    TD_HOST,
    TD_USER,
    TD_PASS,
    LOGLEVEL,
    LOGMECH,
    CURRENT_DATE
)
 
# logger = GetLogger(__name__, level=LOGLEVEL, log_file='data/app_logs.log').logger

log_dir = os.path.join(os.getcwd(), 'data')
 
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    print(f"Directorio creado: {log_dir}")
 
logger = GetLogger(__name__, level=LOGLEVEL, log_file=os.path.join(log_dir, 'app_logs.log')).logger


from typing import Iterable, List, Any
import json, ast
 
# Opcional: si usás LangChain/LangGraph
try:
    from langchain_core.messages import ToolMessage, BaseMessage
except Exception:
    ToolMessage = None
    BaseMessage = object  # fallback
 
def _try_parse_content(content: Any) -> Any:
    """Devuelve dict/list si el content parece JSON o literal de Python; si no, lo deja como string."""
    if isinstance(content, (dict, list)) or content is None:
        return content
    if isinstance(content, str):
        s = content.strip()
        for parser in (json.loads, ast.literal_eval):
            try:
                return parser(s)
            except Exception:
                pass
    return content
 
def get_tool_contents(messages: Iterable[BaseMessage]) -> List[Any]:
    """Extrae el contenido de todos los ToolMessage."""
    out = []
    for m in messages:
        is_tool = (
            (ToolMessage and isinstance(m, ToolMessage)) or
            getattr(m, "type", None) == "tool" or
            m.__class__.__name__ == "ToolMessage"            # por si cambió el import
        )
        if is_tool:
            out.append(_try_parse_content(getattr(m, "content", None)))
    return out
 
def get_last_tool_content(messages: Iterable[BaseMessage]) -> Any:
    """Extrae el content del último ToolMessage (útil si querés solo el último resultado de tool)."""
    for m in reversed(list(messages)):
        is_tool = (
            (ToolMessage and isinstance(m, ToolMessage)) or
            getattr(m, "type", None) == "tool" or
            m.__class__.__name__ == "ToolMessage"
        )
        if is_tool:
            return _try_parse_content(getattr(m, "content", None))
    return None 

# def _compile_graph():
#     memory = get_memory_checkpointer()
#     try:
#         if memory is not None:
#             graph = _supervisor.compile(checkpointer=memory)
#             logger.info("Supervisor compilado con memoria")
#             return graph
#         logger.warning("Memory checkpointer no disponible, compilando sin memoria")
#         return _supervisor.compile()
#     except Exception as e:
#         logger.error(f"Error compilando supervisor: {e}. Compilando sin memoria")
#         return _supervisor.compile()

# def _fetch_dynamic_context_sql():
#     """
#     Ejecuta una consulta SQL para obtener contexto dinámico para el prompt RAG.
#     Devuelve un string listo para inyectar en el prompt o None si falla.
#     """
#     fecha_dinamica_3_meses_atras='2025-05-01'
#     sql =  f"""SELECT DISTINCT p.Boca_Pozo_Nombre_Corto_Oficial
#     FROM P_DIM_V.UPS_DIM_EQUIPOS_ACTIVOS ea
#     JOIN P_DIM_V.UPS_DIM_BOCA_POZO p ON p.Well_Id = ea.WELL_ID
#     WHERE p.Boca_Pozo_Nombre_Corto_Oficial IS NOT NULL
#     AND ea.Event_Code = 'PER'
#     UNION
#     SELECT DISTINCT p.Boca_Pozo_Nombre_Corto_Oficial
#     FROM P_DIM_V.UPS_FT_DLY_OPERACIONES o
#     JOIN P_DIM_V.UPS_DIM_BOCA_POZO p ON p.Well_Id = o.WELL_ID
#     AND o.Evento_Cod = 'PER'
#     WHERE o.FECHA >= DATE '{fecha_dinamica_3_meses_atras}'"""
#     try:
#         conn = get_connection_to_td(TD_HOST, TD_USER, TD_PASS, LOGMECH)
#         cur = conn.cursor()
#         cur.execute(sql)
#         rows = cur.fetchall()
#         cur.close()
#         conn.close()
#         if not rows:
#             return None
#         # Formateo simple como lista
#         formatted = ", ".join(f"{pozo[0]}" for pozo in rows)
#         return formatted
#     except Exception as e:
#         logger.warning(f"No se pudo cargar contexto dinámico para prompt RAG: {e}")
#         return None
 
 
# try:
#     dynamic_context = _fetch_dynamic_context_sql()
#     logger.info(f' Contexto dinámico para RAG: {dynamic_context}')
# except Exception as e:
#     # En caso de error, manejarlo de forma adecuada
#     dynamic_context = None
#     logger.error(f"Error al recuperar contexto SQL: {e}") 

prompt_supervisor_template = ChatPromptTemplate.from_messages([
    ("system", prompt_supervisor["agent"]["system"].format(current_date=CURRENT_DATE, current_day=CURRENT_DAY)),
    ("user", prompt_supervisor["agent"]["user"]),
    MessagesPlaceholder(variable_name="messages"),
])
 
 
_prompt_triage_template = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            """Eres un clasificador estricto. Tu tarea es determinar si la pregunta del usuario
está dentro del dominio de esta aplicación. La aplicación SOLO responde
sobre la industria de Gas/Oil en Vaca Muerta (Argentina), específicamente
consultas de pozos, equipos y yacimientos (producción, métricas, fechas,
identificadores, planificación, etc.). Si la pregunta no está relacionada con
ese dominio, debes marcarla como fuera de alcance.
 
Responde EXCLUSIVAMENTE en JSON válido con las claves:
{{
    "is_relevant": boolean,
    "confidence": number,
    "reason": string
}}
No agregues texto adicional fuera del JSON."""
        ),
    ),
    (
        "user",
        (
            "Pregunta: {question}\n\n"
            "Regla: Marca como relevante solo si trata sobre Vaca Muerta y Gas/Oil\n"
            "(pozos, equipos, yacimientos, producción, KPIs operativos, etc.)."
        ),
    ),
])

# _supervisor = create_supervisor(
#     model=llm_gpt_4_1_mini,
#     agents=[rag_agent], 
#     prompt=prompt_supervisor_template,
#     output_mode="full_history"
# )
 
 
def _is_relevant_keyword_heuristic(user_question: str) -> bool:
    """Heurística simple por palabras clave como respaldo del LLM.
 
    Considera la pregunta relevante si contiene términos claros del dominio.
    """
    if not user_question:
        return False
    text = user_question.lower()
    keywords = [
        # Dominio general
        "neuquen", "neuquén", "gas", "oil", "petroleo", "petróleo",
        # Objetos del dominio
        "pozo", "pozos", "equipo", "equipos", "yacim", "yacimiento", "yacimientos",
        # Operaciones y mediciones
        "produccion", "producción", "novedades", "PADs", "presion", "presión",
        "bbl", "m3", "mm3", "flujo", "caudal", "kpi", "operativo", "drilling",
        "perforacion", "perforación", "completacion", "completación", "workover",
        "rig", "well", "pad", "equipo", "pozo",
    ]
    return any(k in text for k in keywords)
 
 
def _triage_question(user_question: str) -> dict:
    """Evalúa si la pregunta es relevante para el dominio de la app.
 
    Retorna un diccionario con: {
      "is_relevant": bool,
      "confidence": float,
      "reason": str,
      "source": "llm"|"heuristic"|"fallback"
    }
    """
    try:
        chain = _prompt_triage_template | llm_gpt_4o_mini
        response = chain.invoke({"question": user_question})
        content = getattr(response, "content", "")
        data = {}
        try:
            data = json.loads(content)
        except Exception:
            # En caso de que el modelo no devuelva JSON puro, intenta extraer
            # el primer bloque JSON válido simples (fallback liviano)
            try:
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1 and end > start:
                    data = json.loads(content[start : end + 1])
            except Exception:
                data = {}
 
        if isinstance(data, dict) and "is_relevant" in data:
            is_relevant = bool(data.get("is_relevant", False))
            confidence = float(data.get("confidence", 0.0))
            reason = str(data.get("reason", ""))
            print()
            return {
                "is_relevant": is_relevant,
                "confidence": confidence,
                "reason": reason,
                "source": "llm",
            }
 
        # Fallback: heurística por palabras clave
        is_rel = _is_relevant_keyword_heuristic(user_question)
        print('is_rel',is_rel)
        return {
            "is_relevant": is_rel,
            "confidence": 0.5 if is_rel else 0.2,
            "reason": "Clasificación por heurística de palabras clave",
            "source": "heuristic",
        }
    except Exception as triage_error:
        # En caso de error, permitir el paso para no bloquear UX
        try:
            logger.error(f"Error en triage: {str(triage_error)}")
        except Exception:
            pass
        return {
            "is_relevant": True,
            "confidence": 0.0,
            "reason": "Fallback por error en triage",
            "source": "fallback",
        }
 
 
# Función simplificada para compilar el agente RAG si es necesario
def _compile_rag_agent():
    """Compila el agente RAG con memoria si está disponible."""
    memory = get_memory_checkpointer()
    try:
        if memory is not None:
            # El agente RAG ya está compilado, solo retornarlo
            return rag_agent
        logger.warning("Memory checkpointer no disponible, usando agente RAG sin memoria")
        return rag_agent
    except Exception as e:
        logger.error(f"Error con memoria: {e}. Usando agente RAG sin memoria")
        return rag_agent
 
 
def procesar_consulta_langgraph(user_question: str, session_id: str = "default_session") -> tuple[str, str]:
    """Procesa la consulta aplicando un triage previo y luego el agente RAG si corresponde."""
    logger.info(f"Procesando consulta para sesión: {session_id}")
    print(f"🚀 SUPERVISOR: Procesando consulta: '{user_question}'")
 
    # Normalización de session_id
    if not session_id or session_id.strip() == "":
        session_id = "default_session"
        logger.warning("Session ID vacío, usando 'default_session'")
 
    # TRIAGE: decidir si la pregunta está dentro del alcance del dominio
    # triage = _triage_question(user_question)
    # logger.info(
    #     "Triage => is_relevant=%s, confidence=%.2f, source=%s, reason=%s",
    #     triage.get("is_relevant"), triage.get("confidence", 0.0), triage.get("source"), triage.get("reason", ""),
    # )
    # print(f" TRIAGE: is_relevant={triage.get('is_relevant')}, confidence={triage.get('confidence', 0.0)}")
 
    # if not triage.get("is_relevant", False):
    #     fuera_de_scope = (
    #         "Tu consulta está fuera del alcance de esta aplicación. "
    #         "Solo puedo responder sobre pozos, equipos y yacimientos de Vaca Muerta "
    #     )
    #     logger.info(f"[X] CONSULTA FUERA DE ALCANCE: {fuera_de_scope}")
    #     return fuera_de_scope, session_id
 
    # CAMBIADO: Usar directamente el agente RAG en lugar del supervisor
    try:
        logger.info(f"[BOT] INVOCANDO AGENTE RAG...")
        # Crear un estado inicial compatible con el prompt RAG
       
        # El prompt template YA tiene las variables formateadas (pozos, today)
        # Solo necesitamos pasar messages
        initial_state = {
            "messages": [HumanMessage(content=user_question)]
        }
       
        logger.info(f" Estado inicial enviado al agente RAG: {initial_state}")
        logger.info(f" Configuración del agente RAG:")
        logger.info(f"  - Tipo de agente: {type(rag_agent).__name__}")
        logger.info(f"  - Herramientas disponibles: rag_tool (definida en rag_agent.py)")
       
        # react_graph = _compile_graph()
        config = {"configurable": {"thread_id": session_id}}
    
        try:
            output = rag_agent.invoke(
                input={
                    "question": user_question,
                    "messages": [{"role": "user", "content": user_question}],
                },
                config=config,
            )
        except Exception as invoke_error:
            logger.error(f"Error al invocar react_graph: {str(invoke_error)}")
            fallback_graph = rag_agent.compile()
            output = fallback_graph.invoke(
                input={
                    "question": user_question,
                    "messages": [{"role": "user", "content": user_question}],
                }
            )
        logger.info(f" Contenido del output: {output}")
       
        logger.info(f"Agente RAG ejecutado exitosamente")
       
        mensajes = output.get("messages", [])
        if not mensajes:
            logger.warning("No se obtuvieron mensajes en la respuesta")
            return "No se pudo obtener una respuesta: No hay mensajes disponibles.", session_id
        ultimo_mensaje = mensajes[-1]
        penultimo_mensaje = mensajes[-2]
        if isinstance(ultimo_mensaje, AIMessage):
            try:
                contenido = json.loads(ultimo_mensaje.content)
                return contenido, session_id
            except json.JSONDecodeError:
                return ultimo_mensaje.content, session_id

        else:
            return "El último mensaje no es de tipo AIMessage.", session_id

        
    except Exception as invoke_error:
        logger.error(f"Error al invocar agente RAG: {str(invoke_error)}")
        print(f"❌ ERROR al invocar agente RAG: {str(invoke_error)}")
        print(f"🔍 Tipo de error: {type(invoke_error).__name__}")
        print(f"🔍 Detalles del error: {str(invoke_error)}")
        return f"Error al procesar la consulta: {str(invoke_error)}", session_id
    