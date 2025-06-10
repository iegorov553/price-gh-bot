# 🧪 Comprehensive Testing System

A robust, multi-level testing framework for the Price-GH-Bot that ensures reliability across unit, integration, and end-to-end scenarios.

## 🏗️ Architecture

```
tests_new/
├── unit/                   # Fast, isolated tests (< 1s each)
│   ├── test_commission_contracts.py   # Commission calculation logic
│   ├── test_shipping_contracts.py     # Shipping estimation logic
│   └── test_currency_contracts.py     # Currency conversion logic
├── integration/            # Component interaction tests (mocked external deps)
│   └── test_bot_handlers.py          # Handler workflow tests
├── e2e/                    # Full workflow tests (real external services)
│   └── test_real_urls.py             # Real eBay/Grailed scraping
├── fixtures/               # Test data and expectations
│   └── test_data.json               # Current test expectations
├── utils/                  # Test utilities
│   └── data_updater.py              # Auto-update test expectations
└── conftest.py            # Global fixtures and configuration
```

## 🚀 Quick Start

### Prerequisites
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Install browser for E2E tests
playwright install chromium

# Setup pre-commit hooks (optional)
pre-commit install
```

### Running Tests

#### Command Line
```bash
# Run all unit tests (fastest)
pytest tests_new/unit/ -v

# Run integration tests  
pytest tests_new/integration/ -v

# Run E2E tests (slowest, requires network)
BOT_TOKEN=8026508902:AAGWJKei_EyPkpc4x-lt-qFQo53829gQIrU pytest tests_new/e2e/ -v

# Run all tests with coverage
pytest tests_new/ --cov=app --cov-report=html
```

#### Using Makefile
```bash
# Install Makefile and run tests
ln -s Makefile.test Makefile

make test-unit           # Fast unit tests
make test-integration    # Integration tests  
make test-e2e           # End-to-end tests
make test-all           # Complete test suite
make test-coverage      # Tests with coverage report
```

#### Using Docker
```bash
# Run all tests in isolation
docker-compose -f docker-compose.test.yml up test-all

# Run specific test level
docker-compose -f docker-compose.test.yml up test-unit
docker-compose -f docker-compose.test.yml up test-integration
docker-compose -f docker-compose.test.yml up test-e2e

# Development environment
docker-compose -f docker-compose.test.yml up test-dev -d
docker exec -it <container> bash
```

## 📊 Test Categories

### Unit Tests (Fast, Isolated)
- **Commission Contracts**: Verify pricing logic with various scenarios
- **Shipping Contracts**: Test weight estimation and cost calculation
- **Currency Contracts**: Validate exchange rate handling

**Characteristics:**
- Run in < 1 second each
- No external dependencies
- Use mocked configurations
- Focus on business logic correctness

### Integration Tests (Component Interaction)
- **Bot Handlers**: Test message processing workflows
- **Scraper Integration**: Verify scraper + calculator interaction
- **Response Formatting**: Test complete response generation

**Characteristics:**
- Mock external services (eBay, Grailed, CBR API)
- Test component interactions
- Verify data flow between modules
- Focus on integration correctness

### End-to-End Tests (Real Services)
- **Real URL Scraping**: Test with actual eBay/Grailed listings
- **Currency API**: Verify CBR API integration
- **Complete Pipeline**: Full URL-to-RUB conversion flow

**Characteristics:**
- Use real external services
- May be slower and less reliable
- Test actual marketplace behavior
- Focus on real-world scenarios

## 🔧 Configuration

### Environment Variables
```bash
# Required for all tests
BOT_TOKEN=8026508902:AAGWJKei_EyPkpc4x-lt-qFQo53829gQIrU

# Optional configuration
ENABLE_HEADLESS_BROWSER=true   # For E2E seller analysis tests
LOG_LEVEL=INFO                 # Test logging level
ENVIRONMENT=test               # Test environment marker
```

### pytest.ini
The test suite uses comprehensive pytest configuration:
- Strict mode for markers and config
- Async test support
- Coverage configuration
- Custom markers for test categorization
- Timeout handling for slow tests

### Test Markers
```python
@pytest.mark.unit          # Fast unit tests
@pytest.mark.integration   # Integration tests  
@pytest.mark.e2e          # End-to-end tests
@pytest.mark.slow         # Slow tests (> 5s)
@pytest.mark.network      # Requires network access
@pytest.mark.browser      # Requires headless browser
```

## 📈 Test Data Management

### Automated Updates
The system includes automated test data updating:

```bash
# Update test expectations from real data
python tests_new/utils/data_updater.py

# Update specific categories
python -c "
from tests_new.utils.data_updater import TestDataUpdater
import asyncio

async def main():
    updater = TestDataUpdater()
    await updater.update_shipping_expectations()
    await updater.update_currency_ranges()

asyncio.run(main())
"
```

### Fixture Management
- **Static fixtures**: `tests_new/fixtures/test_data.json`
- **Dynamic fixtures**: `tests_new/conftest.py`
- **Generated fixtures**: Auto-updated from real data

## 🏭 CI/CD Integration

### GitHub Actions
The test suite integrates with GitHub Actions for automated testing:

```yaml
# .github/workflows/test-and-deploy.yml provides:
- Lint and type checking
- Unit tests with coverage
- Integration tests  
- E2E tests (on main branch)
- Security scanning
- Docker build verification
- Performance benchmarks
```

### Pre-commit Hooks
Automated quality checks before commits:
- Code formatting (Ruff)
- Linting (Ruff + MyPy)
- Fast unit tests
- Basic validation

```bash
# Setup once
pre-commit install

# Runs automatically on git commit
# Or manually: pre-commit run --all-files
```

## 📊 Coverage and Quality

### Coverage Reports
```bash
# Generate HTML coverage report
pytest tests_new/ --cov=app --cov-report=html
open htmlcov/index.html

# Terminal coverage summary
pytest tests_new/ --cov=app --cov-report=term

# Fail if coverage below threshold
pytest tests_new/ --cov=app --cov-fail-under=70
```

### Quality Metrics
- **Unit test coverage**: Target 80%+
- **Integration coverage**: Target 70%+
- **E2E success rate**: Monitor external service reliability
- **Performance benchmarks**: Track regression

## 🐛 Debugging Failed Tests

### Common Issues

#### Environment Setup
```bash
# Missing bot token
export BOT_TOKEN=8026508902:AAGWJKei_EyPkpc4x-lt-qFQo53829gQIrU

# Missing dependencies
pip install -r requirements-dev.txt

# Browser not installed
playwright install chromium
```

#### Test Data Drift
```bash
# Update expectations from real data
python tests_new/utils/data_updater.py

# Check which URLs are still accessible
make test-verify
```

#### Network Issues
```bash
# Skip E2E tests if network unavailable
pytest tests_new/unit/ tests_new/integration/ -v

# Run with increased timeouts
pytest tests_new/e2e/ -v --timeout=180
```

### Verbose Debugging
```bash
# Maximum verbosity
pytest tests_new/ -v -s --tb=long

# Stop on first failure
pytest tests_new/ -x

# Run specific test
pytest tests_new/unit/test_commission_contracts.py::TestCommissionContracts::test_commission_calculation_contract -v
```

## 🔮 Future Enhancements

### Planned Features
- **Mutation testing**: Verify test quality
- **Property-based testing**: Generate edge cases
- **Visual regression testing**: UI component testing
- **Load testing**: Performance under load
- **Chaos engineering**: Resilience testing

### Performance Optimizations
- **Parallel execution**: Run tests concurrently
- **Smart test selection**: Only run affected tests
- **Test result caching**: Skip unchanged tests
- **Resource pooling**: Reuse expensive setup

## 📚 Best Practices

### Writing Tests
```python
# Good: Descriptive test names
def test_commission_calculation_with_high_shipping_above_threshold():
    pass

# Good: Clear assertions with error messages
assert result.commission == expected, f"Commission failed for {description}"

# Good: Use fixtures for common setup
def test_commission_logic(commission_test_cases, mock_config):
    pass
```

### Test Organization
- **One concept per test**: Focus on single behavior
- **Arrange-Act-Assert**: Clear test structure
- **Independent tests**: No test depends on another
- **Deterministic**: Tests pass/fail consistently

### Performance Guidelines
- **Unit tests**: < 1 second each
- **Integration tests**: < 5 seconds each  
- **E2E tests**: < 60 seconds each
- **Total suite**: < 10 minutes

## 🎯 Success Metrics

The testing system achieves:

✅ **Reliability**: Catch regressions before deployment  
✅ **Confidence**: Deploy with certainty  
✅ **Speed**: Fast feedback during development  
✅ **Coverage**: Comprehensive scenario testing  
✅ **Maintainability**: Self-updating test data  
✅ **Documentation**: Tests as living documentation  

---

🧪 **Happy Testing!** This system ensures every change is thoroughly validated before reaching production.