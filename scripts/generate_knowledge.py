"""Generate knowledge base from Cython-compiled AMSDAL source files.

Reads COMPILE_FILES from each repo's setup.py, generates behavioral
descriptions, and saves as .md files.

Supports two backends:
  - claude: uses Claude Code CLI (claude -p), no API key needed
  - api:    uses Anthropic Batch API, requires ANTHROPIC_API_KEY

Usage:
    # Local — uses Claude Code (no API key needed)
    python scripts/generate_knowledge.py --backend claude

    # CI — uses Anthropic Batch API (needs ANTHROPIC_API_KEY)
    python scripts/generate_knowledge.py --backend api

    # Common options
    python scripts/generate_knowledge.py --workspace /path/to/repos
    python scripts/generate_knowledge.py --dry-run
    python scripts/generate_knowledge.py --force
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = SCRIPT_DIR.parent
KNOWLEDGE_DIR = PLUGIN_DIR / 'knowledge'
CHECKSUMS_FILE = KNOWLEDGE_DIR / '.checksums.json'

REPOS = {
    'amsdal_framework': {
        'package': 'amsdal',
        'source_dir': Path('src') / 'amsdal',
        # Exclude patterns — paths matching any of these are skipped.
        # cloud/ is CLI/deployment infra, not relevant for AMSDAL app development.
        'exclude': ['amsdal/cloud/'],
    },
    'amsdal_models': {
        'package': 'amsdal_models',
        'source_dir': Path('src') / 'amsdal_models',
        'exclude': [],
    },
    'amsdal_data': {
        'package': 'amsdal_data',
        'source_dir': Path('src') / 'amsdal_data',
        'exclude': [],
    },
}

GENERATION_PROMPT = """\
You are documenting a Python module for developers who cannot see the source code \
(it is compiled via Cython). They only have .pyi stub files with signatures.

Your task: describe the **behavior and internal logic** of every class, method, and function \
in this module so that a developer debugging an issue can understand what happens inside \
without seeing the code. The developer should be able to reason about bugs and unexpected \
behavior using ONLY your description, without ever seeing the source.

Rules:
- For each class: describe its purpose, all state it manages (with types and default values), \
and lifecycle.
- For each method/function: describe step-by-step what it does internally, \
in what order, what conditions it checks, what side effects it has.
- **Be specific about values:** include exact default values, exact string constants, \
exact dict keys, exact format strings, exact parameter names passed to other functions. \
Instead of "serializes the object", write "calls model_dump(exclude=set(['field_x']), mode='json')". \
Instead of "checks the condition", write "checks if context.parent is not None".
- **Include branching logic:** describe every if/elif/else branch and the exact conditions. \
Do not summarize complex conditionals — enumerate each branch.
- **Data shapes:** when a dict, list, or data structure is built, describe its exact keys/fields \
and where each value comes from.
- Mention edge cases, error conditions, and what exceptions are raised and when \
(include exact error message strings).
- Mention important interactions with other modules (imports, calls to external services).
- Do NOT reproduce the source code verbatim. Do NOT include full Python code blocks. \
You may include short pseudo-code snippets or signatures where it aids clarity.
- Use markdown formatting with ## for classes and ### for methods.
- Be precise and technical. Target audience: experienced Python developers debugging production issues.
- Write in English.

Module path: `{module_path}`

Source code:
```python
{source_code}
```\
"""


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------

def update_repos(workspace: Path) -> None:
    """Pull latest changes for all repos in the workspace.

    Handles both submodule-based and standalone repo layouts.
    """
    gitmodules = workspace / '.gitmodules'

    if gitmodules.exists():
        # Submodule-based workspace
        logger.info('Updating submodules in %s ...', workspace)

        result = subprocess.run(
            ['git', 'submodule', 'update', '--init', '--recursive'],
            cwd=workspace,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.warning('git submodule update failed: %s', result.stderr.strip())

        result = subprocess.run(
            ['git', 'submodule', 'foreach', 'git checkout main 2>/dev/null || git checkout master 2>/dev/null; git pull'],
            cwd=workspace,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.warning('git submodule foreach pull failed: %s', result.stderr.strip())
        else:
            logger.info('Submodules updated.')
    else:
        # Standalone repos in a directory
        for repo_name in REPOS:
            repo_path = workspace / repo_name

            if not (repo_path / '.git').is_dir():
                continue

            logger.info('Pulling %s ...', repo_name)

            result = subprocess.run(
                ['git', 'pull'],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.warning('  git pull failed for %s: %s', repo_name, result.stderr.strip())
            else:
                output = result.stdout.strip()
                if output == 'Already up to date.':
                    logger.info('  Already up to date.')
                else:
                    logger.info('  Updated.')


# ---------------------------------------------------------------------------
# Core utilities (shared by both backends)
# ---------------------------------------------------------------------------

def parse_compile_files(setup_py_path: Path) -> list[str]:
    """Extract COMPILE_FILES list from a setup.py using AST parsing."""
    source = setup_py_path.read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'COMPILE_FILES':
                    return [elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)]

    msg = f'COMPILE_FILES not found in {setup_py_path}'
    raise ValueError(msg)


def collect_compiled_files(
    repo_path: Path,
    source_dir: Path,
    compile_patterns: list[str],
    exclude_patterns: list[str],
) -> list[Path]:
    """Collect all .py files that match COMPILE_FILES patterns and are not excluded."""
    full_source_dir = repo_path / source_dir
    compiled_files = []

    for py_file in sorted(full_source_dir.rglob('*.py')):
        relative = py_file.relative_to(repo_path / 'src')
        relative_str = str(relative)

        if not any(pattern in relative_str for pattern in compile_patterns):
            continue

        if any(excl in relative_str for excl in exclude_patterns):
            continue

        compiled_files.append(py_file)

    return compiled_files


def file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_checksums() -> dict[str, str]:
    """Load saved checksums from previous run."""
    if CHECKSUMS_FILE.exists():
        return json.loads(CHECKSUMS_FILE.read_text())
    return {}


def save_checksums(checksums: dict[str, str]) -> None:
    """Save checksums to disk."""
    CHECKSUMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKSUMS_FILE.write_text(json.dumps(checksums, indent=2, sort_keys=True) + '\n')


def get_version(repo_path: Path, source_dir: Path) -> str:
    """Read package version from __about__.py."""
    about_file = repo_path / source_dir / '__about__.py'

    if not about_file.exists():
        return 'unknown'

    source = about_file.read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == '__version__':
                    if isinstance(node.value, ast.Constant):
                        return str(node.value.value)

    return 'unknown'


def knowledge_path_for(package: str, py_file: Path, repo_path: Path) -> Path:
    """Compute the .md output path for a source .py file."""
    relative = py_file.relative_to(repo_path / 'src')
    return KNOWLEDGE_DIR / str(relative).replace('.py', '.md')


def checksums_key(package: str, py_file: Path, repo_path: Path) -> str:
    """Create a stable key for the checksums dict."""
    relative = py_file.relative_to(repo_path / 'src')
    return str(relative)


def build_prompt(module_path: str, source_code: str) -> str:
    """Build the generation prompt for a single file."""
    return GENERATION_PROMPT.format(module_path=module_path, source_code=source_code)


def cleanup_stale_files(all_expected_keys: set[str], checksums: dict[str, str]) -> int:
    """Remove .md files for source files that no longer exist."""
    removed = 0

    for key in list(checksums.keys()):
        if key not in all_expected_keys:
            md_path = KNOWLEDGE_DIR / key.replace('.py', '.md')

            if md_path.exists():
                md_path.unlink()
                logger.info('Removed stale: %s', md_path.relative_to(PLUGIN_DIR))
                removed += 1

            del checksums[key]

    # Also clean up empty directories
    for dirpath in sorted(KNOWLEDGE_DIR.rglob('*'), reverse=True):
        if dirpath.is_dir() and not any(dirpath.iterdir()):
            dirpath.rmdir()

    return removed


# ---------------------------------------------------------------------------
# Backend: Claude Code CLI
# ---------------------------------------------------------------------------

def generate_with_claude_cli(
    files_to_generate: list[tuple[str, Path, Path, str]],
    files_map: dict[str, tuple[Path, str]],
    new_checksums: dict[str, str],
    model: str | None,
) -> None:
    """Generate knowledge files using Claude Code CLI (claude -p)."""
    total = len(files_to_generate)
    succeeded = 0
    failed = 0

    for i, (key, py_file, _repo_path, module_path) in enumerate(files_to_generate, 1):
        source_code = py_file.read_text()

        if not source_code.strip():
            logger.info('[%d/%d] Skipping empty: %s', i, total, key)
            continue

        md_path, source_hash = files_map[key]
        logger.info('[%d/%d] Generating: %s', i, total, key)

        prompt = build_prompt(module_path, source_code)

        cmd = ['claude', '-p', prompt]

        if model:
            cmd.extend(['--model', model])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                failed += 1
                logger.error('  Failed (exit %d): %s', result.returncode, result.stderr[:200])
                continue

            content = result.stdout.strip()

            if not content:
                failed += 1
                logger.error('  Failed: empty response')
                continue

            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(content + '\n')
            new_checksums[key] = source_hash
            succeeded += 1
            logger.info('  Saved: %s', md_path.relative_to(PLUGIN_DIR))

        except subprocess.TimeoutExpired:
            failed += 1
            logger.error('  Timeout: %s', key)

    logger.info('Done: %d succeeded, %d failed out of %d', succeeded, failed, total)


# ---------------------------------------------------------------------------
# Backend: Anthropic Batch API
# ---------------------------------------------------------------------------

def generate_with_batch_api(
    files_to_generate: list[tuple[str, Path, Path, str]],
    files_map: dict[str, tuple[Path, str]],
    new_checksums: dict[str, str],
    model: str,
    poll_interval: int,
) -> None:
    """Generate knowledge files using Anthropic Batch API."""
    import anthropic

    client = anthropic.Anthropic()

    requests = []

    for key, py_file, _repo_path, module_path in files_to_generate:
        source_code = py_file.read_text()

        if not source_code.strip():
            continue

        prompt = build_prompt(module_path, source_code)

        requests.append({
            'custom_id': key,
            'params': {
                'model': model,
                'max_tokens': 8192,
                'messages': [{'role': 'user', 'content': prompt}],
            },
        })

    if not requests:
        logger.info('No non-empty files to generate.')
        return

    logger.info('Sending batch of %d requests...', len(requests))
    batch = client.messages.batches.create(requests=requests)
    logger.info('Batch created: %s', batch.id)

    # Poll for completion
    logger.info('Waiting for batch to complete...')

    while True:
        batch = client.messages.batches.retrieve(batch.id)
        counts = batch.request_counts

        logger.info(
            'Batch status: processing=%d, succeeded=%d, errored=%d',
            counts.processing,
            counts.succeeded,
            counts.errored,
        )

        if batch.processing_status == 'ended':
            break

        time.sleep(poll_interval)

    # Process results
    succeeded = 0
    failed = 0

    for result in client.messages.batches.results(batch.id):
        key = result.custom_id
        md_path, source_hash = files_map[key]

        if result.result.type == 'succeeded':
            md_path.parent.mkdir(parents=True, exist_ok=True)
            content = result.result.message.content[0].text
            md_path.write_text(content + '\n')
            new_checksums[key] = source_hash
            succeeded += 1
            logger.info('Generated: %s', md_path.relative_to(PLUGIN_DIR))
        else:
            failed += 1
            error = getattr(result.result, 'error', None)
            logger.error('Failed: %s — %s', key, error)

    logger.info('Batch complete: %d succeeded, %d failed', succeeded, failed)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def collect_files(workspace: Path, force: bool, checksums: dict[str, str]) -> tuple[
    set[str],
    list[tuple[str, Path, Path, str]],
    dict[str, tuple[Path, str]],
]:
    """Scan repos and collect files that need generation."""
    all_expected_keys: set[str] = set()
    files_to_generate: list[tuple[str, Path, Path, str]] = []
    files_map: dict[str, tuple[Path, str]] = {}

    for repo_name, config in REPOS.items():
        repo_path = workspace / repo_name
        setup_py = repo_path / 'setup.py'

        if not setup_py.exists():
            logger.warning('Repo not found: %s — skipping', repo_path)
            continue

        version = get_version(repo_path, config['source_dir'])
        logger.info('Processing %s v%s', repo_name, version)

        compile_patterns = parse_compile_files(setup_py)
        compiled_files = collect_compiled_files(
            repo_path,
            config['source_dir'],
            compile_patterns,
            config.get('exclude', []),
        )

        logger.info('  Found %d compiled files', len(compiled_files))

        for py_file in compiled_files:
            key = checksums_key(config['package'], py_file, repo_path)

            # Skip trivially-empty files (empty or only whitespace/imports) — no behavior to document
            source = py_file.read_text()
            if len(source.strip()) < 20:
                logger.debug('  Skipping trivial: %s', key)
                continue

            all_expected_keys.add(key)

            current_hash = file_hash(py_file)
            md_path = knowledge_path_for(config['package'], py_file, repo_path)
            module_path = key.replace('/', '.').replace('.py', '')

            if not force and checksums.get(key) == current_hash and md_path.exists():
                logger.debug('  Unchanged: %s', key)
                continue

            files_to_generate.append((key, py_file, repo_path, module_path))
            files_map[key] = (md_path, current_hash)

    return all_expected_keys, files_to_generate, files_map


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate knowledge base from AMSDAL source')
    parser.add_argument(
        '--workspace',
        type=Path,
        default=None,
        help='Path to AMSDAL workspace (default: AMSDAL_WORKSPACE env var)',
    )
    parser.add_argument(
        '--backend',
        choices=['claude', 'api'],
        default='claude',
        help='Generation backend: "claude" for Claude Code CLI, "api" for Anthropic Batch API (default: claude)',
    )
    parser.add_argument('--no-pull', action='store_true', help='Skip git pull (default: pull latest before generating)')
    parser.add_argument('--force', action='store_true', help='Regenerate all files, ignore checksums')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be generated')
    parser.add_argument('--model', default=None, help='Model override (default: depends on backend)')
    parser.add_argument('--poll-interval', type=int, default=30, help='Batch API polling interval in seconds')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of files to generate (for testing)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
    )

    workspace = args.workspace or os.environ.get('AMSDAL_WORKSPACE')

    if not workspace:
        logger.error('No workspace specified. Use --workspace or set AMSDAL_WORKSPACE.')
        sys.exit(1)

    workspace = Path(workspace).resolve()

    if not workspace.is_dir():
        logger.error('Workspace not found: %s', workspace)
        sys.exit(1)

    # Pull latest
    if not args.no_pull:
        update_repos(workspace)

    # Collect files
    checksums = load_checksums()
    new_checksums = dict(checksums)
    all_expected_keys, files_to_generate, files_map = collect_files(workspace, args.force, checksums)

    # Cleanup stale files
    removed = cleanup_stale_files(all_expected_keys, new_checksums)

    if removed:
        logger.info('Cleaned up %d stale files', removed)

    if not files_to_generate:
        logger.info('Nothing to generate — all files up to date.')
        save_checksums(new_checksums)
        return

    logger.info('Files to generate: %d', len(files_to_generate))

    if args.dry_run:
        for key, _, _, module_path in files_to_generate:
            print(f'  Would generate: {key}')
        return

    # Apply limit
    if args.limit and args.limit < len(files_to_generate):
        logger.info('Limiting to %d files (--limit)', args.limit)
        files_to_generate = files_to_generate[:args.limit]

    # Generate
    if args.backend == 'claude':
        generate_with_claude_cli(
            files_to_generate=files_to_generate,
            files_map=files_map,
            new_checksums=new_checksums,
            model=args.model,
        )
    else:
        model = args.model or 'claude-sonnet-4-20250514'
        generate_with_batch_api(
            files_to_generate=files_to_generate,
            files_map=files_map,
            new_checksums=new_checksums,
            model=model,
            poll_interval=args.poll_interval,
        )

    save_checksums(new_checksums)
    logger.info('Checksums saved.')


if __name__ == '__main__':
    main()
