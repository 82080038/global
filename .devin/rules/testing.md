# Testing Conventions

- **Framework**: `pytest`
- **Unit tests**: `tests/unit/` (configured in `pyproject.toml` via `testpaths`)
- **E2E tests**: `tests/e2e/` (Playwright)
- **Coverage**: minimum 50% (`fail_under = 50`), source = `src/trading_system`
- **pythonpath**: `src` (added by pytest config)

## Guidelines

- One test file per module, named `test_<module_name>.py`.
- Use `pytest fixtures` in `conftest.py` for shared setup (DB sessions, temp dirs).
- Do not weaken or delete existing tests without explicit direction.
- Add regression tests for bug fixes.
- Run tests: `python -m pytest tests/unit/ -v`
- Run with coverage: `python -m pytest tests/unit/ --cov=trading_system --cov-report=term-missing`
