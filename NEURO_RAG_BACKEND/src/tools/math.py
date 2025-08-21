from langchain.tools import Tool


def multiply(a: int, b: int) -> float:
    return a * b


math_tool = Tool(
    name="math_tool",
    description="Realiza cálculos matemáticos simples como suma, resta, multiplicaciones.",
    func=multiply,
)

