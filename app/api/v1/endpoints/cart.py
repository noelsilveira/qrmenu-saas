from typing import Optional
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.orders import CartAddRequest, CartUpdateRequest, CartResponse
from app.services.cart_service import CartService

router = APIRouter()


async def _get_or_create_cart(session_token: str, merchant_id: UUID, table_id: Optional[UUID] = None):
    cart = await CartService.get_cart(session_token)
    if not cart:
        cart = await CartService.create_cart(merchant_id, table_id, session_token)
    return cart


@router.post("/add", response_model=CartResponse)
async def add_to_cart(
    data: CartAddRequest,
    session_token: str,
    merchant_id: UUID,
    table_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models import MenuItem, ModifierOption, ItemModifier
    from app.schemas.orders import CartItem, CartItemModifier, CartModifierOption

    item_result = await db.execute(
        select(MenuItem).where(
            MenuItem.id == data.item_id,
            MenuItem.merchant_id == merchant_id,
            MenuItem.is_available == True
        )
    )
    menu_item = item_result.scalar_one_or_none()
    if not menu_item:
        raise HTTPException(status_code=404, detail="Menu item not found or unavailable")

    modifiers = []
    if data.modifier_options:
        opt_result = await db.execute(
            select(ModifierOption).where(ModifierOption.id.in_(data.modifier_options))
        )
        options = {str(o.id): o for o in opt_result.scalars().all()}

        mod_groups = {}
        for opt_id in data.modifier_options:
            opt = options.get(str(opt_id))
            if opt:
                mod_id = str(opt.modifier_id)
                if mod_id not in mod_groups:
                    mod_result = await db.execute(
                        select(ItemModifier).where(ItemModifier.id == opt.modifier_id)
                    )
                    mod = mod_result.scalar_one_or_none()
                    mod_groups[mod_id] = {
                        "modifier_id": opt.modifier_id,
                        "name": mod.name if mod else "",
                        "options": []
                    }
                mod_groups[mod_id]["options"].append(opt)

        for mod_data in mod_groups.values():
            modifiers.append(CartItemModifier(
                modifier_id=mod_data["modifier_id"],
                name=mod_data["name"],
                selected_options=[
                    CartModifierOption(
                        option_id=o.id,
                        name=o.name,
                        price_adjustment=o.price_adjustment
                    )
                    for o in mod_data["options"]
                ]
            ))

    cart_item = CartItem(
        item_id=menu_item.id,
        name=menu_item.name,
        quantity=data.quantity,
        unit_price=menu_item.price,
        modifiers=modifiers,
        special_instructions=data.special_instructions
    )

    cart = await _get_or_create_cart(session_token, merchant_id, table_id)
    await CartService.add_item(session_token, cart_item)

    return await CartService.get_cart_response(session_token)


@router.put("/item/{item_id}", response_model=CartResponse)
async def update_cart_item(
    item_id: UUID,
    data: CartUpdateRequest,
    session_token: str,
):
    try:
        await CartService.update_item(session_token, item_id, data.quantity, data.special_instructions)
        return await CartService.get_cart_response(session_token)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/item/{item_id}", response_model=CartResponse)
async def remove_cart_item(
    item_id: UUID,
    session_token: str,
):
    try:
        await CartService.remove_item(session_token, item_id)
        return await CartService.get_cart_response(session_token)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("", response_model=CartResponse)
async def get_cart(
    session_token: str,
):
    try:
        return await CartService.get_cart_response(session_token)
    except ValueError:
        raise HTTPException(status_code=404, detail="Cart not found or expired")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(
    session_token: str,
):
    await CartService.clear_cart(session_token)
