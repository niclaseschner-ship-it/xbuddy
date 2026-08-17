"""LOG-3: Kind-Sprachinhalt darf nicht auf INFO landen (xbuddy#1806).

Vor #1806 protokollierten vier Stellen woertlichen Kind-Sprachinhalt auf
INFO: das STT-Transkript, die Frage an den Sprach-Buddy, dessen
Modell-Antwort samt der daraus extrahierten Buzzwords (alle drei in
llm_service.py/stt_service.py) und der von der Stille-Halluzinations-
Filterung erkannte Text (main.py). LOG-3 verbietet das explizit ("Nutzer-
Inhalte erst recht nicht ... gesprochene Kind-Sprache").

Diese Suite faengt den Rueckfall: taucht der woertliche Inhalt in einem
INFO-Record auf, wird der Test rot. Die Diagnose-Faehigkeit bleibt
erhalten — derselbe Inhalt muss auf DEBUG weiter auffindbar sein.
"""

import io
import logging

from kibuddy.llm_service import beantworte_frage
from kibuddy.session_memory import SessionMemory
from kibuddy.stt_service import transkribiere
from kibuddy.tests.conftest import FakeLLM, FakeSTTEngine

from .test_endpoints import get_stream_event

# Unwahrscheinliche Marker-Strings — Kollision mit anderen Log-Zeilen
# (z. B. Byte-Zaehlern) ausgeschlossen.
_TRANSKRIPT_MARKER = "Warum leuchten die Sterne nachts, Buddy?"
_FRAGE_MARKER = "Wieso ist die Banane krumm, Buddy?"
_ANTWORT_MARKER = "Die Banane waechst krumm wegen Photoperiodismus."

# Transkript, das NUR per Indikator-Substring (nicht per Vollphrase) matcht
# (KIBUDDY-12-H): der Rest des Satzes ist freier (fiktiver) Kind-Wortlaut,
# der den Filter fälschlich mitgerissen hat — genau der False-Positive-Fall,
# den die Watchdog-Nachschaerfung adressiert. "amara.org" ist die
# Code-Konstante aus stt_service._STILLE_HALLUZINATION_INDIKATOREN und darf
# als Diagnose-Treffer auf INFO stehen; der Rest des Satzes ist
# Kind-Sprachinhalt und darf es nicht.
_HALLUZINATION_VOLLTEXT = "Amara.org hat mir das mit den Delfinen erklärt"
_HALLUZINATION_TREFFER = "amara.org"
_HALLUZINATION_KINDINHALT = "delfinen erklärt"  # nur im Volltext, nicht im Treffer


def _info_records(caplog):
    return [r for r in caplog.records if r.levelno == logging.INFO]


def _debug_records(caplog):
    return [r for r in caplog.records if r.levelno == logging.DEBUG]


# ---- stt_service.transkribiere ----

def test_stt_transkript_nicht_auf_info_aber_auf_debug(caplog):
    """#1806/AC3: Transkript-Wortlaut fehlt auf INFO, ist aber auf DEBUG da."""
    stt_engine = FakeSTTEngine(transkript=_TRANSKRIPT_MARKER)

    with caplog.at_level(logging.DEBUG, logger="kibuddy.stt_service"):
        transkribiere(b"FAKEAUDIO", stt_engine)

    info_text = "\n".join(r.getMessage() for r in _info_records(caplog))
    debug_text = "\n".join(r.getMessage() for r in _debug_records(caplog))

    assert _TRANSKRIPT_MARKER not in info_text, (
        "Kind-Sprachinhalt (Transkript) auf INFO — LOG-3-Rueckfall")
    assert _TRANSKRIPT_MARKER in debug_text, (
        "Transkript muss weiterhin auf DEBUG diagnostizierbar sein")


# ---- llm_service.beantworte_frage ----

def test_llm_frage_und_antwort_nicht_auf_info_aber_auf_debug(caplog, tmp_path):
    """#1806/AC3: Frage- UND Antwort-Wortlaut fehlen auf INFO, sind aber auf DEBUG da."""
    raw_json = (
        '{"antwort": "%s", "buzzwords": ["banane", "krumm", "wachstum"]}'
        % _ANTWORT_MARKER
    )
    llm = FakeLLM(antwort=raw_json)
    memory = SessionMemory()

    with caplog.at_level(logging.DEBUG, logger="kibuddy.llm_service"):
        beantworte_frage(
            frage_text=_FRAGE_MARKER,
            data_root=str(tmp_path),
            memory=memory,
            llm=llm,
        )

    info_text = "\n".join(r.getMessage() for r in _info_records(caplog))
    debug_text = "\n".join(r.getMessage() for r in _debug_records(caplog))

    assert _FRAGE_MARKER not in info_text, (
        "Kind-Sprachinhalt (Frage) auf INFO — LOG-3-Rueckfall")
    assert _ANTWORT_MARKER not in info_text, (
        "Kind-Sprachinhalt (Antwort) auf INFO — LOG-3-Rueckfall")
    assert _FRAGE_MARKER in debug_text, (
        "Frage muss weiterhin auf DEBUG diagnostizierbar sein")
    assert _ANTWORT_MARKER in debug_text, (
        "Antwort muss weiterhin auf DEBUG diagnostizierbar sein")


# ---- main.py: Stille-Halluzinations-Filter (Entry-Path: echter Endpunkt) ----

def test_stille_halluzination_gefiltert_kein_kindinhalt_auf_info_aber_treffer_diagnostizierbar(
        client, fake_stt, caplog):
    """#1806/AC3 + Watchdog-Nachschaerfung: der freie Kind-Wortlaut fehlt auf
    INFO, aber die gematchte Code-Konstante (Treffer aus der geschlossenen
    Halluzinations-Liste) steht weiterhin auf INFO — das ist kein
    Kind-Sprachinhalt und LOG-3 greift hier nicht. Eine reine Zeichenzahl
    waere ein False-Positive-Fall unsichtbar; der Treffer bleibt sichtbar.
    Voller Wortlaut zusaetzlich auf DEBUG. Laeuft ueber den echten
    POST /api/v1/kibuddy/frage-Pfad (main.py generate()), nicht isoliert —
    Entry-Path-Coverage."""
    fake_stt.transkript = _HALLUZINATION_VOLLTEXT

    with caplog.at_level(logging.DEBUG, logger="kibuddy.main"):
        resp = client.post(
            "/api/v1/kibuddy/frage",
            data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200
    err_ev = get_stream_event(resp, "error")
    assert err_ev is not None, "Stille-Halluzination muss weiterhin ein error-Event liefern"
    assert err_ev.get("stage") == "stt", (
        "Stille-Halluzination muss weiterhin als STT-Fehler-Event laufen")

    info_text = "\n".join(r.getMessage() for r in _info_records(caplog))
    debug_text = "\n".join(r.getMessage() for r in _debug_records(caplog))

    # Diagnose-Wert bleibt: die gematchte Code-Konstante steht auf INFO —
    # eine reine Zeichenzahl haette einen echten Treffer nicht von einem
    # gleich langen False-Positive unterscheiden koennen.
    assert _HALLUZINATION_TREFFER in info_text, (
        "gematchte Code-Konstante (kein Kind-Inhalt) muss auf INFO stehen — "
        "sonst ist ein False-Positive des Filters im Betrieb unsichtbar")
    # Kein Kind-Inhalt: der freie Teil des Satzes (alles ausser dem
    # Listen-Treffer) darf auf INFO nicht auftauchen.
    assert _HALLUZINATION_KINDINHALT not in info_text.lower(), (
        "Kind-Sprachinhalt (freier Teil des Satzes) auf INFO — LOG-3-Rueckfall")
    assert _HALLUZINATION_VOLLTEXT not in info_text, (
        "voller Kind-Wortlaut auf INFO — LOG-3-Rueckfall")
    # Diagnose-Faehigkeit erhalten: voller Wortlaut bleibt auf DEBUG
    # auffindbar (Beweisstueck: hat der Filter richtig erkannt?).
    assert _HALLUZINATION_VOLLTEXT in debug_text, (
        "gefilterter Wortlaut muss weiterhin auf DEBUG diagnostizierbar sein")
