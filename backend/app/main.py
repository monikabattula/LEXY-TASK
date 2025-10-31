import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.db import init_db, session_scope
from app.core.config import settings
from app.api.v1.routes_documents import router as documents_router
from app.api.v1.routes_sessions import router as sessions_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(title="Legal Doc Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get('/health')
def health():
    # simple DB check
    ok = True
    try:
        with session_scope() as s:
            from sqlmodel import select, text
            s.exec(text("SELECT 1"))
    except Exception:
        ok = False
    return JSONResponse({
        'status': 'ok' if ok else 'degraded',
        'env': settings.app_env,
        'db': ok,
    })


app.include_router(documents_router, prefix="/v1")
app.include_router(sessions_router, prefix="/v1")
