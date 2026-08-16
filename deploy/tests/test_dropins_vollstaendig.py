"""Guard: die versionierten systemd-Drop-Ins und ihre Soll-Liste driften nicht (#1802).

Hintergrund: Bis #1802 lebten 37 von 38 Drop-Ins ausschliesslich in
`/etc/systemd/system/*.service.d/` — was nur dort steht, ueberlebt kein
Neuaufsetzen und kommt in keine zweite Familie (SVC-2 Drift-Schutz). Zwei
Dateien liefen in die **Gegenrichtung**: `memory.conf` fuer plan und familie lag
seit dem 10.08. im Repo und war nie auf der Maschine angekommen, weil
`bootstrap.sh` Drop-Ins gar nicht ausrollte. Die Bremse galt als gebaut und
wirkte nirgends.

**Bewusst akzeptierte Grenze (Nic-Verdikt „a", 2026-08-11):** dieser Guard sieht
NUR das Repo. Wer von Hand direkt auf der Maschine etwas aendert, wird davon
nicht erfasst. Das war der Grund fuer die verworfenen Alternativen — die Wahl
fiel trotzdem auf den Weg, der ohne Disziplin auskommt. Hier deshalb **keine**
Maschinen-Abfrage (kein `systemctl`, kein Lesen aus `/etc`): der Test laeuft in
CI genauso wie am Pi.

Was er stattdessen haelt — drei Naehte, die die Drift im Repo festnageln:

1. **Soll-Liste ↔ Baum, in BEIDE Richtungen.** Die Soll-Liste ist die
   Drop-In-Tabelle in `deploy/systemd/README.md` (die Deploy-Anleitung, die ein
   Mensch beim Aufsetzen liest — kein eingefrorenes Literal in dieser Datei).
   Fehlt eine Baum-Datei in der Tabelle -> rot. Steht eine Tabellen-Zeile ohne
   Datei da -> rot.
2. **Jedes Drop-In-Verzeichnis gehoert zu einer Unit, die `bootstrap.sh`
   installiert.** Ein Verzeichnis `xbuddy-<irgendwas>.service.d/` ohne Eintrag in
   der `SVC_SRC`-Map landete auf der Maschine neben einer Unit, die es nicht
   gibt: eine Datei, die aussieht als wirke sie, und nie wirkt.
3. **Kein absoluter Host-Pfad im Repo.** Per-Instanz-Werte stehen als
   `__XBUDDY_*__`-Platzhalter (SVC-5, Platzhalter-Tabelle in
   `deploy/systemd/README.md`); `bootstrap.sh` substituiert sie beim Ausrollen.

NUR_AUF_DER_MASCHINE: dokumentierter Ausnahme-Satz — Drop-Ins, die am Pi liegen
und bewusst NICHT versioniert werden. Neue Ausnahmen brauchen hier eine
Begruendung.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYSTEMD_DIR = REPO_ROOT / "deploy" / "systemd"
README = SYSTEMD_DIR / "README.md"
BOOTSTRAP = REPO_ROOT / "deploy" / "bootstrap.sh"

ETC_PREFIX = "/etc/systemd/system/"

# Drop-Ins, die am Pi liegen und bewusst NICHT ins Repo wandern. Begruendung
# pro Eintrag — der Schluessel ist der Pfad, den die Datei im Repo HAETTE.
#
# Gemeinsamer Nenner aller Eintraege: sie tragen Per-Person-Werte (Klarname,
# Alter, Telegram-Konto-ID), fuer die die Platzhalter-Tabelle in
# deploy/systemd/README.md keine Form kennt — sie deckt die acht Host-Werte ab
# (USER/HOME/REPO/PYTHON/DATA + drei Display-Origins), keine Identitaeten. Sie
# hier mit erfundenen Ersatzwerten zu versionieren waere eine Konvention aus dem
# Stegreif; sie mit den echten Werten zu versionieren waere ein PII-Leak in ein
# oeffentliches Repo (.gitleaks.toml blockt genau diese Muster, #1724).
# Vorgelegt als offener Punkt in #1802.
NUR_AUF_DER_MASCHINE: dict[str, str] = {
    "xbuddy-eltern-chat.service.d/30-master-id.conf":
        "ELTERNCHAT_MASTER_TELEGRAM_USER_ID — echte Telegram-Konto-ID. "
        ".gitleaks.toml Regel `xbuddy-telegram-chat-id` blockt den Wert; ein "
        "Platzhalter dafuer existiert nicht.",
    "xbuddy-hoerspiel.service.d/20-data-path.conf":
        "HOERSPIEL_DATA_ROOT endet auf dem Klarnamen-Slug des Kindes. "
        "Kind-Slugs sind seit #1783 im gitignored .gitleaks-local.toml gesperrt.",
    "xbuddy-hoerspiel.service.d/30-kind-id.conf":
        "HOERSPIEL_KIND_ID/_NAME/_ALTER — Klarname und Alter eines Kindes. "
        "BOOT-4 verortet Per-Kind-Werte ohnehin im Unit-Koerper, nicht in einem "
        "Drop-In.",
    "xbuddy-hoerspiel-finn.service.d/20-data-path.conf":
        "wie oben (zweite Kind-Instanz, live Port 5055).",
    "xbuddy-hoerspiel-finn.service.d/30-kind-id.conf":
        "wie oben (zweite Kind-Instanz, live Port 5055).",
}

# Verwaist und deshalb weder versioniert noch in der Soll-Liste: der Dienst
# xbuddy-geraete ist mit RAT-31 (cf0dbb1e) aus dem Repo geloescht, die Unit am
# Pi ist `inactive`/`disabled`. Das Aufraeumen der Datei in /etc gehoert zum
# Unit-Aufraeumen in #1862.
VERWAIST = "xbuddy-geraete.service.d/10-data-path.conf"


def _soll_liste() -> dict[str, str]:
    """Liest die Drop-In-Tabelle aus deploy/systemd/README.md.

    Rueckgabe: {repo-relativer Pfad unter deploy/systemd/: /etc-Zielpfad}.
    """
    zeilen_muster = re.compile(
        r"^\|\s*`(deploy/systemd/[^`]+)`\s*\|\s*`(/etc/systemd/system/[^`]+)`\s*\|"
    )
    soll: dict[str, str] = {}
    for zeile in README.read_text(encoding="utf-8").splitlines():
        treffer = zeilen_muster.match(zeile)
        if treffer:
            repo_pfad, etc_pfad = treffer.group(1), treffer.group(2)
            soll[repo_pfad[len("deploy/systemd/"):]] = etc_pfad
    return soll


def _baum() -> set[str]:
    """Findet alle versionierten Drop-Ins unter deploy/systemd/*.service.d/."""
    return {
        pfad.relative_to(SYSTEMD_DIR).as_posix()
        for pfad in SYSTEMD_DIR.glob("*.service.d/*.conf")
    }


def _bootstrap_units() -> set[str]:
    """Liest die SVC_SRC-Map aus deploy/bootstrap.sh (systemd-Namen)."""
    text = BOOTSTRAP.read_text(encoding="utf-8")
    block = re.search(r"declare -A SVC_SRC=\((.*?)\n\)", text, re.DOTALL)
    assert block, "SVC_SRC-Map in deploy/bootstrap.sh nicht gefunden."
    return set(re.findall(r"\[([\w.-]+)\]=", block.group(1)))


# ---------------------------------------------------------------------------
# 1. Soll-Liste ↔ Baum, beide Richtungen
# ---------------------------------------------------------------------------
def test_jede_soll_datei_liegt_im_baum():
    """Richtung A: Was die Deploy-Anleitung verspricht, muss es geben.

    Wird eine versionierte Datei geloescht (oder umbenannt), ohne die Tabelle
    mitzuziehen, verspricht die Anleitung ein Drop-In, das `bootstrap.sh` nie
    ausrollen kann — der Dienst startet ohne seine Ergaenzung.
    """
    soll = _soll_liste()
    assert soll, (
        "Die Drop-In-Tabelle in deploy/systemd/README.md ist leer oder nicht "
        "parsebar. Zeilenform: | `deploy/systemd/<dir>/<datei>` | "
        "`/etc/systemd/system/<dir>/<datei>` | <Zweck> |"
    )
    ist = _baum()
    fehlend = sorted(soll.keys() - ist)
    assert not fehlend, (
        "Diese Drop-Ins stehen in der Soll-Liste (deploy/systemd/README.md, "
        "Tabelle 'Drop-Ins im Repo'), existieren aber NICHT unter "
        "deploy/systemd/ (#1802):\n"
        + "\n".join(f"  - {d}" for d in fehlend)
        + "\n\nFix: Datei anlegen — oder, wenn sie bewusst entfaellt, die "
        "Tabellen-Zeile mit entfernen."
    )


def test_jede_baum_datei_steht_in_der_soll_liste():
    """Richtung B: Was im Repo liegt, muss die Anleitung kennen.

    Das ist die Richtung, die den #1785-Fall gefunden haette: `memory.conf` lag
    im Repo und kam nie auf die Maschine. Eine Datei, die in keiner Soll-Liste
    steht, hat niemanden, der ihren Ausroll-Weg verantwortet.
    """
    soll = _soll_liste()
    ist = _baum()
    unbekannt = sorted(ist - soll.keys())
    assert not unbekannt, (
        "Diese Drop-Ins liegen unter deploy/systemd/, fehlen aber in der "
        "Soll-Liste (deploy/systemd/README.md, Tabelle 'Drop-Ins im Repo') "
        "— niemand verantwortet ihren Ausroll-Weg (#1802):\n"
        + "\n".join(f"  - {d}" for d in unbekannt)
        + "\n\nFix: Tabellen-Zeile ergaenzen (Repo-Pfad | /etc-Zielpfad | Zweck)."
    )


def test_soll_liste_zielpfade_passen_zum_repo_pfad():
    """Der /etc-Zielpfad einer Zeile muss zum Repo-Pfad derselben Zeile passen.

    Sonst kopiert die Anleitung eine Datei an einen fremden Ort — und die
    Tabelle sagt etwas anderes als `bootstrap.sh` tut.
    """
    falsch = sorted(
        f"{rel} -> {etc}"
        for rel, etc in _soll_liste().items()
        if etc != ETC_PREFIX + rel
    )
    assert not falsch, (
        "Zielpfad passt nicht zum Repo-Pfad (erwartet "
        f"{ETC_PREFIX}<gleicher Unterpfad>):\n"
        + "\n".join(f"  - {z}" for z in falsch)
    )


# ---------------------------------------------------------------------------
# 2. Ausnahme-Satz bleibt eine Ausnahme
# ---------------------------------------------------------------------------
def test_ausnahmen_sind_nicht_still_doch_versioniert():
    """Jeder NUR_AUF_DER_MASCHINE-Eintrag darf weder im Baum noch in der
    Soll-Liste auftauchen — sonst ist die dokumentierte Ausnahme veraltet und
    es waere PII ins Repo gewandert, ohne dass die Begruendung mitgezogen wurde.
    """
    ist = _baum()
    soll = _soll_liste()
    verletzt = sorted(
        eintrag for eintrag in NUR_AUF_DER_MASCHINE
        if eintrag in ist or eintrag in soll
    )
    assert not verletzt, (
        "Diese Drop-Ins sind in NUR_AUF_DER_MASCHINE als bewusst NICHT "
        "versioniert dokumentiert, liegen aber jetzt im Repo bzw. in der "
        "Soll-Liste:\n"
        + "\n".join(f"  - {d}: {NUR_AUF_DER_MASCHINE[d]}" for d in verletzt)
        + "\n\nFix: entweder die Datei wieder entfernen — oder die Ausnahme "
        "hier streichen, weil eine Platzhalter-Form beschlossen wurde."
    )


def test_verwaistes_dropin_nicht_versioniert():
    """Das Drop-In des mit RAT-31 abgerissenen geraete-Dienstes wird geloescht,
    nicht versioniert (#1802 AC4)."""
    assert VERWAIST not in _baum(), (
        f"{VERWAIST} gehoert zu xbuddy-geraete — der Dienst ist mit RAT-31 aus "
        "dem Repo geloescht (cf0dbb1e), die Unit am Pi ist inactive/disabled. "
        "Die Datei wird entfernt, nicht versioniert."
    )


# ---------------------------------------------------------------------------
# 3. Naht zu bootstrap.sh + Platzhalter-Form
# ---------------------------------------------------------------------------
def test_jedes_dropin_verzeichnis_hat_eine_unit_in_bootstrap():
    """Ein Drop-In-Verzeichnis ohne Unit in der SVC_SRC-Map von bootstrap.sh
    landet auf der Maschine neben einer Unit, die dort nie installiert wird —
    eine Datei, die aussieht als wirke sie, und nie wirkt."""
    units = _bootstrap_units()
    ohne_unit = sorted(
        verzeichnis.name
        for verzeichnis in SYSTEMD_DIR.glob("*.service.d")
        if verzeichnis.name[: -len(".service.d")] not in units
    )
    assert not ohne_unit, (
        "Diese Drop-In-Verzeichnisse gehoeren zu keiner Unit, die "
        "deploy/bootstrap.sh installiert (SVC_SRC-Map):\n"
        + "\n".join(f"  - {d}" for d in ohne_unit)
        + "\n\nFix: Unit in SVC_SRC ergaenzen — oder das Verzeichnis auf den "
        "Namen umbenennen, unter dem der Dienst im Repo gefuehrt wird."
    )


def test_keine_absoluten_host_pfade_in_dropins():
    """Per-Instanz-Werte stehen als __XBUDDY_*__-Platzhalter (SVC-5), nicht als
    absoluter Pfad — sonst traegt das Repo den Stand EINER Maschine."""
    treffer = []
    for pfad in sorted(SYSTEMD_DIR.glob("*.service.d/*.conf")):
        for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1):
            if zeile.lstrip().startswith("#"):
                continue
            if "/home/" in zeile:
                treffer.append(f"{pfad.relative_to(REPO_ROOT)}:{nr}: {zeile.strip()}")
    assert not treffer, (
        "Absoluter Host-Pfad in einem versionierten Drop-In — erwartet ist die "
        "Platzhalter-Form aus der Tabelle in deploy/systemd/README.md "
        "(__XBUDDY_HOME__/__XBUDDY_REPO__/__XBUDDY_DATA__/__XBUDDY_PYTHON__):\n"
        + "\n".join(f"  - {t}" for t in treffer)
    )
