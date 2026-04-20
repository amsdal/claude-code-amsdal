# Module: `amsdal_models.querysets.base_queryset`

QuerySet hierarchy for building and executing database queries against AMSDAL models. Immutable, chainable API — each method returns a new queryset copy. Four concrete variants for different result shapes: list, optional single, required single, count.

**Module-level state:**
- `logger = logging.getLogger(__name__)`
- `ModelType = TypeVar('ModelType', bound='Model')` — generic type parameter for model types.

---

## `QuerySetBase[ModelType]` (base class)

Abstract base holding all query-building state and shared execution logic. All concrete QuerySet classes inherit from this.

### Constructor: `__init__(entity, executor=None, async_executor=None, *, strict_class_version=False)`

Initializes all state:

| Attribute | Type | Default |
|---|---|---|
| `_entity` | `type[ModelType]` | passed `entity` |
| `_executor` | `ExecutorBase[ModelType]` | `executor` if provided, else class `Executor` |
| `_async_executor` | `AsyncExecutorBase[ModelType]` | `async_executor` if provided, else `AsyncExecutor` |
| `_paginator` | `NumberPaginator` | `NumberPaginator(limit=None, offset=None)` |
| `_order_by` | `list[OrderBy]` | `[]` |
| `_query_specifier` | `QuerySpecifier` | `QuerySpecifier(only=[], distinct=[])` |
| `_conditions` | `Q \| None` | `None` |
| `_using` | `str` | `DEFAULT_DB_ALIAS` (from `amsdal_models.querysets.executor`) |
| `_select_related` | `bool \| dict[str, Any]` | `False` |
| `_annotations` | `dict[str, Any]` | `{}` |
| `_strict_class_version` | `bool` | passed value, default `False` |
| `_is_none` | `bool` | `False` |
| `_decrypt_pii` | `bool` | `False` |

### Property: `entity_name` → `str`

1. Calls `is_partial_model(self._entity)`.
2. If `True`: returns `self._entity.__name__[:-len('Partial')]` — strips trailing `'Partial'` (last 7 chars).
3. Otherwise: returns `self._entity.__name__`.

### Property: `table_name` → `str`

Returns `self._entity.__table_name__` if truthy, else falls back to `self.entity_name`.

### Property: `entity` → `type[ModelType]`

Returns `self._entity` directly.

### Getter methods (no state mutation)

- `get_conditions()` → `self._conditions` (`Q | None`)
- `get_select_related()` → `self._select_related` (`bool | dict[str, Any]`)
- `get_query_specifier()` → `self._query_specifier` (`QuerySpecifier`)
- `get_order_by()` → `self._order_by` (`list[OrderBy]`)
- `get_using()` → `self._using` (`str`)
- `get_paginator()` → `self._paginator` (`NumberPaginator`)

### Chainable methods — all return new queryset copies

#### `using(value: str) -> Self`

Copy via `self._copy()`, sets `new_qs._using = value`, returns new.

#### `annotate(**kwargs) -> Self`

Copy, iterates `kwargs.items()` and sets `new_qs._annotations[key] = value`. **Note:** annotations are additive across chained calls because `_copy()` copies the dict and this mutates it.

#### `_from_queryset(cls, queryset) -> Self` (classmethod)

Creates a new instance of `cls` from an existing queryset. Used by `_copy()` and by cross-class conversions (e.g., `QuerySet.get()` → `QuerySetOneRequired`).

**Step-by-step:**

1. Constructs `cls(queryset._entity)` — passes ONLY entity; all other fields start at defaults.
2. Copies each attribute manually:
   - `_paginator`: `queryset._paginator.model_copy()` (Pydantic shallow copy)
   - `_order_by`: `queryset._order_by.copy()` (list shallow copy)
   - `_select_related`: if `bool` → direct assignment; else `copy.deepcopy()`
   - `_query_specifier`: `queryset._query_specifier.model_copy(deep=True)` (Pydantic DEEP copy)
   - `_conditions`: `queryset._conditions.__copy__()` if non-None, else `None`
   - `_using`: direct assignment
   - `_annotations`: `.copy()` if truthy, else `{}`
   - `_is_none`: direct assignment
   - `_decrypt_pii`: direct assignment
3. Returns the new instance.

**CRITICAL — `_strict_class_version` is NOT copied:** The new instance gets whatever default `cls.__init__` sets (which is `False`). Going from `QuerySet(strict_class_version=True)` through `_from_queryset` (e.g., via `.get()`, `.first()`, `.count()`) **loses the flag**. This is a potential source of bugs.

#### `all() -> Self`

Returns `self._copy()` — full copy with no modifications.

#### `_copy() -> Self`

Delegates to `self._from_queryset(self)`.

#### `__copy__() -> Self`

Delegates to `self._copy()`. `copy.copy(qs)` produces the same result as `qs.all()`.

#### `only(fields: list[str]) -> Self`

1. Copy.
2. Merges new `fields` with existing via set union: `list(set(self._query_specifier.only or []) | set(fields))`.
3. Assigns to `new_qs._query_specifier.only`.

**Behavior:** `only()` is **additive** across calls — `.only(['a']).only(['b'])` results in `only=['a', 'b']`.

#### `distinct(fields: list[str]) -> Self`

1. Copy.
2. Assigns `new_qs._query_specifier.distinct = fields` (direct replacement, NO union).

**Behavior:** `distinct()` is **replacing** — `.distinct(['a']).distinct(['b'])` results in `distinct=['b']`.

#### `none() -> Self`

1. Copy, sets `new_qs._is_none = True`.

**Sticky behavior:** Once `_is_none = True`, it persists through all chained operations (because `_copy()` preserves it via `_from_queryset`). Only way to "undo" is to start a new queryset.

#### `filter(*args: Q, **kwargs) -> Self`

Calls `self._filter(*args, **kwargs)`.

#### `exclude(*args: Q, **kwargs) -> Self`

Calls `self._filter(*args, negated=True, **kwargs)`.

#### `_filter(*args, negated=False, **kwargs) -> Self`

Combines filter arguments into a `Q` object and ANDs with existing conditions.

**Step-by-step:**

1. **No-op guard:** If `not args and not kwargs` → returns `self` unchanged (NOT a copy!).
2. Copy via `self._copy()`.
3. **Build `new_conditions`:**
   - If `args` is truthy: `new_conditions = args[0]`, `args = args[1:]` (consume first Q from args).
   - Else: `new_conditions = Q(**kwargs)`, `kwargs = {}` (consume all kwargs into a Q).
4. For remaining `args`: `new_conditions &= arg` (AND-combine).
5. If `kwargs` still has content: `new_conditions &= Q(**kwargs)`.
6. **Negation:** If `negated=True` → `new_conditions = ~new_conditions`.
7. **Combine with existing:** If `new_conditions` is truthy:
   - If `new_qs._conditions` already exists: `new_qs._conditions &= new_conditions`.
   - Else: `new_qs._conditions = new_conditions`.
8. Returns `new_qs`.

**Edge case:** Step 1 returns `self` (not a copy) when no args/kwargs. So `qs.filter()` and `qs` are literally the same object.

#### `order_by(*args: str) -> Self`

1. Copy.
2. Sets `new_qs._order_by = [OrderBy.from_string(arg) for arg in args]` — **replaces** entire list each call.

#### `__getitem__(index: slice | int) -> Self`

1. Copy.
2. **Slice branch:**
   - Extracts `start, stop, step`.
   - If `step is not None and step != 1` → raises `ValueError(f'QuerySet slicing does not support step: {step}.')`.
   - `new_qs._paginator.offset = start`.
   - `new_qs._paginator.limit = stop - start`.
3. **Int index branch:**
   - `new_qs._paginator.offset = index`.
   - `new_qs._paginator.limit = index + 1`.

**CRITICAL behavior:** For integer index, `limit = index + 1` (not `1`). For `qs[0]`, limit=1 (correct). For `qs[5]`, limit=6 (not 1 — fetches rows 5 through 10, returns the last one? Or fetches 6 rows starting from offset 5? Depends on executor. This is likely a bug waiting to surprise someone.)

#### `select_related(*fields) -> Self`

Builds a nested dict from `__`-separated field paths.

1. Copy.
2. For each `field` string:
   - Split on `'__'`.
   - Walks a nested dict, creating sub-dicts via `setdefault(part, {})`.
3. Assigns `new_qs._select_related = field_dict`.

**Example:** `select_related('author', 'publisher__address')` produces `{'author': {}, 'publisher': {'address': {}}}`.

### Execution helpers

#### `_execute_query() -> list[glue.Data]` (sync, `@sync_mode_only`)

1. If `self._is_none` → returns `[]`.
2. Otherwise: `self._executor(self).query()`.

#### `_execute_count() -> int` (sync, `@sync_mode_only`)

1. If `self._is_none` → returns `0`.
2. Otherwise: `self._executor(self).count()`.

#### `_aexecute_query() -> list[glue.Data]` (async, `@async_mode_only`)

Same logic, but uses `self._async_executor(self).query()` awaited.

#### `_aexecute_count() -> int` (async, `@async_mode_only`)

Same logic with `self._async_executor(self).count()` awaited.

### Instance creation: `_create_instance(*, _is_partial, data) -> ModelType` (sync)

Converts a `glue.Data` row into a model instance, handling metadata parsing and class-version compatibility.

**Step-by-step:**

1. Lazy imports: `COMPATIBLE_CLASS_VERSIONS` (from `amsdal_data.services.historical_table_schema`), `LegacyModel` (from `amsdal_models.classes.model`).
2. `_data = {**data.data}` — shallow copy of row data.
3. **Metadata JSON parsing:** If `_data.get('_metadata')` is exactly type `str` → replaces with `json.loads(_data['_metadata'])`.
4. **Object ID JSON parsing:** If `'_metadata' in _data`:
   - `try`: `_data['_metadata']['object_id'] = json.loads(_data['_metadata']['object_id'])`.
   - Catches `(TypeError, ValueError)` and silently ignores — means `object_id` stays as-is if it's not valid JSON.
5. **Version compatibility check:** If `_metadata` has a non-empty `class_schema_reference` (dict) and the `object_version` is NOT one of `glue.Version.LATEST`, `Versions.LATEST`, or `''`:
   - Queries `HistoricalSchemaVersionManager().get_latest_schema_version(self.entity_name)` → `latest_version`.
   - Reads `version_from_metadata = _data['_metadata']['class_schema_reference']['ref']['object_version']`.
   - **If all of these are true:**
     - `not self._strict_class_version`
     - `data.metadata` is truthy
     - `COMPATIBLE_CLASS_VERSIONS in data.metadata`
     - `{latest_version, version_from_metadata}` is NOT a subset of `data.metadata[COMPATIBLE_CLASS_VERSIONS]`
     - `version_from_metadata != latest_version`
   - Returns `LegacyModel(original_class=self._entity, **_data)` — a legacy wrapper, NOT an instance of the original model.
6. **Partial path:** If `_is_partial` → `create_partial_model(self._entity)(**_data)`.
7. **Regular instantiation:** `obj = self._entity(**_data)`.
8. **Annotation attachment:** For each field in `self._annotations`: if field is in `_data` → `setattr(obj, field, _data[field])`.
9. Returns `obj`.

**Key detail:** `_strict_class_version=True` causes the legacy-model fallback to be skipped — always returns an instance of the requested class, even if schema versions are incompatible.

### Instance creation: `_acreate_instance(*, _is_partial, data) -> ModelType` (async)

Same logic as `_create_instance` EXCEPT:
- Uses `await AsyncHistoricalSchemaVersionManager().get_latest_schema_version(...)`.
- **`_strict_class_version` check is MISSING** in the condition — the async version always returns LegacyModel when other conditions match, regardless of `_strict_class_version`.

**⚠️ SYNC/ASYNC ASYMMETRY:** The sync version honors `_strict_class_version`; the async version does not. This is an inconsistency bug.

### PII decryption

#### `decrypt_pii() -> Self`

Copy, sets `new_qs._decrypt_pii = True`.

#### `_batch_decrypt_pii(items) -> list[ModelType]` (sync)

1. `service = get_crypto_service()`, `pii_fields = get_pii_fields(self._entity)`.
2. Early return if no service, no PII fields, or no items → returns `items` unchanged.
3. Collects `all_values = []` and `index_map = [(item_idx, field_name), ...]` for every non-None PII field value.
4. If no values → returns `items` unchanged.
5. `decrypted = service.decrypt(all_values)` — batch decryption.
6. For each decrypted value: `object.__setattr__(items[item_idx], field_name, decrypted[i])` — **bypasses Pydantic setattr**, writes directly.
7. Returns `items` (the SAME list, mutated in place — not a new list).

#### `_abatch_decrypt_pii(items) -> list[ModelType]` (async)

Same logic but uses `await service.adecrypt(all_values)`.

### Other methods

#### `latest() -> Self`

Returns `self.filter(_address__object_version=Versions.LATEST)`.

#### `_check_type(obj) -> None`

If `type(obj) is not self._entity` → raises `BulkOperationError('Cannot update an object of a different type')`.

Note: uses `type(obj) is not` (strict type check, not `isinstance`) — subclasses will fail this check.

---

## `QuerySet[ModelType]` — list-returning QuerySet

Public interface for database access. Inherits from `QuerySetBase`.

### `get(*args, **kwargs) -> QuerySetOneRequired[ModelType]`

Converts to `QuerySetOneRequired` via `QuerySetOneRequired._from_queryset(self._filter(*args, **kwargs))`. Applies filters before conversion.

### `get_or_none(*args, **kwargs) -> QuerySetOne[ModelType]`

Converts to `QuerySetOne` via `QuerySetOne._from_queryset(self._filter(*args, **kwargs))`.

### `first(*args, **kwargs) -> QuerySetOne[ModelType]`

Converts to `QuerySetOne` BUT sets `qs._raise_on_multiple = False` — tolerates multiple results, returns the first.

### `count() -> QuerySetCount[ModelType]`

Converts to `QuerySetCount` via `_from_queryset(self)` (no filter applied here, just conversion).

### `execute() -> list[ModelType]` (sync, `@sync_mode_only`)

1. `is_partial = bool(self._query_specifier.only)` — true if any `.only()` was applied.
2. `res = self._execute_query()` — returns `list[glue.Data]`.
3. Creates instances via list comprehension: `[self._create_instance(_is_partial=is_partial, data=item) for item in res]`.
4. If `self._decrypt_pii` → applies `_batch_decrypt_pii`.
5. Returns the list.

### `aexecute() -> list[ModelType]` (async, `@async_mode_only`)

Same logic with `_aexecute_query()` and `_acreate_instance()` awaited.

### Chainable methods (`only`, `distinct`, `filter`, `exclude`, `order_by`, `select_related`)

All delegate to `super().*(...)` — just for signature documentation.

---

## `QuerySetOne[ModelType]` — optional single-result QuerySet

Inherits from `QuerySetBase`. Returns single model or `None`.

### `__init__(entity)`

1. `super().__init__(entity)` — with defaults, NO `strict_class_version`.
2. Sets `self._raise_on_multiple = True` (instance attribute — NOT copied by `_from_queryset`).

**Note:** `_raise_on_multiple` is NOT in `_from_queryset` — if you convert a `QuerySet` → `QuerySetOne` via `_from_queryset`, it defaults to `True` because `__init__` sets it. But `first()` explicitly sets it to `False` AFTER conversion.

### `execute() -> ModelType | None` (sync, `@sync_mode_only`)

1. `items = self._execute_query()` — no automatic LIMIT applied!
2. If `len(items) > 1 and self._raise_on_multiple` → raises `MultipleObjectsReturnedError('Multiple items found')`.
3. If `not items` → returns `None`.
4. `is_partial = bool(self._query_specifier.only)`.
5. `item = self._create_instance(_is_partial=is_partial, data=items[0])`.
6. If `self._decrypt_pii` → `self._batch_decrypt_pii([item])` (but return value discarded — mutation in place).
7. Returns `item`.

**⚠️ Key behavior:** `execute()` does **NOT add LIMIT 1** automatically. If your filter matches thousands of rows, ALL are fetched before the count check. Potential performance issue for `get_or_none()` without explicit filtering.

### `aexecute() -> ModelType | None` (async)

Same logic, awaited.

---

## `QuerySetOneRequired[ModelType]` — required single-result QuerySet

Inherits from `QuerySetOne`. Raises if no items found.

### `execute() -> ModelType` (sync, `@sync_mode_only`)

1. `item = super().execute()` — delegates to `QuerySetOne.execute()`.
2. If `item is None` → raises `ObjectDoesNotExistError('No items found')`.
3. Returns `item`.

Inherits `MultipleObjectsReturnedError` behavior from parent.

### `aexecute() -> ModelType` (async)

Same logic, awaited.

### Chainable methods — use `super(QuerySetOne, self)`

Methods `only`, `distinct`, `filter`, `exclude`, `order_by` all use `super(QuerySetOne, self).<method>(...)` — explicitly **skipping** `QuerySetOne`'s override and going directly to `QuerySetBase`. This preserves the return type as `QuerySetOneRequired`, not `QuerySetOne`.

---

## `QuerySetCount[ModelType]` — count QuerySet

Inherits from `QuerySetBase`. Returns integer count.

### `execute() -> int` (sync)

Calls `self._execute_count()` and returns the integer result.

### `aexecute() -> int` (async)

Calls `await self._aexecute_count()`.

### Chainable methods (`only`, `distinct`, `filter`, `exclude`, `order_by`)

Delegate to `super()`.

---

## Key behavioral notes for debugging

1. **Immutability pattern:** Every chainable method returns a new queryset copy. Shallow for `_annotations` and `_order_by` (list `.copy()`); `_select_related` dict is deep-copied only if it's not a `bool`.

2. **`_strict_class_version` is LOST on conversion:** `_from_queryset` does not copy this flag. Conversions via `.get()`, `.first()`, `.count()`, `.get_or_none()` reset it to `False`.

3. **Sync/async asymmetry in `_create_instance`:** Sync checks `self._strict_class_version` in the legacy-model fallback; async does NOT. Behavior differs between the two modes.

4. **`__getitem__` with int index uses `limit = index + 1`:** For `qs[5]`, this sets offset=5 and limit=6. For `qs[0]`, correctly limit=1. The semantics differ from typical list indexing.

5. **`QuerySetOne.execute()` fetches ALL rows first:** No auto-LIMIT. With a loose filter, this can load thousands of rows before the multiple-results check. Use explicit `[:1]` slicing if you need LIMIT semantics.

6. **PII decryption mutates in place:** `_batch_decrypt_pii` uses `object.__setattr__` to bypass Pydantic. Returns the same list — don't rely on getting a new list.

7. **`none()` is sticky:** Once applied, persists through all subsequent chained operations (via `_from_queryset`).

8. **`only()` accumulates, `distinct()` replaces:**
   - `.only(['a']).only(['b'])` → `only=['a', 'b']` (set union)
   - `.distinct(['a']).distinct(['b'])` → `distinct=['b']` (replacement)

9. **`filter()` without args returns `self`, not a copy.** This is a performance optimization but means `qs.filter() is qs` is True.

10. **`_check_type` uses `type() is`, not `isinstance`:** Subclasses fail the check.

11. **Annotations carried into instances:** After fetching, `_annotations` keys are copied onto model instances via `setattr` if present in the row data. Useful for computed fields.

12. **Error messages are exact strings:**
    - `MultipleObjectsReturnedError('Multiple items found')`
    - `ObjectDoesNotExistError('No items found')`
    - `BulkOperationError('Cannot update an object of a different type')`
    - `ValueError(f'QuerySet slicing does not support step: {step}.')`

## Key interactions

| Module | Usage |
|---|---|
| `amsdal_glue` | `glue.Data`, `glue.Version.LATEST` — row data structures and version constants. |
| `amsdal_data.connections.historical.schema_version_manager` | `HistoricalSchemaVersionManager` / `AsyncHistoricalSchemaVersionManager` for version compatibility checks. |
| `amsdal_data.services.historical_table_schema.COMPATIBLE_CLASS_VERSIONS` | Metadata key for version compatibility — lazily imported in `_create_instance`. |
| `amsdal_models.classes.model.LegacyModel` | Fallback model for incompatible schema versions — lazily imported. |
| `amsdal_models.querysets.executor.Executor` / `AsyncExecutor` | Default executors that translate QuerySet state into glue queries. |
| `amsdal_models.classes.fields.pii` | `get_crypto_service`, `get_pii_fields` — PII decryption support. |
| `pydantic_partial.create_partial_model` | Creates partial model classes when `only()` is in effect. |
| `amsdal_utils.utils.decorators.sync_mode_only` / `async_mode_only` | Decorators that raise if called in the wrong mode. |
