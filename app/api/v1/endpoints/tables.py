from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_active_user, require_role
from app.core.cache import cache_delete_pattern
from app.models import User, Merchant, Table, QRSession
from app.models.models import TableStatus
from app.schemas.qr import TableCreate, TableUpdate, TableResponse, QRResponse
from app.services.qr_service import (
    generate_qr_image, save_qr_file, get_qr_file_path, rotate_qr_token,
)

router = APIRouter()


def _get_merchant_id(user: User) -> UUID:
    return user.merchant_id


@router.post("", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
async def create_table(
    data: TableCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    merchant_id = _get_merchant_id(current_user)
    qr_token = rotate_qr_token()

    table = Table(
        merchant_id=merchant_id,
        location_id=data.location_id,
        table_number=data.table_number,
        seating_capacity=data.seating_capacity,
        qr_token=qr_token,
        status=TableStatus.free,
    )
    db.add(table)
    await db.flush()
    await db.refresh(table)

    # Generate QR code
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == merchant_id)
    )
    merchant = merchant_result.scalar_one_or_none()
    merchant_slug = merchant.slug if merchant else "unknown"
    merchant_name = merchant.business_name if merchant else "Menu"
    primary_color = merchant.brand_primary_color if merchant else "#3B82F6"
    secondary_color = merchant.brand_secondary_color if merchant else "#F3F4F6"
    logo_path = None

    img_bytes, filename = generate_qr_image(
        qr_token=qr_token,
        merchant_slug=merchant_slug,
        table_number=data.table_number,
        merchant_name=merchant_name,
        primary_color=primary_color,
        secondary_color=secondary_color,
        logo_path=logo_path,
        fmt="png",
    )
    qr_url = save_qr_file(img_bytes, filename)
    table.qr_code_url = qr_url
    await db.flush()

    return TableResponse(
        id=table.id,
        merchant_id=table.merchant_id,
        location_id=table.location_id,
        table_number=table.table_number,
        seating_capacity=table.seating_capacity,
        qr_code_url=table.qr_code_url,
        qr_token=table.qr_token,
        status=table.status.value,
        last_occupied_at=table.last_occupied_at,
        created_at=table.created_at,
    )


@router.get("", response_model=list[TableResponse])
async def list_tables(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    merchant_id = _get_merchant_id(current_user)
    conditions = [Table.merchant_id == merchant_id]
    if status:
        conditions.append(Table.status == status)

    result = await db.execute(
        select(Table).where(and_(*conditions)).order_by(Table.table_number.asc())
    )
    tables = result.scalars().all()
    return [
        TableResponse(
            id=t.id,
            merchant_id=t.merchant_id,
            location_id=t.location_id,
            table_number=t.table_number,
            seating_capacity=t.seating_capacity,
            qr_code_url=t.qr_code_url,
            qr_token=t.qr_token,
            status=t.status.value,
            last_occupied_at=t.last_occupied_at,
            created_at=t.created_at,
        )
        for t in tables
    ]


@router.get("/{table_id}", response_model=TableResponse)
async def get_table(
    table_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    merchant_id = _get_merchant_id(current_user)
    result = await db.execute(
        select(Table).where(
            Table.id == table_id,
            Table.merchant_id == merchant_id,
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return TableResponse(
        id=table.id,
        merchant_id=table.merchant_id,
        location_id=table.location_id,
        table_number=table.table_number,
        seating_capacity=table.seating_capacity,
        qr_code_url=table.qr_code_url,
        qr_token=table.qr_token,
        status=table.status.value,
        last_occupied_at=table.last_occupied_at,
        created_at=table.created_at,
    )


@router.put("/{table_id}", response_model=TableResponse)
async def update_table(
    table_id: UUID,
    data: TableUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    merchant_id = _get_merchant_id(current_user)
    result = await db.execute(
        select(Table).where(
            Table.id == table_id,
            Table.merchant_id == merchant_id,
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "status" and value:
            value = TableStatus(value)
        setattr(table, field, value)

    await db.flush()
    await db.refresh(table)
    return TableResponse(
        id=table.id,
        merchant_id=table.merchant_id,
        location_id=table.location_id,
        table_number=table.table_number,
        seating_capacity=table.seating_capacity,
        qr_code_url=table.qr_code_url,
        qr_token=table.qr_token,
        status=table.status.value,
        last_occupied_at=table.last_occupied_at,
        created_at=table.created_at,
    )


@router.get("/{table_id}/qr")
async def download_qr(
    table_id: UUID,
    format: str = Query("png"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    merchant_id = _get_merchant_id(current_user)
    result = await db.execute(
        select(Table).where(
            Table.id == table_id,
            Table.merchant_id == merchant_id,
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    if format.lower() == "svg":
        # Generate SVG on the fly
        merchant_result = await db.execute(
            select(Merchant).where(Merchant.id == merchant_id)
        )
        merchant = merchant_result.scalar_one_or_none()
        merchant_slug = merchant.slug if merchant else "unknown"

        from app.services.qr_service import generate_qr_image, save_qr_file
        img_bytes, filename = generate_qr_image(
            qr_token=table.qr_token,
            merchant_slug=merchant_slug,
            table_number=table.table_number,
            fmt="svg",
        )
        filepath = get_qr_file_path(filename)
        with open(filepath, "wb") as f:
            f.write(img_bytes)
        return FileResponse(filepath, media_type="image/svg+xml", filename=filename)

    # PNG: serve from stored file or regenerate
    if table.qr_code_url:
        filename = table.qr_code_url.split("/")[-1]
        filepath = get_qr_file_path(filename)
        if filepath and filepath.exists():
            return FileResponse(filepath, media_type="image/png", filename=filename)

    raise HTTPException(status_code=404, detail="QR file not found")


@router.post("/{table_id}/regenerate-qr", response_model=TableResponse)
async def regenerate_qr(
    table_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    merchant_id = _get_merchant_id(current_user)
    result = await db.execute(
        select(Table).where(
            Table.id == table_id,
            Table.merchant_id == merchant_id,
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    # Rotate token
    table.qr_token = rotate_qr_token()

    # Regenerate QR
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == merchant_id)
    )
    merchant = merchant_result.scalar_one_or_none()
    merchant_slug = merchant.slug if merchant else "unknown"
    merchant_name = merchant.business_name if merchant else "Menu"
    primary_color = merchant.brand_primary_color if merchant else "#3B82F6"
    secondary_color = merchant.brand_secondary_color if merchant else "#F3F4F6"

    img_bytes, filename = generate_qr_image(
        qr_token=table.qr_token,
        merchant_slug=merchant_slug,
        table_number=table.table_number,
        merchant_name=merchant_name,
        primary_color=primary_color,
        secondary_color=secondary_color,
        fmt="png",
    )
    qr_url = save_qr_file(img_bytes, filename)
    table.qr_code_url = qr_url
    await db.flush()
    await db.refresh(table)

    return TableResponse(
        id=table.id,
        merchant_id=table.merchant_id,
        location_id=table.location_id,
        table_number=table.table_number,
        seating_capacity=table.seating_capacity,
        qr_code_url=table.qr_code_url,
        qr_token=table.qr_token,
        status=table.status.value,
        last_occupied_at=table.last_occupied_at,
        created_at=table.created_at,
    )


@router.get("/{table_id}/session")
async def get_table_session(
    table_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    merchant_id = _get_merchant_id(current_user)
    result = await db.execute(
        select(Table).where(
            Table.id == table_id,
            Table.merchant_id == merchant_id,
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    session_result = await db.execute(
        select(QRSession)
        .where(
            QRSession.table_id == table_id,
            QRSession.status == "active",
        )
        .order_by(QRSession.started_at.desc())
        .limit(1)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        return {"session": None}

    return {
        "session": {
            "id": session.id,
            "session_token": session.session_token,
            "customer_phone": session.customer_phone,
            "customer_name": session.customer_name,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "expires_at": session.expires_at.isoformat() if session.expires_at else None,
            "status": session.status,
        }
    }
