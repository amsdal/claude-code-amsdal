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

## Before you commit to anything concrete

This skill is a routing index, not a complete or current spec. Before you finalize ANY concrete artifact — a control type, a condition/action, a config key, a fixture shape — confirm it against an authoritative source FIRST:

1. `knowledge/` — if it concerns runtime behavior / debugging.
2. There is **no dedicated public docs page** for frontend configs. Verify control/config shapes against the `amsdal.contrib.frontend_configs` source in the user's `site-packages` (it is pure Python, readable), and against `knowledge/`.

Do this by default, NOT only when uncertain — you cannot detect what this skill silently omits. A config shape seeming obvious is not evidence it is supported.

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
Phone input with frontend validation. Use `additionalText` for helper text.
```json
{"type": "phone", "id": "phone_field", "name": "mobile_phone", "label": "Phone", "additionalText": "At least phone or email is required"}
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
Multi-line text input.
```json
{"type": "textarea", "id": "notes_field", "name": "notes", "label": "Notes"}
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

`name` is required on every control, including display-only ones.

#### paragraph
Readonly `<p>` text.
```json
{"type": "paragraph", "name": "info_text", "label": "Info", "value": "This is the text in paragraph"}
```

#### header
Readonly `<h3>`.
```json
{"type": "header", "name": "section_header", "label": "", "value": "Header Text", "hideLabel": true}
```

#### infoscreen
Readonly `<div>` — main text in `label`.
```json
{"type": "infoscreen", "name": "review_notice", "label": "Please review your information before submitting."}
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
  "condition": {"operation": "and", "conditions": [{"path": "owner_type_field", "condition": "eq", "value": "Joint"}]},
  "controls": [...]
}
```

### Layout Containers

Layout containers arrange children on a 12-column grid. They enforce strict parent-child pairing (validated server-side on save).

#### row / column
A `row` may contain only `column` children. Each `column` sets its grid span with `width` (`1..12`).
```json
{
  "type": "row", "name": "address_row", "label": "",
  "controls": [
    {"type": "column", "name": "street_col", "width": 8, "controls": [
      {"type": "text", "id": "street_field", "name": "street", "label": "Street"}
    ]},
    {"type": "column", "name": "zip_col", "width": 4, "controls": [
      {"type": "text", "id": "zip_field", "name": "zip", "label": "ZIP"}
    ]}
  ]
}
```
- A non-`column` child of a `row` raises a validation error.

#### tabs / tab
A `tabs` container may contain only `tab` children, and every `tab` must declare a non-empty `label` (used as the tab header title).
```json
{
  "type": "tabs", "name": "profile_tabs", "label": "",
  "controls": [
    {"type": "tab", "name": "personal_tab", "label": "Personal", "controls": [...]},
    {"type": "tab", "name": "financial_tab", "label": "Financial", "controls": [...]}
  ]
}
```
- A `tabs` child that is not a `tab`, or a `tab` without a label, raises a validation error.

> The control `type` is a curated subset shown here. The full `ConfigType` literal also includes types like `array`, `object`, `object_group`, `dict`, `radio`, `toggle`, `group_switch`, `group_toggle`, `wizard`, `time`, `datetime`, `dateTriplet`, `number-slider`, `number-operations`, `file`, `dropzone`, and others — see `models/frontend_control_config.py` for the complete list.

## Common Control Attributes

Only `type` and `name` are required; every other field is optional.

| Attribute | Type | Description |
|-----------|------|-------------|
| `type` | string | Control type (required) |
| `name` | string | Field name sent to backend (required) |
| `id` | string | Unique field ID — used in `{field_id}` body references |
| `label` | string | Visible label text |
| `value` | any | Current / pre-filled value |
| `required` | boolean | Marks field as mandatory |
| `placeholder` | string | Placeholder hint |
| `options` | array | `FrontendConfigOption` `[{label, value}]` for select/multiselect |
| `controls` | array | Child controls for group/section/sections/layout containers |
| `control` | object | Single nested control template (e.g. for `array`) |
| `hideLabel` | boolean | Suppress label rendering |
| `condition` | object | Visibility `Condition` (`{operation, conditions}`) |
| `on_enter` | array | Actions fired when the field value is committed |
| `actions` | array | Actions fired on button click |
| `icon` | string | Icon name (e.g. `"refresh"`, `"send"`) |
| `additional_styles` | object | `{string: string}` inline CSS overrides (camelCase) |
| `override_styles` | object | `{string: string}` style overrides |
| `entityType` | string | Model name for `object_latest` |
| `validators` | array | `FrontendConfigValidator` synchronous validation rules |
| `asyncValidators` | array | `FrontendConfigAsyncValidator` (`{endpoint}`) remote validation |
| `activators` | array | `FrontendActivatorConfig` enable/disable rules |
| `additionalText` | string | Extra helper text rendered with the control |
| `mask` | object | `FrontendConfigTextMask` (`{mask_string, prefix, suffix, thousands_separator}`) |
| `showSearch` | boolean | Enable search box in select-style controls |
| `sliderOptions` | object | `FrontendConfigSliderOption` (`{min, max, range}`) |
| `customLabel` | array | List of strings for composite labels |
| `hide_default_buttons` | boolean | Hide default form buttons (default `false`) |
| `width` | integer | Grid width `1..12` for layout columns |

## Conditions

Control visibility conditions. A control's `condition` field is ALWAYS a single `Condition` object with `operation` + `conditions`. There is no flat single-leaf form — wrap even one leaf in `conditions`.

```json
{
  "operation": "and",
  "conditions": [
    {"path": "us_citizen_field", "condition": "eq", "value": true}
  ]
}
```

`Condition` shape:
- `operation` — `and`, `or`, or `not`
- `conditions` — array of flat leaf items (`ConditionItem`). Leaves are NOT nested; each is one comparison.

`ConditionItem` (leaf) shape:
- `path` — `id` of another field in the same form to compare against
- `condition` — operator string (e.g. `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`)
- `value` — value to compare against (optional, defaults to `null`)

### Compound Condition
```json
{
  "operation": "and",
  "conditions": [
    {"path": "owner_type_field", "condition": "eq", "value": "Joint"},
    {"path": "plan_type_field", "condition": "eq", "value": "Qualified"}
  ]
}
```

## Actions

Actions describe what happens on button click or on field `on_enter`.

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
- `url` — endpoint to call
- `headers` — optional `{string: string}` request headers
- `body` — `{string: any}` payload; field values referenced as `{field_id}`
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
    {"type": "paragraph", "name": "popup_text", "value": "Saved successfully."},
    {"type": "button", "name": "close", "label": "OK", "actions": [{"type": "close_popup", "target_id": "success_popup"}]}
  ]
}
```

### navigate_to_section
Scrolls to a named dashboard section.
```json
{"type": "navigate_to_section", "section_id": "profile"}
```

### open_url
Opens a URL. `blank: true` opens in a new tab (default `false`).
```json
{"type": "open_url", "target_url": "https://example.com/rates", "blank": true}
```

### update_value
Updates a field value from an API response.
```json
{"type": "update_value", "field_id": "secret_field", "value": "{response.details.secret}"}
```

### update_table
Reloads a table element from a data source (same `data_source` shape as a dashboard table).
```json
{
  "type": "update_table",
  "data_source": {"type": "transaction", "entity_name": "get_applications_table"}
}
```

### save
Triggers a save of the current form. No extra fields.
```json
{"type": "save"}
```

### change_context
Updates the frontend context with arbitrary key/values.
```json
{"type": "change_context", "context": {"selected_policy": "{policy_field}"}}
```

### scroll_top
Scrolls the view to the top. No extra fields.
```json
{"type": "scroll_top"}
```

### open_sidebar / close_sidebar
Opens (or closes) a stackable sidebar identified by `id`. Content is either a form (`content_type: "form"` + `control_source`) or static text (`content_type: "static"` + `content_format` + `body`).
```json
{
  "type": "open_sidebar", "id": "detail_sidebar", "title": "Details",
  "position": "right", "size": "medium",
  "content": {
    "content_type": "form",
    "control_source": {"type": "dynamic", "dynamic_value": {"type": "transaction", "entity_name": "aget_class_object_form", "body": {"id": "{row.partition_key}"}}}
  }
}
```
- `position` — `left`, `right` (default), `top`, `bottom`
- `size` — `small`, `medium`, `large` (optional)
- static content example: `{"content_type": "static", "content_format": "markdown", "body": "## Note"}` (`content_format`: `markdown` (default), `html`, `text`)

```json
{"type": "close_sidebar", "target_id": "detail_sidebar"}
```

## Field Value References

| Syntax | Resolves to |
|--------|-------------|
| `{field_id}` | Current value of the field with that `id` |
| `{response.path.to.field}` | Nested field from previous `invoke` response |
| `{row.field_name}` | Field from table row that triggered `on_row_click` |

## on_enter Autosave

`on_enter` is a list of actions fired when the user commits a field value (Enter / blur-commit). Use it for per-field autosave.
```json
{
  "type": "text", "id": "first_name_field", "name": "first_name", "label": "First Name",
  "on_enter": [
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
    {"title": "Portal", "elements": [...], "custom_css": ".portal-table { font-size: 13px; }"}
  ]
}
```
`FrontendConfigDashboard` fields: `title` (required), `elements` (required), `custom_css` (optional — injected as a `<style>` block into the dashboard). There is no `external_id` field on the dashboard model.

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
Tabular data from a data source. Supports `on_row_click`, `table_actions`, plus `pagination`, `sort`, and `versions` contracts.
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
  ],
  "pagination": {"enabled": true, "default_page_size": 50, "page_size_options": [25, 50, 100]},
  "sort": {"enabled": true, "default_sort": ["-created_at"], "sortable_fields": ["created_at", "status"]},
  "versions": {"enabled": true}
}
```
- `pagination` — `enabled` (default `true`), `default_page_size` (default `50`), `page_size_options` (optional list). When set, the frontend forwards page/page_size to the data source transaction.
- `sort` — `enabled` (default `true`), `default_sort` (list of `field` / `-field`), `sortable_fields` (whitelist). Forwards the sort list to the data source transaction.
- `versions` — `enabled` (default `true`). Renders the per-row versions UI.

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
Chart widget. `chart_type` is a free-form string (e.g. `"bar"`, `"line"`). The `data_source` is a standard `FrontendConfigDashboardDataSource` (no aggregation/group_by fields exist on the model — shape the data inside the transaction or via `query_params`).
```json
{
  "type": "chart", "chart_type": "bar", "title": "Monthly Transactions",
  "data_source": {"type": "transaction", "entity_name": "get_monthly_transactions"}
}
```
`DataSource` fields: `type` (`class` | `transaction`), `entity_name` (required), `method_type` (`GET` | `POST`, optional), `query_params` (list of `{field, operator, value}`, for `class` type), `body` (request body, for `transaction` type).
