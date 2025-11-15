# Silence Scooter Integration Tests

Comprehensive test suite for the Silence Scooter Home Assistant custom integration.

## Test Coverage

This test suite covers:

- **Config Flow** (`test_config_flow.py`) - Configuration and options flow
- **Integration Setup** (`test_init.py`) - Entry setup, unload, and services
- **Sensor Platform** (`test_sensor.py`) - All sensor types (writable, template, trigger, utility meter)
- **Number Platform** (`test_number.py`) - Number entities
- **Switch Platform** (`test_switch.py`) - Switch entities
- **DateTime Platform** (`test_datetime.py`) - DateTime entities
- **Helper Functions** (`test_helpers.py`) - Utility and helper functions

## Running Tests

### Install Test Dependencies

```bash
pip install -r tests/requirements_test.txt
```

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_config_flow.py
```

### Run With Coverage Report

```bash
pytest --cov=custom_components.silencescooter --cov-report=html
```

Coverage report will be available in `htmlcov/index.html`

### Run Specific Test

```bash
pytest tests/test_config_flow.py::test_form_valid_imei_15_digits
```

### Run Tests in Verbose Mode

```bash
pytest -v
```

### Run Tests and Show Print Statements

```bash
pytest -s
```

## Test Structure

### Fixtures (`conftest.py`)

Common fixtures used across tests:

- `mock_setup_entry` - Mocks integration setup
- `valid_imei` - Returns a valid 15-digit IMEI
- `valid_imei_short` - Returns a valid 14-digit IMEI
- `mock_mqtt` - Mocks MQTT integration
- `config_entry` - Creates a mock config entry
- `config_entry_multi_device` - Creates a mock config entry for multi-device mode
- `mock_history_file` - Mocks the history.json file
- `mock_automations` - Mocks automation setup

### Test Patterns

All tests follow Home Assistant testing best practices:

1. **Async Tests** - Using `async def test_*` for async operations
2. **Mocking** - External dependencies are mocked (MQTT, file I/O, subprocess)
3. **Isolation** - Each test is independent and doesn't affect others
4. **Coverage** - Both success and failure paths are tested

## Test Categories

### Unit Tests

Test individual components in isolation:
- Entity creation
- State updates
- Value validation
- Restore state functionality

### Integration Tests

Test component interactions:
- Platform setup
- Config entry lifecycle
- Service registration
- MQTT discovery

### Config Flow Tests

Test user configuration:
- IMEI validation (length, format, duplicates)
- Options flow
- Reauth flow for migration
- Parameter validation

## Coverage Goal

Target: **90%+ code coverage** as required by Home Assistant.

Check current coverage:
```bash
pytest --cov=custom_components.silencescooter --cov-report=term-missing
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines and follow Home Assistant's testing standards.

## Troubleshooting

### Import Errors

If you get import errors, ensure Home Assistant is installed:
```bash
pip install homeassistant
```

### Async Warnings

If you see async warnings, ensure `pytest-asyncio` is installed:
```bash
pip install pytest-asyncio
```

### Mock Issues

For mock-related issues, ensure `pytest-mock` is installed:
```bash
pip install pytest-mock
```

## Contributing

When adding new features:

1. Write tests first (TDD approach)
2. Ensure tests pass: `pytest`
3. Check coverage: `pytest --cov`
4. Maintain 90%+ coverage
5. Follow existing test patterns

## Test Data

Test fixtures use realistic data:
- IMEI: `869123456789012` (15 digits)
- IMEI Short: `86912345678901` (14 digits)

## Best Practices

1. **Test both single and multi-device modes**
2. **Mock external dependencies** (MQTT, files, subprocess)
3. **Test error handling** (invalid inputs, missing data)
4. **Test state restoration** (entity persistence)
5. **Use descriptive test names** that explain what is being tested
6. **Keep tests isolated** - no shared state between tests
