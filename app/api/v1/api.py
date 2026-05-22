from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth, merchants, menu, orders, payments,
    whatsapp_acceptance, whatsapp, delivery, drivers, third_party, reconciliation, reports,
    business_hours, acceptance_settings, tables, qr, cart, kds,
    websocket as ws_endpoints, analytics, health,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(merchants.router, prefix="/merchants", tags=["Merchants"])
api_router.include_router(menu.router, prefix="/menu", tags=["Menu"])
api_router.include_router(cart.router, prefix="/cart", tags=["Cart"])
api_router.include_router(orders.router, prefix="/orders", tags=["Orders"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])
api_router.include_router(tables.router, prefix="/tables", tags=["Tables"])
api_router.include_router(qr.router, prefix="/qr", tags=["QR"])
api_router.include_router(kds.router, prefix="/kds", tags=["KDS"])
api_router.include_router(whatsapp_acceptance.router, prefix="/whatsapp", tags=["WhatsApp"])
api_router.include_router(whatsapp.router, prefix="/whatsapp", tags=["WhatsApp"])
api_router.include_router(delivery.router, prefix="/delivery", tags=["Delivery"])
api_router.include_router(drivers.router, prefix="/drivers", tags=["Drivers"])
api_router.include_router(third_party.router, prefix="/third-party", tags=["3rd Party"])
api_router.include_router(reconciliation.router, prefix="/reconciliation", tags=["Reconciliation"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(business_hours.router, prefix="/business-hours", tags=["Business Hours"])
api_router.include_router(acceptance_settings.router, prefix="/acceptance-settings", tags=["Acceptance Settings"])
api_router.include_router(ws_endpoints.router, prefix="/ws", tags=["websocket"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(health.router, tags=["health"])
