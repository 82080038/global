# Run Tests

## Unit tests

```bash
python -m pytest tests/unit/ -v
```

## Unit tests with coverage

```bash
python -m pytest tests/unit/ --cov=trading_system --cov-report=term-missing
```

## Single test file

```bash
python -m pytest tests/unit/test_<module>.py -v
```

## Single test function

```bash
python -m pytest tests/unit/test_<module>::test_<function> -v
```

## E2E tests (Playwright)

```bash
python -m pytest tests/e2e/ -v
```

## Linting

```bash
ruff check src/ tests/
ruff check --fix src/ tests/
```

## Type checking

```bash
mypy src/trading_system/
```
