# Module: `amsdal_data.transactions.manager`

Synchronous and asynchronous transaction managers for the AMSDAL data layer. Both support nested transactions via a parent-child context chain. Delegate actual transaction coordination to `amsdal_glue`.

---

## Module-level state

Two `ContextVar` instances hold per-async-task transaction state:

- **`ASYNC_TRANSACTION_CONTEXT`** — `ContextVar[TransactionContext | None]` with name `'transaction_context'`, default `None`. Per-task transaction context for the async manager.
- **`ASYNC_TRANSACTION_OBJECT`** — `ContextVar[Transaction | None]` with name `'transaction_object'`, default `None`. Per-task root `Transaction` model for the async manager.

Module-level `logger = logging.getLogger(__name__)`.

---

## `AmsdalTransactionManager`

**Metaclass:** `Singleton` (from `amsdal_utils.utils.singleton`) — only one instance per process.

**Purpose:** Synchronous transaction manager. Begin/commit/rollback lifecycle, supports nesting, persists root transaction record to the lakehouse on commit.

### State

| Attribute | Type | Initial | Description |
|---|---|---|---|
| `context` | `TransactionContext \| None` | `None` | Currently active (innermost) context. Linked list via `.parent`. |
| `transaction_object` | `Transaction \| None` | `None` | Root-level `Transaction` record, created on outermost `begin()`. Cleared after outermost commit. |
| `operation_manager` | (from `DataApplication`) | `DataApplication().operation_manager` | Delegate for transaction and data commands. |

**Thread safety:** Uses plain instance attributes. Since the class is a singleton, state is shared across all threads — **NOT thread-safe**. Use `AmsdalAsyncTransactionManager` (ContextVar-backed) for concurrent use.

**`__init__`:** Lazily imports `DataApplication` from `amsdal_data.application` (avoids circular imports). Sets `self.context = None`, `self.transaction_object = None`, assigns `self.operation_manager`.

### Property: `transaction_id` → `str | None`

Returns `self.context.address.object_id` if `self.context is not None`, else `None`.

### `begin(context, transaction_kwargs) -> None`

Starts a new transaction (or nested sub-transaction).

**Parameters:**
- `context`: `TransactionContext` — the new context to activate.
- `transaction_kwargs`: `dict[str, Any]` — must contain `'label'` (required); may contain `'tags'` (defaults to `[]`).

**Step-by-step:**

1. **Nesting check:** If `self.context is not None` → sets `context.parent = self.context` (child of current).
2. **Root creation:** If `self.context is None` → creates `self.transaction_object = Transaction(address=context.address, label=transaction_kwargs['label'], tags=transaction_kwargs.get('tags', []))`. **Raises `KeyError`** if `'label'` is missing.
3. **Context activation:** Sets `self.context = context`.
4. **Glue BEGIN command:** Calls `self.operation_manager.perform_transaction_command(command=glue.TransactionCommand(...))` with:
   - `root_transaction_id`: result of `self.get_root_transaction_id()`
   - `transaction_id`: `context.address.object_id`
   - `schema`: `glue.SchemaReference(name=context.address.class_name, version=glue.Version.LATEST)`
   - `action`: `glue.TransactionAction.BEGIN`
   - `parent_transaction_id`: `context.parent.address.object_id` if `context.parent` else `None`
5. **Failure handling:** If `result.success` is falsy → raises `AmsdalTransactionError('Transaction failed on the begin.')` chained from `result.exception`.

### `commit(return_value) -> None`

Commits the current transaction. For nested transactions, only the innermost is committed; for the root, the transaction record is persisted first.

**Step-by-step:**

1. **Snapshot:** `context = self.context`.
2. **Guard:** If `context is None` → raises `AmsdalTransactionError('No ongoing transaction on transaction commit')`.
3. **Store return value:** `context.return_value = return_value`.
4. **Top-level finalization** (if `context.is_top_level` is truthy):
   - If `self.transaction_object is None` → raises `AmsdalTransactionError('No transaction object on transaction commit')`.
   - Sets `self.transaction_object.ended_at = round(time.time() * 1000)` (current Unix timestamp in milliseconds).
   - Calls `self._store_transaction()` — persists the `Transaction` record to the lakehouse.
5. **Glue COMMIT command:** `self.operation_manager.perform_transaction_command(command=glue.TransactionCommand(...))` with `action=glue.TransactionAction.COMMIT`, other fields same as BEGIN.
6. **Context pop (happens BEFORE result check):**
   - `context = context.parent`
   - `self.context = context`
   - If `context is None` → sets `self.transaction_object = None` (cleared only when the outermost transaction is done).
7. **Handle commit failure** (if `result.success` is falsy):
   - If `context` (the parent after pop) is non-None **and** `not context.is_top_level`:
     - Sends a REVERT command targeting the **parent** context (not the failed child): `action=glue.TransactionAction.REVERT`, `transaction_id=context.address.object_id`, `parent_transaction_id=context.parent.address.object_id if context.parent else None`.
   - Otherwise (parent is None or parent is top-level) → does nothing (TODO comment: "Revert the root transaction? Probably, should be handled by amsdal-glue").
   - Raises `AmsdalTransactionError('Transaction failed on the commit.')` chained from `result.exception`.

**Critical behavior:** The context is popped to the parent **before** the failure check runs. The REVERT targets the parent, not the failed context. `self.context` already points to the parent when the exception is raised.

### `rollback() -> None`

Rolls back the current transaction.

**Step-by-step:**

1. **Snapshot:** `context = self.context`.
2. **Guard:** If `context is None` → raises `AmsdalTransactionError('No ongoing transaction on transaction rollback')`.
3. **Glue ROLLBACK command:** with `action=glue.TransactionAction.ROLLBACK`, same fields as BEGIN/COMMIT.
4. **Failure handling:** If `result.success` is falsy → raises `AmsdalTransactionError('Transaction failed on the rollback.')` chained from `result.exception`.
5. **Context pop:** `self.context = context.parent if context else None` (the `if context` is redundant — already checked in step 2).

**Note:** Unlike `commit`, rollback does NOT clear `self.transaction_object`, does NOT set `context.return_value`, does NOT persist anything. If rollback is called on a top-level transaction, `self.transaction_object` remains set but `self.context` becomes `None`. Subsequent `begin()` will overwrite `self.transaction_object`.

### `_store_transaction() -> None`

Persists the root `Transaction` record to the lakehouse.

**Step-by-step:**

1. `transaction_object = self.transaction_object`.
2. **Early return:** If `transaction_object is None` → returns immediately (no-op).
3. **Serialize:** `data = transaction_object.model_dump()` — full Pydantic serialization, no `exclude`, no `mode` argument, all fields included.
4. **Add partition key:** `data[PRIMARY_PARTITION_KEY] = transaction_object.address.object_id`. The constant is imported from `amsdal_data.connections.constants`.
5. **InsertData command:** `self.operation_manager.perform_data_command_lakehouse(command=glue.DataCommand(...))` with:
   - `root_transaction_id`: `self.get_root_transaction_id()`
   - `transaction_id`: `self.transaction_id` (at this point still points to the committing context, because context pop in `commit()` happens AFTER `_store_transaction()`).
   - `mutations`: `[glue.InsertData(schema=glue.SchemaReference(name=transaction_object.address.class_name, version=transaction_object.address.class_version), data=[glue.Data(data=data)])]`.
6. **Failure handling:** If `result.success` is falsy → raises `AmsdalTransactionError(f'Transaction failed on the store. Error: {result.message}')` chained from `result.exception`. **This is the only error message in the module that includes dynamic content** (`result.message`).

### `get_root_transaction_id() -> str | None`

Walks the context chain up to the root.

**Step-by-step:**

1. `context = self.context`.
2. If `context is None` → returns `None`.
3. While `context.parent` is truthy → `context = context.parent`.
4. Returns `context.address.object_id` (the trailing `if context else None` is redundant — `context` is guaranteed non-None after step 2).

---

## `AmsdalAsyncTransactionManager`

**Metaclass:** `Singleton`.

**Purpose:** Async-safe transaction manager. Identical logic to the sync variant, but all glue commands are `await`ed and state is stored in `ContextVar`s instead of instance attributes — safe for concurrent async tasks.

### State

| Attribute | Storage | Description |
|---|---|---|
| `context` | `ASYNC_TRANSACTION_CONTEXT` ContextVar | Per-task context. Accessed via property. |
| `transaction_object` | `ASYNC_TRANSACTION_OBJECT` ContextVar | Per-task root transaction. Accessed via property. |
| `operation_manager` | Instance attribute | Async operation manager from `AsyncDataApplication`. |

**`__init__`:** Lazily imports `AsyncDataApplication`, assigns `self.operation_manager`. Does NOT initialize `context` or `transaction_object` as instance attributes — those are properties backed by ContextVars.

### Properties

- **`context` getter:** Returns `ASYNC_TRANSACTION_CONTEXT.get()` — the current task's context.
- **`context` setter:** Calls `ASYNC_TRANSACTION_CONTEXT.set(value)`.
- **`transaction_object` getter/setter:** Same pattern with `ASYNC_TRANSACTION_OBJECT`.
- **`transaction_id`:** Same logic as sync — reads `self.context.address.object_id` if context exists.

### Async methods

`begin`, `commit`, `rollback`, `_store_transaction` — identical logic to their sync counterparts, with all `self.operation_manager.*` calls `await`ed (and `_store_transaction` itself `await`ed from within `commit`). All branching, error messages, context-pop-before-check behavior is identical.

### `get_root_transaction_id()` — NOT async

Synchronous. Reads current context from the ContextVar, walks the parent chain. Same logic as sync manager — no I/O, no need for `await`.

---

## Key behavioral notes for debugging

1. **Singleton + ContextVar split:** `AmsdalTransactionManager` uses instance attributes (shared across threads — not thread-safe). `AmsdalAsyncTransactionManager` uses ContextVars (per-task — safe for concurrent coroutines). Don't mix.

2. **Commit failure reverts the parent, not the child:** In `commit()`, by the time failure handling runs, `self.context` already points to the parent. The REVERT command targets the parent. If parent is top-level or None → NO revert is issued (only the exception is raised). This is explicitly marked as TODO in the code.

3. **Rollback doesn't clear `transaction_object`:** After top-level `rollback()`, `self.transaction_object` stays set; only `self.context` becomes `None`. Inspecting manager state between rollback and next begin shows a stale `transaction_object`. Subsequent `begin()` overwrites it, so it's not a leak — but it's a gotcha when debugging.

4. **`_store_transaction` uses `self.transaction_id`:** Inside `commit()`, `_store_transaction()` is called BEFORE the context pop. So `self.transaction_id` returns the committing context's ID (correct). If you refactor this, don't reorder.

5. **`model_dump()` with no arguments:** The `Transaction` object is serialized with default Pydantic params — no field exclusions, no mode selection. All fields go to the lakehouse.

6. **Timestamp precision:** `ended_at = round(time.time() * 1000)` = Unix epoch in milliseconds. `round()` on a float in Python 3 returns `int`.

7. **Label is required:** `transaction_kwargs['label']` uses `[]` access, not `.get()`. Missing label → `KeyError` on root-level `begin()`. Nested begins don't hit this code path (they go through the `if self.context is not None` branch).

8. **Error messages are exact strings** (useful for log matching):
   - `'No ongoing transaction on transaction commit'`
   - `'No transaction object on transaction commit'`
   - `'No ongoing transaction on transaction rollback'`
   - `'Transaction failed on the begin.'` (note trailing period)
   - `'Transaction failed on the commit.'`
   - `'Transaction failed on the rollback.'`
   - `f'Transaction failed on the store. Error: {result.message}'` — the only one with dynamic content.

## Key interactions

| Module | Usage |
|---|---|
| `amsdal_glue` | All transaction lifecycle (BEGIN/COMMIT/ROLLBACK/REVERT) and data persistence (InsertData) go through glue. |
| `amsdal_data.application.DataApplication` / `AsyncDataApplication` | Lazily imported inside `__init__` to avoid circular imports. Provides `operation_manager`. |
| `amsdal_utils.models.data_models.transaction.Transaction` | Pydantic model for the transaction record. Created on root begin, serialized and stored on root commit. |
| `amsdal_data.data_models.transaction_context.TransactionContext` | Carries per-transaction metadata (address, parent link, return value, `is_top_level` flag). Forms a linked list for nesting. |
| `amsdal_data.connections.constants.PRIMARY_PARTITION_KEY` | Partition key field name when storing the transaction record. |
| `amsdal_data.transactions.errors.AmsdalTransactionError` | Single exception type for all transaction failures. |
