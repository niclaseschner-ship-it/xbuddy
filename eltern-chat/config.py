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

from onboarding_store import KEY_FAMILY_GROUP, OnboardingStore

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
    # E-TAB-6 V2 / #508: Multimodal-Modell-Override. leer → Anbieter-Default.
    # #1262: weiterhin genutzt — reicht als `model` an FotoAnalyseProvider durch
    # (leer → Foto-Default claude-opus-5, T1807).
    "multimodal_model": "",         # leer → Foto-Default des Adapters (#1262)
    # CAV-3: Pfad zum öffentlichen Root-CA-Zertifikat, das die CA-Verteilung
    # ausliefert. Per-Instanz-Wert; Default = Standard-Ausgabe des CA-Werkzeugs
    # (tools/ca/make-ca.sh, #36). Niemals der CA-Privatschlüssel.
    "ca_pem_path":    "../tools/ca/out/rootCA.pem",
    # FAA-12 / Auftrag #215: Origin der Familien-Komponente, ueber die die
    # FamilieAnlegenTask Personen schreibt (`POST /api/v1/familie/personen`
    # FAM-12) und liest (`GET /api/v1/familie/personen` FAM-7). Per-Instanz-
    # Wert; Default passt zum Pi-Setup (PORT-2 Familie auf 5010).
    "familie_origin_url": "http://127.0.0.1:5010",
    # `geraete_origin_url` vestigial seit RAT-31 E6c — die geraete-Registry
    # stirbt (#1565), »Gerät koppeln« mintet nur noch einen Pairing-Link.
    # Feld + Default bleiben strukturell erhalten (config bleibt unangetastet).
    "geraete_origin_url": "http://127.0.0.1:5040",
    # `panel_origin_url` vestigial seit RAT-31 E1 — PanelAnlegenTask entfallen
    # (#1470, panel_anlegen-Skill gelöscht). Feld + Default bleiben strukturell
    # erhalten (config bleibt unangetastet). PAA-5 / #183.
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
    # WRO-5 / #1094: Origin des Wetter-Buddys, über die der
    # WetterRegelnOeffnenTask die Mini-App-URL aufbaut
    # (`/display/wetter/regeln`, WRO-5). Per-Instanz-Wert; Default passt
    # zum Pi-Setup (PORT-2 Wetter-Buddy auf 5030). Leer ⇒ Aufgabe NICHT
    # im Katalog (WRO-8 AND-Guard).
    "wetter_origin_url": "http://127.0.0.1:5030",
    # EC-15 / #443: Origin des Icon-Dienstes, über den der
    # RoutinePunkteSetzenTask die ICONS-7-Stichwort-Suche aufruft
    # (`GET /api/v1/icons/suche` ICONS-7). Per-Instanz-Wert; Default
    # passt zum Pi-Setup: seit RAT-31 (Router-Abriss, #1568) serviert die
    # Seiten-Registry `icons/suche` auf 5042 (vormals Router auf 5000).
    # Leer ⇒ Aufgabe NICHT im Katalog (RPS-7 AND-Guard mit
    # routine_origin_url + family_group_chat_id_getter).
    "icon_origin_url": "http://127.0.0.1:5042",
    # FSE-7 / #393: Origin des Photo-Buddys, über den der FotoSendenTask
    # Medien hochlädt (`POST /api/v1/photo/medien` PHOTO-13) und widerruft
    # (`DELETE /api/v1/photo/medien/<id>` PHOTO-16). Per-Instanz-Wert; Default
    # passt zum Pi-Setup (PORT-2 Photo-Buddy auf 5051). Leer ⇒ Aufgabe NICHT
    # im Katalog (FSE-8 AND-Guard mit family_group_chat_id_getter).
    "photo_origin_url": "http://127.0.0.1:5051",
    # SREG-6 / #453: Origin der Seiten-Registry, über die der
    # SeitenUebersichtTask das aggregierte Seiten-Inventar liest
    # (`GET /api/v1/seiten` SREG-3). Per-Instanz-Wert; Default passt zum
    # Pi-Setup (PORT-2 Seiten-Registry auf 5042). Leer ⇒ Aufgabe NICHT im
    # Katalog (SREG-6 AND-Guard mit family_group_chat_id_getter).
    "seiten_origin_url": "http://127.0.0.1:5042",
    # GAA-3.7: HTTPS-Origin, unter der die ausgelieferten Display-URLs
    # erreichbar sind (z. B. "https://xbuddy-hub.local:8443"). Per-Instanz-
    # Wert. Leer (Default) → Bot gibt nur den Pfad `/display/<id>` aus.
    # DEPRECATED (SREG-7 Migration): wird zu display_url_origin_heim;
    # Doppel-Akzeptanz während Migration — `display_url_origin_heim` hat
    # Vorrang wenn beide gesetzt.
    "display_url_origin": "",
    # SREG-7 / #476: Heimnetz-Origin (tritt an die Stelle von display_url_origin).
    # Pflicht für SREG-5-Skill (seiten_uebersicht): ohne diese Origin kann
    # kein tippbarer Übersichts-Link geliefert werden. Leer (Default) →
    # resolve() fällt auf display_url_origin zurück (Migration).
    "display_url_origin_heim": "",
    # EC-15 / #503: Origin des Essens-Buddys, über die die
    # WuenscheZeigenTask die Wunschliste liest (`GET /api/v1/essen/wuensche`
    # ESSEN-15) und die GerichtAnlegenTask Gerichte anlegt
    # (`POST /api/v1/essen/katalog/gerichte` ESSEN-19). Per-Instanz-Wert;
    # Default passt zum Pi-Setup (PORT-2 Essens-Buddy auf 5052). Leer ⇒
    # beide Aufgaben NICHT im Katalog (WZE-8 / GAN-7 AND-Guard).
    "essen_origin_url": "http://127.0.0.1:5052",
    # EZG-6 / EIN-8 / #653: HTTPS-URL der Einkauf-Mini-App (Telegram-WebApp-
    # Ansicht). Leer (Default) → EinkaufZeigenTask nutzt ENV-Fallback
    # MINI_APP_EINKAUF_URL (EZG-6) oder zeigt Fehler-Text ohne Button (EZG-7).
    "mini_app_einkauf_url": "",
    # RAO-6 / T728-C: HTTPS-Basis-URL aller Mini-Apps und PWAs (Funnel-Domain).
    # Leer (Default) → RoutineAnpassenOeffnenTask und HoerspielOeffnenTask
    # werden NICHT im Katalog registriert (RAO-8 / HOE-8 dreifacher Guard).
    # HSP-53 (2026-07-03): wird auch für die Hörspiel-Player-PWA genutzt
    # (mini_app_base_url + /seiten/hoerspiel/player, HOE-5 / HSP-47).
    # Bot-Menü-Buttons (setChatMenuButton) zeigen künftig auf die PWA (HSP-53).
    # Selbe Domain wie mini_app_einkauf_url-Basis, aber als separater Slot —
    # kein String-Parsing der Einkauf-URL.
    "mini_app_base_url": "",
    # HFE-9 / #729: Origin des Hörspiel-Buddys (Mia-Instanz), über die die
    # HoerspielFolgeErzeugenTask Folgen-Vorschläge holt
    # (POST /api/v1/hoerspiel/folgen-vorschlag HFE-3) und Alben baut
    # (POST /api/v1/hoerspiel/alben HFE-5). Per-Instanz-Wert; Default passt
    # zum Pi-Setup (PORT-2 Hörspiel-Buddy Mia auf 5053). Leer ⇒ Aufgabe NICHT im
    # Katalog (AND-Guard mit family_group_chat_id_getter).
    "hoerspiel_url_origin": "http://127.0.0.1:5053",
    # Option C (#1732): die per-kind_id-Origins der weiteren Instanzen kommen aus
    # der zentralen instanzen.json-Registry (`origin`-Feld) — keine handverdrahteten
    # hoerspiel_url_origin_finn/_emil-Felder mehr. hoerspiel_url_origin bleibt als
    # Katalog-Gate + Default-Client (HFE-9 / #729).
    # KAQS-6 / #825: Origin des KIBuddy-Config-Endpunkts, über den die
    # KibuddyAufnahmeQuelleSetzenTask die Aufnahme-Quelle schreibt
    # (PUT /api/v1/kibuddy/config KAQS-5). Per-Instanz-Wert; Default passt
    # zum Pi-Setup (PORT-2 KIBuddy auf 5054, KIBUDDY-25). Leer ⇒ Aufgabe
    # NICHT im Katalog (AND-Guard mit family_group_chat_id_getter, KAQS-6).
    "kibuddy_origin_url": "http://127.0.0.1:5054",
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
ENV_BOT_TOKEN             = "ELTERNCHAT_BOT_TOKEN"               # Geheimnis, Pflicht
ENV_PROVIDER_API_KEY      = "ELTERNCHAT_PROVIDER_API_KEY"        # Geheimnis, optional
ENV_FAMILY_GROUP          = "ELTERNCHAT_FAMILY_GROUP_CHAT_ID"


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
                 routine_origin_url, icon_origin_url, photo_origin_url,
                 seiten_origin_url, display_url_origin_heim,
                 essen_origin_url,
                 log_level,
                 multimodal_model="",
                 mini_app_einkauf_url="",
                 mini_app_base_url="",
                 hoerspiel_url_origin="",
                 kibuddy_origin_url="",
                 wetter_origin_url=""):
        self.bot_token = bot_token
        self.provider_api_key = provider_api_key
        self.provider = provider
        self.provider_model = provider_model
        self.family_group_chat_id = family_group_chat_id
        self.family_group_locked = family_group_locked
        self.context_depth = context_depth
        self.ca_pem_path = ca_pem_path             # CAV-3: Pfad zum öffentlichen Root-CA-Zertifikat
        self.familie_origin_url = familie_origin_url   # FAA-12 / #215: Origin der Familien-Komponente
        self.geraete_origin_url = geraete_origin_url   # vestigial seit RAT-31 E6c (#1565): geraete-Registry stirbt
        self.panel_origin_url = panel_origin_url       # PAA-5 / #183: Origin der Panel-Registry (PREG-15)
        self.plan_origin_url = plan_origin_url         # EC-21 / #215: Origin der Plan-Buddy-Reload-Schnittstelle
        self.display_url_origin = display_url_origin   # GAA-3.7 (deprecated → display_url_origin_heim, SREG-7)
        self.routine_origin_url = routine_origin_url   # RZS-6 / #343: Origin des Routine-Buddys (ROUTINE-14)
        self.icon_origin_url = icon_origin_url         # EC-15 / #443: Origin des Icon-Routers (ICONS-7)
        self.photo_origin_url = photo_origin_url       # FSE-7 / #393: Origin des Photo-Buddys (PHOTO-13/PHOTO-16)
        self.seiten_origin_url = seiten_origin_url     # SREG-6 / #453: Origin der Seiten-Registry (SREG-3)
        self.display_url_origin_heim = display_url_origin_heim         # SREG-7 / #476: Heimnetz-Origin (Funnel-only nach #1458)
        self.essen_origin_url = essen_origin_url       # EC-15 / #503: Origin des Essens-Buddys (ESSEN-15/ESSEN-19)
        self.log_level = log_level                 # LOG-4 (#166): Level-String für tools.logsetup
        # E-TAB-6 V2 / #508: Multimodal-Modell-Override (#1262, PR2 #1334).
        # `multimodal_provider` + `multimodal_api_key` entfernt (#1334): der
        # Foto-Pfad holt den Key aus dem ZD-Store (Foto-Slot), Anbieter ist
        # über den Slot-Vendor gepinnt. Nur `multimodal_model` bleibt.
        self.multimodal_model = multimodal_model        # #1262: Modell-Override an Foto-Adapter
        # EZG-6 / EIN-8 / #653: Mini-App-URL für die Einkaufsliste (EZG-6).
        self.mini_app_einkauf_url = mini_app_einkauf_url  # leer → ENV-Fallback MINI_APP_EINKAUF_URL
        # RAO-6 / T728-C / HSP-53: Basis-URL aller Mini-Apps und PWAs (Funnel-Domain).
        self.mini_app_base_url = mini_app_base_url  # leer → RAO/HOE NICHT im Katalog
        # HFE-9 / #729: Origin des Hörspiel-Buddys Mia (HFE-3/HFE-5, HSP-17).
        self.hoerspiel_url_origin = hoerspiel_url_origin  # leer → HFE NICHT im Katalog
        # Option C (#1732): weitere Instanz-Origins aus instanzen.json-Registry,
        # keine hoerspiel_url_origin_finn/_emil-Felder mehr.
        # KAQS-6 / #825: Origin des KIBuddy-Config-Endpunkts (KAQS-5, KIBUDDY-24/25).
        self.kibuddy_origin_url = kibuddy_origin_url      # leer → KAQS NICHT im Katalog
        # WRO-5 / #1094: Origin des Garderoben-Editors (/display/wetter/regeln)
        self.wetter_origin_url = wetter_origin_url        # leer → WRO NICHT im Katalog


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

    # Bot-Token: ENV(ELTERNCHAT_BOT_TOKEN) → Store-Slot 'eltern-chat-bot-token'
    # → ConfigError EC-15 (T1445, additiv-rückrollbar; ENV-Pfad unverändert).
    # Store-Read ist lazy und defensiv — fehlt der Store oder schlägt der Import
    # fehl, wird None zurückgegeben und der ConfigError greift wie bisher.
    bot_token = os.environ.get(ENV_BOT_TOKEN, "").strip()
    if not bot_token:
        try:
            from tools.zugangsdaten import Zugangsdaten, resolve_store_path
            _zd = zd if zd is not None else Zugangsdaten(resolve_store_path())
            bot_token = (_zd.get("eltern-chat-bot-token") or "").strip()
        except Exception:
            bot_token = ""
    if not bot_token:
        raise ConfigError("%s ist nicht gesetzt (Pflicht, EC-15)" % ENV_BOT_TOKEN)

    # Anbieter-Key-Präsenz: Env > litellm-Motor-Slot > leer (→ Onboarding-Modus,
    # ONB-1). #1510: der Boot-Gate liest jetzt den litellm-Slot
    # (`eltern-chat-litellm-<purpose>-api-key`, via `litellm_key_present`) —
    # GENAU den Slot, den der Laufzeit-Chat-Pfad (LibAgentAdapter) und der
    # SVC-7-Preflight (main._secret_preflight) ohnehin nutzen. Damit gilt der
    # KI-Modus-Gate (`cfg.provider_api_key` truthy) an derselben Naht wie der
    # eager Adapter-Bau — kein Slot-Auseinanderdriften mehr. Der ALTE
    # vendor/single-Slot-Read (T663 Welle A) ist damit aufgelöst; der Key selbst
    # holt die Lib aus dem Slot (ZD-5), config trägt ihn nicht mehr.
    provider_adapter = str(values["provider"]).strip()
    store = OnboardingStore(zd=zd)
    env_key = (os.environ.get(ENV_PROVIDER_API_KEY) or "").strip()
    # `provider_api_key` bleibt ein truthy KI-Modus-Marker: der ENV-Key wörtlich,
    # sonst ein nicht-leerer Platzhalter, wenn der litellm-Slot präsent ist. Der
    # Wert wird nicht mehr als roher Key durchgereicht (tasks.py baut den Motor-
    # Adapter, der den Key selbst aus dem Slot holt).
    if env_key:
        provider_api_key = env_key
    elif store.litellm_key_present(provider_adapter):
        provider_api_key = "litellm-slot"   # präsenz-Marker (nie geloggt/gespiegelt)
    else:
        provider_api_key = ""
    store = store.load()

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
        icon_origin_url=str(values["icon_origin_url"]).strip().rstrip("/"),
        photo_origin_url=str(values["photo_origin_url"]).strip().rstrip("/"),
        seiten_origin_url=str(values["seiten_origin_url"]).strip().rstrip("/"),
        # SREG-7 Migration (abgeschlossen #1458): display_url_origin_heim hat
        # Vorrang; fällt auf display_url_origin zurück (Doppel-Akzeptanz).
        # display_url_origin_tailscale entfernt — Funnel-only (Nic-Setzung
        # 2026-07-25, #1458). Tailnet-IP-Self-Signed-Origin aufgegeben.
        display_url_origin_heim=(
            str(values["display_url_origin_heim"]).strip().rstrip("/")
            or str(values["display_url_origin"]).strip().rstrip("/")
        ),
        essen_origin_url=str(values["essen_origin_url"]).strip().rstrip("/"),
        log_level=str(values["log_level"]).strip(),
        # E-TAB-6 V2 / #508: Multimodal-Modell-Override (#1262, PR2 #1334).
        multimodal_model=str(values["multimodal_model"]).strip(),
        # EZG-6 / EIN-8 / #653: Mini-App-URL für die Einkaufsliste.
        mini_app_einkauf_url=str(values["mini_app_einkauf_url"]).strip(),
        # RAO-6 / T728-C: Basis-URL aller Mini-Apps (Funnel-Domain).
        mini_app_base_url=str(values["mini_app_base_url"]).strip().rstrip("/"),
        # HFE-9 / #729: Origin des Hörspiel-Buddys Mia.
        hoerspiel_url_origin=str(values["hoerspiel_url_origin"]).strip().rstrip("/"),
        # KAQS-6 / #825: Origin des KIBuddy-Config-Endpunkts (KAQS-5, KIBUDDY-25).
        kibuddy_origin_url=str(values["kibuddy_origin_url"]).strip().rstrip("/"),
        # WRO-5 / #1094: Origin des Wetter-Buddys (WRO-8 AND-Guard).
        wetter_origin_url=str(values["wetter_origin_url"]).strip().rstrip("/"),
    )
