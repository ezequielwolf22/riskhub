#!/bin/bash
# setup_cron.sh — Configura crons del sistema para RiskHub.
# Uso: bash /opt/riskhub/scripts/setup_cron.sh
# Requiere: ejecutar como root

set -euo pipefail

CRON_FILE="/etc/cron.d/riskhub"
LOG_DIR="/srv/data/logs"

mkdir -p "$LOG_DIR"

cat > "$CRON_FILE" << 'EOF'
# RiskHub — tareas programadas del sistema
# Backup diario de la BD a las 02:00
0 2 * * * root bash /opt/riskhub/scripts/backup.sh >> /srv/data/logs/backup.log 2>&1

# Rotar logs del backup mensualmente (retener ultimos 3 meses)
0 3 1 * * root find /srv/data/logs -name "backup.log.*" -mtime +90 -delete 2>/dev/null || true
EOF

chmod 644 "$CRON_FILE"

echo "Crons instalados en $CRON_FILE"
echo "Verificar con: crontab -l o cat $CRON_FILE"
