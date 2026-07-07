"""Pairing-Cookie nachschicken — frischer Pairing-Link für ein BESTEHENDES
Gerät (Refs #1380, Nic-Setzung 2026-07-07).

GAA-3.8 postet den Pairing-Link EINMALIG direkt nach der Geräte-Anlage. Der
Link gilt 15 Minuten — läuft er ab, bevor Eltern ihn am Zielgerät öffnen,
braucht das Gerät einen NEUEN Link. `geraet-anlegen.md` GAA-3.8 hatte das
als „eigene Eltern-Chat-Aufgabe" (V2-Aufstockung) vorgemerkt; das ist diese
Funktion.

Der Kern ist trigger-agnostisch (E-GAA-1-Geist) und rein: `finde_geraet`
sucht ein Gerät über die HTTP-Liste der Geraete-Komponente (DCOMP-1, kein
`import geraete`), `baue_pairing_link` signiert den Token und baut den Link
auf die **Funnel-FQDN** (PWA, LE-Cert) — Familien-Geräte brauchen so kein
Zertifikat, nur den Cookie (auth.md AUTH-2). Der Master-ID-Gate und die
DM-Zustellung leben in der aufrufenden Aufgabe (`cookie_nachschicken_task`).

Token-Mechanik identisch zu GAA-3.8 (`_poste_pairing_link`): HMAC-SHA256 mit
dem Bot-Token als Sign-Key, kodiert die `display_id`, 15 Minuten gültig
(`tools.initdata.session_cookie`, auth.md AUTH-2.a).
"""

from tools.initdata import session_cookie


def finde_geraet(client, name):
    """Sucht ein Gerät über `client.liste()` anhand des Anzeigenamens.

    Match-Regel (Fuzzy, tolerant): case-insensitive; zuerst exakter
    Namensgleichklang, sonst der erste Substring-Treffer über `name`. So
    trifft „schick nochmal cookies für Paula" das Gerät „Tablet Paula" und
    ebenso „Paula". Liefert das Geräte-Dict (Felder u. a. `id`, `name`,
    `typ`) oder `None`, wenn nichts passt.

    Hebt keine Fehler ab — ein `GeraeteClientError` aus `client.liste()`
    propagiert an den Aufrufer, der daraus die Bot-Nachricht formt.
    """
    ziel = (name or "").strip().lower()
    if not ziel:
        return None
    geraete = client.liste()
    # 1) exakter Namensgleichklang (case-insensitive) hat Vorrang.
    for g in geraete:
        if str(g.get("name", "")).strip().lower() == ziel:
            return g
    # 2) erster Substring-Treffer.
    for g in geraete:
        if ziel in str(g.get("name", "")).strip().lower():
            return g
    return None


def baue_pairing_link(display_id, bot_token, origin):
    """Signiert einen 15-Minuten-Pairing-Token und baut den Pairing-Link.

    `origin` ist die Funnel-FQDN (auth.md AUTH-2: PWA + `/auth/pair` auf
    derselben Origin, LE-Cert). Ergebnis: `<origin>/auth/pair?token=<X>`.
    """
    token = session_cookie.sign_pairing(display_id, bot_token)
    return "%s/auth/pair?token=%s" % (origin.rstrip("/"), token)
