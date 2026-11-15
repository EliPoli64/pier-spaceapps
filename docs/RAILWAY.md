# Deploying PIER on Railway

Railway does not run `docker-compose.yml` as the production orchestrator. Instead,
each service in the compose file maps 1:1 to a Railway service. This repo keeps a
single definition of the stack in [`docker-compose.yml`](../docker-compose.yml)
and mirrors it on Railway.

## Local: one command

```bash
docker compose up
```

That builds the images and starts:

| Service | URL | Notes |
|---|---|---|
| `api` (FastAPI) | http://localhost:8000 | NASA data, plan generation, SQLite store |
| `web` (React + Vite) | http://localhost:3000 | New frontend; Nginx proxies `/api/` to `api` |
| `ui` (Streamlit) | http://localhost:8501 | Legacy frontend, kept for comparison |

The React app can also run outside Docker for fast iteration:

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to localhost:8000
```

## Railway mapping

| Compose | Railway |
|---|---|
| `services.api` | Railway service `api` |
| `services.web` | Railway service `web` (or `pier-web`) |
| `services.ui` | Railway service `ui` (legacy Streamlit) |
| `build.dockerfile: Dockerfile.api` | API service builds from `Dockerfile.api` |
| `build.dockerfile: Dockerfile.web` | Web service builds from `Dockerfile.web` |
| `build.dockerfile: Dockerfile.ui` | UI service builds from `Dockerfile.ui` |
| `ports: 8000` / `80` / `8501` | Railway public domains |
| `volumes.pier-cache` / `pier-baselines` / `pier-db` | Railway Volumes mounted at the same paths |
| `environment` | Service Variables in the Railway dashboard |
| `healthcheck` | Railway healthcheck path (`/health`, `/`, `/_stcore/health`) |

The web service never exposes the API key to the browser. Nginx receives
`PIER_API_URL` and `PIER_API_KEY` as container environment variables and injects
the key into the upstream request. The browser calls the same origin at `/api/*`,
so no CORS configuration is needed for the React UI.

## One-time setup

1. Create a Railway project and the `production` environment.
2. Import the stack from `docker-compose.yml`: drag the file onto the Railway
   project canvas. Railway stages the `api`, `web` and `ui` services (and their
   volumes).
3. Confirm the services build from `Dockerfile.api`, `Dockerfile.web` and
   `Dockerfile.ui` (or set `RAILWAY_DOCKERFILE_PATH` as a service variable).
4. Generate a public domain for each service.
5. Set these variables on each service:

   **`api`**
   ```
   PIER_DEMO_MODE=1
   PIER_CORS_ORIGINS=*        # or the web/UI domain
   # PIER_API_KEY=...         # optional
   # PIER_API_DB=/data/pier.sqlite3
   ```

   **`web`**
   ```
   PIER_API_URL=https://<api-service-domain>   # no trailing slash
   PIER_API_KEY=<same value as api, or omit>
   ```

   **`ui`**
   ```
   PIER_DEMO_MODE=1
   ```

   Do not set `PORT`; Railway injects it.

6. Create a project token (project → Settings → Tokens → `production`) and add it
   to GitHub as `RAILWAY_TOKEN`.

7. Match the workflow service names to your Railway services. The workflows
   default to `pier-api`, `pier-web` and `pier-ui`. If you imported the compose
   stack and Railway named the services `api`, `web` and `ui`, add these
   repository variables under Settings → Secrets and variables → Actions →
   Variables:

   ```
   RAILWAY_SERVICE_API=api
   RAILWAY_SERVICE_WEB=web
   RAILWAY_SERVICE_UI=ui
   ```

After that, `.github/workflows/deploy-api.yml`, `deploy-web.yml` and
`deploy-ui.yml` deploy to the `api`, `web` and `ui` services on every push to
`master`.

## Notes

- `railway.api.toml` / `railway.web.toml` / `railway.ui.toml` are legacy
  Config-as-Code files. Railway deprecated Config-as-Code; new services cannot
  opt into it and it stops being read on 2026-12-01. The deploy workflows copy the
  matching file to `railway.toml` and copy the service Dockerfile to `Dockerfile`
  as a fallback. Keep the files only as a reference, or move their settings to the
  dashboard / Railway Infrastructure as Code.
- The compose volumes are for local persistence. On Railway, attach a volume per
  mount path if you want cache and plan history to survive redeploys.
- The React UI calls the API over HTTP through Nginx (`/api/*`). The legacy
  Streamlit UI still imports `run_pier` directly, so it does not need the API
  service to be reachable over the network.
- The API store is SQLite at `~/.pier/pier_api.sqlite3`. It is ephemeral unless a
  Railway volume is mounted there.
