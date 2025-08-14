from __future__ import annotations
from typing import Dict, Any, List, Optional
from functools import lru_cache

import json
import re
import os
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage, HumanMessage
from langchain.schema.output_parser import StrOutputParser
from langgraph.graph import StateGraph, END

load_dotenv()  # Carga OPENAI_API_KEY, etc.

###############################################################################
# 1. Variables para los pasos del Chain of Thought
###############################################################################
PASO_1_DETECCION_INTENCION = """
### Paso 1: Detección de Intención
```
[REASONING]
Analizando la intención del usuario...
- ¿Qué tipo de información busca? (consulta, análisis, reporte, comparación, etc.)
- ¿Es una pregunta directa o requiere cálculos/agregaciones?
- ¿Busca datos específicos o tendencias generales?
- ¿Requiere datos en tiempo real o históricos?
- ¿Necesita un reporte estructurado o respuesta directa?
[/REASONING]

INTENCIÓN DETECTADA: [Describe la intención principal]
HERRAMIENTA RECOMENDADA:

SQLTool: Para consultas de datos históricos, análisis de tendencias, métricas almacenadas
report_tool: Para generación de informes estructurados, partes operativos, resúmenes ejecutivos
corva_tool: Para datos en tiempo real, estado actual de equipos y pozos, operaciones en curso
```
"""

PASO_2_DETECCION_ENTIDADES = """
### Paso 2: Detección de Entidades
```
[REASONING]
Identificando entidades clave en la consulta...
- Nombres de equipos, pozos, ubicaciones
- Fechas, rangos temporales
- Métricas específicas (producción, presión, temperatura, etc.)
- Unidades de medida
- Operadores o compañías
[/REASONING]

ENTIDADES IDENTIFICADAS:
- Equipos: [lista de equipos mencionados]
- Pozos: [lista de pozos mencionados]  
- Fechas/Períodos: [rangos temporales]
- Métricas: [variables a consultar]
- Ubicaciones: [campos, bloques, regiones]
- Otros: [cualquier otra entidad relevante]
```
"""

PASO_3_RERANKING_EXAMPLES = """
### Paso 3: Reranking de Few-shot Examples
```
[REASONING]
Seleccionando los ejemplos más relevantes basado en:
- Similitud de intención con consultas anteriores
- Tipo de entidades involucradas
- Complejidad de la consulta
- Patrón de respuesta esperado
[/REASONING]

EJEMPLOS SIMILARES RANKEADOS:
1. [Ejemplo más relevante + score de similitud]
2. [Segundo ejemplo más relevante + score]
3. [Tercer ejemplo más relevante + score]
```
"""

PASO_4_ENTENDIMIENTO_SOLICITUD = """
### Paso 4: Entendimiento de la Solicitud
```
[REASONING]
Interpretando qué exactamente solicita el usuario...
- ¿Qué datos específicos necesita?
- ¿Qué tipo de análisis requiere?
- ¿Hay condiciones o filtros implícitos?
- ¿Qué formato de respuesta espera?
[/REASONING]

SOLICITUD INTERPRETADA: [Descripción clara y precisa de lo que el usuario quiere]
```
"""

PASO_5_DETECCION_RAMA_EQUIPOS = """
### Paso 5: Detección de Rama - EQUIPOS
```
[REASONING]
Evaluando si la consulta se refiere a equipos...
- ¿Menciona nombres de equipos específicos?
- ¿Se refiere a estado operacional actual?
- ¿Busca información del día/tiempo real?
- ¿Involucra métricas de rendimiento de equipos?
[/REASONING]

RAMA EQUIPOS: [SÍ/NO]
Si SÍ:
- Tipo de datos: TIEMPO REAL / DÍA ACTUAL
- Enfoque: Estado operacional, rendimiento, alertas
- Tablas principales: [equipos, sensores, estados_operacionales]
- Métricas típicas: [eficiencia, disponibilidad, producción_diaria]
```
"""

PASO_6_DETECCION_RAMA_POZOS = """
### Paso 6: Detección de Rama - POZOS  
```
[REASONING]
Evaluando si la consulta se refiere a pozos...
- ¿Menciona nombres de pozos específicos?
- ¿Busca datos históricos de producción?
- ¿Involucra análisis de tendencias temporales?
- ¿Se refiere a métricas geológicas o de producción?
[/REASONING]

RAMA POZOS: [SÍ/NO]
Si SÍ:
- Tipo de datos: HISTÓRICOS / TENDENCIAS
- Enfoque: Producción, reservas, análisis temporal
- Tablas principales: [pozos, produccion_historica, reservas]
- Métricas típicas: [barril_diario, presión, caudal, acumulado]
```
"""

# Variable para process_issues (Paso 7)
PASO_7_RESPUESTA_ESTRUCTURADA = """
### Paso 7: Respuesta Estructurada para Text-to-SQL

Basado en el análisis anterior, genero la siguiente estructura para el agente text-to-sql:

```json
{{
  "query_type": "[equipos|pozos|mixto]",
  "intent": "[consulta|análisis|reporte|comparación]",
  "entities": {{
    "equipos": ["lista_equipos"],
    "pozos": ["lista_pozos"],
    "fechas": ["rango_temporal"],
    "metricas": ["variables_solicitadas"],
    "ubicaciones": ["campos_bloques"]
  }},
  "data_context": {{
    "temporal_scope": "[real_time|daily|historical|trend_analysis]",
    "primary_tables": ["tabla1", "tabla2", "tabla3"],
    "join_requirements": ["relaciones_necesarias"],
    "aggregation_needed": "[sum|avg|count|max|min|none]"
  }},
  "filters": {{
    "time_range": "condición_temporal",
    "equipment_status": "condición_estado",
    "location": "condición_ubicación",
    "custom": ["otros_filtros"]
  }},
  "output_requirements": {{
    "format": "[table|chart|summary|detailed]",
    "grouping": ["campos_agrupación"],
    "sorting": ["campos_ordenamiento"],
    "limit": "número_registros"
  }},
  "complexity_score": "[1-5]",
  "confidence_level": "[alta|media|baja]",
  "clarification_needed": ["aspectos_que_requieren_aclaración"]
}}
```
"""

###############################################################################
# 2. Diccionarios de entidades y intenciones
###############################################################################

ENTIDADES_PETROLERAS = {
    "pozos": [
        "LajE-10", "LCav-805", "Ch.G-453", "LCav-883", "LajE-4", "LajE-54", "LLL-1990", 
        "LLL-607", "LCav.x-9", "YPF.Nq.LajE-10(h)", "YPF.Nq.LCav-805(h)", "YPF.Nq.LCav-883(h)",
        "YPF.Nq.LajE-4(h)", "YPF.Nq.LLL-1798(h)", "YPF.Nq.LLL-1794(h)", "YPF.Md.ECP.x-3",
        "YPF.Md.NCF-90", "YPF.Md.NLCa-127", "LACh-331", "LACh-391", "CnE-630", "B-519",
        "LACH-456", "ECP.x-3"
    ],
    "areas_yacimientos": [
        "GUADAL", "CN-IV", "SANTA CRUZ II - FRACCION B", "CERRO MOLLAR OESTE",
        "AGUADA DEL CHIVATO-AGUADA BOCAREY", "CERRO DOÑA JUANA", "RESTINGA ALI",
        "CHULENGO", "CAYELLI", "MARIA INES", "CAÑADON LEON", "LOMA LA LATA",
        "RIO NEUQUEN", "LOMA CAMPANA", "LLANCANELO", "EL OREJANO", "BANDURRIA"
    ],
    "cuencas": [
        "NEUQUINA", "COSTA AF.ARGENTINA", "GOLFO SAN JORGE", "AUSTRAL"
    ],
    "equipos": [
        "DLS-168", "DLS-188", "F35", "PETREX-30", "TACK-02", "NoKdK", "dls-167", "dls-168"
    ],
    "formaciones_geologicas": [
        "GRUPO NEUQUEN", "RAYOSO", "CENTENARIO SUPERIOR", "CENTENARIO INFERIOR",
        "MULICHINCO", "QUINTUCO", "VACA MUERTA"
    ],
    "fases_perforacion": [
        "GUIA", "INTERMEDIA", "AISLACION", "SEGUNDA", "PRIMARIA"
    ],
    "tipos_profundidad": [
        "TVD", "MD", "KOP", "LP", "Profundidad_Programada_Tvd_Num", "Profundidad_Programada_Tmd_Num",
        "MD_HASTA", "MD_DESDE", "PROFUNDIDAD_VERTICAL"
    ],
    "materiales": [
        "GAS OIL", "BARITINA", "CARGAS SOLIDAS", "CARGAS LIQUIDAS", "LODOS", "CEMENTO"
    ],
    "tipos_lodo": [
        "BASE OIL", "BASE AGUA", "DENSIDAD", "VISCOSIDAD", "PH"
    ],
    "tiempos_operaciones": [
        "NPT", "NPTA", "NPTP", "PNE", "HORAS", "DIAS"
    ],
    "personal": [
        "COMPANY MAN", "SUPERVISOR", "Supervisor_Name_1", "Supervisor_Name_2"
    ],
    "codigos_evento": [
        "PER", "TER", "REP", "INW"
    ],
    "coordenadas": [
        "Coordenada_Geografica_Latitud_Meas", "Coordenada_Geografica_Longitud_Meas"
    ],
    "problemas_fallas": [
        "PERDIDA DE CIRCULACION", "INFLUJO DE POZO", "PROBLEMA DE POZO", "EQUIPO DE TORRE",
        "COMPAÑIA DE SERVICIO", "CLIMA / FENOMENOS NATURALES", "EXTERNOS / GREMIALES"
    ],
    "parametros_perforacion": [
        "ROP", "WOB_AVG", "RPM_AVG", "FLOWRATE", "BUR", "TURN", "DROP", "ECD"
    ],
    "equipamiento_seguridad": [
        "BOP", "1ER_BARRERA", "2DA_BARRERA", "DOBLE_BARRERA"
    ]
}

INTENCIONES_PETROLERAS = {
    "consulta_pozos": [
        "buscar pozos por profundidad",
        "obtener pozos con mayor TVD/MD",
        "listar pozos por área",
        "encontrar pozos cercanos por distancia",
        "identificar pozos activos",
        "buscar pozos perforados en período específico"
    ],
    "analisis_profundidad": [
        "consultar profundidad vertical (TVD)",
        "consultar profundidad medida (MD)", 
        "obtener profundidad de formaciones",
        "identificar KOP (Kick Off Point)",
        "identificar LP (Landing Point)",
        "consultar profundidad de fases"
    ],
    "gestion_equipos": [
        "identificar equipos activos",
        "buscar company man por equipo",
        "obtener supervisor de equipo",
        "consultar equipos por actividad",
        "calcular costo promedio de equipo",
        "obtener progreso de perforación por equipo"
    ],
    "analisis_npt": [
        "calcular NPT total",
        "identificar principal causa de NPT",
        "analizar NPT por período",
        "calcular costo de NPT",
        "desglosar NPT por categorías",
        "comparar NPT entre pozos"
    ],
    "analisis_problemas": [
        "identificar pérdidas de circulación",
        "buscar influjos de pozo",
        "analizar fallas por pozo",
        "listar problemas por período",
        "categorizar tipos de fallas"
    ],
    "analisis_rendimiento": [
        "calcular ROP promedio",
        "analizar performance de trépanos",
        "obtener velocidad de perforación equivalente (VPE)",
        "evaluar rendimiento por fase",
        "comparar performance entre pozos"
    ],
    "gestion_materiales": [
        "consultar volumen de materiales utilizados",
        "calcular cantidad de baritina/gas oil",
        "analizar inventario de materiales",
        "obtener volumen perdido a formación"
    ],
    "analisis_lodos": [
        "obtener curva de lodos",
        "generar reporte de lodos base oil/agua",
        "consultar densidad equivalente de perforación",
        "analizar propiedades de lodos"
    ],
    "consultas_temporales": [
        "buscar actividades por fecha",
        "calcular duración de operaciones",
        "obtener última actividad",
        "analizar tendencias temporales",
        "consultar días de ejecución"
    ],
    "analisis_formaciones": [
        "obtener profundidad de formaciones específicas",
        "consultar tope de formaciones",
        "analizar datos de formación",
        "mapear estructura geológica"
    ],
    "gestion_seguridad": [
        "verificar instalación de BOP",
        "consultar fecha de pruebas BOP",
        "obtener estado de barreras",
        "analizar novedades de seguridad",
        "calcular días desde última prueba"
    ],
    "analisis_costos": [
        "calcular costo promedio de equipos",
        "analizar costos por actividad",
        "obtener costo neto de NPT",
        "comparar costos entre operaciones"
    ],
    "analisis_direccional": [
        "consultar BUR promedio",
        "analizar cambio de dirección",
        "obtener inclinación",
        "evaluar perforación direccional"
    ],
    "generacion_reportes": [
        "generar parte operativo",
        "crear reporte de pozo",
        "obtener resumen operacional",
        "generar análisis comparativo"
    ],
    "consultas_geograficas": [
        "calcular distancia entre pozos",
        "buscar pozos en radio específico",
        "obtener coordenadas de pozos",
        "análisis de proximidad"
    ]
}


@lru_cache(maxsize=1)
def get_compiled_critic_prompt_v3() -> str:
    """
    Prompt simplificado sin bloques de código que causan problemas con LangChain
    """
    return """# Sistema: Agente de Re-ranking de Ejemplos

Eres un especialista en seleccionar los mejores ejemplos few-shot para consultas de petróleo y gas.

## Tu Tarea

1. Analiza la consulta del usuario para entender qué tipo de información busca
2. Evalúa si está relacionada con operaciones petroleras (equipos, pozos, perforación, producción, etc.)
3. Selecciona los 3-5 ejemplos MÁS RELEVANTES de la lista de ejemplos disponibles

## Entidades Petroleras Relevantes
- Equipos: DLS-168, DLS-188, F35, PETREX-30, dls-167, etc.
- Pozos: LajE-10, LCav-805, Ch.G-453, LCav-883, LajE-54, YPF.Nq.LCav-415(h), etc.
- Áreas: Vaca Muerta, Loma La Lata, Aguada del Chañar, etc.
- Operaciones: perforación, producción, NPT, ROP, profundidad, etc.

## Criterios de Selección
- Similitud temática: ¿El ejemplo trata el mismo tipo de consulta?
- Entidades comunes: ¿Comparte equipos, pozos o ubicaciones?
- Tipo de análisis: ¿Busca datos similares (costos, tiempos, profundidad, etc.)?
- Complejidad: Priorizar ejemplos de complejidad similar

## Formato de Respuesta OBLIGATORIO

SIEMPRE responde ÚNICAMENTE con un JSON en este formato exacto:

{{"reasoning": "Análisis de por qué esta consulta es relevante y qué ejemplos son más útiles", "success": true, "critique": "", "relevant": ["ejemplo 1", "ejemplo 3", "ejemplo 7"], "why_relevant": "Explicación de por qué estos ejemplos específicos son los más útiles"}}

## Reglas Importantes

1. Si la consulta NO es sobre petróleo/gas: "success": false y explica en "critique"
2. Si la consulta SÍ es relevante: "success": true y lista 3-5 números de ejemplo
3. El campo "relevant" debe contener SOLO números como "ejemplo 1", "ejemplo 2", etc.
4. NUNCA devuelvas categorías como "pozos" o "equipos" en el campo "relevant"

## Ejemplos de Respuesta Correcta

### Para consulta sobre equipos activos:
{{"reasoning": "Consulta sobre equipos activos en perforación. Busco ejemplos que traten sobre estado de equipos, operaciones actuales y listados.", "success": true, "critique": "", "relevant": ["ejemplo 1", "ejemplo 4", "ejemplo 12"], "why_relevant": "Ejemplo 1 trata equipos activos, ejemplo 4 sobre operaciones de perforación, ejemplo 12 sobre listados de equipos"}}

### Para consulta no relacionada:
{{"reasoning": "Consulta sobre cocina no está relacionada con operaciones petroleras", "success": false, "critique": "La consulta no se refiere a equipos, pozos, perforación u operaciones de petróleo y gas", "relevant": [], "why_relevant": ""}}

Responde SOLO con el JSON, sin texto adicional."""


# @lru_cache(maxsize=1)
# def get_compiled_critic_prompt() -> str:
#     """Versión simplificada para debugging"""
#     return """
# Analiza la consulta del usuario y determina si está relacionada con operaciones petroleras.

# Criterios:
# - SUCCESS = TRUE: Si menciona equipos, pozos, Vaca Muerta, YPF, perforación, producción
# - SUCCESS = FALSE: Si es sobre otros temas no relacionados con petróleo/gas

# Responde SOLO con este JSON (sin markdown ni bloques de código):

# {{ "reasoning": "tu análisis en 1-2 oraciones", "success": true, "recommended_tool": "SQLTool", "critique": "" }}
# """


###############################################################################
# 4. Prompt mejorado con cache
###############################################################################

critic_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", get_compiled_critic_prompt_v3()),
        ("user", "Analiza esta consultas: {task_context}\n\n Aqui los ejemplos Few-shot:\n{few_shot_examples}")
    ],
)

###############################################################################
# 5. LLM + parser  (patrón prompt → llm → StrOutputParser)
###############################################################################
from src.pywo_aux_func import llm_gpt4o as llm

parser = StrOutputParser()  # Devuelve texto plano

critic_chain = critic_prompt | llm | parser

###############################################################################
# 6. Definición de estado LangGraph mejorada
###############################################################################

# Contendrá:
#   "task_context": str   → texto con inventario, tarea, etc.
#   "messages": List[BaseMessage] (historial)
#   "output": dict        → JSON evaluador cuando esté listo
#   "few_shot_examples": str → ejemplos few-shot (renombrado desde process_issues)
#   "cot_analysis": dict  → análisis CoT extraído
CriticState = Dict[str, Any]

###############################################################################
# 7. Debug mejorado
###############################################################################


def debug_cot_response(ai_response: str, show_full=False):
    """
    Función mejorada para hacer debug del razonamiento CoT
    """
    print("\n" + "🧠 DEBUGGING CoT REASONING ".center(80, "="))
    
    if show_full:
        print("\n📄 RESPUESTA COMPLETA:")
        print("-" * 50)
        print(ai_response[:2000] + "..." if len(ai_response) > 2000 else ai_response)
    
    # Extraer solo las partes del reasoning - CAMBIADO: [REASONING] en lugar de <reasoning>
    reasoning_pattern = re.compile(r'\[REASONING\](.*?)\[/REASONING\]', re.DOTALL | re.IGNORECASE)
    reasoning_blocks = reasoning_pattern.findall(ai_response)
    
    if reasoning_blocks:
        print(f"\n🔍 BLOQUES DE RAZONAMIENTO ENCONTRADOS ({len(reasoning_blocks)}):")
        print("-" * 50)
        for i, block in enumerate(reasoning_blocks, 1):
            print(f"\n[Bloque {i}]")
            print(block.strip()[:300] + "..." if len(block.strip()) > 300 else block.strip())
    else:
        print("\n⚠️  No se encontraron bloques de razonamiento [REASONING]")
    
    # Buscar secciones específicas
    sections = ['INTENCIÓN DETECTADA', 'ENTIDADES IDENTIFICADAS', 'RAMA EQUIPOS', 'RAMA POZOS']
    print(f"\n📊 SECCIONES CoT DETECTADAS:")
    print("-" * 50)
    
    for section in sections:
        if section in ai_response:
            print(f"✅ {section}")
        else:
            print(f"❌ {section}")
    
    print("\n" + "="*80)


###############################################################################
# 8. Nodo principal mejorado
###############################################################################

JSON_REGEX = re.compile(r"\{[\s\S]*\}")

def run_critic(state: CriticState) -> CriticState:
    """
    Invoca la chain simplificada para re-ranking de ejemplos
    """
    messages: List = state.get("messages", [])
    task_context: str = state["task_context"]
    few_shot_examples: str = state.get("few_shot_examples", "")

    print("\n" + "🧠 INICIANDO CRITIC RE-RANKING ".center(80, "="))
    print(f"📝 INPUT: {task_context[:150]}...")
    
    try:
        # Llamada al LLM con prompt simplificado
        ai_response: str = critic_chain.invoke({
            "task_context": task_context,
            "few_shot_examples": few_shot_examples,
            "reasoning": "placeholder"
        })
        
        print(f"\n📋 RESPUESTA DEL CRITIC:")
        print(f"   Longitud: {len(ai_response)} caracteres")
        print(f"   Preview: {ai_response[:200]}...")
        
        ai_message = HumanMessage(content=ai_response)
        
        new_state: CriticState = {
            "messages": messages + [ai_message],
            "task_context": task_context,
            "few_shot_examples": few_shot_examples
        }

        # Extraer el JSON final
        output_json = extract_final_json(ai_response)
        
        if output_json and validate_critic_json(output_json):
            new_state["output"] = output_json
            print(f"\n✅ CRITIC EXITOSO:")
            print(f"   Success: {output_json.get('success')}")
            print(f"   Relevant: {output_json.get('relevant', [])}")
            if not output_json.get('success'):
                print(f"   Critique: {output_json.get('critique')}")
        else:
            # Fallback mejorado que INTENTA generar números de ejemplo
            print(f"\n⚠️ APLICANDO FALLBACK INTELIGENTE")
            
            # Analizar si la consulta parece válida
            text_to_analyze = task_context.lower()
            
            # Entidades petroleras clave
            petroleum_entities = [
                'dls', 'f35', 'petrex', 'lcav', 'laje', 'equipo', 'pozo', 'well',
                'rig', 'perforación', 'drilling', 'vaca muerta', 'profundidad',
                'npt', 'rop', 'supervisor', 'company man', 'baritina', 'lodo'
            ]
            
            # Palabras clave de operaciones
            operation_keywords = [
                'activo', 'active', 'perforación', 'drilling', 'producción',
                'production', 'costo', 'cost', 'tiempo', 'time', 'profundidad',
                'depth', 'listado', 'list', 'equipos', 'pozos'
            ]
            
            # Contar coincidencias
            entity_matches = sum(1 for entity in petroleum_entities if entity in text_to_analyze)
            operation_matches = sum(1 for op in operation_keywords if op in text_to_analyze)
            total_score = entity_matches + operation_matches
            
            is_petroleum_related = total_score >= 2
            
            if is_petroleum_related:
                # GENERAR números de ejemplo basado en el tipo de consulta
                relevant_examples = []
                
                if any(word in text_to_analyze for word in ['equipo', 'rig', 'activo', 'active']):
                    relevant_examples.extend(['ejemplo 1', 'ejemplo 2', 'ejemplo 4'])
                
                if any(word in text_to_analyze for word in ['pozo', 'well', 'profundidad', 'depth']):
                    relevant_examples.extend(['ejemplo 3', 'ejemplo 5', 'ejemplo 6'])
                
                if any(word in text_to_analyze for word in ['costo', 'cost', 'tiempo', 'time']):
                    relevant_examples.extend(['ejemplo 7', 'ejemplo 8'])
                
                if any(word in text_to_analyze for word in ['npt', 'problema', 'falla']):
                    relevant_examples.extend(['ejemplo 9', 'ejemplo 10'])
                
                # Remover duplicados y limitar a 5
                relevant_examples = list(dict.fromkeys(relevant_examples))[:5]
                
                # Si no se encontraron específicos, usar algunos generales
                if not relevant_examples:
                    relevant_examples = ['ejemplo 1', 'ejemplo 2', 'ejemplo 3']
                
                fallback_output = {
                    "reasoning": f"Fallback inteligente: Detectadas {entity_matches} entidades petroleras y {operation_matches} operaciones. Seleccionando ejemplos relevantes basado en contexto.",
                    "success": True,
                    "critique": "",
                    "relevant": relevant_examples,
                    "why_relevant": "Ejemplos seleccionados automáticamente basado en análisis de entidades y operaciones detectadas",
                    "fallback_applied": True,
                    "confidence_score": total_score
                }
            else:
                # Consulta no relacionada con petróleo
                fallback_output = {
                    "reasoning": f"Consulta no relacionada con operaciones petroleras (score: {total_score})",
                    "success": False,
                    "critique": "La consulta no parece estar relacionada con equipos, pozos, perforación u operaciones de petróleo y gas",
                    "relevant": [],
                    "why_relevant": "",
                    "fallback_applied": True,
                    "confidence_score": total_score
                }
            
            new_state["output"] = fallback_output
            print(f"   Fallback Success: {fallback_output.get('success')}")
            print(f"   Fallback Relevant: {fallback_output.get('relevant', [])}")
            print(f"   Confidence Score: {fallback_output.get('confidence_score')}")
            
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        new_state = create_error_fallback(state, str(e))

    print("=" * 80)
    return new_state

###############################################################################
# 9. Funciones auxiliares mejoradas
###############################################################################


def extract_cot_sections(ai_response: str) -> Dict[str, Any]:
    """
    Extrae las secciones específicas del análisis CoT mejorado
    """
    sections = {}
    
    # Extraer bloques de reasoning - CAMBIADO: [REASONING] en lugar de <reasoning>
    reasoning_pattern = re.compile(r'\[REASONING\](.*?)\[/REASONING\]', re.DOTALL | re.IGNORECASE)
    sections['reasoning_blocks'] = reasoning_pattern.findall(ai_response)
    
    # Extraer secciones específicas con patrones mejorados
    patterns = {
        'intencion': r'INTENCIÓN DETECTADA:\s*(.*?)(?=\n\S|\n### |\n```|\Z)',
        'herramienta_recomendada': r'HERRAMIENTA RECOMENDADA:(.*?)(?=\n### |\n```|\Z)',  # NUEVO
        'entidades': r'ENTIDADES IDENTIFICADAS:(.*?)(?=\n### |\n```|\Z)',
        'ejemplos_rankeados': r'EJEMPLOS SIMILARES RANKEADOS:(.*?)(?=\n### |\n```|\Z)',
        'solicitud': r'SOLICITUD INTERPRETADA:\s*(.*?)(?=\n### |\n```|\Z)',
        'rama_equipos': r'RAMA EQUIPOS:\s*(.*?)(?=\n### |\n```|\Z)', 
        'rama_pozos': r'RAMA POZOS:\s*(.*?)(?=\n### |\n```|\Z)'
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, ai_response, re.DOTALL | re.IGNORECASE)
        sections[key] = match.group(1).strip() if match else ""
    
    return sections

def display_cot_analysis(cot_analysis: Dict[str, Any]):
    """
    Muestra el análisis CoT de forma organizada y mejorada
    """
    print("\n🔍 ANÁLISIS CoT DETECTADO:")
    print("-" * 50)
    
    # Mostrar reasoning blocks
    for i, reasoning in enumerate(cot_analysis.get('reasoning_blocks', []), 1):
        truncated = reasoning.strip()[:200] + "..." if len(reasoning.strip()) > 200 else reasoning.strip()
        print(f"\n💭 Razonamiento {i}: {truncated}")
    
    # Mostrar secciones principales
    section_icons = {
        'intencion': '🎯',
        'herramienta_recomendada': '🔧',  # NUEVO ICONO
        'entidades': '🏷️',
        'ejemplos_rankeados': '📚',
        'solicitud': '💡',
        'rama_equipos': '⚙️',
        'rama_pozos': '🛢️'
    }
    
    for key, content in cot_analysis.items():
        if key != 'reasoning_blocks' and content:
            icon = section_icons.get(key, '📋')
            truncated = content[:150] + "..." if len(content) > 150 else content
            print(f"\n{icon} {key.upper()}: {truncated}")

def extract_final_json(ai_response: str) -> Optional[Dict[str, Any]]:
    """
    Extractor de JSON mejorado que maneja diferentes formatos
    """
    import json
    import re
    
    # Remover bloques de código markdown si existen
    cleaned_response = re.sub(r'```json\s*', '', ai_response)
    cleaned_response = re.sub(r'```\s*', '', cleaned_response)
    
    # Intentar encontrar JSON válido
    json_patterns = [
        r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',  # Patrón original
        r'\{[\s\S]*\}',                      # Más permisivo
    ]
    
    for pattern in json_patterns:
        json_matches = re.findall(pattern, cleaned_response, re.DOTALL)
        
        # Probar cada match encontrado (empezando por el último)
        for json_str in reversed(json_matches):
            try:
                parsed = json.loads(json_str)
                
                # Verificar que tenga estructura básica esperada
                if isinstance(parsed, dict) and "reasoning" in parsed and "success" in parsed:
                    print(f"🔍 JSON EXTRACTION - ✅ JSON válido extraído")
                    return parsed
                    
            except json.JSONDecodeError:
                continue
    
    print(f"🔍 JSON EXTRACTION - ❌ No se pudo extraer JSON válido")
    print(f"🔍 Response preview: {ai_response[:300]}...")
    return None

def validate_critic_json(output_json: Dict[str, Any]) -> bool:
    """
    Validación simplificada enfocada en los campos críticos
    """
    if not isinstance(output_json, dict):
        print(f"🔍 JSON VALIDATION - No es dict: {type(output_json)}")
        return False
    
    # Campos mínimos requeridos
    required_fields = ["reasoning", "success"]
    missing_fields = [field for field in required_fields if field not in output_json]
    
    if missing_fields:
        print(f"🔍 JSON VALIDATION - Campos faltantes: {missing_fields}")
        return False
    
    # Validar tipos
    if not isinstance(output_json.get("success"), bool):
        print(f"🔍 JSON VALIDATION - 'success' no es bool: {type(output_json.get('success'))}")
        return False
    
    if not isinstance(output_json.get("reasoning"), str) or not output_json.get("reasoning").strip():
        print(f"🔍 JSON VALIDATION - 'reasoning' vacío o inválido")
        return False
    
    # Si success=true, debe tener 'relevant'
    if output_json.get("success") and "relevant" not in output_json:
        print(f"🔍 JSON VALIDATION - Success=true pero sin 'relevant'")
        return False
    
    # Validar que 'relevant' contenga números de ejemplo si existe
    if "relevant" in output_json:
        relevant = output_json["relevant"]
        if not isinstance(relevant, list):
            print(f"🔍 JSON VALIDATION - 'relevant' no es lista: {type(relevant)}")
            return False
        
        # Verificar que son números de ejemplo, no categorías
        if relevant:  # Si no está vacío
            categorias_invalidas = ['pozos', 'equipos', 'personal', 'consulta_pozos', 'analisis_']
            tiene_categorias = any(any(cat in str(item).lower() for cat in categorias_invalidas) for item in relevant)
            
            if tiene_categorias:
                print(f"🔍 JSON VALIDATION - 'relevant' contiene categorías en lugar de números: {relevant[:3]}")
                return False
    
    print(f"🔍 JSON VALIDATION - ✅ JSON válido con campos: {list(output_json.keys())}")
    return True

def make_enhanced_fallback_decision(task_context: str, cot_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Toma una decisión de fallback mejorada basada en el análisis CoT y las entidades definidas
    """
    text_to_analyze = (task_context + " " + str(cot_analysis)).lower()
    
    # Verificar entidades petroleras usando nuestros diccionarios
    found_entities = {}
    confidence_score = 0
    
    for category, entities in ENTIDADES_PETROLERAS.items():
        found_in_category = []
        for entity in entities:
            if entity.lower() in text_to_analyze:
                found_in_category.append(entity)
                confidence_score += 1
        
        if found_in_category:
            found_entities[category] = found_in_category
    
    # Verificar intenciones
    found_intentions = {}
    for category, intentions in INTENCIONES_PETROLERAS.items():
        found_in_category = []
        for intention in intentions:
            # Buscar palabras clave de la intención
            intention_words = intention.lower().split()
            if any(word in text_to_analyze for word in intention_words):
                found_in_category.append(intention)
                confidence_score += 0.5
        
        if found_in_category:
            found_intentions[category] = found_in_category
    # Determinar herramienta recomendada
    recommended_tool = "TEXT_TO_SQL"  # Por defecto
    if any(word in text_to_analyze for word in ["tiempo real", "actual", "hoy", "corva", "ahora"]):
        recommended_tool = "CORVA_API"
    elif any(word in text_to_analyze for word in ["reporte", "informe", "parte operativo"]):
        recommended_tool = "REPORTES"
    
    # Decisión basada en análisis CoT si está disponible
    cot_suggests_valid = False
    if cot_analysis.get('rama_equipos') or cot_analysis.get('rama_pozos'):
        cot_suggests_valid = any([
            'sí' in str(cot_analysis.get('rama_equipos', '')).lower(),
            'sí' in str(cot_analysis.get('rama_pozos', '')).lower(),
            'yes' in str(cot_analysis.get('rama_equipos', '')).lower(),
            'yes' in str(cot_analysis.get('rama_pozos', '')).lower()
        ])
        confidence_score += 2 if cot_suggests_valid else 0
    
    # Decisión final con mayor precisión
    is_valid = confidence_score >= 1 or cot_suggests_valid
    confidence_level = "alta" if confidence_score >= 3 else "media" if confidence_score >= 1 else "baja"
    
    critique = ""
    if not is_valid:
        critique = f"La consulta no parece estar relacionada con el dominio de equipos, pozos u operaciones petroleras. " \
                  f"No se detectaron entidades relevantes (score: {confidence_score}). " \
                  f"¿Podrías reformular tu consulta incluyendo información sobre equipos específicos (como DLS-168, F35), " \
                  f"pozos (como LCav-805, LajE-10) o ubicaciones petroleras (como Vaca Muerta, Loma La Lata)?"
    
    return {
        "reasoning": f"Análisis fallback mejorado: Entidades encontradas: {len(found_entities)} categorías, "
                    f"Intenciones detectadas: {len(found_intentions)} categorías, "
                    f"Score de confianza: {confidence_score}, "
                    f"CoT sugiere válido: {cot_suggests_valid}",
        "success": is_valid,
        "critique": critique,
        "recommended_tool": recommended_tool,  # ✅ AGREGAR ESTA LÍNEA
        "relevant": list(found_entities.keys()) + list(found_intentions.keys()),
        "confidence_level": confidence_level,
        "found_entities": found_entities,
        "found_intentions": found_intentions
    }

def create_error_fallback(state: CriticState, error_msg: str) -> CriticState:
    """
    Crea un estado de fallback en caso de error con números de ejemplo
    """
    return {
        "messages": state.get("messages", []),
        "task_context": state["task_context"],
        "few_shot_examples": state.get("few_shot_examples", ""),
        "output": {
            "reasoning": f"Error en el análisis: {error_msg}. Usando ejemplos generales.",
            "success": True,  # Permitir continuar
            "critique": "",
            "relevant": ["ejemplo 1", "ejemplo 2", "ejemplo 3"],  # ← NÚMEROS en lugar de categorías
            "why_relevant": "Ejemplos generales seleccionados debido a error en el análisis",
            "error": error_msg,
            "fallback_applied": True
        }
    }

###############################################################################
# 10. Condición de finalización
###############################################################################

def is_finished(state: CriticState) -> bool:
    return "output" in state

###############################################################################
# 11. Construcción del grafo
###############################################################################

graph = StateGraph(CriticState)
graph.add_node("critic", run_critic)
graph.set_entry_point("critic")
graph.add_conditional_edges("critic", is_finished, {True: END, False: "critic"})
critic_graph = graph.compile()

###############################################################################
# 12. Ejemplo de uso mejorado
###############################################################################
if __name__ == "__main__":
    # Ejemplo de input relacionado con petróleo/gas
    example_input = """¿Qué equipos están activos en el pozo YPF.Nq.LCav-805(h) hoy?"""
    few_shot_examples = PASO_7_RESPUESTA_ESTRUCTURADA

    init_state: CriticState = {
        "task_context": example_input,
        "few_shot_examples": few_shot_examples,
        "messages": []
    }

    print("🚀 INICIANDO EJEMPLO DE USO")
    print(f"📝 Consulta: {example_input}")
    print("-" * 80)

    final_state = critic_graph.invoke(init_state)
    
    print("\n🎯 RESULTADO FINAL:")
    print(json.dumps(final_state["output"], indent=2, ensure_ascii=False))
    
    if "cot_analysis" in final_state:
        print("\n📊 ANÁLISIS CoT GUARDADO:")
        for key, value in final_state["cot_analysis"].items():
            if value:
                print(f"  {key}: {str(value)[:100]}...")
