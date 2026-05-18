from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.db.session import async_session
from app.models import Tenant


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tenant_slug = request.headers.get("X-Tenant-ID") or self.resolve_from_host(request)

        async with async_session() as db:
            from sqlalchemy import select
            stmt = select(Tenant).where(Tenant.slug == tenant_slug)
            result = await db.execute(stmt)
            tenant = result.scalar_one_or_none()
            if tenant:
                request.state.tenant_id = str(tenant.id)
                request.state.tenant_schema = f"tenant_{tenant.slug}"

                # Set PostgreSQL context for RLS
                await db.execute(f"SET search_path TO {request.state.tenant_schema}, public")
                await db.execute(f"SET app.current_tenant = '{tenant.id}'")

        response = await call_next(request)
        return response

    def resolve_from_host(self, request: Request) -> str:
        host = request.headers.get("host", "")
        # Extract tenant from subdomain: tenant.qrmenu.com
        return host.split(".")[0] if "." in host else "default"
