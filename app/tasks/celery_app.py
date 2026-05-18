from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "qrmenu",
    broker=settings.REDIS_CELERY_URI,
    backend=settings.REDIS_CELERY_URI,
    include=["app.tasks.acceptance", "app.tasks.delivery", "app.tasks.reconciliation"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Bahrain",
    enable_utc=True,
    beat_schedule={
        "check-acceptance-timeouts": {
            "task": "app.tasks.acceptance.check_timeouts",
            "schedule": 60.0,  # every 60 seconds
        },
        "driver-location-archive": {
            "task": "app.tasks.delivery.archive_locations",
            "schedule": 3600.0,  # every hour
        },
        "nightly-reconciliation": {
            "task": "app.tasks.reconciliation.run_nightly",
            "schedule": "crontab(hour=2, minute=0)",  # 2 AM daily
        },
    }
)
