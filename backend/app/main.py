"""
FastAPI application factory and configuration.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .core.config import settings
from .api import router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )

    # Include routes
    app.include_router(router)

    # Health check endpoint
    @app.get("/health")
    def health_check():
        """Health check endpoint."""
        return JSONResponse(
            status_code=200,
            content={"status": "ok"}
        )

    return app


# Create app instance
app = create_app()
