# wrapper_react_sql.py
import uuid
from typing import Dict, Any
from langchain.schema import HumanMessage
from .agent import react_graph     # <- importa grafo ReAct
# import src.minipywo as AgentState                      # para el tipo AgentState

def react_sql_wrapper(state: AgentState) -> AgentState:
    """Ejecuta el grafo ReAct (get_query + ejecutar_consulta) como un nodo único
    dentro de otro flujo y devuelve el estado del grafo padre actualizado."""
    
    # 1) Construir estado inicial para el sub-grafo
    history = state.get("messages", [])
    print(f"history: {history}")
    if not history:
        # ¡IMPORTANTE! Usar la pregunta en HumanMessage
        history = [HumanMessage(content=state["question"])]

    sub_state = {
        "messages": history,
        "question"   : state["question"],
        "sql_query"  : None,
        "sql_critique": {},
        "query_result": None,
        "dt"         : state.get("dt", 0.0),
        "session_id" : state.get("session_id", str(uuid.uuid4())),
        "user_id"    : state.get("user_id"),
        "parsed"     : None,
        "should_end" : False,
    }

    # 2) Ejecutar el grafo ReAct — una sola llamada es suficiente
    sub_state = react_graph.invoke(sub_state)      # o .invoke_stream si quieres ver pasos

    # 3) Sincronizar la información relevante al estado padre
    state["sql_query"]    = sub_state.get("sql_query")
    state["query_result"] = sub_state.get("query_result")
    # opcional: si quieres conservar todo el historial conjunto
    state.setdefault("messages", []).extend(
        [m for m in sub_state["messages"] if m not in state["messages"]]
    )
    state["dt"] = sub_state.get("dt", state.get("dt", 0.0))

    # 4) ¡Listo!
    return state