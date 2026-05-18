from fastapi import APIRouter

from app.api.v1.endpoints import auth, merchants, menu, orders, payments, \
    whatsapp_acceptance, delivery_zones, drivers, third_party, reconciliation, reports

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(merchants.router, prefix="/merchants", tags=["Merchants"])
api_router.include_router(menu.router, prefix="/menu", tags=["Menu"])
api_router.include_router(orders.router, prefix="/orders", tags=["Orders"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])
api_router.include_router(whatsapp_acceptance.router, prefix="/whatsapp", tags=["WhatsApp"])
api_router.include_router(delivery_zones.router, prefix="/delivery", tags=["Delivery"])
api_router.include_router(drivers.router, prefix="/drivers", tags=["Drivers"])
api_router.include_router(third_party.router, prefix="/third-party", tags=["3rd Party"])
api_router.include_router(reconciliation.router, prefix="/reconciliation", tags=["Reconciliation"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
