# -*- coding: utf-8 -*-
"""
test_szyfr_zamiany.py - Bramka gałęzi "czyste zamiany" w Szyfrancie (19.6).

Manager Regul od zawsze oferuje typ `szyfr_zamiany`: plik `szyfry/*.yaml`
bez pola `algorytm`, z cala trescia w liscie `zamiany`. Do 19.5.0 dispatcher
`core_poliglota._przetworz_szyfrant` znal WYLACZNIE galaz algorytmiczna, wiec
taki plik ladowal sie do listy w GUI i dopiero przy uzyciu rzucal
`ValueError: Nieznany algorytm szyfru: ""`. Jeden z dziewieciu typow kreatora
produkowal wiec plik martwy z definicji - i zadna bramka tego nie widziala,
bo zaden plik w repozytorium tej galezi nie uzywa (wszystkie szesc szyfrow
w paczkach jest algorytmicznych).

Niezmienniki pilnowane tutaj:
  G1 - szyfr bez `algorytm`, z lista `zamiany`, PRZETWARZA tekst (nie rzuca).
  G2 - przed lista `zamiany` biegnie pre-pass diakrytykow i czyszczenie TTS,
       tak samo jak dla szyfrow algorytmicznych. Wzorzec oparty na znaku,
       ktory pre-pass paczki splaszcza, jest wiec MARTWY (a wzorzec na
       wlasna litere paczki dziala) - to samo ostrzezenie, co w promptach.
  G3 - galaz algorytmiczna nie zmienila zachowania (cezar dalej szyfruje).
  G4 - plik bez `algorytm` I bez `zamiany` dalej jest bledem, ale komunikat
       nazywa brak po imieniu zamiast mowic o "nieznanym algorytmie".

Uruchom:  .venv/Scripts/python -m pytest test_szyfr_zamiany.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_szyfr_zamiany.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_poliglota as cp

_LEET = {
    "id": "leet",
    "etykieta": "Leet",
    "iso": "pl",
    "kategoria": "szyfr",
    "kolejnosc": 100,
    "zamiany": [
        {"wzor": "a", "zamiana": "@"},
        {"wzor": "o", "zamiana": "0"},
    ],
}


def _uruchom(cfg: dict, tekst: str, opcje: dict | None = None) -> str:
    """Odpala dispatcher na PODANEJ konfiguracji, bez pliku na dysku.

    Segmentacja pobiera regule per akapit przez `wariant_po_id`, wiec podmiana
    tej funkcji jest jedynym sposobem, by zmierzyc galaz, ktorej zaden plik
    w repozytorium jeszcze nie uzywa. Podmiana jest cofana w `finally`.
    """
    oryginalna = cp.wariant_po_id
    cp.wariant_po_id = lambda tryb, jezyk, wariant: cfg
    try:
        return cp._przetworz_szyfrant(tekst, "pl", cfg, dict(opcje or {}))
    finally:
        cp.wariant_po_id = oryginalna


def test_g1_szyfr_bez_algorytmu_stosuje_zamiany():
    wynik = _uruchom(_LEET, "Ala ma kota.")
    assert wynik == "Al@ m@ k0t@.", ascii(wynik)


def test_g2_pre_pass_i_czyszczenie_biegna_przed_zamianami():
    # Liczba zamieniona na slowa (czyszczenie TTS z normalizacja) i polskie
    # diakrytyki po pre-passie - dokladnie jak w szyfrach algorytmicznych.
    wynik = _uruchom(_LEET, "Zolw ma 2 lapy (naprawde).")
    assert "2" not in wynik and "dw@" in wynik, ascii(wynik)
    assert "naprawde" not in wynik, ascii(wynik)
    # Wzorzec oparty na znaku, ktory pre-pass paczki spłaszcza, jest MARTWY.
    # Dla paczki `pl` to NIE sa jej wlasne litery (od 19.5.0 stoja w `alfabet`
    # i pre-pass ich nie tyka), tylko obca lacinka: `e` z akcentem wychodzi
    # z pre-passu jako gole `e`, wiec regula na nia nigdy nie trafia.
    cfg = dict(_LEET, zamiany=[{"wzor": "é", "zamiana": "ZZZ"}])
    wynik = _uruchom(cfg, "Bardzo café tutaj.")
    assert "ZZZ" not in wynik and "cafe" in wynik, ascii(wynik)
    # Kontrola dodatnia dla tej samej pary: wlasna litera paczki PRZEZYWA
    # pre-pass, wiec regula na nia dziala (to jest kanon 19.5.0, nie przypadek).
    cfg = dict(_LEET, zamiany=[{"wzor": "ł", "zamiana": "ZZZ"}])
    wynik = _uruchom(cfg, "Bardzo łatwo.")
    assert "ZZZ" in wynik, ascii(wynik)


def test_g3_galaz_algorytmiczna_bez_zmian():
    cezar = cp.wariant_po_id(cp.TRYB_SZYFRANT, "pl", "cezar")
    assert cezar, "pack pl has no cezar cipher - the test lost its input"
    wynik = cp._przetworz_szyfrant("Ala ma kota.", "pl", cezar,
                                   {"przesuniecie": 3})
    assert wynik == "Cnc oc mqwc.", ascii(wynik)


def test_g4_brak_obu_pol_to_blad_nazwany_po_imieniu():
    cfg = {k: v for k, v in _LEET.items() if k != "zamiany"}
    try:
        _uruchom(cfg, "Ala ma kota.")
    except ValueError as exc:
        tresc = str(exc)
        assert "`algorytm`" in tresc and "`zamiany`" in tresc, ascii(tresc)
        assert "Nieznany algorytm" not in tresc, ascii(tresc)
    else:
        raise AssertionError("a cipher with neither field must raise")


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
