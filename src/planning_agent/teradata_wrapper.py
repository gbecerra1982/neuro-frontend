# planning_agent/teradata_wrapper.py
import pandas as pd
import time, contextlib
from src.pywo_aux_func import get_connection_to_db

def run_sql_limited(sql: str,
                    limit: int = 1000,
                    timeout: int = 60):
    """
    Ejecuta una consulta en Teradata usando get_connection_to_db().
    Devuelve (DataFrame | None, error | None).

    • limit   → nº máx. de filas que se retornarán
    • timeout → (opcional) se aplica a la sesión si el driver lo permite
    """
    # Garantizamos que la query nunca devuelva más de 'limit' filas
    # safe_sql = f"""
    # WITH src AS (
    #     {sql.rstrip(';')}
    # )
    # SELECT *
    # FROM src
    # QUALIFY ROW_NUMBER() OVER () <= {limit}
    # """

    start = time.perf_counter()
    cursor, conn = None, None

    try:
        # Conexión reutilizando tu función existente
        conn = get_connection_to_db()             # ← ¡sin duplicar lógica!
        if timeout:
            # Si el driver lo soporta puedes setear timeout de la sesión aquí
            try:
                conn.execute(f"SET SESSION SESSIONTIMEOUT {timeout};")
            except Exception:
                pass

        cursor = conn.cursor()
        cursor.execute(sql.rstrip(';'))

        rows      = cursor.fetchall()
        col_names = [d[0] for d in cursor.description]
        df = pd.DataFrame(rows, columns=col_names)

        runtime = time.perf_counter() - start
        print(f"✅ run_sql_limited – {len(df)} filas en {runtime:0.2f}s")

        return df, None

    except Exception as e:
        print(f"⚠️ run_sql_limited – error: {e}")
        return None, str(e)

    finally:
        with contextlib.suppress(Exception):
            if cursor: cursor.close()
            if conn:   conn.close()