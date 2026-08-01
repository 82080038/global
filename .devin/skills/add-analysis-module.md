# Add a New Analysis Module

1. **Create the module file** in `src/trading_system/analysis/<module_name>.py`.
2. **Implement the analysis class/function** following the pattern of existing modules (e.g., `technical.py`, `fundamental.py`).
3. **Register in pipeline** — update `src/trading_system/analysis/pipeline.py` if the module should run as part of the standard pipeline.
4. **Add to decision engine** — if the module produces a score, update `src/trading_system/decision/engine.py` weights.
5. **Create database table** (if needed) — add an Alembic migration in `alembic/versions/`.
6. **Add CLI subcommand** (optional) — update `src/trading_system/cli.py` if the module needs a dedicated CLI command.
7. **Write unit tests** — create `tests/unit/test_<module_name>.py`.
8. **Run tests**:

```bash
python -m pytest tests/unit/test_<module_name>.py -v
ruff check src/trading_system/analysis/<module_name>.py
```
