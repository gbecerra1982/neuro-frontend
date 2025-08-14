import re, json

def _json_from_llm(raw: str) -> dict:
    """
    Intenta parsear JSON que pueda venir solo o entre ```json ...```.
    Lanza JSONDecodeError si no lo logra.
    """
    # elimina fences ```json … ``` o ``` … ```
    cleaned = re.sub(r"```(?:json)?", "", raw).strip(" `\n")
    return json.loads(cleaned)