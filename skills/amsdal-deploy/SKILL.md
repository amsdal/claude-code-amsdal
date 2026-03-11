---
name: amsdal-deploy
description: >
  AMSDAL CLI commands reference, cloud deployment, monitoring, secrets, migrations CLI.
  TRIGGER when: user asks about CLI commands, deployment, cloud environments, secrets, monitoring, CI/CD, or running amsdal serve/build/verify.
  DO NOT TRIGGER when: user writes application code without needing CLI reference.
user-invocable: true
---

# AMSDAL Deployment & CLI

## Installation

```bash
pip install amsdal[cli]
```

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
```

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
amsdal tests run                          # Run all tests
```

### Workers

```bash
amsdal worker run                         # Background task worker
amsdal worker run --mode scheduler        # Scheduler only
amsdal worker run --mode hybrid           # Scheduler + processor
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
  "json_indent": 4
}
```

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
amsdal[server,cli]>=0.8.0
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