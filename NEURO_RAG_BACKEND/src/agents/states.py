import operator
import pandas as pd
from typing import TypedDict, List, Annotated
from langgraph.graph.message import AnyMessage, add_messages

# STATES Y DATA STRUCTURES
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
    accumulated_sql_results: Annotated[List[SqlStepOutput],operator.add]
    answer: str
    sql_results_accum: List[str]
    messages: Annotated[List[AnyMessage], add_messages]

class AnalystState(TypedDict):
    sql_results_dfs: List[pd.DataFrame]
    computed_analysis: str

class OverallState(TypedDict):
    user_question: str
    sql_results_dfs: List[pd.DataFrame]
    final_analysis: str