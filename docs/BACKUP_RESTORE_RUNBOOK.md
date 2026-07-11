# Runbook: backup y restauración de la base de datos

## Cómo funcionan los backups automatizados

- Job nocturno del scheduler a las **02:30 UTC** (`_run_db_backup` en `app/services/scheduler.py`).
- Usa la API de backup de sqlite3 (`app/services/backup_service.py`): copia consistente
  aunque la app esté escribiendo (compatible con WAL), después comprime a gzip.
- Destino: `<directorio de la BD>/backups/riskhub-YYYYMMDD-HHMMSS.db.gz`.
  En Docker eso queda dentro del volumen `riskhub-data`, así que los backups
  sobreviven a recreaciones del contenedor (no a la pérdida del volumen — ver
  "Copia fuera del servidor").
- Retención: 14 días por defecto. Configurable:
  - `RISKHUB_BACKUP_RETENTION_DAYS` (0 = no purgar nunca)
  - `RISKHUB_BACKUP_DIR` (directorio alternativo)
- Si la BD es PostgreSQL (`RISKHUB_DATABASE_URL`), el servicio se desactiva solo:
  el backup pasa a ser `pg_dump` externo (ver `docs/POSTGRES_MIGRATION_PLAN.md`).

## Endpoints (superadmin)

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/admin/backups` | Listar backups disponibles |
| POST | `/api/admin/backups/run` | Lanzar un backup inmediato |
| GET | `/api/admin/backups/{filename}` | Descargar un backup concreto |
| GET | `/api/admin/backup-db` | Descarga directa de la BD viva (legacy, sin comprimir) |

## Restaurar un backup (producción, Docker)

> Ventana de corte: la app estará parada 1-2 minutos. Avisar a los usuarios.

```bash
ssh root@91.99.83.202 -i ~/.ssh/id_ed25519
cd /opt/riskhub

# 1. Parar la app (el volumen persiste)
docker compose down

# 2. Localizar el volumen y los backups
VOLPATH=$(docker volume inspect riskhub-data --format '{{.Mountpoint}}')
ls -lh "$VOLPATH/backups/"

# 3. Guardar la BD actual por si acaso (¡siempre!)
cp "$VOLPATH/riskhub.db" "$VOLPATH/riskhub.db.pre-restore.$(date +%Y%m%d%H%M)"

# 4. Restaurar el backup elegido
gunzip -c "$VOLPATH/backups/riskhub-YYYYMMDD-HHMMSS.db.gz" > "$VOLPATH/riskhub.db"

# 5. Eliminar los ficheros WAL/SHM antiguos (quedaron de la BD anterior)
rm -f "$VOLPATH/riskhub.db-wal" "$VOLPATH/riskhub.db-shm"

# 6. Arrancar y verificar
docker compose up -d
curl -s http://localhost/api/health
```

Verificación post-restore: login, dashboard con datos, y revisar
`docker compose logs --tail 50 app` por errores de migración (el arranque
re-aplica `_migrate_columns()`, que es idempotente).

## Restaurar en local (desarrollo)

```powershell
# Con la app parada
gzip -d -k .\backups\riskhub-YYYYMMDD-HHMMSS.db.gz
Move-Item -Force .\backups\riskhub-YYYYMMDD-HHMMSS.db .\riskhub.db
Remove-Item -Force .\riskhub.db-wal, .\riskhub.db-shm -ErrorAction SilentlyContinue
```

## Copia fuera del servidor (recomendado)

Los backups viven en el mismo disco que la BD: un fallo del servidor pierde
ambos. Mínimo viable — cron en tu máquina o en otro host:

```bash
# rsync diario de los backups a otra máquina
rsync -az -e "ssh -i ~/.ssh/id_ed25519" \
  root@91.99.83.202:"$(ssh root@91.99.83.202 -i ~/.ssh/id_ed25519 docker volume inspect riskhub-data --format '{{.Mountpoint}}')/backups/" \
  ~/riskhub-backups/
```

(O configurar un cron en el servidor que suba a Hetzner Storage Box / S3.)

## Qué NO cubre este backup

- `rate_limits.db` (contadores de rate limiting — prescindible).
- Ficheros subidos si en el futuro se guardan fuera del volumen.
- La clave `RISKHUB_SECRET_KEY` del `.env` — **sin ella los secretos cifrados
  con Fernet (API keys, SMTP, webhooks) no se pueden descifrar**. Guardar el
  `.env` del servidor en un gestor de secretos aparte.
