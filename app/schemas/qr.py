from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class QRGenerateRequest(BaseModel):
    table_id: UUID
    format: str = "png"  # png or svg


class QRResponse(BaseModel):
    url: str
    token: str
    format: str
    generated_at: datetime


class TableCreate(BaseModel):
    table_number: str
    seating_capacity: int = 2
    location_id: Optional[UUID] = None


class TableUpdate(BaseModel):
    table_number: Optional[str] = None
    seating_capacity: Optional[int] = None
    location_id: Optional[UUID] = None
    status: Optional[str] = None  # free, occupied, reserved


class TableResponse(BaseModel):
    id: UUID
    merchant_id: UUID
    location_id: Optional[UUID] = None
    table_number: str
    seating_capacity: int
    qr_code_url: Optional[str] = None
    qr_token: str
    status: str
    last_occupied_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class QRScanRequest(BaseModel):
    qr_token: str
    customer_phone: Optional[str] = None
    customer_name: Optional[str] = None


class QRScanResponse(BaseModel):
    menu_url: str
    session_token: str
    merchant_name: str
    table_number: str
    table_id: UUID
    expires_at: Optional[datetime] = None


class QRValidateResponse(BaseModel):
    valid: bool
    merchant_id: Optional[UUID] = None
    merchant_name: Optional[str] = None
    merchant_slug: Optional[str] = None
    table_id: Optional[UUID] = None
    table_number: Optional[str] = None
    session_token: Optional[str] = None
    expires_at: Optional[datetime] = None
