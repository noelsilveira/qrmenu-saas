from app.tasks.celery_app import celery_app
from app.db.session import async_session
from app.services.reconciliation.engine import ReconciliationEngine
from datetime import date

@celery_app.task
def run_nightly():
    """Run at 2 AM daily"""
    import asyncio
    asyncio.run(_run_recon_async())

async def _run_recon_async():
    async with async_session() as db:
        engine = ReconciliationEngine(db)
        # Process all active merchants
        merchants = await engine.get_active_merchants()
        for merchant in merchants:
            await engine.run_reconciliation(merchant.id, date.today())
