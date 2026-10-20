"""
gui_wczytanie_pdf.py — wczytanie PDF-a w wątku tła z postępem (19.15).

Słownik z naprawą z fontu czyta się ok. 10 s; dotąd `core_pdf.wyciagnij`
biegł w wątku GUI pod `wx.BusyCursor`, więc NVDA przez cały ten czas
milczała, a okno nie odpowiadało. Tu ten sam wzorzec co odczyt stron-skanów
w Poliglocie (`_start_odczytu_skanow`):
  * `wx.ProgressDialog` (modalny dla aplikacji — czytnik ogłasza jego
    pojawienie się, tytuł i treść; zamknięcie = koniec wczytania, po którym
    panel pokazuje swój zwykły komunikat o wyniku);
  * wątek z własnym try/except — wyjątek w paczce `--windowed` nie ma
    dokąd trafić, więc nieoczekiwany ląduje w `error_log.txt` i wraca do
    panelu jako wynik; `threading.excepthook` z `main` jest siatką ostatnią;
  * wszystko, co dotyka wx, przez `wx.CallAfter`, a callback końca sprawdza,
    czy okno jeszcze żyje (zamknięcie aplikacji w trakcie wczytania).

Panel trzyma `watek` (np. jako `_worker_thread`), żeby jego guardy
`is_alive()` objęły też wczytanie PDF-a.
"""

from __future__ import annotations

import os
import threading
import traceback
from collections.abc import Callable

import wx

import bledy_ai
import core_pdf
from i18n import t


def _zapowiedz(funkcja, *argumenty) -> None:
    """`wx.CallAfter`, który po zamknięciu aplikacji (brak `wx.App`) milczy.

    Audyt: aplikacja zniszczona w trakcie wczytania — `CallAfter` z wątku
    rzucał „No wx.App created yet”, co dawało fałszywy wpis diagnostyki
    i raport crasha z `threading.excepthook`.
    """
    if wx.GetApp() is None:
        return
    try:
        wx.CallAfter(funkcja, *argumenty)
    except (AssertionError, RuntimeError):       # aplikacja kończy się właśnie teraz
        pass


class WczytaniePdf:
    """Jedno wczytanie: `start()`, potem `gotowe(wynik, wyjatek)` w wątku GUI.

    `gotowe` dostaje dokładnie jedno z dwóch: `WynikPdf` albo wyjątek
    (`BrakWarstwyTekstu`, `PdfNieDoOtwarcia` albo nieoczekiwany) — panel
    obsługuje je tak samo jak dotąd przy wywołaniu synchronicznym.
    """

    def __init__(self, okno: wx.Window, sciezka: str,
                 gotowe: Callable[[core_pdf.WynikPdf | None, Exception | None], None],
                 wyciagnij: Callable[..., core_pdf.WynikPdf] | None = None) -> None:
        self._okno = okno
        self._sciezka = sciezka
        self._gotowe = gotowe
        # Wstrzykiwane w testach (powolny / rzucający `wyciagnij` bez MainLoop).
        self._wyciagnij = wyciagnij or core_pdf.wyciagnij
        self._dlg: wx.ProgressDialog | None = None
        self._zakonczone = False
        self.watek = threading.Thread(target=self._worker, daemon=True)
        # Zamknięcie okna w trakcie: `Destroy()` okna najwyższego poziomu jest
        # odroczone do bezczynności pętli, a do tego czasu `bool(okno)` jest
        # prawdą, `IsBeingDeleted()` fałszem, a okno bywa nawet „widoczne”
        # (zmierzone) — pewny sygnał to jego `EVT_CLOSE`, słuchany na czas
        # wczytania (ze `Skip()`, więc handler okna głównego działa dalej).
        self._tlw = wx.GetTopLevelParent(okno)
        self._okno_zamkniete = False

    def start(self) -> threading.Thread:
        try:
            self._dlg = wx.ProgressDialog(
                t("common.pdf_wczytywanie_tytul"),
                self._tresc(1, 0),
                maximum=100, parent=self._okno,
                style=wx.PD_APP_MODAL | wx.PD_ELAPSED_TIME)
            if self._tlw:
                self._tlw.Bind(wx.EVT_CLOSE, self._przy_zamknieciu)
            self.watek.start()
        except Exception as blad:  # noqa: BLE001 — panel dostaje wyjątek jak z wątku
            # Audyt: wątek, który nie wystartował, zostawiał modalny dialog
            # i zablokowane okno na zawsze — sprzątamy, panel dostaje wyjątek.
            self._zakonczone = True
            dlg, self._dlg = self._dlg, None
            if dlg:
                dlg.Destroy()
            if self._tlw:
                self._tlw.Unbind(wx.EVT_CLOSE, handler=self._przy_zamknieciu)
            self._gotowe(None, blad)
        return self.watek

    def _przy_zamknieciu(self, event: wx.CloseEvent) -> None:
        self._okno_zamkniete = True
        event.Skip()

    def _tresc(self, numer: int, liczba: int) -> str:
        return t("common.pdf_wczytywanie_tresc",
                 nazwa_pliku=os.path.basename(self._sciezka),
                 numer_strony=numer, liczba_stron=liczba or "…")

    def _worker(self) -> None:
        """Wątek tła – żaden bezpośredni wx.* (tylko przez wx.CallAfter!)."""
        try:
            wynik = self._wyciagnij(
                self._sciezka, postep=lambda i, n: _zapowiedz(self._postep, i, n))
        except (core_pdf.BrakWarstwyTekstu, core_pdf.PdfNieDoOtwarcia) as exc:
            _zapowiedz(self._koniec, None, exc)          # oczekiwane — panel ma komunikat
        except Exception as exc:  # noqa: BLE001 — wątek nie może umrzeć po cichu
            bledy_ai.zapisz_diagnostyke(exc, "wczytanie_pdf._worker",
                                        slad=traceback.format_exc())
            _zapowiedz(self._koniec, None, exc)
        else:
            _zapowiedz(self._koniec, wynik, None)

    def _postep(self, numer: int, liczba: int) -> None:
        if not self._dlg or self._zakonczone:
            return
        # Treść (czytana przez NVDA) co ok. 10% stron, pasek przy każdej.
        krok = max(1, liczba // 10)
        procent = min(99, numer * 100 // max(liczba, 1))
        if numer == 1 or numer % krok == 0:
            self._dlg.Update(procent, self._tresc(numer, liczba))
        else:
            self._dlg.Update(procent)

    def _koniec(self, wynik: core_pdf.WynikPdf | None, exc: Exception | None) -> None:
        if self._zakonczone:              # wynik stosujemy dokładnie raz
            return
        self._zakonczone = True
        dlg, self._dlg = self._dlg, None
        if dlg:
            dlg.Destroy()
        if self._tlw and not self._okno_zamkniete:
            self._tlw.Unbind(wx.EVT_CLOSE, handler=self._przy_zamknieciu)
        # Okno zamknięte w trakcie wczytania (patrz `__init__`).
        if self._okno_zamkniete or not self._okno or self._okno.IsBeingDeleted():
            return
        self._gotowe(wynik, exc)
