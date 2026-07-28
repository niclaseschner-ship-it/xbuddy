"""Onboarding-Speicher — siehe specs/platform/eltern-chat-onboarding.md ONB-5
(Refs #33, #100, #84, #336).

Hält die Werte, die das Onboarding setzt: den KI-Anbieter-Key und die
Familien-Gruppen-Chat-ID. Seit #84 (OPEN-ZD-B, Schritt 1) und #336
(OPEN-ZD-B, Schritt 2) liegen diese Werte ausschließlich im zentralen
Zugangsdaten-Speicher (`tools/zugangsdaten`, ZD-1: ein Speicher je Instanz) —
die Alt-Klasse/-Datei und die einmalige Migration sind entfernt.

config.py liest diesen Speicher beim Start (EC-15), onboarding.py schreibt ihn
beim Abschluss des Onboardings (ONB-5/ONB-6). Die gelesenen dict-Schlüssel
('provider_api_key'/'family_group_chat_id') bleiben unverändert — config.py
konsumiert sie unverändert.
"""

from tools.llm import litellm_slot_for_provider
from tools.zugangsdaten import Zugangsdaten, resolve_store_path

# Schlüssel im gelesenen dict (Public-Schnittstelle für config.py — unverändert).
KEY_PROVIDER_API_KEY = "provider_api_key"
KEY_FAMILY_GROUP = "family_group_chat_id"

# #84/ZD-2: Namen der beiden Werte im zentralen Zugangsdaten-Speicher. Gedasht
# und genamespaced wie 'plan-google-oauth-refresh-token' — stabile Namen, die
# nicht neu vergeben werden (ZD-2).
ZD_NAME_PROVIDER_API_KEY = "eltern-chat-provider-api-key"
ZD_NAME_FAMILY_GROUP = "eltern-chat-family-group-chat-id"

# T663 Welle A: Slot-Name für den persistenten Anbieter-Namen (ONB-11). Lebt
# zentral hier — der Skill `anbieter_wechseln` importiert die Konstante, statt
# sie als String-Literal selbst zu führen (Watchdog B4: eine Wahrheitsquelle,
# CLAUDE.md §6).
ZD_NAME_PROVIDER_NAME = "eltern-chat-provider-name"

# #1510: Adapter-Name → Brand-Vendor-Slug als schlichte Map. Vorher lag die
# Zuordnung als `brand_vendor`-Klassen-Attribut an den Hand-Vendor-Adaptern
# (`providers/claude.py`, `providers/mistral.py`); diese sterben mit #1510 (der
# Motor-Call läuft über `tools.llm`). Die eine Wahrheitsquelle wandert damit von
# den Klassen in diese Map — ohne Verhaltensänderung (`claude` → `anthropic`,
# `mistral` → `mistral`). Unbekannte Adapter-Namen bleiben Passthrough.
_ADAPTER_BRAND_VENDOR = {
    "claude": "anthropic",
    "mistral": "mistral",
}


def vendor_slug_for_adapter(adapter_name):
    """Löst einen Adapter-Namen auf den Brand-Vendor-Slug auf (T1022).

    `claude` → `anthropic`, `mistral` → `mistral`. Der Slug kommt aus der
    zentralen `_ADAPTER_BRAND_VENDOR`-Map (#1510: früher `brand_vendor` an der
    Provider-Klasse, gelöscht). Unbekannte Adapter-Namen werden 1:1 zurückgegeben —
    Pragmatik für künftige Adapter, deren Adapter-Name dem Brand-Vendor
    entspricht. Convention-Rewrite (ECP-1) tracked #1537.
    """
    if not isinstance(adapter_name, str) or not adapter_name:
        raise ValueError("adapter_name muss ein nicht-leerer String sein")
    return _ADAPTER_BRAND_VENDOR.get(adapter_name, adapter_name)


def zd_name_provider_api_key(adapter_name):
    """Vendor-spezifischer ZD-Slot-Name für den API-Key (T663 Welle A).

    Welle A führt pro Brand-Vendor einen eigenen Slot ein
    (`eltern-chat-anthropic-api-key`, `eltern-chat-mistral-api-key`). Der
    Single-Slot-Name (`eltern-chat-provider-api-key`) bleibt Fallback —
    `load(provider_name=...)` liest vendor-Slot zuerst, fällt auf Single-Slot
    zurück. Welle B (späteres Ticket) entfernt den Single-Slot.

    `adapter_name` ist der app-lokale Anbieter-Name (`claude`, `mistral`).
    Intern wird er über `vendor_slug_for_adapter` auf den Brand-Vendor
    aufgelöst — die Spec ZD-2 bindet den Slot-Namen an den Brand-Vendor
    (Watchdog B2).

    Helper ist hier zentral, damit der Skill `anbieter_wechseln` denselben
    Namens-Bauer importiert (eine Wahrheitsquelle, CLAUDE.md §6).
    """
    vendor = vendor_slug_for_adapter(adapter_name)
    return "eltern-chat-%s-api-key" % vendor


class OnboardingStore:
    """Lädt und speichert die per Onboarding gesetzten Werte über den zentralen
    Zugangsdaten-Speicher (#84/#336, ZD-1).

    `zd` ist der zentrale Speicher; bleibt er None, wird der reguläre
    Per-Instanz-Speicher nach ZD-8 aufgelöst — so bleiben alle Aufrufer
    (config.py, main.py) unverändert, während Tests einen isolierten Speicher
    injizieren.
    """

    def __init__(self, zd=None):
        self._zd = zd if zd is not None else Zugangsdaten(resolve_store_path())

    def load(self, provider_name=None):
        """Liefert die gespeicherten Werte als dict — direkt aus dem ZD-Speicher
        (#336, ZD-only). Fehlt ein Wert, taucht der Schlüssel im Ergebnis nicht
        auf (wie zuvor).

        `provider_name` (T663 Welle A): wenn gesetzt, wird der vendor-spezifische
        Slot zuerst gelesen (`eltern-chat-<vendor>-api-key`, Brand-Vendor —
        ZD-2-Tabelle, `vendor_slug_for_adapter`). Liegt dort kein truthy-Wert,
        fällt der Aufruf auf den Single-Slot (`eltern-chat-provider-api-key`)
        zurück. Default `None` bewahrt das alte Verhalten: nur Single-Slot
        lesen — kein Bruch für Aufrufer, die den Vendor nicht kennen.

        Lazy-Migration (T663 Welle A, ONB-13, Watchdog B3): ist
        `provider_name` gesetzt UND der vendor-Slot leer UND der Single-Slot
        gefüllt, schreibt diese Methode den Single-Slot-Wert einmalig in den
        vendor-Slot. Der Single-Slot bleibt unverändert (Welle B entfernt ihn
        in einem späteren Ticket). Die Migration ist idempotent: läuft sie
        nach dem Schreiben erneut, ist der vendor-Slot bereits gefüllt und
        kein Schreibvorgang nötig.
        """
        data = {}
        provider = None
        if provider_name is not None:
            # Welle A: vendor-Slot bevorzugt, truthy-Check (R8) — leere Strings
            # gelten als nicht gesetzt und triggern den Fallback.
            vendor_slot = zd_name_provider_api_key(provider_name)
            vendor_value = self._zd.get(vendor_slot)
            if vendor_value:
                provider = vendor_value
            else:
                # Lazy-Migration: vendor-Slot leer, Single-Slot prüfen.
                single_value = self._zd.get(ZD_NAME_PROVIDER_API_KEY)
                if single_value:
                    # Einmalig in den vendor-Slot schreiben — Single-Slot bleibt
                    # stehen (Welle B entfernt ihn). Idempotent: beim nächsten
                    # Aufruf gewinnt der vendor-Slot direkt oben.
                    self._zd.set(vendor_slot, single_value)
                    provider = single_value
        if provider is None:
            # Fallback (Welle A) / Default-Pfad: Single-Slot lesen.
            provider = self._zd.get(ZD_NAME_PROVIDER_API_KEY)
        if provider is not None:
            data[KEY_PROVIDER_API_KEY] = provider
        family = self._zd.get(ZD_NAME_FAMILY_GROUP)
        if family is not None:
            data[KEY_FAMILY_GROUP] = family
        return data

    def save(self, provider_api_key=None, family_group_chat_id=None):
        """Schreibt die übergebenen Werte (None wird ignoriert) in den zentralen
        Zugangsdaten-Speicher (#84, write-ZD-only). Der ZD-Speicher legt die
        Datei race-frei mit 0600 an (ZD-3) und schreibt atomar (DCOMP-4)."""
        if provider_api_key is not None:
            self._zd.set(ZD_NAME_PROVIDER_API_KEY, provider_api_key)
        if family_group_chat_id is not None:
            self._zd.set(ZD_NAME_FAMILY_GROUP, family_group_chat_id)

    # ============================================================
    #  #1510: litellm-Motor-Slot — Probe + Boot-Read
    # ============================================================
    #
    # Der Laufzeit-Chat-Pfad (LibAgentAdapter) liest den API-Key aus dem
    # anbieter-benannten litellm-Slot (`eltern-chat-litellm-<purpose>-api-key`,
    # LLMP-5, via `litellm_slot_for_provider`). Onboarding/Anbieter-Wechsel
    # validieren einen Ad-hoc-Key seit #1510 über GENAU diesen Slot: probeweise
    # schreiben → über den Motor pingen → bei Fehler löschen (RATIFIZIERT
    # 20260728-1510). `save`/`load` oben kennen nur die ALTEN Slots; diese
    # Accessoren schreiben/lesen/löschen den litellm-Slot.

    def litellm_probe_write(self, provider, api_key):
        """Schreibt `api_key` PROBEWEISE in den litellm-Slot des Anbieters (#1510).

        Der Slot ist der reguläre Laufzeit-Slot (`litellm_slot_for_provider`) —
        ein gültiger Probe-Wert bleibt einfach stehen und ist damit sofort der
        persistierte Key (der separate ONB-12-Schreibschritt verschmilzt).
        `provider` ist der Adapter-Name (`claude`/`mistral`); unbekannter
        Anbieter → `KeyError` (sichtbar, kein Silent-Fallback — wie die
        Laufzeit-Naht)."""
        self._zd.set(litellm_slot_for_provider("eltern-chat", provider), api_key)

    def litellm_probe_delete(self, provider):
        """Räumt den litellm-Slot des Anbieters nach einem FEHLGESCHLAGENEN
        Probe-Schreib wieder ab (#1510). `tools.zugangsdaten` kennt kein echtes
        Löschen (nur set/set_multi); ein liegengebliebener FALSCH-Key ist aber
        gefährlich (er bestünde den SVC-7-Präsenz-Check und fiele erst live).
        Darum wird der Slot auf den LEEREN String gesetzt — `litellm_key_present`
        (bool-Truthy) und der Lib-`slot_present` (bool(resolve_api_key)) werten
        das identisch als »nicht gesetzt«, ohne einen brauchbaren Key zu behalten."""
        self._zd.set(litellm_slot_for_provider("eltern-chat", provider), "")

    def litellm_key_present(self, provider):
        """True, wenn im litellm-Slot des Anbieters ein nicht-leerer Key liegt
        (#1510). Boot-Gate + Pfad-A-Diskriminante lesen hierüber — genau den
        Slot, den die Laufzeit auch nutzt (kein Slot-Auseinanderdriften).

        Ein unbekannter Anbieter (kein LLM-Slot-Mapping) hat keinen Slot →
        `False` statt Crash. Der eager Adapter-Bau / SVC-7-Preflight fängt einen
        wirklich fehlkonfigurierten Anbieter am Boot mit klarer Meldung ab."""
        try:
            slot = litellm_slot_for_provider("eltern-chat", provider)
        except KeyError:
            return False
        return bool(self._zd.get(slot))
