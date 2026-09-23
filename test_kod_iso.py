"""
test_kod_iso.py - Regresja: znany kod jezyka celu NIE kosztuje mikrocallu ISO (19.8).

Dwa kontrakty, oba zmierzone przez WYKONANIE (stub `core_llm.wywolaj_llm`,
zero sieci, `runtime/` w katalogu tymczasowym):

  1. `tlumacz_ai.tlumacz_dlugi_tekst(kod_iso=...)` z poprawnym kodem nie pyta
     modelu o kod BCP-47 i oddaje podany kod w `WynikTlumaczenia.iso`; pusty
     albo nieparsowalny `kod_iso` zostawia dawna sciezke (jeden mikrocall).
     Sekcje docs (`buduj_wielojezyczne_docs`) placily dotad za ten mikrocall
     per sekcja i per probe, a wyniku nie czytaly.
  2. `core_poliglota.kod_iso_z_nazwy_jezyka` rozpoznaje nazwe DOKLADNIE (po
     foldzie wielkosci liter i diakrytykow) z trzech zrodel: polska nazwa
     kanonu lingua, nazwa enuma jako angielski przymiotnik, natywna nazwa
     wdrozonej paczki. Wszystko inne to `""` - czyli „zapytaj model", nie
     zgadywanie (`Norwegian` nie jest enumem lingua, `pt-BR` to wariant).

Uruchom:  .venv/Scripts/python -m pytest test_kod_iso.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_kod_iso.py
"""

import contextlib
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_llm as cl
import core_poliglota as cp
import tlumacz_ai

TRESC = "Krotki tekst zrodlowy do przetlumaczenia.\n"

_licznik = {"blok": 0, "iso": 0}


def _stub_llm(klient, *, model, system, messages, max_tokens, temperature,
              timeout, segmenty=None, wymusz_json=False, thinking_budget=0,
              schema_json=None, slad=None):
    """Model-echo; prompt ISO rozpoznawany po `BCP-47` (jak w `_pobierz_iso`)."""
    tresc_user = messages[0]["content"]
    if "BCP-47" in tresc_user:
        _licznik["iso"] += 1
        return "is", "end_turn"
    _licznik["blok"] += 1
    return tresc_user, "end_turn"


@contextlib.contextmanager
def _srodowisko():
    katalog = tempfile.mkdtemp()
    stary_llm = cl.wywolaj_llm
    cl.wywolaj_llm = _stub_llm
    _licznik["blok"] = _licznik["iso"] = 0
    try:
        yield katalog
    finally:
        cl.wywolaj_llm = stary_llm
        shutil.rmtree(katalog, ignore_errors=True)


def _przebieg(katalog: str, **kwargs):
    return tlumacz_ai.tlumacz_dlugi_tekst(
        tresc=TRESC, jezyk_docelowy="fiński", klient=None,
        runtime_dir=katalog, oryginalna_nazwa="kod_iso",
        model_tlumacz="stub", **kwargs)


def test_znany_kod_pomija_mikrocall():
    with _srodowisko() as katalog:
        postep: list[str] = []
        wynik = _przebieg(katalog, kod_iso="fi",
                          on_postep=lambda info: postep.append(info.klucz_i18n))
        assert _licznik == {"blok": 1, "iso": 0}, _licznik
        assert wynik.iso == "fi", wynik
        assert wynik.ostrzezenia == [], wynik.ostrzezenia
        assert "ai_postep_iso" not in postep, postep


def test_kod_z_podtagiem_normalizowany():
    with _srodowisko() as katalog:
        wynik = _przebieg(katalog, kod_iso="pt_br")
        assert _licznik["iso"] == 0, _licznik
        assert wynik.iso == "pt-BR", wynik


@pytest.mark.parametrize("kod", ["", "   ", "fiński", "123"])
def test_brak_lub_smieciowy_kod_wraca_do_mikrocallu(kod):
    with _srodowisko() as katalog:
        wynik = _przebieg(katalog, kod_iso=kod)
        assert _licznik["iso"] == 1, _licznik
        assert wynik.iso == "is", "kod ma pochodzic z (zastubowanego) modelu"


@pytest.mark.parametrize("nazwa,kod", [
    ("Fiński", "fi"), ("finski", "fi"), ("  FIŃSKI ", "fi"),
    ("Finnish", "fi"), ("FINNISH", "fi"),
    ("Suomi", "fi"), ("Íslenska", "is"), ("islenska", "is"),
    ("Русский", "ru"), ("Español", "es"), ("Français", "fr"),
    ("Islandzki", "is"), ("Norweski", "nb"), ("Słoweński", "sl"),
    ("Arabski", "ar"), ("Arabic", "ar"),
])
def test_resolver_trafia(nazwa, kod):
    assert cp.kod_iso_z_nazwy_jezyka(nazwa) == kod


@pytest.mark.parametrize("nazwa", [
    "", "   ", "Norwegian", "Slovenian", "pt-BR", "brazylijski portugalski",
    "fińsku", "Suomi (Finlandia)", "Klingon",
])
def test_resolver_nie_zgaduje(nazwa):
    assert cp.kod_iso_z_nazwy_jezyka(nazwa) == ""


def test_natywne_nazwy_tylko_z_paczek_wdrozonych(monkeypatch):
    """Natywna nazwa spoza `dostepne_jezyki_bazowe()` nie ma prawa trafic.

    Audyt 19.8: dawna wersja sprawdzala „svenska", ktorej nie ma jak wpasc do
    mapy (`natywna_nazwa('sv')` zwraca po prostu `'sv'`) - asercja nie mogla
    pasc. Teraz wycofujemy WDROZONA paczke `fi` i patrzymy, czy „Suomi" znika.
    """
    wdrozone = set(cp.dostepne_jezyki_bazowe())
    for kod in wdrozone:
        nazwa = cp.natywna_nazwa(kod)
        assert cp.kod_iso_z_nazwy_jezyka(nazwa) == kod, (kod, nazwa)
    assert cp.kod_iso_z_nazwy_jezyka("Suomi") == "fi"
    monkeypatch.setattr(cp, "dostepne_jezyki_bazowe",
                        lambda: sorted(wdrozone - {"fi"}))
    assert cp.kod_iso_z_nazwy_jezyka("Suomi") == ""
    assert cp.kod_iso_z_nazwy_jezyka("fiński") == "fi", "kanon lingua zostaje"


def test_klucz_niejednoznaczny_wypada(monkeypatch):
    """Nazwa wskazujaca na dwa kody = „zapytaj model", nie wynik kolejnosci petli."""
    oryginal = cp.natywna_nazwa
    monkeypatch.setattr(cp, "natywna_nazwa",
                        lambda kod: "Fiński" if kod == "is" else oryginal(kod))
    assert cp.kod_iso_z_nazwy_jezyka("fiński") == ""
    assert cp.kod_iso_z_nazwy_jezyka("Finnish") == "fi"


# Uruchomienie jako skrypt - deleguje do pytesta (kanon v19.2.1, §6.11).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
