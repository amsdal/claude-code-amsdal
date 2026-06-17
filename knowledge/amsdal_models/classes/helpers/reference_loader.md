# `amsdal_models.classes.helpers.reference_loader`

Module that resolves an AMSDAL `Reference` into a concrete loaded `Model` instance. It contains a single class, `ReferenceLoader`, which is the concrete implementation registered with `ReferenceLoaderManager` (see "Interactions" below) and invoked indirectly when application code calls `Reference.load(...)`, `Reference.aload(...)`, or `await reference`.

## Module-level imports and constants

- `DEFAULT_DB_ALIAS` — imported from `amsdal_data.aliases.using`; exact value `'default'`.
- `LAKEHOUSE_DB_ALIAS` — imported from `amsdal_data.aliases.using`; exact value `'lakehouse'`.
- `Reference`, `ReferenceLoaderBase` — imported from `amsdal_utils.models.data_models.reference`.
- `Model` — imported from `amsdal_models.classes.model`.
- `get_class_manager` — imported from `amsdal_models.contexts`.
- Under `TYPE_CHECKING` only: `QuerySetOneRequired` from `amsdal_models.querysets.base_queryset` (used purely as a return-type annotation, not imported at runtime).
- `Versions` and `QuerySet` are imported lazily *inside* `_load_record` (not at module top level), to avoid import cycles.

---

## `class ReferenceLoader(ReferenceLoaderBase)`

Purpose: takes a single `Reference` and produces the `Model` record it points to, choosing the correct DB alias based on the reference's class/object versions and building a `QuerySet` `.get(...)` query against the reference address.

### State

- `self._reference: Reference` — the only instance attribute. Set in `__init__` from the constructor argument. No default; required. This shadows the base class `ReferenceLoaderBase.__init__`, which also stores `self._reference`. There is no other mutable state; the instance is a thin wrapper around one reference.

### Reference data shape consumed

All reads go through `self._reference.ref`, which is a `ReferenceData` (subclass of `amsdal_utils.models.data_models.address.Address`). The fields used:

- `self._reference.ref.class_name: str` — fully-qualified/registered class name to import.
- `self._reference.ref.class_version: Versions | str` — either a `Versions` enum member or a raw string. By `Reference` validation, never `Versions.ALL`; defaults to `Versions.LATEST` when absent.
- `self._reference.ref.object_id: Any | tuple[Any, ...]` — single scalar PK or a sequence for composite PK. The `Reference` validator normalizes single-element sequences to a scalar.
- `self._reference.ref.object_version: Versions | str` — `Versions` enum member or raw string; never `Versions.ALL`; defaults to `Versions.LATEST` when absent.

Note: the `class_version` / `object_version` values may arrive either as the enum `Versions.LATEST` **or** as the bare string `'LATEST'`, depending on how the `Reference` was constructed/deserialized. `_load_record` explicitly handles both forms (see below).

### Lifecycle

Instantiated per load operation (the manager hands back the *class*; callers instantiate it as `loader_cls(reference)`). It is short-lived: construct, call one of `load_reference` / `aload_reference`, discard.

---

### `__init__(self, reference: Reference)`

- Stores `self._reference = reference`. No validation, no side effects.

---

### `load_reference(self, only: list[str] | None = None, using: str | None = None) -> Model`

Synchronous load. Step by step:

1. `model_class = self._load_model_class()` — resolves and imports the target model class (see `_load_model_class`). May raise if the context is uninitialized or the class is not importable.
2. Calls `self._load_record(model_class, only=only, using=using)` to build a `QuerySetOneRequired[Model]`.
3. Returns `.execute()` on that queryset — synchronous DB execution. Because the queryset is built with `.get(...)`, it is a "one required" queryset: it returns exactly one `Model` and will raise the queryset layer's not-found / multiple-found errors if zero or more than one record matches (those exceptions originate in the queryset module, not here).

Parameters:
- `only` (default `None`): list of field names to restrict the loaded record to. When truthy, applied via `.only(only)`.
- `using` (default `None`): explicit DB alias override; when truthy, applied via `.using(using)` *after* the internally chosen alias, so it overrides the version-derived alias.

Returns the loaded `Model`.

---

### `async aload_reference(self, only: list[str] | None = None, using: str | None = None) -> Model`

Asynchronous counterpart of `load_reference`. Identical logic except the final execution step:

1. `model_class = self._load_model_class()`.
2. `self._load_record(model_class, only=only, using=using)` builds the same queryset.
3. `return await <queryset>.aexecute()` — async execution path.

Same parameter semantics and same not-found/multiple-found behavior (raised by the queryset's async execution).

---

### `_load_model_class(self) -> type[Model]`

Resolves the Python model class from the reference's class name.

1. `class_manager = get_class_manager()` — calls `amsdal_models.contexts.get_class_manager()`. This reads `current_models_context().class_manager`. **If that is `None`, it raises `amsdal_models.errors.ModelsContextNotInitialisedError`** with the message:
   `'AmsdalModelsContext.class_manager is None. Call AmsdalManager.setup(config) before accessing class-manager state.'`
   This is the first failure point when debugging "reference won't load" in a process where AMSDAL was never set up.
2. `model_class = class_manager.import_class(self._reference.ref.class_name)` — delegates class lookup/import to the class manager using the reference's `class_name`. Any import/lookup error (unknown class name, unloaded module) surfaces from `import_class`.
3. Returns the resolved `type[Model]`.

No DB access here; this only resolves the class.

---

### `_load_record(self, model_class, only=None, using=None) -> 'QuerySetOneRequired[Model]'`

Builds (but does NOT execute) the queryset that fetches the referenced record. Returns a `QuerySetOneRequired[Model]`. This is the core version/alias-routing logic.

Lazy imports at the top of the method:
- `from amsdal_utils.models.enums import Versions`
- `from amsdal_models.querysets.base_queryset import QuerySet`

Steps and exact branches:

1. `class_version = self._reference.ref.class_version`.
   - `if class_version == 'LATEST':` → reassign `class_version = Versions.LATEST`. (Normalizes the raw-string form to the enum. Note `Versions` is a `str` Enum whose `LATEST` value is `'LATEST'`, so `Versions.LATEST == 'LATEST'` is also true; this branch specifically converts a plain-string input into the enum object.)

2. `version_id = self._reference.ref.object_version`.
   - `if version_id == 'LATEST':` → reassign `version_id = Versions.LATEST`.

3. Alias selection:
   - `if version_id != Versions.LATEST or class_version != Versions.LATEST:` → `_using = LAKEHOUSE_DB_ALIAS` (`'lakehouse'`).
     Meaning: if *either* the object version or the class version is a specific (non-LATEST) version, route to the lakehouse (historical/versioned) store.
   - `else:` (both are `Versions.LATEST`) → `_using = DEFAULT_DB_ALIAS` (`'default'`).
     Meaning: latest-of-both is served from the default operational store.

4. Build the queryset:
   ```
   qs = QuerySet(model_class).using(_using).get(
       _address__class_version=class_version,
       _address__object_id=self._reference.ref.object_id,
       _address__object_version=version_id,
   )
   ```
   - `.using(_using)` sets the version-derived alias.
   - `.get(...)` produces a "one required" queryset filtered by three exact keyword lookups (note the leading-underscore prefix `_address__`):
     - `_address__class_version` = the (possibly enum-normalized) `class_version`.
     - `_address__object_id` = `self._reference.ref.object_id` (used as-is; for composite PKs this is the sequence/scalar already normalized by the `Reference` validator).
     - `_address__object_version` = the (possibly enum-normalized) `version_id`.

5. `if only:` (truthy non-empty list) → `qs = qs.only(only)`. Restricts selected fields.

6. `if using:` (truthy explicit alias) → `qs = qs.using(using)`. This **overrides** the earlier version-derived `_using`, because `.using` is re-applied. So an explicit `using` argument always wins over the lakehouse/default routing.

7. Returns `qs` (unexecuted). Execution is the caller's responsibility (`.execute()` / `.aexecute()`).

#### Edge cases / debugging notes for `_load_record`

- Only the literal string `'LATEST'` is normalized to `Versions.LATEST`. The string `'ALL'` is *not* handled here, but per `Reference` validation `ALL` is never allowed for either version (the `Reference.set_address` validator raises `ValueError('Class version cannot be ALL.')` / `ValueError('Object version cannot be ALL.')` before a loader is ever created).
- A *specific* version string (anything other than `'LATEST'`/`Versions.LATEST`) leaves `class_version` / `version_id` as that raw string and forces the **lakehouse** alias. If a record exists only in `default` but the reference carries an explicit version, the lakehouse routing can produce a not-found error at execution time.
- `only` and `using` are falsy-checked, not `is not None`-checked: an empty list `only=[]` is treated like `None` (no `.only()` applied); an empty string `using=''` is treated like `None` (no override).

---

## Interactions with other modules

- **`Reference` (`amsdal_utils.models.data_models.reference`)**: `Reference.load(only, using)` calls `ReferenceLoaderManager().get_reference_loader()(self).load_reference(only=only, using=using)`; `Reference.aload(...)` does the async equivalent; `Reference.__await__` delegates to `aload()`. So `await reference` ultimately routes into `ReferenceLoader.aload_reference`.
- **`ReferenceLoaderManager` (singleton)**: holds the registered loader *class* in `_reference_loader`. `set_reference_loader(cls)` registers it; `get_reference_loader()` returns it. `ReferenceLoader` must be registered there (typically during AMSDAL setup) for `Reference.load/aload` to use it. If never registered, `get_reference_loader()` fails (attribute unset on the singleton).
- **`get_class_manager` / `AmsdalModelsContext`**: class resolution depends on the layered models context being initialized with a non-`None` `class_manager`. Uninitialized context → `ModelsContextNotInitialisedError`.
- **`QuerySet` (`amsdal_models.querysets.base_queryset`)**: all actual filtering, alias enforcement, field restriction, and DB execution (sync `execute` / async `aexecute`) plus not-found/multiple-found error semantics live in the queryset layer; `ReferenceLoader` only assembles the query.
- **DB aliases (`amsdal_data.aliases.using`)**: `'default'` for fully-LATEST references, `'lakehouse'` when any specific version is pinned.

## Quick failure-triage map

1. `ModelsContextNotInitialisedError` from `_load_model_class` → AMSDAL `setup` not called.
2. Import/lookup error from `import_class` → bad/unloaded `class_name` in the reference.
3. Record not found at `.execute()`/`.aexecute()` → check version routing: a non-`LATEST` version forces the `lakehouse` alias; verify the record exists in that store, or pass an explicit `using` override.
4. Wrong alias used despite expectations → an explicit `using` argument overrides version-derived routing (applied last).
