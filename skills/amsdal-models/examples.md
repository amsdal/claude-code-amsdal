# AMSDAL Models — Code Examples

## Complete Model with All Features

```python
from typing import ClassVar
from pydantic import Field, field_validator
from amsdal.models import Model, ReferenceField, ManyReferenceField, IndexInfo, UniqueConstraint
from amsdal_models import PIIStr
from amsdal_models.classes.relationships.enum import ReferenceMode


class Company(Model):
    name: str
    industry: str | None = None


class Tag(Model):
    label: str


class Person(Model):
    __table_name__: ClassVar[str] = 'people'
    __indexes__: ClassVar[list[IndexInfo]] = [
        IndexInfo(field='email', name='idx_person_email'),
    ]
    __constraints__: ClassVar[list[UniqueConstraint]] = [
        UniqueConstraint(fields=['email'], name='unique_person_email'),
    ]

    first_name: str
    last_name: str
    age: int = Field(default=0)
    email: PIIStr = Field(title='email')
    company: Company = ReferenceField(..., db_field='company_id', on_delete=ReferenceMode.SET_NULL)
    tags: list[Tag]  # M2M via auto junction table — NEVER set default value for M2M!

    @field_validator('age')
    @classmethod
    def validate_age(cls, v: int) -> int:
        if v < 0 or v > 150:
            raise ValueError('Age must be between 0 and 150')
        return v

    def pre_create(self) -> None:
        if not self.first_name:
            raise ValueError('first_name is required')

    def post_create(self) -> None:
        PersonProfile(person=self, bio='').save()

    def pre_update(self) -> None:
        original = self.refetch_from_db()
        if original.email != self.email:
            raise ValueError('Email cannot be changed after creation')
```

## CRUD Operations

```python
# === CREATE ===
person = Person(first_name='John', last_name='Doe', email='john@example.com')
person.save()

# Async
person = Person(first_name='Jane', last_name='Doe', email='jane@example.com')
await person.asave()

# Bulk create
people = [
    Person(first_name='Alice', last_name='A', email='alice@example.com'),
    Person(first_name='Bob', last_name='B', email='bob@example.com'),
]
Person.objects.bulk_create(people)


# === READ ===
# All
all_people = Person.objects.all().execute()

# Filter with lookups
adults = Person.objects.filter(age__gte=18).execute()
johns = Person.objects.filter(first_name__icontains='john').execute()

# Single object
person = Person.objects.get(email='john@example.com').execute()
person = Person.objects.get_or_none(email='unknown@example.com').execute()  # returns None
person = Person.objects.first(age__gt=18).execute()

# Count
total = Person.objects.filter(age__gte=18).count().execute()

# Ordering
people = Person.objects.order_by('-age', 'last_name').execute()

# Pagination
page1 = Person.objects.all()[0:10].execute()
page2 = Person.objects.all()[10:20].execute()

# Select specific fields only
names = Person.objects.only(['first_name', 'last_name']).execute()

# Eager-load relations
people = Person.objects.select_related('company').all().execute()
for p in people:
    print(p.company.name)  # no extra query

# Distinct
unique_companies = Person.objects.distinct(['company']).execute()

# Decrypt PII
people = Person.objects.decrypt_pii().execute()

# Use specific connection
lakehouse_people = Person.objects.using('lakehouse').all().execute()


# === UPDATE ===
person = Person.objects.get(email='john@example.com').execute()
person.age = 31
person.save()  # creates new version

# Bulk update
for p in people:
    p.age += 1
Person.objects.bulk_update(people)


# === DELETE ===
person = Person.objects.get(email='john@example.com').execute()
person.delete()

# Bulk
Person.objects.bulk_delete(people)
```

## Complex Queries with Q Objects

```python
from amsdal.queryset import Q

# Find people who are either under 18 or over 65
result = Person.objects.filter(
    Q(age__lt=18) | Q(age__gt=65),
).execute()

# Exclude specific names
result = Person.objects.filter(
    Q(age__gte=18),
    city='London',
).exclude(
    Q(first_name='John') | Q(first_name='Bob'),
).execute()

# Complex nesting
result = Person.objects.filter(
    Q(company__name='Acme') & (Q(age__lt=25) | Q(age__gt=50)),
).select_related('company').execute()

# NOT
result = Person.objects.filter(~Q(is_active=False)).execute()
```

## Transactions

```python
from amsdal.transactions import transaction, async_transaction


@transaction(name='TransferFunds', tags=['finance'])
def transfer_funds(from_account_id: str, to_account_id: str, amount: float) -> dict:
    from_acc = Account.objects.get(account_id=from_account_id).execute()
    to_acc = Account.objects.get(account_id=to_account_id).execute()

    if from_acc.balance < amount:
        raise ValueError('Insufficient funds')

    from_acc.balance -= amount
    from_acc.save()

    to_acc.balance += amount
    to_acc.save()

    return {'from_balance': from_acc.balance, 'to_balance': to_acc.balance}


@async_transaction(name='TransferFunds', tags=['finance'])
async def transfer_funds(from_account_id: str, to_account_id: str, amount: float) -> dict:
    from_acc = await Account.objects.get(account_id=from_account_id).aexecute()
    to_acc = await Account.objects.get(account_id=to_account_id).aexecute()

    if from_acc.balance < amount:
        raise ValueError('Insufficient funds')

    from_acc.balance -= amount
    await from_acc.asave()

    to_acc.balance += amount
    await to_acc.asave()

    return {'from_balance': from_acc.balance, 'to_balance': to_acc.balance}
```

## Transaction with Model References (Console-friendly)

```python
from pydantic import BaseModel

from amsdal.contrib.auth.decorators import allow_any
from amsdal.transactions import async_transaction
from amsdal_utils.models.data_models.reference import Reference

from models.book import Book
from models.order import Order


class OrderItemInput(BaseModel):
    book: Reference | Book   # Console renders a Book picker
    quantity: int


@allow_any
@async_transaction(name='PlaceOrder', tags=['orders'])
async def place_order(
    customer_name: str,
    customer_email: str,
    items: list[OrderItemInput],
) -> Order:
    from models.order_item import OrderItem

    order = Order(customer_name=customer_name, customer_email=customer_email, status='pending', total_price=0.0)
    await order.asave()

    total_price = 0.0

    for raw_item in items:
        item = raw_item if isinstance(raw_item, OrderItemInput) else OrderItemInput(**raw_item)
        book = item.book

        if isinstance(book, Reference):
            book = await book.aload()

        if book.stock_quantity < item.quantity:
            raise ValueError(f'Not enough stock for "{book.title}"')

        item_price = book.price * item.quantity
        total_price += item_price

        order_item = OrderItem(order=order, book=book, quantity=item.quantity, price=item_price)
        await order_item.asave()

        book.stock_quantity -= item.quantity
        await book.asave()

    order.total_price = total_price
    await order.asave()

    return order
```

## Metadata & Version History

```python
# Access metadata
person = Person.objects.get(email='john@example.com').execute()
meta = person.get_metadata()

print(meta.object_id)        # unique ID
print(meta.object_version)   # version string
print(meta.created_at)       # timestamp in ms
print(meta.updated_at)       # timestamp in ms
print(meta.is_deleted)       # bool

# Navigate versions
prev = person.previous_version()
if prev:
    print(f'Previous version: {prev.get_metadata().object_version}')

nxt = person.next_version()

# Filter by metadata
from datetime import datetime, timedelta

recent = Person.objects.filter(
    _metadata__created_at__gt=datetime.now() - timedelta(hours=24),
).execute()

deleted = Person.objects.filter(_metadata__is_deleted=True).execute()
```

## Data Migration Example

```python
from amsdal_models.migration import migrations
from amsdal_models.classes.relationships.helpers.deferred_foreign_keys import complete_deferred_foreign_keys


def forward_migration(schemas: migrations.MigrationSchemas) -> None:
    User = schemas.get_model('User')
    Role = schemas.get_model('Role')

    # Resolve FK fields before using relationships
    complete_deferred_foreign_keys(User)

    admin_role = Role(name='admin')
    admin_role.save()

    for user in User.objects.filter(is_staff=True).execute():
        user.role = admin_role.build_reference()
        user.save()


def backward_migration(schemas: migrations.MigrationSchemas) -> None:
    User = schemas.get_model('User')
    complete_deferred_foreign_keys(User)

    for user in User.objects.filter(role__isnull=False).execute():
        user.role = None
        user.save()


class Migration(migrations.Migration):
    operations = [
        migrations.MigrateData(
            forward_migration=forward_migration,
            backward_migration=backward_migration,
        ),
    ]
```

## External Models (Read-Only)

```python
from amsdal_models.classes.external_model import ExternalModel


class LegacyUser(ExternalModel):
    __table_name__ = 'users'
    __connection__ = 'legacy_db'
    __primary_key__ = ['id']

    id: int
    username: str
    email: str
    active: bool


# Query like regular models (read-only)
active_users = LegacyUser.objects.filter(active=True).order_by('username').execute()
user = LegacyUser.objects.get(id=42).execute()
total = LegacyUser.objects.count().execute()

# Chain filters
result = (
    LegacyUser.objects
    .filter(active=True)
    .filter(email__icontains='@company.com')
    .order_by('-id')
    .limit(20)
    .execute()
)


# Generate models at runtime
from amsdal.services import ExternalModelGenerator

generator = ExternalModelGenerator()
models = generator.generate_models_for_connection('legacy_db')
User = models['User']

# Raw SQL for external DBs
from amsdal.services import ExternalDatabaseReader

reader = ExternalDatabaseReader('legacy_db')
users = reader.fetch_all_as_dicts('SELECT * FROM users WHERE active = ?', (1,))
tables = reader.get_table_names()
```

## Rollback

```python
from amsdal.utils.rollback import rollback_to_timestamp, rollback_transaction

# By timestamp
meta = person.get_metadata()
rollback_to_timestamp(meta.updated_at)

# By transaction ID
rollback_transaction(meta.transaction.ref.object_id)

# Async
from amsdal.utils.rollback import async_rollback_to_timestamp, async_rollback_transaction

await async_rollback_to_timestamp(timestamp)
await async_rollback_transaction(transaction_id)
```