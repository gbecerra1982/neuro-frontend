from fuzzywuzzy import fuzz
import re
import os
from langchain.prompts import ChatPromptTemplate
import json
from src.prompts.prompt_minipywoIII import find_values_prompt, context_tables_dict, get_where_instances_prompt
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from src.util import GetLogger
import Levenshtein


LOGLEVEL = os.environ.get('LOGLEVEL_SQLAGENT', 'DEBUG').upper()
logger=GetLogger(__name__, level=LOGLEVEL).logger

logger=GetLogger(__name__, level=LOGLEVEL).logger
LOGLEVEL = os.environ.get('LOGLEVEL_ROOT', 'INFO').upper()
logger = GetLogger("", level=LOGLEVEL).logger



TABLE_BOCA_POZO = "P_DIM_V.UPS_DIM_BOCA_POZO"
ZONA_VACA_MUERTA = "P_DIM_V.UPS_DIM_ZONA"


system = """Eres un asistente encargado de analizar consultas SQL para detectar y mejorar cláusulas WHERE, asegurándote de que las consultas sean precisas y optimizadas. Recibirás una consulta sql_query, deberás realizar varias tareas sobre ella y entregar una lista de valores, columnas y tablas identificadas. Tu misión principal es identificar todas las cláusulas WHERE que no sean de tipo numérico o de fecha, y luego generar una lista de valores, columnas y tablas identificadas. La calidad de tu análisis impacta directamente en la efectividad de las consultas SQL.
# INSTRUCCIONES
- Analiza la sql_query que se te proporcione y realiza las siguientes tareas:
  1. Identifica todas las cláusulas WHERE presentes en la consulta SQL y devuelve cada cláusula identificada como un diccionario con los campos 'value', 'column', y 'table'. Los casos que no se incluiran son aquellos donde el filtro indique por ejemplo NOT NULL u otros valores de ese tipo que ya son predeterminados. 
  Ejemplo de la tarea: consulta: "SELECT COL1, COL2 FROM P_DIM_V.TABLA WHERE COL1 LIKE '%Val1%' AND COL2 LIKE '%Val2%' AND COL3 > 300"" --> [{{"value":"Val1", "column":"COL1", "table":"P_DIM_V.TABLA"}}, {{"value":"Val2", "column":"COL2", "table":"P_DIM_V.TABLA"}}, {{"value":"300", "column":"COL3", "table":"P_DIM_V.TABLA"}}]. Si no se encuentran cláusulas WHERE, devuelve la lista vacía y muestra la lista vacía.
  2. Excluye de la lista todas las cláusulas que contengan filtros cuyo valor sea exclusivamente numérico o una fecha. Ejemplo: [{{"value":"Val1", "column":"COL1", "table":"P_DIM_V.TABLA"}}, {{"value":"Val2", "column":"COL2", "table":"P_DIM_V.TABLA"}}]. Ten en cuenta que no debes excluir valores numéricos que van acompañados de letras (por ejemplo, "Val1", "A-123", "XYZ 234"); solo debes excluir valores que sean exclusivamente numéricos o fechas.
  3. Presenta el resultado final después de la palabra 'LISTA:' con cada valor de la lista entre comillas dobles ("). Nunca incluyas después de la palabra 'LISTA:' el tipo de contenido, como por ejemplo 'plaintext', 'json', 'sql'."""


user = """
    Please, follow this input example format:            
    ----------------------------------------------------------------------            
    # EJEMPLO 1:
    sql_query = SELECT Supervisor_Name_1, Supervisor_Name_2 FROM P_DIM_V.UPS_DIM_EQUIPOS_ACTIVOS WHERE Nombre_Equipo LIKE '%f35%'
    "value" : "f35"
    "column" : "Nombre_Equipo"
    "table" : "P_DIM_V.UPS_DIM_EQUIPOS_ACTIVOS"
    LISTA: [{{"value":"f35", "column":"Nombre_Equipo", "table":"P_DIM_V.UPS_DIM_EQUIPOS_ACTIVOS"}}]

    # EJEMPLO 2:
    sql_query = SELECT SUM(Progreso_Num) FROM P_DIM_V.UPS_FT_AVANCE_PERFORACION AP JOIN P_DIM_V.UPS_DIM_EQUIPOS_ACTIVOS EA ON AP.Equipo_Id = EA.Equipo_Id WHERE AP.Fecha_Dttm = CURRENT_DATE AND EA.Nombre_Equipo LIKE '%laje-54%';
    "value" : "laje-54"
    "column" : "Boca_Pozo_Nombre_Oficial"
    "table" : "P_DIM_V.UPS_DIM_EQUIPOS_ACTIVOS"
    LISTA: [{{"value":"laje-54", "column":"Nombre_Equipo", "table":"P_DIM_V.UPS_DIM_EQUIPOS_ACTIVOS"}}]
    ----------------------------------------------------------------------
    
    Por favor, analiza la '{sql_query}' y realiza las tareas descritas.
    """

def get_where_instances(sql_query, llm):
    # Si la consulta es de Vaca Muerta (detectamos que se utiliza la tabla principal y que se hace referencia a la columna de la tabla unida)
    if TABLE_BOCA_POZO in sql_query.upper() and "ZONA_YACIMIENTO" in sql_query.upper():
        # Retornamos el JSON list determinístico ya armado para Vaca Muerta
        json_list = [
            {"value": "Oeste Norte", "column": "SUBREGION_DBU_NAME", "table": TABLE_BOCA_POZO},
            {"value": "Oeste Sur", "column": "SUBREGION_DBU_NAME", "table": TABLE_BOCA_POZO},
            {"value": "Bandurria Sur", "column": "SUBREGION_DBU_NAME", "table": TABLE_BOCA_POZO},
            {"value": "La Amarga Chica", "column": "SUBREGION_DBU_NAME", "table": TABLE_BOCA_POZO},
            {"value": "Aguada del Chañar", "column": "SUBREGION_DBU_NAME", "table": TABLE_BOCA_POZO},
            {"value": "Loma Campana", "column": "SUBREGION_DBU_NAME", "table": TABLE_BOCA_POZO},
            {"value": "Sur I", "column": "SUBREGION_DBU_NAME", "table": TABLE_BOCA_POZO},
            {"value": "Aguada Toledo - Sierra Barrosa", "column": "ACTIVO_DBU_NAME", "table": TABLE_BOCA_POZO},
            {"value": "VM", "column": "ZONA_YACIMIENTO", "table": ZONA_VACA_MUERTA}
        ]
        return json_list
    else:
        # Recorrido para consultas que NO son de Vaca Muerta: usamos el enfoque actual que invoca al LLM.
    #    prompt_where = ChatPromptTemplate.from_messages([
    #        ("system", system),
    #        ("user", user)
    #    ])

        prompt_where = ChatPromptTemplate.from_messages([
                    ("system", get_where_instances_prompt["system"]),
                    ("user", get_where_instances_prompt["user"])
                ])



        chain_where = prompt_where | llm
        test = chain_where.invoke({"sql_query": sql_query})
        
        # Now we take the part after "LISTA:"
        split_text = test.content.split("LISTA:")
        lista_part = split_text[-1] if len(split_text) > 1 else ""
        # Regex to extract content between square brackets
        lista_part = lista_part.replace("\n", "")
        pattern = re.compile(r'\[[^\]]*\]')
        match = pattern.search(lista_part)
        json_list = []
        if match:
            json_list_str = match.group(0)
            json_list_str = json_list_str.replace("'", '"')
            print("GET_WHERE_INSTANCES json_list_str",json_list_str)  # Extraer el string de la lista
            try:
                print(f"AQUI EL JSON LIST:  {str(json_list)}")
                json_list = json.loads(json_list_str)  # Convertir el string a una lista de Python
            except json.JSONDecodeError:
                print("Error al decodificar JSON.")
        else:
            print("No se encontró la lista.")
    
        return json_list

#---------------------------------------
def get_improved_query(sql_query, json_list, conn, llm, pregunta_usuario, few_shot_queries_equipos=None, few_shot_queries_costos=None):
    """
    Optimiza la validación y mejora de consultas SQL usando validaciones previas y llamadas eficientes al LLM.
    """
    print('ENTRO en GET_IMPROVED_QUERY:')

    json_list_str = json.dumps(json_list)
    es_vaca_muerta = ZONA_VACA_MUERTA in sql_query

    if es_vaca_muerta:
        return _process_vaca_muerta_query(sql_query, json_list_str, llm)
    else:
        return _process_regular_query(sql_query, json_list, conn, llm, pregunta_usuario, few_shot_queries_equipos, few_shot_queries_costos)

def _process_vaca_muerta_query(sql_query, json_list_str, llm):
    """Helper function to process Vaca Muerta queries."""
    logger.info("Detectada consulta de 'Vaca Muerta'. Verificando si se necesita mejorar...")
   
    # Validate if query answers the question
    prompt_validation = ChatPromptTemplate.from_messages([
        ("system", "Eres un experto en Teradata SQL que valida consultas para bases de datos grandes."),
        ("user", """
            Tienes la siguiente consulta SQL predefinida sobre la región de 'Vaca Muerta'.  
            Evalúa si esta consulta YA incluye TODA la información requerida en la pregunta del usuario.
            
            **sql_query:**  
            {sql_query}
            
            **json_list_str:**  
            {json_list_str}
    
            """)
    ])
    logger.info("INVOKING VALIDATION")
    validation_chain = prompt_validation | llm | StrOutputParser()
    validation_result = validation_chain.invoke({
        "sql_query": sql_query,
        "json_list_str": json_list_str
    }).strip().upper()

    if validation_result == "YES":
        logger.info("La consulta predefinida ya responde la pregunta del usuario. No se necesita mejora.")
        return sql_query

# def _process_regular_query(sql_query, json_list, conn, llm, pregunta_usuario, few_shot_queries_equipos, few_shot_queries_costos):
#     """Process regular (non-Vaca Muerta) queries with improved identifier handling."""
#     logger.info("Consulta normal detectada. Aplicando correcciones en WHERE...")
#     print("entro a _PROCESS_REGULAR_QUERY")
    
#     # Check for keywords in user question
#     is_equipment_or_well = _check_equipment_or_well_in_question(pregunta_usuario)
    
#     # 🔧 FIX: Inicializar ambas variables
#     improved_sql_query = sql_query
#     improved_question = pregunta_usuario  # ← AGREGADO: esta línea faltaba
    
#     # Process each item in json_list
#     for item in json_list:
#         print('JSON_LIST ITEM:', item)
#         improved_sql_query, improved_question = _process_json_item(
#             item, 
#             improved_sql_query, 
#             conn, 
#             llm, 
#             is_equipment_or_well, 
#             few_shot_queries_equipos, 
#             few_shot_queries_costos,
#             improved_question  # ← CAMBIO: usar improved_question en lugar de pregunta_usuario
#         )
    
#     return improved_sql_query, improved_question

def _process_regular_query(sql_query, json_list, conn, llm, pregunta_usuario, few_shot_queries_equipos, few_shot_queries_costos):
    """Process regular (non-Vaca Muerta) queries with improved identifier handling."""
    logger.info("Consulta normal detectada. Aplicando correcciones en WHERE...")
    print("🔍 DEBUG: Entro a _PROCESS_REGULAR_QUERY")
    # print(f"🔍 DEBUG: SQL inicial: {sql_query}")
    # print(f"🔍 DEBUG: Pregunta inicial: {pregunta_usuario}")
    # print(f"🔍 DEBUG: JSON_LIST tiene {len(json_list)} items: {json_list}")
    
    # Check for keywords in user question
    is_equipment_or_well = _check_equipment_or_well_in_question(pregunta_usuario)
    # print(f"🔍 DEBUG: is_equipment_or_well: {is_equipment_or_well}")
    
    # 🔧 FIX: Inicializar improved_question antes del loop
    improved_sql_query = sql_query
    improved_question = pregunta_usuario  # ← AGREGADO: faltaba esta inicialización
    
    # Process each item in json_list
    for i, item in enumerate(json_list):
        # print(f'🔍 DEBUG: === Procesando item {i+1}/{len(json_list)} ===')
        # print(f'🔍 DEBUG: JSON_LIST ITEM: {item}')
        # print(f'🔍 DEBUG: SQL antes de procesar: {improved_sql_query}')
        # print(f'🔍 DEBUG: Pregunta antes de procesar: {improved_question}')
        
        try:
            # Llamada a _process_json_item con debugging
            result = _process_json_item(
                item, 
                improved_sql_query, 
                conn, 
                llm, 
                is_equipment_or_well, 
                few_shot_queries_equipos, 
                few_shot_queries_costos,
                improved_question  # ← CAMBIO: usar improved_question en lugar de pregunta_usuario
            )
            
            # Verificar que el resultado sea correcto
            if isinstance(result, (list, tuple)) and len(result) == 2:
                improved_sql_query, improved_question = result
                print(f'✅ DEBUG: Item {i+1} procesado correctamente')
                print(f'🔍 DEBUG: SQL después: {improved_sql_query}')
                print(f'🔍 DEBUG: Pregunta después: {improved_question}')
            else:
                print(f'❌ DEBUG: ERROR - _process_json_item devolvió formato incorrecto: {result}')
                print(f'❌ DEBUG: Tipo: {type(result)}, Longitud: {len(result) if hasattr(result, "__len__") else "N/A"}')
                # Mantener valores actuales si hay error
                print(f'⚠️ DEBUG: Manteniendo valores anteriores para item {i+1}')
                
        except ValueError as e:
            if "too many values to unpack" in str(e):
                print(f'❌ DEBUG: ERROR de unpacking en item {i+1}: {e}')
                print(f'❌ DEBUG: Esto indica que _process_json_item devolvió más de 2 valores')
                # Intentar obtener el resultado de forma segura
                try:
                    result = _process_json_item(
                        item, improved_sql_query, conn, llm, is_equipment_or_well, 
                        few_shot_queries_equipos, few_shot_queries_costos, improved_question
                    )
                    print(f'🔍 DEBUG: Resultado raw para análisis: {result}')
                    if hasattr(result, '__len__') and len(result) >= 2:
                        improved_sql_query, improved_question = result[0], result[1]
                        print(f'✅ DEBUG: Recuperado usando indexing: SQL={improved_sql_query}, Pregunta={improved_question}')
                    else:
                        print(f'⚠️ DEBUG: No se pudo recuperar, manteniendo valores anteriores')
                except Exception as inner_e:
                    print(f'❌ DEBUG: Error en recuperación: {inner_e}')
            else:
                print(f'❌ DEBUG: Error inesperado en item {i+1}: {e}')
                
        except Exception as e:
            print(f'❌ DEBUG: Error general procesando item {i+1}: {e}')
            print(f'⚠️ DEBUG: Manteniendo valores anteriores')
    
    print(f'🔍 DEBUG: === RESULTADO FINAL ===')
    print(f'🔍 DEBUG: SQL final: {improved_sql_query}')
    print(f'🔍 DEBUG: Pregunta final: {improved_question}')
    print(f'🔍 DEBUG: Cambios aplicados: {improved_sql_query != sql_query or improved_question != pregunta_usuario}')
    
    return improved_sql_query, improved_question

def _check_equipment_or_well_in_question(pregunta_usuario):
    """Check if the user's question contains equipment or well keywords."""
    is_equipment_or_well = "equipo" in pregunta_usuario.lower() or "pozo" in pregunta_usuario.lower()
    if is_equipment_or_well:
        logger.info('Se detectó la palabra "equipo" o "pozo" en la pregunta del usuario.')
    return is_equipment_or_well

def _process_json_item(item, sql_query, conn, llm, is_equipment_or_well, few_shot_queries_equipos, few_shot_queries_costos, pregunta_usuario):
    """Process a single item from the json_list."""
    column, value = item['column'], item['value']
    print('🔍 DEBUG: Entro a _PROCESS_JSON_ITEM con item:', item)
    print('🔍 DEBUG: Parámetros recibidos:', {
        'column': column, 
        'value': value, 
        'pregunta_usuario': pregunta_usuario
    })
    
    # Skip certain columns
    if column in ["SUBREGION_DBU_NAME", "ACTIVO_DBU_NAME", "ZONA_YACIMIENTO"]:
        logger.info(f"Columna '{column}' evitada para el valor '{value}'.")
        
        # 🔧 FIX: Siempre devolver 2 valores
        print('🔍 DEBUG: Retornando por columna evitada - sin cambios')
        return sql_query, pregunta_usuario  # ← CAMBIO: era solo sql_query
    
    # Get existing values from database
    partial_observation = _get_column_values(conn, item)
    logger.debug("Valores candidatos encontrados: %s", partial_observation)

    if not partial_observation:
        
        # 🔧 FIX: Siempre devolver 2 valores
        print('🔍 DEBUG: Retornando por partial_observation vacío - sin cambios')
        return sql_query, pregunta_usuario  # ← CAMBIO: era solo sql_query
    
    # Determine if this might be a well or equipment identifier
    is_identifier = _is_identifier_column(column, is_equipment_or_well)
    logger.info(f"Columna '{column}' tratada como identificador: {is_identifier}")
    
    # Find similar values and get corrected value
    print('🔍 DEBUG: Llamando a _get_corrected_value...')
    corrected_value = _get_corrected_value(
        partial_observation,
        value,
        is_identifier,
        llm,
        pregunta_usuario,
        sql_query,
        few_shot_queries_equipos, 
        few_shot_queries_costos 
    )
    
    print(f'🔍 DEBUG: Valor original: "{value}", Valor corregido: "{corrected_value}"')
    
    # Apply correction if different from original
    if corrected_value != value:
        logger.debug("Valor original '%s' distinto al corregido '%s'", value, corrected_value)

        # Validación extra si es identificador
        if is_identifier:
            logger.debug("Aplicando validación extra para identificador…")
            corrected_value = _validate_identifier_correction(value, corrected_value)
        
        logger.info(f'Valor corregido para {column}: {corrected_value}')
        similitud = calcular_similitud_levenshtein(corrected_value, value)
        print(f"🔍 DEBUG: SIMILITUD entre '{corrected_value}' y '{value}': {similitud:.2f}")
        
        # Replace in improved query
        improved_sql_query = sql_query.replace(value, corrected_value)
        improved_question = pregunta_usuario.replace(value, corrected_value)
        logger.info(f'Consulta mejorada: {improved_sql_query}')
        
        print('🔍 DEBUG: Retornando con correcciones aplicadas')
        print(f'🔍 DEBUG: SQL mejorado: {improved_sql_query}')
        print(f'🔍 DEBUG: Pregunta mejorada: {improved_question}')
        return improved_sql_query, improved_question 
    
    # 🔧 NOTA: Este return ya estaba bien (2 valores)
    print('🔍 DEBUG: Retornando sin correcciones - valores originales')
    return sql_query, pregunta_usuario

def _get_column_values(conn, item):
    """Execute query to get values from a column."""
    query = f"SELECT DISTINCT {item['column']} FROM {item['table']}"
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error ejecutando la consulta {query}: {e}")
        return []
    
def _is_identifier_column(column, is_equipment_or_well):
    """Determine if column is an identifier based on name or context."""
    return is_equipment_or_well or any(kw in column.lower() for kw in ["pozo", "equipo", "nombre", "id"])


def _get_corrected_value(partial_observation, value, is_identifier, llm, pregunta_usuario, sql_query=None, few_shot_queries_equipos=None, few_shot_queries_costos=None):
    """Get corrected value using fuzzy search."""
    print('entro a _GET_CORRECTED_VALUE:')
    try:
        limit_val = 500
        list_values = _perform_fuzzy_search(partial_observation, value, limit_val, is_identifier)
        # Get corrected value
        corrected_value_result = select_correct_value_chain(
            value,
            list_values,
            llm,
            equipos=few_shot_queries_equipos,
            few_shot_queries_costos=few_shot_queries_costos,
            pregunta_usuario=pregunta_usuario,
            sql_query=sql_query
        )
        
        return corrected_value_result
        
    except Exception as e:
        logger.error(f"Error en la corrección de valores: {e}")
        # Keep original value in case of error
        return value
    
def _perform_fuzzy_search(partial_observation, value, limit_val, is_identifier):
    """Perform fuzzy search based on identifier status."""
    if is_identifier:
        partial_fuzzy_observation = fuzzy_search_improved(
            partial_observation, 
            value, 
            limit_val,
            is_identifier=True
        )
    else:
        partial_fuzzy_observation = fuzzy_search(
            partial_observation, 
            value, 
            limit_val
        )
    
    return [x[0] for x in partial_fuzzy_observation]

def _validate_identifier_correction(original_value, corrected_value):
    """Validate that numerical components in identifiers are preserved."""
    # If there are numeric components, verify they are preserved
    nums_original = re.findall(r'\d+', original_value)
    
    if not nums_original:
        return corrected_value
    print('_validate_identifier_correction original value:', original_value)
    print('_validate_identifier_correction corrected value:', corrected_value)    
    nums_corrected = re.findall(r'\d+', corrected_value)
    
    # If numeric components don't match, keep original value
    if not nums_corrected or not any(num in nums_corrected for num in nums_original):
        logger.warning(f"Verificación fallida: Los componentes numéricos difieren entre '{original_value}' y '{corrected_value}'. Manteniendo valor original.")
        return original_value
    
    return corrected_value


def select_correct_value_chain(value, list_values, llm, pregunta_usuario=None, sql_query=None, equipos=None,few_shot_queries_costos=None):
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", find_values_prompt['system']),
        ("user", find_values_prompt['user'])
    ])

    chain = prompt | llm | StrOutputParser()
    
    response = chain.invoke({
        "value": value,
        "partial_observation": list_values,
        "equipos": equipos,  
        "few_shot_queries_costos": few_shot_queries_costos,
        "input":pregunta_usuario,
        "sql_query": sql_query
    })
    
    return response

def normalizar_nombre(nombre):
        return nombre #.lower().replace('.', '').replace('-', '').replace('_', '').replace(' ', '')


def fuzzy_search_improved(partial_observation, value, limit=500, is_identifier=False):
    """Versión mejorada de fuzzy_search que prioriza componentes críticos en identificadores"""
    try:
        # Lista de nombres
        if isinstance(partial_observation, list):
            lista_nombres = partial_observation
        else:
            lista_nombres = partial_observation.iloc[:, 0].tolist()
        
        # Normalizamos la lista de nombres y el input del usuario
        nombres_normalizados = [normalizar_nombre(nombre) for nombre in lista_nombres]
        input_normalizado = normalizar_nombre(value)
        
        # Detectar si hay componentes numéricos en el valor
        tiene_numeros = bool(re.search(r'\d+', value))
        
        # Crear una lista para almacenar los nombres junto con su similitud
        resultados_similares = []
        
        # Calculamos la similitud de cada nombre y lo añadimos a la lista
        for nombre, nombre_normalizado in zip(lista_nombres, nombres_normalizados):
            # Método básico de similitud
            similitud = fuzz.partial_ratio(input_normalizado, nombre_normalizado)
            
            # Si es un identificador y contiene números, aplicamos reglas especiales
            if is_identifier and tiene_numeros:
                # Ajustar puntuación basada en coincidencia de componentes numéricos
                nums_valor = re.findall(r'\d+', value)
                nums_nombre = re.findall(r'\d+', nombre)
                
                # Penalizar si hay discrepancia en componentes numéricos
                if nums_valor and nums_nombre:
                    # Si los componentes numéricos no coinciden, reducir drásticamente la similitud
                    nums_match = any(num in nums_nombre for num in nums_valor)
                    if not nums_match:
                        similitud *= 0.3  # Reducir significativamente la puntuación
            
            resultados_similares.append((nombre, similitud))
        
        # Ordenar la lista de resultados por similitud de mayor a menor
        resultados_similares.sort(key=lambda x: x[1], reverse=True)
        
        return resultados_similares[:limit]
    except Exception as e:
        logger.info(f"No se encontraron casos similares: {str(e)}")
        return []

def fuzzy_search(partial_observation, value, limit=500):
    """BUSCA VALORES SIMILARES A FIN DE NO ENVIAR TANTOS A UN PROMPT DE CORRECCIÓN DE ENTIDADES"""
    try:
        # Lista de nombres
        if isinstance(partial_observation, list):
            lista_nombres = partial_observation
        else:
            lista_nombres = partial_observation.iloc[:, 0].tolist()
        
        # Normalizamos la lista de nombres y el input del usuario
        nombres_normalizados = [normalizar_nombre(nombre) for nombre in lista_nombres]
        input_normalizado = normalizar_nombre(value)

        # Crear una lista para almacenar los nombres junto con su similitud
        resultados_similares = []

        # Calculamos la similitud de cada nombre y lo añadimos a la lista
        for nombre, nombre_normalizado in zip(lista_nombres, nombres_normalizados):
            similitud = fuzz.partial_ratio(input_normalizado, nombre_normalizado)
            resultados_similares.append((nombre, similitud))

        # Ordenar la lista de resultados por similitud de mayor a menor
        resultados_similares.sort(key=lambda x: x[1], reverse=True)

        return resultados_similares[:limit]
    except Exception as e:
        logger.info(f"No se encontraron casos similares: {str(e)}")

# GET TABLES
def get_context_tables(selected_table):
    join_dict = context_tables_dict

    added_tables = set()
    reasoning = ""
    for table in selected_table:
        if table in join_dict:
            added_tables.update(join_dict[table]["TABLES"])  # Usamos update para agregar varios elementos a un set
            reasoning += join_dict[table]["REASONING"]
    # Convertir a lista si es necesario, ya sin duplicados
    added_tables = list(added_tables)
    selected_table += added_tables

    # sin duplicados
    selected_table = list(set(selected_table))

    return selected_table, reasoning

def calcular_similitud_levenshtein(palabra1, palabra2):
    # Calcular distancia de Levenshtein
    distancia = Levenshtein.distance(palabra1, palabra2)
    # Calcular similitud
    longitud_max = max(len(palabra1), len(palabra2))
    similaridad = 1 - (distancia / longitud_max)
    return similaridad
