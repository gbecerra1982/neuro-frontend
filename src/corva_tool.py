"""
Corva API Tool para el agente IA - VERSIÓN RESTAURADA Y CORREGIDA PARA AVATAR
===============================================================================

Maneja consultas a los endpoints de Corva según la intención del usuario.
CORRIGE el problema de matching automático incorrecto.
INTEGRADA COMPLETAMENTE CON SISTEMA AVATAR.

Para usar en tu agente, importa: corva_api_query
"""

import requests
import json
import re
import base64
from typing import Dict, List, Optional, Tuple
from langchain.agents import tool
from fuzzywuzzy import fuzz
import os
from langchain_openai import AzureChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from datetime import datetime


# Configuración de la API - ACTUALIZADA PARA APIM YPF
CORVA_BASE_URL = "https://maginternotest.grupo.ypf.com/corva/api"
CORVA_BASE_URL_DATA = "https://maginternotest.grupo.ypf.com/corva/data/api/v1"
CORVA_BASE_API_V1 = "https://maginternotest.grupo.ypf.com/corva/api/v1"
CORVA_BASE_API_V2 = "https://maginternotest.grupo.ypf.com/corva/api/v2"
CORVA_ASSETS_URL = "/data/corva/assets/"
ERROR_MESSAGE_ASSETS = "Error al buscar el asset en la base de datos"
WEIGHT_TO_WEIGHT = "Weight To Weight"

validation_llm = AzureChatOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    openai_api_version=os.getenv("API_VERSION", "2024-10-21"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    model_name="gpt-4o",
    temperature=0,
    timeout=30,
    max_retries=2
)

# FRACKING_METRICS_MAP completo (NUEVA FUNCIONALIDAD):
FRACKING_METRICS_MAP = {
    # Volúmenes
    "volumen_sucio": {
        "key": "total_slurry_volume",
        "description": "Volumen total de volumen sucio por etapa",
        "keywords": ["volumen sucio", "slurry volume", "volumen total sucio"],
        "unit": "bbl"
    },
    "volumen_limpio": {
        "key": "total_clean_volume", 
        "description": "Volumen total limpio por etapa",
        "keywords": ["volumen limpio", "clean volume", "volumen total limpio"],
        "unit": "bbl"
    },
    
    # Químicos líquidos
    "reductor_friccion": {
        "key": "total_friction_reducer",
        "description": "Reductor de fricción total por etapa",
        "keywords": ["reductor de friccion", "friction reducer", "reductor friccion"],
        "unit": "gal"
    },
    "surfactante": {
        "key": "total_surfactant",
        "description": "Surfactante total por etapa", 
        "keywords": ["surfactante", "surfactant"],
        "unit": "gal"
    },
    "biocida": {
        "key": "total_biocide",
        "description": "Biocida total por etapa",
        "keywords": ["biocida", "biocide"],
        "unit": "gal"
    },
    "inhibidor": {
        "key": "total_scale_inhibitor",
        "description": "Inhibidor total por etapa",
        "keywords": ["inhibidor", "scale inhibitor", "inhibidor de escala"],
        "unit": "gal"
    },
    "martillo_liquido": {
        "key": "total_liquid_breaker",
        "description": "Martillo líquido total por etapa",
        "keywords": ["martillo liquido", "liquid breaker", "breaker liquido"],
        "unit": "gal"
    },
    
    # Químicos en polvo
    "concentracion_polvo_fr": {
        "key": "total_powder_fr_concentration",
        "description": "Concentración total de reductor de fricción en polvo por etapa",
        "keywords": ["concentracion polvo", "powder fr concentration", "reductor friccion polvo"],
        "unit": "lbs"
    },
    "triturador_polvo": {
        "key": "total_powder_breaker",
        "description": "Triturador de polvo total por etapa",
        "keywords": ["triturador polvo", "powder breaker", "breaker polvo"],
        "unit": "lbs"
    },
    "gel_polvo": {
        "key": "total_powder_gel",
        "description": "Gel en polvo total por etapa", 
        "keywords": ["gel polvo", "powder gel", "gel en polvo"],
        "unit": "lbs"
    },
    
    # Proppant y timing
    "arena": {
        "key": "total_proppant",
        "description": "Total arena (proppant) por etapa",
        "keywords": ["arena", "proppant", "total arena"],
        "unit": "lbs"
    },
    "tiempo_etapas": {
        "key": "total_swapover_time",
        "description": "Tiempo entre etapas",
        "keywords": ["tiempo etapas", "swapover time", "tiempo entre etapas"],
        "unit": "min"
    }
}

class CorvaAPIError(Exception):
    """Excepción personalizada para errores de la API de Corva"""
    pass

def classify_user_intent(user_query: str) -> str:
    """
    Clasifica la intención del usuario basado en su consulta
    
    Returns:
        str: "alerts", "rigs", "wells", "kpis", "wits_depth", "wits_summary", "metrics_rop", "operations", "assets", o "unknown"
    """
    query_lower = user_query.lower()
    
    # Palabras clave para cada intención
    alert_keywords = ["alerta", "alerts", "alarma", "notificación", "warning"]
    rig_keywords = ["rig","rigs"]
    well_keywords = ["well", "wells"]
    kpi_keywords = ["kpi", "kpis", "performance", "rendimiento", "datos", "conexiones", "operacion"]
    
    # NUEVAS INTENCIONES
    depth_keywords = ["profundidad", "depth", "trepano", "hole_depth", "bit_depth", "profundidad actual"]
    rop_actual_keywords = ["rop actual", "rop current", "velocidad actual", "drilling rate current"]
    rop_metrics_keywords = ["rop promedio", "rop horizontal", "rop average", "rop metrics", "velocidad promedio"]
    operations_keywords = ["conexiones", "connections", "tiempos conexion", "weight to weight", "operaciones", "connection times"]
    assets_keywords = ["assets", "activos", "listado completo", "todos los rigs", "todos los wells"]
    
    # Verificar nuevas intenciones primero (más específicas)
    if any(kw in query_lower for kw in depth_keywords):
        return "wits_depth"
    
    if any(kw in query_lower for kw in rop_actual_keywords):
        return "wits_summary"
        
    if any(kw in query_lower for kw in rop_metrics_keywords):
        return "metrics_rop"
        
    if any(kw in query_lower for kw in operations_keywords):
        return "operations"
    
    if any(kw in query_lower for kw in assets_keywords):
        return "assets"
    
    # Verificar KPIs (mantener lógica original)
    if any(kw in query_lower for kw in kpi_keywords):
        if any(kw in query_lower for kw in rig_keywords + well_keywords):
            return "kpis"
    
    # Verificar alertas
    if any(kw in query_lower for kw in alert_keywords):
        return "alerts"
    
    # Verificar rigs generales
    if any(kw in query_lower for kw in rig_keywords) and not any(kw in query_lower for kw in kpi_keywords):
        return "rigs"
    
    # Verificar wells generales  
    if any(kw in query_lower for kw in well_keywords) and not any(kw in query_lower for kw in kpi_keywords):
        return "wells"
    
    return "unknown"

def normalize_asset_name_for_matching(name: str) -> str:
    """Normaliza nombres para matching inteligente"""
    if not name:
        return ""
    
    normalized = name.lower()
    
    # Remover prefijos YPF específicos
    prefixes = ['ypf.nq.', 'ypf.elg.', 'ypf.', 'nq.', 'elg.']
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    
    return normalized

def calculate_smart_similarity(user_name: str, corva_name: str) -> float:
    """Calcula similitud inteligente entre nombres de assets"""
    if not user_name or not corva_name:
        return 0.0
    
    user_norm = normalize_asset_name_for_matching(user_name)
    corva_norm = normalize_asset_name_for_matching(corva_name)
    
    # 1. Similitud básica
    basic_score = fuzz.partial_ratio(user_name.lower(), corva_name.lower())
    
    # 2. Similitud normalizada (sin prefijos YPF)
    normalized_score = fuzz.ratio(user_norm, corva_norm)
    
    # 3. Bonus por patrones específicos
    pattern_bonus = 0
    
    # Extraer patrón central (ej: "lcav-412" de "YPF.Nq.LCav-412(h)")
    user_pattern = re.search(r'([a-z]+[-_]?\d+)', user_norm)
    corva_pattern = re.search(r'([a-z]+[-_]?\d+)', corva_norm)
    
    if user_pattern and corva_pattern:
        user_core = user_pattern.group(1)
        corva_core = corva_pattern.group(1)
        
        # Si el patrón core es muy similar, dar bonus
        if fuzz.ratio(user_core, corva_core) >= 80:
            pattern_bonus = 20
    
    # 4. Score final
    final_score = max(basic_score, normalized_score) + pattern_bonus
    
    return min(100.0, final_score)

def extract_asset_name(user_query: str) -> Optional[str]:
    """
    Extrae el nombre del asset (rig/well) de la consulta del usuario - VERSIÓN MEJORADA
    
    MEJORAS:
    - Soporte para paréntesis: LCav-415(h), ABC-001(v), etc.
    - Soporte para guiones bajos: Rig_123, Well_ABC_001
    - Soporte para puntos: LCav.415, Rig.123
    - Soporte para barras: LCav/415, ABC/001  
    - Patrones más específicos para pozos petroleros
    """
    if not user_query or not isinstance(user_query, str):
        return None
    
    # PATRONES MEJORADOS - Incluyen caracteres especiales comunes en nombres de pozos
    patterns = [
        # Patrón principal: pozo/rig/well/equipo seguido del nombre (CON PARÉNTESIS)
        r'(?:rig|well|pozo|equipo)\s+["\']?([A-Za-z0-9\s\-_().\/]+?)["\']?(?:\s|$|,|\.|!|\?)',
        
        # Patrón específico para "en el pozo NOMBRE"  
        r'(?:en\s+el\s+pozo|del\s+pozo|al\s+pozo)\s+["\']?([A-Za-z0-9\s\-_().\/]+?)["\']?(?:\s|$|,|\.|!|\?)',
        
        # Patrón para "de/del/para/sobre NOMBRE"
        r'(?:de|del|para|sobre)\s+["\']?([A-Za-z0-9\s\-_().\/]+?)["\']?(?:\s|$|,|\.|!|\?)',
        
        # Patrón entre comillas (cualquier nombre entre comillas)
        r'["\']([A-Za-z0-9\s\-_().\/]+)["\']',
        
        # Patrón específico para códigos de pozos (LCav-415, ABC-001, etc.)
        r'\b([A-Za-z]{2,6}[-_.]?\d{1,4}[A-Za-z]*(?:\([a-zA-Z]\))?)\b',
        
        # Patrón específico para rigs (DLS 167, Rig-123, etc.)  
        r'\b([A-Za-z]{2,4}\s*[-_.]?\s*\d{1,4}[A-Za-z]*)\b',
    ]
    
    query_lower = user_query.lower()
    
    for pattern in patterns:
        matches = re.finditer(pattern, user_query, re.IGNORECASE)
        for match in matches:
            candidate = match.group(1).strip()
            
            # Filtrar candidatos obvios que no son nombres de assets
            if _is_valid_asset_name(candidate, query_lower):
                print(f"🔍 DEBUG EXTRACT - Extraído: '{candidate}' del query: '{user_query}'")
                return candidate
    
    print(f"⚠️ DEBUG EXTRACT - No se pudo extraer asset de: '{user_query}'")
    return None

def _is_valid_asset_name(candidate: str, query_lower: str) -> bool:
    """
    Valida si un candidato es realmente un nombre de asset válido
    """
    if not candidate or len(candidate.strip()) < 2:
        return False
    
    candidate_lower = candidate.lower().strip()
    
    # Filtrar palabras comunes que NO son nombres de assets
    invalid_names = {
        'el', 'la', 'los', 'las', 'de', 'del', 'al', 'en', 'con', 'para', 'por', 
        'este', 'esta', 'ese', 'esa', 'aquel', 'aquella', 'mi', 'tu', 'su',
        'actual', 'nuevo', 'viejo', 'ultimo', 'primer', 'segundo', 'tercero',
        'datos', 'información', 'info', 'kpi', 'kpis', 'profundidad', 'depth',
        'rop', 'alertas', 'alerts', 'wells', 'rigs', 'pozos', 'equipos'
    }
    
    if candidate_lower in invalid_names:
        return False
    
    # Validar que tenga al menos un número o patrón típico de asset
    has_number = any(c.isdigit() for c in candidate)
    has_typical_pattern = any(char in candidate for char in ['-', '_', '(', ')'])
    
    # Patrones típicos de pozos petroleros
    typical_patterns = [
        r'^[A-Za-z]{2,6}[-_.]?\d+',      # LCav-415, ABC_001
        r'^[A-Za-z]+\s*\d+',             # DLS 167, Rig 123  
        r'\d+[A-Za-z]*\([a-zA-Z]\)$',    # 415(h), 001(v)
    ]
    
    matches_pattern = any(re.search(pattern, candidate) for pattern in typical_patterns)
    
    return has_number or matches_pattern

def make_corva_request_fixed(endpoint: str, params: Dict = None, base_url: str = None) -> Dict:
    """
    Versión simplificada que usa solo autenticación APIM YPF
    """
    if base_url is None:
        base_url = CORVA_BASE_URL_DATA

    url = f"{base_url}{endpoint}"
   
    auth_credential = os.getenv("APIM_AUTH_CREDENTIAL")
    if not auth_credential:
        raise CorvaAPIError("APIM_AUTH_CREDENTIAL no configurada")
 
    # Usar solo método APIM
    headers = {
        "Authorization": f"Basic {auth_credential}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    try:
        print(f"🔍 DEBUG - URL: {url}")
        print(f"🔍 DEBUG - Headers: {headers}")
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        print(f"🔍 DEBUG - Status Code: {response.status_code}")
        print(f"🔍 DEBUG - Content-Type: {response.headers.get('content-type', 'N/A')}")
        print(f"🔍 DEBUG - Content-Length: {len(response.content)}")
        
        if response.content:
            content_preview = response.content[:200].decode('utf-8', errors='ignore')
            print(f"🔍 DEBUG - Content Preview: {repr(content_preview)}")
        else:
            print(f"🔍 DEBUG - Content Preview: [EMPTY RESPONSE]")
        
        if response.status_code == 200:
            print("✅ Autenticación APIM exitosa")
            
            if not response.content.strip():
                print("⚠️  Respuesta vacía pero exitosa - devolviendo estructura por defecto")
                return {"data": [], "message": "Respuesta vacía del servidor"}
            
            try:
                json_data = response.json()
                print(f"🔍 DEBUG - JSON parseado exitosamente: {type(json_data)}")
                return json_data
                
            except json.JSONDecodeError as json_error:
                print(f"⚠️  Error al parsear JSON: {json_error}")
                print(f"🔍 DEBUG - Respuesta raw: {response.text[:500]}")
                
                content_type = response.headers.get('content-type', '').lower()
                
                if 'html' in content_type:
                    print("⚠️  Respuesta es HTML - posible página de error del proxy")
                    return {"error": "API devolvió HTML en lugar de JSON", "html_preview": response.text[:200]}
                
                elif 'text' in content_type:
                    print("⚠️  Respuesta es texto plano")
                    return {"data": response.text, "message": "Respuesta en texto plano"}
                
                else:
                    print("⚠️  Formato de respuesta desconocido")
                    return {"error": "Formato de respuesta no reconocido", "content": response.text[:200]}
        
        else:
            print(f"❌ Error HTTP {response.status_code}")
            print(f"🔍 DEBUG - Response: {response.text}")
            raise CorvaAPIError(f"Error HTTP {response.status_code}: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error de conexión: {str(e)}")
        raise CorvaAPIError(f"Error de conexión: {str(e)}")
    except Exception as e:
        print(f"❌ Error inesperado: {str(e)}")
        raise CorvaAPIError(f"Error inesperado: {str(e)}")


def search_asset_by_name(asset_name: str, cutoff_date: str = "2025-07-01") -> Tuple[List[Dict], str]:
    """
    FUNCIÓN COMPLETA CON PRIORIDAD POR RECENCIA - Búsqueda de assets con matching preciso y validación LLM
    
    Args:
        asset_name: Nombre del asset a buscar
        cutoff_date: Filtrar assets activos desde esta fecha (YYYY-MM-DD)
        
    Returns:
        Tuple[List[Dict], str]: (lista_assets, tipo_resultado)
        - tipo_resultado: "exact" (match exacto), "partial" (requiere validación), "none" (sin matches), "error"
    """
    try:
        # 1. OBTENER DATOS DE LA API
        params = {
            "limit": 1000,
            "query": json.dumps({"company_id": 375}),
            "sort": json.dumps({"name": 1}),
            "skip": 0
        }
        
        data = make_corva_request_fixed(CORVA_ASSETS_URL, params=params, base_url=CORVA_BASE_URL_DATA)
        
        # Normalizar respuesta
        if isinstance(data, list):
            assets = data
        elif isinstance(data, dict):
            assets = data.get("data", data.get("results", []))
        else:
            print(f"🔍 DEBUG - Tipo de data inesperado: {type(data)}")
            return [], "error"
        
        if not assets:
            print("🔍 DEBUG - No se encontraron assets en la respuesta")
            return [], "none"
        
        print(f"🔍 DEBUG SEARCH - Assets totales encontrados: {len(assets)}")
        
        # 2. FILTRAR POR FECHA RECIENTE
        recent_assets = []
        for asset in assets:
            if asset and isinstance(asset, dict):
                if filter_by_recent_activity(asset, cutoff_date):
                    recent_assets.append(asset)
        
        print(f"🔍 DEBUG SEARCH - Assets activos desde {cutoff_date}: {len(recent_assets)} de {len(assets)}")
        
        if not recent_assets:
            print(f"🔍 DEBUG - No se encontraron assets activos desde {cutoff_date}")
            return [], "none"
        
        # 3. PREPARAR CANDIDATOS CON INFORMACIÓN COMPLETA
        candidate_assets = []
        for asset in recent_assets:
            if not asset or not isinstance(asset, dict):
                continue
            
            # Extraer nombres
            asset_name_field = (asset.get("name") or 
                               asset.get("asset_name") or 
                               asset.get("data", {}).get("name", ""))
            
            rig_name_field = asset.get("rig", {}).get("name", "")
            
            asset_id = (asset.get("id") or 
                       asset.get("asset_id") or 
                       asset.get("_id", ""))
            
            if not asset_id:
                continue
            
            # Determinar nombre final para mostrar
            final_name = asset_name_field
            if not asset_name_field and rig_name_field:
                final_name = rig_name_field
            elif asset_name_field and rig_name_field:
                final_name = f"{asset_name_field} (Rig: {rig_name_field})"
            
            if not final_name:
                continue
            
            # Determinar ID correcto para KPIs
            kpi_asset_id = asset_id
            active_child = asset.get("active_child")
            if active_child and isinstance(active_child, dict):
                child_id = active_child.get("id")
                if child_id:
                    kpi_asset_id = child_id
            
            candidate_assets.append({
                "id": str(kpi_asset_id),
                "original_id": str(asset_id),
                "attributes": {"name": final_name},
                "well_name": asset_name_field,
                "rig_name": rig_name_field,
                "last_active_at": asset.get("last_active_at", "N/A"),
            })
        
        if not candidate_assets:
            print("🔍 DEBUG - No se encontraron assets válidos después del filtrado")
            return [], "none"
        
        print(f"🔍 DEBUG - Assets válidos después del filtrado: {len(candidate_assets)}")
        
        # 4. APLICAR LÓGICA DE MATCHING MEJORADA
        filtered_candidates = []
        search_name_lower = asset_name.lower()
        
        print(f"🔍 DEBUG - Aplicando matching mejorado para: '{search_name_lower}'")
        
        for asset in candidate_assets:
            # Obtener nombres para matching
            name = asset.get("attributes", {}).get("name", "").lower()
            well_name = asset.get("well_name", "").lower()
            rig_name = asset.get("rig_name", "").lower()
            
            match_found = False
            match_score = 0
            match_reason = ""
            
            # PRIORIDAD 1: MATCH EXACTO COMPLETO
            if (search_name_lower == well_name or 
                search_name_lower == name or 
                search_name_lower == rig_name):
                match_found = True
                match_score = 100
                match_reason = "exact_complete_match"
                
            # PRIORIDAD 2: MATCH EXACTO POR SUBSTRING EN WELL NAME
            elif well_name and search_name_lower in well_name:
                match_found = True
                match_score = 98
                match_reason = "exact_well_substring"
                
            # PRIORIDAD 3: MATCH EXACTO POR SUBSTRING EN NOMBRE COMBINADO
            elif search_name_lower in name:
                match_found = True
                match_score = 95
                match_reason = "exact_name_substring"
                
            # PRIORIDAD 4: FUZZY MATCH ALTO EN WELL NAME
            elif well_name and fuzz.ratio(search_name_lower, well_name) >= 90:
                match_score = fuzz.ratio(search_name_lower, well_name)
                match_found = True
                match_reason = "fuzzy_well_high"
                
            # PRIORIDAD 5: FUZZY MATCH MEDIO EN WELL NAME
            elif well_name and fuzz.partial_ratio(search_name_lower, well_name) >= 85:
                match_score = fuzz.partial_ratio(search_name_lower, well_name)
                match_found = True
                match_reason = "fuzzy_well_medium"
                
            # PRIORIDAD 6: MATCH EN RIG NAME (solo para búsquedas explícitas de rigs)
            elif (any(keyword in search_name_lower for keyword in ["dls", "nabors", "h&p", "rig", "f35", "t430"]) and 
                  rig_name and fuzz.partial_ratio(search_name_lower, rig_name) >= 80):
                match_score = fuzz.partial_ratio(search_name_lower, rig_name)
                match_found = True
                match_reason = "rig_explicit_match"
                
            # PRIORIDAD 7: MATCH POR COMPONENTES CRÍTICOS (números + letras)
            elif well_name or name:
                target_text = well_name if well_name else name
                
                # Extraer componentes críticos: combinaciones letra-número
                search_components = re.findall(r'[a-zA-Z]+[-.]?\d+(?:\([a-zA-Z]\))?', search_name_lower)
                target_components = re.findall(r'[a-zA-Z]+[-.]?\d+(?:\([a-zA-Z]\))?', target_text)
                
                if search_components and target_components:
                    # Buscar matches exactos de componentes
                    exact_component_matches = sum(1 for search_comp in search_components 
                                                if any(search_comp in target_comp for target_comp in target_components))
                    
                    if exact_component_matches > 0:
                        match_score = min(90, (exact_component_matches / len(search_components)) * 85 + 10)
                        if match_score >= 70:
                            match_found = True
                            match_reason = "component_critical_match"
            
            # Agregar candidato si cumple criterios
            if match_found and match_score >= 70:  # Umbral mínimo de 70%
                asset['match_score'] = match_score
                asset['match_reason'] = match_reason
                filtered_candidates.append(asset)
                
                # Debug del match encontrado
                display_name = asset.get("well_name", "") or asset.get("attributes", {}).get("name", "")
                print(f"✅ Match: {display_name} | Score: {match_score:.1f}% | Reason: {match_reason}")
        
        # 5. ORDENAR POR RELEVANCIA Y FECHA DE ACTIVIDAD (NUEVA LÓGICA)
        def calculate_priority_score(candidate):
            """
            Calcula score de prioridad combinando match_score y recencia
            """
            match_score = candidate.get('match_score', 0)
            last_active = candidate.get('last_active_at', '')
            
            # Score base por matching
            priority_score = match_score
            
            # Bonus por recencia (hasta +15 puntos)
            try:
                if last_active and 'T' in last_active:
                    active_date = datetime.fromisoformat(last_active.replace("Z", "").split(".")[0])
                    cutoff = datetime.strptime(cutoff_date, "%Y-%m-%d")
                    
                    # Días desde cutoff_date
                    days_since_cutoff = (active_date - cutoff).days
                    
                    if days_since_cutoff >= 0:
                        # Más reciente = más bonus (máximo 10 puntos)
                        recency_bonus = min(10, days_since_cutoff / 2.4)  # 24 días = 10 puntos
                        priority_score += recency_bonus
                        
                        # Bonus extra para assets muy recientes (últimos 7 días)
                        if days_since_cutoff >= 17:  # Aproximadamente últimos 7 días desde 2025-07-24
                            priority_score += 5
                            
            except Exception:
                pass  # Usar solo match_score si hay problemas con fechas
            
            return priority_score
        
        # Aplicar nuevo score de prioridad
        for candidate in filtered_candidates:
            candidate['priority_score'] = calculate_priority_score(candidate)
        
        # Ordenar por priority_score (incluye match + recencia)
        filtered_candidates.sort(key=lambda x: x.get('priority_score', 0), reverse=True)
        filtered_candidates = filtered_candidates[:25]
        
        if not filtered_candidates:
            print("🔍 DEBUG - No se encontraron candidatos relevantes después del ordenamiento mejorado")
            return [], "none"
        
        print(f"🔍 DEBUG - Enviando {len(filtered_candidates)} candidatos ordenados por prioridad al LLM")
        
        # Debug: Mostrar top candidatos con nuevo scoring
        for i, candidate in enumerate(filtered_candidates[:15], 1):
            well_name = candidate.get("well_name", "N/A")
            rig_name = candidate.get("rig_name", "N/A")
            match_score = candidate.get("match_score", 0)
            priority_score = candidate.get("priority_score", 0)
            last_active = candidate.get("last_active_at", "N/A")
            if last_active != "N/A" and "T" in last_active:
                last_active = last_active[:10]
            print(f"   {i}. Well: {well_name}, Rig: {rig_name}")
            print(f"      Match: {match_score:.1f}%, Priority: {priority_score:.1f}, Activo: {last_active}")
        
        # 6. VALIDACIÓN CON AZURE OPENAI MEJORADA
        match_type, validated_assets = validate_asset_match_with_llm(asset_name, filtered_candidates)
        
        if match_type == "exact" and len(validated_assets) == 1:
            print("✅ LLM encontró UN match exacto")
            return validated_assets, "exact"
        elif validated_assets:
            print(f"⚠️ LLM encontró {len(validated_assets)} matches parciales - requiere validación del usuario")
            return validated_assets, "partial"
        else:
            print("❌ LLM no encontró matches válidos")
            return [], "none"
            
    except Exception as e:
        print(f"❌ Error en búsqueda de assets mejorada: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return [], "error"

def get_alerts() -> Dict:
    """Obtiene alertas generales"""
    try:
        data = make_corva_request_fixed("/alerts", base_url=CORVA_BASE_API_V1)
        
        alerts = data.get("data", []) if isinstance(data, dict) else data
        
        return {
            "success": True,
            "data_type": "alerts",
            "total": len(alerts),
            "results": alerts[:10],  # Limitar a 10 para no sobrecargar
            "message": f"Se encontraron {len(alerts)} alertas"
        }
        
    except CorvaAPIError as e:
        return {"success": False, "error": str(e)}

def get_rigs() -> Dict:
    """Obtiene información general de rigs"""
    try:
        data = make_corva_request_fixed("/rigs", base_url=CORVA_BASE_API_V2)
        print('get rigs dentro de corva_tool:', data)
        
        rigs = data.get("data", []) if isinstance(data, dict) else data
        print('rigs:', rigs)
        
        return {
            "success": True,
            "data_type": "rigs",
            "total": len(rigs),
            "results": rigs[:20],  # Limitar a 20
            "message": f"Se encontraron {len(rigs)} rigs"
        }
        
    except CorvaAPIError as e:
        return {"success": False, "error": str(e)}


def get_assets_general(cutoff_date: str = "2025-07-01") -> Dict:
    """
    VERSIÓN MEJORADA - Obtiene assets con filtro de fecha reciente y ordenamiento por recencia
    
    MEJORAS APLICADAS desde search_asset_by_name:
    - Mismo sistema de filtrado por fecha
    - Ordenamiento por recencia (más activos primero)
    - Debug mejorado con información detallada
    - Límites y parámetros API consistentes
    - Información más rica manteniendo formato simple
    
    Args:
        cutoff_date: Filtrar assets activos desde esta fecha (YYYY-MM-DD)
    """
    try:
        # 1. PARÁMETROS API CONSISTENTES con search_asset_by_name
        params = {
            "limit": 1000,  # ✅ CAMBIADO: Mismo que search_asset_by_name
            "query": json.dumps({"company_id": 375}),
            "sort": json.dumps({"name": 1}),
            "skip": 0
        }
        
        data = make_corva_request_fixed(CORVA_ASSETS_URL, params=params, base_url=CORVA_BASE_URL_DATA)
        
        # Manejar respuesta del endpoint
        if isinstance(data, list):
            assets = data
        elif isinstance(data, dict):
            assets = data.get("data", data.get("results", []))
        else:
            print(f"🔍 DEBUG GENERAL - Tipo de data inesperado: {type(data)}")
            return {"success": False, "error": f"Formato de respuesta inesperado: {type(data)}"}
        
        if not assets:
            print("🔍 DEBUG GENERAL - No se encontraron assets en la respuesta")
            return {"success": True, "data_type": "assets", "total": 0, "results": [], "message": "No se encontraron assets"}
        
        print(f"🔍 DEBUG GENERAL - Assets totales encontrados: {len(assets)}")
        
        # 2. FILTRAR POR FECHA RECIENTE (misma lógica que search_asset_by_name)
        recent_assets = []
        for asset in assets:
            if asset and isinstance(asset, dict):
                if filter_by_recent_activity(asset, cutoff_date):
                    recent_assets.append(asset)
        
        print(f"🔍 DEBUG GENERAL - Assets activos desde {cutoff_date}: {len(recent_assets)} de {len(assets)}")
        
        # 3. PROCESAR Y ENRIQUECER INFORMACIÓN (misma lógica que search_asset_by_name)
        processed_assets = []
        for asset in recent_assets:
            if not asset or not isinstance(asset, dict):
                continue
                
            # Extraer información completa (misma lógica)
            name = (asset.get("name") or 
                   asset.get("asset_name") or 
                   asset.get("data", {}).get("name", "N/A"))
            
            asset_id = (asset.get("id") or 
                       asset.get("asset_id") or 
                       asset.get("_id", "N/A"))
            
            last_active = asset.get("last_active_at", "N/A")
            if last_active != "N/A" and "T" in last_active:
                last_active_display = last_active[:10]  # Solo fecha YYYY-MM-DD
            else:
                last_active_display = last_active
            
            # Incluir rig.name si existe (misma lógica)
            rig_name = asset.get("rig", {}).get("name", "")
            
            # 4. CALCULAR SCORE DE RECENCIA (adaptado de search_asset_by_name)
            recency_score = 0
            try:
                if last_active and "T" in last_active:
                    active_date = datetime.fromisoformat(last_active.replace("Z", "").split(".")[0])
                    cutoff = datetime.strptime(cutoff_date, "%Y-%m-%d")
                    days_since_cutoff = (active_date - cutoff).days
                    
                    if days_since_cutoff >= 0:
                        # Score de recencia para ordenamiento
                        recency_score = days_since_cutoff
            except Exception:
                recency_score = 0
            
            # Crear string con más info pero manteniendo simplicidad
            asset_string = f"{name} (ID: {asset_id})"
            if rig_name:
                asset_string += f" - Rig: {rig_name}"
            asset_string += f" - Activo: {last_active_display}"
            
            processed_assets.append({
                "display_string": asset_string,
                "name": name,
                "asset_id": asset_id,
                "rig_name": rig_name,
                "last_active": last_active,
                "recency_score": recency_score
            })
        
        # 5. ORDENAR POR RECENCIA (más activos primero) - NUEVA LÓGICA
        processed_assets.sort(key=lambda x: x['recency_score'], reverse=True)
        
        # 6. LIMITAR Y EXTRAER STRINGS PARA DISPLAY (aumentado de 15 a 20)
        display_limit = 20  # ✅ CAMBIADO: Más assets mostrados
        limited_assets = processed_assets[:display_limit]
        simplified_assets = [asset['display_string'] for asset in limited_assets]
        
        # 7. DEBUG MEJORADO (similar a search_asset_by_name)
        print(f"🔍 DEBUG GENERAL - Top {min(10, len(limited_assets))} assets por recencia:")
        for i, asset in enumerate(limited_assets[:10], 1):
            print(f"   {i}. {asset['name'][:30]}")
            print(f"      Rig: {asset['rig_name'] or 'N/A'}, Score: {asset['recency_score']}, Activo: {asset['last_active'][:10] if 'T' in asset['last_active'] else asset['last_active']}")
        
        return {
            "success": True,
            "data_type": "assets",
            "total": len(simplified_assets),
            "results": simplified_assets,
            "message": f"Mostrando {len(simplified_assets)} de {len(processed_assets)} assets activos desde {cutoff_date} (de {len(assets)} totales) - Ordenados por recencia"
        }
        
    except CorvaAPIError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"❌ Error inesperado en get_assets_general mejorada: {e}")
        return {"success": False, "error": f"Error inesperado: {str(e)}"}

def get_wells() -> Dict:
    """Obtiene información general de wells"""
    try:
        data = make_corva_request_fixed("/wells", base_url=CORVA_BASE_API_V2)
        
        wells = data.get("data", []) if isinstance(data, dict) else data
        
        return {
            "success": True,
            "data_type": "wells", 
            "total": len(wells),
            "results": wells[:20],  # Limitar a 20
            "message": f"Se encontraron {len(wells)} wells"
        }
        
    except CorvaAPIError as e:
        return {"success": False, "error": str(e)}

def get_kpis_workflow(user_query: str) -> Dict:
    """
    FUNCIÓN MODIFICADA - Flujo para obtener KPIs con validación Azure OpenAI
    
    Ahora confía en la validación del LLM en lugar de usar lógica de similitud manual
    """
    asset_name = extract_asset_name(user_query)
    
    if not asset_name:
        return {
            "success": False,
            "error": "No pude identificar el nombre del rig o well en tu consulta. ¿Podrías especificar el nombre exacto?"
        }
    
    print(f"🔍 DEBUG KPI - Asset extraído: '{asset_name}'")
    
    # Buscar el asset (ahora usa validación LLM)
    matches, search_type = search_asset_by_name(asset_name)
    
    print(f"🔍 DEBUG KPI - Tipo de búsqueda: {search_type}, Matches: {len(matches)}")
    
    if search_type == "error":
        return {"success": False, "error": ERROR_MESSAGE_ASSETS}
    
    elif search_type == "none" or len(matches) == 0:
        return {
            "success": False,
            "error": f"No se encontró ningún rig o well similar a '{asset_name}'. ¿Podrías verificar el nombre?"
        }
    
    elif search_type == "partial":
        # El LLM determinó que no hay match exacto - mostrar opciones al usuario
        options = []
        for asset_option in matches[:5]:
            name = asset_option.get("attributes", {}).get("name", "")
            asset_id = asset_option.get("id", "")
            options.append(f"- {name} (ID: {asset_id})")
        
        return {
            "success": False,
            "error": f"No encontré un match exacto para '{asset_name}' según el análisis del modelo IA. Candidatos encontrados:\n" + 
                    "\n".join(options) + "\n\nPor favor especifica el nombre exacto del asset que necesitas."
        }
    
    elif search_type == "exact" and len(matches) == 1:
        # LLM confirmó match exacto - proceder automáticamente
        asset = matches[0]
        asset_name_found = asset.get("attributes", {}).get("name", "")
        print(f"✅ DEBUG KPI - Match exacto validado por LLM: {asset_name_found}")
        
    else:
        return {
            "success": False,
            "error": f"No se pudo procesar la búsqueda para '{asset_name}'"
        }
    
    # CONTINUAR CON OBTENCIÓN DE KPIs (resto del código sin cambios)
    asset_id = asset.get("id")
    print(f"🔍 DEBUG KPI - Procediendo con asset: {asset_name_found} (ID: {asset_id})")
    
    try:
        params = {
            "limit": 30,
            "query": json.dumps({"asset_id": int(asset_id)}),
            "skip": 0,
            "sort": json.dumps({"timestamp": -1})
        }
        
        print(f"🔍 DEBUG KPI - Consultando KPIs con parámetros: {params}")
        
        kpi_data = make_corva_request_fixed("/data/ypf/kpi-conexiones/", params=params)
        
        print(f"🔍 DEBUG KPI - Respuesta KPI recibida: {type(kpi_data)}, len: {len(kpi_data) if isinstance(kpi_data, list) else 'N/A'}")
        
        if not kpi_data:
            return {
                "success": False,
                "error": f"No se encontraron datos KPI para {asset_name_found} (ID: {asset_id})"
            }
        
        # Mensaje de éxito con info de validación LLM
        success_message = f"Se encontraron {len(kpi_data) if isinstance(kpi_data, list) else 1} registros KPI para {asset_name_found} (validado por IA)"
        
        return {
            "success": True,
            "data_type": "kpis",
            "asset_name": asset_name_found,
            "asset_id": asset_id,
            "total": len(kpi_data) if isinstance(kpi_data, list) else 1,
            "results": kpi_data,
            "message": success_message
        }
        
    except CorvaAPIError as e:
        print(f"🔍 DEBUG KPI - CorvaAPIError: {str(e)}")
        return {"success": False, "error": f"Error al obtener KPIs: {str(e)}"}
    except Exception as e:
        print(f"🔍 DEBUG KPI - Error inesperado: {type(e).__name__}: {str(e)}")
        return {"success": False, "error": f"Error inesperado al obtener KPIs: {str(e)}"}

def get_wits_depth(user_query: str) -> Dict:
    """Obtiene profundidad actual del trepano - SIN VALIDACIÓN DE USUARIO"""
    asset_name = extract_asset_name(user_query)
    
    if not asset_name:
        return {
            "success": False,
            "error": "No pude identificar el nombre del rig o well. Especifica el asset para obtener profundidad."
        }
    
    # Buscar el asset
    matches, search_type = search_asset_by_name(asset_name)
    
    if search_type == "none" or len(matches) == 0:
        return {
            "success": False,
            "error": f"No se encontró un asset para '{asset_name}'. Especifica el nombre exacto."
        }
    
    # 🔧 FIX: Usar el mejor match disponible (sin pedir validación)
    if search_type == "partial":
        # Usar el mejor match pero informar la similitud
        best_match = matches[0]
        similarity = best_match.get("similarity", 0)
        
        if similarity >= 85.0:  # Si es buena similitud, usar automáticamente
            print(f"🔧 USANDO mejor match disponible: {best_match['attributes']['name']} ({similarity:.1f}%)")
            asset = best_match
        else:
            return {
                "success": False,
                "error": f"No se encontró un match suficientemente similar para '{asset_name}' (mejor: {similarity:.1f}%). Especifica el nombre exacto."
            }
    else:
        # Match exacto
        asset = matches[0]
    
    asset_id = asset.get("id")
    asset_name_found = asset.get("attributes", {}).get("name", "")
    
    try:
        params = {
            "skip": 0,
            "limit": 1,
            "query": json.dumps({"asset_id": int(asset_id)}),
            "sort": json.dumps({"timestamp": -1}),
            "fields": "data.hole_depth,data.bit_depth"
        }
        
        # 🔧 CORRECCIÓN PRINCIPAL: Usar CORVA_BASE_URL_DATA en lugar de CORVA_BASE_API_V1
        data = make_corva_request_fixed("/data/corva/wits/", params=params, base_url=CORVA_BASE_URL_DATA)
        
        return {
            "success": True,
            "data_type": "wits_depth",
            "asset_name": asset_name_found,
            "asset_id": asset_id,
            "total": len(data) if isinstance(data, list) else 1,
            "results": data,
            "message": f"Profundidad del trepano para {asset_name_found}"
        }
        
    except CorvaAPIError as e:
        return {"success": False, "error": f"Error al obtener profundidad: {str(e)}"}

def get_wits_summary(user_query: str) -> Dict:
    """Obtiene ROP actual del pozo - SIN VALIDACIÓN DE USUARIO"""
    asset_name = extract_asset_name(user_query)
    
    if not asset_name:
        return {
            "success": False,
            "error": "No pude identificar el nombre del rig o well. Especifica el asset para obtener ROP actual."
        }
    
    matches, search_type = search_asset_by_name(asset_name)
    
    if search_type == "none" or len(matches) == 0:
        return {
            "success": False,
            "error": f"No se encontró un asset para '{asset_name}'. Especifica el nombre exacto."
        }
    
    # 🔧 FIX: Usar el mejor match disponible (sin pedir validación)
    if search_type == "partial":
        # Usar el mejor match pero informar la similitud
        best_match = matches[0]
        similarity = best_match.get("similarity", 0)
        
        if similarity >= 85.0:  # Si es buena similitud, usar automáticamente
            print(f"🔧 USANDO mejor match disponible: {best_match['attributes']['name']} ({similarity:.1f}%)")
            asset = best_match
        else:
            return {
                "success": False,
                "error": f"No se encontró un match suficientemente similar para '{asset_name}' (mejor: {similarity:.1f}%). Especifica el nombre exacto."
            }
    else:
        # Match exacto
        asset = matches[0]
    
    asset_id = asset.get("id")
    asset_name_found = asset.get("attributes", {}).get("name", "")
    
    try:
        params = {
            "skip": 0,
            "limit": 1,
            "query": json.dumps({"asset_id": int(asset_id)}),
            "sort": json.dumps({"timestamp": -1}),
            "fields": "data.rop_mean"
        }
        
        data = make_corva_request_fixed("/data/corva/wits.summary-1ft/", params=params, base_url=CORVA_BASE_URL_DATA)
        
        return {
            "success": True,
            "data_type": "wits_summary",
            "asset_name": asset_name_found,
            "asset_id": asset_id,
            "total": len(data) if isinstance(data, list) else 1,
            "results": data,
            "message": f"ROP actual para {asset_name_found}"
        }
        
    except CorvaAPIError as e:
        return {"success": False, "error": f"Error al obtener ROP actual: {str(e)}"}

def get_metrics_rop(user_query: str, well_section: str = "Production Lateral") -> Dict:
    """Obtiene ROP promedio por sección del pozo - SIN VALIDACIÓN DE USUARIO"""
    asset_name = extract_asset_name(user_query)
    
    if not asset_name:
        return {
            "success": False,
            "error": "No pude identificar el nombre del rig o well. Especifica el asset para obtener métricas ROP."
        }
    
    matches, search_type = search_asset_by_name(asset_name)
    
    if search_type == "none" or len(matches) == 0:
        return {
            "success": False,
            "error": f"No se encontró un asset para '{asset_name}'. Especifica el nombre exacto."
        }
    
    # 🔧 FIX: Usar el mejor match disponible (sin pedir validación)
    if search_type == "partial":
        # Usar el mejor match pero informar la similitud
        best_match = matches[0]
        similarity = best_match.get("similarity", 0)
        
        if similarity >= 85.0:  # Si es buena similitud, usar automáticamente
            print(f"🔧 USANDO mejor match disponible: {best_match['attributes']['name']} ({similarity:.1f}%)")
            asset = best_match
        else:
            return {
                "success": False,
                "error": f"No se encontró un match suficientemente similar para '{asset_name}' (mejor: {similarity:.1f}%). Especifica el nombre exacto."
            }
    else:
        # Match exacto
        asset = matches[0]
    
    asset_id = asset.get("id")
    asset_name_found = asset.get("attributes", {}).get("name", "")
    
    try:
        query_obj = {
            "asset_id": int(asset_id),
            "data.key": "rop",
            "data.type": "well_section",
            "data.well_section": well_section
        }
        
        params = {
            "skip": 0,
            "limit": 10,
            "query": json.dumps(query_obj),
            "sort": json.dumps({"timestamp": 1}),
            "fields": "data.value,data.key,data.type,data.well_section"
        }
        
        data = make_corva_request_fixed("/data/corva/metrics/", params=params, base_url=CORVA_BASE_URL_DATA)
        
        return {
            "success": True,
            "data_type": "metrics_rop",
            "asset_name": asset_name_found,
            "asset_id": asset_id,
            "well_section": well_section,
            "total": len(data) if isinstance(data, list) else 1,
            "results": data,
            "message": f"Métricas ROP para {asset_name_found} en sección {well_section}"
        }
        
    except CorvaAPIError as e:
        return {"success": False, "error": f"Error al obtener métricas ROP: {str(e)}"}

def get_operations(user_query: str, operation_filter: str = "Weight To Weight") -> Dict:
    """Obtiene tiempos de operaciones de conexión - SIN VALIDACIÓN DE USUARIO"""
    asset_name = extract_asset_name(user_query)
    
    if not asset_name:
        return {
            "success": False,
            "error": "No pude identificar el nombre del rig o well. Especifica el asset para obtener operaciones."
        }
    
    matches, search_type = search_asset_by_name(asset_name)
    
    if search_type == "none" or len(matches) == 0:
        return {
            "success": False,
            "error": f"No se encontró un asset para '{asset_name}'. Especifica el nombre exacto."
        }
    
    # 🔧 FIX: Usar el mejor match disponible (sin pedir validación)
    if search_type == "partial":
        # Usar el mejor match pero informar la similitud
        best_match = matches[0]
        similarity = best_match.get("similarity", 0)
        
        if similarity >= 85.0:  # Si es buena similitud, usar automáticamente
            print(f"🔧 USANDO mejor match disponible: {best_match['attributes']['name']} ({similarity:.1f}%)")
            asset = best_match
        else:
            return {
                "success": False,
                "error": f"No se encontró un match suficientemente similar para '{asset_name}' (mejor: {similarity:.1f}%). Especifica el nombre exacto."
            }
    else:
        # Match exacto
        asset = matches[0]
    
    asset_id = asset.get("id")
    asset_name_found = asset.get("attributes", {}).get("name", "")
    
    try:
        query_obj = {"asset_id": int(asset_id)}
        
        # Aplicar filtro de operación
        filter_patterns = {
            "Weight To Weight": "Weight To Weight",
            "Connection": "Connection",
            "Drilling": "Drilling"
        }
        
        pattern = filter_patterns.get(operation_filter, "Weight To Weight")
        query_obj["data.operation_name"] = {
            "$regex": pattern,
            "$options": "i"
        }
        
        params = {
            "skip": 0,
            "limit": 15,
            "query": json.dumps(query_obj),
            "sort": json.dumps({"timestamp": -1}),
            "fields": "data.shift,data.operation_name,data.operation_time,data.well_section,data.start_depth,data.end_depth"
        }
        
        data = make_corva_request_fixed("/data/corva/operations/", params=params, base_url=CORVA_BASE_URL_DATA)
        
        return {
            "success": True,
            "data_type": "operations",
            "asset_name": asset_name_found,
            "asset_id": asset_id,
            "operation_filter": operation_filter,
            "total": len(data) if isinstance(data, list) else 1,
            "results": data,
            "message": f"Operaciones de {operation_filter} para {asset_name_found}"
        }
        
    except CorvaAPIError as e:
        return {"success": False, "error": f"Error al obtener operaciones: {str(e)}"}
    

def detect_high_confidence_match(user_input: str, found_assets: List[Dict]) -> Tuple[bool, Dict]:
    """
    Detecta si hay un match de alta confianza que puede proceder automáticamente
    
    Args:
        user_input (str): Entrada del usuario
        found_assets (List[Dict]): Assets encontrados ordenados por priority_score
        
    Returns:
        Tuple[bool, Dict]: (es_alta_confianza, mejor_asset)
    """
    if not found_assets or len(found_assets) < 1:
        return False, {}
    
    first_asset = found_assets[0]
    first_priority = first_asset.get('priority_score', 0)
    first_match = first_asset.get('match_score', 0)
    first_name = first_asset.get('well_name', '') or first_asset.get('attributes', {}).get('name', '')
    
    print("🎯 EVALUANDO HIGH CONFIDENCE:")
    print(f"   Input: '{user_input}'")
    print(f"   Primer resultado: '{first_name}' (Priority: {first_priority:.1f}, Match: {first_match:.1f})")
    
    # CRITERIO 1: Score muy alto (95%+)
    high_score = first_match >= 95.0
    
    # CRITERIO 2: Gap significativo con segundo resultado
    significant_gap = True
    if len(found_assets) > 1:
        second_priority = found_assets[1].get('priority_score', 0)
        priority_gap = first_priority - second_priority
        significant_gap = priority_gap >= 8.0  # Gap de 8+ puntos
        print(f"   Gap con segundo: {priority_gap:.1f} (required: 8.0)")
    
    # CRITERIO 3: Match exacto en nombres críticos
    user_lower = user_input.lower()
    name_lower = first_name.lower() 
    exact_substring_match = user_lower in name_lower or name_lower in user_lower
    
    # CRITERIO 4: Recencia superior (bonus por ser más activo)
    recency_bonus = first_priority > first_match + 5  # Tiene bonus de recencia significativo
    
    print(f"   Criterios: Score alto: {high_score}, Gap: {significant_gap}, Substring: {exact_substring_match}, Recencia: {recency_bonus}")
    
    # DECISIÓN DE ALTA CONFIANZA
    is_high_confidence = (
        high_score and significant_gap and exact_substring_match
    ) or (
        first_match >= 98.0 and exact_substring_match  # Score casi perfecto + substring match
    ) or (
        first_match >= 100.0 and significant_gap  # Score perfecto + gap
    )
    
    if is_high_confidence:
        print(f"✅ HIGH CONFIDENCE DETECTADO - Procediendo automáticamente con: {first_name}")
        return True, first_asset
    else:
        print("⚠️ No hay alta confianza - Requiere validación del usuario")
        return False, {}

def validate_asset_match_with_llm(user_input: str, found_assets: List[Dict]) -> Tuple[str, List[Dict]]:
    """
    VERSIÓN CON HIGH CONFIDENCE - Usa Azure OpenAI para validar pero permite auto-match en casos claros
    
    Args:
        user_input (str): Entrada original del usuario
        found_assets (List[Dict]): Lista de assets encontrados con priority_score
        
    Returns:
        Tuple[str, List[Dict]]: (tipo_match, assets_validados)
        - tipo_match: "exact" (procede automáticamente), "partial" (requiere validación), "none" (sin matches)
        - assets_validados: lista ordenada por relevancia
    """
    if not found_assets or not user_input:
        return "none", []
    
    # 🚀 NUEVO: Verificar si hay alta confianza ANTES de llamar al LLM
    is_high_confidence, best_asset = detect_high_confidence_match(user_input, found_assets)
    
    if is_high_confidence:
        # Proceder automáticamente sin validación del usuario
        print("🎯 AUTO-MATCH por alta confianza")
        return "exact", [best_asset]
    
    # Si no hay alta confianza, continuar con validación LLM (código existente)
    print("🤖 Enviando al LLM para validación (no hay alta confianza automática)")
    
    # Preparar lista de nombres para el LLM con información de recencia
    asset_names = []
    for i, asset in enumerate(found_assets):
        name = asset.get("attributes", {}).get("name", "")
        last_active = asset.get("last_active_at", "N/A")
        priority_score = asset.get("priority_score", 0)
        
        if last_active != "N/A" and "T" in last_active:
            last_active = last_active[:10]
        
        if name:
            asset_names.append(f"{i+1}. {name} (Activo: {last_active}, Priority: {priority_score:.1f})")
    
    if not asset_names:
        return "none", []
    
    # Prompt MEJORADO para ser menos conservador en casos claros
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Eres un experto en validación de nombres de assets petroleros (rigs y wells/pozos) con enfoque en PRACTICIDAD.

Tu tarea es determinar si alguno de los assets encontrados coincide con lo que el usuario busca.

IMPORTANTE: Los assets pueden ser:
- POZOS/WELLS: Con nombres como "ADCH5 / SLB #1 / Viewer", "LCav-805(h)", "YPF.Nq.LCav-177h", etc.
- RIGS: Con nombres como "DLS 168", "Nabors F35", "H&P T430", "DLS 169", etc.
- COMBINADOS: Formato "Pozo (Rig: NombreRig)" que muestra ambos

CRITERIOS PARA MATCH EXACTO (SÉ MÁS PERMISIVO):
- Si el primer asset tiene Priority Score alto (>110) Y contiene claramente el término buscado → EXACT_MATCH
- Para RIGS: "DLS 168" vs "DLS-168" vs variaciones menores → EXACT_MATCH
- Para POZOS: Si el core del nombre coincide (ej: "LCav-415" en "YPF.Nq.LCav-415(h)") → EXACT_MATCH
- Si hay clara superioridad del primer resultado (Priority >10 puntos sobre segundo) → EXACT_MATCH

**NUEVA REGLA - SER MENOS CONSERVADOR:**
- Si el primer asset es OBVIAMENTE el correcto (alta similitud + alta prioridad), marcar como EXACT_MATCH
- Solo usar MULTIPLE_MATCHES cuando realmente hay ambigüedad significativa
- Priorizar la UTILIDAD sobre la perfección absoluta

INSTRUCCIONES:
1. Si el primer asset es CLARAMENTE el correcto → "EXACT_MATCH" 
2. Solo si hay verdadera ambigüedad → "MULTIPLE_MATCHES"  
3. Si nada es relevante → "NO_EXACT_MATCH"

Formato de respuesta JSON:
{{
  "decision": "EXACT_MATCH|MULTIPLE_MATCHES|NO_EXACT_MATCH",
  "exact_match_number": 1,
  "relevant_matches": [1, 2, 3, 4, 5],
  "reasoning": "explicación breve priorizando utilidad práctica"
}}"""),
        ("user", """Usuario busca: "{user_input}"

Assets encontrados (ordenados por prioridad + recencia):
{asset_list}

El primer resultado tiene Priority Score alto y parece relevante. ¿Es un match exacto suficientemente claro para proceder? Sé práctico, no perfeccionista.""")
    ])
    
    try:
        chain = prompt | validation_llm | StrOutputParser()
        response = chain.invoke({
            "user_input": user_input,
            "asset_list": "\n".join(asset_names)
        })
        
        # Extraer JSON de la respuesta
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            
            decision = result.get("decision", "NO_EXACT_MATCH")
            exact_match_number = result.get("exact_match_number")
            relevant_matches = result.get("relevant_matches", [])
            reasoning = result.get("reasoning", "")
            
            print(f"🤖 LLM Decision: {decision} - {reasoning}")
            
            if decision == "EXACT_MATCH" and exact_match_number:
                # Un match exacto - devolver solo ese asset
                if 1 <= exact_match_number <= len(found_assets):
                    exact_asset = found_assets[exact_match_number - 1]
                    return "exact", [exact_asset]
            
            elif decision == "MULTIPLE_MATCHES" and relevant_matches:
                # Múltiples matches - devolver ordenados por relevancia + recencia
                ordered_assets = []
                for num in relevant_matches:
                    if 1 <= num <= len(found_assets):
                        ordered_assets.append(found_assets[num - 1])
                return "partial", ordered_assets
            
            # NO_EXACT_MATCH o cualquier otro caso
            if relevant_matches:
                ordered_assets = []
                for num in relevant_matches:
                    if 1 <= num <= len(found_assets):
                        ordered_assets.append(found_assets[num - 1])
                return "partial", ordered_assets
            else:
                # Si no hay relevant_matches, devolver los primeros 5 más prioritarios
                return "partial", found_assets[:5]
        
        else:
            print(f"⚠️ No se pudo extraer JSON de la respuesta del LLM: {response}")
            return "partial", found_assets[:5]
            
    except Exception as e:
        print(f"❌ Error en validación con LLM mejorada: {e}")
        # Fallback a lógica original en caso de error
        return "partial", found_assets[:5]

def filter_by_recent_activity(asset: dict, cutoff_date: str = "2025-07-01") -> bool:
    """
    Filtra assets por actividad reciente a partir de una fecha específica
    
    Args:
        asset: Asset a evaluar
        cutoff_date: Fecha de corte en formato "YYYY-MM-DD" 
        
    Returns:
        bool: True si el asset está activo desde la fecha de corte
    """
    try:
        # Obtener last_active_at del asset
        last_active_at = (asset.get("last_active_at") or 
                         asset.get("data", {}).get("last_active_at"))
        
        if not last_active_at:
            # Si no tiene fecha, no incluir (ser más estricto)
            return False
        
        # Convertir string de fecha a datetime para comparar
        if isinstance(last_active_at, str):
            # Formato típico: "2025-07-20T20:05:51.000"
            if "T" in last_active_at:
                asset_date = datetime.fromisoformat(last_active_at.replace("Z", "").split(".")[0])
            else:
                # Si es solo fecha: "2025-07-20"
                asset_date = datetime.strptime(last_active_at[:10], "%Y-%m-%d")
        else:
            return False
        
        # Fecha de corte
        cutoff = datetime.strptime(cutoff_date, "%Y-%m-%d")
        
        # Retornar True si el asset estuvo activo desde la fecha de corte
        is_recent = asset_date >= cutoff
        
        if is_recent:
            print(f"✅ Asset activo reciente: {asset.get('name', 'N/A')[:50]} - {last_active_at[:10]}")
        
        return is_recent
        
    except Exception as e:
        print(f"⚠️ Error parseando fecha para asset {asset.get('name', 'N/A')}: {e}")
        return False

def detect_fracking_metric(user_query: str) -> Tuple[Optional[str], Optional[Dict]]:
    """
    Detecta qué métrica de fracturamiento específica está solicitando el usuario
    
    Args:
        user_query: Consulta del usuario
        
    Returns:
        tuple: (metric_key, metric_info) o (None, None) si no se detecta métrica específica
    """
    query_lower = user_query.lower()
    
    # Buscar la métrica más específica basada en keywords
    best_match = None
    best_score = 0
    
    for metric_key, metric_info in FRACKING_METRICS_MAP.items():
        for keyword in metric_info["keywords"]:
            # Calcular similitud con la consulta
            similarity = fuzz.partial_ratio(keyword, query_lower)
            
            # Si hay match directo de palabras clave, priorizar
            if keyword in query_lower:
                similarity += 20
            
            if similarity > best_score and similarity >= 70:
                best_match = metric_key
                best_score = similarity
                
    if best_match:
        return best_match, FRACKING_METRICS_MAP[best_match]
    
    return None, None

def build_metrics_query(asset_id: str, metric_key: str, stage_number: Optional[int] = None) -> Dict:
    """
    Construye la query dinámica para el endpoint de métricas agregadas
    
    Args:
        asset_id: ID del asset
        metric_key: Clave de la métrica (ej: "total_slurry_volume")
        stage_number: Número de etapa específica (opcional)
        
    Returns:
        dict: Query parameters para el endpoint
    """
    # Match básico
    match_query = {
        "company_id": 375,
        "data.asset_id": {"$in": [int(asset_id)]},
        "data.key": metric_key,
        "data.type": "stage"
    }
    
    # Si se especifica una etapa particular
    if stage_number is not None:
        match_query["data.stage_number"] = stage_number
    
    # Projection para campos que necesitamos
    project_query = {
        "_id": 0,
        "data.asset_id": 1,
        "data.stage_number": 1,
        "data.key": 1,
        "data.value": 1,
        "timestamp": 1
    }
    
    # Sort por número de etapa
    sort_query = {"data.stage_number": 1}
    
    return {
        "match": json.dumps(match_query),
        "project": json.dumps(project_query),
        "sort": json.dumps(sort_query),
        "limit": 100
    }

def get_asset_detailed_info(user_query: str) -> Dict:
    """
    Obtiene información completa y detallada de un asset específico usando la misma lógica de matching
    que search_asset_by_name pero devolviendo toda la información disponible del endpoint.
    
    Esta función está diseñada para responder preguntas como:
    - "Dame información del DLS 168"
    - "Detalles del LCav-415"  
    - "Información completa del rig Nabors F35"
    - "Datos del pozo YPF.Nq.LCav-415(h)"
    
    Args:
        user_query (str): Consulta del usuario que incluye el nombre del asset
        
    Returns:
        Dict: Información completa del asset encontrado o error
    """
    try:
        # 1. EXTRAER NOMBRE DEL ASSET de la consulta
        asset_name = extract_asset_name(user_query)
        
        if not asset_name:
            return {
                "success": False,
                "error": "No pude identificar el nombre del asset en tu consulta. Especifica el nombre del rig o well que necesitas."
            }
        
        print(f"🔍 DEBUG INFO - Asset extraído de consulta: '{asset_name}'")
        
        # 2. USAR LA MISMA LÓGICA DE BÚSQUEDA que search_asset_by_name
        matches, search_type = search_asset_by_name(asset_name)
        
        print(f"🔍 DEBUG INFO - Tipo de búsqueda: {search_type}, Matches: {len(matches)}")
        
        if search_type == "error":
            return {"success": False, "error": ERROR_MESSAGE_ASSETS}
        
        elif search_type == "none" or len(matches) == 0:
            return {
                "success": False,
                "error": f"No se encontró información para '{asset_name}'. Verifica el nombre del asset."  
            }
        
        elif search_type == "partial":
            # Ofrecer opciones al usuario
            options = []
            for asset_option in matches[:5]:
                name = asset_option.get("attributes", {}).get("name", "")
                asset_id = asset_option.get("id", "")
                last_active = asset_option.get("last_active_at", "N/A")
                if last_active != "N/A" and "T" in last_active:
                    last_active = last_active[:10]
                options.append(f"- {name} (ID: {asset_id}, Activo: {last_active})")
            
            return {
                "success": False,
                "error": f"Encontré múltiples assets para '{asset_name}'. Especifica cuál necesitas:\n" + 
                        "\n".join(options)
            }
        
        elif search_type == "exact" and len(matches) == 1:
            # Match exacto encontrado - proceder con información completa
            asset = matches[0]
            asset_id = asset.get("id")
            asset_name_found = asset.get("attributes", {}).get("name", "")
            print(f"✅ DEBUG INFO - Match exacto encontrado: {asset_name_found} (ID: {asset_id})")
            
        else:
            return {
                "success": False,
                "error": f"No se pudo procesar la búsqueda para '{asset_name}'"  
            }
        
        # 3. OBTENER INFORMACIÓN COMPLETA DEL ASSET del endpoint original
        original_asset_id = asset.get("original_id", asset_id)
        
        # Re-consultar el endpoint para obtener el JSON completo
        params = {
            "limit": 1000,
            "query": json.dumps({"company_id": 375}),
            "sort": json.dumps({"name": 1}),
            "skip": 0
        }
        
        data = make_corva_request_fixed(CORVA_ASSETS_URL, params=params, base_url=CORVA_BASE_URL_DATA)
        
        # Encontrar el asset específico en la respuesta completa
        if isinstance(data, list):
            assets = data
        elif isinstance(data, dict):
            assets = data.get("data", data.get("results", []))
        else:
            return {"success": False, "error": "Error obteniendo información detallada del asset"}
        
        # Buscar por ID el asset específico
        target_asset = None
        for raw_asset in assets:
            if not raw_asset or not isinstance(raw_asset, dict):
                continue
                
            raw_id = str(raw_asset.get("id", "")) or str(raw_asset.get("asset_id", "")) or str(raw_asset.get("_id", ""))
            if raw_id == str(original_asset_id) or raw_id == str(asset_id):
                target_asset = raw_asset
                break
        
        if not target_asset:
            return {
                "success": False,
                "error": f"No se pudo obtener información detallada para el asset con ID {asset_id}"
            }
        
        # 4. FORMATEAR INFORMACIÓN COMPLETA DE MANERA LEGIBLE
        formatted_info = format_asset_detailed_info(target_asset, asset_name_found)
        
        return {
            "success": True,
            "data_type": "asset_detailed_info",
            "asset_name": asset_name_found,
            "asset_id": asset_id,
            "query_matched": asset_name,
            "detailed_info": formatted_info,
            "raw_data": target_asset,  # Para debugging si es necesario
            "message": f"Información completa obtenida para {asset_name_found}"
        }
        
    except Exception as e:
        print(f"❌ Error en get_asset_detailed_info: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return {"success": False, "error": f"Error obteniendo información detallada: {str(e)}"}

def format_asset_detailed_info(asset_data: Dict, asset_name: str) -> str:
    """
    Formatea la información completa del asset de manera legible para el usuario
    
    Args:
        asset_data (Dict): Datos completos del asset del endpoint
        asset_name (str): Nombre del asset para contexto
        
    Returns:
        str: Información formateada y legible
    """
    try:
        info_lines = []
        info_lines.append(f"📊 **INFORMACIÓN COMPLETA DE {asset_name}**")
        info_lines.append("=" * 60)
        
        # INFORMACIÓN BÁSICA
        info_lines.append("\n🏷️ **INFORMACIÓN BÁSICA:**")
        info_lines.append(f"- **ID del Asset:** {asset_data.get('id', 'N/A')}")
        info_lines.append(f"- **Nombre:** {asset_data.get('name', 'N/A')}")
        info_lines.append(f"- **Tipo de Asset:** {asset_data.get('asset_type', 'N/A')}")
        info_lines.append(f"- **Compañía ID:** {asset_data.get('company_id', 'N/A')}")
        
        # INFORMACIÓN DEL RIG (si aplica)
        rig_info = asset_data.get('rig', {})
        if rig_info and isinstance(rig_info, dict):
            info_lines.append("\n⚙️ **INFORMACIÓN DEL RIG:**")
            info_lines.append(f"- **Nombre del Rig:** {rig_info.get('name', 'N/A')}")
            info_lines.append(f"- **Contratista:** {rig_info.get('contractor', 'N/A')}")
            info_lines.append(f"- **ID del Rig:** {rig_info.get('id', 'N/A')}")
        
        # ESTADO Y ACTIVIDAD
        info_lines.append("\n📅 **ESTADO Y ACTIVIDAD:**")
        last_active = asset_data.get('last_active_at', 'N/A')
        if last_active != "N/A" and "T" in last_active:
            formatted_date = last_active[:19].replace("T", " ")
            info_lines.append(f"- **Última Actividad:** {formatted_date}")
        else:
            info_lines.append(f"- **Última Actividad:** {last_active}")
        
        info_lines.append(f"- **Estado:** {asset_data.get('status', 'N/A')}")
        
        # ACTIVE CHILD (configuración activa)
        active_child = asset_data.get('active_child', {})
        if active_child and isinstance(active_child, dict):
            info_lines.append(f"- **Configuración Activa ID:** {active_child.get('id', 'N/A')}")
            info_lines.append(f"- **Nombre Configuración:** {active_child.get('name', 'N/A')}")
        
        # UBICACIÓN (si disponible)
        location = asset_data.get('location', {})
        if location and isinstance(location, dict):
            info_lines.append("\n📍 **UBICACIÓN:**")
            info_lines.append(f"- **Ubicación:** {location.get('name', 'N/A')}")
            info_lines.append(f"- **Coordenadas:** {location.get('coordinates', 'N/A')}")
        
        # DATOS ADICIONALES
        data_section = asset_data.get('data', {})
        if data_section and isinstance(data_section, dict) and len(data_section) > 0:
            info_lines.append("\n🔧 **CONFIGURACIÓN Y DATOS TÉCNICOS:**")
            
            # Mostrar algunos campos importantes si existen
            important_fields = [
                'well_type', 'drilling_contractor', 'operator', 'field', 'pad',
                'spud_date', 'td_date', 'completion_date', 'first_production',
                'api_number', 'permit_number', 'measured_depth', 'true_vertical_depth'
            ]
            
            for field in important_fields:
                if field in data_section and data_section[field]:
                    formatted_field = field.replace('_', ' ').title()
                    info_lines.append(f"- **{formatted_field}:** {data_section[field]}")
            
            # Si hay otros campos, mostrar un resumen
            other_fields = [k for k in data_section.keys() if k not in important_fields]
            if other_fields:
                info_lines.append(f"- **Otros campos disponibles:** {', '.join(other_fields[:10])}")
                if len(other_fields) > 10:
                    info_lines.append(f"  (y {len(other_fields) - 10} campos más)")
        
        # METADATOS DEL SISTEMA
        info_lines.append("\n🕒 **METADATOS:**")
        info_lines.append(f"- **Creado:** {asset_data.get('created_at', 'N/A')}")
        info_lines.append(f"- **Actualizado:** {asset_data.get('updated_at', 'N/A')}")
        
        # NOTA SOBRE DATOS ADICIONALES
        info_lines.append("\n💡 **Nota:** Esta información proviene del endpoint de assets de Corva.")
        info_lines.append("Para datos operacionales específicos (KPIs, profundidad, etc.), usa las herramientas especializadas.")
        
        return "\n".join(info_lines)
        
    except Exception as e:
        print(f"❌ Error formateando información del asset: {e}")
        return "Error formateando la información del asset. Datos raw disponibles en la respuesta."

def get_fracking_metrics(user_query: str) -> Dict:
    """
    Obtiene métricas de fracturamiento hidráulico para un asset específico
    
    LÓGICA:
    1. Busca y valida el asset usando la lógica existente
    2. Detecta qué métrica específica se solicita
    3. Construye la query dinámica
    4. Ejecuta la consulta al endpoint de métricas agregadas
    5. Formatea la respuesta
    
    Args:
        user_query: Consulta del usuario que incluye el asset y tipo de métrica
        
    Returns:
        dict: Resultado formateado con las métricas encontradas
    """
    try:
        # PASO 1: EXTRAER NOMBRE DEL ASSET (usando lógica existente)
        asset_name = extract_asset_name(user_query)
        
        if not asset_name:
            return {
                "success": False,
                "error": "No pude identificar el nombre del rig o well en tu consulta. " +
                        "Especifica el asset para obtener métricas de fracturamiento."
            }
        
        print(f"🔍 DEBUG METRICS - Asset extraído: '{asset_name}'")
        
        # PASO 2: DETECTAR MÉTRICA ESPECÍFICA
        metric_key, metric_info = detect_fracking_metric(user_query)
        
        if not metric_key:
            # Si no se detecta métrica específica, listar métricas disponibles
            available_metrics = [info["description"] for info in FRACKING_METRICS_MAP.values()]
            return {
                "success": False,
                "error": f"No pude identificar qué métrica de fracturamiento necesitas para '{asset_name}'. " +
                        "Métricas disponibles:\n" + "\n".join([f"- {metric}" for metric in available_metrics[:5]]) +
                        "\n\nEspecifica el tipo de métrica que necesitas."
            }
        
        print(f"🔍 DEBUG METRICS - Métrica detectada: {metric_info['description']} ({metric_key})")
        
        # PASO 3: BUSCAR Y VALIDAR ASSET (usando lógica existente)
        matches, search_type = search_asset_by_name(asset_name)
        
        if search_type == "error":
            return {"success": False, "error": ERROR_MESSAGE_ASSETS}
        
        elif search_type == "none" or len(matches) == 0:
            return {
                "success": False,
                "error": f"No se encontró un asset para '{asset_name}'. Especifica el nombre exacto."
            }
        
        elif search_type == "partial":
            # El LLM determinó que no hay match exacto - mostrar opciones
            options = []
            for asset_option in matches[:5]:
                name = asset_option.get("attributes", {}).get("name", "")
                asset_id = asset_option.get("id", "")
                options.append(f"- {name} (ID: {asset_id})")
            
            return {
                "success": False,
                "error": f"No encontré un match exacto para '{asset_name}' según el análisis del modelo IA. " +
                        "Candidatos encontrados:\n" + "\n".join(options) + 
                        "\n\nPor favor especifica el nombre exacto del asset que necesitas."
            }
        
        elif search_type == "exact" and len(matches) == 1:
            # LLM confirmó match exacto - proceder automáticamente
            asset = matches[0]
            asset_name_found = asset.get("attributes", {}).get("name", "")
            asset_id = asset.get("id")
            print(f"✅ DEBUG METRICS - Match exacto validado: {asset_name_found} (ID: {asset_id})")
            
        else:
            return {
                "success": False,
                "error": f"No se pudo procesar la búsqueda para '{asset_name}'"
            }
        
        # PASO 4: DETECTAR ETAPA ESPECÍFICA (opcional)
        stage_number = None
        stage_match = re.search(r'etapa\s+(\d+)', user_query.lower())
        if stage_match:
            stage_number = int(stage_match.group(1))
            print(f"🔍 DEBUG METRICS - Etapa específica detectada: {stage_number}")
        
        # PASO 5: CONSTRUIR QUERY DINÁMICA
        query_params = build_metrics_query(asset_id, metric_info["key"], stage_number)
        
        print(f"🔍 DEBUG METRICS - Query construida: {query_params}")
        
        # PASO 6: EJECUTAR CONSULTA AL ENDPOINT
        try:
            endpoint = "/data/corva/metrics/aggregate/"
            metrics_data = make_corva_request_fixed(endpoint, params=query_params, base_url=CORVA_BASE_URL_DATA)
            
            print(f"🔍 DEBUG METRICS - Respuesta recibida: {type(metrics_data)}, registros: {len(metrics_data) if isinstance(metrics_data, list) else 'N/A'}")
            
            if not metrics_data:
                return {
                    "success": False,
                    "error": f"No se encontraron datos de '{metric_info['description']}' para {asset_name_found} (ID: {asset_id})"
                }
            
            # PASO 7: FORMATEAR RESPUESTA
            total_stages = len(metrics_data) if isinstance(metrics_data, list) else 1
            
            return {
                "success": True,
                "data_type": "fracking_metrics",
                "asset_name": asset_name_found,
                "asset_id": asset_id,
                "metric_type": metric_info["description"],
                "metric_key": metric_info["key"], 
                "unit": metric_info["unit"],
                "stage_filter": stage_number,
                "total_stages": len(metrics_data) if isinstance(metrics_data, list) else 1,
                "results": metrics_data,
                "message": f"Métricas de '{metric_info['description']}' para {asset_name_found}" + (f" - Etapa {stage_number}" if stage_number else f" - {total_stages} etapas")}
            
        except Exception as api_error:
            print(f"🔍 DEBUG METRICS - Error en API: {str(api_error)}")
            return {"success": False, "error": f"Error al obtener métricas del endpoint: {str(api_error)}"}
            
    except Exception as e:
        print(f"❌ Error general en get_fracking_metrics: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return {"success": False, "error": f"Error procesando métricas de fracturamiento: {str(e)}"}

def format_fracking_metrics_response(result: Dict) -> str:
    """
    Formatea la respuesta de métricas de fracturamiento para el agente
    
    Args:
        result: Resultado de get_fracking_metrics()
        
    Returns:
        str: Respuesta formateada para mostrar al usuario
    """
    if not result.get("success"):
        return f"❌ Error: {result.get('error', 'Error desconocido')}"
    
    asset_name = result.get("asset_name", "")
    metric_type = result.get("metric_type", "")
    unit = result.get("unit", "")
    total_stages = result.get("total_stages", 0)
    message = result.get("message", "")
    
    response = f"📊 **{metric_type.upper()}** para {asset_name}\n"
    response += f"🎯 {message}\n"
    response += f"📏 Unidad: {unit}\n\n"
    
    # Mostrar datos por etapa
    metrics_data = result.get("results", [])
    
    if isinstance(metrics_data, list) and len(metrics_data) > 0:
        response += f"📈 **RESULTADOS POR ETAPA** (Total: {total_stages} etapas):\n"
        response += "=" * 50 + "\n"
        
        # Mostrar hasta las primeras 10 etapas para no sobrecargar
        for i, stage_data in enumerate(metrics_data[:10], 1):
            if isinstance(stage_data, dict):
                data_section = stage_data.get("data", {})
                stage_num = data_section.get("stage_number", "N/A")
                value = data_section.get("value", "N/A")
                
                # Formatear el valor según la unidad
                if isinstance(value, (int, float)) and value != "N/A":
                    if unit in ["bbl", "gal"]:
                        formatted_value = f"{value:,.2f} {unit}"
                    elif unit == "lbs":
                        formatted_value = f"{value:,.1f} {unit}" 
                    elif unit == "min":
                        formatted_value = f"{value:.2f} {unit}"
                    else:
                        formatted_value = f"{value} {unit}"
                else:
                    formatted_value = f"{value} {unit}"
                
                response += f"• **Etapa {stage_num}:** {formatted_value}\n"
        
        # Si hay más etapas, indicarlo
        if len(metrics_data) > 10:
            response += f"... y {len(metrics_data) - 10} etapas más\n"
        
        # Estadísticas rápidas si hay datos numéricos
        numeric_values = []
        for stage_data in metrics_data:
            if isinstance(stage_data, dict):
                value = stage_data.get("data", {}).get("value")
                if isinstance(value, (int, float)):
                    numeric_values.append(value)
        
        if numeric_values:
            total_value = sum(numeric_values)
            avg_value = total_value / len(numeric_values)
            max_value = max(numeric_values)
            min_value = min(numeric_values)
            
            response += "\n📊 **ESTADÍSTICAS:**\n"
            response += f"• Total acumulado: {total_value:,.2f} {unit}\n"
            response += f"• Promedio por etapa: {avg_value:,.2f} {unit}\n"
            response += f"• Máximo: {max_value:,.2f} {unit}\n"
            response += f"• Mínimo: {min_value:,.2f} {unit}\n"
            
    else:
        response += "⚠️ No se encontraron datos de etapas específicas.\n"
    
    return response


def format_response_for_agent(result: Dict) -> str:
    """
    Formatea la respuesta para el agente de IA
    """
    if not result.get("success"):
        return f"Error: {result.get('error', 'Error desconocido')}"
    
    data_type = result.get("data_type")
    message = result.get("message", "")
    total = result.get("total", 0)
    
    if data_type == "alerts":
        response = f"📢 ALERTAS ({total} total):\n{message}\n\n"
        for i, alert in enumerate(result.get("results", [])[:5], 1):
            response += f"{i}. {alert}\n"
        
    elif data_type == "rigs":
        response = f"🔧 RIGS ({total} total):\n{message}\n\n"
        for i, rig in enumerate(result.get("results", [])[:5], 1):
            response += f"{i}. {rig}\n"
        
    elif data_type == "wells":
        response = f"🏭 WELLS ({total} total):\n{message}\n\n"
        for i, well in enumerate(result.get("results", [])[:5], 1):
            response += f"{i}. {well}\n"
            
    elif data_type == "kpis":
        asset_name = result.get("asset_name", "")
        response = f"📊 KPIs para {asset_name} ({total} registros):\n{message}\n\n"
        
        kpis = result.get("results", [])
        if kpis:
            latest = kpis[0] if isinstance(kpis, list) else kpis
            if isinstance(latest, dict):
                data_section = latest.get("data", {})
                response += f"Último registro:\n"
                response += f"- Operación: {data_section.get('operation_name', 'N/A')}\n"
                response += f"- KPI Valor: {data_section.get('kpi_valor', 'N/A')}\n"
                response += f"- Timestamp: {latest.get('timestamp', 'N/A')}\n\n"
                
    # NUEVAS RESPUESTAS
    elif data_type == "wits_depth":
        asset_name = result.get("asset_name", "")
        response = f"🎯 PROFUNDIDAD TREPANO para {asset_name}:\n{message}\n\n"
        
        data = result.get("results", [])
        if data:
            latest = data[0] if isinstance(data, list) else data
            if isinstance(latest, dict):
                data_section = latest.get("data", {})
                response += f"- Profundidad del hueco: {data_section.get('hole_depth', 'N/A')} ft\n"
                response += f"- Profundidad del trepano: {data_section.get('bit_depth', 'N/A')} ft\n"
                response += f"- Timestamp: {latest.get('timestamp', 'N/A')}\n"
                
    elif data_type == "wits_summary":
        asset_name = result.get("asset_name", "")
        response = f"📏 ROP ACTUAL para {asset_name}:\n{message}\n\n"
        
        data = result.get("results", [])
        if data:
            latest = data[0] if isinstance(data, list) else data
            if isinstance(latest, dict):
                data_section = latest.get("data", {})
                response += f"- ROP promedio: {data_section.get('rop_mean', 'N/A')} ft/hr\n"
                response += f"- Timestamp: {latest.get('timestamp', 'N/A')}\n"
                
    elif data_type == "metrics_rop":
        asset_name = result.get("asset_name", "")
        well_section = result.get("well_section", "")
        response = f"📊 MÉTRICAS ROP para {asset_name} - {well_section}:\n{message}\n\n"
        
        data = result.get("results", [])
        if data:
            response += "Valores ROP encontrados:\n"
            for i, record in enumerate(data[:5], 1):
                if isinstance(record, dict):
                    data_section = record.get("data", {})
                    response += f"{i}. Valor: {data_section.get('value', 'N/A')} ft/hr\n"
                    
    elif data_type == "operations":
        asset_name = result.get("asset_name", "")
        operation_filter = result.get("operation_filter", "")
        response = f"⏱️ OPERACIONES {operation_filter} para {asset_name}:\n{message}\n\n"
        
        data = result.get("results", [])
        if data:
            response += "Operaciones encontradas:\n"
            for i, record in enumerate(data[:5], 1):
                if isinstance(record, dict):
                    data_section = record.get("data", {})
                    response += f"{i}. {data_section.get('operation_name', 'N/A')}\n"
                    response += f"   Tiempo: {data_section.get('operation_time', 'N/A')} min\n"
                    response += f"   Sección: {data_section.get('well_section', 'N/A')}\n"
                    response += f"   Profundidad: {data_section.get('start_depth', 'N/A')} - {data_section.get('end_depth', 'N/A')} ft\n\n"
    
    elif data_type == "assets":
        response = f"📋 ASSETS DISPONIBLES ({total} total):\n{message}\n\n"
        for i, asset in enumerate(result.get("results", [])[:10], 1):
            response += f"{i}. {asset}\n"
                    
    else:
        response = f"Datos obtenidos: {json.dumps(result, indent=2)}"
    
    return response

# FUNCIÓN PRINCIPAL (sin decorador @tool)
def corva_api_query(user_query: str) -> str:
    """
    Función principal que consulta la API de Corva según la intención del usuario.
    Usa solo autenticación APIM.
    
    INTEGRADA COMPLETAMENTE CON SISTEMA AVATAR.
    """
    if not os.getenv("APIM_AUTH_CREDENTIAL"):
        return "Error: No se encontró APIM_AUTH_CREDENTIAL. Por favor, configúrala como variable de entorno."
    
    # Clasificar intención del usuario
    intent = classify_user_intent(user_query)
    
    try:
        if intent == "alerts":
            result = get_alerts()
        elif intent == "rigs":
            result = get_rigs()
        elif intent == "wells":
            result = get_wells()
        elif intent == "kpis":
            result = get_kpis_workflow(user_query)
        # NUEVAS INTENCIONES
        elif intent == "wits_depth":
            result = get_wits_depth(user_query)
        elif intent == "wits_summary":
            result = get_wits_summary(user_query)
        elif intent == "metrics_rop":
            result = get_metrics_rop(user_query)
        elif intent == "operations":
            result = get_operations(user_query)
        elif intent == "assets":
            result = get_assets_general()
        else:
            return ("No pude determinar qué información necesitas sobre Corva. "
                   "Puedo ayudarte con: alertas, rigs, wells, KPIs, profundidad del trepano, "
                   "ROP actual, métricas ROP, o tiempos de operaciones. "
                   "¿Podrías ser más específico?")
        
        return format_response_for_agent(result)
        
    except Exception as e:
        return f"Error inesperado al consultar la API de Corva: {str(e)}"

# TOOL DECORADA (versión simple para uso independiente)
@tool("corva_api_tool", return_direct=False)
def corva_api_tool(user_query: str) -> str:
    """
    Consulta la API de Corva según la intención del usuario.
    
    INTEGRADA COMPLETAMENTE CON SISTEMA AVATAR.
    
    Soporta:
    - Alertas generales: "muéstrame las alertas", "¿hay alguna alerta?"
    - Información de rigs: "lista los rigs", "¿qué rigs están disponibles?"
    - Información de wells: "muestra los wells", "¿cuáles son los pozos?"
    - KPIs específicos: "KPIs del rig DLS 167", "datos del well ABC-001"
    - Profundidad: "profundidad del trepano en LCav-415"
    - ROP actual: "ROP actual del well ABC-001"
    - Métricas ROP: "métricas ROP del rig DLS 167"
    - Operaciones: "tiempos de conexión del well ABC-001"
    
    Args:
        user_query (str): Consulta del usuario
    
    Returns:
        str: Respuesta formateada para el agente
    """
    return corva_api_query(user_query)


"""
CONFIGURACIÓN FINAL PARA SISTEMA AVATAR + APIM YPF:
==================================================

URLs que genera este código:

1. Alertas: https://maginternotest.grupo.ypf.com/corva/api/v1/alerts
2. Rigs: https://maginternotest.grupo.ypf.com/corva/api/v2/rigs  
3. Wells: https://maginternotest.grupo.ypf.com/corva/api/v2/wells
4. Assets: https://maginternotest.grupo.ypf.com/corva/api/v1/assets
5. KPIs: https://maginternotest.grupo.ypf.com/corva/data/api/v1/data/ypf/kpi-conexiones/
6. WITS Depth: https://maginternotest.grupo.ypf.com/corva/api/v1/data/corva/wits
7. WITS Summary: https://maginternotest.grupo.ypf.com/corva/data/api/v1/data/corva/wits.summary-1ft/
8. Metrics ROP: https://maginternotest.grupo.ypf.com/corva/data/api/v1/data/corva/metrics/
9. Operations: https://maginternotest.grupo.ypf.com/corva/data/api/v1/data/corva/operations/

CAMBIOS CRÍTICOS APLICADOS:
============================

🔧 **URLs de endpoint configuradas correctamente**
🔧 **make_corva_request_fixed() con parámetro base_url**
🔧 **search_asset_by_name() con lógica de matching inteligente corregida**
🔧 **get_kpis_workflow() con matching automático inteligente (85%+ similitud)**
🔧 **get_assets_general() optimizada para minimizar tokens**
🔧 **NUEVAS funciones agregadas: get_wits_depth(), get_wits_summary(), get_metrics_rop(), get_operations()**
🔧 **Manejo robusto de estructuras de datos diversas (lista directa vs objeto con data)**
🔧 **Filtrado de assets activos (last_active_at != null)**
🔧 **Optimización de respuestas para evitar sobrecargar el sistema avatar**

RESULTADO: Archivo completamente compatible con el sistema avatar y con todas las correcciones del archivo bot aplicadas.
"""