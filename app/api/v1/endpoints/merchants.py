from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_active_user, require_role
from app.schemas.merchant import (
    MerchantBrandingUpdate,
    MerchantPublicProfile,
    MerchantSettingsUpdate,
    MerchantSettingsResponse,
)
from app.services.merchant_service import MerchantService
from app.models import User

router = APIRouter()


@router.put("/branding")
async def update_branding(
    data: MerchantBrandingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    service = MerchantService(db)
    return await service.update_branding(current_user.merchant_id, data)


@router.get("/public-profile")
async def get_public_profile(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    service = MerchantService(db)
    merchant = await service.get_public_profile(slug)
    if not merchant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    return MerchantPublicProfile(
        business_name=merchant.business_name,
        logo_url=merchant.logo_url,
        colors={
            "primary": merchant.brand_primary_color,
            "secondary": merchant.brand_secondary_color,
        },
        background=merchant.brand_bg_image_url,
    )


@router.put("/settings")
async def update_settings(
    data: MerchantSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    service = MerchantService(db)
    return await service.update_settings(current_user.merchant_id, data)


@router.get("/settings", response_model=MerchantSettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = MerchantService(db)
    merchant = await service.get_by_id(current_user.merchant_id)
    if not merchant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    return MerchantSettingsResponse(
        currency=merchant.currency,
        timezone=merchant.timezone,
    )
