import pytest
from uuid import UUID


async def _setup_merchant_and_login(client):
    """Helper to create tenant, merchant, owner and login."""
    tenant_resp = await client.post("/api/v1/auth/register/tenant", json={
        "name": "Phase3 Tenant",
        "slug": "phase3tenant"
    })
    assert tenant_resp.status_code == 201
    tenant_id = tenant_resp.json()["id"]

    merchant_resp = await client.post(f"/api/v1/auth/register/merchant?tenant_id={tenant_id}", json={
        "business_name": "Phase3 Merchant",
        "slug": "phase3merchant",
        "currency": "BHD",
        "timezone": "Asia/Bahrain"
    })
    assert merchant_resp.status_code == 201
    merchant_id = merchant_resp.json()["id"]

    owner_resp = await client.post(f"/api/v1/auth/register/owner?merchant_id={merchant_id}", json={
        "email": "phase3@test.com",
        "password": "password123",
        "first_name": "Phase",
        "last_name": "Three"
    })
    assert owner_resp.status_code == 201

    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "phase3@test.com",
        "password": "password123"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return token, merchant_id


# ---------------------------------------------------------------------------
# Menu Category Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_and_list_categories(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create category
    resp = await client.post("/api/v1/menu/categories", json={
        "name": "Burgers",
        "description": "Juicy burgers",
        "sort_order": 1,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Burgers"
    assert data["sort_order"] == 1
    cat_id = data["id"]

    # List categories
    list_resp = await client.get("/api/v1/menu/categories", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    cats = list_resp.json()
    assert len(cats) >= 1
    assert any(c["id"] == cat_id for c in cats)


@pytest.mark.asyncio
async def test_update_category(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    resp = await client.post("/api/v1/menu/categories", json={
        "name": "Drinks",
        "sort_order": 2,
    }, headers={"Authorization": f"Bearer {token}"})
    cat_id = resp.json()["id"]

    update_resp = await client.put(f"/api/v1/menu/categories/{cat_id}", json={
        "name": "Cold Drinks",
        "sort_order": 3,
    }, headers={"Authorization": f"Bearer {token}"})
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Cold Drinks"
    assert update_resp.json()["sort_order"] == 3


@pytest.mark.asyncio
async def test_delete_category_soft_delete(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    resp = await client.post("/api/v1/menu/categories", json={
        "name": "Desserts",
        "sort_order": 4,
    }, headers={"Authorization": f"Bearer {token}"})
    cat_id = resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/menu/categories/{cat_id}", headers={"Authorization": f"Bearer {token}"})
    assert del_resp.status_code == 204

    # Should not appear in list
    list_resp = await client.get("/api/v1/menu/categories", headers={"Authorization": f"Bearer {token}"})
    cats = list_resp.json()
    assert not any(c["id"] == cat_id for c in cats)


# ---------------------------------------------------------------------------
# Menu Item Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_and_list_items(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create category first
    cat_resp = await client.post("/api/v1/menu/categories", json={
        "name": "Mains",
        "sort_order": 1,
    }, headers={"Authorization": f"Bearer {token}"})
    cat_id = cat_resp.json()["id"]

    # Create item
    item_resp = await client.post("/api/v1/menu/items", json={
        "name": "Cheeseburger",
        "description": "Beef patty with cheese",
        "price": "3.500",
        "category_id": cat_id,
        "prep_time_min": 10,
    }, headers={"Authorization": f"Bearer {token}"})
    assert item_resp.status_code == 201
    data = item_resp.json()
    assert data["name"] == "Cheeseburger"
    assert float(data["price"]) == 3.5
    item_id = data["id"]

    # List items
    list_resp = await client.get("/api/v1/menu/items", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(i["id"] == item_id for i in items)

    # Filter by category
    filter_resp = await client.get(f"/api/v1/menu/items?category_id={cat_id}", headers={"Authorization": f"Bearer {token}"})
    assert filter_resp.status_code == 200
    assert all(i["category_id"] == cat_id for i in filter_resp.json())


@pytest.mark.asyncio
async def test_update_item_availability(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    item_resp = await client.post("/api/v1/menu/items", json={
        "name": "Fries",
        "price": "1.200",
    }, headers={"Authorization": f"Bearer {token}"})
    item_id = item_resp.json()["id"]
    assert item_resp.json()["is_available"] is True

    update_resp = await client.put(f"/api/v1/menu/items/{item_id}", json={
        "is_available": False,
    }, headers={"Authorization": f"Bearer {token}"})
    assert update_resp.status_code == 200
    assert update_resp.json()["is_available"] is False


@pytest.mark.asyncio
async def test_search_items(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    await client.post("/api/v1/menu/items", json={
        "name": "Classic Burger",
        "description": "A tasty beef burger",
        "price": "4.000",
    }, headers={"Authorization": f"Bearer {token}"})

    await client.post("/api/v1/menu/items", json={
        "name": "Vegan Salad",
        "description": "Fresh greens",
        "price": "2.500",
    }, headers={"Authorization": f"Bearer {token}"})

    search_resp = await client.get("/api/v1/menu/search?q=burger", headers={"Authorization": f"Bearer {token}"})
    assert search_resp.status_code == 200
    results = search_resp.json()
    assert any("Burger" in i["name"] for i in results)


# ---------------------------------------------------------------------------
# Public Menu
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_public_menu(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create category + item
    cat_resp = await client.post("/api/v1/menu/categories", json={
        "name": "Specials",
        "sort_order": 1,
    }, headers={"Authorization": f"Bearer {token}"})
    cat_id = cat_resp.json()["id"]

    await client.post("/api/v1/menu/items", json={
        "name": "Daily Special",
        "price": "5.000",
        "category_id": cat_id,
    }, headers={"Authorization": f"Bearer {token}"})

    public_resp = await client.get("/api/v1/menu/public/phase3merchant")
    assert public_resp.status_code == 200
    data = public_resp.json()
    assert data["merchant_slug"] == "phase3merchant"
    assert data["merchant_name"] == "Phase3 Merchant"
    assert len(data["categories"]) >= 1


@pytest.mark.asyncio
async def test_public_menu_not_found(client):
    resp = await client.get("/api/v1/menu/public/nonexistentmerchant123")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Table Management
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_table_generates_qr(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    resp = await client.post("/api/v1/tables", json={
        "table_number": "5",
        "seating_capacity": 4,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["table_number"] == "5"
    assert data["seating_capacity"] == 4
    assert data["status"] == "free"
    assert data["qr_code_url"] is not None
    assert data["qr_token"] is not None
    table_id = data["id"]

    # List tables
    list_resp = await client.get("/api/v1/tables", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    tables = list_resp.json()
    assert any(t["id"] == table_id for t in tables)


@pytest.mark.asyncio
async def test_regenerate_qr_token(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    resp = await client.post("/api/v1/tables", json={
        "table_number": "7",
        "seating_capacity": 2,
    }, headers={"Authorization": f"Bearer {token}"})
    table_id = resp.json()["id"]
    old_token = resp.json()["qr_token"]

    regen_resp = await client.post(f"/api/v1/tables/{table_id}/regenerate-qr", headers={"Authorization": f"Bearer {token}"})
    assert regen_resp.status_code == 200
    new_token = regen_resp.json()["qr_token"]
    assert new_token != old_token
    assert regen_resp.json()["qr_code_url"] is not None


@pytest.mark.asyncio
async def test_update_table_status(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    resp = await client.post("/api/v1/tables", json={
        "table_number": "1",
        "seating_capacity": 6,
    }, headers={"Authorization": f"Bearer {token}"})
    table_id = resp.json()["id"]

    update_resp = await client.put(f"/api/v1/tables/{table_id}", json={
        "status": "reserved",
    }, headers={"Authorization": f"Bearer {token}"})
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "reserved"


# ---------------------------------------------------------------------------
# QR Scan & Validate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_qr_scan_creates_session(client):
    token, merchant_id = await _setup_merchant_and_login(client)

    # Create table
    table_resp = await client.post("/api/v1/tables", json={
        "table_number": "12",
        "seating_capacity": 4,
    }, headers={"Authorization": f"Bearer {token}"})
    qr_token = table_resp.json()["qr_token"]
    table_id = table_resp.json()["id"]

    # Scan QR
    scan_resp = await client.post("/api/v1/qr/scan", json={
        "qr_token": qr_token,
        "customer_name": "John Doe",
        "customer_phone": "+97312345678",
    })
    assert scan_resp.status_code == 201
    data = scan_resp.json()
    assert data["table_number"] == "12"
    assert data["table_id"] == table_id
    assert data["session_token"] is not None
    assert data["menu_url"] is not None
    assert "phase3merchant" in data["menu_url"]
    session_token = data["session_token"]

    # Validate session
    val_resp = await client.get(f"/api/v1/qr/validate?token={session_token}")
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["valid"] is True
    assert val_data["merchant_name"] == "Phase3 Merchant"
    assert val_data["table_number"] == "12"


@pytest.mark.asyncio
async def test_qr_validate_invalid_token(client):
    resp = await client.get("/api/v1/qr/validate?token=invalidtoken123")
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


@pytest.mark.asyncio
async def test_qr_scan_invalid_token(client):
    resp = await client.post("/api/v1/qr/scan", json={
        "qr_token": "nonexistent-token-12345",
    })
    assert resp.status_code == 404
