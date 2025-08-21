import time
import datetime
import pandas as pd  # noqa: F401 (para tipos en estados)
from langchain.prompts import ChatPromptTemplate
from utils.util_logger import GetLogger
from config.settings import LOGLEVEL, JSON_SCHEMA_PATH
from utils.utils import seleccionar_catalogo
from prompt_engineering.query_prompts import (
    query_prompt_sql,
    few_shot_queries,
)
from llm.llm import llm_gpt_4o_mini
from workflows.states import SqlAgentState, SqlStepOutput


logger = GetLogger(__name__, level=LOGLEVEL, log_file='src/data/app_logs.log').logger


def generate_sql_query(state: SqlAgentState, llm_model=llm_gpt_4o_mini) -> SqlAgentState:
    start = time.perf_counter()
    question = state['question']
    logger.info(f"Pregunta del usuario: {question}")

    selected_table = [
        "dt_comercial.VOLUMENES_PLANIFICADOS_YPF_V",
        "dt_comercial.CV_LOOP_V",
        "dt_comercial.COM_FT_DLY_DESPACHO_VOX",
        "dt_comercial.v_com_dim_producto_vox",
    ]
    fecha_actual = datetime.datetime.now().strftime('%Y-%m-%d')
    logger.info(f"Fecha actual: {fecha_actual}")
    logger.info(f"Tablas seleccionadas: {selected_table}")

    try:
        schema = seleccionar_catalogo(JSON_SCHEMA_PATH) if JSON_SCHEMA_PATH else {}
    except Exception as e:
        logger.error(f"Error cargando schema: {e}")
        schema = {}

    column_strings = []
    for table_name, table_info in schema.items():
        if table_name not in selected_table:
            continue
        columns_dict = table_info.get("columns", {})
        column_lines = [f">> {col_name}: {col_desc}" for col_name, col_desc in columns_dict.items()]
        table_string = f"Tabla: {table_name}\n" + "\n".join(column_lines)
        column_strings.append(table_string)
    column_list = "\n\n".join(column_strings)

    table_description = ""
    for table_name, table_info in schema.items():
        if table_name not in selected_table:
            continue
        description = table_info.get("description_short", "Sin descripción")
        table_description += f"Tabla: {table_name}\n>>Descripción: {description}\n\n"
    descriptions_short = table_description

    prompt = ChatPromptTemplate.from_messages([
        ("system", query_prompt_sql["system"]),
        ("human", query_prompt_sql["human"]),
    ])

    structured_llm = llm_model.with_structured_output(SqlStepOutput)
    get_query_chain = prompt | structured_llm

    try:
        consulta_dict = get_query_chain.invoke(input={
            "fecha_actual": fecha_actual,
            "pregunta_usuario": question,
            "selected_table": selected_table,
            "descriptions_short": descriptions_short,
            "column_list": column_list,
            "few_shot_queries": few_shot_queries,
        })
        state['sql_query'] = consulta_dict['sql']
        end = time.perf_counter()
        logger.info(f"Consulta SQL generada en {end - start:.2f} segundos")
        logger.info(f"SQL generado: {consulta_dict['sql']}")
    except Exception as e:
        logger.error(f"Error generando consulta SQL: {e}")
        state['sql_query'] = ""

    return state

