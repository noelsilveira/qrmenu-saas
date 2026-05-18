import pytest


@pytest.mark.asyncio
async def test_business_hours_crud(client):
    # Setup
    tenant_resp = await client.post("/api/v1/auth/register/tenant", json={
        "name": "Hours Tenant",
        "slug": "hourstenant"
    })
    merchant_resp = await client.post(f"/api/v1/auth/register/merchant?tenant_id={tenant_resp.json()['id']}", json={
        "business_name": "Hours Test",
        "slug": "hourstest"
    })
    merchant_id = merchant_resp.json()["id"]

    await client.post(f"/api/v1/auth/register/owner?merchant_id={merchant_id}", json={
        "email": "hours@test.com",
        "password": "pass123",
        "first_name": "Hours",
        "last_name": "Tester"
    })
    token = (await client.post("/api/v1/auth/login", json={
        "email": "hours@test.com",
        "password": "pass123"
    })).json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}

    # List hours (should have defaults seeded)
    list_resp = await client.get("/api/v1/business-hours/", headers=headers)
    assert list_resp.status_code == 200
    hours = list_resp.json()
    assert len(hours) == 7  # 7 days seeded by register_merchant

    # Create special hours
    create_resp = await client.post("/api/v1/business-hours/", json={
        "merchant_id": merchant_id,
        "day_of_week": 0,
        "open_time": "08:00:00",
        "close_time": "23:00:00",
        "is_closed": False,
        "timezone": "Asia/Bahrain"
    }, headers=headers)
    assert create_resp.status_code == 201
    hours_id = create_resp.json()["id"]

    # Update hours
    update_resp = await client.put(f"/api/v1/business-hours/{hours_id}", json={
        "is_closed": True
    }, headers=headers)
    assert update_resp.status_code == 200
    assert update_resp.json()["is_closed"] is True

    # Check open status
    check_resp = await client.get("/api/v1/business-hours/check", headers=headers)
    assert check_resp.status_code == 200
    assert "open" in check_resp.json()
