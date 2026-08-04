# Testing Conventions

- **Framework**: `pytest`
- **Unit tests**: `tests/unit/` — 45 test files, 600+ tests (configured in `pyproject.toml` via `testpaths`)
- **E2E tests**: `tests/e2e/` (Playwright) — `comprehensive_test.py`, `test_dashboard.py`, `capture_console_errors.py`
- **Coverage**: minimum 50% (`fail_under = 50`), source = `src/trading_system`
- **pythonpath**: `src` (added by pytest config)
- **API key for tests**: `dev-secret-key-2026` (set in `.env`, used via `X-API-Key` header)
- **Conftest**: `tests/unit/conftest.py` — autouse fixture resets `_API_KEY` to `""` for deterministic unauthenticated tests

## Playwright E2E

- **Headed mode**: Use `--window-position=1339,0 --window-size=1280,800` for Epson PJ monitor
- **Selectors**: Use section IDs from `page.tsx`:
  - `page.locator("#section-instrument-status")`
  - `page.locator("#section-storage-sync")`
  - `page.locator(".stat-card[data-label='Total Tickers']")`
- **Wait strategy**: `page.wait_for_selector("h1")` or `page.wait_for_selector("#section-*")` with 30s timeout
- **Screenshot**: `page.screenshot(path=..., full_page=True)` after 5-6s data load wait

## Guidelines

- One test file per module, named `test_<module_name>.py`.
- Use `pytest fixtures` in `conftest.py` for shared setup (DB sessions, temp dirs).
- Do not weaken or delete existing tests without explicit direction.
- Add regression tests for bug fixes.
- Run tests: `python -m pytest tests/unit/ -v`
- Run with coverage: `python -m pytest tests/unit/ --cov=trading_system --cov-report=term-missing`
- Run E2E: `python -m pytest tests/e2e/ -v` or use Playwright directly via `.venv/bin/python`
