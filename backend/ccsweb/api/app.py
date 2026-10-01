"""Application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ccsweb.api.routes import router
from ccsweb.config import get_settings


def _version() -> str:
    version_file = Path(__file__).resolve().parents[3] / "VERSION.txt"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Conversational Chat Storer",
        description="Unified viewer for AI coding-tool chat history.",
        version=_version(),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": _version()}

    return app


app = create_app()
