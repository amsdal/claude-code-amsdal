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
async_mode=true
llm_model_name=gpt-4o
llm_temperature=0.0
embed_model_name=text-embedding-3-small
embed_dimensions=1536
embed_max_chunks=10
embed_max_tokens_per_chunk=800
retriever_default_k=8
```

### Full Configuration (MLConfig)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `async_mode` | `true` | Enable async operations |
| `ml_model_class` | `amsdal_ml.ml_models.openai_model.OpenAIModel` | LLM implementation |
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
| `openai_api_key` | — | OpenAI API key |
| `claude_api_key` | — | Claude API key |
| `oauth_enabled` | `true` | Enable OAuth for MCP |

## ML Models (LLM Interface)

### OpenAIModel

```python
from amsdal_ml.ml_models.openai_model import OpenAIModel

model = OpenAIModel(model_name='gpt-4o', temperature=0.0)
model.setup()

# Sync
response = model.invoke('What is machine learning?')

# Async
response = await model.ainvoke('What is machine learning?')

# Streaming
async for chunk in model.astream('Explain transformers'):
    print(chunk, end='', flush=True)

model.teardown()
```

### Supported Response Formats
- `ResponseFormat.PLAIN_TEXT`
- `ResponseFormat.JSON_OBJECT`
- `ResponseFormat.JSON_SCHEMA`

### Error Hierarchy
```python
from amsdal_ml.ml_models.errors import ModelError, ModelConnectionError, ModelRateLimitError, ModelAPIError
```

### Custom ML Model
```python
from amsdal_ml.ml_models.models import MLModel

class MyCustomModel(MLModel):
    def setup(self): ...
    def teardown(self): ...
    async def ainvoke(self, input, **kwargs) -> str: ...
    async def astream(self, input, **kwargs) -> AsyncIterator[str]: ...
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

# Process file
results = await pipeline.arun(
    file=open('document.pdf', 'rb'),
    filename='document.pdf',
    tags=['documentation'],
)
```

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
from amsdal_ml.agents.default_qa_agent import DefaultQAAgent
from amsdal_ml.agents.python_tool import PythonTool
from amsdal_ml.ml_models.openai_model import OpenAIModel

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

Auto-generates JSON Schema from function signature:

```python
from amsdal_ml.agents.python_tool import PythonTool

async def calculate_total(items: list[str], tax_rate: float = 0.1) -> str:
    """Calculate total price including tax."""
    ...

tool = PythonTool(
    func=calculate_total,
    name='calculate_total',
    description='Calculate total price with tax',
)
# tool.parameters → auto-generated JSON Schema
```

### AgentOutput
```python
class AgentOutput(BaseModel):
    answer: str                     # Final answer text
    used_tools: list[str]          # Names of tools used
    citations: list[dict[str, Any]] # Source citations
```

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

### Available MCP Tools
- `list_available_models` — discover AMSDAL models
- `get_model_schema` — full JSON schema of a model
- `get_model_relationships` — foreign key relationships
- `get_model_field_values_by_ids` — retrieve field values
- `perform_crud_operation` — natural language CRUD
- `search` — semantic search in knowledge base

### MCP Endpoints
```
/mcp          # MCP endpoint
/mcp/sse      # SSE-based MCP endpoint
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

```python
from amsdal_ml.mcp_client.stdio_client import StdioClient
from amsdal_ml.mcp_client.http_client import HttpClient

# Stdio transport
client = StdioClient(command='python', args=['-m', 'my_mcp_server'])
tools = await client.list_tools()
result = await client.call('search', {'query': 'machine learning'})

# HTTP transport
client = HttpClient(url='http://localhost:8080/mcp/sse')
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

```python
import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_model():
    model = AsyncMock()
    model.ainvoke.return_value = 'Mocked response'
    return model


@pytest.mark.asyncio
async def test_agent_run(mock_model):
    agent = DefaultQAAgent(model=mock_model, tools=[])
    output = await agent.arun('Test query')
    assert output.answer == 'Mocked response'


# From amsdal_ml test fixtures (conftest.py):
# - FakeSyncClient / FakeAsyncClient mock OpenAI clients
# - Use @pytest.mark.usefixtures('patch_openai') to inject mocks
# - OPENAI_API_KEY set to dummy value in tests
```

## Architecture Summary

```
amsdal_ml/
├── app.py                    # MLPluginAppConfig — plugin entry point
├── ml_config.py              # MLConfig — all settings from .env
├── ml_models/
│   ├── models.py             # MLModel ABC
│   ├── openai_model.py       # OpenAI implementation
│   └── errors.py             # Error hierarchy
├── ml_retrievers/
│   ├── retriever.py          # MLRetriever ABC, RetrievalChunk
│   └── openai_retriever.py   # OpenAI embeddings search
├── ml_ingesting/
│   ├── ingesting.py          # MLIngesting ABC
│   ├── default_ingesting.py  # DefaultIngesting with chunking
│   ├── openai_ingesting.py   # OpenAI embeddings generation
│   ├── pipeline.py           # DefaultIngestionPipeline
│   ├── model_ingester.py     # ModelIngester for AMSDAL models
│   ├── loaders/              # PdfLoader, etc.
│   ├── processors/           # TextCleaner
│   ├── splitters/            # TokenSplitter
│   ├── embedders/            # OpenAIEmbedder
│   └── stores/               # EmbeddingDataStore
├── agents/
│   ├── agent.py              # Agent ABC, AgentOutput
│   ├── default_qa_agent.py   # ReAct agent
│   ├── functional_calling_agent.py  # Function calling agent
│   └── python_tool.py        # PythonTool wrapper
├── mcp_server/               # MCP server (SSE + stdio)
├── mcp_client/               # MCP client (stdio + HTTP)
├── fileio/                   # File I/O (loaders, attachments)
└── models/
    └── embedding_model.py    # EmbeddingModel (AMSDAL model)
```