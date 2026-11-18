"""Shared Annotated FastAPI dependencies for sessions and authentication."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flowpilot.config import get_settings
from flowpilot.db.models import User
from flowpilot.db.seed import DEMO_USER_EMAIL, seed_defaults
from flowpilot.db.session import get_session
from flowpilot.security import decode_access_token, hash_api_key

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    """Authenticate via Bearer JWT, X-API-Key, or seeded demo user in non-prod mode."""
    settings = get_settings()

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
            user_id = str(payload.get("sub", ""))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired bearer token.",
            ) from exc
        res = await session.execute(
            select(User).where(User.id == user_id, User.is_active.is_(True))
        )
        user = res.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
        return user

    if x_api_key:
        key_hash = hash_api_key(x_api_key)
        res = await session.execute(
            select(User).where(User.api_key_hash == key_hash, User.is_active.is_(True))
        )
        user = res.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
        return user

    if not settings.is_prod:
        res = await session.execute(select(User).where(User.email == DEMO_USER_EMAIL))
        demo_user = res.scalar_one_or_none()
        if demo_user is None:
            demo_user = await seed_defaults(session)
        return demo_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication credentials required.",
    )


CurrentUserDep = Annotated[User, Depends(get_current_user)]
