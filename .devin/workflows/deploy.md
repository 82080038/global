# Workflow: Deploy to Production

## Purpose
Deploy the trading system to a production server (Docker or bare metal).

## Steps

### 1. Run full test suite

```bash
.venv/bin/python -m pytest tests/unit/ -v
.venv/bin/ruff check src/ tests/
cd frontend && npx tsc --noEmit && npm run lint && npm run build
```

### 2. Update version

```bash
# Update in config.py
# Update in README.md
# Update in CHANGELOG.md with release notes
```

### 3. Build Docker images

```bash
# Backend
docker build -t trading-system:latest .

# Frontend
docker build -t trading-frontend:latest frontend/
```

### 4. Docker Compose

```bash
# Production env
ENV=production API_KEY=<secure-key> docker-compose up -d
```

### 5. Verify production

```bash
# Health check
curl -s -H "X-API-Key: <key>" https://your-domain/api/health

# Frontend
curl -s https://your-domain/ | head -5
```

### 6. Git tag

```bash
git tag v0.X.Y
git push origin v0.X.Y
```

## Production checklist

- [ ] `ENV=production` set
- [ ] `API_KEY` is strong and non-empty (fail-fast if empty)
- [ ] `AUTO_TRADE_ENABLED=false` (manual enable after verification)
- [ ] CORS origins restricted to production domain
- [ ] Rate limiting enabled
- [ ] Database backed up
- [ ] Parquet archive synced
- [ ] All tests passing
- [ ] Frontend builds without errors
