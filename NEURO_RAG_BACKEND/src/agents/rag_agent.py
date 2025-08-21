from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.prebuilt import create_react_agent
from llm.llm import llm_gpt_4o_mini
from workflows.states import OverallState
from tools.rag import rag_tool
from prompt_engineering.query_prompts import prompt_rag
from pydantic import BaseModel, Field
from typing import Optional
# from utils.utils import get_connection_to_td
from config.settings import (
    TD_HOST,
    TD_USER,
    TD_PASS,
    LOGLEVEL,
    LOGMECH,
    CURRENT_DATE
)
from utils.util_logger import GetLogger
import logging
 
# Configurar logging adicional
logging.basicConfig(level=logging.INFO)
rag_logger = logging.getLogger("rag_agent")
 
 
logger = GetLogger(__name__, level=LOGLEVEL, log_file='data/app_logs.log').logger
 
 
 
prompt_rag_template = ChatPromptTemplate.from_messages([
    ("system", prompt_rag["agent"]["system"]),
    MessagesPlaceholder(variable_name="messages"),
])


rag_agent = create_react_agent(
    model=llm_gpt_4o_mini,
    tools=[rag_tool],
    name="rag_agent",
    prompt=prompt_rag_template,
)