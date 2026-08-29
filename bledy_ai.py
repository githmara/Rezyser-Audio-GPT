"""
bledy_ai.py — Typowane wyjątki generacji AI (warstwa diagnostyczna ↔ i18n).

Problem, który rozwiązuje (reguła i18n błędów AI):
  Komunikaty o uciętej odpowiedzi / niepoprawnej strukturze JSON, choć wyglądają
  diagnostycznie, ZWYKŁY użytkownik widzi jako dialogi z przyciskiem OK. Surowy
  `str(exc)` w jednym języku (PL/EN) to idealna pożywka na zgłoszenie „braku
  i18n" — zwłaszcza że dokumentacja zachęca usera do otwierania issue, gdy AI
  zaczyna halucynować strukturę wcześniej, niż przewidują progi retry.

Rozwiązanie (dwie warstwy):
  * WARSTWA TECHNICZNA — treść wyjątku (argument konstruktora) zostaje po
    angielsku, z pełnym kontekstem (`finish_reason`, licznik retry, ostatni
    błąd walidacji). Trafia do `error_log.txt` i do maintainera — to ona służy
    do strojenia progów.
  * WARSTWA UŻYTKOWNIKA — GUI NIE pokazuje `str(exc)`. Mapuje TYP wyjątku na
    `klucz_i18n` (gołą nazwę klucza w `ui.yaml`) i woła `t(f"{panel}.{klucz}")`,
    więc komunikat jest natywny w każdym z 9 języków. Namespace (`rezyser.` /
    `opowiesci.`) dokłada panel, bo ten sam typ błędu współdzielą oba moduły.

Wszystkie wyjątki dziedziczą po :class:`RuntimeError`, więc istniejące klauzule
`except RuntimeError` / `except Exception` łapią je bez żadnych zmian — to
czysto addytywne wzbogacenie typu, nie zmiana kontraktu wyjątków.
"""

from __future__ import annotations

import datetime
import os
import platform

import sciezki

# Marker ODRĘBNY od `main.CRASH_MARKER` — to NIE jest crash aplikacji (wyjątek
# jest obsłużony, user dostaje normalny dialog), więc intake bota
# `issue_intake_sami.py` (patrz `_czy_crash_report`) nie powinien pomylić tego
# wpisu z crash-reportem i pomijać detekcję języka.
AI_DIAG_MARKER = "=== REŻYSER AUDIO GPT — AI DIAGNOSTIC LOG ==="
_PLIK_LOGU_BLEDOW = "error_log.txt"


def zapisz_diagnostyke(exc: "BladGeneracjiAI", panel: str) -> None:
    """Dopisuje techniczną treść wyjątku (EN, pełny kontekst) do ``error_log.txt``.

    Bug znaleziony 2026-07-01: `_komunikat_bledu_ai`/`_obsluz_blad` w GUI
    zamieniały wyjątek na komunikat lokalizowany i PORZUCAŁY oryginalną treść
    (`str(exc)`, finish_reason, licznik retry, ostatni błąd walidacji JSON) —
    mimo że docstring modułu obiecywał „trafia do error_log.txt". W praktyce
    nic tam nie trafiało, więc nie dało się zdiagnozować powtarzających się
    halucynacji struktury. Wołaj to PRZED zbudowaniem komunikatu dla usera.

    Nigdy nie rzuca — logowanie diagnostyki nie może wywrócić obsługi błędu,
    którą user i tak zaraz zobaczy w dialogu.

    **Zawartość jest świadomie WYŁĄCZNIE nietreściowa (v18.23).** Komunikat
    ``err_struktura`` prosi użytkownika o dołączenie tego pliku do zgłoszenia,
    a payload zawiera jego nieopublikowaną prozę — więc nie ma tu ani fragmentu
    tekstu, ani nazwy projektu. Diagnozę nosi za to warstwa techniczna:
    środowisko w nagłówku (:func:`core_llm.opisz_srodowisko`) plus ślad wywołań
    w treści wyjątku (model, ``request_id`` KAŻDEJ próby, ``stop_reason``, hash
    schematu, liczniki tokenów, metryki kształtu). Rozważane okno ±120 znaków
    wokół pozycji błędu zostało ODRZUCONE: po włączeniu structured outputs ta
    ścieżka niemal nie odpala, a gdy odpala, to zwykle przez ucięcie odpowiedzi,
    gdzie wycinek nie mówi nic, czego nie mówi licznik tokenów.
    """
    try:
        sciezka = os.path.join(sciezki.KATALOG_BAZOWY_STR, _PLIK_LOGU_BLEDOW)
        stempel = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            import core_llm

            srodowisko = core_llm.opisz_srodowisko()
        except Exception:  # noqa: BLE001 — nagłówek jest dodatkiem, nie warunkiem
            srodowisko = "(unavailable)"
        wpis = (
            f"{AI_DIAG_MARKER}\n"
            f"Panel: {panel}\n"
            f"Typ: {type(exc).__name__}\n"
            f"Data / Time: {stempel}\n"
            f"Platforma / Platform: {platform.platform()}\n"
            f"Srodowisko / Environment: {srodowisko}\n"
            f"{'-' * 60}\n"
            f"{exc}\n"
            f"{'=' * 60}\n\n"
        )
        with open(sciezka, "a", encoding="utf-8") as fh:
            fh.write(wpis)
    except Exception:  # noqa: BLE001 — logowanie nie może zamaskować oryginalnego błędu
        pass


class BladGeneracjiAI(RuntimeError):
    """Bazowy błąd generacji AI.

    `klucz_i18n` to GOŁA nazwa klucza w `ui.yaml` (bez namespace) — panel GUI
    dokłada własny prefiks (`rezyser.` lub `opowiesci.`). Domyślnie wskazuje na
    `err_struktura` jako najbardziej ogólny komunikat „spróbuj ponownie".
    """

    klucz_i18n: str = "err_struktura"


class BladStrukturyJSON(BladGeneracjiAI):
    """LLM zwrócił niepoprawną strukturę JSON mimo wyczerpania prób korekty."""

    klucz_i18n = "err_struktura"


class BladDlugosciOdpowiedzi(BladGeneracjiAI):
    """Odpowiedź ucięta przed domknięciem JSON (`finish_reason='length'`)."""

    klucz_i18n = "err_dlugosc"
