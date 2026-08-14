#!/bin/bash
# Script de reinicio de Uvicorn para el auto-deploy
cd "$(dirname "$0")"

echo "Matando procesos anteriores de uvicorn..."
pkill -f "uvicorn scrapegraph_api" || true
sleep 1

echo "Arrancando Uvicorn en screen..."
screen -dmS uvicorn .venv/bin/python -m uvicorn scrapegraph_api.api:app --host 127.0.0.1 --port 8255

sleep 2
if pgrep -f "uvicorn scrapegraph_api" > /dev/null; then
  echo "Uvicorn arrancó correctamente."
else
  echo "ERROR: Uvicorn no arrancó."
  exit 1
fi
