# 🚀 Deploying IntelliNotes

Two services, one persistent volume, zero secrets in code:

| Piece | What it is | Where to host |
|---|---|---|
| **Backend** | FastAPI + LangGraph agent + ChromaDB + SQLite memory | Any host with **persistent disk** (Railway, Render, Fly.io, VPS) |
| **Frontend** | Streamlit UI (stateless) | Streamlit Community Cloud (free) or any host |

> ⚠️ **Hard constraint:** the vector store (ChromaDB) and conversation memory
> (SQLite) are file-backed and the app must run as a **single process**
> (`--workers 1`). Serverless platforms (Vercel, Lambda) and multi-worker
> setups will corrupt or lose state. The Docker image already enforces this.

---

## 1. Environment variables (backend)

| Variable | Required | Notes |
|---|---|---|
| `GOOGLE_API_KEY` | ✅ | Gemini + embeddings quota |
| `TAVILY_API_KEY` | ✅ | Web-search fallback |
| `API_KEY` | 🔒 recommended | Shared secret; when set, `/chat/`, `/upload-document/`, and `DELETE /documents*` require the `X-API-Key` header |
| `CORS_ORIGINS` | 🔒 recommended | Comma-separated frontend origins, e.g. `https://your-app.streamlit.app` |
| `DATA_DIR` | ⚠️ on hosts | Root of persistent state. Must point at a mounted volume, e.g. `/data` |
| `RATE_LIMIT_CHAT` / `RATE_LIMIT_UPLOAD` | optional | Per-minute limits, `0` disables (defaults 10/min and 5/min) |
| `CHAT_MODEL` | optional | Override `gemini-3.5-flash-lite` for a fresh free-tier quota bucket |
| `KEEP_ALIVE_ENABLED` / `KEEP_ALIVE_URL` | optional | Auto-pings public URL every 10 min to prevent free-tier host sleep (enabled by default) |

Set these in your host's dashboard (Railway/Render variables panel, Fly secrets, etc.).
Never commit `.env`.

## 2. Deploy the backend

### Option A — Docker (works on Railway, Render, Fly, any VPS)

```bash
# local sanity check first:
docker compose up --build          # backend :8000, frontend :8501
docker compose down                # data persists in the intellinotes-data volume
```

Then point your host at `Dockerfile.backend`:

- **Railway**: New Project → Deploy from repo → Root Directory `/` → it detects
  `Dockerfile.backend` (or set `RAILWAY_DOCKERFILE_PATH=Dockerfile.backend`).
  Add a **Volume** mounted at `/data` and set `DATA_DIR=/data`.
- **Render**: New → Web Service → Docker → Dockerfile path `Dockerfile.backend`.
  Add a **Disk** mounted at `/data` and set `DATA_DIR=/data`. Health check path: `/health`.
- **Fly.io**: `fly launch --dockerfile Dockerfile.backend` then
  `fly volumes create intellinotes_data --size 3` and
  `fly deploy` with `[mounts] source="intellinotes_data" destination="/data"`.

The image runs `uvicorn ... --workers 1` as an unprivileged user and exposes `/health`.

### Option B — Render/Railway native Python (no Docker)

- Build: `pip install -r backend/requirements.txt`
- Start: `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT --workers 1`
- Attach a disk/volume at `/data` and set `DATA_DIR=/data`.

## 3. Deploy the frontend (Streamlit Community Cloud — free)

1. Push the repo to GitHub (CI runs the test suite on every push).
2. share.streamlit.io → New app → pick the repo/branch.
3. Main file path: `frontend/app.py`.
4. Advanced settings → Secrets — paste:

```toml
API_BASE = "https://your-backend.up.railway.app"
INTELLINOTES_API_KEY = "the-same-value-as-API_KEY-on-the-backend"
```

`frontend/app.py` reads `API_BASE` / `INTELLINOTES_API_KEY` from environment
first, then from Streamlit secrets, so the same file works locally and in the cloud.

> The backend's `CORS_ORIGINS` must include your final `*.streamlit.app` URL.
> Deploy the backend first so you know the URL before filling in secrets.

## 4. Verify the deployment

```bash
# unauthenticated probe (always open):
curl https://your-backend.example.com/health

# auth + quota smoke test (needs a running server + real keys):
INTELLINOTES_API_KEY=... python scripts/smoke_test.py   # 18 live checks
```

And with auth enabled, an unauthenticated chat attempt must return **401**:

```bash
curl -X POST https://your-backend.example.com/chat/ \
  -H "Content-Type: application/json" -d '{"message":"hi"}'
```

## 5. Local development (unchanged defaults)

Nothing to configure: with no `API_KEY`, auth is off; with no `CORS_ORIGINS`,
localhost:8501 is allowed; rate limits apply only at 10/5 requests per minute.

```bash
uvicorn app.main:app --app-dir backend --reload --port 8000
streamlit run frontend/app.py
```

## Pre-flight checklist

- [ ] Repo pushed to GitHub (never includes `.env` or `data/`)
- [ ] Backend deployed with `GOOGLE_API_KEY`, `TAVILY_API_KEY`
- [ ] Persistent volume mounted and `DATA_DIR` points at it
- [ ] `API_KEY` set; unauthenticated `/chat/` returns 401
- [ ] `CORS_ORIGINS` lists exactly your frontend URL(s)
- [ ] Frontend secrets contain `API_BASE` + `INTELLINOTES_API_KEY`
- [ ] `/health` returns 200; `scripts/smoke_test.py` passes 18/18
- [ ] Rate limits sane (chat 10/min, upload 5/min or your values)
