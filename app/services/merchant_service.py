from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Merchant
from app.schemas.merchant import MerchantBrandingUpdate, MerchantSettingsUpdate


class MerchantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, merchant_id: UUID) -> Optional[Merchant]:
        result = await self.db.execute(select(Merchant).where(Merchant.id == merchant_id))
        return result.scalar_one_or_none()

    async def update_branding(self, merchant_id: UUID, data: MerchantBrandingUpdate) -> Merchant:
        result = await self.db.execute(select(Merchant).where(Merchant.id == merchant_id))
        merchant = result.scalar_one()

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(merchant, field, value)

        await self.db.flush()
        await self.db.refresh(merchant)
        return merchant

    async def update_settings(self, merchant_id: UUID, data: MerchantSettingsUpdate) -> Merchant:
        result = await self.db.execute(select(Merchant).where(Merchant.id == merchant_id))
        merchant = result.scalar_one()

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(merchant, field, value)

        await self.db.flush()
        await self.db.refresh(merchant)
        return merchant

    async def get_public_profile(self, slug: str) -> Optional[Merchant]:
        result = await self.db.execute(
            select(Merchant).where(Merchant.slug == slug)
        )
        return result.scalar_one_or_none()
