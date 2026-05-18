from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID


class MerchantBrandingUpdate(BaseModel):
    logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None
    brand_secondary_color: Optional[str] = None
    brand_bg_image_url: Optional[str] = None
    font_family: Optional[str] = None
    receipt_header: Optional[str] = None
    receipt_footer: Optional[str] = None
    custom_domain: Optional[str] = None


class MerchantPublicProfile(BaseModel):
    business_name: str
    logo_url: Optional[str] = None
    colors: dict
    background: Optional[str] = None
    languages_enabled: List[str] = ["en"]


class MerchantSettingsUpdate(BaseModel):
    currency: Optional[str] = None
    timezone: Optional[str] = None
    tax_config: Optional[dict] = None
    printer_settings: Optional[dict] = None
    whatsapp_template_ids: Optional[dict] = None


class MerchantSettingsResponse(BaseModel):
    currency: str
    timezone: str
    tax_config: Optional[dict] = None
    printer_settings: Optional[dict] = None
    whatsapp_template_ids: Optional[dict] = None
