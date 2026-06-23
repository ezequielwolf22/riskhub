"""Herramienta del vendor para generar ficheros de licencia on-premise.

USO (solo el vendor, NUNCA en el servidor del cliente):
    python tools/gen_license.py \\
        --org "Empresa S.A." \\
        --plan pro \\
        --days 365 \\
        --key /ruta/privada/riskhub_vendor_private.pem \\
        --out license.jwt

Luego entregar license.jwt al cliente para que lo suba via UI admin o lo coloque en:
    /srv/data/license.jwt  (dentro del volumen Docker)

GENERACION DEL PAR DE CLAVES (una sola vez, por el vendor):
    openssl genrsa -out riskhub_vendor_private.pem 2048
    openssl rsa -in riskhub_vendor_private.pem -pubout -out riskhub_vendor_public.pem
    # Actualizar _VENDOR_PUBLIC_KEY en app/services/crypto_license.py con el contenido de riskhub_vendor_public.pem
    # Guardar riskhub_vendor_private.pem en un gestor de secretos (NUNCA en el repo)
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt as pyjwt

_ISSUER = "riskhub-vendor"


def main():
    p = argparse.ArgumentParser(description="Generador de licencias RiskHub on-premise")
    p.add_argument("--org",   required=True,  help="Nombre de la organizacion cliente")
    p.add_argument("--plan",  required=True,  choices=["free", "starter", "pro", "enterprise"],
                   help="Plan de licencia")
    p.add_argument("--days",  type=int, default=365, help="Validez en dias (default: 365)")
    p.add_argument("--grace", type=int, default=30,  help="Dias de gracia tras expirar (default: 30)")
    p.add_argument("--key",   required=True,  help="Ruta a la clave RSA privada del vendor (.pem)")
    p.add_argument("--out",   default="license.jwt", help="Fichero de salida (default: license.jwt)")
    p.add_argument("--modules", nargs="*", default=["all"],
                   help="Modulos habilitados (default: all)")
    args = p.parse_args()

    private_key_path = Path(args.key)
    if not private_key_path.exists():
        print(f"ERROR: clave privada no encontrada: {args.key}", file=sys.stderr)
        sys.exit(1)

    private_key = private_key_path.read_text()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=args.days)

    payload = {
        "iss": _ISSUER,
        "sub": args.org,
        "plan": args.plan,
        "modules": args.modules,
        "grace_days": args.grace,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    token = pyjwt.encode(payload, private_key, algorithm="RS256")

    out_path = Path(args.out)
    out_path.write_text(token if isinstance(token, str) else token.decode())

    print(f"Licencia generada correctamente:")
    print(f"  Org:      {args.org}")
    print(f"  Plan:     {args.plan}")
    print(f"  Emitida:  {now.strftime('%Y-%m-%d')}")
    print(f"  Expira:   {exp.strftime('%Y-%m-%d')} ({args.days} dias)")
    print(f"  Gracia:   {args.grace} dias post-expiry (modo solo lectura)")
    print(f"  Fichero:  {out_path.resolve()}")
    print()
    print("INSTRUCCIONES PARA EL CLIENTE:")
    print(f"  1. Sube el fichero {out_path.name} desde Configuracion > Licencia en RiskHub")
    print(f"  2. O coloca el fichero en /srv/data/license.jwt dentro del servidor")
    print(f"  3. Reinicia la aplicacion para que tome efecto")


if __name__ == "__main__":
    main()
