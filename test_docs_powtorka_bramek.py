"""
test_docs_powtorka_bramek.py - powtorka `_docs` przy twardych bramkach i znakach (v19.20.0).

Dwa dlugi zamkniete w jednym miejscu, `_tlumacz_pojedyncza_sekcje`:

  1. Parzystosc markerow i twardy odcisk struktury ubijaly sekcje od razu
     (18.30.0). Od 19.20 dostaja JEDNA powtorke z liczbowym zarzutem po
     angielsku; druga porazka nadal ubija. Licznik `STATYSTYKA_POWTOREK`
     mowi, czy powtorka naprawia.
  2. Mojibake i slowo z dwoch pism dzialaly tylko w rdzeniu (19.11.0). Od 19.20
     sa zarzutem takze dla prozy podrecznikow - ale tylko, gdy zrodla PL ich
     nie ma (podrecznik moze legalnie cytowac mojibake).

Przebiegi ida przez stub `core_llm.wywolaj_llm` (zero sieci), `runtime/`
i `skrypty/` w katalogu tymczasowym.

Uruchom:  .venv/Scripts/python -m pytest test_docs_powtorka_bramek.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_docs_powtorka_bramek.py
"""

import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_llm as cl
import buduj_wielojezyczne_docs as bd
import higiena_testow as ht

KOD = "fi"
NAZWA_PL = "finski"
RDZEN = "test_docs_powtorka_bramek"
NACISK = "RETRY — YOUR PREVIOUS TRANSLATION"
A_UMLAUT = chr(0xE4)
MOJIBAKE = chr(0xC3) + chr(0xA4)          # "a z umlautem" przeczytane jako cp1252
CYRYLICKIE_A = chr(0x430)

TRESC_PL = (
    "# Naglowek sekcji\n\n"
    "Projekt {nazwa_projektu} liczy {liczba_znakow} znakow.\n"
    "1. Pierwszy punkt listy numerowanej z odrobina tresci.\n"
    "2. Drugi punkt listy, zeby szkielet mial co liczyc.\n"
    "To zdanie istnieje, zeby sekcja przekroczyla dwiescie znakow zrodla.\n"
)

_odpowiedzi: list = []
_prompty: list[str] = []


def _stub_llm(klient, *, model, system, messages, max_tokens, temperature,
              timeout, segmenty=None, wymusz_json=False, schema_json=None, slad=None):
    _prompty.append(system)
    tresc = messages[0]["content"]
    psuj = _odpowiedzi.pop(0) if _odpowiedzi else (lambda t: t)
    return psuj(tresc), "end_turn"


@contextlib.contextmanager
def _srodowisko(*odpowiedzi):
    katalog = tempfile.mkdtemp()
    stary_runtime, stary_llm, stare_odrzuty = bd.RUNTIME_DIR, cl.wywolaj_llm, bd.KATALOG_ODRZUTOW
    bd.RUNTIME_DIR = Path(katalog)
    bd.KATALOG_ODRZUTOW = Path(katalog) / "skrypty"
    cl.wywolaj_llm = _stub_llm
    _odpowiedzi[:] = list(odpowiedzi)
    _prompty.clear()
    bd.STATYSTYKA_POWTOREK.clear()
    try:
        yield
    finally:
        bd.RUNTIME_DIR, cl.wywolaj_llm, bd.KATALOG_ODRZUTOW = (
            stary_runtime, stary_llm, stare_odrzuty)
        bd.STATYSTYKA_POWTOREK.clear()
        ht.usun_katalog(katalog)


def _przebieg(tresc_pl: str = TRESC_PL) -> tuple[bool, str | None, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        ok, wynik = bd._tlumacz_pojedyncza_sekcje(
            KOD, NAZWA_PL, None, "test.yaml", RDZEN, bd.KLUCZ_LEGACY, tresc_pl,
            dry_run=False, model="stub", prompt_dodatkowy="")
    return ok, wynik, buf.getvalue()


def _bez_markera(t: str) -> str:
    return t.replace(bd.TOKEN_FORMAT.format(1), "", 1)


def _bez_punktu(t: str) -> str:
    return t.replace("2. Drugi", "Drugi", 1)


def _z_mojibake(t: str) -> str:
    return t.replace("Pierwszy", "Pierwszy " + MOJIBAKE, 1)


def _z_mieszanym(t: str) -> str:
    return t.replace("Drugi", "Drug" + CYRYLICKIE_A, 1)


# ---------------------------------------------------------------------------
# 1. Twarde bramki: jedna powtorka
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("psuj, fraza", [
    (_bez_markera, "appears 0 time(s) in your answer and 1 time(s) in the source"),
    (_bez_punktu, "the source has 2 numbered list items, your answer has 1"),
])
def test_twarda_bramka_dostaje_powtorke_ktora_naprawia(psuj, fraza):
    with _srodowisko(psuj):
        ok, wynik, log = _przebieg()
        assert ok, log
        assert "{nazwa_projektu}" in wynik
        assert len(_prompty) == 2 and NACISK in _prompty[1] and fraza in _prompty[1]
        assert bd.STATYSTYKA_POWTOREK == {"twarde:naprawiona": 1}


def test_druga_porazka_twardej_bramki_ubija_sekcje():
    with _srodowisko(_bez_markera, _bez_markera):
        ok, wynik, log = _przebieg()
        assert ok is False and wynik is None
        assert len(_prompty) == 2
        assert "❌" in log.split("BROKEN parity")[-2]          # druga = blad
        assert bd.STATYSTYKA_POWTOREK == {"twarde:nienaprawiona": 1}


# ---------------------------------------------------------------------------
# 2. Znaki: mojibake i dwa pisma tylko wtedy, gdy zrodla ich nie ma
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("psuj, fraza", [
    (_z_mojibake, "mojibake"),
    (_z_mieszanym, "mixes letters of two alphabets"),
])
def test_znaki_sa_zarzutem_z_powtorka(psuj, fraza):
    with _srodowisko(psuj):
        ok, _wynik, log = _przebieg()
        assert ok, log
        assert len(_prompty) == 2 and fraza in _prompty[1]
        assert bd.STATYSTYKA_POWTOREK == {"zarzuty:naprawiona": 1}


def test_mojibake_cytowane_w_zrodle_nie_jest_zarzutem():
    zrodlo = TRESC_PL + "Przyklad naprawy: " + MOJIBAKE + " staje sie " + A_UMLAUT + ".\n"
    with _srodowisko():
        ok, _wynik, log = _przebieg(zrodlo)
        assert ok, log
        assert len(_prompty) == 1


def test_zarzuty_znakow_porownuja_ze_zrodlem():
    assert bd.zarzuty_znakow("abc", "abc") == []
    assert bd.zarzuty_znakow("x " + MOJIBAKE, "y " + MOJIBAKE) == []
    assert len(bd.zarzuty_znakow("Drugi", "Drug" + CYRYLICKIE_A)) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
