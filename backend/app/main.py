"""
FastAPI application factory and configuration.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .api import router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routes. The frontend calls the API under /api (Vite strips the
    # prefix in development), so expose the same routes there for the bundled SPA.
    app.include_router(router)
    app.include_router(router, prefix="/api", include_in_schema=False)

    # Health check endpoint
    @app.get("/health")
    def health_check():
        """Health check endpoint."""
        return JSONResponse(
            status_code=200,
            content={"status": "ok"}
        )

    # Serve the built frontend when present (Docker image copies it here).
    frontend_dist = Path(os.getenv("FRONTEND_DIST_DIR", Path(__file__).resolve().parent.parent / "static"))
    if (frontend_dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


# Create app instance
app = create_app()
