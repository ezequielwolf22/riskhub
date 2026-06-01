"""Configuracion centralizada de logging para RiskHub."""
import logging
import logging.handlers
import os
from pathlib import Path


def setup_logging(env: str = "development") -> None:
    """Configura logging con rotacion de archivos y formato consistente.

    - En produccion: archivo rotativo + consola (INFO+)
    - En desarrollo: consola verbose (DEBUG)
    """
    log_level = logging.INFO if env == "production" else logging.DEBUG

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handlers: list[logging.Handler] = []

    # Handler de consola — siempre activo
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(log_level)
    handlers.append(console)

    # Handler de archivo rotativo — solo en produccion o si LOG_DIR esta definido
    log_dir_str = os.environ.get("RISKHUB_LOG_DIR", "/srv/data/logs" if env == "production" else "")
    if log_dir_str:
        log_dir = Path(log_dir_str)
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.TimedRotatingFileHandler(
                filename=log_dir / "riskhub.log",
                when="midnight",
                interval=1,
                backupCount=30,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.INFO)
            handlers.append(file_handler)

            # Log de errores separado
            error_handler = logging.handlers.TimedRotatingFileHandler(
                filename=log_dir / "riskhub_errors.log",
                when="midnight",
                interval=1,
                backupCount=90,
                encoding="utf-8",
            )
            error_handler.setFormatter(formatter)
            error_handler.setLevel(logging.ERROR)
            handlers.append(error_handler)
        except (PermissionError, OSError) as exc:
            logging.getLogger(__name__).warning(
                "No se pudo crear log en disco (%s). Usando solo consola.", exc
            )

    # Configurar el logger raiz
    root = logging.getLogger()
    root.setLevel(log_level)
    # Limpiar handlers existentes antes de agregar los nuestros
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)

    # Reducir verbosidad de librerias externas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
