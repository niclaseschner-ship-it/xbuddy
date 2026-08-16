"""LOG-3: Kind-Sprachinhalt darf nicht auf INFO landen (xbuddy#1806).

Vor #1806 protokollierten drei Stellen woertlichen Kind-Sprachinhalt auf
INFO: das STT-Transkript (stt_service.py), die Frage + Antwort des
Sprach-Buddys (llm_service.py) und der von der Stille-Halluzinations-
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
_HALLUZINATION_MARKER = "Vielen Dank fürs Zuschauen"  # bekannte Whisper-Stille-Phrase


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

def test_stille_halluzination_gefiltert_nicht_auf_info_aber_auf_debug(
        client, fake_stt, caplog):
    """#1806/AC3: der vom Filter erkannte Wortlaut fehlt auf INFO, ist aber
    auf DEBUG da. Laeuft ueber den echten POST /api/v1/kibuddy/frage-Pfad
    (main.py generate()), nicht isoliert — Entry-Path-Coverage."""
    fake_stt.transkript = _HALLUZINATION_MARKER

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

    assert _HALLUZINATION_MARKER not in info_text, (
        "gefilterter Kind-Sprachinhalt auf INFO — LOG-3-Rueckfall")
    assert _HALLUZINATION_MARKER in debug_text, (
        "gefilterter Wortlaut muss weiterhin auf DEBUG diagnostizierbar sein "
        "(Beweisstueck: hat der Filter richtig erkannt?)")
