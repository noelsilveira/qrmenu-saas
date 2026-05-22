import os
import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

import stripe

from app.schemas.orders import PaymentMethod, PaymentStatus, PaymentIntentResponse
from app.core.config import settings

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_BASE_URL = "https://api-m.sandbox.paypal.com" if os.getenv("PAYPAL_SANDBOX", "true").lower() == "true" else "https://api-m.paypal.com"


class PaymentService:
    @staticmethod
    async def create_payment_intent(
        order_id: UUID,
        amount: Decimal,
        currency: str,
        method: PaymentMethod,
        return_url: Optional[str] = None
    ) -> PaymentIntentResponse:
        transaction_id = uuid.uuid4()

        if method == PaymentMethod.stripe:
            return await PaymentService._create_stripe_intent(
                transaction_id, amount, currency, return_url
            )
        elif method == PaymentMethod.paypal:
            return await PaymentService._create_paypal_order(
                transaction_id, amount, currency, return_url
            )
        elif method == PaymentMethod.cod:
            return PaymentIntentResponse(
                transaction_id=transaction_id,
                amount=amount,
                currency=currency,
                status=PaymentStatus.pending,
                redirect_url=None,
                client_secret=None,
                paypal_order_id=None
            )
        else:
            raise ValueError(f"Unsupported payment method: {method}")

    @staticmethod
    async def _create_stripe_intent(
        transaction_id: UUID,
        amount: Decimal,
        currency: str,
        return_url: Optional[str] = None
    ) -> PaymentIntentResponse:
        try:
            amount_cents = int(amount * 1000) if currency == "BHD" else int(amount * 100)

            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency.lower(),
                metadata={"transaction_id": str(transaction_id)},
                automatic_payment_methods={"enabled": True},
            )

            return PaymentIntentResponse(
                transaction_id=transaction_id,
                client_secret=intent.client_secret,
                amount=amount,
                currency=currency,
                status=PaymentStatus.pending,
                redirect_url=return_url
            )
        except stripe.error.StripeError:
            return PaymentIntentResponse(
                transaction_id=transaction_id,
                amount=amount,
                currency=currency,
                status=PaymentStatus.failed,
                redirect_url=None
            )

    @staticmethod
    async def _create_paypal_order(
        transaction_id: UUID,
        amount: Decimal,
        currency: str,
        return_url: Optional[str] = None
    ) -> PaymentIntentResponse:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            auth = aiohttp.BasicAuth(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET)
            async with session.post(
                f"{PAYPAL_BASE_URL}/v1/oauth2/token",
                auth=auth,
                data={"grant_type": "client_credentials"}
            ) as resp:
                token_data = await resp.json()
                access_token = token_data["access_token"]

            payload = {
                "intent": "CAPTURE",
                "purchase_units": [{
                    "amount": {
                        "currency_code": currency.upper(),
                        "value": str(amount)
                    },
                    "custom_id": str(transaction_id)
                }],
                "application_context": {
                    "return_url": return_url,
                    "cancel_url": return_url
                }
            }

            async with session.post(
                f"{PAYPAL_BASE_URL}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=payload
            ) as resp:
                order_data = await resp.json()
                paypal_order_id = order_data.get("id")

                approval_url = None
                for link in order_data.get("links", []):
                    if link["rel"] == "approve":
                        approval_url = link["href"]
                        break

                return PaymentIntentResponse(
                    transaction_id=transaction_id,
                    paypal_order_id=paypal_order_id,
                    amount=amount,
                    currency=currency,
                    status=PaymentStatus.pending,
                    redirect_url=approval_url or return_url
                )

    @staticmethod
    async def confirm_stripe_payment(payment_intent_id: str) -> Dict[str, Any]:
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            return {
                "status": intent.status,
                "amount_received": Decimal(intent.amount_received) / 1000 if intent.currency == "bhd" else Decimal(intent.amount_received) / 100,
                "payment_method": intent.payment_method
            }
        except stripe.error.StripeError as e:
            return {"status": "failed", "error": str(e)}

    @staticmethod
    async def capture_paypal_order(paypal_order_id: str) -> Dict[str, Any]:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            auth = aiohttp.BasicAuth(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET)
            async with session.post(
                f"{PAYPAL_BASE_URL}/v1/oauth2/token",
                auth=auth,
                data={"grant_type": "client_credentials"}
            ) as resp:
                token_data = await resp.json()
                access_token = token_data["access_token"]

            async with session.post(
                f"{PAYPAL_BASE_URL}/v2/checkout/orders/{paypal_order_id}/capture",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
            ) as resp:
                capture_data = await resp.json()
                status = capture_data.get("status", "FAILED")
                return {
                    "status": "completed" if status == "COMPLETED" else "failed",
                    "capture_id": capture_data.get("purchase_units", [{}])[0].get("payments", {}).get("captures", [{}])[0].get("id")
                }

    @staticmethod
    async def process_refund(
        provider: str,
        provider_ref: str,
        amount: Optional[Decimal] = None,
        currency: str = "BHD"
    ) -> Dict[str, Any]:
        if provider == "stripe":
            try:
                refund = stripe.Refund.create(
                    payment_intent=provider_ref,
                    amount=int(amount * 1000) if currency == "BHD" else int(amount * 100) if amount else None
                )
                return {"status": "success", "refund_id": refund.id}
            except stripe.error.StripeError as e:
                return {"status": "failed", "error": str(e)}

        elif provider == "paypal":
            return {"status": "pending", "message": "PayPal refund requires manual API call"}

        return {"status": "completed", "message": "COD refund processed"}
