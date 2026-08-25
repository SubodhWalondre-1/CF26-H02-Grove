from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_token,
    verify_password,
)
from app.models.models import AdminPolicy, User
from app.schemas.schemas import MeResponse, TokenResponse, UserPermissions


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> Optional[User]:
    """
    Authenticates user credentials against the database.
    Returns the User ORM model if valid and active, else None.
    """
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


async def login(
    db: AsyncSession, username: str, password: str
) -> TokenResponse:
    """
    Validates user credentials and generates a new access token.
    """
    user = await authenticate_user(db, username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role_str = (
        user.role.value if hasattr(user.role, "value") else str(user.role)
    )
    token_data = {
        "sub": user.user_id,
        "username": user.username,
        "role": role_str,
    }

    access_token = create_access_token(data=token_data)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        role=role_str,
        user_id=user.user_id,
    )


async def refresh_access_token(
    refresh_token: str, db: AsyncSession
) -> TokenResponse:
    """
    Validates a refresh token and generates a fresh access token for the user.
    """
    payload = decode_token(refresh_token)
    token_type = payload.get("type")
    user_id = payload.get("sub")

    if token_type != "refresh" or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(User.user_id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role_str = (
        user.role.value if hasattr(user.role, "value") else str(user.role)
    )
    token_data = {
        "sub": user.user_id,
        "username": user.username,
        "role": role_str,
    }

    new_access_token = create_access_token(data=token_data)

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        role=role_str,
        user_id=user.user_id,
    )


async def get_user_permissions(
    db: AsyncSession, user: User
) -> UserPermissions:
    """
    Loads runtime policy matrix rows for the user's role from the admin_policies table.
    """
    stmt = select(AdminPolicy).where(AdminPolicy.role == user.role)
    result = await db.execute(stmt)
    policies = result.scalars().all()

    policy_map = {p.action: p.scope for p in policies}

    single_resource_scope = policy_map.get("single_resource", "denied")
    care_bundle_scope = policy_map.get("care_bundle", "denied")
    cancel_scope = policy_map.get("cancel", "denied")
    monitor_scope = policy_map.get("monitor", "denied")

    return UserPermissions(
        single_resource=(single_resource_scope in ("allowed", "operational")),
        care_bundle=(
            care_bundle_scope in ("allowed", "operational", "policy_based")
        ),
        cancel=cancel_scope,
        monitor=monitor_scope,
    )


async def get_me(db: AsyncSession, user: User) -> MeResponse:
    """
    Aggregates user profile metadata and dynamic permissions from database policies.
    """
    permissions = await get_user_permissions(db, user)
    role_str = (
        user.role.value if hasattr(user.role, "value") else str(user.role)
    )
    return MeResponse(
        user_id=user.user_id,
        role=role_str,
        permissions=permissions,
    )
