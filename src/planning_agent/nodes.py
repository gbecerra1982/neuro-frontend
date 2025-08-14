# planning_agent/nodes.py
import json
import time
import logging
from langchain.schema import AIMessage

from src.planning_agent.prompts       import PLAN_PROMPT, VERIFY_PROMPT, ANSWER_PROMPT
from src.planning_agent.teradata_wrapper import run_sql_limited
from src.tables_retrieval import tables_index_retrieval
from src.pywo_aux_func                import (
    llm_gpt_o3_mini as llm_big,
    llm_gpt_4o_mini as llm_small,
)
from src.planning_agent.helpers import _json_from_llm

# ──────────────────────────────────────
# Configuración básica de logging
# ──────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,                          # cámbialo a DEBUG si quieres ver TODO
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("planning_agent")

# ──────────────────────────────────────
# Helpers
# ──────────────────────────────────────
def _to_str(msg):
    """Extrae el texto de AIMessage o pasa str tal cual."""
    return msg.content if isinstance(msg, AIMessage) else str(msg)

# ──────────────────────────────────────
# NODOS
# ──────────────────────────────────────
def schema_retriever(state):
    q = state["question"]
    t0 = time.perf_counter()
    # q = "hola"
    long, short = tables_index_retrieval(q)
    state["schema_hint"] = long
    log.info("🔍 Retrieval: %d chars de esquema en %.2fs", len(short), time.perf_counter() - t0)
    if log.isEnabledFor(logging.DEBUG):
        log.debug("Esquema relevante:\n%s", long)
    return state


def planner(state):
    prompt = PLAN_PROMPT.format(
        question=state["question"],
        schema_hint=state["schema_hint"]
    )
    log.info("🧠 Planner: enviando prompt (%d chars)…", len(prompt))
    raw_msg = llm_big.invoke(prompt)
    raw = _to_str(raw_msg)

    try:
        data = _json_from_llm(raw)
        log.info("Planner: ", data)
    except json.JSONDecodeError as e:
        log.error("Planner: JSON malformado (%s). Raw:\n%s", e, raw)
        raise

    state["plan"]        = data.get("plan")
    state["current_sql"] = data.get("sql")
    state["retry"]       = 0

    log.info("🧠 Planner → plan: %s", state["plan"])
    log.info("🧠 Planner → SQL inicial:\n%s", state["current_sql"])
    return state


def execute_sql(state):
    sql_to_run = state["current_sql"]
    log.info("🚀 Execute: intentamos correr la query (retry %d)…", state["retry"])
    if log.isEnabledFor(logging.DEBUG):
        log.debug("SQL a ejecutar:\n%s", sql_to_run)

    t0 = time.perf_counter()
    df, err = run_sql_limited(sql_to_run)
    elapsed = time.perf_counter() - t0

    state["query_result"] = df
    state["sql_error"]    = err

    if err is None:
        log.info("🚀 Execute: éxito, %d filas, %.2fs", len(df), elapsed)
    else:
        log.warning("🚀 Execute: error tras %.2fs → %s", elapsed, err)

    return state


def verify_sql(state):
    if state["sql_error"] is None:
        state["verified"] = True
        return state

    prompt = VERIFY_PROMPT.format(
        sql   = state["current_sql"],
        error = state["sql_error"]
    )
    log.info("🛠  Verifier: solicitando corrección (retry %d)…", state["retry"])
    raw_msg = llm_small.invoke(prompt)
    raw = _to_str(raw_msg)
    log.info("Verifier raw -> %s", raw)
    try:
        data = _json_from_llm(raw)
    except json.JSONDecodeError as e:
        log.error("Verifier: JSON malformado (%s). Raw:\n%s", e, raw)
        state["verified"] = True   # evita bucle infinito
        return state

    if data.get("should_retry") and state["retry"] < 2:
        state["retry"]      += 1
        state["current_sql"] = data.get("fixed_sql", state["current_sql"])
        state["verified"]    = False
        log.info("🛠  Verifier: reintento %d aceptado. SQL corregido:\n%s",
                 state["retry"], state["current_sql"])
    else:
        state["verified"] = True
        log.info("🛠  Verifier: no se reintenta, pasamos a formatter")

    return state


def formatter(state):
    prompt = ANSWER_PROMPT.format(
        question = state["question"],
        result   = state["query_result"]
    )
    log.info("📦 Formatter: generando respuesta final…")
    ans_msg = llm_small.invoke(prompt)
    state["gral_ans"] = _to_str(ans_msg)
    if log.isEnabledFor(logging.DEBUG):
        log.debug("Respuesta final:\n%s", state["gral_ans"])
    return state