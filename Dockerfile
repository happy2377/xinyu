# ---------- 1) build frontend ----------
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------- 2) runtime: backend + frontend in one container ----------
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 \
    NEXT_TELEMETRY_DISABLED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg procps \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY --from=web /web/.next ./frontend/.next
COPY --from=web /web/public ./frontend/public
COPY --from=web /web/node_modules ./frontend/node_modules
COPY --from=web /web/package.json /web/package-lock.json /web/next.config.ts ./frontend/

COPY docker/start.sh /app/start.sh
RUN chmod +x /app/start.sh \
    && mkdir -p /data/backups \
    && chown -R 1000:1000 /data \
    && chmod -R a+rX /app/frontend

ENV DATABASE_URL=sqlite:////data/xinyu.db
VOLUME ["/data"]
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -fsS http://127.0.0.1:3000/health || exit 1

CMD ["/app/start.sh"]
