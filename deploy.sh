#!/bin/bash
# deploy.sh — Actualiza RiskHub desde GitHub y reinicia el contenedor.
# Uso: bash /opt/riskhub/deploy.sh
# Rollback: bash /opt/riskhub/scripts/rollback.sh [tag]

set -euo pipefail

REPO_DIR="/opt/riskhub"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
VERSIONED_TAG="riskhub:${TIMESTAMP}"

cd "$REPO_DIR"

echo "[$(date -Iseconds)] ==> Iniciando deploy (tag: $VERSIONED_TAG)..."

echo "[$(date -Iseconds)] ==> Pulling latest changes..."
git pull origin main

echo "[$(date -Iseconds)] ==> Construyendo imagen $VERSIONED_TAG..."
docker build -t "$VERSIONED_TAG" -t riskhub:latest .

# Configurar cron de backup diario (idempotente, no falla si ya esta instalado)
bash "$REPO_DIR/scripts/setup_cron.sh" 2>/dev/null || true

# Backup de BD antes de desplegar (no falla el deploy si falla el backup)
echo "[$(date -Iseconds)] ==> Backup pre-deploy..."
bash "$REPO_DIR/scripts/backup.sh" || echo "AVISO: Backup pre-deploy fallo (no critico)"

# Generar certificado TLS si no existe (primer deploy o cert eliminado)
echo "[$(date -Iseconds)] ==> Verificando certificado TLS..."
bash "$REPO_DIR/nginx/generate-certs.sh"

echo "[$(date -Iseconds)] ==> Reiniciando contenedores..."
docker compose up -d

echo "[$(date -Iseconds)] ==> Esperando health check..."
MAX_RETRIES=12
for i in $(seq 1 $MAX_RETRIES); do
    sleep 5
    if curl -fsSk https://localhost/api/health > /dev/null 2>&1; then
        echo ""
        echo "[$(date -Iseconds)] ==> Deploy OK — version activa: $VERSIONED_TAG"
        echo "[$(date -Iseconds)] Para rollback ejecuta: bash $REPO_DIR/scripts/rollback.sh $VERSIONED_TAG"
        # Limpiar imagenes antiguas (mantener las ultimas 5)
        docker images riskhub --format "{{.Tag}}" | grep -v "latest" | tail -n +6 | \
            xargs -I{} docker rmi "riskhub:{}" 2>/dev/null || true
        exit 0
    fi
    echo "[$(date -Iseconds)] Intento $i/$MAX_RETRIES — esperando que la app arranque..."
done

echo "[$(date -Iseconds)] ERROR: Health check fallido tras $MAX_RETRIES intentos."
echo "Logs del contenedor:"
docker compose logs --tail=50
echo ""
echo "Para rollback: bash $REPO_DIR/scripts/rollback.sh"
exit 1
