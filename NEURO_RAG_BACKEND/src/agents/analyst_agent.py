from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.prebuilt import create_react_agent
from llm.llm import llm_gpt_o3_mini
from workflows.states import OverallState
from prompt_engineering.query_prompts import prompt_analyst


prompt_analyst_template = ChatPromptTemplate.from_messages([
    ("system", prompt_analyst["agent"]["system"]),
    MessagesPlaceholder(variable_name="messages"),
])


analyst_agent = create_react_agent(
    model=llm_gpt_o3_mini,
    tools=[],
    name="analyst_agent",
    prompt=prompt_analyst_template,
    state_schema=OverallState,
)

