#!/bin/sh
set -eu

echo "[xinyu] starting backend ..."
cd /app/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACK_PID=$!

echo "[xinyu] starting frontend ..."
cd /app/frontend
# Hugging Face Spaces 通过 app_port=3000 访问，不跟随平台注入的 PORT
PORT="${APP_PORT:-3000}" npm run start -- -H 0.0.0.0 -p "${PORT}" &
FRONT_PID=$!

cleanup() {
  kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true
}
trap cleanup INT TERM

while kill -0 "$BACK_PID" 2>/dev/null && kill -0 "$FRONT_PID" 2>/dev/null; do
  sleep 2
done

echo "[xinyu] a process exited, shutting down container"
cleanup
exit 1
