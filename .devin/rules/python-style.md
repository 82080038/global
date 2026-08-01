# Python Style & Linting

- **Formatter/linter**: `ruff` (config in `pyproject.toml`)
- **Line length**: 120
- **Target**: Python 3.11
- **Selected rules**: `E`, `F`, `W`, `I`, `UP`, `B`, `SIM`
- **Ignored rules**: `E501`, `B008`, `SIM108`, `B007`, `F841`, `SIM102`, `SIM103`, `SIM105`, `SIM110`, `SIM114`, `B019`, `E741`, `E731`, `B905`
- **isort**: first-party package is `trading_system`
- **Type checker**: `mypy` with `python_version = "3.11"`, `ignore_missing_imports = true`

## Guidelines

- Keep imports at the top of the file, sorted by isort conventions.
- Use `from __future__ import annotations` only if needed for forward refs.
- Prefer f-strings over `.format()` or `%` formatting.
- Use `pathlib.Path` over `os.path` for new code.
- Do not add type annotations to every function — follow existing file conventions.
- Do not add or remove comments unless explicitly asked.
