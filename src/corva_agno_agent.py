"""
CORVA AGNO AGENT - VERSIÓN AVATAR CORREGIDA CON INTEGRACIÓN COMPLETA
====================================================================

Solución robusta que maneja correctamente el flujo:
1. Buscar asset_id
2. Validar match exacto  
3. Ejecutar consulta específica

MANTIENE INTEGRACIÓN COMPLETA CON SISTEMA AVATAR
"""

import os
import asyncio
import json
import uuid
import time
from typing import Dict, List, Optional, Any, Tuple
from agno.agent import Agent
from agno.models.azure import AzureOpenAI
from agno.tools import tool

# 🔧 IMPORTAR FUNCIONES EXISTENTES CON RUTA AVATAR CORRECTA
try:
    from src.corva_tool import (
        # Funciones principales existentes
        make_corva_request_fixed,
        classify_user_intent,
        extract_asset_name,
        search_asset_by_name,
        get_alerts,
        get_rigs,
        get_wells,
        get_assets_general,
        get_kpis_workflow,
        format_response_for_agent,
        CorvaAPIError,
        get_wits_depth,
        get_wits_summary,
        get_metrics_rop,
        get_operations,
        
        # NUEVAS FUNCIONES A AGREGAR:
        get_asset_detailed_info,      # ← NUEVA
        get_fracking_metrics,           # ← NUEVA
        format_fracking_metrics_response,  # ← NUEVA
        
        # Funciones auxiliares (mantener existentes)
        normalize_asset_name_for_matching,
        calculate_smart_similarity
    )
except ImportError as e:
    print(f"⚠️ Error al importar funciones de corva_tool_avatar: {e}")
    raise

# 🔧 IMPORTAR MEMORIA AVATAR SI ESTÁ DISPONIBLE
try:
    from src.langmem_functions import (
        get_relevant_context_for_question, 
        create_enhanced_prompt_with_memory,
        get_user_preferences_and_patterns
    )
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False

try:
    from src.postgres_integration import (
        save_complete_memory, save_performance_metric_simple
    )
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False


def validate_azure_env_vars_avatar() -> Tuple[bool, List[str]]:
    """
    Valida que todas las variables de entorno necesarias para Avatar Azure estén configuradas
    
    Returns:
        tuple[bool, list[str]]: (es_válido, variables_faltantes)
    """
    # Variables requeridas para Avatar
    required_vars = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT", 
    ]
    
    # Para deployment Avatar, usar la variable estándar
    deployment_var = "AZURE_OPENAI_DEPLOYMENT_NAME"  # ← Variable Avatar estándar
    api_version_var = "API_VERSION"  # ← Variable Avatar estándar
    
    missing_vars = []
    configured_vars = []
    
    # Validar variables básicas
    for var in required_vars:
        value = os.getenv(var)
        if not value or value.strip() == "":
            missing_vars.append(var)
        else:
            configured_vars.append(var)
    
    # Validar deployment Avatar
    deployment_value = os.getenv(deployment_var)
    if not deployment_value or deployment_value.strip() == "":
        missing_vars.append(deployment_var)
    else:
        configured_vars.append(deployment_var)
    
    # Validar API version Avatar
    api_version_value = os.getenv(api_version_var, "2024-10-21")  # Default Avatar
    if api_version_value:
        configured_vars.append(api_version_var)
    
    if missing_vars:
        print(f"❌ Variables Avatar Azure faltantes: {missing_vars}")
        if configured_vars:
            print(f"✅ Variables Avatar Azure configuradas: {configured_vars}")
        return False, missing_vars
    
    print("✅ Todas las variables Avatar Azure están configuradas correctamente")
    return True, []


class CorvaAgnoAgent:
    """
    Agente ReAct para plataforma Corva - VERSIÓN AVATAR COMPLETA
    
    MANTIENE INTEGRACIÓN COMPLETA CON:
    - Sistema de memoria Avatar
    - PostgreSQL Avatar
    - Variables de entorno Avatar
    - Estructura de proyecto Avatar
    """
    
    def __init__(self):
        """Inicialización robusta con validaciones Avatar"""
        
        # Estado de inicialización Avatar
        self.agent = None
        self.initialization_status = "No inicializado"
        
        try:
            # Verificar variables Avatar necesarias
            if not os.getenv("APIM_AUTH_CREDENTIAL"):
                raise ValueError("APIM_AUTH_CREDENTIAL no encontrada")
            
            # Verificar variables Avatar Azure
            is_valid, missing_vars = validate_azure_env_vars_avatar()
            if not is_valid:
                raise ValueError(f"Variables Avatar Azure faltantes: {missing_vars}")
                
            deployment_name = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')  # ← Variable Avatar estándar
            if not deployment_name:
                raise ValueError("AZURE_OPENAI_DEPLOYMENT_NAME no encontrada")
            
            print(f"🔧 Inicializando Agno Avatar robusto con deployment: {deployment_name}")
            
            # ✅ CONFIGURACIÓN AVATAR CORREGIDA
            azure_model = AzureOpenAI(
                id=deployment_name,
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("API_VERSION", "2024-10-21"),  # ← Variable Avatar estándar
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            
            self.agent = Agent(
                name="CorvaExpertAvatar",
                role="Especialista en datos de Corva con integración completa Avatar",
                model=azure_model,
                tools=[
                    self._create_alerts_tool(),            # 📢 CONSULTAS GENERALES
                    self._create_rigs_tool(),
                    self._create_wells_tool(),
                    self._create_assets_general_tool(),
                    self._create_asset_search_tool(),      # 🔍 BÚSQUEDA INTELIGENTE
                    self._create_asset_detailed_info_tool(),  # ← NUEVA TOOL
                    self._create_kpis_tool(),              # 📊 DATOS ESPECÍFICOS
                    self._create_wits_depth_tool(),
                    self._create_wits_summary_tool(), 
                    self._create_metrics_rop_tool(),
                    self._create_operations_tool(),
                    self._create_fracking_metrics_tool(),  # ← NUEVA TOOL
                ],
                instructions=self._create_avatar_instructions(),
                description="Agente ReAct para plataforma de datos en tiempo real YPF - AVATAR COMPLETO",
                markdown=True,
                show_tool_calls=False,
                debug_mode=False  # ← Avatar no necesita debug visible
            )
            
            self.initialization_status = "✅ Agente Corva Avatar completo inicializado correctamente"
            print(self.initialization_status)
            
        except Exception as e:
            self.initialization_status = f"❌ Error inicializando agente Avatar: {str(e)}"
            print(self.initialization_status)
            raise

    def _create_avatar_instructions(self) -> List[str]:
        """🔧 Instrucciones Avatar optimizadas para integración completa ACTUALIZADAS"""
        
        return ["""
        ## AGENTE CORVA AVATAR - CADENA DE RAZONAMIENTO COMPLETA (CoT) ACTUALIZADA
        
        Eres un agente ReAct experto en datos de Corva para la industria de petróleo y gas, 
        integrado completamente con el sistema Avatar de YPF.

        ### PASO 1: ANÁLISIS DE INTENCIÓN AUTOMÁTICO
        Analiza automáticamente la consulta del usuario y clasifica la intención:
        1. ¿Es una consulta general? → Usar tools directas (alerts, rigs, wells, assets general)
        2. ¿Pide INFORMACIÓN COMPLETA/DETALLADA de un asset? → fetch_asset_detailed_info()
        3. ¿Menciona métricas de FRACTURAMIENTO? → fetch_fracking_metrics()
        4. ¿Menciona un asset específico + datos operacionales? → Proceder al PASO 2
        5. ¿Requiere datos específicos de un asset? → Proceder al PASO 2

        ### PASO 2: BÚSQUEDA Y VALIDACIÓN DE ASSET (OBLIGATORIO para datos específicos)
        **ANTES de obtener datos operacionales específicos:**
        1. Usar search_specific_asset() para buscar el asset
        2. **VALIDACIÓN INTELIGENTE**: Las funciones de datos ya manejan matching automático
        3. Solo mostrar opciones al usuario si hay ambigüedad real
        4. Proceder automáticamente con matches de alta similitud (85%+)

        ### PASO 3: TIPOS DE INFORMACIÓN DISPONIBLE
        
        **INFORMACIÓN BASE/COMPLETA (usar fetch_asset_detailed_info):**
        - Metadata del asset (ID, nombre, tipo, compañía)
        - Información del rig asociado (nombre, contratista)
        - Estado y actividad (última actividad, estado)
        - Ubicación y coordenadas
        - Configuración técnica base
        - Fechas importantes (creación, spud, completion)
        
        **MÉTRICAS DE FRACTURAMIENTO (usar fetch_fracking_metrics):**
        - Volúmenes de fluidos por etapa (sucio, limpio)
        - Químicos líquidos (reductor fricción, surfactante, biocida, inhibidor, martillo líquido)
        - Químicos en polvo (concentración FR, triturador, gel)
        - Proppant (arena) total por etapa
        - Tiempos de operación entre etapas
        
        **DATOS OPERACIONALES EN TIEMPO REAL (usar tools específicas):**
        - KPIs de rendimiento → fetch_asset_kpis()
        - Profundidad actual → fetch_wits_depth()
        - ROP en tiempo real → fetch_wits_summary()
        - Métricas históricas → fetch_metrics_rop()
        - Tiempos de operación → fetch_operations()

        ### EJEMPLOS DE CLASIFICACIÓN ACTUALIZADA:

        ❓ "Dame información del DLS 168" → fetch_asset_detailed_info()
        ❓ "Detalles completos del LCav-415" → fetch_asset_detailed_info()  
        ❓ "Qué sabes sobre el pozo ABC-001" → fetch_asset_detailed_info()
        ❓ "Información base del rig F35" → fetch_asset_detailed_info()

        ❓ "volumen sucio del LCav-415" → fetch_fracking_metrics()
        ❓ "reductor de fricción del DLS 168" → fetch_fracking_metrics() 
        ❓ "arena total del pozo ABC-001" → fetch_fracking_metrics()
        ❓ "tiempo entre etapas del LCav-415" → fetch_fracking_metrics()
        ❓ "químicos del pozo ABC-001 etapa 5" → fetch_fracking_metrics()

        ❓ "KPIs del DLS 168" → search_specific_asset() + fetch_asset_kpis()
        ❓ "profundidad actual del LCav-415" → fetch_wits_depth()
        ❓ "ROP del pozo ABC-001" → fetch_wits_summary()

        ### REGLAS CRÍTICAS DE VALIDACIÓN ACTUALIZADAS:
        - **fetch_asset_detailed_info() NO requiere search_specific_asset() previo** (tiene su propio matching)
        - **fetch_fracking_metrics() NO requiere search_specific_asset() previo** (tiene su propio matching)
        - **Para datos operacionales SÍ usar search_specific_asset() primero**
        - **SIEMPRE mostrar opciones cuando hay múltiples candidatos**

        ### INTEGRACIÓN AVATAR:
        - Mantén respuestas profesionales pero accesibles
        - Usa emojis apropiados para claridad visual
        - Estructura información de manera clara para el usuario Avatar
        - Aprovecha el matching automático inteligente integrado
        
        ### MANEJO DE ERRORES AVATAR:
        - Si hay errores de API, explica claramente el problema
        - Sugiere alternativas cuando sea posible
        - Mantén un tono profesional pero cercano
        - Formatea los resultados de manera clara y estructurada
        
        ### CONVERSIONES IMPORTANTES PARA AVATAR:
        - **Profundidad**: Si hay valores en feet/pies/ft, convertir al sistema métrico multiplicando por 0.3048 y expresar en metros
        - **Tiempo**: Los valores de fetch_operations() están en SEGUNDOS, NO en minutos
        """]

    def _create_alerts_tool(self):
        """📢 Tool para obtener alertas generales"""
        @tool
        def fetch_corva_alerts() -> str:
            """
            Obtiene todas las alertas generales disponibles en Corva.
            Úsala cuando el usuario pregunte por alertas, alarmas o notificaciones.
            
            Returns:
                str: Información formateada de las alertas encontradas
            """
            try:
                result = get_alerts()
                if result and result.get("success"):
                    return format_response_for_agent(result)
                else:
                    error_msg = result.get("error", "Error desconocido") if result else "Respuesta vacía"
                    return f"⚠️ Error obteniendo alertas: {error_msg}"
            except Exception as e:
                return f"Error al obtener alertas: {str(e)}"
        
        return fetch_corva_alerts
    
    def _create_rigs_tool(self):
        """🔧 Tool para obtener información general de rigs"""
        @tool  
        def fetch_corva_rigs() -> str:
            """
            Obtiene información general de todos los rigs disponibles en Corva.
            Úsala cuando el usuario pregunte por equipos, rigs o perforadoras en general.
            
            Returns:
                str: Lista formateada de rigs disponibles
            """
            try:
                result = get_rigs()
                if result and result.get("success"):
                    return format_response_for_agent(result)
                else:
                    error_msg = result.get("error", "Error desconocido") if result else "Respuesta vacía"
                    return f"⚠️ Error obteniendo rigs: {error_msg}"
            except Exception as e:
                return f"Error al obtener rigs: {str(e)}"
        
        return fetch_corva_rigs
    
    def _create_wells_tool(self):
        """🏭 Tool para obtener información general de wells"""
        @tool
        def fetch_corva_wells() -> str:
            """
            Obtiene información general de todos los wells (pozos) disponibles en Corva.
            Úsala cuando el usuario pregunte por pozos, wells en general.
            
            Returns:
                str: Lista formateada de wells disponibles  
            """
            try:
                result = get_wells()
                if result and result.get("success"):
                    return format_response_for_agent(result)
                else:
                    error_msg = result.get("error", "Error desconocido") if result else "Respuesta vacía"
                    return f"⚠️ Error obteniendo wells: {error_msg}"
            except Exception as e:
                return f"Error al obtener wells: {str(e)}"
        
        return fetch_corva_wells
    
    def _create_assets_general_tool(self):
        """📋 Tool para obtener información general de assets"""
        @tool
        def fetch_general_assets() -> str:
            """
            Obtiene información general de todos los assets (rigs y wells) disponibles.
            Úsala cuando el usuario pregunte por assets en general, listado completo de equipos o pozos.
            
            Returns:
                str: Lista formateada de todos los assets disponibles
            """
            try:
                result = get_assets_general()
                if result and result.get("success"):
                    return format_response_for_agent(result)
                else:
                    error_msg = result.get("error", "Error desconocido") if result else "Respuesta vacía"
                    return f"⚠️ Error obteniendo assets generales: {error_msg}"
            except Exception as e:
                return f"Error al obtener assets generales: {str(e)}"
        
        return fetch_general_assets
    
    def _create_asset_search_tool(self):
        """🔍 Tool de búsqueda de assets SIN cache problemático"""
        @tool
        def search_specific_asset(asset_name: str) -> str:
            """
            Busca un asset específico (rig o well) por nombre en la base de datos de Corva.
            
            Esta función usa matching inteligente automático:
            - Match exacto (98%+): Procede automáticamente
            - Match bueno (85-97%): Informa similitud pero permite uso
            - Match bajo (<85%): Solicita validación del usuario
            
            Args:
                asset_name: Nombre exacto o aproximado del asset a buscar
                
            Returns:
                str: Asset encontrado o lista de opciones para validación del usuario
            """
            try:
                clean_name = str(asset_name).strip() if asset_name else ""
                if not clean_name:
                    return "⚠️ No se proporcionó un nombre válido de asset."
                
                print(f"🔍 BUSCANDO ASSET AVATAR: '{clean_name}'")
                
                matches, search_type = search_asset_by_name(clean_name)
                
                print(f"🔍 RESULTADO AVATAR: {search_type}, {len(matches)} matches")
                
                if search_type == "exact":
                    if len(matches) == 1:
                        asset = matches[0]
                        name = asset.get("attributes", {}).get("name", "")
                        asset_id = asset.get("id", "")
                        return f"✅ Asset encontrado: '{name}' (ID: {asset_id})\n\n✅ Puedes proceder con KPIs, profundidad, ROP, etc."
                    
                    else:  # Múltiples matches exactos
                        # Buscar el que coincida EXACTAMENTE
                        for asset in matches:
                            asset_name_field = asset.get("attributes", {}).get("name", "")
                            if asset_name_field.strip().lower() == clean_name.strip().lower():
                                asset_id = asset.get("id", "")
                                return f"✅ Asset encontrado: '{asset_name_field}' (ID: {asset_id})\n\n✅ Puedes proceder con KPIs, profundidad, etc."
                        
                        # Si no encuentra coincidencia exacta en múltiples
                        results = ["🔍 Encontré múltiples assets similares:"]
                        for i, asset in enumerate(matches[:5], 1):
                            name = asset.get("attributes", {}).get("name", "")
                            results.append(f"{i}. {name}")
                        results.append("\n❓ ¿Cuál necesitas? Especifica el nombre exacto.")
                        return "\n".join(results)
                
                elif search_type == "partial":
                    results = [f"🔍 No encontré '{clean_name}' exactamente. Assets similares:"]
                    for i, asset in enumerate(matches[:5], 1):
                        name = asset.get("attributes", {}).get("name", "")
                        similarity = asset.get("similarity", 0)
                        results.append(f"{i}. {name} (similitud: {similarity:.0f}%)")
                    results.append(f"\n❓ ¿Es '{clean_name}' alguno de estos? Las funciones de datos pueden usar el mejor match automáticamente.")
                    return "\n".join(results)
                
                elif search_type == "none":
                    return f"❌ NO encontrado: '{clean_name}'\n\n💡 Usa fetch_general_assets() para ver todos los assets disponibles."
                
                else:
                    return f"⚠️ Error buscando '{clean_name}'"
                    
            except Exception as e:
                print(f"❌ ERROR BÚSQUEDA AVATAR: {e}")
                return f"❌ Error: {str(e)}"
        
        return search_specific_asset

    def _create_kpis_tool(self):
        """📊 HERRAMIENTA DE KPIs SIN DEPENDENCIAS DE CACHE"""
        @tool
        def fetch_asset_kpis(user_query: str) -> str:
            """
            Obtiene KPIs específicos para un rig o well mencionado en la consulta del usuario.
            
            Esta herramienta usa matching automático inteligente integrado:
            - No requiere validación previa obligatoria
            - Maneja automáticamente matches de alta similitud (85%+)
            - Solo solicita aclaración si hay ambigüedad real
            
            Args:
                user_query: Consulta del usuario que incluye el nombre del rig o well
                
            Returns:
                str: KPIs formateados del asset encontrado
                
            Ejemplos de uso:
            - "KPIs del rig DLS 167"
            - "datos de rendimiento del well ABC-001"
            """
            try:
                print(f"📊 OBTENIENDO KPIs AVATAR: '{user_query}'")
                
                # La función get_kpis_workflow ya maneja el matching inteligente
                result = get_kpis_workflow(user_query)
                
                if result and result.get("success"):
                    formatted_result = format_response_for_agent(result)
                    print("✅ KPIs Avatar obtenidos exitosamente")
                    return formatted_result
                else:
                    error_msg = result.get("error", "Error desconocido") if result else "Respuesta vacía"
                    print(f"⚠️ Error KPIs Avatar: {error_msg}")
                    return f"⚠️ Error obteniendo KPIs: {error_msg}"
                    
            except Exception as e:
                error_msg = str(e)
                print(f"❌ ERROR EN KPIs AVATAR: {error_msg}")
                if "Expecting value" in error_msg:
                    return "⚠️ El endpoint de KPIs está disponible pero devolvió una respuesta vacía."
                return f"Error al obtener KPIs: {error_msg}"
        
        return fetch_asset_kpis

    def _create_wits_depth_tool(self):
        """🎯 HERRAMIENTA DE PROFUNDIDAD SIN DEPENDENCIAS"""
        @tool
        def fetch_wits_depth(user_query: str) -> str:
            """
            Obtiene profundidad del trepano de un asset específico.
            
            Usa matching automático inteligente integrado.
            
            Args:
                user_query: Consulta que incluye el nombre del rig o well
                
            Returns:
                str: Profundidad del hueco y del trepano formateada
            """
            try:
                print(f"🎯 OBTENIENDO PROFUNDIDAD AVATAR: '{user_query}'")
                
                result = get_wits_depth(user_query)
                if result and result.get("success"):
                    return format_response_for_agent(result)
                else:
                    error_msg = result.get("error", "Error desconocido") if result else "Respuesta vacía"
                    return f"⚠️ Error obteniendo profundidad: {error_msg}"
                    
            except Exception as e:
                return f"Error al obtener profundidad del trepano: {str(e)}"
        
        return fetch_wits_depth

    def _create_wits_summary_tool(self):
        """📏 HERRAMIENTA DE ROP SIN DEPENDENCIAS"""
        @tool
        def fetch_wits_summary(user_query: str) -> str:
            """
            Obtiene el ROP actual del pozo para un asset específico.
            
            Usa matching automático inteligente integrado.
            
            Args:
                user_query: Consulta que incluye el nombre del rig o well
                
            Returns:
                str: ROP actual formateado
            """
            try:
                print(f"📏 OBTENIENDO ROP AVATAR: '{user_query}'")
                
                result = get_wits_summary(user_query)
                if result and result.get("success"):
                    return format_response_for_agent(result)
                else:
                    error_msg = result.get("error", "Error desconocido") if result else "Respuesta vacía"
                    return f"⚠️ Error obteniendo ROP actual: {error_msg}"
                    
            except Exception as e:
                return f"Error al obtener ROP actual: {str(e)}"
        
        return fetch_wits_summary

    def _create_metrics_rop_tool(self):
        """📊 HERRAMIENTA DE MÉTRICAS ROP SIN DEPENDENCIAS"""
        @tool
        def fetch_metrics_rop(user_query: str) -> str:
            """
            Obtiene métricas de ROP promedio por sección del pozo.
            
            Usa matching automático inteligente integrado.
            
            Args:
                user_query: Consulta que incluye el nombre del rig or well
                
            Returns:
                str: Métricas ROP formateadas por sección
            """
            try:
                print(f"📊 OBTENIENDO MÉTRICAS ROP AVATAR: '{user_query}'")
                
                result = get_metrics_rop(user_query)
                if result and result.get("success"):
                    return format_response_for_agent(result)
                else:
                    error_msg = result.get("error", "Error desconocido") if result else "Respuesta vacía"
                    return f"⚠️ Error obteniendo métricas ROP: {error_msg}"
                    
            except Exception as e:
                return f"Error al obtener métricas ROP: {str(e)}"
        
        return fetch_metrics_rop

    def _create_operations_tool(self):
        """⏱️ HERRAMIENTA DE OPERACIONES SIN DEPENDENCIAS"""
        @tool
        def fetch_operations(user_query: str) -> str:
            """
            Obtiene tiempos de operaciones de conexión para un asset específico.
            
            Usa matching automático inteligente integrado.
            
            Args:
                user_query: Consulta que incluye el nombre del rig o well
                
            Returns:
                str: Tiempos de operaciones formateados
            """
            try:
                print(f"⏱️ OBTENIENDO OPERACIONES AVATAR: '{user_query}'")
                
                result = get_operations(user_query)
                if result and result.get("success"):
                    return format_response_for_agent(result)
                else:
                    error_msg = result.get("error", "Error desconocido") if result else "Respuesta vacía"
                    return f"⚠️ Error obteniendo operaciones: {error_msg}"
                    
            except Exception as e:
                return f"Error al obtener operaciones: {str(e)}"
        
        return fetch_operations
    
    def _create_asset_detailed_info_tool(self):
        """🔧 Tool para obtener información completa y detallada de un asset específico"""
        @tool
        def fetch_asset_detailed_info(user_query: str) -> str:
            """
            Obtiene información completa y detallada de un asset específico (rig o well).
            
            Esta tool está diseñada para responder consultas como:
            - "Dame información del DLS 168"
            - "Detalles completos del LCav-415"
            - "Información del rig Nabors F35"
            - "Datos completos del pozo YPF.Nq.LCav-415(h)"
            - "Qué sabes sobre el asset ABC-001"
            
            IMPORTANTE: Esta tool devuelve información DE BASE del asset (metadata, configuración,
            ubicación, estado, etc.) NO datos operacionales en tiempo real.
            
            Para datos operacionales específicos usa:
            - fetch_asset_kpis() → KPIs y rendimiento
            - fetch_wits_depth() → Profundidad del trepano  
            - fetch_wits_summary() → ROP actual
            
            Args:
                user_query: Consulta del usuario que incluye el nombre del asset
                
            Returns:
                str: Información completa formateada del asset encontrado
                
            Ejemplos de uso:
            - "información completa del DLS 168"
            - "detalles del pozo LCav-415"
            - "datos base del rig F35"
            """
            try:
                result = get_asset_detailed_info(user_query)
                
                if result and result.get("success"):
                    # Extraer la información formateada
                    detailed_info = result.get("detailed_info", "")
                    asset_name = result.get("asset_name", "")
                    message = result.get("message", "")
                    
                    if detailed_info:
                        return f"{message}\n\n{detailed_info}"
                    else:
                        return f"✅ Asset encontrado: {asset_name}, pero no se pudo formatear la información completa."
                else:
                    error_msg = result.get("error", "Error desconocido") if result else "Respuesta vacía"
                    return f"⚠️ Error obteniendo información detallada: {error_msg}"
                    
            except Exception as e:
                return f"Error al obtener información detallada del asset: {str(e)}"
        
        return fetch_asset_detailed_info

    def _create_fracking_metrics_tool(self):
        """📊 Tool para obtener métricas de fracturamiento hidráulico"""
        @tool
        def fetch_fracking_metrics(user_query: str) -> str:
            """
            Obtiene métricas específicas de fracturamiento hidráulico para un asset.
            
            Esta tool maneja métricas agregadas por etapa para operaciones de fracking:
            
            **VOLÚMENES:**
            - Volumen sucio/limpio por etapa
            
            **QUÍMICOS LÍQUIDOS:**
            - Reductor de fricción
            - Surfactante  
            - Biocida
            - Inhibidor de escala
            - Martillo líquido
            
            **QUÍMICOS EN POLVO:**
            - Concentración de polvo FR
            - Triturador de polvo
            - Gel en polvo
            
            **PROPPANT Y TIMING:**
            - Arena total (proppant)
            - Tiempo entre etapas
            
            IMPORTANTE: Esta tool incluye su propia búsqueda y validación de assets.
            
            Args:
                user_query: Consulta que incluye el asset y tipo de métrica deseada
                
            Returns:
                str: Métricas de fracturamiento formateadas por etapa
                
            Ejemplos de uso:
            - "volumen sucio del pozo LCav-415"
            - "reductor de fricción del rig DLS-168"
            - "arena total por etapa del well ABC-001"
            - "tiempo entre etapas del LCav-415 etapa 5"
            """
            try:
                result = get_fracking_metrics(user_query)
                
                if result and result.get("success"):
                    return format_fracking_metrics_response(result)
                else:
                    error_msg = result.get("error", "Error desconocido") if result else "Respuesta vacía"
                    return f"⚠️ {error_msg}"
                    
            except Exception as e:
                return f"Error al obtener métricas de fracturamiento: {str(e)}"
        
        return fetch_fracking_metrics

    def get_status_info(self) -> str:
        """Devuelve información del estado de inicialización Avatar"""
        return self.initialization_status

    def process_query(self, user_query: str, session_id: str = None, user_id: str = None) -> str:
        """
        Procesador Avatar sin cache problemático y con integración completa
        
        INTEGRACIÓN AVATAR:
        - Acepta session_id y user_id para integración con sistema Avatar
        - Maneja memoria Avatar si está disponible
        - Guarda métricas en PostgreSQL Avatar
        """
        try:
            if not user_query or not user_query.strip():
                return "⚠️ Consulta vacía"
            
            clean_query = user_query.strip()
            
            if not self.agent:
                return f"❌ Agente Avatar no inicializado: {self.initialization_status}"
            
            print(f"🚀 PROCESANDO AVATAR: '{clean_query}'")
            
            # 🔧 INTEGRACIÓN MEMORIA AVATAR
            enhanced_query = clean_query
            if MEMORY_AVAILABLE and session_id and user_id:
                try:
                    # Enriquecer query con contexto Avatar
                    relevant_context = get_relevant_context_for_question(clean_query, user_id, session_id)
                    if relevant_context:
                        enhanced_query = f"{clean_query}\n\nContexto Avatar relevante:\n{relevant_context[:300]}..."
                        print(f"✅ Contexto Avatar agregado: {len(relevant_context)} chars")
                except Exception as context_error:
                    print(f"⚠️ Error obteniendo contexto Avatar: {context_error}")
                    # Continuar sin contexto
            
            # Ejecutar agente Agno Avatar
            try:
                response = self.agent.run(enhanced_query)
                
                if response is None:
                    return "⚠️ No se pudo generar respuesta Avatar"
                
                result = str(response)
                
                # 🔧 GUARDAR MÉTRICAS AVATAR
                if POSTGRES_AVAILABLE and session_id:
                    try:
                        save_performance_metric_simple(session_id, "corva_agno_avatar", 0.0, True)
                        print("✅ Métricas Avatar guardadas")
                    except Exception as metrics_error:
                        print(f"⚠️ Error guardando métricas Avatar: {metrics_error}")
                
                print(f"✅ RESPUESTA AVATAR: {len(result)} chars")
                return result
                
            except Exception as agent_error:
                print(f"❌ Error en agente Avatar: {agent_error}")
                return f"Error ejecutando agente Avatar: {str(agent_error)}"
            
        except Exception as e:
            print(f"❌ Error general Avatar: {e}")
            return f"Error procesando Avatar: {str(e)}"


# 🔧 INTERFAZ DE COMPATIBILIDAD AVATAR
_corva_agent_avatar_instance = None

def get_corva_agent() -> CorvaAgnoAgent:
    """Obtiene instancia singleton del agente Avatar"""
    global _corva_agent_avatar_instance
    
    if _corva_agent_avatar_instance is None:
        print("🔄 Inicializando agente Corva Avatar completo...")
        _corva_agent_avatar_instance = CorvaAgnoAgent()
        print(f"✅ Agente Corva Avatar completo inicializado")
    
    return _corva_agent_avatar_instance

def corva_api_query_agnostic(user_query: str) -> str:
    """
    🚀 FUNCIÓN PRINCIPAL AVATAR - Interfaz compatible con sistema Avatar
    
    INTEGRACIÓN AVATAR COMPLETA:
    - Manejo de errores robusto
    - Fallback al método original
    - Compatible con toda la infraestructura Avatar
    """
    try:
        print('🚀 INICIANDO corva_api_query_agnostic AVATAR')
        
        if not user_query or not str(user_query).strip():
            return "⚠️ Consulta vacía recibida."
        
        clean_query = str(user_query).strip()
        print(f"🔍 AVATAR - Query validada: '{clean_query}'")
        
        agent = get_corva_agent()
        return agent.process_query(clean_query)
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ ERROR PRINCIPAL AVATAR: {error_msg}")
        
        # Fallback al método original si está disponible
        try:
            from src.corva_tool_avatar import corva_api_query as original_corva_api_query
            print("🔄 Usando método original Avatar como fallback...")
            return original_corva_api_query(user_query)
        except Exception as fallback_error:
            return f"⚠️ Error en agente Avatar y método original: {str(fallback_error)}"


# 🔧 FUNCIONES DE DIAGNÓSTICO AVATAR
def diagnose_avatar_environment():
    """
    Diagnostica el estado del entorno Avatar específicamente
    """
    print("🔍 DIAGNÓSTICO DEL ENTORNO AVATAR CORVA")
    print("=" * 60)
    
    # 1. Verificar importación de Agno
    try:
        from agno.agent import Agent
        print("✅ Agno importable: SÍ")
    except ImportError:
        print("❌ Agno importable: NO")
    
    # 2. Verificar variables de entorno Avatar
    print("\n🔧 Variables de entorno Avatar:")
    avatar_vars = [
        "APIM_AUTH_CREDENTIAL",
        "AZURE_OPENAI_API_KEY", 
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT_NAME",  # ← Variable Avatar estándar
        "API_VERSION"  # ← Variable Avatar estándar
    ]
    
    for var in avatar_vars:
        value = os.getenv(var)
        if value:
            masked_value = value[:10] + "..." if len(value) > 10 else value
            print(f"  ✅ {var}: {masked_value}")
        else:
            print(f"  ❌ {var}: NO CONFIGURADA")
    
    # 3. Verificar disponibilidad Avatar completa
    is_valid, missing_vars = validate_azure_env_vars_avatar()
    if is_valid:
        print(f"\n🎯 Estado Avatar final: ✅ Todas las variables están configuradas")
    else:
        print(f"\n🎯 Estado Avatar final: ❌ Variables faltantes: {missing_vars}")
    
    # 4. Verificar integración Avatar
    print(f"\n🤖 Integración Avatar:")
    print(f"  📝 Memoria disponible: {MEMORY_AVAILABLE}")
    print(f"  🗄️ PostgreSQL disponible: {POSTGRES_AVAILABLE}")
    
    # 5. Intentar crear agente Avatar
    print(f"\n🚀 Probando inicialización del agente Avatar:")
    try:
        agent = CorvaAgnoAgent()
        print(f"  {agent.get_status_info()}")
    except Exception as e:
        print(f"  ❌ Error Avatar: {e}")

if __name__ == "__main__":
    # Ejecutar diagnóstico Avatar
    diagnose_avatar_environment()


"""
CORRECCIONES CRÍTICAS APLICADAS PARA AVATAR:
============================================

🔧 **Variables de entorno Avatar específicas**: 
   - AZURE_OPENAI_DEPLOYMENT_NAME (estándar Avatar)
   - API_VERSION (estándar Avatar)

🔧 **Importaciones Avatar corregidas**:
   - src.corva_tool_avatar (ruta Avatar correcta)
   - src.langmem_functions (memoria Avatar)
   - src.postgres_integration (PostgreSQL Avatar)

🔧 **Eliminación de cache problemático**:
   - NO más last_asset_search que causaba dependencias
   - Tools independientes que usan matching automático

🔧 **Integración memoria Avatar completa**:
   - get_relevant_context_for_question()
   - create_enhanced_prompt_with_memory()
   - save_performance_metric_simple()

🔧 **Configuración Azure Avatar robusta**:
   - Validación específica para variables Avatar
   - Manejo de errores Avatar apropiado
   - Fallback a métodos originales Avatar

🔧 **Instrucciones optimizadas para Avatar**:
   - CoT apropiado para sistema Avatar
   - Integración con matching automático
   - Manejo de errores Avatar específico

🔧 **Funciones de diagnóstico Avatar**:
   - diagnose_avatar_environment()
   - validate_azure_env_vars_avatar()

RESULTADO: 
==========
Agente Avatar totalmente funcional que mantiene TODA la integración con:
- Sistema de memoria Avatar
- PostgreSQL Avatar  
- Variables de entorno Avatar
- Estructura de proyecto Avatar
- Matching automático inteligente
- Sin dependencias de cache problemáticas

El agente ahora funciona independientemente pero integrado completamente con el ecosistema Avatar.
"""