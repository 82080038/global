# Add a New Analysis Module

1. **Create the module file** in `src/trading_system/analysis/<module_name>.py`.
2. **Implement the analysis class/function** following the pattern of existing modules (e.g., `technical.py`, `fundamental.py`).
   - **Important**: Only process equity stocks (`asset_class = 'equity'`, `is_active = 1`). Non-equity instruments (forex, index, commodity, ETF) are reference data, not trading targets.
3. **Register in pipeline** — update `src/trading_system/analysis/pipeline.py` if the module should run as part of the standard pipeline.
4. **Add to decision engine** — if the module produces a score, update `src/trading_system/decision/engine.py` weights.
5. **Create database table** (if needed) — add an Alembic migration in `alembic/versions/`.
6. **Add API endpoint** (if needed) — add to `src/trading_system/api/app.py` following existing patterns.
7. **Add CLI subcommand** (optional) — update `src/trading_system/cli.py` if the module needs a dedicated CLI command.
8. **Write unit tests** — create `tests/unit/test_<module_name>.py`.
9. **Run tests**:

```bash
.venv/bin/python -m pytest tests/unit/test_<module_name>.py -v
.venv/bin/ruff check src/trading_system/analysis/<module_name>.py
```

10. **Update docs** — update `AGENTS.md` module map and `.devin/rules/` if conventions change.
