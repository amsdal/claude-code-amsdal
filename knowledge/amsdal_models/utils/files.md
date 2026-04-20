# Module: `amsdal_models.utils.files`

Small utility module with a single helper for normalizing file data into guaranteed-valid base64-encoded bytes.

---

## `convert_data_to_base64(file_data) -> bytes`

Ensures the returned value is base64-encoded bytes, regardless of whether the input was raw bytes, a raw string, or already base64-encoded content.

**Step-by-step:**

1. **String normalization:** If `isinstance(file_data, str)` → replaces `file_data` with `file_data.encode()` (UTF-8 bytes by default).
2. **Validity check and conditional re-encoding** (wrapped in `try/except Exception`):
   - Attempts `base64.b64decode(file_data, validate=True)` — this raises `binascii.Error` if `file_data` is not valid base64.
   - If decoding succeeded: re-encodes with `base64.b64encode(...).strip()` and compares to the stripped input. If they differ → the data was NOT already clean base64 → overwrites `file_data` with `base64.b64encode(file_data).strip()`.
   - If decoding succeeded AND re-encode matches the input → `file_data` is already valid base64, leaves it unchanged.
3. **Exception branch:** If the decode/encode/compare chain raised **any** exception → treats `file_data` as raw binary and calls `base64.b64encode(file_data).strip()`, storing the result.
4. Returns `file_data` (always `bytes`).

**Behavioral notes:**

- **`.strip()`** is applied to both the comparison target and the final result — this strips trailing whitespace/newlines, which some base64 tools add.
- **Round-trip detection:** The logic distinguishes "already base64" from "raw binary that happens to be valid base64" by round-tripping and comparing — if `b64encode(b64decode(x)) == x`, then `x` is canonical base64 and is kept as-is.
- **Catches `Exception` broadly:** Not just `binascii.Error` — any unexpected error (including `ValueError`, `TypeError`) falls through to "treat as raw bytes". This makes the function tolerant but can hide genuine bugs.
- **No validation of output:** The function always returns bytes, never raises, and never returns the original input as a string (step 1 ensures bytes).

**Edge cases:**

- Empty string `''` → encodes to `b''`, decodes to `b''`, matches → returned as `b''`.
- Raw bytes that happen to be valid base64 (e.g. ASCII text matching `[A-Za-z0-9+/=]+`) → will be re-encoded (the round-trip comparison detects that `b64encode(b64decode(x)) != x` in that case).
- Non-string, non-bytes input (e.g., `int`) → the `isinstance` check is False, the `try` block raises `TypeError` on `b64decode`, caught by `except`, then `b64encode(int)` raises `TypeError` → **unhandled**, propagates up.
