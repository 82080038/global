# Add a Database Migration

Current migrations: `0001_initial.py`, `0002_d1_d31_tables.py`, `0003_ipo_suspension_delisting.py`

1. **Create migration file** in `alembic/versions/` with format `NNNN_descriptive_name.py`.
2. **Define `upgrade()` and `downgrade()` functions** using SQLAlchemy/Alembic operations.
   - **Important**: Use `sqlalchemy.text()` for raw SQL execution (SQLAlchemy 2.0 requirement).
3. **Update models** in `src/trading_system/data/` to match the new schema.
4. **Apply migration**:

```bash
.venv/bin/alembic upgrade head
```

5. **Rollback** (if needed):

```bash
.venv/bin/alembic downgrade -1
```

6. **Write tests** for any new tables or changed queries in `tests/unit/`.
7. **Run tests**:

```bash
.venv/bin/python -m pytest tests/unit/ -v
.venv/bin/ruff check src/trading_system/
```

8. **Update `.devin/rules/database.md`** with the new migration filename and table count.
