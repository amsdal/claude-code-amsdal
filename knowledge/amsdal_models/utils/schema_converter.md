# Module: `amsdal_models.utils.schema_converter`

Converts raw database schema introspection output (SQLite `PRAGMA table_info`, PostgreSQL `information_schema`, or generic column metadata) into AMSDAL `ObjectSchema` instances suitable for model generation.

---

## `ExternalSchemaConverter`

Stateless converter class. Holds no instance state — all data flows through method arguments. Two static type-mapping methods and three instance methods producing `ObjectSchema` objects.

### Static method: `sqlite_type_to_core_type(sqlite_type) -> str`

Maps a SQLite column type string to a `CoreTypes` value string using SQLite's type-affinity rules ([docs](https://www.sqlite.org/datatype3.html)).

**Step-by-step (first match wins, evaluated top to bottom):**

1. Uppercases input: `sqlite_type_upper = sqlite_type.upper()`.
2. If `'INT'` is a substring → returns `CoreTypes.INTEGER.value`.
3. If any of `'CHAR'`, `'CLOB'`, `'TEXT'` is a substring → returns `CoreTypes.STRING.value`.
4. If any of `'BLOB'`, `'BINARY'` is a substring → returns `CoreTypes.BINARY.value`.
5. If any of `'REAL'`, `'FLOA'`, `'DOUB'` is a substring → returns `CoreTypes.NUMBER.value`.
6. If `'DATE'` is a substring **or** `'TIME'` is a substring → enters a sub-branch:
   - If **both** `'TIME'` and `'DATE'` are substrings → returns `CoreTypes.DATETIME.value`.
   - Else if `'STAMP'` is a substring (catches `TIMESTAMP`) → returns `CoreTypes.DATETIME.value`.
   - Else if `'DATE'` is a substring → returns `CoreTypes.DATE.value`.
   - Else (only `'TIME'` without `'DATE'` or `'STAMP'`) → returns `CoreTypes.DATETIME.value`.
7. If `'BOOL'` is a substring → returns `CoreTypes.BOOLEAN.value`.
8. Fallback → returns `CoreTypes.STRING.value`.

**Edge cases:**
- `'POINT'` → contains `'INT'` → maps to `INTEGER` (not a geometry type).
- `'FLOATINT'` → contains `'INT'` first → `INTEGER`, not `NUMBER`.
- Bare `'TIME'` (no `'DATE'`, no `'STAMP'`) → `DATETIME`, not a dedicated time type.
- Empty string `''` → falls through to the fallback → `STRING`.

### Static method: `postgres_type_to_core_type(postgres_type) -> str`

Maps a PostgreSQL column type string to a `CoreTypes` value string.

**Step-by-step (first match wins):**

1. Lowercases input: `postgres_type_lower = postgres_type.lower()`.
2. Exact match in `('smallint', 'integer', 'bigint', 'serial', 'bigserial', 'smallserial')` → `CoreTypes.INTEGER.value`.
3. Exact match in `('real', 'double precision', 'numeric', 'decimal')` → `CoreTypes.NUMBER.value`.
4. Ends with `'[]'` (array type) → `CoreTypes.ARRAY.value`.
5. Any of `'char'`, `'varchar'`, `'text'` is a substring → `CoreTypes.STRING.value`.
6. `'bytea'` is a substring → `CoreTypes.BINARY.value`.
7. Exact match `'boolean'` → `CoreTypes.BOOLEAN.value`.
8. Exact match `'date'` → `CoreTypes.DATE.value`.
9. Any of `'timestamp'`, `'time'` is a substring → `CoreTypes.DATETIME.value`.
10. Any of `'json'`, `'jsonb'` is a substring → `CoreTypes.DICTIONARY.value`.
11. Fallback → `CoreTypes.STRING.value`.

**Edge cases:**
- Array check (step 4) is **before** the string-type check (step 5), so `'text[]'` returns `ARRAY`, not `STRING`.
- `'varchar(255)'` → contains `'varchar'` → `STRING`.
- `'character varying'` → contains `'char'` → `STRING`.
- Custom user types / enum types that aren't in the explicit lists fall through to `STRING`.

### Instance method: `sqlite_schema_to_object_schema(table_name, columns, connection_name=None) -> ObjectSchema`

Converts SQLite `PRAGMA table_info` output into an `ObjectSchema`.

**Expected `columns` format:** List of dicts with keys `'cid'`, `'name'`, `'type'`, `'notnull'`, `'dflt_value'`, `'pk'`.

**Step-by-step:**

1. Initializes `properties = {}`, `required_fields = []`, `pk_fields = []`.
2. For each `column` dict:
   - `column_name = column['name']`
   - `column_type = column['type']`
   - `is_nullable = column['notnull'] == 0` (SQLite's `notnull` is `1` for NOT NULL, `0` for nullable).
   - `is_pk = column['pk'] > 0` (multi-column PKs have ordinal > 0).
   - `default_value = column.get('dflt_value')` (uses `.get()`, so missing key → `None`).
   - Calls `self.sqlite_type_to_core_type(column_type)` → `core_type`.
   - Builds `property_def = {'type': core_type, 'title': column_name}`.
   - If `default_value is not None` → adds `property_def['default'] = default_value`.
   - Assigns `properties[column_name] = property_def`.
   - If `not is_nullable and not is_pk` → appends `column_name` to `required_fields`. **Note:** PK columns are excluded from required, even if NOT NULL.
   - If `is_pk` → appends `column_name` to `pk_fields`.
3. Builds `schema_data`:
   - `'title': classify(table_name)` — uses `amsdal_utils.utils.text.classify` to convert snake_case to PascalCase (e.g., `'user_accounts'` → `'UserAccounts'`).
   - `'__table_name__': table_name`
   - `'properties': properties`
   - `'required': required_fields`
   - If `pk_fields` is non-empty → adds `'__primary_key__': pk_fields`.
   - If `connection_name` is truthy → adds `'__connection__': connection_name`.
4. Returns `ObjectSchema(**schema_data)`.

**Edge cases:**
- Columns with `dflt_value = 0` or `dflt_value = ''` are treated as "has default" because the check is `is not None`.
- A column that is both PK and NOT NULL will appear in `pk_fields` but **not** in `required_fields` — this is the `and not is_pk` condition.
- Iteration order matches input list order; `properties` dict preserves insertion order (Python 3.7+).

### Instance method: `postgres_schema_to_object_schema(table_name, columns, connection_name=None) -> ObjectSchema`

Converts PostgreSQL `information_schema` output into an `ObjectSchema`.

**Expected `columns` format:** List of dicts with keys `'column_name'`, `'data_type'`, `'is_nullable'`, `'column_default'`.

**Step-by-step:**

1. Initializes `properties = {}`, `required_fields = []` (no `pk_fields` — Postgres version does not track primary keys).
2. For each `column` dict:
   - `column_name = column['column_name']`
   - `data_type = column['data_type']`
   - `is_nullable = column.get('is_nullable', 'YES') == 'YES'` (Postgres returns the string `'YES'` or `'NO'`; default to `'YES'` if missing).
   - `default_value = column.get('column_default')`.
   - Calls `self.postgres_type_to_core_type(data_type)` → `core_type`.
   - Builds `property_def = {'type': core_type, 'title': column_name}`.
   - If `default_value is not None` → adds `property_def['default'] = default_value`.
   - Assigns `properties[column_name] = property_def`.
   - If `not is_nullable` → appends `column_name` to `required_fields` (no PK exclusion in this variant).
3. Builds `schema_data` with `'title'`, `'__table_name__'`, `'properties'`, `'required'`. Adds `'__connection__'` if `connection_name` is truthy.
4. Returns `ObjectSchema(**schema_data)`.

**Difference from SQLite version:** Does NOT populate `__primary_key__` (Postgres PK info is in a separate query that this method does not receive). All NOT NULL columns go into `required_fields`, including PKs.

### Instance method: `generic_schema_to_object_schema(table_name, columns, connection_name=None, type_converter=None) -> ObjectSchema`

Most flexible converter — works with any column format that has `'name'` and `'type'` keys. Optional type converter callable.

**Expected `columns` format minimum:** `[{'name': str, 'type': str}, ...]`. Optional fields: `'nullable'`, `'required'`, `'primary_key'`, `'default'`.

**Step-by-step:**

1. If `type_converter is None` → defaults to `self.sqlite_type_to_core_type`.
2. Initializes `properties = {}`, `required_fields = []`, `pk_fields = []`.
3. For each `column` dict:
   - `column_name = column['name']`
   - `column_type = column['type']`
   - `is_nullable = column.get('nullable', True)` (default: True = nullable).
   - `is_required = column.get('required', False)` (default: False).
   - `is_pk = column.get('primary_key', False)`.
   - `default_value = column.get('default')`.
   - `core_type = type_converter(column_type)`.
   - Builds `property_def = {'type': core_type, 'title': column_name}`. Adds `'default'` if non-None.
   - Assigns `properties[column_name] = property_def`.
   - If `not is_nullable OR is_required` → appends to `required_fields`. **Note:** Either condition makes a field required — unlike the SQLite variant which only uses nullability.
   - If `is_pk` → appends to `pk_fields`.
4. Builds `schema_data` same way as SQLite version: `'title'`, `'__table_name__'`, `'properties'`, `'required'`. Adds `'__primary_key__'` if PKs present. Adds `'__connection__'` if provided.
5. Returns `ObjectSchema(**schema_data)`.

**Key difference from SQLite:**
- Required field logic: `(not is_nullable) OR is_required`, instead of `(not is_nullable) AND (not is_pk)`. PK columns CAN appear in `required_fields` here.
- Uses a pluggable type converter — pass `converter.postgres_type_to_core_type` to use Postgres mapping with generic column format.

---

## Key behavioral notes for debugging

1. **SQLite type-affinity order matters:** The checks run top-to-bottom and first match wins. If your column type contains both `'INT'` and something else (e.g., hypothetical `'INTEGER_TIMESTAMP'`), it will map to `INTEGER` because `'INT'` is checked first.

2. **Postgres arrays use exact suffix match:** `'integer[]'` → `ARRAY`. But `'integer [ ]'` (with spaces) would not match — falls through to `INTEGER` via step 2... actually no, step 2 requires exact match. It would fall through all the way to `STRING`. Whitespace in type names is fragile.

3. **SQLite converter excludes PKs from required:** If you're seeing a non-nullable PK column not appearing in `required`, that's intentional — AMSDAL treats PKs specially via `__primary_key__`.

4. **Defaults of `0` and `''`** are preserved as defaults because the check is `is not None`. `None` defaults are dropped.

5. **`classify` dependency:** The `title` field is derived via `classify(table_name)` from `amsdal_utils.utils.text`. This converts snake_case to PascalCase. If `table_name` is already PascalCase, `classify` is generally idempotent, but check `amsdal_utils` for exact behavior on edge cases (numbers, underscores, Unicode).

6. **All three converters produce the same `ObjectSchema` shape** — only the extraction logic differs. Downstream model generation doesn't know which converter was used.
