#!/bin/bash
# generate-certs.sh — Genera certificado TLS auto-firmado para RiskHub.
# Uso: bash /opt/riskhub/nginx/generate-certs.sh
# El certificado se crea una sola vez; si ya existe, no se sobreescribe.

CERT_DIR="$(dirname "$0")/certs"
mkdir -p "$CERT_DIR"

if [ ! -f "$CERT_DIR/riskhub.crt" ]; then
    echo "Generando certificado TLS auto-firmado (valido 10 anos)..."
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "$CERT_DIR/riskhub.key" \
        -out "$CERT_DIR/riskhub.crt" \
        -subj "/C=ES/ST=Madrid/L=Madrid/O=RiskHub/CN=riskhub.local"
    chmod 600 "$CERT_DIR/riskhub.key"
    chmod 644 "$CERT_DIR/riskhub.crt"
    echo "Certificado auto-firmado generado en $CERT_DIR"
else
    echo "Certificado ya existe en $CERT_DIR, omitiendo generacion."
fi
