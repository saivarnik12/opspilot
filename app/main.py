from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import Base, engine
from app.routes import api_keys, auth, incidents, logs


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    description="AI-powered incident and log analysis platform.",
    version="0.4.0",
    lifespan=lifespan,
)
app.include_router(auth.router)
app.include_router(api_keys.router)
app.include_router(logs.router)
app.include_router(incidents.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": settings.app_name}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app/")


# Monitoring dashboard (no build step): served from the same origin as the API.
app.mount("/app", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="dashboard")
