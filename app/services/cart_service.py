import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.core.cache import cache_get, cache_set, cache_delete
from app.schemas.orders import Cart, CartItem, CartItemModifier, CartModifierOption, CartResponse

CART_TTL_SECONDS = 1800  # 30 minutes


def _cart_key(session_token: str) -> str:
    return f"cart:{session_token}"


def _serialize_decimal(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _deserialize_cart(data: dict) -> Cart:
    items = []
    for item_data in data.get("items", []):
        modifiers = []
        for mod_data in item_data.get("modifiers", []):
            options = [
                CartModifierOption(
                    option_id=UUID(opt["option_id"]),
                    name=opt["name"],
                    price_adjustment=Decimal(opt["price_adjustment"])
                )
                for opt in mod_data.get("selected_options", [])
            ]
            modifiers.append(CartItemModifier(
                modifier_id=UUID(mod_data["modifier_id"]),
                name=mod_data["name"],
                selected_options=options
            ))
        items.append(CartItem(
            item_id=UUID(item_data["item_id"]),
            name=item_data["name"],
            quantity=item_data["quantity"],
            unit_price=Decimal(item_data["unit_price"]),
            modifiers=modifiers,
            special_instructions=item_data.get("special_instructions")
        ))
    return Cart(
        merchant_id=UUID(data["merchant_id"]),
        table_id=UUID(data["table_id"]) if data.get("table_id") else None,
        session_token=data.get("session_token"),
        items=items,
        notes=data.get("notes")
    )


class CartService:
    @staticmethod
    async def get_cart(session_token: str) -> Optional[Cart]:
        data = await cache_get(_cart_key(session_token))
        if not data:
            return None
        return _deserialize_cart(data)

    @staticmethod
    async def create_cart(merchant_id: UUID, table_id: Optional[UUID], session_token: str) -> Cart:
        cart = Cart(
            merchant_id=merchant_id,
            table_id=table_id,
            session_token=session_token,
            items=[]
        )
        await CartService.save_cart(cart)
        return cart

    @staticmethod
    async def save_cart(cart: Cart):
        data = json.loads(cart.model_dump_json())
        await cache_set(_cart_key(cart.session_token), data, CART_TTL_SECONDS)

    @staticmethod
    async def add_item(session_token: str, item: CartItem) -> Cart:
        cart = await CartService.get_cart(session_token)
        if not cart:
            raise ValueError("Cart not found")

        existing = None
        for i, cart_item in enumerate(cart.items):
            if cart_item.item_id == item.item_id:
                existing_mods = {(m.modifier_id, tuple(o.option_id for o in m.selected_options))
                                for m in cart_item.modifiers}
                new_mods = {(m.modifier_id, tuple(o.option_id for o in m.selected_options))
                           for m in item.modifiers}
                if existing_mods == new_mods:
                    existing = i
                    break

        if existing is not None:
            cart.items[existing].quantity += item.quantity
        else:
            cart.items.append(item)

        await CartService.save_cart(cart)
        return cart

    @staticmethod
    async def update_item(session_token: str, item_id: UUID, quantity: Optional[int],
                          special_instructions: Optional[str]) -> Cart:
        cart = await CartService.get_cart(session_token)
        if not cart:
            raise ValueError("Cart not found")

        for i, item in enumerate(cart.items):
            if item.item_id == item_id:
                if quantity is not None:
                    if quantity == 0:
                        cart.items.pop(i)
                    else:
                        item.quantity = quantity
                if special_instructions is not None:
                    item.special_instructions = special_instructions
                break

        await CartService.save_cart(cart)
        return cart

    @staticmethod
    async def remove_item(session_token: str, item_id: UUID) -> Cart:
        cart = await CartService.get_cart(session_token)
        if not cart:
            raise ValueError("Cart not found")

        cart.items = [item for item in cart.items if item.item_id != item_id]
        await CartService.save_cart(cart)
        return cart

    @staticmethod
    async def clear_cart(session_token: str):
        await cache_delete(_cart_key(session_token))

    @staticmethod
    async def get_cart_response(session_token: str, tax_rate: Decimal = Decimal("0.100"),
                                delivery_fee: Decimal = Decimal("0.000")) -> CartResponse:
        cart = await CartService.get_cart(session_token)
        if not cart:
            raise ValueError("Cart not found")

        subtotal = cart.subtotal
        tax_amount = (subtotal * tax_rate).quantize(Decimal("0.001"))
        total = subtotal + tax_amount + delivery_fee

        return CartResponse(
            items=cart.items,
            subtotal=subtotal,
            tax_amount=tax_amount,
            delivery_fee=delivery_fee,
            discount_amount=Decimal("0.000"),
            total=total,
            item_count=sum(item.quantity for item in cart.items),
            expires_at=datetime.utcnow() + timedelta(seconds=CART_TTL_SECONDS)
        )
