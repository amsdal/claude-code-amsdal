# Module: `amsdal.services.transaction_execution`

This module provides infrastructure for discovering, loading, and executing "transaction" functions — user-defined Python functions decorated with `@transaction` (or `@async_transaction` in async mode) located in a configured transactions directory and in contrib packages. It handles both sync and async execution, argument preprocessing (reference loading, file deserialization), and module-level caching.

## Module-level imports and state

- Standard library: `ast`, `asyncio`, `copy`, `importlib`, `logging`, `types`, `Callable`, `Generator`, `suppress`, `SourceFileLoader`, `Path`, `Any`, `Union`, `get_args`, `get_origin`.
- External: `ReferenceLoader` from `amsdal_models.classes.helpers.reference_loader`, `Model` from `amsdal_models.classes.model`, `AmsdalConfigManager` from `amsdal_utils.config.manager`, `Reference` from `amsdal_utils.models.data_models.reference`, `Singleton` from `amsdal_utils.utils.singleton`.
- Internal: `settings` from `amsdal.configs.main`, `TransactionNotFoundError` from `amsdal.errors`.
- `logger = logging.getLogger(__name__)` — module-level logger named `amsdal.services.transaction_execution`.

## Module-level functions

### `is_transaction(statement: ast.AST) -> bool`

Determines whether an AST node represents a transaction function definition.

Step-by-step:
1. Sets local `transaction_name = 'transaction'`.
2. Calls `AmsdalConfigManager().get_config().async_mode`. If truthy, reassigns `transaction_name = 'async_transaction'`. (The decorator name checked depends on the global async mode flag — sync-mode functions decorated with `@async_transaction` will NOT be detected, and vice versa.)
3. If `statement` is not an instance of `ast.AsyncFunctionDef` or `ast.FunctionDef` → return `False`.
4. If `statement.decorator_list` is empty/falsy → return `False`.
5. Iterates `statement.decorator_list` and returns `True` (via `any(...)`) if ANY decorator matches one of:
   - `isinstance(decorator, ast.Name) and decorator.id in [transaction_name]` — i.e. bare decorator like `@transaction`.
   - `isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id in [transaction_name]` — i.e. called decorator like `@transaction(...)`.
6. Only decorators written as plain names or simple calls to a name are recognized. Attribute-style decorators (e.g. `@module.transaction`) are NOT detected.

### `is_hidden_transaction(statement: ast.AST) -> bool`

Returns `True` only when a transaction decorator is invoked with the keyword `hidden=True` written as a literal boolean `True`. Designed to be resolvable statically from source (no import needed).

Step-by-step:
1. Sets local `transaction_name = 'transaction'`; if `AmsdalConfigManager().get_config().async_mode` is truthy → reassigns to `'async_transaction'` (same async-mode dependency as `is_transaction`).
2. If `statement` is not an `ast.AsyncFunctionDef` or `ast.FunctionDef` → returns `False`.
3. Iterates `statement.decorator_list`:
   - `continue` (skip) any decorator that is NOT a call form (`ast.Call`) with `ast.Name` func whose `id == transaction_name`. Bare `@transaction` (no call) is ignored here.
   - For each matching call decorator, iterates `decorator.keywords`; if a keyword has `kw.arg == 'hidden'` AND `kw.value` is an `ast.Constant` AND `kw.value.value is True` → returns `True`.
4. If no such keyword found across all decorators → returns `False`.

Edge cases: only the literal `True` constant matches. `hidden=1`, `hidden=<variable>`, or any non-`ast.Constant` value does not match.

### `annotation_is_model(annotation: Any) -> bool`

Determines whether a type annotation represents an AMSDAL `Model` subclass (optionally wrapped in a Union/Optional).

Step-by-step:
1. Under `suppress(TypeError)`: calls `issubclass(annotation, Model)`. If true → return `True`. `TypeError` is swallowed silently (e.g. when `annotation` is not a class).
2. Computes `_origin = get_origin(annotation)`.
3. If `_origin is types.UnionType` (PEP 604 `X | Y`) or `_origin is Union` (typing.Union), inspects `get_args(annotation)`:
   - Returns `True` only if **every** argument satisfies: `annotation_is_model(arg)` (recursively) or `arg is None` or `arg is type(None)`.
4. Otherwise → returns `False`.

Effectively accepts: `Model`, `Model | None`, `Optional[Model]`, `Union[ModelA, ModelB, None]`. Rejects: `list[Model]`, `dict[str, Model]`, non-model classes.

## Class: `TransactionExecutionService`

Singleton service (metaclass `Singleton` from `amsdal_utils`) for discovering and executing user-defined transaction functions.

### State

- `self._transactions: dict[str, Callable[..., Any]]` — initialized to `{}` in `__init__`. Caches loaded transaction functions by name. **Note**: the code in `_load_transaction` does NOT populate this cache — it only reads from it in `get_transaction_func`. The cache is therefore effectively always empty unless populated externally, so every `get_transaction_func` call falls through to `_load_transaction`.

### Lifecycle

Singleton: the first `TransactionExecutionService()` call creates the instance with empty `_transactions`; all subsequent calls return the same instance.

### `__init__(self) -> None`

Initializes `self._transactions` to an empty `dict`.

### `execute_transaction(self, transaction_name: str, args: dict[str, Any], *, load_references: bool = True) -> Any`

Synchronous execution entry point.

Step-by-step:
1. Calls `self.get_transaction_func(transaction_name=transaction_name)`. Raises `TransactionNotFoundError` if not found (propagates up).
2. Creates `args_copy = copy.deepcopy(args)` — the input dict is never mutated.
3. Argument preprocessing, wrapped in `suppress(Exception)` — **any exception during preprocessing is silently swallowed**, leaving `args_copy` partially preprocessed:
   - Locally imports `from amsdal.models.core.file import File`. If this import fails (model not available), the entire preprocessing block is skipped via `suppress`.
   - Reads `annotations = transaction_func.__annotations__`.
   - Iterates over `args_copy.items()` (field_name, value). For each item where `field_name in annotations and isinstance(value, dict)`:
     - **Reference branch**: if `load_references` is truthy AND `list(value.keys()) == ['ref']` (exactly one key, `'ref'`) AND `isinstance(value['ref'], dict)` AND `annotation_is_model(annotations[field_name])` → replaces value with `ReferenceLoader(Reference(**value)).load_reference()`. Uses the synchronous `load_reference()`.
     - **File branch**: `elif sorted(value.keys()) == ['data', 'filename']` AND `issubclass(annotations[field_name], File)` → replaces value with `File(**value)`. `issubclass` on non-class annotations raises `TypeError` — silently suppressed.
     - Otherwise: value left unchanged.
4. Execution, inside `try`:
   - If `asyncio.iscoroutinefunction(transaction_func)` is `True` → calls `self._run_async_transaction(transaction_func, args_copy)`.
   - Else → calls `transaction_func(**args_copy)` directly.
5. `except Exception`: calls `logger.exception('Failed to execute transaction=%s, args=%s', *(transaction_name, args_copy), exc_info=True)` and re-raises via bare `raise`. The log includes the full (post-preprocessing) args dict.
6. `else`: returns `transaction_result`.

### `async_execute_transaction(self, transaction_name: str, args: dict[str, Any], *, load_references: bool = True) -> Any`

Asynchronous execution entry point. Nearly identical to `execute_transaction` with two differences:

1. **Reference branch behavior**: instead of `ReferenceLoader(Reference(**value)).load_reference()`, assigns `args_copy[field_name] = await Reference(**value)`. `Reference` is awaitable (it defines `__await__`, which delegates to `self.aload().__await__()`), so awaiting it asynchronously resolves the reference into the loaded model instance. This is the async counterpart of the sync branch's `ReferenceLoader(...).load_reference()`. If resolution raises, the surrounding `suppress(Exception)` swallows it and the field remains the raw `{'ref': {...}}` dict.
2. **Execution branch**:
   - If `asyncio.iscoroutinefunction(transaction_func)` → `transaction_result = await transaction_func(**args_copy)`.
   - Else → `transaction_result = transaction_func(**args_copy)` (called synchronously within the async context — blocking).
3. Error logging and re-raise behavior identical to the sync version.

### `get_transaction_func(self, transaction_name: str) -> Callable[..., Any]`

Lookup with cache-then-load pattern.

Step-by-step:
1. If `transaction_name in self._transactions` → returns `self._transactions[transaction_name]`.
2. Otherwise → returns `self._load_transaction(transaction_name)`.

As noted, the cache is never populated internally, so step 2 always runs — every execution re-scans the filesystem and re-executes the module. This has performance implications for large transaction directories and means module-level side effects run on every transaction invocation.

### `_run_async_transaction(transaction_func, args) -> Any` (staticmethod)

Step-by-step:
1. `loop = asyncio.get_event_loop()` — retrieves the current thread's event loop (or creates one on older Python versions; on Python 3.12+ this emits `DeprecationWarning` when no running loop).
2. Returns `loop.run_until_complete(transaction_func(**args))`.

Will raise `RuntimeError` if called when a loop is already running in the current thread (e.g. from inside another coroutine). Designed to be called only from `execute_transaction` (sync path).

### `_load_transaction(self, transaction_name: str) -> Callable[..., Any]`

Scans for, imports, and returns the named transaction function.

Step-by-step:
1. Iterates `self.iter_transaction_definitions()` — yielding `(definition, file_path)` tuples where `definition` is an `ast.FunctionDef`/`ast.AsyncFunctionDef` and `file_path` is a `pathlib.Path`.
2. Skips entries where `definition.name != transaction_name`.
3. On match:
   - Constructs `loader = SourceFileLoader(file_path.stem, str(file_path.absolute()))` — loader name is the file's stem (filename without extension).
   - Creates a fresh module object: `transaction_module = types.ModuleType(loader.name)`.
   - Executes it: `loader.exec_module(transaction_module)`. **This runs the entire Python file top-level**, including all imports and decorators — side effects (e.g. registration) fire here every call.
   - Returns `getattr(transaction_module, transaction_name)` — the live decorated function object.
   - Does NOT insert into `self._transactions`. The module is not inserted into `sys.modules`, so subsequent loads of the same file create a brand-new module object and a brand-new function.
4. If the loop exhausts without matches → raises `TransactionNotFoundError(f'Transaction {transaction_name} not found')`.

### `iter_transaction_definitions(cls) -> Generator[tuple[ast.FunctionDef | ast.AsyncFunctionDef, Path], None, None]` (classmethod)

Enumerates all transaction functions across the main transactions path and contrib packages.

Step-by-step:
1. First yields from `cls._iterate_module(settings.transactions_root_path)` — scans the configured project-level transactions root.
2. Iterates `settings.CONTRIBS`. For each `contrib_config` (expected to be a dotted path like `some.package.AppConfig`):
   - Computes `package_name = contrib_config.rsplit('.', 2)[0]` — strips the last TWO dotted segments (e.g. `some.package.AppConfig` → `some`). **Note**: this is `rsplit('.', 2)[0]`, not `rsplit('.', 1)[0]`. If `contrib_config` has fewer than 2 dots, the entire string is returned.
   - Attempts `importlib.import_module(package_name)`. On `ImportError` → skips this contrib and continues.
   - If the imported module has `__path__` attribute (i.e. is a package):
     - Takes the first path: `contrib_package_path = Path(contrib_module.__path__[0])`.
     - Builds `transactions_path = contrib_package_path / 'transactions'`.
     - If `transactions_path.exists()` AND `transactions_path.is_dir()` → yields from `cls._iterate_module(transactions_path)`.
   - If no `__path__` attribute → silently skips (no exception).

### `_iterate_module(cls, module_path: Path) -> Generator[...]` (classmethod)

Recursive filesystem walker yielding transaction AST nodes.

Step-by-step:
1. If `not module_path.exists()` → returns silently (empty generator).
2. Elif `module_path.is_dir()`: iterates `module_path.iterdir()` and recursively `yield from cls._iterate_module(file)` for each entry. **Does NOT skip dunder directories** (`__pycache__`, `__init__.py` parent dirs) or hidden files — everything is recursed.
3. Elif `module_path.suffix == '.py'`: `yield from cls._iterate_file(module_path)`.
4. Non-`.py` files that are not directories (e.g. `.pyc`, `.md`) are silently skipped.

### `_iterate_file(cls, file_path: Path) -> Generator[...]` (classmethod)

Parses a single `.py` file and yields transaction definitions.

Step-by-step:
1. `transactions_content = file_path.read_text()` — default encoding; can raise `UnicodeDecodeError` on non-UTF-8 files. Not caught here — propagates up.
2. `tree = ast.parse(transactions_content)` — can raise `SyntaxError` on invalid Python. Not caught here.
3. Iterates `ast.walk(tree)` (visits every node in the tree, including nested function definitions inside classes or other functions).
4. For each node, skips unless `is_transaction(definition)` returns `True`.
5. Yields `(definition, file_path)` tuple.

Because `ast.walk` traverses the entire tree, nested transaction-decorated functions (e.g. inside a class body) would be discovered — though `_load_transaction` loads the whole module and does `getattr(module, transaction_name)`, which only finds top-level names. Nested discovered definitions would fail at the `getattr` step with `AttributeError` (uncaught, propagated).

## Key behaviors and pitfalls for debugging

- **Async-mode decorator name depends on global config**: if `AmsdalConfigManager().get_config().async_mode` is `True`, only `@async_transaction`-decorated functions are discovered; if `False`, only `@transaction`. Switching modes without updating decorators makes transactions "disappear" from `iter_transaction_definitions`.
- **Cache never populated**: every call to `get_transaction_func` triggers a full filesystem scan plus `exec_module` of the matching file. Module top-level side effects execute repeatedly.
- **Preprocessing errors silently swallowed**: the `suppress(Exception)` block around argument preprocessing means failures in `Reference(**value)` construction, `ReferenceLoader.load_reference()`, or `File(**value)` are invisible — the transaction receives the raw dict instead of the resolved object.
- **Async reference branch**: `await Reference(**value)` in `async_execute_transaction` resolves the reference asynchronously (`Reference.__await__` → `aload()`); this is the correct async equivalent of the sync `ReferenceLoader(...).load_reference()`. Only on a resolution error (swallowed by `suppress`) does the field remain unresolved.
- **Error logging**: on execution failure, logs at `ERROR` level with message `'Failed to execute transaction=%s, args=%s'`, includes full traceback via `exc_info=True`, then re-raises the original exception.
- **Decorator detection is syntactic**: only works for `@transaction` or `@transaction(...)` written as bare names — `@amsdal.transaction` or `@aliased_decorator` will not be detected.
- **Contrib path parsing**: `contrib_config.rsplit('.', 2)[0]` assumes a dotted config path with at least two dots — e.g. `pkg.app.AppConfig` → `pkg`. Shorter paths yield the full string, which may not be the intended package.
