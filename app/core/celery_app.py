"""
Phase 12 — Celery Application Configuration
Distributed task queue for background processing
"""

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure
import logging

logger = logging.getLogger(__name__)

# Initialize Celery app
celery_app = Celery("qrmenu")

# Load configuration
celery_app.config_from_object({
    "broker_url": "redis://qrmenu-redis:6379/1",
    "result_backend": "redis://qrmenu-redis:6379/2",
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "Asia/Bahrain",
    "enable_utc": True,
    "task_track_started": True,
    "task_time_limit": 3600,  # 1 hour max
    "worker_prefetch_multiplier": 1,
    "worker_max_tasks_per_child": 100,
    "beat_schedule": {
        # ─── Auto-Reconciliation ─────────────────────────────
        "auto-reconciliation": {
            "task": "app.core.celery_tasks.run_auto_reconciliation",
            "schedule": crontab(hour=2, minute=0),  # 2 AM daily
        },
        # ─── Settlement Report Generation ────────────────────
        "daily-settlement-report": {
            "task": "app.core.celery_tasks.generate_settlement_report",
            "schedule": crontab(hour=3, minute=0),  # 3 AM daily
            "kwargs": {"report_type": "daily"},
        },
        "weekly-settlement-report": {
            "task": "app.core.celery_tasks.generate_settlement_report",
            "schedule": crontab(day_of_week=1, hour=4, minute=0),  # Monday 4 AM
            "kwargs": {"report_type": "weekly"},
        },
        "monthly-settlement-report": {
            "task": "app.core.celery_tasks.generate_settlement_report",
            "schedule": crontab(day_of_month=1, hour=5, minute=0),  # 1st of month 5 AM
            "kwargs": {"report_type": "monthly"},
        },
        # ─── Analytics Cache Warmup ──────────────────────────
        "warmup-analytics-cache": {
            "task": "app.core.celery_tasks.warmup_analytics_cache",
            "schedule": 300.0,  # Every 5 minutes
        },
        # ─── WhatsApp Timeout Check ──────────────────────────
        "whatsapp-timeout-check": {
            "task": "app.core.celery_tasks.check_whatsapp_timeouts",
            "schedule": 60.0,  # Every minute
        },
        # ─── Driver Location Cleanup ─────────────────────────
        "cleanup-offline-drivers": {
            "task": "app.core.celery_tasks.cleanup_offline_drivers",
            "schedule": 600.0,  # Every 10 minutes
        },
        # ─── Payout Sync ───────────────────────────────────
        "sync-platform-payouts": {
            "task": "app.core.celery_tasks.sync_platform_payouts",
            "schedule": crontab(hour=6, minute=0),  # 6 AM daily
        },
        # ─── Database Backup ─────────────────────────────────
        "database-backup": {
            "task": "app.core.celery_tasks.backup_database",
            "schedule": crontab(hour=1, minute=0),  # 1 AM daily
        },
    },
})

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.core.celery_tasks"])


@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    """Log task failures for monitoring."""
    logger.error(f"Task {sender.name} [{task_id}] failed: {exception}")
