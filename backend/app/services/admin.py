from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AdminConfig, AdminPolicy, User, UserRole
from app.schemas.schemas import UpdateAdminConfigRequest, UpdatePolicyEntry
from app.services.audit import create_audit_event


async def get_policy_matrix(db: AsyncSession) -> List[AdminPolicy]:
    """
    Retrieves all role-based authorization policy rules ordered by role and action.
    """
    stmt = select(AdminPolicy).order_by(
        AdminPolicy.role.asc(), AdminPolicy.action.asc()
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_policy_matrix(
    db: AsyncSession,
    updates: List[UpdatePolicyEntry],
    updated_by: User,
) -> List[AdminPolicy]:
    """
    Upserts authorization policy rules and records a POLICY_UPDATED audit event.
    """
    changes: List[Dict[str, str]] = []

    for entry in updates:
        role_enum = UserRole(entry.role)
        stmt = select(AdminPolicy).where(
            AdminPolicy.role == role_enum,
            AdminPolicy.action == entry.action,
        )
        result = await db.execute(stmt)
        policy = result.scalar_one_or_none()

        if policy:
            policy.scope = entry.scope
        else:
            new_policy = AdminPolicy(
                role=role_enum,
                action=entry.action,
                scope=entry.scope,
            )
            db.add(new_policy)

        changes.append(
            {
                "role": entry.role,
                "action": entry.action,
                "scope": entry.scope,
            }
        )

    if changes:
        await create_audit_event(
            db=db,
            event_type="POLICY_UPDATED",
            detail={
                "updated_by": updated_by.user_id,
                "changes": changes,
            },
        )
        await db.commit()

    return await get_policy_matrix(db=db)


async def get_admin_config(db: AsyncSession) -> Dict[str, Any]:
    """
    Retrieves and parses system-wide tunable coordinator configuration parameters.
    """
    stmt = select(AdminConfig)
    result = await db.execute(stmt)
    configs = {row.key: row.value for row in result.scalars().all()}

    if (
        "hold_ttl_seconds" not in configs
        or "wait_coefficient_per_min" not in configs
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Missing required admin configuration parameters in database.",
        )

    return {
        "hold_ttl_seconds": int(configs.get("hold_ttl_seconds", 30)),
        "wait_coefficient_per_min": float(configs.get("wait_coefficient_per_min", 0.12)),
        "acuity_override_threshold": float(configs.get("acuity_override_threshold", 9.5)),
        "override_frequency_flag_limit": int(configs.get("override_frequency_flag_limit", 3)),
    }


async def update_admin_config(
    db: AsyncSession,
    updates: UpdateAdminConfigRequest,
    updated_by: User,
) -> Dict[str, Any]:
    """
    Updates system-wide coordinator configuration parameters and records a CONFIG_UPDATED audit event.
    """
    changes: Dict[str, Any] = {}
    now_utc = datetime.now(timezone.utc)

    if updates.hold_ttl_seconds is not None:
        stmt = select(AdminConfig).where(AdminConfig.key == "hold_ttl_seconds")
        result = await db.execute(stmt)
        cfg = result.scalar_one_or_none()
        if cfg:
            cfg.value = Decimal(str(updates.hold_ttl_seconds))
            cfg.updated_by = updated_by.user_id
            cfg.updated_at = now_utc
            changes["hold_ttl_seconds"] = updates.hold_ttl_seconds

    if updates.wait_coefficient_per_min is not None:
        stmt = select(AdminConfig).where(AdminConfig.key == "wait_coefficient_per_min")
        result = await db.execute(stmt)
        cfg = result.scalar_one_or_none()
        if cfg:
            cfg.value = Decimal(str(updates.wait_coefficient_per_min))
            cfg.updated_by = updated_by.user_id
            cfg.updated_at = now_utc
            changes["wait_coefficient_per_min"] = updates.wait_coefficient_per_min

    if updates.acuity_override_threshold is not None:
        stmt = select(AdminConfig).where(AdminConfig.key == "acuity_override_threshold")
        result = await db.execute(stmt)
        cfg = result.scalar_one_or_none()
        if not cfg:
            cfg = AdminConfig(key="acuity_override_threshold", value=Decimal(str(updates.acuity_override_threshold)), updated_by=updated_by.user_id)
            db.add(cfg)
        else:
            cfg.value = Decimal(str(updates.acuity_override_threshold))
            cfg.updated_by = updated_by.user_id
            cfg.updated_at = now_utc
        changes["acuity_override_threshold"] = updates.acuity_override_threshold

    if updates.override_frequency_flag_limit is not None:
        stmt = select(AdminConfig).where(AdminConfig.key == "override_frequency_flag_limit")
        result = await db.execute(stmt)
        cfg = result.scalar_one_or_none()
        if not cfg:
            cfg = AdminConfig(key="override_frequency_flag_limit", value=Decimal(str(updates.override_frequency_flag_limit)), updated_by=updated_by.user_id)
            db.add(cfg)
        else:
            cfg.value = Decimal(str(updates.override_frequency_flag_limit))
            cfg.updated_by = updated_by.user_id
            cfg.updated_at = now_utc
        changes["override_frequency_flag_limit"] = updates.override_frequency_flag_limit

    if changes:
        await create_audit_event(
            db=db,
            event_type="CONFIG_UPDATED",
            detail={
                "updated_by": updated_by.user_id,
                "changes": changes,
            },
        )
        await db.commit()

    return await get_admin_config(db=db)
