# Module: `amsdal_models.classes.helpers.reference_loader`

This module provides `ReferenceLoader` — the mechanism AMSDAL uses to resolve `Reference` objects into actual `Model` instances. It is used whenever a field that holds a reference needs to be dereferenced (loaded from the database).

---

## `ReferenceLoader`

Subclass of `ReferenceLoaderBase` (from `amsdal_utils.models.data_models.reference`). Stateful wrapper around a single `Reference` object, with two public methods (`load_reference` / `aload_reference`) and two private helpers.

### State

| Attribute | Type | Description |
|---|---|---|
| `_reference` | `Reference` | The reference to load. Stored as-is in `__init__`. |

### `__init__(self, reference: Reference) -> None`

Stores the `reference` argument on `self._reference`. No validation, no class resolution — lookups are deferred until `load_reference`/`aload_reference` is called.

### `load_reference(self, only=None, using=None) -> Model` (sync)

Resolves the reference to a `Model` instance synchronously.

**Step-by-step:**

1. Calls `self._load_model_class()` → returns the `type[Model]` for the referenced class.
2. Calls `self._load_record(model_class, only=only, using=using)` → returns a `QuerySetOneRequired[Model]`.
3. Calls `.execute()` on the queryset to run the query synchronously and return the resolved `Model` instance.

**Raises:**
- Whatever `class_manager.import_class()` raises if the class name is unknown.
- `ObjectDoesNotExistError` (from `QuerySetOneRequired.execute()`) if no matching record is found.
- `MultipleObjectsReturnedError` if the filter matches more than one row.

### `aload_reference(self, only=None, using=None) -> Model` (async)

Same as `load_reference`, but awaits `aexecute()` instead of calling `execute()`. Use this in async-mode applications.

### `_load_model_class(self) -> type[Model]`

Resolves the model class from the reference's class name.

**Step-by-step:**

1. Instantiates `ClassManager()` (a singleton from `amsdal_models.classes.class_manager`).
2. Calls `class_manager.import_class(self._reference.ref.class_name)` — dynamically imports and returns the model class.
3. Returns the class.

**Raises:** whatever `import_class` raises when the class name cannot be resolved (typically an `ImportError` or class-registry-specific error).

### `_load_record(self, model_class, only=None, using=None) -> QuerySetOneRequired[Model]`

Builds the actual database query for the referenced object.

**Step-by-step:**

1. Imports `Versions` and `QuerySet` lazily (deferred imports — avoids circular dependencies).
2. Reads `class_version = self._reference.ref.class_version`. If it equals the **string** `'LATEST'`, replaces it with the enum value `Versions.LATEST`.
3. Reads `version_id = self._reference.ref.object_version`. If it equals the **string** `'LATEST'`, replaces it with the enum value `Versions.LATEST`.
4. **Database routing:**
   - If **either** `version_id` or `class_version` is **not** `Versions.LATEST` (i.e., a specific historical version is requested) → uses `_using = LAKEHOUSE_DB_ALIAS` (historical versions live in the lakehouse).
   - Otherwise (both are LATEST) → uses `_using = DEFAULT_DB_ALIAS` (current state DB).
5. Builds the queryset:
   - `QuerySet(model_class).using(_using).get(...)` with `_address__class_version`, `_address__object_id`, `_address__object_version` filters derived from `self._reference.ref`.
6. If `only` is provided (non-empty truthy list): applies `qs.only(only)`.
7. If `using` is provided (non-empty truthy string): applies `qs.using(using)` — **this overrides** the previously selected `_using`. Note: the `only`/`using` call order matters — `using` is applied after the initial `using(_using)` call.
8. Returns the configured queryset.

**Important behavioral notes:**

- **String vs enum comparison for 'LATEST':** The code compares `ref.class_version == 'LATEST'` (a string comparison, not an enum comparison). This means if the reference was serialized with the **enum value** directly (not the string `'LATEST'`), the routing logic in step 4 may differ.
- **Routing to lakehouse vs state:** This is the key detail for debugging "object not found" errors — if the reference points to a specific historical version, the query goes to the lakehouse connection. If the lakehouse is not configured or the version doesn't exist there, the `.execute()` call will raise `ObjectDoesNotExistError`.
- **`using` parameter wins over auto-routing:** The user-provided `using` argument is applied last, overriding both `LAKEHOUSE_DB_ALIAS` and `DEFAULT_DB_ALIAS`.

## Key interactions

| Module | Usage |
|---|---|
| `amsdal_data.aliases.using.DEFAULT_DB_ALIAS` | Used when both version fields are LATEST. |
| `amsdal_data.aliases.using.LAKEHOUSE_DB_ALIAS` | Used when a specific (non-LATEST) version is requested. |
| `amsdal_models.classes.class_manager.ClassManager` | Singleton used to dynamically import model classes by name. |
| `amsdal_models.querysets.base_queryset.QuerySet` | Deferred import; used to build the actual database query. |
| `amsdal_utils.models.enums.Versions.LATEST` | Enum constant for the "latest" sentinel. |

## Error summary

| Scenario | Exception | Origin |
|---|---|---|
| Unknown class name in reference | Depends on `ClassManager.import_class` (typically `ImportError`) | `_load_model_class` |
| No matching record | `ObjectDoesNotExistError('No items found')` | `QuerySetOneRequired.execute()` (see `base_queryset.md`) |
| Multiple matching records | `MultipleObjectsReturnedError('Multiple items found')` | Same as above |
