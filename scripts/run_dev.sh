#!/usr/bin/env bash
# Start backend (port 8000) and frontend dev server (port 5173) for local development.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
uvicorn app.main:app --reload --port 8000 &
API=$!
cd "$ROOT/frontend"
[ -d node_modules ] || npm install
npm run dev
kill $API
