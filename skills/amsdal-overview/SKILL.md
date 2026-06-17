---
name: amsdal-overview
description: >
  AMSDAL framework architecture, key concepts, conventions, and how to create apps from scratch.
  TRIGGER when: user mentions AMSDAL, asks to create/scaffold a new app or project, or asks about AMSDAL architecture/structure.
  DO NOT TRIGGER when: user asks about specific models, server, ETL, ML, or deployment details.
user-invocable: false
---

# AMSDAL Framework Overview

## What is AMSDAL

AMSDAL is a Python SDK/framework for building data-driven applications: REST APIs, ETL pipelines, AI workflows. It provides models with versioning, automatic REST endpoints, multi-database support, and a plugin ecosystem.

## Source-of-truth precedence (when sources disagree)

1. `knowledge/` (this plugin) — generated from compiled source; ground truth for behavior, bugs, edge cases. Highest trust.
2. `docs.amsdal.com` (WebFetch) — authoritative for API / usage (field types, CLI, signatures).
3. This skill's prose — curated quick-reference, may drift. Lowest trust.

Use `knowledge/` for "why does it behave this way / debugging", docs for "how do I use X / what's supported", this skill to orient and route to those.

## Before you commit to anything concrete

This skill is a routing index, not a complete or current spec. Before you finalize ANY concrete artifact — a model or field definition, a transaction or function signature, a CLI command or flag, a server route, a config key, an import path, an API call — confirm it against an authoritative source FIRST:

1. `knowledge/` — if it concerns runtime behavior / debugging.
2. WebFetch the matching `docs.amsdal.com` page (map below) — for API / usage.

Do this by default, NOT only when uncertain — you cannot detect what this skill silently omits. A construct being valid Python/Pydantic, or seeming obvious, is not evidence that AMSDAL supports it.

**Docs map for this skill:**
- creating / scaffolding a new app, CLI → https://docs.amsdal.com/cli/overview/
- installation → https://docs.amsdal.com/get-started/installation/
- config.yml / connections → https://docs.amsdal.com/models/configuration/
- framework concepts / overview → https://docs.amsdal.com/models/background/

## Core Packages & Architecture

```
amsdal_utils          ← shared utilities, events system, enums
    ↑
amsdal_framework      ← core framework: models, configs, app lifecycle
    ↑
amsdal_models         ← ORM: model definitions, QuerySets, managers, migrations
    ↑
amsdal_data           ← data layer: connections, transactions, background tasks
    ↑
amsdal_server         ← FastAPI REST API server, auth, health checks
    ↑
amsdal-glue           ← ETL: multi-source queries, CQRS, planners/executors
```

**Additional packages:**
- `amsdal_cli` — CLI tool for local server, migrations, cloud deployment
- `amsdal_ml` — ML plugin: embeddings, vector search, AI agents, MCP server
- `amsdal_crm` — CRM plugin: entities, deals, pipelines, activities
- `amsdal_mail` — email plugin (SMTP, SES)
- `amsdal_storages` — S3-compatible storage
- `amsdal_langgraph` — LangGraph checkpoint persistence
- `amsdal_integrations` — third-party integrations

## Key Concepts

### Models & Versioning
Every model mutation creates a new version. Full history is preserved. Models are Pydantic v2 based with runtime validation.

### Dual Storage
- **State DB** — current state (latest version only)
- **Lakehouse** — full version history

### CQRS
Queries and commands follow separate paths through planners → tasks → executors → connections.

### Events System
Middleware-chain pattern: `Event → Listener 1 → Listener 2 → ... → Result`. Each listener receives context + next_fn, can modify context via `create_next()`.

### Singleton Managers
Core services accessed via `Container.managers.get(ManagerClass)` and `Container.services.get(ServiceClass)`.

### License Validation
On manager setup, AMSDAL runs a one-time license check per process: `authenticate()` calls `LicenseGuard.ensure_valid()` (`amsdal/manager.py:321-323` sync, `:723-725` async). This happens during app/server bootstrap; an invalid license aborts startup. No action needed for normal development — just be aware boot can fail on license errors.

### Async-First
All ORM methods have sync/async variants: `save()`/`asave()`, `execute()`/`aexecute()`, etc.

### Async/Sync Golden Rule
**If `async_mode: true` in config.yml — EVERYTHING must be async.** This includes database backends (`-async` suffix), all ORM calls (`asave()`, `aexecute()`), transactions (`@async_transaction`), and data migrations. No mixing allowed. Same rule applies in reverse for sync mode.

---

## Creating an AMSDAL App from Scratch

**A new app MUST be created with `amsdal new <APP_NAME> <OUTPUT_PATH>` — never hand-assembled.** The command generates things you cannot reliably recreate by hand: the app's UUID, the full project tree, `config.yml`, a `.env` pre-populated with a placeholder PII crypto service, and the `requirements*.txt` files. Hand-creating the project skips these and produces a subtly broken app.

```bash
amsdal new MyApp ~/projects/     # scaffold the whole project — do this first
```

Confirm the exact command and what it generates by WebFetching https://docs.amsdal.com/cli/overview/ before scaffolding.

Once the app exists, you may add **models and transactions** by hand in the right locations (`src/models/`, `src/transactions/`) — those are just Python files and do not need the CLI. `amsdal generate model/transaction/tests` is also available if you prefer scaffolding them (see https://docs.amsdal.com/cli/overview/).

The structure below is a reference for *what `amsdal new` produces*, not a manual build recipe.

### Project Structure

```
my_app/
├── src/
│   ├── models/              # Model definitions (Python files)
│   │   ├── __init__.py
│   │   ├── book.py
│   │   └── author.py
│   ├── transactions/        # Business logic functions
│   │   ├── __init__.py
│   │   └── checkout.py
│   ├── tests/
│   │   ├── __init__.py
│   │   └── unit/
│   │       ├── __init__.py
│   │       └── test_book.py
│   ├── migrations/          # Auto-generated by `amsdal migrations new`
│   ├── fixtures/            # Seed data (JSON files)
│   │   └── initial_data.json
│   └── app.py               # MainAppConfig (event listeners setup)
├── config.yml               # Database connections
├── .env                     # Environment variables & secrets
├── .amsdal-cli              # CLI config (optional)
├── requirements.txt         # Production dependencies (used in deploy)
└── requirements-dev.txt     # Dev-only dependencies (not deployed)
```

> **Every package under `src/` (`models/`, `transactions/`, `tests/`, and any subpackage) MUST contain an `__init__.py`.** Without it the directory becomes a namespace package whose `__file__` is `None`, and `amsdal migrations new` crashes in the class loader with `TypeError: ... not 'NoneType'` (from `Path(None)`). `amsdal new` creates these for you — if you add a package by hand, add the `__init__.py`.

> The steps below describe the files `amsdal new` already generated — read them to understand and **customize** the scaffold (pick DB backends, set connections, add secrets), not to create the project from scratch.

### Step 1: requirements.txt

**Important:** `requirements.txt` is used during cloud deployment. Only include production dependencies here.

**CRITICAL: Database backend dependencies must match `config.yml` backends.** The base `amsdal` package does NOT include database drivers. You MUST add the correct `amsdal-glue-connections` extras.

**Recommended default** — include both `async-sqlite` and `postgres-binary` so the app works locally (SQLite) and is ready for AMSDAL Cloud deploy (PostgreSQL) without changes:

```
amsdal[server,cli]>=0.9.0
amsdal-glue-connections[async-sqlite,postgres-binary]
# For optimized production deploy, replace postgres-binary with postgres-c:
# amsdal-glue-connections[async-sqlite,postgres-c]
# postgres-c uses psycopg[c] (psycopg3, C-based) — better performance but requires libpq-dev on the system.
# postgres-binary uses psycopg[binary] (psycopg3) — works out of the box, fine for dev and cloud deploy.
```

**Always use this combined form for new projects.** Even if the user only uses SQLite locally, AMSDAL Cloud runs PostgreSQL, so having `postgres-binary` in requirements.txt prevents deploy failures.

**Extras reference:**
| config.yml backend | Required extra |
|---|---|
| `sqlite`, `sqlite-historical` | _(none)_ |
| `sqlite-async`, `sqlite-historical-async` | `async-sqlite` |
| `postgres-state`, `postgres-historical` | `postgres-binary` (or `postgres-c`) |
| `postgres-state-async`, `postgres-historical-async` | `postgres-binary` (or `postgres-c`) |

Add plugin packages as needed:
```
amsdal[server,cli]>=0.9.0
amsdal-glue-connections[async-sqlite,postgres-binary]
amsdal-ml>=0.1.0
amsdal-crm>=0.1.0
amsdal-mail[smtp]>=0.1.0
```

### Step 1b: requirements-dev.txt

Dev-only dependencies — NOT deployed to cloud:

```
-r requirements.txt
pytest>=7.0
pytest-asyncio>=0.21
coverage>=7.0
ruff>=0.4.0
mypy>=1.10
```

### Step 2: config.yml

```yaml
# Sync mode
application_name: MyApp

connections:
  - name: lakehouse
    backend: sqlite-historical
    credentials:
      - db_path: ./lakehouse.db

  - name: state
    backend: sqlite
    credentials:
      - db_path: ./state.db

resources_config:
  lakehouse: lakehouse
  repository:
    default: state
```

```yaml
# Async mode
application_name: MyApp
async_mode: true

connections:
  - name: lakehouse
    backend: sqlite-historical-async
    credentials:
      - db_path: ./lakehouse.db

  - name: state
    backend: sqlite-async
    credentials:
      - db_path: ./state.db

resources_config:
  lakehouse: lakehouse
  repository:
    default: state
```

```yaml
# PostgreSQL (async)
application_name: MyApp
async_mode: true

connections:
  - name: lakehouse
    backend: postgres-historical-async
    credentials:
      - dsn: postgresql://user:password@localhost:5432/myapp_lakehouse

  - name: state
    backend: postgres-state-async
    credentials:
      - dsn: postgresql://user:password@localhost:5432/myapp_state

resources_config:
  lakehouse: lakehouse
  repository:
    default: state
```

```yaml
# Multiple databases — route specific models to different DBs
resources_config:
  lakehouse: lakehouse
  repository:
    default: state
    models:
      User: users-db
      AuditLog: audit-db
```

**Backend aliases:**
- State: `sqlite`, `sqlite-async`, `postgres-state`, `postgres-state-async`
- Historical: `sqlite-historical`, `sqlite-historical-async`, `postgres-historical`, `postgres-historical-async`

### Step 3: .env

**Default contribs** (AuthAppConfig + FrontendConfigAppConfig) are loaded automatically when `AMSDAL_CONTRIBS` is NOT set. Only set this variable if you need to ADD extra contribs beyond the defaults.

```bash
# Contribs — ALWAYS include both default plugins. Add extra plugins after them.
AMSDAL_CONTRIBS="amsdal.contrib.auth.app.AuthAppConfig,amsdal.contrib.frontend_configs.app.FrontendConfigAppConfig"
AMSDAL_ADMIN_USER_EMAIL=admin@example.com
AMSDAL_ADMIN_USER_PASSWORD=admin
AMSDAL_AUTH_JWT_KEY=dev-secret-key
AMSDAL_REQUIRE_DEFAULT_AUTHORIZATION=True

# Cloud credentials (if deploying)
AMSDAL_ACCESS_KEY_ID=
AMSDAL_SECRET_ACCESS_KEY=
```

**CRITICAL: `AMSDAL_CONTRIBS` REPLACES the default list, it does NOT append.** The default includes both `AuthAppConfig` and `FrontendConfigAppConfig`. If you set `AMSDAL_CONTRIBS` to only one plugin, the other is removed. **NEVER remove `FrontendConfigAppConfig`** unless the user explicitly asks — it is required for the AMSDAL Console frontend to work. When adding extra contribs (e.g. ML, CRM), append them to the full list:
```bash
AMSDAL_CONTRIBS="amsdal.contrib.auth.app.AuthAppConfig,amsdal.contrib.frontend_configs.app.FrontendConfigAppConfig,amsdal_ml.app.MLPluginAppConfig"
```

**IMPORTANT: `AMSDAL_REQUIRE_DEFAULT_AUTHORIZATION` controls the default permission mode:**
- **`True` (recommended)** — all endpoints require authentication by default. Use `@permissions(read=AllowAny)` on models and `@allow_any` on transactions that should be public. `@require_auth` is the shorthand alias for `@permissions(RequireAuth)`, and `@allow_any` for `@permissions(AllowAny)`. This is the secure default.
- **`False`** — all endpoints are public by default. Only use this if the app has no auth at all.

**If the user asks for authentication/authorization, ALWAYS set `AMSDAL_REQUIRE_DEFAULT_AUTHORIZATION=True`.** Then selectively open public endpoints with `@permissions` or `@allow_any`. Never set it to `False` when auth is needed — that defeats the purpose.

Example: a store where catalog is public but management is admin-only:
```python
# src/models/book.py — public read, admin-only write
@permissions(
    read=AllowAny,
    create=RequireAuth,
    update=RequireAuth,
    delete=RequireAuth,
)
class Book(Model):
    title: str
    price: float
```

```python
# src/transactions/place_order.py — public transaction
@allow_any
@async_transaction(name='PlaceOrder')
async def place_order(...) -> dict:
    ...
```

### Step 4: Create Models

Create Python files in `src/models/`. **Each model MUST be in its own file. File name = model name in snake_case** (e.g., `BookingOrder` → `booking_order.py`). Never put multiple models in one file.

```python
# src/models/author.py
from amsdal.models import Model


class Author(Model):
    name: str
    bio: str | None = None
```

```python
# src/models/book.py
from amsdal.models import Model
from pydantic import Field

from models.author import Author


class Book(Model):
    title: str
    isbn: str = Field(default='')
    price: float = 0.0
    author: Author
    in_stock: bool = True
```

### Step 5: Create Transactions

Create Python files in `src/transactions/`. Decorate functions with `@transaction` or `@async_transaction`:

```python
# src/transactions/checkout.py
from amsdal.transactions import transaction, async_transaction


@async_transaction(name='Checkout', tags=['orders'])
async def checkout(book_id: str, quantity: int) -> dict:
    from models.book import Book

    book = await Book.objects.get(_address__object_id=book_id).aexecute()
    if not book.in_stock:
        raise ValueError('Book is out of stock')

    return {'book': book.title, 'quantity': quantity, 'total': book.price * quantity}
```

### Step 6: Create app.py (Optional)

Only needed if you register event listeners:

```python
# src/app.py
from amsdal.contrib.app_config import AppConfig


class MainAppConfig(AppConfig):
    def on_setup(self) -> None:
        # Register event listeners here if needed
        pass
```

### Step 7: Create Fixtures (Optional)

JSON files in `src/fixtures/` are auto-loaded on server start. Every fixture **must** have `_external_id` — a unique identifier used for references and idempotent updates:

```json
{
    "Author": [
        {
            "_external_id": "orwell",
            "name": "George Orwell",
            "bio": "English novelist and essayist"
        }
    ],
    "Book": [
        {
            "_external_id": "1984",
            "title": "1984",
            "isbn": "978-0451524935",
            "price": 12.99,
            "author": "orwell",
            "in_stock": true
        }
    ]
}
```

**FK references** use the `_external_id` string of the referenced object (e.g., `"author": "orwell"`). **M2M references** use arrays: `"tags": ["fiction", "classic"]`. See the `amsdal-models` skill for full fixtures documentation.

### Step 8: Run

**Important:** Always use a virtual environment. Never install packages globally.

```bash
python -m venv .venv               # Create virtual environment
source .venv/bin/activate          # Activate (Linux/macOS)
# .venv\Scripts\activate           # Activate (Windows)

pip install -r requirements.txt    # Install production deps
pip install -r requirements-dev.txt # Install dev deps (optional)
amsdal migrations new              # Generate migrations from models
amsdal migrations apply            # Apply migrations
amsdal serve                       # Start server at http://localhost:8080
```

**Before installing packages:** Always check if a virtual environment is already active (`which python` or `echo $VIRTUAL_ENV`). If not, create one or ask the user which environment to use.

> **`amsdal serve` requires AMSDAL credentials** — without them it launches an interactive sign-up prompt that hangs an agent's shell. Don't run it unless `AMSDAL_ACCESS_KEY_ID` / `AMSDAL_SECRET_ACCESS_KEY` are set (env or `.env`); otherwise stop and ask the user to provide them or run the auth flow themselves. `migrations` / `build` / `tests` need no credentials. See [[amsdal-deploy]] → "Credentials & commands that require them".

### .amsdal-cli (Optional)

```json
{
  "config_path": "./config.yml",
  "http_port": 8080,
  "check_model_exists": true,
  "indent": 4
}
```

### Common CLI Commands

```bash
amsdal serve                       # Start local server
amsdal serve --auto-reload         # With auto-reload
amsdal migrations new              # Generate migrations
amsdal migrations apply            # Apply migrations
amsdal migrations                  # List migrations
amsdal verify --building           # Verify syntax + building
amsdal tests                       # Run tests (alias: amsdal test)
```

---

## Coding Conventions

### Style
- **Python 3.11+**
- **Ruff** for linting and formatting
- **Line length:** 120 characters
- **Quotes:** single quotes (`'`)
- **Import style:** force-single-line, order-by-type
- **Type checking:** mypy strict mode (`disallow_any_generics`, `check_untyped_defs`)
- **Formatter:** black-compatible via ruff (120 chars)

### Development Tools
- **hatch** for environment management, scripts, and builds
- **pytest** + **pytest-asyncio** for testing
- **coverage.py** for test coverage

### Common hatch commands
```bash
hatch env create       # Create virtual environment
hatch run sync         # Sync dependencies
hatch run test         # Run tests
hatch run cov          # Tests with coverage
hatch run fmt          # Format code
hatch run style        # Lint check
hatch run typing       # mypy check
hatch run all          # style + typing
hatch run lock         # Update lock file
```

### Naming Conventions
- Models: `PascalCase` (e.g., `PersonProfile`, `AuditLog`)
- Module type enum: `ModuleType.USER`, `ModuleType.CONTRIB`, `ModuleType.CORE`
- Transactions: `PascalCase` function names decorated with `@transaction`
- Config classes: `*AppConfig` (e.g., `AuthAppConfig`, `MLPluginAppConfig`)
- Managers: `*Manager` (e.g., `ConnectionManager`, `AmsdalContextManager`)

### Key Imports & Constants
```python
from amsdal_data.aliases.using import DEFAULT_DB_ALIAS, LAKEHOUSE_DB_ALIAS
from amsdal_utils.config.manager import AmsdalConfigManager  # also: from amsdal import AmsdalConfigManager
from amsdal.context.manager import AmsdalContextManager
from amsdal.models import Model, ReferenceField, ManyReferenceField
from amsdal_models import PIIStr
from amsdal.queryset import Q
from amsdal.transactions import transaction, async_transaction
from amsdal_utils.models.enums import ModuleType
from amsdal_utils.events import EventBus, EventListener, listen_to, Event, EventContext

# Auth decorators & permissions (contrib auth)
from amsdal.contrib.auth.decorators import permissions, require_auth, allow_any
from amsdal.contrib.auth.permissions import RequireAuth, AllowAny, RequirePermissions
```

## Common Mistakes to Avoid

These are critical rules that prevent broken code:

1. **Do NOT call `.save()` or `.delete()` on the same object inside hooks** — causes infinite recursion. Only call these on *other* model instances.
2. **Auth decorators MUST be above `@transaction()`** — if placed below, permissions won't work.
3. **Bulk operations do NOT trigger hooks** — `bulk_create()`, `bulk_update()`, `bulk_delete()` bypass all pre/post hooks.
4. **`SET_NULL` requires Optional field** — `on_delete=ReferenceMode.SET_NULL` only works if the FK field is `str | None = None`.
5. **Event listeners must be registered in `AppConfig.on_setup()`** — never at module top-level or in model files.
6. **Every fixture needs `_external_id`** — unique across all models, used for references between fixtures and for idempotent reloads.
7. **Resolve deferred FK in data migrations** — call `complete_deferred_foreign_keys(Model)` before accessing relationship fields on models from `schemas.get_model()`.
8. **Async mode = everything async** — if `async_mode: true`, all backends, ORM calls, transactions, and data migrations must use async variants. No mixing.
9. **Always call `.execute()` / `.aexecute()` on QuerySets** — without it, you get a QuerySet object, not results.
10. **Transactions return types must be annotated** — type annotations are used for validation and REST API schema generation.
11. **Database driver packages must be in `requirements.txt`** — `amsdal` does not bundle DB drivers. Async SQLite needs `amsdal-glue-connections[async-sqlite]`, PostgreSQL needs `amsdal-glue-connections[postgres-binary]` (or `postgres-c` for production). Without these, you get `ImportError: "aiosqlite" package is required` or similar.
12. **Never set `AMSDAL_REQUIRE_DEFAULT_AUTHORIZATION=False` when auth is needed** — this makes everything public by default, defeating the purpose of auth. Use `True` and selectively open public endpoints with `@permissions(read=AllowAny)` or `@allow_any`.
13. **Never remove default contribs from `AMSDAL_CONTRIBS`** — `AMSDAL_CONTRIBS` replaces the default list (it does not append). Always include both `AuthAppConfig` and `FrontendConfigAppConfig`. Dropping `FrontendConfigAppConfig` breaks the AMSDAL Console frontend.