---
name: amsdal-ecosystem
description: >
  Ready-made AMSDAL plugins — storages (S3), mail, auth, CRM, frontend configs, LangGraph, integrations.
  TRIGGER when: user asks about existing AMSDAL plugins, S3 storage, email, CRM, LangGraph, or wants to integrate third-party services.
  DO NOT TRIGGER when: user creates a new custom plugin (use amsdal-plugins instead).
user-invocable: false
---

# AMSDAL Ecosystem Plugins

Ready-made plugins that extend AMSDAL applications.

## Quick Reference

| Plugin | Package | AppConfig | Purpose |
|--------|---------|-----------|---------|
| Auth | built-in | `amsdal.contrib.auth.app.AuthAppConfig` | Authentication & permissions |
| Frontend Configs | built-in | `amsdal.contrib.frontend_configs.app.FrontendConfigAppConfig` | UI field controls |
| ML | `amsdal-ml` | `amsdal_ml.app.MLPluginAppConfig` | Embeddings, agents, MCP |
| CRM | `amsdal-crm` | `amsdal_crm.app.CRMAppConfig` | CRM: entities, deals, pipelines, activities |
| Mail | `amsdal-mail` | `amsdal_mail.app.MailAppConfig` | Email (SMTP/SES) |
| Storages | `amsdal_storages` | — (storage backend) | S3 file storage |
| LangGraph | `amsdal-workflow` | — (direct use) | LangGraph checkpoint persistence |
| Integrations | `amsdal_integrations` | — (standalone SDK) | Cross-ORM integration |

## Registration

Add AppConfig classes to `AMSDAL_CONTRIBS`:
```bash
AMSDAL_CONTRIBS="amsdal.contrib.auth.app.AuthAppConfig,amsdal_mail.app.MailAppConfig,amsdal_ml.app.MLPluginAppConfig"
```

---

## amsdal_crm — CRM Plugin

Full-featured CRM (Customer Relationship Management) system.

### Installation
```bash
pip install amsdal-crm
```

### Registration
```bash
AMSDAL_CONTRIBS="...,amsdal_crm.app.CRMAppConfig"
```

### Configuration
```bash
# Environment prefix: AMSDAL_CRM_
AMSDAL_CRM_DEFAULT_CURRENCY=USD
AMSDAL_CRM_DEFAULT_ACTIVITY_TIMELINE_LIMIT=100
AMSDAL_CRM_MAX_CUSTOM_FIELDS_PER_ENTITY=50
AMSDAL_CRM_MAX_WORKFLOW_RULES_PER_ENTITY=100
```

### Core Models

**Entity Management:**
- `Entity` — accounts/organizations (name, legal_name, status, assigned_to, notes)
- `EntityRelationship` — relationships between entities
- `EntityIdentifier` — external IDs (tax number, etc.)
- `EntityContactPoint` — contact info (email, phone)
- `EntityAddress` — addresses

**Sales Pipeline:**
- `Pipeline` — pipeline definition (name, description, is_active)
- `Stage` — pipeline stages (name, order, win_probability, status: open/closed_won/closed_lost)
- `Deal` — sales opportunities (name, amount, currency, stage, entity, expected_date, closed_date)

**Activities (Timeline):**
- `Activity` — base activity with polymorphic link to Entity or Deal
- `Task` — tasks with priority and status
- `Event` — meetings/events with start/end time and location
- `EmailActivity` — email records
- `Note` — text notes
- `Call` — phone calls with duration and outcome

**Extensibility:**
- `CustomFieldDefinition` — custom field metadata (text/number/date/choice)
- `WorkflowRule` — automation rules (trigger on create/update/delete, condition + action)
- `Attachment` — file attachments to any CRM record

### Key Services

```python
from amsdal_crm.services.deal_service import DealService
from amsdal_crm.services.activity_service import ActivityService
from amsdal_crm.services.custom_field_service import CustomFieldService
from amsdal_crm.services.workflow_service import WorkflowService
from amsdal_crm.services.email_service import EmailService
```

**DealService** — move deals through pipeline stages:
```python
# Moves deal, creates note, emits lifecycle events
deal = await DealService.amove_deal_to_stage(
    deal=deal,
    new_stage_id=stage_id,
    note='Moved to negotiation',
    user_email='user@example.com',
)
# Emits: ON_DEAL_STAGE_CHANGE, ON_DEAL_WON (if won), ON_DEAL_LOST (if lost)
```

**ActivityService** — get activity timeline:
```python
timeline = await ActivityService.aget_timeline(
    related_to_type='Entity',
    related_to_id='entity-123',
    limit=50,
)
```

**EmailService** — log emails:
```python
email = await EmailService.alog_email(
    subject='Follow-up',
    body='Hello...',
    from_address='sales@example.com',
    to_addresses=['client@example.com'],
    related_to_type='Deal',
    related_to_id='deal-456',
    is_outbound=True,
)
```

### Lifecycle Events
- `ON_DEAL_STAGE_CHANGE` — deal moved between stages
- `ON_DEAL_WON` — deal reached closed_won
- `ON_DEAL_LOST` — deal reached closed_lost

### Workflow Automation
Condition operators: `equals`, `not_equals`, `contains`, `greater_than`, `less_than`
Actions: `update_field`, `create_activity`, `send_notification`

### Permissions
All models use owner-based permissions (`has_object_permission()`):
- Owner (assigned_to matches user email) gets full access
- Super admin gets full access
- Others denied by default

---

## amsdal_storages — S3 File Storage

Store file fields on S3-compatible storage instead of database.

### Installation
```bash
pip install amsdal_storages[s3]
```

### Configuration
```bash
AWS_S3_BUCKET_NAME=my-bucket
AWS_S3_REGION_NAME=us-east-1
AWS_S3_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_S3_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_S3_ENDPOINT_URL=https://s3.amazonaws.com  # optional, for MinIO/custom
```

### Usage with FileField

```python
from amsdal.models import Model
from amsdal.models.core.file import File
from amsdal_models.classes.fields.file import FileField
from amsdal_storages.s3.storage import S3Storage

class Document(Model):
    name: str
    file: File = FileField(storage=S3Storage())
    attachment: File = FileField(storage=S3Storage(object_prefix='attachments/'))
```

### S3Storage Constructor Parameters
- `bucket` (str) — S3 bucket name (or env var)
- `region_name` (str) — AWS region
- `endpoint_url` (str) — custom endpoint (MinIO)
- `object_prefix` (str, default='') — key prefix
- `presign_ttl` (int, default=3600) — presigned URL TTL in seconds
- `access_key_id`, `secret_access_key`, `security_token` — credentials

Supports both sync (boto3) and async (aioboto3).

---

## amsdal_mail — Email Plugin

### Installation
```bash
pip install amsdal-mail[smtp]    # SMTP backend
pip install amsdal-mail[ses]     # AWS SES backend
pip install amsdal-mail[all]     # All backends
```

### Registration
```bash
AMSDAL_CONTRIBS="...,amsdal_mail.app.MailAppConfig"
```

### Configuration

**SMTP:**
```bash
AMSDAL_EMAIL_BACKEND=smtp
AMSDAL_EMAIL_HOST=smtp.gmail.com
AMSDAL_EMAIL_PORT=587
AMSDAL_EMAIL_USER=email@example.com
AMSDAL_EMAIL_PASSWORD=password
AMSDAL_EMAIL_USE_TLS=true
```

**AWS SES:**
```bash
AMSDAL_EMAIL_BACKEND=ses
AWS_ACCESS_KEY_ID=key
AWS_SECRET_ACCESS_KEY=secret
AWS_REGION=us-east-1
```

**Console (development):**
```bash
AMSDAL_EMAIL_BACKEND=console   # prints to stdout
```

**Dummy (testing):**
```bash
AMSDAL_EMAIL_BACKEND=dummy     # no-op
```

### Sending Emails

```python
from amsdal_mail import send_mail, asend_mail, EmailMessage, Attachment

# Simple send
send_mail(
    subject='Welcome!',
    body='Hello, welcome to our platform.',
    from_email='noreply@example.com',
    to=['user@example.com'],
)

# Async send
await asend_mail(
    subject='Welcome!',
    body='<h1>Hello!</h1>',
    from_email='noreply@example.com',
    to=['user@example.com'],
    html=True,
)

# Full EmailMessage
msg = EmailMessage(
    subject='Report',
    body='Please find attached.',
    from_email='reports@example.com',
    to=['manager@example.com'],
    cc=['team@example.com'],
    bcc=['archive@example.com'],
    attachments=[
        Attachment(filename='report.pdf', content=pdf_bytes, mimetype='application/pdf'),
    ],
    tags=['reports'],
    metadata={'report_id': '123'},
)
result = send_mail(msg)
```

### Features
- SMTP & AWS SES backends
- HTML emails
- Attachments
- Inline images (CID)
- Tags and metadata
- Click and open tracking (SES)
- Template support (SES)

---

## amsdal.contrib.auth — Authentication & Permissions

Built into `amsdal_framework`. See the `amsdal-server` skill for full auth documentation.

### Quick Setup
```bash
AMSDAL_CONTRIBS="amsdal.contrib.auth.app.AuthAppConfig"
AMSDAL_ADMIN_USER_EMAIL=admin@example.com
AMSDAL_ADMIN_USER_PASSWORD=securepassword
AMSDAL_AUTH_JWT_KEY=jwt-secret
```

### Key Classes
```python
from amsdal.contrib.auth.permissions import AllowAny, RequireAuth, RequirePermissions
from amsdal.contrib.auth.decorators import permissions, allow_any, require_auth
```

### MFA Support
- TOTP (authenticator apps)
- Email-based codes
- SMS-based codes
- Backup codes

### Settings
| Variable | Description |
|----------|-------------|
| `AMSDAL_REQUIRE_DEFAULT_AUTHORIZATION` | Require auth by default (true) |
| `REQUIRE_MFA_BY_DEFAULT` | Force MFA |
| `MFA_TOTP_ISSUER` | TOTP app name |
| `AUTH_TOKEN_EXPIRATION` | Token lifetime (seconds) |

---

## amsdal.contrib.frontend_configs — UI Controls

Dynamic form definitions for frontend rendering. See the dedicated `amsdal-frontend-configs` skill for full documentation (controls, conditions, actions, dashboards, form helpers).

---

## amsdal_langgraph — LangGraph Checkpoint Persistence

Persist LangGraph workflow state in AMSDAL database.

### Installation
```bash
pip install amsdal-workflow
```

### Usage

```python
from amsdal_langgraph.checkpoint import AmsdalCheckpointSaver

saver = AmsdalCheckpointSaver()

# Use with LangGraph
from langgraph.graph import StateGraph

graph = StateGraph(MyState)
# ... build graph ...
app = graph.compile(checkpointer=saver)

# Run with thread persistence
config = {'configurable': {'thread_id': 'my-thread-1'}}
result = await app.ainvoke(input_data, config)
```

### Key Features
- Both sync and async checkpoint operations
- Thread-based organization
- Data models: `Checkpoint`, `CheckpointWrites`
- Composite primary keys for efficient storage
- TimestampMixin for automatic timestamps

### Core Methods
```python
# Get checkpoint
checkpoint = await saver.aget_tuple(config)

# Store checkpoint
await saver.aput(config, checkpoint, metadata, new_versions)

# Store pending writes
await saver.aput_writes(config, writes, task_id)

# List checkpoints
async for cp in saver.alist(config, limit=10):
    print(cp)

# Delete thread
await saver.adelete_thread(thread_id='my-thread-1')
```

---

## amsdal_integrations — Cross-ORM Integration SDK

Standalone SDK for integrating external systems with AMSDAL via HTTP API.

### Installation
```bash
pip install amsdal_integrations
```

### Usage

```python
from amsdal_integrations import AmsdalIntegration, AsyncAmsdalSdk
from amsdal_integrations.data_classes import IntegrationConfig, Schema, PropertySchema

# Setup
config = IntegrationConfig(
    amsdal_host='http://localhost:8080',
    amsdal_auth=None,  # or httpx.Auth
)

# Sync
integration = AmsdalIntegration(config)

# Register schema
schema = Schema(
    title='ExternalProduct',
    properties={
        'name': PropertySchema(type='string'),
        'price': PropertySchema(type='number'),
    },
    required=['name'],
)
integration.register_schema(schema, operation_id='create-product-schema')

# CRUD
integration.create('ExternalProduct', {'name': 'Widget', 'price': 9.99}, operation_id='create-1')
integration.update('ExternalProduct', object_id='123', data={'price': 12.99}, operation_id='update-1')
integration.delete('ExternalProduct', object_id='123', operation_id='delete-1')

# Async
sdk = AsyncAmsdalSdk(config)
await sdk.create('ExternalProduct', {'name': 'Gadget', 'price': 19.99}, operation_id='create-2')
```

### Features
- Sync and async operations
- Idempotent operations via `operation_id`
- Schema registration/unregistration
- HTTP-based CRUD