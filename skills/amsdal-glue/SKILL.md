---
name: amsdal-glue
description: >
  AMSDAL Glue — ETL, connections, CQRS queries/commands, planners, executors.
  TRIGGER when: user works with ETL pipelines, multi-database queries, CQRS, connections, planners, executors, or code imports from amsdal_glue.
  DO NOT TRIGGER when: user works with simple model CRUD or server endpoints.
user-invocable: false
---

# AMSDAL Glue (ETL)

AMSDAL Glue is a flexible ETL interface providing unified data access across multiple sources (SQL, NoSQL, integrations) through a CQRS pattern.

## Before you commit to anything concrete

This skill is a routing index, not a complete or current spec. Before you finalize ANY concrete artifact — a query/command, a connection config, a planner/executor wiring, an import path, an API call — confirm it against an authoritative source FIRST:

1. `knowledge/` — if it concerns runtime behavior / debugging.
2. WebFetch the matching `docs.amsdal.com` page (map below) — for API / usage.

Do this by default, NOT only when uncertain — you cannot detect what this skill silently omits. A construct being valid Python, or seeming obvious, is not evidence that AMSDAL Glue supports it.

**Docs map for this skill:**
- overview → https://docs.amsdal.com/glue/background/
- connections → https://docs.amsdal.com/glue/multiple-connections/
- queries & commands → https://docs.amsdal.com/glue/examples/

## Architecture

```
Query Service  → Query Planner  → Task Executors → Connection Manager
Command Service → Command Planner → Task Executors → Connection Manager
```

### Packages
- **amsdal-glue-core** — data models and interfaces
- **amsdal-glue-connections** — connection implementations (SQLite, PostgreSQL)
- **amsdal-glue** — ready-to-use package with default implementations

## Initialization

```python
from amsdal_glue import init_default_containers

init_default_containers()
```

## Connection Management

### Register Connection Pools

```python
from amsdal_glue import Container, ConnectionManager, DefaultConnectionPool, SqliteConnection

connection_mng = Container.managers.get(ConnectionManager)

# Default connection
connection_mng.register_connection_pool(
    DefaultConnectionPool(SqliteConnection, db_path='app.sqlite', check_same_thread=False),
)

# Named connection for specific schema
connection_mng.register_connection_pool(
    DefaultConnectionPool(SqliteConnection, db_path='orders.sqlite', check_same_thread=False),
    'orders',
)
```

### Async Connections

```python
from amsdal_glue import Container, AsyncConnectionManager, DefaultAsyncConnectionPool, AsyncSqliteConnection

connection_mng = Container.managers.get(AsyncConnectionManager)
connection_mng.register_connection_pool(
    DefaultAsyncConnectionPool(AsyncSqliteConnection, db_path='app.sqlite', check_same_thread=False),
)
```

### Supported Backends
- `SqliteConnection` / `AsyncSqliteConnection`
- `PostgresConnection` / `AsyncPostgresConnection` — install `amsdal-glue[postgres-c]` or `amsdal-glue[postgres-binary]`
- `CsvConnection` — read CSV files as tables (install `amsdal-glue[csv]`)
- `ElasticsearchConnection` — install `amsdal-glue[elasticsearch]` (import from `amsdal_glue_connections.elasticsearch_connection.sync_connection`; not re-exported from `amsdal_glue`)

## Data Classes

### SchemaReference
```python
from amsdal_glue import SchemaReference, Version

table_ref = SchemaReference(name='customers', version=Version.LATEST, alias='c')
```

### Data
```python
from amsdal_glue import Data

data = Data(data={'name': 'John Doe', 'age': 30})
```

### Schema Definition
```python
from amsdal_glue import Schema, PropertySchema, PrimaryKeyConstraint, IndexSchema, Version

schema = Schema(
    name='Person',
    version=Version.LATEST,
    properties=[
        PropertySchema(name='id', type=int, required=True),
        PropertySchema(name='name', type=str, required=True),
        PropertySchema(name='age', type=int, required=False, default=18),
    ],
    constraints=[PrimaryKeyConstraint(name='pk_person', fields=['id'])],
    indexes=[IndexSchema(name='idx_person_name', fields=['name'])],
)
```

### Constraints
- `PrimaryKeyConstraint` — primary key
- `UniqueConstraint` — uniqueness
- `ForeignKeyConstraint` — relationships
- `CheckConstraint` — custom validation

## Query Operations

### Basic Query

```python
from amsdal_glue import (
    Container, DataQueryService, QueryStatement, SchemaReference,
    Version, DataQueryOperation, FieldReference, Field,
    Conditions, Condition, FieldLookup, Value, FieldReferenceExpression,
)

query = QueryStatement(
    only=[
        FieldReference(field=Field(name='name'), table_name='c'),
        FieldReference(field=Field(name='email'), table_name='c'),
    ],
    table=SchemaReference(name='customers', version=Version.LATEST, alias='c'),
)

service = Container.services.get(DataQueryService)
result = service.execute(query_op=DataQueryOperation(query=query))
assert result.success is True
```

### WHERE Clause

```python
query = QueryStatement(
    table=SchemaReference(name='customers', version=Version.LATEST, alias='c'),
    where=Conditions(
        Condition(
            left=FieldReferenceExpression(
                field_reference=FieldReference(field=Field(name='age'), table_name='c'),
            ),
            lookup=FieldLookup.GT,
            right=Value(18),
        ),
    ),
)
```

### JOIN

```python
from amsdal_glue import JoinQuery

query = QueryStatement(
    only=[
        FieldReference(field=Field(name='name'), table_name='c'),
        FieldReference(field=Field(name='amount'), table_name='o'),
    ],
    table=SchemaReference(name='customers', version=Version.LATEST, alias='c'),
    joins=[
        JoinQuery(
            table=SchemaReference(name='orders', version=Version.LATEST, alias='o'),
            on=Conditions(
                Condition(
                    left=FieldReferenceExpression(
                        field_reference=FieldReference(field=Field(name='customer_id'), table_name='o'),
                    ),
                    lookup=FieldLookup.EQ,
                    right=FieldReferenceExpression(
                        field_reference=FieldReference(field=Field(name='id'), table_name='c'),
                    ),
                ),
            ),
        ),
    ],
)
```

### Subqueries & Aggregations

```python
from amsdal_glue import SubQueryStatement, AggregationQuery, Count, AnnotationQuery

query = QueryStatement(
    table=SchemaReference(name='customers', version=Version.LATEST, alias='c'),
    annotations=[
        AnnotationQuery(
            value=SubQueryStatement(
                query=QueryStatement(
                    aggregations=[
                        AggregationQuery(
                            expression=Count(field=FieldReference(field=Field(name='id'), table_name='orders')),
                            alias='order_count',
                        ),
                    ],
                    table=SchemaReference(name='orders', version=Version.LATEST),
                ),
                alias='order_count',
            ),
        ),
    ],
)
```

### Order, Group, Limit

```python
from amsdal_glue import OrderByQuery, OrderDirection, GroupByQuery, LimitQuery

query = QueryStatement(
    table=SchemaReference(name='orders', version=Version.LATEST, alias='o'),
    order_by=[OrderByQuery(field=FieldReference(field=Field(name='created_at'), table_name='o'), direction=OrderDirection.DESC)],
    group_by=[GroupByQuery(field=FieldReference(field=Field(name='category'), table_name='o'))],
    limit=LimitQuery(limit=10, offset=0),
)
```

### Enums
All re-exported from `amsdal_glue`:
- `Version` — `LATEST`, `ALL`.
- `JoinType` — `INNER`, `LEFT`, `RIGHT`, `FULL` (pass to `JoinQuery(join_type=...)`).
- `OrderDirection` — `ASC`, `DESC`.
- `FilterConnector` — `AND`, `OR` (the `connector=` for `Conditions`).
- `FieldLookup` — see below.
- `TransactionAction` — `BEGIN`, `COMMIT`, `ROLLBACK`, `REVERT` (for `TransactionCommand`).
- `LockAction` — `ACQUIRE`, `RELEASE`; `LockMode` — `EXCLUSIVE`, `SHARED`; `LockParameter` — `NOWAIT`, `SKIP_LOCKED`, `WAIT` (for `LockCommand`).

### Field Lookups
`EXACT`, `EQ`, `NEQ`, `GT`, `GTE`, `LT`, `LTE`, `IN`, `CONTAINS`, `ICONTAINS`, `STARTSWITH`, `ISTARTSWITH`, `ENDSWITH`, `IENDSWITH`, `ISNULL`, `REGEX`, `IREGEX`

The `I*` variants are case-insensitive. There is no `NOT_IN`/`NOT_NULL` lookup — negate instead via `Condition(..., negate=True)`, the unary `~condition` operator, or `ISNULL` for null checks. For example, `~Condition(left=..., lookup=FieldLookup.IN, right=Value([1, 2, 3]))` renders `NOT (... IN (...))`.

### Aggregation Functions
`Count`, `Sum`, `Avg`, `Min`, `Max`

### Negation

`Condition` carries a `negate: bool = False` flag (kw_only). Set it directly, or use the unary `~` operator which flips the flag. `Conditions` also supports `~` (applies De Morgan's law) plus `&` / `|` operators to combine groups.

```python
from amsdal_glue import Condition, Conditions, FieldLookup, FieldReference, FieldReferenceExpression, Field, Value

age_field = FieldReferenceExpression(field_reference=FieldReference(field=Field(name='age'), table_name='c'))

# negate=True → renders NOT (...)
Condition(left=age_field, lookup=FieldLookup.GT, right=Value(18), negate=True)

# equivalent via the ~ operator
~Condition(left=age_field, lookup=FieldLookup.GT, right=Value(18))

# combine and negate whole groups
where = ~(
    Conditions(Condition(left=age_field, lookup=FieldLookup.GT, right=Value(18)))
    & Conditions(Condition(left=age_field, lookup=FieldLookup.LT, right=Value(65)))
)
```

### Expressions

The right/left side of a `Condition` (and annotation/projection values) accept any `Expression`:

- `FieldReferenceExpression(field_reference=FieldReference(...))` — reference a column.
- `Value(value)` — a literal (positional or `Value(value=...)`); optional `output_type=` (e.g. `date`, `datetime`).
- `RawExpression(value, output_type=None)` — raw SQL fragment.
- `Func(name=..., args=[...])` — a SQL function call over sub-expressions.
- `JsonbArrayExpression(items=[...])` — `jsonb_build_array(...)` helper (Postgres).
- `Exists(query=QueryStatement(...), negated=False)` — `EXISTS (...)` / `NOT EXISTS (...)` boolean subquery.

```python
from amsdal_glue import Exists, QueryStatement, SchemaReference, Version, Conditions, Condition, FieldLookup, FieldReference, FieldReferenceExpression, Field

# Correlated EXISTS: pass the Exists expression directly into Conditions.children
where = Conditions(
    Exists(
        query=QueryStatement(
            table=SchemaReference(name='orders', version=Version.LATEST, alias='o'),
            where=Conditions(
                Condition(
                    left=FieldReferenceExpression(
                        field_reference=FieldReference(field=Field(name='customer_id'), table_name='o'),
                    ),
                    lookup=FieldLookup.EQ,
                    right=FieldReferenceExpression(
                        field_reference=FieldReference(field=Field(name='id'), table_name='c'),
                    ),
                ),
            ),
        ),
    ),
)
```

## Command Operations

### Insert Data

```python
from amsdal_glue import InsertData, Data, Container, DataCommand
from amsdal_glue.interfaces import DataCommandService

mutation = InsertData(
    schema=SchemaReference(name='customers', version=Version.LATEST),
    data=[
        Data(data={'name': 'John Doe', 'age': 30}),
        Data(data={'name': 'Jane Doe', 'age': 25}),
    ],
)

service = Container.services.get(DataCommandService)
result = service.execute(command=DataCommand(mutations=[mutation]))
```

`DataCommand(mutations=...)` cannot be empty — an empty list raises `ValueError`. Command/schema/lock/transaction services live in `amsdal_glue.interfaces` (only `DataQueryService` / `AsyncDataQueryService` are top-level on `amsdal_glue`).

### Update Data

```python
from amsdal_glue import UpdateData

mutation = UpdateData(
    schema=SchemaReference(name='customers', version=Version.LATEST),
    data=Data(data={'age': 35}),
    query=Conditions(
        Condition(
            left=FieldReferenceExpression(
                field_reference=FieldReference(field=Field(name='name'), table_name='customers'),
            ),
            lookup=FieldLookup.EQ,
            right=Value('John Doe'),
        ),
    ),
)
```

### Delete Data

```python
from amsdal_glue import DeleteData

mutation = DeleteData(
    schema=SchemaReference(name='customers', version=Version.LATEST),
    query=Conditions(
        Condition(
            left=FieldReferenceExpression(
                field_reference=FieldReference(field=Field(name='name'), table_name='customers'),
            ),
            lookup=FieldLookup.EQ,
            right=Value('John Doe'),
        ),
    ),
)
```

### Schema Mutations

```python
from amsdal_glue import RegisterSchema, RenameSchema, AddProperty, DeleteProperty, RenameProperty
from amsdal_glue import AddConstraint, DeleteConstraint, AddIndex, DeleteIndex

# Create table
RegisterSchema(schema=schema)

# Rename table
RenameSchema(schema_reference=ref, new_schema_name='User')

# Add column
AddProperty(schema_reference=ref, property=PropertySchema(name='email', type=str, required=True))

# Drop column
DeleteProperty(schema_reference=ref, property_name='old_field')

# Rename column
RenameProperty(schema_reference=ref, old_name='email', new_name='email_address')

# Add/remove constraints and indexes
AddConstraint(schema_reference=ref, constraint=UniqueConstraint(name='uk_email', fields=['email']))
AddIndex(schema_reference=ref, index=IndexSchema(name='idx_email', fields=['email']))
```

## Services

### Query Services
- `DataQueryService` / `AsyncDataQueryService` — query data
- `SchemaQueryService` / `AsyncSchemaQueryService` — query schemas

### Command Services
- `DataCommandService` / `AsyncDataCommandService` — mutate data
- `SchemaCommandService` / `AsyncSchemaCommandService` — mutate schemas
- `TransactionCommandService` / `AsyncTransactionCommandService` — transactions
- `LockCommandService` / `AsyncLockCommandService` — locking

All accessed via `Container.services.get(ServiceClass)`.

Only `DataQueryService` / `AsyncDataQueryService` are re-exported from the top-level `amsdal_glue` package. The schema query services and all command services are imported from `amsdal_glue.interfaces`:

```python
from amsdal_glue.interfaces import (
    SchemaQueryService, DataCommandService, SchemaCommandService,
    TransactionCommandService, LockCommandService,
)
```

## Planners, Tasks, Executors

### Planners
Break operations into task graphs:
- `DefaultDataQueryPlanner`, `DefaultSchemaQueryPlanner`
- `DefaultDataCommandPlanner`, `DefaultSchemaCommandPlanner`
- `DefaultTransactionCommandPlanner`, `DefaultLockCommandPlanner`

### Tasks
- `ChainTask` — sequential execution
- `GroupTask` — parallel execution
- `DataQueryTask`, `DataMutationTask`, `SchemaQueryTask`, `SchemaCommandTask`, etc.

### Executors
- `SequentialExecutor` / `ParallelExecutor` — abstract interfaces (from `amsdal_glue.interfaces`).
- `SequentialSyncExecutor` / `AsyncSequentialSyncExecutor` — concrete sequential executors (run tasks in order; registered by `init_default_containers`).
- `ThreadParallelExecutor` — concrete parallel executor (run tasks concurrently via threads).
- `PolarsFinalQueryDataExecutor` / `AsyncPolarsFinalQueryDataExecutor` — join results from multiple sources in memory.

## Cross-Database Queries

AMSDAL Glue handles joins across different databases automatically:
1. Splits query into per-database subqueries
2. Executes in parallel
3. Joins results in memory using Polars

## Result Types

All result types share a common base: `success: bool`, `message: str | None = None`, `exception: Exception | None = None` (there is no `errors` field — a failure surfaces via `success=False` + `message`/`exception`).

- `DataResult` — adds `data: list[Data] | None`
- `SchemaResult` — adds `schemas: list[Schema | None] | None` (not `data`)
- `TransactionResult` — adds `result: Any`
- `LockResult` — adds `result: Any`

## Installation

```bash
pip install amsdal-glue                   # Core (SQLite, CSV via stdlib)
pip install amsdal-glue[postgres-c]       # PostgreSQL (psycopg C build)
pip install amsdal-glue[postgres-binary]  # PostgreSQL (psycopg binary build)
pip install amsdal-glue[async-sqlite]     # Async SQLite
pip install amsdal-glue[elasticsearch]    # Elasticsearch
pip install amsdal-glue[csv]              # CSV connection
```

Available extras: `postgres-c`, `postgres-binary`, `async-sqlite`, `elasticsearch`, `csv` (there is no plain `postgres` extra).