from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MerchantAcceptanceSettings


class AcceptanceService:
    def __init__(self, db):
        self.db = db

    async def handle_interactive_response(self, payload):
        return {"status": "received", "action": "stub"}

    async def handle_delivery_status(self, payload):
        return {"status": "received", "delivery": "stub"}


class AcceptanceSettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_merchant(self, merchant_id: UUID) -> Optional[MerchantAcceptanceSettings]:
        result = await self.db.execute(
            select(MerchantAcceptanceSettings).where(
                MerchantAcceptanceSettings.merchant_id == merchant_id
            )
        )
        return result.scalar_one_or_none()

    async def create_or_update(self, merchant_id: UUID, data: dict) -> MerchantAcceptanceSettings:
        result = await self.db.execute(
            select(MerchantAcceptanceSettings).where(
                MerchantAcceptanceSettings.merchant_id == merchant_id
            )
        )
        settings = result.scalar_one_or_none()

        if not settings:
            settings = MerchantAcceptanceSettings(merchant_id=merchant_id, **data)
            self.db.add(settings)
        else:
            for field, value in data.items():
                if value is not None:
                    setattr(settings, field, value)

        await self.db.flush()
        await self.db.refresh(settings)
        return settings

    async def delete(self, merchant_id: UUID) -> bool:
        result = await self.db.execute(
            select(MerchantAcceptanceSettings).where(
                MerchantAcceptanceSettings.merchant_id == merchant_id
            )
        )
        settings = result.scalar_one_or_none()
        if not settings:
            return False
        await self.db.delete(settings)
        await self.db.flush()
        return True
