# `amsdal.license.constants`

Module holding constants for the license-guard feature. As of the current source it defines a single module-level constant.

## Symbols

### `DEV_LICENSE_PUBLIC_KEY`

- **Name:** `DEV_LICENSE_PUBLIC_KEY`
- **Type:** `str`
- **Exact value:** `''` (empty string)
- **Mutability:** Plain module-level assignment (not a `Final`, not an enum member). It is reassignable and is monkeypatched in tests.

#### Purpose / semantics

This is the **PEM-encoded public key of a dedicated DEV/CI license key pair**. It is used to validate offline development/CI JWT tokens — explicitly **not** production licenses. The source comments state:

- It validates offline dev/CI tokens, not production licenses.
- The empty string is a **placeholder**: the comment notes it is "Replaced with the real generated key in the dev-key task." So the shipped/default value is empty, and a real key is expected to be substituted by a separate build/generation step.

The empty string acts as a sentinel meaning "no dev key configured": consuming code treats a falsy (empty) value as "dev-key validation disabled".

#### Where it is consumed

The only production consumer found in the repo is the JWT token auth handler:

`amsdal_framework/src/amsdal/cloud/services/auth/token.py`

- Imported at the top of the module: `from amsdal.license.constants import DEV_LICENSE_PUBLIC_KEY`.
- Used inside `TokenAuthHandler._decode_with_accepted_keys()`:

  - The handler builds a list `accepted_keys` starting with the primary public key passed to the handler (defaults to `JWT_PUBLIC_KEY` from `amsdal.cloud.constants`).
  - **Only if `DEV_LICENSE_PUBLIC_KEY` is truthy** (i.e. non-empty), it is appended as an additional accepted key:
    ```
    accepted_keys = [self.public_key]
    if DEV_LICENSE_PUBLIC_KEY:
        accepted_keys.append(DEV_LICENSE_PUBLIC_KEY)
    ```
  - Each accepted key is then tried in turn to `jwt.decode(token, key=key, algorithms=['RS256'])`. A token whose RS256 signature matches **either** the primary key or the dev license key is accepted. If a key yields an `InvalidSignatureError`, the loop continues to the next key; if none match, an `AmsdalAuthenticationError('Invalid signature')` is raised. `ExpiredSignatureError` and `DecodeError` short-circuit immediately with their own errors.

In other words, `DEV_LICENSE_PUBLIC_KEY` lets a JWT signed by the dev/CI private key authenticate alongside the normal production key — but only when a real (non-empty) key has been baked in. With the shipped default `''`, this branch is inactive and only the production/primary key is accepted.

#### Relationship to `amsdal.license.guard`

No direct usage of `DEV_LICENSE_PUBLIC_KEY` was found in `amsdal.license.guard` (`LicenseGuard`). The constant lives under the `amsdal.license` package and is conceptually part of the license-guard feature, but its actual runtime consumer is the cloud auth token validator described above, not `LicenseGuard` itself.

#### Test coverage

`amsdal_framework/tests/unit/auth/test_dev_key_token.py` exercises the constant via monkeypatching `amsdal.cloud.services.auth.token.DEV_LICENSE_PUBLIC_KEY`:

- `test_token_signed_by_dev_key_is_accepted` — sets the constant to a freshly generated RSA public key; a token signed with the matching private key (RS256) validates without raising.
- `test_token_signed_by_unknown_key_is_rejected` — sets the constant back to `''`; a token signed by an unrelated key is rejected with `AmsdalAuthenticationError('Invalid signature')`.

This confirms the runtime contract: empty value disables the dev key, a real PEM public-key value enables acceptance of dev-key-signed RS256 tokens.

## Notes / uncertainties

- The "dev-key task" referenced in the source comment (the mechanism that replaces the empty placeholder with a real generated key) was not located in this repo scan; the substitution appears to happen outside the checked-in source. The expected format is a PEM-encoded RSA public key (consistent with the `RS256` algorithm used for verification).
