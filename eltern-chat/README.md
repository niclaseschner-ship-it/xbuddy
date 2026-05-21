# Eltern-Chat

V1-Implementierung der Spec [`specs/platform/eltern-chat.md`](../specs/platform/eltern-chat.md). Refs #27.

Ein konversationeller Kanal zwischen Eltern und XBuddy: ein LLM-Agent in einer
Telegram-Familien-Gruppe, der Eltern-Aufgaben aus einem definierten Katalog
übernimmt. Eigener Prozess, Geschwister von [`router/`](../router/) und
[`controller/`](../controller/).

## Start

```bash
pip install -r eltern-chat/requirements.txt

# Geheimnisse nur über Umgebungsvariablen (EC-15):
export ELTERNCHAT_BOT_TOKEN="<telegram-bot-token>"
export ELTERNCHAT_PROVIDER_API_KEY="<anthropic-api-key>"

# Familien-Gruppen-Chat-ID per Env oder config.json:
export ELTERNCHAT_FAMILY_GROUP_CHAT_ID="-1000000000000"

python3 eltern-chat/main.py --config eltern-chat/config.json --db eltern-chat/conversations.db
```

Konfigurations-Priorität: `ELTERNCHAT_*`-Env > `config.json` > Code-Default
(EC-15). Geheimnisse ausschließlich aus Env.

## Architektur

| Datei | Petrantwortung | Spec |
|---|---|---|
| `main.py` | Entrypoint, Polling-Loop, **Orchestrierung + Sicherheits-Gates** | E-EC-2/E-EC-4 |
| `config.py` | Konfigurations-Auflösung | EC-15 |
| `telegram.py` | Telegram-Kanal-Adapter (Polling) | E-EC-2 |
| `authz.py` | Berechtigung — Live-Mitgliedschaftsprüfung | EC-2/EC-3 |
| `confirm.py` | Bestätigung schreibender Aufgaben (Bestätigungswort) | EC-10/E-EC-7 |
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
kontrollierte Doppelung ersetzt (EC-17). Läufe gegen einen echten Anbieter sind
getrennt und opt-in — sie brauchen einen API-Schlüssel und sind kein Teil eines
Standard-Durchlaufs.

## Deployment-Hinweise

- Der Bot braucht **keine** Admin-Rechte in der Familien-Gruppe (E-EC-7).
- Die Gesprächs-Datenbank (`conversations.db`) ist je Instanz separat und per
  Repo-`.gitignore` ausgeschlossen (EC-16). Fehlt sie, wird sie leer angelegt.
