"""
test_detektor_pism.py - pismo jako fakt: detektor cyrylicy i segmenty pism
Naprawiacza Tagow (v19.17, decyzja maintainera 2026-11-09).

  * wspolny modul `detektor_pism` (blizniak bajt w bajt z ATA) - jego testy
    `detektor_pism_testy.py` sa tu uruchamiane bez zmian;
  * akapit pisany cyrylica dostaje jezyk z alfabetow paczek PRZED lingua
    i bez progu dlugosci (zmierzone: "My zhdyom vas." mialo 19 znakow,
    spadalo pod prog i dostawalo jezyk dokumentu);
  * Naprawiacz nie zmienia tresci, wiec greka (zawsze `el`) i cyrylica
    w akapicie innego pisma dostaja wlasny `lang`; lacinka w akapicie
    innego pisma zostaje pod kodem akapitu (nie da sie jej rozstrzygnac).

Uruchom:  .venv/Scripts/python -m pytest test_detektor_pism.py -q
"""

import ast
import sys
from pathlib import Path

import docx
from docx.oxml.ns import qn

sys.path.insert(0, str(Path(__file__).parent))

import core_poliglota as cp
from detektor_pism_testy import (TestJezykCyrylicy, TestOdcinki,  # noqa: F401
                                 TestPismo)


def c(*kody):
    return "".join(chr(k) for k in kody)


RU_KROTKI = c(0x041C, 0x044B, 0x20, 0x0436, 0x0434, 0x0451, 0x043C, 0x20,
              0x0432, 0x0430, 0x0441, 0x2E)                 # Мы ждём вас.
PRIWIET = c(0x043F, 0x0440, 0x0438, 0x0432, 0x0435, 0x0442)  # привет
LOGOS = c(0x03BB, 0x03CC, 0x03B3, 0x03BF, 0x03C2)            # λόγος
PI = chr(0x03C0)


def test_modul_wspolny_importuje_tylko_stdlib():
    for nazwa in ("detektor_pism.py", "detektor_pism_testy.py"):
        drzewo = ast.parse(Path(__file__).with_name(nazwa).read_text(encoding="utf-8"))
        moduly = set()
        for wezel in ast.walk(drzewo):
            if isinstance(wezel, ast.Import):
                moduly |= {a.name.split(".")[0] for a in wezel.names}
            elif isinstance(wezel, ast.ImportFrom) and wezel.module:
                moduly.add(wezel.module.split(".")[0])
        obce = moduly - set(sys.stdlib_module_names) - {"__future__", "detektor_pism"}
        assert not obce, f"{nazwa}: {obce}"


# ---------------------------------------------------------------------------
# Detekcja
# ---------------------------------------------------------------------------

def test_krotki_akapit_cyrylicki_to_ru():
    assert len(RU_KROTKI) < cp._MIN_TEKST_DLA_DETEKCJI
    assert cp._wykryj_jezyk_fragmentu(RU_KROTKI, "pl") == "ru"
    assert cp.wykryj_jezyk_zrodlowy(RU_KROTKI) == "ru"


def test_jezyk_zrodlowy_bez_ru_w_dostepnych_spada_na_fallback():
    assert cp.wykryj_jezyk_zrodlowy(RU_KROTKI, dostepne=["pl", "en"]) == "pl"


def test_lacinka_dalej_idzie_do_lingua():
    assert cp._wykryj_jezyk_fragmentu("Ala ma kota, a kot ma Alę, i tyle.", "en") == "pl"


def test_oczyszczenie_stempluje_krotki_akapit_ru():
    cfg = cp.wariant_po_id(cp.TRYB_REZYSER, "pl", "oczyszczenie")
    opcje = {}
    cp._przetworz_rezyser(f"Zdanie polskie na start tekstu.\n\n{RU_KROTKI}", "pl", cfg, opcje)
    kody = [s[0] for s in opcje["_segmenty_wynikowe"] if s[2]]
    assert kody == ["pl", "ru"], kody


# ---------------------------------------------------------------------------
# Naprawiacz Tagow
# ---------------------------------------------------------------------------

def _naprawiacz():
    cfg = cp.wariant_po_id(cp.TRYB_REZYSER, "pl", "naprawiacz_tagow")
    assert cfg and cfg.get("kategoria") == "naprawiacz"
    return cfg


def test_txt_obce_pisma_w_spanach(tmp_path):
    tekst = f"Napis {PRIWIET} i {LOGOS}, a obwod to 2{PI}r.\n\n{RU_KROTKI}"
    out = cp.zapisz_wynik(tekst, str(tmp_path), "t", ".txt", "pl", "Rezyser",
                          _naprawiacz(), tekst)
    html = Path(out).read_text(encoding="utf-8")
    assert f'<span lang="ru">{PRIWIET}</span>' in html
    assert f'<span lang="el">{LOGOS}</span>' in html
    assert f'2<span lang="el">{PI}</span>r' in html
    # Caly akapit cyrylicki pod kodem `pl` - jego tresc jest obcym pismem.
    assert f'<p lang="pl"><span lang="ru">{RU_KROTKI[:-1]}</span>.</p>' in html


def test_kody_per_jednostka_wyznaczaja_baze(tmp_path):
    """Akapit z kodem `ru`: cyrylica swoja, lacinka bez spana, greka `el`."""
    tekst = f"{PRIWIET} Moskva {LOGOS}"
    out = cp.zapisz_wynik(tekst, str(tmp_path), "t", ".txt", "pl", "Rezyser",
                          _naprawiacz(), tekst, kody_jednostek=["ru"])
    html = Path(out).read_text(encoding="utf-8")
    assert f'<p lang="ru">{PRIWIET} Moskva <span lang="el">{LOGOS}</span></p>' in html


def test_nieznany_kod_bierze_pismo_tresci(tmp_path):
    """Recznie `uk` (paczki brak): cyrylica jest swoja, zadnego spana."""
    out = cp.zapisz_wynik(PRIWIET, str(tmp_path), "t", ".txt", "pl", "Rezyser",
                          _naprawiacz(), PRIWIET, kody_jednostek=["uk"])
    assert f'<p lang="uk">{PRIWIET}</p>' in Path(out).read_text(encoding="utf-8")


def test_pelny_html_i_drugi_przebieg_nic_nie_dokłada(tmp_path):
    html = f"<html><body><p>Napis {PRIWIET} oraz <b>{LOGOS}</b> tu.</p></body></html>"
    out = cp.zapisz_wynik(html, str(tmp_path), "h", ".html", "pl", "Rezyser",
                          _naprawiacz(), html)
    wynik = Path(out).read_text(encoding="utf-8")
    assert f'<span lang="ru">{PRIWIET}</span>' in wynik
    assert f'<b><span lang="el">{LOGOS}</span></b>' in wynik
    out2 = cp.zapisz_wynik(wynik, str(tmp_path), "h2", ".html", "pl", "Rezyser",
                           _naprawiacz(), wynik)
    assert Path(out2).read_text(encoding="utf-8") == wynik


def test_fragment_html_drugi_przebieg_nic_nie_dokłada(tmp_path):
    tekst = f'Napis <span lang="ru">{PRIWIET}</span> tu.'
    out = cp.zapisz_wynik(tekst, str(tmp_path), "f", ".txt", "pl", "Rezyser",
                          _naprawiacz(), tekst)
    body = Path(out).read_text(encoding="utf-8").split("<body>", 1)[1]
    assert body.count("<span") == 1, body


def _biegi(sciezka):
    akapit = docx.Document(sciezka).paragraphs[0]
    wynik = []
    for r in akapit._p.iter(qn("w:r")):
        lang = r.find(qn("w:rPr")).find(qn("w:lang")).get(qn("w:val"))
        wynik.append(("".join(t.text for t in r.iter(qn("w:t"))), lang))
    return wynik


def test_docx_bieg_rozciety_po_pismach(tmp_path):
    src = tmp_path / "src.docx"
    doc = docx.Document()
    p = doc.add_paragraph(f"Napis {PRIWIET} i {LOGOS} koniec.")
    p.add_run(" pogrubione").bold = True
    doc.save(src)
    out = cp.zapisz_wynik("", str(tmp_path), "w", ".docx", "pl", "Rezyser",
                          _naprawiacz(), "", str(src))
    assert _biegi(out) == [("Napis ", "pl"), (PRIWIET, "ru"), (" i ", "pl"),
                           (LOGOS, "el"), (" koniec.", "pl"), (" pogrubione", "pl")]
    biegi = list(docx.Document(out).paragraphs[0]._p.iter(qn("w:r")))
    assert biegi[-1].find(qn("w:rPr")).find(qn("w:b")) is not None


def test_docx_bieg_z_tabulatorem_zostaje_caly(tmp_path):
    src = tmp_path / "src.docx"
    doc = docx.Document()
    r = doc.add_paragraph().add_run(f"Napis {PRIWIET}")
    r.add_tab()
    doc.save(src)
    out = cp.zapisz_wynik("", str(tmp_path), "w", ".docx", "pl", "Rezyser",
                          _naprawiacz(), "", str(src))
    assert _biegi(out) == [(f"Napis {PRIWIET}", "pl")]


def test_docx_bez_oryginalu(tmp_path):
    tekst = f"Napis {LOGOS} tu."
    out = cp.zapisz_wynik(tekst, str(tmp_path), "w", ".docx", "pl", "Rezyser",
                          _naprawiacz(), tekst)
    assert _biegi(out) == [("Napis ", "pl"), (LOGOS, "el"), (" tu.", "pl")]


def test_krotki_akapit_ru_nie_przestawia_jezyka_lepkiego():
    """Audyt W1: krotkie polskie akapity po cytacie rosyjskim zostaja `pl`."""
    seg = cp._segmentuj_z_ochrona_tagow(
        f"Zdanie polskie na start tekstu, dosc dlugie.\n\n{RU_KROTKI}\n\nTak.\n\nNie.",
        fallback_jezyk="pl")
    kody = [s[0] for s in seg if s[2]]
    assert kody == ["pl", "ru", "pl", "pl"], kody


def test_fragment_html_script_data_lang_i_zagniezdzenie(tmp_path):
    """Audyt N2: tresc <script> nietknieta, `data-lang` to nie `lang`,
    tekst w tagu wewnatrz <span lang> nie dostaje drugiego spana."""
    tekst = (f'A <script>var s="{LOGOS}";</script> '
             f'<span data-lang="x">{LOGOS}</span> '
             f'<span lang="el">{LOGOS}<b>{LOGOS}</b></span> b')
    wynik = cp._owin_obce_pisma_w_akapicie(tekst, "pl")
    assert f'<script>var s="{LOGOS}";</script>' in wynik
    assert f'<span data-lang="x"><span lang="el">{LOGOS}</span></span>' in wynik
    assert f'<span lang="el">{LOGOS}<b>{LOGOS}</b></span>' in wynik


def test_pelny_html_textarea_nietknieta(tmp_path):
    """Audyt N3: span w <textarea> bylby widocznym tekstem."""
    html = f"<html><body><p>x <textarea>{LOGOS}</textarea></p></body></html>"
    out = cp.zapisz_wynik(html, str(tmp_path), "h", ".html", "pl", "Rezyser",
                          _naprawiacz(), html)
    assert f"<textarea>{LOGOS}</textarea>" in Path(out).read_text(encoding="utf-8")


def test_docx_bieg_ze_znacznikiem_strony_rozciety(tmp_path):
    """Audyt N4: `w:lastRenderedPageBreak` (pierwszy bieg strony) nie blokuje
    rozciecia i zostaje tylko w pierwszej kopii."""
    from docx.oxml import OxmlElement
    src = tmp_path / "src.docx"
    doc = docx.Document()
    r = doc.add_paragraph().add_run(f"Napis {LOGOS}")
    r._r.insert(0, OxmlElement("w:lastRenderedPageBreak"))
    doc.save(src)
    out = cp.zapisz_wynik("", str(tmp_path), "w", ".docx", "pl", "Rezyser",
                          _naprawiacz(), "", str(src))
    assert _biegi(out) == [("Napis ", "pl"), (LOGOS, "el")]
    akapit = docx.Document(out).paragraphs[0]._p
    assert len(list(akapit.iter(qn("w:lastRenderedPageBreak")))) == 1


def test_inne_tryby_nie_dostaja_spanow(tmp_path):
    cfg = cp.wariant_po_id(cp.TRYB_REZYSER, "pl", "oczyszczenie")
    tekst = f"Napis {PRIWIET} tu."
    out = cp.zapisz_wynik(tekst, str(tmp_path), "o", ".txt", "pl", "Rezyser", cfg, tekst)
    assert "<span" not in Path(out).read_text(encoding="utf-8")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
