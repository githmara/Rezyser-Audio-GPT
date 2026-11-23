"""
test_obrazy_docx.py - obrazy wstawione w .docx czytane modelem AI (v19.21).

Do 19.20 Poliglota znala tylko tekst .docx: prezentacja z 46 slajdami
wklejonymi jako obrazy wczytywala sie jako jedno zdanie, z komunikatem
o sukcesie. Testy mierza:
  * EKSTRAKCJE - `core_poliglota.elementy_docx`: kolejnosc dokumentu
    (tekst, obraz, tekst), tekst alternatywny z `wp:docPr`, numeracja;
  * ODCZYT - `core_skany.odczytaj_obrazy`: prompt z typu obrazu (JPEG =
    skan, PNG = obraz cyfrowy), kontekst z tekstu przed obrazem, powod BEZ
    wywolania dla formatu spoza listy i obrazu bez danych, blad krytyczny
    = reszta obrazow z powodem (zero ciszy);
  * SKLEJENIE - `core_skany.scal_docx`: akapit pochodzenia przed odczytem,
    tekst alternatywny albo powod w miejscu obrazu nieodczytanego.

Atrapa `wywolaj_llm_z_obrazem`, zero wywolan API.

Uruchom:  .venv/Scripts/python -m pytest test_obrazy_docx.py -q
"""

import io
import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_llm as cl
import core_poliglota as cp
import core_skany as cs


def _png(szer=4, wys=3):
    def blok(typ, dane):
        return (struct.pack(">I", len(dane)) + typ + dane
                + struct.pack(">I", zlib.crc32(typ + dane) & 0xFFFFFFFF))
    surowe = b"".join(b"\x00" + b"\xff\xff\xff" * szer for _ in range(wys))
    return (bytes([137, 80, 78, 71, 13, 10, 26, 10])
            + blok(b"IHDR", struct.pack(">IIBBBBB", szer, wys, 8, 2, 0, 0, 0))
            + blok(b"IDAT", zlib.compress(surowe)) + blok(b"IEND", b""))


@pytest.fixture
def dokument(tmp_path):
    import docx
    from docx.oxml.ns import qn
    d = docx.Document()
    d.add_paragraph("Wstęp przed slajdem.")
    d.add_paragraph().add_run().add_picture(io.BytesIO(_png()))
    d.add_paragraph().add_run().add_picture(io.BytesIO(_png()))
    docpr = list(d.element.body.iter(qn("wp:docPr")))[1]
    docpr.set("descr", "Schemat sądów")
    d.add_paragraph("Zakończenie.")
    sciezka = tmp_path / "slajdy.docx"
    d.save(sciezka)
    return str(sciezka)


def test_elementy_w_kolejnosci_dokumentu(dokument):
    el = cp.elementy_docx(dokument)
    tresciwe = [e if isinstance(e, str) else ("obraz", e.numer, e.opis)
                for e in el if not isinstance(e, str) or e.strip()]
    assert tresciwe == ["Wstęp przed slajdem.", ("obraz", 1, ""),
                        ("obraz", 2, "Schemat sądów"), "Zakończenie."]
    assert cl.typ_obrazu(next(e for e in el if not isinstance(e, str)).dane) == "image/png"


def _atrapa(monkeypatch, odpowiedzi):
    wyslane = []

    def wywolaj(klient, **kw):
        wyslane.append(kw)
        odp = odpowiedzi.pop(0)
        if isinstance(odp, Exception):
            raise odp
        return odp
    monkeypatch.setattr(cl, "wywolaj_llm_z_obrazem", wywolaj)
    return wyslane


def test_odczyt_prompt_z_typu_i_kontekst(monkeypatch, dokument):
    wyslane = _atrapa(monkeypatch, [("# Slajd 1", "end_turn"), ("Slajd 2", "end_turn")])
    el = cp.elementy_docx(dokument)
    wyniki, blad = cs.odczytaj_obrazy(object(), el)
    assert blad is None and [w.status for w in wyniki] == [cs.STATUS_OK, cs.STATUS_OK]
    assert wyslane[0]["system"] == cs.SYSTEM_CYFROWA          # PNG = obraz cyfrowy
    assert "Wstęp przed slajdem." in wyslane[0]["tekst_przed"]
    assert "# Slajd 1" in wyslane[1]["tekst_przed"]            # poprzedni odczyt
    assert cs.system_obrazu(bytes([255, 216, 255, 224])) == cs.SYSTEM_SKANY


def test_format_spoza_listy_i_brak_danych_bez_wywolania(monkeypatch):
    wyslane = _atrapa(monkeypatch, [])
    el = [cp.ObrazDocx(1, b"BM" + bytes(30)), cp.ObrazDocx(2, b"")]
    wyniki, blad = cs.odczytaj_obrazy(object(), el)
    assert wyslane == [] and blad is None
    assert all(w.status == cs.STATUS_BLAD and w.powod for w in wyniki)


def test_blad_krytyczny_reszta_obrazow_z_powodem(monkeypatch, dokument):
    _atrapa(monkeypatch, [cl.BladFunkcjiNiedostepnej("image", "x")])
    wyniki, blad = cs.odczytaj_obrazy(object(), cp.elementy_docx(dokument))
    assert isinstance(blad, cl.BladFunkcjiNiedostepnej)
    assert [w.numer for w in wyniki] == [1, 2]
    assert all(w.status == cs.STATUS_BLAD for w in wyniki)


def test_scal_pochodzenie_opis_i_powod(monkeypatch, dokument):
    el = cp.elementy_docx(dokument)
    wyniki = [cs.WynikStrony(1, cs.STATUS_OK, "Treść slajdu"),
              cs.WynikStrony(2, cs.STATUS_BLAD, powod="awaria")]
    html = cs.scal_docx(el, wyniki, "pl", "slajdy")
    assert "Treść slajdu" in html and "Wstęp przed slajdem." in html
    assert html.index("Wstęp") < html.index("Treść slajdu") < html.index("Zakończenie")
    assert cs.t("poliglota.obraz_pochodzenie", numer_obrazu=1) in html
    assert "Schemat sądów" in html                     # tekst alternatywny obrazu 2
    bez_opisu = [e for e in el if isinstance(e, str)] + [cp.ObrazDocx(9, b"x")]
    html = cs.scal_docx(bez_opisu, [cs.WynikStrony(9, cs.STATUS_BLAD, powod="awaria")],
                        "pl", "t")
    assert cs.t("poliglota.obraz_nieodczytany", numer_obrazu=9, powod="awaria") in html


def test_tekst_tresci_bez_akapitow_pochodzenia(dokument):
    el = cp.elementy_docx(dokument)
    tekst = cs.tekst_tresci_docx(el, [cs.WynikStrony(1, cs.STATUS_OK, "Odczyt [[ILLEGIBLE]]")])
    assert "Odczyt" in tekst and "ILLEGIBLE" not in tekst
    assert cs.t("poliglota.obraz_pochodzenie", numer_obrazu=1) not in tekst


def _jpeg(szer, wys):
    """Minimalny nagłówek JPEG: SOI, APP0 i SOF0 z wymiarami (reszta zbędna)."""
    app0 = bytes([255, 224]) + (16).to_bytes(2, "big") + b"JFIF" + bytes(10)
    sof0 = (bytes([255, 192]) + (17).to_bytes(2, "big") + bytes([8])
            + wys.to_bytes(2, "big") + szer.to_bytes(2, "big") + bytes(10))
    return bytes([255, 216]) + app0 + sof0


class _Klient:
    def __init__(self, provider):
        self.provider = provider


def test_wymiary_z_naglowka_bez_pillow():
    assert cl.wymiary_obrazu(_png(4, 3)) == (4, 3)
    assert cl.wymiary_obrazu(_jpeg(9000, 120)) == (9000, 120)
    assert cl.wymiary_obrazu(b"GIF89a" + (5).to_bytes(2, "little")
                             + (7).to_bytes(2, "little") + bytes(10)) == (5, 7)
    assert cl.wymiary_obrazu(b"BM" + bytes(30)) is None


def test_limity_api_przed_wywolaniem(monkeypatch):
    """Obraz ponad limit dostaje powód z wartościami — bez wywołania API."""
    wyslane = _atrapa(monkeypatch, [])
    za_szeroki = cp.ObrazDocx(1, _jpeg(9000, 120))
    wyniki, blad = cs.odczytaj_obrazy(_Klient(cl.PROVIDER_ANTHROPIC), [za_szeroki])
    assert wyslane == [] and blad is None
    assert wyniki[0].status == cs.STATUS_BLAD
    assert wyniki[0].powod == cs.t("poliglota.obraz_powod_wymiary",
                                   szerokosc=9000, wysokosc=120, limit_px=8000)
    # 4 MB surowych = ~5,3 MB w base64: Anthropic (10 MB) przyjmuje,
    # OpenRouter (próg Bedrocka, 5 MB) już nie.
    duzy = _jpeg(100, 100) + bytes(4 * 1000 * 1000)
    assert cl.limit_obrazu(_Klient(cl.PROVIDER_ANTHROPIC), duzy) is None
    rodzaj, wartosci = cl.limit_obrazu(_Klient(cl.PROVIDER_OPENROUTER), duzy)
    assert rodzaj == "rozmiar" and wartosci["limit_mb"] == "5"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
