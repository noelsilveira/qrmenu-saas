from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import time, date


class BusinessHoursCreate(BaseModel):
    merchant_id: UUID
    day_of_week: int
    open_time: Optional[time] = None
    close_time: Optional[time] = None
    is_closed: bool = False
    is_24h: bool = False
    special_date: Optional[date] = None
    special_open: Optional[time] = None
    special_close: Optional[time] = None
    timezone: str = "Asia/Bahrain"


class BusinessHoursUpdate(BaseModel):
    open_time: Optional[time] = None
    close_time: Optional[time] = None
    is_closed: Optional[bool] = None
    is_24h: Optional[bool] = None
    special_date: Optional[date] = None
    special_open: Optional[time] = None
    special_close: Optional[time] = None
    timezone: Optional[str] = None


class BusinessHoursResponse(BaseModel):
    id: UUID
    merchant_id: UUID
    day_of_week: int
    open_time: Optional[time] = None
    close_time: Optional[time] = None
    is_closed: bool
    is_24h: bool
    special_date: Optional[date] = None
    special_open: Optional[time] = None
    special_close: Optional[time] = None
    timezone: str

    class Config:
        from_attributes = True
