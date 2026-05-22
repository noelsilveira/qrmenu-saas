from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from enum import Enum


class PlatformType(str, Enum):
    talabat = "talabat"
    zomato = "zomato"
    jahez = "jahez"
    careem = "careem"
    custom = "custom"


class PlatformStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    error = "error"
    rate_limited = "rate_limited"


class SyncStatus(str, Enum):
    pending = "pending"
    syncing = "syncing"
    completed = "completed"
    failed = "failed"
    partial = "partial"


# ---------------------------------------------------------------------------
# Platform Connection Schemas
# ---------------------------------------------------------------------------
class PlatformConnectionCreate(BaseModel):
    platform: PlatformType
    merchant_ref: str  # External merchant ID on the platform
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    branch_id: Optional[str] = None
    is_active: bool = True


class PlatformConnectionUpdate(BaseModel):
    merchant_ref: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    branch_id: Optional[str] = None
    is_active: Optional[bool] = None


class PlatformConnectionResponse(BaseModel):
    id: UUID
    merchant_id: UUID
    platform: PlatformType
    merchant_ref: str
    branch_id: Optional[str]
    status: PlatformStatus
    last_sync_at: Optional[datetime]
    last_error: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# 3rd Party Order Schemas (Normalized)
# ---------------------------------------------------------------------------
class ThirdPartyOrderItem(BaseModel):
    external_item_id: str
    name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    modifiers: List[Dict[str, Any]] = []
    special_instructions: Optional[str] = None


class ThirdPartyOrderPayload(BaseModel):
    external_order_id: str
    platform: PlatformType
    customer_name: Optional[str] = None
    customer_phone: str
    delivery_address: Optional[Dict[str, Any]] = None
    items: List[ThirdPartyOrderItem]
    subtotal: Decimal
    tax_amount: Decimal = Decimal("0.000")
    delivery_fee: Decimal = Decimal("0.000")
    discount_amount: Decimal = Decimal("0.000")
    total: Decimal
    currency: str = "BHD"
    notes: Optional[str] = None
    estimated_ready_min: int = 30
    payment_method: str = "online"  # online, cod, wallet
    payment_status: str = "paid"  # paid, pending, failed


class ThirdPartyOrderResponse(BaseModel):
    internal_order_id: UUID
    external_order_id: str
    platform: PlatformType
    status: str
    message: str
    accepted: bool


# ---------------------------------------------------------------------------
# Menu Sync Schemas
# ---------------------------------------------------------------------------
class MenuSyncRequest(BaseModel):
    platform: PlatformType
    connection_id: UUID
    sync_type: str = "full"  # full, incremental, categories_only, items_only


class MenuSyncItem(BaseModel):
    external_id: Optional[str] = None
    name: str
    name_localized: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    price: Decimal
    category_name: str
    category_external_id: Optional[str] = None
    image_url: Optional[str] = None
    is_available: bool = True


class MenuSyncResponse(BaseModel):
    sync_id: UUID
    platform: PlatformType
    status: SyncStatus
    items_synced: int
    items_failed: int
    categories_synced: int
    errors: List[str] = []
    started_at: datetime
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Webhook Schemas (Per Platform)
# ---------------------------------------------------------------------------
class TalabatWebhookPayload(BaseModel):
    event_type: str
    order_id: str
    restaurant_id: str
    timestamp: str
    payload: Dict[str, Any]


class ZomatoWebhookPayload(BaseModel):
    event: str
    order: Dict[str, Any]
    restaurant: Dict[str, Any]
    timestamp: int


class JahezWebhookPayload(BaseModel):
    event_type: str
    data: Dict[str, Any]
    signature: Optional[str] = None


# ---------------------------------------------------------------------------
# Fallback Orchestration Schemas
# ---------------------------------------------------------------------------
class FallbackConfig(BaseModel):
    enabled: bool = True
    max_retry_attempts: int = 3
    retry_delay_seconds: int = 5
    fallback_to_own_delivery: bool = True
    fallback_to_manual: bool = True
    notify_merchant_on_fallback: bool = True


class FallbackLogResponse(BaseModel):
    id: UUID
    order_id: UUID
    platform: PlatformType
    attempt: int
    action: str  # retry, fallback_own, fallback_manual, fail
    error: Optional[str] = None
    success: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Reconciliation Schemas
# ---------------------------------------------------------------------------
class PlatformPayout(BaseModel):
    platform: PlatformType
    period_start: datetime
    period_end: datetime
    total_orders: int
    total_sales: Decimal
    platform_fees: Decimal
    net_payout: Decimal
    currency: str
    status: str  # pending, confirmed, disputed


class ReconciliationSummary(BaseModel):
    merchant_id: UUID
    period_start: datetime
    period_end: datetime
    platforms: List[PlatformPayout]
    total_orders_all_platforms: int
    total_sales_all_platforms: Decimal
    total_platform_fees: Decimal
    total_net_payout: Decimal
    own_orders: int
    own_sales: Decimal
    discrepancy: Optional[Decimal] = None
