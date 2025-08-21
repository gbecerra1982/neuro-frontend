from langchain.tools import Tool
from workflows.sql_workflow import sql_workflow
from workflows.states import SqlAgentState


def sql_tool_fn(question: str) -> SqlAgentState:
    return sql_workflow.invoke(input={"question": question})


sql_tool = Tool(
    name="sql_tool",
    description="Ejecuta consultas SQL generadas, las procesa y devuelve respuestas.",
    func=sql_tool_fn,
)

