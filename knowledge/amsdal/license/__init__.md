# `amsdal.license` (package `__init__.py`)

## Overview

The package `__init__.py` is a **pure re-export module**. It contains no logic of its own.

- It imports `LicenseGuard` from `amsdal.license.guard`.
- It defines `__all__ = ['LicenseGuard']`.

So the only public symbol exposed at `amsdal.license` is **`LicenseGuard`** (sourced from `amsdal.license.guard`). Importing `from amsdal.license import LicenseGuard` is equivalent to `from amsdal.license.guard import LicenseGuard`.

The sibling module `amsdal.license.constants` is **not** re-exported here; it must be imported directly (see below).

---

## `LicenseGuard` (from `amsdal.license.guard`)

Process-level license validation gate. Validates the AMSDAL license **exactly once per process** and caches the result. The cache is stored at **class scope**, so it intentionally **survives** `AmsdalManager.invalidate()` / `teardown()`: a re-created manager does not trigger re-validation. This keeps per-test / per-request setup free of repeated cloud calls.

### State (class-level attributes)

| Attribute    | Type   | Default | Scope | Meaning |
|--------------|--------|---------|-------|---------|
| `_validated` | `bool` | `False` | class | `True` once the license has been successfully validated in this process; gate flag for the one-shot behavior. |

There is no `__init__`; the class is used purely via classmethods. All state lives on the class object itself, shared across all references and all (re-)created managers in the same process.

### `ensure_valid() -> None` (classmethod)

Validate the license once; subsequent calls are no-ops.

Step-by-step:
1. If `cls._validated` is truthy (`True`) → `return` immediately (no-op; nothing else runs). This is the cached fast path.
2. Otherwise, perform a **lazy local import**: `from amsdal.cloud.services.auth.manager import AuthManager`. (Imported inside the method to avoid import-time cycles / cloud dependencies at module load.)
3. Construct `AuthManager()` with **no arguments** and call `.authenticate()` on it.
4. Set `cls._validated = True`.

Important interaction details / side effects:
- `cls._validated` is set to `True` **only after** `AuthManager().authenticate()` returns successfully. If `AuthManager()` construction or `authenticate()` raises, `_validated` stays `False` and the exception propagates to the caller. A subsequent call will therefore retry.
- `AuthManager` is a `Singleton` (metaclass `Singleton`), so repeated construction returns the same instance with the auth type/handler decided on first construction.
- `AuthManager()` (no `auth_type`) selects the handler from `amsdal.configs.main.settings`:
  - If `settings.AUTH_TYPE` is set, it is upper-cased and looked up in `AuthType`; an invalid value raises `AmsdalAuthenticationError` with message `Invalid AMSDAL_AUTH_TYPE: <value!r> (expected "token" or "credentials")`.
  - Else, if `settings.ACCESS_KEY_ID` and `settings.SECRET_ACCESS_KEY` are both set → `AuthType.CREDENTIALS`; else if `settings.ACCESS_TOKEN` is set → `AuthType.TOKEN`.
  - If still undetermined → raises `AmsdalMissingCredentialsError` with message `Missing authentication credentials`.
- `authenticate()` delegates to the chosen handler's `validate_credentials()`; on failure it raises `AmsdalAuthenticationError` (per the handler). Any such exception bubbles up through `ensure_valid` unchanged.

### `is_valid() -> bool` (classmethod)

Returns the current cached flag `cls._validated` directly. Pure read; **no** side effects, **no** validation triggered. Returns `True` only if `ensure_valid()` has previously completed successfully (and `reset()` has not been called since).

### `reset() -> None` (classmethod)

Clears cached validation state — a test / teardown helper.

Step:
1. Sets `cls._validated = False`.

Side effect: after `reset()`, the next `ensure_valid()` call will re-run the full `AuthManager().authenticate()` flow (a cloud/credential call). `is_valid()` will return `False` until then.

---

## `amsdal.license.constants` (sibling module — not re-exported)

Defines a single module-level constant:

| Name                     | Type  | Exact value | Purpose |
|--------------------------|-------|-------------|---------|
| `DEV_LICENSE_PUBLIC_KEY`  | `str` | `''` (empty string) | Public key of the dedicated DEV/CI license key pair, used to validate **offline dev/CI tokens** — NOT production licenses. Currently an empty placeholder; intended to be replaced with the real generated key in the dev-key task. |

Note: as of this source, the value is an empty string `''`. Any code that relies on `DEV_LICENSE_PUBLIC_KEY` to verify dev/CI tokens will be operating with an empty key until it is populated.

---

## Debugging notes / edge cases

- **Once-per-process caching:** Because `_validated` is class-level and never cleared by manager teardown, a single successful `ensure_valid()` makes all later calls no-ops for the lifetime of the process. To force re-validation in a test, call `LicenseGuard.reset()` first.
- **Failure does not poison the cache:** A raised exception during validation leaves `_validated = False`, so the next call retries (it does not permanently mark the license invalid).
- **No explicit "invalid" state:** `LicenseGuard` has no boolean for "validated and failed". Validation either succeeds (sets `_validated = True`) or raises. `is_valid()` returning `False` means "not yet validated / was reset", not "validation failed".
- **Credential resolution happens in `AuthManager`, not `LicenseGuard`.** Errors like missing credentials (`AmsdalMissingCredentialsError: Missing authentication credentials`) or bad auth type (`AmsdalAuthenticationError`) originate from `AuthManager.__init__`, surfaced through `ensure_valid()`.
