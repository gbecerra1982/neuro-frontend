# planning_agent/agente.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict
from src.planning_agent.nodes import (
    schema_retriever, planner, execute_sql, verify_sql, formatter
)

class AgentState(TypedDict):
    question: str
    schema_hint: str
    current_sql: str
    query_result: str
    sql_error: str | None
    plan: str
    retry: int
    verified: bool
    gral_ans: str

def planning_agent_app():
    workflow = StateGraph(AgentState)
    memory   = MemorySaver()

    # Nodos
    workflow.add_node("schema_retriever", schema_retriever)
    workflow.add_node("planner", planner)
    workflow.add_node("execute_sql", execute_sql)
    workflow.add_node("verify_sql", verify_sql)
    workflow.add_node("formatter", formatter)

    # Aristas
    workflow.set_entry_point("schema_retriever")
    workflow.add_edge("schema_retriever", "planner")
    workflow.add_edge("planner", "execute_sql")
    workflow.add_edge("execute_sql", "verify_sql")

    def route_verification(state):
        return "planner" if not state["verified"] else "formatter"

    workflow.add_conditional_edges(
        "verify_sql",
        route_verification,
        {"planner": "planner", "formatter": "formatter"}
    )
    workflow.add_edge("formatter", END)

    # compilar ➜ devuelve CompiledStateGraph
    return workflow.compile(checkpointer=memory)   # ← como en tu otro grafo [1]

# Sólo para prueba manual
if __name__ == "__main__":
    from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

    agent = planning_agent_app()
    # invocar pasando el estado inicial obligatorio
    config = {"configurable": {"thread_id": 1}}
    result_state = agent.invoke({"question": "Dame un resumen de lo que están haciendo los pozos activos en perforación en lomas la lata"}, config)
    print(result_state["gral_ans"])