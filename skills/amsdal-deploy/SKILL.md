---
name: amsdal-deploy
description: >
  AMSDAL CLI commands reference, cloud deployment, monitoring, secrets, migrations CLI.
  TRIGGER when: user asks about CLI commands, deployment, cloud environments, secrets, monitoring, CI/CD, or running amsdal serve/build/verify.
  DO NOT TRIGGER when: user writes application code without needing CLI reference.
user-invocable: true
---

# AMSDAL Deployment & CLI

## Before you commit to anything concrete

This skill is a routing index, not a complete or current spec. Before you finalize ANY concrete artifact — a CLI command or flag, a deploy/secret/env setting, a config key, a command sequence — confirm it against an authoritative source FIRST:

1. `knowledge/` — if it concerns runtime behavior / debugging.
2. WebFetch the matching `docs.amsdal.com` page (map below) — for API / usage.

Do this by default, NOT only when uncertain — you cannot detect what this skill silently omits.

**Docs map for this skill:**
- CLI commands / scaffolding (`amsdal new`, `amsdal generate`, …) → https://docs.amsdal.com/cli/overview/
- cloud deploy / environments / secrets → https://docs.amsdal.com/cli/cloud/
- monitoring → https://docs.amsdal.com/cli/monitoring/

## Installation

```bash
pip install amsdal[cli]
```

## Credentials & commands that require them

Some commands need AMSDAL credentials. On missing/invalid credentials they launch an **interactive sign-up prompt** — which in a non-interactive shell (an agent's Bash) hangs or aborts with no useful error. **Do not run these blindly.**

**Require credentials:**
- `amsdal serve`
- every `amsdal cloud …` subcommand (deploy, secret, environment, dependency, security, external-connections, expose-db, monitoring, tunnel-db, sync-db, gen-token).

**Do NOT require credentials** (safe to run while building locally): `amsdal new`, `amsdal build`, `amsdal migrations new`, `amsdal generate …`, `amsdal tests` / `amsdal verify`.

**Before running a credential-requiring command:** check that `AMSDAL_ACCESS_KEY_ID` and `AMSDAL_SECRET_ACCESS_KEY` are set (in the environment or the project `.env`; an `auth_token` may also be cached under the config dir).

```bash
test -n "$AMSDAL_ACCESS_KEY_ID" && test -n "$AMSDAL_SECRET_ACCESS_KEY" && echo creds-present || grep -qsE 'AMSDAL_ACCESS_KEY_ID' .env && echo creds-in-env-file || echo NO-CREDS
```

If credentials are absent, **stop and ask the user** to either add the keys to `.env` or complete the interactive auth flow themselves (only they can register / obtain keys) — e.g. by running the command with a `! ` prefix so it runs interactively in-session. Then continue. Never try to satisfy the sign-up prompt yourself.

## CLI Commands Reference

### Project Scaffolding

```bash
amsdal new <APP_NAME> <OUTPUT_PATH>       # Create new application
```

### Code Generation

```bash
amsdal generate model Person -attrs "first_name:string last_name:string email:string:required:index age:number:default=21"
amsdal generate property --model Person full_name
amsdal generate modifier --model PersonProfile constructor
amsdal generate hook --model Person post_create
amsdal generate transaction CreateOrder
amsdal generate tests --model-name Person
amsdal generate external-models <connection> [-t table] [-o output_dir] [-f python|json]
amsdal generate permission --model Person                      # Permission fixtures (create/read/update/delete)
amsdal generate permission --model Person --no-delete          # Skip a specific action
amsdal generate frontend_config --model Person                 # Frontend config (ui.json) fixture for a model
```

**Generate subcommand aliases:** `model`/`mdl`/`md`, `property`/`prop`/`pr`, `modifier`/`mod`/`mdf`, `hook`/`hk`/`h`, `transaction`/`tr`/`t`, `permission`/`p`, `frontend_config`/`fconfig`/`fcfg`/`fc`, `external-models`/`ext-models`/`em`.

**Attribute types:** `string`, `number`, `boolean`, `belongs-to:Model`, `has-many:Model`, `dict:string:Model`
**Attribute options:** `:required`, `:index`, `:unique`, `:default=value`

### Build & Verify

```bash
amsdal build                              # Build app, generate models
amsdal verify                             # Check syntax
amsdal verify --building                  # Check syntax + model building
amsdal clean                              # Clean generated files
amsdal clean --remove-db                  # Clean + remove database
```

### Local Server

```bash
amsdal serve                              # Start on port 8080
amsdal serve --host 0.0.0.0 --port 8000
amsdal serve --auto-reload
amsdal serve --no-apply-fixtures
```

### Migrations

```bash
amsdal migrations                         # List all migrations
amsdal migrations new                     # Generate schema migration
amsdal migrations new --data --name populate_roles  # Data migration
amsdal migrations apply                   # Apply all pending
amsdal migrations apply --number 0003     # Apply/rollback to specific
amsdal migrations apply --fake            # Mark as applied without executing
```

**Aliases:** `amsdal migs`, `amsdal migs n`, `amsdal migs apl`

### Testing

```bash
amsdal tests                                              # Run all tests (alias: amsdal test)
amsdal tests --state-option postgres --lakehouse-option postgres   # Run against postgres
amsdal tests --db-execution-type lakehouse_only          # Lakehouse-only execution
amsdal tests -- -k test_name -x                          # Extra args after -- pass through to pytest
```

`db-execution-type`: `include_state_db` (default), `lakehouse_only`.
`state-option` / `lakehouse-option`: `sqlite` (default), `postgres`.

### Workers

```bash
amsdal worker run                         # Background task worker (default mode: executor)
amsdal worker run --mode executor         # Execute tasks
amsdal worker run --mode scheduler        # Create scheduled tasks only
amsdal worker run --mode hybrid           # Execute tasks + create scheduled tasks
```

### External Connections

```bash
amsdal reg-conn sqlite -creds db_path=path/to/db.sqlite3
amsdal reg-conn postgres -creds dsn='postgresql://user:pass@host:5432/db' -creds schema=public
amsdal reg-conn csv -creds db_path=src/csv_dir/ -meta pk="data.csv:column_name"
```

### Restore

```bash
amsdal restore                            # Restore models/state from lakehouse
```

### Plugin Scaffolding

```bash
amsdal plugin MyPlugin .                   # Scaffold a new AMSDAL plugin (creates my_plugin/)
amsdal plugin MyPlugin . --models-format json
amsdal plugin MyPlugin . --async           # Generate plugin in async mode
```

### API Check

```bash
# Compare a target API against another live endpoint
amsdal api-check https://api-prod.example.com --compare-url https://api-staging.example.com -c api-check-config.json

# Compare a target API against previously saved logs
amsdal api-check https://api.example.com --compare-logs previous-logs.json -c api-check-config.json

# Run checks and save logs (use the same URL for target and compare to skip comparison)
amsdal api-check https://api.example.com --compare-url https://api.example.com -o logs.json -c api-check-config.json
```

Requires a config file (`-c/--config`, YAML or JSON) with test cases, endpoints, and auth.
Exactly one of `--compare-url` or `--compare-logs` is required.
Auth env vars: `AMSDAL_API_CHECK_AUTHORIZATION`, `AMSDAL_API_CHECK_EMAIL`, `AMSDAL_API_CHECK_PASSWORD`.

### Auth Token (local)

```bash
amsdal gen-token                           # Generate a token from the local API server (alias: gt)
amsdal gen-token -e admin@example.com -p secret --mfa-code 123456
```

Uses `http://localhost:<http_port>/api`. For a deployed environment use `amsdal cloud gen-token` (see Cloud Deployment).

### Version

```bash
amsdal --version                           # Show versions of installed amsdal packages (alias: -v)
```

## Cloud Deployment

### Environment Management

```bash
amsdal cloud env                          # List environments
amsdal cloud env new uat                  # Create environment
amsdal cloud env checkout uat             # Switch to environment
amsdal cloud env delete uat               # Delete environment
```

### Deploy Application

```bash
amsdal cloud deploys                      # List deployments
amsdal cloud deploys new                  # Deploy
amsdal cloud deploys new --from-env prod  # Deploy with data from another env
amsdal cloud deploys delete <DEPLOY_ID>   # Delete deployment
```

**Deployment options:**
| Flag | Options | Description |
|------|---------|-------------|
| `--deploy-type` | `include_state_db`, `lakehouse_only` | Include state DB (default: include) |
| `--lakehouse-type` | `postgres`, `postgres-immutable`, `spark` | Lakehouse backend |
| `--env` | name | Target environment |
| `--from-env` | name | Copy data from environment |
| `--skip-checks` | — | Skip dependency/secret checks |

### Secrets Management

```bash
amsdal cloud secrets                      # List secrets
amsdal cloud secrets new my_secret 123    # Add secret
amsdal cloud secrets delete my_secret     # Delete secret
amsdal cloud secrets -v                   # Show values
amsdal cloud secrets -v -o json           # JSON output
```

### Dependencies

```bash
amsdal cloud deps                         # List dependencies
amsdal cloud deps new libreoffice         # Add system dependency
amsdal cloud deps delete <name>           # Remove
amsdal cloud deps --sync                  # Sync from cloud
```

### Database Operations

```bash
amsdal cloud sync-db                      # Recreate local DB from remote
amsdal cloud expose-db                    # Add IP to DB allowlist
amsdal cloud tunnel-db                    # Open SSH tunnel to the cloud DB (aliases: tunnel_db, tdb)
amsdal cloud tunnel-db --env uat --local-port 5433 --db-port 5432
```

`tunnel-db` opens a local SSH tunnel through a bastion (default local port `5433`); connect your SQL client to `127.0.0.1:<local-port>` while it runs.

### External Connections

```bash
amsdal cloud external-connections                                   # List external connections (aliases: ext-conn, ec)
amsdal cloud external-connections add my_conn postgres -c dsn=postgresql://user:pass@host:5432/db   # Add (alias: a)
amsdal cloud external-connections update my_conn -b postgres -c dsn=...                              # Update (alias: u)
amsdal cloud external-connections remove my_conn                    # Remove (aliases: rm, r)
```

Pass credentials with repeatable `--credential/-c key=value`; target a non-current env with `--env`.

### Auth Token (deployed)

```bash
amsdal cloud gen-token                     # Generate a token from a deployed environment's API (aliases: gen_token, gt)
amsdal cloud gen-token --env prod -e admin@example.com -p secret --mfa-code 123456
```

### Security

```bash
amsdal cloud security allowlist new                              # Add IP
amsdal cloud security allowlist delete --ip-address 0.0.0.0     # Remove IP
amsdal cloud security basic-auth new -u user -p pass             # Add basic auth
amsdal cloud security basic-auth delete                          # Remove basic auth
amsdal cloud security basic-auth retrieve                        # Get credentials
```

### Monitoring

```bash
amsdal cloud get-monitoring-info          # Get Grafana URL and credentials
```

Grafana dashboard includes:
- Request rate, response times, error rates
- CPU, memory, disk utilization
- Database query times, connection pool status
- Structured application logs

### CI/CD

```bash
amsdal ci-cd                              # Generate CI/CD pipeline files
```

## Configuration

### config.yml (Local Development)

```yaml
application_name: MyApp
async_mode: true

connections:
  - name: lakehouse
    backend: postgres-historical-async
    credentials:
      - dsn: postgresql://user:pass@localhost:5432/lakehouse

  - name: main-db
    backend: sqlite-async
    credentials:
      - db_path: ./default.db

  - name: lock
    backend: amsdal_data.lock.implementations.redis_lock.RedisLock
    credentials:
      - host: localhost
      - port: 6379

resources_config:
  lakehouse: lakehouse
  lock: lock
  repository:
    default: main-db
    models:
      user: users-db
```

### Backend Aliases

**State:** `sqlite`, `sqlite-async`, `postgres-state`, `postgres-state-async`
**Historical:** `sqlite-historical`, `sqlite-historical-async`, `postgres-historical`, `postgres-historical-async`

### .amsdal-cli Config

```json
{
  "config_path": "./config.yml",
  "http_port": 8080,
  "check_model_exists": true,
  "indent": 4
}
```

`indent` controls JSON output indentation (default `4`). Unknown keys are silently ignored, so a wrong key name like `json_indent` has no effect.

### Environment Variables

```bash
AMSDAL_ACCESS_KEY_ID=xxx                  # Cloud credentials
AMSDAL_SECRET_ACCESS_KEY=xxx
AMSDAL_CONTRIBS="..."                     # Contrib plugins to load
AMSDAL_ADMIN_USER_EMAIL=admin@example.com
AMSDAL_ADMIN_USER_PASSWORD=secret
AMSDAL_AUTH_JWT_KEY=jwt-secret
AMSDAL_REQUIRE_DEFAULT_AUTHORIZATION=True
```

## Cloud Deploy: requirements.txt

**AMSDAL Cloud runs PostgreSQL.** The `requirements.txt` MUST include postgres driver even if you use SQLite locally. Without it, deploy will fail at runtime in Kubernetes with an import error.

Recommended:
```
amsdal[server,cli]>=0.9.4
amsdal-glue-connections[async-sqlite,postgres-binary]
```

For optimized production, replace `postgres-binary` with `postgres-c` before deploy (requires `libpq-dev` on the build system).

## Typical Workflow

```bash
# 1. Create app
amsdal new MyApp ~/projects/

# 2. Generate models
amsdal generate model Person -attrs "first_name:string last_name:string"

# 3. Build & verify
amsdal verify --building

# 4. Create & apply migrations
amsdal migrations new
amsdal migrations apply

# 5. Run locally
amsdal serve

# 6. Deploy to cloud
amsdal cloud env new production
amsdal cloud env checkout production
amsdal cloud secrets new API_KEY my-secret-key
amsdal cloud deploys new --deploy-type include_state_db --lakehouse-type postgres
```