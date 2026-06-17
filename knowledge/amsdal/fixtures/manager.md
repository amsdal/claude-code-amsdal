# `amsdal.fixtures.manager`

Loads fixture definitions from JSON/CSV files (or directory trees), and applies them to the AMSDAL database as versioned `Fixture`, `File`, and arbitrary model objects.

## Module-level imports and globals

- `copy`, `json`, `logging`, `uuid` (stdlib); `Generator` from `collections.abc`; `Path` from `pathlib`; `Any` from `typing`.
- `numpy as np`, `pandas as pd` (used for CSV loading).
- `Model` from `amsdal_models.classes.model`.
- `MANY_TO_MANY_FIELDS` from `amsdal_models.classes.relationships.constants` — a string attribute-name constant used with `getattr` to read a model's M2M field map.
- `get_class_manager` from `amsdal_models.contexts` — returns the class manager used to import model classes by name.
- `AmsdalConfigManager` from `amsdal_utils.config.manager`.
- `Versions` from `amsdal_utils.models.enums` — uses `Versions.LATEST`.
- `defaultdict` is imported from `black.trans` (re-exported there; behaves as the stdlib `collections.defaultdict`).
- `BaseModel` from `pydantic`; `FieldInfo` from `pydantic.fields`.
- `process_fixture_value` from `amsdal.fixtures.utils` (see "External helper" section below).
- `logger = logging.getLogger(__name__)`.

---

## `FixtureData` (pydantic `BaseModel`)

Value object describing one fixture record. Fields (all required, no defaults):

- `class_name: str` — name of the target model class.
- `external_id: str` — external identifier used as the object id / lookup key.
- `order: float` — ordering weight used when applying fixtures.
- `data: dict[str, Any]` — the fixture payload (field values).

---

## `BaseFixturesManager`

Base class holding loading logic and shared state. Subclassed by `FixturesManager` (sync) and `AsyncFixturesManager` (async); the apply logic differs only in sync vs async DB calls.

### Class attributes

- `ORDER_MULTIPLIER: int = 10` — per-path order offset multiplier.
- `MAX_FIXTURE_DEPTH: int = 10` — maximum directory recursion depth.

### `__init__(self, fixtures_paths: list[Path]) -> None`

Instance state set:

- `self.fixtures_paths = fixtures_paths` — list of `Path` roots to load from.
- `self.fixtures: dict[str | int, list[tuple[float, FixtureData]]] = defaultdict(list)` — maps an `external_id` key to a list of `(order_value, FixtureData)` tuples. A `defaultdict(list)`, so unknown keys auto-create an empty list.
- `self._class_manager = get_class_manager()`.
- `self._config_manager = AmsdalConfigManager()` (constructed but not referenced elsewhere in this class).

### `load_fixtures(self) -> None`

Iterates `enumerate(self.fixtures_paths)`. For each `(idx, fixtures_path)` calls `self._load_fixtures(fixtures_path, order_shift=self.ORDER_MULTIPLIER * idx)`. So path 0 gets shift 0, path 1 gets shift 10, path 2 gets shift 20, etc. Returns `None`.

### `_load_fixtures(self, fixtures_path: Path, order_shift: int = 0) -> None`

1. If `not fixtures_path.exists()`: return immediately (no error).
2. Initialize local `fixtures: list[dict[str, Any]] = []`.
3. Branch on path type:
   - If `fixtures_path.is_dir()`: call `self._load_fixtures_recursive(fixtures_path, fixtures, order_shift, depth=0, max_depth=self.MAX_FIXTURE_DEPTH)` to populate `fixtures`.
   - Else (a file): open it, `json.load`. If the parsed value is `not isinstance(..., dict)`, raise `ValueError('Fixture data must be a dictionary')`. Otherwise append the dict to `fixtures`.
4. Iterate each `fixture` dict in `fixtures`:
   - Compute `group_order`: `if group_order := fixture.get('order'):` — i.e. only if `fixture['order']` is truthy. When truthy, `group_order += order_shift`. NOTE: `'order'` is treated as a top-level key of the fixture dict and is *also* iterated as a class name below (it is not removed).
   - For each `class_name` in `fixture` (every top-level key):
     - For each `fixture_element` in `fixture[class_name]` (expects a list of dicts):
       - `external_id = fixture_element.pop('_external_id', None)`.
       - `order = fixture_element.pop('_order', 0) + order_shift`.
       - If `not external_id and 'external_id' in fixture_element`: `external_id = fixture_element.pop('external_id')` (fallback to a public `external_id` key, also removing it from the element).
       - Build `fixture_data = FixtureData(class_name=class_name, external_id=external_id, order=order, data=fixture_element)`. (`fixture_element` is the remaining dict after the pops.)
       - Append to `self.fixtures[external_id]` the tuple `(group_order or order or 0, fixture_data)` — the order value is the first truthy of `group_order`, then `order`, else `0`.

Edge cases: if `external_id` is `None`/`''`, the tuple is stored under that key; multiple records sharing the key accumulate in one list. Because `'order'` is iterated as a class name, a fixture file with a top-level `"order"` numeric value will attempt `for fixture_element in <number>` and fail with a `TypeError` (numbers are not iterable). Top-level `order` is intended for grouping, but the code does not skip it.

### `_load_fixtures_recursive(self, current_path, fixtures, order_shift, depth=0, max_depth=10) -> None`

Recursively walks a directory tree, supporting two layouts:
- Pattern A: a folder named after a class, containing CSV files and/or JSON files whose top-level value is a **list**.
- Pattern B: a standalone `.json` file whose top-level value is a **dict** mapping class names to record lists.

Steps:

1. If `depth >= max_depth`: log warning `'Max fixture nesting depth %s reached at %s, skipping deeper levels'` (args `max_depth`, `current_path`) and return.
2. `items = list(current_path.iterdir())`, wrapped in try/except `OSError as e`; on error log `'Cannot access directory %s: %s'` (`current_path`, `e`) and return.
3. For each `item` in `items`:
   - If `item.is_dir()`:
     - List `dir_contents = list(item.iterdir())` in try/except `OSError`; on error log `'Cannot access directory %s: %s'` (`item`, `e`) and `continue`.
     - `has_csv_files = any(f.suffix == '.csv' and f.is_file() for f in dir_contents)`.
     - `has_json_list_files = False`; then for each `f` in `dir_contents`: if `f.is_file()` and `f.suffix == '.json'`, open and `json.load`; if the result `isinstance(data, list)`, set `has_json_list_files = True` and `break`. JSON load errors (`OSError`, `json.JSONDecodeError`) are caught and the file is skipped (`continue`).
     - If `has_csv_files or has_json_list_files`: treat `item` as a class folder (Pattern A) and call `self._load_class_folder_fixtures(item, fixtures)` (wrapped in try/except `OSError` → log `'Cannot access directory %s: %s'` and `continue`). The folder name is assumed to be the class name without verification.
     - Else: recurse via `self._load_fixtures_recursive(item, fixtures, order_shift, depth + 1, max_depth)` (treated as a container directory).
   - Elif `item.is_file() and item.suffix == '.json'` (Pattern B): call `self._load_explicit_class_fixture(item, fixtures)`, wrapped in:
     - except `OSError as e`: log `'Cannot read file %s: %s'` (`item`, `e`), `continue`.
     - except `(json.JSONDecodeError, ValueError) as e`: log `'Invalid JSON in file %s: %s'` (`item`, `e`), `continue`.

Note: `order_shift` is threaded through recursion but is not applied here; ordering is applied later in `_load_fixtures`.

### `_load_class_folder_fixtures(self, class_dir: Path, fixtures: list[dict[str, Any]]) -> None`

Loads all fixture files from one class-named directory (Pattern A). For each `model_file` in `class_dir.iterdir()`:

- If `model_file.suffix == '.json'`:
  - Open, `json.load`. If `not isinstance(_fixture_data, list)`: raise `ValueError(f'Fixture data in {model_file} must be a list')`.
  - Append `{class_dir.name: _fixture_data}` to `fixtures` (the folder name becomes the class name).
  - except `OSError as e`: log `'Cannot read file %s: %s'` (`model_file`, `e`), `continue`.
  - except `(json.JSONDecodeError, ValueError) as e`: log `'Invalid fixture in file %s: %s'` (`model_file`, `e`), `continue`. (The just-raised `ValueError` is caught here, so a non-list JSON is logged and skipped, not propagated.)
- Elif `model_file.suffix == '.csv'`:
  - Open and read via `pd.read_csv(csv_file).replace({np.nan: None}).to_dict(orient='records')` → list of row dicts with NaN replaced by `None`.
  - Append `{class_dir.name: _fixture_data}` to `fixtures`.
  - except `OSError as e`: log `'Cannot read file %s: %s'`, `continue`.
  - except `Exception as e` (broad): log `'Invalid CSV in file %s: %s'` (`model_file`, `e`), `continue`.
- Files with other suffixes are ignored.

### `_load_explicit_class_fixture(self, json_file: Path, fixtures: list[dict[str, Any]]) -> None`

Open `json_file`, `json.load`. If `not isinstance(_fixture_data, dict)`: raise `ValueError(f'Fixture data in {json_file} must be a dictionary')`. Otherwise append the dict to `fixtures`. (Caller wraps and logs exceptions.)

### `iter_fixtures(self) -> Generator[FixtureData, None, None]`

1. Flatten `self.fixtures` into `flattened_fixtures = [(order, data) for class_name, values in self.fixtures.items() for order, data in values]`.
2. `sorted_fixtures = sorted(flattened_fixtures, key=lambda x: x[0])` — ascending by the numeric order value.
3. Yield each `fixture` (the `FixtureData`) from the sorted list in order. Lower order applied first.

### `_process_object_data(self, data, model_fields, m2m_fields) -> dict[str, Any]`

Casts each raw fixture value to the field's declared type. Parameters: `data: dict[str, Any]`, `model_fields: dict[str, FieldInfo]`, `m2m_fields: dict[str, type[Model]]`.

1. Build `fields_by_alias = {(field_info.alias or name): field_info for name, field_info in model_fields.items()}` — maps each field's pydantic alias (or its name when no alias) to its `FieldInfo`. This handles foreign-key fields, which are stored internally as `_<fk>_ref` and exposed publicly only via the alias, so a fixture key like `object_control` is absent from `model_fields` keyed by name but present in `fields_by_alias`.
2. For each `key, value` in `data.items()`:
   - If `key in m2m_fields`: `_ref_type = m2m_fields[key]`; set `data[key] = process_fixture_value(list[_ref_type], value)` — treats the value as a list of references to the M2M target model.
   - Else: `field_info = model_fields.get(key) or fields_by_alias[key]` (lookup by name first, then by alias — a `KeyError` is raised if the key matches neither). Set `data[key] = process_fixture_value(field_info.annotation, value)`.
3. Mutates and returns `data` (same dict object, values replaced in place).

---

## `FixturesManager(BaseFixturesManager)` — synchronous

Loads (via base class) and applies fixtures using synchronous DB execution (`.execute()`, `.save()`).

### `apply_file_fixtures(self) -> None`

For each `_dir` in `self.fixtures_paths`: compute `files_dir = _dir / 'files'` and call `self._apply_file_fixtures(files_dir)`. So binary file fixtures live in a `files/` subdirectory of each fixtures path.

### `_apply_file_fixtures(self, file_dir: Path) -> None`

If `not (file_dir.exists() and file_dir.is_dir())`: return. Otherwise call `self._apply_file_fixtures_rec(file_dir, file_dir)` (base dir equals the start dir).

### `_apply_file_fixtures_rec(self, nested_dir: Path, base_dir: Path) -> None`

For each `nested_object` in `nested_dir.iterdir()`:
- If `nested_object.is_dir()`: recurse `self._apply_file_fixtures_rec(nested_object, base_dir)`, then `continue`.
- If `nested_object.is_file()`: call `self._process_file_fixture(nested_object, f'{nested_object.relative_to(base_dir)}')`. The `file_key` is the file path relative to `base_dir`, stringified (path string including subfolders).

No depth limit here (unlike the JSON loader).

### `_process_file_fixture(self, file_path: Path, file_key: str) -> None`

1. Local import: `from amsdal.models.core.file import File`.
2. Open `file_path` in `'rb'`, read all bytes into `file_data`; `filename = file_path.resolve().name`.
3. Build `data = {'filename': filename, 'data': file_data}`.
4. Query existing: `File.objects.filter(_address__object_id=file_key, _address__object_version=Versions.LATEST).first().execute()` → `existing_file: File | None`.
5. If `existing_file is not None`:
   - `new_file = File.from_bytes(**data)`.
   - If `new_file.data == existing_file.data`: log `'Skipping creating new version of file for file_key=%s, no changes found'` (`file_key`) and return (no write).
   - Else: log `'Creating new version of fixture for file_key=%s'` (`file_key`); set `existing_file.data = data['data']`; `existing_file.save()`.
6. Else (no existing file): log `'Creating first fixture for external_id=%s'` (`file_key`); `instance = File(_object_id=file_key, **data)`; `instance.save(force_insert=True)`.

Note the change-detection compares `new_file.data` to `existing_file.data` (the `File`'s processed `data` attribute), not the raw bytes directly.

### `apply_fixtures(self) -> None`

For each `fixture` from `self.iter_fixtures()` (order-sorted):
1. `fixture_data = self._process_fixture(fixture)`.
2. If `fixture_data` is truthy (not `None`): call `self._process_fixture_object_data(class_name=fixture_data.class_name, external_id=fixture_data.external_id, data=fixture_data.data)`.

So when `_process_fixture` returns `None` (unchanged fixture), the underlying object data is **not** re-applied.

### `_process_fixture(self, fixture: FixtureData) -> FixtureData | None`

Records the fixture itself as a versioned `Fixture` registry object, and returns a fresh copy for object application (or `None` if unchanged).

1. Local import: `from amsdal.models.core.fixture import Fixture`.
2. `external_id = fixture.external_id`.
3. Query: `Fixture.objects.filter(external_id=external_id, _address__object_version=Versions.LATEST).first().execute()` → `existing_fixture: Model | None`.
4. `class_name = fixture.class_name`.
5. If `existing_fixture is not None`:
   - If `fixture.data == existing_fixture.data`: log `'Skipping creating new version of fixture for external_id=%s, no changes found'` (`external_id`) and **return `None`**.
   - Else: log `'Creating new version of fixture for external_id=%s'` (`external_id`); set `existing_fixture.data = fixture.data`; `existing_fixture.save()`.
6. Else: log `'Creating first fixture for external_id=%s'` (`external_id`); create `Fixture(_object_id=uuid.uuid4().hex, external_id=external_id, data=fixture.data, class_name=class_name)`; `instance.save(force_insert=True)`. The `Fixture` object id is a random uuid4 hex (not the external id).
7. Return `FixtureData(external_id=external_id, class_name=class_name, data=copy.deepcopy(fixture.data), order=fixture.order)` — `data` is deep-copied so later mutation in `_process_object_data` does not affect the stored `Fixture.data`.

### `_process_fixture_object_data(self, class_name: str, external_id: str, data: dict[str, Any]) -> None`

Creates/updates the actual target model object.

1. `class_model = self._class_manager.import_class(class_name)`.
2. Query existing: `class_model.objects.filter(_address__object_id=external_id, _address__object_version=Versions.LATEST).first().execute()` → `existing_object: Model | None`.
3. `m2m_fields = getattr(class_model, MANY_TO_MANY_FIELDS, None) or {}` — a dict mapping field name → a tuple `(ref_type, _, _, _)` (4-tuple).
4. `updated_data = self._process_object_data(data, model_fields=class_model.model_fields or {}, m2m_fields={_field: _ref_type for _field, (_ref_type, _, _, _) in m2m_fields.items()})` — collapses each 4-tuple to just its first element (`_ref_type`).
5. `full_data = {**updated_data, '_object_id': external_id}`.
6. If `existing_object is not None`:
   - Log `'Creating new version of %s for external_id=%s'` (`class_model.__name__`, `external_id`).
   - For each `key, val` in `updated_data.items()`: `setattr(existing_object, key, val)` (note: `_object_id` is not set here, only the processed data fields).
   - `existing_object.save()`.
7. Else: log `'Creating %s for external_id=%s'` (`class_model.__name__`, `external_id`); `instance = class_model(**full_data)` (includes `_object_id`); `instance.save(force_insert=True)`.

---

## `AsyncFixturesManager(BaseFixturesManager)` — asynchronous

Behaviorally identical to `FixturesManager` except all DB operations are awaited. The loading methods (`load_fixtures`, `_load_*`, `iter_fixtures`, `_process_object_data`) are inherited unchanged from the base class. Differences in the apply path:

- `apply_file_fixtures` (async): same loop, `await self._apply_file_fixtures(files_dir)`.
- `_apply_file_fixtures` (async): same guard, `await self._apply_file_fixtures_rec(...)`.
- `_apply_file_fixtures_rec` (async): same traversal, `await` on recursive calls and on `self._process_file_fixture(...)`.
- `apply_fixtures` (async): `fixture_data = await self._process_fixture(fixture)`; if truthy, `await self._process_fixture_object_data(...)`.
- `_process_file_fixture` (async): same logic; existing lookup uses `.first().aexecute()`; updates use `await existing_file.asave()`; new file uses `await instance.asave(force_insert=True)`. Same log strings and the same `new_file.data == existing_file.data` skip check.
- `_process_fixture` (async): same logic and same log strings; lookup uses `.aexecute()`; `await existing_fixture.asave()` / `await instance.asave(force_insert=True)`. Returns `None` on unchanged data, else a deep-copied `FixtureData`.
- `_process_fixture_object_data` (async): same logic and log strings; lookup uses `.aexecute()`; `await existing_object.asave()` / `await instance.asave(force_insert=True)`.

All exact string constants, branch conditions, dict keys, and data shapes match the synchronous counterparts above.

---

## External helper: `process_fixture_value` (`amsdal.fixtures.utils`)

Referenced by `_process_object_data` to cast raw fixture values to typed values. Signature `process_fixture_value(annotation: Any, value: Any) -> Any`.

1. If `not annotation` (falsy/`None`): return `None`.
2. If `_is_optional(annotation)`: resolve the non-`None` member type via `_resolve_type_from_optional` and `return _cast_value_to_type(_type, value)`.
   - `_is_optional` returns `True` if `annotation._name == 'Optional'`, or if `annotation` is a `UnionType` with exactly 2 args one of which is `NoneType`.
3. Elif `isinstance(annotation, UnionType)` (PEP 604 `X | Y` that is not the optional case): raise `NotImplementedError('Union types are not supported in fixtures yet.')`.
4. Else `return _cast_value_to_type(annotation, value)`.

`_cast_value_to_type(value_type, value)` branches (in order):
- `value is None` → return `None`.
- `isinstance(value_type, GenericAlias)` (e.g. `dict[...]`, `list[...]`):
  - origin `dict`: if `value` falsy, return as-is; else build a new dict casting each key and value recursively.
  - origin `list`: if `value` is a `str`, split on `,` and strip each element; then cast each element recursively.
  - any other origin: raise `NotImplementedError(f'Type "{value_type}" is not supported in fixtures!')`.
- `typing._UnionGenericAlias` (e.g. `typing.Union[...]`): if it has 3 or 4 args, drop `LegacyModel`, `Reference`, and `NoneType`; if exactly one remains, recurse on it; otherwise raise `NotImplementedError('Union types are not supported in fixtures yet.')`. (This path handles AMSDAL FK annotations, which are unions of model/`Reference`/`LegacyModel`/`None`.)
- `typing._LiteralGenericAlias`: return `value` unchanged.
- `issubclass(value_type, Model)`: return `_construct_reference_value(class_name=value_type.__name__, object_id=value)` — builds a `Reference` with `ref` = `{class_name, class_version: Versions.LATEST, object_id: value, object_version: Versions.LATEST, resource: <connection name for the class>}`. This is how external-id strings become FK/M2M references.
- `issubclass(value_type, TypeModel) and isinstance(value, dict)`: construct `value_type(**value)`.
- `value_type in (int, float) and value == ''` → return `None`.
- `isinstance(value, str) and value_type in [date, datetime]` → `date.fromisoformat(value)` (note: always returns a `date`, even for a `datetime` annotation).
- `value_type is Any` → return `value`.
- `value_type is bytes and isinstance(value, str)` → `value.encode('utf-8')`.
- Fallback → `value_type(value)` (direct constructor call, e.g. `int(value)`, `str(value)`).
