---
name: amsdal-server
description: >
  AMSDAL Server — REST API, authentication, permissions, events, health checks.
  TRIGGER when: user works with REST API endpoints, authentication, permissions, server events, health checks, or code imports from amsdal_server.
  DO NOT TRIGGER when: user only works with models or ETL without server context.
user-invocable: false
---

# AMSDAL Server

AMSDAL Server is a FastAPI-based REST API server that automatically generates endpoints from AMSDAL models.

## Before you commit to anything concrete

This skill is a routing index, not a complete or current spec. Before you finalize ANY concrete artifact — a route, a request/response shape, an auth/permission rule, a config key, an import path, an API call — confirm it against an authoritative source FIRST:

1. `knowledge/` — if it concerns runtime behavior / debugging.
2. WebFetch the matching `docs.amsdal.com` page (map below) — for API / usage.

Do this by default, NOT only when uncertain — you cannot detect what this skill silently omits. A construct being valid Python/Pydantic, or seeming obvious, is not evidence that AMSDAL supports it.

**Docs map for this skill:**
- server overview → https://docs.amsdal.com/server/amsdal-server/
- REST API usage → https://docs.amsdal.com/server/rest-api-guide/
- authentication / permissions → https://docs.amsdal.com/server/amsdal-auth/
- server events → https://docs.amsdal.com/server/server-events/
- health checks → https://docs.amsdal.com/server/health-checks/

## REST API Endpoints

### Objects (CRUD)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/objects/?class_name=X` | List objects |
| GET | `/api/objects/{address}/` | Get single object |
| POST | `/api/objects/?class_name=X` | Create object |
| PUT / POST | `/api/objects/{address}/` | Full update (both methods registered) |
| PATCH | `/api/objects/{address}/` | Partial update |
| DELETE | `/api/objects/{address}/` | Delete object |

### Bulk Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/objects/bulk-create/?class_name=X` | Bulk create |
| PUT / POST | `/api/objects/bulk-update/` | Bulk full update (both methods registered) |
| PATCH | `/api/objects/bulk-update/` | Bulk partial update |
| POST | `/api/objects/bulk-delete/` | Bulk delete |

### Other Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/classes/` | List all model classes |
| GET | `/api/classes/{class_name}/` | Class detail |
| GET | `/api/transactions/` | List transactions |
| GET | `/api/transactions/{name}/` | Transaction detail |
| POST | `/api/transactions/{name}/` | Execute transaction |
| GET | `/api/objects/file-download/{object_id}/` | Download file |
| GET | `/api/objects/download-file/?object_id=...` | Download file (alias, `object_id` as query param) |
| POST | `/api/objects/{address}/validate/?class_name=X` | Validate without saving |
| GET | `/api/probes/liveness/` | Health check |
| GET | `/api/probes/readiness/` | Readiness probe |

## Query Parameters

### Filtering
```
?filter[field__operator]=value
```

Operators: `eq` (default), `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `icontains`, `startswith`, `istartswith`, `endswith`, `iendswith`

```
GET /api/objects/?class_name=Person&filter[age__gte]=18&filter[first_name__icontains]=john
GET /api/objects/?class_name=Person&filter[company__name]=Acme
```

### Field Selection
```
?fields[ClassName]=field1,field2
```

### Pagination
```
?page=1&page_size=10
```
Response includes `total` field.

### Ordering
```
?ordering=[field_name]         # ascending
?ordering=[-field_name]        # descending
?ordering=[last_name,first_name]
```

### Additional Parameters (list endpoint)

These apply to the list endpoint `GET /api/objects/?class_name=X`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_metadata` | bool | true | Include metadata |
| `include_subclasses` | bool | false | Include subclass objects |
| `load_references` | bool | false | Eagerly load references |
| `all_versions` | bool | false | All versions |
| `decrypt_pii` | bool | false | Decrypt PII fields |
| `select_related` | str | — | Comma-separated relations |

### Object-detail parameters

The single-object endpoint `GET /api/objects/{address}/` supports a reduced set
(it does **not** accept `include_subclasses`, `load_references`, `page`, `page_size`, or `ordering`):

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `version_id` | str | `''` | Specific version to fetch |
| `all_versions` | bool | false | Return all versions |
| `include_metadata` | bool | true | Include metadata |
| `file_optimized` | bool | false | Optimized handling for file objects |
| `decrypt_pii` | bool | false | Decrypt PII fields |
| `select_related` | str | — | Comma-separated relations |

## Authentication

Enable auth plugin via `AMSDAL_CONTRIBS`:
```bash
AMSDAL_CONTRIBS="amsdal.contrib.auth.app.AuthAppConfig"
```

### Core Auth Models

**User:** `email`, `password` (`bytes` — bcrypt hash), `permissions` (`list[Permission] | None`)
**Permission:** `resource_type` (`models`/`transactions`), `model` (name or `*`), `action` (`create`/`read`/`update`/`delete`/`execute` or `*`)
**LoginSession:** `email`, `password`, `token` (JWT returned on success), `mfa_code` (optional)

### JWT Auth
```
Authorization: Bearer <JWT_TOKEN>
```

### MFA (Multi-Factor Authentication)
Two-step login when user has active MFA device:
1. POST LoginSession with email + password → `MFARequiredError`
2. Re-POST with `mfa_code` from authenticator app

### Permission Modes

| Mode | Env Variable | Behavior |
|------|-------------|----------|
| Public API | `AMSDAL_REQUIRE_DEFAULT_AUTHORIZATION=False` | Open by default, selectively protect |
| Protected API | `AMSDAL_REQUIRE_DEFAULT_AUTHORIZATION=True` (default) | Closed by default, selectively open |

**ALWAYS use `True` when the user asks for auth/permissions.** Setting `False` makes everything public and defeats the purpose of auth. With `True`, use `@permissions(read=AllowAny)` or `@allow_any` to selectively open specific models/transactions for unauthenticated access.

## Permissions System

### Permission Strings
Format: `{resource_type}.{resource_name}:{action}`

Examples:
- `models.Post:read` — read Posts
- `models.Post:*` — all actions on Post
- `models.*:read` — read any model
- `transactions.CreateOrder:execute` — execute transaction
- `*:*` — superuser

### Permission Classes

```python
from amsdal.contrib.auth.permissions import AllowAny, RequireAuth, RequirePermissions
```

**Note:** `AllowAny` and `RequireAuth` are **singleton instances** (not classes — don't instantiate them). `RequirePermissions` is a class that takes permission strings:

```python
# Compose with & (AND) and | (OR)
RequireAuth & RequirePermissions('models.Post:read')
RequirePermissions('models.Post:read') | RequirePermissions('models.Post:create')
```

### Class-level Permissions (Decorators)

```python
from amsdal.contrib.auth.decorators import permissions, allow_any, require_auth
from amsdal.contrib.auth.permissions import AllowAny, RequireAuth, RequirePermissions

@allow_any
class PublicModel(Model):
    data: str

@require_auth
class SecretModel(Model):
    data: str

@permissions(
    read=AllowAny,
    create=RequireAuth,
    update=RequireAuth & RequirePermissions('models.Post:update'),
    delete=RequirePermissions('models.Post:delete'),
)
class Post(Model):
    title: str
```

**Important:** Auth decorators must be **above** `@transaction()`:
```python
@require_auth
@transaction()
def my_transaction(): ...
```

### Object-level Permissions

```python
class User(Model):
    email: str

    def has_object_permission(self, user, action, update_data=None, auth=None) -> bool:
        from amsdal.contrib.auth.permissions import has_admin_permissions
        if has_admin_permissions(auth):
            return True
        if user.is_authenticated:
            return self.email == user.identity
        return False
```

### Row-level Filtering (API Managers)

```python
from amsdal_models.managers.model_manager import Manager
from amsdal_models.querysets.base_queryset import QuerySet, ModelType

class PostApiManager(Manager):
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

class Post(Model):
    api_objects: ClassVar[PostApiManager] = PostApiManager()
    title: str
    author_email: str
```

## Server Events

Events emitted during server lifecycle. All use the Events System (middleware-chain pattern).

### Lifecycle Events

```python
from amsdal_utils.events import EventListener, listen_to
from amsdal_server.apps.common.events.server import (
    ServerStartupEvent, ServerStartupContext,
    ServerShutdownEvent, ServerShutdownContext,
    RouterSetupEvent, RouterSetupContext,
    MiddlewareSetupEvent, MiddlewareSetupContext,
)
```

**Initialization flow:**
1. Plugin loading (`AppConfig.on_setup()`)
2. Standard routes registered
3. **RouterSetupEvent** — add custom routes
4. Standard middleware registered
5. **MiddlewareSetupEvent** — add custom middleware
6. **License validation** (async, in lifespan) — `LicenseGuard.ensure_valid()` runs at the start of the lifespan, **before** `ServerStartupEvent`; an invalid license aborts boot
7. **ServerStartupEvent** (async, in lifespan)
8. Server running...
9. **ServerShutdownEvent** (async, in lifespan)

### Adding Custom Routes

```python
from fastapi import APIRouter

@listen_to(RouterSetupEvent)
class MyRouteListener(EventListener[RouterSetupContext]):
    def handle(self, context, next_fn):
        router = APIRouter()

        @router.get('/api/custom/hello')
        async def hello():
            return {'message': 'Hello!'}

        context.app.include_router(router)
        return next_fn(context)

    async def ahandle(self, context, next_fn):
        return self.handle(context, next_fn)
```

### Adding Custom Middleware

```python
@listen_to(MiddlewareSetupEvent)
class MyMiddlewareListener(EventListener[MiddlewareSetupContext]):
    def handle(self, context, next_fn):
        context.app.add_middleware(MyCORSMiddleware, allow_origins=['*'])
        return next_fn(context)

    async def ahandle(self, context, next_fn):
        return self.handle(context, next_fn)
```

### Pre-Response Events

Modify responses before returning to client:

```python
from amsdal_server.apps.objects.events.pre_response import (
    ObjectListPreResponseEvent, ObjectListPreResponseContext,
    ObjectDetailPreResponseEvent, ObjectDetailPreResponseContext,
)
from amsdal_server.apps.classes.events.pre_response import (
    ClassListPreResponseEvent, ClassDetailPreResponseEvent,
)
from amsdal_server.apps.transactions.events.pre_response import (
    TransactionListPreResponseEvent, TransactionDetailPreResponseEvent,
)
```

### Auth Events

```python
from amsdal_server.apps.common.events.auth import AuthenticateEvent, AuthenticateContext
from amsdal_server.apps.common.events.authorize import (
    ClassAuthorizeEvent, ClassAuthorizeContext,
    ObjectAuthorizeEvent, ObjectAuthorizeContext,
)
```

## Health Checks

### Built-in Endpoints
- `GET /api/probes/liveness/` — 200 if healthy, 503 if any check fails
- `GET /api/probes/readiness/` — 200 when ready for traffic

### Custom Health Checker

```python
from amsdal_server.apps.healthcheck.services.checkers.base import BaseHealthchecker
from amsdal_server.apps.healthcheck.serializers.healthcheck_result import HealthcheckServiceResult
from amsdal_server.apps.healthcheck.enums import StatusEnum

class RedisHealthchecker(BaseHealthchecker):
    async def check(self) -> HealthcheckServiceResult:
        try:
            await redis_client.ping()
            return HealthcheckServiceResult(
                status=StatusEnum.success,
                service=self.__class__.__name__,
                message='Redis is available',
            )
        except Exception as e:
            return HealthcheckServiceResult(
                status=StatusEnum.error,
                service=self.__class__.__name__,
                message=f'Redis check failed: {e}',
            )
```

Register:
```python
from amsdal_server.apps.healthcheck.services.healthcheck import HealthcheckService

healthcheck_service = HealthcheckService(conditions=[
    ConnectionsHealthchecker(),
    RedisHealthchecker(),
])
```

### Kubernetes Example
```yaml
livenessProbe:
  httpGet:
    path: /api/probes/liveness/
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /api/probes/readiness/
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AMSDAL_CONTRIBS` | Comma-separated contrib app configs |
| `AMSDAL_ADMIN_USER_EMAIL` | Admin email (created on startup) |
| `AMSDAL_ADMIN_USER_PASSWORD` | Admin password |
| `AMSDAL_AUTH_JWT_KEY` | JWT signing key |
| `AMSDAL_REQUIRE_DEFAULT_AUTHORIZATION` | Require auth by default (true) |

See `examples.md` for more code examples.