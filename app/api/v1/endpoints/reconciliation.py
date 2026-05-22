"""
Phase 8 API Endpoints — Reconciliation & Financial Ledger
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_user  # Adjust import as per your auth module
from app.schemas.reconciliation import (
    # Ledger
    LedgerEntryCreate, LedgerEntryUpdate, LedgerEntryResponse,
    LedgerListParams, LedgerSummaryResponse,
    # Reconciliation Run
    ReconciliationRunCreate, ReconciliationRunResponse, ReconciliationRunListParams,
    ReconciliationConfig, ReconciliationTrigger, ReconciliationResult, ReconciliationPreview,
    # Discrepancy
    DiscrepancyCreate, DiscrepancyUpdate, DiscrepancyResolve, DiscrepancyResponse,
    DiscrepancyListParams, DiscrepancySummary,
    # Payout
    PayoutCreate, PayoutUpdate, PayoutResponse, PayoutListParams, PayoutSummary,
    # Settlement
    SettlementReportCreate, SettlementReportResponse, SettlementReportListParams,
    # Dashboard / Export
    ReconciliationDashboard, LedgerExportRequest, ExportFormat
)
from app.services.reconciliation_service import ReconciliationService

router = APIRouter(tags=["reconciliation"])

# ─── HELPERS ───────────────────────────────────────────────────────

def get_service(db: AsyncSession = Depends(get_db)) -> ReconciliationService:
    return ReconciliationService(db)

# ─── FINANCIAL LEDGER ──────────────────────────────────────────────

@router.post("/ledger", response_model=LedgerEntryResponse, status_code=201)
async def create_ledger_entry(
    data: LedgerEntryCreate,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Create a manual ledger entry (e.g., adjustment, refund)."""
    entry = await service.ledger.create_entry(current_user.merchant_id, data)
    return entry

@router.get("/ledger", response_model=List[LedgerEntryResponse])
async def list_ledger_entries(
    entry_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    platform_connection_id: Optional[uuid.UUID] = Query(None),
    order_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """List ledger entries with filters."""
    params = LedgerListParams(
        entry_type=entry_type,
        status=status,
        platform_connection_id=platform_connection_id,
        order_id=order_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size
    )
    entries, total = await service.ledger.list_entries(current_user.merchant_id, params)
    # FastAPI doesn't auto-handle tuple returns with total; return entries only for response_model
    # If you need total count, use a custom response wrapper or headers
    return entries

@router.get("/ledger/summary", response_model=LedgerSummaryResponse)
async def get_ledger_summary(
    date_from: datetime,
    date_to: datetime,
    platform_connection_id: Optional[uuid.UUID] = Query(None),
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Get aggregated ledger summary for a period."""
    return await service.ledger.get_summary(current_user.merchant_id, date_from, date_to, platform_connection_id)

@router.get("/ledger/{entry_id}", response_model=LedgerEntryResponse)
async def get_ledger_entry(
    entry_id: uuid.UUID,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Get a single ledger entry."""
    entry = await service.ledger.get_entry(current_user.merchant_id, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Ledger entry not found")
    return entry

@router.patch("/ledger/{entry_id}", response_model=LedgerEntryResponse)
async def update_ledger_entry(
    entry_id: uuid.UUID,
    data: LedgerEntryUpdate,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Update ledger entry status/metadata."""
    entry = await service.ledger.update_entry_status(current_user.merchant_id, entry_id, data)
    if not entry:
        raise HTTPException(status_code=404, detail="Ledger entry not found")
    return entry

# ─── RECONCILIATION ENGINE ─────────────────────────────────────────

@router.post("/runs/preview", response_model=ReconciliationPreview)
async def preview_reconciliation(
    data: ReconciliationTrigger,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Preview what a reconciliation run would find without executing."""
    return await service.engine.preview(
        current_user.merchant_id,
        data.platform_connection_id,
        data.date_from,
        data.date_to
    )

@router.post("/runs", response_model=ReconciliationResult, status_code=202)
async def trigger_reconciliation(
    data: ReconciliationTrigger,
    background_tasks: BackgroundTasks,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Trigger a new reconciliation run."""
    run_data = ReconciliationRunCreate(
        platform_connection_id=data.platform_connection_id,
        date_from=data.date_from,
        date_to=data.date_to,
        triggered_by="manual",
        config=data.config.model_dump()
    )
    result = await service.engine.run(current_user.merchant_id, run_data, data.config)
    return result

@router.get("/runs", response_model=List[ReconciliationRunResponse])
async def list_reconciliation_runs(
    status: Optional[str] = Query(None),
    platform_connection_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """List reconciliation runs."""
    from app.models.models import ReconciliationRun
    from sqlalchemy import select, desc

    query = select(ReconciliationRun).where(ReconciliationRun.merchant_id == current_user.merchant_id)
    if status:
        query = query.where(ReconciliationRun.status == status)
    if platform_connection_id:
        query = query.where(ReconciliationRun.platform_connection_id == platform_connection_id)
    if date_from:
        query = query.where(ReconciliationRun.date_from >= date_from)
    if date_to:
        query = query.where(ReconciliationRun.date_to <= date_to)

    query = query.order_by(desc(ReconciliationRun.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await service.db.execute(query)
    return result.scalars().all()

@router.get("/runs/{run_id}", response_model=ReconciliationRunResponse)
async def get_reconciliation_run(
    run_id: uuid.UUID,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Get a single reconciliation run."""
    from app.models.models import ReconciliationRun
    from sqlalchemy import select

    result = await service.db.execute(
        select(ReconciliationRun).where(
            ReconciliationRun.id == run_id,
            ReconciliationRun.merchant_id == current_user.merchant_id
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Reconciliation run not found")
    return run

# ─── DISCREPANCIES ─────────────────────────────────────────────────

@router.get("/discrepancies", response_model=List[DiscrepancyResponse])
async def list_discrepancies(
    status: Optional[str] = Query(None),
    discrepancy_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    platform_connection_id: Optional[uuid.UUID] = Query(None),
    reconciliation_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """List discrepancies with filters."""
    params = DiscrepancyListParams(
        status=status,
        discrepancy_type=discrepancy_type,
        severity=severity,
        platform_connection_id=platform_connection_id,
        reconciliation_id=reconciliation_id,
        page=page,
        page_size=page_size
    )
    discrepancies, total = await service.discrepancy.list(current_user.merchant_id, params)
    return discrepancies

@router.get("/discrepancies/summary", response_model=DiscrepancySummary)
async def get_discrepancy_summary(
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Get discrepancy summary dashboard stats."""
    return await service.discrepancy.get_summary(current_user.merchant_id)

@router.get("/discrepancies/{discrepancy_id}", response_model=DiscrepancyResponse)
async def get_discrepancy(
    discrepancy_id: uuid.UUID,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Get a single discrepancy."""
    disc = await service.discrepancy.get(current_user.merchant_id, discrepancy_id)
    if not disc:
        raise HTTPException(status_code=404, detail="Discrepancy not found")
    return disc

@router.patch("/discrepancies/{discrepancy_id}", response_model=DiscrepancyResponse)
async def update_discrepancy(
    discrepancy_id: uuid.UUID,
    data: DiscrepancyUpdate,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Update discrepancy status/notes."""
    disc = await service.discrepancy.update(current_user.merchant_id, discrepancy_id, data)
    if not disc:
        raise HTTPException(status_code=404, detail="Discrepancy not found")
    return disc

@router.post("/discrepancies/{discrepancy_id}/resolve", response_model=DiscrepancyResponse)
async def resolve_discrepancy(
    discrepancy_id: uuid.UUID,
    data: DiscrepancyResolve,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Resolve a discrepancy with notes."""
    disc = await service.discrepancy.resolve(current_user.merchant_id, discrepancy_id, data)
    if not disc:
        raise HTTPException(status_code=404, detail="Discrepancy not found")
    return disc

# ─── PAYOUTS ───────────────────────────────────────────────────────

@router.post("/payouts", response_model=PayoutResponse, status_code=201)
async def create_payout(
    data: PayoutCreate,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Record a platform payout."""
    payout = await service.payout.create(current_user.merchant_id, data)
    return payout

@router.get("/payouts", response_model=List[PayoutResponse])
async def list_payouts(
    status: Optional[str] = Query(None),
    platform_connection_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """List payouts with filters."""
    params = PayoutListParams(
        status=status,
        platform_connection_id=platform_connection_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size
    )
    payouts, total = await service.payout.list(current_user.merchant_id, params)
    return payouts

@router.get("/payouts/summary", response_model=PayoutSummary)
async def get_payout_summary(
    platform_connection_id: Optional[uuid.UUID] = Query(None),
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Get payout summary by status."""
    return await service.payout.get_summary(current_user.merchant_id, platform_connection_id)

@router.get("/payouts/{payout_id}", response_model=PayoutResponse)
async def get_payout(
    payout_id: uuid.UUID,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Get a single payout."""
    payout = await service.payout.get(current_user.merchant_id, payout_id)
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    return payout

@router.patch("/payouts/{payout_id}", response_model=PayoutResponse)
async def update_payout(
    payout_id: uuid.UUID,
    data: PayoutUpdate,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Update payout status/dates."""
    payout = await service.payout.update(current_user.merchant_id, payout_id, data)
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    return payout

@router.post("/payouts/sync/{platform_connection_id}")
async def sync_payouts(
    platform_connection_id: uuid.UUID,
    payouts_data: List[dict],
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Bulk sync payouts from a platform API."""
    created, updated = await service.payout.sync_from_platform(
        current_user.merchant_id, platform_connection_id, payouts_data
    )
    return {"created": created, "updated": updated, "platform_connection_id": str(platform_connection_id)}

# ─── SETTLEMENT REPORTS ──────────────────────────────────────────

@router.post("/reports", response_model=SettlementReportResponse, status_code=201)
async def create_settlement_report(
    data: SettlementReportCreate,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Generate a settlement report for a period."""
    report = await service.settlement.create(current_user.merchant_id, data)
    return report

@router.get("/reports", response_model=List[SettlementReportResponse])
async def list_settlement_reports(
    report_type: Optional[str] = Query(None),
    platform_connection_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    is_final: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """List settlement reports."""
    params = SettlementReportListParams(
        report_type=report_type,
        platform_connection_id=platform_connection_id,
        date_from=date_from,
        date_to=date_to,
        is_final=is_final,
        page=page,
        page_size=page_size
    )
    reports, total = await service.settlement.list(current_user.merchant_id, params)
    return reports

@router.get("/reports/{report_id}", response_model=SettlementReportResponse)
async def get_settlement_report(
    report_id: uuid.UUID,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Get a settlement report."""
    report = await service.settlement.get(current_user.merchant_id, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Settlement report not found")
    return report

@router.post("/reports/{report_id}/finalize", response_model=SettlementReportResponse)
async def finalize_settlement_report(
    report_id: uuid.UUID,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Mark a settlement report as final (immutable)."""
    report = await service.settlement.finalize(current_user.merchant_id, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Settlement report not found")
    return report

# ─── DASHBOARD ─────────────────────────────────────────────────────

@router.get("/dashboard", response_model=ReconciliationDashboard)
async def get_reconciliation_dashboard(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Get unified reconciliation dashboard."""
    if not date_from:
        date_from = datetime.utcnow() - timedelta(days=30)
    if not date_to:
        date_to = datetime.utcnow()

    ledger_summary = await service.ledger.get_summary(current_user.merchant_id, date_from, date_to)
    discrepancy_summary = await service.discrepancy.get_summary(current_user.merchant_id)
    payout_summary = await service.payout.get_summary(current_user.merchant_id)

    # Platform comparison
    from sqlalchemy import select, func
    from app.models.models import FinancialLedger, PlatformConnection

    plat_result = await service.db.execute(
        select(
            FinancialLedger.platform_connection_id,
            func.coalesce(func.sum(FinancialLedger.net_amount), 0).label("total"),
            func.count(FinancialLedger.id).label("count")
        )
        .where(FinancialLedger.merchant_id == current_user.merchant_id)
        .where(FinancialLedger.transaction_date >= date_from)
        .where(FinancialLedger.transaction_date <= date_to)
        .group_by(FinancialLedger.platform_connection_id)
    )
    platform_comparison = [
        {
            "platform_connection_id": str(row.platform_connection_id) if row.platform_connection_id else "direct",
            "total_net": float(row.total),
            "count": row.count
        }
        for row in plat_result.all()
    ]

    # Daily trend (last 30 days)
    from sqlalchemy import cast, Date
    trend_result = await service.db.execute(
        select(
            cast(FinancialLedger.transaction_date, Date).label("day"),
            func.coalesce(func.sum(FinancialLedger.net_amount), 0).label("total"),
            func.count(FinancialLedger.id).label("count")
        )
        .where(FinancialLedger.merchant_id == current_user.merchant_id)
        .where(FinancialLedger.transaction_date >= date_from)
        .where(FinancialLedger.transaction_date <= date_to)
        .group_by(cast(FinancialLedger.transaction_date, Date))
        .order_by("day")
    )
    daily_trend = [
        {"date": str(row.day), "total_net": float(row.total), "count": row.count}
        for row in trend_result.all()
    ]

    return ReconciliationDashboard(
        period_start=date_from,
        period_end=date_to,
        ledger_summary=ledger_summary,
        discrepancy_summary=discrepancy_summary,
        payout_summary=payout_summary,
        platform_comparison=platform_comparison,
        daily_trend=daily_trend
    )

# ─── EXPORT ──────────────────────────────────────────────────────────

@router.post("/ledger/export")
async def export_ledger(
    request: LedgerExportRequest,
    current_user = Depends(get_current_user),
    service: ReconciliationService = Depends(get_service)
):
    """Export ledger entries to CSV/XLSX/PDF."""
    params = LedgerListParams(
        platform_connection_id=request.platform_connection_id,
        entry_type=request.entry_type,
        date_from=request.date_from,
        date_to=request.date_to,
        page=1,
        page_size=10000  # Max export
    )
    entries, total = await service.ledger.list_entries(current_user.merchant_id, params)

    # Simple CSV generation (enhance with proper library in production)
    if request.format == ExportFormat.CSV:
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Type", "Status", "Gross", "Fees", "Tax", "Net", "Currency", "Date", "Description"])
        for e in entries:
            writer.writerow([
                str(e.id), e.entry_type, e.status,
                float(e.gross_amount), float(e.fee_amount), float(e.tax_amount), float(e.net_amount),
                e.currency, e.transaction_date.isoformat(), e.description or ""
            ])
        return {"format": "csv", "data": output.getvalue(), "count": len(entries)}

    elif request.format == ExportFormat.XLSX:
        # TODO: integrate openpyxl or similar
        return {"format": "xlsx", "message": "XLSX export not yet implemented", "count": len(entries)}

    elif request.format == ExportFormat.PDF:
        # TODO: integrate reportlab or similar
        return {"format": "pdf", "message": "PDF export not yet implemented", "count": len(entries)}

    return {"format": request.format.value, "count": len(entries)}
