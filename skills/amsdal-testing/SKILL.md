---
name: amsdal-testing
description: >
  AMSDAL testing patterns, fixtures, pytest utilities.
  TRIGGER when: user writes tests for AMSDAL app, asks about test patterns/fixtures, or code has pytest files for AMSDAL models/server.
  DO NOT TRIGGER when: user writes non-AMSDAL tests.
user-invocable: false
---

# AMSDAL Testing

## Before you commit to anything concrete

This skill is a routing index, not a complete or current spec. Before you finalize ANY concrete artifact — a fixture, a test-runner command/flag, a pytest utility, an import path, an API call — confirm it against an authoritative source FIRST:

1. `knowledge/` — if it concerns runtime behavior / debugging.
2. WebFetch the matching `docs.amsdal.com` page (map below) — for API / usage.

Do this by default, NOT only when uncertain — you cannot detect what this skill silently omits.

**Docs map for this skill:**
- testing (fixtures, CLI test runner, patterns) → https://docs.amsdal.com/models/testing/

## Setup

AMSDAL uses **pytest** + **pytest-asyncio** for testing.

The recommended way to run an app's tests is the CLI command, which **builds the app, runs migrations, and then launches pytest** with the right DB flags:

```bash
amsdal tests              # alias: amsdal test — run all tests via CLI
```

The CLI forwards database options to pytest. Choose the backend(s) to run against:

```bash
amsdal tests                                                    # SQLite state + SQLite lakehouse (default)
amsdal tests --state-option postgres --lakehouse-option postgres   # Postgres state + lakehouse
amsdal tests --db-execution-type lakehouse_only                # lakehouse only, no state DB
```

Any extra args after the known options are passed straight through to pytest, e.g. `amsdal tests -k test_create -x`.

You can also call pytest directly against the `src/` tree (the generated `conftest.py` already wires DB setup; see below). When run directly, the DB options fall back to their SQLite defaults:

```bash
pytest src/                       # run all tests under src/
pytest src/tests/unit/test_person.py
```

> Generated apps ship a `requirements.txt` and are run with `amsdal tests` / `pytest`. The `hatch run …` scripts (`test`, `cov`, `fmt`, `style`, `all`) belong to the AMSDAL framework packages themselves and are **not** present in a generated application.

## Generating Tests

```bash
amsdal generate tests --model-name Person
```

Creates `src/tests/unit/test_person.py` with create / update / delete tests. The generated tests:

- import the model from the generated `models` package (e.g. `from models.person import Person`),
- use **Faker** for field values and `LAKEHOUSE_DB_ALIAS` (from `amsdal_models.querysets.executor`) for lakehouse counts,
- assert by **counting rows in both the state and lakehouse databases** before/after each operation (e.g. `Person.objects.all().count().execute() == 1` and `Person.objects.all().using(LAKEHOUSE_DB_ALIAS).count().execute() == 2` after an update, since the lakehouse keeps every version).

## Test Structure

```
src/
├── tests/
│   ├── unit/
│   │   ├── test_person.py
│   │   └── test_transactions.py
│   ├── integration/
│   │   └── test_api.py
│   └── conftest.py          # Shared fixtures (init_db + DB options)
```

## How tests are wired (conftest)

AMSDAL models cannot be defined inline in a test module — they live in `src/models/`, are built into the `models` package, and must be **migrated** before a test can touch the database. The generated `conftest.py` handles all of this: it adds the DB CLI options, then an **autouse** `init_db` fixture builds a throwaway database and runs migrations around every test, using `init_manager_and_migrate` from `amsdal.utils.tests.helpers`.

This is the real shape of a generated **sync** `conftest.py`:

```python
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from amsdal.manager import AmsdalManager
from amsdal.utils.tests.enums import DbExecutionType
from amsdal.utils.tests.enums import LakehouseOption
from amsdal.utils.tests.enums import StateOption
from amsdal.utils.tests.helpers import init_manager_and_migrate

SRC_DIR = Path(__file__).parent.parent


def pytest_addoption(parser: Any) -> None:
    parser.addoption('--db_execution_type', action='store', default=DbExecutionType.include_state_db)
    parser.addoption('--state_option', action='store', default=StateOption.sqlite)
    parser.addoption('--lakehouse_option', action='store', default=LakehouseOption.sqlite)


@pytest.fixture(scope='module')
def lakehouse_option(request: Any) -> str:
    return request.config.getoption('--lakehouse_option')


@pytest.fixture(scope='module')
def db_execution_type(request: Any) -> str:
    return request.config.getoption('--db_execution_type')


@pytest.fixture(scope='module')
def state_option(request: Any) -> str:
    return request.config.getoption('--state_option')


@pytest.fixture(scope='function', autouse=True)
def init_db(
    db_execution_type: DbExecutionType,
    state_option: StateOption,
    lakehouse_option: LakehouseOption,
) -> Generator[AmsdalManager, Any, None]:
    with init_manager_and_migrate(
        src_dir_path=SRC_DIR,
        db_execution_type=db_execution_type,
        lakehouse_option=lakehouse_option,
        state_option=state_option,
    ) as manager:
        yield manager
```

For an **async** app, the conftest is identical except it imports `AsyncAmsdalManager` and `async_init_manager_and_migrate`, and `init_db` is a `@pytest_asyncio.fixture` that `async with`-enters the async helper.

The DB option enums (all `StrEnum`, from `amsdal.utils.tests.enums`):

| Enum | Members |
|---|---|
| `DbExecutionType` | `lakehouse_only`, `include_state_db` (default) |
| `StateOption` | `sqlite` (default), `postgres` |
| `LakehouseOption` | `postgres`, `sqlite` (default) |

These map directly to the `--db-execution-type` / `--state-option` / `--lakehouse-option` flags on `amsdal tests`.

## Gotchas (read before debugging a flaky failure)

- **`init_db` is function-scoped → model classes are rebuilt for every test.** The autouse fixture re-runs the build/migrate per test, so the class object for a given model differs between tests. If a transaction or helper module imports a model **at module top**, it pins the class object from the first build; a later test constructs a fresh instance whose class no longer matches, and FK validation fails with errors like *"Input should be a valid instance of X"*. The fix lives in [[amsdal-transactions]]: **import model classes inside the function**, never at module top. (Top-level import is fine only for type annotations.)
- **Run the WHOLE suite, not just the file you changed.** This class-identity failure (and other ordering effects) only appears across multiple tests — a test that passes in isolation can fail in the full run, and vice versa. Always confirm with the complete `amsdal tests` run before claiming green.

## Testing AMSDAL Models

### Basic CRUD Test

Import models from the generated `models` package — never declare a `Model` subclass inside a test:

```python
from models.person import Person


def test_create_person():
    person = Person(first_name='John', last_name='Doe', age=25)
    person.save()

    result = Person.objects.get(first_name='John').execute()
    assert result.first_name == 'John'
    assert result.last_name == 'Doe'
    assert result.age == 25


def test_update_person():
    person = Person(first_name='John', last_name='Doe')
    person.save()

    person.age = 30
    person.save()

    updated = Person.objects.get(first_name='John').execute()
    assert updated.age == 30


def test_delete_person():
    person = Person(first_name='John', last_name='Doe')
    person.save()

    person.delete()

    result = Person.objects.get_or_none(first_name='John').execute()
    assert result is None


def test_bulk_operations():
    people = [
        Person(first_name='Alice', last_name='A'),
        Person(first_name='Bob', last_name='B'),
    ]
    Person.objects.bulk_create(people)

    total = Person.objects.count().execute()
    assert total == 2
```

If you need a model class dynamically (e.g. by name, or to reach a contrib model), use the class manager instead of importing:

```python
from amsdal_models.contexts import get_class_manager
from amsdal_utils.models.enums import ModuleType


def test_import_class_by_name():
    Person = get_class_manager().import_class('Person', ModuleType.USER)
    Person(first_name='John', last_name='Doe').save()
    assert Person.objects.all().count().execute() == 1
```

> **Equality caveat:** `Model.__eq__` (and `==`) is **pk-only** — two instances compare equal when they share a type and primary key, regardless of version or field values. Don't assert object equality to check that a save persisted specific data; assert on the queried fields instead. To require the same `object_version` too, use `instance.equals_with_version(other)` (async: `aequals_with_version`).

### Async Tests

```python
import pytest

from models.person import Person


@pytest.mark.asyncio
async def test_async_create():
    person = Person(first_name='Jane', last_name='Doe')
    await person.asave()

    result = await Person.objects.get(first_name='Jane').aexecute()
    assert result.first_name == 'Jane'


@pytest.mark.asyncio
async def test_async_queryset():
    await Person(first_name='Alice', age=20).asave()
    await Person(first_name='Bob', age=30).asave()

    adults = await Person.objects.filter(age__gte=21).aexecute()
    assert len(adults) == 1
    assert adults[0].first_name == 'Bob'
```

## Testing Transactions

```python
import pytest
from amsdal.transactions import transaction


@transaction(name='TransferFunds')
def transfer_funds(from_id: str, to_id: str, amount: float) -> dict:
    from_acc = Account.objects.get(account_id=from_id).execute()
    to_acc = Account.objects.get(account_id=to_id).execute()
    if from_acc.balance < amount:
        raise ValueError('Insufficient funds')
    from_acc.balance -= amount
    from_acc.save()
    to_acc.balance += amount
    to_acc.save()
    return {'success': True}


def test_transfer_funds_success():
    acc1 = Account(account_id='A', balance=100.0)
    acc1.save()
    acc2 = Account(account_id='B', balance=50.0)
    acc2.save()

    result = transfer_funds('A', 'B', 30.0)

    assert result['success'] is True
    assert Account.objects.get(account_id='A').execute().balance == 70.0
    assert Account.objects.get(account_id='B').execute().balance == 80.0


def test_transfer_funds_insufficient():
    acc1 = Account(account_id='A', balance=10.0)
    acc1.save()
    acc2 = Account(account_id='B', balance=50.0)
    acc2.save()

    with pytest.raises(ValueError, match='Insufficient funds'):
        transfer_funds('A', 'B', 100.0)

    # Transaction should have rolled back
    assert Account.objects.get(account_id='A').execute().balance == 10.0
    assert Account.objects.get(account_id='B').execute().balance == 50.0
```

## Testing Hooks

```python
def test_pre_create_hook():
    """Test that pre_create sets default name."""
    person = Person(first_name='', last_name='Doe')

    with pytest.raises(ValueError, match='first_name is required'):
        person.save()


def test_post_create_hook():
    """Test that post_create creates a related profile."""
    person = Person(first_name='John', last_name='Doe')
    person.save()

    profile = PersonProfile.objects.get_or_none(
        person=person.build_reference(),
    ).execute()
    assert profile is not None
```

## Testing Validation

```python
import pytest
from pydantic import ValidationError


def test_valid_age():
    person = Person(first_name='John', last_name='Doe', age=25)
    assert person.age == 25


def test_invalid_age():
    with pytest.raises(ValidationError):
        Person(first_name='John', last_name='Doe', age=-5)


def test_invalid_type():
    with pytest.raises(ValidationError):
        Person(first_name='John', last_name='Doe', age='not_a_number')
```

## Testing Server (API)

### AmsdalTestClient

The server ships its own test client, `AmsdalTestClient` (a subclass of FastAPI/Starlette's `TestClient`) with auth helpers baked in — there is **no** JWT/Bearer-token flow to set up. Build it around your app and authenticate by patching the auth backend, not by sending headers:

```python
from amsdal_server.testing import AmsdalTestClient

client = AmsdalTestClient(app)

client.login_as_admin()                                    # full access, scope '*:*'
client.force_authenticate(user='editor', scopes=['models.Post:read', 'models.Post:create'])
client.logout()                                            # clears authentication
```

- `login_as_admin()` — shortcut for `force_authenticate(user='admin', scopes=['*:*'])`.
- `force_authenticate(user=None, scopes=None)` — `user` may be a username `str` or a `BaseUser`; passing `user=None` clears auth. `scopes` are scope strings like `'models.Post:read'`.
- `login_as(user, scopes=None)` / `logout()` are also available.

The server test suite exposes ready-made `client` and `async_client` fixtures that yield an `AmsdalTestClient`. Note the client is **synchronous** even when wrapping an async app — call `client.get(...)` without `await`:

```python
import pytest


@pytest.mark.asyncio
async def test_list_objects(async_client: AmsdalTestClient):
    async_client.login_as_admin()
    response = async_client.get('/api/objects/', params={'class_name': 'Person'})
    assert response.status_code == 200
    data = response.json()
    assert 'rows' in data
    assert 'total' in data


@pytest.mark.asyncio
async def test_create_object(async_client: AmsdalTestClient):
    async_client.login_as_admin()
    response = async_client.post(
        '/api/objects/',
        params={'class_name': 'Person'},
        json={'first_name': 'John', 'last_name': 'Doe'},
    )
    assert response.status_code == 201   # object create returns 201 Created


@pytest.mark.asyncio
async def test_execute_transaction(async_client: AmsdalTestClient):
    async_client.login_as_admin()
    response = async_client.post(
        '/api/transactions/CreateOrder/',
        json={'product_id': 'abc', 'quantity': 2},
    )
    assert response.status_code == 200
```

### Testing permissions

Combine `force_authenticate` with `override_auth_settings` to assert authorization behaviour. `override_auth_settings` temporarily flips auth settings (e.g. `REQUIRE_DEFAULT_AUTHORIZATION`):

```python
import pytest
from amsdal.contrib.auth.testing import override_auth_settings

from amsdal_server.testing import AmsdalTestClient


@pytest.mark.asyncio
async def test_requires_scope(async_client: AmsdalTestClient):
    with override_auth_settings(REQUIRE_DEFAULT_AUTHORIZATION=True):
        # No scope → forbidden
        response = async_client.get('/api/objects/', params={'class_name': 'Post'})
        assert response.status_code == 403

        # Correct scope → allowed
        async_client.force_authenticate(user='test', scopes=['models.Post:read'])
        response = async_client.get('/api/objects/', params={'class_name': 'Post'})
        assert response.status_code == 200
```

## Testing Plugins

`EventBus.get_listeners(event)` returns a list of listener **ID strings**, not listener instances. Each ID is `f'{cls.__module__}.{cls.__name__}'`, so assert membership by that dotted string:

```python
def test_event_listener_registered():
    from amsdal_utils.events import EventBus
    from amsdal_server.apps.common.events.server import RouterSetupEvent

    listener_ids = EventBus.get_listeners(RouterSetupEvent)
    assert 'my_plugin.listeners.MyRouteListener' in listener_ids
```

A plugin's custom endpoints are tested through the same server `AmsdalTestClient` — the route is mounted when the app builds, so just hit it via the `client` / `async_client` fixture:

```python
import pytest

from amsdal_server.testing import AmsdalTestClient


@pytest.mark.asyncio
async def test_custom_endpoint(async_client: AmsdalTestClient):
    async_client.login_as_admin()
    response = async_client.get('/api/my-plugin/status')
    assert response.status_code == 200
    assert response.json() == {'status': 'active'}
```

## Testing External Models

```python
def test_external_model_query():
    users = LegacyUser.objects.filter(active=True).execute()
    assert all(u.active for u in users)


def test_external_model_count():
    total = LegacyUser.objects.count().execute()
    assert total >= 0
```

## Fixtures & Conftest Patterns

The database is wired by the generated `conftest.py` `init_db` autouse fixture (see **How tests are wired** above). Do **not** call `init_default_containers()` yourself — on its own it sets up nothing, and the `init_manager_and_migrate` helper already builds the manager, runs migrations, and tears down around every test.

Add your own data/object fixtures on top of that. Because `init_db` is autouse and function-scoped, anything you create in a fixture lands in the fresh per-test database:

```python
import pytest

from models.person import Person


@pytest.fixture
def person() -> Person:
    """Create a test person in the (already-migrated) test database."""
    p = Person(first_name='Test', last_name='User', age=25)
    p.save()
    return p
```

For API auth, do **not** mint tokens — there is no JWT/`create_token` helper. Use the `AmsdalTestClient` auth helpers (`login_as_admin()` / `force_authenticate(...)`) shown in **Testing Server (API)**.

### Seed Data (fixtures/)

JSON fixtures in `src/fixtures/` are auto-loaded on server start:

```json
{
    "Person": [
        {
            "first_name": "Admin",
            "last_name": "User",
            "email": "admin@example.com"
        }
    ]
}
```

## Best Practices

1. **TDD style:** Tests should FAIL on buggy code and PASS after the fix
2. **Never write tests that pass on broken code**
3. **Use in-memory SQLite** for unit tests — fast and isolated
4. **Mock external services** (API calls, email, etc.)
5. **Test both sync and async** variants of your code
6. **Test validation** — ensure invalid data is rejected
7. **Test hooks** — verify lifecycle side effects
8. **Test transactions** — verify atomicity on error
9. **Test permissions** — verify auth requirements
10. **Bulk operations don't trigger hooks** — test this explicitly

## Running the suite

```bash
amsdal tests              # build + migrate + pytest (alias: amsdal test)
pytest src/               # run pytest directly (SQLite defaults)
```

> `hatch run …` scripts (`test`, `cov`, `fmt`, `style`, `all`) are part of the **AMSDAL framework packages'** own dev tooling — they are **not** present in a generated application, which ships a `requirements.txt` and is driven by `amsdal tests` / `pytest`.
