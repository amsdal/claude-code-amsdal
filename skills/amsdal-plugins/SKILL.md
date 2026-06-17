---
name: amsdal-plugins
description: >
  Creating AMSDAL plugins — AppConfig, events system, custom routes, middleware.
  TRIGGER when: user creates a custom AMSDAL plugin, works with AppConfig, events system, custom middleware, or asks about plugin architecture.
  DO NOT TRIGGER when: user uses existing plugins (use amsdal-ecosystem instead).
user-invocable: false
---

# AMSDAL Plugins

## Before you commit to anything concrete

This skill is a routing index, not a complete or current spec. Before you finalize ANY concrete artifact — an AppConfig, an event handler, a custom route/middleware, a config key, an import path, an API call — confirm it against an authoritative source FIRST:

1. `knowledge/` — if it concerns runtime behavior / debugging.
2. WebFetch the matching `docs.amsdal.com` page (map below) — for API / usage.

Do this by default, NOT only when uncertain — you cannot detect what this skill silently omits. A construct being valid Python, or seeming obvious, is not evidence that AMSDAL supports it.

**Docs map for this skill:**
- plugins overview → https://docs.amsdal.com/models/plugins/overview/
- events system → https://docs.amsdal.com/framework/events/

## Plugin Structure

```
my_plugin/
├── __init__.py
├── app.py                  # AppConfig — plugin entry point
├── models/                 # Plugin models
│   ├── __init__.py
│   └── my_model.py
├── transactions/           # Business logic
│   ├── __init__.py
│   └── my_transaction.py
├── event_handlers/         # Event listeners
│   ├── __init__.py
│   └── listeners.py
└── fixtures/               # Seed data (optional)
    └── initial.json
```

## AppConfig (Plugin Entry Point)

```python
from amsdal.contrib.app_config import AppConfig


class MyPluginAppConfig(AppConfig):
    title = 'My Plugin'  # optional — controls dashboard display

    def on_setup(self) -> None:
        from amsdal_utils.events import EventBus
        from amsdal_server.apps.common.events.server import RouterSetupEvent, ServerStartupEvent
        from my_plugin.event_handlers.listeners import MyRouteListener, MyStartupListener

        EventBus.subscribe(RouterSetupEvent, MyRouteListener)
        EventBus.subscribe(ServerStartupEvent, MyStartupListener)
```

**Optional overrides:**

- `title` (class attribute) — how the app appears in places like the auto-synthesized dashboard. Defaults to `''`.
- `slug` (property) — stable identifier, derived by convention from the package containing the AppConfig (e.g. `amsdal_storages.app.StoragesAppConfig` → `'amsdal_storages'`). Override if your package does not follow the standard `<package>.app.<NameAppConfig>` layout.
- `models_module_prefix` (property) — module path under which the app's models live (e.g. `<package>.models`). Override if models live elsewhere.

### Registration

Add to `AMSDAL_CONTRIBS` environment variable:
```bash
AMSDAL_CONTRIBS="amsdal.contrib.auth.app.AuthAppConfig,my_plugin.app.MyPluginAppConfig"
```

**Load order:** Plugins (via `AMSDAL_CONTRIBS`) → Application (via `APP_CONFIG`, default: `app.MainAppConfig`)

## Events System

Middleware-chain pattern: each listener receives context + next_fn, modifies context via `create_next()`.

```
Event → Listener 1 → Listener 2 → Listener 3 → Result
         ↓            ↓            ↓
      next_fn()    next_fn()    next_fn()
```

### Core Components

```python
from amsdal_utils.events import Event, EventContext, EventListener, EventBus, listen_to
```

### Defining Events & Contexts

`EventContext` is a **frozen Pydantic model** (`BaseModel`, `arbitrary_types_allowed`). Declare subclasses plainly — do **not** use `@dataclass` (it breaks `create_next()` / `model_copy()` / history).

```python
from amsdal_utils.events import Event, EventContext


class MyContext(EventContext):
    value: int
    processed: bool = False


class MyEvent(Event[MyContext]):
    pass
```

### Creating Listeners

```python
from amsdal_utils.events import EventListener, listen_to


@listen_to(MyEvent, priority=100)
class MyListener(EventListener[MyContext]):
    def handle(self, context: MyContext, next_fn):
        new_context = context.create_next(
            listener_id=self.listener_id,
            processed=True,
            value=context.value * 2,
        )
        return next_fn(new_context)

    async def ahandle(self, context: MyContext, next_fn):
        new_context = context.create_next(
            listener_id=self.listener_id,
            processed=True,
            value=context.value * 2,
        )
        return await next_fn(new_context)
```

### Emitting Events

```python
from amsdal_utils.events import EventBus

# Sync
result = EventBus.emit(MyEvent, MyContext(value=5))

# Async
result = await EventBus.aemit(MyEvent, MyContext(value=5))
```

### Listener Ordering

**By priority** (lower executes first):
```python
@listen_to(MyEvent, priority=100)   # first
class FirstListener(...): ...

@listen_to(MyEvent, priority=200)   # second
class SecondListener(...): ...
```

**By dependencies:**
```python
@listen_to(MyEvent, after=[AuthListener], before=[MLListener])
class CustomListener(...): ...

# String paths for cross-module
@listen_to(MyEvent, after=['myapp.auth.AuthListener'])
class CustomListener(...): ...
```

### Error Handling

```python
from amsdal_utils.events import ErrorStrategy

# Per-listener
@listen_to(MyEvent, error_strategy=ErrorStrategy.LOG_AND_CONTINUE)
class SafeListener(...): ...

# Per-event (default for all listeners)
class SafeEvent(Event[MyContext]):
    default_error_strategy = ErrorStrategy.LOG_AND_CONTINUE
```

**Strategies:** `PROPAGATE` (raise, stop chain), `LOG_AND_CONTINUE`, `SILENT`

### Context History

```python
result = EventBus.emit(MyEvent, context)
history = result.history                            # full mutation history
version = result.get_by_listener('listener_id')     # specific version
```

## Server Events Reference

### Lifecycle Events

| Event | When | Sync/Async |
|-------|------|------------|
| `RouterSetupEvent` | After routes registered | sync (`handle()`) |
| `MiddlewareSetupEvent` | After middleware registered | sync (`handle()`) |
| `ServerStartupEvent` | Server start (lifespan) | async (`ahandle()`) |
| `ServerShutdownEvent` | Server stop (lifespan) | async (`ahandle()`) |

### Pre-Response Events

| Event | When |
|-------|------|
| `ObjectListPreResponseEvent` | Before object list response |
| `ObjectDetailPreResponseEvent` | Before object detail response |
| `ClassListPreResponseEvent` | Before class list response |
| `ClassDetailPreResponseEvent` | Before class detail response |
| `TransactionListPreResponseEvent` | Before transaction list response |
| `TransactionDetailPreResponseEvent` | Before transaction detail response |

### Auth Events

| Event | When |
|-------|------|
| `AuthenticateEvent` | During request authentication |
| `ClassAuthorizeEvent` | Class-level permission check |
| `ObjectAuthorizeEvent` | Object-level permission check |

## Plugin Models

Use `ModuleType.CONTRIB` to indicate plugin models:

```python
from typing import ClassVar

from amsdal.models import Model
from amsdal_utils.models.enums import ModuleType


class AuditLog(Model):
    __module_type__: ClassVar[ModuleType] = ModuleType.CONTRIB

    action: str
    user_email: str
    details: str
    timestamp: str
```

Plugin models get their own migration namespace (applied between core and app migrations).

## Plugin Transactions

AMSDAL auto-discovers transactions in `transactions/` directory:

```python
from amsdal.transactions import transaction
from amsdal.contrib.auth.decorators import require_auth


@require_auth
@transaction(tags=['Audit'])
def export_audit_log(date_from: str, date_to: str) -> dict:
    from my_plugin.models.audit_log import AuditLog

    entries = list(AuditLog.objects.filter(
        timestamp__gte=date_from,
        timestamp__lte=date_to,
    ).execute())

    return {'count': len(entries), 'entries': [e.model_dump() for e in entries]}
```

Exposed via REST API:
- `GET /api/transactions/` — lists all (including plugin transactions)
- `POST /api/transactions/export_audit_log/` — execute

**Important:** Auth decorators must be **above** `@transaction()`.

## Adding Custom Routes

```python
from fastapi import APIRouter
from amsdal_utils.events import EventListener, listen_to
from amsdal_server.apps.common.events.server import RouterSetupEvent, RouterSetupContext


@listen_to(RouterSetupEvent)
class MyRouteListener(EventListener[RouterSetupContext]):
    def handle(self, context: RouterSetupContext, next_fn):
        router = APIRouter(tags=['my-plugin'])

        @router.get('/api/my-plugin/status')
        async def status():
            return {'status': 'active'}

        @router.post('/api/my-plugin/action')
        async def action(data: dict):
            return {'result': 'ok'}

        context.app.include_router(router)
        return next_fn(context)

    async def ahandle(self, context, next_fn):
        return self.handle(context, next_fn)
```

## Adding Custom Middleware

```python
from starlette.middleware.base import BaseHTTPMiddleware
from amsdal_utils.events import EventListener, listen_to
from amsdal_server.apps.common.events.server import MiddlewareSetupEvent, MiddlewareSetupContext


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        import time
        start = time.time()
        response = await call_next(request)
        response.headers['X-Process-Time'] = str(time.time() - start)
        return response


@listen_to(MiddlewareSetupEvent)
class TimingMiddlewareListener(EventListener[MiddlewareSetupContext]):
    def handle(self, context: MiddlewareSetupContext, next_fn):
        context.app.add_middleware(TimingMiddleware)
        return next_fn(context)

    async def ahandle(self, context, next_fn):
        return self.handle(context, next_fn)
```

## For Application (not plugin) Event Setup

Create `src/app.py`:

```python
from amsdal.contrib.app_config import AppConfig


class MainAppConfig(AppConfig):
    def on_setup(self) -> None:
        from amsdal_utils.events import EventBus
        from amsdal_server.apps.common.events.server import ServerStartupEvent
        from my_listeners import MyStartupListener

        EventBus.subscribe(ServerStartupEvent, MyStartupListener)
```

## Built-in Plugins

Registered via `AMSDAL_CONTRIBS`:

| Plugin | AppConfig | Description |
|--------|-----------|-------------|
| Auth | `amsdal.contrib.auth.app.AuthAppConfig` | Authentication & permissions |
| Frontend Configs | `amsdal.contrib.frontend_configs.app.FrontendConfigAppConfig` | UI field configs |
| ML | `amsdal_ml.app.MLPluginAppConfig` | Embeddings, vector search, agents, MCP |
| Mail | `amsdal_mail.app.MailAppConfig` | SMTP/SES email |
| LangGraph | `amsdal_langgraph.app.AmsdalLangGraphAppConfig` | LangGraph checkpoint persistence |

**Storages** has **no** AppConfig and is **not** registered via `AMSDAL_CONTRIBS`. It is wired through the `DEFAULT_FILE_STORAGE` setting (which selects the storage backend class):

```bash
DEFAULT_FILE_STORAGE="amsdal_storages.s3.S3Storage"
```

## Complete Plugin Example

```python
# my_analytics/app.py
from amsdal.contrib.app_config import AppConfig

class AnalyticsAppConfig(AppConfig):
    def on_setup(self) -> None:
        from amsdal_utils.events import EventBus
        from amsdal_server.apps.common.events.server import RouterSetupEvent, ServerStartupEvent
        from my_analytics.listeners import AnalyticsRouteListener, AnalyticsInitListener

        EventBus.subscribe(RouterSetupEvent, AnalyticsRouteListener)
        EventBus.subscribe(ServerStartupEvent, AnalyticsInitListener)


# my_analytics/models/page_view.py
from typing import ClassVar

from amsdal.models import Model
from amsdal_utils.models.enums import ModuleType

class PageView(Model):
    __module_type__: ClassVar[ModuleType] = ModuleType.CONTRIB
    path: str
    user_email: str | None = None
    timestamp: str


# my_analytics/listeners.py
from fastapi import APIRouter
from amsdal_utils.events import EventListener, listen_to
from amsdal_server.apps.common.events.server import RouterSetupEvent, RouterSetupContext

@listen_to(RouterSetupEvent)
class AnalyticsRouteListener(EventListener[RouterSetupContext]):
    def handle(self, context, next_fn):
        router = APIRouter(tags=['analytics'])

        @router.get('/api/analytics/page-views')
        async def page_views(path: str | None = None):
            from my_analytics.models.page_view import PageView
            qs = PageView.objects.all()
            if path:
                qs = qs.filter(path=path)
            total = await qs.count().aexecute()
            return {'total': total}

        context.app.include_router(router)
        return next_fn(context)

    async def ahandle(self, context, next_fn):
        return self.handle(context, next_fn)


# Register: AMSDAL_CONTRIBS="...,my_analytics.app.AnalyticsAppConfig"
```