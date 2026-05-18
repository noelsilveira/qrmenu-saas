from pydantic import BaseModel
from typing import Optional
from uuid import UUID

from app.models.models import OutsideHoursAction, AcceptanceMode


class AcceptanceSettingsCreate(BaseModel):
    merchant_id: UUID
    auto_accept_enabled: bool = False
    auto_accept_timeout_sec: int = 300
    decline_auto_refund: bool = True
    outside_hours_action: OutsideHoursAction = OutsideHoursAction.auto_decline
    max_pending_orders: int = 10
    acceptance_mode: AcceptanceMode = AcceptanceMode.whatsapp
    escalation_sms_after_min: int = 15


class AcceptanceSettingsUpdate(BaseModel):
    auto_accept_enabled: Optional[bool] = None
    auto_accept_timeout_sec: Optional[int] = None
    decline_auto_refund: Optional[bool] = None
    outside_hours_action: Optional[OutsideHoursAction] = None
    max_pending_orders: Optional[int] = None
    acceptance_mode: Optional[AcceptanceMode] = None
    escalation_sms_after_min: Optional[int] = None


class AcceptanceSettingsResponse(BaseModel):
    id: UUID
    merchant_id: UUID
    auto_accept_enabled: bool
    auto_accept_timeout_sec: int
    decline_auto_refund: bool
    outside_hours_action: OutsideHoursAction
    max_pending_orders: int
    acceptance_mode: AcceptanceMode
    escalation_sms_after_min: int

    class Config:
        from_attributes = True
