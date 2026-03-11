---
name: amsdal-frontend-configs
description: >
  AMSDAL Frontend Configs — dynamic forms, controls, conditions, actions, dashboards, tables, charts.
  TRIGGER when: user works with frontend configurations, dynamic forms, dashboard setup, table/chart configs, or admin panel customization.
  DO NOT TRIGGER when: user works with backend models or server without frontend context.
user-invocable: false
---

# AMSDAL Frontend Configs

Frontend configs are JSON-based form definitions that generate UI and interact with the backend. Part of `amsdal.contrib.frontend_configs`.

## Setup

```bash
AMSDAL_CONTRIBS="...,amsdal.contrib.frontend_configs.app.FrontendConfigAppConfig"
```

## Controls

Controls are form elements. Some can contain other controls.

### Input Controls

#### text
Simple text input.
```json
{"type": "text", "id": "first_name_field", "name": "first_name", "label": "First Name"}
```

#### email
Email input with frontend validation.
```json
{"type": "email", "id": "email_field", "name": "personal_email", "label": "Email"}
```

#### phone
Phone input with frontend validation. Supports `helperText`.
```json
{"type": "phone", "id": "phone_field", "name": "mobile_phone", "label": "Phone", "helperText": "At least phone or email is required"}
```

#### password
Masked text input.
```json
{"type": "password", "id": "password_field", "name": "current_password", "label": "Password", "required": true}
```

#### number
Numeric input.
```json
{"type": "number", "id": "premium_field", "name": "premium", "label": "Premium", "value": "100.00", "placeholder": "0.00", "required": true}
```

#### date
Date picker. Value is ISO 8601 (`YYYY-MM-DD`).
```json
{"type": "date", "id": "dob_field", "name": "date_of_birth", "label": "Date of Birth", "value": "1990-05-15"}
```

#### textarea
Multi-line text input. Supports `rows`.
```json
{"type": "textarea", "id": "notes_field", "name": "notes", "label": "Notes", "rows": 4}
```

#### checkbox
Boolean toggle. Value is string `"true"` or `"false"` (not JSON boolean).
```json
{"type": "checkbox", "id": "us_citizen_field", "name": "us_citizen", "label": "U.S. Citizen?", "value": "false"}
```

#### select
Dropdown. Requires `options` array of `{label, value}`.
```json
{
  "type": "select", "id": "state_field", "name": "state", "label": "State", "value": "CA",
  "options": [{"label": "California", "value": "CA"}, {"label": "Texas", "value": "TX"}]
}
```

#### multiselect
Multi-selection dropdown. Value is array. Requires `options`.
```json
{
  "type": "multiselect", "id": "riders_field", "name": "riders", "label": "Riders",
  "value": ["LTC", "WB"],
  "options": [
    {"label": "Long-Term Care", "value": "LTC"},
    {"label": "Waiver of Surrender", "value": "WB"},
    {"label": "Return of Premium", "value": "ROP"}
  ]
}
```
Empty selection produces `[]`, not `null`.

#### object_latest
Entity selector — pick an AMSDAL model instance. `entityType` must match model name.
```json
{"type": "object_latest", "id": "policy_field", "name": "policy", "label": "Policy", "entityType": "Policy", "required": true}
```

#### attachment
File upload control.
```json
{"type": "attachment", "id": "chat_attachments_field", "name": "chat_attachments", "label": "Attachments", "hideLabel": true}
```

### Display Controls

#### paragraph
Readonly `<p>` text.
```json
{"type": "paragraph", "label": "Info", "value": "This is the text in paragraph"}
```

#### header
Readonly `<h3>`.
```json
{"type": "header", "label": "", "value": "Header Text", "hideLabel": true}
```

#### infoscreen
Readonly `<div>` — main text in `label`.
```json
{"type": "infoscreen", "label": "Please review your information before submitting."}
```

#### chat
Read-only chat thread. Value is array of message objects.
```json
{
  "type": "chat", "id": "chat_field_id", "name": "chat_field", "label": "Chat", "hideLabel": true,
  "value": [
    {"role": "user", "content": "Hello", "content_type": "text", "attachments": null, "created_at": "2025-01-01T12:00:00Z"},
    {"role": "assistant", "content": "Hi!", "content_type": "text", "attachments": null, "created_at": "2025-01-01T12:01:00Z"}
  ]
}
```
Message fields: `role` (`user`/`assistant`), `content`, `content_type` (`text`/`markdown`), `attachments`, `created_at`.

### Button

Clickable element with actions. Usually `hideLabel: true`. Supports `icon` and `additional_styles`.
```json
{
  "type": "button", "name": "save_button", "label": "Save", "hideLabel": true,
  "icon": "refresh",
  "actions": [
    {
      "type": "invoke", "method": "POST",
      "url": "/api/transactions/update_profile/",
      "body": {"first_name": "{first_name_field}"},
      "onSuccess": [], "onError": []
    }
  ]
}
```

### Container Controls

#### group
Top-level container wrapping all controls.
```json
{"type": "group", "name": "user_profile", "label": "User Profile", "controls": [...]}
```

#### sections
Renders children as tabs or accordion. Must contain only `section` children.
```json
{
  "type": "sections", "name": "profile_sections", "label": "Profile Sections",
  "controls": [
    {"type": "section", "name": "personal_info", "label": "Personal Info", "controls": [...]}
  ]
}
```

#### section
Named group with visible label. Supports `condition` for visibility.
```json
{
  "type": "section", "name": "joint_owner_section", "label": "Joint Owner",
  "condition": {"target_id": "owner_type_field", "condition": "eq", "value": "Joint"},
  "controls": [...]
}
```

## Common Control Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | string | Unique field ID — used in `{field_id}` body references |
| `type` | string | Control type |
| `name` | string | Field name sent to backend |
| `label` | string | Visible label text |
| `value` | any | Current / pre-filled value |
| `required` | boolean | Marks field as mandatory |
| `placeholder` | string | Placeholder hint |
| `options` | array | `[{label, value}]` for select/multiselect |
| `controls` | array | Child controls for group/section/sections |
| `hideLabel` | boolean | Suppress label rendering |
| `readOnly` | boolean | Render as read-only |
| `condition` | object | Visibility condition |
| `on_blur` | array | Actions fired on field blur |
| `actions` | array | Actions fired on button click |
| `icon` | string | Icon name (e.g. `"refresh"`, `"send"`) |
| `additional_styles` | object | Inline CSS overrides (camelCase) |
| `entityType` | string | Model name for `object_latest` |
| `helperText` | string | Hint text below field |
| `rows` | integer | Visible row height for `textarea` |

## Conditions

Control visibility conditions. Can be simple or compound.

### Simple Condition
```json
{"target_id": "us_citizen_field", "condition": "eq", "value": true}
```
- `target_id` — `id` of another field in the same form
- `condition` — operator: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`
- `value` — value to compare against

### Compound Condition
```json
{
  "operation": "and",
  "conditions": [
    {"target_id": "owner_type_field", "condition": "eq", "value": "Joint"},
    {"target_id": "plan_type_field", "condition": "eq", "value": "Qualified"}
  ]
}
```
Operations: `and`, `or`. Can be nested arbitrarily deep.

## Actions

Actions describe what happens on button click or `on_blur`.

### invoke
Calls a backend endpoint.
```json
{
  "type": "invoke", "method": "POST",
  "url": "/api/transactions/update_profile/",
  "body": {"first_name": "{first_name_field}", "state": "{state_field}"},
  "onSuccess": [], "onError": []
}
```
- `method` — `GET`, `POST`, `PUT`, `PATCH`, `DELETE`
- `body` — field values referenced as `{field_id}`
- `async` — if `true`, fire-and-forget (no UI wait)
- `onSuccess` / `onError` — arrays of follow-up actions

### update_form
Replace current form with content from a transaction.
```json
{
  "type": "update_form",
  "control_source": {
    "type": "dynamic",
    "dynamic_value": {"type": "transaction", "entity_name": "get_security"}
  }
}
```
Supports `body` for passing parameters:
```json
{
  "type": "update_form",
  "control_source": {
    "type": "dynamic",
    "dynamic_value": {
      "type": "transaction", "entity_name": "get_application_form",
      "body": {"application_id": "{row.partition_key}"}
    }
  }
}
```

### show_popup / close_popup
```json
{
  "type": "show_popup", "id": "success_popup",
  "controls": [
    {"type": "text", "value": "Saved successfully."},
    {"type": "button", "name": "close", "label": "OK", "actions": [{"type": "close_popup", "target": "success_popup"}]}
  ]
}
```

### navigate_to_section
Scrolls to a named dashboard section.
```json
{"type": "navigate_to_section", "section_id": "profile"}
```

### open_url
Opens URL in new tab.
```json
{"type": "open_url", "url": "https://example.com/rates"}
```

### update_value
Updates a field value from an API response.
```json
{"type": "update_value", "field_id": "secret_field", "value": "{response.details.secret}"}
```

## Field Value References

| Syntax | Resolves to |
|--------|-------------|
| `{field_id}` | Current value of the field with that `id` |
| `{response.path.to.field}` | Nested field from previous `invoke` response |
| `{row.field_name}` | Field from table row that triggered `on_row_click` |

## on_blur Autosave

Supported on: `text`, `date`, `number`, `phone`, `textarea`, `select`, `multiselect`, `checkbox`.
```json
{
  "type": "text", "id": "first_name_field", "name": "first_name", "label": "First Name",
  "on_blur": [
    {"type": "invoke", "method": "POST", "url": "/api/transactions/save_application/", "body": {"first_name": "{first_name_field}"}}
  ]
}
```

## additional_styles

Inline CSS overrides. camelCase property names. Supported on most controls.

**Centering a button:**
```json
{"additional_styles": {"width": "50%", "marginLeft": "25%", "borderRadius": "8px"}}
```

**Side-by-side buttons (flex layout on parent section):**
```json
{
  "type": "section", "name": "action_buttons", "label": "", "hideLabel": true,
  "additional_styles": {"display": "flex", "gap": "12px", "justifyContent": "flex-end"},
  "controls": [
    {"type": "button", "name": "cancel", "label": "Cancel", "hideLabel": true, "additional_styles": {"flex": "1"}, "actions": [...]},
    {"type": "button", "name": "save", "label": "Save", "hideLabel": true, "additional_styles": {"flex": "1"}, "actions": [...]}
  ]
}
```

## Dashboard Configuration

Dashboard layout defined in fixture file (e.g. `src/fixtures/frontend_config_dashboard.json`).

### Top-level Structure
```json
{
  "FrontendConfigDashboard": [
    {"title": "Portal", "external_id": "default", "elements": [...]}
  ]
}
```
Each entry is a dashboard variant identified by `external_id`.

### Dashboard Element Types

#### form
Embeds a form from a transaction.
```json
{
  "type": "form", "title": "My Profile", "id": "profile",
  "control_source": {"type": "dynamic", "dynamic_value": {"type": "transaction", "entity_name": "get_profile"}}
}
```

#### table
Tabular data from a transaction. Supports `on_row_click` and `table_actions`.
```json
{
  "type": "table", "title": "Applications", "id": "applications",
  "data_source": {"type": "transaction", "entity_name": "get_applications_table"},
  "on_row_click": [
    {
      "type": "update_form",
      "control_source": {"type": "dynamic", "dynamic_value": {"type": "transaction", "entity_name": "get_application_form", "body": {"id": "{row.partition_key}"}}}
    }
  ],
  "table_actions": [
    {"type": "button", "name": "create", "label": "Create New", "hideLabel": true, "actions": [...]}
  ]
}
```

#### section (dashboard)
Top-level grouping (distinct from form `section`).
```json
{"type": "section", "title": "Applications", "elements": [...]}
```

#### grid / grid_col
Grid layout.
```json
{
  "type": "grid", "title": "Overview", "columns": 2, "rows": 1,
  "elements": [{"type": "grid_col", "elements": [...]}]
}
```

#### chart
Chart widget with data aggregation.
```json
{
  "type": "chart", "chart_type": "bar", "title": "Monthly Transactions",
  "data_source": {
    "type": "class", "entity_name": "PaymentTransaction",
    "aggregation": {"field": "amount", "function": "sum", "group_by": "month"}
  }
}
```

## Form Helpers (Python)

Factory functions to build control dicts in transactions instead of writing JSON inline.

```python
from transactions.form_helpers import (
    text_field, date_field, number_field, select_field,
    checkbox_field, phone_field, textarea_field, object_field,
    section, submit_button,
)
```

| Function | Key Args |
|----------|----------|
| `text_field` | `(field_id, name, label, value="", *, required=False, placeholder=None)` |
| `date_field` | `(field_id, name, label, value="", *, required=False)` |
| `number_field` | `(field_id, name, label, value="", *, required=False, placeholder=None)` |
| `select_field` | `(field_id, name, label, options, value="", *, required=False)` |
| `checkbox_field` | `(field_id, name, label, value="false", *, required=False)` |
| `phone_field` | `(field_id, name, label, value="", *, required=False)` |
| `textarea_field` | `(field_id, name, label, value="", *, required=False, placeholder=None)` |
| `object_field` | `(field_id, name, label, entity_type, value="", *, required=False)` |
| `section` | `(name, label, controls)` |
| `submit_button` | `(name, label, url, body, success_message, error_message=None)` |

### Example
```python
controls = [
    section("personal", "Personal Info", [
        text_field("first_name_field", "first_name", "First Name", required=True),
        select_field("state_field", "state", "State", STATE_OPTIONS),
    ]),
    submit_button(
        name="save_btn", label="Save",
        url="/api/transactions/update_profile/",
        body={"first_name": "{first_name_field}", "state": "{state_field}"},
        success_message="Profile saved successfully.",
    ),
]
```

`submit_button` uses `POST` and auto-wires success/error popups.
