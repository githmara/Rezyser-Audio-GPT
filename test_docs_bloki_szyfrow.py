#!/usr/bin/env python
"""
test_docs_bloki_szyfrow.py — bloki CEZAR i SAMOGŁOSKOWIEC brata od docsów (19.18).

Pomiar myślenia 2026-11-12: bez tych bloków model zostawiał w paczkach fi/is
polski alfabet Cezara (35 liter, -34…34) i polską parę Samogłoskowca, więc
rerun brata cofał ręcznie poprawione sekcje. Wartości bloków liczymy z paczki
DOCELOWEJ (silnik + `ui.yaml`), a te testy pilnują, że są jej, a nie polskie.

Bez API: budują sam prompt z prawdziwych szablonów i paczek.

Uruchom:  .venv/Scripts/python -m pytest test_docs_bloki_szyfrow.py -q
"""
from __future__ import annotations

import pytest

import buduj_wielojezyczne_docs as d

SEKCJE = (("manual.yaml", "krok_5_tryb_szyfrant"),
          ("dictionaries.yaml", "co_to_szyfr"))


def _prompt(kod: str, plik: str, klucz: str) -> str:
    szablony = {n: sek for n, _i, sek in d.wczytaj_szablony_pl()}
    return d._zbuduj_prompt_dodatkowy(
        kod, kod.upper(), szablony[plik][klucz],
        nazwa_pliku=plik, klucz_sekcji=klucz)


@pytest.mark.parametrize(("plik", "klucz"), SEKCJE)
def test_cezar_dostaje_alfabet_paczki_docelowej(plik: str, klucz: str) -> None:
    blok = _prompt("fi", plik, klucz).split("### Cipher: Caesar", 1)[1]
    blok = blok.split("\n\n", 1)[0]
    assert "(29 letters)" in blok and "-28…28" in blok and "1-28" in blok
    assert "Caesarin salauksen siirto (0 = satunnainen, alue -28…28)" in blok


@pytest.mark.parametrize(("plik", "klucz"), SEKCJE)
def test_samogloskowiec_dostaje_pare_policzona_silnikiem(plik: str, klucz: str) -> None:
    blok = _prompt("is", plik, klucz).split("### Cipher: Vowelizer", 1)[1]
    assert '"Góðan daginn' in blok and "→ \"Goðon dogonn" in blok
    assert "NO softening rules" in blok


def test_sekcja_bez_szyfrow_nie_dostaje_blokow() -> None:
    szablony = {n: sek for n, _i, sek in d.wczytaj_szablony_pl()}
    prompt = d._zbuduj_prompt_dodatkowy(
        "fi", "Suomi", szablony["manual.yaml"]["krok_2_klucz_api"],
        nazwa_pliku="manual.yaml", klucz_sekcji="krok_2_klucz_api")
    assert "### Cipher: Caesar" not in prompt
    assert "### Cipher: Vowelizer" not in prompt


def test_prog_typoglikemii_w_zrodle_zgadza_sie_z_silnikiem() -> None:
    """Silnik miesza słowa OD `min_dlugosc_slowa` liter; źródło PL tak to mówi."""
    import yaml
    from pathlib import Path
    cfg = yaml.safe_load(
        (Path(d.DICT_DIR) / "pl" / "szyfry" / "typoglikemia.yaml").read_text(encoding="utf-8"))
    prog = int(cfg["min_dlugosc_slowa"])
    szablony = {n: sek for n, _i, sek in d.wczytaj_szablony_pl()}
    for plik, klucz in SEKCJE:
        tekst = " ".join(szablony[plik][klucz].split())
        assert f"co najmniej {prog} znaków" in tekst, (plik, klucz)
        assert f"dłuższego niż {prog} znaki" not in tekst


def test_jakanie_dostaje_slowa_z_reguly_paczki() -> None:
    blok = _prompt("fi", "manual.yaml", "krok_5_tryb_szyfrant").split(
        "### Cipher: Stutter", 1)[1].split("\n\n", 1)[0]
    assert '"tietokone" → "t-t-t-tietokone"' in blok


def test_d3_lapie_polski_cytat_ktory_przezyl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Polskie „k-k-k-komputer" w punkcie jąkania paczki fi = D3; „ssssss" i
    cytat obecny we wszystkich paczkach (tytuł) — nie."""
    szablony = {n: sek for n, _i, sek in d.wczytaj_szablony_pl()}
    tekst_pl = szablony["manual.yaml"]["krok_5_tryb_szyfrant"]
    bwa, _bwp = d._rodzenstwo_audytu()
    operacje = d._operacje_punktow_pl(tekst_pl, d.nazwy_operacji_pl(bwa))
    oryginal = d.wczytaj_istniejacy_docelowy

    def podmieniony(cel):
        sekcje = dict(oryginal(cel) or {})
        if cel.parts[-4] == "fi":
            sekcje["krok_5_tryb_szyfrant"] = tekst_pl   # cała sekcja po polsku
        return sekcje

    monkeypatch.setattr(d, "wczytaj_istniejacy_docelowy", podmieniony)
    wynik = d._cytaty_pl_w_obcych("manual.yaml", "krok_5_tryb_szyfrant",
                                  tekst_pl, operacje)
    cytaty = {c for _r, c in wynik.get("fi", [])}
    assert "k-k-k-komputer" in cytaty
    assert not any(set(c) <= {"s", "z", " ", "-"} for c in cytaty)
    assert [k for k in wynik if wynik[k]] == ["fi"]


def test_repo_bez_bledow_d3() -> None:
    znaleziska, _staty = d.audytuj_przyklady(None, ["manual.yaml", "dictionaries.yaml"])
    assert not [z for z in znaleziska if z.blad and "D3" in str(z)]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
