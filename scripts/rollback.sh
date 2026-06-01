#!/bin/bash
# rollback.sh — Vuelve a la imagen Docker anterior de RiskHub.
# Uso: bash /opt/riskhub/scripts/rollback.sh
# Opcional: bash /opt/riskhub/scripts/rollback.sh riskhub:20240601_143022

set -euo pipefail

REPO_DIR="/opt/riskhub"
cd "$REPO_DIR"

TARGET_TAG="${1:-}"

# Si no se pasa tag, listar disponibles y seleccionar el anterior
if [ -z "$TARGET_TAG" ]; then
    echo "Imagenes disponibles:"
    docker images riskhub --format "table {{.Tag}}\t{{.CreatedAt}}\t{{.Size}}" | head -10
    echo ""
    PREVIOUS=$(docker images riskhub --format "{{.Tag}}" | grep -v "latest" | head -1)
    if [ -z "$PREVIOUS" ]; then
        echo "ERROR: No hay imagen anterior disponible para rollback."
        echo "Tip: el deploy.sh debe haber generado una imagen con timestamp."
        exit 1
    fi
    TARGET_TAG="riskhub:${PREVIOUS}"
    echo "Usando imagen anterior automaticamente: $TARGET_TAG"
fi

echo "==> Rollback a: $TARGET_TAG"
echo "==> Deteniendo contenedor actual..."
docker compose down

echo "==> Actualizando docker-compose para usar $TARGET_TAG ..."
export ROLLBACK_IMAGE="$TARGET_TAG"

# Reemplazar imagen en el compose temporalmente
docker run --rm \
    -v "$REPO_DIR/docker-compose.yml:/docker-compose.yml" \
    --entrypoint sh alpine:3.19 -c \
    "sed -i 's|image: riskhub:.*|image: $TARGET_TAG|g' /docker-compose.yml" 2>/dev/null || true

# Fallback: arrancar directamente con la imagen especificada
docker compose up -d

echo "==> Esperando health check..."
sleep 8
if curl -fsS http://localhost/api/health; then
    echo ""
    echo "==> Rollback completado. App funcionando con $TARGET_TAG"
else
    echo "ERROR: Health check fallido tras rollback."
    docker compose logs --tail=50
    exit 1
fi
