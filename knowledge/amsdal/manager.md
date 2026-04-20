# `amsdal.manager` Module Documentation

This module defines two singleton manager classes that orchestrate the entire AMSDAL framework lifecycle: `AmsdalManager` (sync) and `AsyncAmsdalManager` (async). Both share near-identical behavior but differ in whether setup/teardown/fixture application are synchronous or awaitable.

Both classes inherit from `ClassVersionsMixin` and use the `Singleton` metaclass, meaning instantiating them multiple times returns the same instance until `.invalidate()` is called on the class.

---

## `AmsdalManager`

Top-level orchestrator for the synchronous AMSDAL framework. Holds references to sub-managers (config, data application, class manager, auth manager, metadata manager) and drives the initialization → setup → post-setup → teardown lifecycle.

### State (instance attributes)

All attributes are set during `__init__`:

- `_config_manager: AmsdalConfigManager` — singleton config manager obtained via `AmsdalConfigManager()`.
- `_config: AmsdalConfig` — result of `self._config_manager.get_config()`. If missing, `__init__` raises `AmsdalRuntimeError` (see below).
- `_data_application: DataApplication` — fresh `DataApplication()` instance. Not yet set up — `.setup(config)` is called later in `setup()`.
- `_is_setup: bool` — defaults to `False`. Flipped to `True` at the end of `setup()`, back to `False` at the end of `teardown()`.
- `__is_authenticated: bool` — name-mangled to `_AmsdalManager__is_authenticated`. Defaults to `False`. Set to `True` only after successful `authenticate()`.
- `_metadata_manager: MetadataInfoManager` — singleton. Immediately has `MetadataInfoQuery` registered via `register_metadata_info_query(MetadataInfoQuery)`.
- `_class_manager: ClassManager` — singleton. Used later by `pre_setup()` to register model modules.
- `_auth_manager: AuthManager` — imported lazily inside `__init__` from `amsdal.cloud.services.auth.manager`. May be constructed twice if a signup flow occurs (see below).

Additionally, a global side effect occurs in `__init__`: `ReferenceLoaderManager().set_reference_loader(ReferenceLoader)` registers the `ReferenceLoader` class on the global singleton.

### Lifecycle

1. `__init__(*, raise_on_new_signup=False)` — create singleton, register shared services.
2. `pre_setup()` — register models modules and insert user models dir into `sys.path`.
3. `setup()` — internally calls `pre_setup()`, then sets up data connections.
4. `post_setup()` — wrapped in `@transaction`; registers internal classes and internal tables.
5. `authenticate()` — optional; runs license auth; required before `cloud_actions_manager` is accessible.
6. `apply_fixtures()` — optional; wrapped in `@transaction`; loads and applies fixtures.
7. `teardown()` — tears down and invalidates all singletons.

---

### `__init__(self, *, raise_on_new_signup: bool = False) -> None`

Keyword-only argument `raise_on_new_signup` (default `False`).

Step-by-step:

1. Locally imports `AuthManager` from `amsdal.cloud.services.auth.manager` (lazy import to avoid circular import at module load).
2. Assigns `self._config_manager = AmsdalConfigManager()` — a singleton, so the same instance across calls.
3. Calls `self._config_manager.get_config()` inside a `try` block.
   - If it raises `AttributeError`, catches it and raises `AmsdalRuntimeError` with the exact message `'Missing config. Use AmsdalConfigManager().set_config() before using AmsdalManager'`, chained from the original via `from err`.
4. Stores the returned `AmsdalConfig` in `self._config`.
5. Creates `self._data_application = DataApplication()` (singleton; not yet set up).
6. Initializes flags: `self._is_setup = False`, `self.__is_authenticated = False`.
7. Calls `ReferenceLoaderManager().set_reference_loader(ReferenceLoader)` — global registration of the reference loader class.
8. Creates `self._metadata_manager = MetadataInfoManager()` (singleton) and immediately calls `self._metadata_manager.register_metadata_info_query(MetadataInfoQuery)`.
9. Creates `self._class_manager = ClassManager()` (singleton).
10. Tries to construct `self._auth_manager = AuthManager()`:
    - If `AuthManager.__init__` raises `AmsdalMissingCredentialsError`:
      1. Calls `SignupService.signup_prompt()`.
         - If it returns falsy, the original `AmsdalMissingCredentialsError` is re-raised (bare `raise`).
         - If it returns truthy (user completed signup):
           - If `raise_on_new_signup` is `True`, raises a new `AmsdalSignupError()` chained from the original error (`from e`). Note: this happens *after* a successful signup prompt but before re-attempting `AuthManager()`.
           - Otherwise, re-invokes `AuthManager()` and stores the result in `self._auth_manager`. If this second attempt also fails, the exception propagates (no further handling).

### `is_setup` (property) → `bool`

Returns `self._is_setup`. No side effects.

### `is_authenticated` (property) → `bool`

Returns the private `self.__is_authenticated` (name-mangled). No side effects.

### `pre_setup(self) -> None`

Builds the model module registration list and prepends the user-models parent directory to `sys.path`.

1. Initializes empty list `contrib: list[tuple[str, ModuleType]] = []`.
2. For each `_contrib` string in `settings.CONTRIBS`:
   - Splits from the right with `rsplit('.', 2)` → three parts; keeps only the first (`_contrib_path`), discards the other two.
   - Appends tuple `(f'{_contrib_path}.models', ModuleType.CONTRIB)` to `contrib`.
3. Calls `self._class_manager.register_models_modules(modules=[...], clear_previously_registered=True)`. The `modules` list is built in this exact order:
   - `('amsdal.models.core', ModuleType.CORE)`
   - `('amsdal.models.types', ModuleType.TYPE)`
   - all entries from `contrib` (unpacked with `*contrib`)
   - `(settings.USER_MODELS_MODULE, ModuleType.USER)`
4. Computes `_user_models_path = str(settings.user_models_path.parent.absolute())`.
5. If `_user_models_path not in sys.path`, inserts it at position 0 via `sys.path.insert(0, _user_models_path)`. Otherwise no-op.

Side effect: mutates `sys.path`.

### `setup(self) -> None`

Primary synchronous setup entry point.

1. If `self._is_setup` is `True`, raises `AmsdalRuntimeError('AmsdalManager is already setup')`.
2. Calls `self.pre_setup()` (registers model modules, touches `sys.path`).
3. Calls `self._data_application.setup(self._config)` — establishes data connections using the stored config.
4. Sets `self._is_setup = True`.
5. Calls `BackgroundTransactionManager().initialize_connection(raise_on_no_worker=False)` — gets the singleton and initializes its connection tolerantly (does not raise if no worker is available).
6. Lazy-imports `register_pii_crypto_service` from `amsdal.services.pii_cryptor`.
7. Calls `register_pii_crypto_service(settings.PII_CRYPTOR_BASE_URL, settings.PII_CRYPTOR_CLIENT_ID)`.

Note: if step 3 raises, `_is_setup` remains `False`, but `pre_setup` side effects (class manager registration, `sys.path` mutation) are NOT undone.

### `post_setup(self) -> None`

Decorated with `@transaction` (from `amsdal_data.transactions.decorators`) — runs the body inside a transaction.

1. Calls `self.register_internal_classes()` (provided by `ClassVersionsMixin`).
2. Calls `self._data_application.register_internal_tables()` — creates internal tables in the configured data stores.

### `_check_auth(self) -> None`

Private guard. If `self.__is_authenticated` is falsy, raises `AmsdalAuthenticationError('AmsdalManager is not authenticated')`. Otherwise returns `None`.

### `cloud_actions_manager` (property) → `CloudActionsManager`

1. Calls `self._check_auth()` — raises `AmsdalAuthenticationError` if not authenticated.
2. Returns a fresh `CloudActionsManager()` (note: not cached — a new instance is created on every access; however, `CloudActionsManager` may itself be a singleton).

### `authenticate(self) -> None`

1. Sets `self.__is_authenticated = False` (defensive reset; if auth fails, the previous authenticated state is cleared).
2. Calls `self._auth_manager.authenticate()`. If it raises, the exception propagates and `__is_authenticated` remains `False`.
3. On success, sets `self.__is_authenticated = True`.

### `apply_fixtures(self) -> None`

Decorated with `@transaction`. Loads fixtures from all contrib packages and the user fixtures path.

1. `_contrib_fixture_paths = []`.
2. For each `contrib_module` in `settings.CONTRIBS`:
   - `package_name, _ = contrib_module.rsplit('.', 1)` — strips the last dotted segment.
   - `_contrib_module = import_module(package_name)` — dynamic import; may raise `ImportError`/`ModuleNotFoundError`.
   - `_fixtures_path = Path(_contrib_module.__file__ or '').parent / 'fixtures'` — if `__file__` is `None`, uses empty string → resulting path becomes `/fixtures` from current directory (likely non-existent).
   - If `_fixtures_path.exists()` AND `_fixtures_path.is_dir()`, appends to `_contrib_fixture_paths`. Otherwise silently skipped.
3. Constructs `manager = FixturesManager(fixtures_paths=[*_contrib_fixture_paths, settings.fixtures_root_path])` — contrib paths come first, user path last.
4. Calls `manager.load_fixtures()` — reads/parses.
5. Calls `manager.apply_file_fixtures()` — applies file-based fixtures.
6. Calls `manager.apply_fixtures()` — applies remaining fixtures.

### `init_classes(self) -> None`

**No-op.** The body is an `...` (Ellipsis) with commented-out code. Despite its docstring describing iteration over class schemas, it does nothing at runtime. Preserved as a placeholder.

### `teardown(self) -> None`

Reverses setup and invalidates all singletons. Order matters — singletons are invalidated late so that instance methods can still be called first.

1. Lazy-imports `AuthManager`.
2. If `self._is_setup` is `False`, raises `AmsdalRuntimeError('AmsdalManager is not setup')`.
3. `self._data_application.teardown()` — closes connections on the instance.
4. `DataApplication.invalidate()` — clears the singleton from `Singleton` registry.
5. `BackgroundTransactionManager.invalidate()` — clears that singleton (no prior `teardown()` is called on the instance).
6. `self._class_manager.teardown()` — instance teardown.
7. `self._class_manager.__class__.invalidate()` — invalidates the `ClassManager` singleton.
8. `HistoricalSchemaVersionManager().clear_versions()` — obtains the singleton and clears its version cache.
9. `HistoricalSchemaVersionManager.invalidate()`.
10. `ReferenceLoaderManager.invalidate()`.
11. `MetadataInfoManager.invalidate()`.
12. `AmsdalConfigManager.invalidate()`.
13. `self.__class__.invalidate()` — invalidates `AmsdalManager` itself so the next `AmsdalManager()` builds a fresh instance.
14. `AuthManager.invalidate()`.
15. Sets `self._is_setup = False`.

Note: if step 3 raises, subsequent invalidations are NOT performed and `_is_setup` remains `True`. No try/except/finally.

---

## `AsyncAmsdalManager`

Async counterpart of `AmsdalManager`. Behavior, state, and lifecycle are identical except where noted. The differences are substitutions of async equivalents for I/O-bound components. The private `__is_authenticated` attribute here is mangled to `_AsyncAmsdalManager__is_authenticated`.

### State differences

- `_data_application: AsyncDataApplication` instead of `DataApplication`.
- Uses `AsyncBackgroundTransactionManager` instead of `BackgroundTransactionManager`.
- Uses `AsyncHistoricalSchemaVersionManager` instead of `HistoricalSchemaVersionManager`.
- Uses `AsyncFixturesManager` instead of `FixturesManager`.
- `post_setup` is decorated with `@async_transaction`; `apply_fixtures` is decorated with `@async_transaction`.

### `__init__(self, *, raise_on_new_signup: bool = False) -> None`

Identical to `AmsdalManager.__init__` step-by-step, except `self._data_application = AsyncDataApplication()`. Same error message `'Missing config. Use AmsdalConfigManager().set_config() before using AmsdalManager'` for missing config (the string is unchanged and still references "AmsdalManager", not "AsyncAmsdalManager"). Same signup-handling flow.

### `is_setup` / `is_authenticated`

Same as sync counterparts. `is_authenticated` reads `_AsyncAmsdalManager__is_authenticated`.

### `pre_setup(self) -> None`

**Synchronous** (not a coroutine). Implementation byte-identical to `AmsdalManager.pre_setup()` — same `rsplit('.', 2)` discarding two segments, same module list order, same `sys.path` mutation.

### `setup(self) -> None` (async)

`async def`. Differences from sync version:

1. Guard `if self._is_setup:` → raises `AmsdalRuntimeError('AmsdalManager is already setup')` (same message).
2. Calls `self.pre_setup()` synchronously.
3. `await self._data_application.setup(self._config)` — awaited.
4. Sets `self._is_setup = True`.
5. Calls `AsyncBackgroundTransactionManager().initialize_connection(raise_on_no_worker=False)` — note `initialize_connection` here is called synchronously (not awaited); the method on the async manager is non-coroutine in the call path used here.
6. Lazy-imports and calls `register_pii_crypto_service(settings.PII_CRYPTOR_BASE_URL, settings.PII_CRYPTOR_CLIENT_ID)` — same as sync.

### `post_setup(self) -> None` (async)

`async def`, decorated with `@async_transaction`.

1. Calls `self.aregister_internal_classes()` — NOTE: the call is NOT awaited. This is a method provided by `ClassVersionsMixin`; if it returns a coroutine, the coroutine would be discarded (potential bug / known behavior to reason about). Debugging tip: if internal classes appear missing in async mode, investigate whether `aregister_internal_classes` is actually a coroutine that needs awaiting.
2. `await self._data_application.register_internal_tables()`.

### `_check_auth(self) -> None`

Same semantics and error message as sync version.

### `cloud_actions_manager` (property)

Same semantics. `_check_auth()` first, then returns `CloudActionsManager()`. Property itself is synchronous.

### `authenticate(self) -> None`

**Synchronous** (not async). Identical to sync `authenticate`: resets `__is_authenticated` to `False`, calls `self._auth_manager.authenticate()` (non-awaited), sets `True` on success.

### `apply_fixtures(self) -> None` (async)

`async def`, decorated with `@async_transaction`.

1. Builds `_contrib_fixture_paths` with the same logic as sync version (including the same edge case where `_contrib_module.__file__ or ''` can produce `/fixtures` if `__file__` is `None`).
2. `manager = AsyncFixturesManager(fixtures_paths=[*_contrib_fixture_paths, settings.fixtures_root_path])`.
3. `manager.load_fixtures()` — synchronous call (not awaited).
4. `await manager.apply_file_fixtures()` — awaited.
5. `await manager.apply_fixtures()` — awaited.

### `init_classes(self) -> None`

**No-op.** Same as sync version — commented-out body.

### `teardown(self) -> None` (async)

`async def`. Identical structure to sync teardown, with async substitutions:

1. Lazy-import `AuthManager`.
2. If `self._is_setup` is `False`, raises `AmsdalRuntimeError('AmsdalManager is not setup')` (message unchanged — still says "AmsdalManager").
3. `await self._data_application.teardown()`.
4. `AsyncDataApplication.invalidate()`.
5. `AsyncBackgroundTransactionManager.invalidate()`.
6. `self._class_manager.teardown()` (sync).
7. `self._class_manager.__class__.invalidate()`.
8. `AsyncHistoricalSchemaVersionManager().clear_versions()` — sync call on the singleton.
9. `AsyncHistoricalSchemaVersionManager.invalidate()`.
10. `ReferenceLoaderManager.invalidate()`.
11. `MetadataInfoManager.invalidate()`.
12. `AmsdalConfigManager.invalidate()`.
13. `self.__class__.invalidate()` — invalidates the `AsyncAmsdalManager` singleton.
14. `AuthManager.invalidate()`.
15. `self._is_setup = False`.

Same caveat: if step 3 raises, subsequent cleanup does not execute.

---

## Exceptions raised by this module

| Exception | Condition | Exact message |
|---|---|---|
| `AmsdalRuntimeError` | `__init__` cannot get config (`AttributeError` from `get_config`) | `'Missing config. Use AmsdalConfigManager().set_config() before using AmsdalManager'` |
| `AmsdalRuntimeError` | `setup()` when already set up | `'AmsdalManager is already setup'` |
| `AmsdalRuntimeError` | `teardown()` when not set up | `'AmsdalManager is not setup'` |
| `AmsdalAuthenticationError` | `_check_auth()` / `cloud_actions_manager` access when not authenticated | `'AmsdalManager is not authenticated'` |
| `AmsdalSignupError` | `__init__` when `raise_on_new_signup=True` and signup prompt succeeded | (no explicit message; default exception) |
| `AmsdalMissingCredentialsError` | `__init__` when credentials missing AND `SignupService.signup_prompt()` returned falsy | re-raised from `AuthManager()` |

## Key external interactions

- `AmsdalConfigManager` / `AmsdalConfig` — configuration source; must be pre-configured via `set_config()` before instantiating the manager.
- `DataApplication` / `AsyncDataApplication` — connection lifecycle (`setup(config)`, `register_internal_tables()`, `teardown()`, class-level `invalidate()`).
- `ClassManager` — model modules registration via `register_models_modules(modules=..., clear_previously_registered=True)`.
- `ClassVersionsMixin` — provides `register_internal_classes()` (sync) and `aregister_internal_classes()` (used in async `post_setup`).
- `AuthManager` (lazy-imported from `amsdal.cloud.services.auth.manager`) — raises `AmsdalMissingCredentialsError` on construction if credentials are missing; `authenticate()` performs license verification.
- `SignupService.signup_prompt()` — interactive path triggered only when credentials are missing.
- `FixturesManager` / `AsyncFixturesManager` — `load_fixtures()`, `apply_file_fixtures()`, `apply_fixtures()` pipeline.
- `settings` from `amsdal.configs.main` — reads `CONTRIBS`, `USER_MODELS_MODULE`, `user_models_path`, `fixtures_root_path`, `PII_CRYPTOR_BASE_URL`, `PII_CRYPTOR_CLIENT_ID`.
- `register_pii_crypto_service` from `amsdal.services.pii_cryptor` — called once at end of `setup()`.
- `Singleton` metaclass — provides `invalidate()` class method used throughout `teardown()`.

## Debugging hints

- If `AmsdalManager()` raises `AmsdalRuntimeError` about missing config, the caller forgot to call `AmsdalConfigManager().set_config(...)` before instantiating the manager.
- If attributes appear stale after a `teardown()` + re-instantiation cycle, note that both `self.__class__.invalidate()` and all dependent singletons are invalidated; any external references to old instances are stale.
- If `init_classes()` appears not to do anything — it doesn't. It's a stub.
- In `AsyncAmsdalManager.post_setup()`, `aregister_internal_classes()` is called without `await` — if it returns a coroutine, that coroutine is never awaited (RuntimeWarning about never-awaited coroutine, and internal classes not registered).
- `authenticate()` is synchronous even on `AsyncAmsdalManager`; it calls the sync `AuthManager.authenticate()`.
- The `__is_authenticated` flag is name-mangled per-class (`_AmsdalManager__is_authenticated` vs `_AsyncAmsdalManager__is_authenticated`); external inspection must use the correct mangled name.
- `teardown()` has no `try/finally` — a failure in `_data_application.teardown()` leaves singletons live and `_is_setup=True`.
- Contrib fixture path resolution silently skips contribs whose `fixtures/` subdirectory does not exist; check filesystem if a contrib's fixtures are unexpectedly not applied.
