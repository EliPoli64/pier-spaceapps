# Deploying PIER on Railway

Railway does not run `docker-compose.yml` as the production orchestrator. Instead,
each service in the compose file maps 1:1 to a Railway service. This repo keeps a
single definition of the stack in [`docker-compose.yml`](../docker-compose.yml)
and mirrors it on Railway.

## Local: one command

```bash
docker compose up
```

That builds both images and starts:

| Service | URL |
|---|---|
| `api` (FastAPI) | http://localhost:8000 |
| `ui` (Streamlit) | http://localhost:8501 |

## Railway mapping

| Compose | Railway |
|---|---|
| `services.api` | Railway service `api` |
| `services.ui` | Railway service `ui` |
| `build.dockerfile: Dockerfile.api` | API service builds from `Dockerfile.api` |
| `build.dockerfile: Dockerfile.ui` | UI service builds from `Dockerfile.ui` |
| `ports: 8000` / `8501` | Railway public domains |
| `volumes.pier-cache` / `pier-baselines` / `pier-db` | Railway Volumes mounted at the same paths |
| `environment` | Service Variables in the Railway dashboard |
| `healthcheck` | Railway healthcheck path (`/health` / `/_stcore/health`) |

## One-time setup

1. Create a Railway project and the `production` environment.
2. Import the stack from `docker-compose.yml`: drag the file onto the Railway
   project canvas. Railway stages the `api` and `ui` services (and their volumes).
3. Confirm the services build from `Dockerfile.api` and `Dockerfile.ui`
   (or set `RAILWAY_DOCKERFILE_PATH` as a service variable).
4. Generate a public domain for each service.
5. Set these variables on each service:

   **`api`**
   ```
   PIER_DEMO_MODE=1
   PIER_CORS_ORIGINS=*        # or the UI domain
   # PIER_API_KEY=...         # optional
   # PIER_API_DB=/data/pier.sqlite3
   ```

   **`ui`**
   ```
   PIER_DEMO_MODE=1
   ```

   Do not set `PORT`; Railway injects it.

6. Create a project token (project → Settings → Tokens → `production`) and add it
   to GitHub as `RAILWAY_TOKEN`.

After that, `.github/workflows/deploy-api.yml` and `deploy-ui.yml` deploy to the
`api` and `ui` services on every push to `master`.

## Notes

- `railway.api.toml` / `railway.ui.toml` are legacy Config-as-Code files. Railway
  deprecated Config-as-Code; new services cannot opt into it and it stops being
  read on 2026-12-01. Keep them only as a reference, or move their settings to the
  dashboard / Railway Infrastructure as Code.
- The compose volumes are for local persistence. On Railway, attach a volume per
  mount path if you want cache and plan history to survive redeploys.
- The UI does not call the API over HTTP; it imports `run_pier` directly, so the
  two services can run independently.
