"""
Phase 9 Tests — WebSocket KDS, Driver Tracking, Fleet Map
Run with: pytest tests/test_phase9_websocket_kds.py -v
"""

import uuid
import pytest
import json
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Order, OrderStatus, OrderTypeEnum,
    OrderItem, Driver
)
from app.schemas.websocket import (
    KDSOrder, KDSItem, KDSItemStatus, KDSOrderStatus,
    KDSStats, KDSBumpRequest, KDSUpdateRequest, KDSFilterParams,
    DriverLocationUpdate, DriverStatus, GeoPoint,
    DriverAssignRequest, DriverPickupConfirm, DriverDeliveryConfirm,
    WSAuthPayload, WSSubscribePayload
)
from app.services.kds_service import KDSService
from app.services.driver_tracking_service import DriverTrackingService
from app.core.websocket_manager import ConnectionManager, WSMessage, WSMessageType

# ─── FIXTURES ──────────────────────────────────────────────────────

@pytest.fixture
def merchant_id() -> uuid.UUID:
    return uuid.uuid4()

@pytest.fixture
def branch_id() -> uuid.UUID:
    return uuid.uuid4()

@pytest.fixture
def driver_id() -> uuid.UUID:
    return uuid.uuid4()

@pytest.fixture
def order_id() -> uuid.UUID:
    return uuid.uuid4()

@pytest.fixture
async def sample_order(db_session: AsyncSession, merchant_id: uuid.UUID, order_id: uuid.UUID, branch_id: uuid.UUID) -> Order:
    order = Order(
        id=order_id,
        merchant_id=merchant_id,
        branch_id=branch_id,
        order_number="ORD-KDS-001",
        external_order_id=None,
        status=OrderStatus.CONFIRMED,
        order_type=OrderTypeEnum.dine_in,
        payment_method="cod",
        total=Decimal("45.00"),
        subtotal=Decimal("42.75"),
        tax_amount=Decimal("2.25"),
        customer_name="Test Customer",
        table_number="T-12",
        notes="Extra spicy",
        priority=1,
        created_at=datetime.utcnow() - timedelta(minutes=5),
        confirmed_at=datetime.utcnow() - timedelta(minutes=4),
    )
    db_session.add(order)
    await db_session.flush()

    # Add items
    item1 = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        item_id=None,
        item_name_snapshot="Chicken Burger",
        quantity=2,
        unit_price=Decimal("12.00"),
        total_price=Decimal("24.00"),
        special_instructions="No onion"
    )
    item2 = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        item_id=None,
        item_name_snapshot="Caesar Salad",
        quantity=1,
        unit_price=Decimal("15.00"),
        total_price=Decimal("15.00")
    )
    db_session.add(item1)
    db_session.add(item2)
    await db_session.flush()

    return order

@pytest.fixture
async def sample_driver(db_session: AsyncSession, merchant_id: uuid.UUID, driver_id: uuid.UUID) -> Driver:
    driver = Driver(
        id=driver_id,
        merchant_id=merchant_id,
        name="Ali Driver",
        phone="+97333334444",
        vehicle_type="motorcycle",
        status="available",
        current_lat=Decimal("26.2285"),
        current_lng=Decimal("50.5860"),
        last_location_at=datetime.utcnow(),
        is_active=True
    )
    db_session.add(driver)
    await db_session.flush()
    return driver

# ─── WEBSOCKET MANAGER TESTS ─────────────────────────────────────

@pytest.mark.asyncio
async def test_connection_manager_connect_disconnect():
    manager = ConnectionManager()
    mock_ws = AsyncMock(spec=WebSocket)

    await manager.connect(
        mock_ws,
        merchant_id="merch-123",
        connection_id="conn-1",
        client_type="kds"
    )

    mock_ws.accept.assert_called_once()
    assert "conn-1" in manager._connection_merchant
    assert manager._connection_merchant["conn-1"] == "merch-123"

    await manager.disconnect("conn-1")
    assert "conn-1" not in manager._connection_merchant

@pytest.mark.asyncio
async def test_connection_manager_room_subscribe():
    manager = ConnectionManager()
    mock_ws = AsyncMock(spec=WebSocket)

    await manager.connect(mock_ws, "merch-123", "conn-1", "kds")
    await manager.subscribe("conn-1", "kds:merch-123")

    assert "kds:merch-123" in manager._rooms
    assert "conn-1" in manager._rooms["kds:merch-123"]

    await manager.unsubscribe("conn-1", "kds:merch-123")
    assert "conn-1" not in manager._rooms.get("kds:merch-123", set())

@pytest.mark.asyncio
async def test_connection_manager_broadcast():
    manager = ConnectionManager()
    mock_ws1 = AsyncMock(spec=WebSocket)
    mock_ws2 = AsyncMock(spec=WebSocket)

    await manager.connect(mock_ws1, "merch-123", "conn-1", "kds")
    await manager.connect(mock_ws2, "merch-123", "conn-2", "kds")
    await manager.subscribe("conn-1", "room-a")
    await manager.subscribe("conn-2", "room-a")

    msg = WSMessage(WSMessageType.ORDER_NEW, {"test": "data"}, room="room-a")
    delivered = await manager.broadcast_to_room("room-a", msg)

    assert delivered == 2
    mock_ws1.send_text.assert_called_once()
    mock_ws2.send_text.assert_called_once()

@pytest.mark.asyncio
async def test_connection_manager_merchant_broadcast():
    manager = ConnectionManager()
    mock_ws1 = AsyncMock(spec=WebSocket)
    mock_ws2 = AsyncMock(spec=WebSocket)

    await manager.connect(mock_ws1, "merch-123", "conn-1", "kds")
    await manager.connect(mock_ws2, "merch-123", "conn-2", "merchant")

    msg = WSMessage(WSMessageType.SYSTEM, {"alert": "test"})
    delivered = await manager.broadcast_to_merchant("merch-123", msg, client_type="kds")

    assert delivered == 1
    mock_ws1.send_text.assert_called_once()
    mock_ws2.send_text.assert_not_called()

@pytest.mark.asyncio
async def test_ws_message_serialization():
    msg = WSMessage(
        WSMessageType.ORDER_NEW,
        {"order_id": "123"},
        room="kds:test",
        merchant_id="merch-123"
    )

    data = msg.to_dict()
    assert data["type"] == WSMessageType.ORDER_NEW
    assert data["payload"]["order_id"] == "123"
    assert data["room"] == "kds:test"

    json_str = msg.to_json()
    assert "order:new" in json_str

# ─── KDS SERVICE TESTS ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_order_to_kds_conversion(db_session: AsyncSession, merchant_id: uuid.UUID, sample_order: Order):
    service = KDSService(db_session)
    kds = await service.order_to_kds(sample_order)

    assert kds.order_id == sample_order.id
    assert kds.order_number == "ORD-KDS-001"
    assert kds.status == KDSOrderStatus.PREPARING
    assert len(kds.items) == 2
    assert kds.items[0].name == "Chicken Burger"
    assert kds.items[0].station == "grill"
    assert kds.items[1].station == "salad"
    assert kds.table_number == "T-12"
    assert kds.color_tag in ["green", "yellow", "red"]
    assert kds.elapsed_seconds > 0

@pytest.mark.asyncio
async def test_kds_get_active_orders(db_session: AsyncSession, merchant_id: uuid.UUID, sample_order: Order):
    service = KDSService(db_session)
    orders, total = await service.get_active_orders(merchant_id, None, KDSFilterParams())

    assert len(orders) >= 1
    assert total >= 1
    assert any(o.order_id == sample_order.id for o in orders)

@pytest.mark.asyncio
async def test_kds_bump_order(db_session: AsyncSession, merchant_id: uuid.UUID, sample_order: Order):
    service = KDSService(db_session)

    request = KDSBumpRequest(
        order_id=sample_order.id,
        bumped_by="Chef John",
        station="grill"
    )

    result = await service.bump_order(merchant_id, request)
    assert result is not None
    assert result.status == KDSOrderStatus.SERVED

    # Verify DB updated
    await db_session.refresh(sample_order)
    assert sample_order.status == OrderStatus.SERVED

@pytest.mark.asyncio
async def test_kds_update_order_status(db_session: AsyncSession, merchant_id: uuid.UUID, sample_order: Order):
    service = KDSService(db_session)

    request = KDSUpdateRequest(
        order_id=sample_order.id,
        status=KDSOrderStatus.READY,
        notes="Ready for pickup"
    )

    result = await service.update_order_status(merchant_id, request)
    assert result is not None
    assert result.status == KDSOrderStatus.READY

    await db_session.refresh(sample_order)
    assert sample_order.status == OrderStatus.READY

@pytest.mark.asyncio
async def test_kds_stats(db_session: AsyncSession, merchant_id: uuid.UUID, sample_order: Order):
    service = KDSService(db_session)
    stats = await service.get_stats(merchant_id)

    assert stats.total_active >= 1
    assert stats.total_preparing >= 1
    assert stats.longest_wait_seconds >= 0
    assert stats.orders_per_hour >= 0

@pytest.mark.asyncio
async def test_kds_color_tag_calculation():
    service = KDSService(None)  # No DB needed for this pure function test

    assert service._calculate_color_tag(300, "dine_in") == "green"    # 5 min
    assert service._calculate_color_tag(700, "dine_in") == "yellow"   # ~12 min
    assert service._calculate_color_tag(1000, "dine_in") == "red"     # ~17 min

    assert service._calculate_color_tag(800, "delivery") == "green"   # 13 min < 15
    assert service._calculate_color_tag(1000, "delivery") == "yellow" # ~17 min
    assert service._calculate_color_tag(1300, "delivery") == "red"    # ~22 min

@pytest.mark.asyncio
async def test_kds_station_inference():
    service = KDSService(None)

    assert service._infer_station("Grilled Chicken") == "grill"
    assert service._infer_station("French Fries") == "fryer"
    assert service._infer_station("Green Salad") == "salad"
    assert service._infer_station("Iced Coffee") == "drinks"
    assert service._infer_station("Chocolate Cake") == "dessert"
    assert service._infer_station("Random Dish") == "main"

# ─── DRIVER TRACKING TESTS ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_driver_location_update(db_session: AsyncSession, merchant_id: uuid.UUID, sample_driver: Driver):
    service = DriverTrackingService(db_session)

    update = DriverLocationUpdate(
        driver_id=sample_driver.id,
        location=GeoPoint(lat=26.2300, lng=50.5900, timestamp=datetime.utcnow()),
        status=DriverStatus.EN_ROUTE_DELIVERY,
        battery_level=85,
        order_id=None
    )

    result = await service.update_location(merchant_id, update)

    assert result.driver_id == sample_driver.id
    assert result.status == DriverStatus.EN_ROUTE_DELIVERY
    assert result.location.lat == 26.2300

    # Verify DB updated
    await db_session.refresh(sample_driver)
    assert sample_driver.current_lat == Decimal("26.2300")
    assert sample_driver.status == "en_route_delivery"

@pytest.mark.asyncio
async def test_driver_assign(db_session: AsyncSession, merchant_id: uuid.UUID, 
                              sample_driver: Driver, sample_order: Order):
    service = DriverTrackingService(db_session)

    # Set order to ready for delivery
    sample_order.status = OrderStatus.READY
    sample_order.order_type = OrderTypeEnum.delivery
    await db_session.flush()

    request = DriverAssignRequest(
        order_id=sample_order.id,
        driver_id=sample_driver.id,
        assigned_by="Manager",
        estimated_pickup_time=datetime.utcnow() + timedelta(minutes=10),
        estimated_delivery_time=datetime.utcnow() + timedelta(minutes=30)
    )

    result = await service.assign_driver(merchant_id, request)

    assert result is not None
    assert result.status == DriverStatus.ASSIGNED
    assert result.active_order_id == sample_order.id

    await db_session.refresh(sample_order)
    assert sample_order.driver_id == sample_driver.id
    assert sample_order.status == OrderStatus.OUT_FOR_DELIVERY

@pytest.mark.asyncio
async def test_driver_confirm_pickup(db_session: AsyncSession, merchant_id: uuid.UUID,
                                      sample_driver: Driver, sample_order: Order):
    service = DriverTrackingService(db_session)

    # Setup: assign driver first
    sample_order.driver_id = sample_driver.id
    sample_order.status = OrderStatus.OUT_FOR_DELIVERY
    sample_driver.status = "assigned"
    await db_session.flush()

    request = DriverPickupConfirm(
        order_id=sample_order.id,
        driver_id=sample_driver.id,
        picked_up_at=datetime.utcnow(),
        items_verified=True
    )

    result = await service.confirm_pickup(merchant_id, request)
    assert result is not None

    await db_session.refresh(sample_order)
    assert sample_order.status == OrderStatus.OUT_FOR_DELIVERY
    assert sample_order.picked_up_at is not None

@pytest.mark.asyncio
async def test_driver_confirm_delivery(db_session: AsyncSession, merchant_id: uuid.UUID,
                                         sample_driver: Driver, sample_order: Order):
    service = DriverTrackingService(db_session)

    # Setup
    sample_order.driver_id = sample_driver.id
    sample_order.status = OrderStatus.OUT_FOR_DELIVERY
    sample_driver.status = "en_route_delivery"
    await db_session.flush()

    request = DriverDeliveryConfirm(
        order_id=sample_order.id,
        driver_id=sample_driver.id,
        delivered_at=datetime.utcnow(),
        delivered_to="Customer at door",
        notes="Left at reception"
    )

    result = await service.confirm_delivery(merchant_id, request)
    assert result is not None

    await db_session.refresh(sample_order)
    assert sample_order.status == OrderStatus.DELIVERED
    assert sample_order.delivered_at is not None

    await db_session.refresh(sample_driver)
    assert sample_driver.status == "available"
    assert sample_driver.current_order_id is None

@pytest.mark.asyncio
async def test_fleet_map(db_session: AsyncSession, merchant_id: uuid.UUID, sample_driver: Driver):
    service = DriverTrackingService(db_session)
    fleet = await service.get_fleet_map(merchant_id)

    assert fleet.merchant_id == merchant_id
    assert len(fleet.drivers) >= 1
    assert fleet.total_drivers_online >= 1
    assert fleet.updated_at is not None

@pytest.mark.asyncio
async def test_driver_eta_calculation(db_session: AsyncSession, merchant_id: uuid.UUID, sample_driver: Driver):
    service = DriverTrackingService(db_session)

    # Create order with delivery address
    order = Order(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        order_number="DEL-001",
        status=OrderStatus.OUT_FOR_DELIVERY,
        order_type=OrderTypeEnum.delivery,
        payment_method="cod",
        total=Decimal("30.00"),
        subtotal=Decimal("30.00"),
        delivery_address={"lat": 26.2400, "lng": 50.6000, "formatted": "Test Address"},
        created_at=datetime.utcnow()
    )
    db_session.add(order)
    await db_session.flush()

    eta = service._calculate_eta(sample_driver, order)
    assert eta is not None
    assert eta > 0
    assert eta >= 60  # Minimum 1 minute

# ─── INTEGRATION TESTS ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_order_kds_broadcast(db_session: AsyncSession, merchant_id: uuid.UUID, sample_order: Order):
    """Test that order status changes trigger KDS broadcasts."""
    kds_service = KDSService(db_session)

    # Broadcast new order
    await kds_service.broadcast_new_order(sample_order)

    # Update status and broadcast
    sample_order.status = OrderStatus.READY
    await db_session.flush()
    await kds_service.broadcast_order_update(sample_order, "status_change")

    # Verify KDS representation
    kds = await kds_service.order_to_kds(sample_order)
    assert kds.status == KDSOrderStatus.READY

@pytest.mark.asyncio
async def test_ws_room_helpers():
    """Test room name generation."""
    assert ConnectionManager.kds_room("merch-123") == "kds:merch-123"
    assert ConnectionManager.kds_room("merch-123", "branch-456") == "kds:merch-123:branch-456"
    assert ConnectionManager.driver_room("driver-789") == "driver:driver-789"
    assert ConnectionManager.fleet_room("merch-123") == "fleet:merch-123"
    assert ConnectionManager.order_room("order-abc") == "order:order-abc"
    assert ConnectionManager.merchant_room("merch-123") == "merchant:merch-123"

@pytest.mark.asyncio
async def test_connection_stats():
    manager = ConnectionManager()

    ws1 = AsyncMock(spec=WebSocket)
    ws2 = AsyncMock(spec=WebSocket)
    ws3 = AsyncMock(spec=WebSocket)

    await manager.connect(ws1, "merch-a", "conn-1", "kds")
    await manager.connect(ws2, "merch-a", "conn-2", "merchant")
    await manager.connect(ws3, "merch-b", "conn-3", "kds")

    stats = manager.get_stats()
    assert stats["total_connections"] == 3
    assert stats["total_rooms"] == 0  # No rooms subscribed yet
    assert stats["by_merchant"]["merch-a"] == 2
    assert stats["by_merchant"]["merch-b"] == 1

    merch_stats = manager.get_stats("merch-a")
    assert merch_stats["total_connections"] == 2
