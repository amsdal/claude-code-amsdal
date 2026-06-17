---
name: amsdal-models
description: >
  AMSDAL models, fields, relationships, CRUD, QuerySets, transactions, hooks, migrations.
  TRIGGER when: user creates/modifies models, works with fields/relationships/ForeignKey, QuerySets, CRUD operations, migrations, or code imports from amsdal.models.
  DO NOT TRIGGER when: user asks about server endpoints, ETL, or deployment.
user-invocable: false
---

# AMSDAL Models

## Before you commit to anything concrete

This skill is a routing index, not a complete or current spec. Before you finalize ANY concrete artifact — a model or field definition, a transaction or function signature, a config key, an import path, an API call — confirm it against an authoritative source FIRST:

1. `knowledge/` — if it concerns runtime behavior / debugging.
2. WebFetch the matching `docs.amsdal.com` page (map below) — for API / usage.

Do this by default, NOT only when uncertain — you cannot detect what this skill silently omits. A construct being valid Python/Pydantic, or seeming obvious, is not evidence that AMSDAL supports it.

**Docs map for this skill:**
- field types (incl. what types are/aren't supported) → https://docs.amsdal.com/models/field-types/
- model definition → https://docs.amsdal.com/models/model_definition/python-class/
- relationships (FK / M2M) → https://docs.amsdal.com/models/relationships/
- CRUD operations → https://docs.amsdal.com/models/classes/
- querysets / filtering → https://docs.amsdal.com/models/queryset/queryset/
- field lookups → https://docs.amsdal.com/models/queryset/fields-lookup/
- Q objects → https://docs.amsdal.com/models/queryset/q-object/
- transactions → https://docs.amsdal.com/models/transactions/
- hooks → https://docs.amsdal.com/models/hooks/
- metadata → https://docs.amsdal.com/models/metadata/
- PII encryption → https://docs.amsdal.com/models/pii-encryption/
- migrations → https://docs.amsdal.com/models/migrations/
- fixtures → https://docs.amsdal.com/models/fixtures/
- validation / serialization → https://docs.amsdal.com/models/pydantic/
- external models → https://docs.amsdal.com/models/external-models/
- file storage → https://docs.amsdal.com/models/file-storage/

## File Convention

**Each model MUST be in its own file.** File name = model name in snake_case. Never put multiple models in one file.
- `BookingOrder` → `src/models/booking_order.py`
- `OrderItem` → `src/models/order_item.py`
- `Author` → `src/models/author.py`

**Imports use the `models.` / `transactions.` root — never `src.models.` / `src.transactions.`** — even though the files live under `src/`. A pre-build step collects `src/` into the project root, so imports are rooted there:
- `from models.order_item import OrderItem`
- `from transactions.create_order import create_order`

This applies to `TypeModel` files and cross-model references too (e.g. `from models.address import Address`).

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

**Database result:** `Person` table + `Employee` table (with `first_name` + `company_name`), linked by a foreign key on the primary key. Querying is transparent — both parent and child fields are filterable on the child model. Migrations handle dependency order automatically (parent created before child).

### TypeModel (Embedded Value Objects)

For structured data that should live **inline inside an owning `Model`** (no table, no own id) — e.g. an address, a line item, or a chat message — subclass `TypeModel` instead of `Model`.

```python
from amsdal_models.classes.model import Model, TypeModel

class Address(TypeModel):          # own file: src/models/address.py
    street: str
    city: str
    zip_code: str | None = None

class Company(Model):              # own file: src/models/company.py
    name: str
    headquarters: Address          # stored inline (JSONB) on the Company row
    branches: list[Address] = []   # list of embedded value objects
```

The file convention still applies — **each `TypeModel` goes in its own file** too. When a `Model` references a `TypeModel` from another file, call `Model.model_rebuild()` after the class to resolve the reference.

Key facts (from source):
- **Stored inline (JSONB) inside the owning Model** via plain pydantic `model_dump()` — a `TypeModel` has no table, no `_object_id`, no `save()`/`delete()`, and is not queried on its own.
- **No ORM fields inside it.** A `TypeModel` field may only be a primitive or another `TypeModel` — annotating a field with an ORM `Model` type raises `TypeError` at class creation. Use a `ReferenceField` on the owning `Model` for relations instead.
- **No lifecycle hooks** run for `TypeModel` (`pre_*`/`post_*` create/update/delete are not called). Hooks belong on `Model`.
- **No FK/PK/M2M/`__table_name__` ClassVars.** It does keep `__module_type__: ClassVar[ModuleType]` (default `USER`).
- `validate_assignment=True`, and a JSON **string** is accepted where a `TypeModel` is expected — the `TypeModel` subclass parses it to a dict first (e.g. `Address.model_validate('{...}')`).

### TimestampMixin (auto `created_at` / `updated_at`)

Mix `TimestampMixin` into a `Model` for auto-managed timestamp fields. It is commonly wanted — **default to adding it when generating a model** (or ask the user first).

```python
from amsdal.models.mixins import TimestampMixin
from amsdal.models import Model

class Article(TimestampMixin, Model):     # mixin FIRST, then Model
    title: str
```

- Adds `created_at: datetime | None` and `updated_at: datetime | None`.
- **Auto-stamped via hooks:** `pre_create`/`apre_create` set `created_at`; `pre_update`/`apre_update` set `updated_at` (both `datetime.now(tz=UTC)`).
- **Bulk operations skip hooks** — timestamps are NOT auto-set on `bulk_create`/`bulk_update`. Call `instance.stamp_timestamp(action='create')` / `stamp_timestamp(action='update')` before bulk-saving.
- Pair with `__ordering__: ClassVar[str | list[str]] = ['-updated_at']` to list newest-first.

## Field Types

Declaration syntax follows standard Python class annotations:

- **Required:** `name: str`
- **Optional:** `name: str | None = None`
- **With default:** `age: int = 21`

For the authoritative set of supported field types — which Python types are allowed, AMSDAL special fields (vector, file, PII, references), and any type that is **not** supported — **WebFetch https://docs.amsdal.com/models/field-types/ and verify before choosing a type.** Do not assume a type works just because it is valid Python/Pydantic.

### Restricting a field to a set of values

AMSDAL **does** support enum-style fields. All three forms below convert to a schema property carrying `enum` + `options` metadata, which is what drives the dropdown rendering in Console — they do not "collapse" to an untyped value.

```python
from enum import Enum
from typing import Any, Literal

from pydantic import field_validator

from amsdal.models import Model, validate_options


# 1. Literal — fixes the allowed values at the type level
class Product(Model):
    size: Literal['small', 'medium', 'large']


# 2. Enum subclass — becomes its own named type (options + labels)
class Color(str, Enum):
    RED = 'red'
    GREEN = 'green'
    BLUE = 'blue'

class Item(Model):
    color: Color


# 3. validate_options — stays a plain `str`, validated at runtime
class Package(Model):
    unit: str

    @field_validator('unit')
    @classmethod
    def validate_unit(cls: type, value: Any) -> Any:
        return validate_options(value, options=['kg', 'g', 'lb'])
```

Use `Literal`/`Enum` to fix the type; use `validate_options` to keep a plain `str` field while still restricting (and rendering) the allowed set. See https://docs.amsdal.com/models/model_definition/python-class/ for the `validate_options` validator.

## Display Name (UI-friendly labels)

Every `Model` has a `display_name` property. **By default it returns the object's address (an id-like string)** — not user-friendly. Override it so Console and reference pickers show a readable label.

**When generating a model, add a `display_name` whenever it has obvious human-readable field(s)** (name, title, label, code…).

### Preferred: build it from the model's own scalar fields (no extra queries)

```python
class Customer(Model):
    first_name: str
    last_name: str

    @property
    def display_name(self) -> str:
        return f'{self.first_name} {self.last_name}'
```

`display_name` shows up in Console object/list views and in **FK enrichment**: when another model references this one via FK, the server adds this `display_name` to the reference in list/detail responses (`_enrich_fk_display_names`), so the UI shows the label instead of a raw ref.

Because FK enrichment calls `display_name` for **every row**, a `display_name` built from scalar fields costs nothing extra. Reaching through an FK/M2M inside it would trigger a reference load per row → N+1.

### Including FK fields without N+1 (custom `api_objects` manager + `select_related`)

**Default to the scalar form above.** Only pull an FK into the label when the related entity is genuinely part of how users identify this record — e.g. an invoice naturally reads as `{customer} — {number}`. If the model's own scalar fields already identify it, do **not** reach into an FK (and do not add `select_related`) just because you can.

When the FK truly belongs in the label, make it cheap: bake `select_related` into a custom manager and expose it as **`api_objects`** — the REST/Console list endpoints use `api_objects` when present, otherwise the default `objects` (`get_api_manager`). (You do **not** need to declare `objects` — the base `Model` provides it automatically.)

```python
from typing import ClassVar

from amsdal_models.managers.model_manager import Manager


class InvoiceApiManager(Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('customer')  # nested ok: 'customer__company'


class Invoice(Model):
    number: str
    customer: Customer = ReferenceField(related_name='invoices')

    api_objects: ClassVar[InvoiceApiManager] = InvoiceApiManager()  # used by the server APIs

    @property
    def display_name(self) -> str:
        return f'{self.customer.display_name} — {self.number}'
```

With `select_related('customer')` baked into `api_objects.get_queryset()`, listing invoices loads each `customer` in the **same** query, so `self.customer` inside `display_name` hits memory, not the database — no N+1. Without the custom manager, the same `display_name` would issue one query per row.

Rule of thumb: scalar `display_name` by default → only add the FK + `api_objects` + `select_related` when the related entity is part of the label's meaning.

## Relationships

### Many-to-One (Foreign Key)

```python
from amsdal.models import ReferenceField
from amsdal_models.classes.relationships.enum import ReferenceMode

class Person(Model):
    asset: Asset                                                    # simple FK — preferred!
    asset: Asset = ReferenceField(..., db_field='asset_id')         # custom column name
    asset: Asset = ReferenceField(..., on_delete=ReferenceMode.CASCADE)  # on delete behavior
    asset: Asset = ReferenceField(..., related_name='people')       # custom reverse accessor name
```

**ReferenceMode options:** `CASCADE`, `PROTECT`, `RESTRICT`, `SET_NULL`, `SET_DEFAULT`, `DO_NOTHING`

**Reverse accessor:** Each FK exposes a reverse accessor on the target model. By default it is named `<model>_set` (e.g. `Book.author` → `author.book_set`). Override with `related_name='...'`; set `related_name='+'` to disable the reverse accessor entirely.

### Many-to-Many

**IMPORTANT: M2M fields MUST NOT have a default value (no `= []`). This raises `AmsdalModelError('Many-to-many relation cannot have default value')`.**

```python
from amsdal.models import ManyReferenceField

class Person(Model):
    assets: list[Asset]  # auto junction table — NO default value!

    # OR with custom junction:
    assets: list[Asset] = ManyReferenceField(
        through=PersonAsset,
        through_fields=('person', 'asset'),
    )

    # OR opt into a reverse M2M accessor on the target model:
    assets: list[Asset] = ManyReferenceField(related_name='owners')  # asset.owners
```

**Reverse M2M accessor:** Unlike FK, an M2M field has **no** reverse accessor by default (`related_name=None`). Pass `related_name='...'` to install `target.<related_name>` returning the source objects via the through-table.

### Reading a FK in async mode returns an awaitable

In `async_mode`, accessing a forward FK on a **loaded** instance (e.g. `comment.article`) returns an **awaitable**, not the resolved instance — sync reference loading is forbidden in async context. (A freshly-assigned instance is returned synchronously, which can mask the bug in a single happy-path test.) Always guard before use:

```python
import inspect
from amsdal_utils.models.data_models.reference import Reference

async def get_article(comment: 'Comment') -> 'Article':
    article = comment.article
    if inspect.isawaitable(article):
        article = await article
    if isinstance(article, Reference):
        article = await article.aload()
    return article
```

Or simply `article = await comment.article` when you know it is stored as a reference. This applies to **reading FK attributes off a model**; it is separate from transaction arguments (where the server resolves references for plain-Model annotations — see [[amsdal-transactions]]).

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
| `select_related(*fields)` | QuerySet | Eager-load FK relations (SQL JOIN) |
| `prefetch_related(*args: str \| Prefetch)` | QuerySet | Eager-load reverse-FK / M2M / FK relations (separate queries) |
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

### prefetch_related (Reverse-FK / M2M / FK, no N+1)

Where `select_related` JOINs forward FKs into one query, `prefetch_related` runs **one extra query per relationship** and stitches the results onto the parent instances. Use it for reverse-FK accessors (`author.book_set`), M2M fields, and forward FKs you want batched.

```python
from amsdal_models.querysets.prefetch import Prefetch

# String lookup — populates the relationship cache; accessor returns loaded results
authors = Author.objects.prefetch_related('book_set').execute()
for a in authors:
    for book in a.book_set:   # no extra query
        print(book.title)

# Forward FK and M2M lookups work too
users = User.objects.prefetch_related('profile').execute()
posts = Post.objects.prefetch_related('tags').execute()

# Nested — dotted path follows the relationship chain
authors = Author.objects.prefetch_related('book_set__publisher').execute()
```

**`Prefetch` for finer control** — `@dataclass(frozen=True) Prefetch(lookup, queryset=None, to_attr=None)`:

```python
# Custom queryset on the target (filter / order_by / only are allowed)
Author.objects.prefetch_related(
    Prefetch('book_set', queryset=Book.objects.filter(title__icontains='guide').order_by('title')),
).execute()

# Nested via a custom queryset that itself prefetches
Author.objects.prefetch_related(
    Prefetch('books_with_publisher', queryset=BookWithPublisher.objects.prefetch_related('publisher')),
).execute()

# to_attr — results land as a plain list on instance.__dict__ (NOT the relationship cache)
authors = Author.objects.prefetch_related(
    Prefetch('book_set', queryset=Book.objects.all(), to_attr='collected_books'),
).execute()
for a in authors:
    a.collected_books   # plain list[Book]; a.book_set is left untouched
```

**Custom-queryset constraints (validated at `Prefetch(...)` construction time):**
- Must be a multi-object `QuerySet` — not `.get()` / `.first()` / `.last()`.
- Cannot use `using()` — the database is inherited from the parent queryset.
- Cannot be sliced (`[a:b]`), and cannot use `distinct()` or `annotate()`.

`to_attr` must not collide with an existing field, M2M field, or reverse accessor name — this is checked at `execute()` / `aexecute()` time (not at `Prefetch(...)` construction), raising `ValueError`.

**M2M through-model rule:** when prefetching an M2M field with a custom queryset, the queryset MUST target the auto-generated **through-model**, not the target model. Passing a target-model queryset raises `AmsdalQuerySetError`.

```python
# WRONG — raises AmsdalQuerySetError
Post.objects.prefetch_related(Prefetch('tags', queryset=Tag.objects.filter(active=True)))

# RIGHT — filter on the through-model (exposed as Post.tags_through)
Post.objects.prefetch_related(
    Prefetch('tags', queryset=Post.tags_through.objects.select_related('tags').filter(...)),
)
```

## Transactions

Business logic lives in `@transaction` / `@async_transaction` functions, auto-exposed at `/api/transactions/<name>/`. See the **[[amsdal-transactions]]** skill for the full surface — defining them, model arguments & reference resolution, importing models inside the function, permissions decorator order, background/scheduled transactions, and rollback.

Two rules worth keeping in mind while modeling, both covered there:
- A single model argument should be annotated as the **plain Model** (`book: Book`), not `Reference | Model` — the server auto-loads the referenced object for plain-Model annotations.
- In transaction/helper modules, import model classes **inside** the function (not at module top) so each call resolves the current model build.

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