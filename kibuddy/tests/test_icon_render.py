"""Test-Suite für kibuddy/icon_render.py (KIBUDDY-17, KIBUDDY-28)."""

from kibuddy.icon_render import (
    STOP_WORDS_DE,
    render_worte,
    tokenisiere,
    worte_zu_api_format,
)

# ============================================================
#  Funktionswort-Liste (KIBUDDY-17 ~150 Wörter)
# ============================================================


def test_stop_words_enthalten_artikel():
    for wort in ("der", "die", "das", "ein", "eine"):
        assert wort in STOP_WORDS_DE, "%r fehlt in STOP_WORDS_DE" % wort


def test_stop_words_enthalten_hilfsverben():
    for wort in ("haben", "ist", "wird", "kann", "muss"):
        assert wort in STOP_WORDS_DE


def test_stop_words_enthalten_praepostitionen():
    for wort in ("in", "an", "auf", "von", "zu", "bei", "mit"):
        assert wort in STOP_WORDS_DE


def test_stop_words_enthalten_konjunktionen():
    for wort in ("und", "oder", "aber", "weil", "dass", "wenn"):
        assert wort in STOP_WORDS_DE


def test_stop_words_min_150():
    """KIBUDDY-17 verlangt ~150 deutsche Funktionswörter."""
    assert len(STOP_WORDS_DE) >= 150


# ============================================================
#  Tokenisierung (KIBUDDY-17 Schritte 1–2)
# ============================================================


def test_tokenisiere_einfacher_satz():
    tokens = tokenisiere("Der Hund läuft schnell.")
    assert len(tokens) >= 2
    # "Der" ist Funktionswort.
    der_tok = next((t for t in tokens if t["token"] == "Der"), None)
    assert der_tok is not None
    assert der_tok["typ"] == "funktionswort"
    # "Hund" ist Inhaltswort.
    hund_tok = next((t for t in tokens if t["token"] == "Hund"), None)
    assert hund_tok is not None
    assert hund_tok["typ"] == "inhaltswort"


def test_tokenisiere_satzzeichen_abgetrennt():
    tokens = tokenisiere("Toll!")
    typen = [t["typ"] for t in tokens]
    assert "inhaltswort" in typen
    assert "satzzeichen" in typen


def test_tokenisiere_leerer_text():
    assert tokenisiere("") == []


def test_tokenisiere_nur_funktionswoerter():
    tokens = tokenisiere("und oder aber")
    for tok in tokens:
        assert tok["typ"] == "funktionswort"


# ============================================================
#  Render-Wort-Logik (KIBUDDY-17 Schritte 3–6a)
# ============================================================


def test_render_worte_icon_lookup_aufgerufen_fuer_inhaltswort():
    """Icon-Lookup wird für Inhaltswörter aufgerufen, nicht für Funktionswörter."""
    lookup_calls = []

    def fake_lookup(wort):
        lookup_calls.append(wort)
        return "/display/_shared/icons/arasaac/1234.png"

    render_worte("Der Hund bellt.", icon_lookup_fn=fake_lookup)
    # "Der" ist Funktionswort → kein Lookup-Call.
    assert "der" not in lookup_calls
    # "Hund" und "bellt" sind Inhaltswörter → Lookup-Call.
    assert "hund" in lookup_calls or "bellt" in lookup_calls


def test_render_worte_kein_lookup_fuer_funktionswort():
    lookup_calls = []

    def fake_lookup(wort):
        lookup_calls.append(wort)
        return None

    render_worte("und oder", icon_lookup_fn=fake_lookup)
    assert lookup_calls == []


def test_render_worte_treffer_hat_icon_url():
    def fake_lookup(wort):
        return "/display/_shared/icons/arasaac/2239.png"

    result = render_worte("Biene", icon_lookup_fn=fake_lookup)
    inhaltswort = next(r for r in result if r["typ"] == "inhaltswort")
    assert inhaltswort["icon_url"] == "/display/_shared/icons/arasaac/2239.png"


def test_render_worte_miss_hat_icon_url_none():
    def fake_lookup(wort):
        return None

    result = render_worte("Quarkulus", icon_lookup_fn=fake_lookup)
    inhaltswort = next(r for r in result if r["typ"] == "inhaltswort")
    assert inhaltswort["icon_url"] is None


def test_render_worte_funktionswort_hat_kein_icon_field():
    """Funktionswörter haben keinen icon_url-Slot (KIBUDDY-17 6a)."""
    result = render_worte("und", icon_lookup_fn=lambda w: None)
    fw = next(r for r in result if r["typ"] == "funktionswort")
    assert "icon_url" not in fw


# ============================================================
#  API-Format-Konvertierung (KIBUDDY-24 words-Liste)
# ============================================================


def test_worte_zu_api_format_icon_id_extrahiert():
    worte = [
        {"token": "Hund", "typ": "inhaltswort", "icon_url": "/display/_shared/icons/arasaac/2239.png"},
    ]
    api = worte_zu_api_format(worte)
    assert api[0]["text"] == "Hund"
    assert api[0]["icon_id"] == "2239"


def test_worte_zu_api_format_kein_icon_null():
    worte = [
        {"token": "und", "typ": "funktionswort"},
    ]
    api = worte_zu_api_format(worte)
    assert api[0]["text"] == "und"
    assert api[0]["icon_id"] is None
