from typing import Optional, List
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_active_user, require_role
from app.core.cache import cache_get, cache_set, cache_delete, cache_delete_pattern
from app.models import (
    User, Merchant, MenuCategory, MenuItem, ItemModifier, ModifierOption,
    ItemModifierLink,
)
from app.schemas.menu import (
    CategoryCreate, CategoryUpdate, CategoryResponse, CategoryItemSummary,
    ItemCreate, ItemUpdate, ItemResponse, ItemModifierSummary, ModifierOptionResponse,
    PublicMenuResponse, PublicMenuCategory, PublicMenuItem,
)

router = APIRouter()

MENU_CACHE_TTL = 300  # 5 minutes


def _get_merchant_id(user: User) -> UUID:
    return user.merchant_id


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
@router.get("/categories", response_model=List[CategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    merchant_id = _get_merchant_id(current_user)
    cache_key = f"menu:categories:{merchant_id}"

    cached = await cache_get(cache_key)
    if cached:
        return cached

    # Fetch categories
    cat_result = await db.execute(
        select(MenuCategory)
        .where(MenuCategory.merchant_id == merchant_id, MenuCategory.is_active == True)
        .order_by(MenuCategory.sort_order.asc(), MenuCategory.name.asc())
    )
    categories = cat_result.scalars().all()

    # Fetch items for these categories
    cat_ids = [c.id for c in categories]
    items_result = await db.execute(
        select(MenuItem)
        .where(
            MenuItem.merchant_id == merchant_id,
            MenuItem.category_id.in_(cat_ids) if cat_ids else False,
            MenuItem.is_available == True,
        )
        .order_by(MenuItem.name.asc())
    )
    items = items_result.scalars().all()
    items_by_cat: dict = {}
    for item in items:
        items_by_cat.setdefault(str(item.category_id), []).append(
            CategoryItemSummary(
                id=item.id,
                name=item.name,
                price=item.price,
                is_available=item.is_available,
                image_urls=item.image_urls,
            )
        )

    response = []
    for cat in categories:
        response.append(
            CategoryResponse(
                id=cat.id,
                merchant_id=cat.merchant_id,
                name=cat.name,
                name_localized=cat.name_localized,
                description=cat.description,
                sort_order=cat.sort_order,
                image_url=cat.image_url,
                is_active=cat.is_active,
                parent_id=cat.parent_id,
                items=items_by_cat.get(str(cat.id), []),
                created_at=cat.created_at,
            )
        )

    await cache_set(cache_key, [r.model_dump(mode="json") for r in response], MENU_CACHE_TTL)
    return response


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    merchant_id = _get_merchant_id(current_user)
    category = MenuCategory(
        merchant_id=merchant_id,
        name=data.name,
        name_localized=data.name_localized,
        description=data.description,
        sort_order=data.sort_order,
        image_url=data.image_url,
        parent_id=data.parent_id,
        is_active=True,
    )
    db.add(category)
    await db.flush()
    await db.refresh(category)
    await cache_delete_pattern(f"menu:*:{merchant_id}")
    return CategoryResponse(
        id=category.id,
        merchant_id=category.merchant_id,
        name=category.name,
        name_localized=category.name_localized,
        description=category.description,
        sort_order=category.sort_order,
        image_url=category.image_url,
        is_active=category.is_active,
        parent_id=category.parent_id,
        items=[],
        created_at=category.created_at,
    )


@router.put("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    merchant_id = _get_merchant_id(current_user)
    result = await db.execute(
        select(MenuCategory).where(
            MenuCategory.id == category_id,
            MenuCategory.merchant_id == merchant_id,
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    await db.flush()
    await db.refresh(category)
    await cache_delete_pattern(f"menu:*:{merchant_id}")
    return CategoryResponse(
        id=category.id,
        merchant_id=category.merchant_id,
        name=category.name,
        name_localized=category.name_localized,
        description=category.description,
        sort_order=category.sort_order,
        image_url=category.image_url,
        is_active=category.is_active,
        parent_id=category.parent_id,
        items=[],
        created_at=category.created_at,
    )


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    merchant_id = _get_merchant_id(current_user)
    result = await db.execute(
        select(MenuCategory).where(
            MenuCategory.id == category_id,
            MenuCategory.merchant_id == merchant_id,
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Soft delete: hide category and cascade hide items
    category.is_active = False
    await db.execute(
        select(MenuItem).where(MenuItem.category_id == category_id)
    )
    # Update items to not available
    from sqlalchemy import update
    await db.execute(
        update(MenuItem)
        .where(MenuItem.category_id == category_id)
        .values(is_available=False)
    )
    await db.flush()
    await cache_delete_pattern(f"menu:*:{merchant_id}")
    return None


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
@router.get("/items", response_model=List[ItemResponse])
async def list_items(
    category_id: Optional[UUID] = Query(None),
    available_only: bool = Query(False),
    min_price: Optional[Decimal] = Query(None),
    max_price: Optional[Decimal] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    merchant_id = _get_merchant_id(current_user)

    conditions = [MenuItem.merchant_id == merchant_id]
    if category_id:
        conditions.append(MenuItem.category_id == category_id)
    if available_only:
        conditions.append(MenuItem.is_available == True)
    if min_price is not None:
        conditions.append(MenuItem.price >= min_price)
    if max_price is not None:
        conditions.append(MenuItem.price <= max_price)
    if search:
        conditions.append(
            or_(
                MenuItem.name.ilike(f"%{search}%"),
                MenuItem.description.ilike(f"%{search}%"),
            )
        )

    stmt = (
        select(MenuItem)
        .where(and_(*conditions))
        .order_by(MenuItem.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    # Load modifiers for items
    item_ids = [i.id for i in items]
    modifiers_map = await _load_item_modifiers(db, item_ids)

    response = []
    for item in items:
        response.append(
            ItemResponse(
                id=item.id,
                merchant_id=item.merchant_id,
                category_id=item.category_id,
                name=item.name,
                name_localized=item.name_localized,
                description=item.description,
                price=item.price,
                compare_at_price=item.compare_at_price,
                cost_price=item.cost_price,
                image_urls=item.image_urls,
                sku=item.sku,
                is_available=item.is_available,
                allergens=item.allergens,
                nutritional_info=item.nutritional_info,
                prep_time_min=item.prep_time_min,
                modifiers=modifiers_map.get(str(item.id), []),
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )
    return response


async def _load_item_modifiers(db: AsyncSession, item_ids: List[UUID]) -> dict:
    if not item_ids:
        return {}
    link_result = await db.execute(
        select(ItemModifierLink.item_id, ItemModifierLink.modifier_id)
        .where(ItemModifierLink.item_id.in_(item_ids))
    )
    links = link_result.all()
    modifier_ids = [l.modifier_id for l in links]
    if not modifier_ids:
        return {}

    mod_result = await db.execute(
        select(ItemModifier).where(ItemModifier.id.in_(modifier_ids))
    )
    modifiers = {m.id: m for m in mod_result.scalars().all()}

    opt_result = await db.execute(
        select(ModifierOption).where(ModifierOption.modifier_id.in_(modifier_ids))
    )
    options_by_mod: dict = {}
    for opt in opt_result.scalars().all():
        options_by_mod.setdefault(str(opt.modifier_id), []).append(
            ModifierOptionResponse(
                id=opt.id,
                name=opt.name,
                price_adjustment=opt.price_adjustment,
                is_default=opt.is_default,
                sort_order=opt.sort_order,
            )
        )

    result: dict = {}
    for link in links:
        mod = modifiers.get(link.modifier_id)
        if mod:
            result.setdefault(str(link.item_id), []).append(
                ItemModifierSummary(
                    id=mod.id,
                    name=mod.name,
                    min_select=mod.min_select,
                    max_select=mod.max_select,
                    is_required=mod.is_required,
                    options=options_by_mod.get(str(mod.id), []),
                )
            )
    return result


@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    data: ItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    merchant_id = _get_merchant_id(current_user)
    item = MenuItem(
        merchant_id=merchant_id,
        category_id=data.category_id,
        name=data.name,
        name_localized=data.name_localized,
        description=data.description,
        price=data.price,
        compare_at_price=data.compare_at_price,
        cost_price=data.cost_price,
        image_urls=data.image_urls,
        sku=data.sku,
        is_available=True,
        allergens=data.allergens,
        nutritional_info=data.nutritional_info,
        prep_time_min=data.prep_time_min,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)

    # Attach modifiers
    if data.modifier_ids:
        for mid in data.modifier_ids:
            link = ItemModifierLink(item_id=item.id, modifier_id=mid)
            db.add(link)
        await db.flush()

    await cache_delete_pattern(f"menu:*:{merchant_id}")
    modifiers = await _load_item_modifiers(db, [item.id])
    return ItemResponse(
        id=item.id,
        merchant_id=item.merchant_id,
        category_id=item.category_id,
        name=item.name,
        name_localized=item.name_localized,
        description=item.description,
        price=item.price,
        compare_at_price=item.compare_at_price,
        cost_price=item.cost_price,
        image_urls=item.image_urls,
        sku=item.sku,
        is_available=item.is_available,
        allergens=item.allergens,
        nutritional_info=item.nutritional_info,
        prep_time_min=item.prep_time_min,
        modifiers=modifiers.get(str(item.id), []),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.put("/items/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: UUID,
    data: ItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    merchant_id = _get_merchant_id(current_user)
    result = await db.execute(
        select(MenuItem).where(
            MenuItem.id == item_id,
            MenuItem.merchant_id == merchant_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)

    await db.flush()
    await db.refresh(item)
    await cache_delete_pattern(f"menu:*:{merchant_id}")
    modifiers = await _load_item_modifiers(db, [item.id])
    return ItemResponse(
        id=item.id,
        merchant_id=item.merchant_id,
        category_id=item.category_id,
        name=item.name,
        name_localized=item.name_localized,
        description=item.description,
        price=item.price,
        compare_at_price=item.compare_at_price,
        cost_price=item.cost_price,
        image_urls=item.image_urls,
        sku=item.sku,
        is_available=item.is_available,
        allergens=item.allergens,
        nutritional_info=item.nutritional_info,
        prep_time_min=item.prep_time_min,
        modifiers=modifiers.get(str(item.id), []),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("/items/{item_id}/modifiers", response_model=ItemResponse)
async def attach_modifiers(
    item_id: UUID,
    modifier_ids: List[UUID],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    merchant_id = _get_merchant_id(current_user)
    result = await db.execute(
        select(MenuItem).where(
            MenuItem.id == item_id,
            MenuItem.merchant_id == merchant_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Remove existing links
    from sqlalchemy import delete
    await db.execute(
        delete(ItemModifierLink).where(ItemModifierLink.item_id == item_id)
    )

    for mid in modifier_ids:
        link = ItemModifierLink(item_id=item_id, modifier_id=mid)
        db.add(link)
    await db.flush()

    await cache_delete_pattern(f"menu:*:{merchant_id}")
    modifiers = await _load_item_modifiers(db, [item.id])
    return ItemResponse(
        id=item.id,
        merchant_id=item.merchant_id,
        category_id=item.category_id,
        name=item.name,
        name_localized=item.name_localized,
        description=item.description,
        price=item.price,
        compare_at_price=item.compare_at_price,
        cost_price=item.cost_price,
        image_urls=item.image_urls,
        sku=item.sku,
        is_available=item.is_available,
        allergens=item.allergens,
        nutritional_info=item.nutritional_info,
        prep_time_min=item.prep_time_min,
        modifiers=modifiers.get(str(item.id), []),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


# ---------------------------------------------------------------------------
# Full-text search using PostgreSQL tsvector
# ---------------------------------------------------------------------------
@router.get("/search", response_model=List[ItemResponse])
async def search_items(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    merchant_id = _get_merchant_id(current_user)

    # Use PostgreSQL to_tsvector for full-text search
    search_query = text(
        """
        SELECT id FROM menu_items
        WHERE merchant_id = :merchant_id
          AND (
            to_tsvector('english', COALESCE(name, '') || ' ' || COALESCE(description, ''))
            @@ plainto_tsquery('english', :query)
            OR name ILIKE :like_query
          )
        ORDER BY created_at DESC
        LIMIT 50
        """
    )
    result = await db.execute(
        search_query,
        {
            "merchant_id": str(merchant_id),
            "query": q,
            "like_query": f"%{q}%",
        },
    )
    rows = result.fetchall()
    if not rows:
        return []

    item_ids = [r.id for r in rows]
    items_result = await db.execute(
        select(MenuItem).where(MenuItem.id.in_(item_ids))
    )
    items = items_result.scalars().all()

    # Preserve search result order
    item_map = {str(i.id): i for i in items}
    ordered_items = [item_map[str(r.id)] for r in rows if str(r.id) in item_map]

    modifiers_map = await _load_item_modifiers(db, item_ids)
    response = []
    for item in ordered_items:
        response.append(
            ItemResponse(
                id=item.id,
                merchant_id=item.merchant_id,
                category_id=item.category_id,
                name=item.name,
                name_localized=item.name_localized,
                description=item.description,
                price=item.price,
                compare_at_price=item.compare_at_price,
                cost_price=item.cost_price,
                image_urls=item.image_urls,
                sku=item.sku,
                is_available=item.is_available,
                allergens=item.allergens,
                nutritional_info=item.nutritional_info,
                prep_time_min=item.prep_time_min,
                modifiers=modifiers_map.get(str(item.id), []),
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )
    return response


# ---------------------------------------------------------------------------
# Public Menu (no auth required)
# ---------------------------------------------------------------------------
@router.get("/public/{merchant_slug}", response_model=PublicMenuResponse)
async def public_menu(
    merchant_slug: str,
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"menu:public:{merchant_slug}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    merchant_result = await db.execute(
        select(Merchant).where(Merchant.slug == merchant_slug)
    )
    merchant = merchant_result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    # Fetch active categories
    cat_result = await db.execute(
        select(MenuCategory)
        .where(
            MenuCategory.merchant_id == merchant.id,
            MenuCategory.is_active == True,
        )
        .order_by(MenuCategory.sort_order.asc())
    )
    categories = cat_result.scalars().all()

    cat_ids = [c.id for c in categories]
    items_result = await db.execute(
        select(MenuItem)
        .where(
            MenuItem.merchant_id == merchant.id,
            MenuItem.category_id.in_(cat_ids) if cat_ids else False,
            MenuItem.is_available == True,
        )
    )
    items = items_result.scalars().all()

    item_ids = [i.id for i in items]
    modifiers_map = await _load_item_modifiers(db, item_ids)

    items_by_cat: dict = {}
    for item in items:
        items_by_cat.setdefault(str(item.category_id), []).append(
            PublicMenuItem(
                id=item.id,
                name=item.name,
                name_localized=item.name_localized,
                description=item.description,
                price=item.price,
                compare_at_price=item.compare_at_price,
                image_urls=item.image_urls,
                allergens=item.allergens,
                nutritional_info=item.nutritional_info,
                prep_time_min=item.prep_time_min,
                modifiers=modifiers_map.get(str(item.id), []),
            )
        )

    cat_response = []
    for cat in categories:
        cat_response.append(
            PublicMenuCategory(
                id=cat.id,
                name=cat.name,
                name_localized=cat.name_localized,
                description=cat.description,
                sort_order=cat.sort_order,
                image_url=cat.image_url,
                items=items_by_cat.get(str(cat.id), []),
            )
        )

    response = PublicMenuResponse(
        merchant_name=merchant.business_name,
        merchant_slug=merchant.slug,
        logo_url=merchant.logo_url,
        primary_color=merchant.brand_primary_color,
        secondary_color=merchant.brand_secondary_color,
        currency=merchant.currency,
        categories=cat_response,
    )

    await cache_set(cache_key, response.model_dump(mode="json"), MENU_CACHE_TTL)
    return response
