"""
Phase 10 Service — Sales Reports, Analytics & Insights Engine
"""

import uuid
from datetime import datetime, timedelta, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
from sqlalchemy import select, and_, or_, func, desc, asc, cast, Date, extract, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Order, OrderStatus, OrderTypeEnum, OrderItem,
    Customer,
    PlatformConnection,
    Driver, DeliveryZone,
    FinancialLedger, LedgerEntryType,
    ReconciliationRun,
    Discrepancy, DiscrepancyType, DiscrepancyStatus,
)
from app.schemas.analytics import (
    ReportPeriod, ReportGranularity, SortOrder,
    SalesSummary, SalesByHour, SalesByDay, SalesByPaymentMethod,
    SalesByOrderType, SalesByPlatform, SalesReportResponse, SalesReportRequest,
    ItemPerformance, ItemPerformanceRequest, ItemPerformanceResponse, ModifierPerformance,
    CustomerInsight, CustomerInsightsRequest, CustomerInsightsResponse, CustomerCohort,
    WhatsAppMetric, WhatsAppAnalyticsRequest, WhatsAppAnalyticsResponse,
    DeliveryMetric, DeliveryByZone, DeliveryByDriver,
    DeliveryReportRequest, DeliveryReportResponse,
    ReconciliationReport, ReconciliationReportRequest,
    DashboardKPI, DashboardChart, UnifiedDashboardResponse, DashboardRequest
)

# ─── DATE HELPERS ────────────────────────────────────────────────

def get_period_boundaries(period: ReportPeriod, 
                           date_from: Optional[datetime] = None,
                           date_to: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """Convert ReportPeriod enum to actual datetime boundaries."""
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == ReportPeriod.TODAY:
        return today, today + timedelta(days=1)
    elif period == ReportPeriod.YESTERDAY:
        yesterday = today - timedelta(days=1)
        return yesterday, today
    elif period == ReportPeriod.THIS_WEEK:
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=7)
    elif period == ReportPeriod.LAST_WEEK:
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=7)
    elif period == ReportPeriod.THIS_MONTH:
        start = today.replace(day=1)
        return start, (start + timedelta(days=32)).replace(day=1)
    elif period == ReportPeriod.LAST_MONTH:
        end = today.replace(day=1)
        start = (end - timedelta(days=1)).replace(day=1)
        return start, end
    elif period == ReportPeriod.THIS_QUARTER:
        quarter = (today.month - 1) // 3
        start = today.replace(month=quarter * 3 + 1, day=1)
        return start, (start + timedelta(days=95)).replace(day=1)
    elif period == ReportPeriod.THIS_YEAR:
        start = today.replace(month=1, day=1)
        return start, start.replace(year=start.year + 1)
    elif period == ReportPeriod.CUSTOM and date_from and date_to:
        return date_from, date_to

    return today - timedelta(days=30), today + timedelta(days=1)

def get_previous_period_boundaries(start: datetime, end: datetime) -> Tuple[datetime, datetime]:
    """Get the same-length period before the given one."""
    duration = end - start
    prev_end = start
    prev_start = prev_end - duration
    return prev_start, prev_end

# ─── ANALYTICS SERVICE ───────────────────────────────────────────

class AnalyticsService:
    """
    Unified analytics and reporting engine.

    Generates:
    - Sales reports (hourly, daily, by payment, by type, by platform)
    - Item performance rankings
    - Customer insights and cohort analysis
    - WhatsApp messaging analytics
    - Delivery performance metrics
    - Reconciliation summaries
    - Unified dashboard with KPIs and charts
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── SALES REPORTS ─────────────────────────────────────────────

    async def get_sales_report(self, merchant_id: uuid.UUID, 
                                request: SalesReportRequest) -> SalesReportResponse:
        """Generate comprehensive sales report."""
        start, end = get_period_boundaries(request.period, request.date_from, request.date_to)

        # Base query
        base_query = select(Order).where(
            Order.merchant_id == merchant_id,
            Order.created_at >= start,
            Order.created_at < end,
            Order.status.notin_([OrderStatus.CANCELLED, OrderStatus.PENDING])
        )
        if request.branch_id:
            base_query = base_query.where(Order.branch_id == request.branch_id)

        result = await self.db.execute(base_query)
        orders = result.scalars().all()

        # Summary
        total_orders = len(orders)
        gross_sales = sum(Decimal(str(o.total or 0)) for o in orders)
        total_tax = sum(Decimal(str(o.tax_amount or 0)) for o in orders)
        total_discounts = sum(Decimal(str(o.discount_amount or 0)) for o in orders)
        total_tips = Decimal("0")  # tip_amount field doesn't exist on Order
        net_sales = gross_sales - total_discounts

        # Count items
        item_count = 0
        for o in orders:
            items_result = await self.db.execute(
                select(func.sum(OrderItem.quantity)).where(OrderItem.order_id == o.id)
            )
            item_count += items_result.scalar() or 0

        # By hour
        hourly = defaultdict(lambda: {"orders": 0, "sales": Decimal("0"), "items": 0})
        for o in orders:
            hour = o.created_at.hour if o.created_at else 0
            hourly[hour]["orders"] += 1
            hourly[hour]["sales"] += Decimal(str(o.total or 0))

        by_hour = [
            SalesByHour(hour=h, orders=d["orders"], sales=d["sales"], items=0)
            for h, d in sorted(hourly.items())
        ]

        # By day
        daily = defaultdict(lambda: {"orders": 0, "sales": Decimal("0"), "items": 0})
        for o in orders:
            d = o.created_at.date() if o.created_at else date.today()
            daily[d]["orders"] += 1
            daily[d]["sales"] += Decimal(str(o.total or 0))

        by_day = []
        for d, data in sorted(daily.items()):
            day_name = d.strftime("%A")
            by_day.append(SalesByDay(
                date=d, day_name=day_name,
                orders=data["orders"], sales=data["sales"], items=0
            ))

        # By payment method
        payment_methods = defaultdict(lambda: {"orders": 0, "sales": Decimal("0")})
        for o in orders:
            pm = str(o.payment_method) if o.payment_method else "unknown"
            payment_methods[pm]["orders"] += 1
            payment_methods[pm]["sales"] += Decimal(str(o.total or 0))

        total_sales_for_pct = gross_sales if gross_sales > 0 else Decimal("1")
        by_payment = [
            SalesByPaymentMethod(
                payment_method=pm,
                orders=d["orders"],
                sales=d["sales"],
                percentage=round(float(d["sales"] / total_sales_for_pct * 100), 2)
            )
            for pm, d in payment_methods.items()
        ]

        # By order type
        order_types = defaultdict(lambda: {"orders": 0, "sales": Decimal("0"), "prep_times": []})
        for o in orders:
            ot = o.order_type.value if hasattr(o.order_type, 'value') else str(o.order_type)
            order_types[ot]["orders"] += 1
            order_types[ot]["sales"] += Decimal(str(o.total or 0))
            if o.served_at and o.confirmed_at:
                order_types[ot]["prep_times"].append((o.served_at - o.confirmed_at).total_seconds())

        by_order_type = []
        for ot, d in order_types.items():
            avg_prep = int(sum(d["prep_times"]) / len(d["prep_times"])) if d["prep_times"] else None
            by_order_type.append(SalesByOrderType(
                order_type=ot,
                orders=d["orders"],
                sales=d["sales"],
                percentage=round(float(d["sales"] / total_sales_for_pct * 100), 2),
                avg_prep_time_seconds=avg_prep
            ))

        # By platform
        platforms = defaultdict(lambda: {"orders": 0, "sales": Decimal("0"), "fees": Decimal("0")})
        for o in orders:
            if o.platform_connection_id:
                plat = "3rd_party"  # Simplified; enhance with platform name lookup
            else:
                plat = "direct"
            platforms[plat]["orders"] += 1
            platforms[plat]["sales"] += Decimal(str(o.total or 0))

        by_platform = [
            SalesByPlatform(
                platform=p,
                orders=d["orders"],
                sales=d["sales"],
                fees=d["fees"],
                net=d["sales"] - d["fees"],
                percentage=round(float(d["sales"] / total_sales_for_pct * 100), 2)
            )
            for p, d in platforms.items()
        ]

        # Trend data
        trend = []
        if request.granularity == ReportGranularity.HOURLY:
            for h, d in sorted(hourly.items()):
                trend.append({"label": f"{h:02d}:00", "orders": d["orders"], "sales": float(d["sales"])})
        else:
            for d, data in sorted(daily.items()):
                trend.append({"label": d.isoformat(), "orders": data["orders"], "sales": float(data["sales"])})

        summary = SalesSummary(
            period_start=start,
            period_end=end,
            total_orders=total_orders,
            total_items_sold=item_count,
            gross_sales=gross_sales,
            total_discounts=total_discounts,
            net_sales=net_sales,
            total_tax=total_tax,
            total_fees=Decimal("0"),  # From ledger in v2.0
            total_refunds=Decimal("0"),
            total_tips=total_tips,
            total_delayed=0,
            net_revenue=net_sales + total_tax + total_tips,
            avg_order_value=round(gross_sales / total_orders, 4) if total_orders > 0 else Decimal("0"),
            avg_items_per_order=round(item_count / total_orders, 2) if total_orders > 0 else Decimal("0"),
            currency="BHD"
        )

        return SalesReportResponse(
            summary=summary,
            by_hour=by_hour,
            by_day=by_day,
            by_payment_method=by_payment,
            by_order_type=by_order_type,
            by_platform=by_platform,
            trend=trend
        )

    # ─── ITEM PERFORMANCE ────────────────────────────────────────

    async def get_item_performance(self, merchant_id: uuid.UUID,
                                    request: ItemPerformanceRequest) -> ItemPerformanceResponse:
        """Analyze item sales performance."""
        start, end = get_period_boundaries(request.period, request.date_from, request.date_to)

        # Aggregate order items
        query = select(
            OrderItem.item_id,
            OrderItem.item_name_snapshot.label("item_name"),
            func.coalesce(func.sum(OrderItem.quantity), 0).label("total_sold"),
            func.coalesce(func.sum(OrderItem.total_price), Decimal("0")).label("total_revenue"),
            func.count(func.distinct(OrderItem.order_id)).label("order_count")
        ).join(Order).where(
            Order.merchant_id == merchant_id,
            Order.created_at >= start,
            Order.created_at < end,
            Order.status.notin_([OrderStatus.CANCELLED])
        )

        if request.branch_id:
            query = query.where(Order.branch_id == request.branch_id)

        query = query.group_by(OrderItem.item_id, OrderItem.item_name_snapshot)

        if request.sort_by == "total_sold":
            query = query.order_by(desc("total_sold") if request.sort_order == SortOrder.DESC else asc("total_sold"))
        elif request.sort_by == "revenue":
            query = query.order_by(desc("total_revenue") if request.sort_order == SortOrder.DESC else asc("total_revenue"))

        result = await self.db.execute(query)
        rows = result.all()

        items = []
        total_revenue = Decimal("0")
        total_sold = 0

        for rank, row in enumerate(rows, 1):
            total_revenue += row.total_revenue
            total_sold += row.total_sold

            # Calculate refund rate
            refund_result = await self.db.execute(
                select(func.coalesce(func.sum(OrderItem.quantity), 0)).
                join(Order).where(
                    OrderItem.item_id == row.item_id,
                    Order.merchant_id == merchant_id,
                    Order.created_at >= start,
                    Order.created_at < end,
                    Order.status == OrderStatus.CANCELLED
                )
            )
            refunded = refund_result.scalar() or 0
            refund_rate = round(refunded / (row.total_sold + refunded) * 100, 2) if (row.total_sold + refunded) > 0 else 0

            items.append(ItemPerformance(
                item_id=row.item_id,
                item_name=row.item_name,
                total_sold=row.total_sold,
                total_revenue=row.total_revenue,
                total_refunded=refunded,
                refund_rate=refund_rate,
                popularity_rank=rank,
                trend="stable"
            ))

        return ItemPerformanceResponse(
            items=items,
            total_items=len(items),
            total_revenue=total_revenue,
            total_sold=total_sold,
            top_performer=items[0] if items else None,
            bottom_performer=items[-1] if items else None
        )

    # ─── CUSTOMER INSIGHTS ───────────────────────────────────────

    async def get_customer_insights(self, merchant_id: uuid.UUID,
                                     request: CustomerInsightsRequest) -> CustomerInsightsResponse:
        """Analyze customer behavior and segments."""
        start, end = get_period_boundaries(request.period, request.date_from, request.date_to)

        # Get all customers with orders in period
        query = select(
            Order.customer_id,
            Order.customer_name,
            Order.customer_phone,
            func.count(Order.id).label("total_orders"),
            func.coalesce(func.sum(Order.total), Decimal("0")).label("total_spent"),
            func.min(Order.created_at).label("first_order"),
            func.max(Order.created_at).label("last_order")
        ).where(
            Order.merchant_id == merchant_id,
            Order.created_at >= start,
            Order.created_at < end,
            Order.status.notin_([OrderStatus.CANCELLED])
        ).group_by(Order.customer_id, Order.customer_name, Order.customer_phone)

        if request.min_orders:
            query = query.having(func.count(Order.id) >= request.min_orders)

        if request.sort_by == "total_spent":
            query = query.order_by(desc("total_spent") if request.sort_order == SortOrder.DESC else asc("total_spent"))
        elif request.sort_by == "total_orders":
            query = query.order_by(desc("total_orders") if request.sort_order == SortOrder.DESC else asc("total_orders"))

        result = await self.db.execute(query)
        rows = result.all()

        customers = []
        now = datetime.utcnow()
        total_customers = len(rows)
        new_customers = 0
        returning_customers = 0

        for row in rows:
            days_since = (now - row.last_order).days if row.last_order else None

            # Determine tier
            if row.total_orders == 1:
                tier = "new"
                new_customers += 1
            elif row.total_orders >= 10 and row.total_spent >= Decimal("500"):
                tier = "vip"
                returning_customers += 1
            elif row.total_orders >= 5:
                tier = "loyal"
                returning_customers += 1
            else:
                tier = "regular"
                returning_customers += 1

            # Retention risk
            risk = None
            if days_since is not None:
                if days_since > 60:
                    risk = "high"
                elif days_since > 30:
                    risk = "medium"
                else:
                    risk = "low"

            avg_order = round(row.total_spent / row.total_orders, 4) if row.total_orders > 0 else Decimal("0")

            customers.append(CustomerInsight(
                customer_id=row.customer_id,
                customer_name=row.customer_name,
                customer_phone=row.customer_phone,
                total_orders=row.total_orders,
                total_spent=row.total_spent,
                avg_order_value=avg_order,
                first_order_date=row.first_order,
                last_order_date=row.last_order,
                lifetime_value_tier=tier,
                days_since_last_order=days_since,
                retention_risk=risk
            ))

        # Calculate churned (ordered before period, not in period)
        churned_result = await self.db.execute(
            select(func.count(func.distinct(Order.customer_id))).where(
                Order.merchant_id == merchant_id,
                Order.created_at < start,
                Order.status.notin_([OrderStatus.CANCELLED]),
                Order.customer_id.notin_(
                    select(Order.customer_id).where(
                        Order.merchant_id == merchant_id,
                        Order.created_at >= start,
                        Order.created_at < end
                    )
                )
            )
        )
        churned = churned_result.scalar() or 0

        avg_ltv = round(sum(c.total_spent for c in customers) / len(customers), 4) if customers else Decimal("0")
        avg_orders = round(sum(c.total_orders for c in customers) / len(customers), 2) if customers else Decimal("0")

        return CustomerInsightsResponse(
            customers=customers,
            total_customers=total_customers,
            new_customers=new_customers,
            returning_customers=returning_customers,
            churned_customers=churned,
            avg_customer_lifetime_value=avg_ltv,
            avg_orders_per_customer=avg_orders
        )

    # ─── WHATSAPP ANALYTICS ──────────────────────────────────────

    async def get_whatsapp_analytics(self, merchant_id: uuid.UUID,
                                      request: WhatsAppAnalyticsRequest) -> WhatsAppAnalyticsResponse:
        """Analyze WhatsApp messaging performance."""
        # WhatsAppMessage model not available — return empty placeholder data
        return WhatsAppAnalyticsResponse(
            metrics=WhatsAppMetric(
                total_messages_sent=0,
                total_messages_delivered=0,
                total_messages_read=0,
                delivery_rate=0,
                read_rate=0,
                total_interactive_messages=0,
                total_button_clicks=0,
                total_list_selections=0,
                acceptance_rate=0,
                opt_outs=0,
                complaints=0
            ),
            by_template=[],
            by_hour=[],
            by_day=[]
        )

    # ─── DELIVERY REPORTS ────────────────────────────────────────

    async def get_delivery_report(self, merchant_id: uuid.UUID,
                                   request: DeliveryReportRequest) -> DeliveryReportResponse:
        """Analyze delivery performance."""
        start, end = get_period_boundaries(request.period, request.date_from, request.date_to)

        query = select(Order).where(
            Order.merchant_id == merchant_id,
            Order.created_at >= start,
            Order.created_at < end,
            Order.order_type == OrderTypeEnum.delivery,
            Order.status.notin_([OrderStatus.CANCELLED, OrderStatus.PENDING])
        )

        if request.zone_id:
            query = query.where(Order.delivery_zone_id == request.zone_id)
        if request.driver_id:
            query = query.where(Order.driver_id == request.driver_id)

        result = await self.db.execute(query)
        orders = result.scalars().all()

        total = len(orders)
        delivered = sum(1 for o in orders if o.status == OrderStatus.DELIVERED)
        failed = sum(1 for o in orders if o.status == OrderStatus.REFUNDED)

        # Delivery times
        delivery_times = []
        prep_times = []
        total_times = []

        for o in orders:
            if o.delivered_at and o.picked_up_at:
                delivery_times.append((o.delivered_at - o.picked_up_at).total_seconds())
            if o.picked_up_at and o.confirmed_at:
                prep_times.append((o.picked_up_at - o.confirmed_at).total_seconds())
            if o.delivered_at and o.created_at:
                total_times.append((o.delivered_at - o.created_at).total_seconds())

        avg_delivery = int(sum(delivery_times) / len(delivery_times)) if delivery_times else 0
        avg_prep = int(sum(prep_times) / len(prep_times)) if prep_times else 0
        avg_total = int(sum(total_times) / len(total_times)) if total_times else 0

        # On-time calculation (assume 45 min SLA for delivery)
        on_time = sum(1 for t in total_times if t <= 2700)
        on_time_rate = round(on_time / len(total_times) * 100, 2) if total_times else 0

        # By zone
        zones = defaultdict(lambda: {"orders": 0, "delivery_times": [], "sales": Decimal("0")})
        for o in orders:
            zone = o.delivery_zone_id or "unknown"
            zones[zone]["orders"] += 1
            zones[zone]["sales"] += Decimal(str(o.total or 0))
            if o.delivered_at and o.picked_up_at:
                zones[zone]["delivery_times"].append((o.delivered_at - o.picked_up_at).total_seconds())

        by_zone = []
        for zone_id, data in zones.items():
            avg_dt = int(sum(data["delivery_times"]) / len(data["delivery_times"])) if data["delivery_times"] else 0
            late = sum(1 for t in data["delivery_times"] if t > 2700)
            late_rate = round(late / len(data["delivery_times"]) * 100, 2) if data["delivery_times"] else 0
            by_zone.append(DeliveryByZone(
                zone_name=str(zone_id),
                orders=data["orders"],
                avg_delivery_time_seconds=avg_dt,
                avg_order_value=round(data["sales"] / data["orders"], 4) if data["orders"] > 0 else Decimal("0"),
                late_rate=late_rate
            ))

        # By driver
        drivers = defaultdict(lambda: {"deliveries": 0, "delivery_times": [], "ratings": []})
        for o in orders:
            if o.driver_id:
                drivers[o.driver_id]["deliveries"] += 1
                if o.delivered_at and o.picked_up_at:
                    drivers[o.driver_id]["delivery_times"].append((o.delivered_at - o.picked_up_at).total_seconds())

        by_driver = []
        for driver_id, data in drivers.items():
            avg_dt = int(sum(data["delivery_times"]) / len(data["delivery_times"])) if data["delivery_times"] else 0
            on_time = sum(1 for t in data["delivery_times"] if t <= 2700)
            ot_rate = round(on_time / len(data["delivery_times"]) * 100, 2) if data["delivery_times"] else 0

            # Get driver name
            driver_result = await self.db.execute(
                select(Driver).where(Driver.id == driver_id)
            )
            driver = driver_result.scalar_one_or_none()

            by_driver.append(DeliveryByDriver(
                driver_id=driver_id,
                driver_name=driver.name if driver else "Unknown",
                total_deliveries=data["deliveries"],
                avg_delivery_time_seconds=avg_dt,
                on_time_rate=ot_rate,
                customer_rating=None,
                total_earnings=None
            ))

        # Trend
        daily = defaultdict(lambda: {"orders": 0, "delivered": 0, "avg_time": []})
        for o in orders:
            d = o.created_at.date() if o.created_at else date.today()
            daily[d]["orders"] += 1
            if o.status == OrderStatus.DELIVERED:
                daily[d]["delivered"] += 1
            if o.delivered_at and o.picked_up_at:
                daily[d]["avg_time"].append((o.delivered_at - o.picked_up_at).total_seconds())

        trend = []
        for d, data in sorted(daily.items()):
            avg_t = int(sum(data["avg_time"]) / len(data["avg_time"])) if data["avg_time"] else 0
            trend.append({
                "date": d.isoformat(),
                "orders": data["orders"],
                "delivered": data["delivered"],
                "avg_delivery_seconds": avg_t
            })

        summary = DeliveryMetric(
            total_delivery_orders=total,
            total_delivered=delivered,
            total_failed=failed,
            avg_delivery_time_seconds=avg_delivery,
            avg_prep_time_seconds=avg_prep,
            avg_total_time_seconds=avg_total,
            on_time_rate=on_time_rate,
            late_rate=round(100 - on_time_rate, 2),
            failed_rate=round(failed / total * 100, 2) if total > 0 else 0,
            avg_driver_rating=None,
            total_driver_distance_km=None
        )

        return DeliveryReportResponse(
            summary=summary,
            by_zone=by_zone,
            by_driver=by_driver,
            trend=trend
        )

    # ─── RECONCILIATION REPORT ───────────────────────────────────

    async def get_reconciliation_report(self, merchant_id: uuid.UUID,
                                         request: ReconciliationReportRequest) -> ReconciliationReport:
        """Summarize reconciliation activity."""
        start, end = get_period_boundaries(request.period, request.date_from, request.date_to)

        query = select(ReconciliationRun).where(
            ReconciliationRun.merchant_id == merchant_id,
            ReconciliationRun.created_at >= start,
            ReconciliationRun.created_at < end
        )

        if request.platform_connection_id:
            query = query.where(ReconciliationRun.platform_connection_id == request.platform_connection_id)

        result = await self.db.execute(query)
        runs = result.scalars().all()

        total_runs = len(runs)
        total_checked = sum(r.total_orders_checked for r in runs)
        total_matched = sum(r.total_orders_matched for r in runs)
        match_rate = round(total_matched / total_checked * 100, 2) if total_checked > 0 else 0

        total_disc = sum(r.total_discrepancies_found for r in runs)
        total_resolved = sum(r.total_discrepancies_resolved for r in runs)
        resolution_rate = round(total_resolved / total_disc * 100, 2) if total_disc > 0 else 0

        total_variance = sum(r.total_variance for r in runs)
        avg_variance = round(total_variance / total_runs, 4) if total_runs > 0 else Decimal("0")

        # By platform
        by_platform = defaultdict(lambda: {"runs": 0, "discrepancies": 0})
        for r in runs:
            pid = str(r.platform_connection_id) if r.platform_connection_id else "all"
            by_platform[pid]["runs"] += 1
            by_platform[pid]["discrepancies"] += r.total_discrepancies_found

        # By discrepancy type
        disc_query = select(
            Discrepancy.discrepancy_type,
            func.count(Discrepancy.id).label("count")
        ).where(
            Discrepancy.merchant_id == merchant_id,
            Discrepancy.created_at >= start,
            Discrepancy.created_at < end
        ).group_by(Discrepancy.discrepancy_type)

        disc_result = await self.db.execute(disc_query)
        by_type = [{"type": r.discrepancy_type, "count": r.count} for r in disc_result.all()]

        return ReconciliationReport(
            total_runs=total_runs,
            total_orders_checked=total_checked,
            total_orders_matched=total_matched,
            match_rate=match_rate,
            total_discrepancies=total_disc,
            total_discrepancies_resolved=total_resolved,
            resolution_rate=resolution_rate,
            total_variance=total_variance,
            avg_variance_per_run=avg_variance,
            by_platform=[{"platform": k, **v} for k, v in by_platform.items()],
            by_discrepancy_type=by_type
        )

    # ─── UNIFIED DASHBOARD ───────────────────────────────────────

    async def get_dashboard(self, merchant_id: uuid.UUID,
                            request: DashboardRequest) -> UnifiedDashboardResponse:
        """Generate unified merchant dashboard."""
        start, end = get_period_boundaries(request.period, request.date_from, request.date_to)

        # Previous period for comparison
        prev_start, prev_end = get_previous_period_boundaries(start, end)

        # Current period sales
        sales = await self.get_sales_report(merchant_id, SalesReportRequest(
            period=ReportPeriod.CUSTOM, date_from=start, date_to=end,
            branch_id=request.branch_id
        ))

        # Previous period sales
        prev_sales = await self.get_sales_report(merchant_id, SalesReportRequest(
            period=ReportPeriod.CUSTOM, date_from=prev_start, date_to=prev_end,
            branch_id=request.branch_id
        ))

        # Calculate changes
        def calc_change(current: Decimal, previous: Decimal) -> Tuple[float, str]:
            if previous == 0:
                return (0, "neutral") if current == 0 else (100, "up")
            pct = round(float((current - previous) / previous * 100), 2)
            direction = "up" if pct > 0 else "down" if pct < 0 else "neutral"
            return pct, direction

        sales_change, sales_dir = calc_change(sales.summary.gross_sales, prev_sales.summary.gross_sales)
        orders_change, orders_dir = calc_change(Decimal(sales.summary.total_orders), Decimal(prev_sales.summary.total_orders))
        aov_change, aov_dir = calc_change(sales.summary.avg_order_value, prev_sales.summary.avg_order_value)

        kpis = [
            DashboardKPI(label="Total Sales", value=sales.summary.gross_sales, 
                         change_percent=sales_change, change_direction=sales_dir, period="vs previous"),
            DashboardKPI(label="Total Orders", value=Decimal(sales.summary.total_orders),
                         change_percent=orders_change, change_direction=orders_dir, period="vs previous"),
            DashboardKPI(label="Avg Order Value", value=sales.summary.avg_order_value,
                         change_percent=aov_change, change_direction=aov_dir, period="vs previous"),
            DashboardKPI(label="Net Revenue", value=sales.summary.net_revenue,
                         change_percent=0, change_direction="neutral", period="current"),
        ]

        # Charts
        charts = [
            DashboardChart(
                title="Sales Trend",
                chart_type="line",
                data=sales.trend,
                labels=[d["label"] for d in sales.trend]
            ),
            DashboardChart(
                title="Sales by Payment Method",
                chart_type="donut",
                data=[{"label": p.payment_method, "value": float(p.sales)} for p in sales.by_payment_method],
                labels=[p.payment_method for p in sales.by_payment_method]
            ),
            DashboardChart(
                title="Sales by Order Type",
                chart_type="bar",
                data=[{"label": o.order_type, "value": float(o.sales)} for o in sales.by_order_type],
                labels=[o.order_type for o in sales.by_order_type]
            ),
        ]

        # Alerts
        alerts = []
        if sales.summary.total_delayed > 0:
            alerts.append(f"{sales.summary.total_delayed} orders are currently delayed")

        # Recommendations
        recommendations = []
        if sales_dir == "down" and sales_change < -10:
            recommendations.append("Sales are down significantly. Consider a promotional campaign.")

        return UnifiedDashboardResponse(
            period_start=start,
            period_end=end,
            kpis=kpis,
            charts=charts,
            alerts=alerts,
            recommendations=recommendations
        )
