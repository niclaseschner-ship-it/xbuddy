"""Konfigurations-Auflösung — siehe specs/platform/eltern-chat.md EC-15 und
specs/platform/eltern-chat-onboarding.md (Refs #27, #33).

Priorität je Wert: Umgebungsvariable > Konfigurationsdatei > Onboarding-Speicher
> Default. Der Bot-Token kommt ausschließlich aus einer Umgebungsvariablen
(Pflicht). Der Anbieter-API-Key und die Familien-Gruppen-Chat-ID können aus
Umgebungsvariable/Konfiguration ODER aus dem Onboarding-Speicher stammen; fehlt
der Anbieter-Key auf beiden Wegen, läuft die Instanz im Onboarding-Modus
(ONB-1). Geheimnisse landen nie in einer Datei im Repo (CLAUDE.md §8).
"""

import json
import logging
import os

from onboarding_store import KEY_FAMILY_GROUP, KEY_PROVIDER_API_KEY, OnboardingStore


# EC-15: nicht-geheime Werte mit ihren Defaults (Env > Datei > Default).
DEFAULTS = {
    "provider":       "claude",     # KI-Anbieter (EC-11)
    "provider_model": "",           # leer → Anbieter-Default des Adapters
    "context_depth":  20,           # Gesprächskontext-Tiefe (EC-6)
    # CAV-3: Pfad zum öffentlichen Root-CA-Zertifikat, das die CA-Verteilung
    # ausliefert. Per-Instanz-Wert; Default = Standard-Ausgabe des CA-Werkzeugs
    # (tools/ca/make-ca.sh, #36). Niemals der CA-Privatschlüssel.
    "ca_pem_path":    "../tools/ca/out/rootCA.pem",
    # FAA-12: Pfad zur Familien-Registry (`familie.md` FAM-6), die die
    # FamilieAnlegenTask über FAM-11 fortschreibt. Per-Instanz-Wert; Default
    # passt zum Pi-Setup (familie/familie.json neben dem Eltern-Chat-Repo).
    "family_registry_path": "../familie/familie.json",
    # GAA-5 / GER-9: Pfad zur Geräte-Registry (`geraete.md` GER-4), die die
    # GeraetAnlegenTask über GER-6 fortschreibt. Per-Instanz-Wert; Default
    # passt zum Pi-Setup (geraete/geraete.json neben dem Eltern-Chat-Repo).
    "geraete_registry_path": "../geraete/geraete.json",
    # GAA-3.7: HTTPS-Origin, unter der die ausgelieferten Display-URLs
    # erreichbar sind (z. B. "https://xbuddy-hub.local:8443"). Per-Instanz-
    # Wert. Leer (Default) → Bot gibt nur den Pfad `/display/<id>` aus —
    # ausreichend für Tests/CI, für Familien-Anlage muss der Origin gesetzt
    # sein, damit das ausgeteilte Stück direkt aufs Tablet getippt werden
    # kann.
    "display_url_origin": "",
    # KAV-X: Pfad zur Per-Instanz-`plan/plan.json` (PLAN-28). Nach
    # erfolgreicher Kalender-Auswahl schreibt die »Kalender verbinden«-Skill
    # die gewählte `kalender_id` atomar hier hinein (V1-Provisorium gegen die
    # FS-Linie, sauber gelöst in Folge-Ticket #140). Default zeigt auf das
    # Pi-Layout (plan/plan.json neben dem Eltern-Chat-Repo).
    "plan_json_path": "../plan/plan.json",
}

# Umgebungsvariablen-Namen.
ENV_BOT_TOKEN        = "ELTERNCHAT_BOT_TOKEN"          # Geheimnis, Pflicht
ENV_PROVIDER_API_KEY = "ELTERNCHAT_PROVIDER_API_KEY"   # Geheimnis, optional
ENV_FAMILY_GROUP     = "ELTERNCHAT_FAMILY_GROUP_CHAT_ID"
ENV_OVERRIDES = {
    "provider":             "ELTERNCHAT_PROVIDER",
    "provider_model":       "ELTERNCHAT_PROVIDER_MODEL",
    "context_depth":        "ELTERNCHAT_CONTEXT_DEPTH",
    "ca_pem_path":          "ELTERNCHAT_CA_PEM_PATH",
    "family_registry_path": "ELTERNCHAT_FAMILY_REGISTRY_PATH",
    "geraete_registry_path": "ELTERNCHAT_GERAETE_REGISTRY_PATH",
    "display_url_origin":    "ELTERNCHAT_DISPLAY_URL_ORIGIN",
    "plan_json_path":        "ELTERNCHAT_PLAN_JSON_PATH",
}


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
                 ca_pem_path, family_registry_path, geraete_registry_path,
                 display_url_origin, plan_json_path):
        self.bot_token = bot_token
        self.provider_api_key = provider_api_key
        self.provider = provider
        self.provider_model = provider_model
        self.family_group_chat_id = family_group_chat_id
        self.family_group_locked = family_group_locked
        self.context_depth = context_depth
        self.ca_pem_path = ca_pem_path           # CAV-3: Pfad zum öffentlichen Root-CA-Zertifikat
        self.family_registry_path = family_registry_path   # FAA-12: Pfad zur Familien-Registry (FAM-6)
        self.geraete_registry_path = geraete_registry_path # GAA-5: Pfad zur Geräte-Registry (GER-4)
        self.display_url_origin = display_url_origin       # GAA-3.7: HTTPS-Origin für Display-URLs
        self.plan_json_path = plan_json_path     # KAV-X: Pfad zur Per-Instanz-`plan/plan.json`


def _load_file(path):
    """Lädt die optionale Konfigurationsdatei. Fehlt sie, ist das in Ordnung."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        logging.warning("config.json nicht parsebar (%s): %s — Defaults bleiben", path, e)
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def resolve(config_path, store_path=None, env=None):
    """Löst die Konfiguration nach EC-15 auf. `env` ist überschreibbar (Tests).

    Wirft ConfigError nur, wenn der Bot-Token fehlt oder ein Wert ungültig ist.
    Ein fehlender Anbieter-Key ist kein Fehler — er führt in den Onboarding-Modus.
    """
    if env is None:
        env = os.environ
    file_cfg = _load_file(config_path)
    store = OnboardingStore(store_path).load() if store_path else {}

    # Nicht-geheime Werte: Env > Datei > Default.
    values = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in file_cfg:
            values[key] = file_cfg[key]
        if ENV_OVERRIDES[key] in env:
            values[key] = env[ENV_OVERRIDES[key]]

    try:
        context_depth = int(values["context_depth"])
    except (TypeError, ValueError):
        raise ConfigError("context_depth ist keine Ganzzahl: %r" % values["context_depth"])
    if context_depth < 1:
        raise ConfigError("context_depth muss >= 1 sein, ist %d" % context_depth)

    # Bot-Token: nur Env, Pflicht (Henne-Ei — siehe E-ONB-5).
    bot_token = env.get(ENV_BOT_TOKEN, "").strip()
    if not bot_token:
        raise ConfigError("%s ist nicht gesetzt (Pflicht, EC-15)" % ENV_BOT_TOKEN)

    # Anbieter-Key: Env > Onboarding-Speicher > leer (→ Onboarding-Modus, ONB-1).
    provider_api_key = (env.get(ENV_PROVIDER_API_KEY)
                        or store.get(KEY_PROVIDER_API_KEY)
                        or "").strip()

    # Familien-Gruppe: Env > Datei > Onboarding-Speicher > leer.
    # Per Env/Datei gesetzt → gesperrt, hat Vorrang vor Onboarding-Bindung (ONB-6).
    family_group = ""
    family_group_locked = False
    if env.get(ENV_FAMILY_GROUP):
        family_group, family_group_locked = str(env[ENV_FAMILY_GROUP]).strip(), True
    elif file_cfg.get("family_group_chat_id"):
        family_group, family_group_locked = str(file_cfg["family_group_chat_id"]).strip(), True
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
        family_registry_path=str(values["family_registry_path"]).strip(),
        geraete_registry_path=str(values["geraete_registry_path"]).strip(),
        display_url_origin=str(values["display_url_origin"]).strip().rstrip("/"),
        plan_json_path=str(values["plan_json_path"]).strip(),
    )
