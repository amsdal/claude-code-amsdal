# AMSDAL Server — Code Examples

## Complete Auth Setup

```python
# .env
AMSDAL_CONTRIBS="amsdal.contrib.auth.app.AuthAppConfig"
AMSDAL_ADMIN_USER_EMAIL="admin@example.com"
AMSDAL_ADMIN_USER_PASSWORD="securepassword"
AMSDAL_AUTH_JWT_KEY="your-secret-key"
AMSDAL_REQUIRE_DEFAULT_AUTHORIZATION=True
```

## Model with Full Permission Configuration

```python
from typing import ClassVar, Any
from amsdal.models import Model
from amsdal.contrib.auth.decorators import permissions
from amsdal.contrib.auth.permissions import AllowAny, RequireAuth, RequirePermissions
from amsdal_models.managers.model_manager import Manager
from amsdal_models.querysets.base_queryset import QuerySet, ModelType


class PostApiManager(Manager):
    """Row-level filtering: users only see their own posts."""

    def get_queryset(self) -> QuerySet[ModelType]:
        from amsdal.context.manager import AmsdalContextManager
        from amsdal.contrib.auth.utils.scopes import is_super_admin

        qs = super().get_queryset()
        request = AmsdalContextManager().get_context().get('request', None)

        if not request or not request.auth:
            return qs.none()

        user_scopes = set(getattr(request.auth, 'scopes', []))
        if is_super_admin(user_scopes):
            return qs

        auth_user = getattr(request, 'user', None)
        if auth_user and auth_user.is_authenticated:
            return qs.filter(author_email=auth_user.identity)
        return qs.none()


@permissions(
    read=AllowAny,
    create=RequireAuth,
    update=RequireAuth & RequirePermissions('models.Post:update'),
    delete=RequirePermissions('models.Post:delete'),
)
class Post(Model):
    api_objects: ClassVar[PostApiManager] = PostApiManager()

    title: str
    content: str
    author_email: str
    published: bool = False

    def has_object_permission(
        self,
        user: 'BaseUser',
        action: 'Action',
        update_data: dict[str, Any] | None = None,
        auth: 'AuthCredentials | None' = None,
    ) -> bool:
        from amsdal.contrib.auth.permissions import has_admin_permissions

        if has_admin_permissions(auth):
            return True

        if user.is_authenticated:
            return self.author_email == user.identity

        return False
```

## Secured Transaction

```python
from amsdal.contrib.auth.decorators import require_auth, permissions
from amsdal.contrib.auth.permissions import RequirePermissions
from amsdal.transactions import transaction


@require_auth
@transaction(name='CreateOrder', tags=['orders'])
def create_order(product_id: str, quantity: int) -> dict:
    product = Product.objects.get(product_id=product_id).execute()
    if product.stock < quantity:
        raise ValueError('Insufficient stock')

    order = Order(product=product, quantity=quantity)
    order.save()

    product.stock -= quantity
    product.save()

    return {'order_id': order.get_metadata().object_id}
```

## Custom Routes Plugin

```python
from fastapi import APIRouter, Depends
from amsdal_utils.events import EventListener, listen_to
from amsdal_server.apps.common.events.server import RouterSetupEvent, RouterSetupContext


@listen_to(RouterSetupEvent)
class AnalyticsRouteListener(EventListener[RouterSetupContext]):
    def handle(self, context: RouterSetupContext, next_fn):
        router = APIRouter(tags=['analytics'])

        @router.get('/api/analytics/summary')
        async def summary():
            total_users = await User.objects.count().aexecute()
            total_orders = await Order.objects.count().aexecute()
            return {
                'total_users': total_users,
                'total_orders': total_orders,
            }

        @router.get('/api/analytics/top-products')
        async def top_products(limit: int = 10):
            products = await Product.objects.order_by('-sold_count')[:limit].aexecute()
            return [{'name': p.name, 'sold': p.sold_count} for p in products]

        context.app.include_router(router)
        return next_fn(context)

    async def ahandle(self, context, next_fn):
        return self.handle(context, next_fn)
```

## Custom Middleware

```python
import time
from starlette.middleware.base import BaseHTTPMiddleware
from amsdal_utils.events import EventListener, listen_to
from amsdal_server.apps.common.events.server import MiddlewareSetupEvent, MiddlewareSetupContext


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.time()
        response = await call_next(request)
        response.headers['X-Process-Time'] = str(time.time() - start)
        return response


@listen_to(MiddlewareSetupEvent)
class TimingMiddlewareListener(EventListener[MiddlewareSetupContext]):
    def handle(self, context: MiddlewareSetupContext, next_fn):
        context.app.add_middleware(RequestTimingMiddleware)
        return next_fn(context)

    async def ahandle(self, context, next_fn):
        return self.handle(context, next_fn)
```

## Server Startup Initialization

```python
from amsdal_utils.events import EventListener, listen_to
from amsdal_server.apps.common.events.server import ServerStartupEvent, ServerStartupContext


@listen_to(ServerStartupEvent)
class CacheWarmupListener(EventListener[ServerStartupContext]):
    async def ahandle(self, context: ServerStartupContext, next_fn):
        # Warm up caches on server startup
        categories = await Category.objects.all().aexecute()
        cache = {c.get_metadata().object_id: c for c in categories}
        context.app.state.category_cache = cache
        return await next_fn(context)

    def handle(self, context, next_fn):
        raise NotImplementedError
```

## Pre-Response Event (Enrich API Response)

```python
from amsdal_utils.events import EventListener, listen_to
from amsdal_server.apps.objects.events.pre_response import (
    ObjectListPreResponseEvent,
    ObjectListPreResponseContext,
)


@listen_to(ObjectListPreResponseEvent)
class EnrichOrderListListener(EventListener[ObjectListPreResponseContext]):
    async def ahandle(self, context: ObjectListPreResponseContext, next_fn):
        if context.class_name != 'Order':
            return await next_fn(context)

        # Add computed column to response
        enriched_response = context.response.model_copy(
            update={'columns': context.response.columns + [{'name': 'total_display', 'type': 'str'}]}
        )
        context = context.create_next(
            listener_id=self.listener_id,
            response=enriched_response,
        )
        return await next_fn(context)

    def handle(self, context, next_fn):
        raise NotImplementedError
```

## Custom Health Checker

```python
from amsdal_server.apps.healthcheck.services.checkers.base import BaseHealthchecker
from amsdal_server.apps.healthcheck.serializers import HealthcheckServiceResult, StatusEnum


class ExternalAPIHealthchecker(BaseHealthchecker):
    async def check(self) -> HealthcheckServiceResult:
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get('https://api.external-service.com/health', timeout=5.0)
                if resp.status_code == 200:
                    return HealthcheckServiceResult(
                        status=StatusEnum.success,
                        service=self.__class__.__name__,
                        message='External API is available',
                    )
                return HealthcheckServiceResult(
                    status=StatusEnum.error,
                    service=self.__class__.__name__,
                    message=f'External API returned {resp.status_code}',
                )
        except Exception as e:
            return HealthcheckServiceResult(
                status=StatusEnum.error,
                service=self.__class__.__name__,
                message=f'External API check failed: {e}',
            )
```

## REST API Usage Examples

```bash
# List objects with filtering
curl "http://localhost:8080/api/objects/?class_name=Person&filter[age__gte]=18&page=1&page_size=10"

# Get single object
curl "http://localhost:8080/api/objects/{address}/"

# Create object
curl -X POST "http://localhost:8080/api/objects/?class_name=Person" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"first_name": "John", "last_name": "Doe"}'

# Bulk create
curl -X POST "http://localhost:8080/api/objects/bulk-create/?class_name=Person" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '[{"first_name": "Alice"}, {"first_name": "Bob"}]'

# Update
curl -X PATCH "http://localhost:8080/api/objects/{address}/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"age": 31}'

# Delete
curl -X DELETE "http://localhost:8080/api/objects/{address}/" \
  -H "Authorization: Bearer $TOKEN"

# Execute transaction
curl -X POST "http://localhost:8080/api/transactions/CreateOrder/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"product_id": "abc123", "quantity": 2}'

# Login
curl -X POST "http://localhost:8080/api/objects/?class_name=LoginSession" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "securepassword"}'

# With PII decryption
curl "http://localhost:8080/api/objects/?class_name=Customer&decrypt_pii=true" \
  -H "Authorization: Bearer $TOKEN"

# File download
curl "http://localhost:8080/api/objects/file-download/{file_object_id}/?disposition_type=inline"

# Health check
curl "http://localhost:8080/api/probes/liveness/"
```

## Role-Based Permission Examples

```python
# Superuser — full access
# Permission: *:*

# Content Administrator
# Permissions:
#   models.Post:*
#   models.Comment:*
#   models.Category:read
#   transactions.*:read

# Read-only User
# Permissions:
#   models.Post:read
#   models.Comment:read

# API Integration
# Permissions:
#   transactions.CreateOrder:execute
#   transactions.GetOrderStatus:execute
#   models.Order:read
```