#!/usr/bin/env bash
# Einmalig-Setup des Hörspiel-Buddy auf der Pi-Instanz (HSP-25/HSP-26).
# Idempotent: cp -n verhindert Überschreiben vorhandener Dateien.
# KEIN cp -p — per-Instanz-Daten dürfen nie blind aus dem Repo überschrieben
# werden (feedback_xbuddy_data_familie_kein_blind_copy).
set -euo pipefail

DATA_ROOT="/home/buddy/xbuddy-data/hoerspiel/data"
BRAINSTORM_DIR="/home/buddy/brainstorm/ideas/mia-hoerspiel-app"
PHOTO_SRC="/home/buddy/xbuddy-data/photo/medien/foto-01.jpg"

# -- Verzeichnisstruktur anlegen (idempotent) ----------------------------
mkdir -p \
    "${DATA_ROOT}/alben" \
    "${DATA_ROOT}/shared-assets"

# -- Quell-Dokumente aus Brainstorm (idempotent via cp -n) ---------------
if [ ! -f "${DATA_ROOT}/bible.md" ]; then
    cp "${BRAINSTORM_DIR}/welt_und_charaktere.md" "${DATA_ROOT}/bible.md"
fi

if [ ! -f "${DATA_ROOT}/folgen-historie.md" ]; then
    cp "${BRAINSTORM_DIR}/folgen_historie.md" "${DATA_ROOT}/folgen-historie.md"
fi

# -- Default-Cover-Bild (idempotent) -------------------------------------
if [ ! -f "${DATA_ROOT}/shared-assets/cover-default.jpg" ]; then
    cp "${PHOTO_SRC}" "${DATA_ROOT}/shared-assets/cover-default.jpg"
fi

# -- Intro-Reim (idempotent) ---------------------------------------------
if [ ! -f "${DATA_ROOT}/shared-assets/intro.txt" ]; then
    cat > "${DATA_ROOT}/shared-assets/intro.txt" <<'EOF'
Im Garten hinterm gelben Haus, da schaut die Sonne morgens raus.
Da fliegt ein Stieglitz — seht ihr Stigi?
Da rollt ein Igel — das ist Malini.
Und Vögelchen, ganz lila, ganz weich, schläft im Gras im Sonnenreich.
Drei Freunde, ein Garten, ein Tag fängt an.
Hört zu, was heute alles geschehen kann.
EOF
fi

# -- Outro-Reim (idempotent) ---------------------------------------------
if [ ! -f "${DATA_ROOT}/shared-assets/outro.txt" ]; then
    cat > "${DATA_ROOT}/shared-assets/outro.txt" <<'EOF'
Im Garten hinterm gelben Haus, ruht die Sonne abends aus.
Stigi schläft, Malini auch, Vögelchen träumt im Gartenstrauch.
Drei Freunde, ein Garten, ein Tag ist um.
Morgen geht's weiter, drrrrum:
Schlaf jetzt schön, träum süß und fein, bis morgen, kleines Kind, schlaf ein.
EOF
fi

echo "bootstrap: Hörspiel-Datenwurzel bereit unter ${DATA_ROOT}"
