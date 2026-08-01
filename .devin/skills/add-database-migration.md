# Add a Database Migration

1. **Create migration file** in `alembic/versions/` with format `NNNN_descriptive_name.py`.
2. **Define `upgrade()` and `downgrade()` functions** using SQLAlchemy/Alembic operations.
3. **Update models** in `src/trading_system/data/` to match the new schema.
4. **Apply migration**:

```bash
alembic upgrade head
```

5. **Rollback** (if needed):

```bash
alembic downgrade -1
```

6. **Write tests** for any new tables or changed queries.
7. **Run tests**:

```bash
python -m pytest tests/unit/ -v
```
