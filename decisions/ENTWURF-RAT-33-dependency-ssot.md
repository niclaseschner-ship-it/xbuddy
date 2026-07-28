# ENTWURF — RAT-33: Dependency-SSoT: pyproject [project.dependencies] vs. per-Service requirements.txt

> **STATUS: ENTWURF — Nic-Entscheid ausstehend. Nicht ratifiziert.**
> Vorlage für berater-runde / direkten Nic-Stempel. Datei-Name wird nach
> Ratifizierung auf `RAT-33-dependency-ssot.md` umbenannt.

- **Anlass:** Ticket #1446, ausgelöst durch #1515 (litellm in `eltern-chat/requirements.txt`
  fehlte → 6 pytest rot nach #1509). Watchdog #1403 identifizierte ursprünglich
  die Divergenz.
- **Entscheider:** Nic (Architektur-/Prozess-Entscheid, Nic-Membran)
- **Analyse-Datum:** 2026-07-28

---

## 1. Ist-Zustand: zwei Wahrheitsquellen für dieselben Pakete

### 1a. `pyproject.toml [project.dependencies]` — Root-SSoT-Kandidat

Enthält alle Pakete mit `~=`-Pin (kompatibel, Patch-Updates erlaubt, Breaking-Change gesperrt).
Kommentare belegen den Import-Beweis pro Paket (grep-basiert, nicht spekulativ).

| Paket | Pin in pyproject | Verwendung |
|---|---|---|
| `flask` | `~=3.1` | alle `service/main.py`-Dateien |
| `anthropic` | `~=0.104` | `tools/llm/_vendor/anthropic.py`, `eltern-chat/providers/claude.py` |
| `httpx` | `~=0.28` | `tools/llm/_vendor/mistral.py` |
| `Pillow` | `~=11.1` | `tools/medien_store/normalize.py` |
| `pillow-heif` | `~=1.3` | `tools/medien_store/normalize.py` |
| `litellm` | `~=1.93` | `tools/llm/_vendor/litellm.py` (RAT-26/28) |

### 1b. Per-Service requirements.txt — Fragmentiert, unvollständig

Nur zwei Services haben eine requirements.txt:

**`eltern-chat/requirements.txt`:**
```
anthropic>=0.40     # abweichend: >= statt ~= ; lower bound veraltet (real: 0.104)
litellm~=1.93       # seit #1515-Fix korrekt
```

**`photo/requirements.txt`:**
```
Pillow>=11          # abweichend: >= statt ~= ; weniger streng als pyproject
pillow-heif>=1.0    # abweichend: >= statt ~= ; weniger streng als pyproject
```

**Alle anderen Services** (hoerspiel, kibuddy, wetter, plan, familie, routine, seiten,
router, geraete, panel, controller, essen): **keine requirements.txt**.

### 1c. Divergenzen und Konflikte

| Paket | pyproject | requirements.txt | Divergenz |
|---|---|---|---|
| `anthropic` | `~=0.104` | `eltern-chat: >=0.40` | Pinning-Stil; requirements erlaubt u. U. veraltete Version |
| `Pillow` | `~=11.1` | `photo: >=11` | Pinning-Stil; requirements lässt Pillow 12+ zu (Pi hat 12.2) |
| `pillow-heif` | `~=1.3` | `photo: >=1.0` | Pinning-Stil; requirements lässt 2.x zu |
| `litellm` | `~=1.93` | `eltern-chat: ~=1.93` | Kein Inhalt-Konflikt, aber Doppelung |
| `flask`, `httpx` | in pyproject | nirgends in requirements.txt | ausschließlich in pyproject |

### 1d. Wer installiert was beim Deploy

**Produktions-Betrieb (Pi-Services, systemd):**
- Alle `xbuddy-*`-Services rufen `/home/buddy/apps/venv/bin/python` (Service-venv, `ExecStart`).
- Das Service-venv (`/home/buddy/apps/venv`) enthält alle Pakete — es wurde manuell
  gebaut und wird NICHT durch die requirements.txt-Dateien gesteuert.
- `deploy/update.sh` macht `git pull + systemctl restart` — es ruft **kein `pip install`**.
- `pyproject.toml` wird beim Deploy **nicht installiert** (kein `pip install -e .` o. Ä.).

**CI / Pytest (GitHub Actions, `pytest.yml` + `main-health.yml`):**
- Erstellt `.venv-pytest` mit `--system-site-packages` auf dem Pi-Runner.
- Installiert explizit: `pytest`, `-r eltern-chat/requirements.txt`, `-r photo/requirements.txt`.
- Der Pi-Runner hat system-weit: Flask 3.1.1, anthropic 0.104.0, httpx 0.28.1,
  Pillow 11.1.0, pillow-heif 1.3.0. **Kein litellm** im System-Python.
- `pip-Cache`-Key: `hashFiles('eltern-chat/requirements.txt', 'photo/requirements.txt')`.
- `pyproject.toml` wird in CI **nicht installiert**.

**Fazit:** Weder beim Deploy noch in CI ist `pyproject.toml` der aktive Install-Schritt.
Der produktive Betrieb hängt am manuell gepflegten Service-venv. CI hängt an den
requirements.txt-Fragmenten plus System-Paketen des Runners.

---

## 2. Optionen für SSoT

### Option A — `pyproject.toml` als einzige SSoT; requirements.txt entfallen oder werden generiert

**Mechanik:**
- `pyproject.toml [project.dependencies]` ist SSoT für alle Pakete (wie heute schon dokumentiert).
- `eltern-chat/requirements.txt` und `photo/requirements.txt` werden entweder gelöscht
  oder vollständig aus pyproject generiert (z. B. `pip install -e . --dry-run`).
- CI installiert statt `-r <svc>/requirements.txt` das Root-Package:
  `pip install -e .[dev]` oder `pip install -e .` (alle Deps aus pyproject).
- Der Service-venv bekommt ein `pip install -e .` im Setup-Skript.

**Vorteile:**
- Eine einzige Datei deklariert alle Pakete — keine Divergenz mehr möglich.
- `~=`-Pins in pyproject sind präziser als `>=` in requirements.txt.
- Cache-Key in CI einfacher (nur `hashFiles('pyproject.toml')`).
- Neue Services brauchen keine eigene requirements.txt — Dep einfach in pyproject eintragen.

**Risiken / Nachteile:**
- CI muss umgebaut werden (Install-Schritt ändern); ein-maliger, kleiner PR.
- `pip install -e .` mit `--system-site-packages` auf dem Pi-Runner: Verhalten im
  Edge-Case (Konflikte system ↔ pyproject) muss getestet werden.
- Wenn ein Service künftig eigene Deps braucht, die **nicht** alle Services teilen sollen
  (z. B. foto-spezifische Libs ohne allgemeine Nutzung), ist das mit einer Flat-Liste
  in pyproject unkomfortabel (kein Service-Scoping). Bei 6 Paketen heute kein Problem.
- Monorepo-Build-Tool-Frage: `pip install -e .` installiert ein virtuelles Root-Package,
  das keine echten Python-Module im Repo-Root hat — könnte Verwirrung stiften.

**Aufwand:** Mittel (CI-Umbau + Service-venv-Setup-Skript anpassen + requirements.txt-Löschen).

---

### Option B — requirements.txt als SSoT pro Service; pyproject nur Snapshot/Dokumentation

**Mechanik:**
- Jeder Service bekommt eine vollständige requirements.txt mit seinen echten Laufzeit-Deps.
- pyproject bleibt als Dokumentations-Snapshot, wird aber NICHT der maßgebliche Install-Punkt.
- CI und Service-venv-Setup installieren jeweils `-r <svc>/requirements.txt`.
- Bei Dep-Änderung: requirements.txt des betroffenen Service ändern, pyproject manuell mitführen.

**Vorteile:**
- Minimaler Umbau-Aufwand: CI und Deploy funktionieren schon so.
- Service-Isolierung: Jeder Service hat nur seine tatsächlichen Deps.
- Klar für neue Services: "Schreib eine requirements.txt für deinen Service."

**Risiken / Nachteile:**
- Die Wurzel des heutigen Problems bleibt: pyproject und requirements.txt driften auseinander.
  #1515 und ähnliche Incidents passieren wieder (litellm-Klasse).
- Aktuell fehlen requirements.txt für 12 Services (hoerspiel, kibuddy, wetter, plan, ...):
  das wäre ein erheblicher Initialaufwand — und die fehlenden Services greifen doch auf
  systemweit installierten Pakete zurück (Flask-Abhängigkeit z. B. hoerspiel/main.py).
- "Pyproject nur Snapshot" lädt zu Drift ein, weil niemand die Synchronisierung erzwingt.
- Pinning-Stil-Divergenz (`~=` vs `>=`) bleibt ein Pflege-Problem.

**Aufwand:** Hoch (12 neue requirements.txt-Dateien; Konsistenz-Disziplin dauerhaft nötig).

---

### Option C — Beide behalten + maschineller Konsistenz-Test

**Mechanik:**
- `pyproject.toml` bleibt SSoT für Pinning-Stil und Versions-Deklaration.
- requirements.txt bleibt als Install-Eingabe für CI und Service-venv.
- Ein neuer CI-Check (z. B. `tools/check_deps_consistent.py`) vergleicht
  pyproject-Deps gegen alle requirements.txt und schlägt Alarm bei Drift.
- Bei Dep-Änderung: pyproject UND requirements.txt(s) updaten; Test verhindert Vergessen.

**Vorteile:**
- Kein Umbau des CI-Install-Pfads nötig.
- Drift wird künftig maschinell erkannt (verhindert #1515-Klasse).
- Service-Granularität bleibt erhalten.

**Risiken / Nachteile:**
- Zwei Stellen müssen bei jeder Dep-Änderung synchron gehalten werden — mehr Pflege-Overhead.
- Der Konsistenz-Test selbst ist Entwicklungsaufwand (klein, aber endlich).
- Fundamentale Spannung bleibt: Monorepo hat keine echte single-file SSoT.
- requirements.txt-Fragments haben keine vollständige Abdeckung (12 Services ohne Datei) —
  der Konsistenz-Test löst das Abdeckungsproblem nicht, er vergleicht nur was existiert.

**Aufwand:** Gering (ein kleiner Test-Skript + requirements.txt auf ~=–Pins umstellen).

---

## 3. Empfehlung (Analyse-Ergebnis; Entscheid liegt bei Nic)

**Empfohlen: Option A** — pyproject als einzige SSoT, requirements.txt entfallen.

**Begründung:**
1. **Wurzelursache von #1515:** Zwei Wahrheitsquellen + keine Maschinen-Erzwingung = Drift
   und Incidents. Option A beseitigt die Wurzel, Optionen B und C lindern sie nur.
2. **Realität:** pyproject ist heute schon dokumentierter Anspruchs-SSoT ("grep-belegt,
   keine Spekulation" — pyproject.toml:5); requirements.txt ist ein nicht-ratifiziertes
   Fragment, das organisch gewachsen ist.
3. **Scope passt:** Mit 6 Paketen und einem Monorepo ohne Service-spezifische Dep-Konflikte
   ist Flat-pyproject praktikabel. Wenn ein künftiger Service eine isolierte Dep braucht
   (unwahrscheinlich heute), kann eine service-lokale extras-Sektion in pyproject oder
   ein selektives requirements-Override ergänzt werden.
4. **Aufwand ist klein und einmalig:** CI-Install-Schritt + Service-venv-Setup-Skript
   anpassen; 1–2 PRs, kein laufender Pflege-Overhead.
5. **Anti-Muster-Check:** Option A ersetzt zwei Dateien durch eine — Constitution Nr. 2
   (Einfachheit) spricht dafür.

**Wenn Nic Option C wählt** (geringster kurzfristiger Aufwand), sollte als Mindest-Maßnahme
ein Konsistenz-Test gebaut werden, der pyproject-Deps gegen requirements.txt vergleicht
und bei Drift CI rot macht — die #1515-Klasse wäre damit künftig CI-blockiert statt stumm
durchzulaufen.

---

## 4. Offene Fragen für Nic

1. Welche Option? (A / B / C)
2. Falls Option A: Soll `pip install -e .` oder `pip install -r <(pip-compile pyproject.toml)`
   der CI-Install-Weg sein? (pip-compile = deterministisch, aber Zusatz-Tool)
3. Soll das Service-venv-Setup-Skript dokumentiert/versioniert werden (liegt heute nicht im Repo)?
   Das wäre unabhängig von der SSoT-Wahl eine Härtung.

---

## Belege
- Ticket #1446 (Analyse-Auftrag), #1515 (Auslöser, litellm-Incident), #1403 (Watchdog-Fund)
- `pyproject.toml:1-23` (aktueller Stand der project.dependencies)
- `eltern-chat/requirements.txt:1-6`, `photo/requirements.txt:1-8`
- `.github/workflows/pytest.yml:35-51`, `.github/workflows/main-health.yml:46-70`
- `deploy/update.sh` (kein pip install im Deploy-Pfad)
- Pi-Service-venv: `/home/buddy/apps/venv/bin/python` (`ExecStart` in allen systemd-Units),
  enthält litellm 1.93.0, anthropic 0.97.0, Pillow 12.2.0 — abweichend von pyproject-Pins

Refs #1446 #1515 #1403
