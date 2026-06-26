FROM node:20-alpine AS frontend-builder

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
COPY frontend/packages/shared/package.json ./packages/shared/
COPY frontend/packages/public-app/package.json ./packages/public-app/
COPY frontend/packages/managed-app/package.json ./packages/managed-app/
RUN npm ci --ignore-scripts 2>/dev/null || npm install --ignore-scripts
COPY frontend/ ./
RUN npm run build --workspace=packages/public-app && \
    npm run build --workspace=packages/managed-app

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACP_HOST=0.0.0.0 \
    ACP_PORT=8000 \
    ACP_PUBLIC_WEB_ENABLED=false \
    ACP_LEGACY_DASHBOARD_ENABLED=false \
    ACP_PERSISTENCE_BACKEND=sqlite \
    ACP_SQLITE_PATH=/data/acp/acp.sqlite3 \
    ACP_MANAGED_AUTH_SQLITE_PATH=/data/acp/acp-managed-auth.sqlite3 \
    ACP_ASGI_APP=acp_managed.app:app

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY downloads ./downloads

RUN pip install --no-cache-dir .

COPY --from=frontend-builder /build/packages/public-app/dist ./static/public
COPY --from=frontend-builder /build/packages/managed-app/dist ./static/managed

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD python -c "import os,sys,urllib.request; port=os.getenv('ACP_PORT','8000'); url=f'http://127.0.0.1:{port}/health'; sys.exit(0 if urllib.request.urlopen(url,timeout=2).status==200 else 1)"

CMD ["sh", "-c", "uvicorn ${ACP_ASGI_APP:-acp_managed.app:app} --host ${ACP_HOST:-0.0.0.0} --port ${ACP_PORT:-8000}"]
