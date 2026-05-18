from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.db.session import get_db
from app.core.auth import get_current_active_user
from app.schemas.business_hours import BusinessHoursCreate, BusinessHoursUpdate, BusinessHoursResponse
from app.services.whatsapp.business_hours_service import BusinessHoursService, BusinessHoursValidator
from app.models import User

router = APIRouter()


@router.get("/", response_model=List[BusinessHoursResponse])
async def list_hours(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = BusinessHoursService(db)
    return await service.list_by_merchant(current_user.merchant_id)


@router.post("/", response_model=BusinessHoursResponse, status_code=status.HTTP_201_CREATED)
async def create_hours(
    data: BusinessHoursCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = BusinessHoursService(db)
    create_data = data.model_dump()
    create_data["merchant_id"] = str(current_user.merchant_id)
    return await service.create(create_data)


@router.put("/{hours_id}", response_model=BusinessHoursResponse)
async def update_hours(
    hours_id: str,
    data: BusinessHoursUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    from uuid import UUID
    service = BusinessHoursService(db)
    updated = await service.update(UUID(hours_id), current_user.merchant_id, data.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business hours not found")
    return updated


@router.delete("/{hours_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hours(
    hours_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    from uuid import UUID
    service = BusinessHoursService(db)
    deleted = await service.delete(UUID(hours_id), current_user.merchant_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business hours not found")
    return None


@router.get("/check")
async def check_open(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    validator = BusinessHoursValidator(db)
    return await validator.is_open(current_user.merchant_id)
