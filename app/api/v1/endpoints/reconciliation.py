from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.session import get_db
from app.services.reconciliation.engine import ReconciliationEngine
from app.core.auth import get_current_user

router = APIRouter()

@router.get("/batches")
async def list_batches(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = ReconciliationEngine(db)
    return await service.list_batches(current_user.merchant_id)

@router.post("/batches/generate")
async def generate_batch(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Trigger manual reconciliation batch"""
    from datetime import date
    service = ReconciliationEngine(db)
    return await service.run_reconciliation(current_user.merchant_id, date.today())

@router.get("/variances")
async def list_variances(
    batch_id: UUID = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    service = ReconciliationEngine(db)
    return await service.list_variances(current_user.merchant_id, batch_id)

@router.get("/ledger")
async def get_ledger(
    start_date: str = None,
    end_date: str = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    from app.services.reconciliation.ledger_service import FinancialLedgerService
    service = FinancialLedgerService(db)
    return await service.get_entries(current_user.merchant_id, start_date, end_date)
