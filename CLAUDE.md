# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Enterprise SLM-First Knowledge Copilot - A microservices-based AI knowledge management system that uses Small Language Models (SLMs) as primary routing/processing layers, with LLM escalation only when necessary.

## Architecture

The system uses a **consolidated 3-service architecture** (not 7 as originally designed):

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Service (Port 8000)                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐   │
│  │   Gateway   │  │    Auth     │  │        Metrics          │   │
│  │  (Entry)    │  │  (JWT/RBAC) │  │  (Prometheus + Audit)     │   │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
┌─────────────────────────┐       ┌─────────────────────────┐
│   Knowledge Service     │       │   Inference Service     │
│      (Port 8001)        │       │      (Port 8002)        │
│  ┌─────────────────┐   │       │  ┌─────────────────┐   │
│  │  Search Engine  │   │       │  │ Query Optimizer │   │
│  │  (Qdrant +      │   │       │  │   (Qwen SLM)    │   │
│  │   Embeddings)   │   │       │  └─────────────────┘   │
│  ├─────────────────┤   │       │  ┌─────────────────┐   │
│  │  Ingestion     │   │       │  │    Generator    │   │
│  │  (Parse/Chunk/  │   │       │  │  (LLM/vLLM)     │   │
│  │   Embed)       │   │       │  └─────────────────┘   │
│  └─────────────────┘   │       └─────────────────────────┘
└─────────────────────────┘
```

### Service Dependencies

- **API Service**: Depends on PostgreSQL, Redis, Knowledge Service, Inference Service
- **Knowledge Service**: Depends on PostgreSQL, Qdrant (embedding model loaded at startup)
- **Inference Service**: Depends on vLLM (model loaded at startup)

### Query Flow

1. **API Service** receives query → validates JWT (in-process)
2. **Inference Service** `/optimize` → expands query, returns confidence score
3. If confidence < 0.6: Return clarification request to user
4. **Knowledge Service** `/search` → vector search with RBAC + reranking
5. **Inference Service** `/generate` → generate answer from context
6. **API Service** records metrics (in-process via Prometheus + DB)
7. Return response to client

## Common Commands

### Development Setup

```bash
# Create environment file
cp .env.example .env

# Install dependencies (using uv)
uv sync

# Or using pip
pip install -e ".[dev]"
```

### Running Services

```bash
# Start all services (Docker Compose)
make up

# Start individual infrastructure services
make up-postgres   # PostgreSQL only
make up-redis      # Redis only
make up-qdrant     # Qdrant only

# View logs
make logs
make logs-api         # API Service logs only
make logs-knowledge   # Knowledge Service logs only
make logs-inference   # Inference Service logs only
```

### Testing

Tests use **pytest** with async support. The `make test` command automatically runs `make validate` first.

```bash
# Validate project setup (checks Python, deps, Docker, tests)
make validate

# Run all tests (includes validation)
make test

# Run specific test categories
make test-unit           # Unit tests only (no services needed)
make test-integration    # Integration tests (requires running services)

# Other test options
make test-quick          # Stop on first failure (-x flag)
make test-coverage       # Generate HTML coverage report
make test-watch          # Watch mode (requires pytest-watch)

# Run a specific test
pytest tests/unit/test_auth/test_jwt.py::TestJWTHandler::test_create_access_token -v
```

### Linting and Formatting

```bash
# Ruff (linting and import sorting)
ruff check .                    # Check for issues
ruff check --fix .              # Auto-fix issues
ruff format .                   # Format code

# Type checking
mypy services/ core/

# Pre-commit hooks
pre-commit run --all-files
```

### Database Operations

```bash
# Run migrations
make db-migrate

# Reset database (dangerous - drops all data)
make db-reset

# Seed with test data
make db-seed

# Access PostgreSQL shell
make shell-postgres

# Access Redis CLI
make shell-redis
```

### Running Services Locally (Development)

```bash
# Terminal 1 - API Service
uvicorn services.api.main:app --reload --port 8000

# Terminal 2 - Knowledge Service
uvicorn services.knowledge.main:app --reload --port 8001

# Terminal 3 - Inference Service
uvicorn services.inference.main:app --reload --port 8002
```

## Key Code Locations

### Configuration
- `core/config/settings.py` - Pydantic settings (environment variables)
- `.env.example` - Template for environment variables

### Service Communication
- `services/api/clients/service_client.py` - HTTP client with circuit breaker pattern
- `services/api/clients/circuit_breaker.py` - Circuit breaker for resilience

### Query Processing
- `services/api/routers/query.py` - Main query orchestration flow
- `services/inference/optimizer/` - Query optimization (SLM)
- `services/inference/generator/` - Answer generation (LLM)
- `services/knowledge/retrieval/` - Vector search and reranking

### Authentication
- `core/security/jwt.py` - JWT token handling
- `core/security/deps.py` - FastAPI dependencies for auth
- `services/api/routers/auth.py` - Auth endpoints

### Database
- `services/api/database/models.py` - SQLAlchemy models
- `services/api/database/auth_db.py` - Auth database operations (asyncpg)
- `services/api/database/metrics_db.py` - Metrics/audit operations

### Testing
- `tests/conftest.py` - Shared pytest fixtures
- `tests/unit/` - Unit tests
- `tests/integration/` - Integration tests
- `scripts/validate.py` - Environment validation script

## Important Patterns

### Service Client Usage
Services communicate via HTTP using the `ServiceClient` class with built-in circuit breaker:

```python
from services.api.clients import service_clients

# Get client for external service
knowledge_client = service_clients.get_knowledge_client()
inference_client = service_clients.get_inference_client()

# Make requests
response = await inference_client.post("/optimize", data={"query": "..."})
results = await knowledge_client.post("/search", data={"queries": [...]})
```

### Caching
Redis caching is implemented via `CacheManager` in `services/api/cache.py`:
- Search results: `cache.get_search_cache()` / `set_search_cache()`
- LLM responses: `cache.get_llm_response_cache()` / `set_llm_response_cache()`

### Database Sessions
Two database patterns are used:
1. **Auth DB** (`services/api/database/auth_db.py`): asyncpg for user queries
2. **Metrics DB** (`services/api/database/metrics_db.py`): SQLAlchemy async for metrics/audit

### Settings Access
Always use the cached settings function:
```python
from core.config.settings import get_settings

settings = get_settings()
# Access: settings.database_url, settings.jwt_secret_key, etc.
```

## Technology Stack

- **Framework**: FastAPI with async/await
- **Models**: Qwen-2.5 (1.5B for optimizer, 14B for generator fallback)
- **Embeddings**: BAAI/bge-small-en-v1.5
- **Reranker**: cross-encoder/ms-marco-MiniLM-L-6-v2
- **Vector DB**: Qdrant
- **Relational DB**: PostgreSQL 16 (asyncpg)
- **Cache**: Redis
- **Inference**: vLLM
- **Testing**: pytest with pytest-asyncio
- **Linting**: Ruff

## Environment Variables

Key variables in `.env`:
- `DATABASE_URL` - PostgreSQL connection
- `REDIS_URL` - Redis connection
- `QDRANT_URL` - Qdrant connection
- `JWT_SECRET_KEY` - JWT signing key
- `KNOWLEDGE_SERVICE_URL` / `INFERENCE_SERVICE_URL` - Internal service URLs
- `VLLM_URL` - vLLM inference endpoint
- `CONFIDENCE_THRESHOLD` - Query optimization threshold (default: 0.6)
