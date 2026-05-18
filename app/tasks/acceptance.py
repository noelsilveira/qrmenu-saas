from app.tasks.celery_app import celery_app
from app.db.session import async_session
from app.services.whatsapp.acceptance_service import AcceptanceService

@celery_app.task
def check_timeouts():
    """Run every 60 seconds to check for expired acceptance windows"""
    import asyncio
    asyncio.run(_check_timeouts_async())

async def _check_timeouts_async():
    async with async_session() as db:
        service = AcceptanceService(db)
        await service.process_expired_acceptances()
