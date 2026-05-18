import asyncio
import httpx
import uuid

async def verify():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        slug = f"tenant{uuid.uuid4().hex[:8]}"
        
        # 1. Register Tenant
        r = await client.post("/api/v1/auth/register/tenant", json={"name": "Test Tenant", "slug": slug})
        assert r.status_code == 201, f"Tenant failed: {r.text}"
        tenant_id = r.json()["id"]
        print(f"✅ Tenant created: {tenant_id}")
        
        # 2. Register Merchant
        r = await client.post(f"/api/v1/auth/register/merchant?tenant_id={tenant_id}", 
            json={"business_name": "Test Merchant", "slug": f"{slug}m"})
        assert r.status_code == 201, f"Merchant failed: {r.text}"
        merchant_id = r.json()["id"]
        print(f"✅ Merchant created: {merchant_id}")
        
        # 3. Register Owner
        r = await client.post(f"/api/v1/auth/register/owner?merchant_id={merchant_id}",
            json={"email": f"owner@{slug}.com", "password": "password123", "first_name": "Test", "last_name": "Owner"})
        assert r.status_code == 201, f"Owner failed: {r.text}"
        print(f"✅ Owner registered: {r.json()['email']}")
        
        # 4. Login
        r = await client.post("/api/v1/auth/login", json={"email": f"owner@{slug}.com", "password": "password123"})
        assert r.status_code == 200, f"Login failed: {r.text}"
        access_token = r.json()["access_token"]
        refresh_token = r.json()["refresh_token"]
        print(f"✅ Login successful, token received")
        
        # 5. Get Me
        r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert r.status_code == 200, f"Me failed: {r.text}"
        assert r.json()["email"] == f"owner@{slug}.com"
        print(f"✅ Get me: {r.json()['email']}")
        
        # 6. Refresh Token
        r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert r.status_code == 200, f"Refresh failed: {r.text}"
        print(f"✅ Token refreshed")
        
        # 7. Update Branding
        r = await client.put("/api/v1/merchants/branding", headers={"Authorization": f"Bearer {access_token}"},
            json={"brand_primary_color": "#FF0000", "receipt_header": "Welcome"})
        assert r.status_code == 200, f"Branding failed: {r.text}"
        print(f"✅ Branding updated: {r.json()['brand_primary_color']}")
        
        # 8. Public Profile
        r = await client.get(f"/api/v1/merchants/public-profile?slug={slug}m")
        assert r.status_code == 200, f"Profile failed: {r.text}"
        assert r.json()["business_name"] == "Test Merchant"
        print(f"✅ Public profile: {r.json()['business_name']}")
        
        # 9. Business Hours
        r = await client.get("/api/v1/business-hours/", headers={"Authorization": f"Bearer {access_token}"})
        assert r.status_code == 200, f"Hours failed: {r.text}"
        assert len(r.json()) == 7
        print(f"✅ Business hours: {len(r.json())} days")
        
        # 10. Acceptance Settings
        r = await client.get("/api/v1/acceptance-settings/", headers={"Authorization": f"Bearer {access_token}"})
        assert r.status_code == 200, f"Settings failed: {r.text}"
        assert r.json()["auto_accept_timeout_sec"] == 300
        print(f"✅ Acceptance settings: timeout={r.json()['auto_accept_timeout_sec']}s")
        
        # 11. Update Acceptance Settings
        r = await client.put("/api/v1/acceptance-settings/", headers={"Authorization": f"Bearer {access_token}"},
            json={"auto_accept_enabled": True, "auto_accept_timeout_sec": 120})
        assert r.status_code == 200, f"Update settings failed: {r.text}"
        assert r.json()["auto_accept_enabled"] == True
        print(f"✅ Acceptance settings updated: auto_accept={r.json()['auto_accept_enabled']}")
        
        print("\n🎉 ALL PHASE 2 VERIFICATIONS PASSED")

if __name__ == "__main__":
    asyncio.run(verify())
