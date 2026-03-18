import asyncio
import os

# Setup logging before any other app imports so the "rag" logger is
# configured before route modules get a reference to it.
from app.core.logging import setup_logging
setup_logging()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.dependencies import get_vector_service
from app.api.routes import health, upload, ask

app = FastAPI(
    title="Multi-Seguradora Insurance RAG Assistant",
    description="Assistente de IA para análise de apólices de seguro (Bradesco, Porto Seguro, etc.)",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Pré-carrega o modelo de embeddings em background durante o startup.
    Isso move o carregamento pesado (~60s) para antes do primeiro request,
    evitando timeout no Render durante o healthcheck inicial."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, get_vector_service().warm_up)


os.makedirs("temp_uploads", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(health.router)
app.include_router(upload.router)
app.include_router(ask.router)
