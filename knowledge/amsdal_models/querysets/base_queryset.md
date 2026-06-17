# `amsdal_models.querysets.base_queryset`

QuerySet class hierarchy and the machinery behind filtering, ordering, `select_related`, `prefetch_related`, PII handling, versioning, and instance materialization. This document is exhaustive enough to reason about a query/prefetch/select_related bug without the source.

Key imports / collaborators:
- `Executor` / `AsyncExecutor` (default), `ExecutorBase` / `AsyncExecutorBase`, `DEFAULT_DB_ALIAS` — from `amsdal_models.querysets.executor`. The executor actually runs SQL.
- `Prefetch` — from `amsdal_models.querysets.prefetch` (see its own section below).
- `apply_prefetches` / `aapply_prefetches` — from `amsdal_models.querysets.prefetch_executor`.
- `Q` — `amsdal_utils.query.utils.Q` (filter tree).
- `OrderBy`, `NumberPaginator`, `QuerySpecifier` — query data models from `amsdal_utils`.
- `ModelState`, `STATE_FIELD` — from `amsdal_models.classes.handlers.metadata_handler`.
- Reserved field constants `METADATA_FIELD`, `OBJECT_ID_FIELD`, `OBJECT_VERSION_FIELD`, `REFERENCE_KEY` — from `query_builders.reserved`.
- `sync_mode_only` / `async_mode_only` decorators gate sync vs async execution paths (raise if called in the wrong mode).

Module-level constants:
- `ModelType = TypeVar('ModelType', bound='Model')`
- `_FK_TARGET_CACHE_ATTR = '__fk_target_cache__'`
- `_HAS_PII_ANYWHERE_ATTR = '__has_pii_anywhere__'`

---

## `MembershipSpec` (dataclass, `frozen=True`)

Describes one many-to-many through-table constraint placed on a target queryset (used to render correlated `EXISTS` subqueries later; currently mostly inert metadata that survives clones).

Fields:
- `through_cls: Any` — the auto-generated M2M through model class.
- `source_fk: str` — FK field on the through model pointing back to the parent.
- `target_fk: str` — FK field on the through model pointing at the target.
- `parent: Any` — the parent **model instance**.
- `pin_source_version: bool = True` — whether to freeze (pin) the parent's version when building its reference.
- `parent_ref: Any = None` — transient; a RESOLVED reference copy produced at execute time via `dataclasses.replace`. Never set on the stored spec, only on the per-execute resolved copy.

---

## Module-level helper functions

### `_resolve_fk_target_model(current, segment) -> Any`
Returns the FK target class for `segment` on `current`, or `None` if `segment` is not an FK. Per-class cached in `current.__dict__['__fk_target_cache__']`.
1. If `current` is not a `type` → return `None`.
2. Read cache dict from `current.__dict__`; if empty, create it and store via `type.__setattr__`.
3. If `segment` in cache → return cached value (may be `None`).
4. Imports `FOREIGN_KEYS`, `resolve_field_info_by_external_name`, `build_fk_db_fields`.
5. `fk_fields = getattr(current, FOREIGN_KEYS, None) or []`. If `segment not in fk_fields` → cache `None`, return `None`.
6. `field_info = resolve_field_info_by_external_name(current, segment)`. If `None` → cache `None`, return `None`.
7. `fk_type, _, _ = build_fk_db_fields(segment, field_info)`; cache and return `fk_type`. The return may be a concrete `type[Model]` or a `ForwardRef` (unresolved). Callers treat non-`type` as terminal.

### `_seed_select_related_state(cls, data, state) -> None`
Stamps loaded `ModelState` onto FK targets that `select_related` materialized inline as nested dicts on the parent row. Without this, the nested child defaults to `adding=True` and a cascade save would re-INSERT it. Recursive at every nesting depth.
1. For each `fk` in `getattr(cls, FOREIGN_KEYS, None) or []`:
   - `child = data.get(fk)`; if not a `dict` → `continue`.
   - `child.setdefault(STATE_FIELD, ModelState(adding=False, is_from_lakehouse=state.is_from_lakehouse))` — only seeds if no `_state` key present (a reference-shaped dict resolves as a `Reference` and ignores the extra key, so this is a no-op there).
   - Resolve `fk_type` via `_resolve_fk_target_model`; if it is a `type`, recurse.

### `_has_pii_anywhere(cls, _seen=None) -> bool`
True if `cls` or any FK-reachable model has at least one PII field. Result cached on the class in `__has_pii_anywhere__`. Cycle-safe via a `seen` set.
1. Non-`type` → `False`.
2. Cached value (if not `None`) returned immediately.
3. If `cls in seen` → `False` (cycle). Add `cls` to `seen`.
4. If `get_pii_fields(cls)` truthy → cache `True`, return.
5. For each FK target, recurse; if any has PII → cache `True`, return.
6. Otherwise cache `False`, return.

### `_warn_pii_path(model, field_path) -> None`
Walks a `__`-separated path; if any segment names a PII field of its containing model, logs a **WARNING** (does not raise). Reason: PIIStr uses random-IV non-deterministic ciphertext, so filtering/ordering by it returns no rows.
- Split on `__`. For each part: if `current` is not a `type` → return (cannot inspect ForwardRef). If `part in get_pii_fields(current)` → `logger.warning('Querying by PIIStr field %s.%s — encrypted values use random IV (non-deterministic ciphertext); this query will return no rows. Use a separate non-PII field for searching.', current.__name__, part)` then return. Else advance `current` to the FK target; if `None`, return.

### `_warn_pii_in_q(model, q) -> None`
Recursively walks a `Q` tree; for each `Filter` child calls `_warn_pii_path(model, child.field_name)`; for each nested `Q` recurses.

### `_is_unsaved_model_instance(value) -> bool`
True iff `value` is a `Model` instance not yet persisted. Non-`Model` (incl. `Reference` / serialized strings) → `False`. Persisted-ness keys off `is_new_object` (i.e. `_state.adding`), **not** PK emptiness (AMSDAL auto-generates `object_id` at construction).

### `_validate_no_unsaved_relation_in_q(model, q) -> None`
Recursively walks a `Q` tree and **raises** if any filter value points at an unsaved `Model` instance (forward FK, reverse FK, or m2m — value-driven, no per-relation gating).
- For each child: nested `Q` → recurse; non-`Filter` → skip.
- `value = child.value`; candidates = `list(value)` if value is `list`/`tuple`/`set`, else `[value]`.
- For each candidate, if `_is_unsaved_model_instance(candidate)`:
  - `field = child.field_name.split('__', 1)[0]`; `model_name = getattr(model, '__name__', model)`.
  - Raises **`ValueError`**: `f'Cannot filter {model_name} at {field!r} against an unsaved instance of {type(candidate).__name__} — save it first or pass its Reference.'`

---

## `QuerySetBase(Generic[ModelType])`

Base for all queryset variants. Immutable-by-convention: every mutating method clones first (`_copy`) and mutates the clone. The bound entity (`_entity`) never changes for a queryset's lifetime.

### State (set in `__init__`)
- `_entity: type[ModelType]` — the model class. Immutable.
- `_executor` — `executor or Executor` (class, instantiated per execute as `self._executor(self)`).
- `_async_executor` — `async_executor or AsyncExecutor`.
- `_paginator: NumberPaginator = NumberPaginator(limit=None, offset=None)`.
- `_order_by: list[OrderBy] = []`.
- `_query_specifier: QuerySpecifier = QuerySpecifier(only=[], distinct=[])`.
- `_filter_groups: list[Q] = []` — one `Q` per `.filter()`/`.exclude()` call (structural separation preserved).
- `_m2m_membership: list[MembershipSpec] = []`.
- `_m2m_membership_resolved: list[MembershipSpec] | None = None` — per-execute transient; set at execute time, never carried across clones (not copied by `_from_queryset`).
- `_using: str = DEFAULT_DB_ALIAS`.
- `_select_related: bool | dict[str, Any] = False`.
- `_annotations: dict[str, Any] = {}`.
- `_strict_class_version` — from the `strict_class_version` kwarg (default `False`).
- `_is_none: bool = False`.
- `_decrypt_pii: bool = False`.
- `_prefetch: list[Prefetch] = []`.

`__init__` signature: `(entity, executor=None, async_executor=None, *, strict_class_version=False)`.

### Cloning — `_from_queryset` / `_copy` / `__copy__` / `all`
`_copy()` returns `self._from_queryset(self)`. `__copy__()` and `all()` both delegate to `_copy()`.

`_from_queryset(cls, queryset)` (classmethod) builds a **new instance of `cls`** (so it can up-cast between queryset variants) with `cls(queryset._entity)` (NOTE: executor/async_executor/strict_class_version are NOT re-passed; the new instance gets defaults for those), then copies:
- `_paginator = queryset._paginator.model_copy()`
- `_order_by = queryset._order_by.copy()`
- `_select_related` = the bool itself if bool, else `copy.deepcopy(...)`
- `_query_specifier = queryset._query_specifier.model_copy(deep=True)`
- `_filter_groups = [group.__copy__() for group in queryset._filter_groups]`
- `_m2m_membership = list(queryset._m2m_membership)`
- `_using = queryset._using`
- `_annotations = queryset._annotations.copy() if ... else {}`
- `_is_none = queryset._is_none`
- `_decrypt_pii = queryset._decrypt_pii`
- `_prefetch = list(queryset._prefetch)`

**NOT copied:** `_m2m_membership_resolved` (resets to `None`), `_executor`/`_async_executor`/`_strict_class_version` (reset to constructor defaults), and any subclass-specific attribute like `_raise_on_multiple` (re-initialized by the subclass `__init__` since `cls(...)` is called). This is why `_from_queryset` is the mechanism that converts a `QuerySet` into a `QuerySetOne`/`QuerySetOneRequired`/`QuerySetCount`/`QuerySetExists` while carrying filters/order/etc.

### Accessors
- `entity_name` (cached_property): if `is_partial_model(self._entity)` → `self._entity.__name__[:-len('Partial')]` (strips trailing `Partial`); else `self._entity.__name__`.
- `table_name` (property): `self._entity.__table_name__ or self.entity_name`.
- `entity` (property): `self._entity`.
- `get_conditions() -> Q | None`: if no `_filter_groups` → `None`; else AND-reduces copies of all groups (`functools.reduce(operator.and_, (group.__copy__() ...))`).
- `get_filter_groups() -> list[Q]`: list of `group.__copy__()`.
- `get_m2m_membership() -> list[MembershipSpec]`: returns `list(self._m2m_membership_resolved)` if resolved is not `None`, else `list(self._m2m_membership)`.
- `get_select_related() -> bool | dict`.
- `get_query_specifier() -> QuerySpecifier`.
- `get_order_by() -> list[OrderBy]`.
- `get_using() -> str`.
- `get_paginator() -> NumberPaginator`.

### `_with_m2m_membership(*, through_cls, source_fk, target_fk, parent, pin_source_version=True) -> Self`
Clones, then sets `_m2m_membership` to the old list plus a new `MembershipSpec(...)`. Returns the clone.

### `_resolve_membership_refs() -> list[MembershipSpec]` (sync)
For each stored spec: if `spec.pin_source_version` → try `spec.parent.build_reference(is_frozen=True)`, falling back to `spec.parent.build_reference()` on `ValueError`; else `spec.parent.build_reference()`. Appends `replace(spec, parent_ref=ref)`. Async twin `_aresolve_membership_refs` uses `abuild_reference`.

### Builder methods (each clones first)
- `using(value)` → sets `_using = value`.
- `annotate(**kwargs)` → for each key/value sets `new_qs._annotations[key] = value` (mutates the clone's copied dict).
- `only(fields)` → `new_qs._query_specifier.only = list(set(self._query_specifier.only or []) | set(fields))` (union with existing, de-duplicated, order non-deterministic).
- `distinct(fields)` → `new_qs._query_specifier.distinct = fields` (replaces).
- `none()` → sets `_is_none = True`.
- `order_by(*args)` → if `_has_pii_anywhere(entity)`, warns per arg on `arg.lstrip('-')`. Sets `new_qs._order_by = [OrderBy.from_string(arg) for arg in args]` (replaces). A leading `-` means descending.
- `decrypt_pii()` → sets `_decrypt_pii = True`.
- `latest()` → returns `self.filter(_address__object_version=Versions.LATEST)`.

### `filter(*args, **kwargs)` / `exclude(*args, **kwargs)`
`filter` → `self._filter(*args, **kwargs)`. `exclude` → `self._filter(*args, negated=True, **kwargs)`.

### `_filter(*args, negated=False, **kwargs) -> Self`
1. If no `args` and no `kwargs` → return `self` unchanged (no clone).
2. If `_has_pii_anywhere(self._entity)`: for each `q` in `args` → `_warn_pii_in_q`; for each kwarg selector → `_warn_pii_path`.
3. **Unsaved-relation validation (raises ValueError):** for each `q` in `args` → `_validate_no_unsaved_relation_in_q`; if `kwargs` → validate `Q(**kwargs)`.
4. Clone (`new_qs = self._copy()`).
5. Determine `new_conditions`: if `args` → `new_conditions = args[0]`, `args = args[1:]`; else `new_conditions = Q(**kwargs)`, `kwargs = {}`.
6. AND-combine remaining positional `args` into `new_conditions` (`&=`).
7. If `kwargs` still present → `new_conditions &= Q(**kwargs)`.
8. If `negated` → `new_conditions = ~new_conditions`.
9. If `new_conditions` truthy → `new_qs._filter_groups.append(new_conditions)`.
10. Return `new_qs`.

Each `_filter` call appends **one** group to `_filter_groups` (not merged), preserving per-call structure for later JOIN-alias allocation.

### `__getitem__(index: slice | int) -> Self`
Clones, then:
- slice: `start, stop, step = index.start/stop/step`. If `step not in (None, 1)` → raise **`ValueError`** `f'QuerySet slicing does not support step: {step}.'`. Sets `_paginator.offset = start`, `_paginator.limit = stop - start`.
- int: `_paginator.offset = index`, `_paginator.limit = index + 1`.

(No negative-index handling; uses raw arithmetic.)

### `select_related(*fields: str) -> Self`
Clones. Builds a nested dict from each `field` split on `__`: walks `field_dict` via `setdefault(part, {})` per segment. Sets `new_qs._select_related = field_dict`. **Replaces** any prior value (does not merge). Calling with no args sets `_select_related = {}` (an empty dict, which is falsy but not `False`). `QuerySet` overrides it (just `super().select_related(*fields)`).

### `prefetch_related(*args: str | Prefetch) -> Self`
Clones. For each `arg`:
- `str` → `new_qs._prefetch.append(Prefetch(lookup=arg))`.
- `Prefetch` → `new_qs._prefetch.append(arg)`.
- otherwise → raise **`TypeError`**: `f'prefetch_related arg must be str or Prefetch, got {type(arg).__name__}'`.

Appends (accumulates across calls). Prefetches run after materialization in `QuerySet.execute`/`aexecute` (see those methods). Note: `prefetch_related` is defined on `QuerySetBase`, but only `QuerySet.execute/aexecute` actually invoke `apply_prefetches`.

### Execution primitives (sync; `@sync_mode_only`)
All three first short-circuit on `_is_none`, then set `self._m2m_membership_resolved = self._resolve_membership_refs()` before delegating to a freshly-instantiated executor `self._executor(self)`:
- `_execute_query()` → `[]` if `_is_none`, else `.query()` → `list[glue.Data]`.
- `_execute_count()` → `0` if `_is_none`, else `.count()` → `int`.
- `_execute_exists()` → `False` if `_is_none`, else `.exists()` → `bool`.

Async twins (`@async_mode_only`): `_aexecute_query`, `_aexecute_count`, `_aexecute_exists` — identical but `await self._aresolve_membership_refs()` and `await self._async_executor(self).<op>()`.

### Instance materialization

#### `_metadata_signals_non_latest(metadata) -> bool` (staticmethod)
True iff the row's metadata pins a specific historical schema version.
- Not a `dict` → `False`. `class_schema_reference = metadata.get('class_schema_reference')`; not a `dict` → `False`.
- `version = class_schema_reference.get(REFERENCE_KEY, {}).get(OBJECT_VERSION_FIELD)`.
- Returns `version not in (glue.Version.LATEST, Versions.LATEST, '', None)`.

#### `_create_instance(*, _is_partial, data, state) -> ModelType` (sync)
Defines a lazy `_resolver()` returning `get_historical_schema_version_manager().get_latest_schema_version(self.entity_name)`, then delegates to `_legacy_or_native_instance`.

#### `_acreate_instance(*, _is_partial, data, state)` (async)
Pre-resolves the async-only dependency *only when needed*:
1. `cached_latest_version = None`. `_resolver()` raises **`RuntimeError`** `'async _acreate_instance: latest_version requested without metadata signaling non-LATEST version'` if called while `cached_latest_version is None`.
2. Peeks `data.data.get(METADATA_FIELD)` (if `data.data` is a dict). If `peek` is a `str`, `json.loads` it (on `TypeError`/`ValueError` → `peek=None`).
3. If `_metadata_signals_non_latest(peek)` → `await get_latest_schema_version(entity_name)` into `cached_latest_version`.
4. Delegates to `_legacy_or_native_instance`.

#### `_legacy_or_native_instance(*, _is_partial, data, latest_version_resolver, state) -> ModelType`
Shared sync core. Decides `LegacyModel` vs native entity construction.
1. `_data = {**data.data}` (shallow copy).
2. If `type(_data.get(METADATA_FIELD)) is str` → `_data[METADATA_FIELD] = json.loads(...)`.
3. If `METADATA_FIELD in _data` → try `_data[METADATA_FIELD][OBJECT_ID_FIELD] = json.loads(_data[METADATA_FIELD][OBJECT_ID_FIELD])`; swallow `TypeError`/`ValueError`.
4. For each `_pii_field` in `get_pii_fields(self._entity)`: if value is `str` but not `EncryptedStr` → wrap as `EncryptedStr(value)`.
5. `_seed_select_related_state(self._entity, _data, state)` — stamps `adding=False` onto inline select_related FK children (see helper).
6. If `_metadata_signals_non_latest(_data.get(METADATA_FIELD))`:
   - `latest_version = latest_version_resolver()`.
   - `version_from_metadata = _data[METADATA_FIELD]['class_schema_reference'][REFERENCE_KEY][OBJECT_VERSION_FIELD]`.
   - **LegacyModel branch** taken iff ALL of: `not self._strict_class_version` AND `data.metadata` truthy AND `COMPATIBLE_CLASS_VERSIONS in data.metadata` AND `{latest_version, version_from_metadata}` is **not** a subset of `data.metadata[COMPATIBLE_CLASS_VERSIONS]` — AND ALSO `version_from_metadata != latest_version`. If so → `return LegacyModel(original_class=self._entity, _state=state, **_data)`.
7. If `_is_partial` → `return create_partial_model(self._entity)(**_data, _state=state)`.
8. Else `obj = self._entity(**_data, _state=state)`; for each `_field` in `self._annotations`, if `_field in _data` → `setattr(obj, _field, _data[_field])`; return `obj`.

### PII decryption helpers
- `_collect_pii_for_decrypt(items, pii_fields) -> (all_values, index_map)`: iterates items × pii_fields; skips `None`; uses `value.ciphertext` if `EncryptedStr` else the raw value; builds parallel `all_values` and `index_map` (list of `(item_idx, field_name)`).
- `_batch_decrypt_pii(items)` (`@sync_mode_only`): `service = get_crypto_service()`. If `not service or not pii_fields or not items` → return `items` unchanged. Collect; if `not all_values` → return. `decrypted = service.decrypt(all_values)`; write back via `object.__setattr__(items[item_idx], field_name, decrypted[i])`. Returns `items`.
- `_abatch_decrypt_pii(items)` (`@async_mode_only`): same but `await service.adecrypt(...)`.

### `_check_type(obj) -> None`
If `type(obj) is not self._entity` → raise **`BulkOperationError`** `'Cannot update an object of a different type'`. (Exact type match; subclasses rejected.)

---

## `QuerySet(QuerySetBase[ModelType])`

The default deferred queryset returned by `<Model>.objects`. Adds variant-transition methods and list execution.

### Transition methods (build a different queryset class via `_from_queryset`)
- `get(*args, **kwargs)` → `QuerySetOneRequired._from_queryset(self._filter(*args, **kwargs))`. Execution returns one item or raises.
- `get_or_none(*args, **kwargs)` → `QuerySetOne._from_queryset(self._filter(*args, **kwargs))`. One item or `None`.
- `first(*args, **kwargs)` → builds a `QuerySetOne` from the filtered set, then sets `qs._raise_on_multiple = False` (so multiple rows do not raise; returns the first).
- `count()` → `QuerySetCount._from_queryset(self)`.
- `exists()` → `QuerySetExists._from_queryset(self)`.
- `select_related(*fields)`, `only`, `distinct`, `filter`, `exclude`, `order_by` — thin `super()` overrides (docstrings only; same behavior as base).

### `execute() -> list[ModelType]` (`@sync_mode_only`)
1. `is_partial = bool(self._query_specifier.only)`.
2. `is_from_lakehouse = self._executor(self).is_using_lakehouse`.
3. `res = self._execute_query()` (returns `[]` if `_is_none`).
4. Materialize each row: `self._create_instance(_is_partial=is_partial, data=item, state=ModelState(adding=False, is_from_lakehouse=is_from_lakehouse))`.
5. If `self._decrypt_pii` → `items = self._batch_decrypt_pii(items)`.
6. If `self._prefetch` → import `apply_prefetches` and call `apply_prefetches(items, self._prefetch, using=self._using)` (mutates items in place; see prefetch_executor section).
7. Return `items`.

### `aexecute() -> list[ModelType]` (`@async_mode_only`)
Async twin: `is_from_lakehouse` from `self._async_executor(self).is_using_lakehouse`; materializes via `await self._acreate_instance(...)` over `await self._aexecute_query()`; decrypt via `_abatch_decrypt_pii`; prefetch via `await aapply_prefetches(items, self._prefetch, using=self._using)`.

`only`/`distinct`/`filter`/`exclude`/`order_by` are `super()` overrides (docstrings only).

---

## `QuerySetOne(QuerySetBase[ModelType])`

Resolves to a single object or `None`.

### `__init__(entity)`
Calls `super().__init__(entity)` then sets `self._raise_on_multiple = True`. (Note: because `_from_queryset` calls `cls(entity)`, a cloned `QuerySetOne` is re-initialized with `_raise_on_multiple = True` unless explicitly overridden — `QuerySet.first()` overrides it to `False` after construction.)

`only`/`distinct`/`filter`/`exclude`/`order_by` — `super()` overrides (same behavior).

### `execute() -> ModelType | None` (`@sync_mode_only`)
1. `items = self._execute_query()`.
2. If `len(items) > 1 and self._raise_on_multiple` → raise **`MultipleObjectsReturnedError`** `'Multiple items found'`.
3. If `not items` → return `None`.
4. `is_partial = bool(self._query_specifier.only)`; `is_from_lakehouse` from `self._executor(self).is_using_lakehouse`.
5. `item = self._create_instance(_is_partial=is_partial, data=items[0], state=ModelState(adding=False, is_from_lakehouse=is_from_lakehouse))`.
6. If `_decrypt_pii` → `self._batch_decrypt_pii([item])` (note: result not re-assigned; mutation is in place).
7. Return `item`. **Note:** `QuerySetOne.execute` does NOT run prefetches (only `QuerySet.execute`/`aexecute` does).

### `aexecute()` (`@async_mode_only`)
Async twin; `MultipleObjectsReturnedError` same message; uses `await self._aexecute_query()`, `_acreate_instance`, `_abatch_decrypt_pii`.

---

## `QuerySetOneRequired(QuerySetOne[ModelType])`

Resolves to a single object or **raises** if none. Built by `QuerySet.get()`.

`only`/`distinct`/`filter`/`exclude`/`order_by` call `super(QuerySetOne, self).<m>(...)` — i.e. bypass `QuerySetOne` and go straight to `QuerySetBase`'s implementation (functionally identical).

### `execute() -> ModelType` (`@sync_mode_only`)
`item = super().execute()` (runs `QuerySetOne.execute`, including the multiple-objects check); if `item is None` → raise **`ObjectDoesNotExistError`** `'No items found'`; else return `item`.

### `aexecute()` — async twin; same `ObjectDoesNotExistError` `'No items found'`.

---

## `QuerySetCount(QuerySetBase[ModelType])`

Resolves to an `int` row count. Built by `QuerySet.count()`. `only`/`distinct`/`filter`/`exclude`/`order_by` are `super()` overrides.
- `execute() -> int` (`@sync_mode_only`): `return self._execute_count()`.
- `aexecute() -> int` (`@async_mode_only`): `return await self._aexecute_count()`.

Does not instantiate model objects.

---

## `QuerySetExists(QuerySetBase[ModelType])`

Resolves to a `bool`. Built by `QuerySet.exists()`. Issues a `LIMIT 1` SELECT (via the executor's `.exists()`); does NOT instantiate model objects. `only`/`distinct`/`filter`/`exclude`/`order_by` are `super()` overrides (no docstrings).
- `execute() -> bool` (`@sync_mode_only`): `return self._execute_exists()`.
- `aexecute() -> bool` (`@async_mode_only`): `return await self._aexecute_exists()`.

---

## Errors raised by this module (from `amsdal_models.querysets.errors`)

All inherit `AmsdalQuerySetError` (← `AmsdalError`):
- `ObjectDoesNotExistError` — `QuerySetOneRequired.execute/aexecute` when no row.
- `MultipleObjectsReturnedError` — `QuerySetOne.execute/aexecute` when >1 row and `_raise_on_multiple`.
- `BulkOperationError` — `_check_type` on type mismatch.
- `AmsdalQuerySetError` — raised in prefetch_executor for the M2M target-model-queryset misuse.

Plus stdlib `ValueError` (unsaved-relation filter, slice step), `TypeError` (`prefetch_related` bad arg), `RuntimeError` (`_acreate_instance` resolver misuse).

---

# Prefetch subsystem (sibling modules)

## `amsdal_models.querysets.prefetch.Prefetch` (dataclass, `frozen=True`)

User-facing descriptor for one prefetch operation. **Validation runs at construction time**, not at execute time.

Fields:
- `lookup: str` — dotted relationship path (e.g. `'book_set'`, `'book_set__publisher'`).
- `queryset: QuerySetBase[Any] | None = None` — optional custom queryset on the **target** model (or the **through** model for M2M); defaults to `<target>.objects.all()`.
- `to_attr: str | None = None` — optional attribute name to store results as a plain list (not the relationship cache).

### `__post_init__`
1. `lookup` not a `str` → **`TypeError`** `'Prefetch lookup must be a string'`.
2. Empty `lookup` → **`ValueError`** `'Prefetch lookup must be a non-empty string'`.
3. If `queryset is not None` → `_validate_queryset(queryset)`.

### `_validate_queryset(qs)` (staticmethod)
- `isinstance(qs, QuerySetOne)` → **`TypeError`** `'Prefetch.queryset must be a QuerySet, not a single-object query (.first/.last/.get)'`.
- `qs._using != DEFAULT_DB_ALIAS` → **`ValueError`** `'Prefetch.queryset cannot use `using()` — database is inherited from parent queryset'`.
- `qs._paginator.limit is not None or qs._paginator.offset is not None` → **`ValueError`** `'Prefetch.queryset cannot be sliced — per-parent limit needs window functions (not supported in v1)'`.
- `qs._query_specifier.distinct` → **`NotImplementedError`** `'Prefetch.queryset with `distinct()` is not supported in v1'`.
- `qs._annotations` → **`NotImplementedError`** `'Prefetch.queryset with `annotate()` is not supported in v1'`.

**M2M contract:** for an M2M field, `queryset` MUST be on the auto-generated through model, NOT the target model — otherwise `AmsdalQuerySetError` at execute time (see executor).

---

## `amsdal_models.querysets.prefetch_resolver`

### `RelationshipKind(str, Enum)`
`FORWARD_FK = 'forward_fk'`, `REVERSE_FK = 'reverse_fk'`, `M2M = 'm2m'`.

### `ResolvedPrefetch` (dataclass, frozen)
`kind: RelationshipKind`, `target_cls: type[Model]`, `grouping_fk_field: str`, `relation_name: str`, `remaining_path: str`.

### `resolve_path(parent_cls, lookup) -> ResolvedPrefetch`
Resolves only the **first** path segment. `head, _, rest = lookup.partition('__')`.
1. If `head` in `parent_cls.<FOREIGN_KEYS>` → FORWARD_FK; `target_cls = _resolve_forward_fk_target(...)`; `grouping_fk_field='_address__object_id'`; `relation_name=head`; `remaining_path=rest`.
2. Elif `head` in `parent_cls.<REVERSE_FOREIGN_KEYS>` → REVERSE_FK; `lookup_name = descriptor.reverser_qualified_name or descriptor.reverser_class_name`; `target_cls = _resolve_reverser_class(lookup_name)`; `grouping_fk_field = descriptor.fk_field`.
3. Elif `head` in `parent_cls.<MANY_TO_MANY_FIELDS>` → M2M; unpacks `(m2m_ref, _m2m_model, through_fields, _field_info)`; `target_cls = m2m_ref`; `grouping_fk_field = through_fields[0] if through_fields else parent_cls.__name__.lower()`.
4. Else → **`ValueError`** `f'{parent_cls.__name__} has no relationship named {head!r}'`.

`_resolve_forward_fk_target` raises **`ValueError`** if field_info is `None` (`f'Cannot resolve forward FK target for {parent_cls.__name__}.{fk_field}'`) or the annotation does not resolve to a class (`f'Forward FK target for {parent_cls.__name__}.{fk_field} did not resolve to a class'`).

---

## `amsdal_models.querysets.prefetch_executor`

Entry points: `apply_prefetches(parents, prefetches, *, using=None)` (sync) and `aapply_prefetches(...)` (async). Mutate `parents` in place; no return value.

### `apply_prefetches` / `aapply_prefetches`
1. If `not parents or not prefetches` → return.
2. `parent_cls = type(parents[0])`.
3. `_validate_to_attr_collisions(parent_cls, prefetches)`.
4. For each `prefetch`: `resolved = resolve_path(parent_cls, prefetch.lookup)`; then `_apply_one_sync` / `await _apply_one_async`.

### `_validate_to_attr_collisions(parent_cls, prefetches)`
For each prefetch with `to_attr is not None`:
- If `to_attr in parent_cls.model_fields` → **`ValueError`** `f'Prefetch.to_attr={p.to_attr!r} collides with existing field on {parent_cls.__name__}'`.
- If `to_attr in relation_names` (from `_relation_accessor_names`: union of `FOREIGN_KEYS`, `MANY_TO_MANY_FIELDS` keys, `REVERSE_FOREIGN_KEYS` keys, `REVERSE_MANY_TO_MANY` keys) → **`ValueError`** `f'Prefetch.to_attr={p.to_attr!r} collides with an existing relation accessor on {parent_cls.__name__}'`.

### `_augment_only_for_grouping(qs, grouping_field, target_cls)`
If the queryset has no `only` → return unchanged. Else compute `required = {grouping_field, *pk_field_names_of(target_cls)}`; if any are missing from `only` → `qs.only(list(missing))` (so grouping/PK fields are always fetched). Used so a user-supplied `only()` on a prefetch queryset still includes the columns needed to group results back to parents.

### `_apply_one_sync` / `_apply_one_async` (per prefetch, one path hop)
1. `saved = [p for p in parents if not p._state.adding]` — unsaved parents are skipped entirely.
2. Build `nested` list (for multi-hop / nested prefetches): `list(prefetch.queryset._prefetch)` if a queryset given, else `[]`. If `resolved.remaining_path` → append `Prefetch(resolved.remaining_path, to_attr=prefetch.to_attr)`.
3. If the hop queryset itself has `_prefetch` → clone it (`hop_queryset = hop_queryset.all()`) and clear `hop_queryset._prefetch = []` (those are captured in `nested`, avoiding double-resolution).
4. `_strip_to_attr = resolved.remaining_path and prefetch.to_attr is not None`. `hop1_prefetch = dataclasses.replace(prefetch, queryset=hop_queryset, to_attr=None if _strip_to_attr else prefetch.to_attr)` — on a multi-hop with a `to_attr`, the `to_attr` is deferred to the final hop and stripped from the intermediate hop.
5. Dispatch on `resolved.kind`:
   - `REVERSE_FK` → `_apply_reverse_fk_*`; then `collected = _collect_from_dict(saved, to_attr)` if `to_attr`, else `_collect_children_sync(saved, relation_name)`.
   - `FORWARD_FK` → `_apply_forward_fk_*`; then `collected = _collect_single_from_dict(...)` if `to_attr`, else `_collect_targets_sync(...)`.
   - `M2M` → if `not saved`: return; else `_apply_m2m_*(saved[0], saved, ...)`; collect like REVERSE_FK.
   - else → **`NotImplementedError`** `f'Prefetch kind {resolved.kind} not yet supported'`.
6. If `nested and collected` → recurse `apply_prefetches(collected, nested, using=using)`.

### Collectors
- `_collect_children_sync(parents, cache_key)`: extends from each parent's `__pydantic_private__[RELATIONSHIPS_CACHE_KEY][cache_key]` (skips `None`).
- `_collect_targets_sync(...)`: appends the single cached value (skips `None`).
- `_collect_from_dict(parents, attr)`: extends from each `p.__dict__.get(attr)` when truthy.
- `_collect_single_from_dict(parents, attr)`: appends each `p.__dict__.get(attr)` when not `None`.

### `_apply_forward_fk_sync` / `_apply_forward_fk_async`
1. If `not parents` → return.
2. `reference_attr = f'{resolved.relation_name}_reference'`. Collect non-`None` references into `target_refs` (a set).
3. If `target_refs` empty → for every parent set target to `None` (`object.__setattr__(p, to_attr, None)` if `to_attr`, else `write_cache(p, relation_name, None)`); return.
4. `is_lakehouse = parents[0]._state.is_from_lakehouse or get_data_application().is_lakehouse_only`.
5. If `is_lakehouse and prefetch.queryset is None` → `base_qs = target_cls.objects.using(LAKEHOUSE_DB_ALIAS).latest().filter(_metadata__is_deleted=False)` (latest + not-deleted view).
6. Else → `base_qs = prefetch.queryset or target_cls.objects.all()`; if `prefetch.queryset is None and using is not None` → `base_qs = base_qs.using(using)`.
7. `composed = _augment_only_for_grouping(base_qs, '_address__object_id', target_cls).filter(_address__object_id__in=[r.ref.object_id for r in target_refs])`.
8. `targets = composed.execute()` (or `await ...aexecute()`). `by_ref = {t.build_reference(): t for t in targets}`.
9. For each parent: look up its `reference_attr` value; `target = None` if missing else `by_ref.get(ref_val)`. If `to_attr` → `object.__setattr__(p, to_attr, target)`; else `write_cache(p, relation_name, target)` and (if both `target` and `ref_val` not `None`) populate `p.__dict__['__fk_resolved_cache__'][relation_name] = (ref_val, target)`.

### `_apply_reverse_fk_sync` / `_apply_reverse_fk_async`
1. If `not parents` → return. `is_lakehouse` as above.
2. **Lakehouse + no custom queryset branch:** `fk_field = resolved.grouping_fk_field`; collect distinct `parent_object_ids`; `raw_qs = target_cls.objects.using(LAKEHOUSE_DB_ALIAS).latest().filter(_metadata__is_deleted=False)`; augment-only; `composed = base_qs.filter(**{f'{fk_field}___address__object_id__in': parent_object_ids})`; execute; group children by `getattr(child, f'{fk_field}_reference').ref.object_id` (hashable). For each parent, `children_for_parent = grouped.get(hashable(parent.object_id), [])`; if `to_attr` → set list; else build `RelatedSet(parent, name=relation_name, strategy=_ReverseFKStrategy(fk_field=fk_field), target_cls, cache=...)` and `write_cache`. Return.
3. **Default branch:** `parent_refs = list({p.build_reference() for p in parents})`; `raw_qs = prefetch.queryset or target_cls.objects.all()`; if no queryset and `using` → `.using(using)`; augment-only on `grouping_fk_field`; `composed = base_qs.filter(**{f'{grouping_fk_field}__in': parent_refs})`; execute; group children by `getattr(child, f'{grouping_fk_field}_reference')`; per parent attach via `to_attr` or `RelatedSet`/`write_cache` keyed by `parent.build_reference()`.

### `_apply_m2m_sync` / `_apply_m2m_async`
1. If `not parents` → return. `through_cls = getattr(type(sample_parent), f'{resolved.relation_name}_through')`.
2. Collect distinct parent refs (`_m2m_parent_ref_sync`: `build_reference(is_frozen=True)` if `is_from_lakehouse` else `build_reference()`; async uses `abuild_reference`).
3. `target_field = _target_field_name(parent_cls, relation_name)` (`through_fields[1]` if present, else `m2m_ref.__name__.lower()`).
4. **Queryset-on-wrong-model guard:** if `prefetch.queryset is not None` and `prefetch.queryset._entity is not through_cls` → raise **`AmsdalQuerySetError`** with a long message: `Prefetch.queryset for M2M field {lookup!r} must be on the through-model ({through_cls.__name__}), not on the target model ({target_cls.__name__}). ...` (suggests using `{through_cls}.objects.select_related({lookup})...` or dropping `queryset=`).
5. `base_qs = prefetch.queryset or through_cls.objects.all()`; if no queryset and `using` → `.using(using)`.
6. `_exclude_deleted` = True only when `prefetch.queryset is None` AND (`sample_parent._state.is_from_lakehouse or get_data_application().is_lakehouse_only`).
7. **`_exclude_deleted` path:** query through-rows raw (`base_qs.filter(**{f'{grouping_fk_field}__in': parent_refs})`), collect `target_oid`s via `f'{target_field}_reference'`, then re-query targets `target_cls.objects.using(LAKEHOUSE_DB_ALIAS).latest().filter(_metadata__is_deleted=False).filter(_address__object_id__in=all_target_object_ids)`; build `target_by_oid` (hashable oid keys); group per parent (keyed by `f'{grouping_fk_field}_reference'`). Rationale: `select_related` would pin the FK to the through-row's version, which may predate a tombstone.
8. **Default path:** `base_qs.select_related(target_field).filter(**{f'{grouping_fk_field}__in': parent_refs})`; execute; group `getattr(row, target_field)` by `getattr(row, f'{grouping_fk_field}_reference')`.
9. For each parent: `targets = grouped.get(parent_ref, [])`; if `to_attr` → `object.__setattr__(parent, to_attr, list(targets))`; else build `RelatedSet(parent, name=relation_name, strategy=_M2MStrategy(through_cls, parent_fk=grouping_fk_field, target_fk=target_field), target_cls, cache=list(targets))` and `write_cache`.

### Storage outcome summary
- With `to_attr`: result stored as a plain attribute via `object.__setattr__` — a `list` for reverse-FK / M2M, a single object (or `None`) for forward-FK.
- Without `to_attr`: stored in the relationship cache via `write_cache(...)` under `relation_name` (`RELATIONSHIPS_CACHE_KEY` in `__pydantic_private__`); reverse-FK/M2M wrap results in a `RelatedSet`, forward-FK stores the single target. Forward-FK additionally records `__fk_resolved_cache__[relation_name] = (ref_val, target)`.
- **Unsaved parents (`_state.adding` True) are silently excluded** from all prefetch queries (`saved` filter).
- One SQL query is issued per prefetch level (per hop), batched across all parents via `<grouping_fk>__in=[...]`.
