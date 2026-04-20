# Knowledge Base Index

Behavioral documentation for Cython-compiled AMSDAL modules. Each file describes what the code does internally — step-by-step logic, edge cases, error conditions, and interactions with other modules.

## How to use this index

1. **Got a traceback?** Convert the Python module path to a file path (e.g., `amsdal_data.transactions.manager` → `amsdal_data/transactions/manager.md`).
2. **Got a symptom or topic?** Find the matching entry in the tables below.
3. **Don't know the name?** Scan the "Topics → files" section for keywords.

---

## Traceback patterns → knowledge files

Direct 1:1 mapping. When you see these module paths in errors or logs, open the corresponding file.

| Module path | Knowledge file |
|---|---|
| `amsdal.manager` | [amsdal/manager.md](amsdal/manager.md) |
| `amsdal.fixtures.manager` | [amsdal/fixtures/manager.md](amsdal/fixtures/manager.md) |
| `amsdal.fixtures.utils` | [amsdal/fixtures/utils.md](amsdal/fixtures/utils.md) |
| `amsdal.mixins.class_versions_mixin` | [amsdal/mixins/class_versions_mixin.md](amsdal/mixins/class_versions_mixin.md) |
| `amsdal.services.transaction_execution` | [amsdal/services/transaction_execution.md](amsdal/services/transaction_execution.md) |
| `amsdal_models.classes.constants` | [amsdal_models/classes/constants.md](amsdal_models/classes/constants.md) |
| `amsdal_models.classes.enums` | [amsdal_models/classes/enums.md](amsdal_models/classes/enums.md) |
| `amsdal_models.classes.helpers.reference_loader` | [amsdal_models/classes/helpers/reference_loader.md](amsdal_models/classes/helpers/reference_loader.md) |
| `amsdal_models.classes.utils` | [amsdal_models/classes/utils.md](amsdal_models/classes/utils.md) |
| `amsdal_models.querysets.base_queryset` | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) |
| `amsdal_models.utils.files` | [amsdal_models/utils/files.md](amsdal_models/utils/files.md) |
| `amsdal_models.utils.schema_converter` | [amsdal_models/utils/schema_converter.md](amsdal_models/utils/schema_converter.md) |
| `amsdal_models.utils.specific_version` | [amsdal_models/utils/specific_version.md](amsdal_models/utils/specific_version.md) |
| `amsdal_data.lock.implementations.redis_lock` | [amsdal_data/lock/implementations/redis_lock.md](amsdal_data/lock/implementations/redis_lock.md) |
| `amsdal_data.lock.implementations.thread_lock` | [amsdal_data/lock/implementations/thread_lock.md](amsdal_data/lock/implementations/thread_lock.md) |
| `amsdal_data.transactions.manager` | [amsdal_data/transactions/manager.md](amsdal_data/transactions/manager.md) |

---

## Topics → knowledge files

### QuerySets, querying, filtering

| Symptom / question | File |
|---|---|
| `.get()`, `.get_or_none()`, `.first()`, `.count()` behavior | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) |
| `MultipleObjectsReturnedError` / `ObjectDoesNotExistError` | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) |
| `.only()` vs `.distinct()` / `.filter()` vs `.exclude()` | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) |
| `.none()` sticky behavior / empty QuerySet | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) |
| `.select_related()` / `.annotate()` | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) |
| Slicing `qs[n]` / `qs[a:b]` unexpected limit | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) |
| `LegacyModel` returned instead of model class | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) (`_create_instance` section) |
| `strict_class_version` flag not honored | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) |
| PII decryption / `decrypt_pii()` behavior | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) |

### References, foreign keys

| Symptom / question | File |
|---|---|
| Reference not resolving / `ReferenceLoader` failures | [amsdal_models/classes/helpers/reference_loader.md](amsdal_models/classes/helpers/reference_loader.md) |
| Lakehouse vs state DB routing for FK lookups | [amsdal_models/classes/helpers/reference_loader.md](amsdal_models/classes/helpers/reference_loader.md) |
| Historical version of referenced object | [amsdal_models/classes/helpers/reference_loader.md](amsdal_models/classes/helpers/reference_loader.md) |

### Transactions

| Symptom / question | File |
|---|---|
| `@transaction` / `@async_transaction` execution | [amsdal_data/transactions/manager.md](amsdal_data/transactions/manager.md) |
| `AmsdalTransactionError` on begin/commit/rollback | [amsdal_data/transactions/manager.md](amsdal_data/transactions/manager.md) |
| Nested transactions / parent context chain | [amsdal_data/transactions/manager.md](amsdal_data/transactions/manager.md) |
| REVERT behavior on commit failure | [amsdal_data/transactions/manager.md](amsdal_data/transactions/manager.md) |
| Thread safety / ContextVar-based async variant | [amsdal_data/transactions/manager.md](amsdal_data/transactions/manager.md) |
| Custom transaction discovery / loading | [amsdal/services/transaction_execution.md](amsdal/services/transaction_execution.md) |
| `TransactionNotFoundError` | [amsdal/services/transaction_execution.md](amsdal/services/transaction_execution.md) |
| Transaction arguments not preprocessed / refs not loaded | [amsdal/services/transaction_execution.md](amsdal/services/transaction_execution.md) |

### Fixtures

| Symptom / question | File |
|---|---|
| Fixture loading from JSON / CSV / directory tree | [amsdal/fixtures/manager.md](amsdal/fixtures/manager.md) |
| `_external_id` / `external_id` resolution | [amsdal/fixtures/manager.md](amsdal/fixtures/manager.md) |
| Fixture order / `_order` / multi-path ordering | [amsdal/fixtures/manager.md](amsdal/fixtures/manager.md) |
| `File` fixture / binary fixture upload | [amsdal/fixtures/manager.md](amsdal/fixtures/manager.md) |
| Fixture not re-applied after change | [amsdal/fixtures/manager.md](amsdal/fixtures/manager.md) |
| Type coercion in fixtures (dict/list/Optional/Union) | [amsdal/fixtures/utils.md](amsdal/fixtures/utils.md) |
| Date/datetime parsing from fixture string | [amsdal/fixtures/utils.md](amsdal/fixtures/utils.md) |

### Framework lifecycle

| Symptom / question | File |
|---|---|
| `AmsdalManager.setup()` / `teardown()` | [amsdal/manager.md](amsdal/manager.md) |
| `'Missing config'` runtime error | [amsdal/manager.md](amsdal/manager.md) |
| Authentication flow / signup prompts | [amsdal/manager.md](amsdal/manager.md) |
| Singleton invalidation during teardown | [amsdal/manager.md](amsdal/manager.md) |
| Internal class registration | [amsdal/mixins/class_versions_mixin.md](amsdal/mixins/class_versions_mixin.md) |

### Locking (concurrency)

| Symptom / question | File |
|---|---|
| `ThreadLock` semantics / race conditions | [amsdal_data/lock/implementations/thread_lock.md](amsdal_data/lock/implementations/thread_lock.md) |
| `RedisLock` / distributed locking | [amsdal_data/lock/implementations/redis_lock.md](amsdal_data/lock/implementations/redis_lock.md) |
| Stale locks after process crash | [amsdal_data/lock/implementations/redis_lock.md](amsdal_data/lock/implementations/redis_lock.md) |
| `'release unlocked lock'` RuntimeError | [amsdal_data/lock/implementations/thread_lock.md](amsdal_data/lock/implementations/thread_lock.md) |

### Schema / type system

| Symptom / question | File |
|---|---|
| `CoreTypes` enum values / `BASIC_TYPES_MAP` | [amsdal_models/classes/constants.md](amsdal_models/classes/constants.md) |
| `IMPORT_MAP` for generated code | [amsdal_models/classes/constants.md](amsdal_models/classes/constants.md) |
| `CoreModules`, `SystemModules`, `ModelType` enums | [amsdal_models/classes/enums.md](amsdal_models/classes/enums.md) |
| `ModelType.from_schema()` classification | [amsdal_models/classes/enums.md](amsdal_models/classes/enums.md) |
| SQLite / Postgres type mapping to CoreTypes | [amsdal_models/utils/schema_converter.md](amsdal_models/utils/schema_converter.md) |
| External schema introspection → `ObjectSchema` | [amsdal_models/utils/schema_converter.md](amsdal_models/utils/schema_converter.md) |
| Partial model naming (`XPartial`) | [amsdal_models/classes/constants.md](amsdal_models/classes/constants.md) |
| `_reference` field suffix for FK companion fields | [amsdal_models/classes/constants.md](amsdal_models/classes/constants.md) |

### Model utilities

| Symptom / question | File |
|---|---|
| `resolve_models_module()` — module path resolution by `ModuleType` | [amsdal_models/classes/utils.md](amsdal_models/classes/utils.md) |
| `resolve_base_class_for_schema()` — Model vs TypeModel | [amsdal_models/classes/utils.md](amsdal_models/classes/utils.md) |
| `build_class_schema_reference()` / `build_class_meta_schema_reference()` | [amsdal_models/classes/utils.md](amsdal_models/classes/utils.md) |
| `get_custom_properties()` / `is_partial_model()` | [amsdal_models/classes/utils.md](amsdal_models/classes/utils.md) |
| `object_id_to_internal()` — composite PK unwrapping | [amsdal_models/classes/utils.md](amsdal_models/classes/utils.md) |
| `convert_data_to_base64()` — file data encoding | [amsdal_models/utils/files.md](amsdal_models/utils/files.md) |
| `SpecificVersion` type alias | [amsdal_models/utils/specific_version.md](amsdal_models/utils/specific_version.md) |

---

## Known-bug quick reference

These are behaviors documented in the knowledge base that surprise developers. If a user reports one of these symptoms, check the linked file first.

| Symptom | File / section |
|---|---|
| Transaction cache always empty, every call re-parses module | [amsdal/services/transaction_execution.md](amsdal/services/transaction_execution.md) (cache never populated) |
| Async refs not resolved in transactions (`await Reference(...)`) | [amsdal/services/transaction_execution.md](amsdal/services/transaction_execution.md) (`async_execute_transaction`) |
| Internal classes not registered in async mode | [amsdal/mixins/class_versions_mixin.md](amsdal/mixins/class_versions_mixin.md) (`aregister_internal_classes`) |
| `datetime` fixture field loses time component | [amsdal/fixtures/utils.md](amsdal/fixtures/utils.md) (`_cast_value_to_type`, date parsing branch) |
| `.first()` / `.get_or_none()` fetches ALL rows before LIMIT check | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) (`QuerySetOne.execute`) |
| `qs[5]` slices offset=5, limit=6 (not limit=1) | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) (`__getitem__`) |
| `strict_class_version=True` lost after `.get()` / `.first()` / `.count()` | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) (`_from_queryset`) |
| `RedisLock` has no TTL — stale locks on process crash | [amsdal_data/lock/implementations/redis_lock.md](amsdal_data/lock/implementations/redis_lock.md) |
| `ThreadLock` race on first acquire | [amsdal_data/lock/implementations/thread_lock.md](amsdal_data/lock/implementations/thread_lock.md) |
| `commit()` failure reverts parent, not failed child | [amsdal_data/transactions/manager.md](amsdal_data/transactions/manager.md) |
| Fixture with top-level `order` key crashes on iteration | [amsdal/fixtures/manager.md](amsdal/fixtures/manager.md) (`_load_fixtures`) |

---

## Cross-references: where to find symbols mentioned in knowledge files

When a knowledge file mentions a class, function, or constant from another module, use this table to find its definition. For symbols with a knowledge file, read that next. For pure-Python symbols, read the source from the user's `site-packages`.

### Classes and managers

| Symbol | Location |
|---|---|
| `Model`, `TypeModel`, `LegacyModel` | `site-packages/amsdal_models/classes/model.py` (pure Python) |
| `ModelBase` | `site-packages/amsdal_utils/models/base.py` |
| `BaseModel` (AMSDAL's, not Pydantic's) | `site-packages/amsdal_models/classes/base.py` |
| `ClassManager` | `site-packages/amsdal_models/classes/class_manager.py` (pure Python) |
| `AmsdalConfigManager`, `AmsdalConfig` | `site-packages/amsdal_utils/config/manager.py` |
| `DataApplication`, `AsyncDataApplication` | `site-packages/amsdal_data/application.py` |
| `HistoricalSchemaVersionManager`, `AsyncHistoricalSchemaVersionManager` | `site-packages/amsdal_data/connections/historical/schema_version_manager.py` |
| `MetadataInfoManager`, `MetadataInfoQuery` | `site-packages/amsdal_data/services/metadata_info.py` |
| `ReferenceLoaderManager` | `site-packages/amsdal_utils/models/data_models/reference.py` |
| `BackgroundTransactionManager`, `AsyncBackgroundTransactionManager` | `site-packages/amsdal_data/transactions/background/` |
| `FixturesManager`, `AsyncFixturesManager`, `BaseFixturesManager` | [amsdal/fixtures/manager.md](amsdal/fixtures/manager.md) (documented) |
| `AmsdalTransactionManager`, `AmsdalAsyncTransactionManager` | [amsdal_data/transactions/manager.md](amsdal_data/transactions/manager.md) (documented) |
| `ExternalSchemaConverter` | [amsdal_models/utils/schema_converter.md](amsdal_models/utils/schema_converter.md) (documented) |
| `ReferenceLoader` | [amsdal_models/classes/helpers/reference_loader.md](amsdal_models/classes/helpers/reference_loader.md) (documented) |
| `TransactionExecutionService` | [amsdal/services/transaction_execution.md](amsdal/services/transaction_execution.md) (documented) |
| `ClassVersionsMixin` | [amsdal/mixins/class_versions_mixin.md](amsdal/mixins/class_versions_mixin.md) (documented) |
| `AmsdalManager`, `AsyncAmsdalManager` | [amsdal/manager.md](amsdal/manager.md) (documented) |
| `RedisLock`, `ThreadLock`, `LockBase` | See [redis_lock.md](amsdal_data/lock/implementations/redis_lock.md), [thread_lock.md](amsdal_data/lock/implementations/thread_lock.md); `LockBase` at `site-packages/amsdal_data/lock/base.py` |
| `Executor`, `AsyncExecutor`, `ExecutorBase`, `AsyncExecutorBase` | `site-packages/amsdal_models/querysets/executor.py` |
| `QuerySet`, `QuerySetBase`, `QuerySetOne`, `QuerySetOneRequired`, `QuerySetCount` | [amsdal_models/querysets/base_queryset.md](amsdal_models/querysets/base_queryset.md) (documented) |
| `Singleton` (metaclass) | `site-packages/amsdal_utils/utils/singleton.py` |
| `CloudActionsManager` | `site-packages/amsdal/cloud/services/actions/manager.py` (excluded from knowledge) |
| `AuthManager`, `SignupService` | `site-packages/amsdal/cloud/services/auth/` (excluded from knowledge) |

### Data models / structures

| Symbol | Location |
|---|---|
| `Reference` | `site-packages/amsdal_utils/models/data_models/reference.py` |
| `Transaction` (data model) | `site-packages/amsdal_utils/models/data_models/transaction.py` |
| `TransactionContext` | `site-packages/amsdal_data/data_models/transaction_context.py` |
| `ObjectSchema` | `site-packages/amsdal_utils/schemas/schema.py` |
| `Address` | `site-packages/amsdal_utils/models/data_models/address.py` |
| `LockObject` | `site-packages/amsdal_data/data_models/lock_object.py` |
| `Q` (query object) | `site-packages/amsdal_utils/query/utils.py` |
| `OrderBy`, `NumberPaginator`, `QuerySpecifier` | `site-packages/amsdal_utils/query/data_models/` |
| `File` (model) | `site-packages/amsdal/models/core/file.py` |
| `Fixture` (model) | `site-packages/amsdal/models/core/fixture.py` |
| `FixtureData` (dataclass) | [amsdal/fixtures/manager.md](amsdal/fixtures/manager.md) (documented) |

### Enums and constants

| Symbol | Location |
|---|---|
| `Versions`, `ModuleType` | `site-packages/amsdal_utils/models/enums.py` |
| `CoreTypes`, `MetaClasses`, `BaseClasses` | `site-packages/amsdal_utils/models/data_models/enums.py` |
| `CoreModules`, `SystemModules`, `ModelType` | [amsdal_models/classes/enums.md](amsdal_models/classes/enums.md) (documented) |
| `BASE_OBJECT_TYPE`, `BASIC_TYPES_MAP`, `IMPORT_MAP`, `FILE_CLASS_NAME`, `REFERENCE_FIELD_SUFFIX`, `PARTIAL_CLASS_NAME_SUFFIX`, `CORE_MODELS_MODULE`, `CONTRIB_MODELS_MODULE`, `USER_MODELS_MODULE`, `TYPE_MODELS_MODULE` | [amsdal_models/classes/constants.md](amsdal_models/classes/constants.md) (documented) |
| `DEFAULT_DB_ALIAS`, `LAKEHOUSE_DB_ALIAS` | `site-packages/amsdal_data/connections/constants.py` (or `amsdal_data/aliases/using.py`) |
| `PRIMARY_PARTITION_KEY` | `site-packages/amsdal_data/connections/constants.py` |
| `MANY_TO_MANY_FIELDS` | `site-packages/amsdal_models/classes/constants.py` (**not** in the knowledge-documented `constants.py` — pure-Python constant) |
| `COMPATIBLE_CLASS_VERSIONS` | `site-packages/amsdal_data/services/historical_table_schema.py` |

### Decorators, helpers, utilities

| Symbol | Location |
|---|---|
| `@transaction`, `@async_transaction` | `site-packages/amsdal_data/transactions/decorators.py` |
| `@sync_mode_only`, `@async_mode_only` | `site-packages/amsdal_utils/utils/decorators.py` |
| `@permissions`, `@allow_any` | `site-packages/amsdal/contrib/auth/decorators/` |
| `PrivateProperty` | `site-packages/amsdal_models/classes/decorators/private_property.py` |
| `build_reference()` | `site-packages/amsdal_utils/models/utils/reference_builders.py` |
| `classify()` | `site-packages/amsdal_utils/utils/text.py` |
| `get_crypto_service()`, `get_pii_fields()` | `site-packages/amsdal_models/classes/fields/pii.py` |
| `create_partial_model()` | `site-packages/pydantic_partial/` (third-party library) |
| `is_partial_model()`, `resolve_models_module()`, `resolve_base_class_for_schema()`, `build_class_schema_reference()`, `build_class_meta_schema_reference()`, `get_custom_properties()`, `object_id_to_internal()` | [amsdal_models/classes/utils.md](amsdal_models/classes/utils.md) (documented) |
| `process_fixture_value()` | [amsdal/fixtures/utils.md](amsdal/fixtures/utils.md) (documented) |
| `convert_data_to_base64()` | [amsdal_models/utils/files.md](amsdal_models/utils/files.md) (documented) |
| `SpecificVersion` | [amsdal_models/utils/specific_version.md](amsdal_models/utils/specific_version.md) (documented) |

### Errors and exceptions

| Symbol | Location |
|---|---|
| `AmsdalTransactionError` | `site-packages/amsdal_data/transactions/errors.py` |
| `AmsdalConnectionError` | `site-packages/amsdal_data/errors.py` |
| `AmsdalRuntimeError`, `AmsdalAuthenticationError`, `AmsdalSignupError`, `AmsdalAuthConnectionError`, `TransactionNotFoundError`, `AmsdalMissingCredentialsError` | `site-packages/amsdal/errors.py` |
| `MultipleObjectsReturnedError`, `ObjectDoesNotExistError`, `BulkOperationError` | `site-packages/amsdal_models/querysets/errors.py` |

### External integrations

| Symbol | Location |
|---|---|
| `amsdal_glue` (entire package) | `site-packages/amsdal_glue/` (pure Python — read full source as needed) |
| `glue.TransactionCommand`, `glue.DataCommand`, `glue.InsertData`, `glue.Data`, `glue.Version`, `glue.SchemaReference`, `glue.TransactionAction` | `site-packages/amsdal_glue/` |

---

## What's NOT in the knowledge base

This knowledge base covers **only Cython-compiled modules** in the three core packages (`amsdal`, `amsdal_models`, `amsdal_data`). For other sources:

- **Pure Python AMSDAL packages** (`amsdal_server`, `amsdal-glue`, `amsdal_cli`, `amsdal_utils`, `amsdal_ml`, `amsdal_mail`, `amsdal_storages`, `amsdal_langgraph`, `amsdal_crm`, `amsdal_integrations`) — read the source directly from the user's `site-packages` directory.
- **`.pyi` type stubs** (class signatures, method signatures) — read from the user's venv alongside the `.so` files.
- **`amsdal.cloud` submodule** — excluded from this knowledge base; it's CLI/deployment infrastructure not relevant for application development.
- **Models defined inside schemas** (`amsdal.models.core.*`, `amsdal.contrib.*.models`) — not compiled; read from `site-packages`.
