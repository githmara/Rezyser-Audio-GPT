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


def _returny_wlasne(funkcja: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Return]:
    """`return` należące do TEJ funkcji — bez zagnieżdżonych def/lambda/klas."""
    wynik: list[ast.Return] = []
    stos = list(funkcja.body)
    while stos:
        wezel = stos.pop()
        if isinstance(wezel, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(wezel, ast.Return):
            wynik.append(wezel)
        stos.extend(ast.iter_child_nodes(wezel))
    return wynik


def zwracajace_wartosc(tekst: str) -> list[str]:
    """Funkcje `test_*` (także metody klas `Test*`), które zwracają WARTOŚĆ.

    Bramka v19.20.0 (dług z 19.2.1). Pytest ignoruje wartość zwróconą przez
    test i tylko ostrzega (`PytestReturnNotNoneWarning`) — więc test pisany
    w stylu „zwróć wynik porównania” zamiast `assert` jest ZIELONY zawsze.
    Ostrzeżenie ginie w podsumowaniu; ta bramka nie. Goły `return` i
    `return None` są legalne (wczesne wyjście).
    """
    trafienia: list[str] = []
    for wezel in ast.walk(ast.parse(tekst)):
        if not (isinstance(wezel, (ast.FunctionDef, ast.AsyncFunctionDef))
                and wezel.name.startswith("test")):
            continue
        for ret in _returny_wlasne(wezel):
            if ret.value is None:
                continue
            if isinstance(ret.value, ast.Constant) and ret.value.value is None:
                continue
            trafienia.append(f"{wezel.name}:{ret.lineno}")
    return trafienia


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


def test_zaden_test_nie_zwraca_wartosci():
    """Wartość zwrócona z testu jest dla pytesta niema — zamień ją na `assert`."""
    trafienia = [f"{p.name}::{t}" for p in _pliki_testowe()
                 for t in zwracajace_wartosc(p.read_text(encoding="utf-8"))]
    assert not trafienia, (
        "te testy zwracają wartość zamiast ją asertować: " + ", ".join(trafienia))


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


def test_detektor_returnu_lapie_wartosc_i_puszcza_wczesne_wyjscie():
    zly = "def test_a():\n    return 1 == 1\n\nclass TestK:\n    def test_b(self):\n        return x\n"
    assert zwracajace_wartosc(zly) == ["test_a:2", "test_b:6"]
    dobry = (
        "def test_a():\n    if warunek:\n        return\n    assert True\n\n"
        "def test_b():\n    return None\n\n"
        "def test_c():\n    def pomoc():\n        return 5\n    assert pomoc() == 5\n\n"
        "def _pomocnik():\n    return 3\n"
    )
    assert zwracajace_wartosc(dobry) == []


def test_zrodlo_kanonu_przechodzi_mimo_wlasnego_printu():
    """`test_core_updater.py` ma w bloku print o tokenie — bramka pyta o delegację."""
    tekst = (KORZEN / "test_core_updater.py").read_text(encoding="utf-8")
    blok = _blok_main(tekst)
    assert blok is not None, "źródło kanonu straciło blok skryptowy"
    assert "GITHUB_TOKEN" in ast.unparse(blok), "blok źródła kanonu stracił print o tokenie"
    assert deleguje_do_pytesta(tekst)


def test_liczby_testow_w_contributing():
    """Bramka (v19.15): CONTRIBUTING.md cytuje liczbę plików i testów — tu, bo
    to plik, który CONTRIBUTING każe uruchomić po dodaniu nowego `test_*.py`.
    Zbiera testy bez uruchamiania (`--collect-only`), bez sieci."""
    import przelicznik_testow as pt
    tekst = (KORZEN / "CONTRIBUTING.md").read_text(encoding="utf-8")
    testy, pominiete = pt.zebrane_testy()
    bledy = pt.sprawdz(tekst, len(pt.pliki_testowe()), testy)
    assert not bledy, "\n".join(bledy) + "\nFix: .venv/Scripts/python przelicznik_testow.py --zapisz"
    if pominiete:
        # Bez wx (L3) moduł wypada ze zbierania: liczby testów nie da się tu
        # sprawdzić — widoczny skip, nie fałszywy rozjazd.
        pytest.skip("test count unverifiable here, modules not collected: " + "; ".join(pominiete))


def test_przelicznik_lapie_rozjazd():
    import przelicznik_testow as pt
    pliki = len(pt.pliki_testowe())
    tekst = "There are 13 regression test files (179 tests, about a minute).\n| x | `pytest test_nie_ma.py` |"
    bledy = pt.sprawdz(tekst, pliki, 850)
    assert len(bledy) == 3 and "test_nie_ma.py" in bledy[2]
    assert pt.sprawdz(pt.zapisz(tekst, pliki, 850).split("\n")[0], pliki, 850) == []
    assert pt.sprawdz("thirteen regression test files", pliki, 850)   # liczba słowem = błąd


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
