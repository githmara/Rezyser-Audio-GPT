"""
test_pola_schematu_w_prompcie.py - kazde pole schematu JSON jest opisane w prompcie (v19.20.0).

Dlug 19.3.0. Pole schematu structured outputs, o ktorym prompt nie mowi ani
slowa, dostaje znaczenie WYMYSLONE przez model - zmierzone na Burzy (19.3):
`streszczenie` bez instrukcji model wypelnial zapowiedzia PRZYSZLYCH zdarzen,
a GUI podstawialo to jako Pamiec Dlugotrwala. `test_burza_schemat.py` pilnuje
tego dla Burzy przez "wszystkie pola wymagane"; tura Opowiesci ma pola
opcjonalne z zalozenia, wiec potrzebna jest bramka GENERYCZNA: nazwa kazdego
pola (rekurencyjnie: properties, items, anyOf/oneOf) musi stac w prompcie
systemowym, ktory jedzie z tym schematem - w KAZDEJ paczce i w kazdym trybie.

Pierwszy przeglad (2026-11-15) znalazl jedna dziure: blok `stan.fiolka`
(`obecna`, `uzyto_razy`, `zniszczona`) jest w schemacie tury wszystkich trzech
trybow narracyjnych, a opisuje go tylko prompt Mniejszego Zla. Zamknieta w tym
samym cyklu schematem PER TRYB (`opowiesci_ai.SCHEMA_TURA_PER_TRYB`): tryby 3/4
nie dostaja juz `stan.fiolka` ani w walidowanym kanonie testu, ani w kopii API.
`ZNANE_DZIURY` zostaje jako mechanizm (pusty) - wpis, ktory przestal byc
prawdziwy, zglasza sie sam.

Uruchom:  .venv/Scripts/python -m pytest test_pola_schematu_w_prompcie.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_pola_schematu_w_prompcie.py
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_poliglota as cp
import core_zastepcze as cz
import opowiesci_ai as oai
import przepisy_rezysera as pr
import rezyser_ai as rai


def pola_schematu(schemat, wynik=None) -> set[str]:
    """Nazwy wszystkich pol schematu, rekurencyjnie."""
    wynik = set() if wynik is None else wynik
    if isinstance(schemat, dict):
        for nazwa, pod in (schemat.get("properties") or {}).items():
            wynik.add(nazwa)
            pola_schematu(pod, wynik)
        for klucz in ("items", "anyOf", "oneOf", "allOf"):
            pod = schemat.get(klucz)
            for element in (pod if isinstance(pod, list) else [pod]):
                if isinstance(element, dict):
                    pola_schematu(element, wynik)
    return wynik


def nieopisane(schemat, prompt: str) -> set[str]:
    """Pola, ktorych nazwa nie stoi w prompcie jako osobne slowo."""
    return {p for p in pola_schematu(schemat)
            if not re.search(r"(?<![A-Za-z0-9_])" + re.escape(p) + r"(?![A-Za-z0-9_])",
                             prompt)}


# (zrodlo, tryb) -> pola swiadomie nieopisane, z powodem w docstringu modulu.
ZNANE_DZIURY: dict[tuple[str, int], frozenset[str]] = {}

KODY = cp.dostepne_jezyki_bazowe()


def _przypadki():
    for kod in KODY:
        for id_przepisu, schemat in (("burza", rai.SCHEMA_BURZA),
                                     ("skrypt", rai.SCHEMA_SKRYPT)):
            yield f"{kod}/rezyser/{id_przepisu}", ("rezyser", 0), schemat, (
                lambda k=kod, i=id_przepisu: pr.buduj_prompt_systemowy(
                    pr.zaladuj_przepis(i, k), ""))
        for tryb in (oai.TRYB_SWOBODNY, oai.TRYB_WYBOROW, oai.TRYB_MNIEJSZE_ZLO):
            yield f"{kod}/opowiesci/tryb{tryb}", ("opowiesci", tryb), oai.SCHEMA_TURA_PER_TRYB[tryb], (
                lambda k=kod, t=tryb: oai._zbuduj_prompt_systemowy(t, k))
    yield "core_zastepcze", ("zastepcze", 0), cz.SCHEMAT, (lambda: cz.SYSTEM)


PRZYPADKI = list(_przypadki())


def test_zakres_nie_jest_pusty():
    assert len(KODY) >= 9
    assert len(PRZYPADKI) == len(KODY) * 5 + 1


@pytest.mark.parametrize("nazwa, zrodlo, schemat, prompt",
                         PRZYPADKI, ids=[p[0] for p in PRZYPADKI])
def test_kazde_pole_schematu_jest_w_prompcie(nazwa, zrodlo, schemat, prompt):
    brak = nieopisane(schemat, prompt()) - ZNANE_DZIURY.get(zrodlo, frozenset())
    assert not brak, (
        f"{nazwa}: the schema sends field(s) {sorted(brak)} that the system prompt "
        f"never mentions - the model will invent their meaning")


def test_znane_dziury_sa_wciaz_prawdziwe():
    """Zamknieta dziura musi zniknac z `ZNANE_DZIURY`, inaczej maskuje regres.

    Petla zamiast parametryzacji: pusty `ZNANE_DZIURY` dalby pytestowi pusty
    zbior parametrow, czyli skip, ktory nic nie mowi.
    """
    for zrodlo, dziury in ZNANE_DZIURY.items():
        for nazwa, z, schemat, prompt in PRZYPADKI:
            if z == zrodlo:
                wciaz = nieopisane(schemat, prompt()) & dziury
                assert wciaz == dziury, (
                    f"{nazwa}: {sorted(dziury - wciaz)} are described now "
                    f"- remove them from ZNANE_DZIURY")


def test_fiolka_tylko_w_mniejszym_zlu():
    """Schemat API trybow 3/4 nie zna fiolki; Mniejsze Zlo tak."""
    def stan_api(tryb):
        return oai.SCHEMA_TURA_API_PER_TRYB[tryb]["anyOf"][0]["properties"]["stan"]
    for tryb in (oai.TRYB_SWOBODNY, oai.TRYB_WYBOROW):
        assert "fiolka" not in stan_api(tryb)["properties"]
        assert stan_api(tryb)["additionalProperties"] is False
    assert "fiolka" in stan_api(oai.TRYB_MNIEJSZE_ZLO)["properties"]
    # Kanon walidacji nietkniety: stary zapis 3/4 z fiolka w stanie przechodzi.
    assert "fiolka" in oai.SCHEMA_TURA["properties"]["stan"]["properties"]


@pytest.mark.parametrize("tryb", [oai.TRYB_SWOBODNY, oai.TRYB_WYBOROW, oai.TRYB_MNIEJSZE_ZLO])
def test_generuj_ture_wysyla_schemat_swojego_trybu(tryb, monkeypatch):
    wyslane = []
    tura = ('{"narracja": "n", "wybory": [], "postacie_aktywne": [], '
            '"stan": {"lokacja": "x"}, "meta": {}}')

    def atrapa(*_a, **kw):
        wyslane.append(kw["schema_json"])
        return tura, "end_turn"

    monkeypatch.setattr(oai, "_wywolaj_claude", atrapa)
    oai.generuj_ture(None, oai.SnapshotOpowiesci(nazwa_gry="t", numer_tury=1), "go", tryb)
    assert wyslane == [oai.SCHEMA_TURA_API_PER_TRYB[tryb]]


def test_detektor_lapie_pole_i_granice_slowa():
    schemat = {"type": "object", "properties": {
        "tekst": {"type": "string"},
        "lista": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}}}}}}
    assert pola_schematu(schemat) == {"tekst", "lista", "id"}
    # `kontekst` nie opisuje pola `tekst`, `idea` nie opisuje `id`.
    assert nieopisane(schemat, "kontekst, lista, idea") == {"tekst", "id"}
    assert nieopisane(schemat, "`tekst`, `lista[].id`") == set()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
