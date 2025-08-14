from src.minipywo import (
    AgentState,
    check_general_relevance,
    general_response,
    corva_call,
    stream_ini,
    generate_human_readable_answer,
    react_sql_wrapper
)
from src.enrutadores.routers import general_relevance_router, field_corr_router, sql_error_router
# from src.react_sql_agent.src.wrapper_agent import react_sql_wrapper 
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

def minipywo_app():
    """
    Workflow del avatar con minipywo. Esta version usa fuzzy para la correccion de enitadades y contempla respuestas de corva.
    """
    
    workflow = StateGraph(AgentState)
    memory = MemorySaver()
    
    workflow.add_node("check_relevance", check_general_relevance)
    workflow.set_entry_point('check_relevance')
    workflow.add_node("general_response", general_response)
    workflow.add_node("corva", corva_call)
    workflow.add_node('stream_ini_consulta', stream_ini)
    workflow.add_conditional_edges( "check_relevance", general_relevance_router, {
            "consulta": "stream_ini_consulta",
            "general_response":"general_response",
            "corva": "corva"
       },
    )
        # ─────── NUEVO NODO CON GRAFO REACT ───────
    workflow.add_node("react_sql", react_sql_wrapper) 
    # from stream_ini_consulta --> react_sql
    workflow.add_edge("stream_ini_consulta", "react_sql")   
    
    # Después de react_sql vamos a la respuesta legible para humano
    workflow.add_node("generate_human_readable_answer", generate_human_readable_answer)
    workflow.add_edge("react_sql", "generate_human_readable_answer")
    # cierres
    workflow.add_edge("generate_human_readable_answer", END)
    workflow.add_edge("general_response", END)
    workflow.add_edge("corva", END)
    
    return workflow.compile(checkpointer=memory)



if __name__ == "__main__":
    """ 
    Sección de pruebas unitarias:
    """
    import uuid
    import os
    from pywo_aux_func import replace_token

    THREAD_ID = os.environ.get("THREAD_ID", str(uuid.uuid4()))
    config = {"configurable": {"thread_id": THREAD_ID}}

    user_question_1 = "que es un avatar?"
    user_question_13 = "Quien es el presidente de ypf?"
    user_question_14 = "Ahora quiero saber como me llamo y si te he preguntado que es un avatar" 
    user_question_15 = "Que sabes de YPF?" 
    user_question_16 = "Te he preguntado por YPF?" 
    user_question_17 = "Como es tu nombre?" 
    user_question_0 = "Que es la sala de RTIC?" 
    user_question_2 =  "me das la última información de los equipos activos del día" #* pero si le pregunto por la question 3 o 4 da la info del equipo.
    user_question_3 = "Me das las novedades del equipo ls 168?"
    user_question_4 = "Me das las novedades del equipo ls 166 en perforacion?"
    user_question_5 = "cuales son las novedades del dia del area de concesion de la angostura sur?" 
    user_question_6 = "Dame los nombres de los equipos DLS activos"
    user_question_7 = "¿Cuál es el costo promedio de equipo para los equipos de Nabors en el último año?" # PYWO BOT DEV me da la misma respuesta.
    user_question_8 = "¿Quién es el company man del equipo F35?"
    user_question_9 = "¿Me das informacion del pozo sclh-1219?" # No trae informacion pero pywodev si.
    user_question_19 = "¿Cuáles son los nombres de los company man para el pozo lach 954 en perforación?"
    user_question_10 = "¿Cuántas horas de NPT hubo en las últimas 24 horas para el pozo YPF.Nq.LACh-391(h)?"# pywobot tampoco trae nada.
    user_question_11 = "cuales son las ultimas novedades?" # distinto a lo que trae pywobot
    user_question_12 = "me das las novedades del area LA ANGOSTURA SUR?" # rompe teradata por la query que devuelve.
    user_question_18 = "quien es el company man del equipo 272839-nube-termo"
    user_question_20 = "los equipos flush by en uso?" # lo corrigio a dls-168...jaja.
    user_question_21 = "que equipos están en fase de aislación en las ultimas 24 horas?" # Observacion: No me trajo todos los equipos.
    user_question_22 = "¿Cuál es la profundidad medida (MD) del tope de la formación Rayoso para el pozo específico LajE4?" # esta no la filtra y encima rompe la consulta. 
    user_question_23 = " Necesito un lista con los pozos activos en vaca muerta."# nonteype object has no attribute strip ???????????
    user_question_24 = "¿Cuál es la profundidad vertical del pozo Lcav 416?" # dice que no encuentra una columna en la base de datos.
    user_question_25 = "cuales son los pozos lach activos?"
    user_question_26 = "Que es la sala RTIC?"
    user_question_27 = "cuanto duro cada fase del pozo LaCh 391?"#  falla el corrector. Lo llega a pozo laje-391# Un dia despuest esto lo hace bien. Aleatoriedad en la generación del modelo?
    user_question_28 = "cuanto duro cada fase del pozo LLL 1587?" # lo hizo perfecto!
    user_question_50 = "¿Cuál es el costo promedio del equipo perforador petrex-30?"
    user_question_51 = "cual es el contratista que mas pozos perforó en el año 2025?" # video demo....
    user_question_52 = "cual fue el equipo que mas pozos perforó hoy?"
    user_question_53 = "cual es el equipo que mas rapido perforó en el día?"
    user_question_54 = "cual es el nombre del equipo que mas rapido perforo en el dia de ayer?"
    user_question_55 = "quien es el vicepresidente de tecnología de YPF?"

    user_question_56 = "dame una lista de los directivos de ypf"
    user_question_57 = "sobre que temas tienes informacion?"
    user_question_58 = "Que equipos de perforación están activos en fase aislación?"

    user_question_random1 = "cuando fue el ultimo cambio de bearing y en que equipo fue?"
    user_question_random10 = "cuanto duró el skidding en el pozo lcav 682?"
    user_question_random2 = "cual es el costo actual del evento donde se encuentra el Y-207?"
    user_question_random3 = "en que pozo se encuentra el equipo Y-207?" # Este lo llevo al Y-301 Y 201.  CORREGIR.

    user_question_random = "me puede decir si algun pozo activo tuvo algun incidente de seguridad?"
    user_question_random = "Cuantos empleados tiene ypf?"
    # Dame más detalles de las actividades que está llevando el equipo dls 166.
    # 1- ¿Cuáles son las novedades de los pozos activos en perforación?
    # 2- y que están haciendo los equipos DLS?
    # 2- a nivel de seguridad hubo algun evento en perforacion?

    app = minipywo_app()
    
    original_list = ['Rial', 'Taim','aim', 'Cénter','ipf','IPF']
    replacement_list = ['Real', 'Time','ime', 'Center','YPF','YPF']
    
    mode = 'invoke' 
    if mode == 'invoke':
        result_1 = app.invoke({"question": user_question_random2}, config)
        print("Result:", result_1["query_result"])
        #result_2 = app.invoke({"question": user_question_random2}, config)
        #print("Result:", result_2["query_result"])
        #result_3 = app.invoke({"question": user_question_11}, config)
        #print("Result:", result_3["query_result"])
        #result_4 = app.invoke({"question": user_question_random3}, config)
        #print("Result:", result_4["query_result"])
       
    else:
    
        for i, metadata in app.stream({"question":user_question_28}, stream_mode="messages",config=config):
            if (metadata['langgraph_node'] =='general_response') or (metadata['langgraph_node']=='generate_human_readable_answer') or (metadata['langgraph_node']=='stream_ini_consulta') or (metadata['langgraph_node']=='repreguntar'):
                token = i.content
                corrected_token = replace_token(token, original_list, replacement_list)
                print(token)
                print(corrected_token)

    