import time
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from utils.util_logger import GetLogger
from config.settings import LOGLEVEL
from prompt_engineering.query_prompts import query_prompt_format_answer
from llm.llm import llm_gpt_4o_mini
from workflows.states import SqlAgentState


logger = GetLogger(__name__, level=LOGLEVEL, log_file='src/data/app_logs.log').logger


def format_sql_results(state: SqlAgentState, llm_model=llm_gpt_4o_mini) -> SqlAgentState:
    start = time.perf_counter()
    pregunta = state["question"]
    sql_query = state["sql_query"]
    result = state["sql_results"]

    logger.info(f"Pregunta: {pregunta}")
    logger.info(f"Query ejecutada: {sql_query}")
    logger.info(f"Resultados obtenidos: {len(result) if result else 0} caracteres")

    generate_prompt = ChatPromptTemplate.from_messages([
        ("system", query_prompt_format_answer['system']),
        ("human", query_prompt_format_answer['human']),
    ])
    human_response = generate_prompt | llm_model | StrOutputParser()

    try:
        logger.info("Generando respuesta final con LLM...")
        answer = human_response.invoke({'question': pregunta, 'query': sql_query, 'results': result})
        state["answer"] = answer
        state.setdefault("sql_results_accum", []).append(answer)
        end = time.perf_counter()
        logger.info(f"Respuesta formateada en {end - start:.2f} segundos")
        logger.info(f"Respuesta generada: {answer}")
    except Exception as e:
        logger.error(f"Error formateando respuesta: {e}")
        state["answer"] = f"Error al formatear la respuesta: {str(e)}"

    return state

