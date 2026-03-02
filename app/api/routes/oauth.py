"""
Google OAuth routes.
"""

from __future__ import annotations

import os
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.organisation import Organisation
from app.models.user import User, UserRole

router = APIRouter(tags=["oauth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
DEFAULT_GOOGLE_REDIRECT_URI = "http://localhost:8000/auth/callback"


@router.get("/auth/google")
async def google_auth_redirect() -> RedirectResponse:
    """Redirect users to Google OAuth consent screen."""
    settings = get_settings()
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", DEFAULT_GOOGLE_REDIRECT_URI)
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
        }
    )
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{query}")


@router.get("/auth/callback")
async def google_auth_callback(
    code: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Handle Google OAuth callback and return NexusAPI JWT."""
    if code is None or not code.strip():
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": "oauth_failed",
                "message": "Missing authorization code",
            },
        )

    settings = get_settings()
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", DEFAULT_GOOGLE_REDIRECT_URI)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            if token_response.status_code != status.HTTP_200_OK:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "error": "oauth_failed",
                        "message": "Google authentication failed",
                    },
                )

            token_payload = token_response.json()
            access_token = token_payload.get("access_token")
            if not access_token:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "error": "oauth_failed",
                        "message": "Google authentication failed",
                    },
                )

            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()

        email = (userinfo.get("email") or "").strip().lower()
        name = (userinfo.get("name") or "").strip()
        google_id = (userinfo.get("sub") or userinfo.get("id") or "").strip()
        if not email or "@" not in email or not google_id:
            raise ValueError("Missing required Google profile fields")

        email_domain = email.split("@", 1)[1].lower()

        org_query = select(Organisation).where(Organisation.slug == email_domain)
        organisation = (await db.execute(org_query)).scalar_one_or_none()
        created_organisation = False

        if organisation is None:
            organisation = Organisation(name=email_domain, slug=email_domain)
            db.add(organisation)
            await db.flush()
            created_organisation = True

        user_query = select(User).where(User.google_id == google_id)
        user = (await db.execute(user_query)).scalar_one_or_none()
        resolved_role = UserRole.ADMIN if created_organisation else UserRole.MEMBER
        if user is None:
            user = User(
                email=email,
                name=name or email_domain,
                google_id=google_id,
                organisation_id=organisation.id,
                role=resolved_role,
            )
            db.add(user)
        else:
            user.email = email
            user.name = name or user.name
            user.organisation_id = organisation.id
            # Never silently downgrade existing admins on re-login.
            if user.role != UserRole.ADMIN:
                user.role = resolved_role

        await db.commit()
        await db.refresh(user)

        jwt_token = create_access_token(
            {
                "user_id": str(user.id),
                "organisation_id": str(user.organisation_id),
                "role": user.role.value,
            }
        )

        frontend_success_url = (settings.frontend_oauth_success_url or "").strip()
        payload = {
            "access_token": jwt_token,
            "token_type": "bearer",
            "user_id": str(user.id),
            "organisation_id": str(organisation.id),
            "role": user.role.value,
        }
        if frontend_success_url:
            fragment = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in payload.items())
            return RedirectResponse(url=f"{frontend_success_url}#{fragment}")
        return JSONResponse(status_code=status.HTTP_200_OK, content=payload)
    except Exception:
        await db.rollback()
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": "oauth_failed",
                "message": "Google authentication failed",
            },
        )
