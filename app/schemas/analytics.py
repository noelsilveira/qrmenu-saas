"""
Phase 10 Schemas — Sales Reports, Analytics & Insights
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

# ─── REPORT PERIOD ENUMS ───────────────────────────────────────────

class ReportPeriod(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_QUARTER = "this_quarter"
    THIS_YEAR = "this_year"
    CUSTOM = "custom"

class ReportGranularity(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

# ─── SALES REPORT SCHEMAS ────────────────────────────────────────

class SalesSummary(BaseModel):
    period_start: datetime
    period_end: datetime
    total_orders: int
    total_items_sold: int
    gross_sales: Decimal
    total_discounts: Decimal
    net_sales: Decimal
    total_tax: Decimal
    total_fees: Decimal
    total_refunds: Decimal
    total_tips: Decimal
    total_delayed: int = 0
    net_revenue: Decimal
    avg_order_value: Decimal
    avg_items_per_order: Decimal
    currency: str = "BHD"

class SalesByHour(BaseModel):
    hour: int  # 0-23
    orders: int
    sales: Decimal
    items: int

class SalesByDay(BaseModel):
    date: date
    day_name: str
    orders: int
    sales: Decimal
    items: int
    vs_previous_period: Optional[float] = None  # percentage change

class SalesByPaymentMethod(BaseModel):
    payment_method: str
    orders: int
    sales: Decimal
    percentage: float

class SalesByOrderType(BaseModel):
    order_type: str
    orders: int
    sales: Decimal
    percentage: float
    avg_prep_time_seconds: Optional[int] = None

class SalesByPlatform(BaseModel):
    platform: str  # direct, talabat, zomato, jahez
    orders: int
    sales: Decimal
    fees: Decimal
    net: Decimal
    percentage: float

class SalesReportResponse(BaseModel):
    summary: SalesSummary
    by_hour: List[SalesByHour]
    by_day: List[SalesByDay]
    by_payment_method: List[SalesByPaymentMethod]
    by_order_type: List[SalesByOrderType]
    by_platform: List[SalesByPlatform]
    trend: List[Dict[str, Any]]  # time series for charts

class SalesReportRequest(BaseModel):
    period: ReportPeriod = ReportPeriod.TODAY
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    branch_id: Optional[UUID] = None
    granularity: ReportGranularity = ReportGranularity.DAILY

# ─── ITEM PERFORMANCE SCHEMAS ────────────────────────────────────

class ItemPerformance(BaseModel):
    item_id: Optional[UUID] = None
    item_name: str
    category_name: Optional[str] = None
    total_sold: int
    total_revenue: Decimal
    total_refunded: int
    refund_rate: float  # percentage
    avg_prep_time_seconds: Optional[int] = None
    popularity_rank: int
    vs_previous_period: Optional[float] = None
    trend: str = "stable"  # up, down, stable

class ItemPerformanceRequest(BaseModel):
    period: ReportPeriod = ReportPeriod.THIS_MONTH
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    branch_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    sort_by: str = "total_sold"  # total_sold, revenue, refund_rate
    sort_order: SortOrder = SortOrder.DESC
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

class ItemPerformanceResponse(BaseModel):
    items: List[ItemPerformance]
    total_items: int
    total_revenue: Decimal
    total_sold: int
    top_performer: Optional[ItemPerformance] = None
    bottom_performer: Optional[ItemPerformance] = None

class ModifierPerformance(BaseModel):
    modifier_name: str
    total_selected: int
    attach_rate: float  # percentage of orders that include this modifier
    extra_revenue: Decimal

# ─── CUSTOMER INSIGHTS SCHEMAS ───────────────────────────────────

class CustomerInsight(BaseModel):
    customer_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    total_orders: int
    total_spent: Decimal
    avg_order_value: Decimal
    first_order_date: Optional[datetime] = None
    last_order_date: Optional[datetime] = None
    favorite_items: List[str] = Field(default_factory=list)
    favorite_order_type: Optional[str] = None
    lifetime_value_tier: str = "regular"  # new, regular, loyal, vip
    days_since_last_order: Optional[int] = None
    retention_risk: Optional[str] = None  # low, medium, high

class CustomerInsightsRequest(BaseModel):
    period: ReportPeriod = ReportPeriod.THIS_MONTH
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    tier: Optional[str] = None  # filter by tier
    min_orders: Optional[int] = None
    sort_by: str = "total_spent"
    sort_order: SortOrder = SortOrder.DESC
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

class CustomerInsightsResponse(BaseModel):
    customers: List[CustomerInsight]
    total_customers: int
    new_customers: int
    returning_customers: int
    churned_customers: int
    avg_customer_lifetime_value: Decimal
    avg_orders_per_customer: Decimal

class CustomerCohort(BaseModel):
    cohort_month: str  # YYYY-MM
    customers_acquired: int
    month_0_retention: float  # 100%
    month_1_retention: Optional[float] = None
    month_3_retention: Optional[float] = None
    month_6_retention: Optional[float] = None
    month_12_retention: Optional[float] = None

# ─── WHATSAPP ANALYTICS SCHEMAS ──────────────────────────────────

class WhatsAppMetric(BaseModel):
    total_messages_sent: int
    total_messages_delivered: int
    total_messages_read: int
    delivery_rate: float
    read_rate: float
    total_interactive_messages: int
    total_button_clicks: int
    total_list_selections: int
    acceptance_rate: float  # orders accepted via WhatsApp
    avg_response_time_seconds: Optional[int] = None
    opt_outs: int
    complaints: int

class WhatsAppAnalyticsRequest(BaseModel):
    period: ReportPeriod = ReportPeriod.THIS_MONTH
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None

class WhatsAppAnalyticsResponse(BaseModel):
    metrics: WhatsAppMetric
    by_template: List[Dict[str, Any]]  # per message template performance
    by_hour: List[Dict[str, Any]]
    by_day: List[Dict[str, Any]]

# ─── DELIVERY REPORT SCHEMAS ─────────────────────────────────────

class DeliveryMetric(BaseModel):
    total_delivery_orders: int
    total_delivered: int
    total_failed: int
    avg_delivery_time_seconds: int
    avg_prep_time_seconds: int
    avg_total_time_seconds: int  # prep + delivery
    on_time_rate: float  # percentage
    late_rate: float
    failed_rate: float
    avg_driver_rating: Optional[float] = None
    total_driver_distance_km: Optional[float] = None

class DeliveryByZone(BaseModel):
    zone_name: str
    orders: int
    avg_delivery_time_seconds: int
    avg_order_value: Decimal
    late_rate: float

class DeliveryByDriver(BaseModel):
    driver_id: UUID
    driver_name: str
    total_deliveries: int
    avg_delivery_time_seconds: int
    on_time_rate: float
    customer_rating: Optional[float] = None
    total_earnings: Optional[Decimal] = None

class DeliveryReportRequest(BaseModel):
    period: ReportPeriod = ReportPeriod.THIS_MONTH
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    zone_id: Optional[UUID] = None
    driver_id: Optional[UUID] = None

class DeliveryReportResponse(BaseModel):
    summary: DeliveryMetric
    by_zone: List[DeliveryByZone]
    by_driver: List[DeliveryByDriver]
    trend: List[Dict[str, Any]]

# ─── RECONCILIATION REPORT SCHEMAS ─────────────────────────────────

class ReconciliationReport(BaseModel):
    total_runs: int
    total_orders_checked: int
    total_orders_matched: int
    match_rate: float
    total_discrepancies: int
    total_discrepancies_resolved: int
    resolution_rate: float
    total_variance: Decimal
    avg_variance_per_run: Decimal
    by_platform: List[Dict[str, Any]]
    by_discrepancy_type: List[Dict[str, Any]]

class ReconciliationReportRequest(BaseModel):
    period: ReportPeriod = ReportPeriod.THIS_MONTH
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    platform_connection_id: Optional[UUID] = None

# ─── UNIFIED DASHBOARD SCHEMAS ───────────────────────────────────

class DashboardKPI(BaseModel):
    label: str
    value: Decimal
    change_percent: Optional[float] = None
    change_direction: str = "neutral"  # up, down, neutral
    period: str

class DashboardChart(BaseModel):
    title: str
    chart_type: str  # line, bar, pie, donut
    data: List[Dict[str, Any]]
    labels: List[str]
    colors: Optional[List[str]] = None

class UnifiedDashboardResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    kpis: List[DashboardKPI]
    charts: List[DashboardChart]
    alerts: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)

class DashboardRequest(BaseModel):
    period: ReportPeriod = ReportPeriod.TODAY
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    branch_id: Optional[UUID] = None

# ─── EXPORT SCHEMAS ──────────────────────────────────────────────

class ReportExportRequest(BaseModel):
    report_type: str  # sales, items, customers, whatsapp, delivery, reconciliation
    period: ReportPeriod = ReportPeriod.THIS_MONTH
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    format: str = "csv"  # csv, xlsx, pdf
    branch_id: Optional[UUID] = None
    filters: Optional[Dict[str, Any]] = None

class ReportExportResponse(BaseModel):
    download_url: str
    file_format: str
    file_size_bytes: int
    generated_at: datetime
    expires_at: datetime
