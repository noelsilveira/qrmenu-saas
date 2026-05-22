import pytest
from uuid import UUID
from decimal import Decimal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _setup_merchant_and_login(client):
    tenant_resp = await client.post("/api/v1/auth/register/tenant", json={
        "name": "Phase7 Tenant",
        "slug": "phase7tenant"
    })
    assert tenant_resp.status_code == 201
    tenant_id = tenant_resp.json()["id"]

    merchant_resp = await client.post(f"/api/v1/auth/register/merchant?tenant_id={tenant_id}", json={
        "business_name": "Phase7 Merchant",
        "slug": "phase7merchant",
        "currency": "BHD",
        "timezone": "Asia/Bahrain"
    })
    assert merchant_resp.status_code == 201
    merchant_id = merchant_resp.json()["id"]

    owner_resp = await client.post(f"/api/v1/auth/register/owner?merchant_id={merchant_id}", json={
        "email": "phase7@test.com",
        "password": "password123",
        "first_name": "Phase",
        "last_name": "Seven"
    })
    assert owner_resp.status_code == 201

    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "phase7@test.com",
        "password": "password123"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return token, merchant_id


# ---------------------------------------------------------------------------
# Platform Connection Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_connection(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    resp = await client.post("/api/v1/third-party/connections", json={
        "platform": "talabat",
        "merchant_ref": "talabat_12345",
        "api_key": "test_key_123",
        "api_secret": "test_secret_456",
        "webhook_secret": "wh_secret_789",
        "branch_id": "branch_001",
        "is_active": True,
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["platform"] == "talabat"
    assert data["merchant_ref"] == "talabat_12345"
    assert data["status"] == "active"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_connections(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create 2 connections
    for platform in ["talabat", "zomato"]:
        await client.post("/api/v1/third-party/connections", json={
            "platform": platform,
            "merchant_ref": f"{platform}_ref",
            "is_active": True,
        }, headers={"Authorization": f"Bearer {token}"})

    resp = await client.get("/api/v1/third-party/connections", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    connections = resp.json()
    assert len(connections) == 2
    assert any(c["platform"] == "talabat" for c in connections)
    assert any(c["platform"] == "zomato" for c in connections)


@pytest.mark.asyncio
async def test_update_connection(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    create_resp = await client.post("/api/v1/third-party/connections", json={
        "platform": "talabat",
        "merchant_ref": "old_ref",
        "is_active": True,
    }, headers={"Authorization": f"Bearer {token}"})
    conn_id = create_resp.json()["id"]

    resp = await client.put(f"/api/v1/third-party/connections/{conn_id}", json={
        "merchant_ref": "new_ref",
        "is_active": False,
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["merchant_ref"] == "new_ref"
    assert data["is_active"] is False


# ---------------------------------------------------------------------------
# Order Ingestion Webhook Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_talabat_webhook_ingest(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create connection
    await client.post("/api/v1/third-party/connections", json={
        "platform": "talabat",
        "merchant_ref": "rest_123",
        "is_active": True,
    }, headers={"Authorization": f"Bearer {token}"})

    # Send Talabat order webhook
    webhook_payload = {
        "order": {
            "order_id": "TAL-12345",
            "restaurant_id": "rest_123",
            "customer": {
                "name": "John Doe",
                "phone": "+97312345678"
            },
            "items": [
                {"id": "item_1", "name": "Chicken Burger", "quantity": 2, "unit_price": 3.5, "total_price": 7.0}
            ],
            "subtotal": 7.0,
            "tax": 0.7,
            "delivery_fee": 1.0,
            "discount": 0,
            "total": 8.7,
            "currency": "BHD",
            "payment_method": "online",
            "payment_status": "paid",
            "delivery_address": {"lat": 26.22, "lng": 50.59, "text": "Manama"},
            "estimated_ready_min": 25,
        }
    }

    resp = await client.post("/api/v1/third-party/webhook/talabat", json=webhook_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert data["status"] == "created"
    assert data["external_order_id"] == "TAL-12345"
    assert data["platform"] == "talabat"


@pytest.mark.asyncio
async def test_zomato_webhook_ingest(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    await client.post("/api/v1/third-party/connections", json={
        "platform": "zomato",
        "merchant_ref": "zom_456",
        "is_active": True,
    }, headers={"Authorization": f"Bearer {token}"})

    webhook_payload = {
        "order": {
            "order_id": "ZOM-67890",
            "restaurant": {"id": "zom_456"},
            "user": {"name": "Jane Doe", "phone": "+97387654321"},
            "items": [
                {"item_id": "i1", "item_name": "Falafel Wrap", "quantity": 1, "price": 2.5, "addons": []}
            ],
            "subtotal": 2.5,
            "taxes": 0.25,
            "delivery_charges": 0.5,
            "discount_total": 0,
            "order_total": 3.25,
            "currency": "BHD",
            "payment_mode": "online",
            "is_paid": True,
            "delivery_address": {"lat": 26.23, "lng": 50.60},
        }
    }

    resp = await client.post("/api/v1/third-party/webhook/zomato", json=webhook_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert data["platform"] == "zomato"


@pytest.mark.asyncio
async def test_jahez_webhook_ingest(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    await client.post("/api/v1/third-party/connections", json={
        "platform": "jahez",
        "merchant_ref": "jah_789",
        "branch_id": "branch_99",
        "is_active": True,
    }, headers={"Authorization": f"Bearer {token}"})

    webhook_payload = {
        "data": {
            "order": {
                "order_number": "JAH-11111",
                "branch_id": "branch_99",
                "customer": {"name": "Ahmed", "mobile": "+97311112222"},
                "items": [
                    {"product_id": "p1", "product_name": "Shawarma", "quantity": 1, "unit_price": 1.5, "total_price": 1.5, "options": []}
                ],
                "sub_total": 1.5,
                "vat_amount": 0.075,
                "delivery_fee": 0.5,
                "discount_amount": 0,
                "grand_total": 2.075,
                "payment_type": "online",
                "is_paid": True,
                "address": {"lat": 26.24, "lng": 50.61},
                "preparation_time": 20,
            }
        }
    }

    resp = await client.post("/api/v1/third-party/webhook/jahez", json=webhook_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert data["platform"] == "jahez"


@pytest.mark.asyncio
async def test_webhook_duplicate_order(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    await client.post("/api/v1/third-party/connections", json={
        "platform": "talabat",
        "merchant_ref": "rest_dup",
        "is_active": True,
    }, headers={"Authorization": f"Bearer {token}"})

    webhook_payload = {
        "order": {
            "order_id": "TAL-DUP-001",
            "restaurant_id": "rest_dup",
            "customer": {"name": "Test", "phone": "+97300000000"},
            "items": [{"id": "i1", "name": "Item", "quantity": 1, "unit_price": 1, "total_price": 1}],
            "subtotal": 1,
            "tax": 0,
            "delivery_fee": 0,
            "total": 1,
            "currency": "BHD",
        }
    }

    # First ingest
    resp1 = await client.post("/api/v1/third-party/webhook/talabat", json=webhook_payload)
    assert resp1.json()["accepted"] is True

    # Duplicate should be rejected
    resp2 = await client.post("/api/v1/third-party/webhook/talabat", json=webhook_payload)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "duplicate"
    assert resp2.json()["accepted"] is False


# ---------------------------------------------------------------------------
# Menu Sync Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_menu_sync(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create category + items
    cat_resp = await client.post("/api/v1/menu/categories", json={
        "name": "Burgers", "sort_order": 1,
    }, headers={"Authorization": f"Bearer {token}"})
    cat_id = cat_resp.json()["id"]

    await client.post("/api/v1/menu/items", json={
        "name": "Classic Burger", "price": "3.500", "category_id": cat_id,
    }, headers={"Authorization": f"Bearer {token}"})

    # Create connection
    conn_resp = await client.post("/api/v1/third-party/connections", json={
        "platform": "talabat",
        "merchant_ref": "rest_sync",
        "is_active": True,
    }, headers={"Authorization": f"Bearer {token}"})
    conn_id = conn_resp.json()["id"]

    resp = await client.post("/api/v1/third-party/sync/menu", json={
        "platform": "talabat",
        "connection_id": conn_id,
        "sync_type": "full",
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["items_synced"] >= 1
    assert data["categories_synced"] >= 1


# ---------------------------------------------------------------------------
# Fallback Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fallback_config(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    resp = await client.get("/api/v1/third-party/fallback/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["max_retry_attempts"] == 3
    assert data["fallback_to_own_delivery"] is True


@pytest.mark.asyncio
async def test_trigger_fallback(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create an order first
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

    resp = await client.post(f"/api/v1/third-party/fallback/{order_id}?platform=talabat&error=API timeout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["order_id"] == order_id
    assert data["platform"] == "talabat"
    assert data["action"] in ["retry", "fallback_own", "fallback_manual"]
