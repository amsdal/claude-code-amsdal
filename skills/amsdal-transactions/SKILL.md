---
name: amsdal-transactions
description: >
  AMSDAL transactions — @transaction/@async_transaction, model arguments & reference resolution, importing models inside functions, permissions decorator order, background/scheduled transactions, rollback.
  TRIGGER when: user creates/modifies a transaction or business-logic function, uses @transaction/@async_transaction, calls a transaction via /api/transactions/, or passes models as transaction arguments.
  DO NOT TRIGGER when: user only defines models/fields/querysets with no business-logic function (use amsdal-models), or only configures server endpoints/auth (use amsdal-server).
user-invocable: false
---

# AMSDAL Transactions

Transactions are decorated functions (`@transaction` / `@async_transaction`) that run business logic atomically. Every transaction is auto-exposed as a REST endpoint at `/api/transactions/<name>/` and can be rendered as an action in the Console.

Related skills: [[amsdal-models]] (the models they operate on), [[amsdal-server]] (how they are exposed and authorized), [[amsdal-testing]] (calling them from tests).

## Before you commit to anything concrete

This skill is a routing index, not a complete or current spec. Before you finalize ANY concrete artifact — a transaction signature, an argument annotation, a decorator, an import path, an API call — confirm it against an authoritative source FIRST:

1. `knowledge/` — if it concerns runtime behavior / debugging (e.g. `knowledge/amsdal/services/transaction_execution.md` describes how arguments are preprocessed).
2. WebFetch the matching `docs.amsdal.com` page (map below) — for API / usage.

Do this by default, NOT only when uncertain — you cannot detect what this skill silently omits.

**Docs map for this skill:**
- transactions → https://docs.amsdal.com/models/transactions/
- CRUD used inside transactions → https://docs.amsdal.com/models/classes/
- relationships / references → https://docs.amsdal.com/models/relationships/
- exposing & authorizing transactions → https://docs.amsdal.com/server/rest-api-guide/

## Defining a transaction

```python
from amsdal.transactions import transaction, async_transaction


@transaction
def create_person(first_name: str) -> Person:
    p = Person(first_name=first_name)
    p.save()
    return p


@async_transaction
async def create_person(first_name: str) -> Person:
    p = Person(first_name=first_name)
    await p.asave()
    return p


# With metadata
@transaction(name='Create Person', tags=['person', 'create'])
def create_person(...): ...
```

Nested transactions are independent — an inner rollback does not affect the outer transaction.

## Async/sync rule

**If `async_mode: true` in config.yml — use `@async_transaction` and ONLY async calls** (`await x.asave()`, `await qs.aexecute()`, …). **If sync mode — `@transaction` and ONLY sync calls.** No mixing. (Discovery is mode-aware: in async mode only `@async_transaction` functions are found, and vice versa — a transaction with the wrong decorator silently "disappears" from `/api/transactions/`.)

## Import models inside the function (avoid stale class identity)

In transaction and helper modules, import model classes **inside** the function that constructs or queries them — not at module top:

```python
@async_transaction(name='CreateComment')
async def create_comment(article: 'Article', text: str) -> 'Comment':
    from models.comment import Comment   # resolve the CURRENT model build

    comment = Comment(article=article, text=text)
    await comment.asave()
    return comment
```

**Why:** AMSDAL rebuilds and re-registers model classes (notably the test harness rebuilds them for **every** test). A module-top import pins a stale class object, so constructing or FK-validating with it fails in a full test run while passing in isolation (the two runs use different class objects for the "same" model). Import per call always resolves the current build.

Top-level imports in a transaction module are fine **only for type annotations** (ideally under `if TYPE_CHECKING:`). Any construction or query must use an in-function import. Note this is the **opposite** of model files, which must import their FK targets at module top (needed for class building).

## Model arguments & reference resolution

The REST endpoint receives a raw JSON dict; `TransactionExecutionService` preprocesses it before calling your function (see `knowledge/amsdal/services/transaction_execution.md`). It **auto-loads a stored object** for an argument only when **both**:

1. the JSON value is a reference `{"ref": {...}}`, and
2. the argument annotation is a `Model` (or `Model | None`, or a union of Models).

Collections (`list[Model]`, `dict[...]`) and non-model unions are **not** auto-loaded. The `@transaction` decorator itself does **not** validate or coerce arguments.

### Single model argument — annotate as the plain Model

```python
@async_transaction(name='ArchiveArticle', tags=['articles'])
async def archive_article(article: Article) -> Article:
    # `article` is already a loaded Article — the server resolved the {"ref": ...} payload.
    article.is_archived = True
    await article.asave()
    return article
```

- **Do NOT write `article: Reference | Article`.** `Reference` is not a `Model`, so that union fails the auto-load check — the server then passes you a raw reference/dict and you must load it by hand. Plain `Article` (or `Article | None`) is correct, and also lets the API/Console treat the argument as a model picker.
- Called **directly** (e.g. from tests) no preprocessing runs — pass a real `Article` instance.

### Collections / structured input — resolve manually or use a typed DTO

Auto-load does **not** apply to `list[Article]`; via REST the items arrive as raw `{"ref": {...}}` dicts. Two valid options:

```python
from amsdal_utils.models.data_models.reference import Reference


# Option 1 — accept the list, resolve each reference yourself
@async_transaction(name='BulkArchive')
async def bulk_archive(articles: list[Article]) -> int:
    count = 0
    for raw in articles:
        article = raw if isinstance(raw, (Reference, Article)) else Reference(**raw)
        if isinstance(article, Reference):
            article = await article.aload()
        article.is_archived = True
        await article.asave()
        count += 1
    return count
```

```python
from pydantic import BaseModel


# Option 2 — a typed pydantic BaseModel DTO (REST gets a JSON schema, Console renders a form).
# Inside a BaseModel, pydantic coerces the field, so `Reference | Model` IS appropriate here.
class ArticleLine(BaseModel):
    article: Reference | Article   # pydantic coerces the incoming dict
    position: int


@async_transaction(name='Reorder')
async def reorder(lines: list[ArticleLine]) -> None:
    for raw in lines:
        line = raw if isinstance(raw, ArticleLine) else ArticleLine(**raw)
        article = line.article
        if isinstance(article, Reference):
            article = await article.aload()
        ...
```

- Never use `list[dict]` / `dict[str, Any]` for structured input — no JSON schema is generated and the Console cannot render a form. Use a `BaseModel` DTO.
- `Reference | Model` belongs **inside a `BaseModel` DTO** (pydantic coerces it), **not** as a direct transaction parameter (where it disables the server's auto-load).

## Permissions decorator order

Stack auth decorators **above** the transaction decorator (auth must be the outermost wrapper):

```python
from amsdal.contrib.auth.decorators import allow_any   # or require_auth, permissions


@allow_any
@async_transaction(name='CreateComment')
async def create_comment(...): ...
```

## Background transactions (Celery)

```python
@transaction
def send_email(email: str) -> None: ...


@transaction
def create_and_notify(name: str, email: str) -> Person:
    p = Person(first_name=name)
    p.save()
    send_email.submit(email)  # runs in background
    return p
```

## Scheduled transactions

```python
from amsdal.transactions import ScheduleConfig, Crontab


@transaction(schedule=600)  # every 10 minutes
def cleanup(): ...


@transaction(schedule_config=ScheduleConfig(schedule=Crontab(minute=0, hour=0)))
def daily_report(): ...
```

## Rollback

```python
from amsdal.utils.rollback import rollback_to_timestamp, rollback_transaction

rollback_to_timestamp(metadata.updated_at)
rollback_transaction(metadata.transaction.ref.object_id)
```
