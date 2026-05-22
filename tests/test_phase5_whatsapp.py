import pytest
from uuid import UUID
from decimal import Decimal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _setup_merchant_and_login(client):
    tenant_resp = await client.post("/api/v1/auth/register/tenant", json={
        "name": "Phase5 Tenant",
        "slug": "phase5tenant"
    })
    assert tenant_resp.status_code == 201
    tenant_id = tenant_resp.json()["id"]

    merchant_resp = await client.post(f"/api/v1/auth/register/merchant?tenant_id={tenant_id}", json={
        "business_name": "Phase5 Merchant",
        "slug": "phase5merchant",
        "currency": "BHD",
        "timezone": "Asia/Bahrain"
    })
    assert merchant_resp.status_code == 201
    merchant_id = merchant_resp.json()["id"]

    owner_resp = await client.post(f"/api/v1/auth/register/owner?merchant_id={merchant_id}", json={
        "email": "phase5@test.com",
        "password": "password123",
        "first_name": "Phase",
        "last_name": "Five"
    })
    assert owner_resp.status_code == 201

    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "phase5@test.com",
        "password": "password123"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return token, merchant_id


async def _create_category_item(client, token, merchant_id):
    cat_resp = await client.post("/api/v1/menu/categories", json={
        "name": "Test Category",
        "sort_order": 1,
    }, headers={"Authorization": f"Bearer {token}"})
    cat_id = cat_resp.json()["id"]

    item_resp = await client.post("/api/v1/menu/items", json={
        "name": "Test Burger",
        "description": "A tasty burger",
        "price": "4.500",
        "category_id": cat_id,
        "prep_time_min": 10,
    }, headers={"Authorization": f"Bearer {token}"})
    item_id = item_resp.json()["id"]
    return cat_id, item_id


async def _create_table(client, token):
    table_resp = await client.post("/api/v1/tables", json={
        "table_number": "5",
        "seating_capacity": 4,
    }, headers={"Authorization": f"Bearer {token}"})
    return table_resp.json()


async def _checkout_order(client, token, merchant_id, item_id, table):
    session_token = table["qr_token"]
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 2,
    })

    checkout_resp = await client.post(f"/api/v1/orders/checkout?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "customer_phone": "+97312345678",
        "customer_name": "John Doe",
        "order_type": "dine_in",
        "payment_method": "cod",
    })
    assert checkout_resp.status_code == 201
    return checkout_resp.json()["order_id"]


# ---------------------------------------------------------------------------
# Acceptance Request Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_acceptance(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    order_id = await _checkout_order(client, token, merchant_id, item_id, table)

    # Request acceptance
    resp = await client.post("/api/v1/whatsapp/acceptance/request", json={
        "order_id": order_id,
        "timeout_minutes": 5,
        "notify_channels": ["whatsapp"],
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["order_id"] == order_id
    assert data["acceptance_status"] == "pending"
    assert data["timeout_at"] is not None
    assert data["message_id"] is not None


@pytest.mark.asyncio
async def test_get_acceptance_status(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    order_id = await _checkout_order(client, token, merchant_id, item_id, table)

    # Request acceptance
    await client.post("/api/v1/whatsapp/acceptance/request", json={
        "order_id": order_id,
        "timeout_minutes": 5,
    }, headers={"Authorization": f"Bearer {token}"})

    # Get status
    resp = await client.get(f"/api/v1/whatsapp/acceptance/{order_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["time_remaining_seconds"] is not None
    assert data["is_expired"] is False


@pytest.mark.asyncio
async def test_manual_accept_order(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    order_id = await _checkout_order(client, token, merchant_id, item_id, table)

    # Request acceptance
    await client.post("/api/v1/whatsapp/acceptance/request", json={
        "order_id": order_id,
        "timeout_minutes": 5,
    }, headers={"Authorization": f"Bearer {token}"})

    # Merchant accepts via portal
    resp = await client.post("/api/v1/whatsapp/acceptance/respond", json={
        "order_id": order_id,
        "action": "accept",
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "accept"
    assert data["new_status"] == "accepted"
    assert data["order_status"] == "confirmed"

    # Verify order status updated
    order_resp = await client.get(f"/api/v1/orders/merchant/{order_id}", headers={"Authorization": f"Bearer {token}"})
    assert order_resp.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_manual_reject_order(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    order_id = await _checkout_order(client, token, merchant_id, item_id, table)

    # Request acceptance
    await client.post("/api/v1/whatsapp/acceptance/request", json={
        "order_id": order_id,
        "timeout_minutes": 5,
    }, headers={"Authorization": f"Bearer {token}"})

    # Merchant rejects via portal
    resp = await client.post("/api/v1/whatsapp/acceptance/respond", json={
        "order_id": order_id,
        "action": "reject",
        "reason": "Out of stock",
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "reject"
    assert data["new_status"] == "rejected"
    assert data["order_status"] == "cancelled"

    # Verify order status updated
    order_resp = await client.get(f"/api/v1/orders/merchant/{order_id}", headers={"Authorization": f"Bearer {token}"})
    assert order_resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Webhook Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_webhook_accept_button(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    order_id = await _checkout_order(client, token, merchant_id, item_id, table)

    # Request acceptance
    await client.post("/api/v1/whatsapp/acceptance/request", json={
        "order_id": order_id,
        "timeout_minutes": 5,
    }, headers={"Authorization": f"Bearer {token}"})

    # Simulate WhatsApp button click webhook
    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "test_entry",
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "+97312345678",
                        "id": "test_msg_id",
                        "timestamp": "1234567890",
                        "type": "interactive",
                        "interactive": {
                            "type": "button_reply",
                            "button_reply": {
                                "id": f"accept:{order_id}",
                                "title": "Accept"
                            }
                        }
                    }]
                },
                "field": "messages"
            }]
        }]
    }

    resp = await client.post("/api/v1/whatsapp/webhook", json=webhook_payload)
    assert resp.status_code == 200

    # Verify order was accepted
    order_resp = await client.get(f"/api/v1/orders/merchant/{order_id}", headers={"Authorization": f"Bearer {token}"})
    assert order_resp.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_webhook_reject_button(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    order_id = await _checkout_order(client, token, merchant_id, item_id, table)

    # Request acceptance
    await client.post("/api/v1/whatsapp/acceptance/request", json={
        "order_id": order_id,
        "timeout_minutes": 5,
    }, headers={"Authorization": f"Bearer {token}"})

    # Simulate WhatsApp reject button click
    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "test_entry",
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "+97312345678",
                        "id": "test_msg_id",
                        "timestamp": "1234567890",
                        "type": "interactive",
                        "interactive": {
                            "type": "button_reply",
                            "button_reply": {
                                "id": f"reject:{order_id}",
                                "title": "Reject"
                            }
                        }
                    }]
                },
                "field": "messages"
            }]
        }]
    }

    resp = await client.post("/api/v1/whatsapp/webhook", json=webhook_payload)
    assert resp.status_code == 200

    # Verify order was rejected
    order_resp = await client.get(f"/api/v1/orders/merchant/{order_id}", headers={"Authorization": f"Bearer {token}"})
    assert order_resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Timeout Engine Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_timeout_config(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    resp = await client.get("/api/v1/whatsapp/timeout/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["timeout_minutes"] == 5
    assert data["fallback_action"] == "auto_reject"


@pytest.mark.asyncio
async def test_timeout_config_update(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    resp = await client.put("/api/v1/whatsapp/timeout/config", json={
        "enabled": True,
        "timeout_minutes": 10,
        "auto_reject_reason": "No response",
        "fallback_action": "auto_reject",
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["timeout_minutes"] == 10


# ---------------------------------------------------------------------------
# Customer Notification Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_customer_notification(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    order_id = await _checkout_order(client, token, merchant_id, item_id, table)

    resp = await client.post("/api/v1/whatsapp/customer/notify", json={
        "order_id": order_id,
        "customer_phone": "+97312345678",
        "notification_type": "order_ready",
        "message": "Your order is ready!",
        "language": "en",
    }, headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] is True
    assert data["channel"] == "whatsapp"
    assert data["message_id"] is not None
