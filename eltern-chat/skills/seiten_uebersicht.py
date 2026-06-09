"""Seiten-Übersicht — specs/platform/seiten-registry.md (SREG-5/SREG-5b/SREG-7).

Aufrufbare, trigger-agnostische Funktion (EC-9-Muster): liefert dem
Aufrufer einen Link auf die gerenderte Übersichts-Seite (SREG-12) plus
eine Sub-Frage ob der Elternteil einen direkten View-Link will.

**Default-Pfad (SREG-5):**
  Jede Frage-Familie nach Seiten/Links → EIN Link auf
  `display_url_origin_heim + /api/v1/seiten/uebersicht` + Sub-Frage.
  Der Skill ruft GET /api/v1/seiten NICHT selbst auf (SREG-5-Pivot).

**Opt-in-Pfad (SREG-5b) — Zweistufiges KI-Matching (Weg 2, #488):**
  Runde 1 (`aktion="inventar"`): Skill ruft seiten_client.inventar() EINMAL,
  gibt das Inventar als kompaktes Tool-Result zurück (KEIN Bot-Post). Das LLM
  wählt die passende View anhand label/key/synonyme/zeigt und ruft die Task
  erneut mit dem exakten label oder key als `suchbegriff` auf.

  Runde 2 (`aktion="match"`): Equality-Lookup auf label ODER key (SREG-5b).
  Eindeutiger Treffer → direkte URL als Tool-Result. Kein Treffer → klare
  Fehler-Antwort (kein Default-Loop). Substring-basiertes matche_view()
  bleibt für aktion=inventar (Runde 1) reserviert.

  Dieser Zwei-Runden-Ansatz ersetzt lokales Substring-Matching gegen vage
  Suchbegriffe: das LLM ist der einzige Ranker (SREG-5b: kein lokales
  Substring-/Wortlisten-Match auf natürlichsprachliche Begriffe, #488).
  Equality bei aktion=match verhindert Präfix-Geschwister-Mehrdeutigkeit
  (T549-Fix2: „Panel paulas-panel-01" trifft nicht mehr „Panel paulas-panel-01
  bearbeiten" — deterministisches Lookup auf diszipliniertem Wert, SREG-5b).

Eingang: optionaler `suchbegriff` (für Opt-in-Pfad), optionale `aktion`.
  Ohne Suchbegriff/aktion → Default-Pfad.
  Suchbegriff + aktion="inventar" → Runde 1: Inventar als Tool-Result.
  Suchbegriff + aktion="match"   → Runde 2: Equality-Lookup label/key.

**Ergebnis (EC-29):**
  Die Funktion returnt in jedem Pfad einen User-tauglichen Antwort-Text
  als String (Tool-Result). Das LLM postet — die Funktion sendet selbst
  keine Telegram-Nachricht (EC-29).
  Berechtigungs-Bruch (SREG-6): wirft `BerechtigungError` — der Agent-Loop
  schreibt den Fehler-Tool-Result-Block (agent.py Fehlerpfad).
"""

import logging

from skills.seiten_client import SeitenClientError

logger = logging.getLogger(__name__)


class BerechtigungError(Exception):
    """Aufrufer ist kein autorisiertes Familienmitglied (SREG-6, EC-29).

    Der Agent-Loop fängt diese Exception und schreibt einen
    Fehler-Tool-Result-Block; das LLM schweigt in der Antwort.
    """


# Ergebnis-Signale der Funktion (SREG-5/SREG-5b) — nur noch intern/compat.
SIGNAL_DEFAULT_GESENDET  = "default_gesendet"
SIGNAL_INVENTAR_GELIEFERT = "inventar_geliefert"  # Runde 1 Opt-in: Inventar an LLM, kein Bot-Post.
SIGNAL_DIREKT_GESENDET   = "direkt_gesendet"
SIGNAL_MEHRDEUTIG        = "mehrdeutig"
SIGNAL_ABGELEHNT         = "abgelehnt"
SIGNAL_NICHT_ERREICHBAR  = "nicht_erreichbar"

# Aktions-Werte für den Opt-in-Pfad (SREG-5b Weg 2, #488).
AKTION_INVENTAR = "inventar"   # Runde 1: Inventar an LLM zurückgeben.
AKTION_MATCH    = "match"      # Runde 2: Substring-Match + Bot-Post.

# SREG-12: Pfad der gerenderten Übersichts-Seite (stabil per URL-8, 2026-06-08).
PFAD_UEBERSICHT = "/api/v1/seiten/uebersicht"

# SREG-5b-Mehrdeutigkeit-Heuristik: Wenn der zweitbeste Treffer den
# Suchbegriff ebenfalls direkt in label, synonyme oder zeigt enthält,
# gilt das Match als mehrdeutig → EC-22-Rückfrage statt Direkt-Antwort.
# Konservativ: lieber Rückfrage als falsche Direkt-Antwort (SREG-5b).
_MEHRDEUTIGKEIT_MINDEST_TREFFER = 2


def baue_uebersichts_url(display_url_origin_heim):
    """Baut die Übersichts-URL aus Origin + stabilem Pfad (SREG-5/SREG-12).

    Wirft `ValueError` wenn `display_url_origin_heim` leer/None ist —
    V1-Pflicht: ohne Origin kann kein tippbarer Link geliefert werden
    (SREG-7: display_url_origin_heim muss gesetzt sein).
    """
    origin = (display_url_origin_heim or "").strip().rstrip("/")
    if not origin:
        raise ValueError(
            "display_url_origin_heim ist nicht gesetzt — "
            "SREG-7 V1-Pflicht: Heim-Origin muss konfiguriert sein")
    return origin + PFAD_UEBERSICHT


def formatiere_default_antwort(display_url_origin_heim):
    """Formatiert die Default-Antwort (SREG-5): Link + Sub-Frage.

    Liefert den vollständigen Bot-Text für den Default-Pfad. Wirft
    `ValueError` wenn `display_url_origin_heim` leer/None (SREG-7).
    """
    url = baue_uebersichts_url(display_url_origin_heim)
    return (
        "Hier ist die Übersicht aller Seiten: %s\n\n"
        "Soll ich dir die passende Seite stattdessen direkt hier schicken?"
    ) % url


def formatiere_direkt_url(display_url_origin_heim, pfad, varianten_query=None):
    """Baut die direkte View-URL für den Opt-in-Pfad (SREG-5b/SREG-7).

    `pfad` ist der Pfad-Eintrag aus dem Inventar (z. B. `/display/wetter/regeln`).
    `varianten_query` ist ein optionales flaches Objekt (Dict) mit Query-Parametern
    aus einem Varianten-Eintrag (SREG-1).
    """
    origin = (display_url_origin_heim or "").strip().rstrip("/")
    url = origin + pfad
    if varianten_query:
        # flaches Dict → query-String
        params = "&".join(
            "%s=%s" % (k, v)
            for k, v in varianten_query.items()
        )
        url = "%s?%s" % (url, params)
    return url


def _enthalt_suchbegriff(eintrag, q):
    """Prüft ob ein Inventar-Eintrag den Suchbegriff direkt enthält.

    Sucht in label, synonyme und zeigt (case-insensitiv). Pfad und typ
    werden NICHT gesucht — nur die inhaltsbeschreibenden Felder (SREG-5b).
    """
    label = str(eintrag.get("label") or "").lower()
    synonyme_text = " ".join(
        str(s) for s in (eintrag.get("synonyme") or [])
    ).lower()
    zeigt = str(eintrag.get("zeigt") or "").lower()
    return q in label or q in synonyme_text or q in zeigt


def formatiere_inventar_tool_result(eintraege):
    """Kompaktes Tool-Result-Format für das Inventar (SREG-5b Runde 1, #488).

    Pro Eintrag eine Zeile: `key | label | synonyme | zeigt`
    (nur die inhaltsbeschreibenden Felder — kein pfad/typ).
    Das LLM wählt anhand dieser Liste die passende View und ruft die Task
    erneut mit `aktion="match"` und dem exakten label oder key auf.

    Liefert die Inventar-Liste als formatierten String (Tool-Result).
    Leeres Inventar → kurze Hinweis-Meldung.
    """
    if not eintraege:
        return "Seiten-Inventar: (leer — keine aufrufbaren Views registriert)"
    zeilen = ["Seiten-Inventar (%d Eintraege) — bitte passenden label/key auswaehlen:" % len(eintraege)]
    for e in eintraege:
        if not isinstance(e, dict):
            continue
        key      = str(e.get("key")     or "")
        label    = str(e.get("label")   or "")
        synonyme = ", ".join(str(s) for s in (e.get("synonyme") or []))
        zeigt    = str(e.get("zeigt")   or "")
        zeilen.append("  key=%s | label=%s | synonyme=[%s] | zeigt=%s"
                      % (key, label, synonyme, zeigt))
    return "\n".join(zeilen)


def formatiere_mehrdeutigkeit_tool_result(treffer):
    """Strukturiertes Tool-Result für das LLM bei EC-22-Mehrdeutigkeit (#549).

    Listet alle Kandidaten mit label, key und pfad auf — so kann das LLM
    nach der Disambiguation-Antwort des Elternteils den passenden Kandidaten
    per exaktem label identifizieren und die Task mit aktion="match" aufrufen.

    Format pro Kandidat: `N. label: "..."; key: ...; pfad: ...`
    Plus Auflösungs-Anweisung: LLM soll beim nächsten User-Turn mit
    aktion="match" + dem exakten label aufrufen, NICHT ohne suchbegriff
    (das würde den Default-Fallback auslösen statt des gewünschten Views).
    """
    zeilen = [
        "Ich habe eine Rückfrage gestellt — der Eltern muss zwischen diesen "
        "Views wählen:",
    ]
    for i, e in enumerate(treffer, 1):
        label = str(e.get("label") or e.get("pfad") or "?")
        key   = str(e.get("key")   or "")
        pfad  = str(e.get("pfad")  or "")
        zeilen.append('%d. label: "%s"; key: %s; pfad: %s' % (i, label, key, pfad))
    zeilen.append("")
    zeilen.append(
        "Wenn der Eltern in der nächsten Antwort wählt (z.B. \"Die Ansicht\", "
        "\"Die zweite\", \"den Editor\"), rufe diese Task erneut auf mit "
        "aktion=match + dem exakten label aus dieser Liste oder dem key aus "
        "dieser Liste — Equality wird geprüft, kein Substring-Match. "
        "Der key ist eindeutig, falls Labels Präfix-Geschwister sind. "
        "NICHT ohne suchbegriff (das löst Default-Fallback aus).")
    return "\n".join(zeilen)


def matche_view(eintraege, suchbegriff):
    """Pro-View-Matching für den Opt-in-Pfad (SREG-5b).

    Filtert Inventar-Einträge nach dem Suchbegriff gegen label/synonyme/zeigt.
    Liefert `(treffer_liste, mehrdeutig)`:
      - `treffer_liste`: alle matchenden Einträge
      - `mehrdeutig`: True, wenn mindestens zwei Treffer den Begriff direkt
        tragen (SREG-5b-Heuristik — konservativ: lieber Rückfrage).
    """
    if not eintraege or not suchbegriff:
        return [], False

    q = str(suchbegriff).strip().lower()
    if not q:
        return [], False

    treffer = [e for e in eintraege if isinstance(e, dict) and _enthalt_suchbegriff(e, q)]

    # Mehrdeutigkeit: mind. 2 Treffer im Direkt-Match → EC-22-Rückfrage.
    mehrdeutig = len(treffer) >= _MEHRDEUTIGKEIT_MINDEST_TREFFER
    return treffer, mehrdeutig


def matche_view_exakt(eintraege, suchbegriff):
    """Equality-Lookup für aktion=match (SREG-5b/T549-Fix2).

    Prüft `eintrag["label"] == suchbegriff` ODER `eintrag["key"] == suchbegriff`
    (case-sensitiv, exakte Übereinstimmung). Erster Treffer gewinnt — label und
    key sind eindeutige Identifier, kein Substring-Match (verhindert
    Präfix-Geschwister-Mehrdeutigkeit bei aktion=match, T549).

    Liefert den ersten passenden Eintrag oder None.
    """
    if not eintraege or not suchbegriff:
        return None
    q = str(suchbegriff).strip()
    if not q:
        return None
    for e in eintraege:
        if not isinstance(e, dict):
            continue
        if str(e.get("label") or "") == q or str(e.get("key") or "") == q:
            return e
    return None


def formatiere_ec22_rueckfrage(treffer):
    """Formatiert die EC-22-Rückfrage bei mehrdeutigen Treffern (SREG-5b/EC-22).

    Listet die ersten Treffer namentlich auf. EC-22: einmal kurz nachfragen,
    dann gezielt liefern.
    """
    # Maximal 4 Optionen benennen, damit die Nachricht kurz bleibt.
    max_optionen = 4
    labels = [
        e.get("label") or e.get("pfad") or "?"
        for e in treffer[:max_optionen]
    ]
    optionen_text = " oder ".join('„%s"' % lb for lb in labels)
    if len(treffer) > max_optionen:
        optionen_text += " (oder eine weitere Seite)"
    return "Meintest du %s?" % optionen_text


# ============================================================
#  Haupt-Funktion
# ============================================================

def seiten_uebersicht(chat_id, from_user_id, suchbegriff,
                      seiten_client, is_member_fn,
                      display_url_origin_heim=None,
                      aktion=None):
    """Seiten-Übersicht — aufrufbare Funktion (SREG-5/SREG-5b/SREG-6, EC-29).

    **Ohne Suchbegriff (Default-Pfad, SREG-5):**
      Returnt EINEN Link auf die Übersichts-Seite + Sub-Frage als Text.
      Ruft GET /api/v1/seiten NICHT auf.

    **Mit Suchbegriff + aktion="inventar" (Opt-in Runde 1, SREG-5b):**
      Ruft seiten_client.inventar() EINMAL.
      Returnt kompaktes Tool-Result (label + key + synonyme + zeigt je View).
      KEIN Bot-Post. Das LLM wählt die passende View und ruft erneut mit
      aktion="match" und dem exakten label/key auf (Weg 2, #488).

    **Mit Suchbegriff + aktion="match" (Opt-in Runde 2, SREG-5b):**
      Equality-Lookup auf label ODER key (case-sensitiv, exakt).
      Treffer → direkte URL als Tool-Result-Text.
      Kein Treffer → klare Fehler-Antwort (kein Default-Loop).

    `chat_id`                  — Zielchat (Gruppe oder Privatchat, nur für Logging).
    `from_user_id`             — Telegram-User-ID des Aufrufers (EC-2).
    `suchbegriff`              — Leer/None → Default-Pfad; gesetzt → Opt-in-Pfad.
    `seiten_client`            — SeitenClient-Instanz (nur im Opt-in-Pfad genutzt).
    `is_member_fn`             — Callable `(user_id) -> bool` (SREG-6/EC-2).
    `display_url_origin_heim`  — Heim-Origin (SREG-7). Pflicht für Default-Pfad.
    `aktion`                   — "inventar" (Runde 1) oder "match" (Runde 2).
                                  Nur im Opt-in-Pfad relevant. None/leer → Default.

    Returnt User-tauglichen Antwort-Text als String (EC-29).
    Wirft `BerechtigungError` bei SREG-6-Verletzung.
    """
    # SREG-6: Berechtigung — EC-2-Mitgliedschaft.
    if chat_id is None or from_user_id is None or not is_member_fn(from_user_id):
        logger.info("seiten_uebersicht: User %s ist kein Familienmitglied oder chat_id fehlt"
                    " — abgelehnt (SREG-6)", from_user_id)
        raise BerechtigungError("Du bist kein Mitglied der Familien-Gruppe.")

    q = str(suchbegriff or "").strip()

    if not q:
        # Default-Pfad (SREG-5): Link + Sub-Frage, kein Registry-Call.
        try:
            antwort = formatiere_default_antwort(display_url_origin_heim)
        except ValueError as e:
            logger.warning("seiten_uebersicht: Origin nicht konfiguriert — %s", e)
            return (
                "Die Seiten-Übersicht ist noch nicht konfiguriert "
                "(display_url_origin_heim fehlt, SREG-7).")
        logger.info("seiten_uebersicht: Default-Pfad an Chat %s", chat_id)
        return antwort

    # Opt-in-Pfad (SREG-5b): Runde 1 oder Runde 2.
    try:
        eintraege = seiten_client.inventar()
    except SeitenClientError as e:
        logger.warning("seiten_uebersicht: Registry nicht erreichbar — %s", e)
        return (
            "Die Seiten-Registry ist gerade nicht erreichbar — "
            "bitte gleich nochmal probieren.")

    # Runde 1 (aktion="inventar"): Inventar als Tool-Result → kein Bot-Post.
    # Das LLM wählt die passende View und ruft mit aktion="match" + exaktem
    # label/key erneut auf (SREG-5b Weg 2, #488; EC-29).
    if str(aktion or "").strip() == AKTION_INVENTAR:
        inventar_text = formatiere_inventar_tool_result(eintraege)
        logger.info("seiten_uebersicht: Inventar an LLM geliefert (%d Eintraege, q=%r)",
                    len(eintraege), q)
        return inventar_text

    # Runde 2 (aktion="match"): Equality-Lookup auf label ODER key
    # (SREG-5b/T549-Fix2). Verhindert Präfix-Geschwister-Mehrdeutigkeit.
    if str(aktion or "").strip() == AKTION_MATCH:
        eintrag = matche_view_exakt(eintraege, q)
        if eintrag is None:
            # Kein Treffer → klare Fehler-Antwort (kein Default-Loop).
            logger.info("seiten_uebersicht: aktion=match kein Treffer (q=%r) in Chat %s",
                        q, chat_id)
            return (
                "Ich habe keinen Eintrag mit dem label oder key \"%s\" gefunden. "
                "Bitte mit aktion=inventar das aktuelle Inventar abrufen und "
                "einen exakten label oder key aus der Liste verwenden." % q)

        # Equality-Treffer → direkte URL als Tool-Result-Text (SREG-5b).
        pfad = eintrag.get("pfad") or ""
        varianten_query = eintrag.get("query") if isinstance(eintrag.get("query"), dict) else None
        try:
            url = formatiere_direkt_url(display_url_origin_heim, pfad, varianten_query)
        except Exception:
            url = pfad
        label = eintrag.get("label") or pfad
        logger.info("seiten_uebersicht: Direkt-URL via Equality (q=%r, pfad=%s) an Chat %s",
                    q, pfad, chat_id)
        return "Hier ist der direkte Link: %s (%s)" % (url, label)

    # Fallback: Substring-Match (aktion=None/unbekannt) — für direkte Anfragen
    # ohne zweistufiges KI-Matching (SREG-5b Legacy-Pfad).
    treffer, mehrdeutig = matche_view(eintraege, q)

    if not treffer:
        # Kein Treffer → Fallback auf Default-Link (SREG-5b: kein stilles Ende).
        try:
            url = baue_uebersichts_url(display_url_origin_heim)
            return (
                "Ich habe keine passende Seite gefunden. "
                "Die vollständige Übersicht: %s" % url)
        except ValueError:
            return "Ich habe keine passende Seite gefunden."

    if mehrdeutig:
        # Mehrere Treffer → EC-22-Rückfrage als Tool-Result (SREG-5b/EC-22/EC-29).
        # Das Tool-Result enthält sowohl die User-taugliche Rückfrage als auch die
        # strukturierte Kandidaten-Liste (EC-29 Tool-Result-Vertrag: Agent-Steuer-Hinweise
        # und User-Text dürfen im selben Tool-Result stehen).
        rueckfrage = formatiere_ec22_rueckfrage(treffer)
        kandidaten_text = formatiere_mehrdeutigkeit_tool_result(treffer)
        logger.info("seiten_uebersicht: EC-22-Rückfrage (%d Treffer, q=%r) an Chat %s",
                    len(treffer), q, chat_id)
        return "%s\n\n%s" % (rueckfrage, kandidaten_text)

    # Eindeutiger Treffer → direkte URL als Tool-Result-Text (SREG-5b).
    eintrag = treffer[0]
    pfad = eintrag.get("pfad") or ""
    # Variant-Query: wenn der Eintrag selbst ein Varianten-Eintrag ist (SREG-1).
    varianten_query = eintrag.get("query") if isinstance(eintrag.get("query"), dict) else None

    try:
        url = formatiere_direkt_url(display_url_origin_heim, pfad, varianten_query)
    except Exception:
        # Defensiv: Origin fehlt → Pfad als Fallback.
        url = pfad

    label = eintrag.get("label") or pfad
    logger.info("seiten_uebersicht: Direkt-URL (q=%r, pfad=%s) an Chat %s",
                q, pfad, chat_id)
    return "Hier ist der direkte Link: %s (%s)" % (url, label)
