"""
test_kanon_testow.py — bramka na sposób URUCHAMIANIA plików testowych (v19.7).

Plik testowy bez bloku `__main__` nie krzyczy — uruchomiony klasycznie
(`.venv/Scripts/python test_cos.py`) definiuje funkcje i kończy się z kodem 0
bez jednej linii outputu. Zmierzone 2026-09-21 na `test_audyt_kreatora.py`
i `test_prompty_markery.py`: dwie CICHE ZIELENIE, czyli dokładnie ta klasa,
którą v19.2.1 opisała w `test_core_updater.py` („test, ktory nie ma jak
zawiesc, jest gorszy od braku testu").

Drugi kształt tej samej wady to własny harness sumujący wyniki (pętla po
`globals()` z `except AssertionError`), który stał w 24 plikach. Łapie
WYŁĄCZNIE asercje, więc `pytest.skip()` — rzucający `Skipped`, potomka
`BaseException`, nie `AssertionError` — wywraca mu cały przebieg zamiast się
pokazać, a `@pytest.mark.parametrize` i fixture (`tmp_path`, `monkeypatch`,
`capsys`) są dla niego niewidzialne: wywoła funkcję bez argumentów i dostanie
`TypeError`. W dniu migracji żaden z tych plików takiego mechanizmu nie używał,
więc była to pułapka, nie czynny bug — i właśnie dlatego zamyka ją bramka,
a nie nota w pamięci.

KANON: jeden mechanizm, jedno raportowanie —
`if __name__ == "__main__": sys.exit(pytest.main([__file__, "-v"]))`.
`test_core_updater.py` (źródło kanonu, v19.2.1) dokłada w bloku print
o `GITHUB_TOKEN` — bramka pyta o DELEGACJĘ, nie o identyczność bajt w bajt.

Uruchom:  .venv/Scripts/python -m pytest test_kanon_testow.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_kanon_testow.py
"""

import ast
import sys
from pathlib import Path

import pytest

KORZEN = Path(__file__).parent


def _pliki_testowe() -> list[Path]:
    return sorted(KORZEN.glob("test_*.py"))


def _blok_main(tekst: str) -> ast.If | None:
    """Zwraca modułowy `if __name__ == "__main__":` albo None."""
    for wezel in ast.parse(tekst).body:
        if not isinstance(wezel, ast.If):
            continue
        warunek = wezel.test
        if (isinstance(warunek, ast.Compare)
                and isinstance(warunek.left, ast.Name)
                and warunek.left.id == "__name__"
                and any(isinstance(c, ast.Constant) and c.value == "__main__"
                        for c in warunek.comparators)):
            return wezel
    return None


def deleguje_do_pytesta(tekst: str) -> bool:
    """Czy plik uruchomiony jako skrypt oddaje przebieg pytestowi."""
    blok = _blok_main(tekst)
    if blok is None:
        return False
    for wezel in ast.walk(blok):
        if (isinstance(wezel, ast.Call)
                and isinstance(wezel.func, ast.Attribute)
                and wezel.func.attr == "main"
                and isinstance(wezel.func.value, ast.Name)
                and wezel.func.value.id == "pytest"):
            return True
    return False


def sumuje_wyniki_sam(tekst: str) -> bool:
    """Czy w bloku skryptowym siedzi własny harness łapiący asercje."""
    blok = _blok_main(tekst)
    if blok is None:
        return False
    for wezel in ast.walk(blok):
        if (isinstance(wezel, ast.ExceptHandler)
                and isinstance(wezel.type, ast.Name)
                and wezel.type.id == "AssertionError"):
            return True
    return False


# ---------------------------------------------------------------------------
# 1. Kanon na realnym repo
# ---------------------------------------------------------------------------
def test_zbior_plikow_nie_jest_pusty():
    """Bramka bez przedmiotu jest zielona zawsze — najpierw sprawdzamy, że ma co mierzyć."""
    pliki = _pliki_testowe()
    assert len(pliki) >= 20, f"glob `test_*.py` znalazł tylko {len(pliki)} plików"
    assert Path(__file__) in pliki, "bramka nie widzi samej siebie"


def test_kazdy_plik_testowy_deleguje_do_pytesta():
    """Uruchomiony klasycznie plik MUSI raportować, a nie kończyć się cicho na 0."""
    braki = [p.name for p in _pliki_testowe()
             if not deleguje_do_pytesta(p.read_text(encoding="utf-8"))]
    assert not braki, (
        "te pliki uruchomione jako skrypt nic nie raportują: "
        + ", ".join(braki)
        + " — dopisz `if __name__ == \"__main__\": "
          "sys.exit(pytest.main([__file__, \"-v\"]))`")


def test_zaden_plik_nie_sumuje_wynikow_sam():
    """Drugi sposób raportowania jest tym cichym — patrz docstring modułu."""
    wlasne = [p.name for p in _pliki_testowe()
              if sumuje_wyniki_sam(p.read_text(encoding="utf-8"))]
    assert not wlasne, (
        "własny harness sumujący wyniki wrócił do: " + ", ".join(wlasne))


# ---------------------------------------------------------------------------
# 2. Dowód bojowy — defekt wstrzykiwany per klasa + kontrole odwrotne
# ---------------------------------------------------------------------------
_KANON = (
    "def test_cos():\n    assert True\n\n\n"
    'if __name__ == "__main__":\n'
    '    sys.exit(pytest.main([__file__, "-v"]))\n'
)
_BEZ_BLOKU = "def test_cos():\n    assert True\n"
_RECZNY = (
    "def test_cos():\n    assert True\n\n\n"
    'if __name__ == "__main__":\n'
    "    for nazwa, funkcja in sorted(globals().items()):\n"
    "        try:\n"
    "            funkcja()\n"
    "        except AssertionError as exc:\n"
    "            print(exc)\n"
    "    sys.exit(0)\n"
)
_POZA_BLOKIEM = "import pytest\npytest.main([__file__])\n"


def test_detektor_lapie_brak_bloku():
    assert not deleguje_do_pytesta(_BEZ_BLOKU)
    assert not sumuje_wyniki_sam(_BEZ_BLOKU)


def test_detektor_lapie_reczny_harness():
    assert not deleguje_do_pytesta(_RECZNY)
    assert sumuje_wyniki_sam(_RECZNY)


def test_detektor_akceptuje_kanon():
    """Kontrola odwrotna: poprawny plik NIE produkuje trafienia."""
    assert deleguje_do_pytesta(_KANON)
    assert not sumuje_wyniki_sam(_KANON)


def test_wolanie_pytesta_poza_blokiem_nie_liczy_sie():
    """`pytest.main` w ciele modułu odpaliłby się też pod pytestem — to nie kanon."""
    assert not deleguje_do_pytesta(_POZA_BLOKIEM)


def test_zrodlo_kanonu_przechodzi_mimo_wlasnego_printu():
    """`test_core_updater.py` ma w bloku print o tokenie — bramka pyta o delegację."""
    tekst = (KORZEN / "test_core_updater.py").read_text(encoding="utf-8")
    blok = _blok_main(tekst)
    assert blok is not None, "źródło kanonu straciło blok skryptowy"
    assert "GITHUB_TOKEN" in ast.unparse(blok), "blok źródła kanonu stracił print o tokenie"
    assert deleguje_do_pytesta(tekst)


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
