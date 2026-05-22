"""
Phase 8 Schemas — Reconciliation & Financial Ledger
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

# ─── ENUMS ─────────────────────────────────────────────────────────

class LedgerEntryType(str, Enum):
    ORDER_PAYMENT = "order_payment"
    PLATFORM_FEE = "platform_fee"
    DELIVERY_FEE = "delivery_fee"
    REFUND = "refund"
    PAYOUT = "payout"
    ADJUSTMENT = "adjustment"
    TAX = "tax"
    TIP = "tip"

class LedgerEntryStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    RECONCILED = "reconciled"
    DISPUTED = "disputed"
    WRITTEN_OFF = "written_off"

class ReconciliationRunStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"

class DiscrepancyType(str, Enum):
    MISSING_ORDER = "missing_order"
    ORPHAN_ORDER = "orphan_order"
    AMOUNT_MISMATCH = "amount_mismatch"
    FEE_MISMATCH = "fee_mismatch"
    DUPLICATE_PAYOUT = "duplicate_payout"
    MISSING_PAYOUT = "missing_payout"
    TAX_MISMATCH = "tax_mismatch"
    STATUS_MISMATCH = "status_mismatch"

class DiscrepancyStatus(str, Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    IGNORED = "ignored"

class PayoutStatus(str, Enum):
    EXPECTED = "expected"
    SCHEDULED = "scheduled"
    IN_TRANSIT = "in_transit"
    RECEIVED = "received"
    FAILED = "failed"
    DISPUTED = "disputed"

class ReportType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"

# ─── FINANCIAL LEDGER SCHEMAS ──────────────────────────────────────

class LedgerEntryBase(BaseModel):
    entry_type: LedgerEntryType
    currency: str = Field(default="BHD", max_length=3)
    gross_amount: Decimal = Field(..., ge=0, decimal_places=4)
    fee_amount: Decimal = Field(default=Decimal("0.0000"), ge=0, decimal_places=4)
    tax_amount: Decimal = Field(default=Decimal("0.0000"), ge=0, decimal_places=4)
    net_amount: Decimal = Field(..., decimal_places=4)
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    transaction_date: datetime

class LedgerEntryCreate(LedgerEntryBase):
    order_id: Optional[UUID] = None
    platform_connection_id: Optional[UUID] = None
    payout_id: Optional[UUID] = None
    platform_reference: Optional[str] = None
    platform_order_id: Optional[str] = None

class LedgerEntryUpdate(BaseModel):
    status: Optional[LedgerEntryStatus] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class LedgerEntryResponse(LedgerEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID
    order_id: Optional[UUID] = None
    platform_connection_id: Optional[UUID] = None
    payout_id: Optional[UUID] = None
    platform_reference: Optional[str] = None
    platform_order_id: Optional[str] = None
    status: LedgerEntryStatus
    reconciliation_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

class LedgerListParams(BaseModel):
    entry_type: Optional[LedgerEntryType] = None
    status: Optional[LedgerEntryStatus] = None
    platform_connection_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

class LedgerSummary(BaseModel):
    total_gross: Decimal
    total_fees: Decimal
    total_tax: Decimal
    total_net: Decimal
    count: int
    currency: str

class LedgerSummaryByType(BaseModel):
    entry_type: LedgerEntryType
    total_gross: Decimal
    total_net: Decimal
    count: int

class LedgerSummaryResponse(BaseModel):
    overall: LedgerSummary
    by_type: List[LedgerSummaryByType]
    date_from: datetime
    date_to: datetime

# ─── RECONCILIATION RUN SCHEMAS ────────────────────────────────────

class ReconciliationRunBase(BaseModel):
    platform_connection_id: Optional[UUID] = None
    date_from: datetime
    date_to: datetime

class ReconciliationRunCreate(ReconciliationRunBase):
    triggered_by: str = Field(default="manual", max_length=50)
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ReconciliationRunResponse(ReconciliationRunBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID
    status: ReconciliationRunStatus
    total_orders_checked: int
    total_orders_matched: int
    total_discrepancies_found: int
    total_discrepancies_resolved: int
    total_amount_checked: Decimal
    total_variance: Decimal
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    triggered_by: str
    config_snapshot: Dict[str, Any]
    created_at: datetime

class ReconciliationRunListParams(BaseModel):
    status: Optional[ReconciliationRunStatus] = None
    platform_connection_id: Optional[UUID] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

# ─── DISCREPANCY SCHEMAS ───────────────────────────────────────────

class DiscrepancyBase(BaseModel):
    discrepancy_type: DiscrepancyType
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    description: Optional[str] = None

class DiscrepancyCreate(DiscrepancyBase):
    reconciliation_id: UUID
    order_id: Optional[UUID] = None
    platform_order_id: Optional[str] = None
    platform_connection_id: Optional[UUID] = None
    payout_id: Optional[UUID] = None
    expected_amount: Optional[Decimal] = None
    actual_amount: Optional[Decimal] = None
    variance: Optional[Decimal] = None
    currency: str = "BHD"
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None

class DiscrepancyUpdate(BaseModel):
    status: Optional[DiscrepancyStatus] = None
    resolution_notes: Optional[str] = None
    severity: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")

class DiscrepancyResolve(BaseModel):
    status: DiscrepancyStatus = DiscrepancyStatus.RESOLVED
    resolution_notes: str
    resolved_by: str = Field(..., max_length=100)

class DiscrepancyResponse(DiscrepancyBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID
    reconciliation_id: UUID
    status: DiscrepancyStatus
    order_id: Optional[UUID] = None
    platform_order_id: Optional[str] = None
    platform_connection_id: Optional[UUID] = None
    payout_id: Optional[UUID] = None
    expected_amount: Optional[Decimal] = None
    actual_amount: Optional[Decimal] = None
    variance: Optional[Decimal] = None
    currency: str
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    resolution_notes: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

class DiscrepancyListParams(BaseModel):
    status: Optional[DiscrepancyStatus] = None
    discrepancy_type: Optional[DiscrepancyType] = None
    severity: Optional[str] = None
    platform_connection_id: Optional[UUID] = None
    reconciliation_id: Optional[UUID] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

class DiscrepancySummary(BaseModel):
    total_open: int
    total_under_review: int
    total_resolved: int
    total_escalated: int
    total_ignored: int
    total_variance: Decimal
    by_type: Dict[str, int]

# ─── PAYOUT SCHEMAS ────────────────────────────────────────────────

class PayoutBase(BaseModel):
    platform_payout_id: str = Field(..., max_length=255)
    platform_period_start: Optional[datetime] = None
    platform_period_end: Optional[datetime] = None
    currency: str = Field(default="BHD", max_length=3)
    gross_sales: Decimal = Field(default=Decimal("0.0000"), ge=0, decimal_places=4)
    total_fees: Decimal = Field(default=Decimal("0.0000"), ge=0, decimal_places=4)
    total_refunds: Decimal = Field(default=Decimal("0.0000"), ge=0, decimal_places=4)
    total_adjustments: Decimal = Field(default=Decimal("0.0000"), decimal_places=4)
    net_payout: Decimal = Field(..., ge=0, decimal_places=4)
    breakdown: Optional[Dict[str, Any]] = Field(default_factory=dict)
    bank_reference: Optional[str] = None
    bank_account_last4: Optional[str] = Field(None, max_length=4)
    expected_date: Optional[datetime] = None
    sent_date: Optional[datetime] = None
    received_date: Optional[datetime] = None

class PayoutCreate(PayoutBase):
    platform_connection_id: UUID
    status: PayoutStatus = PayoutStatus.EXPECTED

class PayoutUpdate(BaseModel):
    status: Optional[PayoutStatus] = None
    bank_reference: Optional[str] = None
    sent_date: Optional[datetime] = None
    received_date: Optional[datetime] = None
    net_payout: Optional[Decimal] = None

class PayoutResponse(PayoutBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID
    platform_connection_id: UUID
    status: PayoutStatus
    created_at: datetime
    updated_at: datetime

class PayoutListParams(BaseModel):
    status: Optional[PayoutStatus] = None
    platform_connection_id: Optional[UUID] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

class PayoutSummary(BaseModel):
    total_expected: Decimal
    total_scheduled: Decimal
    total_in_transit: Decimal
    total_received: Decimal
    total_failed: Decimal
    count_by_status: Dict[str, int]
    currency: str

# ─── SETTLEMENT REPORT SCHEMAS ───────────────────────────────────

class SettlementReportBase(BaseModel):
    report_type: ReportType = ReportType.DAILY
    period_start: datetime
    period_end: datetime
    platform_connection_id: Optional[UUID] = None

class SettlementReportCreate(SettlementReportBase):
    pass

class SettlementReportResponse(SettlementReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID
    total_orders: int
    total_sales: Decimal
    total_fees: Decimal
    total_refunds: Decimal
    total_payouts: Decimal
    net_revenue: Decimal
    platform_breakdown: Dict[str, Any]
    payment_method_breakdown: Dict[str, Any]
    file_url: Optional[str] = None
    file_format: Optional[str] = None
    is_final: bool
    generated_at: datetime
    created_at: datetime
    updated_at: datetime

class SettlementReportListParams(BaseModel):
    report_type: Optional[ReportType] = None
    platform_connection_id: Optional[UUID] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    is_final: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

# ─── RECONCILIATION ENGINE SCHEMAS ───────────────────────────────

class ReconciliationConfig(BaseModel):
    auto_resolve_minor: bool = Field(default=True, description="Auto-resolve discrepancies under threshold")
    minor_threshold: Decimal = Field(default=Decimal("0.1000"), ge=0, decimal_places=4)
    match_by_platform_id: bool = Field(default=True)
    match_by_amount: bool = Field(default=True)
    amount_tolerance: Decimal = Field(default=Decimal("0.0100"), ge=0, decimal_places=4)
    include_pending_orders: bool = Field(default=False)
    include_cancelled_orders: bool = Field(default=False)

class ReconciliationTrigger(BaseModel):
    platform_connection_id: Optional[UUID] = None  # None = all platforms
    date_from: datetime
    date_to: datetime
    config: ReconciliationConfig = Field(default_factory=ReconciliationConfig)

class ReconciliationResult(BaseModel):
    run_id: UUID
    status: ReconciliationRunStatus
    orders_checked: int
    orders_matched: int
    discrepancies_found: int
    discrepancies_auto_resolved: int
    total_variance: Decimal
    message: str

class ReconciliationPreview(BaseModel):
    """Preview of what reconciliation would find without executing."""
    would_create_run: bool
    estimated_orders: int
    estimated_discrepancies: int
    estimated_variance: Decimal
    platforms: List[UUID]
    date_from: datetime
    date_to: datetime

# ─── DASHBOARD / ANALYTICS SCHEMAS ─────────────────────────────────

class ReconciliationDashboard(BaseModel):
    period_start: datetime
    period_end: datetime

    # Ledger stats
    ledger_summary: LedgerSummaryResponse

    # Discrepancy stats
    discrepancy_summary: DiscrepancySummary

    # Payout stats
    payout_summary: PayoutSummary

    # Platform comparison
    platform_comparison: List[Dict[str, Any]]

    # Trends
    daily_trend: List[Dict[str, Any]]

class ExportFormat(str, Enum):
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"

class LedgerExportRequest(BaseModel):
    date_from: datetime
    date_to: datetime
    platform_connection_id: Optional[UUID] = None
    entry_type: Optional[LedgerEntryType] = None
    format: ExportFormat = ExportFormat.CSV
