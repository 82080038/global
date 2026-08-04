# Run Tests

## Unit tests

```bash
.venv/bin/python -m pytest tests/unit/ -v
```

## Unit tests with coverage

```bash
.venv/bin/python -m pytest tests/unit/ --cov=trading_system --cov-report=term-missing
```

## Single test file

```bash
.venv/bin/python -m pytest tests/unit/test_<module>.py -v
```

## Single test function

```bash
.venv/bin/python -m pytest tests/unit/test_<module>::test_<function> -v
```

## E2E tests (Playwright)

```bash
# Headless
.venv/bin/python -m pytest tests/e2e/ -v

# Headed (for visual verification)
.venv/bin/python -c "
from playwright.sync_api import sync_playwright
import os
os.environ['DISPLAY'] = ':1'
with sync_playwright() as p:
    b = p.chromium.launch(headless=False, args=['--no-sandbox','--disable-gpu','--window-position=1339,0','--window-size=1280,800'])
    ctx = b.new_context(viewport={'width':1280,'height':800})
    page = ctx.new_page()
    page.goto('http://localhost:3000/', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_selector('#section-instrument-status', timeout=30000)
    import time; time.sleep(5)
    page.screenshot(path='/tmp/data_inspection.png', full_page=True)
    b.close()
"
```

## Linting

```bash
.venv/bin/ruff check src/ tests/
.venv/bin/ruff check --fix src/ tests/
```

## Type checking

```bash
.venv/bin/mypy src/trading_system/
```

## Frontend type check

```bash
cd frontend && npx tsc --noEmit
```
