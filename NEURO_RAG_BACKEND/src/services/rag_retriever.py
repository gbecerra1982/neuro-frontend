import re
from utils.utils_azure_storage import AzureStorage
from utils.utils_azure_search import AzureSearch
from typing import Optional, List, Dict, Any
import tiktoken
import os

from utils.util_logger import GetLogger
import logging
from config.settings import (
    TD_HOST,
    TD_USER,
    TD_PASS,
    LOGLEVEL,
    LOGMECH,
    CURRENT_DATE
)
import os
# Configurar logging adicional
logging.basicConfig(level=logging.INFO)
rag_logger = logging.getLogger("rag_agent")
 
log_dir = os.path.join(os.getcwd(), 'data')
 
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    print(f"Directorio creado: {log_dir}")
 
logger = GetLogger(__name__, level=LOGLEVEL, log_file=os.path.join(log_dir, 'app_logs.log')).logger


# logger = GetLogger(__name__, level=LOGLEVEL, log_file='data/app_logs.log').logger

def retrieve_doc_fn(question: str) -> str:
    try:
        # Extraer pozo y fecha de forma robusta, permitiendo comas dentro de fecha
        pozo_match = re.search(r"pozo\s*:\s*([^,]+)", question, flags=re.IGNORECASE)
        fecha_match = re.search(r"fecha\s*:\s*(.+)$", question, flags=re.IGNORECASE)
        equipo_match = re.search(r"equipo\s*:\s*([^,]+)", question, flags=re.IGNORECASE)
 
        pozo = pozo_match.group(1).strip() if pozo_match else None
        fecha = fecha_match.group(1).strip() if fecha_match else None
        equipo = equipo_match.group(1).strip() if equipo_match else None
 
        if not pozo or not fecha:
            return str({"error": True, "rag_result": "Parámetros insuficientes. Requerido: pozo, fecha y equipo"})
 
        storage = AzureStorage()
 
        def _count_tokens(text: Optional[str], encoding_name: str = "o200k_base") -> int:
            if not text:
                return 0
            try:
                enc = tiktoken.get_encoding(encoding_name)
                return len(enc.encode(text))
            except Exception:
                # Fallback simple
                return len(text.split())
 
        def _trim_text_to_tokens(text: str, max_tokens: int, encoding_name: str = "o200k_base") -> str:
            try:
                enc = tiktoken.get_encoding(encoding_name)
                tokens = enc.encode(text)
                if len(tokens) <= max_tokens:
                    return text
                return enc.decode(tokens[:max_tokens])
            except Exception:
                # Fallback aproximado por palabras
                words = text.split()
                return " ".join(words[:max_tokens])
 
        # Presupuesto de tokens para contenido RAG (configurable por env)
        MAX_RAG_TOKENS = int(os.environ.get("RAG_MAX_TOKENS", "10000000"))
        ENCODING = "o200k_base"
 
        # Detectar rango dentro del mismo parámetro fecha extrayendo dos fechas ISO
        iso_fechas = re.findall(r"\d{4}-\d{2}-\d{2}", fecha)
        if len(iso_fechas) >= 2:
            inicio, fin = iso_fechas[0], iso_fechas[1]
            resultados: List[Dict[str, Any]] = storage.read_rango_fecha_pozo_blobs(inicio, fin, pozo)
            enriched: List[Dict[str, Any]] = []
            total_tokens = 0
            truncated = False
            for item in resultados:
                content = item.get("content")
                remaining_budget = MAX_RAG_TOKENS - total_tokens
                if remaining_budget <= 0:
                    truncated = True
                    break
                tok = _count_tokens(content, ENCODING)
                if tok > remaining_budget:
                    # recortar el contenido del último día para que entre en presupuesto
                    trimmed = _trim_text_to_tokens(content or "", remaining_budget, ENCODING)
                    tok = _count_tokens(trimmed, ENCODING)
                    enriched.append({**item, "content": trimmed, "token_count": tok, "truncated": True})
                    total_tokens += tok
                    truncated = True
                    break
                enriched.append({**item, "token_count": tok})
                total_tokens += tok
            return str({
                "success": True,
                "rag_result": enriched,
                "total_token_count": total_tokens,
                "encoding": ENCODING,
                "truncated": truncated,
                "max_rag_tokens": MAX_RAG_TOKENS
            })
 
        # Caso de una sola fecha
        results = storage.read_fecha_pozo_blob(fecha, pozo)
        token_count = _count_tokens(results, ENCODING)
        truncated = False
        if token_count > MAX_RAG_TOKENS:
            results = _trim_text_to_tokens(results or "", MAX_RAG_TOKENS, ENCODING)
            token_count = _count_tokens(results, ENCODING)
            truncated = True
        return str({
            "success": True,
            "rag_result": results,
            "token_count": token_count,
            "encoding": ENCODING,
            "truncated": truncated,
            "max_rag_tokens": MAX_RAG_TOKENS
        })
    except Exception as e:
        return str({"error": True, "rag_result": f"Error al buscar los datos: {e}"})


def retrieve_fn(pozo, fecha: str, equipo) -> str:
    try:
        logger.info(f'fecha, pozo, equipo, {fecha} {pozo} {equipo}')
       
        ai_search = AzureSearch()
        results = ai_search.search_azure("", fecha, pozo, equipo)
 
        return str({"success": True, "se pudo extraer respuesta del outputse pudo extraer respuesta del output": results})
   
    except Exception as e:
        return str({"error": True, "rag_result": f"Error al buscar los datos: {e}"})

