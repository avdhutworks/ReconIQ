
from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import settings
from app.modules.ingestion.router import router as ingestion_router
from app.modules.source_systems.router import (
    router as source_system_router,
)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "AI-Powered Intelligent Payment Reconciliation "
        "and Exception Management Platform"
    ),
)


@app.get("/")
def root():
    return {
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "message": "Welcome to ReconIQ",
    }


app.include_router(health_router)
app.include_router(source_system_router)
app.include_router(ingestion_router)
