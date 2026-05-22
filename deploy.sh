#!/bin/bash
# deploy.sh - Actualiza RiskHub desde GitHub y reinicia el contenedor.
# Uso: bash /opt/riskhub/deploy.sh
set -e

REPO_DIR="/opt/riskhub"
cd "$REPO_DIR"

echo "==> Pulling latest changes..."
git pull origin main

echo "==> Rebuilding image..."
docker compose build --no-cache

echo "==> Restarting container..."
docker compose up -d

echo "==> Waiting for health check..."
sleep 5
curl -fsS http://localhost/api/health && echo "" && echo "==> Deploy OK"
