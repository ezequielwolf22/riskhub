#!/bin/bash
# backup_offsite.sh — Replica los backups locales a un Hetzner Storage Box
# (copia offsite 3-2-1). Se ejecuta despues del backup local diario.
#
# Uso: bash /opt/riskhub/scripts/backup_offsite.sh
# Cron recomendado: justo despues de backup.sh (ver setup_cron.sh).
#
# Configuracion: NO lleva credenciales embebidas. Lee /etc/riskhub/offsite.env,
# que el operador crea una sola vez con los datos de su Storage Box:
#
#   # /etc/riskhub/offsite.env  (chmod 600, propietario root)
#   STORAGEBOX_USER="u123456"                       # o un sub-usuario u123456-sub1
#   STORAGEBOX_HOST="u123456.your-storagebox.de"
#   STORAGEBOX_PORT="23"                            # Hetzner: SSH/rsync en el puerto 23
#   STORAGEBOX_SSH_KEY="/root/.ssh/storagebox_ed25519"
#   STORAGEBOX_REMOTE_DIR="riskhub-backups"         # carpeta destino dentro del box
#   OFFSITE_RETENTION_DAYS="30"                      # 0 = no purgar en remoto
#
# Alta de la clave (una vez, desde el servidor, con la clave publica ya
# autorizada en el Storage Box via panel de Hetzner o ssh-copy-id -p23):
#   ssh-keygen -t ed25519 -f /root/.ssh/storagebox_ed25519 -N ""
#   # subir la publica al Storage Box (menu "SSH keys" del panel, o):
#   #   cat /root/.ssh/storagebox_ed25519.pub | ssh -p23 u123456@u123456.your-storagebox.de install-ssh-key
#
# Si falta el fichero de config o algun dato, el script AVISA y termina con
# exito (exit 0): la ausencia de offsite no debe tumbar el backup local ni el
# deploy. Solo un fallo real de transferencia (con config presente) da error.

set -uo pipefail

CONFIG_FILE="${RISKHUB_OFFSITE_ENV:-/etc/riskhub/offsite.env}"
LOCAL_BACKUP_DIR="${RISKHUB_BACKUP_DIR:-/srv/data/backups}"

log() { echo "[$(date -Iseconds)] $*"; }

if [ ! -f "$CONFIG_FILE" ]; then
    log "AVISO: $CONFIG_FILE no existe. Backup offsite no configurado — omitido."
    log "       Crea el fichero segun la cabecera de este script para activarlo."
    exit 0
fi

# shellcheck disable=SC1090
source "$CONFIG_FILE"

STORAGEBOX_PORT="${STORAGEBOX_PORT:-23}"
STORAGEBOX_REMOTE_DIR="${STORAGEBOX_REMOTE_DIR:-riskhub-backups}"
OFFSITE_RETENTION_DAYS="${OFFSITE_RETENTION_DAYS:-30}"

missing=""
[ -z "${STORAGEBOX_USER:-}" ] && missing="$missing STORAGEBOX_USER"
[ -z "${STORAGEBOX_HOST:-}" ] && missing="$missing STORAGEBOX_HOST"
[ -z "${STORAGEBOX_SSH_KEY:-}" ] && missing="$missing STORAGEBOX_SSH_KEY"
if [ -n "$missing" ]; then
    log "AVISO: faltan variables en $CONFIG_FILE:$missing — offsite omitido."
    exit 0
fi
if [ ! -f "$STORAGEBOX_SSH_KEY" ]; then
    log "AVISO: la clave SSH $STORAGEBOX_SSH_KEY no existe — offsite omitido."
    exit 0
fi
if [ ! -d "$LOCAL_BACKUP_DIR" ]; then
    log "AVISO: no hay directorio de backups local ($LOCAL_BACKUP_DIR) — nada que replicar."
    exit 0
fi

SSH_CMD="ssh -p ${STORAGEBOX_PORT} -i ${STORAGEBOX_SSH_KEY} -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
REMOTE="${STORAGEBOX_USER}@${STORAGEBOX_HOST}"

log "Replicando $LOCAL_BACKUP_DIR -> ${REMOTE}:${STORAGEBOX_REMOTE_DIR}/ (puerto ${STORAGEBOX_PORT})"

# Asegurar la carpeta remota (el Storage Box trae un sftp/ssh restringido pero
# admite mkdir). No fallar si ya existe.
$SSH_CMD "$REMOTE" "mkdir -p ${STORAGEBOX_REMOTE_DIR}" 2>/dev/null || true

# rsync incremental: solo sube backups nuevos, verifica por tamanio+mtime.
# --ignore-existing evita reescribir los .gz ya subidos (son inmutables).
if ! rsync -a --ignore-existing --stats \
        -e "$SSH_CMD" \
        "$LOCAL_BACKUP_DIR"/riskhub*.db.gz \
        "${REMOTE}:${STORAGEBOX_REMOTE_DIR}/" 2>&1 | sed 's/^/    /'; then
    log "ERROR: la transferencia rsync al Storage Box fallo."
    exit 1
fi

log "Replica offsite completada."

# Purga remota por retencion (opcional). El shell del Storage Box es limitado
# pero admite find; si no, se ignora sin romper.
if [ "$OFFSITE_RETENTION_DAYS" -gt 0 ] 2>/dev/null; then
    if $SSH_CMD "$REMOTE" \
        "find ${STORAGEBOX_REMOTE_DIR} -name 'riskhub*.db.gz' -mtime +${OFFSITE_RETENTION_DAYS} -delete" 2>/dev/null; then
        log "Purga remota aplicada (retencion: ${OFFSITE_RETENTION_DAYS} dias)."
    else
        log "AVISO: no se pudo purgar en remoto (shell restringido). Revisa retencion manualmente."
    fi
fi

log "Backup offsite OK."
