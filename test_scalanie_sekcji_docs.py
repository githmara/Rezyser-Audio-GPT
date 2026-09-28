"""
test_scalanie_sekcji_docs.py - Tryb `--klucz` buildera docs trzyma kolejnosc PL (v19.8.2).

Do v19.8.1 scalanie robilo `dict(istniejace).update(przetlumaczone)`, wiec
NOWA sekcja wstawiona w srodek polskiego szablonu ladowala w paczce obcej na
koncu pliku - a generator renderuje sekcje w kolejnosci pliku.

  1. Nowy klucz ze srodka PL trafia w to samo miejsce w wyniku.
  2. Przetlumaczona sekcja zastepuje istniejaca, reszta zostaje nietknieta.
  3. Sierota (klucz tylko w pliku docelowym) nie ginie - idzie na koniec.

Uruchom:  .venv/Scripts/python -m pytest test_scalanie_sekcji_docs.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_scalanie_sekcji_docs.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import buduj_wielojezyczne_docs as bd

PL = {"wstep": "PL1", "nowa": "PL2", "zakonczenie": "PL3"}


def test_nowy_klucz_w_miejscu_z_pl():
    wynik = bd.scal_sekcje_w_kolejnosci_pl(
        PL, {"wstep": "EN1", "zakonczenie": "EN3"}, {"nowa": "EN2"})
    assert list(wynik) == ["wstep", "nowa", "zakonczenie"]
    assert wynik == {"wstep": "EN1", "nowa": "EN2", "zakonczenie": "EN3"}


def test_przetlumaczona_zastepuje_istniejaca():
    wynik = bd.scal_sekcje_w_kolejnosci_pl(
        PL, {"wstep": "stare", "nowa": "EN2", "zakonczenie": "EN3"},
        {"wstep": "nowe"})
    assert list(wynik) == ["wstep", "nowa", "zakonczenie"]
    assert wynik["wstep"] == "nowe" and wynik["nowa"] == "EN2"


def test_sierota_nie_ginie():
    wynik = bd.scal_sekcje_w_kolejnosci_pl(
        PL, {"sierota": "X", "wstep": "EN1", "zakonczenie": "EN3"},
        {"nowa": "EN2"})
    assert list(wynik) == ["wstep", "nowa", "zakonczenie", "sierota"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
