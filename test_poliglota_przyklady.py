#!/usr/bin/env python
"""
test_poliglota_przyklady.py — przykłady dydaktyczne brata Poligloty (19.18).

Pomiar myślenia 2026-11-12: trzy pliki fi/is odpadały w OBU wariantach
(z myśleniem i bez), bo bramka żądała czegoś, czego prompt zabraniał:

* `oczyszczenie` — silnik nie liczył przykładu „123" → słownie, więc prompt
  kazał zostawić parę źródłową, a bramka odrzucała „123" jako polskie słowo;
* `jakanie` (fi) — polskie „ja" szukane jako PODCIĄG trafiało w fińskie
  „kirjain" i w spójnik „ja".

Bez API.

Uruchom:  .venv/Scripts/python -m pytest test_poliglota_przyklady.py -q
"""
from __future__ import annotations

import pytest

import buduj_wielojezyczne_poliglota as bwp

OPIS_FI = ('Jokainen kirjain ja sana toistetaan: "tietokone" → "t-t-tietokone", '
           '"se" → "se".')


def _problemy(tgt: str, zakazane: tuple[str, ...]) -> list[str]:
    problemy, _uwagi = bwp.waliduj_jednostke(
        OPIS_FI, tgt, bwp.KLASA_OPIS, slowa_zakazane=zakazane)
    return [p for p in problemy if "ŹRÓDŁA POLSKIEGO" in p]


def test_polskie_slowo_jako_podciag_lub_spojnik_nie_jest_przeciekiem() -> None:
    assert _problemy(OPIS_FI, ("ja", "komputer")) == []


def test_polskie_slowo_jako_zrodlo_pary_jest_przeciekiem() -> None:
    tgt = OPIS_FI.replace('"se" → "se"', '"ja" → "ja"')
    assert len(_problemy(tgt, ("ja",))) == 1


def test_wspolne_slowo_nie_jest_zakazane() -> None:
    pary_pl = [("123", "sto dwadzieścia trzy"), ("komputer", "k-k-komputer")]
    wyliczone = [{"source_word": "123", "engine_output": "satakaksikymmentäkolme"}]
    assert bwp.slowa_zastapione(pary_pl, wyliczone) == ("komputer",)
    assert bwp.slowa_zastapione(pary_pl, None) == ("123", "komputer")


@pytest.mark.parametrize(("iso", "oczekiwane"), [
    ("fi", "satakaksikymmentäkolme"), ("is", "eitt hundrað tuttugu og þrír")])
def test_przyklad_liczby_liczy_silnik(iso: str, oczekiwane: str) -> None:
    cfg = {"normalizuj_liczby": True, "iso": iso}
    assert bwp._wynik_przykladu("", "123", cfg, {}) == oczekiwane
    assert bwp.sprawdz_pare_przykladu("", "123", oczekiwane, cfg, {}) is None
    assert bwp.sprawdz_pare_przykladu("", "123", "yksi", cfg, {}) is not None


def test_bez_normalizacji_liczb_nie_ma_przykladu() -> None:
    assert bwp._wynik_przykladu("", "123", {"normalizuj_liczby": False}, {}) is None


def test_prompt_kaze_pominac_przyklad_bez_zamiennika() -> None:
    assert "DROP that example" in bwp._ZASADY_PRZYKLADOW
    assert "keep the pair exactly as it is in the source" not in bwp._ZASADY_PRZYKLADOW


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
