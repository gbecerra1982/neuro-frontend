#!/bin/bash

# Activar virtualenv si corresponde (opcional)
# source venv/bin/activate

# Lanzar FastAPI (modifica la ruta a backend.py según tu estructura real)
python Avatar-Pywo/NEURO_RAG_BACKEND/src/backend.py &

# Lanzar Flask
python app.py

# Nota:
# El & al final de la línea de backend.py ejecuta FastAPI en segundo plano,
# y luego Flask en primer plano.
# Si quieres ambos en segundo plano, agrega & al final de ambas líneas.