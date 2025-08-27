import time
import pandas as pd
from utils.util_logger import GetLogger
from config.settings import LOGLEVEL, CLOUDERA_HOST, CLOUDERA_USER, CLOUDERA_PASS, CLOUDERA_PORT, CLOUDERA_AUTH
from utils.utils import get_connection_to_cl
from workflows.states import SqlAgentState


logger = GetLogger(__name__, level=LOGLEVEL, log_file='src/data/app_logs.log').logger


def execute_sql_query(state: SqlAgentState) -> SqlAgentState:
    start = time.perf_counter()
    sql_query = state["sql_query"]
    limit_rows = 10000
    logger.info(f"Query a ejecutar: {sql_query}")

    try:
        conn = get_connection_to_cl(CLOUDERA_HOST, CLOUDERA_USER, CLOUDERA_PASS, CLOUDERA_PORT, CLOUDERA_AUTH)
    except Exception as e:
        logger.error(f"Error conectando a Cloudera: {e}")
        state["sql_results"] = f"Error de conexión a Cloudera: {str(e)}"
        return state

    count = 0
    flag = True

    while flag and count < 3:
        count += 1
        logger.info(f"Intento de ejecución #{count}")
        try:
            cursor = conn.cursor()
            cursor.execute(sql_query)
            resultados = cursor.fetchall()
            description = cursor.description
            cursor.close()
            conn.close()

            resultados_df = pd.DataFrame(resultados, columns=[desc[0] for desc in description])
            cantidad_res = len(resultados_df)
            logger.info(f"Consulta ejecutada: {cantidad_res} filas obtenidas")

            if cantidad_res > limit_rows:
                resultados_df = resultados_df.head(limit_rows)
                logger.warning(f"Resultados limitados a {limit_rows} filas")

            respuesta_generada = f"Resultados:\n{resultados_df.to_markdown()}"
            flag = False
            state['sql_results'] = respuesta_generada

        except Exception as e:
            logger.warning(f"Error en intento #{count}: {str(e)}")
            state["sql_results"] = f"Error al ejecutar la SQL query: {str(e)}"
            if count >= 3:
                logger.error("Máximo número de intentos alcanzado")

    end = time.perf_counter()
    logger.info(f"Ejecución completada en {end - start:.2f} segundos")
    return state

