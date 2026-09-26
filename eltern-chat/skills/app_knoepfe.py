"""App-Knöpfe — der EINE Knopf-Baustein aller Chat-Skills, die eine App öffnen (#1964).

specs/platform/eltern-chat.md EC-46. Nic 26.09.2026: jede App ist im Chat
erfragbar, und zwar **einheitlich**. Darum baut kein Skill seine App-Knöpfe
selbst — `app_oeffnen`, `einkauf_zeigen` und `seiten_uebersicht` holen sie hier.

Eine App bekommt immer dieselbe Knopfreihe (Reihenfolge fest):

  1. der Mini-App-Knopf (`web_app_url`) — öffnet die App im Telegram-Fenster;
  2. „🌐 Im Browser öffnen" (`url`) — Telegram öffnet url-Knöpfe im externen
     Browser; dort sieht man die Adresse und kann die Seite installieren (#1953);
  3. „⬇ Installieren" (`url` + `?installieren=1`) — **nur** bei einer PWA
     (`views.json` `typ: "pwa"`, Inventar-Feld `pwa`). Der Parameter lässt
     das gemeinsame Install-Skript der PWA-Mäntel den Install-Hinweis zeigen
     (#1955, `seiten/static/app-installieren.js`).

Der Link ist kein Credential: ein noch nicht angemeldeter Browser läuft über
den Pairing-Weg (`auth.md` AUTH-2.a).

RAT-16: kein Telegram-Vokabular — die Knöpfe sind das vendor-neutrale
`presentation.inline_buttons`-Format (TASK-10c Form (b)), das
`tasks.render_form_b` übersetzt.
"""

BROWSER_LABEL = "🌐 Im Browser öffnen"
INSTALLIEREN_LABEL = "⬇ Installieren"
INSTALLIEREN_PARAMETER = "installieren=1"


def absolute_url(basis_url, pfad):
    """Setzt Basis-Origin und Registry-Pfad zu einer absoluten Adresse zusammen.

    Ein Pfad, der schon absolut ist (`http…`), bleibt unverändert. Doppelte
    Schrägstriche an der Naht werden vermieden.
    """
    pfad = pfad or ""
    if pfad.startswith(("https://", "http://")):
        return pfad
    return (basis_url or "").rstrip("/") + "/" + pfad.lstrip("/")


def installier_url(url):
    """Hängt `installieren=1` an — mit `&`, wenn die Adresse schon eine Query hat."""
    trenner = "&" if "?" in url else "?"
    return url + trenner + INSTALLIEREN_PARAMETER


def app_knoepfe(url, label, pwa=False, name=None):
    """Die Knopfreihe EINER App (Liste für `presentation.inline_buttons`).

    `url`   — absolute Adresse der App.
    `label` — Beschriftung des Mini-App-Knopfs.
    `pwa`   — True: dritter Knopf „⬇ Installieren".
    `name`  — nur wenn mehrere Apps in EINER Nachricht stehen: dann tragen
              Browser- und Installier-Knopf den App-Namen, damit man sie
              auseinanderhält („🌐 Wetter heute im Browser").
    """
    if name:
        browser = "🌐 %s im Browser" % name
        installieren = "⬇ %s installieren" % name
    else:
        browser = BROWSER_LABEL
        installieren = INSTALLIEREN_LABEL
    knoepfe = [
        {"label": label, "web_app_url": url},
        {"label": browser, "url": url},
    ]
    if pwa:
        knoepfe.append({"label": installieren, "url": installier_url(url)})
    return knoepfe
