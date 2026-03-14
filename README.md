# AMSDAL Claude Code Plugin

Claude Code plugin that gives Claude full knowledge of the AMSDAL framework: models, REST API, ETL, ML, deployment, testing, and the plugin ecosystem.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and working
- Git + SSH access to AMSDAL repositories (for source code access)

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

### 3. Set up AMSDAL source workspace (recommended)

Start Claude Code and run the built-in command:

```
/amsdal:amsdal-workspace
```

This will:
- Clone all AMSDAL repos as git submodules into one directory
- Set `AMSDAL_WORKSPACE` in your shell profile permanently
- Run it again later to pull the latest changes for all repos

### 4. Verify

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
| `/amsdal:amsdal-workspace` | Clone or update all AMSDAL source repositories |
| `/amsdal:amsdal-deploy` | CLI reference, cloud deployment, monitoring |

### Agent

| Agent | What it does |
|-------|-------------|
| `amsdal-expert` | Deep research agent that reads actual AMSDAL source code. Use for questions like "what does X method actually do?" |

## Source Code Access

The `amsdal-expert` agent searches through locally cloned AMSDAL repos. This is useful because:

- Documentation can be outdated, source code is always current
- Tests show real usage patterns
- You can check actual API signatures

### Setup with command (recommended)

```
/amsdal:amsdal-workspace
```

### Manual setup

If you already have repos cloned, just set the env var. Add to your shell profile:

**zsh** (`~/.zshrc`):
```bash
export AMSDAL_WORKSPACE=/path/to/your/amsdal_repos
```

**bash on macOS** (`~/.bash_profile`):
```bash
export AMSDAL_WORKSPACE=/path/to/your/amsdal_repos
```

**bash on Linux/WSL** (`~/.bashrc`):
```bash
export AMSDAL_WORKSPACE=/path/to/your/amsdal_repos
```

**fish**:
```bash
set -Ux AMSDAL_WORKSPACE /path/to/your/amsdal_repos
```

Expected layout under `$AMSDAL_WORKSPACE`:
```
amsdal_framework/    amsdal_models/    amsdal_data/
amsdal_server/       amsdal_utils/     amsdal-glue/
amsdal_cli/          amsdal_ml/        amsdal_crm/
amsdal_mail/         amsdal_storages/  amsdal_langgraph/
amsdal_integrations/
```

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