# PIER Docker image
# ===================
# Default image is demo-safe: PIER_DEMO_MODE=1, no Earthdata credentials,
# no live network calls to NASA / partner services unless explicitly enabled.
#
# Quick demo (no credentials needed):
#   docker run --rm -p 8000:8000 pier-spaceapps
uvicorn piper_agent.api.main:app --host 0.0.0.0 --port 8000
#
# Production path (live NASA Earthdata / partner data):
#   docker run --rm -p 8000:8000 \
#     -e PIER_DEMO_MODE=0 \
#     -e EARTHDATA_USERNAME=your_username \
#     -e EARTHDATA_PASSWORD=your_password \
#     -e PIER_OPENET_API_KEY=... \
#     -e PIER_SMAP_API_KEY=... \
#     pier-spaceapps
#
# IMPORTANT:
#   - Real credentials are never committed and are mounted at runtime.
#   - The default container does NOT include Earthdata credentials.
#   - PIER_DEMO_MODE=0 requires Earthdata credentials for the live IMERG path.
#   - The demo path (PIER_DEMO_MODE=1) is the default and requires no credentials.
FROM python:3.11-slim

WORKDIR /app

# wget is required by imergpy (GES DISC OTF subset download service).
# curl is used by the Dockerfile healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Smoke test: verify core imports
RUN python -c "import streamlit, pandas, folium, numpy, requests, openpyxl; print('imports ok')"

# Default: demo (cache-only) mode. No live NASA / partner calls.
ENV PIER_DEMO_MODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://127.0.0.1:8000/health?demo_mode=true || exit 1

# Default process: FastAPI server, demo mode by default.
CMD ["uvicorn", "piper_agent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Production-path notes (for operators, not for the Dockerfile itself):
#   - Set PIER_DEMO_MODE=0 at runtime to enable the live NASA path.
#   - The live path requires EARTHDATA_USERNAME and EARTHDATA_PASSWORD for IMERG.
#   - OpenET, SMAP, and SoilGrids are optional and degrade gracefully.
#   - The healthcheck targets demo_mode=true by default; production health reads
#     demo_mode_status from /health (no credentials are revealed).
#   - For a production run with live APIs, mount a .env with credentials at runtime;
#     do NOT bake real credentials into the image.
