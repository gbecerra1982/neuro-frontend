# Neuro RAG
 
## 📖 Introducción
 
**Botcom** es un sistema inteligente de consultas SQL que permite a los usuarios hacer preguntas en lenguaje natural sobre datos de ventas y planificación de YPF. Utiliza IA para generar consultas SQL automáticamente, ejecutarlas en Cloudera/Hive, y devolver respuestas comprensibles.
 
### 🎯 Características Principales
 
- 🗣️ **Consultas en lenguaje natural**: Pregunta en español, obtén datos
- 🧠 **Memoria conversacional**: Mantiene contexto entre preguntas
- 🔄 **Agentes especializados**: SQL, análisis y formateo de resultados
- 🚀 **API REST**: Integración fácil con aplicaciones
- 📊 **Interfaz web**: Cliente Streamlit incluido
 

**Componentes:**
- **FastAPI**: API REST para procesamiento de consultas
- **LangGraph**: Orquestación de agentes con memoria persistente
- **Azure OpenAI**: Modelos GPT-4o para generación SQL y análisis
- **Cloudera/Hive**: Base de datos corporativa
- **MemorySaver**: Sistema de memoria conversacional
 
## 🔧 Requisitos Previos
 
### Software Necesario
- **Python 3.9+**
- **Conexión a Cloudera/Hive**
- **Azure OpenAI** (API Key y Endpoint)
- **Git** (para clonar el repositorio)
 
### Dependencias Principales
- `langchain-openai`
- `langgraph`
- `fastapi`
- `streamlit`
- `pandas`
 
## ⚙️ Instalación
 
### 1. Clonar el Repositorio
```bash
git clone [URL_DEL_REPO]
cd [nombre_del_repo]
```
 
### 2. Crear Entorno Virtual
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```
 
### 3. Instalar Dependencias
```bash
pip install -r requirements.txt
```
 
### 4. Configurar Variables de Entorno
 
Copia el archivo template y configura tus credenciales:
```bash
cp env_template.txt .env
```
 
Edita `.env` con tus valores:
```env
# Azure OpenAI
AZURE_OPENAI_API_KEY=tu_api_key_aqui
AZURE_OPENAI_ENDPOINT=https://tu-openai-endpoint.openai.azure.com/
 
# Logging (opcional)
LOGLEVEL_UTIL=INFO
```

### 6. PROXY
Asegurarse de tener el proxy activado. Y agregar ";*cloudera.site" para poder hacer las consultas

## 🚀 Ejecución
 
### API Completa (Recomendado)
```bash
python src/backend.py
```
La API estará disponible en: `http://localhost:8000`
```bash
streamlit run streamlit-app.py
```
La interfaz web estará en: `http://localhost:8501`
 
## 🧪 Testing y Validación

 
### Verificar Logs
Los logs aparecerán en la consola con formato:
```
[2024-01-15 10:30:00][INFO][backend][build_agent] Construyendo agente SQL con memoria
[2024-01-15 10:30:01][INFO][backend][procesar_consulta_langgraph] Procesando consulta para sesión: test_session
```

 
### Ejemplos de Preguntas
 
#### Consultas de Datos
- "¿Cuáles fueron las ventas de junio 2024?"
- "Muestra los datos de la estación 818"
- "¿Cómo estuvimos comparado con el plan?"
- "¿Qué productos se vendieron más en diciembre?"
 
## 📁 Estructura del Proyecto
 
```
├── app/                          # Aplicación principal
├── streamlit-app.py             # Frontend web
├── config.yaml                  # Configuración del sistema
├── .env                         # Variables de entorno (no incluido)
├── requirements.txt             # Dependencias Python
├── src/
│   ├── llm/
│   │   └── llm.py              # Configuración de modelos LLM
│   ├── prompt_engineering/
│   │   └── query_prompts.py    # Prompts para agentes
│   ├── utils/
│   │   └── utils.py            # Utilidades y conexiones
│   ├── data/
│   │   └── cloudera_schema.json # Schema de tablas
│   └── notebooks/              # Notebooks de desarrollo
        └── backend.py          # API FastAPI principal
├── test/                       # Scripts de testing
└── README.md                   # Este archivo
```
 
### Archivos Clave
 
- **`backend.py`** ⭐: API principal con agentes y memoria
- **`streamlit-app.py`** ⭐: Interfaz web de usuario
- **`config.yaml`**: Configuración estructural
- **`.env`**: Secretos y credenciales
- **`src/llm/llm.py`**: Configuración de modelos OpenAI
- **`src/prompt_engineering/query_prompts.py`**: Prompts especializados
 
## 🐛 Troubleshooting
 
### Problema: "Error configurando MemorySaver"
**Solución**: Verifica que `langgraph` esté instalado correctamente:
```bash
pip install --upgrade langgraph
```
 
### Problema: "Error conectando a Cloudera"
**Solución**:
1. Verifica las credenciales en `.env`
2. Confirma conectividad de red
3. Revisa los logs para errores específicos
 
### Problema: "Schema file not found"
**Solución**:
1. Asegúrate de que existe `src/data/cloudera_schema.json`
2. O crea un fallback en `data/cloudera_schema.json`
 
### Problema: "Azure OpenAI API Error"
**Solución**:
1. Verifica `AZURE_OPENAI_API_KEY` y `AZURE_OPENAI_ENDPOINT`
2. Confirma que los deployment names en `llm.py` coinciden con Azure
 
## 📊 Monitoreo y Logs
 
### Niveles de Log
- **INFO**: Flujo principal de ejecución
- **DEBUG**: Detalles técnicos (queries, parámetros)
- **WARNING**: Situaciones atípicas manejadas
- **ERROR**: Errores que requieren atención
 
 
### Configurar Nivel de Logging
En `.env`:
```env
LOGLEVEL_UTIL=DEBUG  # Para logs detallados
LOGLEVEL_UTIL=INFO   # Para logs normales
```
 
## 🔄 Flujo de Procesamiento
 
1. **Usuario hace pregunta** → Streamlit o API REST
2. **Análisis de intención** → ¿SQL o matemáticas?
3. **Generación SQL** → LLM convierte pregunta a SQL
4. **Ejecución** → Query en Cloudera/Hive
5. **Formateo** → LLM convierte resultados a respuesta natural
6. **Memoria** → Guarda contexto para próximas preguntas
7. **Respuesta** → Usuario recibe respuesta comprensible
 
## 🔐 Seguridad
 
- **Variables sensibles** en `.env` (no versionado)
- **CORS configurado** para desarrollo (restringir en producción)
- **Validación de entrada** con Pydantic
- **Manejo seguro de conexiones** de base de datos
 
## 🚀 Próximos Pasos
 
## 📞 Soporte
 
Para problemas o preguntas:
1. Revisa los logs en consola
2. Verifica la configuración en `.env`
3. Consulta esta documentación
4. Usa el endpoint `/health` para diagnóstico
 
---
 
**Versión**: 1.0.0  
**Última actualización**: 07/08/2025