# Streamlit conectado a API
import streamlit as st
import requests  # Usamos requests para interactuar con la API HTTP
import json
from langchain_core.messages import AIMessage
import requests

 
 
API_BASE_URL='http://localhost:8000'
 
def consultar_langgraph(user_question: str) -> str:
    """Consulta la API HTTP con la pregunta del usuario y devuelve la respuesta final."""
    try:
        # Preparar los datos para la solicitud
        payload = {
            "question": user_question,
            "session_id": "default_session"
        }
       
        # Hacer la solicitud HTTP POST a la API
        response = requests.post(
            f"{API_BASE_URL}/ask",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=200
        )
       
        # Verificar si la respuesta fue exitosa
        if response.status_code == 200:
            data = response.json()
            if data.get("success", False):
                return data.get("answer", "No se recibió respuesta de la API.")
            else:
                return f"Error en la API: {data.get('error_message', 'Error desconocido')}"
        else:
            # Intentar obtener el mensaje de error del detalle
            try:
                error_data = response.json()
                error_message = error_data.get("detail", f"Error HTTP {response.status_code}")
            except:
                error_message = f"Error HTTP {response.status_code}"
           
            return f"Error al consultar la API: {error_message}"
           
    except requests.exceptions.ConnectionError:
        return "Error de conexión: No se pudo conectar con la API. Asegúrate de que esté ejecutándose en el puerto 8000."
    except requests.exceptions.Timeout:
        return "Tiempo de espera agotado: La consulta tardó demasiado en procesarse. Intenta con una pregunta más simple."
    except requests.exceptions.RequestException as e:
        return f"Error de solicitud: {str(e)}"
    except Exception as e:
        return f"Error inesperado: {str(e)}"
 
# --- Configuración inicial e interfaz ---
# Título de la app
st.title("Neuro RAG")
 
# Indicador de estado de la API
try:
    test_response = requests.get(f"{API_BASE_URL}/health", timeout=3)
    if test_response.status_code == 200:
        st.markdown("""
        <div class="api-status api-connected">
            ✅ API conectada y funcionando correctamente
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="api-status api-disconnected">
             API responde pero con errores
        </div>
        """, unsafe_allow_html=True)
except:
    st.markdown("""
    <div class="api-status api-disconnected">
         No se puede conectar con la API en localhost:8000
    </div>
    """, unsafe_allow_html=True)
 
# Creamos un historial de mensajes
if "historial" not in st.session_state:
    st.session_state["historial"] = []
 
# Mostrar el historial de conversación
if st.session_state["historial"]:
    st.markdown("### 💬 Conversación")
   
    # Contenedor para el chat
    chat_container = st.container()
   
    with chat_container:
        for mensaje in st.session_state["historial"]:
            if mensaje["role"] == "user":
                st.markdown(f"""
                <div class="message-container">
                    <div class="user-message">
                        <strong>Tú:</strong><br>
                        {mensaje['content']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            elif mensaje["role"] == "assistant":
                st.markdown(f"""
                <div class="message-container">
                    <div class="bot-message">
                        <strong>Neuro:</strong><br>
                        \n{mensaje['content']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
   
    st.markdown("---")
else:
    st.markdown("### ¡Hola! Soy Neuro RAG")
    st.markdown("Pregúntame lo que necesites saber. ¡Estoy aquí para ayudarte!")
 
# Formulario para nueva pregunta (al final)
with st.form(key="chat_form", clear_on_submit=True):
    col1, col2 = st.columns([4, 1])
   
    with col1:
        user_question = st.text_input(
            "Escribe tu pregunta:",
            placeholder="Por ejemplo: ¿Cuáles son las novedades del pozo LACh-1117(h)?",
            label_visibility="collapsed"
        )
   
    with col2:
        submit_button = st.form_submit_button("🚀 Enviar", use_container_width=True)
 
# Procesar la pregunta cuando se envíe
if submit_button and user_question:
    # Añadimos la pregunta del usuario al historial
    st.session_state["historial"].append({"role": "user", "content": user_question})
 
    # Mostrar indicador de "consultando API..."
    with st.spinner("Neuro está buscando información"):
        try:
            # Obtener la respuesta de la API
            respuesta = consultar_langgraph(user_question)
 
            # Añadimos la respuesta al historial
            st.session_state["historial"].append({"role": "assistant", "content": respuesta})
        except Exception as e:
            # En caso de errores
            respuesta = f"Error inesperado al procesar tu pregunta: {str(e)}"
            st.session_state["historial"].append({"role": "assistant", "content": respuesta})
   
    # Recargar la página para mostrar la nueva conversación
    st.rerun()
 
# Botón para limpiar el historial
if st.session_state["historial"]:
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Limpiar chat", type="secondary"):
            st.session_state["historial"] = []
            st.rerun()
    with col2:
        st.caption("Tip: Si tienes problemas de conexión, verifica que tu API esté ejecutándose en el puerto 8000")