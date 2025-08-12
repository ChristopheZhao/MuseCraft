# Comprehensive Integration Test Suite

This directory contains a comprehensive integration test and validation suite for the short video generation platform. The test suite is designed to validate system integration, performance, error handling, and deployment readiness.

## 📋 Test Suite Overview

### Test Categories

1. **End-to-End Workflow Tests** (`test_comprehensive_e2e_workflow.py`)
   - Complete user journey testing
   - Multi-agent workflow validation
   - Interactive editing workflows
   - Multi-language support testing
   - API integration testing

2. **System Integration Validation** (`test_system_integration_validation.py`)
   - Database and Redis integration
   - API and WebSocket integration
   - AI service integration chains
   - File storage integration
   - Component boundary validation

3. **Performance Benchmarks** (`test_performance_benchmarks.py`)
   - API response time benchmarks
   - Concurrent request performance
   - Workflow execution performance
   - System resource utilization
   - Database performance under load
   - WebSocket performance testing

4. **Error Scenarios and Recovery** (`test_error_scenarios_and_recovery.py`)
   - AI service timeout recovery
   - Database connection failure recovery
   - Partial workflow failure recovery
   - Resource exhaustion handling
   - Cascading failure recovery
   - Chaos engineering tests

5. **Deployment Validation** (`test_deployment_validation.py`)
   - Environment configuration validation
   - Database deployment readiness
   - Redis deployment readiness
   - API endpoints validation
   - Security configuration testing
   - Production deployment checklist

6. **Monitoring and Health Checks** (`test_monitoring_and_health_checks.py`)
   - System metrics collection
   - Application metrics tracking
   - Real-time monitoring dashboard
   - Threshold-based alerting
   - Comprehensive health checks

7. **CI/CD Integration** (`test_ci_cd_integration.py`)
   - Build process validation
   - Automated test execution
   - Code quality checks
   - Security scanning
   - Deployment artifact generation

## 🚀 Quick Start

### Prerequisites

```bash
# Install test dependencies
pip install -r requirements.txt
pip install pytest-json-report pytest-html pytest-xdist pytest-timeout

# Setup test databases
export DATABASE_URL="postgresql://test:test@localhost:5432/test_db"
export REDIS_URL="redis://localhost:6379/0"

# Create storage directories
mkdir -p storage/{uploads,generated,temp}
```

### Running Tests

#### Run All High Priority Tests
```bash
python ../scripts/run_integration_tests.py --priority high
```

#### Run Specific Test Suites
```bash
python ../scripts/run_integration_tests.py --suites e2e integration deployment
```

#### Run All Tests (Comprehensive)
```bash
python ../scripts/run_integration_tests.py --all
```

#### Run Tests with Specific Markers
```bash
pytest -m "integration and not slow"
pytest -m "e2e or performance"
pytest -m "deployment"
```

### Using pytest directly

```bash
# Run end-to-end tests
pytest tests/test_comprehensive_e2e_workflow.py -v

# Run performance tests
pytest tests/test_performance_benchmarks.py -v --tb=short

# Run with JSON report
pytest tests/ -v --json-report --json-report-file=test_report.json

# Run with HTML report
pytest tests/ --html=report.html --self-contained-html
```

## 📊 Test Configuration

### Pytest Configuration
The test suite uses `pytest-integration.ini` for configuration:

- **Markers**: Integration, e2e, performance, load, error_scenarios, deployment, monitoring, ci_cd
- **Timeouts**: 300 seconds default, configurable per test
- **Async Support**: Full asyncio support enabled
- **Reporting**: JSON and HTML reports supported
- **Logging**: Comprehensive logging to files and console

### Environment Variables

#### Required
- `DATABASE_URL`: Test database connection string
- `REDIS_URL`: Test Redis connection string
- `SECRET_KEY`: Test secret key (minimum 32 characters)

#### Optional
- `OPENAI_API_KEY`: For AI service integration tests
- `STABILITY_API_KEY`: For image generation tests
- `UPLOAD_PATH`: File upload directory (default: storage/uploads)
- `GENERATED_PATH`: Generated files directory (default: storage/generated)
- `TEMP_PATH`: Temporary files directory (default: storage/temp)

#### CI/CD Environment
- `CI`: Set to "true" in CI environment
- `GITHUB_ACTIONS`: Set automatically by GitHub Actions
- `PYTEST_CURRENT_TEST`: Set during test execution

## 🏗️ Test Architecture

### Test Fixtures

#### Database Fixtures
- `test_db_session`: Async database session for testing
- `test_engine`: Test database engine
- `sample_task`: Pre-created test task

#### Redis Fixtures
- `test_redis`: Test Redis connection
- `mock_websocket`: Mock WebSocket connection

#### Storage Fixtures
- `test_storage_dirs`: Temporary storage directories
- `integration_helper`: Test helper utilities

#### Mock Fixtures
- `mock_ai_services`: Mocked AI service providers
- `mock_celery_tasks`: Mocked Celery task execution

### Test Helpers

#### IntegrationTestHelper
Provides utilities for:
- Waiting for task completion
- Creating test files
- Validating outputs
- Performance measurement

#### Performance Thresholds
- API response time: 2.0 seconds
- WebSocket latency: 0.5 seconds
- Task processing time: 60.0 seconds
- Memory usage: 500 MB
- CPU usage: 80%

## 📈 Performance Testing

### Load Testing Configuration
```python
load_test_config = {
    'concurrent_users': 10,
    'requests_per_user': 5,
    'ramp_up_time': 30,
    'test_duration': 300,
    'acceptable_response_time': 2.0,
    'acceptable_error_rate': 0.05
}
```

### Benchmark Categories
- **API Response Times**: REST endpoint performance
- **Concurrent Load**: Multi-user simulation
- **Workflow Performance**: End-to-end task execution
- **Resource Utilization**: CPU, memory, disk usage
- **Database Performance**: Query optimization
- **WebSocket Performance**: Real-time communication

## 🔧 Error Testing

### Error Injection Scenarios
- Service timeouts and failures
- Database connection issues
- File system errors
- Resource exhaustion
- Network partitions
- Cascading failures

### Recovery Validation
- Automatic retry mechanisms
- Fallback service usage
- Graceful degradation
- Error propagation
- State consistency

## 🚀 Deployment Validation

### Deployment Readiness Checklist
- ✅ Environment configuration
- ✅ Database connectivity and schema
- ✅ Redis connectivity and operations
- ✅ API endpoint functionality
- ✅ External service connectivity
- ✅ File system permissions
- ✅ Security configuration
- ✅ Monitoring and logging

### Production Requirements
- **Success Rate**: ≥80% for deployment readiness
- **Critical Tests**: System integration, deployment validation must pass
- **Performance**: All benchmarks within acceptable thresholds
- **Security**: No critical vulnerabilities detected

## 📊 Reporting

### Automated Reports
The test suite generates multiple report formats:

#### JSON Reports
```json
{
  "test_execution_summary": {
    "total_execution_time": 1234.56,
    "total_suites": 7,
    "successful_suites": 6,
    "success_rate": 85.7
  },
  "deployment_readiness": {
    "ready": true,
    "readiness_score": 85.7
  }
}
```

#### HTML Reports
- Visual test results dashboard
- Interactive failure analysis
- Performance charts
- Deployment readiness status

### CI/CD Integration
- GitHub Actions workflow automation
- Pull request status checks
- Slack notifications
- Artifact storage and retention

## 🔍 Troubleshooting

### Common Issues

#### Database Connection Errors
```bash
# Check database service
pg_isready -h localhost -p 5432
# Verify credentials
PGPASSWORD=test psql -h localhost -U test -d test_db -c "SELECT 1;"
```

#### Redis Connection Errors
```bash
# Check Redis service
redis-cli ping
# Test connection
redis-cli -h localhost -p 6379 ping
```

#### Permission Issues
```bash
# Fix storage permissions
chmod -R 755 storage/
# Create missing directories
mkdir -p storage/{uploads,generated,temp}
```

#### Timeout Issues
```bash
# Increase timeout for slow tests
pytest --timeout=600 tests/test_performance_benchmarks.py
# Run without timeout
pytest --timeout=0 tests/
```

### Debug Mode
```bash
# Run with debug logging
pytest -v -s --log-cli-level=DEBUG tests/

# Run single test with full output
pytest -v -s tests/test_comprehensive_e2e_workflow.py::TestComprehensiveE2EWorkflow::test_full_user_journey_professional_video
```

## 📚 Best Practices

### Writing Integration Tests
1. **Isolation**: Each test should be independent
2. **Cleanup**: Always clean up test data and resources
3. **Mocking**: Mock external services appropriately
4. **Timeouts**: Set reasonable timeouts for async operations
5. **Assertions**: Use descriptive assertion messages

### Performance Testing
1. **Baselines**: Establish performance baselines
2. **Variance**: Account for system variance
3. **Load Patterns**: Use realistic load patterns
4. **Resource Monitoring**: Monitor system resources during tests
5. **Thresholds**: Set and maintain performance thresholds

### CI/CD Integration
1. **Fast Feedback**: Run critical tests first
2. **Parallel Execution**: Use parallel test execution when possible
3. **Artifact Management**: Store and manage test artifacts
4. **Notification**: Set up appropriate notifications
5. **Deployment Gates**: Use test results as deployment gates

## 🤝 Contributing

### Adding New Tests
1. Follow existing test patterns and structure
2. Add appropriate markers for test categorization
3. Include comprehensive documentation
4. Update this README with new test information
5. Ensure tests are deterministic and reliable

### Test Categories
- Use `@pytest.mark.integration` for integration tests
- Use `@pytest.mark.e2e` for end-to-end tests
- Use `@pytest.mark.performance` for performance tests
- Use `@pytest.mark.slow` for long-running tests

### Code Quality
- Follow PEP 8 style guidelines
- Include type hints where appropriate
- Write descriptive test names and docstrings
- Add logging for debugging purposes
- Handle exceptions appropriately

## 📖 Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/14/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)
- [Redis Testing](https://redis-py.readthedocs.io/en/stable/examples/redis_usage.html)
- [GitHub Actions](https://docs.github.com/en/actions)