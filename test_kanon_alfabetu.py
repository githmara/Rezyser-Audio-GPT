"""
test_kanon_alfabetu.py - Kontrakty kanonu `alfabet` vs pre-pass (v19.5).

Bramka `audyt_podstaw` pilnuje DANYCH: czy paczka nie splaszcza wlasnej litery
i czy cala lacinka wychodzi z pre-passu. Nie odpowiada natomiast na pytanie
o SKUTEK w silniku - a to on byl tu realna usterka. Do v19.4.2 paczka `pl`
romanizowala wlasne litery w `podstawy.yaml::polskie_znaki`, wiec:

  * szyfr Cezara nigdy nie widzial dziewieciu z trzydziestu pieciu liter
    swojego alfabetu (deszyfracja polskiego tekstu nie byla wierna),
  * `pl/akcenty/rosyjski.yaml` musial wylaczyc pre-pass W CALOSCI, zeby
    zachowac s/z dla swoich zmiekczen - i przez to przepuszczal do cyrylicy
    obca lacinke jawnym tekstem.

Testy nizej mierza obie te wlasnosci na REALNEJ paczce, bo obie sa umowa
z uzytkownikiem, nie detalem implementacji.

Uruchom:  .venv/Scripts/python -m pytest test_kanon_alfabetu.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_kanon_alfabetu.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_poliglota as cp

# Pangram z kompletem polskich diakrytykow, w obu wielkosciach.
_PANGRAM = "Zazolc gesla jazn"
_PANGRAM_PL = "Zażółć gęślą jaźń"
_PANGRAM_PL_DUZE = _PANGRAM_PL.upper()


def _cezar(tekst: str, przesuniecie: int) -> str:
    return cp.przetworz(tekst, cp.TRYB_SZYFRANT, "pl", "cezar",
                        {"przesuniecie": przesuniecie, "wymus_jezyk": "pl"})


def test_cezar_pl_jest_odwracalny_na_diakrytykach():
    """Szyfr i deszyfr polskiego tekstu wracaja do zrodla ZNAK W ZNAK.

    To nie jest test algorytmu - Cezar byl poprawny zawsze. To test tego, czy
    tekst w ogole DOCHODZI do niego w swojej postaci: pre-pass paczki biegnie
    przed szyfrem, wiec splaszczanie wlasnych liter odbieralo alfabetowi
    dziewiec pozycji, zanim cokolwiek sie przesunelo.
    """
    for zrodlo in (_PANGRAM_PL, _PANGRAM_PL_DUZE):
        for shift in (1, 7, 17):
            szyfr = _cezar(zrodlo, shift)
            assert szyfr != zrodlo, f"szyfr nie zmienil tekstu (shift {shift})"
            assert _cezar(szyfr, -shift) == zrodlo, \
                f"deszyfracja nie wierna: {zrodlo!r} -> {szyfr!r} -> " \
                f"{_cezar(szyfr, -shift)!r}"


def test_cezar_pl_przesuwa_wlasne_litery():
    """Polski diakrytyk MUSI sie przesunac, a nie przejsc jak cyfra.

    Kontrola komplementarna do odwracalnosci: tekst zlozony wylacznie z liter
    diakrytycznych rozni sie od zrodla tylko wtedy, gdy alfabet naprawde je
    zawiera. Splaszczanie w pre-passie dawalo tu zaszyfrowane `A`/`C`/`E`...
    """
    zrodlo = "ĄĆĘŁŃÓŚŹŻ"
    szyfr = _cezar(zrodlo, 3)
    assert len(szyfr) == len(zrodlo), f"dlugosc sie rozjechala: {szyfr!r}"
    assert szyfr != zrodlo
    assert _cezar(szyfr, -3) == zrodlo


def test_romanizacja_przetrwala_przeprowadzke_do_akcentow():
    """Siedem akcentow `pl` nadal romanizuje wlasne litery paczki.

    Pary wyszly z `podstawy.yaml` na czolo `zamiany:`. Rownowaznosc opiera sie
    na tym, ze pre-pass i tak biegl PRZED `zamiany` - ale opiera sie tez na
    tym, ze pary faktycznie sa w kazdym z siedmiu plikow, a nie w szesciu.
    """
    for akcent in ("angielski", "finski", "francuski", "hiszpanski",
                   "islandzki", "niemiecki", "wloski"):
        wynik = cp.zastosuj_reguly_fonetyczne(_PANGRAM_PL, akcent, "pl")
        for diakrytyk in _PANGRAM_PL:
            assert diakrytyk.isascii() or diakrytyk not in wynik, \
                f"{akcent}: `{diakrytyk}` przeszlo nieromanizowane -> {wynik!r}"


def test_rosyjski_zachowuje_zmiekczenia_i_czysci_obca_lacinke():
    """Jeden akcent, dwie wlasnosci, ktore do v19.4.2 wykluczaly sie wzajemnie.

    `pl/rosyjski` transliteruje polskie diakrytyki WPROST na cyrylice, wiec
    potrzebuje ich w wejsciu - i dlatego mial pre-pass wylaczony. Kosztem bylo
    to, ze obca lacinka (`S` z haczkiem, umlauty) wchodzila do cyrylicy jawnym
    tekstem. Od v19.5 obie rzeczy sa prawdziwe naraz.
    """
    wynik = cp.zastosuj_reguly_fonetyczne("jaźń świt", "rosyjski", "pl")
    assert not wynik.isascii(), "brak transliteracji na cyrylice"
    assert "ź" not in wynik and "ś" not in wynik, \
        f"polski diakrytyk przezyl transliteracje: {wynik!r}"

    obce = cp.zastosuj_reguly_fonetyczne(
        "Škoda Řehoř z Zürichu", "rosyjski", "pl")
    for znak in "ŠŘřü":
        assert znak not in obce, \
            f"obcy znak `{znak}` doszedl do cyrylicy: {obce!r}"


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
