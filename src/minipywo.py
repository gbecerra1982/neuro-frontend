import os
import re
import json
from typing import TypedDict, List, Optional, Any, Annotated
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage
from langchain_core.messages.modifier import RemoveMessage
from langgraph.graph.message import add_messages
from langchain.schema import (
    SystemMessage, HumanMessage, AIMessage, BaseMessage,
    AgentAction, AgentFinish
)


from src.pywo_aux_func import llm_gpt_o3_mini, llm_gpt_4o_mini, llm_gpt4o ,get_connection_to_db, _improve_query_if_needed, _get_column_information, juntar_numeros_sucesivos, _regenerate_query, selected_tables_fun, get_tables
from typing import List, Optional, Annotated
import pandas as pd
from src.util import GetLogger
import time
import uuid
from src.catalogo_retrieval import catalogo_index_retrieval, embeddings
from src.tables_retrieval import tables_index_retrieval
from src.prompts.prompt_minipywoIII import stream_ini_prompt, general_response_prompt, sql_readeble_prompt, agent_prompts, corva_prompt
from src.prompts.prompt_minipywoIII import query_prompt_equipos

from src.prompts.entidades_dict import corrections

from src.schema_td import datos_db
from src.corva_agno_agent import corva_api_query_agnostic
from src.self_verification_agent.src.sql_verification import run_critic_with_examples
from src.self_verification_agent.src.agent import critic_graph 

api_key = os.getenv("CORVA_API_KEY")
pm = 10 # parametro memoria corto plazo
LOGLEVEL = os.environ.get('LOGLEVEL_SQLAGENT', 'DEBUG').upper()
logger=GetLogger(__name__, level=LOGLEVEL).logger

logger=GetLogger(__name__, level=LOGLEVEL).logger
LOGLEVEL = os.environ.get('LOGLEVEL_ROOT', 'INFO').upper()
logger = GetLogger("", level=LOGLEVEL).logger

# Imports de PostgreSQL - Versión Simplificada

from src.postgres_integration import (
    save_complete_memory, save_to_memory_simple, save_sql_execution_simple, 
    save_sql_error_simple, save_performance_metric_simple, 
    get_postgres_connection, test_postgres_connection
)

from src.langmem_functions import (
    get_relevant_context_for_question, 
    create_enhanced_prompt_with_memory,
    get_user_preferences_and_patterns,
    extract_user_id_from_session,
    create_user_session_id
)



class AgentState(TypedDict):
    question: str
    session_id: str                   # ID único de sesión
    user_id: Optional[int]            # ID del usuario (opcional)
    invoke_params: dict[str, Any]     # Parámetros de invocación como diccionario
    raw_sql_query: str # consulta previa a improve query
    sql_query: str  
    sql_critique: dict[str, Any]      # Crítica o detalle de la sentencia SQL
    query_result: str
    query_errors: List[str]
    relevance: str
    sql_error: bool
    name_validation: bool
    tipo_consulta: str
    gral_ans: str
    entity: bool
    correction_success: bool
    name_correction: bool
    lista_equipos_activos: List[str]
    lista_pozos_activos_perforacion: List[str]
    dt: float
    messages: Annotated[List[AnyMessage], add_messages] 
    session_id: str  # ID único de sesión
    user_id: Optional[str]  # ID del usuario (opcional)
    # test duplicacion de estado:
    #parsed         : AgentAction | AgentFinish | None  # <-- lo que devuelve parser
    #should_end     : bool | None              # para el condicional


class CheckRelevance(BaseModel):
    relevance: str = Field(
        description="Indica si la pregnta está relacionada con la base de datos. La salida puede ser 'consulta' o 'casual'."
    )


def check_general_relevance(state: AgentState, llm_model=llm_gpt_4o_mini): 
    """
    Funcion que ayuda a orquestar el flujo del grafo hacia un chat casual, una consulta en 
    Teradata o una consulta de la plataforma corva a partir de una pregunta o consulta del usuario.
    Args:
    question: pregunta del usuario.
    LLM: Modelo de Lenguaje a utilizar.
    Returns:
    relevance: casual, corva o consulta. 
    """
    start = time.perf_counter()
    question = state["question"]
    session_id = state.get('session_id', str(uuid.uuid4()))
    user_id = state.get('user_id')  # NO sobrescribir
    if not user_id:  # Solo extraer si no viene del estado
        session_id = state.get('session_id', str(uuid.uuid4()))
        user_id = extract_user_id_from_session(session_id)
        state['session_id'] = session_id
    state['user_id'] = user_id
    print('Entro a la funcion check_general_relevance')
    print(f"Checkea la categoria de la pregunta: {question}")

    # NUEVO: Obtener contexto histórico
    #relevant_context = get_relevant_context_for_question(question, user_id, session_id)

    #system = agent_prompts['agent']["system"]
    # Prompt original
    system_original = agent_prompts['agent']["system"]
    
    # NUEVO: Enriquecer prompt con memoria - FIX: Usar template variable
    try:
        system_enhanced = create_enhanced_prompt_with_memory(
            system_original, question, user_id, session_id
        )
    except Exception as e:
        print(f"⚠️ Error enriqueciendo prompt con memoria: {str(e)}")
        # Fallback al prompt original si hay error
        system_enhanced = system_original
    
    human = f"Pregunta: {question}"

    # FIX: Usar el prompt como texto literal sin variables de template
    check_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "{system_prompt}"),  # ← CAMBIO: usar variable
            ("human", "{human_input}"),     # ← CAMBIO: usar variable
        ]
    )
    
    structured_llm = llm_model.with_structured_output(CheckRelevance)
    relevance_checker = check_prompt | structured_llm
 
    # FIX: Pasar los valores como variables
    relevance = relevance_checker.invoke({
        "system_prompt": system_enhanced,  # ← CAMBIO: pasar como variable
        "human_input": human               # ← CAMBIO: pasar como variable
    })
    
    state["relevance"] = relevance.relevance
    print(f"Relevancia determinada por el llm en gral relevance: {state['relevance']}")
    end = time.perf_counter()
    state["dt"] = end - start

    # NUEVO: Guardar métricas con memoria
    try:
        save_performance_metric_simple(session_id, 'check_general_relevance_memory', 
                                      end - start, True)
    except:
        pass
    print(f"Check relevance tiempo transcurrido: {end - start:.2f} segundos")
    
    return state

def general_response(state: AgentState, llm_model=llm_gpt_4o_mini): 
    """
    Funcion que busca generar un chat casual y general a una pregunta o consulta del usuario.
    Args:
    question: pregunta del usuario.
    LLM: Modelo de Lenguaje a utilizar.
    Returns:
    query_result: string.
    """
    print("Entro a general_response")

    start = time.perf_counter()
    pregunta = state['question']
    print('Entro a responder la pregunta:', pregunta)
    print('messages:', state["messages"])

    # Generar session_id si no existe
    # ✅ PRESERVAR user_id del estado
    session_id = state.get('session_id', str(uuid.uuid4()))
    user_id = state.get('user_id')  # NO sobrescribir
    if not user_id:  # Solo extraer si no viene del estado
        user_id = extract_user_id_from_session(session_id)
    state['session_id'] = session_id
    state['user_id'] = user_id

    
    # NUEVO: Obtener patrones del usuario
    user_patterns = get_user_preferences_and_patterns(user_id, session_id)
    print('USER PATTERN DENTRO DE GENERAL RESPONSE')
    print('=====================================================================')
    print(user_patterns)

    print('=====================================================================')  

    # NUEVO: Personalizar el prompt basándose en el usuario
    system_original = general_response_prompt['system']
    
    # Agregar personalización al sistema
    if user_patterns.get('user_type') == 'power_user':
        system_enhanced = system_original + "\n\nNOTA: Este usuario es avanzado y hace preguntas técnicas frecuentes. Puedes ser más específico y técnico en tus respuestas."
    else:
        system_enhanced = system_original + "\n\nNOTA: Este usuario es casual. Mantén respuestas simples y amigables."
    
    # NUEVO: Agregar contexto histórico relevante - FIX: Con manejo de errores
    try:
        system_enhanced = create_enhanced_prompt_with_memory(
            system_enhanced, pregunta, user_id, session_id
        )
        print('SYSTEM_ENHANCED DENTRO DE GENERAL RESPONSE:')
        print("==========================================")
        print(system_enhanced)
        print("==========================================")
    except Exception as e:
        print(f"⚠️ Error enriqueciendo prompt con memoria: {str(e)}")
        # Fallback al prompt original si hay error
        system_enhanced = system_original
        print('SYSTEM_ENHANCED DENTRO DE GENERAL RESPONSE en exception:')
        print("==========================================")
        print(system_enhanced)
        print("==========================================")

    # FIX: Usar variables de template en lugar de texto directo
    #funny_prompt = ChatPromptTemplate.from_messages([
    #    ("system", "{system_prompt}"),  # ← CAMBIO: usar variable
    #    MessagesPlaceholder("messages"),
    #    ('human', "{human_prompt}"),    # ← CAMBIO: usar variable
    #])

    funny_prompt = ChatPromptTemplate.from_messages([
        ("system", system_enhanced),  # ← CAMBIO: usar variable
        MessagesPlaceholder("messages"),
        ('human', general_response_prompt['human']),    # ← CAMBIO: usar variable
    ])

    funny_response = funny_prompt | llm_model | StrOutputParser()
    
    # FIX: Pasar los valores como variables
    #respuesta = funny_response.invoke({
    #    'system_prompt': system_enhanced,           # ← CAMBIO: pasar como variable
    #    'human_prompt': general_response_prompt['human'],  # ← CAMBIO: pasar como variable
    #    'pregunta': pregunta, 
    #    'messages': state["messages"]
    #})
    respuesta = funny_response.invoke({
        'pregunta': pregunta, 'messages': state["messages"] 
    })

    state["query_result"] = respuesta
   
    end = time.perf_counter()
    execution_time = end - start
    print(f"General response Tiempo transcurrido: {execution_time:.2f} segundos")

    
    # 1) New messages with UUIDs
    human_msg = HumanMessage(id=str(uuid.uuid4()), content=pregunta, name='memoria')
    ai_msg    = AIMessage(id=str(uuid.uuid4()), content=respuesta, name='memoria')

    # NUEVO: GUARDAR EN POSTGRESQL
    try:
        print('User_id que va desde minipywo:',state['user_id'])
        save_complete_memory(state, "general_chat_personalized", human_msg.id, ai_msg.id)
        save_performance_metric_simple(session_id, "general_response_memory", execution_time, True)
        print("✅ Respuesta personalizada guardada en PostgreSQL")
    except Exception as e:
        print(f"⚠️ Error guardando en PostgreSQL: {str(e)}")
        # Continuar funcionando aunque falle PostgreSQL

    # 2) Remove all but the last 4 messages
    #removals = [RemoveMessage(id=m.id) for m in state["messages"][:-pm]]
    print('DENTRO DE GENERAL_RESPONSE',state["messages"])
    # 3) Return removals + new messages + other field updates
    return {
        "messages":    [*state["messages"], human_msg, ai_msg],
        "query_result": respuesta,
        "dt":           state["dt"] + end - start,
        "session_id":  session_id
    }


def corva_call(state: AgentState, llm_model=llm_gpt_4o_mini):
    """
    Función que usa directamente el agente Agno de Corva con streaming simulado
    VERSIÓN MEJORADA: Simula streaming para compatibilidad con frontend
    """
    print('Entro a corva_call con streaming simulado')
    start = time.perf_counter()
    
    # Preservar user_id del estado
    session_id = state.get('session_id', str(uuid.uuid4()))
    user_id = state.get('user_id')
    if not user_id:
        user_id = extract_user_id_from_session(session_id)
    
    state['session_id'] = session_id
    state['user_id'] = user_id
    pregunta = state['question']
    
    print(f'Procesando consulta Corva: {pregunta}')
    
    # ✅ OBTENER RESPUESTA DE CORVA
    answer_cor = corva_api_query_agnostic(pregunta)
    
    # 🔧 NUEVA ESTRATEGIA: Usar un prompt template + LLM para generar streaming
    # Esto permite que LangGraph maneje el streaming correctamente
    
    #corva_streaming_prompt = ChatPromptTemplate.from_messages([
    #    ("system", """Eres un asistente especializado en datos de Corva. 
    #    Tu trabajo es presentar la siguiente información de manera clara y estructurada.
        
    #    INFORMACIÓN DE CORVA:
    #    {corva_response}
        
    #    Presenta esta información de manera profesional y clara, manteniendo todos los detalles importantes."""),
    #    ("human", "Pregunta del usuario: {pregunta}")
    #])

    corva_streaming_prompt = ChatPromptTemplate.from_messages([
        ("system", corva_prompt["system"]),
        ("human", corva_prompt["human"])
    ])
    print('==================================================')
    print('==================================================')
    print('==================================================')
    print('CORVA STREAMING PROMPT:', corva_streaming_prompt)
    print('==================================================')
    print('==================================================')
    print('==================================================')
    # Crear chain para streaming
    streaming_chain = corva_streaming_prompt | llm_model | StrOutputParser()
    
    # ✅ GENERAR RESPUESTA CON STREAMING (esto permite que LangGraph haga streaming)
    respuesta_final = streaming_chain.invoke({
        "corva_response": answer_cor,
        "pregunta": pregunta,
        'dic_equi':corrections,
    })
    
    end = time.perf_counter()
    execution_time = end - start
    
    state['query_result'] = respuesta_final
    state['dt'] = state.get('dt', 0) + execution_time
    
    # Crear mensajes para historial (memoria SÍ lleva name='memoria')
    human_msg = HumanMessage(id=str(uuid.uuid4()), content=pregunta, name='memoria')
    ai_msg = AIMessage(id=str(uuid.uuid4()), content=respuesta_final, name='memoria')
    
    # Guardar en PostgreSQL
    try:
        save_complete_memory(state, "corva_call_streaming", human_msg.id, ai_msg.id)
        save_performance_metric_simple(session_id, "corva_call", execution_time, True)
        print("✅ Datos Corva guardados en PostgreSQL")
    except Exception as e:
        print(f"⚠️ Error guardando en PostgreSQL: {str(e)}")
    
    return {
        "messages": [*state["messages"], human_msg, ai_msg],
        "query_result": respuesta_final,
        "dt": state["dt"],
        "session_id": session_id,
        "user_id": user_id
    }


def stream_ini(state: AgentState, llm_model=llm_gpt_4o_mini):
    """
    Funcion que avisa que inicia la busqueda de la respuesta a la pregunta del usuario.
    Args:
    question: pregunta del usuario.
    LLM: Modelo de Lenguaje a utilizar.
    Returns:
    query_result: Aviso que inicia la busqueda de la respuesta.
    """
    start = time.perf_counter()
    pregunta = state['question']
    print("Entro a stream_ini")
    print("ESTADO EN STREAM INI:",state["messages"])
    generate_prompt = ChatPromptTemplate.from_messages([
         ("system", stream_ini_prompt['system']),
         ("human",  stream_ini_prompt['human'])
         ])
    
    human_no_response = generate_prompt | llm_model | StrOutputParser()
    answer = human_no_response.invoke({"pregunta_usuario":pregunta})
    
    state["query_result"] = answer
    end = time.perf_counter()
    state["dt"] = state["dt"] + end -start
    print(f"No correction response Tiempo transcurrido: {end - start:.2f} segundos")
    #print(f"Tiempo acumulado en No correction response: {state["dt"]:.2f} segundos")
    return state




class ConvertToSQL(BaseModel):
    sql_query: str = Field(
        description="Consulta SQL correspondiente a la pregunta en lenguage natural del usuario."
    )

def get_query(state: AgentState, llm_model=llm_gpt_o3_mini):
    """
    Arma una consulta SQL para teradata en función de lo que pide el usuario. 
    La pregunta debe de estar orientada a la información que tienen las tablas.
    """
    print('Entro a get_query CON MEMORIA DE LARGO PLAZO')
    
    if state['dt'] >=25:
        logs = [
        "Estoy consultando a la base de datos."
        ]
        state["messages"] = state.get("messages", []) + [AIMessage(content=log, name="log") for log in logs]
    
    start1 = time.perf_counter()

    
    question = state['question']
    print('GET QUERY LELGA PREGUNTA:', question)
    question = juntar_numeros_sucesivos(question)
    print('GET QUERY CORRECCION TRANSITORIA DE NUMEROS',question)
    logger.info(f"question: {question}")

    # ✅ PRESERVAR user_id del estado
    session_id = state.get('session_id', str(uuid.uuid4()))
    user_id = state.get('user_id')  # NO sobrescribir
    if not user_id:  # Solo extraer si no viene del estado
        user_id = extract_user_id_from_session(session_id)
        state['session_id'] = session_id
    
    state['user_id'] = user_id  # Asegurar que esté en el estado

    user_patterns = get_user_preferences_and_patterns(user_id, session_id)

    selected_table = []
    for i in datos_db.keys():
        selected_table.append(i)
    
    descriptions_long, descriptions_short = tables_index_retrieval(question)
    few_shot_queries, few_shot_tables, _ = catalogo_index_retrieval(question)
    
    selected_table, _, _ = get_tables(
    question, 
    few_shot_tables, 
    descriptions_long, 
    llm_model
    )

    # Se agrega por defaul para identificacion de pozos 
    vista = 'P_DIM_V.UPS_DIM_BOCA_POZO'

    if vista not in selected_table:
        selected_table.append(vista)

    column_list = _get_column_information(pregunta_usuario = question, selected_table=selected_table)

    descriptions_short = selected_tables_fun(datos_db)   


    # NUEVO: Enriquecer el prompt del sistema con memoria histórica
    system_original = query_prompt_equipos["system"]
        
    # NUEVO: Enriquecer el prompt del sistema con memoria histórica y personalización
    system_original = query_prompt_equipos["system"]
    if user_patterns.get('user_type') == 'power_user':
        system_enhanced = system_original + "\n\nNOTA: Este usuario es avanzado y hace preguntas técnicas frecuentes. Puedes ser más específico y técnico en tus respuestas."
    else:
        system_enhanced = system_original + "\n\nNOTA: Este usuario es casual. Mantén respuestas simples y amigables."
    

    system_enhanced = create_enhanced_prompt_with_memory(
        system_original, question, user_id, session_id
    )
    
    # NUEVO: Agregar consultas similares del historial como ejemplos adicionales
    logger.info("-------------------------------ST-historical_context-------------------------------")
    historical_context = get_relevant_context_for_question(question, user_id, session_id, max_context_items=3)
    # print(historical_context)
    logger.info("-------------------------------EN-historical_context------------------------------- \n\n")
    #############
 
    prompt = ChatPromptTemplate.from_messages([
             ("system", system_enhanced), 
             ("user", query_prompt_equipos["human"]) 
        ])
    ##################
    
    structured_llm = llm_model.with_structured_output(ConvertToSQL)

    get_query_chain = prompt | structured_llm 
    
    # Incluir contexto histórico en los parámetros
    invoke_params = {
        "pregunta_usuario": question,
        "selected_table": selected_table,
        "descriptions_short": descriptions_short,
        "column_list": column_list,
        "few_shot_queries": few_shot_queries
    }
    
    # # NUEVO: Si hay contexto histórico, agregarlo como ejemplo adicional
    # if historical_context:
    #     invoke_params["historical_examples"] = historical_context[:500]  # Limitar longitud
    # #print('invoke params dentro de GET QUERY:', invoke_params["historical_examples"])

    # 
    print_prompt=True
    if print_prompt:
        prompt_como_string = prompt.format(**invoke_params)
        print("\n----- PROMPT ENVIADO AL LLM -----\n")
        print(prompt_como_string)

    logger.info("\n----- ST get_query_chain -----\n")
    consulta = get_query_chain.invoke(invoke_params)
    logger.info("\n----- EN get_query_chain -----\n")

    

    consulta = consulta.sql_query
    # Save original sql query sin improve query
    state['raw_sql_query'] = consulta

    conn = get_connection_to_db()
    consulta, improved_question = _improve_query_if_needed(consulta, conn, question)
    
    print(f'DESPUES Pregunta antes de entrar al FUZZY:{improved_question}')

    state['sql_query']=consulta
    state['question']=improved_question
    state['invoke_params']=invoke_params
    end1 = time.perf_counter()
    state["dt"] = state["dt"] + end1 - start1
    print(f"state['sql_query']: {state['sql_query']}")
    print(f"Get query Tiempo transcurrido: {end1 - start1:.2f} segundos")
    
    
    try:
        # IDs para trazabilidad (puedes mejorar cómo se generan si quieres, pero uuid está bien)
        human_msg_id = str(uuid.uuid4())
        ai_msg_id = str(uuid.uuid4())
        save_sql_execution_simple(
            session_id, 
            state['question'], 
            state['sql_query'], 
            True,  # success
            end1 - start1  # processing_time
        )
        save_complete_memory(state, "sql_workflow_complete", human_msg_id, ai_msg_id)
        #save_performance_metric_simple(session_id, 'get_query_memory', end1 - start1, True)
        print("✅ Memory completa guardada (AgentState) en PostgreSQL")
    except Exception as e:
        print(f"⚠️ Error guardando consulta SQL: {str(e)}")
    conn.close()
    return state


def ejecutar_consulta(state: AgentState):
    """
    Función que ayuda a orquestar el flujo del grafo hacia un pedido de una novedad o una consulta
    en Teradata. Se basa en la pregunta o consulta del usuario.

    Args:
        state: Estado del agente (AgentState)

    Returns:
        AgentState actualizado con los resultados de la consulta.
    """
    logger.info("🚀 Entrando en ejecutar_consulta...")

    start = time.perf_counter()
    session_id = state.get("session_id", str(uuid.uuid4()))
    state["session_id"] = session_id
    logger.info(f"🆔 Session ID: {session_id}")

    # Determina la query SQL a ejecutar
    if state["sql_critique"].get("success", True):
        sql_query = state["sql_query"].strip()
        logger.info("✅ Usando la query SQL original...")
    else:
        sql_query = state["sql_critique"].get("sql_query", "").strip()
        logger.info("🔄 Usando una query SQL corregida del análisis SQL critique...")

    # Pregunta del usuario
    pregunta = state["question"]
    logger.info(f"ℹ️ Pregunta del usuario: {pregunta}")
    logger.info(f"📜 Query a ejecutar: {sql_query}")

    # Configuración inicial
    limit_rows = 500
    conn = get_connection_to_db()
    count = 0
    flag = True
    resultados_df = None  # Asegúrate de inicializar en caso de fallos

    while flag and count < 3:
        count += 1
        try:
            logger.info(f"🔄 Ejecutando intento {count} de consulta SQL...")

            cursor = conn.cursor()
            cursor.execute(sql_query)
            resultados = cursor.fetchall()
            description = cursor.description
            cursor.close()
            conn.close()

            # Convertir los resultados a un DataFrame de Pandas
            resultados_df = pd.DataFrame(resultados, columns=[desc[0] for desc in description])
            cantidad_res = len(resultados_df)
            logger.info(f"✅ Consulta ejecutada exitosamente. Filas recuperadas: {cantidad_res}")

            # Limitar el número de filas si excede el límite
            if cantidad_res > limit_rows:
                resultados_df = resultados_df.head(limit_rows)
                logger.info(f"🔢 Resultado truncado a {limit_rows} filas.")

            # Generar respuesta para el resultado
            respuesta_generada = f"Consulta: {sql_query}\nResultados:\n{resultados_df.to_markdown()}"
            state["query_result"] = respuesta_generada
            flag = False
            logger.info("🎉 SQL query ejecutada correctamente en este intento.")
            logger.info(respuesta_generada)
            #state["query_errors"].append("")

        except Exception as e:
            error_message = str(e)
            state["query_result"] = f"Error al ejecutar la SQL query: {error_message}"
            logger.error("❌ No se pudo ejecutar la consulta en Teradata.")
            logger.exception(error_message)  # Muestra el stack trace del error
            error_string = f"Consulta ejecutada: {sql_query}. Error: {error_message}"

            # Agregamos el mensaje a la lista de errores
            state["query_errors"].append(error_string)
            return state
            # Intentar regenerar la query y guardarla
            # sql_query = _regenerate_query(pregunta, esquema=datos_db, llm_model=llm_gpt_o3_mini)
            # logger.info(f"🔄 Query regenerada: {sql_query}")

            try:
                save_sql_error_simple(session_id, pregunta, sql_query, error_message, count)
                logger.info(f"✅ Error SQL guardado correctamente en intento {count}.")
            except Exception as db_error:
                logger.error(f"⚠️ Error al guardar el SQL error en la base de datos: {str(db_error)}")

    end = time.perf_counter()
    execution_time = end - start
    state["dt"] += execution_time
    logger.info(f"⏲️ Tiempo total de ejecución: {execution_time:.2f} segundos.")

    # Guardar métricas de rendimiento
    try:
        success_flag = flag == False
        save_performance_metric_simple(session_id, "ejecutar_consulta", execution_time, success_flag)
        logger.info(f"✅ Métricas de rendimiento guardadas exitosamente.")
    except Exception as e:
        logger.error(f"⚠️ Error al guardar métricas de rendimiento: {str(e)}")

    logger.info("🏁 Saliendo de ejecutar_consulta.")
    return state


def generate_human_readable_answer(state: AgentState, llm_model = llm_gpt_4o_mini):
    """
    Funcion que genera una respuesta legible para un humano a partir de la salida de Teradata y la consulta del usuario.
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
    result = state["query_result"]
    dt = state["dt"]
    generate_prompt = ChatPromptTemplate.from_messages([
         ("system", sql_readeble_prompt['system']), MessagesPlaceholder("messages"),
         ("human",sql_readeble_prompt['human'])
         ])

    human_response = generate_prompt | llm_model | StrOutputParser()
    answer = human_response.invoke({'question':pregunta,
                                    'results':result,
                                    'messages': state["messages"],
                                    'dic_equi':corrections,
                                    'dt':dt})
    
    state["query_result"] = answer
    end = time.perf_counter()

    print(f"Respuesta humana Tiempo transcurrido: {end - start:.2f} segundos")
    
    # 1) New messages with UUIDs
    human_msg = HumanMessage(id=str(uuid.uuid4()), content=pregunta, name='memoria')
    ai_msg    = AIMessage(id=str(uuid.uuid4()), content=answer, name='memoria')

    # 2) Remove all but the last 4 messages
    #removals = [RemoveMessage(id=m.id) for m in state["messages"][:-3]]
    #print('Mensajes de la conversion previos:', state['messages'])
    

    try:
        save_complete_memory(state, "sql_workflow_complete", human_msg.id, ai_msg.id)
        print("✅ Estado SQL completo guardado")
    except Exception as e:
        print(f"⚠️ Error guardando estado SQL: {str(e)}")


    return {
        "messages":    [*state["messages"], human_msg, ai_msg],
        "query_result": answer,
        "dt":           state["dt"] + end -start,
        "session_id":   state.get('session_id', str(uuid.uuid4()))
    }



from src.self_verification_agent.src.sql_verification import run_sql_critic

def get_query_critique(state: AgentState):
    """Genera una crítica para la consulta SQL o proceso de generación de una consulta en `state`
    y la añade bajo la clave ``"sql_critique"``. 
    """
    logger.info('Run Critique Agent SQL')

    # 1. Verificación de claves obligatorias
    required_keys = ("sql_query", "raw_sql_query", "question", "invoke_params")
    missing = [k for k in required_keys if k not in state]
    if missing:
        logger.info(f"Faltan claves obligatorias en el estado: {', '.join(missing)}")
        
    session_id = state.get('session_id', str(uuid.uuid4()))
    state['session_id'] = session_id
    
    # 2. Ejecutar el crítico SQL
    critic_output, _ = run_sql_critic(
        state["question"],
        state["invoke_params"]["few_shot_queries"],
        state["invoke_params"]["column_list"],
        state["sql_query"].strip(),
        state["raw_sql_query"].strip(),
        state.get("query_errors", "")
    )
    logger.info(f'critic_output: {critic_output}')
    state["sql_critique"] = critic_output

    return state

def get_query_(question):
    """
    Arma una consulta SQL para teradata en función de la tarea o pregunta asignada. 
    La pregunta debe de estar orientada a la información que tienen las tablas.

    Args:
        question: tarea a transformar en consulta sql
    """
    logger.info(f"↩️  Entrando a get_query_ | pregunta: {question!r}")
    start_total = time.perf_counter()
    timings = {}  

    llm_model = llm_gpt_o3_mini
    # state = AgentState

    # if state['dt'] >=25:
    #     logs = [
    #     "Estoy consultando a la base de datos."
    #     ]
    #     state["messages"] = state.get("messages", []) + [AIMessage(content=log, name="log") for log in logs]
    
    # start1 = time.perf_counter()
    logger.info(f"question: {question}")

    selected_table = []
    for i in datos_db.keys():
        selected_table.append(i)

    # 1) Embedding de la pregunta ─────────────────────────
    t0 = time.perf_counter()    
    embedding_vec = embeddings.embed_query(question)  # 1 sola llamada
    timings["embedding"] = time.perf_counter() - t0
    logger.info(f"[TIMING] embedding               : {timings['embedding']:.3f} s")

    # 2) Retrieval de tablas ──────────────────────────────
    t0 = time.perf_counter()
    descriptions_long, descriptions_short = tables_index_retrieval(question, embedding_vec)
    timings["tables_retrieval"] = time.perf_counter() - t0
    logger.info(f"[TIMING] tables_index_retrieval   : {timings['tables_retrieval']:.3f} s")
    # logger.info(f"descriptions_short   : {descriptions_short}")

    # 3) Retrieval de ejemplos (catálogo) ─────────────────
    t0 = time.perf_counter()
    few_shot_queries, few_shot_tables, _ = catalogo_index_retrieval(question, embedding_vec)

    _, few_shot_queries = run_critic_with_examples(
        question,
        few_shot_queries,  # ← USAR LA VERSION STRING
        critic_graph
    )
    # debug_dict_issues(critic_output, "critic_output")
    # debug_dict_issues(few_shot_queries_returned, "few_shot_queries_post_critic")
    
    # log_debug(f"\n🔄 DESPUÉS DE run_critic_with_examples:")
    # log_debug(f"   Critic output success: {critic_output.get('success')}")
    # log_debug(f"   Critic output keys: {list(critic_output.keys()) if isinstance(critic_output, dict) else 'No dict'}")
    # log_debug(f"   Few shot queries returned length: {len(few_shot_queries_returned)}")
    # log_debug(f"   Few shot queries returned preview: {repr(few_shot_queries_returned[:300])}")
    print(f"few_shot_queries: {few_shot_queries}")

    timings["catalogo_retrieval"] = time.perf_counter() - t0
    logger.info(f"[TIMING] catalogo_index_retrieval : {timings['catalogo_retrieval']:.3f} s")

    # 4) Selección de tablas ──────────────────────────────
    t0 = time.perf_counter()    
    selected_table, _, _ = get_tables(
    question, 
    few_shot_tables, 
    descriptions_long, 
    llm_model
    )
    timings["get_tables"] = time.perf_counter() - t0
    logger.info(f"selected_table   : {selected_table}")
    logger.info(f"[TIMING] get_tables               : {timings['get_tables']:.3f} s")

    # 5) Columnas ─────────────────────────────────────────
    t0 = time.perf_counter()
    column_list = _get_column_information(pregunta_usuario = question, selected_table=selected_table)
    timings["columns_info"] = time.perf_counter() - t0
    logger.info(f"[TIMING] _get_column_information  : {timings['columns_info']:.3f} s")


    descriptions_short = selected_tables_fun(datos_db)   


    # NUEVO: Enriquecer el prompt del sistema con memoria histórica
    system_original = query_prompt_equipos["system"]
        
    # NUEVO: Enriquecer el prompt del sistema con memoria histórica y personalización
    # system_original = query_prompt_equipos["system"]
    # if user_patterns.get('user_type') == 'power_user':
    #     system_enhanced = system_original + "\n\nNOTA: Este usuario es avanzado y hace preguntas técnicas frecuentes. Puedes ser más específico y técnico en tus respuestas."
    # else:
    #     system_enhanced = system_original + "\n\nNOTA: Este usuario es casual. Mantén respuestas simples y amigables."
    

    # system_enhanced = create_enhanced_prompt_with_memory(
    #     system_original, question, user_id, session_id
    # )
    
    # NUEVO: Agregar consultas similares del historial como ejemplos adicionales
    # historical_context = get_relevant_context_for_question(question, user_id, session_id, max_context_items=3)
    
    #############
    
    # 6) Prompt + LLM ─────────────────────────────────────
    t0 = time.perf_counter()
    prompt = ChatPromptTemplate.from_messages([
             ("system", system_original), 
             ("user", query_prompt_equipos["user"]) 
        ])
    ##################
    
    # structured_llm = llm_model.with_structured_output(ConvertToSQL)

    # get_query_chain = prompt | structured_llm 
    
    # Incluir contexto histórico en los parámetros
    invoke_params = {
        "pregunta_usuario": question,
        "selected_table": selected_table,
        "descriptions_short": descriptions_short,
        "column_list": column_list,
        "few_shot_queries": few_shot_queries,
        "reasoning": "",
        "few_shot_queries_equipos": "",
        "few_shot_queries_costos": "",
    }
    
    get_query_chain = prompt | llm_model | StrOutputParser()

    # NUEVO: Si hay contexto histórico, agregarlo como ejemplo adicional
    # if historical_context:
    #     invoke_params["historical_examples"] = historical_context[:500]  # Limitar longitud
    #print('invoke params dentro de GET QUERY:', invoke_params["historical_examples"])

    consulta_raw = get_query_chain.invoke(invoke_params)

    # Intentamos extraer JSON válido
    JSON_REGEX = re.compile(r"\{[\s\S]*\}")
    match = JSON_REGEX.search(consulta_raw)
    if match:
        try:
            output_json = json.loads(match.group())
            # Verificación mínima de claves
    
        except Exception:
            pass  # JSON malformado → se repetirá el nodo

    # Registrar la respuesta original del LLM para debugging
    logger.debug(f'Respuesta original del LLM: {output_json}')
    
    # Limpiar la consulta SQL utilizando nuestra función simplificada
    consulta = limpiar_consulta_sql(output_json["sql"])

    timings["prompt_llm"] = time.perf_counter() - t0
    logger.info(f"[TIMING] prompt+LLM invoke        : {timings['prompt_llm']:.3f} s")
    # Save original sql query sin improve query
    # state['raw_sql_query'] = consulta

    # 7) Mejorar la query ─────────────────────────────────
    t0 = time.perf_counter()
    conn = get_connection_to_db()
    consulta, _ = _improve_query_if_needed(consulta, conn, question)
    timings["_improve_query"] = time.perf_counter() - t0
    logger.info(f"[TIMING] improve_query_if_needed  : {timings['_improve_query']:.3f} s")
    # print(f'DESPUES Pregunta antes de entrar al FUZZY:{improved_question}')

    # state['sql_query']=consulta
    # state['question']=improved_question
    # state['invoke_params']=invoke_params
    # end1 = time.perf_counter()
    # state["dt"] = state["dt"] + end1 - start1
    # print(f"state['sql_query']: {state['sql_query']}")
    # print(f"Get query Tiempo transcurrido: {end1 - start1:.2f} segundos")
    
    
    # try:
    #     # IDs para trazabilidad (puedes mejorar cómo se generan si quieres, pero uuid está bien)
    #     human_msg_id = str(uuid.uuid4())
    #     ai_msg_id = str(uuid.uuid4())
    #     save_sql_execution_simple(
    #         session_id, 
    #         state['question'], 
    #         state['sql_query'], 
    #         True,  # success
    #         end1 - start1  # processing_time
    #     )
    #     save_complete_memory(state, "sql_workflow_complete", human_msg_id, ai_msg_id)
    #     #save_performance_metric_simple(session_id, 'get_query_memory', end1 - start1, True)
    #     print("✅ Memory completa guardada (AgentState) en PostgreSQL")
    # except Exception as e:
    #     print(f"⚠️ Error guardando consulta SQL: {str(e)}")
    # conn.close()
    return consulta

def ejecutar_consulta_(sql_query):
    """
    Función que ayuda a orquestar el flujo del grafo hacia un pedido de una novedad o una consulta
    en Teradata. Se basa en la pregunta o consulta del usuario.

    Args:
        sql_query: consulta sql en str
        state: Estado del agente (AgentState)

    Returns:
        AgentState actualizado con los resultados de la consulta.
    """
    logger.info("🚀 Entrando en ejecutar_consulta...")
    # state = AgentState

    # start = time.perf_counter()
    # session_id = state.get("session_id", str(uuid.uuid4()))
    # state["session_id"] = session_id
    # logger.info(f"🆔 Session ID: {session_id}")

    # # Determina la query SQL a ejecutar
    # if state["sql_critique"].get("success", True):
    #     sql_query = state["sql_query"].strip()
    #     logger.info("✅ Usando la query SQL original...")
    # else:
    #     sql_query = state["sql_critique"].get("sql_query", "").strip()
    #     logger.info("🔄 Usando una query SQL corregida del análisis SQL critique...")

    # Pregunta del usuario
    logger.info(f"📜 Query a ejecutar: {sql_query}")

    # Configuración inicial
    limit_rows = 200
    conn = get_connection_to_db()
    count = 0
    # flag = True
    resultados_df = None  # Asegúrate de inicializar en caso de fallos

    try:
        logger.info(f"🔄 Ejecutando intento {count} de consulta SQL...")

        cursor = conn.cursor()
        cursor.execute(sql_query)
        resultados = cursor.fetchall()
        description = cursor.description
        cursor.close()
        conn.close()

        # Convertir los resultados a un DataFrame de Pandas
        resultados_df = pd.DataFrame(resultados, columns=[desc[0] for desc in description])
        cantidad_res = len(resultados_df)
        logger.info(f"✅ Consulta ejecutada exitosamente. Filas recuperadas: {cantidad_res}")

        # Limitar el número de filas si excede el límite
        if cantidad_res > limit_rows:
            resultados_df = resultados_df.head(limit_rows)
            logger.info(f"🔢 Resultado truncado a {limit_rows} filas.")

        # Generar respuesta para el resultado
        respuesta_generada = f"Consulta: {sql_query}\nResultados:\n{resultados_df.to_markdown()}"
        # state["query_result"] = respuesta_generada
        # flag = False
        # logger.info("🎉 SQL query ejecutada correctamente en este intento.")
        # logger.info(respuesta_generada)
        # state["query_errors"] = []
        return respuesta_generada

    except Exception as e:
        # error_message = str(e)
        # state["query_result"] = f"Error al ejecutar la SQL query: {error_message}"
        # logger.error("❌ No se pudo ejecutar la consulta en Teradata.")
        # logger.exception(error_message)  # Muestra el stack trace del error
        # error_string = f"Consulta ejecutada: {sql_query}. Error: {error_message}"

        # # Agregamos el mensaje a la lista de errores
        # state["query_errors"].append(error_string)
        return f"Error al ejecutar la SQL query: {e}"
        # Intentar regenerar la query y guardarla
        # sql_query = _regenerate_query(pregunta, esquema=datos_db, llm_model=llm_gpt_o3_mini)
        # logger.info(f"🔄 Query regenerada: {sql_query}")

        

import uuid
from typing import Dict, Any
from langchain.schema import HumanMessage
from src.react_sql_agent.src.agent import react_graph     # <- importa grafo ReAct


def react_sql_wrapper(state: AgentState) -> AgentState:
    """Ejecuta el grafo ReAct (get_query + ejecutar_consulta) como un nodo único
    dentro de otro flujo y devuelve el estado del grafo padre actualizado."""
    
    # 1) Construir estado inicial para el sub-grafo
    session_id = state.get("session_id") or str(uuid.uuid4())
    state["session_id"] = session_id    

    update = {
        "question": state["question"],
        "messages": [HumanMessage(content=state["question"])],
        "thread_id": session_id  
    }

    # 2) Ejecutar el grafo ReAct — una sola llamada es suficiente
    sub_state = react_graph.invoke(update)      # o .invoke_stream si quieres ver pasos

    # 3) Sincronizar la información relevante al estado padre
    state["sql_query"]    = sub_state.get("sql_query")
    state["query_result"] = sub_state.get("query_result")
    # opcional: si quieres conservar todo el historial conjunto
    state.setdefault("messages", []).extend(
        [m for m in sub_state["messages"] if m not in state["messages"]]
    )
    state["dt"] = sub_state.get("dt", state.get("dt", 0.0))

    # 4) ¡Listo!
    return state

def limpiar_consulta_sql(consulta_raw):
    """
    Función simplificada para extraer solo la consulta SQL válida, eliminando cualquier
    texto explicativo antes o después de la consulta y asegurándose de que NO termina
    con punto y coma (específico para Teradata SQL).
    """
    # Si la consulta está vacía, devolver vacío
    if not consulta_raw or consulta_raw.strip() == '':
        return ''
    
    # Eliminar marcadores de código
    consulta = consulta_raw.replace('```sql', '').replace('```', '').replace('`', '')
    
    # Patrones que indican el INICIO de una consulta SQL válida
    inicio_patterns = [
        'SELECT ', 'select ', 'WITH ', 'with ', 
        'INSERT ', 'insert ', 'UPDATE ', 'update ', 
        'DELETE ', 'delete ', 'CREATE ', 'create ',
        'ALTER ', 'alter ', 'DROP ', 'drop '
    ]
    
    # Patrones que indican el FIN de una consulta SQL válida
    fin_patterns = [
        ' **', '**', ' --', '--', ' /*', '/*', ' #', '#',
        'Explicación:', 'explicación:', 'Explanation:', 'explanation:',
        'Nota:', 'nota:', 'Note:', 'note:',
        'Esta consulta', 'esta consulta', 'This query', 'this query'
    ]
    
    # Buscar el inicio de la consulta SQL
    inicio_idx = -1
    for pattern in inicio_patterns:
        pos = consulta.lower().find(pattern.lower())
        if pos != -1 and (inicio_idx == -1 or pos < inicio_idx):
            inicio_idx = pos
    
    if inicio_idx == -1:
        # No se encontró un patrón de inicio válido
        return ''
    
    # Extraer desde el inicio encontrado
    consulta = consulta[inicio_idx:]
    
    # Buscar el fin de la consulta SQL
    fin_idx = len(consulta)
    for pattern in fin_patterns:
        pos = consulta.lower().find(pattern.lower())
        if pos != -1 and pos < fin_idx:
            fin_idx = pos
    
    # Si se encontró un punto y coma, eliminar el punto y coma y todo lo que sigue
    punto_coma_idx = consulta.find(';')
    if punto_coma_idx != -1 and punto_coma_idx < fin_idx:
        fin_idx = punto_coma_idx  # No incluir el punto y coma
    
    # Extraer solo hasta el fin encontrado
    consulta = consulta[:fin_idx].strip()
    
    # Asegurarse de que NO termina con punto y coma (importante para Teradata)
    if consulta.endswith(';'):
        consulta = consulta[:-1]
    
    # Eliminar espacios extras
    consulta = ' '.join(consulta.split())
    
    return consulta

#==========
if __name__ == '__main__':
    print('entro al print')



    