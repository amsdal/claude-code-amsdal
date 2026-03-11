---
name: amsdal-models
description: >
  AMSDAL models, fields, relationships, CRUD, QuerySets, transactions, hooks, migrations.
  TRIGGER when: user creates/modifies models, works with fields/relationships/ForeignKey, QuerySets, CRUD operations, migrations, or code imports from amsdal.models.
  DO NOT TRIGGER when: user asks about server endpoints, ETL, or deployment.
user-invocable: false
---

# AMSDAL Models

## File Convention

**Each model MUST be in its own file.** File name = model name in snake_case. Never put multiple models in one file.
- `BookingOrder` → `src/models/booking_order.py`
- `OrderItem` → `src/models/order_item.py`
- `Author` → `src/models/author.py`

## Model Definition

Models inherit from `Model` and are Pydantic v2 based:

```python
from amsdal.models import Model

class Person(Model):
    first_name: str
    last_name: str
    age: int = 0
    email: str | None = None
```

### Table Configuration

```python
from typing import ClassVar
from amsdal.models import IndexInfo, UniqueConstraint

class Person(Model):
    __table_name__: ClassVar[str] = 'people'                    # custom table name
    __primary_key__: ClassVar[list[str]] = ['person_id']         # custom PK
    __indexes__: ClassVar[list[IndexInfo]] = [
        IndexInfo(field='email', name='idx_email'),
    ]
    __constraints__: ClassVar[list[UniqueConstraint]] = [
        UniqueConstraint(fields=['email'], name='unique_email'),
    ]

    person_id: int
    email: str
```

### Inheritance

Inheritance creates **separate tables** connected by a FK on the primary key. The child table duplicates all parent fields for performance.

```python
class Person(Model):
    first_name: str

class Employee(Person):
    company_name: str
```

**Database result:** `Person` table + `Employee` table (with `first_name` + `company_name`), linked by `Employee.partition_key → Person.partition_key`. Querying is transparent — both parent and child fields are filterable on the child model. Migrations handle dependency order automatically (parent created before child).

## Field Types

- **Required:** `name: str`
- **Optional:** `name: str | None = None`
- **With default:** `age: int = 21`
- **VectorField:** `embedding: VectorField(768)` — from `amsdal_models.classes.fields.vector`
- **FileField:** `doc: File = FileField(storage=DBStorage())` — `FileField` from `amsdal_models.classes.fields.file`, `File` from `amsdal.models.core.file`
- **PIIStr:** `email: PIIStr = Field(title='email')` — AES-256-GCM encrypted field, from `amsdal_models`

## Relationships

### Many-to-One (Foreign Key)

```python
from amsdal.models import ReferenceField
from amsdal_models.classes.relationships.enum import ReferenceMode

class Person(Model):
    asset: Asset                                                    # simple FK — preferred!
    asset: Asset = ReferenceField(..., db_field='asset_id')         # custom column name
    asset: Asset = ReferenceField(..., on_delete=ReferenceMode.CASCADE)  # on delete behavior
```

**ReferenceMode options:** `CASCADE`, `PROTECT`, `RESTRICT`, `SET_NULL`, `SET_DEFAULT`, `DO_NOTHING`

### Many-to-Many

**IMPORTANT: M2M fields MUST NOT have a default value (no `= []`). This will raise `AmsdalModelError`.**

```python
from amsdal.models import ManyReferenceField

class Person(Model):
    assets: list[Asset]  # auto junction table — NO default value!

    # OR with custom junction:
    assets: list[Asset] = ManyReferenceField(
        through=PersonAsset,
        through_fields=('person', 'asset'),
    )
```

### Frozen References
Pin a reference to a specific version:
```python
frozen_ref = person.build_reference(is_frozen=True)
event = Event(name='Birthday', person=frozen_ref)
```

## Async/Sync Rule

**If `async_mode: true` in config.yml — use ONLY async methods everywhere:** `asave()`, `aexecute()`, `adelete()`, `@async_transaction`, async data migrations. **If sync mode — use ONLY sync methods.** No mixing.

## CRUD Operations

### Create
```python
# Sync
person = Person(first_name='John', last_name='Doe')
person.save()

# Async
await person.asave()

# Bulk
Person.objects.bulk_create(people)            # sync
await Person.objects.bulk_acreate(people)     # async
```

### Read
```python
# All
persons = Person.objects.all().execute()                    # sync
persons = await Person.objects.all().aexecute()             # async

# Filter
persons = Person.objects.filter(name='John').execute()

# Single
person = Person.objects.get(email='john@example.com').execute()
person = Person.objects.get_or_none(email='john@example.com').execute()
person = Person.objects.first(age__gt=18).execute()

# Count
total = Person.objects.count().execute()
```

### Update
```python
person = Person.objects.get(email='john@example.com').execute()
person.last_name = 'Smith'
person.save()  # creates new version

# Bulk
Person.objects.bulk_update(people)
```

### Delete
```python
person.delete()                            # sync
await person.adelete()                     # async
Person.objects.bulk_delete(people)         # bulk sync
await Person.objects.bulk_adelete(people)  # bulk async
```

### Refetch
```python
person = person.refetch_from_db()               # sync
person = await person.arefetch_from_db()        # async
person = person.refetch_from_db(latest=True)    # latest version
```

## QuerySet API

### Chaining Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `all()` | QuerySet | No filters |
| `filter(*args, **kwargs)` | QuerySet | Include matching |
| `exclude(*args, **kwargs)` | QuerySet | Exclude matching |
| `get(**kwargs)` | Single | Exactly one or error |
| `get_or_none(**kwargs)` | Single/None | One or None |
| `first(**kwargs)` | Single/None | First result |
| `count()` | int | Count results |
| `order_by(*fields)` | QuerySet | Sort (prefix `-` for desc) |
| `distinct(fields)` | QuerySet | Unique results |
| `only(fields)` | QuerySet | Load specific fields only |
| `select_related(*fields)` | QuerySet | Eager-load relations |
| `using(alias)` | QuerySet | Use specific connection |
| `latest()` | QuerySet | Latest versions only |
| `annotate(**kwargs)` | QuerySet | Add annotations |
| `decrypt_pii()` | QuerySet | Decrypt PII fields |
| `none()` | QuerySet | Empty queryset |

### Pagination (Slicing)
```python
Person.objects.all()[0:10].execute()      # first 10
Person.objects.all()[20:30].execute()     # skip 20, get 10
```

### Field Lookups

**Comparison:** `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `isnull`
**String:** `contains`, `icontains`, `startswith`, `istartswith`, `endswith`, `iendswith`
**Nested:** `json_field__nested_field__eq='value'`
**Related:** `company__name='Acme'` (with `select_related`)
**Metadata:** `_metadata__is_deleted=True`, `_metadata__created_at__gt=timestamp`

### Q Objects (Complex Queries)

```python
from amsdal.queryset import Q

# AND
Q(gender='male') & Q(age__gt=18)

# OR
Q(gender='male') | Q(gender='female')

# NOT
~Q(is_active=False)

# Nested
Q(gender='male') & Q(Q(age__lt=18) | Q(age__gt=65))

# With QuerySet
Person.objects.filter(Q(age__lt=18) | Q(gender='female'), city='London')
```

### select_related (Avoid N+1)

```python
persons = Person.objects.select_related('company', 'company__location').all().execute()
for p in persons:
    print(p.company.location.name)  # already loaded
```

## Transactions

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

# Nested transactions are independent — inner rollback doesn't affect outer
```

### Model References in Transaction Arguments

When a transaction accepts a model as input (e.g. selecting a Book in an order), **use `Reference | Model` type inside a Pydantic `BaseModel`**. The AMSDAL Console will render a proper picker/selector for the model, and the REST API will accept a reference object. Inside the transaction, resolve the reference with `.load()` / `.aload()`.

**IMPORTANT:** Never use `list[dict]` or `dict[str, Any]` for structured input — the REST API won't generate a proper JSON schema and the Console can't render a form. Always use a typed Pydantic `BaseModel`.

```python
from pydantic import BaseModel
from amsdal.transactions import async_transaction
from amsdal_utils.models.data_models.reference import Reference

from models.book import Book


class OrderItemInput(BaseModel):
    book: Reference | Book   # Console renders as a Book picker
    quantity: int


@async_transaction(name='PlaceOrder', tags=['orders'])
async def place_order(
    customer_name: str,
    items: list[OrderItemInput],
) -> Order:
    for raw_item in items:
        item = raw_item if isinstance(raw_item, OrderItemInput) else OrderItemInput(**raw_item)
        book = item.book

        # Resolve reference to actual model instance
        if isinstance(book, Reference):
            book = await book.aload()

        # Now use book.title, book.price, etc.
        ...
```

**Key rules:**
- Use `Reference | Model` (not just `Model`) — the API sends a reference, not the full object
- Always check `isinstance(book, Reference)` and call `.aload()` (async) or `.load()` (sync) to get the real instance
- Use `BaseModel` (not AMSDAL `Model`) for input DTOs — these are not stored in the DB
- Handle `raw_item` as either dict or `OrderItemInput` since the server may pass raw dicts

### Background Transactions (Celery)
```python
@transaction
def send_email(email: str) -> None: ...

@transaction
def create_and_notify(name: str, email: str) -> Person:
    p = Person(first_name=name).save()
    send_email.submit(email)  # runs in background
    return p
```

### Scheduled Transactions
```python
@transaction(schedule=600)  # every 10 minutes
def cleanup(): ...

@transaction(schedule_config=ScheduleConfig(schedule=Crontab(minute=0, hour=0)))
def daily_report(): ...
```

### Rollback
```python
from amsdal.utils.rollback import rollback_to_timestamp, rollback_transaction

rollback_to_timestamp(metadata.updated_at)
rollback_transaction(metadata.transaction.ref.object_id)
```

## Hooks (Lifecycle)

| Hook | Sync | Async | When |
|------|------|-------|------|
| Before init | `pre_init` | — | Before init & validation |
| After init | `post_init` | — | After init & validation |
| Before create | `pre_create` | `apre_create` | Before first save |
| After create | `post_create` | `apost_create` | After first save |
| Before update | `pre_update` | `apre_update` | Before update |
| After update | `post_update` | `apost_update` | After update |
| Before delete | `pre_delete` | `apre_delete` | Before delete |
| After delete | `post_delete` | `apost_delete` | After delete |

**Important:** Do NOT call `.save()` or `.delete()` on the same object inside hooks. Bulk operations do NOT trigger hooks.

```python
class Person(Model):
    def pre_create(self):
        if not self.name:
            self.name = 'Default'

    def post_create(self):
        PersonProfile(person=self).save()

    def pre_update(self):
        original = self.refetch_from_db()
        if original.name != self.name:
            raise ValueError('Name cannot be changed')
```

## Metadata

Every mutation creates metadata. Read-only access:

```python
metadata = person.get_metadata()       # sync
metadata = await person.aget_metadata() # async
```

**Fields:** `is_deleted`, `created_at` (ms), `updated_at` (ms), `object_id`, `object_version`, `prior_version`, `next_version`, `address`, `reference_to`, `referenced_by`, `transaction`

## Version History

```python
prev = person.previous_version()       # sync
prev = await person.aprevious_version() # async
nxt = person.next_version()
```

## PII Encryption

Field-level AES-256-GCM encryption backed by AWS KMS:

```python
from amsdal.models import Model
from amsdal_models import PIIStr
from pydantic import Field

class Customer(Model):
    name: str
    email: PIIStr = Field(title='email')

# Decrypt on read
users = await User.objects.decrypt_pii().aexecute()

# REST API: GET /api/objects/?class_name=User&decrypt_pii=true
```

## Validation

Pydantic v2 validators work on AMSDAL models:

```python
from pydantic import field_validator, model_validator

class Person(Model):
    age: int

    @field_validator('age')
    @classmethod
    def validate_age(cls, v):
        if v < 0 or v > 150:
            raise ValueError('Age must be between 0 and 150')
        return v
```

## Migrations

```bash
amsdal migrations new                    # generate schema migration
amsdal migrations new --data --name populate_roles  # data migration
amsdal migrations apply                  # apply all pending
amsdal migrations apply --number 0003    # rollback to 0003
amsdal migrations                        # list with status
```

Data migration template:
```python
from amsdal_models.migration import migrations

def forward_migration(schemas: migrations.MigrationSchemas) -> None:
    User = schemas.get_model('User')
    # use User.objects... for queries

class Migration(migrations.Migration):
    operations = [
        migrations.MigrateData(forward_migration=forward_migration, backward_migration=backward_migration),
    ]
```

**Important:** For relationship fields in data migrations, resolve deferred references:
```python
from amsdal_models.classes.relationships.helpers.deferred_foreign_keys import complete_deferred_foreign_keys
complete_deferred_foreign_keys(Order)
```

## External Models (Read-Only)

```python
from amsdal_models.classes.external_model import ExternalModel

class ExternalUser(ExternalModel):
    __table_name__ = 'users'
    __connection__ = 'external_db'
    __primary_key__ = ['id']
    id: int
    username: str

users = ExternalUser.objects.filter(active=True).execute()
```

## Serialization

```python
person.model_dump()       # resolves references
person.model_dump_refs()  # keeps references as Reference dicts
person.model_dump_json()  # JSON string, keeps references
```

## Context Manager

```python
from amsdal import AmsdalContextManager

context = AmsdalContextManager.get_context()
request = context['request']  # Starlette Request when running with server
```

## Fixtures

Fixtures are seed data auto-loaded on server start from `src/fixtures/`. Supports JSON and CSV formats.

### Key Rules
- **Every fixture MUST have `_external_id`** — unique across ALL models. Used for FK/M2M references and idempotent reloads (re-running won't duplicate data).
- **`_order`** (optional, default `0`) — controls load sequence. Supports negative values and floats.
- **Deleting a fixture file does NOT delete DB records** — must delete manually.

### Single-File (Multiple Models)

```json
{
    "Category": [
        {"_external_id": "fiction", "name": "Fiction"},
        {"_external_id": "science", "name": "Science"}
    ],
    "Author": [
        {"_external_id": "orwell", "name": "George Orwell", "bio": "English novelist"}
    ],
    "Book": [
        {
            "_external_id": "1984",
            "_order": 1,
            "title": "1984",
            "price": 12.99,
            "author": "orwell",
            "categories": ["fiction", "science"]
        }
    ]
}
```

### FK References
Use the `_external_id` string of the target object:
```json
{"_external_id": "book1", "title": "1984", "author": "orwell"}
```

### M2M References
Use an array of `_external_id` strings:
```json
{"_external_id": "book1", "tags": ["fiction", "classic", "dystopia"]}
```

### Self-References
```json
{
    "Category": [
        {"_external_id": "root", "name": "Root", "parent": null},
        {"_external_id": "child", "_order": 1, "name": "Child", "parent": "root"}
    ]
}
```

### File Fixtures
Place files in `src/fixtures/files/{ModelName}/`:
```
src/fixtures/
├── data.json
└── files/
    └── Document/
        ├── contract.pdf
        └── readme.txt
```

Reference by path `{ModelName}/{filename}`:
```json
{"_external_id": "doc1", "name": "Contract", "file": "Document/contract.pdf"}
```

For file arrays:
```json
{"_external_id": "hotel1", "photos": ["Property/1.jpg", "Property/2.jpg"]}
```

### Per-Model Directory Structure
Alternative to single-file: one folder per model with JSON/CSV inside.
```
src/fixtures/
├── Author/
│   └── authors.json
├── Book/
│   └── books.csv
└── files/
    └── ...
```

### CSV Format
```csv
_external_id,name,email,company,tags
john,John Doe,john@example.com,acme_company,"tag1,tag2"
jane,Jane Doe,jane@example.com,acme_company,tag1
```

Comma-separated values in a cell are automatically split for M2M fields. Empty cells become `None`.

See `examples.md` for more code examples.