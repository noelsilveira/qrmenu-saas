from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from enum import Enum


class OrderType(str, Enum):
    dine_in = "dine_in"
    takeaway = "takeaway"
    delivery = "delivery"
    drive_in = "drive_in"


class OrderStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    preparing = "preparing"
    ready = "ready"
    served = "served"
    cancelled = "cancelled"
    refunded = "refunded"


class PaymentMethod(str, Enum):
    stripe = "stripe"
    paypal = "paypal"
    cod = "cod"
    wallet = "wallet"


class PaymentStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


# ---------------------------------------------------------------------------
# Cart Schemas
# ---------------------------------------------------------------------------
class CartModifierOption(BaseModel):
    option_id: UUID
    name: str
    price_adjustment: Decimal = Decimal("0.000")


class CartItemModifier(BaseModel):
    modifier_id: UUID
    name: str
    selected_options: List[CartModifierOption]


class CartItem(BaseModel):
    item_id: UUID
    name: str
    quantity: int = Field(..., ge=1)
    unit_price: Decimal
    modifiers: List[CartItemModifier] = []
    special_instructions: Optional[str] = None

    @property
    def line_total(self) -> Decimal:
        mod_total = sum(
            opt.price_adjustment
            for mod in self.modifiers
            for opt in mod.selected_options
        )
        return (self.unit_price + mod_total) * self.quantity


class Cart(BaseModel):
    merchant_id: UUID
    table_id: Optional[UUID] = None
    session_token: Optional[str] = None
    items: List[CartItem] = []
    notes: Optional[str] = None

    @property
    def subtotal(self) -> Decimal:
        return sum(item.line_total for item in self.items)


class CartAddRequest(BaseModel):
    item_id: UUID
    quantity: int = Field(1, ge=1)
    modifier_options: List[UUID] = []
    special_instructions: Optional[str] = None


class CartUpdateRequest(BaseModel):
    quantity: Optional[int] = Field(None, ge=0)
    special_instructions: Optional[str] = None


class CartResponse(BaseModel):
    items: List[CartItem]
    subtotal: Decimal
    tax_amount: Decimal = Decimal("0.000")
    delivery_fee: Decimal = Decimal("0.000")
    discount_amount: Decimal = Decimal("0.000")
    total: Decimal
    item_count: int
    expires_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Checkout Schemas
# ---------------------------------------------------------------------------
class CheckoutRequest(BaseModel):
    customer_phone: str
    customer_name: Optional[str] = None
    order_type: OrderType = OrderType.dine_in
    payment_method: PaymentMethod
    notes: Optional[str] = None
    delivery_address: Optional[dict] = None
    discount_code: Optional[str] = None


class CheckoutResponse(BaseModel):
    order_id: UUID
    status: OrderStatus
    total: Decimal
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    client_secret: Optional[str] = None
    paypal_order_id: Optional[str] = None
    redirect_url: Optional[str] = None
    expires_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Order Item Response
# ---------------------------------------------------------------------------
class OrderItemModifierResponse(BaseModel):
    modifier_name: str
    selected_options: List[str]
    price_adjustment: Decimal


class OrderItemResponse(BaseModel):
    id: UUID
    menu_item_id: UUID
    name: str
    name_localized: Optional[dict] = None
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    modifiers: List[OrderItemModifierResponse] = []
    special_instructions: Optional[str] = None
    prep_time_min: int
    status: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Order Response
# ---------------------------------------------------------------------------
class OrderResponse(BaseModel):
    id: UUID
    merchant_id: UUID
    table_id: Optional[UUID] = None
    customer_phone: str
    customer_name: Optional[str] = None
    session_token: Optional[str] = None
    order_type: OrderType
    status: OrderStatus
    payment_method: Optional[PaymentMethod] = None
    payment_status: PaymentStatus
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    delivery_fee: Decimal
    total: Decimal
    currency: str
    notes: Optional[str] = None
    items: List[OrderItemResponse] = []
    estimated_ready_at: Optional[datetime] = None
    served_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderListResponse(BaseModel):
    orders: List[OrderResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Order Status Update (Kitchen / Merchant)
# ---------------------------------------------------------------------------
class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    reason: Optional[str] = None


class OrderItemStatusUpdate(BaseModel):
    item_id: UUID
    status: str


class BulkOrderStatusUpdate(BaseModel):
    order_ids: List[UUID]
    status: OrderStatus


# ---------------------------------------------------------------------------
# Payment Schemas
# ---------------------------------------------------------------------------
class PaymentIntentRequest(BaseModel):
    order_id: UUID
    method: PaymentMethod
    return_url: Optional[str] = None


class PaymentIntentResponse(BaseModel):
    transaction_id: UUID
    client_secret: Optional[str] = None
    paypal_order_id: Optional[str] = None
    redirect_url: Optional[str] = None
    amount: Decimal
    currency: str
    status: PaymentStatus


class PaymentConfirmRequest(BaseModel):
    transaction_id: UUID
    provider_ref: str


class PaymentWebhookPayload(BaseModel):
    event_type: str
    provider: str
    payload: dict


class RefundRequest(BaseModel):
    order_id: UUID
    amount: Optional[Decimal] = None
    reason: Optional[str] = None


class RefundResponse(BaseModel):
    transaction_id: UUID
    refunded_amount: Decimal
    status: PaymentStatus
    refund_ref: Optional[str] = None
