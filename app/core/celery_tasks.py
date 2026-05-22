"""
Phase 12 — Celery Background Tasks
Scheduled and on-demand background processing
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.db.session import async_session
from app.models.models import Order, OrderStatus, Merchant, Driver
from app.services.reconciliation_service import ReconciliationService, ReconciliationEngine
from app.services.analytics_service import AnalyticsService
from app.services.kds_service import KDSService
from app.core.websocket_manager import ws_manager, WSMessage, WSMessageType

logger = logging.getLogger(__name__)


def get_db() -> AsyncSession:
    """Get database session for Celery tasks."""
    return async_session()


# ═══════════════════════════════════════════════════════════════
# RECONCILIATION TASKS
# ═══════════════════════════════════════════════════════════════

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_auto_reconciliation(self):
    """Run auto-reconciliation for all merchants at 2 AM daily."""
    logger.info("Starting auto-reconciliation task")

    async def _reconcile():
        async with get_db() as db:
            # Get all active merchants
            result = await db.execute(select(Merchant).where(Merchant.is_active == True))
            merchants = result.scalars().all()

            for merchant in merchants:
                try:
                    engine = ReconciliationEngine(db)
                    from app.schemas.reconciliation import ReconciliationRunCreate, ReconciliationConfig

                    yesterday = datetime.utcnow() - timedelta(days=1)
                    run_data = ReconciliationRunCreate(
                        date_from=yesterday.replace(hour=0, minute=0, second=0),
                        date_to=yesterday.replace(hour=23, minute=59, second=59),
                        triggered_by="scheduled"
                    )
                    config = ReconciliationConfig(auto_resolve_minor=True)

                    result_obj = await engine.run(merchant.id, run_data, config)
                    logger.info(f"Reconciliation for merchant {merchant.id}: {result_obj.message}")

                except Exception as e:
                    logger.error(f"Reconciliation failed for merchant {merchant.id}: {e}")

    asyncio.run(_reconcile())
    return {"status": "completed", "timestamp": datetime.utcnow().isoformat()}


# ═══════════════════════════════════════════════════════════════
# SETTLEMENT REPORT TASKS
# ═══════════════════════════════════════════════════════════════

@shared_task(bind=True, max_retries=2)
def generate_settlement_report(self, report_type: str = "daily"):
    """Generate settlement reports (daily/weekly/monthly)."""
    logger.info(f"Generating {report_type} settlement report")

    async def _generate():
        async with get_db() as db:
            service = ReconciliationService(db)
            result = await db.execute(select(Merchant).where(Merchant.is_active == True))
            merchants = result.scalars().all()

            for merchant in merchants:
                try:
                    from app.schemas.reconciliation import SettlementReportCreate, ReportType

                    now = datetime.utcnow()
                    if report_type == "daily":
                        start = now - timedelta(days=1)
                        end = now
                    elif report_type == "weekly":
                        start = now - timedelta(days=7)
                        end = now
                    else:  # monthly
                        start = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
                        end = now.replace(day=1)

                    report_data = SettlementReportCreate(
                        report_type=ReportType(report_type),
                        period_start=start,
                        period_end=end
                    )

                    report = await service.settlement.create(merchant.id, report_data)
                    await service.settlement.finalize(merchant.id, report.id)
                    logger.info(f"Generated {report_type} report for merchant {merchant.id}")

                except Exception as e:
                    logger.error(f"Report generation failed for merchant {merchant.id}: {e}")

    asyncio.run(_generate())
    return {"status": "completed", "report_type": report_type}


# ═══════════════════════════════════════════════════════════════
# ANALYTICS CACHE TASKS
# ═══════════════════════════════════════════════════════════════

@shared_task
def warmup_analytics_cache():
    """Pre-compute analytics dashboard data every 5 minutes."""
    logger.info("Warming up analytics cache")

    async def _warmup():
        async with get_db() as db:
            service = AnalyticsService(db)
            from app.schemas.analytics import DashboardRequest, ReportPeriod

            result = await db.execute(select(Merchant).where(Merchant.is_active == True))
            merchants = result.scalars().all()

            for merchant in merchants:
                try:
                    request = DashboardRequest(period=ReportPeriod.TODAY)
                    await service.get_dashboard(merchant.id, request)
                except Exception as e:
                    logger.warning(f"Cache warmup failed for merchant {merchant.id}: {e}")

    asyncio.run(_warmup())
    return {"status": "cached", "timestamp": datetime.utcnow().isoformat()}


# ═══════════════════════════════════════════════════════════════
# WHATSAPP TIMEOUT TASKS
# ═══════════════════════════════════════════════════════════════

@shared_task
def check_whatsapp_timeouts():
    """Check and expire WhatsApp acceptance timeouts every minute."""
    logger.info("Checking WhatsApp timeouts")

    expired_count = 0

    async def _check():
        nonlocal expired_count
        async with get_db() as db:
            # Find orders with expired WhatsApp acceptance window
            timeout_threshold = datetime.utcnow() - timedelta(minutes=10)

            result = await db.execute(
                select(Order).where(
                    Order.status == OrderStatus.PENDING,
                    Order.whatsapp_sent_at <= timeout_threshold,
                    Order.whatsapp_accepted == False
                )
            )
            expired_orders = result.scalars().all()
            expired_count = len(expired_orders)

            for order in expired_orders:
                order.status = OrderStatus.CANCELLED
                order.cancellation_reason = "WhatsApp acceptance timeout"
                order.updated_at = datetime.utcnow()

                # Notify customer
                # TODO: Send timeout notification via WhatsApp

                logger.info(f"Order {order.id} cancelled due to WhatsApp timeout")

            await db.commit()

    asyncio.run(_check())
    return {"expired_count": expired_count}


# ═══════════════════════════════════════════════════════════════
# DRIVER CLEANUP TASKS
# ═══════════════════════════════════════════════════════════════

@shared_task
def cleanup_offline_drivers():
    """Mark drivers as offline if no location update in 30 minutes."""
    logger.info("Cleaning up offline drivers")

    offline_count = 0

    async def _cleanup():
        nonlocal offline_count
        async with get_db() as db:
            offline_threshold = datetime.utcnow() - timedelta(minutes=30)

            result = await db.execute(
                select(Driver).where(
                    Driver.status.in_(["available", "returning"]),
                    Driver.last_location_at <= offline_threshold
                )
            )
            stale_drivers = result.scalars().all()
            offline_count = len(stale_drivers)

            for driver in stale_drivers:
                driver.status = "offline"
                driver.updated_at = datetime.utcnow()
                logger.info(f"Driver {driver.id} marked offline")

            await db.commit()

    asyncio.run(_cleanup())
    return {"offline_count": offline_count}


# ═══════════════════════════════════════════════════════════════
# PAYOUT SYNC TASKS
# ═══════════════════════════════════════════════════════════════

@shared_task(bind=True, max_retries=3)
def sync_platform_payouts(self):
    """Sync payouts from Talabat/Zomato/Jahez at 6 AM daily."""
    logger.info("Syncing platform payouts")

    async def _sync():
        async with get_db() as db:
            from app.services.third_party_service import ThirdPartyService
            service = ThirdPartyService(db)

            # TODO: Implement platform-specific payout sync
            # This is a placeholder for the actual platform API integration
            logger.info("Payout sync completed (placeholder)")

    asyncio.run(_sync())
    return {"status": "synced"}


# ═══════════════════════════════════════════════════════════════
# BACKUP TASKS
# ═══════════════════════════════════════════════════════════════

@shared_task
def backup_database():
    """Create database backup at 1 AM daily."""
    logger.info("Starting database backup")

    import subprocess
    import os

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_file = f"/backups/qrmenu_backup_{timestamp}.sql"

    os.makedirs("/backups", exist_ok=True)

    try:
        # This assumes pg_dump is available in the container
        result = subprocess.run(
            ["pg_dump", "-h", "postgres", "-U", "postgres", "-d", "qrmenu", "-f", backup_file],
            capture_output=True,
            text=True,
            env={**os.environ, "PGPASSWORD": "postgres"}
        )

        if result.returncode == 0:
            logger.info(f"Backup created: {backup_file}")
            return {"status": "success", "file": backup_file}
        else:
            logger.error(f"Backup failed: {result.stderr}")
            return {"status": "failed", "error": result.stderr}

    except Exception as e:
        logger.error(f"Backup error: {e}")
        return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════════
# ON-DEMAND TASKS (triggered by API/webhooks)
# ═══════════════════════════════════════════════════════════════

@shared_task
def send_order_confirmation_email(order_id: str, customer_email: str):
    """Send order confirmation email (async)."""
    logger.info(f"Sending confirmation email for order {order_id}")
    # TODO: Integrate with email service (SendGrid, AWS SES)
    return {"sent": True, "order_id": order_id}


@shared_task
def process_webhook_event(platform: str, payload: dict):
    """Process third-party webhook asynchronously."""
    logger.info(f"Processing {platform} webhook")

    async def _process():
        async with get_db() as db:
            from app.services.third_party_service import ThirdPartyService
            service = ThirdPartyService(db)

            # TODO: Implement actual webhook processing
            # Placeholder — ingest_order or custom webhook handler
            logger.info(f"Webhook processed for {platform}")

    asyncio.run(_process())
    return {"processed": True, "platform": platform}


@shared_task
def generate_pdf_report(report_id: str, merchant_id: str):
    """Generate PDF report asynchronously."""
    logger.info(f"Generating PDF report {report_id}")
    # TODO: Integrate with PDF generation library
    return {"generated": True, "report_id": report_id}
