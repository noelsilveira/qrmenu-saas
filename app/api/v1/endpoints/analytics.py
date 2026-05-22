"""
Phase 10 API Endpoints — Analytics, Sales Reports & Insights
"""

import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_user
from app.schemas.analytics import (
    SalesReportRequest, SalesReportResponse,
    ItemPerformanceRequest, ItemPerformanceResponse,
    CustomerInsightsRequest, CustomerInsightsResponse,
    WhatsAppAnalyticsRequest, WhatsAppAnalyticsResponse,
    DeliveryReportRequest, DeliveryReportResponse,
    ReconciliationReportRequest, ReconciliationReport,
    DashboardRequest, UnifiedDashboardResponse,
    ReportExportRequest, ReportExportResponse,
    ReportPeriod
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(tags=["analytics"])

def get_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(db)

# ─── SALES REPORTS ─────────────────────────────────────────────────

@router.post("/sales", response_model=SalesReportResponse)
async def get_sales_report(
    request: SalesReportRequest,
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Generate comprehensive sales report."""
    return await service.get_sales_report(current_user.merchant_id, request)

@router.get("/sales/summary")
async def get_sales_summary(
    period: ReportPeriod = Query(ReportPeriod.TODAY),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    branch_id: Optional[uuid.UUID] = Query(None),
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Quick sales summary endpoint."""
    request = SalesReportRequest(
        period=period,
        date_from=date_from,
        date_to=date_to,
        branch_id=branch_id
    )
    report = await service.get_sales_report(current_user.merchant_id, request)
    return report.summary

# ─── ITEM PERFORMANCE ──────────────────────────────────────────────

@router.post("/items", response_model=ItemPerformanceResponse)
async def get_item_performance(
    request: ItemPerformanceRequest,
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Analyze item sales performance."""
    return await service.get_item_performance(current_user.merchant_id, request)

@router.get("/items/top")
async def get_top_items(
    period: ReportPeriod = Query(ReportPeriod.THIS_MONTH),
    limit: int = Query(10, ge=1, le=100),
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Get top performing items."""
    request = ItemPerformanceRequest(
        period=period,
        sort_by="total_sold",
        sort_order="desc",
        page_size=limit
    )
    return await service.get_item_performance(current_user.merchant_id, request)

# ─── CUSTOMER INSIGHTS ───────────────────────────────────────────

@router.post("/customers", response_model=CustomerInsightsResponse)
async def get_customer_insights(
    request: CustomerInsightsRequest,
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Analyze customer behavior and segments."""
    return await service.get_customer_insights(current_user.merchant_id, request)

@router.get("/customers/vip")
async def get_vip_customers(
    period: ReportPeriod = Query(ReportPeriod.THIS_MONTH),
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Get VIP customers."""
    request = CustomerInsightsRequest(
        period=period,
        tier="vip",
        sort_by="total_spent",
        sort_order="desc",
        page_size=50
    )
    return await service.get_customer_insights(current_user.merchant_id, request)

@router.get("/customers/at-risk")
async def get_at_risk_customers(
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Get customers at risk of churning."""
    request = CustomerInsightsRequest(
        period=ReportPeriod.THIS_MONTH,
        sort_by="total_spent",
        sort_order="desc",
        page_size=200
    )
    result = await service.get_customer_insights(current_user.merchant_id, request)
    at_risk = [c for c in result.customers if c.retention_risk in ["medium", "high"]]
    return {
        "at_risk_count": len(at_risk),
        "customers": [c.model_dump() for c in at_risk]
    }

# ─── WHATSAPP ANALYTICS ──────────────────────────────────────────

@router.post("/whatsapp", response_model=WhatsAppAnalyticsResponse)
async def get_whatsapp_analytics(
    request: WhatsAppAnalyticsRequest,
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Analyze WhatsApp messaging performance."""
    return await service.get_whatsapp_analytics(current_user.merchant_id, request)

@router.get("/whatsapp/summary")
async def get_whatsapp_summary(
    period: ReportPeriod = Query(ReportPeriod.THIS_MONTH),
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Quick WhatsApp metrics summary."""
    request = WhatsAppAnalyticsRequest(period=period)
    result = await service.get_whatsapp_analytics(current_user.merchant_id, request)
    return result.metrics

# ─── DELIVERY REPORTS ────────────────────────────────────────────

@router.post("/delivery", response_model=DeliveryReportResponse)
async def get_delivery_report(
    request: DeliveryReportRequest,
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Analyze delivery performance."""
    return await service.get_delivery_report(current_user.merchant_id, request)

@router.get("/delivery/summary")
async def get_delivery_summary(
    period: ReportPeriod = Query(ReportPeriod.THIS_MONTH),
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Quick delivery metrics summary."""
    request = DeliveryReportRequest(period=period)
    result = await service.get_delivery_report(current_user.merchant_id, request)
    return result.summary

@router.get("/delivery/drivers")
async def get_driver_performance(
    period: ReportPeriod = Query(ReportPeriod.THIS_MONTH),
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Get driver performance rankings."""
    request = DeliveryReportRequest(period=period)
    result = await service.get_delivery_report(current_user.merchant_id, request)
    return {
        "drivers": [d.model_dump() for d in result.by_driver],
        "total_drivers": len(result.by_driver)
    }

# ─── RECONCILIATION REPORTS ──────────────────────────────────────

@router.post("/reconciliation", response_model=ReconciliationReport)
async def get_reconciliation_report(
    request: ReconciliationReportRequest,
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Summarize reconciliation activity."""
    return await service.get_reconciliation_report(current_user.merchant_id, request)

# ─── UNIFIED DASHBOARD ───────────────────────────────────────────

@router.post("/dashboard", response_model=UnifiedDashboardResponse)
async def get_dashboard(
    request: DashboardRequest,
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Get unified merchant dashboard with KPIs and charts."""
    return await service.get_dashboard(current_user.merchant_id, request)

@router.get("/dashboard")
async def get_dashboard_quick(
    period: ReportPeriod = Query(ReportPeriod.TODAY),
    branch_id: Optional[uuid.UUID] = Query(None),
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Quick dashboard endpoint with query params."""
    request = DashboardRequest(period=period, branch_id=branch_id)
    return await service.get_dashboard(current_user.merchant_id, request)

# ─── EXPORT ──────────────────────────────────────────────────────

@router.post("/export")
async def export_report(
    request: ReportExportRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(get_current_user),
    service: AnalyticsService = Depends(get_service)
):
    """Generate and export a report file."""
    # This is a stub - implement actual file generation in production
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Report Type", "Period", "Generated At"])
    writer.writerow([request.report_type, request.period.value, datetime.utcnow().isoformat()])

    # In production, upload to S3/cloud storage and return URL
    return {
        "download_url": f"/tmp/{request.report_type}_{datetime.utcnow().timestamp()}.csv",
        "file_format": request.format,
        "file_size_bytes": len(output.getvalue()),
        "generated_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(hours=24)
    }
