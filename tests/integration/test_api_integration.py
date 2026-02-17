"""Integration tests for the consolidated API service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAPIServiceIntegration:
    """Integration tests for API service health and core functionality."""
    
    @pytest.mark.asyncio
    async def test_api_service_imports(self):
        """Test that all API service modules can be imported."""
        try:
            from services.api import main
            from services.api import cache
            from services.api import database
            from services.api.routers import auth_router, query_router
            assert main is not None
            assert cache is not None
            assert database is not None
            assert auth_router is not None
            assert query_router is not None
        except ImportError as e:
            pytest.fail(f"Failed to import API service modules: {e}")
    
    @pytest.mark.asyncio
    async def test_knowledge_service_imports(self):
        """Test that all knowledge service modules can be imported."""
        try:
            from services.knowledge import main
            from services.knowledge.ingestion import parser, chunker
            from services.knowledge.retrieval import embeddings, vector_store
            assert main is not None
            assert parser is not None
            assert chunker is not None
            assert embeddings is not None
            assert vector_store is not None
        except ImportError as e:
            pytest.fail(f"Failed to import knowledge service modules: {e}")
    
    @pytest.mark.asyncio
    async def test_inference_service_imports(self):
        """Test that all inference service modules can be imported."""
        try:
            from services.inference import main
            from services.inference.generator import llm_client
            from services.inference.optimizer import model
            assert main is not None
            assert llm_client is not None
            assert model is not None
        except ImportError as e:
            pytest.fail(f"Failed to import inference service modules: {e}")
    
    @pytest.mark.asyncio
    async def test_core_config_loading(self, test_settings):
        """Test that core configuration loads correctly."""
        from core.config.settings import Settings
        
        settings = test_settings
        assert settings.environment == "testing"
        assert settings.jwt_secret_key is not None
        assert settings.database_url is not None
        assert settings.redis_url is not None
        assert settings.qdrant_url is not None
        assert settings.chunk_size == 512
        assert settings.confidence_threshold == 0.6
    
    @pytest.mark.asyncio
    async def test_security_modules_available(self):
        """Test that security modules are properly configured."""
        try:
            from core.security.jwt import create_access_token
            from core.security.password import verify_password, hash_password
            assert create_access_token is not None
            assert verify_password is not None
            assert hash_password is not None
        except ImportError as e:
            pytest.fail(f"Failed to import security modules: {e}")
    
    @pytest.mark.asyncio
    async def test_document_parser_supported_formats(self):
        """Test that document parser supports required formats."""
        from services.knowledge.ingestion.parser import DocumentParser
        
        supported_formats = [
            "test.pdf",
            "test.docx",
            "test.doc",
            "test.txt",
            "test.md",
        ]
        
        for filename in supported_formats:
            assert DocumentParser.is_supported(filename), f"Format {filename} not supported"
    
    @pytest.mark.asyncio
    async def test_embedding_model_config(self, test_settings):
        """Test that embedding model configuration is set."""
        settings = test_settings
        assert settings.embedding_model == "BAAI/bge-small-en-v1.5"
        assert settings.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        assert settings.llm_model == "Qwen/Qwen2.5-1.5B-Instruct"
    
    @pytest.mark.asyncio
    async def test_service_client_initialization(self):
        """Test that service clients can be initialized."""
        from services.api.clients.service_client import ServiceClient
        
        client = ServiceClient(
            base_url="http://localhost:8001",
            service_name="test-service",
            timeout=30.0
        )
        
        assert client.base_url == "http://localhost:8001"
        assert client.service_name == "test-service"
        assert client.timeout == 30.0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_available(self):
        """Test that circuit breaker is properly implemented."""
        from services.api.clients.circuit_breaker import CircuitBreaker, CircuitState
        
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_rate_limiter_config(self, test_settings):
        """Test that rate limiting configuration is set."""
        settings = test_settings
        assert settings.rate_limit_requests == 100
        assert settings.rate_limit_window == 60
    
    @pytest.mark.asyncio
    async def test_cache_ttl_config(self, test_settings):
        """Test that cache TTL configuration is set."""
        settings = test_settings
        assert settings.cache_embedding_ttl == 86400
        assert settings.cache_search_ttl == 3600
        assert settings.cache_llm_response_ttl == 86400


class TestDocumentFlow:
    """Integration tests for document ingestion flow."""
    
    @pytest.mark.asyncio
    async def test_document_chunking(self):
        """Test document chunking functionality."""
        from services.knowledge.ingestion import chunker
        
        test_text = "This is a test document. " * 100
        chunks = chunker.chunk_text(test_text, chunk_size=512, overlap=50)
        
        assert len(chunks) > 0
        assert all(isinstance(chunk, str) for chunk in chunks)
    
    @pytest.mark.asyncio
    async def test_document_parser_text_extraction(self):
        """Test that document parser can extract text."""
        from services.knowledge.ingestion.parser import DocumentParser
        
        # Create a simple test file content
        test_content = b"Test document content for parsing"
        
        # Test TXT parsing
        extracted = DocumentParser.parse(test_content, "test.txt")
        assert extracted is not None
        assert len(extracted) > 0


class TestAuthFlow:
    """Integration tests for authentication flow."""
    
    @pytest.mark.asyncio
    async def test_password_hashing(self):
        """Test password hashing and verification."""
        from core.security.password import hash_password, verify_password
        
        password = "TestPassword123!"
        hashed = hash_password(password)
        
        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("WrongPassword", hashed)
    
    @pytest.mark.asyncio
    async def test_jwt_token_creation(self, test_settings):
        """Test JWT token creation."""
        from core.security.jwt import create_access_token
        from datetime import timedelta
        
        token_data = {"sub": "testuser"}
        token = create_access_token(
            data=token_data,
            expires_delta=timedelta(minutes=30)
        )
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0


class TestServiceConfiguration:
    """Test service configuration and environment setup."""
    
    @pytest.mark.asyncio
    async def test_docker_compose_services_configured(self, test_settings):
        """Test that all services are properly configured."""
        settings = test_settings
        
        # Check service URLs
        assert settings.knowledge_service_url is not None
        assert settings.inference_service_url is not None
        
        # Check database connectivity settings
        assert "postgres" in settings.database_url or "localhost" in settings.database_url
        assert settings.postgres_user is not None
        assert settings.postgres_password is not None
        assert settings.postgres_db is not None
    
    @pytest.mark.asyncio
    async def test_prometheus_metrics_config(self, test_settings):
        """Test Prometheus metrics configuration."""
        settings = test_settings
        assert settings.metrics_enabled is not None
        assert settings.metrics_port == 9090
