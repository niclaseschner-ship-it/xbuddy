"""Einkauf hinzufügen — specs/platform/einkauf-hinzufuegen.md (EIN-1 … EIN-8).

Aufrufbare, trigger-agnostische Funktion (EIN-1, E-EIN-2-Muster): nimmt
einen Eltern-Text entgegen, zerlegt ihn in Items (EIN-3), löst für jedes
Item Kategorie + ARASAAC-Piktogramm auf (EIN-4), schreibt sie über die
Essens-Buddy-Schnittstelle als klasse=einkauf, quelle=eltern (EIN-5) und
gibt eine kompakte Bot-Antwort zurück (EIN-6).

**Direkt-Modus (E-EIN-1):** kein propose→confirm. Items werden sofort
geschrieben.

**Eingang:**
  - `text`          — Eltern-Eingabe, z. B. "Brot, Milch und Joghurt".
  - `from_user_id`  — Telegram-User-ID des Aufrufers (Berechtigung EIN-2).
  - `essen_client`  — EssenClient-Instanz (CLIENT-1-Naht).
  - `icon_client`   — IconClient-Instanz (ICONS-7, EIN-4).
  - `is_member_fn`  — Callable `(user_id) -> bool` (EIN-2, EC-2).
  - `katalog`       — optional; Liste von Katalog-Items mit {label, bild_ref,
                      item_id, kategorie} für Katalog-Match (EIN-4 Schritt 1).
                      Wenn None, wird kein Katalog-Match gemacht (Test-Naht).

**Ausgang:** User-tauglicher Antwort-Text als String (EIN-6, EC-29).

RAT-16: Adapter-Disziplin — diese Datei enthält kein Telegram-Vokabular.
Alles Telegram-Spezifische (Inline-Buttons, Tap-Handler) liegt im Adapter
(_task.py).
"""

import logging
import re

from skills._errors import BerechtigungError
from skills.essen_client import FEHLER_DUPLIKAT, FEHLER_GRENZE, EssenClientError

logger = logging.getLogger(__name__)

# ============================================================
#  EIN-3: Item-Zerlegung
# ============================================================

# Lead-Phrasen: case-insensitiv vom Anfang strippen (EIN-3 / EIN-4).
_LEAD_PHRASEN = [
    "auch noch",
    "und auch",
    "dann noch",
    "außerdem",
    "ausserdem",
    "bitte",
]

# EIN-3: max 50 Items pro Aufruf.
MAX_ITEMS = 50

# EIN-3: Trennzeichen — Komma, Semikolon, Zeilenumbruch, " und ".
_TRENN_RE = re.compile(r"[,;\n]|\s+und\s+")

# EIN-4: ARASAAC-Default-Icon (Einkaufswagen).
DEFAULT_BILD_REF = "5948"
DEFAULT_KATEGORIE = "sonstiges"

# EIN-4: Plural-Suffix-Stripping (V1, einfache Suffixe).
_PLURAL_SUFFIXE = ["-innen", "innen", "-en", "nen", "-er", "er",
                   "-n", "n", "-s", "s", "-e", "e"]


def _strip_lead(text):
    """EIN-3/EIN-4: Lead-Phrase vom Anfang des Textes entfernen.

    Versucht case-insensitiv, eine der _LEAD_PHRASEN am Textanfang zu
    entfernen. Auch "bitte" am Ende wird entfernt.
    """
    t = text.strip()
    lower = t.lower()
    for phrase in _LEAD_PHRASEN:
        if lower.startswith(phrase):
            t = t[len(phrase):].strip()
            break
    # "bitte" am Ende
    if t.lower().endswith("bitte"):
        t = t[:-len("bitte")].strip()
    return t


def zerlege_items(text):
    """EIN-3: Zerlegt den Eltern-Text in eine Liste von bereinigten Item-Strings.

    Trennzeichen: Komma, Semikolon, Zeilenumbruch, ' und ' (mit Whitespace).
    Lead-Phrasen werden am Anfang des gesamten Textes entfernt (einmalig).
    Leere Items (doppeltes Komma etc.) werden verworfen.

    Gibt eine Liste von Strings zurück; oder eine leere Liste, wenn der Text
    nach Bereinigung nichts enthält.
    """
    # Lead-Phrasen einmalig vom Anfang entfernen.
    text = _strip_lead(text.strip() if text else "")
    if not text:
        return []
    teile = _TRENN_RE.split(text)
    items = []
    for teil in teile:
        s = teil.strip()
        if s:
            items.append(s)
    return items


def _lemmatisiere(label):
    """EIN-4: Versucht Pluralform zu lemmatisieren via Suffix-Stripping (V1).

    Probiert die gängigen Plural-Suffixe (absteigend nach Länge) und gibt die
    Stammform zurück, wenn ein Suffix gefunden wird. Sonst das Original.
    """
    low = label.lower()
    # Absteigend nach Länge — längere Suffixe zuerst.
    for suf in sorted(_PLURAL_SUFFIXE, key=len, reverse=True):
        if low.endswith(suf) and len(low) > len(suf) + 2:
            return low[: -len(suf)]
    return low


def _katalog_match(label, katalog):
    """EIN-4 Schritt 1: Katalog-Match, case-insensitiv + Pluralformversuch.

    `katalog` ist eine Liste von Dicts mit {label, bild_ref, item_id, kategorie}.
    Liefert das erste treffende Katalog-Item-Dict oder None.
    """
    if not katalog:
        return None
    low = label.lower()
    lemma = _lemmatisiere(label)
    for eintrag in katalog:
        kat_label = (eintrag.get("label") or "").lower()
        if kat_label in (low, lemma):
            return eintrag
        # Auch den Lemma des Katalog-Labels versuchen.
        if _lemmatisiere(eintrag.get("label") or "") == lemma:
            return eintrag
    return None


def _icons7_match(label, icon_client):
    """EIN-4 Schritt 2: ICONS-7 Fallback.

    Gibt die erste ARASAAC-ID als String zurück oder None wenn kein Treffer.
    IconClientError → None (Skill fällt geräuschlos auf Default).
    """
    try:
        kandidaten = icon_client.suche(label, max_treffer=1)
    except Exception:
        logger.debug("einkauf_hinzufuegen: ICONS-7 nicht erreichbar für %r", label)
        return None
    if kandidaten:
        return str(kandidaten[0].get("id") or "")
    return None


def _canonical_label(label):
    """EIN-5: canonical-Label — Erst-Buchstabe groß, Rest unverändert."""
    if not label:
        return label
    return label[0].upper() + label[1:]


def _match_item(label, katalog, icon_client):
    """EIN-4: Auto-Match für ein einzelnes Item.

    Reihenfolge:
      1. Katalog-Match (label case-insensitiv + Pluralform-Versuch).
      2. ICONS-7-Fallback.
      3. Default: bild_ref=5948, item_id='frei:<lower>', kategorie='sonstiges'.

    Liefert (canonical_label, bild_ref, item_id, kategorie).
    """
    # Schritt 1: Katalog
    treffer = _katalog_match(label, katalog)
    if treffer:
        canonical = treffer.get("label") or _canonical_label(label)
        return (
            canonical,
            str(treffer.get("bild_ref") or DEFAULT_BILD_REF),
            str(treffer.get("item_id") or ("frei:" + label.lower())),
            treffer.get("kategorie") or DEFAULT_KATEGORIE,
        )

    # Schritt 2: ICONS-7
    icon_id = _icons7_match(label, icon_client)
    if icon_id:
        return (
            _canonical_label(label),
            icon_id,
            "frei:" + label.lower(),
            DEFAULT_KATEGORIE,
        )

    # Schritt 3: Default
    return (
        _canonical_label(label),
        DEFAULT_BILD_REF,
        "frei:" + label.lower(),
        DEFAULT_KATEGORIE,
    )


# ============================================================
#  EIN-6: Antwort-Format
# ============================================================

def _kuerze(label, max_len=30):
    """Kürzt ein Label für die Antwort auf max_len Zeichen."""
    if len(label) > max_len:
        return label[:max_len - 1] + "…"
    return label


def _baue_antwort(hinzugefuegt, uebersprungen, grenze_halt, offen_n):
    """EIN-6: baut den Bot-Antwort-Text.

    `hinzugefuegt` — Liste von Labels, die angelegt wurden.
    `uebersprungen` — Liste von Labels, die schon offen waren (Duplikat-Skip).
    `grenze_halt`   — (offen_jetzt, grenze) oder None wenn kein Grenz-Halt.
    `offen_n`       — Gesamtzahl offener Items nach der Operation (int).
    """
    # Sonderfall: alles geskippt, nichts neu
    if not hinzugefuegt and uebersprungen:
        labels = ", ".join(_kuerze(lbl) for lbl in uebersprungen)
        return "Die %s %s schon offen auf der Liste — %d offen." % (
            labels,
            "sind" if len(uebersprungen) > 1 else "ist",
            offen_n,
        )

    # Normaler Antwort-Prefix (Standardfall + Grenze-Halt)
    n = len(hinzugefuegt)
    if n == 0:
        prefix = ""
    elif n <= 3:
        labels_str = ", ".join(_kuerze(lbl) for lbl in hinzugefuegt)
        prefix = "🛒 %s dazu — %d offen." % (labels_str, offen_n)
    else:
        labels_str = ", ".join(_kuerze(lbl) for lbl in hinzugefuegt)
        prefix = "🛒 %d Items dazu — %s. %d offen." % (n, labels_str, offen_n)

    zeilen = []
    if prefix:
        zeilen.append(prefix)

    # EC-10 A2-Quittungs-Wort-Pflicht: Undo-Hinweis mit Wort `falsch` (EC-10 A2, #938).
    # #1843: Die Zeile muss den Effekt NENNEN, nicht nur das Wort — sonst raten
    # Eltern, was `falsch` bewirkt. Der Wortlaut ist frei (EC-10 A2 laesst dem
    # Skill die Stimme), verbindlich ist der Inhalt. Hier konkret: die Items
    # gehen wieder von der Liste runter.
    #
    # Diese Zeile geht WOERTLICH raus: die Modell-Anweisung reicht jede Zeile mit
    # `falsch` unveraendert an die Familie durch, es glaettet sie also niemand.
    if hinzugefuegt:
        zeilen.append(
            "Wenn das ein Missverständnis war, sag einfach `falsch` — "
            "dann nehme ich %s wieder von der Liste."
            % ("das" if len(hinzugefuegt) == 1 else "sie")
        )

    # Skip-Zeile
    if uebersprungen:
        skip_labels = ", ".join(_kuerze(lbl) for lbl in uebersprungen)
        zeilen.append("(%d schon drauf: %s)" % (len(uebersprungen), skip_labels))

    # Grenze-Halt-Zeile
    if grenze_halt:
        offen_jetzt = grenze_halt[0]
        grenze = grenze_halt[1]
        nicht_n = grenze_halt[2] if len(grenze_halt) > 2 else 0
        zeilen.append(
            "⚠️ %d Items konnten nicht: Liste hat %s/%s, erst aufräumen." % (
                nicht_n, offen_jetzt, grenze))

    return "\n".join(zeilen)


# ============================================================
#  Haupt-Funktion
# ============================================================

def einkauf_hinzufuegen(text, from_user_id, essen_client, icon_client,
                        is_member_fn, katalog=None, receipt_store=None,
                        chat_id=None):
    """Einkauf hinzufügen — aufrufbare Funktion (EIN-1, E-EIN-2, EC-29).

    Trigger-agnostisch: nimmt Eltern-Text und schreibt Items zur
    Einkaufsliste (klasse=einkauf, quelle=eltern).

    Direkt-Modus (E-EIN-1): kein propose→confirm.

    `receipt_store` — A2ReceiptStore-Instanz (EC-10 A2-Receipt, #841) oder None.
    `chat_id`       — Telegram-Chat-ID für den Receipt; None → kein Receipt.

    Wirft `BerechtigungError` bei EIN-2-Verletzung.
    Gibt User-tauglichen Antwort-Text als String zurück (EC-29).
    """
    # EIN-2: Berechtigung
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("einkauf_hinzufuegen: User %s nicht berechtigt", from_user_id)
        raise BerechtigungError("Das geht nur für Eltern.")

    # EIN-7: leere Eingabe
    if not text or not str(text).strip():
        return ("Was soll auf die Liste? Beispiel: `Brot, Milch`.")

    # EIN-3: Zerlegung
    items = zerlege_items(text)
    if not items:
        return ("Was soll auf die Liste? Beispiel: `Brot, Milch`.")

    # EIN-3: >50 Items → Ablehnung
    if len(items) > MAX_ITEMS:
        return (
            "Mehr als %d Items in einem Rutsch ist viel — "
            "schick mir bitte in zwei Nachrichten." % MAX_ITEMS
        )

    # EIN-4 + EIN-5: pro Item match + POST
    hinzugefuegt = []    # Labels erfolgreich angelegt
    uebersprungen = []   # Labels als Duplikat übersprungen
    grenze_halt = None   # (offen_jetzt, grenze, nicht_konnten_n) oder None
    grenze_items = []    # Labels die wegen Grenze nicht angelegt werden konnten
    # EC-10 A2-Receipt (#841): (resource_id, inverse_call)-Tupel pro erfolgreichem Item.
    receipt_items = []   # gesammelt, am Ende atomar geschrieben

    for item_text in items:
        if grenze_halt is not None:
            # Grenze bereits erreicht — restliche Items sammeln
            grenze_items.append(item_text)
            continue

        canonical, bild_ref, item_id, kategorie = _match_item(
            item_text, katalog, icon_client)

        try:
            resp = essen_client.hinzufuegen_einkauf(
                label=canonical,
                bild_ref=bild_ref,
                item_id=item_id,
                kategorie=kategorie,
            )
            server_id = resp["id"]
            hinzugefuegt.append(canonical)
            # EC-10 A2-Receipt (#938): server_id aus POST-Antwort verwenden,
            # NICHT die clientseitige item_id. DELETE filtert per Server-ID
            # (essen/main.py ESSEN-17). inverse_call in HTTP-Form (spec Z. 533-535).
            receipt_items.append(
                (str(server_id),
                 'essen DELETE /api/v1/essen/wuensche/%s' % server_id))
            logger.info(
                "einkauf_hinzufuegen: angelegt %r (item_id=%s, server_id=%s, kat=%s)",
                canonical, item_id, server_id, kategorie)

        except EssenClientError as e:
            if e.marker == FEHLER_DUPLIKAT:
                # EIN-5: Duplikat geräuschlos überspringen
                logger.info("einkauf_hinzufuegen: Duplikat %r — übersprungen",
                            canonical)
                uebersprungen.append(canonical)

            elif e.marker == FEHLER_GRENZE:
                # EIN-5: Listen-Grenze — restliche Items abbrechen
                grenze_daten = getattr(e, "grenze_daten", {}) or {}
                offen_jetzt = grenze_daten.get("offen_jetzt", "?")
                grenze = grenze_daten.get("grenze", "?")
                grenze_items.append(canonical)
                grenze_halt = (offen_jetzt, grenze, len(grenze_items))
                logger.info(
                    "einkauf_hinzufuegen: Listen-Grenze — offen=%s, grenze=%s",
                    offen_jetzt, grenze)

            else:
                # EIN-7: sonstige Fehler → Klartext-Meldung
                logger.warning("einkauf_hinzufuegen: Fehler beim POST: %s", e)
                if "HTTP 5" in str(e):
                    return ("Die Liste-API meldet einen Fehler. "
                            "Versuch's gleich nochmal.")
                if not e.marker or e.marker not in (FEHLER_DUPLIKAT, FEHLER_GRENZE):
                    return ("Die Liste ist gerade nicht erreichbar — "
                            "versuch's gleich nochmal.")
                return "Das hat leider nicht geklappt — bitte versuch's gleich nochmal."

    # EC-10 A2-Receipt (#841): alle erfolgreich angelegten Items atomar receipten.
    # insert_many() siegelt Vorgänger-Receipts desselben chat_id und schreibt
    # alle neuen Einträge mit identischer committed_at (spec Z. 543-548).
    if receipt_items and receipt_store is not None and chat_id is not None:
        try:
            receipt_store.insert_many(
                "einkauf_hinzufuegen", chat_id, receipt_items)
            logger.debug(
                "einkauf_hinzufuegen: %d A2-Receipts geschrieben (chat_id=%s)",
                len(receipt_items), chat_id)
        except Exception as e:
            # Receipt-Fehler bricht die bereits erfolgreichen Schreibakte
            # NICHT ab (ehrliche Grenze EC-7: Items sind in der Liste).
            logger.warning(
                "einkauf_hinzufuegen: A2-Receipt-Insert fehlgeschlagen: %s", e)

    # EIN-6: Antwort bauen
    # offen_n: wir haben keine direkte Counter-API; wir approximieren
    # anhand der tatsächlich angelegten Items.
    # Wenn Grenze erreicht: offen_jetzt aus Grenze-Antwort nehmen.
    # Einfacher Schätzwert — genaue Zahl steht im essen_client nicht zur
    # Verfügung ohne Extra-GET; V1 akzeptiert das (ehrliche Grenze EC-7).
    offen_n = grenze_halt[0] if grenze_halt is not None else len(hinzugefuegt)

    if grenze_halt is not None:
        # Update: grenze_halt-Tuple muss nicht_n korrekt tragen
        grenze_halt = (grenze_halt[0], grenze_halt[1], len(grenze_items))

    return _baue_antwort(
        hinzugefuegt=hinzugefuegt,
        uebersprungen=uebersprungen,
        grenze_halt=grenze_halt,
        offen_n=offen_n,
    )
