"""
NexusAPI — Multi-Tenant Credit-Gated Backend
FastAPI application entrypoint.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    get_settings()
    configure_logging()
    yield


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    from app.api.routes.auth import router as auth_router
    from app.api.routes.credits import router as credits_router
    from app.api.routes.health import router as health_router
    from app.api.routes.oauth import router as oauth_router
    from app.api.routes.product import router as product_router
    from app.middleware.error_handler import error_handling_middleware_dispatch
    from app.middleware.logging_middleware import logging_middleware_dispatch
    from app.middleware.rate_limit import rate_limit_middleware_dispatch

    app = FastAPI(
        title="NexusAPI",
        description="Multi-Tenant Credit-Gated Backend",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.middleware("http")(error_handling_middleware_dispatch)
    app.middleware("http")(logging_middleware_dispatch)
    app.middleware("http")(rate_limit_middleware_dispatch)
    app.include_router(auth_router)
    app.include_router(credits_router)
    app.include_router(product_router)
    app.include_router(health_router)
    app.include_router(oauth_router)

    @app.get("/")
    async def root():
        """Root health check."""
        return {"status": "ok", "service": "nexusapi"}

    return app


app = create_app()


def run():
    """CLI entrypoint for uvicorn."""
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    run()
