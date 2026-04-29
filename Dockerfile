# --- stage 1: build the React SPA -------------------------------------------
FROM node:20-alpine AS web-build

WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY web/ ./
RUN npm run build


# --- stage 2: python runtime ------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY src/ ./src/
COPY --from=web-build /web/dist /app/web/dist

RUN useradd --create-home --uid 1000 app \
 && mkdir -p /app/data \
 && chown -R app:app /app
USER app

ENV DATA_DIR=/app/data \
    WEB_DIST=/app/web/dist \
    DASHBOARD_HOST=0.0.0.0 \
    DASHBOARD_PORT=8000
VOLUME ["/app/data"]
EXPOSE 8000

CMD ["python", "-m", "src.main"]
