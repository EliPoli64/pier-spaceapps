# PIER Docker image — mitigates imergpy/wget install risk (Spec §9)
FROM python:3.11-slim

WORKDIR /app

# wget required by imergpy (GES DISC OTF subset download service)
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Smoke test: verify core imports
RUN python -c "import streamlit, pandas, folium, numpy, requests, openpyxl; print('imports ok')"

# Default: run the CLI in demo (cache-only) mode
CMD ["python", "-m", "piper_agent", "--help"]
