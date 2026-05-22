"""
Phase 10 Tests — Sales Reports, Analytics & Insights
Run with: pytest tests/test_phase10_analytics.py -v
"""

import uuid
import pytest
from datetime import datetime, timedelta, date
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Order, OrderStatus, OrderTypeEnum,
    OrderItem, Customer, Merchant, PlatformConnection
)
from app.schemas.analytics import (
    ReportPeriod, ReportGranularity, SortOrder,
    SalesReportRequest, ItemPerformanceRequest,
    CustomerInsightsRequest, DeliveryReportRequest,
    ReconciliationReportRequest, DashboardRequest
)
from app.services.analytics_service import AnalyticsService, get_period_boundaries, get_previous_period_boundaries

# ─── FIXTURES ──────────────────────────────────────────────────────

@pytest.fixture
def merchant_id() -> uuid.UUID:
    return uuid.uuid4()

@pytest.fixture
def branch_id() -> uuid.UUID:
    return uuid.uuid4()

@pytest.fixture
async def seed_orders(db_session: AsyncSession, merchant_id: uuid.UUID, branch_id: uuid.UUID):
    """Create sample orders for analytics testing."""
    orders = []
    base_time = datetime.utcnow() - timedelta(days=5)

    for i in range(10):
        order = Order(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            branch_id=branch_id,
            order_number=f"ORD-{100+i}",
            status=OrderStatus.DELIVERED if i < 8 else OrderStatus.CANCELLED,
            order_type=OrderTypeEnum.delivery if i % 2 == 0 else OrderTypeEnum.dine_in,
            payment_method="cod" if i % 3 == 0 else "online",
            total=Decimal(str(25.0 + (i * 5))),
            subtotal=Decimal(str(23.0 + (i * 5))),
            tax_amount=Decimal("1.25"),
            discount_amount=Decimal("2.0") if i % 2 == 0 else Decimal("0"),
            customer_name=f"Customer {i}",
            customer_phone=f"+9733333{i:04d}",
            table_number=f"T-{i}" if i % 2 == 1 else None,
            created_at=base_time + timedelta(hours=i * 2),
            confirmed_at=base_time + timedelta(hours=i * 2, minutes=5),
            served_at=base_time + timedelta(hours=i * 2, minutes=25) if i < 8 else None,
            picked_up_at=base_time + timedelta(hours=i * 2, minutes=20) if i < 8 and i % 2 == 0 else None,
            delivered_at=base_time + timedelta(hours=i * 2, minutes=40) if i < 8 and i % 2 == 0 else None,
            priority=i % 3
        )
        db_session.add(order)
        orders.append(order)

    await db_session.flush()

    # Add items to orders
    for order in orders:
        for j in range(2):
            item = OrderItem(
                id=uuid.uuid4(),
                order_id=order.id,
                item_id=None,
                item_name_snapshot=f"Item {j} for {order.order_number}",
                quantity=1 + j,
                unit_price=Decimal(str(10.0 + j * 5)),
                total_price=Decimal(str((1 + j) * (10.0 + j * 5)))
            )
            db_session.add(item)

    await db_session.flush()
    return orders

# ─── DATE HELPER TESTS ─────────────────────────────────────────────

def test_get_period_boundaries_today():
    start, end = get_period_boundaries(ReportPeriod.TODAY)
    assert start.date() == datetime.utcnow().date()
    assert end == start + timedelta(days=1)

def test_get_period_boundaries_yesterday():
    start, end = get_period_boundaries(ReportPeriod.YESTERDAY)
    assert start.date() == (datetime.utcnow() - timedelta(days=1)).date()
    assert end.date() == datetime.utcnow().date()

def test_get_period_boundaries_this_week():
    start, end = get_period_boundaries(ReportPeriod.THIS_WEEK)
    assert start.weekday() == 0  # Monday
    assert end == start + timedelta(days=7)

def test_get_period_boundaries_this_month():
    start, end = get_period_boundaries(ReportPeriod.THIS_MONTH)
    assert start.day == 1
    assert end.day == 1
    assert end.month != start.month or end.year != start.year

def test_get_period_boundaries_custom():
    custom_start = datetime(2026, 5, 1)
    custom_end = datetime(2026, 5, 15)
    start, end = get_period_boundaries(ReportPeriod.CUSTOM, custom_start, custom_end)
    assert start == custom_start
    assert end == custom_end

def test_get_previous_period_boundaries():
    start = datetime(2026, 5, 10)
    end = datetime(2026, 5, 20)
    prev_start, prev_end = get_previous_period_boundaries(start, end)
    assert prev_end == start
    assert (prev_end - prev_start) == (end - start)

# ─── SALES REPORT TESTS ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_sales_report_summary(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = SalesReportRequest(period=ReportPeriod.CUSTOM, 
                                  date_from=datetime.utcnow() - timedelta(days=10),
                                  date_to=datetime.utcnow())

    report = await service.get_sales_report(merchant_id, request)

    assert report.summary.total_orders >= 8  # 8 delivered, 2 cancelled excluded
    assert report.summary.gross_sales > 0
    assert report.summary.avg_order_value > 0
    assert report.summary.currency == "BHD"
    assert len(report.by_hour) > 0
    assert len(report.by_day) > 0
    assert len(report.by_payment_method) > 0
    assert len(report.by_order_type) > 0

@pytest.mark.asyncio
async def test_sales_report_by_payment_method(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = SalesReportRequest(period=ReportPeriod.CUSTOM,
                                  date_from=datetime.utcnow() - timedelta(days=10),
                                  date_to=datetime.utcnow())

    report = await service.get_sales_report(merchant_id, request)

    total_pct = sum(p.percentage for p in report.by_payment_method)
    assert abs(total_pct - 100.0) < 0.1  # Should sum to ~100%

    for pm in report.by_payment_method:
        assert pm.orders >= 0
        assert pm.sales >= 0
        assert 0 <= pm.percentage <= 100

@pytest.mark.asyncio
async def test_sales_report_by_order_type(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = SalesReportRequest(period=ReportPeriod.CUSTOM,
                                  date_from=datetime.utcnow() - timedelta(days=10),
                                  date_to=datetime.utcnow())

    report = await service.get_sales_report(merchant_id, request)

    types = [o.order_type for o in report.by_order_type]
    assert "delivery" in types or "dine_in" in types

    for ot in report.by_order_type:
        assert ot.orders >= 0
        assert 0 <= ot.percentage <= 100

@pytest.mark.asyncio
async def test_sales_report_trend_data(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = SalesReportRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=10),
        date_to=datetime.utcnow(),
        granularity=ReportGranularity.DAILY
    )

    report = await service.get_sales_report(merchant_id, request)
    assert len(report.trend) > 0
    assert all("label" in d and "sales" in d for d in report.trend)

# ─── ITEM PERFORMANCE TESTS ────────────────────────────────────────

@pytest.mark.asyncio
async def test_item_performance_ranking(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = ItemPerformanceRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=10),
        date_to=datetime.utcnow(),
        sort_by="total_sold",
        sort_order=SortOrder.DESC
    )

    result = await service.get_item_performance(merchant_id, request)

    assert len(result.items) > 0
    assert result.total_items > 0
    assert result.total_revenue > 0
    assert result.total_sold > 0

    # Verify ranking
    for i, item in enumerate(result.items):
        assert item.popularity_rank == i + 1

    if result.items:
        assert result.top_performer is not None
        assert result.bottom_performer is not None

@pytest.mark.asyncio
async def test_item_performance_refund_rate(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = ItemPerformanceRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=10),
        date_to=datetime.utcnow()
    )

    result = await service.get_item_performance(merchant_id, request)

    for item in result.items:
        assert 0 <= item.refund_rate <= 100
        assert item.total_sold >= 0
        assert item.total_revenue >= 0

# ─── CUSTOMER INSIGHTS TESTS ─────────────────────────────────────

@pytest.mark.asyncio
async def test_customer_insights_basic(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = CustomerInsightsRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=10),
        date_to=datetime.utcnow()
    )

    result = await service.get_customer_insights(merchant_id, request)

    assert len(result.customers) > 0
    assert result.total_customers > 0
    assert result.avg_customer_lifetime_value >= 0
    assert result.avg_orders_per_customer >= 0

@pytest.mark.asyncio
async def test_customer_tiers(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = CustomerInsightsRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=10),
        date_to=datetime.utcnow()
    )

    result = await service.get_customer_insights(merchant_id, request)

    tiers = [c.lifetime_value_tier for c in result.customers]
    assert any(t in tiers for t in ["new", "regular", "loyal", "vip"])

    # New customers have exactly 1 order
    new_customers = [c for c in result.customers if c.lifetime_value_tier == "new"]
    for c in new_customers:
        assert c.total_orders == 1

@pytest.mark.asyncio
async def test_customer_retention_risk(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = CustomerInsightsRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=10),
        date_to=datetime.utcnow()
    )

    result = await service.get_customer_insights(merchant_id, request)

    for customer in result.customers:
        assert customer.retention_risk in ["low", "medium", "high", None]
        if customer.days_since_last_order is not None:
            assert customer.days_since_last_order >= 0

@pytest.mark.asyncio
async def test_customer_churned_count(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = CustomerInsightsRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=10),
        date_to=datetime.utcnow()
    )

    result = await service.get_customer_insights(merchant_id, request)
    assert result.churned_customers >= 0

# ─── DELIVERY REPORT TESTS ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_delivery_report_summary(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = DeliveryReportRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=10),
        date_to=datetime.utcnow()
    )

    result = await service.get_delivery_report(merchant_id, request)

    assert result.summary.total_delivery_orders >= 0
    assert 0 <= result.summary.on_time_rate <= 100
    assert 0 <= result.summary.late_rate <= 100
    assert result.summary.avg_delivery_time_seconds >= 0
    assert result.summary.avg_prep_time_seconds >= 0

@pytest.mark.asyncio
async def test_delivery_by_zone(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = DeliveryReportRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=10),
        date_to=datetime.utcnow()
    )

    result = await service.get_delivery_report(merchant_id, request)

    for zone in result.by_zone:
        assert zone.orders >= 0
        assert 0 <= zone.late_rate <= 100
        assert zone.avg_delivery_time_seconds >= 0

@pytest.mark.asyncio
async def test_delivery_trend(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = DeliveryReportRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=10),
        date_to=datetime.utcnow()
    )

    result = await service.get_delivery_report(merchant_id, request)

    assert len(result.trend) >= 0
    for t in result.trend:
        assert "date" in t
        assert "orders" in t
        assert "delivered" in t

# ─── DASHBOARD TESTS ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unified_dashboard(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)
    request = DashboardRequest(period=ReportPeriod.CUSTOM,
                                date_from=datetime.utcnow() - timedelta(days=10),
                                date_to=datetime.utcnow())

    result = await service.get_dashboard(merchant_id, request)

    assert result.period_start is not None
    assert result.period_end is not None
    assert len(result.kpis) >= 4
    assert len(result.charts) >= 3

    for kpi in result.kpis:
        assert kpi.label is not None
        assert kpi.value is not None
        assert kpi.change_direction in ["up", "down", "neutral"]

    for chart in result.charts:
        assert chart.title is not None
        assert chart.chart_type in ["line", "bar", "pie", "donut"]
        assert len(chart.data) >= 0

@pytest.mark.asyncio
async def test_dashboard_kpi_calculations(db_session: AsyncSession, merchant_id: uuid.UUID, seed_orders):
    service = AnalyticsService(db_session)

    # Current period
    current_request = DashboardRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=5),
        date_to=datetime.utcnow()
    )
    current = await service.get_dashboard(merchant_id, current_request)

    # Should have sales KPI
    sales_kpi = next((k for k in current.kpis if k.label == "Total Sales"), None)
    assert sales_kpi is not None
    assert sales_kpi.value >= 0

# ─── EDGE CASE TESTS ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_period(db_session: AsyncSession, merchant_id: uuid.UUID):
    """Test analytics with no orders in period."""
    service = AnalyticsService(db_session)

    # Future period with no data
    request = SalesReportRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() + timedelta(days=10),
        date_to=datetime.utcnow() + timedelta(days=20)
    )

    result = await service.get_sales_report(merchant_id, request)
    assert result.summary.total_orders == 0
    assert result.summary.gross_sales == Decimal("0")
    assert result.summary.avg_order_value == Decimal("0")
    assert len(result.by_hour) == 0

@pytest.mark.asyncio
async def test_single_order_period(db_session: AsyncSession, merchant_id: uuid.UUID):
    """Test analytics with exactly one order."""
    service = AnalyticsService(db_session)

    order = Order(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        order_number="ORD-SINGLE",
        status=OrderStatus.DELIVERED,
        order_type=OrderTypeEnum.dine_in,
        payment_method="cod",
        total=Decimal("50.0"),
        subtotal=Decimal("47.5"),
        tax_amount=Decimal("2.5"),
        created_at=datetime.utcnow() - timedelta(hours=1),
        confirmed_at=datetime.utcnow() - timedelta(minutes=50),
        served_at=datetime.utcnow() - timedelta(minutes=20)
    )
    db_session.add(order)
    await db_session.flush()

    request = SalesReportRequest(
        period=ReportPeriod.CUSTOM,
        date_from=datetime.utcnow() - timedelta(days=1),
        date_to=datetime.utcnow()
    )

    result = await service.get_sales_report(merchant_id, request)
    assert result.summary.total_orders == 1
    assert result.summary.gross_sales == Decimal("50.0")
    assert result.summary.avg_order_value == Decimal("50.0")
    assert len(result.by_payment_method) == 1
    assert result.by_payment_method[0].payment_method == "cod"
