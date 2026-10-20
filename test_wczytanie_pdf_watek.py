"""
test_wczytanie_pdf_watek.py — wczytanie PDF-a w wątku tła (19.15).

`core_pdf.wyciagnij` biegł w wątku GUI pod `wx.BusyCursor` (słownik ≈ 10 s,
NVDA milczała). Teraz `gui_wczytanie_pdf.WczytaniePdf` w Poliglocie
i Konwerterze. Testy z PRAWDZIWYM wątkiem i powolnym, sztucznym
`wyciagnij` (blokuje się na `threading.Event`), bez MainLoop:
`wx.CallAfter` oddaje `app.ProcessPendingEvents()`.

Uruchom:  .venv/Scripts/python -m pytest test_wczytanie_pdf_watek.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_wczytanie_pdf_watek.py
"""

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

wx = pytest.importorskip("wx")

import core_pdf  # noqa: E402
import i18n  # noqa: E402


class _Postep:
    """Zamiast `wx.ProgressDialog` (modalny dla aplikacji) — zapis wywołań."""
    instancje: list = []

    def __init__(self, tytul, tresc, *_a, **_k):
        self.tresci = [tresc]
        self.zniszczony = False
        _Postep.instancje.append(self)

    def Update(self, _wartosc, tresc=None):
        if tresc:
            self.tresci.append(tresc)
        return True, False

    def Destroy(self):
        self.zniszczony = True

    def __bool__(self):
        return not self.zniszczony


@pytest.fixture
def srodowisko(monkeypatch):
    app = wx.App(False)
    jezyk_przed = i18n.aktualny_jezyk()
    i18n.ustaw_jezyk("pl")
    komunikaty: list[str] = []
    monkeypatch.setattr(wx, "MessageBox", lambda tresc, *_a, **_k: komunikaty.append(tresc) or wx.OK)
    monkeypatch.setattr(wx, "ProgressDialog", _Postep)
    _Postep.instancje = []
    puszczaj = threading.Event()
    wywolania: list[str] = []
    zachowanie = {"wyjatek": None}

    def powolny_wyciagnij(sciezka, znane_litery=None, postep=None):
        wywolania.append(sciezka)
        if postep:
            postep(1, 2)
        assert puszczaj.wait(10), "test nie puścił wątku"
        if zachowanie["wyjatek"] is not None:
            raise zachowanie["wyjatek"]
        return core_pdf.WynikPdf(akapity=["Akapit PDF."], liczba_stron=2,
                                 akapity_stron=[["Akapit PDF."], []])

    monkeypatch.setattr(core_pdf, "wyciagnij", powolny_wyciagnij)
    ramka = wx.Frame(None)
    try:
        yield app, ramka, komunikaty, puszczaj, wywolania, zachowanie
    finally:
        puszczaj.set()
        if ramka:
            ramka.Destroy()
        app.Destroy()
        i18n.ustaw_jezyk(jezyk_przed)


def _dokoncz(app, watek):
    watek.join(10)
    assert not watek.is_alive()
    for _ in range(5):
        app.ProcessPendingEvents()


def _poliglota(ramka, monkeypatch, tmp_path):
    import gui_poliglota as gp
    panel = gp.PoliglotaPanel(ramka)
    zakonczone = []
    monkeypatch.setattr(panel, "_dokoncz_wczytanie",
                        lambda nazwa, wynik, *_a: zakonczone.append((nazwa, wynik)))
    p = tmp_path / "dokument.pdf"
    p.write_bytes(b"%PDF-1.4")              # treść czyta sztuczny `wyciagnij`
    panel._txt_file.SetValue(str(p))
    return panel, zakonczone


def test_poliglota_drugie_wczytanie_odrzucone_wynik_raz(srodowisko, monkeypatch, tmp_path):
    app, ramka, komunikaty, puszczaj, wywolania, _ = srodowisko
    panel, zakonczone = _poliglota(ramka, monkeypatch, tmp_path)
    panel._on_load(None)
    watek = panel._worker_thread
    assert watek.is_alive() and panel._file_content == ""
    # Drugi „Wczytaj”, „Przeglądaj” i „Wyczyść” w trakcie: odmowa z komunikatem.
    panel._on_load(None)
    panel._on_browse(None)
    panel._on_clear(None)
    assert komunikaty == ["Przetwarzanie jest już w toku. Poczekaj na zakończenie."] * 3
    assert len(wywolania) == 1
    puszczaj.set()
    _dokoncz(app, watek)
    assert panel._file_content == "Akapit PDF." and panel._file_ext == ".txt"
    assert len(zakonczone) == 1
    # Postęp: okno z nazwą pliku i numerem strony, zamknięte na końcu.
    postep = _Postep.instancje[0]
    assert "dokument.pdf" in postep.tresci[0] and any("strona 1 z 2" in t for t in postep.tresci)
    assert postep.zniszczony


def test_poliglota_wyjatek_w_watku_zgloszony(srodowisko, monkeypatch, tmp_path):
    app, ramka, komunikaty, puszczaj, _, zachowanie = srodowisko
    zapisane = []
    slady = []
    monkeypatch.setattr("bledy_ai.zapisz_diagnostyke",
                        lambda exc, panel, slad=None: zapisane.append(panel) or slady.append(slad))
    panel, zakonczone = _poliglota(ramka, monkeypatch, tmp_path)
    zachowanie["wyjatek"] = RuntimeError("simulated failure")
    panel._on_load(None)
    puszczaj.set()
    _dokoncz(app, panel._worker_thread)
    assert any("simulated failure" in k for k in komunikaty), komunikaty
    assert zapisane == ["wczytanie_pdf._worker"]           # error_log.txt
    # Audyt: wpis ze śladem wywołań (plik i linia), nie samo `str(exc)`.
    assert "Traceback" in slady[0] and "powolny_wyciagnij" in slady[0]
    assert zakonczone == [] and panel._file_content == "" and panel._file_ext == ""
    assert _Postep.instancje[0].zniszczony


def test_poliglota_oczekiwany_blad_pdf_bez_logu(srodowisko, monkeypatch, tmp_path):
    app, ramka, komunikaty, puszczaj, _, zachowanie = srodowisko
    zapisane = []
    monkeypatch.setattr("bledy_ai.zapisz_diagnostyke",
                        lambda exc, panel, slad=None: zapisane.append(panel))
    panel, _ = _poliglota(ramka, monkeypatch, tmp_path)
    zachowanie["wyjatek"] = core_pdf.PdfNieDoOtwarcia("x.pdf", True, "Incorrect password")
    panel._on_load(None)
    puszczaj.set()
    _dokoncz(app, panel._worker_thread)
    assert zapisane == [] and len(komunikaty) == 1 and "hasł" in komunikaty[0]


def test_zamkniecie_okna_w_trakcie_wczytania(srodowisko, monkeypatch, tmp_path):
    app, ramka, komunikaty, puszczaj, _, _ = srodowisko
    panel, zakonczone = _poliglota(ramka, monkeypatch, tmp_path)
    panel._on_load(None)
    watek = panel._worker_thread
    ramka.Close()                            # jak krzyżyk okna: EVT_CLOSE → Destroy
    app.ProcessPendingEvents()
    puszczaj.set()
    _dokoncz(app, watek)                     # wątek kończy się po Destroy — bez wyjątku
    assert zakonczone == [] and komunikaty == []


def test_watek_ktory_nie_wystartowal_nie_blokuje_okna(srodowisko, monkeypatch, tmp_path):
    # Audyt: `Thread.start` rzucający po utworzeniu modalnego dialogu zostawiał
    # dialog i zablokowane okno na zawsze, a Poliglota — `_file_ext` „.pdf”.
    import gui_wczytanie_pdf as gwp
    app, ramka, komunikaty, *_ = srodowisko

    def nie_startuje(self):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(gwp.threading.Thread, "start", nie_startuje)
    panel, zakonczone = _poliglota(ramka, monkeypatch, tmp_path)
    panel._on_load(None)
    assert _Postep.instancje[0].zniszczony
    assert any("can't start new thread" in k for k in komunikaty)
    assert panel._file_ext == "" and zakonczone == []
    assert not panel._worker_thread.is_alive()


def test_konwerter_blad_po_wyniku_przyjaznym_komunikatem(srodowisko, monkeypatch, tmp_path):
    # Audyt: krok po wyniku (zdania o naprawie) stał dawniej w `try` odczytu.
    import core_skany
    import gui_konwerter as gk
    app, ramka, komunikaty, puszczaj, _, _ = srodowisko
    monkeypatch.setattr(core_skany, "zdania_naprawy_pdf",
                        lambda _w: (_ for _ in ()).throw(ValueError("boom")))
    panel = gk.KonwerterPanel(ramka)
    p = tmp_path / "dokument.pdf"
    p.write_bytes(b"%PDF-1.4")
    panel._txt_file.SetValue(str(p))
    panel._on_build(None)
    puszczaj.set()
    _dokoncz(app, panel._worker_thread)
    assert len(komunikaty) == 1 and "boom" in komunikaty[0]


def test_zapowiedz_po_zamknieciu_aplikacji_milczy(monkeypatch):
    # Audyt: `wx.CallAfter` bez `wx.App` rzucał „No wx.App created yet” →
    # fałszywa diagnostyka i raport crasha z `threading.excepthook`.
    import gui_wczytanie_pdf as gwp
    monkeypatch.setattr(wx, "GetApp", lambda: None)
    gwp._zapowiedz(lambda: None)                     # bez wyjątku


def test_wynik_stosowany_dokladnie_raz():
    import gui_wczytanie_pdf as gwp
    app = wx.App(False)
    ramka = wx.Frame(None)
    try:
        wyniki = []
        w = gwp.WczytaniePdf(ramka, "x.pdf", lambda wynik, exc: wyniki.append((wynik, exc)))
        w._koniec("pierwszy", None)
        w._koniec("drugi", None)
        assert wyniki == [("pierwszy", None)]
    finally:
        ramka.Destroy()
        app.Destroy()


def test_konwerter_drugi_start_odrzucony_i_buduje_po_wyniku(srodowisko, monkeypatch, tmp_path):
    import gui_konwerter as gk
    app, ramka, komunikaty, puszczaj, wywolania, _ = srodowisko
    zapisy = []
    monkeypatch.setattr(gk.docx.document.Document, "save", lambda self, p: zapisy.append(p))
    panel = gk.KonwerterPanel(ramka)
    p = tmp_path / "dokument.pdf"
    p.write_bytes(b"%PDF-1.4")
    panel._txt_file.SetValue(str(p))
    panel._on_build(None)
    watek = panel._worker_thread
    panel._on_build(None)
    panel._on_browse(None)
    assert komunikaty == ["Przetwarzanie jest już w toku. Poczekaj na zakończenie."] * 2
    assert len(wywolania) == 1 and zapisy == []
    puszczaj.set()
    _dokoncz(app, watek)
    assert len(zapisy) == 1
    assert len(komunikaty) == 3 and "Plik zapisano jako" in komunikaty[2]


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
