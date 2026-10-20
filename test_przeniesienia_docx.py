"""
test_przeniesienia_docx.py — czyszczenie `.docx` w Reżyserze (19.15, etap 4).

Logika czyszczenia żyje we wspólnym module `czyszczenie_tekstu.py` (bliźniak
bajt w bajt z ATA); jego zachowanie pilnują wektory
`czyszczenie_tekstu_wektory.json` uruchamiane tu przez runner unittest
`czyszczenie_tekstu_wektory.py` — ten sam, który ATA uruchamia bez zmian.
Ten plik sprawdza to, czego wektory nie widzą — wpięcie w Reżysera:
  1. runner wektorów przechodzi w całości;
  2. alfabety paczek (`core_poliglota.alfabety_paczek`) — dane, z których
     moduł ocenia mojibake;
  3. obie ścieżki `.docx` (Poliglota `tekst_docx`, Konwerter) czyszczą tak samo.

Uruchom:  .venv/Scripts/python -m pytest test_przeniesienia_docx.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_przeniesienia_docx.py
"""

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_poliglota as cp  # noqa: E402

TLO = "Ковид-диссидентов много. Онлайн."
REGULA_1 = "Урок он- лайн."             # reguła 1 trafia — bramka reguły 3 otwarta


def test_runner_wektorow_wspolnych():
    import io
    import czyszczenie_tekstu_wektory as runner
    wynik = unittest.TextTestRunner(verbosity=0, stream=io.StringIO()).run(
        unittest.defaultTestLoader.loadTestsFromModule(runner))
    assert wynik.wasSuccessful(), [str(x[1]) for x in wynik.failures + wynik.errors]


def test_modul_nie_importuje_projektu():
    # Bliźniak bajt w bajt: żadnego importu z Reżysera ani ATA.
    import ast
    drzewo = ast.parse(Path(__file__).with_name("czyszczenie_tekstu.py").read_text(encoding="utf-8"))
    moduly = {n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "")
              for n in ast.walk(drzewo) if isinstance(n, (ast.Import, ast.ImportFrom))}
    assert moduly <= {"__future__", "re", "unicodedata"}, moduly


def test_alfabety_paczek_per_jezyk():
    alfabety = cp.alfabety_paczek()
    assert {"pl", "ru", "fr", "is"} <= set(alfabety)
    assert "ą" in alfabety["pl"] and "Я" in alfabety["ru"] and "é" in alfabety["fr"]
    # „Áèáëèîòåêà”: każda litera znana jakiejś paczce, żadna paczka nie ma
    # wszystkich — na tym stoi ocena mojibake.
    assert not any(set("Áèáëèîòåêà") <= a for a in alfabety.values())


POVEST = ("À ñå ðîäè ïîøëè ñëàáû, 1äîáðó áîæëèâè1, à íà áåçóìèå îáðàòèëèñÿ è ó÷åëè æèòü "
          "â ñóåòh èâ íåïðàâäh,* â ïåðå÷èíå2* â")


@pytest.mark.parametrize("paczki", [None, ("pl", "en", "fi", "is", "it", "ru")])
def test_mojibake_jedno_kodowanie_na_prawdziwych_alfabetach(paczki):
    # Etap 5, „Повесть о Горе-Злочастии”: przy alfabetach paczek Reżysera ten
    # akapit samodzielnie wygrywał przez mac-cyrillic („обратилис€”). Jednostka
    # ma jedno kodowanie — tu też sytuacja ATA (sześć paczek, bez fr/de/es).
    import czyszczenie_tekstu as ct
    alfabety = [a for k, a in cp.alfabety_paczek().items() if paczki is None or k in paczki]
    wstep = "Ïîâåñòü î Ãîðå-Çëî÷àñòèè. Áèáëèîòåêà ëèòåðàòóðû Äðåâíåé Ðóñè."
    wynik, info = ct.napraw_mojibake_akapitow([wstep, POVEST], alfabety)
    assert wynik == [wstep.encode("latin-1").decode("cp1251"),
                     POVEST.encode("latin-1").decode("cp1251")]
    assert info["kodowania"] == {"latin-1>cp1251": 2}


@pytest.mark.parametrize("paczki", [None, ("pl", "en", "fi", "is", "it", "ru")])
def test_mojibake_teksty_paczek_nietkniete(paczki):
    # Sytuacja ATA: bez paczek fr/de/es ich teksty nie mogą zostać „przekodowane”
    # (cp866 robiło „Hauptmen№leiste”, cp1251 „partоmes”).
    import czyszczenie_tekstu as ct
    alfabety = [a for k, a in cp.alfabety_paczek().items() if paczki is None or k in paczki]
    for kod in ("fr", "de", "es", "is", "fi", "pl"):
        linie = (Path(__file__).parent / "dictionaries" / kod / "gui" / "ui.yaml") \
            .read_text(encoding="utf-8").split("\n")
        assert ct.napraw_mojibake_akapitow(linie, alfabety)[1]["przekodowane"] == 0, kod


def _docx(sciezka, *akapity):
    import docx
    d = docx.Document()
    for a in akapity:
        d.add_paragraph(a)
    d.save(str(sciezka))


def test_tekst_docx_poligloty(tmp_path):
    p = tmp_path / "slownik.docx"
    _docx(p, TLO, REGULA_1, "Издание, по- священного теме.",
          "Áèáëèîòåêà ëèòåðàòóðû Äðåâíåé Ðóñè. XVII âåê. Ïîâåñòü î Ãîðå-Çëî÷àñòèè")
    assert cp.tekst_docx(str(p)).split("\n")[1:] == [
        "Урок онлайн.", "Издание, посвященного теме.",
        "Библиотека литературы Древней Руси. XVII век. Повесть о Горе-Злочастии"]


def test_notatki_bez_reguly_1_nietkniete(tmp_path):
    p = tmp_path / "notatki.docx"
    _docx(p, "Плохой- хуже всех, худший.", "Ostatnia strofa- życzenia do E.")
    assert cp.tekst_docx(str(p)).split("\n") == [
        "Плохой- хуже всех, худший.", "Ostatnia strofa- życzenia do E."]


def test_konwerter_czysci_tak_samo(tmp_path, monkeypatch):
    wx = pytest.importorskip("wx")
    import docx
    import gui_konwerter as gk
    import i18n
    p = tmp_path / "slownik.docx"
    _docx(p, TLO, REGULA_1, "Издание, по- священного теме.")
    zapisane = []
    monkeypatch.setattr(docx.document.Document, "save",
                        lambda self, _p: zapisane.append([x.text for x in self.paragraphs]))
    monkeypatch.setattr(wx, "MessageBox", lambda *_a, **_k: wx.OK)
    app = wx.App(False)
    jezyk_przed = i18n.aktualny_jezyk()
    i18n.ustaw_jezyk("pl")
    ramka = wx.Frame(None)
    try:
        panel = gk.KonwerterPanel(ramka)
        panel._txt_file.SetValue(str(p))
        panel._on_build(None)
    finally:
        ramka.Destroy()
        app.Destroy()
        i18n.ustaw_jezyk(jezyk_przed)
    assert zapisane, "Konwerter nic nie zapisał"
    tekst = "\n".join(zapisane[-1])
    assert "посвященного" in tekst and "по- священного" not in tekst


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
