import pytest
from uuid import UUID


@pytest.mark.asyncio
async def test_register_tenant(client):
    resp = await client.post("/api/v1/auth/register/tenant", json={
        "name": "Test Tenant",
        "slug": "testtenant"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Tenant"
    assert data["slug"] == "testtenant"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_merchant(client):
    # First create tenant
    tenant_resp = await client.post("/api/v1/auth/register/tenant", json={
        "name": "Test Tenant 2",
        "slug": "testtenant2"
    })
    tenant_id = tenant_resp.json()["id"]

    resp = await client.post(f"/api/v1/auth/register/merchant?tenant_id={tenant_id}", json={
        "business_name": "Test Merchant",
        "slug": "testmerchant",
        "currency": "BHD",
        "timezone": "Asia/Bahrain"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["business_name"] == "Test Merchant"
    assert data["slug"] == "testmerchant"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_owner_and_login(client):
    # Setup tenant + merchant
    tenant_resp = await client.post("/api/v1/auth/register/tenant", json={
        "name": "Test Tenant 3",
        "slug": "testtenant3"
    })
    tenant_id = tenant_resp.json()["id"]

    merchant_resp = await client.post(f"/api/v1/auth/register/merchant?tenant_id={tenant_id}", json={
        "business_name": "Test Merchant 3",
        "slug": "testmerchant3"
    })
    merchant_id = merchant_resp.json()["id"]

    # Register owner
    owner_resp = await client.post(f"/api/v1/auth/register/owner?merchant_id={merchant_id}", json={
        "email": "owner@test.com",
        "password": "password123",
        "first_name": "Test",
        "last_name": "Owner"
    })
    assert owner_resp.status_code == 201
    assert owner_resp.json()["email"] == "owner@test.com"

    # Login
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "owner@test.com",
        "password": "password123"
    })
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"

    # Refresh token
    refresh_resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": tokens["refresh_token"]
    })
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens

    # Get me (with auth)
    me_resp = await client.get("/api/v1/auth/me", headers={
        "Authorization": f"Bearer {new_tokens['access_token']}"
    })
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "owner@test.com"
