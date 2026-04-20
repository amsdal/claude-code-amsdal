# Module: `amsdal_data.lock.implementations.thread_lock`

In-process thread-based implementation of `LockBase`. Suitable for single-process deployments. Uses Python's `threading.Lock` under the hood.

---

## `ThreadLock`

Subclass of `LockBase`. Holds per-address `threading.Lock` instances and metadata in in-memory dicts.

### State

| Attribute | Type | Initial | Description |
|---|---|---|---|
| `locks` | `dict[Address, Lock]` | `{}` | Maps each address to its `threading.Lock` instance. |
| `lock_data` | `dict[Address, LockObject]` | `{}` | Maps each address to its `LockObject` (metadata + expiration). |

### `__init__(self) -> None`

Initializes both dicts as empty. No other setup.

### `connect(*args, **kwargs) -> None`

**No-op.** Empty body (`...`). Thread locks need no connection setup.

### `disconnect() -> None`

**No-op.** Empty body.

### Property: `is_connected` → `bool`

Always returns `True`. In-memory locks are always "connected".

### Property: `is_alive` → `bool`

Always returns `True`.

### `acquire(target_address, *, timeout_ms=-1, blocking=True, metadata=None) -> bool`

Acquires a lock for the given address.

**Step-by-step:**

1. **Lazy lock creation:** If `target_address not in self.locks`:
   - Creates a new `threading.Lock()` and stores it in `self.locks[target_address]`.
   - Creates a `LockObject(expires_at=..., data=metadata or {})` and stores it in `self.lock_data[target_address]`:
     - If `timeout_ms >= 0` → `expires_at = round(time() * 1000) + timeout_ms` (absolute ms-epoch expiry).
     - If `timeout_ms < 0` (typically `-1`) → `expires_at = -1` (no expiration).
   - `data` defaults to `{}` when metadata is None.
2. Retrieves `lock = self.locks[target_address]`.
3. **Blocking branch** (`blocking=True`):
   - Calls `lock.acquire(timeout=timeout_ms / 1000 if timeout_ms >= 0 else -1)`.
   - **Note:** `threading.Lock.acquire(timeout=-1)` is actually valid Python — negative timeouts are interpreted as no timeout (blocks indefinitely). But `threading.Lock.acquire(timeout=0)` is **not** the same as `blocking=False` — it checks once and returns.
4. **Non-blocking branch** (`blocking=False`):
   - Calls `lock.acquire(blocking=False)`. Returns immediately with `True` if acquired, `False` if contended.

**Return:** `True` if acquired, `False` if timed out or contended.

**Important behavioral notes:**

- **Lock and metadata created only on first call:** Subsequent calls with the same `target_address` reuse the existing `threading.Lock`. The `lock_data` entry is **not refreshed** — `expires_at` and `data` are frozen at the first `acquire` call. If you need updated metadata per acquisition, this module does not support that.
- **No ownership tracking:** `threading.Lock` does not track which thread acquired it. Any thread calling `release()` with the address will release the lock (see below).
- **`expires_at` is informational only:** The module stores it in `LockObject` but does NOT enforce expiration. The lock won't auto-release after `timeout_ms` elapses. Only the initial `acquire` call respects the timeout — subsequent access is permanent until `release()`.
- **Dict access thread-safety:** Python dicts are thread-safe for single operations but not for compound ones. The `if target_address not in self.locks` + subsequent insert is a **race condition** — two threads can both see "missing" and both create new Lock objects. One will be lost. This can cause two threads to both think they hold "the" lock. In practice, this window is very narrow but exists.

### `release(target_address) -> None`

Releases the lock for the given address.

**Step-by-step:**

1. If `target_address in self.locks`:
   - Retrieves `lock = self.locks[target_address]`.
   - Calls `lock.release()`.
2. If `target_address not in self.locks` → **silently does nothing** (no error).

**Important:**

- **No owner check:** Any thread can release any lock. If thread A acquires and thread B releases, `threading.Lock.release()` succeeds (non-reentrant `Lock` doesn't track owner, unlike `RLock`).
- **`RuntimeError` risk:** If the lock is released when it wasn't acquired (i.e., the Python-level Lock is not currently held), `threading.Lock.release()` raises `RuntimeError('release unlocked lock')`. The docstring mentions this, but the code doesn't catch it — propagates to caller.
- **`lock_data` is not cleaned up** — the metadata dict grows indefinitely as new addresses are locked. Long-running processes with many distinct addresses could accumulate entries.

---

## Debugging notes

1. **"release unlocked lock" RuntimeError:** Acquire/release mismatch. Common causes:
   - Acquire failed but code proceeded to release without checking the return value.
   - Multiple releases for one acquire.
   - Release called on an address that was never acquired.

2. **Race condition on first acquire:** In highly concurrent scenarios, if two threads acquire the same new address simultaneously, one may get a `threading.Lock` that another thread doesn't see. Mitigation: pre-create locks at application startup if addresses are known.

3. **`expires_at` misleading:** Do not rely on the stored `expires_at` for lock expiration. The lock itself does not expire — `expires_at` is just metadata. If you need expiring locks, use `RedisLock` (which also currently lacks TTL, or implement application-level expiration).

4. **Memory growth:** `locks` and `lock_data` dicts grow without bound. In long-running processes with many addresses, consider manual cleanup.
