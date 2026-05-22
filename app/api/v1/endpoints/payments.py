from typing import Optional
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import get_current_active_user, require_role
from app.models import User, PaymentTransaction, Order
from app.schemas.orders import (
    PaymentIntentRequest, PaymentIntentResponse,
    PaymentConfirmRequest, PaymentWebhookPayload,
    RefundRequest, RefundResponse,
    PaymentStatus, PaymentMethod
)
from app.services.payment_service import PaymentService
from app.core.cache import cache_delete_pattern

router = APIRouter()


def _get_merchant_id(user: User) -> UUID:
    return user.merchant_id


# ---------------------------------------------------------------------------
# Create payment intent
# ---------------------------------------------------------------------------
@router.post("/intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    data: PaymentIntentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create payment intent for an order."""
    merchant_id = _get_merchant_id(current_user)

    result = await db.execute(
        select(Order).where(
            Order.id == data.order_id,
            Order.merchant_id == merchant_id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return await PaymentService.create_payment_intent(
        order_id=order.id,
        amount=order.total,
        currency=order.currency,
        method=data.method,
        return_url=data.return_url
    )


# ---------------------------------------------------------------------------
# Confirm payment (Stripe/PayPal return)
# ---------------------------------------------------------------------------
@router.post("/confirm")
async def confirm_payment(
    data: PaymentConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    """Confirm payment after customer completes checkout."""
    result = await db.execute(
        select(PaymentTransaction).where(PaymentTransaction.id == data.transaction_id)
    )
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.method == PaymentMethod.stripe.value:
        confirm = await PaymentService.confirm_stripe_payment(data.provider_ref)
        if confirm["status"] == "succeeded":
            transaction.status = PaymentStatus.completed.value
            transaction.provider_ref = data.provider_ref
        else:
            transaction.status = PaymentStatus.failed.value
            transaction.failure_reason = confirm.get("error", "Payment failed")

    elif transaction.method == PaymentMethod.paypal.value:
        capture = await PaymentService.capture_paypal_order(data.provider_ref)
        if capture["status"] == "completed":
            transaction.status = PaymentStatus.completed.value
            transaction.provider_ref = capture.get("capture_id")
        else:
            transaction.status = PaymentStatus.failed.value

    order_result = await db.execute(
        select(Order).where(Order.id == transaction.order_id)
    )
    order = order_result.scalar_one_or_none()
    if order:
        if transaction.status == PaymentStatus.completed.value:
            order.payment_status = PaymentStatus.completed.value
            if order.status.value == "PENDING":
                from app.models.models import OrderStatus as OrderStatusEnum
                order.status = OrderStatusEnum.CONFIRMED
        else:
            order.payment_status = PaymentStatus.failed.value

    await db.flush()
    await cache_delete_pattern(f"orders:*:{transaction.merchant_id}")

    return {"status": transaction.status, "order_id": str(transaction.order_id)}


# ---------------------------------------------------------------------------
# COD: Mark as confirmed
# ---------------------------------------------------------------------------
@router.post("/cod/{order_id}/confirm")
async def confirm_cod(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager", "staff")),
):
    """Confirm a COD order."""
    merchant_id = _get_merchant_id(current_user)

    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.merchant_id == merchant_id,
            Order.payment_method == PaymentMethod.cod.value
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="COD order not found")

    order.payment_status = PaymentStatus.completed.value
    from app.models.models import OrderStatus as OrderStatusEnum
    order.status = OrderStatusEnum.CONFIRMED
    await db.flush()
    await cache_delete_pattern(f"orders:*:{merchant_id}")

    return {"status": "confirmed", "order_id": str(order_id)}


# ---------------------------------------------------------------------------
# Refund
# ---------------------------------------------------------------------------
@router.post("/refund", response_model=RefundResponse)
async def process_refund(
    data: RefundRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("owner", "manager")),
):
    """Process refund for an order."""
    merchant_id = _get_merchant_id(current_user)

    result = await db.execute(
        select(Order).where(
            Order.id == data.order_id,
            Order.merchant_id == merchant_id
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    tx_result = await db.execute(
        select(PaymentTransaction).where(
            PaymentTransaction.order_id == order.id,
            PaymentTransaction.status == PaymentStatus.completed.value
        )
    )
    transaction = tx_result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(status_code=400, detail="No completed payment found for refund")

    refund_amount = data.amount or transaction.amount

    refund = await PaymentService.process_refund(
        provider=transaction.method,
        provider_ref=transaction.provider_ref,
        amount=refund_amount,
        currency=transaction.currency
    )

    if refund["status"] == "success":
        transaction.status = PaymentStatus.refunded.value
        transaction.refunded_amount = refund_amount
        from app.models.models import OrderStatus as OrderStatusEnum
        order.status = OrderStatusEnum.REFUNDED
        await db.flush()
        await cache_delete_pattern(f"orders:*:{merchant_id}")

        return RefundResponse(
            transaction_id=transaction.id,
            refunded_amount=refund_amount,
            status=PaymentStatus.refunded,
            refund_ref=refund.get("refund_id")
        )
    else:
        raise HTTPException(status_code=400, detail=refund.get("error", "Refund failed"))


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------
@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook events."""
    import stripe
    import os

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        tx_result = await db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.provider_ref == payment_intent["id"]
            )
        )
        transaction = tx_result.scalar_one_or_none()
        if transaction:
            transaction.status = PaymentStatus.completed.value
            transaction.provider_response = event

            order_result = await db.execute(
                select(Order).where(Order.id == transaction.order_id)
            )
            order = order_result.scalar_one_or_none()
            if order:
                order.payment_status = PaymentStatus.completed.value
                if order.status.value == "PENDING":
                    from app.models.models import OrderStatus as OrderStatusEnum
                    order.status = OrderStatusEnum.CONFIRMED

            await db.flush()

    elif event["type"] == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]
        tx_result = await db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.provider_ref == payment_intent["id"]
            )
        )
        transaction = tx_result.scalar_one_or_none()
        if transaction:
            transaction.status = PaymentStatus.failed.value
            transaction.failure_reason = payment_intent.get("last_payment_error", {}).get("message", "Payment failed")
            await db.flush()

    return {"status": "ok"}


@router.post("/webhook/paypal")
async def paypal_webhook(
    data: PaymentWebhookPayload,
    db: AsyncSession = Depends(get_db),
):
    """Handle PayPal webhook events."""
    if data.event_type in ["CHECKOUT.ORDER.APPROVED", "PAYMENT.CAPTURE.COMPLETED"]:
        custom_id = data.payload.get("purchase_units", [{}])[0].get("custom_id")
        if custom_id:
            tx_result = await db.execute(
                select(PaymentTransaction).where(
                    PaymentTransaction.id == UUID(custom_id)
                )
            )
            transaction = tx_result.scalar_one_or_none()
            if transaction:
                transaction.status = PaymentStatus.completed.value
                order_result = await db.execute(
                    select(Order).where(Order.id == transaction.order_id)
                )
                order = order_result.scalar_one_or_none()
                if order:
                    order.payment_status = PaymentStatus.completed.value
                    if order.status.value == "PENDING":
                        from app.models.models import OrderStatus as OrderStatusEnum
                        order.status = OrderStatusEnum.CONFIRMED
                await db.flush()

    return {"status": "ok"}
