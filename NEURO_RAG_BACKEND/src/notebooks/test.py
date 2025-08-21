# %%
# IMPORTACIONES
# Librerias
import os
import json
import teradatasql
import pandas as pd
import time
import datetime

# Langchain y Langgraph
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START,END

# Data Stracture
from pydantic import BaseModel, Field
from typing import TypedDict

# Importaciones desde archivos auxiliares
#from src.utils.utils import GetLogger
#from src.prompt_engineering.query_prompts import query_prompt_sql


# %%
import logging
import sys
import os

LOGLEVEL = os.environ.get('LOGLEVEL_UTIL', 'INFO').upper()
class GetLogger:
    def __init__(self, name, level=logging.INFO):
        self.logger=logging.getLogger(name)
        self.logger.propagate=False
        self.logger.setLevel(level)
        if not self.logger.handlers:
            stream_handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('[%(asctime)s][%(levelname)s][%(name)s][%(funcName)s] %(message)s')
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)

logging.getLogger('azure').setLevel(logging.WARNING)
logger=GetLogger(__name__, level=LOGLEVEL).logger

# %%
query_prompt_sql = {
    "system": """
          # Sistema: Asistente Experto en SQL Teradata para YPF

          ## Tu rol y objetivo
          Eres un asistente especializado de YPF, experto en generar consultas SQL para Teradata relacionadas al área de Comercial (Ventas y planificación B2C de combustibles). 
          Tu tarea es crear consultas precisas basadas en la pregunta del usuario: {pregunta_usuario}.
          
          ## Modelo de datos: Entidades y relaciones

          ### Conceptos clave
          - **Ventas**: Hace referencia a ventas en "litros". Si necesitan en m3 se debe dividir por 1000. Si consultan por ventas hasta el dia de hoy, hace referencia las ventas acumuladas durante el mes hata el día de ayer, es decir día cerrado.
              
          ### Tablas principales y sus relaciones
          Tablas:
          1. P_DIM_V.COM_FT_DLY_DESPACHO_VOX (Claves: Establecimiento_Id, Producto_Id)
          2. P_DIM_V.COM_DIM_PRODUCTO_VOX (Claves: PRODUCT_ID)
          3. P_DIM_V.COM_DIM_ESTABLECIMIENTO_VOX (Claves: Establecimiento_Id)
          
          Relaciones:
          P_DIM_V.COM_FT_DLY_DESPACHO_VOX.Producto_Id = P_DIM_V.COM_DIM_PRODUCTO_VOX.PRODUCT_ID
          P_DIM_V.COM_FT_DLY_DESPACHO_VOX.Establecimiento_Id = P_DIM_V.COM_DIM_ESTABLECIMIENTO_VOX.Establecimiento_Id

          ## Sintaxis específica de Teradata SQL

          ### Reglas generales
          - Importante: No usar alias con las palabras reservadas en la generación de queries (Ejemplos: 'EQ', 'DO', 'IN', 'AS', 'BY', 'OR', 'ON').
          - Nunca usar 'EQ' ya que es una palabra reservada de Teradata SQL. 
          - No usar punto y coma (;) al final de las consultas
          - Responder siempre en español
          - *** MUCHA ATENCION: Uso de TOP: 
            -- Si el usuario solicita listar datos sin restricciones, genera la consulta sin incluir una cláusula TOP.
            -- Si el usuario solicita explícitamente un límite en los resultados, usa la cláusula TOP con el valor solicitado.
          - Asegúrate de que la consulta visualice todos los datos cuando la intención es un listado completo.
          - Usar TOP en lugar de LIMIT (con ORDER BY obligatorio)
          - Usar de forma obligatoria TOP despues del SELECT al comienzo de la consulta
          - No combinar DISTINCT con TOP
          - No usar TOP con SAMPLE
          - Usar SAMPLE para limitar filas en orden aleatorio
          - No combinar DISTINCT con TOP
          - No usar TOP con SAMPLE
          - MUY MUY IMPORTANTE: Evitar usar alias con palabras reservadas: 'EQ', 'DO', 'IN', 'AS', 'BY', 'OR', 'ON'
          - Usar LIKE con LOWER para búsquedas insensibles a mayúsculas: `LOWER(columna) LIKE LOWER('%valor%')`
          - Si se usa la columna 'WELL_ID', incluir también la columna del nombre del pozo
          - La consulta generada debe usar solo los nombres de columnas y tablas indicadas como relevantes o disponibles
          - Siempre calificar columnas ambiguas: Cualquier columna que pudiera existir en más de una tabla debe incluir el nombre o alias de la tabla.
          - Usar prefijos claros: Si hay múltiples tablas con estructuras similares, usa alias que indiquen claramente la naturaleza de cada tabla.
          - Revisar las reglas para join.

          ### Formato específico para fechas
          - Anteponer DATE a valores de fecha: `WHERE FECHA >= DATE '2024-01-01'`
          - Valor predeterminado para fechas es el día completo finalizado, es decir el dia de ayer: CURRENT_DATE()-1

          ### Reglas para JOIN
          - INNER JOIN: cuando la relación es obligatoria
          - LEFT JOIN: cuando la relación es opcional
          - Relaciones múltiples: usar operador AND
          - Siempre usar alias para columnas en consultas con JOIN

          ## Información adicional
          - **Fecha de hoy**: {fecha_actual}
          - **Tablas relevantes para esta consulta**: {selected_table}
          - **Descripción de las tablas**: {descriptions_short}
          - **Lista de columnas disponibles**: {column_list} 
          - **Ejemplos similares**:{few_shot_queries}


          ## Output
          - Muy importante: No olvidar no usar alias con las palabras reservadas en la generación de queries (Ejemplos: 'EQ', 'DO', 'IN', 'AS', 'BY', 'OR', 'ON').
          - Particularmente nunca usar 'EQ' como alias porque es una palabra reservada de Teradata. 
          - MUY IMPORTANTE: Utilizar la memoria disponible de los últimos cuatro mensajes o indicacón dentro de la pregunta del usuario.

            
  """,
    "human": "Consulta del usuario: {pregunta_usuario}\nTeradata SQL Query: "
}
query_prompt_format_answer = {
      "system":"""Eres un asistente que proporciona respuestas analíticas como resumen de un resultado de consulta a una base de datos del area comercial. 
                Tienes la pregunta del usuario, la consulta SQL y los resultados de la consulta. 

                ## OUTPUT
                - Responde con los pasos que se siguieron para extraer la información y un análisis según la pregunta del usuario

                """,
    "human":"""#Usuario:
                {question}

                # Query: 
                {query}
                # Resultado:
                {results}
   
                # Tarea:
                - Responde en español de manera estructurada y con los pasos que se siguieron hasta responder la consults
                - Imprime un resultado en formato de tabla markdown que sea conciso y que de una muestra del resultado
                
    """
}

# %%
# VARIABLES DE ENTORNO
# Logging
LOGLEVEL = os.environ.get('LOGLEVEL_SQLAGENT', 'DEBUG').upper()
logger=GetLogger(__name__, level=LOGLEVEL).logger

logger=GetLogger(__name__, level=LOGLEVEL).logger
LOGLEVEL = os.environ.get('LOGLEVEL_ROOT', 'INFO').upper()
logger = GetLogger("", level=LOGLEVEL).logger

# Azure
azure_openai_api_key = os.environ.get('AZURE_OPENAI_API_KEY')
azure_openai_endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT')

# Teradata
TD_HOST = os.environ.get('TD_HOST')
TD_USER = os.environ.get('TD_USER')
TD_PASS = os.environ.get('TERADATA_PASS')
TD_LOGMECH = os.environ.get('LOGMECH')


# %%
# MODELOS LLM

llm_gpt4o = AzureChatOpenAI(
        api_key=azure_openai_api_key,
        openai_api_version="2024-10-21",
        azure_deployment="chat4og",
        azure_endpoint=azure_openai_endpoint,
        model_name="gpt-4o",
        seed=42,
        timeout=180)

llm_gpt_4o_mini = AzureChatOpenAI(
        api_key=azure_openai_api_key,
        openai_api_version="2025-01-01-preview",
        azure_deployment="gpt-4o-mini",
        azure_endpoint=azure_openai_endpoint,
        model_name="gpt-4o-mini",
        seed=42,
        timeout=180)

llm_gpt_o3_mini = AzureChatOpenAI(
        api_key=azure_openai_api_key,
        openai_api_version="2025-01-01-preview",
        azure_deployment="o3-mini",
        azure_endpoint=azure_openai_endpoint,
        model_name="o3-mini",
        temperature= 1,
        seed=42,
        timeout=180)


# %%
# FUNCIONES

# Conexión a Teradata
def get_connection_to_db(td_host, td_user, td_pass, td_logmech):
    
    print(td_host, td_user, td_pass, td_logmech)
    conn_str = '{"host":"%s","user":"%s","password":"%s","logmech":"%s"}' % (
        td_host, td_user, td_pass, td_logmech
    )
    print('string de conexion:', conn_str)
    conn = teradatasql.connect(conn_str)
    print('conexion satisfactoria')
    return conn

def seleccionar_catalogo():
    with open(json_schema, 'r', encoding='UTF-8') as json_file:
        schema = json.load(json_file)
    return schema


json_schema = 'c:\\Users\\SE45352\\Documents\\repos\\BOTCOM\\src\\data\\schema.json'
json_schema = os.path.abspath(json_schema)


# %%
# STATES Y DATA STRUCTURES
# --- 1. Definimos el estado compartido entre nodos ---
class AgentState(TypedDict):
    question: str
    sql_query: str
    sql_results: str
    answer: str
    messages: list  # Para emitir logs como AIMessage(name="log") 

class ConvertToSQL(BaseModel):
    sql_query: str = Field(
        description="Consulta SQL correspondiente a la pregunta en lenguage natural del usuario."
    )


# %%
schema = seleccionar_catalogo()

# %%
def generate_sql_query(state: AgentState, llm_model=llm_gpt_4o_mini) -> AgentState:
    """
    Arma una consulta SQL para teradata en función de lo que pide el usuario. 
    La pregunta debe de estar orientada a la información que tienen las tablas.
    """
    
    print('Entro a get_query')
    
    question = state['question']
    selected_table = ['P_DIM_V.COM_FT_DLY_DESPACHO_VOX', 
                      'P_DIM_V.COM_DIM_PRODUCTO_VOX',
                      'P_DIM_V.COM_DIM_ESTABLECIMIENTO_VOX'] #tablas de interés para el miniPywo 
    fecha_actual = datetime.datetime.now().strftime('%Y-%m-%d')
    schema = seleccionar_catalogo()
    # Obtencion de Column List
    column_list = ""
    column_strings = []
    
    for table_name, table_info in schema.items():
        if table_name not in selected_table:
            continue
        columns_dict = table_info.get("columns", {})
        column_lines = [f">> {col_name}: {col_desc}" for col_name, col_desc in columns_dict.items()]
        table_string = f"Tabla: {table_name}\n" + "\n".join(column_lines)
        column_strings.append(table_string)
    
    column_list = "\n\n".join(column_strings)

    # Obtencion de Description Short
    description = []
    table_description = ""
    for table_name, table_info in schema.items():
        if table_name not in selected_table:
            continue  # Saltar si no está en selected_table
        description = table_info.get("description_short", "Sin descripción")
        table_description += f"Tabla: {table_name}\n>>Descripción: {description}\n\n"
    descriptions_short = table_description
    
    prompt = ChatPromptTemplate.from_messages([
             ("system", query_prompt_sql["system"]),
             ("human", query_prompt_sql["human"]) 
        ])
    
    structured_llm = llm_model.with_structured_output(ConvertToSQL)


    get_query_chain = prompt | structured_llm 
    print("Por generar consulta con llm")
    consulta = get_query_chain.invoke(input={
            "fecha_actual": fecha_actual,
            "pregunta_usuario": question,
            "selected_table": selected_table,
            "descriptions_short": descriptions_short,
            "column_list": column_list,
            "few_shot_queries": None
        })

    print("Genero la consulta")
    state['sql_query']=consulta.sql_query
    print("Consulta generada: ", consulta)
    return state

# Nodo que, dada una consulta de Teradata, la ejecuta
def execute_sql_query(state:AgentState):
    """
    Funcion que ayuda a orquestar el flujo del grafo hacia un pedido de una novedad o una consulta en 
    Teradata. Se basa en la pregunta o consulta del usuario.
    Args:
    question: pregunta del usuario.
    LLM: Modelo de Lenguaje a utilizar.
    Returns:
    tipo_consulta: novedades o get_query. Valor binario para el enrutador.
    """

    start = time.perf_counter()
    sql_query = state["sql_query"]#.strip()
    limit_rows=2000

    conn = get_connection_to_db(TD_HOST,TD_USER,TD_PASS,TD_LOGMECH)
    #print('Pude hacer bien la conexión')
    
    count = 0
    flag = True

    while flag and count < 3:
        count += 1
        try:
            cursor = conn.cursor()
            #print(f"intento ejecuar la consulta nro {count}")
            cursor.execute(sql_query)
            resultados = cursor.fetchall()
            description = cursor.description
            cursor.close()
            conn.close()
            resultados_df = pd.DataFrame(resultados, columns=[desc[0] for desc in description])           
            cantidad_res = len(resultados_df)
            if cantidad_res > limit_rows:
                resultados_df = resultados_df.head(limit_rows)
            #print(resultados_df)
            respuesta_generada = f"Resultados:\n{resultados_df.to_markdown()}"
            flag = False            
            state['sql_results']= respuesta_generada
            print("SQL query executed successfully.")

        except Exception as e:

            state["sql_results"] = f"Error al ejecutar la SQL query: {str(e)}"
            print('no se pudo ejecutar la consulta en Teradata')

    end = time.perf_counter()
    #state["dt"] = state["dt"] + end -start
    #print(f"Ejecutar consulta Tiempo transcurrido: {end - start:.2f} segundos")
    #print(f"Tiempo acumlado en Ejecutar consulta: {state["dt"]:.2f} segundos")
    return state

# Nodo que procesa la salida de teradta para obtener una respuesta humana.
def format_sql_results(state: AgentState, llm_model = llm_gpt_4o_mini):
    """
    Funcion que ayuda a orquestar el flujo del grafo hacia un pedido de una novedad o una consulta en 
    Teradata. Se basa en la pregunta o consulta del usuario.
    Args:
    question: pregunta del usuario.
    query_result: Resultado de la query ejecutada en Teradata.
    LLM: Modelo de Lenguaje a utilizar.
    Returns:
    query_result: Respuesta del LLM  a la pregunta del usuario respecto a la salida de Teradata.  
    """
    print('Entro a la funcion generate_human_readable_answer')
    start = time.perf_counter()
    pregunta = state["question"]
    sql_query = state["sql_query"]
    result = state["sql_results"]
    #dt = state["dt"]
    print("Consulta: ", sql_query)
    print("Resultado: ", result)
    generate_prompt = ChatPromptTemplate.from_messages([
         ("system", query_prompt_format_answer['system']), #, MessagesPlaceholder("messages"),
         ("human",query_prompt_format_answer['human'])
         ])

    human_response = generate_prompt | llm_model | StrOutputParser()
    answer = human_response.invoke({'question':pregunta,
                                    'query': sql_query,
                                    'results':result
                                    })
    #,                                    'dt':dt})
    
    state["answer"] = answer
    
    # 1) New messages with UUIDs
    #human_msg = HumanMessage(id=str(uuid.uuid4()), content=pregunta, name='memoria')
    #ai_msg    = AIMessage(id=str(uuid.uuid4()), content=answer, name='memoria')

    # 2) Remove all but the last 4 messages
    #removals = [RemoveMessage(id=m.id) for m in state["messages"][:-4]]
    
    return state

""" {
        #"messages":    [*removals, human_msg, ai_msg],
        "answer": answer,
        #"dt":           state["dt"] + end -start,
    } """

# %%
# WORKFLOW
def build_tts_workflow():
    graph = StateGraph(AgentState)
    graph.set_entry_point("generate_sql")

    graph.add_node("generate_sql", generate_sql_query)
    graph.add_node("execute_sql", execute_sql_query)
    graph.add_node("format_results", format_sql_results)

    graph.add_edge(START, "generate_sql")
    graph.add_edge("generate_sql", "execute_sql")
    graph.add_edge("execute_sql", "format_results")
    graph.add_edge("format_results", END)
    return graph.compile()

# %%
app = build_tts_workflow()
from IPython.display import Image
# debajo de donde guarda el grafo de langgraph.
print(app.get_graph().draw_ascii())

# %%
user_question_random = "Cuales son las ventas de junio para la estación de servicio MAGNETO en Salta por tipo de producto"
result_1 = app.invoke({"question": user_question_random}, debug=True)
print("RESULTADO:\n\n", result_1["answer"])


