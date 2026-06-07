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
