# Module: `amsdal_models.utils.specific_version`

Trivially small module containing a single type alias used as a sentinel/marker.

---

## `SpecificVersion`

**Definition:** `class SpecificVersion(str): ...`

A `str` subclass with an empty body. Used as a distinct type to mark that a value represents a specific version identifier (rather than the `Versions.LATEST` enum or a plain string).

**Usage pattern:** Code that needs to distinguish "specific version string" from "arbitrary string" checks with `isinstance(value, SpecificVersion)`. A regular string literal won't pass this check — it must be explicitly wrapped: `SpecificVersion("v1.2.3")`.

**Behavior:** Inherits everything from `str`. All string operations (concatenation, slicing, formatting) work as normal. Instances compare equal to regular strings with the same content (because `str.__eq__` compares by content).

**Implications for debugging:**
- `SpecificVersion("abc") == "abc"` is `True` (string equality).
- `isinstance(SpecificVersion("abc"), str)` is `True`.
- `isinstance("abc", SpecificVersion)` is `False` — only wrapping makes it pass.
- Serialization (e.g., to JSON) produces a plain string — round-tripping through JSON loses the `SpecificVersion` type, it comes back as `str`.
