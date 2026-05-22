"""
Phase 9 Service — Kitchen Display System (KDS)
Manages real-time order flow for kitchen display screens.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal
from sqlalchemy import select, and_, or_, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Order, OrderStatus, OrderItem,
    FinancialLedger, LedgerEntryType
)
from app.schemas.websocket import (
    KDSOrder, KDSItem, KDSItemStatus, KDSOrderStatus,
    KDSStats, KDSBumpRequest, KDSUpdateRequest, KDSFilterParams,
    KDSDisplayConfig
)
from app.core.websocket_manager import ws_manager, WSMessage, WSMessageType

# ─── KDS SERVICE ─────────────────────────────────────────────────

class KDSService:
    """
    Kitchen Display System service.

    Responsibilities:
    - Transform Order → KDSOrder for display
    - Track item-level preparation status
    - Calculate SLA metrics and color tags
    - Broadcast updates to KDS WebSocket rooms
    - Handle bump (complete) operations
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Order Transformation ──────────────────────────────────────

    async def order_to_kds(self, order: Order) -> KDSOrder:
        """Convert a database Order to KDS display format."""

        # Fetch items
        items_result = await self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order.id)
        )
        order_items = items_result.scalars().all()

        kds_items = []
        for item in order_items:
            # Extract modifiers from JSONB modifier_summary
            modifiers = []
            if item.modifier_summary and isinstance(item.modifier_summary, dict):
                mods = item.modifier_summary.get("modifiers") or item.modifier_summary.get("items", [])
                if isinstance(mods, list):
                    for m in mods:
                        if isinstance(m, dict):
                            name = m.get("name") or m.get("modifier_name")
                            if name:
                                modifiers.append(name)
                        elif isinstance(m, str):
                            modifiers.append(m)

            kds_items.append(KDSItem(
                item_id=item.id,
                name=item.item_name_snapshot,
                quantity=item.quantity,
                modifiers=modifiers,
                special_instructions=item.special_instructions,
                status=self._map_item_status(order.status),
                station=self._infer_station(item.item_name_snapshot),
                started_at=order.confirmed_at
            ))

        # Calculate elapsed time
        now = datetime.utcnow()
        elapsed = int((now - order.created_at).total_seconds()) if order.created_at else 0

        # Determine color tag based on SLA
        order_type_val = order.order_type.value if hasattr(order.order_type, 'value') else str(order.order_type)
        color_tag = self._calculate_color_tag(elapsed, order_type_val)

        # Map order status to KDS status
        kds_status = self._map_order_status(order.status)

        return KDSOrder(
            order_id=order.id,
            order_number=order.order_number,
            external_order_id=order.external_order_id,
            status=kds_status,
            items=kds_items,
            table_number=order.table_number,
            order_type=order_type_val,
            priority=order.priority or 0,
            created_at=order.created_at,
            promised_time=order.promised_delivery_time,
            elapsed_seconds=elapsed,
            customer_name=order.customer_name,
            delivery_address=order.delivery_address.get("formatted") if isinstance(order.delivery_address, dict) else None,
            driver_name=order.driver_name if hasattr(order, 'driver_name') else None,
            notes=order.notes,
            color_tag=color_tag
        )

    def _map_order_status(self, order_status: OrderStatus) -> KDSOrderStatus:
        """Map internal order status to KDS display status."""
        mapping = {
            OrderStatus.PENDING: KDSOrderStatus.PENDING,
            OrderStatus.CONFIRMED: KDSOrderStatus.PREPARING,
            OrderStatus.PREPARING: KDSOrderStatus.PREPARING,
            OrderStatus.READY: KDSOrderStatus.READY,
            OrderStatus.SERVED: KDSOrderStatus.SERVED,
            OrderStatus.OUT_FOR_DELIVERY: KDSOrderStatus.READY,
            OrderStatus.DELIVERED: KDSOrderStatus.SERVED,
            OrderStatus.CANCELLED: KDSOrderStatus.CANCELLED,
        }
        return mapping.get(order_status, KDSOrderStatus.PENDING)

    def _map_item_status(self, order_status: OrderStatus) -> KDSItemStatus:
        """Map order status to item status."""
        mapping = {
            OrderStatus.PENDING: KDSItemStatus.PENDING,
            OrderStatus.CONFIRMED: KDSItemStatus.PREPARING,
            OrderStatus.PREPARING: KDSItemStatus.PREPARING,
            OrderStatus.READY: KDSItemStatus.READY,
            OrderStatus.SERVED: KDSItemStatus.SERVED,
            OrderStatus.OUT_FOR_DELIVERY: KDSItemStatus.READY,
            OrderStatus.DELIVERED: KDSItemStatus.SERVED,
        }
        return mapping.get(order_status, KDSItemStatus.PENDING)

    def _infer_station(self, item_name: str) -> str:
        """Infer kitchen station from item name (naive; enhance with menu metadata)."""
        name_lower = item_name.lower()
        if any(w in name_lower for w in ["grill", "steak", "burger", "chicken", "meat"]):
            return "grill"
        if any(w in name_lower for w in ["fry", "fries", "fried", "crispy", "wings"]):
            return "fryer"
        if any(w in name_lower for w in ["salad", "greens", "vegan", "healthy"]):
            return "salad"
        if any(w in name_lower for w in ["drink", "coffee", "tea", "juice", "soda", "water"]):
            return "drinks"
        if any(w in name_lower for w in ["dessert", "cake", "ice cream", "sweet"]):
            return "dessert"
        return "main"

    def _calculate_color_tag(self, elapsed_seconds: int, order_type: str) -> str:
        """Calculate SLA color: green (< 10min), yellow (10-15min), red (> 15min)."""
        # Delivery gets more time
        thresholds = {
            "delivery": (900, 1200),      # 15min warn, 20min critical
            "dine_in": (600, 900),         # 10min warn, 15min critical
            "takeaway": (300, 600),        # 5min warn, 10min critical
        }

        warn, critical = thresholds.get(order_type, (600, 900))

        if elapsed_seconds > critical:
            return "red"
        elif elapsed_seconds > warn:
            return "yellow"
        return "green"

    # ─── KDS Operations ────────────────────────────────────────────

    async def get_active_orders(
        self,
        merchant_id: uuid.UUID,
        branch_id: Optional[uuid.UUID] = None,
        params: Optional[KDSFilterParams] = None
    ) -> Tuple[List[KDSOrder], int]:
        """Get all active (non-completed) orders for KDS display."""

        active_statuses = [
            OrderStatus.PENDING,
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY,
            OrderStatus.OUT_FOR_DELIVERY
        ]

        query = select(Order).where(
            Order.merchant_id == merchant_id,
            Order.status.in_(active_statuses)
        )

        if branch_id:
            query = query.where(Order.branch_id == branch_id)

        if params:
            if params.status:
                status_values = [s.value if hasattr(s, 'value') else s for s in params.status]
                # Need to map KDS statuses back to Order statuses
                order_statuses = []
                for s in params.status:
                    if s == KDSOrderStatus.PENDING:
                        order_statuses.append(OrderStatus.PENDING)
                    elif s == KDSOrderStatus.PREPARING:
                        order_statuses.extend([OrderStatus.CONFIRMED, OrderStatus.PREPARING])
                    elif s == KDSOrderStatus.READY:
                        order_statuses.append(OrderStatus.READY)
                    elif s == KDSOrderStatus.SERVED:
                        order_statuses.extend([OrderStatus.SERVED, OrderStatus.DELIVERED])
                if order_statuses:
                    query = query.where(Order.status.in_(order_statuses))

            if params.order_type:
                query = query.where(Order.order_type == params.order_type)

            if params.search:
                search = f"%{params.search}%"
                query = query.where(
                    or_(
                        Order.order_number.ilike(search),
                        Order.customer_name.ilike(search),
                        Order.external_order_id.ilike(search)
                    )
                )

        query = query.order_by(desc(Order.priority), Order.created_at)

        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar()

        if params:
            query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)

        result = await self.db.execute(query)
        orders = result.scalars().all()

        kds_orders = [await self.order_to_kds(o) for o in orders]

        # Filter delayed_only in memory (since color_tag is computed)
        if params and params.delayed_only:
            kds_orders = [o for o in kds_orders if o.color_tag == "red"]

        return kds_orders, total

    async def bump_order(self, merchant_id: uuid.UUID, request: KDSBumpRequest) -> Optional[KDSOrder]:
        """Mark an order as completed (bumped off the screen)."""

        result = await self.db.execute(
            select(Order).where(
                Order.id == request.order_id,
                Order.merchant_id == merchant_id
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            return None

        # Update order status
        order.status = OrderStatus.SERVED
        order.served_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()

        await self.db.flush()

        kds_order = await self.order_to_kds(order)

        # Broadcast to KDS room
        room = ws_manager.kds_room(str(merchant_id), str(order.branch_id) if order.branch_id else None)
        msg = WSMessage(
            WSMessageType.ORDER_BUMP,
            {
                "order_id": str(order.id),
                "order_number": order.order_number,
                "bumped_by": request.bumped_by,
                "station": request.station,
                "order": kds_order.model_dump()
            },
            room=room,
            merchant_id=str(merchant_id)
        )
        await ws_manager.broadcast_to_room(room, msg)

        return kds_order

    async def update_order_status(
        self,
        merchant_id: uuid.UUID,
        request: KDSUpdateRequest
    ) -> Optional[KDSOrder]:
        """Update order or item status from KDS."""

        result = await self.db.execute(
            select(Order).where(
                Order.id == request.order_id,
                Order.merchant_id == merchant_id
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            return None

        if request.status:
            # Map KDS status back to Order status
            status_map = {
                KDSOrderStatus.PREPARING: OrderStatus.PREPARING,
                KDSOrderStatus.READY: OrderStatus.READY,
                KDSOrderStatus.SERVED: OrderStatus.SERVED,
                KDSOrderStatus.CANCELLED: OrderStatus.CANCELLED,
            }
            new_status = status_map.get(request.status)
            if new_status:
                order.status = new_status
                if new_status == OrderStatus.READY:
                    order.ready_at = datetime.utcnow()
                elif new_status == OrderStatus.SERVED:
                    order.served_at = datetime.utcnow()

        if request.notes:
            order.notes = request.notes

        order.updated_at = datetime.utcnow()
        await self.db.flush()

        kds_order = await self.order_to_kds(order)

        # Broadcast update
        room = ws_manager.kds_room(str(merchant_id), str(order.branch_id) if order.branch_id else None)
        msg = WSMessage(
            WSMessageType.ORDER_STATUS_CHANGE,
            {
                "order_id": str(order.id),
                "new_status": kds_order.status.value,
                "order": kds_order.model_dump()
            },
            room=room,
            merchant_id=str(merchant_id)
        )
        await ws_manager.broadcast_to_room(room, msg)

        return kds_order

    async def get_stats(self, merchant_id: uuid.UUID, branch_id: Optional[uuid.UUID] = None) -> KDSStats:
        """Get real-time KDS statistics."""

        active_statuses = [
            OrderStatus.PENDING,
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY,
            OrderStatus.OUT_FOR_DELIVERY
        ]

        query = select(Order).where(
            Order.merchant_id == merchant_id,
            Order.status.in_(active_statuses)
        )
        if branch_id:
            query = query.where(Order.branch_id == branch_id)

        result = await self.db.execute(query)
        orders = result.scalars().all()

        total = len(orders)
        preparing = sum(1 for o in orders if o.status in [OrderStatus.CONFIRMED, OrderStatus.PREPARING])
        ready = sum(1 for o in orders if o.status == OrderStatus.READY)

        # Delayed = elapsed > 15 min
        now = datetime.utcnow()
        delayed = sum(
            1 for o in orders
            if o.created_at and (now - o.created_at).total_seconds() > 900
        )

        # Average prep time (for completed orders today)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        completed_result = await self.db.execute(
            select(Order).where(
                Order.merchant_id == merchant_id,
                Order.status.in_([OrderStatus.SERVED, OrderStatus.DELIVERED]),
                Order.served_at >= today_start
            )
        )
        completed = completed_result.scalars().all()

        avg_prep = 0
        if completed:
            prep_times = [
                (o.served_at - o.created_at).total_seconds()
                for o in completed
                if o.served_at and o.created_at
            ]
            avg_prep = int(sum(prep_times) / len(prep_times)) if prep_times else 0

        longest_wait = 0
        if orders:
            waits = [
                (now - o.created_at).total_seconds()
                for o in orders if o.created_at
            ]
            longest_wait = int(max(waits)) if waits else 0

        # Orders per hour (last 4 hours)
        four_hours_ago = datetime.utcnow() - timedelta(hours=4)
        recent_result = await self.db.execute(
            select(func.count(Order.id)).where(
                Order.merchant_id == merchant_id,
                Order.created_at >= four_hours_ago
            )
        )
        recent_count = recent_result.scalar()
        orders_per_hour = recent_count / 4.0

        return KDSStats(
            total_active=total,
            total_preparing=preparing,
            total_ready=ready,
            total_delayed=delayed,
            avg_prep_time_seconds=avg_prep,
            longest_wait_seconds=longest_wait,
            orders_per_hour=round(orders_per_hour, 1)
        )

    async def broadcast_new_order(self, order: Order) -> None:
        """Broadcast a new order to all KDS displays for the merchant."""
        kds_order = await self.order_to_kds(order)

        room = ws_manager.kds_room(
            str(order.merchant_id),
            str(order.branch_id) if order.branch_id else None
        )

        msg = WSMessage(
            WSMessageType.ORDER_NEW,
            {"order": kds_order.model_dump()},
            room=room,
            merchant_id=str(order.merchant_id)
        )

        await ws_manager.broadcast_to_room(room, msg)

    async def broadcast_order_update(self, order: Order, event: str = "update") -> None:
        """Broadcast an order update to KDS displays."""
        kds_order = await self.order_to_kds(order)

        room = ws_manager.kds_room(
            str(order.merchant_id),
            str(order.branch_id) if order.branch_id else None
        )

        msg_type = WSMessageType.ORDER_UPDATE
        if order.status == OrderStatus.READY:
            msg_type = WSMessageType.ORDER_READY

        msg = WSMessage(
            msg_type,
            {"order": kds_order.model_dump(), "event": event},
            room=room,
            merchant_id=str(order.merchant_id)
        )

        await ws_manager.broadcast_to_room(room, msg)
