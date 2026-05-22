"""
Phase 8 Tests — Reconciliation & Financial Ledger
Run with: pytest tests/test_phase8_reconciliation.py -v
"""

import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    FinancialLedger, LedgerEntryType, LedgerEntryStatus,
    ReconciliationRun, ReconciliationRunStatus,
    Discrepancy, DiscrepancyType, DiscrepancyStatus,
    Payout, PayoutStatus,
    SettlementReport, ReportType,
    Order, OrderStatus, OrderTypeEnum,
    PlatformConnection, Merchant, Tenant
)
from app.schemas.reconciliation import (
    LedgerEntryCreate, LedgerEntryUpdate, LedgerListParams,
    ReconciliationRunCreate, ReconciliationConfig, ReconciliationTrigger,
    DiscrepancyCreate, DiscrepancyUpdate, DiscrepancyResolve, DiscrepancyListParams,
    PayoutCreate, PayoutUpdate, PayoutListParams,
    SettlementReportCreate, SettlementReportListParams,
)
from app.services.reconciliation_service import (
    LedgerService, ReconciliationEngine, DiscrepancyService,
    PayoutService, SettlementReportService, ReconciliationService
)

# ─── FIXTURES ──────────────────────────────────────────────────────

@pytest.fixture
async def merchant_id(db_session: AsyncSession) -> uuid.UUID:
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Phase8 Test Tenant",
        slug=f"phase8-{uuid.uuid4().hex[:8]}"
    )
    db_session.add(tenant)
    await db_session.flush()

    merchant = Merchant(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        business_name="Phase8 Test Merchant",
        slug=f"phase8-merchant-{uuid.uuid4().hex[:8]}",
        currency="BHD",
        timezone="Asia/Bahrain"
    )
    db_session.add(merchant)
    await db_session.flush()
    return merchant.id

@pytest_asyncio.fixture
async def platform_connection(db_session: AsyncSession, merchant_id: uuid.UUID) -> PlatformConnection:
    pc = PlatformConnection(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        platform="talabat",
        merchant_ref="talabat_12345",
        api_key="test_key",
        api_secret="test_secret",
        webhook_secret="secret",
        is_active=True,
    )
    db_session.add(pc)
    await db_session.flush()
    return pc

@pytest_asyncio.fixture
async def sample_order(db_session: AsyncSession, merchant_id: uuid.UUID, platform_connection: PlatformConnection) -> Order:
    order = Order(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        platform_connection_id=platform_connection.id,
        order_number="ORD-001",
        external_order_id="TAL-12345",
        status=OrderStatus.CONFIRMED,
        order_type=OrderTypeEnum.delivery,
        payment_method="online",
        subtotal=Decimal("25.500"),
        tax_amount=Decimal("1.250"),
        total=Decimal("25.500"),
        created_at=datetime.utcnow()
    )
    db_session.add(order)
    await db_session.flush()
    return order

# ─── LEDGER SERVICE TESTS ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_ledger_entry(db_session: AsyncSession, merchant_id: uuid.UUID):
    service = LedgerService(db_session)
    data = LedgerEntryCreate(
        entry_type=LedgerEntryType.ORDER_PAYMENT,
        gross_amount=Decimal("100.0000"),
        net_amount=Decimal("100.0000"),
        transaction_date=datetime.utcnow()
    )
    entry = await service.create_entry(merchant_id, data)

    assert entry.id is not None
    assert entry.merchant_id == merchant_id
    assert entry.entry_type == LedgerEntryType.ORDER_PAYMENT
    assert entry.gross_amount == Decimal("100.0000")
    assert entry.status == LedgerEntryStatus.PENDING

@pytest.mark.asyncio
async def test_list_ledger_entries(db_session: AsyncSession, merchant_id: uuid.UUID):
    service = LedgerService(db_session)

    # Create entries
    for i in range(3):
        data = LedgerEntryCreate(
            entry_type=LedgerEntryType.ORDER_PAYMENT,
            gross_amount=Decimal(f"{10 * (i+1)}.0000"),
            net_amount=Decimal(f"{10 * (i+1)}.0000"),
            transaction_date=datetime.utcnow()
        )
        await service.create_entry(merchant_id, data)

    params = LedgerListParams(page=1, page_size=10)
    entries, total = await service.list_entries(merchant_id, params)

    assert len(entries) == 3
    assert total == 3

@pytest.mark.asyncio
async def test_ledger_summary(db_session: AsyncSession, merchant_id: uuid.UUID):
    service = LedgerService(db_session)

    # Create mixed entries
    await service.create_entry(merchant_id, LedgerEntryCreate(
        entry_type=LedgerEntryType.ORDER_PAYMENT,
        gross_amount=Decimal("100.0000"),
        fee_amount=Decimal("15.0000"),
        tax_amount=Decimal("5.0000"),
        net_amount=Decimal("80.0000"),
        transaction_date=datetime.utcnow()
    ))
    await service.create_entry(merchant_id, LedgerEntryCreate(
        entry_type=LedgerEntryType.REFUND,
        gross_amount=Decimal("20.0000"),
        net_amount=Decimal("-20.0000"),
        transaction_date=datetime.utcnow()
    ))

    date_from = datetime.utcnow() - timedelta(days=1)
    date_to = datetime.utcnow() + timedelta(days=1)
    summary = await service.get_summary(merchant_id, date_from, date_to)

    assert summary.overall.count == 2
    assert summary.overall.total_gross == Decimal("120.0000")
    assert summary.overall.total_net == Decimal("60.0000")
    assert len(summary.by_type) == 2

@pytest.mark.asyncio
async def test_create_order_ledger_entries(db_session: AsyncSession, merchant_id: uuid.UUID, sample_order: Order):
    service = LedgerService(db_session)
    entries = await service.create_order_ledger_entries(merchant_id, sample_order)

    assert len(entries) == 2  # payment + platform fee
    assert entries[0].entry_type == LedgerEntryType.ORDER_PAYMENT
    assert entries[1].entry_type == LedgerEntryType.PLATFORM_FEE
    assert entries[1].net_amount < 0  # Fee is negative

# ─── RECONCILIATION ENGINE TESTS ───────────────────────────────────

@pytest.mark.asyncio
async def test_reconciliation_preview(db_session: AsyncSession, merchant_id: uuid.UUID, sample_order: Order):
    engine = ReconciliationEngine(db_session)

    date_from = datetime.utcnow() - timedelta(days=1)
    date_to = datetime.utcnow() + timedelta(days=1)

    preview = await engine.preview(merchant_id, sample_order.platform_connection_id, date_from, date_to)

    assert preview.would_create_run is True
    assert preview.estimated_orders >= 1
    assert preview.estimated_discrepancies >= 0

@pytest.mark.asyncio
async def test_reconciliation_run_with_match(db_session: AsyncSession, merchant_id: uuid.UUID,
                                              sample_order: Order, platform_connection: PlatformConnection):
    engine = ReconciliationEngine(db_session)
    ledger_service = LedgerService(db_session)

    # Create matching ledger entry
    await ledger_service.create_entry(merchant_id, LedgerEntryCreate(
        entry_type=LedgerEntryType.ORDER_PAYMENT,
        gross_amount=Decimal("25.5000"),
        net_amount=Decimal("25.5000"),
        platform_order_id="TAL-12345",
        platform_connection_id=platform_connection.id,
        transaction_date=datetime.utcnow()
    ))

    date_from = datetime.utcnow() - timedelta(days=1)
    date_to = datetime.utcnow() + timedelta(days=1)

    run_data = ReconciliationRunCreate(
        platform_connection_id=platform_connection.id,
        date_from=date_from,
        date_to=date_to,
        triggered_by="test"
    )
    config = ReconciliationConfig()

    result = await engine.run(merchant_id, run_data, config)

    assert result.status == ReconciliationRunStatus.COMPLETED
    assert result.orders_checked >= 1
    assert result.orders_matched >= 1
    assert result.discrepancies_found == 0

@pytest.mark.asyncio
async def test_reconciliation_run_with_amount_mismatch(db_session: AsyncSession, merchant_id: uuid.UUID,
                                                        sample_order: Order, platform_connection: PlatformConnection):
    engine = ReconciliationEngine(db_session)
    ledger_service = LedgerService(db_session)

    # Create ledger entry with different amount
    await ledger_service.create_entry(merchant_id, LedgerEntryCreate(
        entry_type=LedgerEntryType.ORDER_PAYMENT,
        gross_amount=Decimal("30.0000"),  # Mismatch: order is 25.500
        net_amount=Decimal("30.0000"),
        platform_order_id="TAL-12345",
        platform_connection_id=platform_connection.id,
        transaction_date=datetime.utcnow()
    ))

    date_from = datetime.utcnow() - timedelta(days=1)
    date_to = datetime.utcnow() + timedelta(days=1)

    run_data = ReconciliationRunCreate(
        platform_connection_id=platform_connection.id,
        date_from=date_from,
        date_to=date_to,
        triggered_by="test"
    )
    config = ReconciliationConfig()

    result = await engine.run(merchant_id, run_data, config)

    assert result.status == ReconciliationRunStatus.PARTIAL
    assert result.discrepancies_found >= 1
    assert result.total_variance > 0

@pytest.mark.asyncio
async def test_reconciliation_run_orphan_order(db_session: AsyncSession, merchant_id: uuid.UUID, sample_order: Order):
    engine = ReconciliationEngine(db_session)

    date_from = datetime.utcnow() - timedelta(days=1)
    date_to = datetime.utcnow() + timedelta(days=1)

    run_data = ReconciliationRunCreate(
        platform_connection_id=sample_order.platform_connection_id,
        date_from=date_from,
        date_to=date_to,
        triggered_by="test"
    )
    config = ReconciliationConfig()

    result = await engine.run(merchant_id, run_data, config)

    assert result.discrepancies_found >= 1
    # Check orphan discrepancy was created
    disc_result = await db_session.execute(
        select(Discrepancy).where(Discrepancy.reconciliation_id == result.run_id)
    )
    discrepancies = disc_result.scalars().all()
    assert any(d.discrepancy_type == DiscrepancyType.ORPHAN_ORDER for d in discrepancies)

# ─── DISCREPANCY SERVICE TESTS ─────────────────────────────────────

@pytest.mark.asyncio
async def test_discrepancy_lifecycle(db_session: AsyncSession, merchant_id: uuid.UUID):
    disc_service = DiscrepancyService(db_session)

    # Create reconciliation run first
    run = ReconciliationRun(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        date_from=datetime.utcnow() - timedelta(days=1),
        date_to=datetime.utcnow(),
        status=ReconciliationRunStatus.COMPLETED
    )
    db_session.add(run)
    await db_session.flush()

    # Create discrepancy
    disc_data = DiscrepancyCreate(
        reconciliation_id=run.id,
        discrepancy_type=DiscrepancyType.AMOUNT_MISMATCH,
        severity="medium",
        expected_amount=Decimal("100.0000"),
        actual_amount=Decimal("95.0000"),
        variance=Decimal("5.0000"),
        description="Test discrepancy"
    )
    # Manually create since schema doesn't have merchant_id
    disc = Discrepancy(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        **disc_data.model_dump()
    )
    db_session.add(disc)
    await db_session.flush()

    # Get
    fetched = await disc_service.get(merchant_id, disc.id)
    assert fetched is not None
    assert fetched.status == DiscrepancyStatus.OPEN

    # Update
    updated = await disc_service.update(merchant_id, disc.id, DiscrepancyUpdate(
        status=DiscrepancyStatus.UNDER_REVIEW,
        resolution_notes="Investigating"
    ))
    assert updated.status == DiscrepancyStatus.UNDER_REVIEW

    # Resolve
    resolved = await disc_service.resolve(merchant_id, disc.id, DiscrepancyResolve(
        resolution_notes="Found the missing item",
        resolved_by="test_user"
    ))
    assert resolved.status == DiscrepancyStatus.RESOLVED
    assert resolved.resolved_by == "test_user"
    assert resolved.resolved_at is not None

@pytest.mark.asyncio
async def test_discrepancy_summary(db_session: AsyncSession, merchant_id: uuid.UUID):
    disc_service = DiscrepancyService(db_session)

    run = ReconciliationRun(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        date_from=datetime.utcnow() - timedelta(days=1),
        date_to=datetime.utcnow(),
        status=ReconciliationRunStatus.COMPLETED
    )
    db_session.add(run)
    await db_session.flush()

    # Create multiple discrepancies
    for i, dtype in enumerate([DiscrepancyType.AMOUNT_MISMATCH, DiscrepancyType.MISSING_ORDER,
                                DiscrepancyType.AMOUNT_MISMATCH]):
        disc = Discrepancy(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            reconciliation_id=run.id,
            discrepancy_type=dtype,
            status=DiscrepancyStatus.OPEN if i < 2 else DiscrepancyStatus.RESOLVED,
            severity="medium",
            variance=Decimal("10.0000")
        )
        db_session.add(disc)
    await db_session.flush()

    summary = await disc_service.get_summary(merchant_id)
    assert summary.total_open == 2
    assert summary.total_resolved == 1
    assert summary.by_type[DiscrepancyType.AMOUNT_MISMATCH.value] == 2

# ─── PAYOUT SERVICE TESTS ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_payout_create_and_get(db_session: AsyncSession, merchant_id: uuid.UUID, platform_connection: PlatformConnection):
    service = PayoutService(db_session)

    data = PayoutCreate(
        platform_connection_id=platform_connection.id,
        platform_payout_id="PAY-001",
        net_payout=Decimal("500.0000"),
        gross_sales=Decimal("600.0000"),
        total_fees=Decimal("100.0000")
    )
    payout = await service.create(merchant_id, data)

    assert payout.id is not None
    assert payout.status == PayoutStatus.EXPECTED

    fetched = await service.get(merchant_id, payout.id)
    assert fetched.platform_payout_id == "PAY-001"

@pytest.mark.asyncio
async def test_payout_update(db_session: AsyncSession, merchant_id: uuid.UUID, platform_connection: PlatformConnection):
    service = PayoutService(db_session)

    payout = await service.create(merchant_id, PayoutCreate(
        platform_connection_id=platform_connection.id,
        platform_payout_id="PAY-002",
        net_payout=Decimal("200.0000")
    ))

    updated = await service.update(merchant_id, payout.id, PayoutUpdate(
        status=PayoutStatus.RECEIVED,
        received_date=datetime.utcnow()
    ))

    assert updated.status == PayoutStatus.RECEIVED
    assert updated.received_date is not None

@pytest.mark.asyncio
async def test_payout_sync_from_platform(db_session: AsyncSession, merchant_id: uuid.UUID, platform_connection: PlatformConnection):
    service = PayoutService(db_session)

    platform_payouts = [
        {
            "payout_id": "EXT-001",
            "net_payout": 300.00,
            "gross_sales": 350.00,
            "total_fees": 50.00,
            "status": "expected",
            "period_start": datetime.utcnow(),
            "period_end": datetime.utcnow()
        },
        {
            "payout_id": "EXT-002",
            "net_payout": 150.00,
            "status": "received",
            "received_date": datetime.utcnow()
        }
    ]

    created, updated = await service.sync_from_platform(merchant_id, platform_connection.id, platform_payouts)
    assert created == 2
    assert updated == 0

    # Sync again should update
    platform_payouts[0]["net_payout"] = 310.00
    created, updated = await service.sync_from_platform(merchant_id, platform_connection.id, platform_payouts)
    assert created == 0
    assert updated == 2

@pytest.mark.asyncio
async def test_payout_summary(db_session: AsyncSession, merchant_id: uuid.UUID, platform_connection: PlatformConnection):
    service = PayoutService(db_session)

    for status in [PayoutStatus.EXPECTED, PayoutStatus.RECEIVED, PayoutStatus.RECEIVED]:
        await service.create(merchant_id, PayoutCreate(
            platform_connection_id=platform_connection.id,
            platform_payout_id=f"PAY-{status.value}-{uuid.uuid4().hex[:4]}",
            net_payout=Decimal("100.0000"),
            status=status
        ))

    summary = await service.get_summary(merchant_id)
    assert summary.total_expected == Decimal("100.0000")
    assert summary.total_received == Decimal("200.0000")
    assert summary.count_by_status["expected"] == 1
    assert summary.count_by_status["received"] == 2

# ─── SETTLEMENT REPORT TESTS ───────────────────────────────────────

@pytest.mark.asyncio
async def test_settlement_report_create(db_session: AsyncSession, merchant_id: uuid.UUID, platform_connection: PlatformConnection):
    service = SettlementReportService(db_session)
    ledger_service = LedgerService(db_session)

    # Seed ledger data
    await ledger_service.create_entry(merchant_id, LedgerEntryCreate(
        entry_type=LedgerEntryType.ORDER_PAYMENT,
        gross_amount=Decimal("100.0000"),
        fee_amount=Decimal("15.0000"),
        net_amount=Decimal("85.0000"),
        platform_connection_id=platform_connection.id,
        transaction_date=datetime.utcnow()
    ))

    data = SettlementReportCreate(
        report_type=ReportType.DAILY,
        period_start=datetime.utcnow() - timedelta(days=1),
        period_end=datetime.utcnow() + timedelta(days=1),
        platform_connection_id=platform_connection.id
    )
    report = await service.create(merchant_id, data)

    assert report.total_orders == 1
    assert report.total_sales == Decimal("100.0000")
    assert report.total_fees == Decimal("15.0000")
    assert report.net_revenue == Decimal("85.0000")
    assert report.is_final is False

@pytest.mark.asyncio
async def test_settlement_report_finalize(db_session: AsyncSession, merchant_id: uuid.UUID):
    service = SettlementReportService(db_session)

    report = SettlementReport(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        report_type=ReportType.DAILY,
        period_start=datetime.utcnow() - timedelta(days=1),
        period_end=datetime.utcnow(),
        total_orders=0,
        total_sales=Decimal("0"),
        is_final=False
    )
    db_session.add(report)
    await db_session.flush()

    finalized = await service.finalize(merchant_id, report.id)
    assert finalized.is_final is True

# ─── INTEGRATION / FACADE TESTS ────────────────────────────────────

@pytest.mark.asyncio
async def test_reconciliation_service_facade(db_session: AsyncSession, merchant_id: uuid.UUID):
    """Test that the composite service exposes all sub-services."""
    service = ReconciliationService(db_session)

    assert service.ledger is not None
    assert service.engine is not None
    assert service.discrepancy is not None
    assert service.payout is not None
    assert service.settlement is not None

@pytest.mark.asyncio
async def test_end_to_end_reconciliation_flow(db_session: AsyncSession, merchant_id: uuid.UUID,
                                               sample_order: Order, platform_connection: PlatformConnection):
    """Full flow: order → ledger → reconcile → discrepancy → resolve → report."""
    service = ReconciliationService(db_session)

    # 1. Order creates ledger entries
    entries = await service.ledger.create_order_ledger_entries(merchant_id, sample_order)
    assert len(entries) > 0

    # 2. Run reconciliation
    date_from = datetime.utcnow() - timedelta(days=1)
    date_to = datetime.utcnow() + timedelta(days=1)

    run_data = ReconciliationRunCreate(
        platform_connection_id=platform_connection.id,
        date_from=date_from,
        date_to=date_to,
        triggered_by="e2e_test"
    )
    config = ReconciliationConfig()
    result = await service.engine.run(merchant_id, run_data, config)

    assert result.status in [ReconciliationRunStatus.COMPLETED, ReconciliationRunStatus.PARTIAL]

    # 3. Check discrepancies
    disc_params = DiscrepancyListParams(page=1, page_size=50)
    discrepancies, _ = await service.discrepancy.list(merchant_id, disc_params)

    # 4. Resolve any discrepancies
    for disc in discrepancies:
        if disc.status == DiscrepancyStatus.OPEN:
            await service.discrepancy.resolve(merchant_id, disc.id, DiscrepancyResolve(
                resolution_notes="E2E test resolution",
                resolved_by="e2e_test"
            ))

    # 5. Generate settlement report
    report_data = SettlementReportCreate(
        report_type=ReportType.DAILY,
        period_start=date_from,
        period_end=date_to
    )
    report = await service.settlement.create(merchant_id, report_data)
    assert report is not None

    # 6. Finalize
    finalized = await service.settlement.finalize(merchant_id, report.id)
    assert finalized.is_final is True
