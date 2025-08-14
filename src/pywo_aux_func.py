import os
import json
from langchain_openai import AzureChatOpenAI
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
import teradatasql
import pandas as pd
import re

from src.sqltool_aux_fun import get_context_tables
from src.catalogo_retrieval import catalogo_index_retrieval
from src.columns_retrieval import columns_index_retrieval
from src.tables_retrieval import tables_index_retrieval
from src.util import GetLogger

from src.prompts.prompt_minipywoIII import tables_prompt, query_prompt_equipos
from src.sqltool_aux_fun import get_where_instances, get_improved_query
import time



LOGLEVEL = os.environ.get('LOGLEVEL_SQLAGENT', 'DEBUG').upper()
logger=GetLogger(__name__, level=LOGLEVEL).logger

logger=GetLogger(__name__, level=LOGLEVEL).logger
LOGLEVEL = os.environ.get('LOGLEVEL_ROOT', 'INFO').upper()
logger = GetLogger("", level=LOGLEVEL).logger

azure_openai_api_key = os.environ.get('AZURE_OPENAI_API_KEY')
azure_openai_endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT')


llm_gpt4o = AzureChatOpenAI(
        api_key=azure_openai_api_key,
        openai_api_version="2024-10-21",
        azure_deployment="chat4og",
        azure_endpoint=azure_openai_endpoint,
        model_name="gpt-4o",
        seed=42,
        timeout=180,
        temperature=0)

llm_gpt_4o_mini = AzureChatOpenAI(
        api_key=azure_openai_api_key,
        openai_api_version="2025-01-01-preview",
        azure_deployment="gpt-4o-mini",
        azure_endpoint=azure_openai_endpoint,
        model_name="gpt-4o-mini",
        seed=42,
        timeout=180,
        temperature=0)

llm_gpt_o3_mini = AzureChatOpenAI(
        api_key=azure_openai_api_key,
        openai_api_version="2025-01-01-preview",
        azure_deployment="o3-mini",
        azure_endpoint=azure_openai_endpoint,
        model_name="o3-mini",
        temperature= 1,
        seed=42,
        timeout=180)

def get_connection_to_db():
    td_user="YS02420"
    td_host="10.236.148.7"
    td_logmech="LDAP"
    td_pass = 'SalioElNuevoBillete#10000'
    conn_str = '{"host":"%s","user":"%s","password":"%s","logmech":"%s"}' % (
        td_host, td_user, td_pass, td_logmech
    )
    conn = teradatasql.connect(conn_str)
    return conn

#=======
TABLE_BOCA_POZO = "P_DIM_V.UPS_DIM_BOCA_POZO"
ZONA_VACA_MUERTA = "P_DIM_V.UPS_DIM_ZONA"
CONSULTA_BASE_VACA_MUERTA = "SELECT bp.*, z.* FROM P_DIM_V.UPS_DIM_BOCA_POZO bp JOIN P_DIM_V.UPS_DIM_ZONA z ON bp.yacimiento_id = z.yacimiento_id WHERE ((bp.SUBREGION_DBU_NAME IN ('Oeste Norte', 'Oeste Sur', 'Bandurria Sur', 'La Amarga Chica', 'Aguada del Chañar', 'Loma Campana', 'Sur I') AND bp.ACTIVO_DBU_NAME <> 'Aguada Toledo - Sierra Barrosa') OR (z.ZONA_YACIMIENTO = 'VM'))"
VACA_MUERTA = "vaca muerta"
NOC = "NOC"

# TRAIGO DE SQLTOOL:
def is_special_query(pregunta: str) -> bool:
    text = pregunta.lower()
    return VACA_MUERTA in text or NOC in text

def handle_special_query(pregunta: str):
    text = pregunta.lower()
    tables = [TABLE_BOCA_POZO, ZONA_VACA_MUERTA]
    result = {"tables": tables}
    if any(w in text for w in ["cuantos","cantidad","numero","número"]):
        result["query_type"] = "count"
    reasoning = "La consulta menciona 'Vaca Muerta' o 'NOC', seleccionando tablas específicas."
    logger.debug(f"Tablas (Vaca Muerta): {result}")
    logger.debug(f"SQL generado: {CONSULTA_BASE_VACA_MUERTA}")
    return result, reasoning, CONSULTA_BASE_VACA_MUERTA

def build_prompts():
    sys = tables_prompt["system"]
    if "JSON" not in sys:
        sys += "\n\nResponde con un objeto JSON válido …"
    usr = tables_prompt["user"]
    if "JSON" not in usr:
        usr += "\n\nFormato de respuesta: {{\"tables\": […]}}."
    return sys, usr

def call_llm_json(pregunta, few_shot, descriptions_long, llm_sql_tool):
    parser = JsonOutputParser()
    sys, usr = build_prompts()
    prompt = ChatPromptTemplate.from_messages([("system", sys),("user", usr)])
    chain = prompt | llm_sql_tool | parser
    logger.debug("Invocando LLM con JsonOutputParser…")
    return chain.invoke({
        "input": pregunta,
        "descriptions_long": descriptions_long,
        "few_shot_examples": few_shot
    })

def parse_selected_tables(selected: dict):
    if not isinstance(selected, dict) or "tables" not in selected:
        raise ValueError(f"Formato inesperado: {type(selected)}")
    try:
        return get_context_tables(selected)
    except Exception as e:
        logger.warning(f"Fallo con dict completo: {e}, intentando lista…")
        return get_context_tables(selected.get("tables", []))

#==========

def get_tables(pregunta_usuario, few_shot_tables, descriptions_long, llm_sql_tool):
    """
    Determina las tablas relevantes para una pregunta del usuario.
    """
    if is_special_query(pregunta_usuario):
        return handle_special_query(pregunta_usuario)

    logger.debug("Flujo normal de selección de tablas")
    try:
        selected_dict = call_llm_json(
            pregunta_usuario, few_shot_tables, descriptions_long, llm_sql_tool
        )
        logger.debug(f"Respuesta LLM (JSON): {selected_dict}")
        selected_table, reasoning = parse_selected_tables(selected_dict)
        return selected_table, reasoning, None
    except Exception as e:
        logger.error(f"Error procesando respuesta LLM: {e}")
        return [], "Error al procesar la respuesta del modelo.", None 

def _improve_query_if_needed(consulta, conn, pregunta_usuario, llm_model= llm_gpt4o):
    """
    Improve query if WHERE conditions exist.
    This is a private helper function used only within text_to_sql.
    """    
    improved_question = ""
    json_list = get_where_instances(consulta, llm_model)
    if json_list:
        # print('Ejecutando mejora de la consulta con get_improved_query')
        consulta, improved_question = get_improved_query(consulta, json_list, conn, llm_model, pregunta_usuario)
        # print(f'Consulta después de la mejora: {consulta}')
    else: 
        print('No es posible mejorar la query')
    return consulta, improved_question


def _get_column_information(pregunta_usuario, selected_table, embedding_vec=None):
    """
    Get column information for selected tables.
    This is a private helper function used only within text_to_sql.
    """
    column_list = ""
    for table_name in selected_table:
        print(f"Buscando columnas para la tabla {table_name}")
        columns, _ = columns_index_retrieval(pregunta_usuario, table_name, embedding_vec)
        if columns:
            column_list += f"<<<Tabla {table_name} Columns: \n{columns}>>>\n\n"
        else:
            print(f"No se encontraron columnas relevantes para {table_name}")
    
    return column_list



class ConvertToSQL(BaseModel):
    sql_query: str = Field(
        description="Consulta SQL correspondiente a la pregunta en lenguage natural del usuario."
    )


def _regenerate_query(pregunta_usuario, esquema ,llm_model):
    """
    Regenerate a SQL query.
    
    Args:
        Various parameters needed for query generation
        
    Returns:
        str: Regenerated SQL query
    """
    logger.debug("Regenerando consulta...")
    print('Entro a regenerate_query')
    
    selected_table = []
    for i in esquema.keys():
        selected_table.append(i)
    
    few_shot_queries, _, _ = catalogo_index_retrieval(pregunta_usuario)
    column_list = _get_column_information(pregunta_usuario = pregunta_usuario, selected_table=selected_table)
    descriptions_short = selected_tables_fun(esquema)
       
    prompt = ChatPromptTemplate.from_messages([
             ("system", query_prompt_equipos["system"]),
             ("human", query_prompt_equipos["human"]) 
        ])
    
    structured_llm = llm_model.with_structured_output(ConvertToSQL)

    get_query_chain = prompt | structured_llm 
    start = time.perf_counter()
    consulta = get_query_chain.invoke({
            "pregunta_usuario": pregunta_usuario,
            "selected_table": selected_table,
            "descriptions_short": descriptions_short,
            "column_list": column_list,
            "few_shot_queries": few_shot_queries
        })
    end = time.perf_counter()
    print(f"tiempo de invoke: {end - start:.2f} segundos")

    consulta = consulta.sql_query
    print(f'Consulta REGENERADA: {consulta}')
    conn = get_connection_to_db()
    start = time.perf_counter()
    consulta = _improve_query_if_needed(consulta, conn, pregunta_usuario)
    end = time.perf_counter()
    print(f"tiempo de improve if needed dentro del regenerate query: {end - start:.2f} segundos")

    conn.close()

    logger.debug(f"Consulta regenerada: {consulta}")
    return consulta


def df2list(consulta, conec, col_name):
    """
    Funcion que ejecuta una consulta sql dada, guarda como dataframe la salida y se queda con una de las columnas de interés como lista de Python.
    """
    cursor = conec.cursor()
    cursor.execute(consulta)
    results = cursor.fetchall()
    description = cursor.description
    resultados_df = pd.DataFrame(results, columns = [desc[0] for desc in description])
    my_list = resultados_df[col_name].tolist()
    return my_list


def replace_token(token, original_list, replacement_list):
    """
    Reemplaza un token por otro. Dado una lista con el token como llegaria del servicio de STT,
    puede reemplzarlo por otro para pasarlo bien en las burbujas de dialogo del chat del avatar.
    Args:
        token (str): token 
        original_list (list): Lista de tokens a reemplazar
        replacement_list (list): Lista de token 
    Returns:
        str: Token reemplzado.
    """
    
    leading_space = ''
    trailing_space = ''
    if token and token[0].isspace():
        i = 0
        while i < len(token) and token[i].isspace():
            leading_space += token[i]
            i += 1
    if token and token[-1].isspace():
        i = len(token) - 1
        while i >= 0 and token[i].isspace():
            trailing_space = token[i] + trailing_space
            i -= 1
    stripped_token = token.strip()
    
    stripped_originals = [orig.strip() for orig in original_list]
    if stripped_token in stripped_originals:
        index = stripped_originals.index(stripped_token)
        return leading_space + replacement_list[index] + trailing_space
    return token

def selected_tables_fun(esquema)->dict:
    """
    Funcion que lleva el archivo shcema.json al formato necesario en las funciones de get_query.
    """
    u = {}
    for i in esquema.keys():
        u[i] = {'description_short':esquema[i]['description_short']}
    return u




def juntar_numeros_sucesivos_base(texto):
    # Usamos una expresión regular para detectar números separados por espacios
    texto_corregido = re.sub(r'(\d+)\s+(\d+)', r'\1\2', texto)
    return texto_corregido

def juntar_numeros_sucesivos(texto):
    # Diccionario para convertir números escritos en palabras a valores numéricos
    palabras_a_numeros = {
        "cero": "0",
        "uno": "1",
        "dos": "2",
        "tres": "3",
        "cuatro": "4",
        "cinco": "5",
        "seis": "6",
        "siete": "7",
        "ocho": "8",
        "nueve": "9",
        "diez": "10",
        "once": "11",
        "doce":"12"
    }

    # Reemplaza los números en palabras por sus valores numéricos en el texto
    for palabra, numero in palabras_a_numeros.items():
        texto = re.sub(fr'\b{palabra}\b', numero, texto, flags=re.IGNORECASE)

    # Une los números consecutivos
    texto_corregido = re.sub(r'(\d+)\s+(\d+)', r'\1\2', texto)

    return texto_corregido

if __name__ == '__main__':

    """
    Sección de pruebas unitarias:
    """

    consulta_1 = "SELECT Boca_Pozo_Nombre_Oficial FROM P_DIM_V.UPS_DIM_EQUIPOS_ACTIVOS WHERE Event_Code = 'PER'"
    consulta_2 =  "SELECT BB.NOMBRE_EQUIPO, AA.Event_Code FROM P_DIM_V.UPS_DIM_EQUIPOS_ACTIVOS AA,P_DIM_V.UPS_DIM_EQUIPO BB WHERE AA.Equipo_Id = BB.EQUIPO_ID AND AA.Event_Code = 'PER'"
    conn = get_connection_to_db()
    col_name_1 = 'Boca_Pozo_Nombre_Oficial'
    col_name_2 = 'NOMBRE_EQUIPO'
   
    lista_equipos = df2list(consulta_2,conn, col_name_2)
    print('la lista de equipos queda:', lista_equipos)
    lista_pozos = df2list(consulta_1,conn, col_name_1)
    print('la lista de pozos queda:', lista_pozos)
  


