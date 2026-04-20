# AMSDAL Claude Code Plugin

Claude Code plugin that gives Claude full knowledge of the AMSDAL framework: models, REST API, ETL, ML, deployment, testing, and the plugin ecosystem.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and working

That's it. The plugin is fully self-contained.

## Quick Start

### 1. Clone the plugin

```bash
git clone git@github.com:amsdal/claude-code-amsdal.git ~/claude-code-amsdal
```

### 2. Install the plugin

Add it as a local marketplace and install:

```bash
claude plugin marketplace add ~/claude-code-amsdal
claude plugin install amsdal@amsdal-plugins
```

This makes the plugin available in every Claude Code session (CLI and Desktop Code tab).

### 3. Verify

Start Claude Code in any directory and ask something like:

> "How do I create an AMSDAL model with a foreign key?"

Claude should know the answer without any extra context.

## Alternative Installation Methods

### Per-project scope

Install for a specific project only (writes to `.claude/settings.json`):

```bash
claude plugin install amsdal@amsdal-plugins --scope project
```

### One-time session (for development/testing)

```bash
claude --plugin-dir ~/claude-code-amsdal
```

## What's Included

### Skills

Skills are contextual knowledge packs that Claude loads automatically based on what you're working on.

**Auto-loaded (Claude picks these up from context):**

| Skill | When | What it knows |
|-------|------|---------------|
| `amsdal-overview` | Always | Architecture, project structure, how to create apps from scratch, conventions |
| `amsdal-models` | Working with models | Fields, relationships, CRUD, QuerySets, transactions, hooks, migrations |
| `amsdal-server` | Working with server | REST API, authentication, permissions, events, health checks |
| `amsdal-glue` | Working with ETL | Connections, CQRS, queries/commands, planners, executors |
| `amsdal-ml` | Working with ML/AI | Embeddings, AI agents, MCP server, semantic search |
| `amsdal-ecosystem` | Using existing plugins | S3 storage, email, CRM, LangGraph, integrations |
| `amsdal-frontend-configs` | Working with frontend | Dynamic forms, controls, conditions, actions, dashboards |
| `amsdal-testing` | Writing tests | pytest patterns, fixtures, utilities |
| `amsdal-plugins` | Creating plugins | AppConfig, events system, custom routes, middleware |

**Manual (invoke explicitly when needed):**

| Command | What it does |
|---------|-------------|
| `/amsdal:amsdal-deploy` | CLI reference, cloud deployment, monitoring |

### Agent: `amsdal-expert`

Deep research agent for questions that require understanding internal behavior — e.g. "why does `QuerySet.get()` return a LegacyModel?", "what does `AmsdalTransactionManager.commit` do on failure?", traceback analysis.

The agent cross-references three sources:

1. **Knowledge base** (bundled with this plugin) — behavioral descriptions of Cython-compiled modules.
2. **`.pyi` stubs** (from your installed AMSDAL packages) — exact API signatures.
3. **Source code** of pure-Python packages (from your venv's `site-packages`) — `amsdal_server`, `amsdal-glue`, `amsdal_cli`, etc.

## Knowledge Base

Core AMSDAL packages (`amsdal`, `amsdal_models`, `amsdal_data`) are compiled via Cython — you only have `.so` binaries and `.pyi` stubs, not Python source. This makes debugging harder because internal behavior isn't visible.

To bridge this gap, the plugin includes a `knowledge/` directory with **behavioral documentation** for every Cython-compiled module. Each file describes step-by-step what the code does internally, edge cases, error conditions, and side effects.

### Structure

The directory mirrors the package layout 1:1:

```
knowledge/
├── amsdal/                              # amsdal_framework internals
│   ├── fixtures/manager.md
│   ├── manager.md
│   ├── services/transaction_execution.md
│   └── ...
├── amsdal_models/
│   ├── classes/
│   │   ├── constants.md
│   │   ├── enums.md
│   │   ├── helpers/reference_loader.md
│   │   └── utils.md
│   ├── querysets/base_queryset.md
│   └── utils/
│       ├── files.md
│       ├── schema_converter.md
│       └── specific_version.md
└── amsdal_data/
    ├── lock/implementations/
    │   ├── redis_lock.md
    │   └── thread_lock.md
    └── transactions/manager.md
```

### How the agent uses it

When you share a traceback like:
```
amsdal_data.transactions.manager.AmsdalTransactionManager.commit
```

The agent finds `knowledge/amsdal_data/transactions/manager.md`, reads the behavioral description of `commit()`, and explains what happens inside — including the order of operations, when `REVERT` is issued, and which errors are raised.

The knowledge base is kept up-to-date with AMSDAL releases.

## What Can Claude Do With This Plugin?

- **Create AMSDAL apps from scratch** — models, transactions, config, fixtures
- **Write models** with fields, relationships, validation, hooks
- **Set up authentication** and permissions
- **Build ETL pipelines** with multi-database queries
- **Integrate ML features** — embeddings, AI agents, MCP server
- **Use existing plugins** — S3 storage, email, CRM, LangGraph
- **Write tests** following AMSDAL patterns
- **Create custom plugins** with events, routes, middleware
- **Help with deployment** — CLI commands, cloud, monitoring
- **Debug production issues** — trace through internal behavior of Cython-compiled modules via the bundled knowledge base
