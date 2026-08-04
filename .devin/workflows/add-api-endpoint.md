# Workflow: Add API Endpoint + Frontend Section

## Purpose
Add a new API endpoint to the backend and a corresponding section in the Data Inspection Dashboard frontend.

## Steps

### 1. Add backend endpoint

Add the endpoint in `src/trading_system/api/app.py` following the existing pattern:

```python
@app.get("/api/your-endpoint")
def your_endpoint():
    """Description of what this endpoint returns."""
    with storage._connect() as conn:
        rows = conn.execute("""
            SELECT ... FROM ...
            WHERE ...
        """).fetchall()
    
    result = [
        {"field1": r[0], "field2": r[1]}
        for r in rows
    ]
    
    return {"data": result}
```

### 2. Restart backend

```bash
pkill -f "uvicorn trading_system"
ENV=development API_KEY=dev-secret-key-2026 .venv/bin/uvicorn trading_system.api.app:app --port 8000 --log-level warning &
```

### 3. Verify endpoint

```bash
curl -s -H "X-API-Key: dev-secret-key-2026" http://localhost:8000/api/your-endpoint | python3 -m json.tool
```

### 4. Add TypeScript interface in frontend

In `frontend/app/page.tsx`, add interface after existing ones:

```typescript
interface YourData {
  field1: string;
  field2: number;
}
```

### 5. Add state hook

```typescript
const [yourData, setYourData] = useState<YourData | null>(null);
```

### 6. Add fetch to `fetchAll`

```typescript
safeApiFetch<YourData>("/api/your-endpoint").then(setYourData).catch(...)
```

### 7. Add UI section with unique ID

```tsx
{yourData && (
  <div id="section-your-data" className="mb-4 rounded border border-zinc-800 bg-zinc-900/50 p-4">
    <h2 className="mb-3 text-sm font-bold text-zinc-300">Your Section Title</h2>
    {/* content */}
  </div>
)}
```

### 8. Verify frontend compiles

Check Next.js dev server output for `✓ Compiled` and `GET / 200`.

### 9. Visual verification

```bash
.venv/bin/python -c "
from playwright.sync_api import sync_playwright
import os, time
os.environ['DISPLAY'] = ':1'
with sync_playwright() as p:
    b = p.chromium.launch(headless=False, args=['--no-sandbox','--disable-gpu','--window-position=1339,0','--window-size=1280,800'])
    ctx = b.new_context(viewport={'width':1280,'height':800})
    page = ctx.new_page()
    page.goto('http://localhost:3000/', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_selector('#section-your-data', timeout=30000)
    time.sleep(5)
    page.screenshot(path='/tmp/your_section.png', full_page=True)
    b.close()
"
```

### 10. Update `.devin/rules/api-and-frontend.md`

Add the new endpoint and section ID to the rules file.
