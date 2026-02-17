# Enterprise SLM-First Knowledge Copilot
## Architectural System Design Document

## 1. Overview

This document describes the system architecture for a multi-user, API-first, SLM-first Enterprise Knowledge Copilot.

The system is designed to:
- Serve enterprise knowledge queries
- Use Small Language Models (SLMs) as primary routing and processing layers
- Escalate to Large Language Models (LLMs) only when necessary
- Enforce multi-user role-based access control
- Provide full observability and cost tracking
- Be deployable via containerized microservices

**This is a enyerprise production-oriented architecture**

---

## 2. System Goals

### Functional Goals
- Multi-user support with RBAC
- Secure document retrieval
- Query optimization using SLM
- Confidence-based routing
- Optional LLM fallback
- Audit logging and observability

### Non-Functional Goals
- Low latency for common tasks (<500ms target)
- Reduced LLM dependency (60–80% reduction target)
- Modular service design
- Replaceable model components
- Vendor independence
- API-first design

---

## 3. High-Level Architecture

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

---

## 4. Microservice Breakdown

### 4.1 Gateway Service

**Responsibilities:**
- Entry point for all client requests
- Orchestrates calls between services
- Applies routing logic
- Implements confidence thresholds
- Logs request metadata

**Endpoints:**
- `POST /query` - Submit a query
- `GET /health` - Health check

---

### 4.2 Auth Service

**Responsibilities:**
- JWT authentication
- Role-based access control (RBAC)
- User identity management

**User Roles (V1):**
- Admin
- HR
- Engineering
- Finance
- Operations

**Endpoints:**
- `POST /login` - User login
- `POST /validate` - Validate JWT token

---

### 4.3 Query Optimizer Service (SLM)

**Model:** Qwen-2.5 (1.5B or 7B)

**Responsibilities:**
- Query expansion and enrichment
- Keyword extraction
- Query rephrasing for better retrieval (HyDE or similar)
- Confidence scoring on query clarity

**Output:**
```json
{
  "optimized_queries": ["query 1", "query 2"],
  "confidence": 0.85
}
```

---

### 4.4 Search Engine Service (Retrieval + Rerank)

**Note:** Consolidated Retrieval, Permission Filter, and Reranker for performance.

**Responsibilities:**
- Vector search via Qdrant
- Enforce document-level RBAC (Permission Filter)
- Re-rank top-K documents using Cross-Encoder
- Generate semantic embeddings

**Technology Stack:**
- Qdrant (vector DB)
- BAAI/bge-small-en-v1.5 (embeddings)
- cross-encoder/ms-marco-MiniLM-L-6-v2 (reranker)

---

### 4.5 Generator Service (LLM Fallback)

**Responsibilities:**
- Handle complex reasoning tasks
- Generate final answers when escalation required
- Track token usage and cost

**Escalation Conditions:**
- Optimizer confidence < 0.6 (threshold)
- Reranker ambiguity high
- Context complexity exceeds threshold

---

### 4.6 Metrics & Audit Service

**Responsibilities:**
- Log request metadata:
  - `user_id`
  - `query_confidence`
  - `branch_taken`
  - `escalation_flag`
  - `latency_per_service`
  - `token_usage` (if LLM invoked)
- Provide metrics endpoints

**Endpoints:**
- `GET /metrics` - Prometheus metrics
- `GET /audit-log` - Historical audit logs

---

## 5. Data Layer

### 5.1 PostgreSQL
- Users and roles
- Audit logs
- Routing decisions
- RBAC mappings

### 5.2 Vector Database (Qdrant)
- Document embeddings
- Metadata (department, access role)

### 5.3 Object Storage
- Raw enterprise documents
- MinIO (S3 compatible) or local filesystem

---

## 6. Routing Logic

### Default Flow
1. **Validate user** via Auth Service
2. **Optimize query** via Query Optimizer Service (Qwen)
3. **Confidence Check:**
   - If confidence ≥ 0.6 → proceed to Retrieval
   - If confidence < 0.6 → request clarification or escalate
4. **Retrieve** documents from vector DB
5. **Rerank** documents using Cross-Encoder
6. **Generate** answer via Generator Service
7. **Return** response to client

---

## 7. Confidence Threshold Strategy

### Initial Configuration
- **Optimizer threshold:** 0.6
- **Reranker uncertainty threshold:** configurable
- **Escalation flag:** logged per request

### Future Enhancements
- Adaptive thresholds based on user role
- Dynamic threshold tuning via metrics feedback

---

## 8. Observability Strategy

### Key Metrics to Track
- LLM escalation rate
- Average latency per service
- Token usage trends
- Cost saved vs LLM-only baseline
- Query optimization success rate

**This enables cost-awareness and architectural optimization.**

---

## 9. Deployment Architecture

### Containerized Services
Each service has:
- FastAPI application
- Dockerfile
- Health endpoint (`/health`)

### Orchestration
- Docker Compose (V1) - Initial deployment
- Kubernetes-ready structure (future)

---

## 10. Security Considerations

- JWT-based authentication
- Strict service-to-service boundaries
- No direct LLM access to full document corpus
- Role-filtered retrieval before generation
- All decisions and queries logged
- Encryption for sensitive data in transit

---

## 11. Architectural Principles

- **SLM-first routing** - Use small models for classification/optimization
- **LLM as escalation, not default** - Minimize LLM usage
- **Replaceable model services** - Swap models without code changes
- **Observability-driven AI** - Track all decisions for improvement
- **Vendor independence** - No lock-in to proprietary services
- **Service isolation** - Clear boundaries and contracts
- **Stateless model services** - Enable horizontal scaling

---

## 12. Future Enhancements

- UI layer (Next.js or Streamlit)
- Domain specialization (Finance, Healthcare)
- Adaptive routing based on user patterns
- Human-in-the-loop escalation
- A/B testing for model variants
- Cost dashboard visualization
- Multi-language support

---

## 12.1 Document Ingestion Pipeline

### Overview
A dedicated service for processing and indexing new documents into the system.

### Flow
```
Document Upload → Parser → Chunking → Embedding → Qdrant + RBAC Metadata
```

### 12.1.1 Ingestion Service

**Responsibilities:**
- Accept document uploads (PDF, DOCX, TXT, Markdown)
- Parse and extract text content
- Chunk documents into semantic segments
- Generate embeddings using BAAI/bge-small-en-v1.5
- Store embeddings in Qdrant with RBAC metadata
- Track ingestion status and errors

**Endpoints:**
- `POST /documents` - Upload a new document
- `GET /documents/{id}/status` - Check ingestion status
- `DELETE /documents/{id}` - Remove a document

**Chunking Strategy:**
- Default chunk size: 512 tokens
- Overlap: 50 tokens
- Preserve metadata: source, department, access_role

---

## 12.2 Error Handling & Resilience

### Service Health & Circuit Breakers
- All services expose `/health` endpoint
- Implement circuit breaker patterns for inter-service calls
- Graceful degradation when services are unavailable

### Retry Policy
- Default retry: 3 attempts with exponential backoff
- Retryable errors: network timeouts, 503 Service Unavailable
- Non-retryable: 400 Bad Request, 401 Unauthorized, 404 Not Found

### Dead Letter Queue
- Failed requests logged to PostgreSQL for manual review
- Alerting on failure rates > 5%

### Error Response Format
```json
{
  "error": "error_code",
  "message": "human_readable_message",
  "request_id": "uuid",
  "timestamp": "ISO8601"
}
```

---

## 12.3 Caching Strategy

### Redis Caching Layer

| Cache Key Pattern | TTL | Description |
|-------------------|-----|-------------|
| `embedding:{hash}` | 24h | Query embedding results |
| `search:{user_role}:{query_hash}` | 1h | Search results with RBAC |
| `llm_response:{prompt_hash}` | 24h | LLM response caching |

### Cache Invalidation
- On document deletion: invalidate related search caches
- On role change: invalidate all user caches
- On document update: rebuild embeddings and invalidate

---

## 12.4 Rate Limiting & Quotas

### Per-User Rate Limiting (Gateway Service)
- Default: 100 requests/minute
- Authenticated users: 500 requests/minute
- Admin users: unlimited

### LLM Token Quotas
- Monthly quota per role (configurable)
- Department-level spending caps
- Warning at 80% quota utilization

### Implementation
- Use Redis for distributed rate limiting
- Track token usage in Metrics & Audit Service
- Return 429 Too Many Requests when exceeded

---

## 12.5 Data Validation & Security

### Input Validation
- Validate all incoming queries via Pydantic models
- Sanitize user input to prevent prompt injection
- Max query length: 1000 characters
- Max file upload size: 50MB

### PII Detection
- Detect potential PII in queries (emails, phone numbers, SSN patterns)
- Redact PII before sending to embedding/retrieval services
- Log PII detection events for audit

### Prompt Injection Prevention
- Reject queries containing known prompt injection patterns
- Use sandboxed prompting for LLM generation
- Validate LLM outputs before returning to client

---

## 12.6 API Versioning

### Version Strategy
- URL-based versioning: `/v1/`, `/v2/`
- Default version: v1
- Deprecation timeline: 12 months notice before retiring versions

### Endpoints
- `/v1/query` - Query endpoint (v1)
- `/v2/query` - Query endpoint (v2 with improvements)
- `/v1/documents` - Document ingestion (v1)
- `/v2/documents` - Document ingestion (v2)

---

## 13. Tools & Technologies Stack

### Core Frameworks
- **Language:** Python 3.11+
- **API Framework:** FastAPI (Async/Await)
- **Orchestration:** LangGraph (Stateful agent workflows)
- **Data Validation:** Pydantic V2
- **Environment Management:** Poetry or uv

### AI & Models (SLM-First)
- **Query Optimizer:** Qwen-2.5 (1.5B or 7B) - served via vLLM
- **Embeddings:** BAAI/bge-small-en-v1.5 (High performance, low latency)
- **Reranker:** cross-encoder/ms-marco-MiniLM-L-6-v2
- **Generator (Fallback):** Qwen-2.5-14B or external LLM API
- **Inference Engine:** vLLM (Critical for <500ms latency)

### Data Infrastructure
- **Vector Database:** Qdrant (Docker: `qdrant/qdrant:latest`)
- **Relational Database:** PostgreSQL 16
- **State Store:** Redis (LangGraph state & conversation history)
- **Object Storage:** MinIO (S3 compatible) or local filesystem

### Security & Operations
- **Authentication:** OAuth2 with Password Flow + JWT (python-jose)
- **Containerization:** Docker & Docker Compose
- **Monitoring:** Prometheus + Grafana
- **Logging:** Structlog

### Development Tools
- **Linting/Formatting:** Ruff
- **Testing:** Pytest, Testcontainers
- **Version Control:** Git

---

## 14. Architectural Differentiator

This system demonstrates:

✓ **Heterogeneous model orchestration** - Multiple SLMs + fallback LLM
✓ **Confidence-based routing** - Intelligent decision on when to escalate
✓ **Enterprise-grade RBAC enforcement** - Document-level access control
✓ **Cost-aware AI infrastructure** - Minimize LLM token usage
✓ **Production microservice design** - Containerized, observable, scalable

---

**Document Version:** 1.0  
**Last Updated:** February 2026  
**Status:** Ready for Implementation