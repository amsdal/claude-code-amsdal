# Module: `amsdal_models.classes.enums`

This module defines three string enumerations used across the AMSDAL models layer to identify core module names, well-known system type/validator names, and the kind of model represented by a schema.

## Imports and external dependencies

- `Enum` from the standard library `enum` module — base class for all enumerations defined here.
- `MetaClasses` from `amsdal_utils.models.data_models.enums` — enum used in `ModelType.from_schema` to compare against `schema.meta_class`. Only the member `MetaClasses.TYPE` is referenced.
- `ObjectSchema` from `amsdal_utils.schemas.schema` — the schema type accepted by `ModelType.from_schema`. The classmethod reads the attribute `meta_class` on instances of this type.

All three classes inherit from `(str, Enum)`, meaning each member is simultaneously an `Enum` instance and a real `str`. Comparisons such as `CoreModules.REFERENCE == 'Reference'` evaluate to `True`, and the values can be passed directly anywhere a plain string is expected (JSON serialization, dictionary keys, `str.format`, etc.).

---

## Class: `CoreModules`

### Purpose
Enumerates names of "core" AMSDAL modules — modules that the framework treats specially. Currently it defines a single member used to refer to the `Reference` core module by its canonical string name.

### State / Members
The class has exactly one member; no other state is managed.

| Member | Value (str) |
|---|---|
| `REFERENCE` | `'Reference'` |

### Lifecycle
Pure enumeration — no instances are constructed at runtime beyond the singleton members created when the class is first imported. There are no methods, classmethods, or staticmethods on this class.

### Behavior notes for debuggers
- `CoreModules.REFERENCE.value` is the literal string `'Reference'` (capitalized R, no whitespace, no namespace prefix).
- Because the class inherits from `str`, `CoreModules.REFERENCE == 'Reference'` is `True` and `isinstance(CoreModules.REFERENCE, str)` is `True`.
- Iterating `CoreModules` yields exactly one member.
- Looking up an unknown name (e.g. `CoreModules('Other')` or `CoreModules['OTHER']`) raises `ValueError` / `KeyError` per the standard `Enum` contract — no custom `_missing_` hook is defined.

---

## Class: `SystemModules`

### Purpose
Enumerates the canonical string names of "system" identifiers that AMSDAL emits or recognizes when generating / interpreting model code. The set is a mix of typing constructs (`dict`, `list`, `Any`, `type`, `Optional`, `Union`, `ClassVar`), Pydantic-style validator decorator/function names (`field_validator`, `validate_non_empty_keys`, `validate_options`), and date/time type names (`date`, `datetime`). These strings are used as identifiers in generated source, schema metadata, and lookup tables — so the exact spelling and casing matter.

### State / Members
The class manages exactly the following members; no other instance or class attributes are assigned. Each value is a literal string that exactly matches its intended Python-level identifier (case-sensitive).

| Member | Value (str) | Refers to |
|---|---|---|
| `DICT` | `'dict'` | built-in `dict` type |
| `LIST` | `'list'` | built-in `list` type |
| `ANY` | `'Any'` | `typing.Any` |
| `TYPE` | `'type'` | built-in `type` |
| `OPTIONAL` | `'Optional'` | `typing.Optional` |
| `UNION` | `'Union'` | `typing.Union` |
| `CLASS_VAR` | `'ClassVar'` | `typing.ClassVar` |
| `FIELD_VALIDATOR` | `'field_validator'` | `pydantic.field_validator` decorator |
| `FIELD_DICTIONARY_VALIDATOR` | `'validate_non_empty_keys'` | name of a validator function used for dict fields |
| `FIELD_OPTIONS_VALIDATOR` | `'validate_options'` | name of a validator function used for option/choice fields |
| `DATE` | `'date'` | `datetime.date` |
| `DATETIME` | `'datetime'` | `datetime.datetime` |

### Lifecycle
Pure enumeration — no methods, classmethods, or staticmethods. Members are created once when the module is imported and never mutated.

### Behavior notes for debuggers
- Two members have a value that is *not* the lowercased member name: `FIELD_DICTIONARY_VALIDATOR` resolves to the string `'validate_non_empty_keys'` (not `'field_dictionary_validator'`) and `FIELD_OPTIONS_VALIDATOR` resolves to `'validate_options'` (not `'field_options_validator'`). Code that compares against these enums by string value must use the value strings shown above; comparing against the member name will silently mismatch.
- Casing of `ANY`, `OPTIONAL`, `UNION`, `CLASS_VAR` values is title-/Pascal-cased (`'Any'`, `'Optional'`, `'Union'`, `'ClassVar'`) because they correspond to `typing` symbols. The remaining values are lowercase. A case-sensitive comparison against the wrong casing (e.g. matching `'any'` instead of `'Any'`) will fail.
- `DICT` and `TYPE` collide with built-in names when used as bare strings; downstream code that emits these values into generated source will produce identifiers that shadow built-ins unless qualified.
- Membership lookup `SystemModules('Any')` returns `SystemModules.ANY`; `SystemModules('any')` raises `ValueError` because no `_missing_` hook normalizes case.
- Iteration order is the declaration order shown in the table above (Python `Enum` preserves declaration order).

---

## Class: `ModelType`

### Purpose
Distinguishes between the two kinds of model categories AMSDAL recognizes when interpreting an `ObjectSchema`: a *type* schema (a meta/type definition) versus a regular *model* schema. The class also provides a single classmethod that performs this categorization given an `ObjectSchema`.

### State / Members
Two members; no additional class- or instance-level state is held.

| Member | Value (str) |
|---|---|
| `TYPE` | `'type'` |
| `MODEL` | `'model'` |

Note that `ModelType.TYPE` shares the value string `'type'` with `SystemModules.TYPE`, but they are distinct objects from different enum classes. Equality between them holds only at the string level (`ModelType.TYPE == SystemModules.TYPE` evaluates to `True` because both `==` reduces to `'type' == 'type'`); however, identity comparison (`is`) and `isinstance` checks against the specific enum class will distinguish them.

### Lifecycle
Singleton members are created on import. The single classmethod below is the only callable; it does not mutate any state.

### Method: `from_schema`

#### Signature
```
@classmethod
def from_schema(cls, schema: ObjectSchema) -> 'ModelType'
```

#### Step-by-step behavior
1. The method receives one argument, `schema`, expected to be an `ObjectSchema` instance (imported from `amsdal_utils.schemas.schema`).
2. It accesses the attribute `schema.meta_class` directly. No `getattr` with a default is used — if `schema` does not have a `meta_class` attribute, an `AttributeError` propagates to the caller. No exception is caught or wrapped.
3. It compares `schema.meta_class` against `MetaClasses.TYPE` using the `==` operator (not `is`). Because `MetaClasses` is itself a string enum (per AMSDAL convention in `amsdal_utils.models.data_models.enums`), this comparison succeeds whenever `schema.meta_class` is either the enum member `MetaClasses.TYPE` or any string equal to its value.
4. Branching on the comparison result:
   - **If** `schema.meta_class == MetaClasses.TYPE` → returns `cls.TYPE`, i.e. the member `ModelType.TYPE` whose value is the string `'type'`.
   - **Else** (any other value of `meta_class`, including `None`, other `MetaClasses` members, or unrelated strings) → returns `cls.MODEL`, i.e. the member `ModelType.MODEL` whose value is the string `'model'`.
5. The implementation is a single conditional expression `cls.TYPE if schema.meta_class == MetaClasses.TYPE else cls.MODEL`. There is no logging, no validation of the input, and no caching; each call re-evaluates the comparison.

#### Side effects
None. The method is pure: it does not mutate `schema`, `cls`, or any module-level state, and it makes no I/O.

#### Edge cases / failure modes
- `schema is None` → `AttributeError: 'NoneType' object has no attribute 'meta_class'` propagates.
- `schema` lacks the `meta_class` attribute → `AttributeError` propagates with the standard CPython message format.
- `schema.meta_class` is a string equal to the value of `MetaClasses.TYPE` (rather than the enum member itself) → still classified as `ModelType.TYPE`, because `(str, Enum)` members compare equal to matching plain strings.
- `schema.meta_class` is any value not equal to `MetaClasses.TYPE` (including obviously incorrect values such as integers, `None`, or unrelated objects) → silently classified as `ModelType.MODEL`. The method does **not** raise on unrecognized meta classes; this is a common source of "everything looks like a MODEL" bugs when an upstream change introduces a new `MetaClasses` member.
- Because `cls` is bound to whichever class invoked the classmethod, calling `from_schema` on a subclass of `ModelType` (if one were to be defined) would return that subclass's `TYPE`/`MODEL` members rather than `ModelType`'s.

#### Interaction surface
- Reads `MetaClasses.TYPE` from `amsdal_utils.models.data_models.enums`. Any rename or value change of that member will silently flip the branch outcome.
- Reads `ObjectSchema.meta_class` from `amsdal_utils.schemas.schema`. Schema instances produced elsewhere in AMSDAL must populate this attribute for classification to work.
