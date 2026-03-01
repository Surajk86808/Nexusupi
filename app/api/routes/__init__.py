"""API route modules."""

from app.api.routes.auth import router as auth_router
from app.api.routes.credits import router as credits_router
from app.api.routes.oauth import router as oauth_router
from app.api.routes.product import router as product_router

__all__ = ["auth_router", "credits_router", "oauth_router", "product_router"]
