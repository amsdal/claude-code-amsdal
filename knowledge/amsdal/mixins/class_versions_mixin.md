## ClassVersionsMixin

A mixin class intended to be combined with other classes to provide functionality for registering internal AMSDAL framework classes with a historical schema version manager. The class itself holds no instance state and defines no `__init__`; it exposes only static and class methods. Its purpose is to seed the `HistoricalSchemaVersionManager` (or its async counterpart) with a known fixed set of "internal" class names so that downstream code resolving class versions can find entries for these built-in types even before any migration has produced schema versions for them.

**Dependencies:**
- Imports `AsyncHistoricalSchemaVersionManager` and `HistoricalSchemaVersionManager` from `amsdal_data.connections.historical.schema_version_manager`.

**State managed:** None. The mixin itself is stateless. All mutation happens on the externally provided or instantiated `schema_version_manager` object.

**Lifecycle:** The mixin is not instantiated for its own sake — its methods are invoked as class methods, typically during AMSDAL framework bootstrap/initialization to prime the schema version registry with internal class names.

### `_register_internal_classes(schema_version_manager)` (staticmethod)

**Signature:** Accepts a single parameter `schema_version_manager` typed as `HistoricalSchemaVersionManager | AsyncHistoricalSchemaVersionManager`. Returns `None`.

**Step-by-step internal behavior:**

1. Iterates over a fixed tuple of exactly five string literals, in this order:
   - `'Object'`
   - `'Transaction'`
   - `'Metadata'`
   - `'Reference'`
   - `'Migration'`
2. For each string (bound to the loop variable `internal_class`), calls `schema_version_manager.register_last_version(internal_class, '')`. The second positional argument is always the empty string `''` — this represents the version identifier being registered for that class name.
3. Performs no return value handling; discards whatever `register_last_version` returns (including `None` or a coroutine).

**Important branching / conditions:** None. There is no conditional logic, no try/except, no checking whether the manager is sync or async. The method blindly calls `register_last_version` on whatever object is passed, with the same two arguments, five times.

**Side effects:** Each call to `register_last_version(internal_class, '')` mutates state inside the passed-in `schema_version_manager`, registering the empty string `''` as the "last version" for each of the five internal class names. The exact mutation semantics are defined by the schema version manager implementation in `amsdal_data.connections.historical.schema_version_manager`.

**Edge cases / pitfalls:**
- **Async manager is not awaited.** If `schema_version_manager` is an `AsyncHistoricalSchemaVersionManager` and `register_last_version` is a coroutine function, the returned coroutines are discarded without being awaited. This will typically produce a `RuntimeWarning: coroutine '...' was never awaited` and the registrations will **not** actually take effect. If production behavior shows that internal classes are not registered when using the async manager, this is the likely root cause — see `aregister_internal_classes` below for the same issue at the call-site level.
- If `register_last_version` is synchronous on the async manager (i.e., the async manager exposes a sync `register_last_version`), registration will succeed normally. Whether this is the case depends on the async manager's API surface — consult the `amsdal_data` module.
- If any call to `register_last_version` raises an exception, iteration stops immediately and subsequent internal classes in the tuple are **not** registered. There is no cleanup or partial-rollback.
- The order of registration is fixed: `Object` first, then `Transaction`, `Metadata`, `Reference`, `Migration` last. If downstream logic depends on registration order (e.g., earliest-registered wins), this order matters.
- Exact class names are case-sensitive string literals. Any downstream lookup using a different casing (e.g., `'object'`, `'METADATA'`) will not find these registrations.

**Exceptions:** Does not raise any exceptions on its own. Any exception surfaced here propagates from `register_last_version`.

### `register_internal_classes()` (classmethod)

**Signature:** Takes no arguments beyond `cls`. Returns `None`.

**Step-by-step internal behavior:**

1. Instantiates a fresh `HistoricalSchemaVersionManager()` with no constructor arguments. Note: this assumes `HistoricalSchemaVersionManager` is either a singleton (its `__init__` returns/reuses a shared instance) or that a default construction is sufficient to reach the shared registry — if the class is not singleton-backed, this produces a new, disconnected instance and registrations will be applied to that isolated instance, not to any globally shared one. Check the implementation of `HistoricalSchemaVersionManager` in `amsdal_data` to confirm.
2. Passes the newly constructed instance directly as the sole argument to `cls._register_internal_classes(...)`, which runs the five-class registration loop described above.
3. Returns `None` implicitly.

**Side effects:** Registers the five internal class names (`Object`, `Transaction`, `Metadata`, `Reference`, `Migration`) with empty-string versions in the `HistoricalSchemaVersionManager` instance constructed in step 1.

**Edge cases:**
- If `HistoricalSchemaVersionManager()` itself raises during construction (e.g., missing configuration, missing connection state), the method fails before any registrations occur.
- Because `cls._register_internal_classes` is a staticmethod, the `cls` binding is only used for method resolution and does not affect behavior — subclasses that override `_register_internal_classes` will have their override used here.

### `aregister_internal_classes()` (classmethod)

**Signature:** Takes no arguments beyond `cls`. Returns `None`.

**Note on naming:** The `a`-prefix in AMSDAL conventionally denotes an async counterpart (e.g., `aregister` = async version of `register`). However, this method is declared with `def`, not `async def`, and it does not `await` anything — the "async" aspect refers only to the **manager** used, not to this method being awaitable.

**Step-by-step internal behavior:**

1. Instantiates a fresh `AsyncHistoricalSchemaVersionManager()` with no constructor arguments. Same singleton caveat as `register_internal_classes`.
2. Passes the newly constructed async manager as the sole argument to `cls._register_internal_classes(...)`.
3. Returns `None` implicitly.

**Critical bug warning:** Because `_register_internal_classes` invokes `schema_version_manager.register_last_version(...)` without `await`, and because `AsyncHistoricalSchemaVersionManager.register_last_version` is presumably a coroutine function, calling `aregister_internal_classes()` will:
- Create five coroutine objects,
- Immediately discard each of them,
- Return without registering anything,
- Likely emit `RuntimeWarning: coroutine '...' was never awaited` at garbage collection time.

If a developer reports "internal classes are not registered in async mode" or "nothing happens when I call `aregister_internal_classes`", this is the explanation. The fix would require either making `_register_internal_classes` itself `async def` and awaiting the calls (plus making `aregister_internal_classes` `async def` and awaiting the helper), or providing a sync `register_last_version` on the async manager. Neither is done in this module.

**Side effects (if register_last_version is sync on the async manager):** Registers the five internal class names with empty-string versions.

**Side effects (if register_last_version is a coroutine on the async manager):** Effectively none — coroutines are dropped unawaited.

**Exceptions:** Does not raise on its own. Does not produce a `SyntaxError` or `TypeError` for the unawaited coroutines — Python tolerates unawaited coroutines at runtime and only warns (typically at GC).

---

## Summary of behavioral contract

- Calling `ClassVersionsMixin.register_internal_classes()` prime-registers exactly five internal class names — `Object`, `Transaction`, `Metadata`, `Reference`, `Migration` — each paired with the empty string `''` as the version, in a newly constructed `HistoricalSchemaVersionManager` instance.
- Calling `ClassVersionsMixin.aregister_internal_classes()` attempts the same against a newly constructed `AsyncHistoricalSchemaVersionManager`, but because the helper does not `await`, it works correctly only if the async manager's `register_last_version` is synchronous; otherwise registrations silently fail.
- No other behavior, no caching, no deduplication, no validation, no logging is performed by this mixin.
