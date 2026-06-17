# `amsdal.license.guard`

Process-level license validation gate for AMSDAL. The module exposes a single class, `LicenseGuard`, which validates the AMSDAL license **exactly once per Python process** and caches the result at class scope.

The package `__init__` (`amsdal/license/__init__.py`) re-exports only `LicenseGuard`:

```python
from amsdal.license.guard import LicenseGuard
__all__ = ['LicenseGuard']
```

> Note on the sibling module `amsdal.license.constants`: it currently defines exactly one symbol, `DEV_LICENSE_PUBLIC_KEY` (a module-level `str`, current value `''` — empty string). Its docstring states it is the public key of the dedicated DEV/CI license key pair, used to validate offline dev/CI tokens (NOT production licenses), and is meant to be replaced with the real generated key in the "dev-key" task. **`guard.py` does NOT import or reference `DEV_LICENSE_PUBLIC_KEY` at all** — the constant is unused by the guard in the current source. No symbols from `amsdal.license.constants` are referenced by `LicenseGuard`.

---

## `class LicenseGuard`

Purpose: a process-wide gate that ensures the AMSDAL license is validated once and only once, then caches the outcome so repeated calls are cheap no-ops.

### State (all class-scoped, no instance state)

| Attribute | Scope | Type | Default | Meaning |
|-----------|-------|------|---------|---------|
| `_validated` | class attribute | `bool` | `False` | Whether the license has already been successfully validated in this process. Set to `True` only after a successful validation call; reset to `False` by `reset()`. |

There is no `__init__`; the class is never instantiated by its own API. All three public methods are `@classmethod`s and operate on the class object (`cls`). Because `_validated` lives at class scope, the cached result **intentionally survives** `AmsdalManager.invalidate()` / `teardown()` — a re-created manager does NOT trigger re-validation. This is by design so that per-test / per-request setup does not incur repeated cloud authentication calls. The only ways to clear the cache are calling `LicenseGuard.reset()` or starting a fresh process.

### Lifecycle

1. First call to `ensure_valid()` while `_validated is False` performs the real validation (a cloud authentication round-trip via `AuthManager`).
2. On success, `_validated` is flipped to `True`; every later `ensure_valid()` returns immediately.
3. `is_valid()` reports the cached flag without performing validation.
4. `reset()` clears the flag, re-arming a future `ensure_valid()` to validate again.

---

### `@classmethod ensure_valid(cls) -> None`

Validate the license once; subsequent calls are no-ops.

Step-by-step internal behavior, in order:

1. **Branch — cache check:** `if cls._validated:` → if the flag is already `True`, `return` immediately. No authentication is performed, no side effects. (This is the only `if`; there is no explicit `else`.)
2. If the flag is `False`, perform a **lazy import** inside the method body:
   `from amsdal.cloud.services.auth.manager import AuthManager`. The import is deliberately local (inside the method, not at module top) to avoid import-time coupling / circular imports and to keep module import cheap.
3. Construct an `AuthManager` instance with no arguments: `AuthManager()`, and immediately call `.authenticate()` on it: `AuthManager().authenticate()`. This is the actual license/credential enforcement step (see "Validation / enforcement chain" below).
4. **Only if** `authenticate()` returns without raising, set `cls._validated = True`. The cache is updated last, so a failed authentication leaves `_validated` as `False` and a later call will retry.

Side effects:
- Triggers a credential validation through `AuthManager` (may perform a network/cloud round-trip depending on the configured auth handler).
- Mutates the class attribute `LicenseGuard._validated` to `True` on success.

Return value: `None`.

Failure behavior: `ensure_valid` does **not** catch or wrap exceptions. Any exception raised by `AuthManager()` construction or by `authenticate()` propagates unchanged to the caller, and `_validated` stays `False`. See the enforcement chain for the concrete exception types.

---

### `@classmethod is_valid(cls) -> bool`

Returns the cached validation flag.

Behavior:
- Single statement: `return cls._validated`.
- Performs **no** validation, no import, no network call. It is a pure read of the class flag.
- Returns `True` if `ensure_valid()` previously succeeded in this process (and `reset()` has not been called since), otherwise `False`.

No side effects.

---

### `@classmethod reset(cls) -> None`

Clear the cached validation state — a test/teardown helper.

Behavior:
- Single statement: `cls._validated = False`.
- After calling this, the next `ensure_valid()` will perform full validation again.
- No return value (`None`), no import, no network call. Pure flag reset.

---

## Validation / enforcement chain (what `ensure_valid` actually triggers)

`ensure_valid()` delegates the real work to `AuthManager().authenticate()` from `amsdal.cloud.services.auth.manager`. To debug a license failure, understand this downstream chain:

### `AuthManager.__init__(self, auth_type: AuthType | None = None)`

`AuthManager` uses the `Singleton` metaclass (from `amsdal_utils.utils.singleton`), so within a process there is effectively one instance per constructor-arg signature. `LicenseGuard` always calls it as `AuthManager()` (i.e. `auth_type=None`). Construction logic, in order:

1. **If** `auth_type is None and settings.AUTH_TYPE` (a truthy `settings.AUTH_TYPE` string):
   try `auth_type = AuthType[settings.AUTH_TYPE.upper()]`.
   - On `KeyError`: raise `AmsdalAuthenticationError` with message
     `f'Invalid AMSDAL_AUTH_TYPE: {settings.AUTH_TYPE!r} (expected "token" or "credentials")'`
     (chained `from e`).
2. **If** `auth_type is None` still (no explicit type, `AUTH_TYPE` unset/empty): infer from credentials in `settings`:
   - **If** `settings.ACCESS_KEY_ID and settings.SECRET_ACCESS_KEY` → `auth_type = AuthType.CREDENTIALS`.
   - **elif** `settings.ACCESS_TOKEN` → `auth_type = AuthType.TOKEN`.
   - (implicit else: `auth_type` remains `None`).
3. **If** `auth_type is None` (nothing inferred): raise `AmsdalMissingCredentialsError` with message `'Missing authentication credentials'`. — This is the typical exception when **no license/credentials are configured**.
4. Select the handler:
   - **If** `auth_type == AuthType.TOKEN` → `self._auth_handler = TokenAuthHandler(settings.ACCESS_TOKEN)`.
   - **elif** `auth_type == AuthType.CREDENTIALS` → `self._auth_handler = CredentialsAuthHandler(settings.ACCESS_KEY_ID, settings.SECRET_ACCESS_KEY)`.
   - **else** → raise `AmsdalAuthenticationError` with message `f'Invalid authentication type: {auth_type}'`.

`self._auth_handler` is typed `AuthHandlerBase` and is the only instance attribute.

### `AuthManager.authenticate(self) -> None`

- Single delegation: `self._auth_handler.validate_credentials()`.
- Documented to raise `AmsdalAuthenticationError` if authentication fails. The concrete validation (and any network/cloud call, signature/expiry checks, etc.) is performed inside the selected handler (`TokenAuthHandler` or `CredentialsAuthHandler`) `validate_credentials()` method — not in `guard.py` or `AuthManager` itself.

### Settings consulted (`amsdal.configs.main.settings`)

- `settings.AUTH_TYPE` — env-driven auth type string (expected `"token"` or `"credentials"`, case-insensitive via `.upper()`).
- `settings.ACCESS_KEY_ID`, `settings.SECRET_ACCESS_KEY` — used for `CREDENTIALS` auth.
- `settings.ACCESS_TOKEN` — used for `TOKEN` auth.

### Exception types a license debugger may see from `ensure_valid()`

| Exception | Source / condition |
|-----------|--------------------|
| `AmsdalMissingCredentialsError` (msg `'Missing authentication credentials'`) | No `AUTH_TYPE` and no usable credentials/token in `settings`. |
| `AmsdalAuthenticationError` (msg `f'Invalid AMSDAL_AUTH_TYPE: {...!r} ...'`) | `settings.AUTH_TYPE` not a valid `AuthType` member. |
| `AmsdalAuthenticationError` (msg `f'Invalid authentication type: {auth_type}'`) | `auth_type` resolved to a value that is neither `TOKEN` nor `CREDENTIALS`. |
| `AmsdalAuthenticationError` (per handler docstring) | Underlying handler `validate_credentials()` rejects the license (e.g. invalid signature, expired, revoked — enforced inside the handler). |

Both error classes come from `amsdal.errors`. All of these propagate out of `LicenseGuard.ensure_valid()` unmodified, and leave `LicenseGuard._validated == False` so a corrected configuration can be retried.

---

## Debugging quick-reference

- "License keeps passing even after teardown / config change" → `_validated` is a class-level cache that survives manager teardown by design; call `LicenseGuard.reset()` (or restart the process) to force re-validation.
- "License never re-checks within tests" → same cause; use `reset()` between tests.
- "`is_valid()` returns `False` but I never saw an error" → `ensure_valid()` was never called, or `reset()` was called; `is_valid()` does not validate, it only reads the flag.
- "Validation fails immediately with missing-credentials" → no auth config present (`AmsdalMissingCredentialsError`); check `AMSDAL_AUTH_TYPE`, `ACCESS_KEY_ID`/`SECRET_ACCESS_KEY`, `ACCESS_TOKEN` settings.
- `amsdal.license.constants.DEV_LICENSE_PUBLIC_KEY` is currently `''` and unused by the guard — do not assume the guard performs offline key verification with it in this source version.
