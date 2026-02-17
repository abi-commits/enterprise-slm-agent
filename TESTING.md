# Testing & Validation Guide

This guide covers testing, validation, and quality assurance for the SLM-First Knowledge Copilot.

## Quick Start

### 1. Validate Your Setup

Before running any tests, validate your development environment:

```bash
make validate
```

This checks:
- Python version (3.11+)
- Required dependencies
- Project structure
- Docker setup
- Docker services running status
- Pytest configuration

### 2. Run Tests

```bash
# Run all tests
make test

# Run only unit tests
make test-unit

# Run only integration tests
make test-integration

# Run tests with coverage report
make test-coverage

# Run tests in quick mode (stop on first failure)
make test-quick

# Run tests in watch mode (requires pytest-watch)
make test-watch
```

## Test Organization

```
tests/
├── conftest.py              # Shared pytest fixtures and configuration
├── fixtures/                # Test data and mocks
│   └── __init__.py
├── unit/                    # Unit tests (isolated component tests)
│   ├── test_auth/
│   ├── test_security/
│   ├── test_models/
│   ├── test_metrics/
│   ├── test_search/
│   ├── test_generator/
│   ├── test_query_optimizer/
│   ├── test_gateway/
│   └── test_evaluation/
└── integration/             # Integration tests (service-to-service)
    └── test_api_integration.py
```

## Running Tests Locally

### Prerequisites

1. **Install dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```

2. **Start services** (for integration tests):
   ```bash
   make up
   ```

3. **Create .env file**:
   ```bash
   cp .env.example .env
   ```

### Unit Tests (No Services Required)

Unit tests are isolated and don't require running services:

```bash
make test-unit
```

These tests cover:
- Authentication logic
- Security utilities (JWT, password hashing)
- Data models and validation
- Schema validation
- Prompt generation
- Metrics calculation

### Integration Tests

Integration tests validate interactions between services:

```bash
make test-integration
```

These tests check:
- Module imports across all services
- Configuration loading
- Service client initialization
- Document parsing pipeline
- Authentication flow
- Service connectivity

**Note**: Some integration tests require running services. The tests will skip gracefully if services are unavailable.

## Test Coverage

Generate a coverage report:

```bash
make test-coverage
```

This creates an HTML report in `htmlcov/index.html`:

```bash
# Open coverage report
open htmlcov/index.html  # macOS
# or
xdg-open htmlcov/index.html  # Linux
```

## Writing Tests

### Basic Test Structure

```python
import pytest

class TestMyFeature:
    """Test cases for my feature."""
    
    @pytest.mark.asyncio
    async def test_something(self):
        """Test description."""
        # Arrange
        expected = "value"
        
        # Act
        result = some_function()
        
        # Assert
        assert result == expected
```

### Using Fixtures

Fixtures are reusable test components:

```python
def test_with_user(test_user_data):
    """Test using test user fixture."""
    assert test_user_data["username"] == "testuser"

def test_with_settings(test_settings):
    """Test using test settings fixture."""
    assert test_settings.environment == "testing"
```

Available fixtures in `tests/conftest.py`:
- `test_settings` - Test configuration
- `test_user_data` - Standard user test data
- `admin_user_data` - Admin user test data
- `mock_settings` - Mocked settings object
- `mock_http_client` - Mocked HTTP client
- `event_loop` - Async event loop

### Testing Async Code

Use `@pytest.mark.asyncio` decorator:

```python
@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await async_function()
    assert result is not None
```

## Validation Strategy

### Pre-Test Validation

The `validate` command checks:

1. **Environment Readiness**
   - Python version
   - Installed packages
   - Project structure

2. **Docker Setup**
   - Docker is running
   - Docker Compose configuration exists
   - Services are properly configured

3. **Pytest Configuration**
   - Test discovery works
   - Fixtures are available
   - Configuration is valid

### Test-Time Validation

Tests automatically validate:

1. **Module Imports** - All services and core modules load correctly
2. **Configuration** - Settings load with expected values
3. **Security** - Password hashing and JWT work correctly
4. **Data Parsing** - Documents can be parsed in supported formats
5. **Service Connectivity** - Service clients can be initialized
6. **Persistence** - Database and cache connections are configured

## Debugging Tests

### Run with Verbose Output

```bash
pytest tests/ -v -v
```

### Run with Full Traceback

```bash
pytest tests/ --tb=long
```

### Run Specific Test

```bash
# Run specific test class
pytest tests/unit/test_auth/test_auth_routes.py::TestLoginEndpoint

# Run specific test method
pytest tests/unit/test_auth/test_auth_routes.py::TestLoginEndpoint::test_login_success
```

### Use Print Debugging

```python
def test_something():
    result = some_function()
    print(f"\nResult: {result}")  # Using -s flag to see output
    assert result is not None
```

Run with `-s` to see print statements:
```bash
pytest tests/ -s
```

### Use PDB (Python Debugger)

```python
def test_something():
    result = some_function()
    breakpoint()  # Will drop into debugger
    assert result is not None
```

Run with `--pdb` to stop at first failure:
```bash
pytest tests/ --pdb
```

## Continuous Integration

### Local Pre-commit Hook

Setup pre-commit to validate before commits:

```bash
pre-commit install
```

### CI/CD Pipeline

For GitHub Actions, see `.github/workflows/` for:
- Running tests on pull requests
- Coverage report generation
- Test result reporting

## Performance Testing

### Monitor Test Execution Time

```bash
pytest tests/ --durations=10
```

Shows the 10 slowest tests.

### Parallel Execution

Install pytest-xdist:
```bash
pip install pytest-xdist
```

Run tests in parallel:
```bash
pytest tests/ -n auto
```

## Troubleshooting

### Tests Fail on Import

**Issue**: `ModuleNotFoundError: No module named 'services'`

**Solution**: 
```bash
pip install -e .  # Install package in editable mode
```

### Async Test Timeout

**Issue**: Tests hang or timeout

**Solution**: Check `conftest.py` for proper event loop configuration

### Service Connection Errors

**Issue**: Integration tests fail to connect to services

**Solution**:
```bash
make up  # Start services
make test-integration  # Run integration tests
```

### Database Connection Issues

**Issue**: "Connection refused" errors

**Solution**:
```bash
# Check PostgreSQL is running
make ps
# Check database credentials in .env match docker-compose.yml
# Restart database
make down
make up-postgres
```

## Best Practices

1. **Keep Tests Independent** - Each test should be able to run standalone
2. **Use Fixtures** - Share common setup through fixtures, not copy-paste
3. **Test Behavior** - Test what the code does, not how it does it
4. **Meaningful Assertions** - Use clear assertion messages
5. **Mock External Services** - Don't rely on external APIs in tests
6. **Cover Edge Cases** - Test error paths and boundary conditions
7. **Keep Tests Fast** - Avoid slow I/O in unit tests
8. **Use Descriptive Names** - Test names should describe what they test

## Next Steps

- ✅ Run `make validate` to check your setup
- ✅ Run `make test-unit` to verify code logic
- ✅ Run `make test-integration` to verify service integration
- ✅ Run `make test-coverage` to identify gaps
- ✅ Write tests for new features before implementation (TDD)

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [FastAPI Testing](https://fastapi.tiangolo.com/advanced/testing-events/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
