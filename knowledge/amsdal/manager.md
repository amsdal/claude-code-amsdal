# Module `amsdal.manager`

Central lifecycle orchestrators for the AMSDAL framework. Defines two singleton manager classes — `AmsdalManager` (synchronous) and `AsyncAmsdalManager` (asynchronous). Each reads configuration, installs per-layer contexts (data / models / framework), eager-imports and resolves all registered model classes, connects the data layer, registers internal classes/tables, applies fixtures, performs license authentication, and tears everything down on exit.

Both classes are near-identical mirror images; the async one differs only in `async`/`await` on `connect_data`, `setup`, `post_setup`, `apply_fixtures`, `teardown`, uses async data-layer component classes, and registers the async metadata query / async fixtures manager. Differences are noted explicitly per method.

## Module-level imports and their roles

- `sys`, `import_module` (from `importlib`), `Path` (from `pathlib`) — stdlib.
- `AsyncDataApplication`, `DataApplication` (`amsdal_data.application`) — data layer application objects.
- `AsyncMetadataInfoQuery`, `MetadataInfoQuery` (`amsdal_data.query`) — metadata query implementations registered into the metadata manager.
- `async_transaction`, `transaction` (`amsdal_data.transactions.decorators`) — decorators wrapping methods in a (async) transaction.
- `ReferenceLoader` (`amsdal_models.classes.helpers.reference_loader`) — concrete reference loader registered into `ReferenceLoaderManager`.
- `get_class_manager` (`amsdal_models.contexts`) — returns the current models-context class manager.
- `MetadataInfoManager` (`amsdal_utils.classes.metadata_manager`) — manager for metadata info queries; has class method `invalidate()`.
- `AmsdalConfig` (`amsdal_utils.config.data_models.amsdal_config`) — config data model.
- `AmsdalConfigManager` (`amsdal_utils.config.manager`) — config manager; `get_config()` may raise `AttributeError` if no config set; has class method `invalidate()`.
- `ReferenceLoaderManager` (`amsdal_utils.models.data_models.reference`) — has instance method `set_reference_loader(...)` and class method `invalidate()`.
- `ModuleType` (`amsdal_utils.models.enums`) — enum with members `CORE`, `TYPE`, `CONTRIB`, `USER` (and others) used to tag model modules.
- `Singleton` (`amsdal_utils.utils.singleton`) — metaclass (see below).
- `CloudActionsManager` (`amsdal.cloud.services.actions.manager`).
- `settings` (`amsdal.configs.main`) — settings object; attributes used: `CONTRIBS`, `USER_MODELS_MODULE`, `user_models_path`, `fixtures_root_path`, `STRICT_BOOTSTRAP`.
- `AmsdalAuthenticationError`, `AmsdalRuntimeError` (`amsdal.errors`).
- `AsyncFixturesManager`, `FixturesManager` (`amsdal.fixtures.manager`).
- `ClassVersionsMixin` (`amsdal.mixins.class_versions_mixin`) — base mixin (see below).

### `Singleton` metaclass behavior (from `amsdal_utils.utils.singleton`)

`Singleton(type, Generic[T])` keeps a class-level dict `__instances: dict[type, instance]`.
- `__call__(cls, *args, **kwargs)`: if `cls not in __instances`, creates the instance via `super().__call__(...)` and stores it; always returns the stored instance. Thus `AmsdalManager()` / `AsyncAmsdalManager()` return the same object every time until invalidated.
- `invalidate(cls)`: if `cls is Singleton` clears ALL instances; elif `cls in __instances` deletes only that class's instance. `self.__class__.invalidate()` in `teardown` drops the cached singleton so the next construction re-runs `__init__`.

### `ClassVersionsMixin` behavior (from `amsdal.mixins.class_versions_mixin`)

Provides registration of AMSDAL internal classes.
- `_register_internal_classes(schema_version_manager)` (staticmethod): loops over the exact tuple of class names `('Object', 'Transaction', 'Metadata', 'Reference', 'Migration')` and calls `schema_version_manager.register_last_version(internal_class, '')` for each (second arg is the empty string `''`, i.e. version key).
- `register_internal_classes()` (classmethod): calls `_register_internal_classes(get_historical_schema_version_manager())` (`get_historical_schema_version_manager` imported from `amsdal_data.contexts`).
- `aregister_internal_classes()` (async classmethod): same body — calls `_register_internal_classes(get_historical_schema_version_manager())`; it is `async` only to fit the async call site (it does not actually await anything internally).

---

## `AmsdalManager`

`class AmsdalManager(ClassVersionsMixin, metaclass=Singleton)`

Synchronous orchestrator of the whole framework. Singleton: only one instance exists per process until `teardown()` (or explicit `invalidate()`).

### State (instance attributes set in `__init__`)

- `_config_manager: AmsdalConfigManager` — a freshly constructed `AmsdalConfigManager()`.
- `_config: AmsdalConfig` — result of `_config_manager.get_config()`.
- `_data_application: DataApplication` — freshly constructed `DataApplication()`.
- `_is_setup: bool` — initial value `False`. Set `True` at end of `setup()`, `False` in `teardown()`. Exposed read-only via `is_setup`.
- `__is_authenticated: bool` — name-mangled to `_AmsdalManager__is_authenticated`. Initial value `False`. Set `True` by `authenticate()`. Exposed read-only via `is_authenticated`.
- `_metadata_manager: MetadataInfoManager` — freshly constructed `MetadataInfoManager()`; has `MetadataInfoQuery` registered into it.
- `_frozen: bool` — initial value `False`. Set `True` at end of `_freeze()`; reset to `False` at the start of `teardown()`. Acts as the K1-invariant flag (no method in this module reads it as a guard — informational).
- `_default_data_context: object | None` — initial `None`; populated by `_install_layer_contexts()` with an `AmsdalDataContext()`; reset to `None` during `teardown()`.
- `_default_models_context: object | None` — initial `None`; populated with an `AmsdalModelsContext(...)`; reset to `None` during `teardown()`.
- `_default_framework_context: object | None` — initial `None`; populated with an `AmsdalContext()`; reset to `None` during `teardown()`.

### `__init__(self) -> None`

Steps in order:
1. `self._config_manager = AmsdalConfigManager()`.
2. Try `config = self._config_manager.get_config()`. If it raises `AttributeError` (caught as `err`), raises `AmsdalRuntimeError` with exact message `'Missing config. Use AmsdalConfigManager().set_config() before using AmsdalManager'`, chained `from err`.
3. `self._config = config`.
4. `self._data_application = DataApplication()`.
5. `self._is_setup = False`.
6. `self.__is_authenticated = False`.
7. `ReferenceLoaderManager().set_reference_loader(ReferenceLoader)` — registers the concrete reference loader class.
8. `self._metadata_manager = MetadataInfoManager()`.
9. `self._metadata_manager.register_metadata_info_query(MetadataInfoQuery)` (sync-specific call).
10. Sets `self._frozen = False`, and the three `_default_*_context` attributes to `None`.
11. Calls `self._install_layer_contexts()`.

Side effects: mutates the global reference-loader manager and metadata manager; installs/activates module-global layer contexts (see `_install_layer_contexts`).

### `is_setup` (property) -> bool

Returns `self._is_setup`.

### `is_authenticated` (property) -> bool

Returns `self.__is_authenticated` (the name-mangled flag). True only after `authenticate()` succeeded.

### `pre_setup(self) -> None`

Registers model modules and ensures the user models path is importable.
1. Builds `contrib: list[tuple[str, ModuleType]] = []`. For each `_contrib` string in `settings.CONTRIBS`: splits with `_contrib.rsplit('.', 2)` taking the first part `_contrib_path` (drops the last two dotted segments), appends the tuple `(f'{_contrib_path}.models', ModuleType.CONTRIB)`.
2. Calls `get_class_manager().register_models_modules(modules=[...], clear_previously_registered=True)`. The `modules` list, in exact order, is:
   - `('amsdal.models.core', ModuleType.CORE)`
   - `('amsdal.models.types', ModuleType.TYPE)`
   - `*contrib` (all contrib tuples expanded in order)
   - `(settings.USER_MODELS_MODULE, ModuleType.USER)`
   `clear_previously_registered=True` wipes any prior registrations.
3. Computes `_user_models_path = str(settings.user_models_path.parent.absolute())`.
4. If `_user_models_path not in sys.path`: `sys.path.insert(0, _user_models_path)` (prepended so user models resolve first).

### `setup(self) -> None`

Full framework startup; idempotency-guarded.
1. If `self._is_setup` is truthy: raise `AmsdalRuntimeError('AmsdalManager is already setup')`.
2. `self.pre_setup()`.
3. `self._run_bootstrap_phase()` (imports + resolves all model classes, then `_freeze()`).
4. Imports `freeze as freeze_lifecycle` from `amsdal_models.classes.loading`; calls `freeze_lifecycle(strict=settings.STRICT_BOOTSTRAP)` — locks the model-loading lifecycle; `strict` taken from settings.
5. `self.connect_data(self._config)` — sets up the data application and binds data-layer managers to the current data context.
6. Imports `get_background_transaction_manager` from `amsdal_data.contexts`; calls `get_background_transaction_manager().initialize_connection(raise_on_no_worker=False)` — lazily initializes the background transaction connection without raising if no worker is present.
7. Imports `register_pii_crypto_service` from `amsdal.services.pii_cryptor`; calls `register_pii_crypto_service()`.
8. `self._is_setup = True`.

Note: `setup()` does NOT call `post_setup()` or `apply_fixtures()`; callers invoke those separately.

### `_freeze(self) -> None`

Asserts invariant K1: no registered class has unresolved deferred references. Iterates EVERY class registered in the class manager (including classes created at import time before the manager existed).
1. Imports `BootstrapError` from `amsdal_models.classes.loading`, and the constants `DEFERRED_FOREIGN_KEYS`, `DEFERRED_M2M_FIELDS`, `DEFERRED_PRIMARY_KEYS` from `amsdal_models.classes.relationships.constants` (these constants are attribute-name strings).
2. `cm = get_class_manager()`; `seen: set[type] = set()`.
3. Iterates `cm._loaded_classes.items()` as `(_module_type, by_name)`. `by_name` maps `class_name -> versions`.
4. For each `(class_name, versions)`:
   - If `isinstance(versions, dict)`: `entries = versions.values()`; else `entries = [versions]`.
   - For each `entry`: resolves the class object `cls = getattr(entry, 'cls', None) or (entry[0] if isinstance(entry, tuple) else entry)` — i.e. uses `entry.cls` if present/truthy, else first tuple element if a tuple, else the entry itself.
   - If `cls in seen`: `continue`. Else add to `seen`.
   - For each `attr_name` in the tuple `(DEFERRED_PRIMARY_KEYS, DEFERRED_FOREIGN_KEYS, DEFERRED_M2M_FIELDS)`: `leftover = getattr(cls, attr_name, None)`. If `leftover` is truthy: raise `BootstrapError` with message `f'class {class_name} has unresolved {attr_name} after bootstrap: {leftover!r}'`.
5. After the loop (no leftovers found): `self._frozen = True`.

### `_install_layer_contexts(self) -> None`

Creates and activates per-layer default contexts that are module-global (visible from any task/thread). Important for FastAPI/ASGI where request handlers run in sibling tasks of the lifespan-setup task.
1. Imports `AmsdalDataContext`, `set_default_data_context` (`amsdal_data.contexts`); `FileClassRegistry` (`amsdal_models.classes.registry`); `AmsdalModelsContext`, `set_default_models_context` (`amsdal_models.contexts`); `AmsdalContext`, `set_default_context` (`amsdal.contexts`).
2. Data layer: `self._default_data_context = AmsdalDataContext()` (empty placeholder; data fields populated later by `connect_data`); `set_default_data_context(self._default_data_context)`.
3. Imports `ClassManager` from `amsdal_models.classes.class_manager`.
4. Models layer: `self._default_models_context = AmsdalModelsContext(class_registry=FileClassRegistry(), class_manager=ClassManager())`; `set_default_models_context(self._default_models_context)`.
5. Framework layer: `self._default_framework_context = AmsdalContext()` (empty placeholder); `set_default_context(self._default_framework_context)`.

### `connect_data(self, config: AmsdalConfig) -> None`

Initializes data-layer state and binds it to the current `AmsdalDataContext`. Components are created in strict dependency order (docstring rationale: HSVM, transaction manager, table schema manager each read prior components via the context, so order matters and `table_schema_manager` MUST be last).
1. Imports: `HistoricalSchemaVersionManager` (`amsdal_data.connections.historical.schema_version_manager`); `current_data_context` (`amsdal_data.contexts`); `TableSchemasManager` (`amsdal_data.services.table_schema_manager`); `BackgroundTransactionManager` (`amsdal_data.transactions.background.manager`); `AmsdalTransactionManager` (`amsdal_data.transactions.manager`).
2. `self._data_application.setup(config)`.
3. `ctx = current_data_context()`.
4. Assigns, in order: `ctx.data_application = self._data_application`; `ctx.historical_schema_version_manager = HistoricalSchemaVersionManager()`; `ctx.transaction_manager = AmsdalTransactionManager()`; `ctx.background_transaction_manager = BackgroundTransactionManager()`; `ctx.table_schema_manager = TableSchemasManager()`.

### `_run_bootstrap_phase(self) -> None`

Eager-imports all registered model modules and bulk-resolves deferred references (replaces lazy `complete_deferred_*` calls in the metaclass). Reverse-FK draining happens automatically inside the metaclass `__new__` during import; no separate drain here.
1. Imports `ModelImporter`, `TopologicalResolver` from `amsdal_models.classes.loading`.
2. `cm = get_class_manager()`.
3. `importer = ModelImporter(modules=cm._models_modules)`.
4. `imported = importer.import_all()` — `imported` is an iterable of `(cls, module_type)` tuples.
5. `classes = [cls for cls, _mt in imported]`.
6. Imports `ClassSource` (`amsdal_models.classes.class_manager`) and `current_models_context` (`amsdal_models.contexts`).
7. `registry = current_models_context().class_registry`.
8. For each `(cls, module_type)` in `imported`: `registry.register(cls, module_type=module_type, module_path=cls.__module__, source=ClassSource.FILE)`.
9. `TopologicalResolver().resolve_classes(classes)` — bulk-resolves deferred PKs/FKs/M2M.
10. For each `cls` in `classes`: `try: cls.model_rebuild(force=True)` — rebuilds the Pydantic schema after FK/M2M field changes. `except Exception: pass` (broad bare-suppress; tolerates edge cases like `TypeModel` / partial models). The final invariant is enforced by `_freeze()`.
11. `self._freeze()`.

### `post_setup(self) -> None`  (decorated `@transaction`)

Runs inside a transaction. Registers internal classes and creates internal tables.
1. `self.register_internal_classes()` — from the mixin, registers last versions for `Object`, `Transaction`, `Metadata`, `Reference`, `Migration` with version `''`.
2. `self._data_application.register_internal_tables()`.

### `_check_auth(self) -> None`

Authentication guard.
1. Imports `LicenseGuard` from `amsdal.license.guard`.
2. Condition: `if not (self.__is_authenticated or LicenseGuard.is_valid())`. I.e. raises only when BOTH the instance flag is False AND `LicenseGuard.is_valid()` returns falsy. In that case raises `AmsdalAuthenticationError('AmsdalManager is not authenticated')`. Otherwise returns silently.

### `cloud_actions_manager` (property) -> CloudActionsManager

1. Calls `self._check_auth()` (raises `AmsdalAuthenticationError` if not authenticated and license invalid).
2. Returns a freshly constructed `CloudActionsManager()` (new instance each access).

### `authenticate(self) -> None`

1. Imports `LicenseGuard` from `amsdal.license.guard`.
2. `LicenseGuard.ensure_valid()` — raises if the license is invalid (exception type/behavior defined in `LicenseGuard`, not here).
3. On success: `self.__is_authenticated = True`.

### `apply_fixtures(self) -> None`  (decorated `@transaction`)

Loads and applies fixtures, contrib fixtures first then app fixtures, inside a transaction.
1. `_contrib_fixture_paths = []`.
2. For each `contrib_module` string in `settings.CONTRIBS`:
   - `package_name, _ = contrib_module.rsplit('.', 1)` (drops the last dotted segment).
   - `_contrib_module = import_module(package_name)`.
   - `_fixtures_path = Path(_contrib_module.__file__ or '').parent / 'fixtures'` (uses `''` if `__file__` is None, making the path `fixtures` relative to cwd).
   - If `_fixtures_path.exists() and _fixtures_path.is_dir()`: append it to `_contrib_fixture_paths`.
3. `manager = FixturesManager(fixtures_paths=[*_contrib_fixture_paths, settings.fixtures_root_path])` — contrib paths first, app `fixtures_root_path` last.
4. `manager.load_fixtures()`.
5. `manager.apply_file_fixtures()`.
6. `manager.apply_fixtures()`.

### `init_classes(self) -> None`

No-op. Body is fully commented out plus a bare `...`. Returns None and does nothing. (Historically iterated schema manager class schemas, skipping `SchemaTypes.TYPE`, importing the rest.)

### `teardown(self) -> None`

Full cleanup on application exit; guarded.
1. Imports `AuthManager` from `amsdal.cloud.services.auth.manager`.
2. If `not self._is_setup`: raise `AmsdalRuntimeError('AmsdalManager is not setup')`.
3. `self._frozen = False`.
4. If `self._default_data_context is not None`: imports `get_historical_schema_version_manager` (`amsdal_data.contexts`); calls `get_historical_schema_version_manager().clear_versions()`. (Done BEFORE clearing contexts, because the accessor would raise once the context is cleared.)
5. `self._data_application.teardown()`.
6. If `self._default_models_context is not None`: imports `unfreeze as unfreeze_lifecycle` (`amsdal_models.classes.loading`); calls `unfreeze_lifecycle()`; then `get_class_manager().teardown()`.
7. If `self._default_framework_context is not None`: imports `clear_default_context` (`amsdal.contexts`); calls `clear_default_context()`; sets `self._default_framework_context = None`.
8. If `self._default_models_context is not None`: imports `clear_default_models_context` (`amsdal_models.contexts`); sets `self._default_models_context.class_manager = None`; calls `clear_default_models_context()`; sets `self._default_models_context = None`.
9. If `self._default_data_context is not None`: imports `clear_default_data_context` (`amsdal_data.contexts`); detaches data-layer state in this exact order BEFORE clearing (so callers via `current_data_context()` see `None` not a half-torn manager): `table_schema_manager = None`, `background_transaction_manager = None`, `transaction_manager = None`, `historical_schema_version_manager = None`, `data_application = None`; then `clear_default_data_context()`; `self._default_data_context = None`.
10. Class-level invalidations, in exact order: `ReferenceLoaderManager.invalidate()`; `MetadataInfoManager.invalidate()`; `AmsdalConfigManager.invalidate()`; `self.__class__.invalidate()` (drops this manager from the `Singleton` cache); `AuthManager.invalidate()`.
11. `self._is_setup = False`.

---

## `AsyncAmsdalManager`

`class AsyncAmsdalManager(ClassVersionsMixin, metaclass=Singleton)`

Asynchronous mirror of `AmsdalManager`. Same singleton semantics, same state attributes, same overall flow. Only the differences are described here; everything else is identical to the sync class above (including `pre_setup`, `_freeze`, `_install_layer_contexts`, `_run_bootstrap_phase`, `_check_auth`, `cloud_actions_manager`, `authenticate`, `init_classes`, `is_setup`, `is_authenticated`).

### State differences

- `_data_application: AsyncDataApplication` — constructed as `AsyncDataApplication()` instead of `DataApplication()`.
- `__is_authenticated` is name-mangled to `_AsyncAmsdalManager__is_authenticated`.
- All other attributes (`_config_manager`, `_config`, `_is_setup`, `_metadata_manager`, `_frozen`, the three `_default_*_context`) have the same names, types, and initial values as the sync class.

### `__init__(self) -> None`

Identical to sync `__init__` except:
- Step 4: `self._data_application = AsyncDataApplication()`.
- Step 9: `self._metadata_manager.register_async_metadata_info_query(AsyncMetadataInfoQuery)` (instead of `register_metadata_info_query(MetadataInfoQuery)`).
- Same `AmsdalRuntimeError` message on missing config: `'Missing config. Use AmsdalConfigManager().set_config() before using AmsdalManager'`.

### `connect_data(self, config: AmsdalConfig) -> None`  (async)

Async counterpart of `AmsdalManager.connect_data`. Same structure/order, but uses async component classes and awaits setup.
1. Imports: `AsyncHistoricalSchemaVersionManager` (`amsdal_data.connections.historical.schema_version_manager`); `current_data_context` (`amsdal_data.contexts`); `AsyncTableSchemasManager` (`amsdal_data.services.table_schema_manager`); `AsyncBackgroundTransactionManager` (`amsdal_data.transactions.background.manager`); `AmsdalAsyncTransactionManager` (`amsdal_data.transactions.manager`).
2. `await self._data_application.setup(config)`.
3. `ctx = current_data_context()`.
4. Assigns in order: `ctx.data_application = self._data_application`; `ctx.historical_schema_version_manager = AsyncHistoricalSchemaVersionManager()`; `ctx.transaction_manager = AmsdalAsyncTransactionManager()`; `ctx.background_transaction_manager = AsyncBackgroundTransactionManager()`; `ctx.table_schema_manager = AsyncTableSchemasManager()`.

### `setup(self) -> None`  (async)

Same as sync `setup` except step 5 is `await self.connect_data(self._config)`. All other steps identical, including the `'AmsdalManager is already setup'` guard message, `freeze_lifecycle(strict=settings.STRICT_BOOTSTRAP)`, `get_background_transaction_manager().initialize_connection(raise_on_no_worker=False)` (NOT awaited — synchronous call), and `register_pii_crypto_service()`. Sets `self._is_setup = True` at the end.

### `post_setup(self) -> None`  (async, decorated `@async_transaction`)

1. `await self.aregister_internal_classes()` (the async mixin classmethod).
2. `await self._data_application.register_internal_tables()`.

### `apply_fixtures(self) -> None`  (async, decorated `@async_transaction`)

Same contrib-path discovery loop as the sync version (identical `rsplit('.', 1)`, `import_module`, `Path(... or '').parent / 'fixtures'`, `exists() and is_dir()` checks). Differences:
- `manager = AsyncFixturesManager(fixtures_paths=[*_contrib_fixture_paths, settings.fixtures_root_path])`.
- `manager.load_fixtures()` (synchronous).
- `await manager.apply_file_fixtures()`.
- `await manager.apply_fixtures()`.

### `teardown(self) -> None`  (async)

Identical to sync `teardown` step-for-step except step 5 is `await self._data_application.teardown()`. The guard message is `'AmsdalManager is not setup'`. `clear_versions()`, `unfreeze_lifecycle()`, `get_class_manager().teardown()`, context detach/clear order, and the five class-level invalidations (`ReferenceLoaderManager.invalidate()`, `MetadataInfoManager.invalidate()`, `AmsdalConfigManager.invalidate()`, `self.__class__.invalidate()`, `AuthManager.invalidate()`) are all the same. Ends with `self._is_setup = False`.

---

## Typical lifecycle / call order

1. Construct config via `AmsdalConfigManager().set_config(...)` (external, before using the manager — otherwise `__init__` raises `AmsdalRuntimeError`).
2. `manager = AmsdalManager()` / `AsyncAmsdalManager()` — installs layer contexts.
3. `manager.setup()` / `await manager.setup()` — pre_setup → bootstrap → freeze lifecycle → connect_data → background tx init → PII crypto register; sets `_is_setup=True`.
4. `manager.post_setup()` / `await ...` — registers internal classes + tables (transactional).
5. Optional `manager.authenticate()` and `manager.apply_fixtures()`.
6. `manager.teardown()` / `await ...` — reverses everything and invalidates singletons; sets `_is_setup=False`.

## Error/exception summary

- `AmsdalRuntimeError('Missing config. Use AmsdalConfigManager().set_config() before using AmsdalManager')` — in `__init__` when `get_config()` raises `AttributeError`.
- `AmsdalRuntimeError('AmsdalManager is already setup')` — in `setup()` when `_is_setup` is already True.
- `AmsdalRuntimeError('AmsdalManager is not setup')` — in `teardown()` when `_is_setup` is False.
- `AmsdalAuthenticationError('AmsdalManager is not authenticated')` — in `_check_auth()` (and thus `cloud_actions_manager`) when not authenticated and `LicenseGuard.is_valid()` is falsy.
- `BootstrapError('class {class_name} has unresolved {attr_name} after bootstrap: {leftover!r}')` — in `_freeze()` when any registered class still has a truthy deferred-PK/FK/M2M attribute.
- `LicenseGuard.ensure_valid()` (in `authenticate()`) may raise its own exception if the license is invalid.
