# `amsdal_models.classes.constants`

This module defines module-level constants used throughout the AMSDAL models package. It contains no classes, methods, or functions — only constant values. However, since the developer must be able to reason about behavior without seeing the source, every constant's exact value, structure, and intended consumers are documented below.

## Module Imports

The module pulls in the following symbols at import time:

- `date` from `datetime`
- `datetime` from `datetime`
- `Any` from `typing`
- `CoreTypes` (enum) from `amsdal_utils.models.data_models.enums`
- `CoreModules` (enum) from `amsdal_models.classes.enums`
- `SystemModules` (enum) from `amsdal_models.classes.enums`

If any of these imports fail, the entire `amsdal_models.classes.constants` module fails to import, which cascades to every consumer of these constants.

## Constants

### `BASE_OBJECT_TYPE`

- **Type:** `str`
- **Value:** `'object'`
- **Purpose:** The canonical string identifier for the root/base object type in AMSDAL's type system. Used as the default or fallback type name when a model has no explicit parent type, and as a sentinel when checking whether a type is the root of the class hierarchy.
- **Debugging note:** If class resolution logic checks `type_name == 'object'`, it is comparing against this constant. Any change to this value would break class hierarchy resolution.

### `BASIC_TYPES_MAP`

- **Type:** `dict[CoreTypes, type | typing.Any]`
- **Purpose:** Maps AMSDAL's abstract `CoreTypes` enum members to concrete Python types. Used by model builders, validators, and serializers to translate schema type declarations into runtime Python types for field annotation, coercion, and validation.
- **Exact entries (in declaration order):**
  - `CoreTypes.NUMBER` → `float`
  - `CoreTypes.INTEGER` → `int`
  - `CoreTypes.STRING` → `str`
  - `CoreTypes.BOOLEAN` → `bool`
  - `CoreTypes.DICTIONARY` → `dict`
  - `CoreTypes.ARRAY` → `list`
  - `CoreTypes.ANYTHING` → `typing.Any` (special form, not a real type)
  - `CoreTypes.BINARY` → `bytes`
  - `CoreTypes.DATE` → `datetime.date`
  - `CoreTypes.DATETIME` → `datetime.datetime`
- **Edge cases:**
  - `CoreTypes.ANYTHING` maps to `typing.Any`, which is **not** a runtime-instantiable type. Code that attempts `isinstance(value, BASIC_TYPES_MAP[CoreTypes.ANYTHING])` will raise `TypeError` because `Any` is a special typing form.
  - `CoreTypes.NUMBER` maps to `float` (not `Decimal` or `int | float`). Integer-valued JSON numbers will be coerced to `float` when this mapping is used.
  - Lookups for any `CoreTypes` member not listed here (e.g., custom or future enum values) raise `KeyError`.

### Model-module category constants

These four strings are used as categorization labels for models, typically to distinguish where a model originated (framework-provided vs. user-defined vs. type-system metadata). They appear in schema loaders, class resolution, and migration logic.

- **`CORE_MODELS_MODULE`** — `str` — value `'core'`. Label for framework-core models.
- **`CONTRIB_MODELS_MODULE`** — `str` — value `'contrib'`. Label for contrib/optional bundled models.
- **`USER_MODELS_MODULE`** — `str` — value `'user'`. Label for application-defined models.
- **`TYPE_MODELS_MODULE`** — `str` — value `'type'`. Label for type-system metadata models.

**Debugging note:** These four strings are frequently used as dict keys or directory names. A mismatch in casing or pluralization (e.g., `'users'` vs `'user'`) when consuming these constants will silently miss all models in that category.

### `IMPORT_MAP`

- **Type:** `dict[str, tuple[str, str]]`
- **Purpose:** Lookup table used by the code generator / class builder when emitting `from X import Y` statements in generated Python modules. Given the string value of a `SystemModules` or `CoreModules` enum member, returns a 2-tuple `(module_path, symbol_name)` from which that symbol should be imported.
- **Key type:** `str` — specifically the `.value` of an enum member, NOT the enum member itself. Callers must do `IMPORT_MAP[SystemModules.ANY.value]`, not `IMPORT_MAP[SystemModules.ANY]`.
- **Value type:** `tuple[str, str]` where index `0` is the fully-qualified module path and index `1` is the symbol name to import.
- **Exact entries (in declaration order):**
  - `SystemModules.ANY.value` → `('typing', 'Any')`
  - `SystemModules.OPTIONAL.value` → `('typing', 'Optional')`
  - `SystemModules.UNION.value` → `('typing', 'Union')`
  - `SystemModules.CLASS_VAR.value` → `('typing', 'ClassVar')`
  - `SystemModules.FIELD_VALIDATOR.value` → `('pydantic.functional_validators', 'field_validator')`
  - `SystemModules.FIELD_DICTIONARY_VALIDATOR.value` → `('amsdal_models.classes.builder.validators.dict_validators', 'validate_non_empty_keys')`
  - `SystemModules.FIELD_OPTIONS_VALIDATOR.value` → `('amsdal_models.classes.builder.validators.options_validators', 'validate_options')`
  - `SystemModules.DATE.value` → `('datetime', 'date')`
  - `SystemModules.DATETIME.value` → `('datetime', 'datetime')`
  - `CoreModules.REFERENCE.value` → `('amsdal_utils.models.data_models.reference', 'Reference')`
- **Edge cases and debugging notes:**
  - This map mixes keys derived from two different enums (`SystemModules` and `CoreModules`). If both enums ever declare a member with the same `.value`, the later declaration (`CoreModules.REFERENCE`) would overwrite the earlier one.
  - The map is not exhaustive over `SystemModules`/`CoreModules`. Lookups for enum values not listed (e.g., hypothetical `SystemModules.LIST` or other `CoreModules` members) raise `KeyError`.
  - The dict validator is specifically `validate_non_empty_keys` — it does not validate values, only that dict keys are non-empty. Bugs where empty-string keys survive validation point to this validator not being wired up.
  - The options validator is `validate_options` from `options_validators` — used for enum/choice-style fields.
  - `Optional` and `Union` are imported from `typing` (not `types`), so generated code targets the classic typing forms rather than PEP 604 `X | None` syntax.
  - `field_validator` comes from `pydantic.functional_validators` (Pydantic v2 path). Generated code is Pydantic-v2-specific; Pydantic v1 environments will fail to import.

### `FILE_CLASS_NAME`

- **Type:** `str`
- **Value:** `'File'`
- **Purpose:** The well-known class name used to identify file-type models. Code elsewhere checks `class_name == 'File'` (or uses this constant) to branch into file-specific handling such as binary storage, upload routing, or file serialization.
- **Debugging note:** If a user-defined model is named `File`, it may collide with framework logic that assumes this name refers to the framework's built-in file class. Case is significant — `'file'` or `'FILE'` will not match.

### `REFERENCE_FIELD_SUFFIX`

- **Type:** `str`
- **Value:** `'_reference'`
- **Purpose:** Suffix appended to a foreign-key / reference field's base name to produce the name of the companion field that holds the actual `Reference` object (as opposed to the resolved target model). For example, a field `author` on a model will have an associated `author_reference` field when serialized/stored.
- **Debugging note:** Field-name collisions occur if a user declares a field whose name already ends in `_reference` — the generated companion field would then be e.g. `author_reference_reference`. Serializers that strip or append this suffix by string manipulation (rather than field-metadata inspection) are a common source of bugs here.

### `PARTIAL_CLASS_NAME_SUFFIX`

- **Type:** `str`
- **Value:** `'Partial'`
- **Purpose:** Suffix appended to a model class's name to derive the name of its "partial" variant — a generated companion class where all fields are optional, typically used for PATCH-style updates or partial deserialization. For example, model `User` has a partial variant named `UserPartial`.
- **Debugging note:** Class lookup that concatenates `class_name + 'Partial'` depends on this exact value. If a user declares a model whose name ends in `Partial`, its generated partial variant will be named `XPartialPartial`, which can confuse registries keyed by class name.

## Module-level behavior

- The module executes all assignments exactly once at import time. There are no functions, classes, lazy initializers, or `__getattr__` hooks — every constant is a plain module attribute, resolvable via `getattr(amsdal_models.classes.constants, name)`.
- All constants are mutable container objects (`dict`) or immutable primitives (`str`, `tuple`). The two dicts (`BASIC_TYPES_MAP`, `IMPORT_MAP`) are **not frozen**; any consumer can mutate them at runtime, which would globally affect all subsequent lookups. This is a known footgun — accidental mutation is a realistic source of cross-module bugs.
- There is no runtime validation that `SystemModules`/`CoreModules` enum values used as keys in `IMPORT_MAP` actually exist in their respective enums beyond the standard attribute access at module-load time. A rename of any enum member's `.value` string without updating this file would silently break imports downstream (the key lookup would raise `KeyError` at code-generation time, not at import time).
