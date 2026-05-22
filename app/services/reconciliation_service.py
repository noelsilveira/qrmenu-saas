"""
Phase 8 Service — Reconciliation & Financial Ledger Engine
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, and_, or_, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    FinancialLedger, LedgerEntryType, LedgerEntryStatus,
    ReconciliationRun, ReconciliationRunStatus,
    Discrepancy, DiscrepancyType, DiscrepancyStatus,
    Payout, PayoutStatus,
    SettlementReport, ReportType,
    Order, OrderStatus, PlatformConnection
)
from app.schemas.reconciliation import (
    LedgerEntryCreate, LedgerEntryUpdate, LedgerListParams,
    ReconciliationRunCreate, ReconciliationConfig,
    DiscrepancyCreate, DiscrepancyUpdate, DiscrepancyResolve, DiscrepancyListParams,
    PayoutCreate, PayoutUpdate, PayoutListParams,
    SettlementReportCreate, SettlementReportListParams,
    ReconciliationResult, ReconciliationPreview,
    LedgerSummary, LedgerSummaryByType, LedgerSummaryResponse,
    DiscrepancySummary, PayoutSummary
)

# ─── CONSTANTS ─────────────────────────────────────────────────────

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")

# ─── LEDGER SERVICE ────────────────────────────────────────────────

class LedgerService:
    """Manages the immutable financial ledger."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_entry(self, merchant_id: uuid.UUID, data: LedgerEntryCreate) -> FinancialLedger:
        """Create a new immutable ledger entry."""
        entry = FinancialLedger(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            **data.model_dump(exclude_unset=True)
        )
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        return entry

    async def get_entry(self, merchant_id: uuid.UUID, entry_id: uuid.UUID) -> Optional[FinancialLedger]:
        result = await self.db.execute(
            select(FinancialLedger)
            .where(FinancialLedger.id == entry_id, FinancialLedger.merchant_id == merchant_id)
        )
        return result.scalar_one_or_none()

    async def list_entries(self, merchant_id: uuid.UUID, params: LedgerListParams) -> Tuple[List[FinancialLedger], int]:
        query = select(FinancialLedger).where(FinancialLedger.merchant_id == merchant_id)

        if params.entry_type:
            query = query.where(FinancialLedger.entry_type == params.entry_type.value)
        if params.status:
            query = query.where(FinancialLedger.status == params.status.value)
        if params.platform_connection_id:
            query = query.where(FinancialLedger.platform_connection_id == params.platform_connection_id)
        if params.order_id:
            query = query.where(FinancialLedger.order_id == params.order_id)
        if params.date_from:
            query = query.where(FinancialLedger.transaction_date >= params.date_from)
        if params.date_to:
            query = query.where(FinancialLedger.transaction_date <= params.date_to)

        # Count
        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar()

        # Paginate
        query = query.order_by(desc(FinancialLedger.transaction_date))
        query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)

        result = await self.db.execute(query)
        return result.scalars().all(), total

    async def update_entry_status(self, merchant_id: uuid.UUID, entry_id: uuid.UUID, 
                                   data: LedgerEntryUpdate) -> Optional[FinancialLedger]:
        entry = await self.get_entry(merchant_id, entry_id)
        if not entry:
            return None

        if data.status:
            entry.status = data.status.value
        if data.description:
            entry.description = data.description
        if data.metadata:
            entry.meta_data = {**(entry.meta_data or {}), **data.metadata}

        entry.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(entry)
        return entry

    async def get_summary(self, merchant_id: uuid.UUID, date_from: datetime, date_to: datetime,
                          platform_connection_id: Optional[uuid.UUID] = None) -> LedgerSummaryResponse:
        """Aggregate ledger summary for a period."""

        base_query = select(FinancialLedger).where(
            FinancialLedger.merchant_id == merchant_id,
            FinancialLedger.transaction_date >= date_from,
            FinancialLedger.transaction_date <= date_to
        )
        if platform_connection_id:
            base_query = base_query.where(FinancialLedger.platform_connection_id == platform_connection_id)

        subq = base_query.subquery()

        # Overall totals
        overall_result = await self.db.execute(
            select(
                func.coalesce(func.sum(subq.c.gross_amount), Decimal("0")).label("total_gross"),
                func.coalesce(func.sum(subq.c.fee_amount), Decimal("0")).label("total_fees"),
                func.coalesce(func.sum(subq.c.tax_amount), Decimal("0")).label("total_tax"),
                func.coalesce(func.sum(subq.c.net_amount), Decimal("0")).label("total_net"),
                func.count(subq.c.id).label("count")
            ).select_from(subq)
        )
        overall = overall_result.one()

        # By type
        by_type_result = await self.db.execute(
            select(
                FinancialLedger.entry_type,
                func.coalesce(func.sum(FinancialLedger.gross_amount), Decimal("0")).label("total_gross"),
                func.coalesce(func.sum(FinancialLedger.net_amount), Decimal("0")).label("total_net"),
                func.count(FinancialLedger.id).label("count")
            )
            .where(FinancialLedger.merchant_id == merchant_id)
            .where(FinancialLedger.transaction_date >= date_from)
            .where(FinancialLedger.transaction_date <= date_to)
            .group_by(FinancialLedger.entry_type)
        )

        by_type = [
            LedgerSummaryByType(
                entry_type=row.entry_type,
                total_gross=row.total_gross,
                total_net=row.total_net,
                count=row.count
            )
            for row in by_type_result.all()
        ]

        return LedgerSummaryResponse(
            overall=LedgerSummary(
                total_gross=overall.total_gross,
                total_fees=overall.total_fees,
                total_tax=overall.total_tax,
                total_net=overall.total_net,
                count=overall.count,
                currency="BHD"
            ),
            by_type=by_type,
            date_from=date_from,
            date_to=date_to
        )

    async def create_order_ledger_entries(self, merchant_id: uuid.UUID, order: Order) -> List[FinancialLedger]:
        """Automatically create ledger entries when an order is paid."""
        entries = []

        # Main order payment entry
        payment_entry = FinancialLedger(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            order_id=order.id,
            entry_type=LedgerEntryType.ORDER_PAYMENT,
            status=LedgerEntryStatus.CONFIRMED,
            currency="BHD",
            gross_amount=Decimal(str(order.total)),
            fee_amount=Decimal("0"),
            tax_amount=Decimal(str(order.tax_amount or 0)),
            net_amount=Decimal(str(order.total)),
            platform_order_id=order.external_order_id,
            description=f"Order payment #{order.order_number}",
            transaction_date=order.created_at or datetime.utcnow()
        )
        self.db.add(payment_entry)
        entries.append(payment_entry)

        # If there's a platform fee (calculated as % of gross)
        if order.platform_connection_id:
            # Default 15% platform fee — can be overridden by platform config
            platform_fee_rate = Decimal("0.15")  # TODO: fetch from platform config
            fee_amount = (Decimal(str(order.total)) * platform_fee_rate).quantize(FOUR_PLACES)

            fee_entry = FinancialLedger(
                id=uuid.uuid4(),
                merchant_id=merchant_id,
                order_id=order.id,
                platform_connection_id=order.platform_connection_id,
                entry_type=LedgerEntryType.PLATFORM_FEE,
                status=LedgerEntryStatus.CONFIRMED,
                currency="BHD",
                gross_amount=Decimal("0"),
                fee_amount=fee_amount,
                tax_amount=Decimal("0"),
                net_amount=-fee_amount,
                platform_order_id=order.external_order_id,
                description=f"Platform fee for order #{order.order_number}",
                transaction_date=order.created_at or datetime.utcnow()
            )
            self.db.add(fee_entry)
            entries.append(fee_entry)

        await self.db.flush()
        return entries


# ─── RECONCILIATION ENGINE ────────────────────────────────────────

class ReconciliationEngine:
    """Core auto-reconciliation logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ledger_service = LedgerService(db)

    async def preview(self, merchant_id: uuid.UUID, platform_connection_id: Optional[uuid.UUID],
                      date_from: datetime, date_to: datetime) -> ReconciliationPreview:
        """Preview what reconciliation would find."""

        # Count orders in period
        order_query = select(func.count(Order.id)).where(
            Order.merchant_id == merchant_id,
            Order.created_at >= date_from,
            Order.created_at <= date_to
        )
        if platform_connection_id:
            order_query = order_query.where(Order.platform_connection_id == platform_connection_id)

        order_result = await self.db.execute(order_query)
        order_count = order_result.scalar()

        # Estimate discrepancies (historical rate ~3%)
        estimated_discrepancies = int(order_count * 0.03)
        estimated_variance = Decimal(str(estimated_discrepancies)) * Decimal("2.5000")

        platforms = []
        if platform_connection_id:
            platforms = [platform_connection_id]
        else:
            # Get all active platform connections
            plat_result = await self.db.execute(
                select(PlatformConnection.id).where(
                    PlatformConnection.merchant_id == merchant_id,
                    PlatformConnection.is_active == True
                )
            )
            platforms = [r for r in plat_result.scalars().all()]

        return ReconciliationPreview(
            would_create_run=True,
            estimated_orders=order_count,
            estimated_discrepancies=estimated_discrepancies,
            estimated_variance=estimated_variance.quantize(FOUR_PLACES),
            platforms=platforms,
            date_from=date_from,
            date_to=date_to
        )

    async def run(self, merchant_id: uuid.UUID, data: ReconciliationRunCreate,
                  config: ReconciliationConfig) -> ReconciliationResult:
        """Execute a full reconciliation run."""

        # Create run record
        run = ReconciliationRun(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            platform_connection_id=data.platform_connection_id,
            date_from=data.date_from,
            date_to=data.date_to,
            status=ReconciliationRunStatus.IN_PROGRESS,
            triggered_by=data.triggered_by,
            config_snapshot=config.model_dump(mode='json'),
            started_at=datetime.utcnow()
        )
        self.db.add(run)
        await self.db.flush()

        try:
            discrepancies = []
            orders_matched = 0
            auto_resolved = 0
            total_variance = Decimal("0")

            # Fetch orders in scope
            order_query = select(Order).where(
                Order.merchant_id == merchant_id,
                Order.created_at >= data.date_from,
                Order.created_at <= data.date_to
            )
            if data.platform_connection_id:
                order_query = order_query.where(Order.platform_connection_id == data.platform_connection_id)
            if not config.include_pending_orders:
                order_query = order_query.where(Order.status != OrderStatus.PENDING)
            if not config.include_cancelled_orders:
                order_query = order_query.where(Order.status != OrderStatus.CANCELLED)

            order_result = await self.db.execute(order_query)
            orders = order_result.scalars().all()

            run.total_orders_checked = len(orders)

            for order in orders:
                match_found = False

                # Strategy 1: Match by platform order ID
                if config.match_by_platform_id and order.external_order_id:
                    ledger_match = await self.db.execute(
                        select(FinancialLedger).where(
                            FinancialLedger.merchant_id == merchant_id,
                            FinancialLedger.platform_order_id == order.external_order_id,
                            FinancialLedger.transaction_date >= data.date_from,
                            FinancialLedger.transaction_date <= data.date_to
                        )
                    )
                    ledger_entry = ledger_match.scalars().first()
                    if ledger_entry:
                        match_found = True
                        orders_matched += 1

                        # Check amount match
                        if config.match_by_amount:
                            order_total = Decimal(str(order.total or 0))
                            ledger_gross = Decimal(str(ledger_entry.gross_amount or 0))
                            tolerance = config.amount_tolerance

                            if abs(order_total - ledger_gross) > tolerance:
                                variance = (order_total - ledger_gross).quantize(FOUR_PLACES)
                                disc = Discrepancy(
                                    id=uuid.uuid4(),
                                    merchant_id=merchant_id,
                                    reconciliation_id=run.id,
                                    discrepancy_type=DiscrepancyType.AMOUNT_MISMATCH,
                                    status=DiscrepancyStatus.OPEN,
                                    severity="high" if abs(variance) > Decimal("10") else "medium",
                                    order_id=order.id,
                                    platform_order_id=order.external_order_id,
                                    platform_connection_id=order.platform_connection_id,
                                    expected_amount=order_total,
                                    actual_amount=ledger_gross,
                                    variance=variance,
                                    currency="BHD",
                                    expected_value=str({"order_total": float(order_total)}),
                                    actual_value=str({"ledger_gross": float(ledger_gross)}),
                                    description=f"Order total {order_total} vs ledger {ledger_gross}"
                                )
                                self.db.add(disc)
                                discrepancies.append(disc)
                                total_variance += abs(variance)

                                # Auto-resolve if under threshold
                                if config.auto_resolve_minor and abs(variance) <= config.minor_threshold:
                                    disc.status = DiscrepancyStatus.RESOLVED
                                    disc.resolution_notes = f"Auto-resolved: variance {variance} under threshold {config.minor_threshold}"
                                    disc.resolved_at = datetime.utcnow()
                                    disc.resolved_by = "system"
                                    auto_resolved += 1

                # Strategy 2: If no platform ID match, check for orphan
                if not match_found:
                    disc = Discrepancy(
                        id=uuid.uuid4(),
                        merchant_id=merchant_id,
                        reconciliation_id=run.id,
                        discrepancy_type=DiscrepancyType.ORPHAN_ORDER,
                        status=DiscrepancyStatus.OPEN,
                        severity="medium",
                        order_id=order.id,
                        platform_order_id=order.external_order_id,
                        platform_connection_id=order.platform_connection_id,
                        expected_amount=Decimal(str(order.total or 0)),
                        actual_amount=Decimal("0"),
                        variance=Decimal(str(order.total or 0)),
                        currency="BHD",
                        description=f"Order #{order.order_number} has no matching platform/ledger record"
                    )
                    self.db.add(disc)
                    discrepancies.append(disc)
                    total_variance += Decimal(str(order.total or 0))

            # Check for missing orders (ledger has platform_order_id but no matching order)
            if data.platform_connection_id:
                orphan_ledger_query = select(FinancialLedger).where(
                    FinancialLedger.merchant_id == merchant_id,
                    FinancialLedger.platform_connection_id == data.platform_connection_id,
                    FinancialLedger.transaction_date >= data.date_from,
                    FinancialLedger.transaction_date <= data.date_to,
                    FinancialLedger.platform_order_id.isnot(None)
                )
                orphan_result = await self.db.execute(orphan_ledger_query)
                orphan_ledgers = orphan_result.scalars().all()

                for ledger in orphan_ledgers:
                    # Check if order exists
                    order_exists = await self.db.execute(
                        select(func.count(Order.id)).where(
                            Order.merchant_id == merchant_id,
                            Order.external_order_id == ledger.platform_order_id
                        )
                    )
                    if order_exists.scalar() == 0:
                        disc = Discrepancy(
                            id=uuid.uuid4(),
                            merchant_id=merchant_id,
                            reconciliation_id=run.id,
                            discrepancy_type=DiscrepancyType.MISSING_ORDER,
                            status=DiscrepancyStatus.OPEN,
                            severity="high",
                            platform_order_id=ledger.platform_order_id,
                            platform_connection_id=data.platform_connection_id,
                            expected_amount=Decimal("0"),
                            actual_amount=Decimal(str(ledger.gross_amount or 0)),
                            variance=Decimal(str(ledger.gross_amount or 0)),
                            currency="BHD",
                            description=f"Platform order {ledger.platform_order_id} found in ledger but no local order"
                        )
                        self.db.add(disc)
                        discrepancies.append(disc)
                        total_variance += Decimal(str(ledger.gross_amount or 0))

            # Update run stats
            run.status = ReconciliationRunStatus.COMPLETED if len(discrepancies) == 0 else ReconciliationRunStatus.PARTIAL
            run.total_orders_matched = orders_matched
            run.total_discrepancies_found = len(discrepancies)
            run.total_discrepancies_resolved = auto_resolved
            run.total_amount_checked = sum(Decimal(str(o.total or 0)) for o in orders)
            run.total_variance = total_variance.quantize(FOUR_PLACES)
            run.completed_at = datetime.utcnow()

            await self.db.flush()

            return ReconciliationResult(
                run_id=run.id,
                status=run.status,
                orders_checked=run.total_orders_checked,
                orders_matched=orders_matched,
                discrepancies_found=len(discrepancies),
                discrepancies_auto_resolved=auto_resolved,
                total_variance=total_variance.quantize(FOUR_PLACES),
                message=f"Reconciliation completed. {orders_matched}/{run.total_orders_checked} matched. {len(discrepancies)} discrepancies found."
            )

        except Exception as e:
            run.status = ReconciliationRunStatus.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            await self.db.flush()

            return ReconciliationResult(
                run_id=run.id,
                status=ReconciliationRunStatus.FAILED,
                orders_checked=run.total_orders_checked,
                orders_matched=0,
                discrepancies_found=0,
                discrepancies_auto_resolved=0,
                total_variance=Decimal("0"),
                message=f"Reconciliation failed: {str(e)}"
            )


# ─── DISCREPANCY SERVICE ─────────────────────────────────────────

class DiscrepancyService:
    """Manages discrepancy lifecycle."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, merchant_id: uuid.UUID, discrepancy_id: uuid.UUID) -> Optional[Discrepancy]:
        result = await self.db.execute(
            select(Discrepancy)
            .options(selectinload(Discrepancy.order))
            .where(Discrepancy.id == discrepancy_id, Discrepancy.merchant_id == merchant_id)
        )
        return result.scalar_one_or_none()

    async def list(self, merchant_id: uuid.UUID, params: DiscrepancyListParams) -> Tuple[List[Discrepancy], int]:
        query = select(Discrepancy).where(Discrepancy.merchant_id == merchant_id)

        if params.status:
            query = query.where(Discrepancy.status == params.status.value)
        if params.discrepancy_type:
            query = query.where(Discrepancy.discrepancy_type == params.discrepancy_type.value)
        if params.severity:
            query = query.where(Discrepancy.severity == params.severity)
        if params.platform_connection_id:
            query = query.where(Discrepancy.platform_connection_id == params.platform_connection_id)
        if params.reconciliation_id:
            query = query.where(Discrepancy.reconciliation_id == params.reconciliation_id)

        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar()

        query = query.order_by(desc(Discrepancy.created_at))
        query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)

        result = await self.db.execute(query)
        return result.scalars().all(), total

    async def update(self, merchant_id: uuid.UUID, discrepancy_id: uuid.UUID,
                     data: DiscrepancyUpdate) -> Optional[Discrepancy]:
        disc = await self.get(merchant_id, discrepancy_id)
        if not disc:
            return None

        if data.status:
            disc.status = data.status.value
        if data.resolution_notes:
            disc.resolution_notes = data.resolution_notes
        if data.severity:
            disc.severity = data.severity

        disc.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(disc)
        return disc

    async def resolve(self, merchant_id: uuid.UUID, discrepancy_id: uuid.UUID,
                      data: DiscrepancyResolve) -> Optional[Discrepancy]:
        disc = await self.get(merchant_id, discrepancy_id)
        if not disc:
            return None

        disc.status = data.status.value
        disc.resolution_notes = data.resolution_notes
        disc.resolved_by = data.resolved_by
        disc.resolved_at = datetime.utcnow()
        disc.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(disc)
        return disc

    async def get_summary(self, merchant_id: uuid.UUID) -> DiscrepancySummary:
        result = await self.db.execute(
            select(
                Discrepancy.status,
                func.count(Discrepancy.id).label("count"),
                func.coalesce(func.sum(Discrepancy.variance), Decimal("0")).label("total_variance")
            )
            .where(Discrepancy.merchant_id == merchant_id)
            .group_by(Discrepancy.status)
        )

        counts = {r.status: {"count": r.count, "variance": r.total_variance} for r in result.all()}

        by_type_result = await self.db.execute(
            select(Discrepancy.discrepancy_type, func.count(Discrepancy.id).label("count"))
            .where(Discrepancy.merchant_id == merchant_id)
            .group_by(Discrepancy.discrepancy_type)
        )
        by_type = {r.discrepancy_type: r.count for r in by_type_result.all()}

        return DiscrepancySummary(
            total_open=counts.get("open", {}).get("count", 0),
            total_under_review=counts.get("under_review", {}).get("count", 0),
            total_resolved=counts.get("resolved", {}).get("count", 0),
            total_escalated=counts.get("escalated", {}).get("count", 0),
            total_ignored=counts.get("ignored", {}).get("count", 0),
            total_variance=sum(
                counts.get(s, {}).get("variance", Decimal("0")) 
                for s in ["open", "under_review", "escalated"]
            ),
            by_type=by_type
        )


# ─── PAYOUT SERVICE ────────────────────────────────────────────────

class PayoutService:
    """Manages platform payout tracking."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, merchant_id: uuid.UUID, data: PayoutCreate) -> Payout:
        payout = Payout(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            **data.model_dump(exclude_unset=True)
        )
        self.db.add(payout)
        await self.db.flush()
        await self.db.refresh(payout)
        return payout

    async def get(self, merchant_id: uuid.UUID, payout_id: uuid.UUID) -> Optional[Payout]:
        result = await self.db.execute(
            select(Payout)
            .options(selectinload(Payout.platform_connection))
            .where(Payout.id == payout_id, Payout.merchant_id == merchant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_platform_id(self, merchant_id: uuid.UUID, platform_payout_id: str,
                                    platform_connection_id: uuid.UUID) -> Optional[Payout]:
        result = await self.db.execute(
            select(Payout).where(
                Payout.merchant_id == merchant_id,
                Payout.platform_payout_id == platform_payout_id,
                Payout.platform_connection_id == platform_connection_id
            )
        )
        return result.scalar_one_or_none()

    async def list(self, merchant_id: uuid.UUID, params: PayoutListParams) -> Tuple[List[Payout], int]:
        query = select(Payout).where(Payout.merchant_id == merchant_id)

        if params.status:
            query = query.where(Payout.status == params.status.value)
        if params.platform_connection_id:
            query = query.where(Payout.platform_connection_id == params.platform_connection_id)
        if params.date_from:
            query = query.where(Payout.expected_date >= params.date_from)
        if params.date_to:
            query = query.where(Payout.expected_date <= params.date_to)

        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar()

        query = query.order_by(desc(Payout.expected_date))
        query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)

        result = await self.db.execute(query)
        return result.scalars().all(), total

    async def update(self, merchant_id: uuid.UUID, payout_id: uuid.UUID,
                     data: PayoutUpdate) -> Optional[Payout]:
        payout = await self.get(merchant_id, payout_id)
        if not payout:
            return None

        if data.status:
            payout.status = data.status.value
        if data.bank_reference:
            payout.bank_reference = data.bank_reference
        if data.sent_date:
            payout.sent_date = data.sent_date
        if data.received_date:
            payout.received_date = data.received_date
        if data.net_payout is not None:
            payout.net_payout = data.net_payout

        payout.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(payout)
        return payout

    async def get_summary(self, merchant_id: uuid.UUID,
                          platform_connection_id: Optional[uuid.UUID] = None) -> PayoutSummary:
        subq = select(Payout).where(Payout.merchant_id == merchant_id)
        if platform_connection_id:
            subq = subq.where(Payout.platform_connection_id == platform_connection_id)
        subq = subq.subquery()

        result = await self.db.execute(
            select(
                subq.c.status,
                func.coalesce(func.sum(subq.c.net_payout), Decimal("0")).label("total"),
                func.count(subq.c.id).label("count")
            )
            .select_from(subq)
            .group_by(subq.c.status)
        )

        by_status = {r.status: {"total": r.total, "count": r.count} for r in result.all()}

        return PayoutSummary(
            total_expected=by_status.get("expected", {}).get("total", Decimal("0")),
            total_scheduled=by_status.get("scheduled", {}).get("total", Decimal("0")),
            total_in_transit=by_status.get("in_transit", {}).get("total", Decimal("0")),
            total_received=by_status.get("received", {}).get("total", Decimal("0")),
            total_failed=by_status.get("failed", {}).get("total", Decimal("0")),
            count_by_status={k: v["count"] for k, v in by_status.items()},
            currency="BHD"
        )

    async def sync_from_platform(self, merchant_id: uuid.UUID, platform_connection_id: uuid.UUID,
                                  platform_payouts: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Bulk sync payouts from a platform API. Returns (created, updated)."""
        created_count = 0
        updated_count = 0

        for payout_data in platform_payouts:
            platform_payout_id = payout_data.get("payout_id")
            if not platform_payout_id:
                continue

            existing = await self.get_by_platform_id(merchant_id, platform_payout_id, platform_connection_id)

            if existing:
                # Update
                if "status" in payout_data:
                    existing.status = payout_data["status"]
                if "net_payout" in payout_data:
                    existing.net_payout = Decimal(str(payout_data["net_payout"]))
                if "sent_date" in payout_data:
                    existing.sent_date = payout_data["sent_date"]
                if "received_date" in payout_data:
                    existing.received_date = payout_data["received_date"]
                if "breakdown" in payout_data:
                    existing.breakdown = payout_data["breakdown"]
                existing.updated_at = datetime.utcnow()
                updated_count += 1
            else:
                # Create
                new_payout = Payout(
                    id=uuid.uuid4(),
                    merchant_id=merchant_id,
                    platform_connection_id=platform_connection_id,
                    platform_payout_id=platform_payout_id,
                    platform_period_start=payout_data.get("period_start"),
                    platform_period_end=payout_data.get("period_end"),
                    status=payout_data.get("status", "expected"),
                    currency=payout_data.get("currency", "BHD"),
                    gross_sales=Decimal(str(payout_data.get("gross_sales", 0))),
                    total_fees=Decimal(str(payout_data.get("total_fees", 0))),
                    total_refunds=Decimal(str(payout_data.get("total_refunds", 0))),
                    total_adjustments=Decimal(str(payout_data.get("total_adjustments", 0))),
                    net_payout=Decimal(str(payout_data.get("net_payout", 0))),
                    breakdown=payout_data.get("breakdown", {}),
                    bank_reference=payout_data.get("bank_reference"),
                    expected_date=payout_data.get("expected_date"),
                    sent_date=payout_data.get("sent_date"),
                    received_date=payout_data.get("received_date")
                )
                self.db.add(new_payout)
                created_count += 1

        await self.db.flush()
        return created_count, updated_count


# ─── SETTLEMENT REPORT SERVICE ─────────────────────────────────────

class SettlementReportService:
    """Generates settlement reports."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, merchant_id: uuid.UUID, data: SettlementReportCreate) -> SettlementReport:
        # Auto-calculate totals from ledger
        ledger_query = select(FinancialLedger).where(
            FinancialLedger.merchant_id == merchant_id,
            FinancialLedger.transaction_date >= data.period_start,
            FinancialLedger.transaction_date <= data.period_end
        )
        if data.platform_connection_id:
            ledger_query = ledger_query.where(FinancialLedger.platform_connection_id == data.platform_connection_id)

        ledger_result = await self.db.execute(ledger_query)
        entries = ledger_result.scalars().all()

        total_sales = sum(e.gross_amount for e in entries if e.entry_type == LedgerEntryType.ORDER_PAYMENT)
        total_fees = sum(e.fee_amount for e in entries)
        total_refunds = sum(e.net_amount for e in entries if e.entry_type == LedgerEntryType.REFUND)

        # Payouts in period
        payout_query = select(Payout).where(
            Payout.merchant_id == merchant_id,
            Payout.expected_date >= data.period_start,
            Payout.expected_date <= data.period_end
        )
        if data.platform_connection_id:
            payout_query = payout_query.where(Payout.platform_connection_id == data.platform_connection_id)

        payout_result = await self.db.execute(payout_query)
        payouts = payout_result.scalars().all()
        total_payouts = sum(p.net_payout for p in payouts)

        # Platform breakdown
        platform_breakdown = {}
        for e in entries:
            pid = str(e.platform_connection_id) if e.platform_connection_id else "direct"
            if pid not in platform_breakdown:
                platform_breakdown[pid] = {"sales": Decimal("0"), "fees": Decimal("0"), "orders": 0}
            if e.entry_type == LedgerEntryType.ORDER_PAYMENT:
                platform_breakdown[pid]["sales"] += e.gross_amount
                platform_breakdown[pid]["orders"] += 1
            platform_breakdown[pid]["fees"] += e.fee_amount

        report = SettlementReport(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            report_type=data.report_type.value,
            period_start=data.period_start,
            period_end=data.period_end,
            platform_connection_id=data.platform_connection_id,
            total_orders=sum(1 for e in entries if e.entry_type == LedgerEntryType.ORDER_PAYMENT),
            total_sales=total_sales,
            total_fees=total_fees,
            total_refunds=abs(total_refunds),
            total_payouts=total_payouts,
            net_revenue=total_sales - total_fees - abs(total_refunds),
            platform_breakdown={k: {sk: float(sv) if isinstance(sv, Decimal) else sv for sk, sv in v.items()} 
                               for k, v in platform_breakdown.items()},
            payment_method_breakdown={},  # TODO: enrich from order payment methods
            is_final=False
        )
        self.db.add(report)
        await self.db.flush()
        await self.db.refresh(report)
        return report

    async def get(self, merchant_id: uuid.UUID, report_id: uuid.UUID) -> Optional[SettlementReport]:
        result = await self.db.execute(
            select(SettlementReport).where(
                SettlementReport.id == report_id,
                SettlementReport.merchant_id == merchant_id
            )
        )
        return result.scalar_one_or_none()

    async def list(self, merchant_id: uuid.UUID, params: SettlementReportListParams) -> Tuple[List[SettlementReport], int]:
        query = select(SettlementReport).where(SettlementReport.merchant_id == merchant_id)

        if params.report_type:
            query = query.where(SettlementReport.report_type == params.report_type.value)
        if params.platform_connection_id:
            query = query.where(SettlementReport.platform_connection_id == params.platform_connection_id)
        if params.date_from:
            query = query.where(SettlementReport.period_start >= params.date_from)
        if params.date_to:
            query = query.where(SettlementReport.period_end <= params.date_to)
        if params.is_final is not None:
            query = query.where(SettlementReport.is_final == params.is_final)

        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar()

        query = query.order_by(desc(SettlementReport.period_start))
        query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)

        result = await self.db.execute(query)
        return result.scalars().all(), total

    async def finalize(self, merchant_id: uuid.UUID, report_id: uuid.UUID) -> Optional[SettlementReport]:
        report = await self.get(merchant_id, report_id)
        if not report:
            return None

        report.is_final = True
        report.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(report)
        return report


# ─── COMPOSITE RECONCILIATION SERVICE ─────────────────────────────

class ReconciliationService:
    """Facade exposing all Phase 8 services."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ledger = LedgerService(db)
        self.engine = ReconciliationEngine(db)
        self.discrepancy = DiscrepancyService(db)
        self.payout = PayoutService(db)
        self.settlement = SettlementReportService(db)
