# -------------------------------------------------------------------------
# sql Critic Agent
# -------------------------------------------------------------------------
from .agent import critic_graph
import re
from typing import Dict, List, Tuple

def run_sql_critic(
            pregunta_usuario: str,
            few_shot_queries: str,
            column_list: list[str],
            consulta_sql: str,
            raw_sql_query: str,
            query_errors=[]):
            """
            Construye el contexto, ejecuta el critic_graph y devuelve:
            • output (dict)   → reasoning / success / critique / (otros)
            • critica_o_ok    → texto de crítica si success=False, '' si success=True
            """

            # 1. Armar el contexto que verá el crítico
            # Si hubo un error en la ejecución de la consulta sql
            if len(query_errors) > 0:
                feedback = "### Errores en las ejecuciones previas:\n" + "\n\n".join(query_errors)
                print(f"feedback: {feedback}")
            else: 
                feedback = ""

            example_input = f"""Evaluate the generated SQL against the user question.

        ### Pregunta del usuario
        {pregunta_usuario}

        # Contexto
        ### Columnas disponibles
        {column_list}

        ### Few-shot de referencia
        {few_shot_queries}

        # Proceso por analizar (Consulta y su ejecución y errores)
        ---------------------------------------------------------
        ### Consulta generada por el LLM
        {raw_sql_query}

        ### Consulta con where instances  corregidas en función de la base de datos. Se reemplazan los nombres indicados por el usuario por los correspondientes en la base de datos.
        {consulta_sql}

        {feedback}
        ---------------------------------------------------------
        
        ### CoT - Cadena de razonamiento
        Usa reasoning y critique con una estrategia de chain of tought, de manera que se analice paso a paso por qué la consulta sql es correcta o no. 
        Analiza si todas las columnas y tablas fueron extraidas del contexto provisto ().
        Agregá columnas si sirven para entender el resultado, por ejemplo si se pide el dato de un pozo o equipo, agrega el nombre del pozo o equipo para aportar claridad.
        Ordená por fecha o grupo u otra columnas siempre que pueda aportar al entendimiento.
        Las consultas generales es probable que no tengan few shot disponibles, considerar validas. Por ejemplo: "Dame las novedades de perforación"
        En caso que la consulta el razonamiento no sea correcto, conservar o mejorar la consulta original en el campo \"sql_query\".
        Where instances fueron corregidas en instancias previas, no considerarlas error. 
        Nunca modifiques la consulta sql con columnas o tablas que no se muestren en el contexto (Columnas disponibles y Few-shot de referencia)

        """
            
            # 2. process_issues (vacío por ahora)
            init_state = {
                "task_context": example_input,
                "process_issues": "\"sql_query\": \"<string>\", #If apply create a new sql corrected or imrpoved, at least mantain the original sql query \n\"confianza\": \"<int>\", #Puntuación del 1 a 5 que indique si la consulta requiere revisión (menor o igual a 2).",
                "messages": []
            }

            # 3. Ejecutar el grafo crítico
            final_state = critic_graph.invoke(init_state)
            output = final_state["output"]

            # 4. Si falla, devolvemos la crítica inmediata
            if not output.get("success", False):
                return output, output.get("critique", "Sin crítica")

            # 5. Éxito → no hay crítica
            return output, ""

def run_critic_with_examples(
    pregunta_usuario: str,
    few_shot_queries: str,
    critic_graph,
) -> Tuple[Dict, str]:
    """
    Ejecuta el critic para re-ranking inteligente de ejemplos y devuelve 
    los ejemplos más relevantes seleccionados.
    """
    
    print("\n" + "🔍 INICIANDO RE-RANKING DE EJEMPLOS ".center(80, "="))
    print(f"📝 Pregunta: {pregunta_usuario}")
    
    # ---------------------------------------------------------------------
    # 1. Construir el contexto para el critic
    # ---------------------------------------------------------------------
    example_input = f"""These are few shot that serve as example for the user input, critic:
###
{pregunta_usuario}
###
Few_shot:
###
{few_shot_queries}
###
"""

    # Información para el critic sobre el formato esperado
    process_issues = (
        '"relevant": ["ejemplo 1", "ejemplo 3", "ejemplo 7"], '
        '"why_relevant": "Explicación de relevancia"'
    )

    init_state: Dict = {
        "task_context": example_input,
        "process_issues": process_issues,
        "messages": []
    }

    # ---------------------------------------------------------------------
    # 2. Ejecutar el critic
    # ---------------------------------------------------------------------
    final_state = critic_graph.invoke(init_state)
    output = final_state["output"]
    
    print(f"🎯 RESULTADO DEL CRITIC:")
    print(f"   Success: {output.get('success')}")
    print(f"   Relevant: {output.get('relevant', [])}")
    print(f"   Fallback aplicado: {output.get('fallback_applied', False)}")

    # ---------------------------------------------------------------------
    # 3. Convertir few_shot_queries a diccionario
    # ---------------------------------------------------------------------
    ejemplos = examples_to_dict(few_shot_queries)
    print(f"📚 Ejemplos disponibles: {len(ejemplos)} items")
    
    if not ejemplos:
        print("⚠️ ERROR: No se pudieron parsear los ejemplos")
        return output, few_shot_queries  # Devolver original como fallback

    # ---------------------------------------------------------------------
    # 4. Procesar selección del critic
    # ---------------------------------------------------------------------
    relevantes = output.get("relevant", [])
    solo_relevantes_list = []
    
    if output.get("success") and relevantes:
        print(f"✅ Procesando {len(relevantes)} ejemplos seleccionados")
        
        for item in relevantes:
            item_str = str(item).strip().lower()
            
            # Buscar match exacto
            exact_match = None
            for ejemplo_key in ejemplos.keys():
                if item_str == ejemplo_key.lower():
                    exact_match = ejemplo_key
                    break
            
            if exact_match:
                solo_relevantes_list.append(f"{exact_match}\n{ejemplos[exact_match]}")
                print(f"   ✅ {exact_match}")
            else:
                # Buscar match parcial (por si hay variaciones)
                partial_matches = [k for k in ejemplos.keys() if item_str in k.lower()]
                if partial_matches:
                    best_match = partial_matches[0]
                    solo_relevantes_list.append(f"{best_match}\n{ejemplos[best_match]}")
                    print(f"   ✅ {best_match} (parcial)")
                else:
                    print(f"   ❌ No encontrado: {item}")
    
    # ---------------------------------------------------------------------
    # 5. Validar resultado y aplicar fallback si es necesario
    # ---------------------------------------------------------------------
    if not solo_relevantes_list:
        if output.get("success"):
            print("⚠️ WARNING: Critic exitoso pero sin matches - usando primeros 3 ejemplos")
            # Usar los primeros 3 ejemplos como fallback
            for i, (key, contenido) in enumerate(ejemplos.items()):
                if i < 3:
                    solo_relevantes_list.append(f"{key}\n{contenido}")
        else:
            print("❌ Critic falló - consulta no relevante")
            # No devolver ejemplos para consultas no relevantes
            return output, ""
    
    # ---------------------------------------------------------------------
    # 6. Construir resultado final
    # ---------------------------------------------------------------------
    solo_relevantes = "\n\n".join(solo_relevantes_list)
    
    print(f"   Ejemplos seleccionados: {len(solo_relevantes_list)}")
    print(f"   Longitud total: {len(solo_relevantes)} caracteres")
    
    if solo_relevantes_list:
        ejemplos_nombres = [item.split('\n')[0] for item in solo_relevantes_list]
        print(f"   Ejemplos incluidos: {ejemplos_nombres}")
    
    print("=" * 80)
    
    # Debug para troubleshooting
    if len(solo_relevantes) == 0 and output.get("success"):
        print(f"🐛 DEBUG - Problema detectado:")
        print(f"   Relevantes del critic: {relevantes}")
        print(f"   Keys disponibles: {list(ejemplos.keys())[:5]}...")
    
    return output, solo_relevantes


# -------------------------------------------------------------------------
# Utilidad auxiliar para convertir few_shot_queries → dict
# -------------------------------------------------------------------------

def examples_to_dict(text: str) -> Dict[str, str]:
    pattern = re.compile(
        r"Ejemplo\s+(\d+)\n"        # encabezado "Ejemplo n"
        r"(.*?)"                    # contenido del ejemplo
        r"(?=\nEjemplo\s+\d+|\Z)",  # hasta el próximo "Ejemplo" o fin
        re.S
    )
    return {f"ejemplo {m.group(1)}": m.group(2).strip() for m in pattern.finditer(text)}
