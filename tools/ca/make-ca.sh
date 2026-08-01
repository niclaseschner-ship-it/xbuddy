#!/usr/bin/env bash
#
# make-ca.sh — lokale Root-CA + Server-Zertifikat für die XBuddy-Origin (#36).
#
# Formalisiert das ad-hoc-CA-Setup. Es erzeugt:
#   (a) eine lokale Root-CA  — lange Laufzeit (~10 Jahre), der die Geräte der
#       Familie einmalig vertrauen (URL-11);
#   (b) ein Server-Zertifikat für die EINE XBuddy-Origin (URL-12), signiert
#       von dieser CA, mit passenden SAN-Einträgen.
#
# Hintergrund (das *Warum*): siehe specs/platform/urls.md URL-11 + URL-12.
# Anleitung (das *Wie*): siehe tools/ca/README.md.
#
# Geheimnisse — CLAUDE.md §8:
#   Die erzeugten Schlüssel (rootCA-key.pem, server-key.pem) sind Per-Instanz-
#   Geheimnisse. Sie gehören NIEMALS ins Repo. Nur dieses Skript ist versioniert;
#   der voreingestellte Ausgabe-Ordner (out/) ist per .gitignore ausgeschlossen.
#
# Idempotenz:
#   - Eine bereits vorhandene Root-CA wird wiederverwendet (nicht überschrieben),
#     damit ausgerollte Geräte-Trust-Anker gültig bleiben. Wer die CA neu bauen
#     will, löscht rootCA*.pem von Hand oder nutzt einen leeren --out-Ordner.
#   - Das Server-Zertifikat wird bei jedem Lauf neu ausgestellt (kurzlebiger,
#     SAN-Liste kann sich ändern) — die CA bleibt dabei stabil.
#
set -euo pipefail

# ----------------------------------------------------------------------
#  Parameter — alles überschreibbar, sinnvolle Defaults aus dem ad-hoc-Setup.
# ----------------------------------------------------------------------
OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/out"
CA_DAYS=3650          # ~10 Jahre Root-CA-Laufzeit (URL-11: lange Laufzeit)
SERVER_DAYS=365       # Server-Cert: <=398 Tage (CAV-8: CA/Browser-Forum, Apple-Strenge)
CA_CN="XBuddy Dev CA"
CA_O="XBuddy"
SERVER_CN="xbuddy-hub"
# SAN-Einträge der Origin. Per-Instanz: Host-IP der Pi + lokale DNS-Namen.
# Komma-getrennte Liste aus IP:<addr> und DNS:<name>.
SAN="DNS:localhost,DNS:xbuddy-hub.local,IP:127.0.0.1"

usage() {
  cat <<'EOF'
make-ca.sh — XBuddy Root-CA + Server-Zertifikat (#36)

Verwendung:
  tools/ca/make-ca.sh [Optionen]

Optionen:
  --out DIR           Ausgabe-Verzeichnis (Default: tools/ca/out)
  --san LISTE         SAN-Einträge der Origin, komma-getrennt
                      (Default: DNS:localhost,DNS:xbuddy-hub.local,IP:127.0.0.1)
                      Beispiel: --san "DNS:xbuddy-hub.local,IP:192.168.0.78"
  --server-cn NAME    Common Name des Server-Certs (Default: xbuddy-hub)
  --ca-days N         Laufzeit der Root-CA in Tagen (Default: 3650, ~10 Jahre)
  --server-days N     Laufzeit des Server-Certs in Tagen (Default: 365, max 398 — CAV-8)
  -h, --help          diese Hilfe

Ergebnis im Ausgabe-Verzeichnis:
  rootCA.pem          Root-CA-Zertifikat  — auf die Geräte der Familie verteilen
  rootCA-key.pem      Root-CA-Schlüssel   — GEHEIM, niemals weitergeben
  server-cert.pem     Server-Zertifikat  — für nginx (ssl_certificate)
  server-key.pem      Server-Schlüssel   — GEHEIM, für nginx (ssl_certificate_key)

Beispiel (Pi mit fester LAN-IP):
  tools/ca/make-ca.sh --san "DNS:xbuddy-hub.local,IP:192.168.0.78"
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)         OUT_DIR="$2"; shift 2 ;;
    --san)         SAN="$2"; shift 2 ;;
    --server-cn)   SERVER_CN="$2"; shift 2 ;;
    --ca-days)     CA_DAYS="$2"; shift 2 ;;
    --server-days) SERVER_DAYS="$2"; shift 2 ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "unbekannte Option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

command -v openssl >/dev/null 2>&1 || { echo "openssl nicht gefunden" >&2; exit 1; }

mkdir -p "$OUT_DIR"

CA_KEY="$OUT_DIR/rootCA-key.pem"
CA_CERT="$OUT_DIR/rootCA.pem"
SRV_KEY="$OUT_DIR/server-key.pem"
SRV_CSR="$OUT_DIR/server.csr"
SRV_CERT="$OUT_DIR/server-cert.pem"
SRV_EXT="$OUT_DIR/server-ext.cnf"

# ----------------------------------------------------------------------
#  (a) Root-CA — idempotent: vorhandene CA wird wiederverwendet.
# ----------------------------------------------------------------------
if [[ -f "$CA_KEY" && -f "$CA_CERT" ]]; then
  echo "Root-CA existiert bereits — wiederverwendet: $CA_CERT"
else
  echo "Erzeuge Root-CA ($CA_DAYS Tage) …"
  openssl genrsa -out "$CA_KEY" 4096
  chmod 600 "$CA_KEY"
  openssl req -x509 -new -nodes \
    -key "$CA_KEY" \
    -sha256 -days "$CA_DAYS" \
    -subj "/O=$CA_O/CN=$CA_CN" \
    -out "$CA_CERT"
fi

# ----------------------------------------------------------------------
#  (b) Server-Zertifikat — bei jedem Lauf neu, von der CA signiert.
# ----------------------------------------------------------------------
echo "Erzeuge Server-Zertifikat ($SERVER_DAYS Tage, CN=$SERVER_CN) …"
echo "  SAN: $SAN"

# v3-Erweiterungen des Server-Certs: Server-TLS, mit SAN-Liste.
cat > "$SRV_EXT" <<EOF
basicConstraints = CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = $SAN
EOF

openssl genrsa -out "$SRV_KEY" 2048
chmod 600 "$SRV_KEY"
openssl req -new \
  -key "$SRV_KEY" \
  -subj "/CN=$SERVER_CN" \
  -out "$SRV_CSR"
openssl x509 -req \
  -in "$SRV_CSR" \
  -CA "$CA_CERT" -CAkey "$CA_KEY" -CAcreateserial \
  -sha256 -days "$SERVER_DAYS" \
  -extfile "$SRV_EXT" \
  -out "$SRV_CERT"

echo
echo "Fertig. Artefakte in: $OUT_DIR"
echo "  rootCA.pem       → auf die Geräte der Familie verteilen (Trust-Anker)"
echo "  server-cert.pem  → nginx ssl_certificate"
echo "  server-key.pem   → nginx ssl_certificate_key  (GEHEIM)"
echo
echo "Verifikation der Kette:"
openssl verify -CAfile "$CA_CERT" "$SRV_CERT"
