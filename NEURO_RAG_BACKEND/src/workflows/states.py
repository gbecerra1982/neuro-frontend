from typing import TypedDict, Annotated, List
import pandas as pd
from langgraph.graph.message import AnyMessage, add_messages


class SqlStepOutput(TypedDict):
    planning: str
    reasoning: str
    step: str
    sql: str
    success: bool
    result: str


class MessagesState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]


class SqlAgentState(MessagesState):
    question: str
    sql_query: str
    sql_results: str
    accumulated_sql_results: Annotated[List[SqlStepOutput], list.__add__]
    answer: str
    sql_results_accum: List[str]


class AnalystState(TypedDict):
    sql_results_dfs: List[pd.DataFrame]
    computed_analysis: str


class OverallState(SqlAgentState):
    question: str
    accumulated_sql_results: Annotated[List[SqlStepOutput], list.__add__]
    sql_results_dfs: List[pd.DataFrame]
    analysis_result: str
    rag_result: Annotated[List[str], list.__add__]

    pozos:List[str]

