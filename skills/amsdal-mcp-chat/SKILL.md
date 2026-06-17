---
name: amsdal-mcp-chat
description: >
  Recipe for an MCP-powered chat feature inside an AMSDAL app — a Chat model rendered as a conversational UI in AMSDAL Console, backed by a transaction that runs a FunctionalCallingAgent against an MCP server (typically AMSDAL's own, under the user's JWT).
  TRIGGER when: user wants to add a chat / conversational UI / "MCP chat" / AI-agent chat to an AMSDAL app, or wants AMSDAL Console to edit a model as a chat.
  DO NOT TRIGGER when: user only needs a raw LLM call or a standalone agent without the Console UI (use amsdal-ml), or a frontend form without an agent (use amsdal-frontend-configs).
user-invocable: false
---

# Recipe: Build an MCP chat feature

## Before you commit to anything concrete

This recipe is a routing index, not a complete or current spec. Before you finalize ANY concrete artifact — an agent/tool definition, an `MCPServerConfig`, a control/fixture shape, a transaction signature, an import path, an API call — confirm it against an authoritative source FIRST:

1. `knowledge/` — if it concerns runtime behavior / debugging.
2. WebFetch the matching `docs.amsdal.com` page (map below) — for API / usage.

Do this by default, NOT only when uncertain — you cannot detect what this skill silently omits. A construct being valid Python/Pydantic, or seeming obvious, is not evidence that AMSDAL supports it.

**Docs map for this skill:**
- agents (`FunctionalCallingAgent`) → https://docs.amsdal.com/framework/plugins/amsdal-ml/agents/
- agent tools → https://docs.amsdal.com/framework/plugins/amsdal-ml/agent-tools/
- MCP setup → https://docs.amsdal.com/framework/plugins/amsdal-ml/mcp-setup/
- (frontend controls have no dedicated docs page — see the [[amsdal-frontend-configs]] skill)

A "chat with MCP" in an AMSDAL app is a **cross-cutting pattern** made of three parts that
work together:

1. **A `Chat` model** whose editing screen in AMSDAL Console renders as a chat.
2. **A frontend config** (fixture) that maps that model to a `chat` control + an input + a
   send button that calls a transaction.
3. **A transaction** that runs a `FunctionalCallingAgent` wired to an MCP server and returns
   the updated message list.

Related skills: [[amsdal-ml]] (agent + `MCPServerConfig`), [[amsdal-frontend-configs]]
(`chat`/`button`/`invoke` controls), [[amsdal-server]] (transactions are exposed at
`/api/transactions/<name>/`), [[amsdal-models]] (`Model`, `TypeModel`, `TimestampMixin`).

## Tool surface: AMSDAL MCP vs curated PythonTools

The agent can be given the **generic AMSDAL MCP server** (its
`perform_transaction_operation` / `perform_crud_operation` / discovery tools), or a
**hand-written set of `PythonTool`s**.

**Default to the generic AMSDAL MCP server + `AmsdalSkill` records.** It is the lower-code
path and is **not** an extra security surface:

- `perform_transaction_operation` runs the transaction through the **same**
  `TransactionExecutionApi.execute_transaction` the REST endpoint uses, so the
  transaction's auth decorators (`@allow_any` / `@require_auth` / `@permissions`) apply
  unchanged.
- `perform_crud_operation` enforces class- and object-level permissions
  (`authorize_class` / `authorize_object`).
- The agent forwards the caller's JWT (`_user_jwt`); an unauthenticated caller runs in
  anonymous context.

**Net effect: the agent can reach exactly what that same principal could already reach
through the REST API — no more.** If your permission system already constrains models and
transactions correctly, the MCP surface is constrained the same way, for free. (OAuth
applies only to *external* MCP clients like Claude Desktop; the in-app server-side agent
just forwards the request JWT — no OAuth setup.) The agent also receives each transaction's
argument schema, so it maps arguments by name.

Crucially, `perform_transaction_operation` also **resolves model-typed (FK) arguments from
natural language itself**: for a parameter annotated as a model, it looks the referenced
object up via NLQuery (permission-checked) and passes the reference — in a two-step
analyze-then-confirm flow — so the agent never fetches ids or builds references by hand.
Model/FK arguments are therefore *not* a reason to prefer curated tools.

This is the natural fit for **conversational management**, especially when one chat handles
**several records of the same kind**: only the LLM can resolve which record a follow-up
message refers to from the conversation, so the LLM is the right place to track which one is
in play. Encode multi-step procedures as `AmsdalSkill` records — the steps to follow, in
order, with examples — so the agent applies them reliably (discovered via
`list_available_skills`, see [[amsdal-ml]]).

Letting the agent supply an identifying argument value is fine here: it identifies the
principal's own data, the LLM needs that identifier to disambiguate anyway, and permissions
still bound every call. (The only cost: that value passes through the model context /
provider.)

Choose **curated `PythonTool`s** only when there is a *stated* requirement the default cannot
meet: a hard-constrained surface (expose a few operations, not every `@allow_any`
transaction), server-side logic beyond the transaction, or an argument value the app owner
has explicitly decided must **never** reach the model. Do **not assume** an argument must be
hidden — letting the agent supply the principal's own identifier is normally fine (see
above). Treat "must be hidden" as an explicit requirement; if it is unclear, keep the generic
MCP default and ask the user rather than inventing the constraint. Curated tools also
disambiguate cleanly only for a **single fixed record per chat**.

When a user asks for "a chat with MCP", do this in order:
1. **Check** whether suitable chat models already exist in `src/models/`. If not, **propose
   creating** the `Chat` model below.
2. **Add the frontend config fixture** so Console shows the model as a chat.
3. **Add the transaction** with the agent code.
4. **Generate a migration** and apply it; test the chat in Console.

The shape below is the **recommended, leaner** one — a single embedded `TypeModel` for
messages held on the `Chat` record, instead of a separate persisted message table plus a
view model. The whole conversation lives in one `Chat` object.

---

## 1. The Chat model (one Model + one embedded TypeModel)

Keep the whole conversation inside a single `Chat` record. `messages` is a list of an
**embedded `TypeModel`** — there is no separate persisted message table to keep in sync.

Per the [[amsdal-models]] file convention, **each model lives in its own file** (file name =
model name in snake_case), so this is two files: the embedded `ChatMessage` type and the
`Chat` model that holds a list of it.

```python
# src/models/chat_message.py
import datetime as dt
from typing import Any, Literal

from amsdal_models.classes.model import TypeModel


class ChatMessage(TypeModel):
    """One conversation message — embedded inside Chat.messages, not its own table."""
    role: Literal['system', 'user', 'assistant']
    content: str
    content_type: str = 'text'                 # 'text' for user, 'markdown' for assistant
    attachments: list[dict[str, Any]] | None = None
    created_at: dt.datetime | None = None
    # Optional agent state, kept so multi-turn tool calls can be restored:
    tool_calls: list[dict[str, Any]] | None = None
    mcp_items: list[dict[str, Any]] | None = None
```

```python
# src/models/chat.py
from typing import ClassVar

from amsdal.models.mixins import TimestampMixin
from amsdal_models.classes.model import Model
from amsdal_utils.models.enums import ModuleType

from models.chat_message import ChatMessage


class Chat(TimestampMixin, Model):
    __module_type__: ClassVar[ModuleType] = ModuleType.USER
    __ordering__: ClassVar[str | list[str]] = ['-updated_at']

    messages: list[ChatMessage] = []


Chat.model_rebuild()
```

`TypeModel` is a non-persisted embedded structure: `Chat.messages` is stored as embedded
data on the `Chat` record. `TimestampMixin` adds `created_at`/`updated_at`; `__ordering__`
sorts newest-first in lists. Call `Chat.model_rebuild()` after defining it so the
cross-file `ChatMessage` reference resolves.

## 2. The frontend config (renders the model as a chat)

Register a `FrontendModelConfig` fixture bound to `class_name: "Chat"`. The `chat` control
binds to the `messages` field; the button `invoke`s the transaction and, on success, writes
the returned messages back into `messages`, pins the conversation via `change_context`, and
clears the input. See [[amsdal-frontend-configs]] for the control/action reference.

```json
{
  "FrontendModelConfig": [
    {
      "external_id": "chat_frontend_config",
      "class_name": "Chat",
      "control": {
        "type": "group",
        "name": "ChatControls",
        "label": "Chat",
        "controls": [
          { "id": "messages",   "type": "chat", "name": "messages",   "label": "Conversation" },
          { "id": "chat_input", "type": "text", "name": "chat_input", "label": "Message" },
          {
            "type": "button",
            "name": "send",
            "label": "Send",
            "actions": [
              {
                "type": "invoke",
                "method": "POST",
                "url": "/api/transactions/mcp_agent/",
                "body": { "object_id": "{context.object_id}", "message": "{chat_input}" },
                "onSuccess": [
                  { "type": "update_value",   "field_id": "messages",   "value": "{response.messages}" },
                  { "type": "change_context", "context": { "object_id": "{response.object_id}" } },
                  { "type": "update_value",   "field_id": "chat_input", "value": "" }
                ]
              }
            ]
          }
        ]
      }
    }
  ]
}
```

Put this in `src/fixtures/` (e.g. `chat_frontend_config.json`); AMSDAL loads fixtures from
there on startup. To also support uploads, add an `{"type": "attachment", ...}` control and
thread an `attachments` argument through the transaction.

## 3. The transaction (agent + MCP)

Exposed automatically at `POST /api/transactions/mcp_agent/` (see [[amsdal-server]]). It
loads/creates the `Chat`, appends the user turn, runs a `FunctionalCallingAgent` against the
MCP server **as the current user**, appends the assistant turn (saving tool state), and
returns the rebuilt message list.

```python
# src/transactions/mcp_agent.py
import datetime as dt
import os
from typing import Any

from amsdal.context.manager import AmsdalContextManager
from amsdal.transactions import async_transaction
from amsdal_ml.agents.functional_calling_agent import FunctionalCallingAgent
from amsdal_ml.ml_models.openai.openai_model import OpenAIModel
from amsdal_ml.ml_models.primitives import ChatMessage as AgentMessage
from amsdal_ml.ml_models.primitives import MCPItem, MCPServerConfig, MessageRole, ToolCall
from amsdal_server.configs.main import settings

from models.chat import Chat
from models.chat_message import ChatMessage

SYSTEM_PROMPT = (
    'You are an assistant running inside AMSDAL with live MCP tools. '
    'Use the provided tools to read and modify data on the user\'s behalf.'
)


@async_transaction(name='mcp_agent', tags=['mcp', 'chat'])
async def mcp_agent(object_id: str | None, message: str) -> dict[str, Any]:
    message = (message or '').strip()
    if not message:
        return {'status': 'error', 'reason': 'Empty content'}

    # 1) Load or create the Chat — the whole conversation lives in this one record.
    if object_id:
        chat = await Chat.objects.get(_address__object_id=object_id).aexecute()
    else:
        chat = Chat(messages=[])
        await chat.asave()
        object_id = str(chat.object_id)

    # 2) Append the user's turn.
    chat.messages.append(
        ChatMessage(role='user', content=message, created_at=dt.datetime.now(tz=dt.UTC))
    )

    # 3) Configure the agent against AMSDAL's own MCP server, authenticated as this user.
    llm = OpenAIModel(model_name='gpt-4o', temperature=0.0)
    mcp = MCPServerConfig(name='amsdal', url=os.environ['MCP_SERVER_URL'], auth=_user_jwt())
    agent = FunctionalCallingAgent(model=llm, mcp_servers=[mcp], max_steps=5)

    # 4) Rebuild agent history from stored messages (restore tool state across turns).
    history = [AgentMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT)]
    for m in chat.messages[:-1]:
        history.append(
            AgentMessage(
                role=MessageRole(m.role),
                content=m.content,
                tool_calls=[ToolCall.from_dict(d) for d in (m.tool_calls or [])],
                mcp_items=[MCPItem.from_dict(d) for d in (m.mcp_items or [])],
            )
        )

    out = await agent.arun(user_query=message, history=history)
    answer = (out.message.content if out.message else out.answer) or ''

    # 5) Append the assistant's turn, persisting tool state for the next turn.
    chat.messages.append(
        ChatMessage(
            role='assistant',
            content=answer,
            content_type='markdown',
            created_at=dt.datetime.now(tz=dt.UTC),
            tool_calls=[tc.to_dict() for tc in out.message.tool_calls] if out.message else None,
            mcp_items=[it.to_dict() for it in out.message.mcp_items] if out.message else None,
        )
    )
    await chat.asave()

    # Return only what the `chat` control renders: user/assistant turns with the
    # documented fields. The system prompt and tool_calls/mcp_items stay in the stored
    # chat.messages (used to rebuild agent history) but are not pushed to the UI.
    return {
        'status': 'ok',
        'object_id': object_id,
        'messages': [
            {
                'role': m.role,
                'content': m.content,
                'content_type': m.content_type,
                'attachments': m.attachments,
                'created_at': m.created_at.isoformat() if m.created_at else None,
            }
            for m in chat.messages
            if m.role in ('user', 'assistant')
        ],
    }


def _user_jwt() -> str | None:
    """Forward the caller's bearer token so the agent acts with their permissions."""
    request = AmsdalContextManager().get_context().get('request')
    if not request:
        return None
    header = request.headers.get(settings.AUTHORIZATION_HEADER, '')
    return header[len('Bearer '):] if header.startswith('Bearer ') else (header or None)
```

The `body` keys in the frontend config (`object_id`, `message`) must match the transaction
parameters; the `onSuccess` `update_value` reads `{response.messages}`, which is exactly the
`messages` list this transaction returns.

## How it fits together

```
AMSDAL Console (Chat edit screen)
  └─ frontend config: chat control (messages) + input + Send button
        └─ invoke POST /api/transactions/mcp_agent/   {object_id, message}
              └─ transaction: FunctionalCallingAgent + MCPServerConfig(auth = user JWT)
                    └─ MCP server (e.g. AMSDAL's own) → tools run as the user
              ← {status, object_id, messages}
        └─ onSuccess: messages ← response.messages; pin object_id; clear input
```

## Testing locally

The chat has three network hops — browser→app (REST), app→LLM provider, provider→MCP server
— so local setup has a few moving parts:

1. **Install + register the plugin:** `pip install amsdal-ml`, add
   `amsdal_ml.app.MLPluginAppConfig` to `AMSDAL_CONTRIBS`.
2. **LLM key in `.env`:** `OPENAI_API_KEY=...` (or `ANTHROPIC_API_KEY=...`); optionally
   `llm_model_name=...`. These are `MLConfig` fields, so `.env` is enough (see [[amsdal-ml]]).
3. **Simplify auth for local:** set `oauth_enabled=false` in `.env` so the MCP endpoint takes
   the forwarded bearer JWT directly (no external OAuth dance).
4. **Expose the MCP endpoint publicly** so the LLM provider can reach it — e.g.
   `ngrok http 8080` → `https://<id>.ngrok.app`. The provider, not your app, connects to
   `/mcp/sse`, so `localhost` will not work for it.
5. **Run with the tunnel URL as a real env var:**
   `MCP_SERVER_URL=https://<id>.ngrok.app/mcp/sse amsdal serve` (not just in `.env`).
6. **Open the chat in Console:** console.amsdal.com → toggle **Guest** → set Api Domain to
   your app's REST URL (`http://localhost:8080` is fine — the browser reaches the app
   directly) → open the chat model and converse. The `Chat` model + transaction must be
   `AllowAny` / `@allow_any` for a guest to use them.

Two different URLs: Console→app REST can be `localhost`; provider→MCP must be the public
tunnel.

## Gotchas

- **Anonymous users reach the chat in Console via Guest login — no custom web UI needed.**
  On the Console (console.amsdal.com) login screen, toggling **Guest** lets a visitor enter
  just the app's Api Domain (e.g. `http://localhost:8080`) — no email/password — and use the
  app unauthenticated. They can then interact with any model/transaction whose permissions
  are `AllowAny` / `@allow_any`. So a public-facing chat does **not** need a separate
  frontend: make the `Chat` model and its transaction `AllowAny` / `@allow_any` and shoppers
  use it as guests. A custom frontend is only needed to embed the chat *outside* Console.
- **One `TypeModel`, not two.** Prefer a single embedded `ChatMessage(TypeModel)` over a
  separate persisted message table + a view model — the conversation is one `Chat` record.
- **Spell `__module_type__` with two leading underscores.** A single-underscore
  `_module_type__` is silently ignored (the model defaults to `ModuleType.USER`).
- **`MCP_SERVER_URL` must be a real env var, and reachable by the LLM provider.**
  `os.environ['MCP_SERVER_URL']` reads the process environment, and AMSDAL does **not** load
  `.env` into `os.environ` — set it on the command, e.g.
  `MCP_SERVER_URL=https://<public-host>/mcp/sse amsdal serve` (putting it only in `.env` has
  no effect). Crucially, `mcp_servers=` is forwarded **to the LLM model**, so the **provider
  (OpenAI/Anthropic) connects to this URL**, not your app — `http://localhost:8080` will not
  work for them; for local testing expose the endpoint via a public tunnel (e.g. ngrok) and
  use that URL. The `auth` on `MCPServerConfig` is forwarded to the MCP server, so permission
  checks still apply (anonymous if no JWT). (To keep MCP calls in-process on `localhost`
  instead, wire the MCP server as a `ToolClient` in `tools=` rather than `mcp_servers=`.)
- **`OpenAIModel` is async by default.** Inside the transaction use `await agent.arun(...)`;
  the model is set up by the agent as needed (see [[amsdal-ml]]).
- **This recipe is async-only.** `amsdal_ml` currently runs async-only, so the app must too —
  it assumes `async_mode: true` in `config.yml`. Per [[amsdal-models]] (Async/Sync Rule) do
  not mix sync/async; in a sync project every `a*` call (`asave`/`aexecute`/`arun`) and
  `@async_transaction` would have to become its sync counterpart, which `amsdal_ml` does not
  support today.
- **The transaction URL uses the Python def name**, not the `@async_transaction(name=...)`
  kwarg. The frontend config must call `/api/transactions/<def_name>/` — here the def is
  `mcp_agent`, so the URL is `/api/transactions/mcp_agent/` regardless of `name=`.
