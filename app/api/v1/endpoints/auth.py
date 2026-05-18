from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import decode_token
from app.core.auth import get_current_user, get_current_active_user, require_role
from app.schemas.auth import (
    TenantCreate, TenantResponse,
    MerchantCreate, MerchantResponse,
    UserRegister, UserResponse,
    LoginRequest, TokenPair, RefreshRequest,
    StaffInviteRequest,
)
from app.services.auth_service import AuthService
from app.models import User

router = APIRouter()


@router.post("/register/tenant", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def register_tenant(
    data: TenantCreate,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    return await service.register_tenant(data)


@router.post("/register/merchant", response_model=MerchantResponse, status_code=status.HTTP_201_CREATED)
async def register_merchant(
    data: MerchantCreate,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID
    service = AuthService(db)
    return await service.register_merchant(data, UUID(tenant_id))


@router.post("/register/owner", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_owner(
    data: UserRegister,
    merchant_id: str,
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID
    service = AuthService(db)
    return await service.register_owner(data, UUID(merchant_id))


@router.post("/login", response_model=TokenPair)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    result = await service.login(data)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    tokens, user = result
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "expires_in": 900,
    }


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    tokens = await service.refresh_token(data.refresh_token)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "expires_in": 900,
    }


@router.post("/invite-staff", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def invite_staff(
    data: StaffInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    service = AuthService(db)
    return await service.invite_staff(
        email=data.email,
        role=data.role,
        merchant_id=current_user.merchant_id,
        invited_by=current_user,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_active_user),
):
    return current_user
