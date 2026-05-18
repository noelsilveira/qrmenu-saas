from datetime import datetime, time, timedelta
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MerchantBusinessHours


class BusinessHoursService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_merchant(self, merchant_id: UUID) -> List[MerchantBusinessHours]:
        result = await self.db.execute(
            select(MerchantBusinessHours)
            .where(MerchantBusinessHours.merchant_id == merchant_id)
            .order_by(MerchantBusinessHours.day_of_week)
        )
        return result.scalars().all()

    async def create(self, data: dict) -> MerchantBusinessHours:
        hours = MerchantBusinessHours(**data)
        self.db.add(hours)
        await self.db.flush()
        await self.db.refresh(hours)
        return hours

    async def update(self, hours_id: UUID, merchant_id: UUID, data: dict) -> Optional[MerchantBusinessHours]:
        result = await self.db.execute(
            select(MerchantBusinessHours).where(
                MerchantBusinessHours.id == hours_id,
                MerchantBusinessHours.merchant_id == merchant_id,
            )
        )
        hours = result.scalar_one_or_none()
        if not hours:
            return None

        for field, value in data.items():
            if value is not None:
                setattr(hours, field, value)

        await self.db.flush()
        await self.db.refresh(hours)
        return hours

    async def delete(self, hours_id: UUID, merchant_id: UUID) -> bool:
        result = await self.db.execute(
            select(MerchantBusinessHours).where(
                MerchantBusinessHours.id == hours_id,
                MerchantBusinessHours.merchant_id == merchant_id,
            )
        )
        hours = result.scalar_one_or_none()
        if not hours:
            return False
        await self.db.delete(hours)
        await self.db.flush()
        return True


class BusinessHoursValidator:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def is_open(self, merchant_id: UUID, check_time: Optional[datetime] = None) -> dict:
        now = check_time or datetime.utcnow()
        day_of_week = now.weekday()

        # Check special date first
        result = await self.db.execute(
            select(MerchantBusinessHours).where(
                MerchantBusinessHours.merchant_id == merchant_id,
                MerchantBusinessHours.special_date == now.date(),
            )
        )
        special = result.scalar_one_or_none()
        if special:
            if special.is_closed:
                return {"open": False, "closes_at": None, "opens_at": None, "minutes_until_close": 0}
            if special.is_24h:
                return {"open": True, "closes_at": None, "opens_at": None, "minutes_until_close": 1440}
            closes_at = datetime.combine(now.date(), special.special_close) if special.special_close else None
            minutes = 0
            if closes_at:
                minutes = int((closes_at - now).total_seconds() / 60)
            return {
                "open": True,
                "closes_at": special.special_close.isoformat() if special.special_close else None,
                "opens_at": special.special_open.isoformat() if special.special_open else None,
                "minutes_until_close": max(minutes, 0),
            }

        # Check regular hours
        result = await self.db.execute(
            select(MerchantBusinessHours).where(
                MerchantBusinessHours.merchant_id == merchant_id,
                MerchantBusinessHours.day_of_week == day_of_week,
            )
        )
        regular = result.scalar_one_or_none()
        if not regular:
            return {"open": False, "closes_at": None, "opens_at": None, "minutes_until_close": 0}

        if regular.is_closed:
            return {"open": False, "closes_at": None, "opens_at": None, "minutes_until_close": 0}
        if regular.is_24h:
            return {"open": True, "closes_at": None, "opens_at": None, "minutes_until_close": 1440}

        open_time = regular.open_time
        close_time = regular.close_time

        if not open_time or not close_time:
            return {"open": False, "closes_at": None, "opens_at": None, "minutes_until_close": 0}

        current_time = now.time()

        # Handle overnight shifts (e.g., 18:00 - 02:00)
        if close_time < open_time:
            is_open = current_time >= open_time or current_time <= close_time
            if is_open:
                if current_time <= close_time:
                    closes_at = datetime.combine(now.date(), close_time)
                else:
                    closes_at = datetime.combine(now.date() + timedelta(days=1), close_time)
                minutes = int((closes_at - now).total_seconds() / 60)
                return {
                    "open": True,
                    "closes_at": close_time.isoformat(),
                    "opens_at": open_time.isoformat(),
                    "minutes_until_close": max(minutes, 0),
                }
            else:
                return {"open": False, "closes_at": close_time.isoformat(), "opens_at": open_time.isoformat(), "minutes_until_close": 0}
        else:
            is_open = open_time <= current_time <= close_time
            if is_open:
                closes_at = datetime.combine(now.date(), close_time)
                minutes = int((closes_at - now).total_seconds() / 60)
                return {
                    "open": True,
                    "closes_at": close_time.isoformat(),
                    "opens_at": open_time.isoformat(),
                    "minutes_until_close": max(minutes, 0),
                }
            else:
                return {"open": False, "closes_at": close_time.isoformat(), "opens_at": open_time.isoformat(), "minutes_until_close": 0}
