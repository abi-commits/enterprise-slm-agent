# Enterprise SLM-First Knowledge Copilot - Makefile
# Consolidated architecture: 3 application services + infrastructure

# Colors
GREEN = \033[0;32m
YELLOW = \033[1;33m
BLUE = \033[0;34m
NC = \033[0m # No Color

# Help target
.PHONY: help
help:
	@echo ""
	@echo -e "$(BLUE)Enterprise SLM-First Knowledge Copilot - Makefile$(NC)"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Development:"
	@echo "  up                  - Start all services with docker compose"
	@echo "  down                - Stop all services"
	@echo "  restart             - Restart all services"
	@echo "  logs                - View logs from all services"
	@echo "  logs-follow         - Follow logs from all services"
	@echo "  build               - Build all service images"
	@echo "  rebuild             - Rebuild all service images (no cache)"
	@echo ""
	@echo "Individual Services:"
	@echo "  up-postgres         - Start PostgreSQL only"
	@echo "  up-redis            - Start Redis only"
	@echo "  up-qdrant           - Start Qdrant only"
	@echo "  up-minio            - Start MinIO only"
	@echo "  up-vllm             - Start vLLM only"
	@echo "  up-api              - Start API Service only"
	@echo "  up-knowledge        - Start Knowledge Service only"
	@echo "  up-inference        - Start Inference Service only"
	@echo ""
	@echo "Database:"
	@echo "  db-migrate          - Run database migrations (alembic upgrade head)"
	@echo "  db-rollback         - Rollback one migration"
	@echo "  db-rollback-all     - Rollback all migrations"
	@echo "  db-history          - Show migration history"
	@echo "  db-current          - Show current migration"
	@echo "  db-generate         - Generate new migration from models"
	@echo "  db-reset            - Reset database (danger!)"
	@echo "  db-seed             - Seed database with test data"
	@echo ""
	@echo "Development:"
	@echo "  shell-api           - Shell into API Service"
	@echo "  shell-knowledge     - Shell into Knowledge Service"
	@echo "  shell-inference     - Shell into Inference Service"
	@echo "  shell-postgres      - Shell into PostgreSQL"
	@echo "  shell-redis         - Shell into Redis"
	@echo ""
	@echo "Testing & Validation:"
	@echo "  validate            - Validate project setup and dependencies"
	@echo "  test                - Run all tests (includes validation)"
	@echo "  test-quick          - Run tests in quick mode (stop on first failure)"
	@echo "  test-unit           - Run unit tests only"
	@echo "  test-integration    - Run integration tests only"
	@echo "  test-coverage       - Run tests with coverage report"
	@echo "  test-watch          - Run tests in watch mode (requires pytest-watch)"
	@echo ""
	@echo "Utilities:"
	@echo "  clean               - Remove all containers, volumes, and images"
	@echo "  clean-data          - Remove data volumes only"
	@echo "  ports              - Show port mappings"
	@echo "  health             - Check health of all services"
	@echo "  env                - Copy .env.example to .env"
	@echo ""

# =============================================================================
# Development Commands
# =============================================================================

up:
	@echo -e "$(GREEN)Starting all services...$(NC)"
	docker compose up -d
	@echo ""
	@echo -e "$(GREEN)Services started!$(NC)"
	@echo "API Service:       http://localhost:8000"
	@echo "Knowledge Service: http://localhost:8001"
	@echo "Inference Service: http://localhost:8002"
	@echo "Qdrant:            http://localhost:6333"
	@echo "PostgreSQL:        localhost:5432"
	@echo "Redis:             localhost:6379"
	@echo "MinIO:             http://localhost:9000"

down:
	@echo -e "$(YELLOW)Stopping all services...$(NC)"
	docker compose down

restart:
	@echo -e "$(YELLOW)Restarting all services...$(NC)"
	docker compose restart

logs:
	docker compose logs -f

logs-follow:
	docker compose logs -f

build:
	@echo -e "$(GREEN)Building all service images...$(NC)"
	docker compose build

rebuild:
	@echo -e "$(YELLOW)Rebuilding all service images (no cache)...$(NC)"
	docker compose build --no-cache

# =============================================================================
# Individual Services
# =============================================================================

up-postgres:
	docker compose up -d postgres

up-redis:
	docker compose up -d redis

up-qdrant:
	docker compose up -d qdrant

up-minio:
	docker compose up -d minio

up-vllm:
	docker compose up -d vllm

up-api:
	docker compose up -d api-service

up-knowledge:
	docker compose up -d knowledge-service

up-inference:
	docker compose up -d inference-service

# Service-specific logs
logs-api:
	docker compose logs -f api-service

logs-knowledge:
	docker compose logs -f knowledge-service

logs-inference:
	docker compose logs -f inference-service

# =============================================================================
# Database Commands
# =============================================================================

db-migrate:
	@echo -e "$(GREEN)Running database migrations...$(NC)"
	alembic upgrade head

db-migrate-offline:
	@echo -e "$(GREEN)Generating offline migration SQL...$(NC)"
	alembic upgrade head --sql > migrations.sql

db-rollback:
	@echo -e "$(YELLOW)Rolling back one migration...$(NC)"
	alembic downgrade -1

db-rollback-all:
	@echo -e "$(YELLOW)Rolling back all migrations...$(NC)"
	alembic downgrade base

db-history:
	@echo -e "$(BLUE)Migration history:$(NC)"
	alembic history --verbose

db-current:
	@echo -e "$(BLUE)Current migration:$(NC)"
	alembic current

db-generate:
	@echo -e "$(GREEN)Generating new migration...$(NC)"
	@read -p "Migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

db-reset:
	@echo -e "$(YELLOW)WARNING: Resetting database...$(NC)"
	docker compose down -v
	docker compose up -d postgres
	sleep 5
	alembic upgrade head
	@echo -e "$(GREEN)Database reset complete!$(NC)"

db-seed:
	@echo -e "$(GREEN)Seeding database...$(NC)"
	python -m scripts.seed_database

# =============================================================================
# Shell Access
# =============================================================================

shell-api:
	docker compose exec api-service /bin/sh

shell-knowledge:
	docker compose exec knowledge-service /bin/sh

shell-inference:
	docker compose exec inference-service /bin/sh

shell-postgres:
	docker compose exec postgres psql -U slm_user -d slm_knowledge

shell-redis:
	docker compose exec redis redis-cli

# =============================================================================
# Testing
# =============================================================================

validate:
	@echo -e "$(BLUE)Validating project setup...$(NC)"
	python scripts/validate.py

test: validate
	@echo -e "$(GREEN)Running all tests...$(NC)"
	pytest tests/ -v --tb=short

test-quick:
	@echo -e "$(GREEN)Running tests (quick mode)...$(NC)"
	pytest tests/ -v --tb=short -x

test-unit:
	@echo -e "$(GREEN)Running unit tests...$(NC)"
	pytest tests/unit/ -v --tb=short

test-integration:
	@echo -e "$(GREEN)Running integration tests...$(NC)"
	pytest tests/integration/ -v --tb=short

test-coverage:
	@echo -e "$(GREEN)Running tests with coverage...$(NC)"
	pytest tests/ --cov=services --cov=core --cov-report=html --cov-report=term-missing
	@echo -e "$(GREEN)Coverage report generated in htmlcov/index.html$(NC)"

test-watch:
	@echo -e "$(GREEN)Running tests in watch mode...$(NC)"
	ptw -- tests/unit/ -v

# =============================================================================
# Utilities
# =============================================================================

clean:
	@echo -e "$(YELLOW)Stopping and removing all containers, volumes, and images...$(NC)"
	docker compose down -v --rmi all

clean-data:
	@echo -e "$(YELLOW)Removing data volumes only...$(NC)"
	docker compose down -v

ports:
	@echo ""
	@echo "Port Mappings:"
	@echo "=============="
	@docker compose ps --format "table {{.Name}}\t{{.Ports}}"

health:
	@echo ""
	@echo "Service Health Status:"
	@echo "======================="
	@curl -s http://localhost:8000/health 2>/dev/null && echo " API:        HEALTHY" || echo "API:        UNHEALTHY"
	@curl -s http://localhost:8001/health 2>/dev/null && echo " Knowledge:  HEALTHY" || echo "Knowledge:  UNHEALTHY"
	@curl -s http://localhost:8002/health 2>/dev/null && echo " Inference:  HEALTHY" || echo "Inference:  UNHEALTHY"
	@curl -s http://localhost:6333/health 2>/dev/null && echo " Qdrant:     HEALTHY" || echo "Qdrant:     UNHEALTHY"

env:
	@echo -e "$(GREEN)Creating .env from .env.example...$(NC)"
	cp .env.example .env
	@echo -e "$(GREEN).env file created! Please update with your values.$(NC)"

# =============================================================================
# Quick Start
# =============================================================================

.PHONY: quickstart
quickstart: env up
	@echo ""
	@echo -e "$(GREEN)========================================$(NC)"
	@echo -e "$(GREEN)  Quick Start Complete!$(NC)"
	@echo -e "$(GREEN)========================================$(NC)"
	@echo ""
	@echo "Next steps:"
	@echo "1. Update .env with your values"
	@echo "2. Access the API at http://localhost:8000"
	@echo "3. Run 'make logs' to see service logs"
	@echo ""
