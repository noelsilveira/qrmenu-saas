from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_active_user
from app.schemas.acceptance_settings import AcceptanceSettingsUpdate, AcceptanceSettingsResponse
from app.services.whatsapp.acceptance_service import AcceptanceSettingsService
from app.models import User

router = APIRouter()


@router.get("/", response_model=AcceptanceSettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = AcceptanceSettingsService(db)
    settings = await service.get_by_merchant(current_user.merchant_id)
    if not settings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Acceptance settings not found")
    return settings


@router.put("/", response_model=AcceptanceSettingsResponse)
async def update_settings(
    data: AcceptanceSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = AcceptanceSettingsService(db)
    settings = await service.create_or_update(
        current_user.merchant_id,
        data.model_dump(exclude_unset=True),
    )
    return settings
