from typing import Optional
from utils.utils import get_connection_to_td
from config.settings import (
    TD_HOST,
    TD_USER,
    TD_PASS,
    LOGLEVEL,
    LOGMECH,
    CURRENT_DATE
)
from utils.util_logger import GetLogger
import os

log_dir = os.path.join(os.getcwd(), 'data')
 
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    print(f"Directorio creado: {log_dir}")
 
logger = GetLogger(__name__, level=LOGLEVEL, log_file=os.path.join(log_dir, 'app_logs.log')).logger

# logger = GetLogger(__name__, level=LOGLEVEL, log_file='src/data/app_logs.log').logger


def _fetch_dynamic_context_sql() -> Optional[str]:
    """
    Ejecuta una consulta SQL para obtener contexto dinámico para el prompt RAG.
    Devuelve un string listo para inyectar en el prompt o None si falla.
    """
    fecha_dinamica_3_meses_atras='2025-05-01'
    sql =  f"""SELECT DISTINCT p.Boca_Pozo_Nombre_Corto_Oficial
    FROM P_DIM_V.UPS_DIM_EQUIPOS_ACTIVOS ea
    JOIN P_DIM_V.UPS_DIM_BOCA_POZO p ON p.Well_Id = ea.WELL_ID
    WHERE p.Boca_Pozo_Nombre_Corto_Oficial IS NOT NULL
    AND ea.Event_Code = 'PER'
    UNION
    SELECT DISTINCT p.Boca_Pozo_Nombre_Corto_Oficial
    FROM P_DIM_V.UPS_FT_DLY_OPERACIONES o
    JOIN P_DIM_V.UPS_DIM_BOCA_POZO p ON p.Well_Id = o.WELL_ID
    AND o.Evento_Cod = 'PER'
    WHERE o.FECHA >= DATE '{fecha_dinamica_3_meses_atras}'"""
    try:
        conn = get_connection_to_td(TD_HOST, TD_USER, TD_PASS, LOGMECH)
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            return None
        # Formateo simple como lista
        formatted = ", ".join(f"{pozo[0]}" for pozo in rows)
        return formatted
    except Exception as e:
        logger.warning(f"No se pudo cargar contexto dinámico para prompt RAG: {e}")
        return None
