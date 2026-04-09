"""
RepAIr API — Motor de planificación para taller de motos
=========================================================
FastAPI + SQLite
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db.database import init_db
from .routers import jobs, plan, mechanics

app = FastAPI(
    title="RepAIr API",
    description="Motor de planificación inteligente para taller de motos",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


app.include_router(jobs.router)
app.include_router(plan.router)
app.include_router(mechanics.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "RepAIr API"}
