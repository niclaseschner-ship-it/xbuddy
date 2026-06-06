"""Wetter-Buddy — Schreib-Validierung + atomarer Save der Garderobe (WETTER-30).

Siehe specs/buddies/wetter.md §10. Dieses Modul besitzt das **Speichern** der
editierten Garderoben-Matrix aus dem Eltern-Editor (WETTER-26): es validiert die
gesendete Matrix gegen die kuratierte Palette (WETTER-29) und den frisch
geladenen Stand und schreibt `wetter.json` **atomar** zurück — auf denselben
Pfad, den config.py liest, sodass der Kiosk die Änderung per Reload-on-Read
(DCOMP-2) ohne Restart übernimmt.

Editierbar sind **nur die Kleidungs-Sets** (Pflicht/Optional je Regel und des
Fallbacks, WETTER-28). Schwellen (`bedingung`), Hinweistext sowie **Anzahl und
Reihenfolge** der Regeln bleiben read-only — dieses Modul übernimmt sie
unverändert aus dem geladenen Stand und lehnt eine Matrix ab, deren Regel-Anzahl
oder Bedingungs-Reihenfolge abweicht (WETTER-28/30).

Validierung (WETTER-30) läuft **vor** dem Write: jede Pflicht-Zelle (jede Regel
UND das Fallback) nicht leer, jedes Pikto aus der Palette; Optional-Sets dürfen
leer sein. Schlägt sie fehl, bleibt `wetter.json` **byte-unverändert**.

Der atomare Write spiegelt das photo/store.py-Muster (Temp-Datei im
Zielverzeichnis + os.replace) — **kein zweiter Schreibstil**.

Public-API: `speichere_garderobe`, Fehlertyp `ValidierungsFehler`/`StoreError`.
"""

import contextlib
import json
import os
import tempfile


class StoreError(Exception):
    """Der atomare Schreibvorgang von wetter.json ist fehlgeschlagen (WETTER-30/DCOMP-4)."""


class ValidierungsFehler(Exception):
    """Die gesendete Matrix ist ungültig (WETTER-30) — es wird NICHT geschrieben.

    `wetter.json` bleibt byte-unverändert; der Editor zeigt die Begründung.
    """


def _bedingung_signatur(roh_regel):
    """Die read-only Bedingung einer Regel als vergleichbare Signatur (WETTER-28).

    Dient dem Reihenfolge-/Anzahl-Check: nur die `bedingung` zählt — die ist die
    Identität der Regel, die der Editor NICHT verändern darf.
    """
    return json.dumps(roh_regel.get("bedingung") or {}, sort_keys=True,
                      ensure_ascii=False)


def _set_aus_matrix(eintrag, schluessel, kontext, palette_piktos):
    """Liest ein Kleidungs-Set (`pflicht`/`optional`) aus einem Matrix-Eintrag.

    Validiert jedes Stück gegen die Palette (WETTER-29/30) und baut die
    `{name, pikto}`-Liste im config.py-Feldformat. Hebt ValidierungsFehler bei
    einem Pikto außerhalb der Palette oder einem strukturell kaputten Eintrag.
    """
    roh = eintrag.get(schluessel) or []
    if not isinstance(roh, list):
        raise ValidierungsFehler(
            "%s: %r ist keine Liste von Kleidungsstücken" % (kontext, schluessel))
    teile = []
    for stueck in roh:
        if not isinstance(stueck, dict) or stueck.get("pikto") in (None, ""):
            raise ValidierungsFehler(
                "%s (%s): Kleidungsstück ohne pikto: %r" % (kontext, schluessel, stueck))
        pikto = str(stueck["pikto"])
        if pikto not in palette_piktos:
            raise ValidierungsFehler(
                "%s (%s): pikto %r nicht in der kuratierten Palette (WETTER-29)"
                % (kontext, schluessel, pikto))
        name = str(stueck.get("name", "")).strip()
        if not name:
            # Der Name folgt aus der Palette — wir akzeptieren auch nur das
            # Pikto und ergänzen den Palette-Namen nicht hier (Editor sendet
            # beides). Leerer Name ist erlaubt, config.py braucht aber name:
            # in der Praxis liefert der Editor den Palette-Namen mit.
            raise ValidierungsFehler(
                "%s (%s): Kleidungsstück ohne name: %r" % (kontext, schluessel, stueck))
        teile.append({"name": name, "pikto": pikto})
    return teile


def _merge_outfit(roh_alt, eintrag_neu, kontext, palette_piktos, pflicht_pflicht):
    """Baut den neuen Outfit-Block: editierte Sets, read-only Bedingung/Hinweis.

    `roh_alt` ist der Block aus dem geladenen Stand (Regel oder Fallback);
    `eintrag_neu` der editierte Block aus der gesendeten Matrix. Pflicht/Optional
    kommen aus `eintrag_neu` (validiert); `bedingung` und `hinweis` werden
    unverändert aus `roh_alt` übernommen (WETTER-28). `pflicht_pflicht=True`
    erzwingt ein nicht-leeres Pflicht-Set (WETTER-30).
    """
    pflicht = _set_aus_matrix(eintrag_neu, "pflicht", kontext, palette_piktos)
    optional = _set_aus_matrix(eintrag_neu, "optional", kontext, palette_piktos)
    if pflicht_pflicht and not pflicht:
        raise ValidierungsFehler(
            "%s: Pflicht-Set darf nicht leer sein (WETTER-30)" % kontext)
    block = dict(roh_alt)  # read-only Felder (bedingung, hinweis, _was) behalten
    block["pflicht"] = pflicht
    block["optional"] = optional
    return block


def baue_neuen_stand(geladener_stand, neue_matrix, palette):
    """Validiert die Matrix und baut den neuen wetter.json-Inhalt (WETTER-28/30).

    `geladener_stand` ist das frisch geladene wetter.json (dict) — die SSoT für
    die read-only Felder (Ort, Schwellen, Hinweise, Tageszeiten). `neue_matrix`
    ist die editierte Matrix `{regeln: [...], fallback: {...}}` aus dem Editor.
    `palette` ist das palette-Modul (Public-API `erlaubte_piktos`).

    Hebt ValidierungsFehler, wenn Anzahl/Reihenfolge der Regeln abweicht, eine
    Pflicht-Zelle leer ist oder ein Pikto außerhalb der Palette liegt. Liefert
    bei Gültigkeit den vollständigen neuen Stand (dict) zum atomaren Schreiben —
    schreibt selbst NICHT.
    """
    if not isinstance(neue_matrix, dict):
        raise ValidierungsFehler("Matrix ist kein Objekt")
    alt_wardrobe = (geladener_stand.get("wardrobe") or {})
    alt_regeln = alt_wardrobe.get("regeln") or []
    neu_regeln = neue_matrix.get("regeln")
    if not isinstance(neu_regeln, list):
        raise ValidierungsFehler("Matrix ohne `regeln`-Liste")

    # WETTER-28: Anzahl + Bedingungs-Reihenfolge unverändert.
    if len(neu_regeln) != len(alt_regeln):
        raise ValidierungsFehler(
            "Regel-Anzahl verändert (%d ≠ %d) — Anzahl ist read-only (WETTER-28)"
            % (len(neu_regeln), len(alt_regeln)))
    for i, (alt, neu) in enumerate(zip(alt_regeln, neu_regeln, strict=True)):
        if not isinstance(neu, dict):
            raise ValidierungsFehler("Regel %d ist kein Objekt" % i)
        if "bedingung" in neu and \
                _bedingung_signatur(neu) != _bedingung_signatur(alt):
            raise ValidierungsFehler(
                "Regel %d: Bedingung/Reihenfolge verändert — read-only (WETTER-28)" % i)

    palette_piktos = palette.erlaubte_piktos()

    neue_regeln = [
        _merge_outfit(alt, neu, "Regel %d" % i, palette_piktos, pflicht_pflicht=True)
        for i, (alt, neu) in enumerate(zip(alt_regeln, neu_regeln, strict=True))
    ]

    alt_fb = alt_wardrobe.get("fallback")
    if not isinstance(alt_fb, dict):
        raise ValidierungsFehler("Geladener Stand ohne `fallback` (WETTER-14)")
    neu_fb = neue_matrix.get("fallback")
    if not isinstance(neu_fb, dict):
        raise ValidierungsFehler("Matrix ohne `fallback`-Objekt")
    neues_fb = _merge_outfit(alt_fb, neu_fb, "fallback", palette_piktos,
                             pflicht_pflicht=True)

    neuer_stand = dict(geladener_stand)
    neue_wardrobe = dict(alt_wardrobe)
    neue_wardrobe["regeln"] = neue_regeln
    neue_wardrobe["fallback"] = neues_fb
    neuer_stand["wardrobe"] = neue_wardrobe
    return neuer_stand


def _schreibe_atomar(config_path, neuer_stand):
    """Schreibt wetter.json atomar (DCOMP-4, photo/store.py-Muster).

    Temp-Datei im Zielverzeichnis → os.replace. Hebt StoreError ohne eine halbe
    oder verwaiste Temp-Datei zu hinterlassen. So sieht ein gleichzeitiger
    Kiosk-Read (DCOMP-2) nie eine halb geschriebene Datei (WETTER-30).
    """
    ziel_dir = os.path.dirname(os.path.abspath(config_path)) or "."
    os.makedirs(ziel_dir, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".wetter.", suffix=".json.tmp",
                                        dir=ziel_dir)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(neuer_stand, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, config_path)
    except OSError as e:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise StoreError("wetter.json konnte nicht geschrieben werden: %s" % e) from e


def speichere_garderobe(config_path, neue_matrix, palette, geladener_stand):
    """Validiert + schreibt die editierte Garderobe atomar (WETTER-28/30).

    `config_path` ist der Pfad, den der Kiosk liest (`runtime['config_path']`,
    DCOMP-2). `neue_matrix` ist die editierte Matrix aus dem Editor; `palette`
    das palette-Modul; `geladener_stand` der frisch geladene wetter.json-Inhalt
    (dict) — er trägt Ort/Schwellen/Hinweise read-only weiter.

    Bei ungültiger Matrix → ValidierungsFehler, `wetter.json` byte-unverändert
    (es wird gar nicht erst geschrieben). Bei Schreibfehler → StoreError. Sonst:
    der neue Stand liegt atomar auf `config_path`, sichtbar per DCOMP-2 ohne
    Restart.
    """
    neuer_stand = baue_neuen_stand(geladener_stand, neue_matrix, palette)
    _schreibe_atomar(config_path, neuer_stand)
