from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from datetime import datetime


# ---------------------------------------------------------------------------
# Modifier Schemas
# ---------------------------------------------------------------------------
class ModifierOptionCreate(BaseModel):
    name: str
    price_adjustment: Decimal = Decimal("0.00")
    is_default: bool = False
    sort_order: int = 0


class ModifierOptionResponse(BaseModel):
    id: UUID
    name: str
    price_adjustment: Decimal
    is_default: bool
    sort_order: int

    class Config:
        from_attributes = True


class ModifierCreate(BaseModel):
    name: str
    description: Optional[str] = None
    min_select: int = 0
    max_select: int = 1
    is_required: bool = False
    sort_order: int = 0
    options: List[ModifierOptionCreate] = []


class ModifierResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    min_select: int
    max_select: int
    is_required: bool
    sort_order: int
    options: List[ModifierOptionResponse] = []

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Category Schemas
# ---------------------------------------------------------------------------
class CategoryCreate(BaseModel):
    name: str
    name_localized: Optional[dict] = None
    description: Optional[str] = None
    sort_order: int = 0
    image_url: Optional[str] = None
    parent_id: Optional[UUID] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    name_localized: Optional[dict] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    image_url: Optional[str] = None
    parent_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class CategoryItemSummary(BaseModel):
    id: UUID
    name: str
    price: Decimal
    is_available: bool
    image_urls: Optional[dict] = None

    class Config:
        from_attributes = True


class CategoryResponse(BaseModel):
    id: UUID
    merchant_id: UUID
    name: str
    name_localized: Optional[dict] = None
    description: Optional[str] = None
    sort_order: int
    image_url: Optional[str] = None
    is_active: bool
    parent_id: Optional[UUID] = None
    items: List[CategoryItemSummary] = []
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Item Schemas
# ---------------------------------------------------------------------------
class ItemCreate(BaseModel):
    name: str
    name_localized: Optional[dict] = None
    description: Optional[str] = None
    price: Decimal = Field(..., ge=0)
    compare_at_price: Optional[Decimal] = None
    cost_price: Optional[Decimal] = None
    category_id: Optional[UUID] = None
    image_urls: Optional[dict] = None
    sku: Optional[str] = None
    allergens: Optional[dict] = None
    nutritional_info: Optional[dict] = None
    prep_time_min: int = 0
    modifier_ids: List[UUID] = []


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    name_localized: Optional[dict] = None
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, ge=0)
    compare_at_price: Optional[Decimal] = None
    cost_price: Optional[Decimal] = None
    category_id: Optional[UUID] = None
    image_urls: Optional[dict] = None
    sku: Optional[str] = None
    allergens: Optional[dict] = None
    nutritional_info: Optional[dict] = None
    prep_time_min: Optional[int] = None
    is_available: Optional[bool] = None


class ItemModifierSummary(BaseModel):
    id: UUID
    name: str
    min_select: int
    max_select: int
    is_required: bool
    options: List[ModifierOptionResponse] = []

    class Config:
        from_attributes = True


class ItemResponse(BaseModel):
    id: UUID
    merchant_id: UUID
    category_id: Optional[UUID] = None
    name: str
    name_localized: Optional[dict] = None
    description: Optional[str] = None
    price: Decimal
    compare_at_price: Optional[Decimal] = None
    cost_price: Optional[Decimal] = None
    image_urls: Optional[dict] = None
    sku: Optional[str] = None
    is_available: bool
    allergens: Optional[dict] = None
    nutritional_info: Optional[dict] = None
    prep_time_min: int
    modifiers: List[ItemModifierSummary] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Public Menu Schemas
# ---------------------------------------------------------------------------
class PublicMenuCategory(BaseModel):
    id: UUID
    name: str
    name_localized: Optional[dict] = None
    description: Optional[str] = None
    sort_order: int
    image_url: Optional[str] = None
    items: List["PublicMenuItem"] = []


class PublicMenuItem(BaseModel):
    id: UUID
    name: str
    name_localized: Optional[dict] = None
    description: Optional[str] = None
    price: Decimal
    compare_at_price: Optional[Decimal] = None
    image_urls: Optional[dict] = None
    allergens: Optional[dict] = None
    nutritional_info: Optional[dict] = None
    prep_time_min: int
    modifiers: List[ItemModifierSummary] = []


PublicMenuCategory.model_rebuild()


class PublicMenuResponse(BaseModel):
    merchant_name: str
    merchant_slug: str
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    currency: str
    categories: List[PublicMenuCategory]
