"""Authentication routes (JWT login, demo session, current user profile)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from flowpilot.api.deps import CurrentUserDep, SessionDep
from flowpilot.config import get_settings
from flowpilot.db.models import User
from flowpilot.db.seed import DEMO_USER_EMAIL, seed_defaults
from flowpilot.security import create_access_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str
    role: str


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    res = await session.execute(select(User).where(User.email == payload.email))
    user = res.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    token = create_access_token(subject=user.id, role=user.role)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
    )


@router.post("/demo-token", response_model=TokenResponse)
async def demo_token(session: SessionDep) -> TokenResponse:
    if get_settings().is_prod:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Demo auth disabled in prod."
        )
    res = await session.execute(select(User).where(User.email == DEMO_USER_EMAIL))
    user = res.scalar_one_or_none() or await seed_defaults(session)
    token = create_access_token(subject=user.id, role=user.role)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
    )


@router.get("/me")
async def get_me(user: CurrentUserDep) -> dict[str, str]:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
    }
