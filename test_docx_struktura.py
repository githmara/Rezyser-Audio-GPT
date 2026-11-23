"""
test_docx_struktura.py - struktura .docx i poprawki audytu 19.21 (Reżyser + wspólna
polityka bliźniaków z ATA).

Audyty subagentowe obu bliźniaków (2026-11-23) udowodniły wykonaniem klasy, których
dotąd nic nie mierzyło. Wspólna polityka, którą ATA realizuje u siebie tak samo:
  * pole tekstowe czytane W MIEJSCU, po akapicie, w którym stoi (raz, bez
    `mc:Fallback`);
  * nagłówki i stopki nie wchodzą do treści, ale są liczone do komunikatu;
  * wykres i SmartArt = element nieodczytany (tekst alternatywny albo powód),
    bez płatnego wywołania;
  * kontrolki zawartości i `w:customXml` na każdym poziomie, także wiersza;
  * śledzenie zmian: treść usunięta pomijana (z obrazami), wstawiona czytana;
  * ta sama część pakietu wstawiona kilka razy = jeden odczyt;
  * grupa obrazów: każdy osobno, własny tekst alternatywny przed tekstem grupy.
Do tego znaleziska samego Reżysera: obraz liczony podwójnie przez `mc:Fallback`
(F1), grupa ucięta do pierwszego obrazu (F2), `<span lang>` w zapisie surowym (F3),
szyfrant dzielący akapit na kawałki (F4), wersaliki zawsze neutralne (F8),
drugi przebieg gubiący spacje i zagnieżdżający wstawki (F9).

Atrapa `wywolaj_llm_z_obrazem`, zero wywołań API.

Uruchom:  .venv/Scripts/python -m pytest test_docx_struktura.py -q
"""

import copy
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

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
NS = (f'xmlns:w="{W}" xmlns:a="{A}" xmlns:r="{R}" xmlns:wp="{WP}" xmlns:pic="{PIC}" '
      'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" '
      'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
      'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
      'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
      'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"')


def _png(szer=4, wys=3):
    def blok(typ, dane):
        return (struct.pack(">I", len(dane)) + typ + dane
                + struct.pack(">I", zlib.crc32(typ + dane) & 0xFFFFFFFF))
    surowe = b"".join(bytes([0]) + bytes([255, 255, 255]) * szer for _ in range(wys))
    return (bytes([137, 80, 78, 71, 13, 10, 26, 10])
            + blok(b"IHDR", struct.pack(">IIBBBBB", szer, wys, 8, 2, 0, 0, 0))
            + blok(b"IDAT", zlib.compress(surowe)) + blok(b"IEND", b""))


def _dokument():
    import docx
    return docx.Document()


def _obrazek(d, szer=4, opis=None):
    p = d.add_paragraph()
    p.add_run().add_picture(io.BytesIO(_png(szer)))
    if opis is not None:
        p._p.find(f".//{{{WP}}}docPr").set("descr", opis)
    return p


def _xml(d, xml):
    from docx.oxml import parse_xml
    el = parse_xml(xml)
    cialo = d.element.body
    cialo.insert(len(cialo) - 1, el)
    return el


def _zapisz(d, tmp_path, nazwa):
    sciezka = tmp_path / nazwa
    d.save(sciezka)
    return str(sciezka)


def _obrazy(el):
    return [e for e in el if not isinstance(e, str)]


def _teksty(el):
    return [e for e in el if isinstance(e, str) and e.strip()]


# --- obrazy ----------------------------------------------------------------

def test_obraz_z_wariantem_vml_liczony_raz(tmp_path):
    """F1: `mc:Choice` (DrawingML) i `mc:Fallback` (VML) to ten sam obraz."""
    from docx.oxml import parse_xml
    d = _dokument()
    p = _obrazek(d)
    rysunek = p._p.find(f".//{{{W}}}drawing")
    rid = rysunek.find(f".//{{{A}}}blip").get(f"{{{R}}}embed")
    bieg = rysunek.getparent()
    alt = parse_xml(f'<mc:AlternateContent {NS}><mc:Choice Requires="wps"/><mc:Fallback>'
                    f'<w:pict><v:shape><v:imagedata r:id="{rid}"/></v:shape></w:pict>'
                    '</mc:Fallback></mc:AlternateContent>')
    alt[0].append(copy.deepcopy(rysunek))
    bieg.remove(rysunek)
    bieg.append(alt)
    assert len(_obrazy(cp.elementy_docx(_zapisz(d, tmp_path, "alt.docx")))) == 1


def test_grupa_kazdy_obraz_z_wlasnym_opisem(tmp_path):
    """F2 + polityka: wszystkie obrazy grupy; własny opis przed opisem grupy."""
    from docx.oxml import parse_xml
    d = _dokument()
    p1, p2 = _obrazek(d, 5), _obrazek(d, 6)
    pic2 = copy.deepcopy(p2._p.find(f".//{{{PIC}}}pic"))
    pic2.find(f".//{{{PIC}}}cNvPr").set("descr", "Drugi obraz.")
    d.element.body.remove(p2._p)
    gd = p1._p.find(f".//{{{A}}}graphicData")
    pic1 = gd.find(f"{{{PIC}}}pic")
    gd.remove(pic1)
    grupa = parse_xml(f'<wpg:wgp {NS}/>')
    grupa.append(pic1)
    grupa.append(pic2)
    gd.append(grupa)
    p1._p.find(f".//{{{WP}}}docPr").set("descr", "Schemat grupy.")
    obrazy = _obrazy(cp.elementy_docx(_zapisz(d, tmp_path, "grupa.docx")))
    assert [o.opis for o in obrazy] == ["Schemat grupy.", "Drugi obraz."]
    assert all(o.dane for o in obrazy)


def test_vml_z_o_relid_jest_czytany(tmp_path):
    d = _dokument()
    rid, _ = d.part.get_or_add_image(io.BytesIO(_png(7)))
    _xml(d, f'<w:p {NS}><w:r><w:pict><v:shape><v:imagedata o:relid="{rid}"/>'
            '</v:shape></w:pict></w:r></w:p>')
    obrazy = _obrazy(cp.elementy_docx(_zapisz(d, tmp_path, "orelid.docx")))
    assert len(obrazy) == 1 and obrazy[0].dane


def test_ten_sam_obraz_piec_razy_to_jeden_odczyt(tmp_path, monkeypatch):
    d = _dokument()
    for i in range(5):
        d.add_paragraph(f"Slajd {i}.")
        _obrazek(d, 8)
    el = cp.elementy_docx(_zapisz(d, tmp_path, "logo.docx"))
    wywolania = []
    monkeypatch.setattr(cl, "wywolaj_llm_z_obrazem",
                        lambda klient, **kw: (wywolania.append(1), ("Logo", "end_turn"))[1])
    assert cs.liczba_odczytow(el) == 1
    wyniki, blad = cs.odczytaj_obrazy(object(), el)
    assert blad is None and len(wywolania) == 1
    assert [w.numer for w in wyniki] == [1, 2, 3, 4, 5]
    assert all(w.status == cs.STATUS_OK for w in wyniki)


def test_wykres_bez_wywolania_z_opisem_w_wyniku(tmp_path, monkeypatch):
    d = _dokument()
    _xml(d, f'<w:p {NS}><w:r><w:drawing><wp:inline><wp:docPr id="11" name="W" '
            'descr="ALT WYKRESU"/><a:graphic><a:graphicData '
            'uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
            '<c:chart r:id="rId900"/></a:graphicData></a:graphic></wp:inline>'
            '</w:drawing></w:r></w:p>')
    el = cp.elementy_docx(_zapisz(d, tmp_path, "wykres.docx"))
    monkeypatch.setattr(cl, "wywolaj_llm_z_obrazem",
                        lambda *a, **k: pytest.fail("wykres nie idzie do modelu"))
    assert [o.rodzaj for o in _obrazy(el)] == ["wykres"] and cs.liczba_odczytow(el) == 0
    wyniki, _ = cs.odczytaj_obrazy(object(), el)
    assert wyniki[0].powod == cs.t("poliglota.obraz_powod_wykres")
    assert "ALT WYKRESU" in cs.scal_docx(el, wyniki, "pl", "t")


# --- tekst i struktura -------------------------------------------------------

def test_pole_tekstowe_po_akapicie_kotwicy(tmp_path):
    d = _dokument()
    d.add_paragraph("Akapit zwykly.")
    _xml(d, f'<w:p {NS}><w:r><w:t>Kotwica.</w:t></w:r><w:r><w:drawing><wp:anchor>'
            '<wp:docPr id="9" name="Pole"/><a:graphic><a:graphicData '
            'uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
            '<wps:wsp><wps:txbx><w:txbxContent><w:p><w:r><w:t>TEKST POLA</w:t></w:r></w:p>'
            '</w:txbxContent></wps:txbx></wps:wsp></a:graphicData></a:graphic></wp:anchor>'
            '</w:drawing></w:r></w:p>')
    sciezka = _zapisz(d, tmp_path, "pole.docx")
    assert _teksty(cp.elementy_docx(sciezka)) == ["Akapit zwykly.", "Kotwica.", "TEKST POLA"]
    assert "TEKST POLA" in cp.tekst_docx(sciezka)


def test_wiersz_w_kontrolce_i_customxml(tmp_path):
    from docx.oxml import parse_xml
    d = _dokument()
    t = d.add_table(rows=2, cols=1)
    t.cell(0, 0).text = "Wiersz zwykly."
    t.cell(1, 0).text = "WIERSZ W KONTROLCE"
    tr = t._tbl.findall(f"{{{W}}}tr")[1]
    sdt = parse_xml(f'<w:sdt {NS}><w:sdtPr/><w:sdtContent/></w:sdt>')
    t._tbl.replace(tr, sdt)
    sdt[1].append(tr)
    _xml(d, f'<w:customXml {NS} w:element="s"><w:p><w:r><w:t>W CUSTOMXML</w:t></w:r>'
            '</w:p></w:customXml>')
    teksty = _teksty(cp.elementy_docx(_zapisz(d, tmp_path, "sdt.docx")))
    assert teksty == ["Wiersz zwykly.", "WIERSZ W KONTROLCE", "W CUSTOMXML"]


def test_sledzenie_zmian(tmp_path):
    from docx.oxml import parse_xml
    d = _dokument()
    p = _obrazek(d, 9)
    bieg = p._p.find(f"{{{W}}}r")
    usuniety = parse_xml(f'<w:del {NS} w:id="1" w:author="x" w:date="2026-01-01T00:00:00Z"/>')
    p._p.replace(bieg, usuniety)
    usuniety.append(bieg)
    _xml(d, f'<w:p {NS}><w:r><w:t xml:space="preserve">Stary </w:t></w:r>'
            '<w:del w:id="3" w:author="x" w:date="2026-01-01T00:00:00Z"><w:r>'
            '<w:delText>USUNIETY</w:delText></w:r></w:del>'
            '<w:ins w:id="2" w:author="x" w:date="2026-01-01T00:00:00Z"><w:r>'
            '<w:t>WSTAWIONY</w:t></w:r></w:ins>'
            '<w:fldSimple w:instr="AUTHOR"><w:r><w:t> POLE</w:t></w:r></w:fldSimple></w:p>')
    el = cp.elementy_docx(_zapisz(d, tmp_path, "zmiany.docx"))
    assert _obrazy(el) == [], "obraz usunięty przy śledzeniu zmian nie jest czytany"
    assert _teksty(el) == ["Stary WSTAWIONY POLE"]


def test_naglowki_i_stopki_liczone_nie_czytane(tmp_path):
    d = _dokument()
    d.add_paragraph("Tresc ciala.")
    d.sections[0].header.paragraphs[0].text = "NAGLOWEK"
    d.sections[0].footer.paragraphs[0].text = "STOPKA"
    sciezka = _zapisz(d, tmp_path, "hf.docx")
    assert _teksty(cp.elementy_docx(sciezka)) == ["Tresc ciala."]
    assert cp.czesci_pominiete_docx(sciezka) == 2
    pusty = _dokument()
    pusty.add_paragraph("x")
    assert cp.czesci_pominiete_docx(_zapisz(pusty, tmp_path, "bez.docx")) == 0


# --- języki w akapicie i szyfrant --------------------------------------------

MIESZANY = ("Organy pojednawcze — примирительного характера, которые рассматривают "
            "споры между сторонами; mediacja i arbitraż.")


@pytest.mark.parametrize("szyfr", ["cezar", "odwracanie"])
def test_szyfrant_nie_dzieli_akapitu(szyfr):
    """F4: jeden język na akapit — szyfrogram bez wstawek i odwracalny bez wymuszenia."""
    op: dict = {}
    zaszyfrowany = cp.przetworz(MIESZANY, cp.TRYB_SZYFRANT, "pl", szyfr, op)
    assert "<span" not in zaszyfrowany
    assert len([s for s in op["_segmenty_wynikowe"] if s[2]]) == 1


def test_zapis_surowy_bez_wstawek_lang(tmp_path):
    """F3: `.srt` i inne formaty surowe nie dostają `<span lang>` do treści."""
    op: dict = {}
    wynik = cp.przetworz("Ten akapit jest po polsku, ale ma wtręt: the quick brown fox "
                         "jumps over the lazy dog, i koniec zdania.",
                         cp.TRYB_REZYSER, "pl", "oczyszczenie", op)
    assert "<span" in wynik
    sciezka = cp.zapisz_wynik(wynik, str(tmp_path), "wynik", ".srt", "pl", cp.TRYB_REZYSER,
                              cp.wariant_po_id(cp.TRYB_REZYSER, "pl", "oczyszczenie"), wynik,
                              segmenty_wynikowe=op["_segmenty_wynikowe"])
    assert "<span" not in Path(sciezka).read_text(encoding="utf-8")


def test_naglowek_wersalikami_dostaje_wlasny_jezyk():
    """F8: zdanie wersalikami w rosyjskim akapicie nie dziedziczy rosyjskiego."""
    kawalki = cp._kawalki_jezykow("ŁÓDŹ JEST PIĘKNYM MIASTEM, а Москва — столица России "
                                  "и крупнейший город страны.", {"lacinka": "pl"})
    assert [k for k, _ in kawalki] == ["pl", "ru"]


def test_drugi_przebieg_idempotentny_i_spacje_przy_znacznikach():
    """F9: wynik przetworzony drugi raz bez zmian; spacja przy `<b>` zostaje."""
    tekst = ("Ten akapit jest po polsku, ale ma wtręt: the quick brown fox jumps over "
             "the lazy dog, i koniec zdania po polsku.")
    raz = cp.przetworz(tekst, cp.TRYB_REZYSER, "pl", "oczyszczenie", {})
    assert cp.przetworz(raz, cp.TRYB_REZYSER, "pl", "oczyszczenie", {}) == raz
    wynik = cp.przetworz("Ten akapit jest <b>bardzo</b> ważny dla nas wszystkich, naprawdę.",
                         cp.TRYB_REZYSER, "pl", "oczyszczenie", {})
    assert "jest <b>bardzo</b> ważny" in wynik


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
