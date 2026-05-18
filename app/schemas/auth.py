from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID
from datetime import datetime

from app.models.models import UserRole


class TenantCreate(BaseModel):
    name: str
    slug: str
    plan_id: Optional[UUID] = None


class TenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class MerchantCreate(BaseModel):
    business_name: str
    slug: str
    industry_template_id: Optional[UUID] = None
    whatsapp_number: Optional[str] = None
    currency: str = "BHD"
    timezone: str = "Asia/Bahrain"


class MerchantResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    business_name: str
    slug: str
    logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None
    brand_secondary_color: Optional[str] = None
    whatsapp_number: Optional[str] = None
    currency: str
    timezone: str
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None


class UserResponse(BaseModel):
    id: UUID
    email: Optional[str] = None
    phone: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: UserRole
    is_active: bool
    merchant_id: UUID

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class StaffInviteRequest(BaseModel):
    email: EmailStr
    role: UserRole


class JWTPayload(BaseModel):
    sub: str
    tenant_id: Optional[str] = None
    merchant_id: Optional[str] = None
    role: Optional[str] = None
    scope: Optional[str] = None
    exp: Optional[datetime] = None
    type: str = "access"
