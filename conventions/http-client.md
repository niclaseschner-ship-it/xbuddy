# HTTP-Client — Konvention     (ID-Präfix: CLIENT)

XBuddy-Komponenten kommunizieren über HTTP (DCOMP-1). Jede Komponente, die
eine andere über HTTP konsumiert, braucht einen dünnen Client-Wrapper. Diese
Konvention legt die vier Bausteine fest, die alle solchen Clients gemeinsam
tragen — damit Geschwister-Clients konsistent bleiben und Tests ohne echten
HTTP-Server auskommen.

**Heimat:** die aktuellen Clients, aus denen diese Konvention extrahiert wurde
(n=4 Familien-Clients heute, plus zwei weitere Komponenten-Clients):
- `tools/familie_client.py` (gemeinsamer Service-Auth-Client → Familie, FAM-7;
  konsumiert von vier Services — essen, hoerspiel, routine, seiten — fuer den
  Mini-App-Auth-Decorator, seit T1015 / Cluster-A-Option-B 2026-06-18-1720).
- `plan/familie_client.py` (Plan-Buddy → Familie-Komponente, FAM-7).
- `hoerspiel/familie_client.py` (Hörspiel-Buddy → Familie-Komponente, FAM-7;
  Spezial-Use-Case Face-Pille mit `snapshot()`/`RegistryView`/`Person`-Lookup —
  bleibt buddy-lokal, weil der gemeinsame Auth-Client nur `get_telegram_ids()`
  bietet).
- `eltern-chat/skills/familie_client.py` (Eltern-Chat → Familie-Komponente, FAM-7/FAM-12/FAM-13).
- `eltern-chat/skills/geraete_client.py` (Eltern-Chat → Geräte-Komponente, GER-13/GER-15).

### CLIENT-1 — Test-Naht: optionaler `transport=`-Callable im Konstruktor
Jeder HTTP-Client zu einer XBuddy-Daten-Komponente nimmt einen optionalen
`transport=`-Parameter im Konstruktor. Default (`None`): echter HTTP-Aufruf
über `urllib`. Tests übergeben einen In-Process-Stub (ein Callable), der
dieselbe Signatur wie die interne `_call`-Methode trägt — so laufen alle
Client-Tests ohne echten HTTP-Server.

Konkrete Signatur des Stubs in den Eltern-Chat-Clients:
`(method, path, *, body=None, content_type=None) -> (status_code, bytes)`.
Im Plan-Buddy-Client (nur Lesen): `(url) -> bytes`.

Neue Clients orientieren sich an der Signatur der bereits laufenden
Geschwister-Clients.

### CLIENT-2 — Timeout: Default 2,0 Sekunden, konfigurierbar via Konstruktor
Der HTTP-Timeout ist 2,0 Sekunden. Der Wert ist großzügig für
Loopback-Aufrufe (sub-ms im Normalfall) und kurz genug, damit der
Aufrufer-Thread im unhealthy-Fall nicht minutenlang blockiert.

Jeder Client legt den Default als Modul-Konstante fest:
`HTTP_TIMEOUT_SECONDS = 2.0`. Der Konstruktor nimmt `timeout=HTTP_TIMEOUT_SECONDS`
als Override — so können Tests oder ungewöhnliche Deployments den Wert anpassen,
ohne die Konstante zu ändern.

### CLIENT-3 — Fehler-Klasse: komponentenspezifische Subklasse von `Exception`
Jeder Client definiert eine eigene Fehler-Klasse nach dem Schema
`<Komponente>ClientError(Exception)`. Sie fängt einheitlich ab:
Netzwerkfehler (`URLError`, `OSError`), HTTP-Fehler (4xx, 5xx) und
Schema-Drift (unerwartete JSON-Form). Der Aufrufer (Skill) hat genau eine
Klasse zu fangen und formuliert daraus die Bot-Nachricht — kein Stack-Trace
nach oben.

Beispiele aus den laufenden Clients: `FamilieClientError`,
`GeraeteClientError`.

Der Plan-Buddy-Client (`plan/familie_client.py`) loggt Fehler stattdessen
als Warnung und gibt einen leeren Snapshot zurück — das ist der
Plan-Buddy-spezifische Fallback (PLAN-20-Geist). Der gemeinsame
`tools/familie_client.py` folgt demselben Geist im Auth-Lookup-Use-Case
(`get_telegram_ids()` schluckt `FamilieClientError` und gibt `None` zurück,
damit der Auth-Decorator beim Service-Ausfall fail-open läuft). Neue Clients
aus dem Eltern-Chat-Kontext folgen dem `<Komponente>ClientError`-Muster mit
Re-Raise.

### CLIENT-4 — Pfad-Konstanten aus `conventions/urls.md` (URL-14)
Endpoint-Pfade werden **nicht erfunden**, sondern aus den stabilen URL-Verträgen
der jeweiligen Komponente (URL-14 in `conventions/urls.md`) übernommen. Pro
Client: `PFAD_<RESSOURCE> = "/api/v1/<komponente>/..."` als Modul-Konstante.

Beispiele:
- `PFAD_PERSONEN = "/api/v1/familie/personen"` (FAM-7, FAM-12, FAM-13)
- `PFAD_GERAETE = "/api/v1/geraete/"` (GER-13, GER-15)

Wer einen neuen Client schreibt, liest zuerst `conventions/urls.md` und trägt
dort ggf. den noch fehlenden URL-Vertrag nach — kein Pfad als Magic-String
direkt im Client-Code.
