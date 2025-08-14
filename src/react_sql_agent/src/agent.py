"""
react_sql_agent.py
Agente ReAct con LangGraph que usa:
    • get_query -> genera la SQL
    • ejecutar_consulta -> ejecuta la SQL y guarda el resultado
"""

from __future__ import annotations
import json, uuid, time
from typing import TypedDict, List, Dict, Any, Annotated
import os

from langchain_core.messages import AnyMessage
from langchain.schema import (
    SystemMessage, HumanMessage, AIMessage, BaseMessage,
    AgentAction, AgentFinish
)
from langchain.agents.output_parsers import ReActJsonSingleInputOutputParser
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from src.pywo_aux_func import llm_gpt4o as llm
from src.util import GetLogger

LOGLEVEL = os.environ.get('LOGLEVEL_SQLAGENT', 'DEBUG').upper()
logger=GetLogger(__name__, level=LOGLEVEL).logger

# --------------------------------------------------------------------------
# 1.  STATE QUE VIAJA POR EL GRAFO
# --------------------------------------------------------------------------
class AgentSubState(TypedDict):
    messages       : Annotated[List[AnyMessage], add_messages]         # historial ReAct
    question       : str                      # última pregunta de usuario
    sql_query      : str | None               # query producida por get_query
    sql_critique   : Dict[str, Any]           # si tuvieras un paso de crítica
    query_result   : str | None               # markdown/str con los resultados
    dt             : float                    # tiempo acumulado
    session_id     : str
    user_id        : str | None
    parsed         : AgentAction | AgentFinish | None  # <-- lo que devuelve parser
    should_end     : bool | None              # para el condicional


# --------------------------------------------------------------------------
# 2.  IMPORTA TUS FUNCIONES ORIGINALES COMO “TOOLS”
# --------------------------------------------------------------------------
from src.minipywo import get_query_, ejecutar_consulta_

# --------------------------------------------------------------------------
# 3.  LLM + PROMPT PARA PATRÓN REACT
# --------------------------------------------------------------------------
from src.react_sql_agent.src.prompt import agent_prompt
system_prompt = agent_prompt["system"]

react_prompt_header = [SystemMessage(content=system_prompt)]
react_parser = ReActJsonSingleInputOutputParser()  

# --------------------------------------------------------------------------
# 4.  NODOS
# --------------------------------------------------------------------------
def run_agent(state: AgentSubState) -> AgentSubState:
    """
    Nodo 1: LLM razona y decide la proxima accion.
    """
    msgs = react_prompt_header + state["messages"]
    llm_response = llm(msgs, stop=["Observation"]).content
    parsed = react_parser.parse(llm_response)
    print("--------------------------------------------------------------------------llm_response----------------------------------------------------------------------")
    print(llm_response)
    print("--------------------------------------------------------------------------llm_response parsed-----------------------------------------------------------------")
    print(parsed)
    # Guardamos en historial
    state["messages"].append(AIMessage(content=llm_response))
    state["parsed"] = parsed
    return state


def execute_tools(state: AgentSubState) -> AgentSubState:
    """
    Nodo 2: ejecuta el tool pedido por el agente.
    """
    print("---------------------------------execute_tools---------------------------------")
    parsed = state["parsed"]

    # El agente terminó
    if isinstance(parsed, AgentFinish):
        state["should_end"] = True
        return state

    # Solo esperamos dos tools posibles
    if parsed.tool == "get_query":
        state["question"] = parsed.tool_input
        
        state['sql_query'] = get_query_(state["question"])                         # <-- tu función
        observation = f"SQL generada:\n```sql\n{state['sql_query']}\n```"

    elif parsed.tool == "ejecutar_consulta":
        state["query_result"] = ejecutar_consulta_(state['sql_query'])                 # <-- tu función
        observation = state["query_result"]
    
    elif parsed.tool == "ejecutar_consulta_simple":
        sql_query_fix = parsed.tool_input
        state["query_result"] = ejecutar_consulta_(sql_query_fix)                 # <-- tu función
        observation = state["query_result"]

    else:
        observation = f"Tool {parsed.tool} no soportada."
    
    # Añadimos Observation al historial ReAct
    state["messages"].append(
        AIMessage(content=f"Observation: {observation}")
    )
    state["should_end"] = False
    return state


def should_continue(state: AgentSubState) -> str:
    """
    Arista condicional: ¿volvemos a run_agent o terminamos?
    """
    print("---------------------------------should_continue---------------------------------")
    if state.get("should_end"):
        return END
    return "run_agent"


# --------------------------------------------------------------------------
# 5.  GRAFO
# --------------------------------------------------------------------------
graph = StateGraph(AgentSubState)
memory = MemorySaver()

graph.add_node("run_agent", run_agent)
graph.add_node("execute_tools", execute_tools)

graph.add_edge("run_agent", "execute_tools")
graph.add_conditional_edges("execute_tools", should_continue)

graph.set_entry_point("run_agent")
react_graph = graph.compile(checkpointer=memory)


# --------------------------------------------------------------------------
# 6.  EJECUCIÓN DE EJEMPLO
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import pprint, datetime

    user_question = input("Usuario: ")
    session_id = str(uuid.uuid4())
    init_state: AgentSubState = {
        "messages": [HumanMessage(content=user_question)],
        "question": user_question,
        "sql_query": None,
        "sql_critique": {},
        "query_result": None,
        "dt": 0.0,
        "session_id": session_id,
        "user_id": None,
        "parsed": None,
        "should_end": False
    }

    config = {"configurable": {"thread_id": session_id}}
    # stream() devuelve los estados sucesivos en tiempo real
    print("\n--- INICIANDO AGENTE ---\n")
    for step_state in react_graph.stream(init_state, config):
        # imprimimos lo último que haya dicho el modelo
        # last_msg = step_state["messages"][-1]
        
        print(step_state)
        # también podrías mostrar la SQL o los tiempos si quieres
    
    print("\n--- CONVERSACIÓN TERMINADA ---")