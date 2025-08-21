import logging
import sys
import os

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

# Data Stracture
from pydantic import BaseModel, Field
from typing import TypedDict, List

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


          ## OUTPUT

          Tu única tarea es generar una respuesta JSON válida para el siguiente esquema.

          - **IMPORTANTE**: No incluyas ninguna explicación fuera del JSON.
          - El JSON debe poder ser parseado por `json.loads`.
          - NO agregues texto adicional antes ni después.

          Devuelve un único objeto JSON con el siguiente formato:

         {{
            "planning": "<Describe brevemente qué pasos SQL se deben seguir para responder la pregunta del usuario.>",
            "reasoning": "<Explica por qué se estructura así la consulta SQL (por ejemplo, filtrado por código vs texto, joins necesarios, fechas, etc).>",
            "step": "<Número o nombre de paso dentro de un proceso multi-step. Ejemplo: 'Paso 1/2: Ventas por región'>",
            "sql": "<Consulta SQL en Teradata sin punto y coma al final. Cumple las reglas de alias, joins y TOP.>",
            "success": true,
            "results": <resultado de ejecutar la query>
          }}       
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

def seleccionar_catalogo(json_schema):
    json_schema = os.path.abspath(json_schema)
    print('json_schema',json_schema)
    with open(json_schema, 'r', encoding='UTF-8') as json_file:
        schema = json.load(json_file)
    return schema


#json_schema = r"../data/schema.json"
#json_schema = os.path.abspath(json_schema)


def generate_sql_query(state: SqlAgentState, llm_model=llm_gpt_4o_mini) -> SqlAgentState:
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
    #print("FECHA", fecha_actual)
    #print("TABLES", selected_table)
    #print("COLUMS", column_list)
    #print("DESCRIPTION", descriptions_short)

    prompt = ChatPromptTemplate.from_messages([
             ("system", query_prompt_sql["system"]),
             ("human", query_prompt_sql["human"]) 
        ])
    
    structured_llm = llm_model.with_structured_output(SqlStepOutput)


    get_query_chain = prompt | structured_llm
    print("Por generar consulta con llm")
    consulta_dict = get_query_chain.invoke(input={
            "fecha_actual": fecha_actual,
            "pregunta_usuario": question,
            "selected_table": selected_table,
            "descriptions_short": descriptions_short,
            "column_list": column_list,
            "few_shot_queries": None
        })

    print("Genero la consulta")
    #print(consulta_dict)
    #print(type(consulta_dict))
    state['sql_query']=consulta_dict['sql']
    #print("Consulta generada: ", consulta_dict)
    return state

# Nodo que, dada una consulta de Teradata, la ejecuta
def execute_sql_query(state:SqlAgentState):
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
def format_sql_results(state: SqlAgentState, llm_model = llm_gpt_4o_mini):
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
    
    # 🔁 Acumulamos en 'sql_results_accum'
    state.setdefault("sql_results_accum", []).append(answer)
    
    # 1) New messages with UUIDs
    #human_msg = HumanMessage(id=str(uuid.uuid4()), content=pregunta, name='memoria')
    #ai_msg    = AIMessage(id=str(uuid.uuid4()), content=answer, name='memoria')

    # 2) Remove all but the last 4 messages
    #removals = [RemoveMessage(id=m.id) for m in state["messages"][:-4]]
    
    return state