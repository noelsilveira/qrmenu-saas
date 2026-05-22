import pytest
from uuid import UUID
from decimal import Decimal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _setup_merchant_and_login(client):
    tenant_resp = await client.post("/api/v1/auth/register/tenant", json={
        "name": "Phase6 Tenant",
        "slug": "phase6tenant"
    })
    assert tenant_resp.status_code == 201
    tenant_id = tenant_resp.json()["id"]

    merchant_resp = await client.post(f"/api/v1/auth/register/merchant?tenant_id={tenant_id}", json={
        "business_name": "Phase6 Merchant",
        "slug": "phase6merchant",
        "currency": "BHD",
        "timezone": "Asia/Bahrain"
    })
    assert merchant_resp.status_code == 201
    merchant_id = merchant_resp.json()["id"]

    owner_resp = await client.post(f"/api/v1/auth/register/owner?merchant_id={merchant_id}", json={
        "email": "phase6@test.com",
        "password": "password123",
        "first_name": "Phase",
        "last_name": "Six"
    })
    assert owner_resp.status_code == 201

    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "phase6@test.com",
        "password": "password123"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return token, merchant_id


# ---------------------------------------------------------------------------
# Delivery Zone Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_and_list_zones(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create zone
    resp = await client.post("/api/v1/delivery/zones", json={
        "name": "Manama Central",
        "boundaries": [
            {"lat": 26.21, "lng": 50.58},
            {"lat": 26.22, "lng": 50.58},
            {"lat": 26.22, "lng": 50.59},
            {"lat": 26.21, "lng": 50.59},
        ],
        "base_fee": "1.500",
        "per_km_fee": "0.500",
        "min_order_value": "5.000",
        "max_delivery_distance_km": "15.0",
        "estimated_delivery_min": 30,
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Manama Central"
    assert float(data["base_fee"]) == 1.5
    zone_id = data["id"]

    # List zones
    list_resp = await client.get("/api/v1/delivery/zones", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    zones = list_resp.json()
    assert any(z["id"] == zone_id for z in zones)


@pytest.mark.asyncio
async def test_zone_match_inside(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create zone (square around Manama)
    await client.post("/api/v1/delivery/zones", json={
        "name": "Manama",
        "boundaries": [
            {"lat": 26.20, "lng": 50.57},
            {"lat": 26.25, "lng": 50.57},
            {"lat": 26.25, "lng": 50.62},
            {"lat": 26.20, "lng": 50.62},
        ],
        "base_fee": "1.000",
        "per_km_fee": "0.300",
        "min_order_value": "3.000",
    }, headers={"Authorization": f"Bearer {token}"})

    # Match point inside zone
    resp = await client.post("/api/v1/delivery/zones/match", json={
        "lat": 26.22,
        "lng": 50.59,
        "order_value": "10.000",
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["deliverable"] is True
    assert data["zone_name"] == "Manama"
    assert float(data["base_fee"]) >= 0


@pytest.mark.asyncio
async def test_zone_match_outside(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create zone
    await client.post("/api/v1/delivery/zones", json={
        "name": "Manama",
        "boundaries": [
            {"lat": 26.20, "lng": 50.57},
            {"lat": 26.25, "lng": 50.57},
            {"lat": 26.25, "lng": 50.62},
            {"lat": 26.20, "lng": 50.62},
        ],
        "base_fee": "1.000",
    }, headers={"Authorization": f"Bearer {token}"})

    # Match point far outside
    resp = await client.post("/api/v1/delivery/zones/match", json={
        "lat": 26.50,
        "lng": 50.80,
        "order_value": "10.000",
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["deliverable"] is False


# ---------------------------------------------------------------------------
# Driver Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_and_list_drivers(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    resp = await client.post("/api/v1/delivery/drivers", json={
        "name": "Ali Ahmed",
        "phone": "+97312345678",
        "email": "ali@test.com",
        "vehicle_type": "motorcycle",
        "vehicle_plate": "12345",
        "max_orders_per_run": 3,
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Ali Ahmed"
    assert data["status"] == "available"
    driver_id = data["id"]

    # List
    list_resp = await client.get("/api/v1/delivery/drivers", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    drivers = list_resp.json()
    assert any(d["id"] == driver_id for d in drivers)


@pytest.mark.asyncio
async def test_driver_location_update(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create driver
    resp = await client.post("/api/v1/delivery/drivers", json={
        "name": "Ali Ahmed",
        "phone": "+97312345678",
    }, headers={"Authorization": f"Bearer {token}"})
    driver_id = resp.json()["id"]

    # Update location
    loc_resp = await client.post(f"/api/v1/delivery/drivers/{driver_id}/location", json={
        "lat": 26.22,
        "lng": 50.59,
        "accuracy": 5.0,
        "heading": 90.0,
        "speed": 30.0,
    }, headers={"Authorization": f"Bearer {token}"})

    assert loc_resp.status_code == 200
    assert loc_resp.json()["status"] == "ok"

    # Get location
    get_resp = await client.get(f"/api/v1/delivery/drivers/{driver_id}/location", headers={"Authorization": f"Bearer {token}"})
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["lat"] == 26.22
    assert data["lng"] == 50.59


@pytest.mark.asyncio
async def test_driver_status_update(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    resp = await client.post("/api/v1/delivery/drivers", json={
        "name": "Ali Ahmed",
        "phone": "+97312345678",
    }, headers={"Authorization": f"Bearer {token}"})
    driver_id = resp.json()["id"]

    # Set offline
    status_resp = await client.post(f"/api/v1/delivery/drivers/{driver_id}/status?status=offline", headers={"Authorization": f"Bearer {token}"})
    assert status_resp.status_code == 200
    assert status_resp.json()["driver_status"] == "offline"

    # Set available
    status_resp = await client.post(f"/api/v1/delivery/drivers/{driver_id}/status?status=available", headers={"Authorization": f"Bearer {token}"})
    assert status_resp.status_code == 200
    assert status_resp.json()["driver_status"] == "available"


# ---------------------------------------------------------------------------
# Fleet Dashboard
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fleet_status(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create 2 drivers
    for name in ["Driver A", "Driver B"]:
        await client.post("/api/v1/delivery/drivers", json={
            "name": name,
            "phone": f"+9731234567{name[-1]}",
        }, headers={"Authorization": f"Bearer {token}"})

    resp = await client.get("/api/v1/delivery/fleet/status", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_drivers"] == 2
    assert data["available_drivers"] >= 0


# ---------------------------------------------------------------------------
# Delivery Assignment Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manual_assignment(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create driver
    driver_resp = await client.post("/api/v1/delivery/drivers", json={
        "name": "Ali Ahmed",
        "phone": "+97312345678",
    }, headers={"Authorization": f"Bearer {token}"})
    driver_id = driver_resp.json()["id"]

    # Create order (need category + item + table + checkout)
    cat_resp = await client.post("/api/v1/menu/categories", json={
        "name": "Test", "sort_order": 1,
    }, headers={"Authorization": f"Bearer {token}"})
    cat_id = cat_resp.json()["id"]

    item_resp = await client.post("/api/v1/menu/items", json={
        "name": "Burger", "price": "4.500", "category_id": cat_id,
    }, headers={"Authorization": f"Bearer {token}"})
    item_id = item_resp.json()["id"]

    table_resp = await client.post("/api/v1/tables", json={
        "table_number": "1", "seating_capacity": 2,
    }, headers={"Authorization": f"Bearer {token}"})
    table = table_resp.json()
    session_token = table["qr_token"]

    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id, "quantity": 1,
    })

    checkout_resp = await client.post(f"/api/v1/orders/checkout?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "customer_phone": "+97312345678",
        "order_type": "delivery",
        "payment_method": "cod",
        "delivery_address": {"lat": 26.22, "lng": 50.59, "text": "Manama, Block 123"},
    })
    order_id = checkout_resp.json()["order_id"]

    # Assign driver
    assign_resp = await client.post("/api/v1/delivery/assignments", json={
        "order_id": order_id,
        "driver_id": driver_id,
        "delivery_address": {"lat": 26.22, "lng": 50.59, "text": "Manama"},
    }, headers={"Authorization": f"Bearer {token}"})

    assert assign_resp.status_code == 201
    data = assign_resp.json()
    assert data["order_id"] == order_id
    assert data["driver_id"] == driver_id
    assert data["status"] == "assigned"


@pytest.mark.asyncio
async def test_assignment_status_workflow(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Setup driver + order
    driver_resp = await client.post("/api/v1/delivery/drivers", json={
        "name": "Ali", "phone": "+97312345678",
    }, headers={"Authorization": f"Bearer {token}"})
    driver_id = driver_resp.json()["id"]

    cat_resp = await client.post("/api/v1/menu/categories", json={"name": "Test", "sort_order": 1}, headers={"Authorization": f"Bearer {token}"})
    item_resp = await client.post("/api/v1/menu/items", json={"name": "Burger", "price": "4.500", "category_id": cat_resp.json()["id"]}, headers={"Authorization": f"Bearer {token}"})
    table_resp = await client.post("/api/v1/tables", json={"table_number": "1", "seating_capacity": 2}, headers={"Authorization": f"Bearer {token}"})
    table = table_resp.json()

    await client.post(f"/api/v1/cart/add?session_token={table['qr_token']}&merchant_id={merchant_id}&table_id={table['id']}", json={"item_id": item_resp.json()["id"], "quantity": 1})
    checkout = await client.post(f"/api/v1/orders/checkout?session_token={table['qr_token']}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "customer_phone": "+97312345678", "order_type": "delivery", "payment_method": "cod",
        "delivery_address": {"lat": 26.22, "lng": 50.59},
    })
    order_id = checkout.json()["order_id"]

    # Create assignment
    assign = await client.post("/api/v1/delivery/assignments", json={
        "order_id": order_id, "driver_id": driver_id,
        "delivery_address": {"lat": 26.22, "lng": 50.59},
    }, headers={"Authorization": f"Bearer {token}"})
    assignment_id = assign.json()["id"]

    # PICKED_UP
    resp = await client.put(f"/api/v1/delivery/assignments/{assignment_id}/status", json={
        "status": "picked_up", "lat": 26.21, "lng": 50.58,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["status"] == "picked_up"

    # EN_ROUTE
    resp = await client.put(f"/api/v1/delivery/assignments/{assignment_id}/status", json={
        "status": "en_route", "lat": 26.215, "lng": 50.585,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["status"] == "en_route"

    # DELIVERED
    resp = await client.put(f"/api/v1/delivery/assignments/{assignment_id}/status", json={
        "status": "delivered", "lat": 26.22, "lng": 50.59,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["status"] == "delivered"
    assert resp.json()["actual_delivery_at"] is not None

    # Driver should be available again
    driver = await client.get(f"/api/v1/delivery/drivers/{driver_id}", headers={"Authorization": f"Bearer {token}"})
    assert driver.json()["status"] == "available"


@pytest.mark.asyncio
async def test_delivery_tracking(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Setup
    driver_resp = await client.post("/api/v1/delivery/drivers", json={"name": "Ali", "phone": "+97312345678"}, headers={"Authorization": f"Bearer {token}"})
    driver_id = driver_resp.json()["id"]

    cat_resp = await client.post("/api/v1/menu/categories", json={"name": "Test", "sort_order": 1}, headers={"Authorization": f"Bearer {token}"})
    item_resp = await client.post("/api/v1/menu/items", json={"name": "Burger", "price": "4.500", "category_id": cat_resp.json()["id"]}, headers={"Authorization": f"Bearer {token}"})
    table_resp = await client.post("/api/v1/tables", json={"table_number": "1", "seating_capacity": 2}, headers={"Authorization": f"Bearer {token}"})
    table = table_resp.json()

    await client.post(f"/api/v1/cart/add?session_token={table['qr_token']}&merchant_id={merchant_id}&table_id={table['id']}", json={"item_id": item_resp.json()["id"], "quantity": 1})
    checkout = await client.post(f"/api/v1/orders/checkout?session_token={table['qr_token']}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "customer_phone": "+97312345678", "order_type": "delivery", "payment_method": "cod",
        "delivery_address": {"lat": 26.22, "lng": 50.59, "text": "Manama Tower"},
    })
    order_id = checkout.json()["order_id"]

    assign = await client.post("/api/v1/delivery/assignments", json={
        "order_id": order_id, "driver_id": driver_id,
        "delivery_address": {"lat": 26.22, "lng": 50.59, "text": "Manama Tower"},
    }, headers={"Authorization": f"Bearer {token}"})
    assignment_id = assign.json()["id"]

    # Update status with location
    await client.put(f"/api/v1/delivery/assignments/{assignment_id}/status", json={
        "status": "en_route", "lat": 26.215, "lng": 50.585,
    }, headers={"Authorization": f"Bearer {token}"})

    # Get tracking
    resp = await client.get(f"/api/v1/delivery/assignments/{assignment_id}/tracking", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["delivery_id"] == assignment_id
    assert data["driver_name"] == "Ali"
    assert data["status"] == "en_route"
    assert data["customer_address"]["text"] == "Manama Tower"
