"""Tests für die Neustart-Bremse (StartLimit vs. RestartSec×Burst), #1801.

Der Kern-Befund von #1801: `xbuddy-plan` und `xbuddy-familie` liefen live mit
`RestartSec=10s` und einem StartLimit-Fenster, das GENAUSO LANG ist wie die
Wartezeit zwischen zwei Neustarts. Damit kann der Neustart-Zähler nie fünf
Versuche INNERHALB des Fensters sammeln: jeder Versuch fällt in ein frisch
geöffnetes Fenster und setzt es zurück. Die Bremse existiert, greift aber
rechnerisch nie (Beleg: 14 Abstürze je Dienst am 2026-08-10, ohne dass
systemd eingriff).

WICHTIG — und das ist der Punkt, an dem eine frühere Fassung dieses Tests
falsch lag: keine der 13 `*/*.service`-Vorlagen im Repo setzt
`StartLimitIntervalSec`/`StartLimitBurst` überhaupt. „Nirgends gesetzt"
bedeutet aber NICHT „kein Fenster" — systemd wendet dann seinen Vorgabewert
an, und der ist `StartLimitIntervalSec=10s` / `StartLimitBurst=5`
(`systemctl show -p DefaultStartLimitIntervalSec -p DefaultStartLimitBurst`,
Stand systemd 257). Bei `RestartSec=10s` (jede Vorlage) ist das EXAKT die
kaputte #1801-Konfiguration. Ein Fenster, das fehlt, ist also nicht der
neutrale Fall, sondern der Fehlerfall selbst — und muss das Fenster (nicht
den Test) ROT machen, kein `SKIPPED`.

Der Fix sind versionierte Drop-Ins unter `deploy/systemd/xbuddy-<comp>.
service.d/restart-window.conf`, die `StartLimitIntervalSec` explizit über
`RestartSec × StartLimitBurst` heben — bisher nur für plan und familie
(#1801-Scope).

Dieser Test prüft die RECHNUNG, nicht die konkrete Zahl — für jede
Unit-Vorlage im Repo (Basis-Unit + ihre Repo-Drop-Ins unter deploy/systemd/,
sonst der systemd-Default) muss gelten:

    StartLimitIntervalSec > RestartSec × StartLimitBurst

Das fängt auch die nächste Unit, die jemand mit derselben Fehlkonfiguration
anlegt — neu UND ohne jedes StartLimit, denn dann greift derselbe kaputte
Default wie bei plan/familie vor #1801.

## Der Schuldstand

Die 11 übrigen Services (`_BEKANNTER_SCHULDSTAND_STARTLIMIT_FEHLT`, unten)
haben HEUTE dieselbe Fehlkonfiguration wie plan/familie vor diesem Ticket.
Sie hier mitzureparieren wäre Scope-Bruch (#1801 ist im Contract explizit auf
plan/familie verscoped); sie stillschweigend rot zu lassen würde die Suite
unbrauchbar machen (jeder Lauf rot, niemand schaut mehr hin). Deshalb: ein
BENANNTER Schuldstand, kein Ausnahme-SKIP ohne Adresse — jede Unit, die
NICHT auf der Liste steht, muss gesund sein, wird also mit ROT sanktioniert.

Auflösung braucht ZWEI Schritte mit zwei verschiedenen Besitzern (nicht
einen — elf Drop-Ins anlegen, solange der Ausroll-Kanal nicht trägt, wäre
genau das Muster, das #1801 gerade behebt: eine Bremse im Repo, die
nirgends greift):

  1. **#1883** legt die elf fehlenden `restart-window.conf`-Drop-Ins an
     (dieselbe Rechnung wie plan/familie) — das ist die Handlung, die diese
     Liste schrumpfen lässt.
  2. **#1802** besitzt den Ausroll-Kanal (`deploy/bootstrap.sh` rollt
     Drop-Ins grundsätzlich nicht aus, siehe deploy/systemd/README.md) —
     ohne #1802 landet ein #1883-Drop-In im Repo, aber nie in `/etc`.

Eine Zeile fällt erst dann zurecht aus dieser Liste, wenn BEIDES für den
jeweiligen Dienst zutrifft: Drop-In existiert im Repo UND ist live
ausgerollt (`systemctl show <svc> -p StartLimitIntervalUSec` zeigt den
neuen Wert, nicht mehr den systemd-Default). Eine Selbstprüfung
(`test_schuldstand_ist_noch_kaputt` weiter unten) hält die Liste in diese
Richtung ehrlich: repariert sich der Repo-Zustand, ohne dass die Zeile
gestrichen wird, schlägt sie an.

Die andere Richtung — die Liste bleibt Jahre unverändert stehen, niemand
fragt nach — sichert keine Selbstprüfung ab, denn "unverändert" ist ohne
Zeitbezug nicht von "erledigt" zu unterscheiden. Deshalb ein Datum:
**Reviewfällig ab 2026-11-17** (drei Monate nach Anlage dieses Tests,
2026-08-17). Wer nach diesem Datum auf diese Liste stößt, prüft #1883 und
#1802 nach, ob sie noch offen sind, statt die Liste für ewig gültig zu
halten.

Lauf: python3 -m pytest deploy/tests/test_restart_bremse.py -v -rs
"""

import glob
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# systemd-Defaults, wenn eine Unit die Direktive nirgends setzt (systemd 257,
# `systemctl show -p DefaultStartLimitIntervalSec -p DefaultStartLimitBurst`).
_DEFAULT_START_LIMIT_INTERVAL_SEC = 10.0
_DEFAULT_START_LIMIT_BURST = 5
_DEFAULT_RESTART_SEC = 0.1  # 100ms

_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(ms|s|min|h)?$")
_UNIT_FACTOR = {"ms": 0.001, "s": 1.0, "min": 60.0, "h": 3600.0}

# Benannter Schuldstand (#1801): diese Vorlagen setzen KEIN StartLimit-Fenster
# — weder in der Basis-Unit noch in einem deploy/systemd/-Drop-In — und hängen
# damit am systemd-Default (10s/5), der bei RestartSec=10s EXAKT die
# #1801-Fehlkonfiguration ist.
#
# Zwei Besitzer, zwei Schritte (siehe Modul-Docstring "Der Schuldstand" für
# die Begründung, warum beide gebraucht werden):
#   #1883 — legt die elf restart-window.conf-Drop-Ins im Repo an.
#   #1802 — rollt Drop-Ins auf die Maschine aus (bootstrap.sh tut das heute
#           nicht).
# Bewusst NICHT in #1801 mitgefixt (Contract-Scope: nur plan/familie).
#
# Reviewfällig ab 2026-11-17 — siehe Modul-Docstring. Jede Zeile fällt raus,
# sobald der jeweilige Drop-In EXISTIERT UND live ausgerollt ist;
# test_schuldstand_ist_noch_kaputt hält die Liste in diese Richtung ehrlich.
_BEKANNTER_SCHULDSTAND_STARTLIMIT_FEHLT = {
    "eltern-chat/eltern-chat.service",
    "essen/essen.service",
    "hoerspiel/hoerspiel-emil.service",
    "hoerspiel/hoerspiel-finn.service",
    "hoerspiel/hoerspiel.service",
    "kibuddy/kibuddy.service",
    "panel/panel.service",
    "photo/photo.service",
    "routine/routine.service",
    "seiten/seiten.service",
    "wetter/wetter.service",
}


def _to_seconds(value):
    """Wandelt einen systemd-Zeitwert (z. B. '10', '10s', '2min') in Sekunden."""
    m = _DURATION_RE.match(value.strip())
    if not m:
        raise ValueError(f"Unbekanntes systemd-Zeitformat: {value!r}")
    num = float(m.group(1))
    unit = m.group(2) or "s"
    return num * _UNIT_FACTOR[unit]


def _parse_directives(path):
    """Liest 'Key=Value'-Direktiven je Abschnitt aus einer systemd-Unit-/
    Drop-In-Datei. Letzter Wert je Key gewinnt (systemd-Verhalten bei
    einwertigen Direktiven wie RestartSec=/StartLimitIntervalSec=)."""
    sections = {}
    current = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1]
                sections.setdefault(current, {})
                continue
            if current is None or "=" not in line:
                continue
            key, _, value = line.partition("=")
            sections[current][key.strip()] = value.strip()
    return sections


def _dropin_dir_for(unit_path, repo_root=REPO_ROOT):
    comp = os.path.splitext(os.path.basename(unit_path))[0]
    return os.path.join(repo_root, "deploy", "systemd", f"xbuddy-{comp}.service.d")


def _layered_value(unit_path, section, key, repo_root=REPO_ROOT):
    """Liest EINE Direktive aus Basis-Unit + Repo-Drop-Ins
    (deploy/systemd/xbuddy-<comp>.service.d/*.conf, alphabetisch geladen wie
    systemd das tut — letzter Wert gewinnt). Gibt den rohen String zurück
    oder None, wenn die Direktive nirgends steht.

    Das ist die EINE Stelle, an der systemds Überlagerungsregel (Basis, dann
    Drop-Ins) modelliert wird — sowohl RestartSec als auch
    StartLimitIntervalSec/-Burst laufen hier durch, damit ein künftiger
    Drop-In, der RestartSec verändert, nicht an einer der beiden Stellen
    unbemerkt bleibt (das war der Fehler in einer Vorfassung dieses Tests).
    """
    value = _parse_directives(unit_path).get(section, {}).get(key)
    dropin_dir = _dropin_dir_for(unit_path, repo_root=repo_root)
    if os.path.isdir(dropin_dir):
        for conf in sorted(glob.glob(os.path.join(dropin_dir, "*.conf"))):
            conf_value = _parse_directives(conf).get(section, {}).get(key)
            if conf_value is not None:
                value = conf_value
    return value


def _effective_restart_sec(unit_path, repo_root=REPO_ROOT):
    """RestartSec aus Basis-Unit + Repo-Drop-Ins (siehe `_layered_value`),
    sonst der systemd-Default (100ms).

    `repo_root` ist injizierbar, damit Tests eine synthetische Repo-Struktur
    in tmp_path prüfen können, ohne das echte Repo zu berühren.
    """
    raw = _layered_value(unit_path, "Service", "RestartSec", repo_root=repo_root)
    return _to_seconds(raw) if raw is not None else _DEFAULT_RESTART_SEC


def _effective_start_limit(unit_path, repo_root=REPO_ROOT):
    """Effektives (StartLimitIntervalSec, StartLimitBurst) aus Basis-Unit +
    Repo-Drop-Ins (siehe `_layered_value`), sonst der systemd-Default
    (10s/5). Gibt IMMER ein konkretes Wertepaar zurück — ein fehlendes
    Fenster ist der Fehlerfall, nicht „kein Fenster, also übersprungen"
    (das war der Bug in der Vorfassung dieses Tests).

    `repo_root` ist injizierbar, damit Tests eine synthetische Repo-Struktur
    in tmp_path prüfen können, ohne das echte Repo zu berühren.
    """
    interval = _layered_value(unit_path, "Unit", "StartLimitIntervalSec", repo_root=repo_root)
    burst = _layered_value(unit_path, "Unit", "StartLimitBurst", repo_root=repo_root)
    interval_s = _to_seconds(interval) if interval is not None else _DEFAULT_START_LIMIT_INTERVAL_SEC
    burst_n = int(burst) if burst is not None else _DEFAULT_START_LIMIT_BURST
    return interval_s, burst_n


def _bremse_greift(unit_path, repo_root=REPO_ROOT):
    """True, wenn das wirksame StartLimit-Fenster größer ist als
    RestartSec × StartLimitBurst — die Bremse kann dann rechnerisch greifen."""
    interval_s, burst_n = _effective_start_limit(unit_path, repo_root=repo_root)
    restart_sec = _effective_restart_sec(unit_path, repo_root=repo_root)
    return interval_s > restart_sec * burst_n


def _iter_unit_paths():
    return sorted(glob.glob(os.path.join(REPO_ROOT, "*", "*.service")))


# ── Regression über alle Unit-Vorlagen im Repo ─────────────────────────────

@pytest.mark.parametrize(
    "unit_path", _iter_unit_paths(), ids=lambda p: os.path.relpath(p, REPO_ROOT)
)
def test_startlimit_fenster_ist_groesser_als_restart_takt(unit_path):
    rel = os.path.relpath(unit_path, REPO_ROOT)
    interval_s, burst_n = _effective_start_limit(unit_path)
    restart_sec = _effective_restart_sec(unit_path)
    window_needed = restart_sec * burst_n
    greift = interval_s > window_needed

    if rel in _BEKANNTER_SCHULDSTAND_STARTLIMIT_FEHLT:
        pytest.skip(
            f"{rel}: bekannter Schuldstand (#1801; Drop-In anlegen ist #1883, "
            f"Live-Ausrollen ist #1802 — beides gebraucht, siehe Modul-"
            f"Docstring) — wirksames StartLimitIntervalSec={interval_s}s "
            f"(kein Drop-In, systemd-Default) ist nicht größer als "
            f"RestartSec({restart_sec}s) × Burst({burst_n}) = {window_needed}s. "
            "Reviewfällig ab 2026-11-17."
        )

    assert greift, (
        f"{rel}: StartLimitIntervalSec={interval_s}s ist nicht größer als "
        f"RestartSec({restart_sec}s) × StartLimitBurst({burst_n}) = "
        f"{window_needed}s — die Neustart-Bremse kann rechnerisch nie fünf "
        "Versuche im Fenster zählen (#1801). Falls das ein bekannter, noch "
        "nicht ausgerollter Fall ist: in "
        "_BEKANNTER_SCHULDSTAND_STARTLIMIT_FEHLT eintragen, NICHT diesen "
        "Test schwächen."
    )


def test_schuldstand_liste_zeigt_auf_echte_units():
    """Tippfehler-Schutz: jede Zeile im Schuldstand muss eine real gefundene
    Unit-Vorlage treffen, sonst prüft sie nichts (stille Lücke)."""
    gefundene = {os.path.relpath(p, REPO_ROOT) for p in _iter_unit_paths()}
    unbekannt = _BEKANNTER_SCHULDSTAND_STARTLIMIT_FEHLT - gefundene
    assert not unbekannt, f"Schuldstand nennt Units, die es nicht gibt: {unbekannt}"


def test_schuldstand_ist_noch_kaputt():
    """Hält den Schuldstand ehrlich: steht eine Unit noch auf der Liste,
    obwohl sie längst ein Drop-In hat und die Bremse greift, ist das kein
    Erfolg — das ist eine vergessene Streichung, die den nächsten Leser
    in die Irre führt."""
    fertig_aber_noch_gelistet = {
        rel for rel in _BEKANNTER_SCHULDSTAND_STARTLIMIT_FEHLT
        if _bremse_greift(os.path.join(REPO_ROOT, rel))
    }
    assert not fertig_aber_noch_gelistet, (
        "Diese Units sind repariert (Bremse greift bereits), stehen aber "
        f"noch im Schuldstand: {fertig_aber_noch_gelistet} — aus "
        "_BEKANNTER_SCHULDSTAND_STARTLIMIT_FEHLT streichen."
    )


def test_plan_und_familie_haben_repo_drop_in():
    """AC1-Beleg: beide Ticket-Dienste tragen jetzt ein explizites Fenster,
    das die Bremse rechnerisch greifen lässt — und stehen NICHT im
    Schuldstand."""
    for comp in ("plan", "familie"):
        rel = f"{comp}/{comp}.service"
        unit_path = os.path.join(REPO_ROOT, rel)
        assert os.path.isfile(unit_path), unit_path
        assert rel not in _BEKANNTER_SCHULDSTAND_STARTLIMIT_FEHLT
        interval_s, burst_n = _effective_start_limit(unit_path)
        assert interval_s == 120.0
        assert burst_n == 5
        assert _bremse_greift(unit_path)


# ── Der Rückfall, direkt geprüft (unabhängig vom Repo-Zustand) ─────────────

def _write_unit(tmp_path, comp, restart_sec, unit_extra=""):
    comp_dir = tmp_path / comp
    comp_dir.mkdir()
    unit_path = comp_dir / f"{comp}.service"
    unit_path.write_text(
        f"[Unit]\n{unit_extra}\n[Service]\nRestart=on-failure\nRestartSec={restart_sec}\n",
        encoding="utf-8",
    )
    return str(unit_path)


def _write_dropin(tmp_path, comp, interval_sec, burst, restart_sec=None, filename="restart-window.conf"):
    dropin_dir = tmp_path / "deploy" / "systemd" / f"xbuddy-{comp}.service.d"
    dropin_dir.mkdir(parents=True, exist_ok=True)
    conf = dropin_dir / filename
    lines = [f"[Unit]\nStartLimitIntervalSec={interval_sec}\nStartLimitBurst={burst}\n"]
    if restart_sec is not None:
        lines.append(f"[Service]\nRestartSec={restart_sec}\n")
    conf.write_text("".join(lines), encoding="utf-8")


def test_rueckfall_fehlendes_fenster_ist_rot(tmp_path):
    """Der Fall, den die Vorfassung dieses Tests fälschlich übersprang: KEIN
    Drop-In, keine Basis-Unit-Direktive — der wirksame Wert ist der
    systemd-Default (10s/5), und bei RestartSec=10s ist das exakt die
    kaputte #1801-Konfiguration. Muss ROT sein, nicht übersprungen."""
    unit_path = _write_unit(tmp_path, "ohne_fenster", restart_sec=10)
    # Bewusst KEIN _write_dropin(...) — das ist der Punkt dieses Tests.

    interval_s, burst_n = _effective_start_limit(unit_path, repo_root=str(tmp_path))
    assert (interval_s, burst_n) == (10.0, 5), (
        "Ohne Drop-In muss der systemd-Default greifen, nicht 'kein Wert'."
    )
    assert not _bremse_greift(unit_path, repo_root=str(tmp_path)), (
        "Eine Unit ganz ohne StartLimit-Fenster hat die #1801-Fehlkonfiguration "
        "per Default — die Prüfung MUSS das als kaputt erkennen (rot), sonst "
        "fängt der Test keine neue Unit mit derselben Lücke ab."
    )


def test_rueckfall_kaputtes_fenster_wird_erkannt(tmp_path):
    """Fenster <= RestartSec × Burst muss die Prüfung rot machen — genau der
    Fehler aus #1801 (RestartSec=10s, Fenster=10s, Burst=5: 10 <= 50)."""
    unit_path = _write_unit(tmp_path, "kaputt", restart_sec=10)
    _write_dropin(tmp_path, "kaputt", interval_sec=10, burst=5)

    assert not _bremse_greift(unit_path, repo_root=str(tmp_path)), (
        "Testfixtur baut absichtlich die #1801-Fehlkonfiguration nach — "
        "die Invariante MUSS hier verletzt sein, sonst prüft der Test nichts."
    )


def test_rueckfall_repariertes_fenster_besteht(tmp_path):
    """Das Gegenstück: ein Fenster deutlich über RestartSec × Burst besteht."""
    unit_path = _write_unit(tmp_path, "repariert", restart_sec=10)
    _write_dropin(tmp_path, "repariert", interval_sec=120, burst=5)

    assert _bremse_greift(unit_path, repo_root=str(tmp_path))


def test_rueckfall_dropin_ueberschreibt_auch_restart_sec(tmp_path):
    """`_effective_start_limit` überlagert Basis-Unit + Repo-Drop-Ins bereits
    korrekt; `_effective_restart_sec` muss dieselbe Überlagerung fahren, sonst
    entsteht dieselbe Lücke, die die Vorfassung dieses Tests schon einmal
    hatte — nur eine Ebene tiefer: ein künftiger Drop-In, der RestartSec
    anhebt, würde die reale Invariante brechen, während die Prüfung mit dem
    alten (Basis-Unit-)Wert weiterrechnet und grün bleibt."""
    unit_path = _write_unit(tmp_path, "ueberschrieben", restart_sec=10)
    _write_dropin(tmp_path, "ueberschrieben", interval_sec=120, burst=5)
    # Zweiter, alphabetisch später geladener Drop-In hebt RestartSec an —
    # unabhängig vom ersten, so wie systemd mehrere *.conf-Dateien im selben
    # .service.d/-Verzeichnis überlagert.
    _write_dropin(
        tmp_path, "ueberschrieben", interval_sec=120, burst=5,
        restart_sec=60, filename="zz-slower-restart.conf",
    )

    assert _effective_restart_sec(unit_path, repo_root=str(tmp_path)) == 60.0, (
        "RestartSec aus einem Drop-In wird ignoriert — _effective_restart_sec "
        "liest offenbar nur die Basis-Unit."
    )
    assert not _bremse_greift(unit_path, repo_root=str(tmp_path)), (
        "Mit RestartSec=60s (per Drop-In) und Fenster=120s ist 120 <= 60×5=300 "
        "— die Invariante MUSS das als kaputt erkennen, nicht mit dem "
        "veralteten RestartSec=10s aus der Basis-Unit grün bleiben."
    )
