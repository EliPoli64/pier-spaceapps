# PIER Web UI

React + TypeScript frontend for PIER. It replaces the Streamlit screen with a
responsive dashboard, a click-to-pin Leaflet map, a five-slide tutorial and an
English/Spanish interface.

## Stack

- React 19 + TypeScript
- Vite 8
- Tailwind CSS 4
- Leaflet + React Leaflet
- Lucide icons

## Local development

Start the FastAPI service first:

```bash
# from the repository root
uvicorn piper_agent.api.main:app --reload --port 8000
```

Then run the web app:

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Vite proxies `/api/*` to `http://localhost:8000`, stripping the `/api` prefix.
That mirrors the production Nginx proxy, so the browser never needs the API host
or API key.

## Build

```bash
npm run build        # type-check + production bundle in dist/
npm run preview      # serve the production bundle locally
```

## Docker Compose

From the repository root:

```bash
docker compose up --build web
```

The app is served at http://localhost:3000. Nginx proxies `/api/*` to the
`api` service on the Compose network.

## Configuration

| Variable | Where | Purpose |
|---|---|---|
| `VITE_API_BASE` | Vite build-time | Override the API base. Defaults to `/api`. Only needed for a direct cross-origin API. |
| `VITE_API_KEY` | Vite build-time | Optional `X-API-Key` for a direct cross-origin API. **This is visible in the browser.** Prefer the Nginx proxy. |
| `PIER_API_URL` | Web container runtime | Upstream FastAPI origin used by Nginx. Example: `https://<api-service-domain>`. No trailing slash. |
| `PIER_API_KEY` | Web container runtime | Optional API key injected by Nginx into `X-API-Key`. Never shipped to the browser. |

The preferred production setup is the Nginx proxy: the browser calls the same
origin at `/api/*`, Nginx adds the key server-side, and no CORS is required.

## Deployment

Railway builds `Dockerfile.web` for the `web` service. See
[`docs/RAILWAY.md`](../docs/RAILWAY.md) for the service variables, domain and
workflow setup. The legacy Streamlit UI remains in `piper_agent/ui/` and can run
alongside the React app.
