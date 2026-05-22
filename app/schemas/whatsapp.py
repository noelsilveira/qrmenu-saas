from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from enum import Enum


class AcceptanceStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    auto_rejected = "auto_rejected"
    timeout = "timeout"


class WhatsAppButtonType(str, Enum):
    reply = "reply"
    url = "url"


class WhatsAppButton(BaseModel):
    type: WhatsAppButtonType = WhatsAppButtonType.reply
    title: str = Field(..., max_length=20)
    id: str  # callback payload identifier


class WhatsAppTemplateMessage(BaseModel):
    to: str  # phone number with country code
    template_name: str
    language_code: str = "en"
    parameters: Optional[Dict[str, str]] = None
    buttons: Optional[List[WhatsAppButton]] = None


class WhatsAppInteractiveMessage(BaseModel):
    to: str
    header_text: Optional[str] = None
    body_text: str
    footer_text: Optional[str] = None
    buttons: List[WhatsAppButton]


class WhatsAppTextMessage(BaseModel):
    to: str
    body: str


# ---------------------------------------------------------------------------
# Acceptance Flow Schemas
# ---------------------------------------------------------------------------
class OrderAcceptanceRequest(BaseModel):
    order_id: UUID
    timeout_minutes: int = Field(5, ge=1, le=60)
    notify_channels: List[str] = ["whatsapp"]  # whatsapp, sms, push


class OrderAcceptanceResponse(BaseModel):
    order_id: UUID
    acceptance_status: AcceptanceStatus
    timeout_at: Optional[datetime] = None
    notified_at: datetime
    merchant_phone: str
    message_id: Optional[str] = None


class MerchantAcceptAction(BaseModel):
    order_id: UUID
    action: str  # accept, reject
    reason: Optional[str] = None
    responded_by: Optional[str] = None  # phone number or user_id


class MerchantAcceptActionResponse(BaseModel):
    order_id: UUID
    action: str
    new_status: str
    order_status: str
    customer_notified: bool


# ---------------------------------------------------------------------------
# Timeout Engine Schemas
# ---------------------------------------------------------------------------
class TimeoutConfig(BaseModel):
    enabled: bool = True
    timeout_minutes: int = 5
    auto_reject_reason: str = "Merchant did not respond in time"
    fallback_action: str = "auto_reject"  # auto_reject, escalate, call_manager


class TimeoutStatus(BaseModel):
    order_id: UUID
    status: AcceptanceStatus
    timeout_at: Optional[datetime]
    time_remaining_seconds: Optional[int]
    is_expired: bool


# ---------------------------------------------------------------------------
# Webhook Schemas
# ---------------------------------------------------------------------------
class WhatsAppWebhookPayload(BaseModel):
    object: str = "whatsapp_business_account"
    entry: List[Dict[str, Any]]


class WhatsAppMessageWebhook(BaseModel):
    id: str
    from_number: str
    timestamp: str
    type: str  # text, interactive, button, etc.
    text_body: Optional[str] = None
    button_payload: Optional[str] = None  # e.g. "accept:order-uuid"
    interactive_button_id: Optional[str] = None


class WhatsAppStatusWebhook(BaseModel):
    id: str
    status: str  # sent, delivered, read, failed
    timestamp: str
    recipient_id: str


# ---------------------------------------------------------------------------
# Customer Notification Schemas
# ---------------------------------------------------------------------------
class CustomerNotificationRequest(BaseModel):
    order_id: UUID
    customer_phone: str
    notification_type: str  # order_accepted, order_rejected, order_ready, order_delayed
    message: Optional[str] = None
    language: str = "en"


class CustomerNotificationResponse(BaseModel):
    order_id: UUID
    sent: bool
    message_id: Optional[str] = None
    channel: str
    timestamp: datetime


# ---------------------------------------------------------------------------
# Acceptance Settings (Merchant-level)
# ---------------------------------------------------------------------------
class AcceptanceSettingsUpdate(BaseModel):
    auto_accept_enabled: Optional[bool] = None
    timeout_minutes: Optional[int] = Field(None, ge=1, le=120)
    notification_phone: Optional[str] = None
    fallback_phone: Optional[str] = None
    business_hours_only: Optional[bool] = None
    acceptance_mode: Optional[str] = None  # auto, manual, whatsapp


class AcceptanceSettingsResponse(BaseModel):
    merchant_id: UUID
    auto_accept_enabled: bool
    timeout_minutes: int
    notification_phone: Optional[str]
    fallback_phone: Optional[str]
    business_hours_only: bool
    acceptance_mode: str
    updated_at: datetime
