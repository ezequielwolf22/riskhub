#!/bin/bash
# backup.sh — Copia segura de la BD SQLite de RiskHub con rotacion de 30 dias.
# Uso: bash /opt/riskhub/scripts/backup.sh
# Cron recomendado: 0 2 * * * bash /opt/riskhub/scripts/backup.sh >> /srv/data/logs/backup.log 2>&1

set -euo pipefail

CONTAINER="riskhub"
DB_IN_CONTAINER="/srv/data/riskhub.db"
BACKUP_DIR="/srv/data/backups"
RETENTION_DAYS=30
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/riskhub_${TIMESTAMP}.db.gz"

# Verificar que el contenedor esta corriendo. Se hace el backup via "docker
# exec" en lugar de leer el archivo directamente desde el host: el nombre real
# del volumen Docker depende del project name de Compose (p.ej. el volumen
# declarado "riskhub-data" en docker-compose.yml termina llamandose en disco
# "riskhub_riskhub-data", con un prefijo que puede variar) — usar el path
# dentro del contenedor evita depender de ese detalle.
if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" >/dev/null 2>&1; then
    echo "[$(date -Iseconds)] ERROR: El contenedor $CONTAINER no esta corriendo"
    exit 1
fi

# Crear directorio de backups si no existe
mkdir -p "$BACKUP_DIR"

# Hacer snapshot seguro via SQLite .backup (evita corrupcion durante escrituras)
echo "[$(date -Iseconds)] Iniciando backup de RiskHub..."

TEMP_COPY=$(mktemp /tmp/riskhub_backup_XXXXXX.db)
# La imagen (python:3.11-slim) no trae el binario "sqlite3", asi que se usa
# el modulo sqlite3 de la stdlib de Python (ya presente) en su lugar.
docker exec "$CONTAINER" python -c "
import sqlite3
src = sqlite3.connect('$DB_IN_CONTAINER')
dst = sqlite3.connect('/tmp/riskhub_backup_tmp.db')
src.backup(dst)
dst.close()
src.close()
"
docker cp "${CONTAINER}:/tmp/riskhub_backup_tmp.db" "$TEMP_COPY"
docker exec "$CONTAINER" rm -f /tmp/riskhub_backup_tmp.db

# Comprimir
gzip -c "$TEMP_COPY" > "$BACKUP_FILE"
rm -f "$TEMP_COPY"

BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "[$(date -Iseconds)] Backup creado: $BACKUP_FILE ($BACKUP_SIZE)"

# Rotar backups antiguos
DELETED=$(find "$BACKUP_DIR" -name "riskhub_*.db.gz" -mtime +"$RETENTION_DAYS" -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[$(date -Iseconds)] $DELETED backups antiguos eliminados (retencion: $RETENTION_DAYS dias)"
fi

# Verificar integridad del backup
VERIFY=$(gzip -t "$BACKUP_FILE" && echo "OK" || echo "FAIL")
echo "[$(date -Iseconds)] Integridad del backup: $VERIFY"

if [ "$VERIFY" != "OK" ]; then
    echo "[$(date -Iseconds)] ERROR: El backup no paso la verificacion de integridad"
    exit 1
fi

echo "[$(date -Iseconds)] Backup completado correctamente."
