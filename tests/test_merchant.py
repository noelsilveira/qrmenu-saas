import pytest


@pytest.mark.asyncio
async def test_merchant_onboarding_flow(client):
    # Setup
    tenant_resp = await client.post("/api/v1/auth/register/tenant", json={
        "name": "Merchant Tenant",
        "slug": "merchanttenant"
    })
    tenant_id = tenant_resp.json()["id"]

    merchant_resp = await client.post(f"/api/v1/auth/register/merchant?tenant_id={tenant_id}", json={
        "business_name": "Burger Joint",
        "slug": "burgerjoint"
    })
    merchant_id = merchant_resp.json()["id"]

    owner_resp = await client.post(f"/api/v1/auth/register/owner?merchant_id={merchant_id}", json={
        "email": "burger@joint.com",
        "password": "secret123",
        "first_name": "Burger",
        "last_name": "Boss"
    })
    token = (await client.post("/api/v1/auth/login", json={
        "email": "burger@joint.com",
        "password": "secret123"
    })).json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}

    # Update branding
    branding_resp = await client.put("/api/v1/merchants/branding", json={
        "brand_primary_color": "#FF0000",
        "brand_secondary_color": "#FFFFFF",
        "receipt_header": "Welcome to Burger Joint"
    }, headers=headers)
    assert branding_resp.status_code == 200
    assert branding_resp.json()["brand_primary_color"] == "#FF0000"

    # Get public profile
    profile_resp = await client.get("/api/v1/merchants/public-profile?slug=burgerjoint")
    assert profile_resp.status_code == 200
    assert profile_resp.json()["business_name"] == "Burger Joint"

    # Update settings
    settings_resp = await client.put("/api/v1/merchants/settings", json={
        "currency": "USD",
        "timezone": "America/New_York"
    }, headers=headers)
    assert settings_resp.status_code == 200
    assert settings_resp.json()["currency"] == "USD"

    # Get settings
    get_settings = await client.get("/api/v1/merchants/settings", headers=headers)
    assert get_settings.status_code == 200
    assert get_settings.json()["currency"] == "USD"
