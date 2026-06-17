# `amsdal.mixins.class_versions_mixin`

Module that defines a single mixin, `ClassVersionsMixin`, used to seed the historical schema-version manager with the framework's built-in ("internal") classes so they are treated as having a known last version.

## Module-level imports and dependencies

- `from typing import TYPE_CHECKING` — used only to guard type-only imports.
- `from amsdal_data.contexts import get_historical_schema_version_manager` — runtime import. This is the accessor used by the mixin to obtain the active schema-version manager.
- Under `TYPE_CHECKING` only (not imported at runtime), for annotations:
  - `AsyncHistoricalSchemaVersionManager` from `amsdal_data.connections.historical.schema_version_manager`
  - `HistoricalSchemaVersionManager` from the same module.

### `get_historical_schema_version_manager()` (external, in `amsdal_data.contexts`)

Returns `current_data_context().historical_schema_version_manager`. If that attribute is `None` (i.e. `AmsdalManager.connect_data(config)` / `AsyncAmsdalManager.connect_data` has not run yet), it raises `DataContextNotInitialisedError` with the message:

> `AmsdalDataContext.historical_schema_version_manager is None. Call AmsdalManager.connect_data(config) (or AsyncAmsdalManager.connect_data) before accessing schema-version state.`

Consequently, every method below that calls this accessor will propagate `DataContextNotInitialisedError` if the data layer has not been connected.

### `register_last_version(schema_name, schema_version)` (external, on the manager)

Both the sync `HistoricalSchemaVersionManager` and the async `AsyncHistoricalSchemaVersionManager` implement this identically and **synchronously** (it is a plain method, not a coroutine, in either class):

```
def register_last_version(self, schema_name, schema_version):
    self._cache_last_versions[schema_name] = schema_version
```

It simply assigns into the manager's internal `_cache_last_versions` dict, mapping the schema name to the given version string. No validation, no return value, no I/O.

## `ClassVersionsMixin`

Purpose: a stateless mixin that registers AMSDAL's internal/system classes as having a "last version" of empty string `''` in the active historical schema-version manager.

State: **none.** The class declares no instance attributes, no class attributes, and no `__init__`. It holds no version data itself; all state lives in the schema-version manager's `_cache_last_versions` dict. Lifecycle is trivial — it is intended to be mixed into another class and its methods called (typically once, during data-layer setup) to seed internal class versions.

### `_register_internal_classes(schema_version_manager)` (staticmethod)

Signature: `_register_internal_classes(schema_version_manager: 'HistoricalSchemaVersionManager | AsyncHistoricalSchemaVersionManager') -> None`

The single private worker that performs the registration. Steps, in order:

1. Iterates over a hard-coded tuple of exactly five internal class names, in this order:
   `'Object'`, `'Transaction'`, `'Metadata'`, `'Reference'`, `'Migration'`.
2. For each `internal_class`, calls `schema_version_manager.register_last_version(internal_class, '')` — passing the class name as `schema_name` and the empty string `''` as `schema_version`.

Side effect: after completion, the manager's `_cache_last_versions` dict contains the five keys `'Object'`, `'Transaction'`, `'Metadata'`, `'Reference'`, `'Migration'`, each mapped to `''`. If any of these keys already existed, they are overwritten with `''`.

Notes / edge cases:
- The empty-string version `''` is significant: these system tables are non-versioned, and `''` denotes the canonical/base version for them.
- The method accepts the manager as an explicit argument and does **not** itself fetch it from the context, so it never raises `DataContextNotInitialisedError` on its own.
- Because `register_last_version` is synchronous on both manager types, this method works correctly whether passed a sync or an async manager; no awaiting is involved.
- No return value (`None`).

### `register_internal_classes()` (classmethod)

Signature: `register_internal_classes(cls) -> None`

Steps:
1. Calls `get_historical_schema_version_manager()` to obtain the active manager (propagates `DataContextNotInitialisedError` if the data layer is not connected).
2. Calls `cls._register_internal_classes(<manager>)`.

Side effect: identical to `_register_internal_classes` — seeds the five internal classes with version `''` into the manager's cache. Synchronous; returns `None`.

### `aregister_internal_classes()` (async classmethod)

Signature: `async aregister_internal_classes(cls) -> None`

The asynchronous counterpart. Its body is **identical** to `register_internal_classes` and contains no `await`:
1. Calls `get_historical_schema_version_manager()` (propagates `DataContextNotInitialisedError` if unset).
2. Calls `cls._register_internal_classes(<manager>)`.

Side effect: same as the sync version — registers the five internal classes with version `''`. The `async` keyword exists only so async setup code can `await` it uniformly; because the underlying `register_last_version` is synchronous, no real awaiting occurs. Returns `None` (the coroutine resolves to `None`).

## Behavioral summary for debugging

- If a developer sees a `DataContextNotInitialisedError` originating here, the cause is calling `register_internal_classes()` / `aregister_internal_classes()` before `connect_data()` has run — not a fault in the mixin itself.
- The exact, fixed set of registered names is `('Object', 'Transaction', 'Metadata', 'Reference', 'Migration')`, each with version `''`. Any of these missing, or having a non-empty version, in `_cache_last_versions` after setup indicates this seeding did not run, or was overwritten elsewhere later.
- The mixin overwrites unconditionally; calling either public method multiple times is idempotent (always (re)sets the same five keys to `''`).
