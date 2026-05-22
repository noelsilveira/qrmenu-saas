import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Order, OrderItem, PaymentTransaction, MenuItem, ItemModifier, ModifierOption,
    ItemModifierLink,
)
from app.models.models import OrderStatus as OrderStatusEnum, OrderTypeEnum
from app.schemas.orders import (
    OrderStatus, PaymentMethod, PaymentStatus, OrderType,
    Cart, CartItem, CartItemModifier, CartModifierOption,
    OrderResponse, OrderItemResponse, OrderItemModifierResponse,
    CheckoutRequest, CheckoutResponse
)
from app.services.cart_service import CartService
from app.services.payment_service import PaymentService
from app.core.cache import cache_delete_pattern


def _schema_status_to_enum(status: OrderStatus) -> OrderStatusEnum:
    mapping = {
        OrderStatus.pending: OrderStatusEnum.PENDING,
        OrderStatus.confirmed: OrderStatusEnum.CONFIRMED,
        OrderStatus.preparing: OrderStatusEnum.PREPARING,
        OrderStatus.ready: OrderStatusEnum.READY,
        OrderStatus.served: OrderStatusEnum.SERVED,
        OrderStatus.cancelled: OrderStatusEnum.CANCELLED,
        OrderStatus.refunded: OrderStatusEnum.REFUNDED,
    }
    return mapping.get(status, OrderStatusEnum.PENDING)


def _enum_status_to_schema(status: OrderStatusEnum) -> str:
    return status.value.lower()


def _schema_type_to_enum(ot: OrderType) -> OrderTypeEnum:
    mapping = {
        OrderType.dine_in: OrderTypeEnum.dine_in,
        OrderType.takeaway: OrderTypeEnum.takeaway,
        OrderType.delivery: OrderTypeEnum.delivery,
        OrderType.drive_in: OrderTypeEnum.drive_in,
    }
    return mapping.get(ot, OrderTypeEnum.dine_in)


class OrderStateMachine:
    VALID_TRANSITIONS = {
        OrderStatusEnum.PENDING: [OrderStatusEnum.CONFIRMED, OrderStatusEnum.CANCELLED],
        OrderStatusEnum.CONFIRMED: [OrderStatusEnum.PREPARING, OrderStatusEnum.CANCELLED],
        OrderStatusEnum.PREPARING: [OrderStatusEnum.READY, OrderStatusEnum.CANCELLED],
        OrderStatusEnum.READY: [OrderStatusEnum.SERVED, OrderStatusEnum.CANCELLED],
        OrderStatusEnum.SERVED: [],
        OrderStatusEnum.CANCELLED: [OrderStatusEnum.REFUNDED],
        OrderStatusEnum.REFUNDED: [],
    }

    @staticmethod
    def can_transition(current: OrderStatusEnum, new: OrderStatusEnum) -> bool:
        return new in OrderStateMachine.VALID_TRANSITIONS.get(current, [])

    @staticmethod
    def get_allowed_transitions(current: OrderStatusEnum) -> List[OrderStatusEnum]:
        return OrderStateMachine.VALID_TRANSITIONS.get(current, [])


class OrderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_order_from_cart(
        self,
        session_token: str,
        checkout: CheckoutRequest,
        merchant_id: UUID,
        table_id: Optional[UUID] = None
    ) -> CheckoutResponse:
        cart = await CartService.get_cart(session_token)
        if not cart or not cart.items:
            raise ValueError("Cart is empty")

        subtotal = cart.subtotal
        tax_rate = Decimal("0.100")
        tax_amount = (subtotal * tax_rate).quantize(Decimal("0.001"))
        delivery_fee = Decimal("0.500") if checkout.order_type == OrderType.delivery else Decimal("0.000")
        discount_amount = Decimal("0.000")
        total = subtotal + tax_amount + delivery_fee - discount_amount

        order_type_enum = _schema_type_to_enum(checkout.order_type)

        order = Order(
            merchant_id=merchant_id,
            table_id=table_id,
            customer_phone=checkout.customer_phone,
            customer_name=checkout.customer_name,
            session_token=session_token,
            order_type=order_type_enum,
            status=OrderStatusEnum.PENDING,
            payment_method=checkout.payment_method.value,
            payment_status=PaymentStatus.pending.value,
            subtotal=subtotal,
            tax_amount=tax_amount,
            discount_amount=discount_amount,
            delivery_fee=delivery_fee,
            total=total,
            currency="BHD",
            notes=checkout.notes,
            estimated_ready_at=datetime.utcnow() + timedelta(minutes=20)
        )
        self.db.add(order)
        await self.db.flush()

        for cart_item in cart.items:
            total_price = cart_item.line_total
            order_item = OrderItem(
                order_id=order.id,
                item_id=cart_item.item_id,
                item_name_snapshot=cart_item.name,
                quantity=cart_item.quantity,
                unit_price=cart_item.unit_price,
                total_price=total_price,
                modifier_summary=[
                    {
                        "modifier_name": m.name,
                        "selected_options": [o.name for o in m.selected_options],
                        "price_adjustment": str(sum(o.price_adjustment for o in m.selected_options))
                    }
                    for m in cart_item.modifiers
                ],
                special_instructions=cart_item.special_instructions,
                prep_time_min=5,
                prep_status="pending"
            )
            self.db.add(order_item)

        await self.db.flush()

        client_secret = None
        paypal_order_id = None
        redirect_url = None

        if checkout.payment_method in [PaymentMethod.stripe, PaymentMethod.paypal]:
            payment_intent = await PaymentService.create_payment_intent(
                order_id=order.id,
                amount=total,
                currency="BHD",
                method=checkout.payment_method
            )

            transaction = PaymentTransaction(
                id=payment_intent.transaction_id,
                order_id=order.id,
                merchant_id=merchant_id,
                method=checkout.payment_method.value,
                status=payment_intent.status.value,
                amount=total,
                currency="BHD",
                provider_ref=payment_intent.paypal_order_id if checkout.payment_method == PaymentMethod.paypal else None
            )
            self.db.add(transaction)
            await self.db.flush()

            client_secret = payment_intent.client_secret
            paypal_order_id = payment_intent.paypal_order_id
            redirect_url = payment_intent.redirect_url

        elif checkout.payment_method == PaymentMethod.cod:
            transaction = PaymentTransaction(
                id=uuid.uuid4(),
                order_id=order.id,
                merchant_id=merchant_id,
                method=PaymentMethod.cod.value,
                status=PaymentStatus.pending.value,
                amount=total,
                currency="BHD"
            )
            self.db.add(transaction)
            await self.db.flush()

        await CartService.clear_cart(session_token)
        await cache_delete_pattern(f"orders:*:{merchant_id}")

        return CheckoutResponse(
            order_id=order.id,
            status=OrderStatus(_enum_status_to_schema(order.status)),
            total=total,
            payment_method=checkout.payment_method,
            payment_status=PaymentStatus(order.payment_status),
            client_secret=client_secret,
            paypal_order_id=paypal_order_id,
            redirect_url=redirect_url,
            expires_at=datetime.utcnow() + timedelta(minutes=30)
        )

    async def get_order(self, order_id: UUID, merchant_id: Optional[UUID] = None) -> Optional[OrderResponse]:
        result = await self.db.execute(
            select(Order).where(
                Order.id == order_id,
                Order.merchant_id == merchant_id if merchant_id else True
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            return None
        return await self._to_response(order)

    async def list_orders(
        self,
        merchant_id: UUID,
        status: Optional[OrderStatus] = None,
        order_type: Optional[OrderType] = None,
        payment_status: Optional[PaymentStatus] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        conditions = [Order.merchant_id == merchant_id]
        if status:
            conditions.append(Order.status == _schema_status_to_enum(status))
        if order_type:
            conditions.append(Order.order_type == _schema_type_to_enum(order_type))
        if payment_status:
            conditions.append(Order.payment_status == payment_status.value)
        if date_from:
            conditions.append(Order.created_at >= date_from)
        if date_to:
            conditions.append(Order.created_at <= date_to)

        count_result = await self.db.execute(
            select(Order).where(and_(*conditions))
        )
        total = len(count_result.scalars().all())

        result = await self.db.execute(
            select(Order)
            .where(and_(*conditions))
            .order_by(desc(Order.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        orders = result.scalars().all()

        responses = []
        for order in orders:
            responses.append(await self._to_response(order))

        return {
            "orders": responses,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    async def update_status(
        self,
        order_id: UUID,
        merchant_id: UUID,
        new_status: OrderStatus,
        reason: Optional[str] = None
    ) -> OrderResponse:
        result = await self.db.execute(
            select(Order).where(
                Order.id == order_id,
                Order.merchant_id == merchant_id
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            raise ValueError("Order not found")

        new_enum = _schema_status_to_enum(new_status)
        if not OrderStateMachine.can_transition(order.status, new_enum):
            raise ValueError(
                f"Cannot transition from {order.status.value} to {new_enum.value}. "
                f"Allowed: {[s.value for s in OrderStateMachine.get_allowed_transitions(order.status)]}"
            )

        order.status = new_enum
        order.updated_at = datetime.utcnow()

        if new_enum == OrderStatusEnum.SERVED:
            order.served_at = datetime.utcnow()

        if new_enum == OrderStatusEnum.CANCELLED and reason:
            order.notes = f"{order.notes or ''}\nCancelled: {reason}"

        await self.db.flush()
        await cache_delete_pattern(f"orders:*:{merchant_id}")

        return await self._to_response(order)

    async def update_item_status(
        self,
        order_id: UUID,
        merchant_id: UUID,
        item_id: UUID,
        status: str
    ) -> OrderResponse:
        result = await self.db.execute(
            select(OrderItem).join(Order).where(
                OrderItem.id == item_id,
                Order.id == order_id,
                Order.merchant_id == merchant_id
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise ValueError("Order item not found")

        item.prep_status = status
        await self.db.flush()

        return await self.get_order(order_id, merchant_id)

    async def _to_response(self, order: Order) -> OrderResponse:
        items_result = await self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order.id)
        )
        items = items_result.scalars().all()

        item_responses = []
        for item in items:
            mods = []
            for mod_data in (item.modifier_summary or []):
                if isinstance(mod_data, dict):
                    mods.append(OrderItemModifierResponse(
                        modifier_name=mod_data.get("modifier_name", ""),
                        selected_options=mod_data.get("selected_options", []),
                        price_adjustment=Decimal(mod_data.get("price_adjustment", "0"))
                    ))

            item_responses.append(OrderItemResponse(
                id=item.id,
                menu_item_id=item.item_id,
                name=item.item_name_snapshot,
                name_localized=None,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                modifiers=mods,
                special_instructions=item.special_instructions,
                prep_time_min=item.prep_time_min,
                status=item.prep_status
            ))

        return OrderResponse(
            id=order.id,
            merchant_id=order.merchant_id,
            table_id=order.table_id,
            customer_phone=order.customer_phone or "",
            customer_name=order.customer_name,
            session_token=order.session_token,
            order_type=OrderType(_enum_status_to_schema(order.order_type)),
            status=OrderStatus(_enum_status_to_schema(order.status)),
            payment_method=PaymentMethod(order.payment_method) if order.payment_method else None,
            payment_status=PaymentStatus(order.payment_status),
            subtotal=order.subtotal,
            tax_amount=order.tax_amount,
            discount_amount=order.discount_amount,
            delivery_fee=order.delivery_fee,
            total=order.total,
            currency=order.currency,
            notes=order.notes,
            items=item_responses,
            estimated_ready_at=order.estimated_ready_at,
            served_at=order.served_at,
            created_at=order.created_at,
            updated_at=order.updated_at
        )
