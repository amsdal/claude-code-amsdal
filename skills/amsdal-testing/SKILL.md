---
name: amsdal-testing
description: >
  AMSDAL testing patterns, fixtures, pytest utilities.
  TRIGGER when: user writes tests for AMSDAL app, asks about test patterns/fixtures, or code has pytest files for AMSDAL models/server.
  DO NOT TRIGGER when: user writes non-AMSDAL tests.
user-invocable: false
---

# AMSDAL Testing

## Setup

AMSDAL uses **pytest** + **pytest-asyncio** for testing.

```bash
pip install amsdal[cli]
amsdal tests run          # Run all tests via CLI
```

Or directly:
```bash
hatch run test            # Run tests
hatch run cov             # Tests with coverage
pytest tests/             # Direct pytest
```

## Generating Tests

```bash
amsdal generate tests --model-name Person
```

Creates `src/tests/unit/test_person.py` with basic CRUD test skeleton.

## Test Structure

```
src/
├── tests/
│   ├── unit/
│   │   ├── test_person.py
│   │   └── test_transactions.py
│   ├── integration/
│   │   └── test_api.py
│   └── conftest.py          # Shared fixtures
```

## Testing AMSDAL Models

### Basic CRUD Test

```python
import pytest
from amsdal.models import Model


class Person(Model):
    first_name: str
    last_name: str
    age: int = 0


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

### Async Tests

```python
import pytest


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

### Using AMSDAL's Test Server

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_objects(app, auth_token):
    async with AsyncClient(app=app, base_url='http://test') as client:
        response = await client.get(
            '/api/objects/',
            params={'class_name': 'Person'},
            headers={'Authorization': f'Bearer {auth_token}'},
        )
        assert response.status_code == 200
        data = response.json()
        assert 'rows' in data
        assert 'total' in data


@pytest.mark.asyncio
async def test_create_object(app, auth_token):
    async with AsyncClient(app=app, base_url='http://test') as client:
        response = await client.post(
            '/api/objects/',
            params={'class_name': 'Person'},
            json={'first_name': 'John', 'last_name': 'Doe'},
            headers={'Authorization': f'Bearer {auth_token}'},
        )
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_execute_transaction(app, auth_token):
    async with AsyncClient(app=app, base_url='http://test') as client:
        response = await client.post(
            '/api/transactions/CreateOrder/',
            json={'product_id': 'abc', 'quantity': 2},
            headers={'Authorization': f'Bearer {auth_token}'},
        )
        assert response.status_code == 200
```

## Testing Plugins

```python
def test_event_listener_registered():
    from amsdal_utils.events import EventBus
    from amsdal_server.apps.common.events.server import RouterSetupEvent

    listeners = EventBus.get_listeners(RouterSetupEvent)
    listener_types = [type(l) for l in listeners]
    assert MyRouteListener in listener_types


@pytest.mark.asyncio
async def test_custom_endpoint(app):
    async with AsyncClient(app=app, base_url='http://test') as client:
        response = await client.get('/api/my-plugin/status')
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

### conftest.py

```python
import pytest
from amsdal_glue import init_default_containers


@pytest.fixture(autouse=True)
def setup_amsdal():
    """Initialize AMSDAL containers for each test."""
    init_default_containers()
    yield
    # cleanup if needed


@pytest.fixture
def person():
    """Create a test person."""
    p = Person(first_name='Test', last_name='User', age=25)
    p.save()
    return p


@pytest.fixture
def auth_token():
    """Get auth token for API tests."""
    from amsdal.contrib.auth.utils.jwt import create_token
    return create_token(email='test@example.com', scopes=['*:*'])
```

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

## Code Quality Commands

```bash
hatch run fmt              # Format code
hatch run style            # Lint check (ruff)
hatch run typing           # Type check (mypy)
hatch run all              # style + typing
```
