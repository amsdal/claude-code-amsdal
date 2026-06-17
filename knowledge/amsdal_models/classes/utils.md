# `amsdal_models.classes.utils`

Module of stateless helper functions used by the AMSDAL model layer to:
resolve generated-module names, resolve the base model class for a schema,
build `Reference` objects pointing at class schemas / class-meta schemas,
discover custom properties on a model, and detect / normalize
`pydantic_partial`-generated partial models.

There are **no classes** defined in this module — it is a collection of
module-level functions plus two module-level string constants.

## Imports and external dependencies

- `amsdal_utils.models.base.ModelBase` — root sentinel used as the MRO stop
  condition in `get_custom_properties`.
- `amsdal_utils.models.data_models.enums.BaseClasses` — `str`-backed `Enum`:
  `OBJECT = 'Object'`, `CLASS_OBJECT = 'ClassObject'`,
  `CLASS_OBJECT_META = 'ClassObjectMeta'`. Because it subclasses `str`, a member
  compares equal to its string value (e.g. `BaseClasses.OBJECT == 'Object'`).
- `amsdal_utils.models.data_models.enums.MetaClasses` — `str`-backed `Enum`:
  `TYPE = 'TypeMeta'`, `CLASS_OBJECT = 'ClassObject'`.
- `amsdal_utils.models.data_models.reference.Reference` — returned by reference
  builders.
- `amsdal_utils.models.enums.ModuleType` — `str`-backed `Enum`: `TYPE = 'type'`,
  `CORE = 'core'`, `USER = 'user'`, `CONTRIB = 'contrib'`.
- `amsdal_utils.models.enums.Versions` — `str`-backed `Enum`: `ALL = 'ALL'`,
  `LATEST = 'LATEST'`.
- `amsdal_utils.models.utils.reference_builders.build_reference` — actual
  `Reference` constructor (see notes under reference-building functions).
- `amsdal_utils.schemas.schema.ObjectSchema` — schema input type.
- `amsdal_models.classes.base.BaseModel` — type hint for model classes.
- Module-name constants from `amsdal_models.classes.constants`:
  `CONTRIB_MODELS_MODULE = 'contrib'`, `CORE_MODELS_MODULE = 'core'`,
  `TYPE_MODELS_MODULE = 'type'`, `USER_MODELS_MODULE = 'user'`.
- `amsdal_models.classes.decorators.private_property.PrivateProperty` — a
  `property` subclass; used to exclude private properties in
  `get_custom_properties`.
- Under `TYPE_CHECKING` only: `Model` and `TypeModel` from
  `amsdal_models.classes.model` (real imports are done lazily inside the
  functions that need them).

## Module-level constants

- `_PARTIAL_MODEL_MODULE = 'pydantic_partial.partial'` — exact module path that
  `pydantic_partial.create_partial_model` assigns as `__module__` to generated
  partial models. Used by both `is_partial_model` and `is_partial_namespace`.

---

### `resolve_models_module(models_module_name: str, module_type: ModuleType) -> str`

Builds the fully-qualified generated-models submodule name for a given base
module name and a `ModuleType`.

Step-by-step (if/elif chain on `module_type`):

1. If `module_type == ModuleType.USER` → return `f'{models_module_name}.user'`
   (i.e. `f'{models_module_name}.{USER_MODELS_MODULE}'`).
2. Elif `module_type == ModuleType.CONTRIB` → return
   `f'{models_module_name}.contrib'`.
3. Elif `module_type == ModuleType.CORE` → return `f'{models_module_name}.core'`.
4. Elif `module_type == ModuleType.TYPE` → return `f'{models_module_name}.type'`.
5. Else → build `msg = f'Invalid schema type: {module_type}'` and
   `raise ValueError(msg)`.

Side effects: none. The suffix strings come from the `*_MODELS_MODULE`
constants; note each constant equals the lowercase value of its corresponding
`ModuleType` member.

---

### `resolve_base_class_for_schema(schema: ObjectSchema) -> type[Union[Model, TypeModel]]`

Decides whether a schema should be backed by the full `Model` class or the
lighter `TypeModel` class, based on the schema's `meta_class` attribute.

Step-by-step:

1. If `schema.meta_class == MetaClasses.CLASS_OBJECT.value` (i.e. the string
   `'ClassObject'`):
   - Lazily `from amsdal_models.classes.model import Model`.
   - Return `Model`.
2. Else (any other `meta_class` value, including `'TypeMeta'` /
   `MetaClasses.TYPE.value`):
   - Lazily `from amsdal_models.classes.model import TypeModel`.
   - Return `TypeModel`.

Notes:
- Comparison is against the enum's `.value` (`'ClassObject'`), so
  `schema.meta_class` is expected to be a plain string.
- The docstring mentions `ValueError` for an invalid meta class, but the actual
  implementation has **no such raise** — every non-`'ClassObject'` value falls
  into the `TypeModel` branch.
- Imports are intentionally local to avoid circular imports with
  `amsdal_models.classes.model`.

---

### `build_class_schema_reference(class_name: str, model_class: type[BaseModel]) -> Reference`

Builds a `Reference` that points at the *schema record* describing a class.
Determines, from the model's module type and the class name, which storage
class (`'Object'` vs `'ClassObject'`) holds that schema.

Step-by-step:

1. Read `module_type = model_class.__module_type__` (a `ModuleType`, provided by
   the model class itself).
2. Branch deciding `schema_storage_class_name`:
   - If `module_type == ModuleType.TYPE` **OR** `class_name` is in the tuple
     `(BaseClasses.OBJECT, BaseClasses.CLASS_OBJECT, BaseClasses.CLASS_OBJECT_META)`:
     - `schema_storage_class_name = BaseClasses.OBJECT.value` → `'Object'`.
   - Else:
     - `schema_storage_class_name = BaseClasses.CLASS_OBJECT.value` →
       `'ClassObject'`.
   - The `in` membership uses enum members on the right side; since `BaseClasses`
     subclasses `str`, a plain `class_name` string such as `'Object'`,
     `'ClassObject'`, or `'ClassObjectMeta'` will match the corresponding member.
3. Return `build_reference(...)` with keyword arguments:
   - `class_name = schema_storage_class_name`
   - `class_version = Versions.LATEST`
   - `object_id = class_name` (the original passed-in `class_name`)
   - `object_version = Versions.LATEST`

Resulting `Reference` shape (built by `build_reference`): a `Reference` whose
`ref` is a `ReferenceData` with fields `resource` (connection name looked up via
`AmsdalConfigManager().get_connection_name_by_model_name(schema_storage_class_name)`),
`class_name = schema_storage_class_name`, `class_version = Versions.LATEST`,
`object_id = class_name`, `object_version = Versions.LATEST`.

The docstring lists `ValueError` ("If the schema type is invalid"), but this
function itself does not raise.

---

### `build_class_meta_schema_reference(class_name: str, object_id: Any) -> Reference | None`

Builds a `Reference` to a class *meta* schema, but only for the
`ClassObjectMeta` record; returns `None` otherwise.

Step-by-step:

1. Guard: if `class_name != BaseClasses.CLASS_OBJECT_META` (i.e. not the string
   `'ClassObjectMeta'`) → return `None`. Only the `ClassObjectMeta` record holds
   a reference to a class meta schema.
2. Reassign `class_name` / `object_id` based on `object_id`:
   - If `object_id == BaseClasses.CLASS_OBJECT` (i.e. equals `'ClassObject'`):
     - `class_name = BaseClasses.OBJECT.value` → `'Object'`.
     - `object_id = BaseClasses.CLASS_OBJECT.value` → `'ClassObject'` (normalizes
       an enum-valued `object_id` to its plain string).
   - Else:
     - `class_name = BaseClasses.CLASS_OBJECT.value` → `'ClassObject'`.
     - `object_id` is left unchanged.
3. Return `build_reference(...)` with keyword arguments:
   - `class_name = class_name` (the reassigned value: `'Object'` or
     `'ClassObject'`)
   - `class_version = Versions.LATEST`
   - `object_id = object_id`
   - `object_version = Versions.LATEST`

Return type: `Reference | None`. No exceptions raised by this function.

---

### `get_custom_properties(model: type[ModelBase]) -> set[str]`

Collects the names of all "custom" (public, non-private) Python `property`
descriptors declared anywhere in a model's MRO above `ModelBase`.

State / accumulator:
- `properties: set[str] = set()` — empty set, populated and returned.

Step-by-step:

1. Iterate `_class` over `model.mro()` (method resolution order, most-derived
   first).
2. For each `_class`:
   - If `_class is ModelBase` → `break` immediately. `ModelBase` and everything
     after it in the MRO are **not** inspected (its own properties and base
     framework properties are excluded).
   - Otherwise iterate `name, value` over `vars(_class).items()` (the class's
     own `__dict__`, not inherited entries — inheritance is handled by walking
     the MRO).
     - If `isinstance(value, property)` **AND** `not isinstance(value, PrivateProperty)`:
       - `properties.add(name)`.
3. Return `properties`.

Edge cases:
- A property overridden in several MRO classes is added once (set semantics).
- `PrivateProperty` is a `property` subclass, so the second condition filters
  out private properties while the first still matches plain `property`
  instances.
- If `ModelBase` is not in the MRO (unexpected), the loop runs to completion.

---

### `is_partial_model(model_class: type[Any]) -> bool`

Detects whether a class object is a `pydantic_partial`-generated partial model.

Behavior: returns `model_class.__module__ == 'pydantic_partial.partial'`
(`== _PARTIAL_MODEL_MODULE`). True only when the class's `__module__` exactly
equals that string. No side effects.

---

### `is_partial_namespace(namespace: Mapping[str, Any]) -> bool`

Same detection as `is_partial_model`, but operates on the *class-construction
namespace mapping* rather than an already-built class. Intended for use inside
the model metaclass `__new__`, before the class object exists.

Behavior: returns `namespace.get('__module__') == 'pydantic_partial.partial'`.
Uses `.get`, so a namespace lacking a `'__module__'` key yields `None`, which is
not equal to the constant → returns `False`. No side effects.

---

### `object_id_to_internal(object_id: Any) -> Any`

Normalizes a list-wrapped single-element object id down to the bare value;
mirrors the same unwrapping that `build_reference` performs internally.

Step-by-step:

1. If `isinstance(object_id, list)` **AND** `len(object_id) == 1` → return
   `object_id[0]`.
2. Otherwise → return `object_id` unchanged.

Edge cases: empty lists, lists with 2+ elements, and non-list values are all
returned unchanged. No side effects, no exceptions.
