---
name: amsdal-ml
description: >
  AMSDAL ML plugin — embeddings, vector search, AI agents, MCP server, document ingestion.
  TRIGGER when: user works with ML features, embeddings, vector search, AI agents, MCP server, or code imports from amsdal_ml.
  DO NOT TRIGGER when: user does general ML/data-science without AMSDAL context.
user-invocable: false
---

# AMSDAL ML Plugin

Machine learning plugin for AMSDAL providing embeddings, semantic search, AI agents, and MCP server integration.

## Before you commit to anything concrete

This skill is a routing index, not a complete or current spec. Before you finalize ANY concrete artifact — a config key, an agent/tool definition, an embeddings/search call, an MCP setting, an import path, an API call — confirm it against an authoritative source FIRST:

1. `knowledge/` — if it concerns runtime behavior / debugging.
2. WebFetch the matching `docs.amsdal.com` page (map below) — for API / usage.

Do this by default, NOT only when uncertain — you cannot detect what this skill silently omits. A construct being valid Python/Pydantic, or seeming obvious, is not evidence that AMSDAL supports it.

**Docs map for this skill:**
- overview → https://docs.amsdal.com/framework/plugins/amsdal-ml/overview/
- embeddings configuration → https://docs.amsdal.com/framework/plugins/amsdal-ml/embeddings-configuration/
- semantic / vector search → https://docs.amsdal.com/framework/plugins/amsdal-ml/semantic-search/
- agents → https://docs.amsdal.com/framework/plugins/amsdal-ml/agents/
- agent tools → https://docs.amsdal.com/framework/plugins/amsdal-ml/agent-tools/
- MCP setup → https://docs.amsdal.com/framework/plugins/amsdal-ml/mcp-setup/
- document ingestion → https://docs.amsdal.com/framework/plugins/amsdal-ml/ingestion/
- NL query / create / update / delete → https://docs.amsdal.com/framework/plugins/amsdal-ml/nl-query/

## Installation & Setup

```bash
pip install amsdal-ml
```

### AppConfig Registration
```bash
AMSDAL_CONTRIBS="amsdal.contrib.auth.app.AuthAppConfig,amsdal_ml.app.MLPluginAppConfig"
```

### Environment Variables
```bash
OPENAI_API_KEY=sk-...
# For the Claude/Anthropic provider:
ANTHROPIC_API_KEY=sk-ant-...
async_mode=true
llm_model_name=gpt-4o
llm_temperature=0.0
embed_model_name=text-embedding-3-small
embed_dimensions=1536
embed_max_chunks=10
embed_max_tokens_per_chunk=800
retriever_default_k=8
```

`MLConfig` (`amsdal_ml/ml_config.py`) is a flat `pydantic-settings` model with `env_prefix=''`, `case_sensitive=False`, loaded from `.env`. Field names are also the env var names (case-insensitive).

**`.env` is read by `MLConfig` for its own fields — it is NOT loaded into `os.environ`.** So `OPENAI_API_KEY` (`openai_api_key`), `ANTHROPIC_API_KEY`, `llm_model_name`, `llm_temperature`, `oauth_enabled`, etc. resolve from `.env` (the LLM clients fall back to `ml_config`). But a plain `os.environ['X']` / `os.getenv('X')` for a name that is **not** an `MLConfig` field will **not** see a `.env`-only value — export those as real environment variables.

### Full Configuration (MLConfig)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `async_mode` | `true` | Enable async operations |
| `oauth_enabled` | `true` | Enable OAuth for MCP |
| `ml_model_class` | `amsdal_ml.ml_models.openai.openai_model.OpenAIModel` | LLM implementation for agents/ingesting |
| `mcp_ml_model_class` | `amsdal_ml.ml_models.openai.openai_model.OpenAIModel` | LLM used by the MCP server tools |
| `ml_retriever_class` | `amsdal_ml.ml_retrievers.openai_retriever.OpenAIRetriever` | Retriever implementation |
| `ml_ingesting_class` | `amsdal_ml.ml_ingesting.openai_ingesting.OpenAIIngesting` | Ingesting implementation |
| `llm_model_name` | `gpt-4o` | Default LLM model |
| `llm_temperature` | `0.0` | LLM temperature |
| `embed_model_name` | `text-embedding-3-small` | Embedding model |
| `embed_dimensions` | `1536` | Embedding vector size |
| `embed_max_depth` | `2` | Max recursion depth for text generation |
| `embed_max_chunks` | `10` | Max chunks per object |
| `embed_max_tokens_per_chunk` | `800` | Token limit per chunk |
| `retriever_default_k` | `8` | Default search results count |
| `retriever_include_tags_default` | `[]` | Default include-tags for retrieval |
| `retriever_exclude_tags_default` | `[]` | Default exclude-tags for retrieval |
| `openai_api_key` | — | OpenAI API key (env `OPENAI_API_KEY`) |
| `anthropic_api_key` | — | Anthropic/Claude API key (env `ANTHROPIC_API_KEY`) |
| `require_default_authorization` | `true` | Require authorization for MCP/CRUD operations by default |
| `embedding_targets` | `[]` | List of `EmbeddingTarget` configs (model / embedding_class / embedding_field / primary_key / fetch_fn / tags) |

OAuth-specific fields (used when `oauth_enabled=true`): `oauth_client_id_expiration_days` (30), `oauth_code_exp_minutes` (10), `oauth_access_token_exp_hours` (24), `oauth_refresh_token_exp_days` (90), `oauth_login_path` (`/auth/login`), `oauth_issuer` (`http://127.0.0.1:8000`).

## ML Models (LLM Interface)

### OpenAIModel

`OpenAIModel.__init__` is keyword-only. `setup()`/`teardown()` are **async** (`await` them). When `async_mode=true` (the default), the **sync** `invoke`/`stream` raise `RuntimeError` — use `ainvoke`/`astream`. `ainvoke` returns an `LLModelOutput`; the text is on `.content`.

```python
from amsdal_ml.ml_models.openai.openai_model import OpenAIModel

model = OpenAIModel(model_name='gpt-4o', temperature=0.0)
await model.setup()

# Async (default async_mode=true)
output = await model.ainvoke('What is machine learning?')
print(output.content)

# Streaming yields text chunks (str)
async for chunk in model.astream('Explain transformers'):
    print(chunk, end='', flush=True)

await model.teardown()
```

`OpenAIModel.setup()` reads the key from `OPENAI_API_KEY` (env) or `ml_config.openai_api_key`.

### ClaudeModel (Anthropic)

The Claude provider mirrors the same `MLModel` interface and is interchangeable with `OpenAIModel` in agents, ingesting, and the MCP model. The key is read from `ANTHROPIC_API_KEY` (env) or `ml_config.anthropic_api_key`.

```python
from amsdal_ml.ml_models.claude.claude_model import ClaudeModel

model = ClaudeModel(model_name='claude-sonnet-4-5', temperature=0.0, max_tokens=4096)
await model.setup()

output = await model.ainvoke('Summarize this changelog')
print(output.content)

async for chunk in model.astream('Explain the diff'):
    print(chunk, end='', flush=True)

await model.teardown()
```

`ClaudeModel.__init__` is keyword-only with `max_tokens` defaulting to `4096`. Its `supported_formats` are `PLAIN_TEXT` and `JSON_SCHEMA` (no `JSON_OBJECT`). To make it the default LLM, set `ml_model_class=amsdal_ml.ml_models.claude.claude_model.ClaudeModel`.

### Supported Response Formats
- `ResponseFormat.PLAIN_TEXT`
- `ResponseFormat.JSON_OBJECT` (OpenAI only)
- `ResponseFormat.JSON_SCHEMA`

### LLModelOutput

`invoke`/`ainvoke` return `LLModelOutput` (a dataclass):

```python
@dataclass
class LLModelOutput:
    content: str        # the generated text
    raw_response: Any = None  # provider-native response object
```

### Error Hierarchy
```python
from amsdal_ml.ml_models.errors import ModelError, ModelConnectionError, ModelRateLimitError, ModelAPIError
```

### Custom ML Model

`MLModel` is the ABC (re-exported from `amsdal_ml.ml_models`). `setup`/`teardown` are async; `ainvoke`/`astream` return an `LLModelOutput` / yield `str` chunks.

```python
from amsdal_ml.ml_models.base_model import MLModel  # or: from amsdal_ml.ml_models import MLModel

class MyCustomModel(MLModel):
    async def setup(self) -> None: ...
    async def teardown(self) -> None: ...
    async def ainvoke(self, input, **kwargs) -> LLModelOutput: ...
    async def astream(self, input, **kwargs) -> AsyncIterator[str]: ...
    # plus the abstract role/field properties (input_role, output_role, content_field, ...)
```

Configure in `.env`:
```bash
ml_model_class=myapp.models.MyCustomModel
```

## Embeddings & Ingesting

### EmbeddingModel (Data Model)

```python
from amsdal_ml.models.embedding_model import EmbeddingModel

# Stored in DB with:
# - data_object_class: str (source model class)
# - data_object_id: str (source object ID)
# - chunk_index: int
# - raw_text: str
# - embedding: VectorField(1536)
# - tags: list[str]
# - ml_metadata: Any
```

### Basic Ingesting

```python
from amsdal_ml.ml_ingesting.openai_ingesting import OpenAIIngesting

ingester = OpenAIIngesting(tags=['product-docs'])

# Generate embeddings from model instance
embeddings = await ingester.agenerate_embeddings(my_object)

# Save to EmbeddingModel
await ingester.asave(embeddings, my_object)
```

### Document Ingestion Pipeline

For processing files (PDF, text, etc.) into embeddings:

```python
from amsdal_ml.ml_ingesting.pipeline import DefaultIngestionPipeline
from amsdal_ml.ml_ingesting.loaders.pdf_loader import PdfLoader
from amsdal_ml.ml_ingesting.processors.text_cleaner import TextCleaner
from amsdal_ml.ml_ingesting.splitters.token_splitter import TokenSplitter
from amsdal_ml.ml_ingesting.embedders.openai_embedder import OpenAIEmbedder
from amsdal_ml.ml_ingesting.stores.embedding_data import EmbeddingDataStore

pipeline = DefaultIngestionPipeline(
    loader=PdfLoader(),
    cleaner=TextCleaner(),
    splitter=TokenSplitter(max_tokens=800, overlap_tokens=80),
    embedder=OpenAIEmbedder(),
    store=EmbeddingDataStore(),
)

# Process file — `source=` is REQUIRED, otherwise arun() raises
# RuntimeError('source is required for ingestion pipeline').
from amsdal_ml.ml_ingesting.types import IngestionSource

results = await pipeline.arun(
    open('document.pdf', 'rb'),       # first positional arg: the file object
    filename='document.pdf',
    tags=['documentation'],
    source=IngestionSource(
        object_class='Document',
        object_id='doc-123',
        tags=['knowledge-base'],
        metadata={'origin': 'upload'},
    ),
)
# Returns the list of stored embedding records.
```

> `ModelIngester` (below) builds the `IngestionSource` for you from each model instance, so prefer it when ingesting AMSDAL model objects.

### ModelIngester (High-Level)

Process AMSDAL model instances with file fields:

```python
from amsdal_ml.ml_ingesting.model_ingester import ModelIngester

ingester = ModelIngester(
    pipeline=pipeline,
    base_tags=['knowledge-base'],
    base_metadata={'source': 'uploads'},
)

results = await ingester.aingest(
    objects=my_model_objects,
    fields=['content_field'],
    tags=['extra-tag'],
)
```

### Custom Ingesting

```python
from amsdal_ml.ml_ingesting.default_ingesting import DefaultIngesting

ingester = DefaultIngesting(
    tags=['custom'],
    chunk_strategy=my_strategy,
    token_len_fn=my_token_counter,
    header_fn=lambda obj, path: f'# {obj.__class__.__name__}',
    facts_transform=my_transform_fn,
)
```

## Semantic Search (Retriever)

```python
from amsdal_ml.ml_retrievers.openai_retriever import OpenAIRetriever

retriever = OpenAIRetriever()

results = await retriever.asimilarity_search(
    query='How to configure authentication?',
    k=5,
    include_tags=['documentation'],
    exclude_tags=['deprecated'],
)

for chunk in results:
    print(f'{chunk.object_class}:{chunk.object_id} (distance: {chunk.distance})')
    print(f'Tags: {chunk.tags}')
    print(f'Text: {chunk.raw_text[:200]}...')
```

### RetrievalChunk Fields
- `object_class` — source model class name
- `object_id` — source object ID
- `chunk_index` — chunk index within object
- `raw_text` — original chunk text
- `distance` — similarity distance
- `tags` — user-defined tags
- `metadata` — additional metadata

## AI Agents

### DefaultQAAgent (ReAct Pattern)

```python
from amsdal_ml.agents.default_qa_agent import DefaultQAAgent  # or: from amsdal_ml.agents import DefaultQAAgent
from amsdal_ml.agents.structured_tools.python_tool import PythonTool  # or: from amsdal_ml.agents.structured_tools import PythonTool
from amsdal_ml.ml_models.openai.openai_model import OpenAIModel

# Define tools
async def search_products(query: str, category: str | None = None) -> str:
    """Search products in the catalog."""
    products = await Product.objects.filter(name__icontains=query).aexecute()
    return '\n'.join(f'{p.name}: ${p.price}' for p in products)

llm = OpenAIModel()
tool = PythonTool(search_products, name='search_products', description='Search products in catalog')

agent = DefaultQAAgent(
    model=llm,
    tools=[tool],
    max_steps=6,
)

# Run
output = await agent.arun('Find red products under $50')
print(output.answer)
print(f'Used tools: {output.used_tools}')
print(f'Citations: {output.citations}')

# Stream
async for chunk in agent.astream('What are the top products?'):
    print(chunk, end='', flush=True)
```

### FunctionalCallingAgent (Native Tool Use)

```python
from amsdal_ml.agents.functional_calling_agent import FunctionalCallingAgent

agent = FunctionalCallingAgent(
    model=llm,
    tools=[tool1, tool2],
    max_steps=6,
)

output = await agent.arun(
    user_query='Analyze sales data',
    history=previous_messages,  # conversation history
    attachments=[file_attachment],
)
```

### PythonTool

Auto-generates JSON Schema from the function signature (`name`/`description` are required, `func` is the first arg):

```python
from amsdal_ml.agents.structured_tools.python_tool import PythonTool

async def calculate_total(items: list[str], tax_rate: float = 0.1) -> str:
    """Calculate total price including tax."""
    ...

tool = PythonTool(
    calculate_total,
    name='calculate_total',
    description='Calculate total price with tax',
)
# tool.parameters → auto-generated JSON Schema (type/properties/required)
```

### AgentOutput

`AgentOutput` is a Pydantic model (`amsdal_ml.agents.base_agent`, re-exported from `amsdal_ml.agents`):

```python
class AgentOutput(BaseModel):
    answer: str                       # Final answer text
    message: ChatMessage | None = None  # Full assistant message (role/content/tool_calls/...)
    used_tools: list[str] = []        # Names of tools used
    citations: list[dict[str, Any]] = []  # Source citations
```

Note: `DefaultQAAgent` populates `answer` and `used_tools` and leaves `citations` empty; `FunctionalCallingAgent` may also set `message`.

### Connecting an agent to MCP servers (MCPServerConfig)

`FunctionalCallingAgent` can connect to one or more **remote MCP servers** and call their tools natively — no manual `ToolClient`/`PythonTool` wiring. Pass `mcp_servers=` a single `MCPServerConfig` or a list. This is the agent acting as an MCP **client**, and is distinct from **MCP Server Integration** below (which *exposes* AMSDAL itself as an MCP server). A common use is pointing the agent at AMSDAL's own MCP endpoint with the current user's JWT, so it executes transactions/CRUD with that user's permissions.

```python
from amsdal_ml.ml_models.openai.openai_model import OpenAIModel
from amsdal_ml.ml_models.primitives import MCPServerConfig
from amsdal_ml.agents.functional_calling_agent import FunctionalCallingAgent

mcp = MCPServerConfig(
    name='amsdal',                  # logical name (also surfaces as MCPItem.server_name)
    url='https://my-app/mcp/sse',   # remote MCP (SSE) endpoint
    auth=user_jwt,                  # optional bearer token forwarded to the server
)

agent = FunctionalCallingAgent(model=llm, mcp_servers=[mcp], max_steps=5)
out = await agent.arun(user_query='...', history=history)
```

`MCPServerConfig` fields (`amsdal_ml.ml_models.primitives`): `name`, `url`, `auth=None`, `description=None`, `tool_filter=None`, `extra_params=None`, `metadata={}`.

**Persisting tool state across turns.** When the model calls MCP tools, `AgentOutput.message` carries `mcp_items: list[MCPItem]` and `tool_calls: list[ToolCall]`. To resume a multi-turn conversation, serialize them with `.to_dict()` and restore with `.from_dict()` (`MCPItem.from_dict` dispatches on a `__type__` registry key, so subclasses like `MCPToolCall`/`MCPToolResult`/`MCPListTools` round-trip):

```python
from amsdal_ml.ml_models.primitives import MCPItem, ToolCall

stored_items = [it.to_dict() for it in out.message.mcp_items]   # save with the message
stored_calls = [tc.to_dict() for tc in out.message.tool_calls]
# next turn — rebuild the ChatMessage with restored state:
items = [MCPItem.from_dict(d) for d in stored_items]
calls = [ToolCall.from_dict(d) for d in stored_calls]
```

## Natural-Language Query (NLQuery)

The `amsdal_ml.nlquery` subsystem turns natural-language requests into CRUD against an
AMSDAL `QuerySet` using an `MLModel` to interpret the request. It is what backs the MCP
`perform_crud_operation` tool. Four facades are exported from `amsdal_ml.nlquery`:

- `NLQueryCreator` — create records
- `NLQueryRetriever` — read/filter records
- `NLQueryUpdater` — update records
- `NLQueryDeleter` — delete records

(Each also has a lower-level `*Executor` variant — `NLQueryRetrieverExecutor`, etc. —
that returns model instances instead of `Document`s.)

Every facade is constructed with `(llm, queryset, ...)` and exposes the same async flow:
`analyze(query)` → an analysis object, then `invoke(analysis)` → `list[Document]`. The
`invoke_one(query_or_analysis)` shortcut analyzes (if needed) and returns a single
`Document`.

```python
from amsdal_ml.nlquery import NLQueryRetriever
from amsdal_ml.ml_models.openai.openai_model import OpenAIModel

llm = OpenAIModel()
await llm.setup()

retriever = NLQueryRetriever(llm=llm, queryset=Product.objects.all())

# Two-step: analyze then execute
analysis = await retriever.analyze('products under $100')
documents = await retriever.invoke(analysis)

# Or one-shot
documents = await retriever.invoke_one('products under $100')

for doc in documents:
    print(doc.page_content)   # JSON-serialized record
    print(doc.metadata)       # full model_dump() of the record
```

`Document` (`amsdal_ml.ml_retrievers.retriever`) has `page_content: str` and
`metadata: dict[str, Any]`. `NLQueryCreator` / `NLQueryUpdater` / `NLQueryDeleter` follow
the same `analyze` / `invoke` / `invoke_one` shape against the same QuerySet.

## File Attachments

```python
from amsdal_ml.fileio.base_loader import FileItem, FileAttachment, BaseFileLoader

# Create from path
item = FileItem.from_path('/path/to/document.pdf')

# Create from bytes
item = FileItem.from_bytes(pdf_bytes, filename='doc.pdf')

# Create from text
item = FileItem.from_str('Plain text content', filename='note.txt')

# Use with agent
output = await agent.arun(
    user_query='Summarize this document',
    attachments=[await loader.load(item)],
)
```

**Attachment types:**
- `PLAIN_TEXT` — text content sent inline
- `FILE_ID` — file uploaded to provider, referenced by ID

## MCP Server Integration

AMSDAL ML exposes an MCP server when running with `amsdal serve`.

### Available MCP Tools (HTTP server, mounted with `amsdal serve`)

Exposed by the model-explorer server (`amsdal_ml/mcp_server/server_model_explorer/tools/`):

- `list_available_models` — discover registered AMSDAL models (optionally filter by scope)
- `list_available_transactions` — discover executable AMSDAL transactions
- `list_available_skills` — list registered `AmsdalSkill` entries and their triggers
- `get_model_schema` — full JSON schema of a model
- `get_model_relationships` — FK/M2M relationships (outgoing + incoming)
- `perform_crud_operation` — natural-language CRUD (backed by the NLQuery subsystem)
- `perform_transaction_operation` — run an AMSDAL transaction from natural language (two-step `confirm=false` then `confirm=true`)

> `search` (semantic search) is **only** registered by the standalone stdio server (`server_retriever_stdio.py`), not by the HTTP server.

### Permissions

MCP tools run through AMSDAL's normal permission system — the MCP surface is **not** a
bypass:

- `perform_transaction_operation` executes via the same
  `TransactionExecutionApi.execute_transaction` as the REST `/api/transactions/` endpoint,
  so each transaction's auth decorators (`@allow_any` / `@require_auth` / `@permissions`)
  apply.
- `perform_crud_operation` and the read tools enforce class- and object-level permissions
  (`authorize_class` / `authorize_object`; row-level via `api_objects`).
- The request's JWT is bridged into AMSDAL context (`with_amsdal_context`); an
  unauthenticated caller runs in anonymous context.

Net effect: a client reaches exactly what its principal could reach through the REST API —
no more.

### MCP Endpoint

A single SSE app is mounted at `/mcp` (`mcp_server.sse_app()` → `context.app.mount('/mcp', ...)`); the SSE endpoint itself is `/mcp/sse`.

```
/mcp          # mounted MCP (SSE) app
/mcp/sse      # SSE endpoint clients connect to
```

### Claude Desktop Integration

```json
{
  "mcpServers": {
    "my-amsdal-app": {
      "url": "http://localhost:8080/mcp/sse"
    }
  }
}
```

### Standalone MCP Server (Stdio)

```bash
python -m amsdal_ml.mcp_server.server_retriever_stdio \
  --amsdal-config "$(echo '{"async_mode": true, ...}' | base64)"
```

### MCP Client

Both clients implement the `ToolClient` protocol: `list_tools() -> list[ToolInfo]` and `call(tool_name, args, *, timeout=None)`.

```python
from amsdal_ml.mcp_client.stdio_client import StdioClient
from amsdal_ml.mcp_client.http_client import HttpClient

# Stdio transport — StdioClient(alias, module_or_cmd, *args, persist_session=True, send_amsdal_config=True)
# Launch a python module:
client = StdioClient('local', 'my_mcp_server')          # runs `python -m my_mcp_server`
# Or an explicit command:
client = StdioClient('local', 'python', '-m', 'my_mcp_server')
tools = await client.list_tools()
result = await client.call('search', {'query': 'machine learning'})

# HTTP transport — keyword-only alias/url (+ optional headers)
client = HttpClient(alias='remote', url='http://localhost:8080/mcp/sse')
tools = await client.list_tools()
```

### Using MCP Tools with Agents

```python
from amsdal_ml.agents.functional_calling_agent import FunctionalCallingAgent

agent = FunctionalCallingAgent(
    model=llm,
    tools=[python_tool, mcp_client],  # MCP client implements ToolClient protocol
)

output = await agent.arun('Search for relevant documents about pricing')
```

## OAuth Support

When `oauth_enabled=true`, MCP endpoints are protected with OAuth:

```bash
oauth_enabled=true
oauth_client_id_expiration_days=30
oauth_code_exp_minutes=10
oauth_access_token_exp_hours=24
oauth_refresh_token_exp_days=90
oauth_login_path=/auth/login
oauth_issuer=http://127.0.0.1:8000
```

## Testing ML Code

Don't mock the model with a bare `AsyncMock`: `ainvoke`/`astream` must return an
`LLModelOutput` (text on `.content`), and `DefaultQAAgent` parses the model output
as ReAct markup (`Thought:`/`Action:`/`Final Answer:`). Instead implement a small
fake `MLModel` that returns scripted `LLModelOutput`s, mirroring the amsdal_ml test
suite (`tests/agents_tests/test_fakes.py`):

```python
import pytest

from amsdal_ml.agents.default_qa_agent import DefaultQAAgent
from amsdal_ml.ml_models.base_model import MLModel
from amsdal_ml.ml_models.primitives import LLModelOutput
from amsdal_ml.ml_models.response_format import ResponseFormat


class FakeModel(MLModel):
    def __init__(self, *, async_mode: bool, scripted: list[str]):
        self.async_mode = async_mode
        self._scripted = list(scripted)

    @property
    def adapter(self):
        from amsdal_ml.ml_models.openai.openai_adapter import OpenAIAdapter
        return OpenAIAdapter()

    @property
    def supported_formats(self) -> set[ResponseFormat]:
        return {ResponseFormat.PLAIN_TEXT, ResponseFormat.JSON_SCHEMA}

    # role/field properties required by the ABC
    @property
    def input_role(self) -> str: return 'user'
    @property
    def output_role(self) -> str: return 'assistant'
    @property
    def tool_role(self) -> str: return 'tool'
    @property
    def system_role(self) -> str: return 'system'
    @property
    def content_field(self) -> str: return 'content'
    @property
    def role_field(self) -> str: return 'role'
    @property
    def tool_call_id_field(self) -> str: return 'tool_call_id'
    @property
    def tool_name_field(self) -> str: return 'name'

    async def setup(self) -> None: ...
    async def teardown(self) -> None: ...

    async def ainvoke(self, input, **kwargs) -> LLModelOutput:  # noqa: A002
        return LLModelOutput(content=self._scripted.pop(0))

    def invoke(self, input, **kwargs) -> LLModelOutput:  # noqa: A002
        return LLModelOutput(content=self._scripted.pop(0))

    async def astream(self, input, **kwargs):  # noqa: A002
        yield self._scripted.pop(0)

    def stream(self, input, **kwargs):  # noqa: A002
        yield self._scripted.pop(0)


@pytest.mark.asyncio
async def test_agent_returns_final_answer():
    # ReAct: a single step with no tool call → Final Answer
    model = FakeModel(
        async_mode=True,
        scripted=['Thought: Do I need to use a tool? No\nFinal Answer: Done\n'],
    )
    agent = DefaultQAAgent(model=model, tools=[])
    output = await agent.arun('Test query')
    assert output.answer == 'Done'


# From amsdal_ml test fixtures (tests/conftest.py):
# - FakeSyncClient / FakeAsyncClient replace the OpenAI clients
# - Use @pytest.mark.usefixtures('patch_openai') to inject them
# - OPENAI_API_KEY is set to a dummy value ('sk-test-123') in tests
```

## Architecture Summary

```
amsdal_ml/
├── app.py                    # MLPluginAppConfig — plugin entry point
├── ml_config.py              # MLConfig — all settings from .env
├── ml_models/
│   ├── base_model.py         # MLModel ABC
│   ├── base_adapter.py       # BaseAdapter ABC
│   ├── primitives.py         # LLModelOutput, ChatMessage, BaseTool, ...
│   ├── response_format.py    # ResponseFormat enum
│   ├── errors.py             # Error hierarchy
│   ├── openai/
│   │   └── openai_model.py   # OpenAIModel implementation
│   └── claude/
│       └── claude_model.py   # ClaudeModel (Anthropic) implementation
├── ml_retrievers/
│   ├── retriever.py          # MLRetriever ABC, RetrievalChunk, Document
│   └── openai_retriever.py   # OpenAI embeddings search
├── ml_ingesting/
│   ├── ingesting.py          # MLIngesting ABC
│   ├── default_ingesting.py  # DefaultIngesting with chunking
│   ├── openai_ingesting.py   # OpenAI embeddings generation
│   ├── pipeline.py           # DefaultIngestionPipeline
│   ├── model_ingester.py     # ModelIngester for AMSDAL models
│   ├── types.py              # IngestionSource, chunk/page types
│   ├── loaders/              # PdfLoader, etc.
│   ├── processors/           # TextCleaner
│   ├── splitters/            # TokenSplitter
│   ├── embedders/            # OpenAIEmbedder
│   └── stores/               # EmbeddingDataStore
├── agents/
│   ├── base_agent.py         # Agent ABC, AgentOutput
│   ├── default_qa_agent.py   # ReAct agent
│   ├── functional_calling_agent.py  # Function calling agent
│   ├── structured_tools/     # PythonTool wrapper
│   ├── tools/                # built-in tools (e.g. retriever_search)
│   ├── mcp/                  # MCP connectors for agents
│   └── memory/               # agent memory
├── nlquery/                  # NL→CRUD: NLQueryCreator/Retriever/Updater/Deleter
├── mcp_server/
│   ├── server_model_explorer/  # HTTP (SSE) server tools (crud/discovery/execution)
│   ├── server_retriever_stdio.py  # standalone stdio server (search tool)
│   └── mcp_oauth/            # OAuth routes/middleware + /mcp mount
├── mcp_client/               # MCP client (StdioClient + HttpClient)
├── fileio/                   # File I/O (loaders, attachments)
├── prompts/                  # prompt templates (agents, mcp, nl_query)
├── utils/                    # shared helpers
└── models/
    └── embedding_model.py    # EmbeddingModel (AMSDAL model)
```