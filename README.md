# Enterprise SLM-First Knowledge Copilot

A multi-user, API-first, SLM-first Enterprise Knowledge Copilot designed to serve enterprise knowledge queries using Small Language Models (SLMs) as primary routing and processing layers, with escalation to Large Language Models (LLMs) only when necessary.

## Architecture Overview

The system follows a microservices architecture with the following components:

```
Client
   ↓
API Gateway (Entry Point)
   ↓
Auth Service (JWT + RBAC)
   ↓
Query Optimizer Service (SLM - Qwen)
   ↓
Confidence Check (Threshold ≥ 0.6?)
   ├── No → Request Clarification / Escalate
   ↓
   Yes
   ↓
Search Engine Service
(Retrieval + Permission Filter + Reranker)
   ↓
Generator Service (LLM / SLM)
   ↓
Response Builder
   ↓
Metrics + Audit Service
   ↓
Client Response
```

## Project Structure

```
slm_first/
├── services/
│   ├── gateway/          # API Gateway - Entry point for all client requests
│   ├── auth/            # Authentication Service - JWT + RBAC
│   ├── query_optimizer/ # Query Optimizer Service - SLM-based query processing
│   ├── search/          # Search Engine Service - Vector search + Reranker
│   ├── generator/       # Generator Service - LLM fallback for complex tasks
│   ├── metrics/         # Metrics & Audit Service - Observability
│   └── ingestion/      # Document Ingestion Service - Document processing
├── core/
│   ├── config/          # Configuration management
│   ├── security/        # Security utilities (JWT, password hashing)
│   └── models/          # Pydantic models and data classes
├── tests/
│   ├── unit/            # Unit tests
│   ├── integration/     # Integration tests
│   └── fixtures/        # Test fixtures
├── pyproject.toml       # Project dependencies
└── README.md           # This file
```

## Technology Stack

### Core Frameworks
- **Language:** Python 3.11+
- **API Framework:** FastAPI (Async/Await)
- **Data Validation:** Pydantic V2
- **Environment Management:** uv / Poetry

### AI & Models (SLM-First)
- **Query Optimizer:** Qwen-2.5 (1.5B or 7B) - served via vLLM
- **Embeddings:** BAAI/bge-small-en-v1.5
- **Reranker:** cross-encoder/ms-marco-MiniLM-L-6-v2
- **Generator (Fallback):** Qwen-2.5-14B or external LLM API
- **Inference Engine:** vLLM

### Data Infrastructure
- **Vector Database:** Qdrant
- **Relational Database:** PostgreSQL 16
- **State Store:** Redis
- **Object Storage:** MinIO (S3 compatible) or local filesystem

### Security & Operations
- **Authentication:** OAuth2 with Password Flow + JWT
- **Logging:** Structlog
- **Monitoring:** Prometheus + Grafana
- **Containerization:** Docker & Docker Compose

## Prerequisites

- Python 3.11 or higher
- Docker and Docker Compose
- PostgreSQL 16 (can be run via Docker)
- Redis (can be run via Docker)
- Qdrant (can be run via Docker)

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd slm_first
```

### 2. Create Virtual Environment

Using uv:
```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

Using venv:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

Using uv:
```bash
uv sync
```

Using pip:
```bash
pip install -e ".[dev]"
```

### 4. Environment Configuration

Create a `.env` file in the project root:

```env
# Application
APP_NAME=slm-first
APP_VERSION=0.1.0
DEBUG=false
LOG_LEVEL=INFO

# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=slm_first

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# JWT
JWT_SECRET_KEY=your-super-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30

# Service URLs
AUTH_SERVICE_URL=http://localhost:8001
GATEWAY_SERVICE_URL=http://localhost:8000
QUERY_OPTIMIZER_URL=http://localhost:8002
SEARCH_SERVICE_URL=http://localhost:8003
GENERATOR_SERVICE_URL=http://localhost:8004
METRICS_SERVICE_URL=http://localhost:8005
INGESTION_SERVICE_URL=http://localhost:8006

# Model Configuration
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
SLM_MODEL=qwen/Qwen2.5-1.5B-Instruct
LLM_MODEL=qwen/Qwen2.5-14B-Instruct

# Confidence Thresholds
OPTIMIZER_CONFIDENCE_THRESHOLD=0.6
RERANKER_UNCERTAINTY_THRESHOLD=0.3
```

### 5. Start Infrastructure Services

Using Docker Compose:

```bash
docker compose up -d postgres redis qdrant
```

### 6. Run Database Migrations

```bash
# Create initial database schema
python -m core.config.init_db
```

## Running the Services

### Development Mode

You can run individual services for development:

```bash
# Terminal 1 - Auth Service
uvicorn services.auth.main:app --reload --port 8001

# Terminal 2 - Gateway Service
uvicorn services.gateway.main:app --reload --port 8000

# Terminal 3 - Query Optimizer
uvicorn services.query_optimizer.main:app --reload --port 8002

# Terminal 4 - Search Service
uvicorn services.search.main:app --reload --port 8003

# Terminal 5 - Generator Service
uvicorn services.generator.main:app --reload --port 8004

# Terminal 6 - Metrics Service
uvicorn services.metrics.main:app --reload --port 8005

# Terminal 7 - Ingestion Service
uvicorn services.ingestion.main:app --reload --port 8006
```

### Docker Compose (All Services)

```bash
docker compose up -d
```

## API Endpoints

### Gateway Service (Port 8000)
- `POST /v1/query` - Submit a knowledge query
- `GET /health` - Health check

### Auth Service (Port 8001)
- `POST /v1/auth/login` - User login
- `POST /v1/auth/validate` - Validate JWT token
- `POST /v1/auth/refresh` - Refresh access token

### Query Optimizer Service (Port 8002)
- `POST /v1/optimize` - Optimize and expand query
- `GET /health` - Health check

### Search Service (Port 8003)
- `POST /v1/search` - Vector search with RBAC
- `POST /v1/rerank` - Re-rank search results
- `GET /health` - Health check

### Generator Service (Port 8004)
- `POST /v1/generate` - Generate response from context
- `GET /health` - Health check

### Metrics Service (Port 8005)
- `GET /v1/metrics` - Prometheus metrics
- `GET /v1/audit-log` - Historical audit logs
- `GET /health` - Health check

### Ingestion Service (Port 8006)
- `POST /v1/documents` - Upload a new document
- `GET /v1/documents/{id}/status` - Check ingestion status
- `DELETE /v1/documents/{id}` - Remove a document
- `GET /health` - Health check

## User Roles

The system supports the following roles:
- **Admin** - Full system access
- **HR** - HR documents access
- **Engineering** - Engineering documents access
- **Finance** - Finance documents access
- **Operations** - Operations documents access

## Testing

Run tests:

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# With coverage
pytest --cov=services --cov=core --cov-report=html
```

## Monitoring

### Prometheus Metrics

Access Prometheus metrics at: `http://localhost:8005/v1/metrics`

### Structured Logs

Logs are output in JSON format via Structlog for easy parsing by log aggregation systems.

## Development Guidelines

1. **Code Style**: Follow PEP 8, enforced via Ruff
2. **Type Hints**: Use type hints for all function signatures
3. **Testing**: Write unit tests for all new features
4. **Documentation**: Update API documentation when endpoints change
5. **Logging**: Use Structlog for all logging needs

## License

MIT License - See LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request
