"""
test_akcent_wersaliki.py - Regresja kroku wersalikowego silnika akcentow (18.22).

Bramki audytora (`buduj_wielojezyczne_akcenty.py`) pilnuja DANYCH: wzorcow,
kolejnosci, przykladow w prozie. Semantyki samego silnika nie pilnuje zadna
z nich, a to ona rozstrzyga, czy regula jednoliterowa z wielo-znakowym wynikiem
(`Z` -> `Zh`) nie zostawi „ZhDAT" w tekscie pisanym WERSALIKAMI. Testy sa
SYNTETYCZNE (wlasne listy regul, nie paczki z `dictionaries/`), zeby zmiana
danych ich nie przewracala.

Uruchom:  .venv/Scripts/python test_akcent_wersaliki.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import core_poliglota as cp


def zastosuj(tekst, *reguly):
    """`_zastosuj_zamiany` na regulach podanych jako `(wzor, zamiana[, regex])`."""
    lista = [{"wzor": r[0], "zamiana": r[1], **({"regex": True} if len(r) > 2 else {})}
             for r in reguly]
    return cp._zastosuj_zamiany(tekst, lista)


def test_wynik_podniesiony_w_wyrazie_wersalikami():
    assert zastosuj("ЖДАТЬ", ("Ж", "Zh")) == "ZHДАТЬ"


def test_wyraz_z_wielkiej_litery_zostaje_mieszany():
    # „Ждать" to nie krzyk, tylko poczatek zdania.
    assert zastosuj("Ждать", ("Ж", "Zh")) == "Zhдать"


def test_samotna_litera_to_inicjal_nie_krzyk():
    assert zastosuj("Ж", ("Ж", "Zh")) == "Zh"
    assert zastosuj("Ж. Kowalski", ("Ж", "Zh")) == "Zh. Kowalski"


def test_wynik_bez_malych_liter_dziala_jak_dawniej():
    assert zastosuj("ЖДАТЬ", ("Ж", "Ж")) == "ЖДАТЬ"
    assert zastosuj("abc", ("b", "X")) == "aXc"


def test_wzorzec_ze_spacja_wymaga_wersalikow_w_calosci():
    # Wariant reguly, w ktorej wielka litera zastepowala granice slowa
    # (`de/rosyjski`: ` SP` -> `SzP`): w wersalikach granica jest jawna, wiec
    # wzorzec obejmuje spacje i SASIEDNI wyraz - podniesienie tylko gdy oba
    # wyrazy sa wersalikami.
    assert zastosuj("ALA SPORT", (" SP", " Shp")) == "ALA SHPORT"
    assert zastosuj("ala SPORT", (" SP", " Shp")) == "ala ShpORT"


def test_wiele_trafien_w_jednym_wyrazie():
    assert zastosuj("ЖЖ", ("Ж", "Zh")) == "ZHZH"


def test_regula_regex_z_grupa():
    # Wzorzec z odwolaniem do grupy: podnosimy ROZWINIETY wynik, nie szablon.
    regula = (r"([BCDFGKPTbcdfgkpt])\b", r"\1a", True)
    assert zastosuj("DESK", regula) == "DESKA"
    assert zastosuj("Desk", regula) == "Deska"


def test_pre_pass_diakrytykow_tez_podnosi():
    podstawy = {"polskie_znaki": [{"wzor": "Þ", "zamiana": "Th"},
                                  {"wzor": "Ð", "zamiana": "Th"}]}
    assert cp._usun_polskie_znaki("ÞAÐ", podstawy) == "THATH"
    assert cp._usun_polskie_znaki("Það", podstawy) == "Thað"


def test_pismo_bez_wielkosci_liter_nie_jest_wersalikami():
    # Alfabet bez rozroznienia wielkosci liter nie moze udawac krzyku.
    assert zastosuj("日本語", ("日", "ni")) == "ni本語"


def test_podniesienie_utrzymuje_wyraz_w_wersalikach_dla_kolejnych_regul():
    assert zastosuj("ŽĎ", ("Ž", "Zh"), ("Ď", "Dj")) == "ZHDJ"


if __name__ == "__main__":
    testy = [(nazwa, obiekt) for nazwa, obiekt in sorted(globals().items())
             if nazwa.startswith("test_") and callable(obiekt)]
    bledy = []
    for nazwa, funkcja in testy:
        try:
            funkcja()
            print(f"  OK   {nazwa}")
        except AssertionError as exc:
            bledy.append(nazwa)
            print(f"  FAIL {nazwa}: {exc}")
    print(f"\n{len(testy) - len(bledy)}/{len(testy)} zaliczonych.")
    sys.exit(1 if bledy else 0)
