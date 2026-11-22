"""
test_jezyki_w_akapicie.py - kilka jezykow WEWNATRZ akapitu (v19.21).

Wycinki slajdow z prezentacji prawniczej ("organy pojednawcze -
примирительного характера; mediacja") dawaly caly akapit pod jednym
jezykiem, wiec polowa tekstu szla regulami drugiego jezyka. Od 19.21
granica PISMA dzieli akapit zawsze, a w obrebie jednego pisma lingua
przelacza jezyk dopiero od PROG_SLOW_ZMIANY_JEZYKA slow (wzor: dodatek NVDA
Enhanced Language Detection). Testy mierza:
  * PODZIAL - granice pism, prog slow, neutralnosc lacinkowego szumu,
  * SKUTEK - oczyszczenie zachowuje spacje na granicach i daje <span lang>,
    akcent ma jeden jezyk glosu, zapis .docx robi z wtretu bieg z w:lang,
  * KONTRAKT - "wymus jezyk" niczego nie dzieli (odwracalny szyfr).

Uruchom:  .venv/Scripts/python -m pytest test_jezyki_w_akapicie.py -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_poliglota as cp

pytestmark = pytest.mark.skipif(cp._zbuduj_detektor_lingua() is None,
                                reason="lingua niedostepna")


def _kody(akapit, lacinka="pl"):
    stan = {"lacinka": lacinka}
    kawalki = cp._kawalki_jezykow(akapit, stan)
    assert "".join(t for _, t in kawalki) == akapit      # pokrycie bez reszty
    return [k for k, _ in kawalki], kawalki


def test_granica_pisma_dzieli_zawsze():
    kody, kawalki = _kody("2. organy pojednawcze — примирительного характера; mediacja")
    assert kody == ["pl", "ru", "pl"]
    assert kawalki[2][1].strip() == "mediacja"


def test_krotka_lacinka_wsrod_cyrylicy_dostaje_jezyk_dokumentu():
    assert _kody("Оправданный - uniewinniony")[0] == ["ru", "pl"]
    assert _kody("Оправданный - uniewinniony", lacinka="fi")[0] == ["ru", "fi"]


def test_lacinkowy_szum_jest_neutralny():
    for akapit in ("Закон РФ от 26.06.1992 N 3132-1 о статусе судей",
                   "ГЛАВА III. ОБЩИЕ ПОЛОЖЕНИЯ",
                   "КОМИССИЯ (ICC RUSSIA) http://www.iccwbo.ru"):
        assert _kody(akapit)[0] == ["ru"], akapit


def test_odcinek_ponizej_progu_nie_przelacza():
    tekst = ("Międzynarodowa Izba Handlowa (International Chamber of Commerce - ICC) "
             "jest organizacją reprezentującą interesy światowego biznesu")
    assert _kody(tekst)[0] == ["pl"]
    assert _kody("opuść (alt+q) przycisk")[0] == ["pl"]


def test_zdanie_innego_jezyka_tego_samego_pisma_przelacza():
    tekst = ("Ala ma kota, a kot ma Alę i razem wychodzą. "
             "The quick brown fox jumps over the lazy dog. "
             "A potem znowu wracamy do polskiego tekstu.")
    kody, kawalki = _kody(tekst)
    assert kody == ["pl", "en", "pl"]
    assert "quick brown fox" in kawalki[1][1]


def test_lacinka_dokumentu_aktualizuje_sie_na_pewnym_odcinku():
    stan = {"lacinka": "pl"}
    cp._kawalki_jezykow("Hyvää huomenta kaikille, tänään puhumme laista.", stan)
    assert stan["lacinka"] == "fi"


def test_oczyszczenie_zachowuje_spacje_i_daje_span():
    opcje = {}
    wynik = cp.przetworz("определение ochrona prawna существенно шире российского понимания",
                         "Rezyser", "pl", "oczyszczenie", opcje)
    assert 'определение <span lang="pl">ochrona prawna</span> существенно' in wynik
    tekstowe = [s for s in opcje["_segmenty_wynikowe"] if s[2]]
    assert [s[0] for s in tekstowe] == ["ru"]            # jeden akapit, glos glowny


def test_akcent_ma_jeden_jezyk_glosu():
    opcje = {}
    wynik = cp.przetworz("organy pojednawcze — примирительного характера; mediacja",
                         "Rezyser", "pl", "angielski", opcje)
    assert "<span" not in wynik
    assert {s[0] for s in opcje["_segmenty_wynikowe"] if s[2]} == {"en"}
    assert not any(0x400 <= ord(z) <= 0x4FF for z in wynik)     # zero cyrylicy


def test_wymus_jezyk_nie_dzieli():
    opcje = {"wymus_jezyk": "pl"}
    cp.przetworz("organy pojednawcze — примирительного характера; mediacja",
                 "Rezyser", "pl", "oczyszczenie", opcje)
    tekstowe = [s for s in opcje["_segmenty_wynikowe"] if s[2]]
    assert len(tekstowe) == 1 and tekstowe[0][0] == "pl"
    assert "<span" not in tekstowe[0][1]


def test_zapis_docx_robi_z_wtretu_bieg(tmp_path):
    import docx
    from docx.oxml.ns import qn
    zrodlo = "определение ochrona prawna существенно шире российского понимания"
    opcje = {}
    wynik = cp.przetworz(zrodlo, "Rezyser", "pl", "oczyszczenie", opcje)
    sciezka = cp.zapisz_wynik(wynik, str(tmp_path), "w", ".docx", "pl", "Rezyser",
                              cp.wariant_po_id("Rezyser", "pl", "oczyszczenie"), zrodlo,
                              segmenty_wynikowe=opcje["_segmenty_wynikowe"])
    akapit = docx.Document(sciezka).paragraphs[0]
    assert "<span" not in akapit.text
    biegi = [(r.text, r._r.find(qn("w:rPr") + "/" + qn("w:lang")).get(qn("w:val")))
             for r in akapit.runs]
    assert ("ochrona prawna", "pl") in biegi
    assert {kod for _, kod in biegi} == {"ru", "pl"}


def test_kawalki_spanow_linia_w_calosci_w_spanie():
    assert cp._kawalki_spanow('  <span lang="pl">sąd</span> ') == [("pl", "  sąd ")]
    assert cp._kawalki_spanow("bez znacznikow") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
