# benchmark_simple.py
import time
import traceback
from typing import List, Dict
import os
import pandas as pd
import uuid
###############################################################################
# 1) ------------------ CAMBIA SOLO ESTA SECCIÓN SI QUIERES -------------------
###############################################################################
# Aquí instancias el agente que desees usar
# from src.agente import planning_agent_app       # <-- cámbialo si necesitas otro
# AGENT = planning_agent_app()

import uuid
import os
from src.pywo_aux_func import replace_token
from src.agente import minipywo_app
import csv


THREAD_ID = os.environ.get("THREAD_ID", str(uuid.uuid4()))
config = {"configurable": {"thread_id": THREAD_ID}}

def create_user_session_id(user_id: int) -> str:
    """
    Crea un session_id que incluye el user_id para tracking
    """
    import uuid
    return f"user{user_id}_session_{str(uuid.uuid4())}"

def test_with_memory_local(user_id: int, question: str):
    """
    Prueba el flujo con memoria de largo plazo usando minipywo_app_with_memory.
    """
    from src.langmem_functions import create_user_session_id

    session_id = create_user_session_id(user_id)
    config = {"configurable": {"thread_id": session_id}}

    app = minipywo_app()

    initial_state = {
        "question": question,
        "session_id": session_id,
        "user_id": user_id,
        "sql_query": "",
        "query_result": "",
        "relevance": "",
        "sql_error": False,
        "name_validation": False,
        "tipo_consulta": "",
        "gral_ans": "",
        "entity": False,
        "correction_success": False,
        "name_correction": False,
        "lista_equipos_activos": [],
        "lista_pozos_activos_perforacion": [],
        "dt": 0.0,
        "messages": []
    }

    result = app.invoke(initial_state, config)
    print(f"👤 Usuario {user_id} [MEMORIA]: {result['query_result'][:200]}...")
    return result


# user_question_0 = "Hola mi nobre es Alfonso, como andas?"
# test_with_memory_local(144, user_question_0)


def invoke_agent(question: str) -> str:
    """
    Llama al agente global y devuelve la respuesta.
    Si tu agente escribe la respuesta en otra clave del estado final,
    cámbiala aquí y listo.
    """
    question = "cantidad de pozos por provincia"
    res = test_with_memory_local(144, question)
    return res 

invoke_agent("cantidad de pozos por provincia")
###############################################################################

# 2) ------------------------- LISTA DE PREGUNTAS -----------------------------
TEST_SET: List[Dict] = [
    "¿Cuáles son los equipos activos?",
    "Dame la producción del pozo 654 el último mes",
    "¿Cuánto diesel se consumió la semana pasada?",
]

# 3) --------------------------- FUNCIÓN RUNNER -------------------------------
def run_benchmark(test_set: List[Dict],
                  output_file: str = "benchmark/runs/benchmark.xlsx") -> None:
    rows = []

    for test in test_set:
        name      = test["name"]
        question  = test["question"]

        try:
            t0 = time.perf_counter()
            answer = invoke_agent(question)
            latency = time.perf_counter() - t0
            print(f"✔️  {name:20s} | {latency:.2f}s")
        except Exception as exc:
            latency = None
            answer  = f"ERROR: {exc}"
            traceback.print_exc()
            print(f"❌  {name:20s} | ERROR")

        rows.append(
            {"nombre_test": name,
             "pregunta_target": question,
             "respuesta": answer,
             "latencia": latency}
        )

    pd.DataFrame(rows).to_excel(output_file, index=False)
    print(f"\nResultados guardados en {output_file}")

# 4) ------------------------------- MAIN -------------------------------------
if __name__ == "__main__":
    run_benchmark(TEST_SET)