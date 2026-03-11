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
- `PostgresConnection` / `AsyncPostgresConnection` — install `amsdal-glue[postgres]`

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
    Conditions, Condition, FieldLookup, Value,
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
            field=FieldReference(field=Field(name='age'), table_name='c'),
            lookup=FieldLookup.GT,
            value=Value(18),
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
                    field=FieldReference(field=Field(name='customer_id'), table_name='o'),
                    lookup=FieldLookup.EQ,
                    value=FieldReference(field=Field(name='id'), table_name='c'),
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

### Field Lookups
`EQ`, `NEQ`, `GT`, `LT`, `GTE`, `LTE`, `STARTSWITH`, `ENDSWITH`, `CONTAINS`, `IN`, `NOT_IN`, `NULL`, `NOT_NULL`

### Aggregation Functions
`Count`, `Sum`, `Avg`, `Min`, `Max`

## Command Operations

### Insert Data

```python
from amsdal_glue import InsertData, Data, Container, DataCommandService

mutation = InsertData(
    schema=SchemaReference(name='customers', version=Version.LATEST),
    data=[
        Data(data={'name': 'John Doe', 'age': 30}),
        Data(data={'name': 'Jane Doe', 'age': 25}),
    ],
)

service = Container.services.get(DataCommandService)
result = service.execute(command=DataMutationCommand(mutations=[mutation]))
```

### Update Data

```python
from amsdal_glue import UpdateData

mutation = UpdateData(
    schema=SchemaReference(name='customers', version=Version.LATEST),
    data=Data(data={'age': 35}),
    query=Conditions(
        Condition(
            field=FieldReference(field=Field(name='name'), table_name='customers'),
            lookup=FieldLookup.EQ,
            value=Value('John Doe'),
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
            field=FieldReference(field=Field(name='name'), table_name='customers'),
            lookup=FieldLookup.EQ,
            value=Value('John Doe'),
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
- `SequentialExecutor` — run tasks in order
- `ParallelExecutor` — run tasks concurrently
- `PolarsFinalQueryDataExecutor` — join results from multiple sources in memory

## Cross-Database Queries

AMSDAL Glue handles joins across different databases automatically:
1. Splits query into per-database subqueries
2. Executes in parallel
3. Joins results in memory using Polars

## Result Types

- `DataResult` — `success: bool`, `data: list`, `errors: list`
- `SchemaResult` — `success: bool`, `data: list`
- `TransactionResult` — `success: bool`
- `LockResult` — `success: bool`

## Installation

```bash
pip install amsdal-glue                   # Core
pip install amsdal-glue[postgres]         # With PostgreSQL
pip install amsdal-glue[postgres-binary]  # PostgreSQL binary
```