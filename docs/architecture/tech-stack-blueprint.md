# Technology Stack Blueprint

> Business-agnostic reference for replicating this application's architecture in a new project.

---

## 1. Architecture Overview

**Monorepo** with two top-level service directories and shared spec/doc folders:

```
project-root/
├── formcraft-backend/       # Python API server
├── formcraft-frontend/      # Angular SPA
├── e2e/                     # Playwright end-to-end tests
├── formcraft-specs/         # Feature specifications & plans
├── docs/                    # Documentation
├── docker-compose.yml       # Local multi-service orchestration
└── .github/workflows/       # CI/CD pipelines
```

**Communication pattern:** Frontend → Nginx reverse-proxy → Backend REST API → Supabase (DB + Auth + Storage).

---

## 2. Backend

| Concern | Technology | Version |
|---|---|---|
| **Language** | Python | 3.12 |
| **Web framework** | FastAPI | 0.115.6 |
| **ASGI server** | Uvicorn (standard extras) | 0.34.0 |
| **Data validation** | Pydantic v2 + pydantic-settings | 2.10.4 / 2.7.1 |
| **Rate limiting** | SlowAPI | 0.1.9 |
| **JWT auth** | python-jose[cryptography] | 3.3.0 |
| **HTTP client** | httpx (async) | 0.28.1 |
| **File uploads** | python-multipart | 0.0.20 |

### Backend project layout

```
formcraft-backend/
├── app/
│   ├── main.py            # Application factory (create_app)
│   ├── api/routes/         # FastAPI routers (one file per domain)
│   ├── core/               # Config, middleware, DB error helpers
│   ├── models/             # Domain models
│   ├── schemas/            # Pydantic request/response schemas
│   ├── services/           # Business logic layer
│   ├── middleware/          # Custom middleware
│   └── templates/          # Server-side templates (emails, etc.)
├── assets/                 # Static assets (fonts, images)
├── migrations/             # SQL migration files
├── requirements.txt        # Pinned dependencies
├── Dockerfile
└── .env                    # Environment variables (not committed)
```

### Configuration

- **Environment-driven** via `pydantic-settings` (`BaseSettings`), loaded from `.env` file.
- Key env vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_JWT_SECRET`, `CORS_ORIGINS`, AWS/Azure AI credentials.

---

## 3. Frontend

| Concern | Technology | Version |
|---|---|---|
| **Framework** | Angular | 19 |
| **Language** | TypeScript | ~5.6 |
| **UI component library** | Angular Material + Angular CDK | ^19.0.0 |
| **Styling** | SCSS (component-scoped) + Angular Material prebuilt theme (`indigo-pink`) |
| **State management** | RxJS | ~7.8 |
| **i18n** | @ngx-translate/core + http-loader | ^16.0.0 |
| **Schema validation** | Zod | ^3.23 |
| **Canvas / drawing** | Konva | ^9.3 |
| **Supabase client** | @supabase/supabase-js | ^2.105 |
| **Payments (client)** | @stripe/stripe-js | ^9.8 |
| **Icons** | material-icons | ^1.13 |
| **Build tooling** | @angular-devkit/build-angular (application builder) | ^19.0.0 |

### Frontend project layout

```
formcraft-frontend/
├── src/
│   ├── app/               # Angular modules, components, services
│   ├── assets/            # Static files (i18n JSONs, images)
│   ├── environments/      # environment.ts / environment.prod.ts
│   ├── styles.scss        # Global styles
│   └── main.ts            # Bootstrap entry
├── angular.json           # Angular workspace config
├── proxy.conf.json        # Dev-server API proxy config
├── package.json
├── nginx.conf.template    # Production Nginx config (template-based)
└── Dockerfile             # Multi-stage: Node build → Nginx serve
```

### Key configuration

- **Component style:** SCSS, non-inline, non-standalone (NgModule-based).
- **Component prefix:** `fc`.
- **Bundle budgets:** 2 MB warning / 3 MB error (initial).
- **Dev proxy:** `proxy.conf.json` forwards `/api/` to the backend.

---

## 4. Database & BaaS — Supabase

| Concern | Detail |
|---|---|
| **Database** | PostgreSQL 17 (managed by Supabase) |
| **Auth** | Supabase Auth (JWT, email/password, OAuth providers, MFA-ready) |
| **Storage** | Supabase Storage (S3-compatible, configurable buckets with MIME filters & size limits) |
| **Realtime** | Supabase Realtime (enabled, WebSocket-based) |
| **Edge Functions** | Supabase Edge Runtime (Deno 2) |
| **Row Level Security** | RLS policies per table for tenant/org isolation |
| **Connection pooler** | PgBouncer in transaction mode (configurable) |
| **SDK (backend)** | `supabase` Python SDK 2.11.0 |
| **SDK (frontend)** | `@supabase/supabase-js` ^2.105.4 |

### Migrations

- Versioned SQL files in `formcraft-backend/migrations/` (application-managed).
- Supabase CLI migrations in `formcraft-backend/supabase/migrations/` (for local dev).

---

## 5. Containerization

### Backend Dockerfile

- **Base:** `python:3.12-slim`
- Installs system deps: Pango, Cairo, HarfBuzz, Arabic/Noto fonts (for PDF rendering).
- `pip install` from pinned `requirements.txt`.
- Runs `uvicorn` on port **8000**, 1 worker.
- Built-in healthcheck via `curl http://localhost:8000/api/health`.

### Frontend Dockerfile (multi-stage)

- **Stage 1 (build):** `node:20-alpine` → `npm ci` → `ng build --configuration=${BUILD_ENV}`
- **Stage 2 (serve):** `nginx:alpine` → copies built SPA to `/usr/share/nginx/html`
- Uses `nginx.conf.template` with envsubst for runtime `BACKEND_HOST` injection.
- Exposes port **80**.
- Healthcheck via `wget` on `/index.html`.

### Docker Compose

```yaml
services:
  backend:
    build: ./formcraft-backend
    env_file: ./formcraft-backend/.env
    expose: ["8000"]
    healthcheck: curl http://localhost:8000/api/health
    restart: unless-stopped

  frontend:
    build: ./formcraft-frontend
    ports: ["80:80"]
    depends_on: [backend]
    restart: unless-stopped
```

- Frontend proxies `/api/` requests to `backend:8000` via Nginx.

---

## 6. CI/CD

| Concern | Detail |
|---|---|
| **Platform** | GitHub Actions |
| **Triggers** | Push to `main` on changed paths + manual `workflow_dispatch` |
| **Container registry** | GitHub Container Registry (`ghcr.io`) |
| **Build** | Docker Buildx with GHA cache (`cache-from: type=gha`) |
| **Image tagging** | Commit SHA + `latest` on default branch |
| **Deployment target** | **Bunny Magic Containers** (via `BunnyWay/actions/container-update-image`) |
| **Pipelines** | Separate workflows for backend and frontend (path-filtered) |

### Bunny Magic Containers — Deployment Model

Bunny groups multiple containers under a single **app**. Containers within the same app share a network namespace (they communicate via `localhost`, similar to a Kubernetes Pod).

| Container | Image source | Public port | Custom hostname |
|---|---|---|---|
| `<project>-backend` | `ghcr.io/<owner>/<project>-backend:latest` | 8000 | `<project>-api.<domain>` |
| `<project>-frontend` | `ghcr.io/<owner>/<project>-frontend:latest` | 80 | `<project>.<domain>` |

- Because containers share a network namespace, the frontend Nginx config uses `BACKEND_HOST=localhost` in production (not a Docker service name).
- Each CI workflow deploys to the **same Bunny app** (`BUNNY_API_KEY` + app-specific `BUNNY_BACKEND_APP_ID` / `BUNNY_FRONTEND_APP_ID`).

### CI Workflow Pattern (per service)

Each service follows an identical workflow structure:

```yaml
name: Deploy <Service>
on:
  push:
    branches: [main]
    paths:
      - '<project>-<service>/**'
      - '.github/workflows/deploy-<service>.yml'
  workflow_dispatch:

env:
  REGISTRY: ghcr.io

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Normalize image name casing
        id: normalize_image
        run: echo "image_name=${GITHUB_REPOSITORY_OWNER,,}/<project>-<service>" >> "$GITHUB_OUTPUT"

      - uses: docker/metadata-action@v5
        id: meta
        env:
          IMAGE_NAME: ${{ steps.normalize_image.outputs.image_name }}
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=
            type=raw,value=latest,enable={{is_default_branch}}

      - uses: docker/setup-buildx-action@v3

      - uses: docker/build-push-action@v5
        env:
          IMAGE_NAME: ${{ steps.normalize_image.outputs.image_name }}
        with:
          context: ./<project>-<service>
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          platforms: linux/amd64
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - uses: BunnyWay/actions/container-update-image@main
        env:
          IMAGE_NAME: ${{ steps.normalize_image.outputs.image_name }}
        with:
          api_key: ${{ secrets.BUNNY_API_KEY }}
          app_id: ${{ secrets.BUNNY_<SERVICE>_APP_ID }}
          container: <project>-<service>
          image_tag: latest
```

**Required GitHub Actions secrets:**
- `BUNNY_API_KEY` — Bunny.net API key
- `BUNNY_BACKEND_APP_ID` — Bunny app container ID for the backend
- `BUNNY_FRONTEND_APP_ID` — Bunny app container ID for the frontend

---

## 7. Reverse Proxy — Nginx

- Serves SPA with `try_files $uri $uri/ /index.html` fallback.
- Proxies `/api/` to backend with forwarded headers (`X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`).
- **Timeouts:** 120s read/send, 10s connect.
- **Security headers:** `X-Content-Type-Options`, `X-Frame-Options DENY`, `HSTS`, `CSP`, `Referrer-Policy`.
- **Caching:** `no-store` for `index.html`; `must-revalidate` for CSS; gzip enabled.

---

## 8. Testing

| Layer | Tool | Version |
|---|---|---|
| **Backend unit/integration** | pytest + pytest-asyncio | 8.3.4 / 0.25.2 |
| **Backend HTTP testing** | httpx (TestClient) | 0.28.1 |
| **AWS mocking** | moto[bedrock] | 5.0.27 |
| **Frontend unit** | Karma + Jasmine | 6.4 / 5.4 |
| **E2E** | Playwright | ^1.60 |
| **Linting** | ruff (Python), Angular CLI lint (TS) | — |

---

## 9. AI / Document Intelligence

| Service | SDK | Purpose |
|---|---|---|
| **AWS Bedrock** | boto3 1.36.4 | LLM inference (Claude 3 Haiku) |
| **Azure Document Intelligence** | azure-ai-formrecognizer 3.3.0 | OCR / form field extraction |

---

## 10. PDF & Reporting

| Library | Version | Purpose |
|---|---|---|
| **WeasyPrint** | 63.1 | HTML/CSS → PDF rendering (supports Arabic via Pango/HarfBuzz) |
| **openpyxl** | 3.1.5 | Excel workbook export |
| **matplotlib** | 3.10.0 | Server-side chart generation for reports |
| **ng2-charts / Chart.js** | (frontend) | Client-side charting |
| **qrcode[pil]** | 8.0 | QR code generation |
| **python-barcode** | 0.15.1 | Barcode generation |
| **Pillow** | 11.1.0 | Image processing |
| **arabic-reshaper + python-bidi** | 3.0.0 / 0.6.7 | Arabic text shaping for PDF |

---

## 11. Scheduling

| Library | Version | Purpose |
|---|---|---|
| **APScheduler** | 3.11.0 | Background job scheduling (reports, batch processing) |

---

## 12. Security

- **Auth:** Supabase JWT-based auth with RLS enforcement at database level.
- **Rate limiting:** SlowAPI (per-endpoint configurable).
- **CORS:** Configurable origin allowlist via env var.
- **Security headers middleware:** Custom FastAPI middleware for response headers.
- **Nginx hardening:** CSP, HSTS, X-Frame-Options, X-Content-Type-Options.
- **Env management:** Secrets in `.env` (not committed); CI secrets via GitHub Actions secrets.

---

## 13. How to Bootstrap a New Project Using This Stack

> Replace `<project>` with your project name (e.g., `invoicehub`) throughout.

---

### Step 1 — Create the Monorepo

```
<project>/
├── <project>-backend/
├── <project>-frontend/
├── e2e/
├── docs/
├── docker-compose.yml
└── .github/workflows/
```

Initialize a Git repo at the root. Add a `.gitignore` covering Python (`__pycache__`, `.env`, `*.pyc`), Node (`node_modules/`, `dist/`), and IDE files.

---

### Step 2 — Backend Setup

#### 2a. Initialize the Python project

```bash
mkdir -p <project>-backend/app/{api/routes,core,models,schemas,services,middleware,templates}
mkdir -p <project>-backend/{assets,migrations}
cd <project>-backend
python -m venv venv && source venv/bin/activate
```

#### 2b. Install core dependencies

Create `requirements.txt` with pinned versions:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.7.1
slowapi==0.1.9
python-jose[cryptography]==3.3.0
httpx==0.28.1
python-multipart==0.0.20
supabase==2.11.0
```

Add optional dependencies as needed (WeasyPrint, boto3, openpyxl, APScheduler, etc.).

#### 2c. Application factory pattern

Create `app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

def create_app() -> FastAPI:
    app = FastAPI(title="<Project>", root_path="/api")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    # app.include_router(...)

    return app

app = create_app()
```

#### 2d. Configuration via pydantic-settings

Create `app/core/config.py`:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_KEY: str
    SUPABASE_JWT_SECRET: str
    CORS_ORIGINS: list[str] = ["http://localhost:4200"]

    class Config:
        env_file = ".env"
```

#### 2e. Create `.env` (never commit)

```
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_KEY=...
SUPABASE_JWT_SECRET=...
CORS_ORIGINS=["http://localhost:4200","http://localhost"]
```

#### 2f. Health check endpoint

Create `app/api/routes/health.py`:

```python
from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok"}
```

#### 2g. Backend Dockerfile

```dockerfile
FROM python:3.12-slim

# Add system deps only if needed (e.g., PDF rendering):
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libpango-1.0-0 libpangocairo-1.0-0 libcairo2 fonts-noto-core curl \
#     && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY assets/ assets/
COPY app/ app/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

---

### Step 3 — Frontend Setup

#### 3a. Scaffold Angular project

```bash
ng new <project>-frontend --prefix=<prefix> --style=scss --standalone=false --skip-git
cd <project>-frontend
```

#### 3b. Install dependencies

```bash
ng add @angular/material
npm install @ngx-translate/core @ngx-translate/http-loader @supabase/supabase-js zod
```

Add optional packages as needed (`konva`, `@stripe/stripe-js`, `ng2-charts`, etc.).

#### 3c. Dev proxy configuration

Create `proxy.conf.json`:

```json
{
  "/api": {
    "target": "http://localhost:8000",
    "secure": false,
    "changeOrigin": true,
    "logLevel": "info"
  }
}
```

Add to `angular.json` under `serve > options`:

```json
"proxyConfig": "proxy.conf.json"
```

#### 3d. Environment files

`src/environments/environment.ts`:

```typescript
export const environment = {
  production: false,
  supabaseUrl: 'https://<ref>.supabase.co',
  supabaseAnonKey: '...',
  apiUrl: '/api'
};
```

Create a matching `environment.prod.ts` with `production: true`.

#### 3e. Nginx config template

Create `nginx.conf.template`:

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # CSS — cache with revalidation
    location ~* \.css$ {
        expires 0;
        add_header Cache-Control "max-age=0, must-revalidate";
        add_header X-Content-Type-Options nosniff always;
        try_files $uri =404;
    }

    # index.html — never cache
    location = /index.html {
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header Pragma "no-cache" always;
        add_header X-Content-Type-Options nosniff always;
        add_header X-Frame-Options DENY always;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        try_files $uri =404;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy — ${BACKEND_HOST} is replaced at runtime by envsubst
    location /api/ {
        proxy_pass http://${BACKEND_HOST}:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
        proxy_connect_timeout 10s;
    }

    # Security headers
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/font-woff2;
}
```

#### 3f. Frontend Dockerfile (multi-stage)

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG BUILD_ENV=production
RUN npm run build -- --configuration=${BUILD_ENV}

FROM nginx:alpine
COPY --from=build /app/dist/<project>-frontend/browser /usr/share/nginx/html
# Default to "backend" for docker-compose; override to "localhost" for Bunny shared-network
ENV BACKEND_HOST=backend
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/index.html || exit 1
```

> **Important:** The `COPY --from=build` path must match Angular's `outputPath` in `angular.json`. Check `dist/<project>-frontend/browser` vs `dist/<project>-frontend`.

---

### Step 4 — Database (Supabase)

1. **Create a Supabase project** at [supabase.com](https://supabase.com).
2. **Collect credentials:** Project URL, anon key, service role key, JWT secret → put in backend `.env`.
3. **Enable RLS** on every table for tenant/org isolation.
4. **Migrations:** Store versioned SQL files in `<project>-backend/migrations/`. Apply them via the Supabase dashboard, CLI, or a startup migration runner.
5. **Storage buckets:** Configure via dashboard with appropriate MIME filters and size limits.
6. **Auth:** Configure email/password, OAuth providers, and MFA as needed.

---

### Step 5 — Docker Compose (Local Development)

Create `docker-compose.yml` at the repo root:

```yaml
services:
  backend:
    build:
      context: ./<project>-backend
    env_file:
      - ./<project>-backend/.env
    expose:
      - "8000"
    healthcheck:
      test: ["CMD", "sh", "-c", "curl -fsS http://localhost:8000/api/health >/dev/null"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped

  frontend:
    build:
      context: ./<project>-frontend
      args:
        - BUILD_ENV=${FRONTEND_BUILD_ENV:-development}
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped
```

Run locally:

```bash
docker compose up --build
# Frontend: http://localhost
# API proxied through Nginx: http://localhost/api/
```

- In Docker Compose, `BACKEND_HOST` defaults to `backend` (the service name).
- Nginx resolves `/api/` → `http://backend:8000`.

---

### Step 6 — CI/CD (GitHub Actions)

#### 6a. Create two workflow files

- `.github/workflows/deploy-backend.yml`
- `.github/workflows/deploy-frontend.yml`

Use the CI Workflow Pattern template from Section 6 above, replacing `<project>` and `<service>`.

#### 6b. Configure GitHub repo secrets

| Secret | Value |
|---|---|
| `BUNNY_API_KEY` | Bunny.net API key |
| `BUNNY_BACKEND_APP_ID` | Container ID for the backend container in Bunny |
| `BUNNY_FRONTEND_APP_ID` | Container ID for the frontend container in Bunny |

#### 6c. Configure GHCR access

- Workflows use `GITHUB_TOKEN` (automatic) with `packages: write` permission.
- Ensure the repo's package visibility settings allow the Bunny pull.

---

### Step 7 — Bunny Magic Containers Deployment

1. **Create an app** in Bunny Dashboard → Edge Platform → Magic Containers.
2. **Add two containers** within the app:
   - `<project>-backend` — image from `ghcr.io/<owner>/<project>-backend`, public port `8000`.
   - `<project>-frontend` — image from `ghcr.io/<owner>/<project>-frontend`, public port `80`.
3. **Set `BACKEND_HOST=localhost`** as an environment variable on the frontend container (containers share a network namespace and communicate via localhost).
4. **Configure endpoints:**
   - Backend endpoint: custom hostname `<project>-api.<domain>` → port 8000.
   - Frontend endpoint: custom hostname `<project>.<domain>` → port 80.
5. **Add a GHCR Image Registry** in Bunny (Image Registries tab) with a GitHub PAT that has `read:packages` scope.
6. **Set regions** and scaling as needed.

---

### Step 8 — Testing Setup

#### 8a. Backend tests

```bash
cd <project>-backend
pip install pytest pytest-asyncio httpx
mkdir tests
```

Use `httpx.AsyncClient` with FastAPI's `TestClient` pattern.

#### 8b. Frontend tests

Angular CLI comes with Karma + Jasmine pre-configured. Run:

```bash
ng test
```

#### 8c. E2E tests (Playwright)

```bash
mkdir e2e && cd e2e
npm init -y
npm install -D @playwright/test
npx playwright install
```

Configure `playwright.config.ts` with `baseURL: 'http://localhost'`.

---

### Step 9 — Checklist Before First Deploy

- [ ] Backend `.env` has all Supabase credentials
- [ ] Backend health endpoint responds at `/api/health`
- [ ] Frontend builds successfully with `ng build --configuration=production`
- [ ] `docker compose up --build` runs both services and `/api/health` is reachable via `http://localhost/api/health`
- [ ] Nginx proxies `/api/` requests correctly to backend
- [ ] GHCR images build and push from GitHub Actions
- [ ] Bunny app created with both containers, endpoints configured
- [ ] `BACKEND_HOST=localhost` set on frontend container in Bunny
- [ ] DNS records point custom hostnames to Bunny endpoints
- [ ] RLS enabled on all Supabase tables
