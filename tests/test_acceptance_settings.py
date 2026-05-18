import pytest


@pytest.mark.asyncio
async def test_acceptance_settings_crud(client):
    # Setup
    tenant_resp = await client.post("/api/v1/auth/register/tenant", json={
        "name": "Acceptance Tenant",
        "slug": "acceptancetenant"
    })
    merchant_resp = await client.post(f"/api/v1/auth/register/merchant?tenant_id={tenant_resp.json()['id']}", json={
        "business_name": "Acceptance Test",
        "slug": "acceptancetest"
    })
    merchant_id = merchant_resp.json()["id"]

    await client.post(f"/api/v1/auth/register/owner?merchant_id={merchant_id}", json={
        "email": "acc@test.com",
        "password": "pass123",
        "first_name": "Acc",
        "last_name": "Tester"
    })
    token = (await client.post("/api/v1/auth/login", json={
        "email": "acc@test.com",
        "password": "pass123"
    })).json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}

    # Get settings (seeded on merchant creation)
    get_resp = await client.get("/api/v1/acceptance-settings/", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["auto_accept_enabled"] is False
    assert get_resp.json()["auto_accept_timeout_sec"] == 300

    # Update settings
    update_resp = await client.put("/api/v1/acceptance-settings/", json={
        "auto_accept_enabled": True,
        "auto_accept_timeout_sec": 120,
        "max_pending_orders": 20
    }, headers=headers)
    assert update_resp.status_code == 200
    assert update_resp.json()["auto_accept_enabled"] is True
    assert update_resp.json()["auto_accept_timeout_sec"] == 120
    assert update_resp.json()["max_pending_orders"] == 20
