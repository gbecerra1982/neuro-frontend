from langgraph.graph import StateGraph, START, END
from workflows.states import SqlAgentState
from services.sql_generator import generate_sql_query
from services.sql_executor import execute_sql_query
from services.sql_formatter import format_sql_results


def build_sql_workflow(state_schema=SqlAgentState) -> StateGraph:
    graph = StateGraph(state_schema)
    graph.set_entry_point("generate_sql")

    graph.add_node("generate_sql", generate_sql_query)
    graph.add_node("execute_sql", execute_sql_query)
    graph.add_node("format_results", format_sql_results)

    graph.add_edge(START, "generate_sql")
    graph.add_edge("generate_sql", "execute_sql")
    graph.add_edge("execute_sql", "format_results")
    graph.add_edge("format_results", END)
    return graph.compile()


sql_workflow = build_sql_workflow(state_schema=SqlAgentState)

