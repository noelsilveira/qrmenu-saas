from uuid import UUID
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.config import settings
from app.models import Table, QRSession, Merchant
from app.schemas.qr import QRScanRequest, QRScanResponse, QRValidateResponse
from app.services.qr_service import generate_qr_url

router = APIRouter()


@router.post("/scan", response_model=QRScanResponse, status_code=status.HTTP_201_CREATED)
async def scan_qr(
    data: QRScanRequest,
    db: AsyncSession = Depends(get_db),
):
    # Find table by QR token
    result = await db.execute(
        select(Table).where(Table.qr_token == data.qr_token)
    )
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Invalid QR code")

    # Get merchant
    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == table.merchant_id)
    )
    merchant = merchant_result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    # Create or update session
    session_token = UUID(int=0).hex  # placeholder, use proper token
    import secrets
    session_token = secrets.token_urlsafe(32)

    expires_at = datetime.utcnow() + timedelta(hours=4)

    session = QRSession(
        table_id=table.id,
        session_token=session_token,
        customer_phone=data.customer_phone,
        customer_name=data.customer_name,
        expires_at=expires_at,
        status="active",
    )
    db.add(session)

    # Update table status
    table.status = "occupied"
    table.last_occupied_at = datetime.utcnow()
    await db.flush()

    menu_url = generate_qr_url(
        qr_token=table.qr_token,
        merchant_slug=merchant.slug,
        table_number=table.table_number,
    )

    return QRScanResponse(
        menu_url=menu_url,
        session_token=session_token,
        merchant_name=merchant.business_name,
        table_number=table.table_number,
        table_id=table.id,
        expires_at=expires_at,
    )


@router.get("/validate", response_model=QRValidateResponse)
async def validate_session(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(QRSession).where(
            QRSession.session_token == token,
            QRSession.status == "active",
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        return QRValidateResponse(valid=False)

    if session.expires_at and session.expires_at < datetime.utcnow():
        session.status = "expired"
        await db.flush()
        return QRValidateResponse(valid=False)

    # Get table and merchant
    table_result = await db.execute(
        select(Table).where(Table.id == session.table_id)
    )
    table = table_result.scalar_one_or_none()
    if not table:
        return QRValidateResponse(valid=False)

    merchant_result = await db.execute(
        select(Merchant).where(Merchant.id == table.merchant_id)
    )
    merchant = merchant_result.scalar_one_or_none()
    if not merchant:
        return QRValidateResponse(valid=False)

    return QRValidateResponse(
        valid=True,
        merchant_id=merchant.id,
        merchant_name=merchant.business_name,
        merchant_slug=merchant.slug,
        table_id=table.id,
        table_number=table.table_number,
        session_token=session.session_token,
        expires_at=session.expires_at,
    )
