import uuid
from datetime import datetime, time, date
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional, List

from sqlalchemy import (
    ForeignKey, String, Boolean, DateTime, Time, Date,
    Integer, Text, Numeric, Enum, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class UserRole(PyEnum):
    owner = "owner"
    manager = "manager"
    cashier = "cashier"
    kitchen = "kitchen"
    readonly = "readonly"


class OrderTypeEnum(PyEnum):
    dine_in = "dine_in"
    drive_in = "drive_in"
    pickup = "pickup"
    delivery = "delivery"
    web = "web"


class OrderStatus(PyEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    READY = "READY"
    SERVED = "SERVED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class DeliveryType(PyEnum):
    in_house = "in_house"
    third_party = "third_party"
    pickup = "pickup"
    dine_in = "dine_in"


class AcceptanceStatus(PyEnum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    auto_accepted = "auto_accepted"
    timeout = "timeout"


class AcceptedBy(PyEnum):
    merchant = "merchant"
    system = "system"
    whatsapp = "whatsapp"


class TableStatus(PyEnum):
    free = "free"
    occupied = "occupied"
    reserved = "reserved"


class DriverShiftStatus(PyEnum):
    scheduled = "scheduled"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class SettlementStatus(PyEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ReconciliationStatus(PyEnum):
    open = "open"
    processing = "processing"
    matched = "matched"
    variance = "variance"
    closed = "closed"


class OrderTagEnum(PyEnum):
    urgent = "urgent"
    allergy = "allergy"
    vip = "vip"
    complimentary = "complimentary"


class PaymentGateway(PyEnum):
    stripe = "stripe"
    paypal = "paypal"
    hyperpay = "hyperpay"
    telr = "telr"
    cod = "cod"


class PaymentStatus(PyEnum):
    pending = "pending"
    authorized = "authorized"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"
    partially_refunded = "partially_refunded"


class WhatsAppMessageStatus(PyEnum):
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class WhatsAppAction(PyEnum):
    accept = "accept"
    decline = "decline"
    timeout = "timeout"


class OutsideHoursAction(PyEnum):
    auto_decline = "auto_decline"
    schedule_next_day = "schedule_next_day"
    allow_anyway = "allow_anyway"


class AcceptanceMode(PyEnum):
    manual = "manual"
    auto = "auto"
    whatsapp = "whatsapp"


class TemplateStatus(PyEnum):
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


class AssignmentType(PyEnum):
    auto = "auto"
    manual = "manual"
    driver_pickup = "driver_pickup"


class DeliveryAttemptStatus(PyEnum):
    pending = "pending"
    success = "success"
    failed = "failed"
    rescheduled = "rescheduled"


class ThirdPartyPartnerName(PyEnum):
    talabat = "talabat"
    zomato = "zomato"
    jahez = "jahez"


class AuthType(PyEnum):
    api_key = "api_key"
    oauth2 = "oauth2"
    basic = "basic"


# ---------------------------------------------------------------------------
# Shared Schema (public)
# ---------------------------------------------------------------------------
class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("public.subscription_plans.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    settings: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price_monthly: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    price_yearly: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    max_merchants: Mapped[int] = mapped_column(Integer, default=1)
    max_items: Mapped[int] = mapped_column(Integer, default=100)
    features: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)


class IndustryTemplate(Base):
    __tablename__ = "industry_templates"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    schema_defaults: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    preview_image_url: Mapped[Optional[str]] = mapped_column(String)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)


class SystemAuditLog(Base):
    __tablename__ = "system_audit_logs"
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    table_name: Mapped[str] = mapped_column(String, nullable=False)
    record_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    changed_fields: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Tenant Schema tables
# ---------------------------------------------------------------------------
class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    business_name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    industry_template_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("public.industry_templates.id"))
    logo_url: Mapped[Optional[str]] = mapped_column(String)
    brand_primary_color: Mapped[Optional[str]] = mapped_column(String, default="#3B82F6")
    brand_secondary_color: Mapped[Optional[str]] = mapped_column(String, default="#F3F4F6")
    brand_bg_image_url: Mapped[Optional[str]] = mapped_column(String)
    whatsapp_number: Mapped[Optional[str]] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String, default="BHD")
    timezone: Mapped[str] = mapped_column(String, default="Asia/Bahrain")
    tax_number: Mapped[Optional[str]] = mapped_column(String)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String)
    phone: Mapped[Optional[str]] = mapped_column(String)
    password_hash: Mapped[Optional[str]] = mapped_column(String)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.readonly)
    first_name: Mapped[Optional[str]] = mapped_column(String)
    last_name: Mapped[Optional[str]] = mapped_column(String)
    avatar_url: Mapped[Optional[str]] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)
    permissions: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String)
    city: Mapped[Optional[str]] = mapped_column(String)
    country: Mapped[Optional[str]] = mapped_column(String)
    phone: Mapped[Optional[str]] = mapped_column(String)
    email: Mapped[Optional[str]] = mapped_column(String)
    lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8))
    lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    opening_hours: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    phone: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String)
    email: Mapped[Optional[str]] = mapped_column(String)
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    visit_count: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    last_order_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MenuCategory(Base):
    __tablename__ = "menu_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_localized: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    description: Mapped[Optional[str]] = mapped_column(String)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[Optional[str]] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("menu_categories.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("menu_categories.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_localized: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    description: Mapped[Optional[str]] = mapped_column(String)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    compare_at_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    cost_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    image_urls: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    sku: Mapped[Optional[str]] = mapped_column(String)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    allergens: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    nutritional_info: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    prep_time_min: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ItemModifier(Base):
    __tablename__ = "item_modifiers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String)
    min_select: Mapped[int] = mapped_column(Integer, default=0)
    max_select: Mapped[int] = mapped_column(Integer, default=1)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ModifierOption(Base):
    __tablename__ = "modifier_options"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    modifier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item_modifiers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price_adjustment: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ItemModifierLink(Base):
    __tablename__ = "item_modifier_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("menu_items.id"), nullable=False)
    modifier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item_modifiers.id"), nullable=False)


class Table(Base):
    __tablename__ = "tables"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("locations.id"))
    table_number: Mapped[str] = mapped_column(String, nullable=False)
    seating_capacity: Mapped[int] = mapped_column(Integer, default=2)
    qr_code_url: Mapped[Optional[str]] = mapped_column(String)
    qr_token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[TableStatus] = mapped_column(Enum(TableStatus), default=TableStatus.free)
    last_occupied_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QRSession(Base):
    __tablename__ = "qr_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tables.id"), nullable=False)
    session_token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    customer_phone: Mapped[Optional[str]] = mapped_column(String)
    customer_name: Mapped[Optional[str]] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String, default="active")
    cart_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrderType(Base):
    __tablename__ = "order_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    type: Mapped[OrderTypeEnum] = mapped_column(Enum(OrderTypeEnum), nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    min_order_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    fees: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Order Engine
# ---------------------------------------------------------------------------
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("locations.id"))
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    customer_phone: Mapped[Optional[str]] = mapped_column(String)
    customer_name: Mapped[Optional[str]] = mapped_column(String)
    table_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tables.id"))
    qr_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("qr_sessions.id"))
    order_type: Mapped[OrderTypeEnum] = mapped_column(Enum(OrderTypeEnum), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.PENDING)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String, default="BHD")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="qr")
    payment_status: Mapped[str] = mapped_column(String, default="pending")
    whatsapp_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    kitchen_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ready_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    served_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Delivery v2.0
    delivery_type: Mapped[Optional[DeliveryType]] = mapped_column(Enum(DeliveryType))
    delivery_zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("delivery_zones.id"))
    delivery_address_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("delivery_addresses.id"))
    driver_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("drivers.id"))
    third_party_partner_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("third_party_partners.id"))
    third_party_order_ref: Mapped[Optional[str]] = mapped_column(String)
    estimated_delivery_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    actual_delivery_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivery_rating: Mapped[Optional[int]] = mapped_column(Integer)
    delivery_tip: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    delivery_otp: Mapped[Optional[str]] = mapped_column(String)
    delivery_proof_url: Mapped[Optional[str]] = mapped_column(String)

    # WhatsApp acceptance
    acceptance_status: Mapped[Optional[AcceptanceStatus]] = mapped_column(Enum(AcceptanceStatus))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    accepted_by: Mapped[Optional[AcceptedBy]] = mapped_column(Enum(AcceptedBy))
    decline_reason: Mapped[Optional[str]] = mapped_column(String)

    # Scheduling
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime)


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    item_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("menu_items.id"))
    item_name_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    modifier_summary: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    special_instructions: Mapped[Optional[str]] = mapped_column(String)
    kitchen_station: Mapped[Optional[str]] = mapped_column(String)
    prep_status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrderStatusLog(Base):
    __tablename__ = "order_status_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String)
    to_status: Mapped[str] = mapped_column(String, nullable=False)
    changed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    changed_by_type: Mapped[Optional[str]] = mapped_column(String)
    reason: Mapped[Optional[str]] = mapped_column(String)
    meta_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrderTag(Base):
    __tablename__ = "order_tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    tag: Mapped[OrderTagEnum] = mapped_column(Enum(OrderTagEnum), nullable=False)
    added_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# WhatsApp Acceptance
# ---------------------------------------------------------------------------
class WhatsAppAcceptanceLog(Base):
    __tablename__ = "whatsapp_acceptance_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    merchant_phone: Mapped[str] = mapped_column(String, nullable=False)
    template_id: Mapped[Optional[str]] = mapped_column(String)
    message_id: Mapped[Optional[str]] = mapped_column(String)
    status: Mapped[WhatsAppMessageStatus] = mapped_column(Enum(WhatsAppMessageStatus), default=WhatsAppMessageStatus.sent)
    action: Mapped[Optional[WhatsAppAction]] = mapped_column(Enum(WhatsAppAction))
    response_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime)
    decline_reason: Mapped[Optional[str]] = mapped_column(String)
    auto_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MerchantBusinessHours(Base):
    __tablename__ = "merchant_business_hours"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    open_time: Mapped[Optional[time]] = mapped_column(Time)
    close_time: Mapped[Optional[time]] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_24h: Mapped[bool] = mapped_column(Boolean, default=False)
    special_date: Mapped[Optional[date]] = mapped_column(Date)
    special_open: Mapped[Optional[time]] = mapped_column(Time)
    special_close: Mapped[Optional[time]] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String, default="Asia/Bahrain")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MerchantAcceptanceSettings(Base):
    __tablename__ = "merchant_acceptance_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False, unique=True)
    auto_accept_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_accept_timeout_sec: Mapped[int] = mapped_column(Integer, default=300)
    decline_auto_refund: Mapped[bool] = mapped_column(Boolean, default=True)
    outside_hours_action: Mapped[OutsideHoursAction] = mapped_column(Enum(OutsideHoursAction), default=OutsideHoursAction.auto_decline)
    max_pending_orders: Mapped[int] = mapped_column(Integer, default=10)
    acceptance_mode: Mapped[AcceptanceMode] = mapped_column(Enum(AcceptanceMode), default=AcceptanceMode.whatsapp)
    escalation_sms_after_min: Mapped[int] = mapped_column(Integer, default=15)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WhatsAppTemplateRegistry(Base):
    __tablename__ = "whatsapp_template_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    template_name: Mapped[str] = mapped_column(String, nullable=False)
    meta_template_id: Mapped[Optional[str]] = mapped_column(String)
    language_code: Mapped[str] = mapped_column(String, default="en")
    category: Mapped[str] = mapped_column(String, default="UTILITY")
    status: Mapped[TemplateStatus] = mapped_column(Enum(TemplateStatus), default=TemplateStatus.PENDING)
    params_schema: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------
class DeliveryZone(Base):
    __tablename__ = "delivery_zones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    boundary: Mapped[Optional[dict]] = mapped_column(JSONB)  # GeoJSON Polygon
    center_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8))
    center_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    estimated_prep_min: Mapped[int] = mapped_column(Integer, default=20)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DeliveryPricingRule(Base):
    __tablename__ = "delivery_pricing_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("delivery_zones.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    base_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    per_km_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    minimum_order: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    free_delivery_threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    surge_multiplier: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.00"))
    surge_start: Mapped[Optional[time]] = mapped_column(Time)
    surge_end: Mapped[Optional[time]] = mapped_column(Time)
    max_fee_cap: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("50.00"))
    currency: Mapped[str] = mapped_column(String, default="BHD")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeliveryAddress(Base):
    __tablename__ = "delivery_addresses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String)
    address_line_1: Mapped[str] = mapped_column(String, nullable=False)
    address_line_2: Mapped[Optional[str]] = mapped_column(String)
    city: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, default="Bahrain")
    postal_code: Mapped[Optional[str]] = mapped_column(String)
    lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8))
    lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8))
    building_name: Mapped[Optional[str]] = mapped_column(String)
    floor_apartment: Mapped[Optional[str]] = mapped_column(String)
    delivery_notes: Mapped[Optional[str]] = mapped_column(String)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeliveryETAHistory(Base):
    __tablename__ = "delivery_eta_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("delivery_zones.id"))
    predicted_eta_min: Mapped[int] = mapped_column(Integer, default=0)
    actual_delivery_min: Mapped[Optional[int]] = mapped_column(Integer)
    driver_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("drivers.id"))
    distance_km: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    traffic_factor: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    day_of_week: Mapped[Optional[int]] = mapped_column(Integer)
    hour_of_day: Mapped[Optional[int]] = mapped_column(Integer)
    weather_factor: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Driver Fleet
# ---------------------------------------------------------------------------
class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    phone: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String)
    avatar_url: Mapped[Optional[str]] = mapped_column(String)
    license_number: Mapped[Optional[str]] = mapped_column(String)
    license_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime)
    vehicle_type: Mapped[Optional[str]] = mapped_column(String)
    vehicle_plate: Mapped[Optional[str]] = mapped_column(String)
    vehicle_color: Mapped[Optional[str]] = mapped_column(String)
    insurance_doc_url: Mapped[Optional[str]] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rating: Mapped[Decimal] = mapped_column(Numeric(2, 1), default=Decimal("5.0"))
    total_deliveries: Mapped[int] = mapped_column(Integer, default=0)
    total_earnings: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DriverShift(Base):
    __tablename__ = "driver_shifts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    actual_start: Mapped[Optional[datetime]] = mapped_column(DateTime)
    actual_end: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[DriverShiftStatus] = mapped_column(Enum(DriverShiftStatus), default=DriverShiftStatus.scheduled)
    break_minutes: Mapped[int] = mapped_column(Integer, default=0)
    zone_assignment: Mapped[Optional[str]] = mapped_column(String)
    max_orders: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DriverLocation(Base):
    __tablename__ = "driver_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lat: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    lng: Mapped[Decimal] = mapped_column(Numeric(11, 8), nullable=False)
    accuracy_meters: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    speed_kmh: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    heading: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    battery_level: Mapped[Optional[int]] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_moving: Mapped[bool] = mapped_column(Boolean, default=False)


class DriverEarnings(Base):
    __tablename__ = "driver_earnings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    base_earnings: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tip_earnings: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    bonus_earnings: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    penalty: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    net_earnings: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    settlement_status: Mapped[SettlementStatus] = mapped_column(Enum(SettlementStatus), default=SettlementStatus.pending)
    settlement_ref: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Delivery Assignment
# ---------------------------------------------------------------------------
class DeliveryAssignment(Base):
    __tablename__ = "delivery_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    driver_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("drivers.id"))
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("delivery_zones.id"))
    assignment_type: Mapped[AssignmentType] = mapped_column(Enum(AssignmentType), default=AssignmentType.auto)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String)
    picked_up_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivery_otp: Mapped[Optional[str]] = mapped_column(String)
    delivery_proof_url: Mapped[Optional[str]] = mapped_column(String)
    customer_rating: Mapped[Optional[int]] = mapped_column(Integer)
    customer_tip: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeliveryRoute(Base):
    __tablename__ = "delivery_routes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("delivery_assignments.id"), nullable=False)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    waypoints: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    optimized_sequence: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    total_distance_km: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    estimated_duration_min: Mapped[Optional[int]] = mapped_column(Integer)
    actual_duration_min: Mapped[Optional[int]] = mapped_column(Integer)
    route_geometry: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)  # GeoJSON LineString
    traffic_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("delivery_assignments.id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DeliveryAttemptStatus] = mapped_column(Enum(DeliveryAttemptStatus), default=DeliveryAttemptStatus.pending)
    failure_reason: Mapped[Optional[str]] = mapped_column(String)
    customer_not_available: Mapped[bool] = mapped_column(Boolean, default=False)
    wrong_address: Mapped[bool] = mapped_column(Boolean, default=False)
    driver_notes: Mapped[Optional[str]] = mapped_column(String)
    photo_url: Mapped[Optional[str]] = mapped_column(String)
    next_attempt_scheduled: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DriverRating(Base):
    __tablename__ = "driver_ratings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=False)
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"))
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    review_text: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    merchant_response: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# 3rd Party
# ---------------------------------------------------------------------------
class ThirdPartyPartner(Base):
    __tablename__ = "third_party_partners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    partner_name: Mapped[ThirdPartyPartnerName] = mapped_column(Enum(ThirdPartyPartnerName), nullable=False)
    partner_merchant_id: Mapped[Optional[str]] = mapped_column(String)
    api_endpoint: Mapped[Optional[str]] = mapped_column(String)
    auth_type: Mapped[AuthType] = mapped_column(Enum(AuthType), default=AuthType.api_key)
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    commission_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("15.00"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String)
    sync_menu: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_inventory: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ThirdPartyOrder(Base):
    __tablename__ = "third_party_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("third_party_partners.id"), nullable=False)
    partner_order_ref: Mapped[str] = mapped_column(String, nullable=False)
    partner_status: Mapped[Optional[str]] = mapped_column(String)
    partner_rider_name: Mapped[Optional[str]] = mapped_column(String)
    partner_rider_phone: Mapped[Optional[str]] = mapped_column(String)
    partner_eta_min: Mapped[Optional[int]] = mapped_column(Integer)
    partner_delivery_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    partner_commission: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    partner_payout: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_sync_status: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ThirdPartyPayout(Base):
    __tablename__ = "third_party_payouts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("third_party_partners.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payout_period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    payout_period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    gross_sales: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    commission_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    net_payout: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    payout_reference: Mapped[Optional[str]] = mapped_column(String)
    payout_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reconciliation_status: Mapped[ReconciliationStatus] = mapped_column(Enum(ReconciliationStatus), default=ReconciliationStatus.open)
    variance_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReconciliationBatch(Base):
    __tablename__ = "reconciliation_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    batch_period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    batch_period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_in_house: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_3rd_party: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_delivery_fees: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_tips: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_commissions: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    net_revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String, default="open")
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gateway: Mapped[PaymentGateway] = mapped_column(Enum(PaymentGateway), nullable=False)
    gateway_transaction_id: Mapped[Optional[str]] = mapped_column(String)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String, default="BHD")
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.pending)
    payment_method_details: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    refund_reason: Mapped[Optional[str]] = mapped_column(String)
    webhook_payload: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MerchantWallet(Base):
    __tablename__ = "merchant_wallets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False, unique=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String, default="BHD")
    total_earned: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_withdrawn: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    last_settlement_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_sales: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    payment_gateway_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    status: Mapped[SettlementStatus] = mapped_column(Enum(SettlementStatus), default=SettlementStatus.pending)
    transfer_reference: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaxRate(Base):
    __tablename__ = "tax_rates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    applies_to: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
