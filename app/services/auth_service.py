from datetime import datetime, time
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tenant, Merchant, User, MerchantBusinessHours, MerchantAcceptanceSettings, SubscriptionPlan
from app.models.models import UserRole, OutsideHoursAction, AcceptanceMode
from app.core.security import get_password_hash, verify_password, create_access_token, create_refresh_token
from app.schemas.auth import TenantCreate, MerchantCreate, UserRegister, LoginRequest


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_tenant(self, data: TenantCreate) -> Tenant:
        tenant = Tenant(
            name=data.name,
            slug=data.slug,
            plan_id=data.plan_id,
            is_active=True,
            settings={},
        )
        self.db.add(tenant)
        await self.db.flush()
        await self.db.refresh(tenant)
        return tenant

    async def register_merchant(self, data: MerchantCreate, tenant_id: UUID) -> Merchant:
        merchant = Merchant(
            tenant_id=tenant_id,
            business_name=data.business_name,
            slug=data.slug,
            industry_template_id=data.industry_template_id,
            whatsapp_number=data.whatsapp_number,
            currency=data.currency,
            timezone=data.timezone,
            is_verified=False,
        )
        self.db.add(merchant)
        await self.db.flush()
        await self.db.refresh(merchant)

        # Seed default business hours (9am - 10pm, all days)
        for day in range(7):
            bh = MerchantBusinessHours(
                merchant_id=merchant.id,
                day_of_week=day,
                open_time=time(9, 0),
                close_time=time(22, 0),
                is_closed=False,
                is_24h=False,
                timezone=data.timezone,
            )
            self.db.add(bh)

        # Seed default acceptance settings
        acc = MerchantAcceptanceSettings(
            merchant_id=merchant.id,
            auto_accept_enabled=False,
            auto_accept_timeout_sec=300,
            decline_auto_refund=True,
            outside_hours_action=OutsideHoursAction.auto_decline,
            max_pending_orders=10,
            acceptance_mode=AcceptanceMode.whatsapp,
            escalation_sms_after_min=15,
        )
        self.db.add(acc)
        await self.db.flush()

        return merchant

    async def register_owner(self, data: UserRegister, merchant_id: UUID) -> User:
        user = User(
            merchant_id=merchant_id,
            email=data.email,
            phone=data.phone,
            password_hash=get_password_hash(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            role=UserRole.owner,
            is_active=True,
            permissions={},
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def login(self, data: LoginRequest) -> Optional[Tuple[dict, dict]]:
        result = await self.db.execute(
            select(User).where(User.email == data.email, User.is_active == True)
        )
        user = result.scalar_one_or_none()
        if not user or not user.password_hash:
            return None
        if not verify_password(data.password, user.password_hash):
            return None

        # Get merchant and tenant info
        result = await self.db.execute(
            select(Merchant).where(Merchant.id == user.merchant_id)
        )
        merchant = result.scalar_one_or_none()
        tenant_id = merchant.tenant_id if merchant else None

        access_token = create_access_token(
            subject=user.id,
            tenant_id=tenant_id,
            merchant_id=user.merchant_id,
            role=user.role.value if user.role else None,
        )
        refresh_token = create_refresh_token(
            subject=user.id,
            tenant_id=tenant_id,
            merchant_id=user.merchant_id,
            role=user.role.value if user.role else None,
        )

        # Update last login
        user.last_login = datetime.utcnow()
        await self.db.flush()

        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}, user

    async def refresh_token(self, refresh_token_str: str) -> Optional[dict]:
        from app.core.security import decode_token
        payload = decode_token(refresh_token_str)
        if not payload or payload.get("type") != "refresh":
            return None

        user_id = payload.get("sub")
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )
        user = result.scalar_one_or_none()
        if not user:
            return None

        tenant_id = payload.get("tenant_id")
        merchant_id = payload.get("merchant_id")
        role = payload.get("role")

        new_access = create_access_token(
            subject=user.id,
            tenant_id=tenant_id,
            merchant_id=merchant_id,
            role=role,
        )
        new_refresh = create_refresh_token(
            subject=user.id,
            tenant_id=tenant_id,
            merchant_id=merchant_id,
            role=role,
        )

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
        }

    async def invite_staff(self, email: str, role: UserRole, merchant_id: UUID, invited_by: User) -> User:
        user = User(
            merchant_id=merchant_id,
            email=email,
            role=role,
            is_active=True,
            permissions={},
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user
