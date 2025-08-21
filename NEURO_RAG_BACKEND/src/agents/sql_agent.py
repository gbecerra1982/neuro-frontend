import datetime
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.prebuilt import create_react_agent
from llm.llm import llm_gpt_4o_mini
from tools.sql import sql_tool
from tools.math import math_tool
from workflows.states import SqlAgentState
from prompt_engineering.query_prompts import prompt_sql_agent
from config.settings import CURRENT_DATE, CURRENT_DAY


prompt_sql_agent_template = ChatPromptTemplate.from_messages([
    ("system", prompt_sql_agent["agent"]["system"].format(current_date=CURRENT_DATE, current_day=CURRENT_DAY)),
    ("user", prompt_sql_agent["agent"]["user"]),
    MessagesPlaceholder(variable_name="messages"),
])


sql_agent = create_react_agent(
    model=llm_gpt_4o_mini,
    tools=[sql_tool, math_tool],
    name="sql_agent",
    prompt=prompt_sql_agent_template,
    state_schema=SqlAgentState,
)

