from typing import Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_active_user, require_role
from app.models import User
from app.schemas.orders import (
    CheckoutRequest, CheckoutResponse,
    OrderResponse, OrderListResponse,
    OrderStatusUpdate, OrderItemStatusUpdate, BulkOrderStatusUpdate,
    OrderStatus, PaymentStatus
)
from app.services.order_service import OrderService
from app.schemas.order import OrderCreate as LegacyOrderCreate, OrderResponse as LegacyOrderResponse, OrderStatusUpdate as LegacyOrderStatusUpdate

router = APIRouter()


def _get_merchant_id(user: User) -> UUID:
    return user.merchant_id


# ---------------------------------------------------------------------------
# Legacy compatibility endpoints
# ---------------------------------------------------------------------------
@router.post("", response_model=LegacyOrderResponse)
async def create_order(
    order_in: LegacyOrderCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Legacy create order endpoint (stub)."""
    raise HTTPException(status_code=501, detail="Use /checkout instead")


# ---------------------------------------------------------------------------
# Customer-facing: Checkout
# ---------------------------------------------------------------------------
@router.post("/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def checkout(
    data: CheckoutRequest,
    session_token: str,
    merchant_id: UUID,
    table_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    """Convert cart to order. Creates payment intent if needed."""
    service = OrderService(db)
    try:
        return await service.create_order_from_cart(
            session_token=session_token,
            checkout=data,
            merchant_id=merchant_id,
            table_id=table_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Customer: Get my order
# ---------------------------------------------------------------------------
@router.get("/customer/{order_id}", response_model=OrderResponse)
async def get_customer_order(
    order_id: UUID,
    session_token: str,
    db: AsyncSession = Depends(get_db),
):
    """Customer checks their order status."""
    service = OrderService(db)
    order = await service.get_order(order_id)
    if not order or order.session_token != session_token:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


# ---------------------------------------------------------------------------
# Merchant: List orders
# ---------------------------------------------------------------------------
@router.get("/merchant", response_model=dict)
async def list_merchant_orders(
    status: Optional[OrderStatus] = Query(None),
    order_type: Optional[str] = Query(None),
    payment_status: Optional[PaymentStatus] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all orders for merchant with filters."""
    merchant_id = _get_merchant_id(current_user)
    service = OrderService(db)

    ot = None
    if order_type:
        try:
            ot = OrderStatus(order_type)
        except:
            pass

    result = await service.list_orders(
        merchant_id=merchant_id,
        status=status,
        order_type=ot,
        payment_status=payment_status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size
    )
    return result


# ---------------------------------------------------------------------------
# Merchant: Get single order
# ---------------------------------------------------------------------------
@router.get("/merchant/{order_id}", response_model=OrderResponse)
async def get_merchant_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get order details."""
    merchant_id = _get_merchant_id(current_user)
    service = OrderService(db)
    order = await service.get_order(order_id, merchant_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


# ---------------------------------------------------------------------------
# Merchant: Update order status (Kitchen / Counter)
# ---------------------------------------------------------------------------
@router.put("/merchant/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: UUID,
    data: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Update order status via state machine."""
    merchant_id = _get_merchant_id(current_user)
    service = OrderService(db)
    try:
        return await service.update_status(
            order_id=order_id,
            merchant_id=merchant_id,
            new_status=data.status,
            reason=data.reason
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/merchant/{order_id}/items/{item_id}/status", response_model=OrderResponse)
async def update_order_item_status(
    order_id: UUID,
    item_id: UUID,
    data: OrderItemStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Update individual item status (for KDS)."""
    merchant_id = _get_merchant_id(current_user)
    service = OrderService(db)
    try:
        return await service.update_item_status(
            order_id=order_id,
            merchant_id=merchant_id,
            item_id=item_id,
            status=data.status
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/merchant/bulk-status", response_model=List[OrderResponse])
async def bulk_update_status(
    data: BulkOrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Bulk update order statuses."""
    merchant_id = _get_merchant_id(current_user)
    service = OrderService(db)
    results = []
    for order_id in data.order_ids:
        try:
            order = await service.update_status(
                order_id=order_id,
                merchant_id=merchant_id,
                new_status=data.status
            )
            results.append(order)
        except ValueError:
            pass
    return results


# ---------------------------------------------------------------------------
# Merchant: Cancel order
# ---------------------------------------------------------------------------
@router.post("/merchant/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Cancel an order."""
    merchant_id = _get_merchant_id(current_user)
    service = OrderService(db)
    try:
        return await service.update_status(
            order_id=order_id,
            merchant_id=merchant_id,
            new_status=OrderStatus.cancelled,
            reason=reason
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
