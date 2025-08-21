from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import health, ask


app = FastAPI(
    title="Botcom API",
    description="API para consultas de ventas y planificación usando LangGraph",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ask.router)

