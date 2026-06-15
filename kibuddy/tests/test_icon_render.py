"""Test-Suite für kibuddy/icon_render.py (KIBUDDY-17, KIBUDDY-17.3, KIBUDDY-28)."""


from kibuddy.icon_render import (
    STOP_WORDS_DE,
    _reset_stop_words_cache,
    load_stop_words,
    tokenisiere,
    worte_zu_words_api,
)

# ============================================================
#  Funktionswort-Liste (KIBUDDY-17 ~150 Wörter, aus Default-Datei)
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
#  Funktionswort-Override aus data_root (KIBUDDY-17.3)
# ============================================================


def test_load_stop_words_override(tmp_path):
    """Override-Datei in data_root überschreibt Default (KIBUDDY-17.3)."""
    _reset_stop_words_cache()
    override = tmp_path / "funktionswort-liste.txt"
    override.write_text("testfunktionswort\nandereswort\n", encoding="utf-8")
    words = load_stop_words(data_root=tmp_path)
    assert "testfunktionswort" in words
    assert "andereswort" in words
    _reset_stop_words_cache()


def test_load_stop_words_fallback_to_default(tmp_path):
    """Fehlende Override-Datei → Default-Datei wird benutzt (KIBUDDY-17.3)."""
    _reset_stop_words_cache()
    # tmp_path hat keine funktionswort-liste.txt
    words = load_stop_words(data_root=tmp_path)
    assert len(words) >= 150
    assert "der" in words
    _reset_stop_words_cache()


def test_load_stop_words_override_wort_wird_gefiltert(tmp_path):
    """Ein Wort in der Override-Datei wird als Funktionswort klassifiziert."""
    _reset_stop_words_cache()
    override = tmp_path / "funktionswort-liste.txt"
    override.write_text("quarkulus\n", encoding="utf-8")
    words = load_stop_words(data_root=tmp_path)
    assert "quarkulus" in words
    # Tokenisierung benutzt diesen Cache.
    tokens = tokenisiere("quarkulus")
    assert len(tokens) == 1
    assert tokens[0]["typ"] == "funktionswort"
    _reset_stop_words_cache()


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
#  API-Format (KIBUDDY-17 FIX1: {text, is_inhaltswort} — kein icon_id)
# ============================================================


def test_worte_zu_words_api_inhaltswort():
    """Inhaltswort bekommt is_inhaltswort=True (KIBUDDY-17 FIX1)."""
    api = worte_zu_words_api("Hund")
    inhaltswort = next(w for w in api if w["text"] == "Hund")
    assert inhaltswort["is_inhaltswort"] is True
    assert "icon_id" not in inhaltswort


def test_worte_zu_words_api_funktionswort():
    """Funktionswort bekommt is_inhaltswort=False."""
    api = worte_zu_words_api("und")
    fw = next(w for w in api if w["text"] == "und")
    assert fw["is_inhaltswort"] is False
    assert "icon_id" not in fw


def test_worte_zu_words_api_gemischter_satz():
    """Gemischter Satz: Artikel False, Nomen True (KIBUDDY-17)."""
    api = worte_zu_words_api("Der Hund bellt.")
    by_text = {w["text"]: w for w in api}
    assert by_text["Der"]["is_inhaltswort"] is False
    assert by_text["Hund"]["is_inhaltswort"] is True
    # Satzzeichen ist kein Inhaltswort.
    assert by_text["."]["is_inhaltswort"] is False


def test_worte_zu_words_api_kein_urllib_call(monkeypatch):
    """Kein urllib-Call vom Server — Icon-Lookup ist clientseitig (KIBUDDY-17)."""
    import urllib.request

    def _fail(*a, **kw):
        raise AssertionError("Server darf keinen urllib-Call machen (KIBUDDY-17 FIX1)")

    monkeypatch.setattr(urllib.request, "urlopen", _fail)
    # Dieser Aufruf darf keinen urllib-Call machen.
    worte_zu_words_api("Der Hund bellt.")
