import pytest
from uuid import UUID
from decimal import Decimal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _setup_merchant_and_login(client):
    """Helper to create tenant, merchant, owner and login."""
    tenant_resp = await client.post("/api/v1/auth/register/tenant", json={
        "name": "Phase4 Tenant",
        "slug": "phase4tenant"
    })
    assert tenant_resp.status_code == 201
    tenant_id = tenant_resp.json()["id"]

    merchant_resp = await client.post(f"/api/v1/auth/register/merchant?tenant_id={tenant_id}", json={
        "business_name": "Phase4 Merchant",
        "slug": "phase4merchant",
        "currency": "BHD",
        "timezone": "Asia/Bahrain"
    })
    assert merchant_resp.status_code == 201
    merchant_id = merchant_resp.json()["id"]

    owner_resp = await client.post(f"/api/v1/auth/register/owner?merchant_id={merchant_id}", json={
        "email": "phase4@test.com",
        "password": "password123",
        "first_name": "Phase",
        "last_name": "Four"
    })
    assert owner_resp.status_code == 201

    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "phase4@test.com",
        "password": "password123"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return token, merchant_id


async def _create_category_item(client, token, merchant_id):
    """Create a category and menu item for testing."""
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
    """Create a table with QR."""
    table_resp = await client.post("/api/v1/tables", json={
        "table_number": "5",
        "seating_capacity": 4,
    }, headers={"Authorization": f"Bearer {token}"})
    return table_resp.json()


# ---------------------------------------------------------------------------
# Cart Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cart_add_item(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add item to cart
    resp = await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 2,
        "modifier_options": [],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == 2
    assert float(data["subtotal"]) == 9.0  # 4.5 * 2


@pytest.mark.asyncio
async def test_cart_update_quantity(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add item
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 1,
    })

    # Update quantity
    resp = await client.put(f"/api/v1/cart/item/{item_id}?session_token={session_token}", json={
        "quantity": 3,
    })
    assert resp.status_code == 200
    assert resp.json()["items"][0]["quantity"] == 3


@pytest.mark.asyncio
async def test_cart_remove_item(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add item
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 1,
    })

    # Remove item
    resp = await client.delete(f"/api/v1/cart/item/{item_id}?session_token={session_token}")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 0


@pytest.mark.asyncio
async def test_cart_clear(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add item
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 1,
    })

    # Clear cart
    resp = await client.delete(f"/api/v1/cart?session_token={session_token}")
    assert resp.status_code == 204

    # Verify empty
    get_resp = await client.get(f"/api/v1/cart?session_token={session_token}")
    assert get_resp.status_code == 404  # Cart not found after clear


# ---------------------------------------------------------------------------
# Checkout & Order Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_checkout_cod(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add to cart
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 2,
    })

    # Checkout COD
    resp = await client.post(f"/api/v1/orders/checkout?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "customer_phone": "+97312345678",
        "customer_name": "John Doe",
        "order_type": "dine_in",
        "payment_method": "cod",
        "notes": "Extra ketchup please",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["payment_method"] == "cod"
    assert data["payment_status"] == "pending"
    assert float(data["total"]) > 0
    order_id = data["order_id"]

    # Verify cart cleared
    cart_resp = await client.get(f"/api/v1/cart?session_token={session_token}")
    assert cart_resp.status_code == 404

    # Merchant can view order
    merchant_resp = await client.get(f"/api/v1/orders/merchant/{order_id}", headers={"Authorization": f"Bearer {token}"})
    assert merchant_resp.status_code == 200
    assert merchant_resp.json()["customer_phone"] == "+97312345678"


@pytest.mark.asyncio
async def test_order_status_workflow(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add to cart
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 2,
    })

    # Checkout
    checkout_resp = await client.post(f"/api/v1/orders/checkout?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "customer_phone": "+97312345678",
        "order_type": "dine_in",
        "payment_method": "cod",
    })
    order_id = checkout_resp.json()["order_id"]

    # Confirm COD
    await client.post(f"/api/v1/payments/cod/{order_id}/confirm", headers={"Authorization": f"Bearer {token}"})

    # Update to PREPARING
    resp = await client.put(f"/api/v1/orders/merchant/{order_id}/status", json={
        "status": "preparing",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "preparing"

    # Update to READY
    resp = await client.put(f"/api/v1/orders/merchant/{order_id}/status", json={
        "status": "ready",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"

    # Update to SERVED
    resp = await client.put(f"/api/v1/orders/merchant/{order_id}/status", json={
        "status": "served",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "served"
    assert resp.json()["served_at"] is not None


@pytest.mark.asyncio
async def test_invalid_status_transition(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add to cart
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 2,
    })

    # Checkout
    checkout_resp = await client.post(f"/api/v1/orders/checkout?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "customer_phone": "+97312345678",
        "order_type": "dine_in",
        "payment_method": "cod",
    })
    order_id = checkout_resp.json()["order_id"]

    # Try to jump PENDING → SERVED (invalid)
    resp = await client.put(f"/api/v1/orders/merchant/{order_id}/status", json={
        "status": "served",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400
    assert "Cannot transition" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_order(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add to cart
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 2,
    })

    # Checkout
    checkout_resp = await client.post(f"/api/v1/orders/checkout?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "customer_phone": "+97312345678",
        "order_type": "dine_in",
        "payment_method": "cod",
    })
    order_id = checkout_resp.json()["order_id"]

    # Cancel
    resp = await client.post(f"/api/v1/orders/merchant/{order_id}/cancel?reason=Customer request", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_list_orders_filter(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add to cart
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 2,
    })

    # Create 2 orders
    for i in range(2):
        await client.post(f"/api/v1/orders/checkout?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
            "customer_phone": "+97312345678",
            "order_type": "dine_in",
            "payment_method": "cod",
        })
        # Re-add to cart for next checkout (cart is cleared after each checkout)
        if i == 0:
            await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
                "item_id": item_id,
                "quantity": 2,
            })

    # List all
    resp = await client.get("/api/v1/orders/merchant", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2

    # Filter by status
    resp = await client.get("/api/v1/orders/merchant?status=pending", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert all(o["status"] == "pending" for o in resp.json()["orders"])


# ---------------------------------------------------------------------------
# Customer Order Tracking
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_customer_track_order(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add to cart
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 2,
    })

    # Checkout
    checkout_resp = await client.post(f"/api/v1/orders/checkout?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "customer_phone": "+97312345678",
        "order_type": "dine_in",
        "payment_method": "cod",
    })
    order_id = checkout_resp.json()["order_id"]

    # Customer tracks order
    resp = await client.get(f"/api/v1/orders/customer/{order_id}?session_token={session_token}")
    assert resp.status_code == 200
    assert resp.json()["id"] == order_id


# ---------------------------------------------------------------------------
# Payment Intent (Stripe/PayPal structure)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_payment_intent_structure(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add to cart
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 2,
    })

    # Checkout with Stripe
    checkout_resp = await client.post(f"/api/v1/orders/checkout?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "customer_phone": "+97312345678",
        "order_type": "dine_in",
        "payment_method": "stripe",
    })
    assert checkout_resp.status_code == 201
    data = checkout_resp.json()
    assert data["payment_method"] == "stripe"
    # Without real Stripe key, client_secret may be None but structure is correct
    assert "client_secret" in data


# ---------------------------------------------------------------------------
# Bulk Status Update
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bulk_status_update(client):
    token, merchant_id = await _setup_merchant_and_login(client)
    _, item_id = await _create_category_item(client, token, merchant_id)
    table = await _create_table(client, token)
    session_token = table["qr_token"]

    # Add to cart
    await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
        "item_id": item_id,
        "quantity": 2,
    })

    # Create 2 orders
    order_ids = []
    for i in range(2):
        resp = await client.post(f"/api/v1/orders/checkout?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
            "customer_phone": "+97312345678",
            "order_type": "dine_in",
            "payment_method": "cod",
        })
        order_ids.append(resp.json()["order_id"])
        # Re-add to cart for next checkout (cart is cleared after each checkout)
        if i == 0:
            await client.post(f"/api/v1/cart/add?session_token={session_token}&merchant_id={merchant_id}&table_id={table['id']}", json={
                "item_id": item_id,
                "quantity": 2,
            })

    # Confirm COD for both
    for oid in order_ids:
        await client.post(f"/api/v1/payments/cod/{oid}/confirm", headers={"Authorization": f"Bearer {token}"})

    # Bulk update to preparing
    resp = await client.post("/api/v1/orders/merchant/bulk-status", json={
        "order_ids": order_ids,
        "status": "preparing",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert all(o["status"] == "preparing" for o in resp.json())
