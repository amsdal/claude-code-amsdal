# Module: `amsdal.fixtures.manager`

This module provides managers for loading, processing, and applying fixture data (data + binary files) to the AMSDAL database. It supports two I/O modes (sync `FixturesManager`, async `AsyncFixturesManager`) sharing a common loading base (`BaseFixturesManager`).

Module-level objects:
- `logger = logging.getLogger(__name__)` — used for all logging (namespace `amsdal.fixtures.manager`).
- Third-party imports of note: `numpy as np`, `pandas as pd` (used only for CSV loading), and — unusually — `from black.trans import defaultdict`. The `defaultdict` re-export from Black's internals is used to back `self.fixtures`. Functionally equivalent to `collections.defaultdict`, but a dependency on `black` must exist.
- Imports `process_fixture_value` from `amsdal.fixtures.utils`. Model imports (`File`, `Fixture`) are deferred inside methods to avoid import cycles.

---

## `FixtureData` (pydantic `BaseModel`)

A typed container describing a single, fully-parsed fixture record.

State (fields, all required unless noted):
- `class_name: str` — the AMSDAL model class name the fixture belongs to (e.g., `"Company"`).
- `external_id: str` — the stable logical identifier used for upserts and cross-references between fixtures. May be `None`/empty in edge cases (see `_load_fixtures`), even though typed `str`.
- `order: float` — sort key used by `iter_fixtures`. Lower values are applied first.
- `data: dict[str, Any]` — the remaining per-object attributes after `_external_id`, `_order`, and `external_id` have been popped out.

No custom validators, no lifecycle hooks.

---

## `BaseFixturesManager`

Responsible for reading fixtures from disk into memory, arranging them by order, and providing a per-object data-transform used by subclasses before persistence.

Class constants:
- `ORDER_MULTIPLIER: int = 10` — multiplier applied to the index of each path in `fixtures_paths`; defines the precedence window between different fixture roots.
- `MAX_FIXTURE_DEPTH: int = 10` — maximum depth for recursive directory traversal before the method bails out with a warning.

### `__init__(self, fixtures_paths: list[Path]) -> None`

Initializes in-memory state:
1. Stores the input list verbatim in `self.fixtures_paths: list[Path]`.
2. Creates `self.fixtures: dict[str | int, list[tuple[float, FixtureData]]] = defaultdict(list)` (imported from `black.trans`). Keyed by `external_id` (string/int/None), value is a list of `(order, FixtureData)` pairs.
3. Instantiates `self._class_manager = ClassManager()` (from `amsdal_models.classes.class_manager`) — used later to resolve class names to model classes.
4. Instantiates `self._config_manager = AmsdalConfigManager()` — held but not directly referenced by this class; available to subclasses/consumers.

### `load_fixtures(self) -> None`

Iterates `self.fixtures_paths` via `enumerate`, and for each `(idx, fixtures_path)` pair invokes `self._load_fixtures(fixtures_path, order_shift=self.ORDER_MULTIPLIER * idx)`. So the first path's order shift is `0`, the second `10`, the third `20`, etc. This means later paths are guaranteed to apply after earlier paths for any `order` less than `ORDER_MULTIPLIER`.

### `_load_fixtures(self, fixtures_path: Path, order_shift: int = 0) -> None`

Loads fixtures from a single path (file or directory).

Step-by-step:
1. If `fixtures_path.exists()` is `False`, returns immediately (silent).
2. Initializes local `fixtures: list[dict[str, Any]] = []`. Each element is a mapping `{class_name: [fixture_element, ...]}`.
3. Branching on path type:
   - If `fixtures_path.is_dir()`: calls `self._load_fixtures_recursive(fixtures_path, fixtures, order_shift, depth=0, max_depth=self.MAX_FIXTURE_DEPTH)`.
   - Else (assumed file): opens the file, `json.load`s it into `_fixture_data`. If `_fixture_data` is not a `dict`, raises `ValueError('Fixture data must be a dictionary')`. Otherwise appends `_fixture_data` to `fixtures`.
4. Iterates each `fixture` dict in `fixtures`:
   - Reads optional group order: `group_order := fixture.get('order')`. If truthy (non-zero, non-None), adds `order_shift` to it. **Bug-worthy quirk**: `'order'` is treated as a class name in the inner loop too, because there is no `continue`/filter — see below.
   - Iterates `for class_name in fixture:` (includes the `'order'` key if present) and then `for fixture_element in fixture[class_name]:`. If `'order'` was a scalar (int/float) rather than a list, iterating over it will raise `TypeError`. Fixtures containing a top-level `'order'` key must therefore have it be list-like or absent.
   - Per `fixture_element` (a dict):
     - `external_id = fixture_element.pop('_external_id', None)`.
     - `order = fixture_element.pop('_order', 0) + order_shift`.
     - If `not external_id` and `'external_id' in fixture_element`, sets `external_id = fixture_element.pop('external_id')`. Note this only runs if `_external_id` was missing/falsy; if `_external_id` was present, plain `external_id` remains inside the fixture's data.
     - Builds `FixtureData(class_name=class_name, external_id=external_id, order=order, data=fixture_element)`.
     - Appends `(group_order or order or 0, fixture_data)` to `self.fixtures[external_id]`. The ordering value precedence is: `group_order` if truthy, else `order` if truthy, else `0`. Zero/None all collapse to `0`.

Edge cases:
- If `external_id` ends up `None`/empty, all such fixtures are bucketed under key `None` in `self.fixtures`. They are still iterated and applied, but `external_id` on the resulting `FixtureData` will be `None`, which `_process_fixture` / `_process_fixture_object_data` will then try to use verbatim.

### `_load_fixtures_recursive(self, current_path, fixtures, order_shift, depth=0, max_depth=10) -> None`

Traverses a directory tree to identify "class folders" (Pattern A) and "explicit class JSON files" (Pattern B).

Step-by-step:
1. If `depth >= max_depth`, logs warning `'Max fixture nesting depth %s reached at %s, skipping deeper levels'` with `max_depth` and `current_path`, returns.
2. Attempts `items = list(current_path.iterdir())`. On `OSError`, logs `'Cannot access directory %s: %s'` and returns.
3. For each `item`:
   - **If `item.is_dir()`:**
     - Tries `dir_contents = list(item.iterdir())`. On `OSError`, logs `'Cannot access directory %s: %s'` and `continue`s.
     - `has_csv_files`: `True` iff any `f` in `dir_contents` has suffix `.csv` AND `f.is_file()`.
     - `has_json_list_files`: starts `False`. For each file with suffix `.json`, opens and `json.load`s it. If the loaded data `isinstance(..., list)`, sets `has_json_list_files = True` and breaks. Any `OSError` or `json.JSONDecodeError` during this probe is silently swallowed (`continue`). **Side effect: this causes JSON files to be parsed twice** (once here to classify, once later in `_load_class_folder_fixtures`).
     - If `has_csv_files or has_json_list_files`: calls `self._load_class_folder_fixtures(item, fixtures)`. On `OSError` from that call, logs `'Cannot access directory %s: %s'` and continues. **Note**: `order_shift` is NOT propagated into `_load_class_folder_fixtures` — class-folder fixtures lose the per-path shift.
     - Else: recurses with `self._load_fixtures_recursive(item, fixtures, order_shift, depth + 1, max_depth)`.
   - **Elif `item.is_file() and item.suffix == '.json'`:** calls `self._load_explicit_class_fixture(item, fixtures)`.
     - On `OSError`: logs `'Cannot read file %s: %s'`, `continue`.
     - On `json.JSONDecodeError` or `ValueError`: logs `'Invalid JSON in file %s: %s'`, `continue`.
   - All other items (symlinks not resolving to dir/file, non-JSON files at container level) are ignored silently.

Classification rule summary: A subdirectory is treated as a **class folder** if it contains at least one CSV file OR at least one top-level JSON file whose content is a list. Otherwise it's a **container** and the function recurses.

### `_load_class_folder_fixtures(self, class_dir: Path, fixtures: list[dict[str, Any]]) -> None`

Loads all fixtures from a directory whose **name equals a class name** (e.g., `Company/`).

For each `model_file` in `class_dir.iterdir()`:
- **If suffix `.json`:**
  - Opens, `json.load`s into `_fixture_data`.
  - If not `isinstance(_fixture_data, list)`: raises `ValueError(f'Fixture data in {model_file} must be a list')` — caught below.
  - Otherwise appends `{class_dir.name: _fixture_data}` to `fixtures`.
  - `OSError` → warning `'Cannot read file %s: %s'`, continue.
  - `json.JSONDecodeError` or `ValueError` → warning `'Invalid fixture in file %s: %s'`, continue.
- **Elif suffix `.csv`:**
  - Opens file. Reads via `pd.read_csv(csv_file).replace({np.nan: None}).to_dict(orient='records')`. Each row becomes a dict, with NaN values coerced to `None`.
  - Appends `{class_dir.name: _fixture_data}` to `fixtures`.
  - `OSError` → warning `'Cannot read file %s: %s'`, continue.
  - Any other `Exception` → warning `'Invalid CSV in file %s: %s'`, continue. (Intentionally broad.)
- Other suffixes are skipped silently.

### `_load_explicit_class_fixture(self, json_file: Path, fixtures: list[dict[str, Any]]) -> None`

Loads a single `{"ClassName": [...], ...}` JSON file (Pattern B).

- Opens and `json.load`s.
- If the parsed value is not a `dict`, raises `ValueError(f'Fixture data in {json_file} must be a dictionary')`.
- Otherwise appends the loaded dict to `fixtures`.

Caller (`_load_fixtures_recursive`) is responsible for handling `OSError` and `JSONDecodeError`.

### `iter_fixtures(self) -> Generator[FixtureData, None, None]`

Flattens all stored fixtures and yields them sorted by order.

1. Flattens: `[(order, data) for class_name, values in self.fixtures.items() for order, data in values]`. Note the iteration variable is named `class_name`, but it is actually the dict key (an `external_id`). Misleading naming; no functional consequence.
2. Sorts by `order` ascending using `sorted(..., key=lambda x: x[0])`. Sort is stable, so within the same order value, insertion order is preserved.
3. Yields only the `FixtureData` instances (drops the order tuple element).

### `_process_object_data(self, data, model_fields, m2m_fields) -> dict[str, Any]`

Transforms a raw data dict in place (and returns it) by coercing each value according to the target model's field type, using `process_fixture_value` from `amsdal.fixtures.utils`.

For each `(key, value)` in `data.items()`:
- If `key in m2m_fields`: let `_ref_type = m2m_fields[key]`; sets `data[key] = process_fixture_value(list[_ref_type], value)`. That is, coerces to a list of the related model class.
- Else: assumes `key in model_fields`, takes `field_info = model_fields[key]`, sets `data[key] = process_fixture_value(field_info.annotation, value)`.

Edge cases:
- If `key` is absent from both `m2m_fields` and `model_fields`, lookup `model_fields[key]` raises `KeyError` unhandled.
- `data` is mutated during iteration — `dict.items()` over Py3 iterates the snapshot of keys, but because we only reassign existing keys (not add/remove), this is safe.

---

## `FixturesManager(BaseFixturesManager)`

Synchronous orchestrator that applies loaded fixtures to the database.

### `apply_file_fixtures(self) -> None`

Applies binary file fixtures from a `files/` subdirectory of each fixtures path.

For each `_dir` in `self.fixtures_paths`: computes `files_dir = _dir / 'files'` and calls `self._apply_file_fixtures(files_dir)`.

### `_apply_file_fixtures(self, file_dir: Path) -> None`

Guard: if not (`file_dir.exists()` AND `file_dir.is_dir()`), returns silently. Otherwise calls `self._apply_file_fixtures_rec(file_dir, file_dir)` — passing the same path as both the walker position and the base for relative keys.

### `_apply_file_fixtures_rec(self, nested_dir, base_dir) -> None`

Walks the `files/` tree. For each entry `nested_object` in `nested_dir.iterdir()`:
- If directory: recurse (`self._apply_file_fixtures_rec(nested_object, base_dir)`), `continue`.
- Elif file: calls `self._process_file_fixture(nested_object, f'{nested_object.relative_to(base_dir)}')`. The second argument is the path relative to the top-level `files/` directory, stringified — used as the file's external key.

No error handling at this level: `OSError`, `PermissionError`, etc. propagate.

### `apply_fixtures(self) -> None`

Main entry point for applying data fixtures.

For each `fixture` yielded by `self.iter_fixtures()` (already sorted by `order`):
1. `fixture_data = self._process_fixture(fixture)` — upserts the `Fixture` meta-record.
2. If `fixture_data` is truthy (i.e., there was a change), calls `self._process_fixture_object_data(class_name=fixture_data.class_name, external_id=fixture_data.external_id, data=fixture_data.data)` to upsert the actual target object.

If `_process_fixture` returns `None` (no change detected), the object-data step is skipped entirely — meaning the target object is **not re-saved** when the fixture payload matches what's already recorded, even if someone else altered the target.

### `_process_file_fixture(self, file_path: Path, file_key: str) -> None`

Upserts a single file as an `amsdal.models.core.file.File` instance.

1. Imports `File` lazily from `amsdal.models.core.file`.
2. Opens `file_path` in binary mode; reads all bytes into `file_data`; computes `filename = file_path.resolve().name` (just the basename, resolved).
3. Builds `data = {'filename': filename, 'data': file_data}`.
4. Queries for an existing file: `File.objects.filter(_address__object_id=file_key, _address__object_version=Versions.LATEST).first().execute()`. Result typed as `File | None`.
5. If `existing_file is not None`:
   - Constructs a new candidate: `new_file = File.from_bytes(**data)`.
   - If `new_file.data == existing_file.data`: logs `'Skipping creating new version of file for file_key=%s, no changes found'` and returns without saving.
   - Else: logs `'Creating new version of fixture for file_key=%s'`, sets `existing_file.data = data['data']` (**only** `data`, not `filename`), and calls `existing_file.save()`. Filename updates are silently dropped.
6. Else (no existing): logs `'Creating first fixture for external_id=%s'` (log uses `external_id` label but the value is `file_key`), instantiates `File(_object_id=file_key, filename=..., data=...)`, calls `instance.save(force_insert=True)`.

Note: the `File.data` equality check relies on `File.from_bytes`'s own semantics; if `from_bytes` performs transforms (e.g., compression, hashing), the equality is comparing post-transform payloads, not raw bytes.

### `_process_fixture(self, fixture: FixtureData) -> FixtureData | None`

Upserts the `Fixture` meta-record that tracks each fixture's external_id ↔ data history.

1. Imports `Fixture` lazily from `amsdal.models.core.fixture`.
2. `external_id = fixture.external_id`.
3. Queries: `Fixture.objects.filter(external_id=external_id, _address__object_version=Versions.LATEST).first().execute()` into `existing_fixture: Model | None`.
4. `class_name = fixture.class_name`.
5. If `existing_fixture is not None`:
   - If `fixture.data == existing_fixture.data`: logs `'Skipping creating new version of fixture for external_id=%s, no changes found'` and **returns `None`** (signals caller to skip object-data upsert).
   - Else: logs `'Creating new version of fixture for external_id=%s'`, sets `existing_fixture.data = fixture.data`, calls `existing_fixture.save()`.
6. Else: logs `'Creating first fixture for external_id=%s'`, creates `instance = Fixture(_object_id=uuid.uuid4().hex, external_id=external_id, data=fixture.data, class_name=class_name)`, calls `instance.save(force_insert=True)`. Note the `_object_id` is a fresh random UUID hex; identity lookup is via `external_id` field, NOT `_object_id`.
7. Returns a fresh `FixtureData(external_id=external_id, class_name=class_name, data=copy.deepcopy(fixture.data), order=fixture.order)`. The deep copy insulates downstream mutation in `_process_fixture_object_data` from affecting the Fixture record just saved.

### `_process_fixture_object_data(self, class_name, external_id, data) -> None`

Upserts the actual target object described by the fixture.

1. `class_model = self._class_manager.import_class(class_name)` — resolves the class by name (may raise if the class isn't registered).
2. Queries for existing instance: `class_model.objects.filter(_address__object_id=external_id, _address__object_version=Versions.LATEST).first().execute()`. The `_object_id` address component equals the fixture's `external_id`.
3. `m2m_fields = getattr(class_model, MANY_TO_MANY_FIELDS, None) or {}`. The `MANY_TO_MANY_FIELDS` attribute, if present, maps field name → tuple. Each tuple is `(ref_type, _, _, _)` — a 4-tuple where only the first element (the related model class) is used.
4. Builds a reduced m2m map: `{_field: _ref_type for _field, (_ref_type, _, _, _) in m2m_fields.items()}`.
5. `updated_data = self._process_object_data(data, model_fields=class_model.model_fields or {}, m2m_fields=...)` — coerces each value in `data`.
6. `full_data = {**updated_data, '_object_id': external_id}` — pins the object id to the external_id for insert.
7. Branch:
   - If `existing_object is not None`: logs `'Creating new version of %s for external_id=%s'` with `class_model.__name__, external_id`. Iterates `for key, val in updated_data.items(): setattr(existing_object, key, val)` — mutates each attribute, then calls `existing_object.save()`. **Note**: `_object_id` is NOT reassigned (it's not in `updated_data`); attributes not present in `updated_data` remain untouched on the existing object.
   - Else: logs `'Creating %s for external_id=%s'`, instantiates `instance = class_model(**full_data)` (passing `_object_id=external_id` as kwarg), and calls `instance.save(force_insert=True)`.

---

## `AsyncFixturesManager(BaseFixturesManager)`

Async counterpart to `FixturesManager`. Semantics are identical except for:
- All persistence methods are `async def`.
- Query execution uses `.aexecute()` instead of `.execute()`.
- Saves use `instance.asave(...)` instead of `instance.save(...)`.
- Methods `apply_file_fixtures`, `_apply_file_fixtures`, `_apply_file_fixtures_rec`, `apply_fixtures`, `_process_file_fixture`, `_process_fixture`, `_process_fixture_object_data` are coroutines and await their persistence calls.

Notable detail: directory iteration still uses synchronous `Path.iterdir()` and file reads still use synchronous `open(...)`. Only database I/O is awaited.

All log messages, equality checks, control flow branches, data shapes, field mappings, object-id handling, UUID generation for new `Fixture` records, deep-copy of `data` in the returned `FixtureData`, and `_process_object_data` usage match the synchronous version exactly. Any divergence between the two managers in behavior would be a bug, not an intentional difference.

---

## Cross-cutting behaviors / debugging notes

- **External ID resolution order** in `_load_fixtures`: `_external_id` > `external_id` (only if `_external_id` was missing/falsy) > `None`. `_external_id` is always popped; `external_id` is only popped when `_external_id` was missing/falsy.
- **Order resolution** per stored tuple: `group_order or order or 0`. Group-level `order` (if truthy) overrides per-element `_order` entirely.
- **`order_shift` leakage**: propagated to per-file/per-element `_order` in `_load_fixtures`, but NOT into `_load_class_folder_fixtures` (Pattern A). Class-folder fixtures therefore start at `_order=0` plus `order_shift` applied at the top level — meaning CSV/JSON-list-sourced entries inside class folders effectively get `order_shift` only via the outer loop since the top-level `for fixture in fixtures` iteration re-applies `order_shift` in `_load_fixtures`. So class-folder fixtures DO get `order_shift` because it's applied at the `fixture_element` level in the outer loop, not inside the class-folder loader. Verify at `_load_fixtures` line `order = fixture_element.pop('_order', 0) + order_shift`.
- **Skip-on-no-change optimization**: `_process_fixture` returning `None` causes `_process_fixture_object_data` to be skipped. If the `Fixture` meta-record exists and matches but the target object has been deleted or modified externally, fixtures will NOT repair it.
- **`black.trans.defaultdict`** is a runtime dependency on the `black` code formatter package; removal of `black` would break initialization.
- **Double JSON parsing** in `_load_fixtures_recursive`: list-vs-dict classification reads each JSON file, then `_load_class_folder_fixtures` / `_load_explicit_class_fixture` reads it again. Large fixture trees incur this cost.
- **Silent failures**: classification probe swallows `OSError`/`json.JSONDecodeError`; CSV loader swallows every `Exception` as a warning. Malformed fixtures may never raise, just disappear with a WARNING log line.
