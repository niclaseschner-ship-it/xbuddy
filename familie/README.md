# Familien-Registry

V1-Implementierung der Spec [`specs/platform/familie.md`](../specs/platform/familie.md). Refs #38.

Die zentrale Liste der Personen einer Familie — Erwachsene und Kinder — mit
Name, Profilfoto, Ring-Farbe und optionalen Kontakt-Merkmalen (E-Mail,
Telegram-ID). Eine Instanz beschreibt genau eine Familie (FAM-1). Die Registry
besitzt diese Daten und stellt sie über eine Schnittstelle bereit; Konsumenten
(Plan-Buddy-App, später Eltern-Chat) sind Nutzer, nicht Mit-Eigentümer (E-FAM-1).

**V1-Scope:** nur Identität — keine Rollen und Rechte (E-FAM-2). Berechtigung
bleibt beim Eltern-Chat (Telegram-Gruppen-Mitgliedschaft).

## Start

```bash
# Minimal (lokal, HTTP, familie.json im Arbeitsverzeichnis, fotos/ daneben)
python3 familie/main.py

# Mit Registry-Pfad und HTTPS (Pi-Dev-Setup)
python3 familie/main.py \
  --registry /tmp/xbuddy-serve/familie/familie.json \
  --cert /tmp/xbuddy-serve/cert.pem \
  --key  /tmp/xbuddy-serve/key.pem
```

CLI > ENV > config.json > Code-Defaults (FAM-9). Fehlt die Registry-Datei beim
Start, läuft der Dienst mit leerer Familie weiter und protokolliert eine
Warnung (FAM-6).

ENV-Variablen (CONFIG-5, nach `<KOMPONENTE>_<KEY>`-Schema):

| Variable                 | Bedeutung                       |
|--------------------------|---------------------------------|
| `FAMILIE_REGISTRY`       | Pfad zur Registry-Datei         |
| `FAMILIE_FOTOS`          | Foto-Verzeichnis                |
| `FAMILIE_LISTEN_HOST`    | Bind-Adresse (Default: `127.0.0.1`) |
| `FAMILIE_LISTEN_PORT`    | Bind-Port (Default: `5010`)     |
| `FAMILIE_LOG_LEVEL`      | Log-Level (Default: `INFO`)     |

Runtime-Konfig (`familie/config.json`) — Override über `listen_host`,
`listen_port`, `log_level`. CLI-Flags `--host`, `--port`, `--log-level`
sind Test-Werkzeug (FAM-9).

## Service-Topologie

Die Spec lässt offen, ob die Registry ein eigener Dienst ist oder mitgehostet
wird. V1-Entscheidung: eine schlanke eigenständige Flask-App — Geschwister von
[`router/`](../router/) und [`eltern-chat/`](../eltern-chat/). Kein
Dienst-Verbund auf Vorrat; `main.py:app` ist ein gewöhnliches Flask-Objekt und
bei späterem Bedarf von einem Mit-Host importierbar.

## Endpunkte

| Endpunkt | Zweck | Spec |
|---|---|---|
| `GET /api/v1/familie/personen` | alle Personen (ohne Foto-Binär) | FAM-7 |
| `GET /api/v1/familie/personen/<id>` | eine Person je `id` | FAM-7 |
| `GET /api/v1/familie/foto/<id>` | Profilfoto; 200 mit Foto / 404 ohne | FAM-8 |

## Dateien

- `registry.py` — Personen-Modell (FAM-3), Ring-Palette (FAM-4), Laden der
  Registry-Datei (FAM-6), Personen- und Foto-Auflösung (FAM-7/FAM-8).
- `main.py` — Flask-App mit den HTTP-Endpunkten + Entrypoint, Konfiguration (FAM-9).
- `familie.example.json` — Format der Registry-Datei. `familie.json` selbst ist
  per Repo-`.gitignore` ausgeschlossen — pro Instanz separat gepflegt (FAM-6).

## Daten je Instanz

`familie.json` und das Foto-Verzeichnis (Default `fotos/` neben der
Registry-Datei, FAM-9) sind Per-Instanz-Daten und gehören **nicht** ins Repo
(FAM-6, `.gitignore`). Die Datei wird in V1 von Hand gepflegt — ein UI dafür ist
ausdrücklich Out-of-Scope.

## Ring-Farb-Palette (FAM-4)

`blue`, `orange`, `green`, `red`, `purple`, `teal`, `gray`. Endlich — mehr
Personen als Farben ist eine Spec-Änderung, kein Config-Wert. `gray` ist die
Farbe für Personen ohne feste Zuordnung.

## Tests

```bash
python3 -m pytest familie/tests/ -v
```

Ein automatisierter Test je Requirement-ID (FAM-10), ohne Netz; der
Foto-Endpunkt wird über den Flask-Testclient geprüft.
