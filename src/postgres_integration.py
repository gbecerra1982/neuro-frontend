import psycopg2
import json
from datetime import datetime, timedelta
import uuid
from typing import Dict, Any, Optional, Union  # se usan= 

# ===============================
# CONFIGURACIÓN BASE DE DATOS - DATOS REALES
# ===============================

POSTGRES_CONFIG = {
    'host': 'ydtzdadpgpt001.postgres.database.azure.com',
    'database': 'pywoavatar_dev',
    'user': 'usr_pywoavatar', 
    'password': 'Acceso19052025',
    'port': 5432,
    'sslmode': 'require'
}

def get_postgres_connection():
    """
    Establece conexión con PostgreSQL en Azure
    """
    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        return conn
    except Exception as e:
        print(f"Error conectando a PostgreSQL: {str(e)}")
        return None

# ===============================
# FUNCIONES BÁSICAS DE GUARDADO
# ===============================


def save_complete_memory(state_dict, interaction_type: str = "general", 
                        human_msg_id: Union[str, uuid.UUID, None] = None, 
                        ai_msg_id: Union[str, uuid.UUID, None] = None):
    """
    Función COMPLETA para guardar todo el AgentState en Memory
    
    Args:
        state_dict: Diccionario con el estado del agente
        interaction_type: Tipo de interacción
        human_msg_id: ID del mensaje humano (puede ser UUID o string)
        ai_msg_id: ID del mensaje AI (puede ser UUID o string)
    """
    try:
        conn = get_postgres_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()

        # Extraer todos los datos del estado
        user_id_raw = state_dict.get('user_id', None)
        session_id_raw = state_dict.get('session_id', str(uuid.uuid4()))
        user_question = state_dict.get('question', '')
        relevance = state_dict.get('relevance', '')
        sql_query = state_dict.get('sql_query', '')
        query_result = state_dict.get('query_result', '')
        correction_success = state_dict.get('correction_success', False)
        processing_time = state_dict.get('dt', 0.0)
        lista_equipos = state_dict.get('lista_equipos_activos', [])
        lista_pozos = state_dict.get('lista_pozos_activos_perforacion', [])
        
        # FIX: Normalizar todos los IDs a string para PostgreSQL
        user_id = str(user_id_raw) if user_id_raw is not None else None
        session_id = str(session_id_raw) if session_id_raw is not None else str(uuid.uuid4())
        human_message_id = str(human_msg_id) if human_msg_id is not None else None
        ai_message_id = str(ai_msg_id) if ai_msg_id is not None else None
        
        # Debug: mostrar qué estamos guardando
        print(f"💾 Guardando Memory:")
        print(f"   📝 User ID: {user_id} (original: {type(user_id_raw)} {user_id_raw})")
        print(f"   📝 Session ID: {session_id} (original: {type(session_id_raw)})")
        print(f"   📝 Human Msg ID: {human_message_id}")
        print(f"   📝 AI Msg ID: {ai_message_id}")
        
        # Crear snapshot del estado completo
        agent_snapshot = {
            'sql_error': state_dict.get('sql_error', False),
            'name_validation': state_dict.get('name_validation', False),
            'tipo_consulta': state_dict.get('tipo_consulta', ''),
            'entity': state_dict.get('entity', False),
            'name_correction': state_dict.get('name_correction', False),
            'gral_ans': state_dict.get('gral_ans', ''),
            'interaction_type': interaction_type,
            'timestamp': datetime.now().isoformat()
        }
        
        insert_query = """
        INSERT INTO Memory (
            user_id, session_id, user_question, relevance, sql_query, query_result,
            correction_success, processing_time_seconds, interaction_type,
            human_message_id, ai_message_id, lista_equipos_activos, 
            lista_pozos_activos, agent_state_snapshot, created_at, expires_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """
        
        expires_at = datetime.now() + timedelta(hours=24)
        
        cursor.execute(insert_query, (
            user_id,
            session_id,
            user_question,
            relevance,
            sql_query,
            query_result,
            correction_success,
            processing_time,
            interaction_type,
            human_message_id,
            ai_message_id,
            json.dumps(lista_equipos),
            json.dumps(lista_pozos),
            json.dumps(agent_snapshot),
            datetime.now(),
            expires_at
        ))
        
        memory_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"✅ Memory completa guardada - ID: {memory_id}")
        print(f"   📝 SQL Query: {'✅ Sí' if sql_query else '❌ Vacío'}")
        print(f"   📝 Query Result: {'✅ Sí' if query_result else '❌ Vacío'}")
        print(f"   📝 Relevance: {'✅ Sí' if relevance else '❌ Vacío'}")
        print(f"   📝 User ID: {'✅ Sí' if user_id else '❌ Vacío'}")
        return memory_id
        
    except Exception as e:
        print(f"❌ Error guardando Memory completa: {str(e)}")
        return False

def save_to_memory_simple(session_id: Union[str, uuid.UUID], question: str, response: str, 
                         interaction_type: str = "general", processing_time: float = 0.0):
    """
    Función simplificada para guardar en Memory
    """
    try:
        conn = get_postgres_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        
        # FIX: Normalizar session_id a string
        session_id_str = str(session_id)
        
        insert_query = """
        INSERT INTO Memory (
            session_id, user_question, query_result, interaction_type,
            processing_time_seconds, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id;
        """
        
        cursor.execute(insert_query, (
            session_id_str,
            question,
            response,
            interaction_type,
            processing_time,
            datetime.now()
        ))
        
        memory_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"✅ Guardado en Memory - ID: {memory_id}")
        return memory_id
        
    except Exception as e:
        print(f"❌ Error guardando en Memory: {str(e)}")
        return False

def save_sql_execution_simple(session_id: Union[str, uuid.UUID], question: str, sql_query: str, 
                             success: bool = True, processing_time: float = 0.0):
    """
    Función simplificada para guardar ejecuciones SQL
    """
    try:
        conn = get_postgres_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        
        # FIX: Normalizar session_id a string
        session_id_str = str(session_id)
        
        insert_query = """
        INSERT INTO SQL_Query_Executions (
            session_id, original_question, generated_sql, execution_success,
            processing_time_seconds, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id;
        """
        
        cursor.execute(insert_query, (
            session_id_str,
            question,
            sql_query,
            success,
            processing_time,
            datetime.now()
        ))
        
        execution_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"✅ Guardado SQL execution - ID: {execution_id}")
        return execution_id
        
    except Exception as e:
        print(f"❌ Error guardando SQL execution: {str(e)}")
        return False

def save_sql_error_simple(session_id: Union[str, uuid.UUID], question: str, failed_sql: str, 
                         error_message: str, attempt_number: int = 1):
    """
    Función simplificada para guardar errores SQL
    """
    try:
        conn = get_postgres_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        
        # FIX: Normalizar session_id a string
        session_id_str = str(session_id)
        
        insert_query = """
        INSERT INTO SQL_Execution_Errors (
            session_id, original_question, failed_sql, error_message,
            attempt_number, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id;
        """
        
        cursor.execute(insert_query, (
            session_id_str,
            question,
            failed_sql,
            error_message,
            attempt_number,
            datetime.now()
        ))
        
        error_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"✅ Guardado error SQL - ID: {error_id}")
        return error_id
        
    except Exception as e:
        print(f"❌ Error guardando SQL error: {str(e)}")
        return False

def save_performance_metric_simple(session_id: Union[str, uuid.UUID], function_name: str, 
                                  execution_time: float, success: bool = True):
    """
    Función simplificada para guardar métricas de rendimiento
    """
    try:
        conn = get_postgres_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        
        # FIX: Normalizar session_id a string
        session_id_str = str(session_id)
        
        insert_query = """
        INSERT INTO Performance_Metrics (
            session_id, function_name, execution_time_seconds, success, created_at
        ) VALUES (%s, %s, %s, %s, %s)
        RETURNING id;
        """
        
        cursor.execute(insert_query, (
            session_id_str,
            function_name,
            execution_time,
            success,
            datetime.now()
        ))
        
        metric_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return metric_id
        
    except Exception as e:
        print(f"❌ Error guardando métrica: {str(e)}")
        return False

# ===============================
# FUNCIÓN DE TEST
# ===============================

def test_postgres_connection():
    """
    Test rápido de conexión
    """
    conn = get_postgres_connection()
    if conn:
        print("✅ Conexión PostgreSQL OK")
        conn.close()
        return True
    else:
        print("❌ Error conexión PostgreSQL")
        return False