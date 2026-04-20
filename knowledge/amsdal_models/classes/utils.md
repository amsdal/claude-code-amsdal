# Module: `amsdal_models.classes.utils`

Utility functions used internally by the class/model machinery. No classes — pure helpers for resolving module names, class references, discovering properties, and detecting partial models.

---

## `resolve_models_module(models_module_name, module_type) -> str`

Maps a base module name + `ModuleType` enum to the correct submodule path where models of that type live.

**Step-by-step:**

1. Dispatches on `module_type`:
   - `ModuleType.USER` → returns `f'{models_module_name}.{USER_MODELS_MODULE}'`
   - `ModuleType.CONTRIB` → returns `f'{models_module_name}.{CONTRIB_MODELS_MODULE}'`
   - `ModuleType.CORE` → returns `f'{models_module_name}.{CORE_MODELS_MODULE}'`
   - `ModuleType.TYPE` → returns `f'{models_module_name}.{TYPE_MODELS_MODULE}'`
2. If `module_type` matches none of the above → raises `ValueError(f'Invalid schema type: {module_type}')`.

The constants (`USER_MODELS_MODULE`, etc.) are imported from `amsdal_models.classes.constants` — see that module's knowledge file for the exact string values.

---

## `resolve_base_class_for_schema(schema) -> type[Union[Model, TypeModel]]`

Picks the appropriate base class (`Model` vs `TypeModel`) based on the schema's `meta_class` attribute.

**Step-by-step:**

1. If `schema.meta_class == MetaClasses.CLASS_OBJECT.value` → imports `Model` (deferred import from `amsdal_models.classes.model`) and returns it.
2. Otherwise → imports `TypeModel` (deferred import) and returns it.

**Note:** The comparison uses `.value` (string), not the enum itself. If `schema.meta_class` happens to be an enum instance, it won't match.

---

## `build_class_schema_reference(class_name, model_class) -> Reference`

Builds a `Reference` pointing to the schema record for a given model class. Used when you need to reference a class definition as data (AMSDAL stores class schemas as versioned records).

**Step-by-step:**

1. Reads `module_type = model_class.__module_type__` (set by the metaclass when the model is registered).
2. Chooses `schema_storage_class_name`:
   - If `module_type == ModuleType.TYPE` **or** the `class_name` is one of `BaseClasses.OBJECT`, `BaseClasses.CLASS_OBJECT`, `BaseClasses.CLASS_OBJECT_META` → uses `BaseClasses.OBJECT.value` ("Object" schema).
   - Otherwise → uses `BaseClasses.CLASS_OBJECT.value` ("ClassObject" schema).
3. Calls `build_reference(class_name=schema_storage_class_name, class_version=Versions.LATEST, object_id=class_name, object_version=Versions.LATEST)` and returns the result.

**Important:** The `object_id` of the returned reference is the model class name (string), not a UUID. Schema records are identified by class name.

---

## `build_class_meta_schema_reference(class_name, object_id) -> Reference | None`

Builds a reference to the class meta-schema. Returns `None` for any class that isn't `ClassObjectMeta`.

**Step-by-step:**

1. **Guard:** if `class_name != BaseClasses.CLASS_OBJECT_META` → returns `None`. Meta-schema references only exist for `ClassObjectMeta` records.
2. **Special case for `CLASS_OBJECT` objects:**
   - If `object_id == BaseClasses.CLASS_OBJECT` → sets `class_name = BaseClasses.OBJECT.value` and `object_id = BaseClasses.CLASS_OBJECT.value`.
   - Otherwise → sets `class_name = BaseClasses.CLASS_OBJECT.value` (but leaves `object_id` as-is).
3. Calls `build_reference(class_name=class_name, class_version=Versions.LATEST, object_id=object_id, object_version=Versions.LATEST)` and returns the result.

**Edge case:** The `class_name` local variable is reassigned in step 2 — the original parameter value is not returned in the reference.

---

## `get_custom_properties(model) -> set[str]`

Collects the names of all `@property`-decorated methods on a model class (and its ancestors), excluding `PrivateProperty` decorators.

**Step-by-step:**

1. Initializes an empty `set[str]` named `properties`.
2. Walks `model.mro()` (method resolution order). For each `_class`:
   - **Stops** as soon as it reaches `ModelBase` (does not inspect `ModelBase` itself or anything above it in the MRO).
   - Iterates `vars(_class).items()`. For each `(name, value)`:
     - If `isinstance(value, property)` **and** `not isinstance(value, PrivateProperty)` → adds `name` to the set.
3. Returns the set.

**Why it skips `ModelBase`:** This prevents the function from including built-in Pydantic/framework properties that exist on the base class. Only properties defined on user-subclasses are collected.

**PrivateProperty exclusion:** `PrivateProperty` (from `amsdal_models.classes.decorators.private_property`) is a subclass of `property`. The `isinstance(value, property) and not isinstance(value, PrivateProperty)` check includes all properties except private ones.

---

## `is_partial_model(model_class) -> bool`

Detects whether a class was created as a partial model (via the `pydantic_partial` library).

**Implementation:** Returns `model_class.__module__ == 'pydantic_partial.partial'`.

**Caveat:** This check is fragile — it depends on the internal module path of `pydantic_partial`. If the library restructures, this will silently break. There is no fallback check (no class attribute, no name suffix).

---

## `object_id_to_internal(object_id) -> Any`

Unwraps a single-element list into its sole element. Used to normalize composite primary keys that happen to have only one component.

**Step-by-step:**

1. If `isinstance(object_id, list)` **and** `len(object_id) == 1` → returns `object_id[0]`.
2. Otherwise → returns `object_id` unchanged.

**Behavior:**
- `[42]` → `42`
- `[42, 'abc']` → `[42, 'abc']` (multi-element list untouched)
- `42` → `42` (non-list untouched)
- `[]` → `[]` (empty list untouched — the length check requires exactly 1)
