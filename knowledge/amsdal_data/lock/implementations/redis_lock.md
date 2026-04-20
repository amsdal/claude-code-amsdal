# Module: `amsdal_data.lock.implementations.redis_lock`

Redis-backed implementation of `LockBase` — distributed lock suitable for multi-process / multi-host deployments. Uses Redis `SET NX` for atomic lock acquisition.

---

## `RedisLock`

Subclass of `LockBase`. Wraps a `redis.Redis` client; lock state lives in Redis, not in the Python process.

### State

| Attribute | Type | Initial | Description |
|---|---|---|---|
| `client` | `redis.Redis` | **Not initialized until `connect()` is called** | The active Redis client. |

**No `__init__`** — `client` is set by `connect()`. Until then, accessing `client` raises `AttributeError`. All methods guard against this via `getattr(self, 'client', None)`.

### Property: `is_connected` → `bool`

Returns `getattr(self, 'client', None) is not None`. True only after `connect()` has successfully assigned `client`. Does NOT verify the connection is actually alive — that requires `is_alive`.

### Property: `is_alive` → `bool`

Returns `True` only if the Redis server actually responds to `PING`.

**Step-by-step:**

1. If `client` attribute is missing or `None` → returns `False`.
2. Calls `self.client.ping()`. If it raises `redis.exceptions.ConnectionError` → returns `False`.
3. Otherwise → returns `True`.

**Caveat:** Catches only `ConnectionError`. Other Redis errors (e.g., `TimeoutError`, `AuthenticationError`) will propagate, not return `False`.

### `connect(host, *, port=6379, username=None, password=None, ssl=False, ssl_certfile=None, ssl_keyfile=None, ssl_ca_certs=None) -> None`

Creates a Redis client and stores it as `self.client`.

**Step-by-step:**

1. Calls `self._get_redis_client(host, port=..., username=..., password=..., ssl=..., ssl_certfile=..., ssl_keyfile=..., ssl_ca_certs=...)`.
2. Assigns the returned client to `self.client`.

**Important:** `_get_redis_client` does NOT eagerly verify the connection. `redis.Redis(...)` constructs a client lazily; connection happens on first operation. This means `connect()` can "succeed" even when Redis is unreachable — errors surface on first `acquire()`/`release()`.

### `disconnect() -> None`

Calls `self.client.close()`. **Does NOT** check whether `client` is set — if called before `connect()` (or after a disconnect), raises `AttributeError`.

### `acquire(target_address, *, timeout_ms=-1, blocking=True, metadata=None) -> bool`

Acquires a Redis-based lock for the given address using `SET NX`.

**Step-by-step:**

1. **Connection guard:** If `getattr(self, 'client', None)` is falsy → raises `AmsdalConnectionError('RedisLock is not connected. Call connect() before using this method.')`.
2. Defines inner function `_set_command()`:
   - Calls `self.client.set(target_address.to_string(), value, nx=True)`.
   - `value` is `json.dumps(metadata)` if metadata is non-None, otherwise the empty string `''`.
   - `nx=True` means: set only if key does not exist (atomic).
   - Returns `bool(res)` — `True` if the key was set (lock acquired), `False` if it already existed (lock held by someone else).
3. **Blocking branch** (`blocking=True`):
   - Initializes `_timing = 0.0` and `_timeout_seconds = timeout_ms / 1000.0`.
   - Loop: calls `_set_command()`. If it returns `True` → exits with `True`.
   - If `timeout_ms >= 0` and `_timing >= _timeout_seconds` → exits with the last `_result` (which is `False`).
   - Otherwise: sleeps `0.1` seconds, increments `_timing` by `0.1`, retries.
4. **Non-blocking branch** (`blocking=False`):
   - Single call to `_set_command()`, returns its result immediately.

**Important behavioral notes:**

- **Infinite wait:** `timeout_ms = -1` means no timeout in blocking mode. The loop condition `0 <= _timeout_seconds <= _timing` is false when `_timeout_seconds` is negative, so the loop never exits on timeout. You must have another way to stop the process.
- **Granularity:** Polling interval is hardcoded to `0.1` seconds (100ms). A lock freed 10ms after acquisition attempt still takes up to 100ms to be detected.
- **No lock TTL:** The `SET NX` call has no `EX`/`PX` argument, meaning the key has no expiration. If the holder crashes without releasing, the key persists until manually removed — potential deadlock.
- **Empty metadata vs no metadata:** If `metadata is None`, stores empty string `''`. If `metadata = {}`, stores `'{}'`. Distinct values.
- **Key format:** Uses `target_address.to_string()` as the Redis key. Addresses must have stable string representations.

### `release(target_address) -> None`

Deletes the Redis key to release the lock.

**Step-by-step:**

1. **Connection guard:** Same as `acquire` — if `client` is not set → raises `AmsdalConnectionError('RedisLock is not connected. Call connect() before using this method.')`.
2. Calls `self.client.delete(target_address.to_string())`.

**Important notes:**

- **Not ownership-aware:** Any process calling `release()` with the right address will delete the key, even if another process currently holds the lock. This is unsafe without a separate ownership token — typical distributed lock safety (e.g., Redlock) is NOT implemented.
- **No-op if key doesn't exist:** `DEL` on missing key returns `0` but does not raise.

### Static method: `_get_redis_client(host, *, port=6379, username=None, password=None, ssl=False, ssl_certfile=None, ssl_keyfile=None, ssl_ca_certs=None) -> Any`

Returns a `redis.Redis` client, handling the optional dependency import.

**Step-by-step:**

1. Attempts `import redis` inside the function body.
2. If `ImportError` → raises `ImportError('RedisLock requires the redis package. Use pip "install amsdal_data[redis-lock]"')` with the original exception chained via `from exc`.
3. Returns `redis.Redis(host=host, port=port, username=username, password=password, ssl=ssl, ssl_certfile=ssl_certfile, ssl_keyfile=ssl_keyfile, ssl_ca_certs=ssl_ca_certs)`.

**Note:** `redis` is also imported at the top of the module unconditionally. The inner re-import in `_get_redis_client` serves as an explicit error message but is redundant — if the top-level import fails, the module itself won't load.

---

## Debugging notes

1. **"RedisLock is not connected" error:** Means `connect()` was never called, or `connect()` was called but `client` was somehow unset. Check that the caller initializes the lock properly before use.

2. **Lock never acquired despite Redis being reachable:** Check key collisions — multiple processes might be using the same `target_address` string intentionally or via a bug in address construction.

3. **Stale locks after process crash:** Since keys have no TTL, a crashed process leaves orphan locks. Manual cleanup in Redis required, or implement TTL-based locking externally.

4. **Metadata is JSON-serialized:** Non-JSON-serializable objects in `metadata` raise `TypeError` from `json.dumps`. Not caught.

5. **Polling overhead:** In heavy contention, each process spins at 10Hz against Redis. Consider `blocking=False` with retries at the caller level if you need different backoff.
