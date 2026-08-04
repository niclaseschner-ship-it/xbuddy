# Eltern-Chat

V1-Implementierung der Specs [`eltern-chat.md`](../specs/platform/eltern-chat.md)
und [`eltern-chat-onboarding.md`](../specs/platform/eltern-chat-onboarding.md).
Refs #27, #33.

Ein konversationeller Kanal zwischen Eltern und XBuddy: ein LLM-Agent in einer
Telegram-Familien-Gruppe, der Eltern-Aufgaben aus einem definierten Katalog
übernimmt. Eigener Prozess, Geschwister von [`router/`](../router/) und
[`controller/`](../controller/).

## Start

```bash
# Laufzeit-Abhängigkeiten kommen aus dem EINEN Dependency-SSoT pyproject.toml
# (RAT-33 Option A, #1534) — installiere sie repo-weit in dein venv:
pip install /home/buddy/repos/xbuddy   # bzw. den Pfad deines Checkouts (pip install .)

# Pflicht: der Telegram-Bot-Token (nur über Umgebungsvariable, EC-15).
export ELTERNCHAT_BOT_TOKEN="<telegram-bot-token>"

python3 eltern-chat/main.py \
  --config eltern-chat/config.json \
  --db    eltern-chat/conversations.db \
  --store eltern-chat/onboarding-store.json
```

Mehr braucht eine **frische Instanz nicht**: ohne KI-Anbieter-Key startet der
Bot im **Onboarding-Modus** (ONB-1) und richtet sich per Chat selbst ein —
sobald er einer Telegram-Gruppe hinzugefügt wird (siehe Abschnitt Onboarding).

Wer Key und Familien-Gruppe vorab setzen will (überspringt das Onboarding):

```bash
export ELTERNCHAT_PROVIDER_API_KEY="<anthropic-api-key>"
export ELTERNCHAT_FAMILY_GROUP_CHAT_ID="-1000000000000"
```

Konfigurations-Priorität: `ELTERNCHAT_*`-Env > `config.json` > Onboarding-Speicher
> Code-Default (EC-15). Geheimnisse nie in einer Datei im Repo.

## Onboarding

Eine Instanz ohne Anbieter-Key kann noch keine KI nutzen. Der Onboarding-Modus
(Spec `eltern-chat-onboarding.md`) überbrückt das deterministisch:

1. Der Bot wird einer Telegram-Gruppe hinzugefügt → er sendet eine
   Einstiegs-Nachricht (ONB-2).
2. Ein Familienmitglied schickt ihm **im Privatchat** den Anbieter-Key (ONB-3).
3. Der Bot validiert den Key per Test-Aufruf (ONB-4), speichert ihn (ONB-5) und
   bindet die Gruppe als Familien-Gruppe (ONB-6).
4. Danach wechselt er in den KI-Modus (ONB-7) — die regulären Anforderungen
   `eltern-chat.md` (EC-4 ff.) gelten.

## Architektur

| Datei | Verantwortung | Spec |
|---|---|---|
| `main.py` | Entrypoint, Polling-Loop, **Orchestrierung + Sicherheits-Gates** | E-EC-2/E-EC-4 |
| `config.py` | Konfigurations-Auflösung | EC-15 |
| `telegram.py` | Telegram-Kanal-Adapter (Polling) | E-EC-2 |
| `authz.py` | Berechtigung — Live-Mitgliedschaftsprüfung | EC-2/EC-3 |
| `confirm.py` | Bestätigung schreibender Aufgaben (Bestätigungswort) | EC-10/E-EC-7 |
| `onboarding.py` | Deterministischer Onboarding-Flow (kein LLM) | ONB-1…ONB-8 |
| `onboarding_store.py` | Persistenter Speicher für Key & Familien-Gruppe | ONB-5 |
| `history.py` | Gesprächsverlauf, SQLite, je Chat | EC-6/EC-16 |
| `model.py` | Kanonisches, anbieter-neutrales Modell | E-EC-6 |
| `agent.py` | Dünner Agent-Loop (kein Framework) | E-EC-5 |
| `tasks.py` | Aufgaben-Katalog als Rahmen | EC-8 |
| `providers/` | KI-Anbieter-Adapter (V1: Claude) | E-EC-6/EC-11 |

**Sicherheits-Architektur (E-EC-4):** Berechtigung (`authz`) und Bestätigung
(`confirm`) liegen außerhalb des Agent-Loops. `agent.py` importiert beide nicht
— der LLM kann die Gates nicht umgehen, weil er sie nie aufruft.

## Aufgaben-Katalog

`tasks.py` ist der Rahmen (Registry, lesend/schreibend). V1 registriert KEINE
konkrete Aufgabe — die erste Aufgabe kommt aus einem eigenen Spec+Ticket (EC-8)
und ergänzt `build_catalog()` additiv.

## Tests

```bash
python3 -m pytest eltern-chat/tests/ -v
```

Die Suite läuft reproduzierbar und ohne Netz: der KI-Anbieter ist durch eine
kontrollierte Doppelung ersetzt (EC-17/ONB-9). Läufe gegen einen echten
Anbieter sind getrennt und opt-in.

## Deployment-Hinweise

- Der Bot braucht **keine** Admin-Rechte in der Familien-Gruppe (E-EC-7).
- Gesprächs-Datenbank (`conversations.db`) und Onboarding-Speicher
  (`onboarding-store.json`) sind je Instanz separat und per Repo-`.gitignore`
  ausgeschlossen (EC-16/ONB-5). Fehlen sie, werden sie angelegt.
- Der Onboarding-Speicher enthält den Anbieter-Key — Dateirechte 0600.
