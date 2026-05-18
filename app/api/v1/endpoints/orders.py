from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.session import get_db
from app.schemas.order import OrderCreate, OrderResponse, OrderStatusUpdate
from app.services.order_service import OrderService
from app.core.auth import get_current_user

router = APIRouter()

@router.post("", response_model=OrderResponse)
async def create_order(
    order_in: OrderCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create order with WhatsApp acceptance trigger for delivery orders"""
    service = OrderService(db)
    order = await service.create(order_in, current_user.merchant_id)

    # Trigger WhatsApp acceptance for delivery orders
    if order.delivery_type in ["delivery", "pickup"]:
        background_tasks.add_task(
            service.trigger_acceptance_flow, order.id
        )

    return order

@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = OrderService(db)
    return await service.get(order_id, current_user.merchant_id)

@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: UUID,
    status_update: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = OrderService(db)
    return await service.update_status(order_id, status_update, current_user)

@router.patch("/{order_id}/kitchen-start")
async def kitchen_start(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = OrderService(db)
    return await service.kitchen_start(order_id, current_user)

@router.patch("/{order_id}/ready")
async def order_ready(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = OrderService(db)
    return await service.mark_ready(order_id, current_user)

@router.patch("/{order_id}/serve")
async def order_serve(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = OrderService(db)
    return await service.mark_served(order_id, current_user)

@router.patch("/{order_id}/assign-driver")
async def assign_driver(
    order_id: UUID,
    driver_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Manual driver assignment (manager/owner)"""
    from app.services.delivery.assignment_service import DriverAssignmentService
    service = DriverAssignmentService(db)
    return await service.manual_assign(order_id, driver_id, current_user)
