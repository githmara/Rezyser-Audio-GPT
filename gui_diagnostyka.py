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
import i18n
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


# =============================================================================
# Alarm: zepsuty plik tłumaczeń (twardy tekst PL+EN, v18.25)
# =============================================================================
# Raport wyżej mówi o plikach REGUŁ i sam potrzebuje `i18n`, żeby złożyć zdania.
# Gdy zepsuty jest `gui/ui.yaml`, tej drogi nie ma: klucze `diag.*` wróciłyby
# jako `[diag.wstep]`. Dlatego ta jedna ścieżka ma tekst zaszyty w kodzie po
# polsku i po angielsku — świadomy wyjątek od reguły „etykiety w ui.yaml",
# dokładnie jak `main._pokaz_dialog_crash` (handler ostatniej szansy nie może
# zależeć od warstwy, która właśnie padła).

_ALARM_TYTUL = "Reżyser Audio GPT — tłumaczenia interfejsu / interface translations"

# Powód → (zdanie PL, zdanie EN). Kody pochodzą z `i18n.POWOD_*`.
_ALARM_POWODY: dict[str, tuple[str, str]] = {
    i18n.POWOD_PARSE: (
        "błąd składni YAML we wskazanym miejscu (linia:kolumna)",
        "a YAML syntax error at the position shown (line:column)",
    ),
    i18n.POWOD_PUSTY: (
        "plik nie zawiera tłumaczeń (jest pusty albo nie jest mapą klucz: wartość)",
        "the file carries no translations (it is empty or not a key: value mapping)",
    ),
    i18n.POWOD_ODCZYT: (
        "nie udało się odczytać pliku (uprawnienia albo plik zajęty przez inny program)",
        "the file could not be read (permissions, or another program holds it open)",
    ),
}


def tekst_alarmu_ui(awarie: tuple[i18n.AwariaUI, ...]) -> str:
    """Składa treść alarmu o zepsutym ``ui.yaml`` (pusty ciąg = nie ma o czym mówić).

    Wyłuskane z prezentacji, żeby dało się to sprawdzić bez ``MainLoop`` —
    treść jest jedyną rzeczą, która w tym dialogu może być błędna.

    Skutek opisujemy DWOJAKO, bo user widzi dwie zupełnie różne rzeczy: dopóki
    angielski zapas (``i18n.JEZYK_FALLBACK``) jest zdrowy, interfejs mówi po
    angielsku; gdy padł także on — w oknach zostają surowe nazwy kluczy.
    """
    if not awarie:
        return ""
    zapas_dziala = not any(w.jezyk == i18n.JEZYK_FALLBACK for w in awarie)

    pozycje: list[str] = []
    for w in awarie:
        powod_pl, powod_en = _ALARM_POWODY.get(w.powod, (w.powod, w.powod))
        pozycje.append(
            f"[{w.jezyk}] {w.sciezka}\n"
            f"    PL: {powod_pl}\n"
            f"    EN: {powod_en}"
            + (f"\n    {w.szczegol}" if w.szczegol else "")
        )
    lista = "\n\n".join(pozycje)

    if zapas_dziala:
        skutek_pl = ("Napisy w oknach będą tymczasowo po ANGIELSKU — z zapasowej "
                     "paczki, która jest w porządku.")
        skutek_en = ("Labels will temporarily appear in ENGLISH — taken from the "
                     "fallback pack, which is fine.")
    else:
        skutek_pl = ("Zamiast napisów w oknach mogą pojawić się nazwy kluczy "
                     "w nawiasach kwadratowych (np. [main.app_title]), bo padła "
                     "też angielska paczka zapasowa.")
        skutek_en = ("Instead of labels you may see key names in square brackets "
                     "(e.g. [main.app_title]), because the English fallback pack "
                     "is broken as well.")

    return (
        "Nie udało się wczytać pliku z tłumaczeniami interfejsu.\n\n"
        f"{lista}\n\n"
        f"{skutek_pl}\n\n"
        "Co zrobić: otwórz wskazany plik w edytorze tekstu, popraw wskazane "
        "miejsce (najczęstsza pomyłka to niezamknięty cudzysłów albo złe wcięcie) "
        "i URUCHOM APLIKACJĘ PONOWNIE — tłumaczenia wczytują się raz, przy "
        "starcie. Jeśli nie wiesz, co poprawić, usuń plik i zainstaluj aplikację "
        "ponownie; wtedy wróci wersja z instalatora.\n\n"
        "----------------------------------------------------------------\n\n"
        "[EN] The interface translation file could not be loaded.\n\n"
        f"{skutek_en}\n\n"
        "What to do: open the file listed above in a text editor, fix the spot "
        "indicated (an unclosed quote or a bad indent is the usual cause) and "
        "RESTART THE APPLICATION — translations are loaded once, at startup. "
        "If you cannot tell what to fix, delete the file and reinstall the "
        "application to get the shipped version back."
    )


def pokaz_alarm_ui(parent: wx.Window | None, awarie: tuple[i18n.AwariaUI, ...]) -> None:
    """Pokazuje alarm o zepsutym ``ui.yaml`` (no-op przy braku awarii).

    ``parent=None`` jest legalne: alarm leci z ``main.main()`` PRZED powstaniem
    głównego okna (język ustawiamy zaraz po ``wx.App``), więc dialog nie ma
    jeszcze do czego się przypiąć.
    """
    tresc = tekst_alarmu_ui(awarie)
    if not tresc:
        return
    _dialog_twardy(_ALARM_TYTUL, tresc, parent)


def _dialog_twardy(tytul: str, tresc: str, parent: wx.Window | None) -> None:
    """Jak :func:`_dialog`, ale BEZ ani jednego napisu z ``i18n``.

    Przycisk dostaje „Zamknij / Close" na sztywno — ``t("common.btn_zamknij")``
    zwróciłoby tu w najgorszym razie `[common.btn_zamknij]`, czyli dokładnie
    objaw, o którym ten dialog ma poinformować.
    """
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
    btn = wx.Button(dlg, wx.ID_OK, label="Zamknij / Close")
    sizer.Add(btn, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=10)
    dlg.SetSizer(sizer)
    btn.SetDefault()
    pole.SetFocus()      # NVDA czyta treść od razu po otwarciu
    dlg.ShowModal()
    dlg.Destroy()


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
