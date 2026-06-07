"""Konfigurations-Auflösung — siehe specs/platform/eltern-chat.md EC-15 und
specs/platform/eltern-chat-onboarding.md (Refs #27, #33, #179).

Priorität je Wert: Umgebungsvariable > Konfigurationsdatei > Onboarding-Speicher
> Default. Der Bot-Token kommt ausschließlich aus einer Umgebungsvariablen
(Pflicht). Der Anbieter-API-Key und die Familien-Gruppen-Chat-ID können aus
Umgebungsvariable/Konfiguration ODER aus dem Onboarding-Speicher stammen; fehlt
der Anbieter-Key auf beiden Wegen, läuft die Instanz im Onboarding-Modus
(ONB-1). Geheimnisse landen nie in einer Datei im Repo (CLAUDE.md §8).

Seit #179: die generische Datei+ENV-Auflösung der nicht-geheimen Schema-Werte
übernimmt der gemeinsame `tools.configloader` (CONFIG-1, Konvention
`ELTERNCHAT_<KEY>`). Geheimnisse (Bot-Token, Anbieter-API-Key) und der
Onboarding-Speicher-Lookup (Anbieter-Key, Familien-Gruppen-Chat-ID) bleiben
hier komponentenspezifisch — der Loader rührt Geheimnisse nicht an (CONFIG-3).
"""

import json
import os
import sys

# Repo-Wurzel auf den Importpfad — der Loader liegt unter `tools/`, das
# eltern-chat-Paket ist wegen seines Bindestrichs paketlos und sieht das
# Repo-Root sonst nicht (auch nicht beim Direktstart von main.py über
# systemd). Analog plan/main.py / router/main.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from onboarding_store import KEY_FAMILY_GROUP, KEY_PROVIDER_API_KEY, OnboardingStore

from tools import configloader

# EC-15: nicht-geheime Werte mit ihren Defaults — Schema für den gemeinsamen
# `tools.configloader` (CONFIG-1, #179). Der Loader macht Datei < ENV nach
# Konvention `ELTERNCHAT_<KEY>` (Großbuchstaben des Schema-Schlüssels).
#
# `family_group_chat_id` steht hier mit Default `""`, weil sie im Onboarding-
# Pfad leer bleiben darf (ONB-1/ONB-6). Die *Sperr*-Logik (ENV/Datei sperren,
# Onboarding bindet ohne Sperre) sitzt unten in `resolve` — der Loader liefert
# nur den Wert, nicht die Quelle.
DEFAULTS = {
    "provider":       "claude",     # KI-Anbieter (EC-11)
    "provider_model": "",           # leer → Anbieter-Default des Adapters
    "context_depth":  40,           # Gesprächskontext-Tiefe (EC-6, #312)
    # CAV-3: Pfad zum öffentlichen Root-CA-Zertifikat, das die CA-Verteilung
    # ausliefert. Per-Instanz-Wert; Default = Standard-Ausgabe des CA-Werkzeugs
    # (tools/ca/make-ca.sh, #36). Niemals der CA-Privatschlüssel.
    "ca_pem_path":    "../tools/ca/out/rootCA.pem",
    # FAA-12 / Auftrag #215: Origin der Familien-Komponente, ueber die die
    # FamilieAnlegenTask Personen schreibt (`POST /api/v1/familie/personen`
    # FAM-12) und liest (`GET /api/v1/familie/personen` FAM-7). Per-Instanz-
    # Wert; Default passt zum Pi-Setup (PORT-2 Familie auf 5010).
    "familie_origin_url": "http://127.0.0.1:5010",
    # GAA-5 / Auftrag #215: Origin der Geraete-Komponente, ueber die die
    # GeraetAnlegenTask Geraete schreibt (`POST /api/v1/geraete/` GER-15).
    # Per-Instanz-Wert; Default passt zum Pi-Setup (PORT-2 Geraete auf 5040).
    "geraete_origin_url": "http://127.0.0.1:5040",
    # PAA-5 / #183: Origin der Panel-Registry, über die die PanelAnlegenTask
    # Panel-Instanzen schreibt (`POST /api/v1/panels/` PREG-15). Per-Instanz-
    # Wert; Default passt zum Pi-Setup (PORT-2 Panel-Registry auf 5041).
    "panel_origin_url": "http://127.0.0.1:5041",
    # EC-21 / Auftrag #215: Origin der Plan-Buddy-Reload-Schnittstelle
    # (`POST /api/v1/plan/admin/reload`, #151). Per-Instanz-Wert; Default
    # passt zum Pi-Setup (PORT-2 Plan-Buddy auf 5020).
    "plan_origin_url": "http://127.0.0.1:5020",
    # RZS-6 / #343: Origin des Routine-Buddys, über die die
    # RoutineZeitenSetzenTask die Zeiten schreibt (`PUT /api/v1/routine/config`
    # ROUTINE-14). Per-Instanz-Wert; Default passt zum Pi-Setup
    # (PORT-2 Routine-Buddy auf 5050).
    "routine_origin_url": "http://127.0.0.1:5050",
    # FSE-7 / #393: Origin des Photo-Buddys, über den der FotoSendenTask
    # Medien hochlädt (`POST /api/v1/photo/medien` PHOTO-13) und widerruft
    # (`DELETE /api/v1/photo/medien/<id>` PHOTO-16). Per-Instanz-Wert; Default
    # passt zum Pi-Setup (PORT-2 Photo-Buddy auf 5070). Leer ⇒ Aufgabe NICHT
    # im Katalog (FSE-8 AND-Guard mit family_group_chat_id_getter).
    "photo_origin_url": "http://127.0.0.1:5070",
    # GAA-3.7: HTTPS-Origin, unter der die ausgelieferten Display-URLs
    # erreichbar sind (z. B. "https://xbuddy-hub.local:8443"). Per-Instanz-
    # Wert. Leer (Default) → Bot gibt nur den Pfad `/display/<id>` aus —
    # ausreichend für Tests/CI, für Familien-Anlage muss der Origin gesetzt
    # sein, damit das ausgeteilte Stück direkt aufs Tablet getippt werden
    # kann.
    "display_url_origin": "",
    # ONB-6 / EC-15: Familien-Gruppen-Chat-ID. Default leer = Onboarding-
    # Bindung. Über ENV oder Datei gesetzt → gesperrt (Vorrang vor
    # Onboarding-Bindung) — die Sperr-Logik sitzt in `resolve`, nicht im
    # Loader.
    "family_group_chat_id": "",
    # LOG-4 (#166): Log-Level für `tools.logsetup.setup`. Default INFO
    # entspricht LOG-2 („INFO im Betrieb"). Override per ENV
    # `ELTERNCHAT_LOG_LEVEL` oder Konfig-Datei; das CLI-Flag `--log-level`
    # überschreibt den Loader-Output im Aufrufer (Test-Werkzeug, CONFIG-1).
    "log_level":           "INFO",
}

# Umgebungsvariablen-Namen der Geheimnisse / Pflicht-Werte. Diese gehen am
# Loader vorbei (CONFIG-3) — Geheimnisse berührt der Loader nicht.
ENV_BOT_TOKEN        = "ELTERNCHAT_BOT_TOKEN"          # Geheimnis, Pflicht
ENV_PROVIDER_API_KEY = "ELTERNCHAT_PROVIDER_API_KEY"   # Geheimnis, optional
ENV_FAMILY_GROUP     = "ELTERNCHAT_FAMILY_GROUP_CHAT_ID"


class ConfigError(Exception):
    """Eine Pflicht-Konfiguration fehlt oder ist ungültig (EC-15)."""


class Config:
    """Aufgelöste Instanz-Konfiguration.

    `provider_api_key` und `family_group_chat_id` können leer sein — dann ist
    das Onboarding zuständig (ONB-1/ONB-6). `family_group_locked` ist True, wenn
    die Familien-Gruppe per Env/Config gesetzt wurde; dann hat sie Vorrang vor
    einer Onboarding-Bindung (ONB-6).
    """

    def __init__(self, bot_token, provider_api_key, provider, provider_model,
                 family_group_chat_id, family_group_locked, context_depth,
                 ca_pem_path, familie_origin_url, geraete_origin_url,
                 panel_origin_url, plan_origin_url, display_url_origin,
                 routine_origin_url, photo_origin_url, log_level):
        self.bot_token = bot_token
        self.provider_api_key = provider_api_key
        self.provider = provider
        self.provider_model = provider_model
        self.family_group_chat_id = family_group_chat_id
        self.family_group_locked = family_group_locked
        self.context_depth = context_depth
        self.ca_pem_path = ca_pem_path             # CAV-3: Pfad zum öffentlichen Root-CA-Zertifikat
        self.familie_origin_url = familie_origin_url   # FAA-12 / #215: Origin der Familien-Komponente
        self.geraete_origin_url = geraete_origin_url   # GAA-5 / #215: Origin der Geraete-Komponente
        self.panel_origin_url = panel_origin_url       # PAA-5 / #183: Origin der Panel-Registry (PREG-15)
        self.plan_origin_url = plan_origin_url         # EC-21 / #215: Origin der Plan-Buddy-Reload-Schnittstelle
        self.display_url_origin = display_url_origin   # GAA-3.7: HTTPS-Origin für Display-URLs
        self.routine_origin_url = routine_origin_url   # RZS-6 / #343: Origin des Routine-Buddys (ROUTINE-14)
        self.photo_origin_url = photo_origin_url       # FSE-7 / #393: Origin des Photo-Buddys (PHOTO-13/PHOTO-16)
        self.log_level = log_level                 # LOG-4 (#166): Level-String für tools.logsetup


def _family_group_in_file(config_path):
    """Prüft, ob `family_group_chat_id` explizit in der Konfigurations-Datei
    steht — getrennt vom Loader, weil die Quelle (Datei vs. Default) das
    Sperr-Verhalten bestimmt (ONB-6: ENV/Datei sperren, Onboarding-Bindung
    nicht). Eine fehlende oder kaputte Datei zählt als „nicht in Datei"."""
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    val = data.get("family_group_chat_id")
    return val is not None and str(val).strip() != ""


def resolve(config_path, zd=None):
    """Löst die Konfiguration nach EC-15 auf.

    Generische Schicht (DEFAULTS-Schema-Werte): geht durch den gemeinsamen
    `tools.configloader` — Datei < ENV (`ELTERNCHAT_<KEY>`) < Default.
    Geheimnisse (Bot-Token, Anbieter-Key) und die Sperr-Logik der Familien-
    Gruppe sitzen darunter — der Loader rührt sie nicht an (CONFIG-3).

    `zd` ist ein optionaler Zugangsdaten-Speicher (Zugangsdaten-Instanz); bleibt
    er None, wird der reguläre Per-Instanz-Speicher nach ZD-8 aufgelöst. Tests
    injizieren hier einen isolierten Speicher (#336).

    Wirft ConfigError nur, wenn der Bot-Token fehlt oder ein Wert ungültig ist.
    Ein fehlender Anbieter-Key ist kein Fehler — er führt in den Onboarding-
    Modus (ONB-1).
    """
    try:
        values = configloader.load(
            component="elternchat",
            schema=DEFAULTS,
            config_path=config_path,
        )
    except configloader.ConfigLoaderError as e:
        # Loader-Fehler (kaputte Datei, ENV-Coercion) werden als ConfigError
        # nach oben gereicht — Aufrufer erwartet eine einzige Fehlerklasse.
        raise ConfigError(str(e)) from e

    # EC-15: context_depth muss >= 1 sein. Der Loader hat schon auf int
    # koerciert (Schema-Default 20 ist int); wir prüfen hier nur noch die
    # untere Grenze und die Boundary-Fälle, bei denen Datei einen Nicht-Int
    # eingeschmuggelt haben könnte.
    try:
        context_depth = int(values["context_depth"])
    except (TypeError, ValueError):
        raise ConfigError(
            "context_depth ist keine Ganzzahl: %r" % values["context_depth"])
    if context_depth < 1:
        raise ConfigError("context_depth muss >= 1 sein, ist %d" % context_depth)

    # Bot-Token: nur Env, Pflicht (Henne-Ei — siehe E-ONB-5).
    bot_token = os.environ.get(ENV_BOT_TOKEN, "").strip()
    if not bot_token:
        raise ConfigError("%s ist nicht gesetzt (Pflicht, EC-15)" % ENV_BOT_TOKEN)

    # Anbieter-Key: Env > Onboarding-Speicher > leer (→ Onboarding-Modus, ONB-1).
    store = OnboardingStore(zd=zd).load()
    provider_api_key = (os.environ.get(ENV_PROVIDER_API_KEY)
                        or store.get(KEY_PROVIDER_API_KEY)
                        or "").strip()

    # Familien-Gruppe: Env > Datei > Onboarding-Speicher > leer.
    # Per Env/Datei gesetzt → gesperrt, hat Vorrang vor Onboarding-Bindung (ONB-6).
    # Der Loader-Output liefert den ENV-/Datei-/Default-Wert; das Sperr-Bit
    # erkennen wir an der Quelle (ENV-gesetzt ODER Datei-gesetzt, nicht
    # Default).
    family_group = ""
    family_group_locked = False
    if os.environ.get(ENV_FAMILY_GROUP):
        family_group = os.environ[ENV_FAMILY_GROUP].strip()
        family_group_locked = True
    elif _family_group_in_file(config_path):
        family_group = str(values["family_group_chat_id"]).strip()
        family_group_locked = True
    elif store.get(KEY_FAMILY_GROUP):
        family_group = str(store[KEY_FAMILY_GROUP]).strip()

    return Config(
        bot_token=bot_token,
        provider_api_key=provider_api_key,
        provider=str(values["provider"]).strip(),
        provider_model=str(values["provider_model"]).strip(),
        family_group_chat_id=family_group,
        family_group_locked=family_group_locked,
        context_depth=context_depth,
        ca_pem_path=str(values["ca_pem_path"]).strip(),
        familie_origin_url=str(values["familie_origin_url"]).strip().rstrip("/"),
        geraete_origin_url=str(values["geraete_origin_url"]).strip().rstrip("/"),
        panel_origin_url=str(values["panel_origin_url"]).strip().rstrip("/"),
        plan_origin_url=str(values["plan_origin_url"]).strip().rstrip("/"),
        display_url_origin=str(values["display_url_origin"]).strip().rstrip("/"),
        routine_origin_url=str(values["routine_origin_url"]).strip().rstrip("/"),
        photo_origin_url=str(values["photo_origin_url"]).strip().rstrip("/"),
        log_level=str(values["log_level"]).strip(),
    )
