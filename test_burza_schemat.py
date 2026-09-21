"""
test_burza_schemat.py - Kontrakt schematu Burzy i silnika akcentow z Ksiegi (19.3).

Dwa niezalezne defekty tej samej klasy „martwy kod, ktory ozyl":

1. Klucz JSON `streszczenie` w `SCHEMA_BURZA`. Prompt Burzy nie mowi o nim ani
   slowa (sufiksy zniesione w v18.13), wiec do refaktoru na structured outputs
   model po prostu go nie wypelnial. Po refaktorze galaz tury mowi „fill in ALL
   fields of this branch", wiec pole BEZ instrukcji promptowej dostaje znaczenie
   wymyslone przez model - zmierzone na projekcie uzytkownika: model wpisywal
   tam ZAPOWIEDZ przyszlych zdarzen, a GUI podstawialo to jako Pamiec
   Dlugotrwala, ktora ma streszczac PRZESZLOSC.
   Niezmiennik: kazde pole schematu Burzy jest WYMAGANE (a wiec opisane
   w prompcie), a nadmiarowy klucz w odpowiedzi jest bledem struktury.

2. Reguly ad-hoc akcentu w Ksiedze Swiata (`'w' na 'v'`) - drugi, cichy kanal
   psucia ortografii: spojnik `na` byl zaszyty po polsku (8 z 9 paczek bez
   szans), skladni nie opisywal zaden podrecznik, a tresc reguly jechala do
   modelu w `world_context` jako instrukcja lamania ortografii.
   Niezmiennik: akcent deklaruje sie WYLACZNIE nazwa z pliku `akcenty/*.yaml`.

Uruchom:  .venv/Scripts/python -m pytest test_burza_schemat.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_burza_schemat.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import jsonschema

import core_rezyser as cr
import rezyser_ai as rai

ODPOWIEDZ_OK = {
    "opcje": [
        {"tytul": "T", "opis": "O", "cel_sceny": "C"},
    ],
}


def _pola_opcjonalne(schema, sciezka="root"):
    """Lista `(sciezka, pole)` dla pol obiektu, ktorych nie ma w `required`."""
    wynik = []
    if not isinstance(schema, dict):
        return wynik
    if schema.get("type") == "object":
        props = set((schema.get("properties") or {}).keys())
        wymagane = set(schema.get("required") or [])
        wynik += [(sciezka, p) for p in sorted(props - wymagane)]
    for klucz, pod in (schema.get("properties") or {}).items():
        wynik += _pola_opcjonalne(pod, f"{sciezka}.{klucz}")
    if "items" in schema:
        wynik += _pola_opcjonalne(schema["items"], f"{sciezka}[]")
    return wynik


def test_schemat_nie_zna_klucza_streszczenie():
    assert "streszczenie" not in (SCHEMA_PROPS := set(
        rai.SCHEMA_BURZA["properties"])), SCHEMA_PROPS
    # To samo w schemacie wysylanym do API (galezie `anyOf` dyskryminatora).
    assert "streszczenie" not in json.dumps(rai.SCHEMA_BURZA_API)


def test_kazde_pole_burzy_jest_wymagane():
    """Pole opcjonalne = pole, o ktorym prompt milczy, a model je wypelni."""
    assert _pola_opcjonalne(rai.SCHEMA_BURZA) == []


def test_nadmiarowy_klucz_to_blad_struktury():
    """Gdyby model dopisal `streszczenie` z wlasnej woli - retry, nie zapis."""
    z_nadmiarem = dict(ODPOWIEDZ_OK, streszczenie="zapowiedz przyszlosci")
    jsonschema.validate(instance=ODPOWIEDZ_OK, schema=rai.SCHEMA_BURZA)
    try:
        jsonschema.validate(instance=z_nadmiarem, schema=rai.SCHEMA_BURZA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("the schema accepted a surplus `streszczenie` key")


def test_wynik_burzy_nie_nosi_streszczenia():
    wynik = rai.WynikBurzy()
    assert not hasattr(wynik, "streszczenie"), vars(wynik)


def test_nie_ma_drugiej_drogi_do_pamieci_dlugotrwalej():
    """Tagowa ekstrakcja `<STRESZCZENIE>` zniesiona razem z kluczem JSON."""
    assert not hasattr(rai, "wyciagnij_streszczenie")
    assert not hasattr(rai.WynikGeneracji(tekst_odpowiedzi=""), "nowe_streszczenie")


def test_persystencja_ignoruje_klucz_ze_starych_plikow():
    katalog = Path(tempfile.mkdtemp())
    try:
        projekt = cr.ProjektRezysera(app_dir=str(katalog))
        projekt.nazwa_pliku = "proba"
        sciezka = Path(projekt.zapisz_brainstorm(ODPOWIEDZ_OK["opcje"]))
        zapisane = json.loads(sciezka.read_text(encoding="utf-8"))
        assert "streszczenie" not in zapisane, zapisane
        # Plik z v19.2 (z kluczem) musi sie dalej wczytywac.
        sciezka.write_text(
            json.dumps({**zapisane, "streszczenie": "stara zapowiedz"}),
            encoding="utf-8",
        )
        wczytane = projekt.wczytaj_brainstorm("proba")
        assert wczytane == {"opcje": ODPOWIEDZ_OK["opcje"]}, wczytane
    finally:
        shutil.rmtree(katalog, ignore_errors=True)


def test_regula_adhoc_z_ksiegi_nie_psuje_tekstu():
    lore = "[Joana] - zamien 'w' na 'v'\n"
    tekst = "[Joana] Wielka woda.\n"
    assert cr.zbuduj_mape_akcentow(lore, "pl") == {}
    assert cr.zastosuj_akcenty_uniwersalne(tekst, lore, "pl") == tekst


def test_nazwa_akcentu_bez_pliku_nie_trafia_do_mapy():
    """Mapa obiecuje tylko to, co silnik potrafi nalozyc."""
    lore = "[Kai] - ma akcent szwedzki\n"
    assert cr.zbuduj_mape_akcentow(lore, "pl") == {}


def test_znany_akcent_dalej_dziala_i_daje_kanoniczne_id():
    lore = "[Marek] - ma akcent francuski\n"
    mapa = cr.zbuduj_mape_akcentow(lore, "pl")
    assert mapa == {"marek": {"nazwa": "francuski"}}, mapa
    wynik = cr.zastosuj_akcenty_uniwersalne("[Marek] Wielka szansa.\n", lore, "pl")
    assert wynik != "[Marek] Wielka szansa.\n", wynik
    assert wynik.startswith("[Marek] ")


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
