import uuid
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderItem, Merchant, PlatformConnection
from app.models.models import OrderStatus as OrderStatusEnum, OrderTypeEnum
from app.schemas.third_party import (
    PlatformType, ThirdPartyOrderPayload, ThirdPartyOrderResponse,
    ThirdPartyOrderItem, MenuSyncItem, MenuSyncResponse, SyncStatus,
    FallbackConfig, FallbackLogResponse,
)
from app.schemas.orders import PaymentMethod
from app.services.order_service import OrderService
from app.core.cache import cache_get, cache_set, cache_delete


class OrderNormalizer:
    """Normalize 3rd party order formats to internal Order model."""

    @staticmethod
    def talabat(payload: dict) -> ThirdPartyOrderPayload:
        """Convert Talabat order format to normalized payload."""
        order_data = payload.get("order", {})
        items = []
        for item in order_data.get("items", []):
            items.append(ThirdPartyOrderItem(
                external_item_id=str(item.get("id", "")),
                name=item.get("name", ""),
                quantity=item.get("quantity", 1),
                unit_price=Decimal(str(item.get("unit_price", 0))),
                total_price=Decimal(str(item.get("total_price", 0))),
                modifiers=item.get("modifiers", []),
                special_instructions=item.get("special_instructions")
            ))

        return ThirdPartyOrderPayload(
            external_order_id=str(order_data.get("order_id", "")),
            platform=PlatformType.talabat,
            customer_name=order_data.get("customer", {}).get("name"),
            customer_phone=order_data.get("customer", {}).get("phone", ""),
            delivery_address=order_data.get("delivery_address"),
            items=items,
            subtotal=Decimal(str(order_data.get("subtotal", 0))),
            tax_amount=Decimal(str(order_data.get("tax", 0))),
            delivery_fee=Decimal(str(order_data.get("delivery_fee", 0))),
            discount_amount=Decimal(str(order_data.get("discount", 0))),
            total=Decimal(str(order_data.get("total", 0))),
            currency=order_data.get("currency", "BHD"),
            notes=order_data.get("notes"),
            estimated_ready_min=order_data.get("estimated_ready_min", 30),
            payment_method=order_data.get("payment_method", "online"),
            payment_status=order_data.get("payment_status", "paid")
        )

    @staticmethod
    def zomato(payload: dict) -> ThirdPartyOrderPayload:
        """Convert Zomato order format to normalized payload."""
        order_data = payload.get("order", {})
        items = []
        for item in order_data.get("items", []):
            items.append(ThirdPartyOrderItem(
                external_item_id=str(item.get("item_id", "")),
                name=item.get("item_name", ""),
                quantity=item.get("quantity", 1),
                unit_price=Decimal(str(item.get("price", 0))),
                total_price=Decimal(str(item.get("price", 0))) * item.get("quantity", 1),
                modifiers=[{"name": m.get("name", ""), "price": m.get("price", 0)} 
                          for m in item.get("addons", [])],
                special_instructions=item.get("instructions")
            ))

        return ThirdPartyOrderPayload(
            external_order_id=str(order_data.get("order_id", "")),
            platform=PlatformType.zomato,
            customer_name=order_data.get("user", {}).get("name"),
            customer_phone=order_data.get("user", {}).get("phone", ""),
            delivery_address=order_data.get("delivery_address"),
            items=items,
            subtotal=Decimal(str(order_data.get("subtotal", 0))),
            tax_amount=Decimal(str(order_data.get("taxes", 0))),
            delivery_fee=Decimal(str(order_data.get("delivery_charges", 0))),
            discount_amount=Decimal(str(order_data.get("discount_total", 0))),
            total=Decimal(str(order_data.get("order_total", 0))),
            currency=order_data.get("currency", "BHD"),
            notes=order_data.get("instructions"),
            estimated_ready_min=30,
            payment_method=order_data.get("payment_mode", "online"),
            payment_status="paid" if order_data.get("is_paid") else "pending"
        )

    @staticmethod
    def jahez(payload: dict) -> ThirdPartyOrderPayload:
        """Convert Jahez order format to normalized payload."""
        data = payload.get("data", {})
        order_data = data.get("order", {})
        items = []
        for item in order_data.get("items", []):
            items.append(ThirdPartyOrderItem(
                external_item_id=str(item.get("product_id", "")),
                name=item.get("product_name", ""),
                quantity=item.get("quantity", 1),
                unit_price=Decimal(str(item.get("unit_price", 0))),
                total_price=Decimal(str(item.get("total_price", 0))),
                modifiers=[{"name": o.get("name", ""), "price": o.get("price", 0)} 
                          for o in item.get("options", [])],
                special_instructions=item.get("notes")
            ))

        return ThirdPartyOrderPayload(
            external_order_id=str(order_data.get("order_number", "")),
            platform=PlatformType.jahez,
            customer_name=order_data.get("customer", {}).get("name"),
            customer_phone=order_data.get("customer", {}).get("mobile", ""),
            delivery_address=order_data.get("address"),
            items=items,
            subtotal=Decimal(str(order_data.get("sub_total", 0))),
            tax_amount=Decimal(str(order_data.get("vat_amount", 0))),
            delivery_fee=Decimal(str(order_data.get("delivery_fee", 0))),
            discount_amount=Decimal(str(order_data.get("discount_amount", 0))),
            total=Decimal(str(order_data.get("grand_total", 0))),
            currency="BHD",
            notes=order_data.get("notes"),
            estimated_ready_min=order_data.get("preparation_time", 30),
            payment_method=order_data.get("payment_type", "online"),
            payment_status="paid" if order_data.get("is_paid") else "pending"
        )


class ThirdPartyService:
    """Handle 3rd party order ingestion, menu sync, and fallback."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.normalizer = OrderNormalizer()

    async def ingest_order(
        self,
        merchant_id: UUID,
        platform: PlatformType,
        raw_payload: dict,
        connection_id: Optional[UUID] = None
    ) -> ThirdPartyOrderResponse:
        """Ingest a 3rd party order and create internal order."""

        # Normalize payload
        try:
            if platform == PlatformType.talabat:
                normalized = self.normalizer.talabat(raw_payload)
            elif platform == PlatformType.zomato:
                normalized = self.normalizer.zomato(raw_payload)
            elif platform == PlatformType.jahez:
                normalized = self.normalizer.jahez(raw_payload)
            else:
                return ThirdPartyOrderResponse(
                    internal_order_id=UUID(int=0),
                    external_order_id="",
                    platform=platform,
                    status="error",
                    message=f"Unsupported platform: {platform}",
                    accepted=False
                )
        except Exception as e:
            return ThirdPartyOrderResponse(
                internal_order_id=UUID(int=0),
                external_order_id=raw_payload.get("order", {}).get("order_id", ""),
                platform=platform,
                status="error",
                message=f"Normalization failed: {str(e)}",
                accepted=False
            )

        # Check for duplicate
        dup_result = await self.db.execute(
            select(Order).where(
                Order.merchant_id == merchant_id,
                Order.source == platform.value,
                Order.external_order_id == normalized.external_order_id
            )
        )
        if dup_result.scalar_one_or_none():
            return ThirdPartyOrderResponse(
                internal_order_id=UUID(int=0),
                external_order_id=normalized.external_order_id,
                platform=platform,
                status="duplicate",
                message="Order already exists",
                accepted=False
            )

        # Create internal order
        order = Order(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            customer_phone=normalized.customer_phone,
            customer_name=normalized.customer_name,
            order_type=OrderTypeEnum.delivery,
            status=OrderStatusEnum.PENDING,
            payment_method=PaymentMethod.cod.value if normalized.payment_method == "cod" else PaymentMethod.stripe.value,
            payment_status=normalized.payment_status,
            subtotal=normalized.subtotal,
            tax_amount=normalized.tax_amount,
            discount_amount=normalized.discount_amount,
            delivery_fee=normalized.delivery_fee,
            total=normalized.total,
            currency=normalized.currency,
            notes=normalized.notes,
            source=platform.value,
            external_order_id=normalized.external_order_id,
            delivery_address=normalized.delivery_address,
            estimated_ready_at=datetime.utcnow() + timedelta(minutes=normalized.estimated_ready_min),
        )
        self.db.add(order)
        await self.db.flush()

        # Create order items
        for item in normalized.items:
            order_item = OrderItem(
                id=uuid.uuid4(),
                order_id=order.id,
                item_name_snapshot=item.name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                modifier_summary=item.modifiers,
                special_instructions=item.special_instructions,
                prep_status="pending"
            )
            self.db.add(order_item)

        await self.db.flush()

        # Auto-accept if payment is confirmed
        if normalized.payment_status == "paid":
            order.status = OrderStatusEnum.CONFIRMED
            await self.db.flush()

        return ThirdPartyOrderResponse(
            internal_order_id=order.id,
            external_order_id=normalized.external_order_id,
            platform=platform,
            status="created",
            message="Order ingested successfully",
            accepted=True
        )

    async def sync_menu(
        self,
        merchant_id: UUID,
        connection_id: UUID,
        platform: PlatformType
    ) -> MenuSyncResponse:
        """Sync merchant menu to 3rd party platform."""
        from app.models import MenuItem, MenuCategory

        # Get merchant items
        items_result = await self.db.execute(
            select(MenuItem).where(
                MenuItem.merchant_id == merchant_id,
                MenuItem.is_available == True
            )
        )
        items = items_result.scalars().all()

        categories_result = await self.db.execute(
            select(MenuCategory).where(
                MenuCategory.merchant_id == merchant_id,
                MenuCategory.is_active == True
            )
        )
        categories = categories_result.scalars().all()

        # Build sync items
        sync_items = []
        for item in items:
            cat = next((c for c in categories if c.id == item.category_id), None)
            sync_items.append(MenuSyncItem(
                name=item.name,
                name_localized=item.name_localized,
                description=item.description,
                price=item.price,
                category_name=cat.name if cat else "Uncategorized",
                image_url=item.image_urls.get("primary") if item.image_urls else None,
                is_available=item.is_available
            ))

        # In production, this would call the platform API
        # For now, simulate success
        return MenuSyncResponse(
            sync_id=uuid.uuid4(),
            platform=platform,
            status=SyncStatus.completed,
            items_synced=len(sync_items),
            items_failed=0,
            categories_synced=len(categories),
            errors=[],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )

    async def verify_webhook_signature(
        self,
        platform: PlatformType,
        payload: bytes,
        signature: str,
        secret: str
    ) -> bool:
        """Verify webhook signature from 3rd party."""
        if platform == PlatformType.talabat:
            expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, signature)
        elif platform == PlatformType.zomato:
            expected = hashlib.md5(f"{secret}{payload.decode()}".encode()).hexdigest()
            return expected == signature
        elif platform == PlatformType.jahez:
            expected = hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()
            return hmac.compare_digest(expected, signature)
        return False

    async def get_platform_connections(
        self,
        merchant_id: UUID,
        platform: Optional[PlatformType] = None
    ) -> List[PlatformConnection]:
        """Get active platform connections for merchant."""
        conditions = [PlatformConnection.merchant_id == merchant_id]
        if platform:
            conditions.append(PlatformConnection.platform == platform.value)

        result = await self.db.execute(
            select(PlatformConnection).where(and_(*conditions))
        )
        return result.scalars().all()


class FallbackOrchestrator:
    """Handle failures by falling back to own delivery or manual processing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def handle_failure(
        self,
        order_id: UUID,
        platform: PlatformType,
        error: str,
        config: FallbackConfig
    ) -> FallbackLogResponse:
        """Handle 3rd party failure with retry and fallback logic."""

        # Check retry count
        retry_key = f"fallback:retry:{order_id}"
        retry_count = await cache_get(retry_key) or 0

        if retry_count < config.max_retry_attempts:
            # Retry
            await cache_set(retry_key, retry_count + 1, ttl_seconds=3600)
            return FallbackLogResponse(
                id=uuid.uuid4(),
                order_id=order_id,
                platform=platform,
                attempt=retry_count + 1,
                action="retry",
                error=error,
                success=False,
                created_at=datetime.utcnow()
            )

        # Max retries reached - fallback
        if config.fallback_to_own_delivery:
            # Route to own delivery fleet
            order_result = await self.db.execute(
                select(Order).where(Order.id == order_id)
            )
            order = order_result.scalar_one_or_none()

            if order:
                order.source = f"{platform.value}_fallback"
                await self.db.flush()

                # Trigger auto-assign if delivery
                if order.order_type.value == "delivery":
                    from app.services.delivery_service import DeliveryAssignmentService
                    assign_service = DeliveryAssignmentService(self.db)
                    await assign_service.auto_assign(order.merchant_id, order.id)

            return FallbackLogResponse(
                id=uuid.uuid4(),
                order_id=order_id,
                platform=platform,
                attempt=config.max_retry_attempts,
                action="fallback_own",
                error=error,
                success=True,
                created_at=datetime.utcnow()
            )

        elif config.fallback_to_manual:
            # Flag for manual intervention
            order_result = await self.db.execute(
                select(Order).where(Order.id == order_id)
            )
            order = order_result.scalar_one_or_none()
            if order:
                order.notes = f"{order.notes or ''}\n[MANUAL FALLBACK] {platform.value}: {error}"
                await self.db.flush()

            return FallbackLogResponse(
                id=uuid.uuid4(),
                order_id=order_id,
                platform=platform,
                attempt=config.max_retry_attempts,
                action="fallback_manual",
                error=error,
                success=True,
                created_at=datetime.utcnow()
            )

        # Complete failure
        return FallbackLogResponse(
            id=uuid.uuid4(),
            order_id=order_id,
            platform=platform,
            attempt=config.max_retry_attempts,
            action="fail",
            error=error,
            success=False,
            created_at=datetime.utcnow()
        )
