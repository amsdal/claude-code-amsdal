# Module: `amsdal.fixtures.utils`

This module provides utilities for converting raw fixture values (typically loaded from YAML/JSON fixtures) into properly typed Python objects based on type annotations from model classes. It handles type coercion for primitives, collections, unions/optionals, literals, AMSDAL `Model` references, and nested `TypeModel` structures.

## Module-level imports and dependencies

- `datetime.date`, `datetime.datetime` — used for ISO date parsing.
- `types.GenericAlias` — used to detect parameterized generic types like `list[int]`, `dict[str, int]`.
- `types.NoneType` — used to identify `None` slots inside Union/Optional type args.
- `types.UnionType` — used to detect PEP 604 union syntax (e.g., `int | str`).
- `typing.Any`, `typing.Literal`, `typing.Optional`, `typing.Union` — used both as type hints and as runtime comparators.
- `amsdal_models.classes.model.LegacyModel` — a marker class filtered out of Union args before resolving a "single real type".
- `amsdal_utils.models.data_models.reference.Reference` — also filtered out of Union args; used as the target structure when converting model references.
- `amsdal_models.classes.model.Model` and `TypeModel` — imported lazily inside `_cast_value_to_type` to avoid top-level circular imports.
- `amsdal_utils.config.manager.AmsdalConfigManager` and `amsdal_utils.models.enums.Versions` — imported lazily inside `_construct_reference_value`.

---

### `process_fixture_value(annotation: Any, value: Any) -> Any`

**Purpose:** Top-level entry point. Converts a raw fixture `value` into the correct Python type based on the provided `annotation`.

**Step-by-step behavior:**

1. **Falsy annotation guard.** If `annotation` is falsy (evaluates to `False` under `not annotation`) — e.g., `None`, empty string, `0` — the function returns `None` immediately, regardless of `value`.
   - Note: this uses `not annotation`, not `annotation is None`, so any annotation whose truthiness is `False` short-circuits.
2. **Optional handling.** Calls `_is_optional(annotation)`. If it returns `True`:
   - Extracts the non-`NoneType` argument via `_resolve_type_from_optional(annotation)`.
   - Recursively delegates to `_cast_value_to_type(_type, value)` and returns the result.
   - This means `Optional[X]` and `X | None` are unwrapped to `X` before casting, but `None` values pass through via `_cast_value_to_type`'s own `None` guard.
3. **Non-optional `UnionType` rejection.** If `annotation` is a `UnionType` (PEP 604 `X | Y` syntax) and it was *not* detected as Optional, raises `NotImplementedError` with the exact message: `'Union types are not supported in fixtures yet.'`
4. **Default path.** Otherwise delegates to `_cast_value_to_type(annotation, value)` and returns the result.

**Edge cases:**
- An empty string as annotation returns `None` (falsy short-circuit).
- A `UnionType` with exactly 2 args where one is `NoneType` is Optional → allowed.
- A `UnionType` with 3+ args, or 2 args neither of which is `NoneType`, hits the `NotImplementedError`.

---

### `_cast_value_to_type(value_type: type | GenericAlias, value: Any) -> Any`

**Purpose:** Core type coercion dispatcher. Matches `value_type` against a fixed series of cases in order and converts `value` accordingly.

**Step-by-step behavior (order matters — first matching branch wins):**

1. **Lazy import.** Imports `Model` and `TypeModel` from `amsdal_models.classes.model` inside the function body.
2. **`None` value guard.** If `value is None`, returns `None` immediately without touching `value_type`.
3. **`GenericAlias` branch** (e.g., `list[int]`, `dict[str, int]`): reads `value_type.__origin__`.
   - **If `_origin is dict`:**
     - If `value` is falsy (empty dict, `None` already handled above, empty string, `0`), returns `value` unchanged (no conversion performed).
     - Otherwise unpacks the two args: `_key_type, _value_type = value_type.__args__`.
     - Builds a new empty dict `_value = {}`.
     - Iterates `value.items()`, and for each `(_key, _val)` pair calls `process_fixture_value(_key_type, _key)` for the key and `process_fixture_value(_value_type, _val)` for the value, assigning them into `_value`.
     - Returns the rebuilt dict.
     - **Warning:** if two different keys map to the same processed key, the later pair overwrites the earlier.
   - **If `_origin is list`:**
     - If `value` is a `str`, splits it by `,` and strips whitespace from each element (`map(str.strip, value.split(','))`); the mapped iterator replaces `value`.
     - Unpacks a single arg: `(_value_type,) = value_type.__args__` (will raise `ValueError` at unpacking time if the list type has not exactly 1 type argument).
     - Returns a list comprehension `[process_fixture_value(_value_type, _val) for _val in value]`.
   - **Any other origin** (tuple, set, frozenset, etc.): raises `NotImplementedError` with the message: `f'Type "{value_type}" is not supported in fixtures!'` (the f-string embeds the repr of `value_type`, e.g., `'Type "tuple[int, int]" is not supported in fixtures!'`).
4. **`typing.Union` branch** — detected via `isinstance(value_type, type(Union[str | int]))`, i.e., checking against `typing._UnionGenericAlias`:
   - Only accepts unions with 3 or 4 args (`len(value_type.__args__) in [3, 4]`).
   - Filters out `LegacyModel`, `Reference`, and `NoneType` from `__args__`.
   - If exactly one arg remains after filtering, recurses with `process_fixture_value(args[0], value)`.
   - Otherwise raises `NotImplementedError` with: `'Union types are not supported in fixtures yet.'`
   - **Note:** this branch is specifically designed to handle AMSDAL's idiomatic model references, where a model field is typed as something like `Union[MyModel, LegacyModel, Reference]` or `Union[MyModel, LegacyModel, Reference, None]`. The "real" type `MyModel` is extracted and recursed on.
5. **`typing.Literal` branch** — detected via `isinstance(value_type, type(Literal[1, 2]))`, i.e., checking against `typing._LiteralGenericAlias`:
   - Returns `value` unchanged. No validation is performed against the allowed literal values.
6. **`Model` subclass branch** — `issubclass(value_type, Model)`:
   - Returns `_construct_reference_value(class_name=value_type.__name__, object_id=value)`.
   - The raw `value` is treated as the object id for the referenced model instance.
7. **`TypeModel` subclass branch** — `issubclass(value_type, TypeModel) and isinstance(value, dict)`:
   - Instantiates `value_type(**value)`, using the dict as keyword arguments.
   - If `value` is a `TypeModel` type but `value` is not a dict, this branch is skipped and execution falls through to later branches.
8. **Numeric empty-string coercion** — `value_type in (int, float) and value == ''`:
   - Returns `None`. Note this only applies when the expected type is `int` or `float` and the raw string is empty. Empty strings for other numeric-like types (e.g. `Decimal`) are *not* converted here.
9. **ISO date/datetime parsing** — `isinstance(value, str) and value_type in [date, datetime]`:
   - Returns `date.fromisoformat(value)` for **both** `date` and `datetime` annotations.
   - **Bug-worthy detail:** even when the annotation is `datetime`, this calls `date.fromisoformat`, not `datetime.fromisoformat`. So a `datetime` field populated from a string always yields a `date`, dropping any time component.
10. **`Any` passthrough** — `value_type is Any`: returns `value` unchanged.
11. **`bytes` from `str`** — `value_type is bytes and isinstance(value, str)`: returns `value.encode('utf-8')`.
12. **Default fallthrough.** Calls `value_type(value)` and returns the result.
   - This is how plain primitives (`int('42')`, `str(5)`, `bool(1)`, etc.) and any other user class with a one-arg constructor get constructed.
   - Any exception raised by the constructor propagates to the caller unchanged.

**Ordering consequences:**
- `Literal` is matched before `Model`/`TypeModel`, so a literal annotation never attempts subclass checks.
- The numeric empty-string rule runs *after* the Union/Literal/Model branches but *before* the date branch, so `int('')` never calls the default constructor.
- `Any` is matched *after* date parsing, so `value_type=Any` with a string value still falls through to the `Any` passthrough (no date parsing occurs because `Any in [date, datetime]` is `False`).

---

### `_is_optional(annotation: Any) -> bool`

**Purpose:** Determines whether an annotation represents an Optional (i.e., `X | None`).

**Step-by-step behavior:**

1. Reads `annotation._name` via `getattr(..., '_name', '')`. If it equals `Optional.__name__` (the literal string `'Optional'`), returns `True`.
   - This catches `typing.Optional[X]` expressed as `Union[X, None]` via the `typing` module, which sets `_name = 'Optional'` on the generic alias.
2. If `annotation` is a `UnionType` (PEP 604 `X | None` syntax):
   - Reads `__args__` via `getattr(..., '__args__', [])`.
   - Returns `True` iff the tuple has exactly 2 elements **and** any of them is `NoneType`.
3. Otherwise returns `False`.

**Edge case:** A `typing.Union[X, Y, None]` with 3+ args will *not* be considered Optional by this function even though it technically permits `None`.

---

### `_resolve_type_from_optional(annotation: Any) -> Any`

**Purpose:** Extracts the first non-`NoneType` argument from an Optional annotation's `__args__`.

**Behavior:** Returns `next(item for item in annotation.__args__ if item is not NoneType)`. If there are multiple non-`None` args (which `_is_optional` would have rejected), the first one wins. If `__args__` doesn't exist, `getattr(..., '__args__', [])` returns `[]` and `next(...)` raises `StopIteration`.

---

### `_construct_reference_value(class_name: str, object_id: Any) -> Reference`

**Purpose:** Builds an AMSDAL `Reference` object pointing to an instance of a model class by id.

**Step-by-step behavior:**

1. Lazily imports `AmsdalConfigManager` from `amsdal_utils.config.manager` and `Versions` from `amsdal_utils.models.enums`.
2. Instantiates `AmsdalConfigManager()` and binds it to `_config_manager`. Because `AmsdalConfigManager` is typically a singleton in AMSDAL, this returns the already-initialized manager; if it has not been configured yet, downstream calls may fail.
3. Calls `_config_manager.get_connection_name_by_model_name(class_name)` to resolve which backend connection stores this model class; the returned value is used as the `resource` field.
4. Constructs and returns a `Reference` initialized from a single kwarg dict `{'ref': {...}}` with the following **exact** keys and values under `ref`:
   - `'class_name'` → the `class_name` argument (the Python class `__name__`, not a fully-qualified dotted path).
   - `'class_version'` → `Versions.LATEST` (enum member, always resolves to the most recent class version at runtime, not at fixture load time).
   - `'object_id'` → the `object_id` argument, passed through untransformed. Can be any JSON-serializable value (str, int, list, dict) depending on how the target model's primary key is structured.
   - `'object_version'` → `Versions.LATEST`.
   - `'resource'` → the connection name resolved from the config manager.
5. Returns the constructed `Reference`.

**Side effects:** Touches the global `AmsdalConfigManager` singleton and therefore depends on AMSDAL configuration being initialized before fixtures are loaded. If the class name is unknown to the config manager, the underlying call may raise (e.g., `KeyError` or an AMSDAL-specific error depending on config manager implementation).

**Note for debugging:** Both `class_version` and `object_version` are hard-coded to `Versions.LATEST`. Fixtures cannot target a specific historical version through this utility — if you need a pinned version, the reference must be constructed elsewhere.

---

## Common failure modes and debugging notes

- **`NotImplementedError: 'Union types are not supported in fixtures yet.'`** — the annotation is a Union not matching AMSDAL's 3/4-arg `{Model, LegacyModel, Reference[, None]}` pattern, or a PEP 604 `A | B` with neither being `NoneType`.
- **`NotImplementedError: 'Type "X" is not supported in fixtures!'`** — the annotation is a parameterized generic whose origin is neither `dict` nor `list` (e.g., `tuple`, `set`, `frozenset`).
- **`ValueError` during unpacking** — a `list[...]` annotation with zero or multiple type args; failure occurs at `(_value_type,) = value_type.__args__`.
- **`StopIteration`** — `_resolve_type_from_optional` called on an annotation without `__args__` or without any non-`None` member.
- **Silent coercion surprises:**
  - `datetime` fields are parsed with `date.fromisoformat`, so time components are lost.
  - `Literal[...]` accepts any value without validation.
  - Empty dict/list/str/0 with a `dict[...]` annotation returns the raw value unchanged (skipping key/value conversion).
  - A `list[...]` annotation with a string value is split on commas — so a string containing a comma will always be split, even if the intended value was a single element containing `,`.
  - For `Model` subclass annotations, the raw `value` is always treated as `object_id`; no validation that the referenced object exists is performed.
