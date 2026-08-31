"""
gui_diagnostyka.py — raport „dlaczego silnik pominął twoją regułę" (od v18.24.2).

Problem, który ten moduł zamyka: pliki w ``dictionaries/`` są EDYTOWALNE przez
użytkownika (Manager Reguł otwiera je w systemowym edytorze tekstu), a loadery
przepisów muszą wadliwy plik pominąć, żeby nie wywrócić aplikacji. Do v18.24.1
powód pominięcia szedł wyłącznie przez ``print(..., file=sys.stderr)`` — a build
release jest ``--windowed``, więc ``sys.stderr`` jest ``None`` i komunikat
przepadał. Kto zepsuł przepis, widział tylko brak opcji w RadioBoxie albo brak
przycisku postprodukcji; najgorsza ścieżka (błąd składni YAML) milczała nawet
w trybie dev.

Podział odpowiedzialności:
    * silnik (``przepisy_rezysera``, ``opowiesci_ai``) zbiera powody
      STRUKTURALNIE — kod powodu + dane techniczne, bez ``i18n`` i bez wxPython;
    * ten moduł składa z nich tekst w języku interfejsu i pokazuje go tam, gdzie
      użytkownik działa: przy wejściu do panelu Reżysera / Opowieści oraz pod
      przyciskiem „Odśwież" w Managerze Reguł.

Komunikaty (klucze ``diag.*`` w ``dictionaries/<kod>/gui/ui.yaml``) są długie
i techniczne, więc zgodnie z CLAUDE.md idą do ``wx.Dialog`` z ``TextCtrl``
(``TE_READONLY``), nie do ``wx.MessageBox``.
"""

from __future__ import annotations

import os

import wx

import core_poliglota as cp
import opowiesci_ai as oai
import przepisy_rezysera as pr
from i18n import aktualny_jezyk, t


# Podfolder paczki językowej z przepisami Opowieści (``opowiesci_ai`` liczy
# ścieżki sam, ale skan diagnostyczny musi wyliczyć LISTĘ plików do sprawdzenia).
_FOLDER_OPOWIESCI = "opowiesci"

# Panel narzędzia powstaje na nowo przy każdym wejściu (``main._pokaz_narzedzie``
# niszczy poprzedni), więc bez tej pamięci ten sam raport wyskakiwałby przy
# każdym kliknięciu „Reżyser". Raportujemy RAZ na sesję procesu per zestaw
# powodów: naprawa w Managerze Reguł czyści rejestr, więc kolejny, INNY problem
# znów się pokaże.
_POKAZANE: set[tuple[str, str, str]] = set()


# =============================================================================
# Skan aktywny (Manager Reguł)
# =============================================================================
def przeskanuj_reguly(jezyk: str | None = None) -> tuple[pr.PominietyPlik, ...]:
    """Czyta paczkę od nowa i zwraca wszystkie powody pominięcia.

    Rejestr powodów wypełnia się LENIWIE — panel zgłasza tylko to, co sam
    próbował wczytać. Manager Reguł potrzebuje odpowiedzi „czy moje pliki są
    dobre" NIEZALEŻNIE od tego, w które narzędzia użytkownik zdążył wejść, więc
    tutaj czyścimy cache (to zarazem naprawa bez restartu aplikacji: po poprawce
    kolejne wejście do panelu weźmie świeżą treść z dysku) i wczytujemy paczkę
    jawnie.

    Skanujemy paczkę JĘZYKA INTERFEJSU, a ``en`` dokładamy dopiero wtedy, gdy
    ta paczka nie dała ani jednego trybu — czyli DOKŁADNIE w sytuacji, w której
    panele sięgają po miękki fallback (``gui_rezyser``: ``if not przepisy and
    jezyk_ui != "en"``). Bezwarunkowy skan ``en`` byłby szumem: użytkownik
    z polskim interfejsem czyta polskie przepisy i nie ma powodu dowiadywać się
    o literówce w pliku, którego aplikacja u niego nie tknie.
    """
    jezyk = jezyk or aktualny_jezyk()
    pr.wyczysc_cache()
    cp.wyczysc_cache()
    oai._zaladuj_przepis.cache_clear()
    # Skan to świeży start diagnostyki: po naprawie (albo po zepsuciu pliku na
    # nowo TYM SAMYM sposobem) panele muszą mieć prawo pokazać raport ponownie.
    _POKAZANE.clear()

    _skanuj_paczke(jezyk)
    if jezyk != "en" and not pr.lista_trybow(jezyk):
        _skanuj_paczke("en")
    return pr.pominiete_pliki()


def _skanuj_paczke(kod: str) -> None:
    """Wczytuje wszystkie reguły jednej paczki, żeby wypełnić rejestr powodów.

    Zakres = te same kategorie, które Manager Reguł wystawia do edycji:
    ``rezyser/`` (tryby + postprodukcje), ``opowiesci/`` oraz ``akcenty/``
    i ``szyfry/``. Bez dwóch ostatnich raport „reguły sprawdzone" byłby
    obietnicą na wyrost — akcent zepsuty w edytorze tekstu znikałby z Poligloty
    tak samo cicho jak wcześniej tryb z Reżysera.
    """
    pr.lista_trybow(kod)
    pr.lista_postprodukcji(kod)
    cp.lista_wariantow(cp.TRYB_REZYSER, kod)      # akcenty/
    cp.lista_wariantow(cp.TRYB_SZYFRANT, kod)     # szyfry/
    for nazwa in _przepisy_opowiesci(kod):
        try:
            oai._zaladuj_przepis(kod, nazwa)
        except Exception:                                           # noqa: BLE001
            # Powód (błąd składni) jest już w rejestrze; wyjątek oznacza tylko,
            # że plik nie nadaje się do użycia — skan leci dalej po kolejne.
            pass
    # Zaczątki mają walidację WPISÓW (nie tylko pliku), a Manager Reguł ma
    # odpowiadać na „czy moje pliki są dobre" tak samo jak panel Opowieści.
    try:
        oai.zaczatki(kod)
    except Exception:                                               # noqa: BLE001
        pass


def _przepisy_opowiesci(jezyk: str) -> list[str]:
    """Nazwy (bez rozszerzenia) plików ``dictionaries/<jezyk>/opowiesci/*.yaml``.

    Skanujemy FOLDER, nie listę kanoniczną — prywatny przepis dopisany przez
    użytkownika też ma zostać sprawdzony, a brakujący plik z kanonu zgłosi się
    sam przy próbie użycia (fallback do ``en``).
    """
    folder = os.path.join(pr.DICTIONARIES_DIR, jezyk, _FOLDER_OPOWIESCI)
    if not os.path.isdir(folder):
        return []
    return sorted(
        os.path.splitext(n)[0] for n in os.listdir(folder)
        if n.lower().endswith((".yaml", ".yml"))
    )


# =============================================================================
# Formatowanie raportu
# =============================================================================
def sformatuj_raport(wpisy: tuple[pr.PominietyPlik, ...]) -> str:
    """Składa treść raportu w języku interfejsu (pusty ciąg dla braku powodów).

    Kolejność: wstęp → pozycje (plik, powód, szczegóły techniczne) → stopka
    z instrukcją naprawy. Ścieżka pliku i szczegół techniczny zostają dosłowne —
    użytkownik ma je odnaleźć w Managerze Reguł i w edytorze tekstu.
    """
    if not wpisy:
        return ""
    linie = [t("diag.wstep"), ""]
    for wpis in wpisy:
        linie.append(t("diag.wpis", plik=wpis.sciezka))
        linie.append(t(f"diag.powod.{wpis.powod}"))
        if wpis.szczegol:
            linie.append(t("diag.szczegol", szczegol=wpis.szczegol))
        linie.append("")
    linie.append(t("diag.stopka"))
    return "\n".join(linie)


# =============================================================================
# Prezentacja
# =============================================================================
def pokaz_raport(parent: wx.Window, wpisy: tuple[pr.PominietyPlik, ...]) -> None:
    """Pokazuje raport w dialogu (no-op, gdy nie ma o czym mówić)."""
    tresc = sformatuj_raport(wpisy)
    if not tresc:
        return
    _dialog(parent, t("diag.tytul"), tresc)


def pokaz_raport_lub_potwierdzenie(
    parent: wx.Window,
    wpisy: tuple[pr.PominietyPlik, ...],
) -> None:
    """Jak :func:`pokaz_raport`, ale brak powodów też dostaje odpowiedź.

    Używane pod „Odśwież" w Managerze Reguł: użytkownik nacisnął przycisk, żeby
    czegoś się dowiedzieć, więc cisza byłaby tu myląca („sprawdziło się czy
    nie?"). Krótkie potwierdzenie idzie przez ``wx.MessageBox`` — to jednorazowe
    powiadomienie, nie długa treść techniczna.
    """
    if wpisy:
        pokaz_raport(parent, wpisy)
        return
    wx.MessageBox(
        t("diag.brak_zastrzezen"),
        t("diag.brak_zastrzezen_tytul"),
        wx.OK | wx.ICON_INFORMATION,
        parent,
    )


def pokaz_raport_raz(parent: wx.Window) -> None:
    """Raport przy wejściu do panelu — tylko dla powodów jeszcze nie pokazanych.

    Wołane przez ``RezyserPanel`` / ``OpowiesciPanel`` po zbudowaniu interfejsu.
    Panel powstaje na nowo przy każdym przełączeniu narzędzia, więc bez filtra
    „już pokazane" ten sam dialog wracałby przy każdym kliknięciu — a nie ma go
    jak wyłączyć inaczej niż poprawieniem pliku.

    Rejestr jest WSPÓLNY dla całej aplikacji, więc panel może pokazać powód
    dotyczący pliku drugiego narzędzia (zależnie od kolejności wejść). To celowe:
    użytkownik ma jeden zestaw reguł i jeden moment, w którym chce o problemie
    usłyszeć — a każdy powód pokazujemy tylko raz.

    Wywołanie odkładamy przez ``wx.CallAfter``: konstruktor panelu jeszcze się
    nie skończył, a modalny dialog przed pierwszym ``Layout()`` przeszkadza
    czytnikowi ekranu (NVDA czyta wtedy niedokończony widok).
    """
    nowe = tuple(
        w for w in pr.pominiete_pliki()
        if (w.sciezka, w.powod, w.szczegol) not in _POKAZANE
    )
    if not nowe:
        return
    for w in nowe:
        _POKAZANE.add((w.sciezka, w.powod, w.szczegol))
    tresc = sformatuj_raport(nowe)
    wx.CallAfter(_dialog, parent, t("diag.tytul"), tresc)


def _dialog(parent: wx.Window, tytul: str, tresc: str) -> None:
    """Dialog z ``TextCtrl`` (TE_READONLY) + „Zamknij" — wzorzec A11y z CLAUDE.md."""
    if not parent:
        return
    dlg = wx.Dialog(
        parent, title=tytul,
        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        size=(700, 460),
    )
    sizer = wx.BoxSizer(wx.VERTICAL)
    pole = wx.TextCtrl(
        dlg, value=tresc,
        style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP,
        name=tytul,
    )
    sizer.Add(pole, proportion=1, flag=wx.ALL | wx.EXPAND, border=10)
    btn = wx.Button(dlg, wx.ID_OK, label=t("common.btn_zamknij"))
    sizer.Add(btn, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=10)
    dlg.SetSizer(sizer)
    btn.SetDefault()
    pole.SetFocus()      # NVDA czyta treść raportu od razu po otwarciu
    dlg.ShowModal()
    dlg.Destroy()
