from typing import Callable
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_token
from app.models.models import User
from app.schemas.schemas import PaginationParams

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extracts and validates JWT Bearer token, then retrieves the user from the database.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    user_id = payload.get("sub")
    token_type = payload.get("type")

    if not user_id or token_type != "access":
        raise credentials_exception

    stmt = select(User).where(User.user_id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    return user


def require_role(*roles: str) -> Callable:
    """
    Dependency factory to restrict endpoint access by user roles.
    """

    async def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_role_str = (
            current_user.role.value
            if hasattr(current_user.role, "value")
            else str(current_user.role)
        )
        if user_role_str not in roles and str(current_user.role) not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires one of the following roles: {', '.join(roles)}",
            )
        return current_user

    return role_checker


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency returning any authenticated active user.
    """
    return current_user


async def get_pagination(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        default=25, ge=1, le=100, description="Items per page (1-100)"
    ),
) -> PaginationParams:
    """
    Dependency extracting and validating pagination query parameters.
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Page number must be greater than or equal to 1.",
        )
    if page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Page size must be between 1 and 100.",
        )
    return PaginationParams(page=page, page_size=page_size)


# Convenience alias for role-based endpoint protection
require_admin = require_role("admin")
require_doctor = require_role("doctor")
require_doctor_or_admin = require_role("doctor", "admin")

