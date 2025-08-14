import psycopg2
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
from src.postgres_integration import get_postgres_connection
import difflib
import uuid

# ===============================
# LANGMEM - MEMORIA DE LARGO PLAZO
# ===============================

def get_user_conversation_history(user_id: Union[int, str, uuid.UUID, None] = None, 
                                session_id: str = None, 
                                last_n_days: int = 30, limit: int = 20) -> List[Dict]:
    """
    Recupera el historial de conversaciones del usuario para contexto de largo plazo
    
    Args:
        user_id: ID del usuario (puede ser int, string UUID, o UUID object)
        session_id: ID de sesión actual (para excluir)
        last_n_days: Últimos N días de conversaciones
        limit: Máximo número de interacciones a recuperar
    
    Returns:
        Lista de interacciones históricas ordenadas por relevancia
    """
    try:
        conn = get_postgres_connection()
        if not conn:
            return []
            
        cursor = conn.cursor()
        
        # Construir query dinámicamente
        base_query = """
        SELECT 
            session_id,
            user_question,
            query_result,
            relevance,
            sql_query,
            interaction_type,
            processing_time_seconds,
            created_at,
            correction_success,
            user_id
        FROM Memory 
        WHERE created_at >= %s
        """
        
        params = [datetime.now() - timedelta(days=last_n_days)]
        
        # FIX: Normalizar user_id a string
        if user_id:
            user_id_str = str(user_id)  # Convierte UUID, int, o string a string
            print('USER_ID dentro de get_user_conversation_history:', user_id_str)
            base_query += " AND session_id IN (SELECT DISTINCT session_id FROM Memory WHERE user_id = %s)"
            params.append(user_id_str)
            
        # Excluir sesión actual
        if session_id:
            session_id_str = str(session_id)
            base_query += " AND session_id != %s"
            params.append(session_id_str)
            
        base_query += """
        ORDER BY 
            CASE WHEN interaction_type = 'sql_workflow_complete' THEN 1 ELSE 2 END,
            created_at DESC
        LIMIT %s
        """
        params.append(limit)
        
        cursor.execute(base_query, params)
        results = cursor.fetchall()
        
        # Convertir a formato útil
        history = []
        for row in results:
            history.append({
                'session_id': row[0],
                'question': row[1],
                'answer': row[2],
                'relevance': row[3],
                'sql_query': row[4],
                'interaction_type': row[5],
                'processing_time': row[6],
                'created_at': row[7],
                'correction_success': row[8],
                'user_id':row[9]
            })
            
        cursor.close()
        conn.close()
        
        print(f"📚 Recuperadas {len(history)} interacciones del historial")
        return history
        
    except Exception as e:
        print(f"❌ Error recuperando historial: {str(e)}")
        return []

def get_relevant_context_for_question(current_question: str, user_id: int = None, 
                                      session_id: str = None, max_context_items: int = 10) -> str:
    """
    Busca contexto relevante en el historial para la pregunta actual, 
    aplicando Top-K adaptativo y priorizando entidades y presentaciones.
    """
    import difflib

    # Patrones y entidades clave
    META_QUESTIONS = [
        "como me llamo", "quién soy", "mi nombre", "quien soy", "quién es el usuario",
        "cómo te llamas", "mi usuario", "resumen", "anteriores", "previas"
    ]
    ENTITY_KEYWORDS = [
        "equipo", "pozo", "zona", "NPT", "perforación", "terminacion", "workover"
    ]

    try:
        # Recuperar historial
        history = get_user_conversation_history(user_id, session_id, last_n_days=7, limit=50)
        print(f"📚 Recuperadas {len(history)} interacciones del historial")
        #for idx, item in enumerate(history, 1):
        #    print(f"🔎 [{idx}] Pregunta: {item.get('question')}\n    Respuesta: {item.get('answer')}\n    SQL: {item.get('sql_query')}\n    Fecha: {item.get('created_at')}\n" + "-"*60)

        if not history:
            return ""

        # 1. Top-K adaptativo
        question_lower = current_question.lower()
        is_meta = any(meta in question_lower for meta in META_QUESTIONS)
        base_top_k = 5
        top_k = min(max_context_items, 10) if is_meta else base_top_k

        # 2. Última presentación de usuario ("me llamo", etc)
        last_intro = None
        for item in reversed(history):
            q = item.get("question", "").lower()
            if "me llamo" in q or "mi nombre es" in q:
                last_intro = item
                break

        # 3. Coincidencia de entidades: 
        entity_matches = []
        for item in history:
            q_text = item.get("question", "").lower()
            if any(entity in question_lower and entity in q_text for entity in ENTITY_KEYWORDS):
                entity_matches.append(item)

        # 4. Similitud (puedes cambiar a embeddings si quieres, aquí difflib por robustez)
        def sim(q1, q2):
            return difflib.SequenceMatcher(None, q1, q2).ratio()

        scored = [
            (sim(current_question, item.get("question", "")), item)
            for item in history
        ]
        scored = sorted(scored, key=lambda x: x[0], reverse=True)
        top_k_similar = [item for score, item in scored[:top_k]]

        # 5. Mezcla y deduplica (prioridad: presentación > entidades > top_k_similar)
        combined = []
        if last_intro:
            combined.append(last_intro)
        combined += [item for item in entity_matches if item not in combined]
        combined += [item for item in top_k_similar if item not in combined]
        combined = combined[:max_context_items]

        # 6. Arma el contexto textual
        context_parts = ["CONTEXTO PREVIO DEL USUARIO:"]
        for i, item in enumerate(combined, 1):
            days_ago = (datetime.now() - item['created_at']).days
            time_ref = f"hace {days_ago} días" if days_ago > 0 else "hoy"
            context_parts.append(f"{i}. ({time_ref}) Pregunta: {item['question']}")
            if item['sql_query']:
                context_parts.append(f"   SQL generada: {item['sql_query'][:100]}...")
            context_parts.append(f"   Respuesta: {item['answer'][:200]}...")
            context_parts.append("")

        context = "\n".join(context_parts)
        print(f"🧠 Contexto relevante encontrado: {len(combined)} elementos")
        #for i, item in enumerate(combined, 1):
            #print(f"🔗 [{i}] Pregunta: {item.get('question')}")
            #print(f"    Respuesta: {item.get('answer')}")
            #print(f"    SQL: {item.get('sql_query')}")
            #print(f"    Fecha: {item.get('created_at')}")
            #print("-" * 60)
        return context

    except Exception as e:
        print(f"❌ Error buscando contexto: {str(e)}")
        return ""

def get_user_preferences_and_patterns(user_id: Union[int, str, uuid.UUID, None] = None, 
                                     session_id: str = None) -> Dict[str, Any]:
    """
    Analiza patrones y preferencias del usuario basado en historial
    """
    try:
        conn = get_postgres_connection()
        if not conn:
            return {}
            
        cursor = conn.cursor()
        
        # Obtener estadísticas del usuario
        stats_query = """
        SELECT 
            COUNT(*) as total_interactions,
            COUNT(CASE WHEN relevance = 'consulta' THEN 1 END) as sql_queries,
            COUNT(CASE WHEN relevance = 'casual' THEN 1 END) as casual_chats,
            AVG(processing_time_seconds) as avg_processing_time,
            COUNT(CASE WHEN correction_success = true THEN 1 END) as successful_corrections,
            COUNT(DISTINCT session_id) as total_sessions
        FROM Memory 
        WHERE created_at >= %s
        """
        
        params = [datetime.now() - timedelta(days=30)]
        
        if user_id:
            # FIX: Normalizar user_id a string
            user_id_str = str(user_id)
            # Buscar sesiones del usuario
            stats_query += " AND session_id LIKE %s"
            params.append(f"%user{user_id_str}%")
        elif session_id:
            session_id_str = str(session_id)
            stats_query += " AND session_id = %s"
            params.append(session_id_str)
            
        cursor.execute(stats_query, params)
        stats = cursor.fetchone()
        
        # Obtener temas más consultados
        topics_query = """
        SELECT 
            interaction_type,
            COUNT(*) as frequency
        FROM Memory 
        WHERE created_at >= %s
        GROUP BY interaction_type
        ORDER BY frequency DESC
        LIMIT 5
        """
        cursor.execute(topics_query, [datetime.now() - timedelta(days=30)])
        topics = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        preferences = {
            'total_interactions': stats[0] if stats else 0,
            'sql_queries': stats[1] if stats else 0,
            'casual_chats': stats[2] if stats else 0,
            'avg_processing_time': float(stats[3]) if stats and stats[3] else 0,
            'successful_corrections': stats[4] if stats else 0,
            'total_sessions': stats[5] if stats else 0,
            'preferred_topics': [{'topic': topic[0], 'frequency': topic[1]} for topic in topics],
            'user_type': 'power_user' if (stats and stats[0] > 50) else 'casual_user'
        }
        
        print(f"👤 Patrones de usuario analizados: {preferences['user_type']}")
        return preferences
        
    except Exception as e:
        print(f"❌ Error analizando patrones: {str(e)}")
        return {}

def create_enhanced_prompt_with_memory(original_prompt: str, current_question: str, 
                                     user_id: int = None, session_id: str = None) -> str:
    """
    Enriquece el prompt original con contexto de memoria de largo plazo
    """
    try:
        # Obtener contexto relevante
        relevant_context = get_relevant_context_for_question(current_question, user_id, session_id)
        
        # Obtener preferencias del usuario
        user_patterns = get_user_preferences_and_patterns(user_id, session_id)
        
        # Construir prompt enriquecido
        enhanced_parts = [original_prompt]
        
        # Agregar contexto histórico si existe
        if relevant_context:
            enhanced_parts.append("\n" + "="*50)
            enhanced_parts.append(relevant_context)
            enhanced_parts.append("="*50)
            
        # Agregar información del usuario si es útil
        if user_patterns and user_patterns.get('total_interactions', 0) > 5:
            user_info = f"\nINFO DEL USUARIO: {user_patterns['user_type']} "
            user_info += f"({user_patterns['total_interactions']} interacciones, "
            user_info += f"{user_patterns['sql_queries']} consultas SQL)"
            
            if user_patterns.get('preferred_topics'):
                top_topic = user_patterns['preferred_topics'][0]
                user_info += f", tema frecuente: {top_topic['topic']}"
                
            enhanced_parts.append(user_info)
            
        # Instrucción para usar el contexto
        if relevant_context:
            enhanced_parts.append("""
# SISTEMA INTELIGENTE DE MEMORIA DE LARGO PLAZO - CoT PROMPT

## ROL Y CONTEXTO
Eres un asistente experto en operaciones de perforación y terminación de YPF, equipado con un sistema avanzado de memoria de largo plazo. Tu misión es proporcionar respuestas contextualizadas, precisas y personalizadas utilizando tanto el conocimiento actual como el historial de interacciones del usuario.

## CADENA DE PENSAMIENTO OBLIGATORIA (CoT)

### PASO 1: ANÁLISIS DE ENTIDADES Y CONTEXTO
**ANTES de responder cualquier pregunta, SIEMPRE ejecuta este análisis:**

```
🔍 DETECCIÓN DE ENTIDADES:
1. Nombres de personas mencionados o implícitos
2. Equipos específicos (perforas, workovers, MASES, pulling)
3. Pozos identificados por nombre o código
4. Zonas geográficas (cuencas, yacimientos, provincias)
5. Fechas y períodos temporales
6. Tipos de consulta SQL implícitos
7. Referencias a consultas anteriores ("como antes", "igual que la vez pasada")
8. Terminología técnica específica del usuario
```

### PASO 2: BÚSQUEDA EN MEMORIA HISTÓRICA
**Ejecutar análisis de contexto histórico:**

```
🧠 RECUPERACIÓN DE MEMORIA:
1. ¿Existe contexto histórico relevante para estas entidades?
   → Usar: get_relevant_context_for_question()
   
2. ¿Qué patrones de uso tiene este usuario?
   → Usar: get_user_preferences_and_patterns()
   
3. ¿Hay consultas SQL similares exitosas anteriores?
   → Revisar: historial de sql_workflow_complete
   
4. ¿El usuario se ha presentado antes con un nombre?
   → Verificar: general_chat_personalized
   
5. ¿Existen correcciones de entidades exitosas previas?
   → Consultar: correction_success = true
```

### PASO 3: CONTEXTUALIZACIÓN INTELIGENTE
**Razonamiento sobre el contexto encontrado:**

```
🎯 APLICACIÓN DE CONTEXTO:
1. ¿La pregunta actual es continuación de una anterior?
   - SI: Referenciar brevemente la consulta previa
   - NO: Proceder como consulta independiente

2. ¿Las entidades detectadas requieren corrección/validación?
   - Equipos/Pozos: Usar listas activas actuales
   - Nombres: Mantener consistencia con presentaciones previas

3. ¿El tipo de usuario requiere personalización?
   - Power User: Respuesta técnica y detallada
   - Casual User: Respuesta simple y clara

4. ¿Existen SQL queries reutilizables?
   - Adaptar consultas exitosas similares
   - Mencionar optimizaciones basadas en historial
```

### PASO 4: GENERACIÓN DE RESPUESTA CONTEXTUALIZADA
**Construir respuesta enriquecida:**

```
📝 COMPOSICIÓN DE RESPUESTA:
1. SALUDO PERSONALIZADO (si aplica):
   - Usar nombre del usuario si se ha presentado
   - Referenciar contexto de la sesión actual
   - Si detectas que el usuario te preguntó por su nombre, busca en el historial si alguna vez te dijo ‘me llamo X’ o algo equivalente, y usa esa información para responder

2. RECONOCIMIENTO DE CONTEXTO (si relevante):
   - "Como consultaste anteriormente sobre [entidad]..."
   - "Siguiendo con tu análisis de [tema]..."

3. RESPUESTA PRINCIPAL:
   - Aplicar personalización según tipo de usuario
   - Integrar conocimiento histórico cuando enriquezca la respuesta
   - Usar terminología consistente con interacciones previas

4. OPTIMIZACIÓN SQL (para consultas de datos):
   - Aprovechar queries exitosas similares
   - Mencionar mejoras basadas en experiencia previa
```

### PASO 5: PERSISTENCIA Y APRENDIZAJE
**Guardar nueva información para futuras interacciones:**

```
💾 GUARDADO INTELIGENTE:
1. Nuevas entidades detectadas
2. Preferencias de formato observadas
3. Éxito/fallo de correcciones realizadas
4. Patrones de consulta identificados
5. Contexto de la interacción completa

→ Usar: save_complete_memory() con interaction_type apropiado
```

## REGLAS DE DETECCIÓN DE ENTIDADES

### NOMBRES DE PERSONAS
- **Frases clave**: "Me llamo...", "Soy...", "Mi nombre es..."
- **Persistencia**: Una vez detectado, usar en interacciones futuras
- **Formato**: Mantener formalidad (usar Sr./Sra. si apropiado)

### EQUIPOS Y POZOS
- **Validación**: Siempre contrastar con listas activas actuales
- **Corrección**: Sugerir nombres similares de listas oficiales
- **Memoria**: Recordar equipos/pozos consultados frecuentemente

### ZONAS GEOGRÁFICAS
- **Jerarquía**: País → Provincia → Departamento → Cuenca → Yacimiento
- **Contexto**: Asociar con operaciones y equipos relevantes

### CONSULTAS SQL
- **Reutilización**: Identificar patrones de consulta similares
- **Optimización**: Sugerir mejoras basadas en experiencia previa
- **Eficiencia**: Evitar regenerar consultas idénticas

## COMPORTAMIENTOS ESPECÍFICOS

### PARA USUARIOS POWER
```
- Mostrar detalles técnicos avanzados
- Referenciar múltiples consultas históricas
- Proporcionar optimizaciones SQL específicas
- Usar terminología técnica especializada
```

### PARA USUARIOS CASUALES
```
- Explicaciones simples y claras
- Contexto mínimo pero útil
- Evitar jerga técnica excesiva
- Enfocar en resultados prácticos
```

### PARA CONSULTAS DE SEGUIMIENTO
```
- Referenciar explícitamente la consulta anterior
- Mostrar evolución o cambios respecto a resultados previos
- Mantener coherencia con análisis anteriores
```

## CASOS ESPECIALES

### REFERENCIAS AMBIGUAS
- "ese pozo", "el equipo anterior" → Usar historial para resolver
- "como la vez pasada" → Buscar y referenciar interacción específica

### CORRECCIONES DE ENTIDADES
- Priorizar nombres de listas oficiales actuales
- Considerar correcciones exitosas previas del usuario
- Explicar cambios cuando sean significativos

### CONSULTAS TEMPORALES
- "equipos activos hoy" → Usar datos actuales + contexto histórico
- "desde la última vez" → Calcular período basado en última consulta

## FORMATO DE RAZONAMIENTO INTERNO

**ESTRUCTURA OBLIGATORIA para logging interno:**
```
[ENTITY_DETECTION] Entidades encontradas: [lista]
[MEMORY_SEARCH] Contexto relevante: [resumen]
[USER_PROFILE] Tipo: [power/casual], Historial: [X interactions]
[CONTEXT_APPLICATION] Estrategia: [explicación]
[RESPONSE_PERSONALIZATION] Adaptaciones: [lista]
```

## LÍMITES Y SALVAGUARDAS

- **NO** inventar información que no esté en memoria o datos actuales
- **NO** hacer suposiciones sobre entidades no confirmadas
- **SIEMPRE** validar nombres de equipos/pozos con listas oficiales
- **VERIFICAR** que el contexto histórico sea realmente relevante
- **MANTENER** confidencialidad entre diferentes usuarios/sesiones

## OBJETIVO FINAL

Proporcionar una experiencia fluida y contextualizada donde el usuario sienta que el sistema "recuerda" y "aprende" de interacciones previas, mejorando continuamente la calidad y personalización de las respuestas.

""")
        
        enhanced_prompt = "\n".join(enhanced_parts)
        
        print(f"🚀 Prompt enriquecido con memoria (longitud: {len(enhanced_prompt)} chars)")
        return enhanced_prompt
        
    except Exception as e:
        print(f"❌ Error creando prompt enriquecido: {str(e)}")
        return original_prompt

# ===============================
# FUNCIONES HELPER PARA INTEGRACIÓN
# ===============================


def extract_user_id_from_session(session_id: str) -> Optional[str]:
    """
    Extrae user_id del session_id si sigue un patrón específico
    Ejemplo: "user123_session_uuid" -> "123"
    O devuelve el session_id completo si no hay patrón
    """
    try:
        if "user" in session_id:
            parts = session_id.split("_")
            for part in parts:
                if part.startswith("user") and part[4:].isdigit():
                    return part[4:]  # Devolver como string, no int
        # Si no hay patrón, devolver el session_id completo como user_id
        return session_id
    except:
        return session_id

def create_user_session_id(user_id: int) -> str:
    """
    Crea un session_id que incluye el user_id para tracking
    """
    import uuid
    return f"user{user_id}_session_{str(uuid.uuid4())}"