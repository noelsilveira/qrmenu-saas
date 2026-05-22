import uuid
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_active_user, require_role
from app.models import User
from app.schemas.third_party import (
    PlatformConnectionCreate, PlatformConnectionUpdate, PlatformConnectionResponse,
    ThirdPartyOrderResponse, MenuSyncRequest, MenuSyncResponse,
    TalabatWebhookPayload, ZomatoWebhookPayload, JahezWebhookPayload,
    FallbackConfig, FallbackLogResponse,
    PlatformType, PlatformStatus,
)
from app.services.third_party_service import ThirdPartyService, FallbackOrchestrator

router = APIRouter()

def _get_merchant_id(user: User) -> UUID:
    return user.merchant_id


# ---------------------------------------------------------------------------
# Platform Connections
# ---------------------------------------------------------------------------
@router.post("/connections", response_model=PlatformConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    data: PlatformConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Connect a 3rd party platform (Talabat, Zomato, Jahez)."""
    merchant_id = _get_merchant_id(current_user)

    from app.models import PlatformConnection as PC
    conn = PC(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        platform=data.platform.value,
        merchant_ref=data.merchant_ref,
        api_key=data.api_key,
        api_secret=data.api_secret,
        webhook_secret=data.webhook_secret,
        branch_id=data.branch_id,
        status=PlatformStatus.active.value,
        is_active=data.is_active,
    )
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return conn


@router.get("/connections", response_model=List[PlatformConnectionResponse])
async def list_connections(
    platform: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all platform connections."""
    merchant_id = _get_merchant_id(current_user)

    from app.models import PlatformConnection as PC
    from sqlalchemy import and_

    conditions = [PC.merchant_id == merchant_id]
    if platform:
        conditions.append(PC.platform == platform)

    result = await db.execute(
        select(PC).where(and_(*conditions)).order_by(PC.created_at.desc())
    )
    return result.scalars().all()


@router.put("/connections/{connection_id}", response_model=PlatformConnectionResponse)
async def update_connection(
    connection_id: UUID,
    data: PlatformConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Update platform connection credentials."""
    merchant_id = _get_merchant_id(current_user)

    from app.models import PlatformConnection as PC
    result = await db.execute(
        select(PC).where(PC.id == connection_id, PC.merchant_id == merchant_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(conn, field, value)

    await db.flush()
    await db.refresh(conn)
    return conn


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Disconnect a platform."""
    merchant_id = _get_merchant_id(current_user)

    from app.models import PlatformConnection as PC
    result = await db.execute(
        select(PC).where(PC.id == connection_id, PC.merchant_id == merchant_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    await db.delete(conn)
    await db.flush()


# ---------------------------------------------------------------------------
# Order Ingestion Webhooks
# ---------------------------------------------------------------------------
@router.post("/webhook/talabat")
async def talabat_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Handle incoming Talabat order webhooks."""
    payload = await request.json()

    # Extract restaurant ID to find merchant
    restaurant_id = payload.get("order", {}).get("restaurant_id", "")

    # Find connection by merchant_ref
    from app.models import PlatformConnection as PC
    result = await db.execute(
        select(PC).where(PC.merchant_ref == restaurant_id, PC.platform == "talabat")
    )
    conn = result.scalar_one_or_none()

    if not conn:
        raise HTTPException(status_code=404, detail="Restaurant not registered")

    # Verify signature if configured
    if conn.webhook_secret and x_signature:
        body = await request.body()
        service = ThirdPartyService(db)
        valid = await service.verify_webhook_signature(
            PlatformType.talabat, body, x_signature, conn.webhook_secret
        )
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Ingest order
    service = ThirdPartyService(db)
    response = await service.ingest_order(
        merchant_id=conn.merchant_id,
        platform=PlatformType.talabat,
        raw_payload=payload,
        connection_id=conn.id
    )

    return response


@router.post("/webhook/zomato")
async def zomato_webhook(
    request: Request,
    x_zomato_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Handle incoming Zomato order webhooks."""
    payload = await request.json()

    restaurant_id = str(payload.get("order", {}).get("restaurant", {}).get("id", ""))

    from app.models import PlatformConnection as PC
    result = await db.execute(
        select(PC).where(PC.merchant_ref == restaurant_id, PC.platform == "zomato")
    )
    conn = result.scalar_one_or_none()

    if not conn:
        raise HTTPException(status_code=404, detail="Restaurant not registered")

    service = ThirdPartyService(db)
    response = await service.ingest_order(
        merchant_id=conn.merchant_id,
        platform=PlatformType.zomato,
        raw_payload=payload,
        connection_id=conn.id
    )

    return response


@router.post("/webhook/jahez")
async def jahez_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Handle incoming Jahez order webhooks."""
    payload = await request.json()

    branch_id = str(payload.get("data", {}).get("order", {}).get("branch_id", ""))

    from app.models import PlatformConnection as PC
    result = await db.execute(
        select(PC).where(PC.branch_id == branch_id, PC.platform == "jahez")
    )
    conn = result.scalar_one_or_none()

    if not conn:
        raise HTTPException(status_code=404, detail="Branch not registered")

    if conn.webhook_secret and x_signature:
        body = await request.body()
        service = ThirdPartyService(db)
        valid = await service.verify_webhook_signature(
            PlatformType.jahez, body, x_signature, conn.webhook_secret
        )
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid signature")

    service = ThirdPartyService(db)
    response = await service.ingest_order(
        merchant_id=conn.merchant_id,
        platform=PlatformType.jahez,
        raw_payload=payload,
        connection_id=conn.id
    )

    return response


# ---------------------------------------------------------------------------
# Menu Sync
# ---------------------------------------------------------------------------
@router.post("/sync/menu", response_model=MenuSyncResponse)
async def sync_menu(
    data: MenuSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Sync merchant menu to 3rd party platform."""
    merchant_id = _get_merchant_id(current_user)
    service = ThirdPartyService(db)
    return await service.sync_menu(merchant_id, data.connection_id, data.platform)


# ---------------------------------------------------------------------------
# Fallback Configuration
# ---------------------------------------------------------------------------
@router.get("/fallback/config", response_model=FallbackConfig)
async def get_fallback_config(
    current_user: User = Depends(get_current_active_user),
):
    """Get fallback orchestration config."""
    return FallbackConfig(
        enabled=True,
        max_retry_attempts=3,
        retry_delay_seconds=5,
        fallback_to_own_delivery=True,
        fallback_to_manual=True,
        notify_merchant_on_fallback=True
    )


@router.put("/fallback/config", response_model=FallbackConfig)
async def update_fallback_config(
    data: FallbackConfig,
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Update fallback config."""
    return data


# ---------------------------------------------------------------------------
# Fallback Trigger (Manual)
# ---------------------------------------------------------------------------
@router.post("/fallback/{order_id}", response_model=FallbackLogResponse)
async def trigger_fallback(
    order_id: UUID,
    platform: str,
    error: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Manually trigger fallback for a failed 3rd party order."""
    orchestrator = FallbackOrchestrator(db)
    config = FallbackConfig()

    try:
        pt = PlatformType(platform)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid platform: {platform}")

    return await orchestrator.handle_failure(order_id, pt, error, config)
