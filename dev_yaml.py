#!/usr/bin/env python
"""dev_yaml.py — wspólne wczytanie YAML-a dla dev-tooli. Cisza jest tu ZAKAZANA.

Trzeci wspólny mięsień rodziny dev-tooli po :mod:`dev_konsola` (UTF-8 na stdout)
i :mod:`tlumacz_bramki` (bramki tłumaczeń). Wyjmuje implementację, którą
`audyt_leakow` dopracował przez trzy wydania i która stała się STANDARDEM
JAKOŚCI dla całego drzewa (decyzja maintainera 2026-09-08):

    plik, którego nie umiemy przeczytać, ORAZ plik, który parsuje się do
    czegoś innego niż oczekiwany kształt, są błędem FATALNYM — nigdy pustym
    słownikiem.

Dwie połowy jednej reguły, każda dopisana po realnej wpadce:

  * v18.9 — `return {}` w handlerze dawało bramce „zero sekcji = zero leaków =
    czysto", czyli zielone światło dla pliku, którego nikt nie przeczytał;
  * v18.26.1 — plik, który PARSUJE SIĘ poprawnie, ale nie do mapy (lista, GOŁY
    SKALAR, `null` po wykasowaniu treści), wracał przez `if not isinstance(dane,
    dict): return {}` — czyli znowu jako „czysto". Narzędzie przyjmuje konkretny
    schemat, więc niezgodność ze schematem jest błędem PLIKU, nie powodem do
    ciszy.

Czym ten moduł NIE jest: warstwą runtime'u. Aplikacja nie może padać na
zepsutym pliku reguł, który użytkownik sam edytuje — tam ten sam standard
realizuje REJESTR POWODÓW (`przepisy_rezysera.zglos_pominiecie`,
`i18n._zglos_awarie`) czytany przez `gui_diagnostyka`. Wspólne jest kryterium
(nic nie wypada ze skanu po cichu), różny kanał.

Parser wstrzykuje WOŁAJĄCY (`parser=`), bo w tym drzewie żyją dwa: `pyyaml`
(silnik, `audyt_leakow`, `generuj_dokumentacje`) i `ruamel` w trybie `safe`
(rodzina `buduj_wielojezyczne_*`, która round-trip ma i tak pod ręką). Różnią
się w drobiazgach YAML 1.1 vs 1.2 (`yes` jako bool kontra napis), więc
narzędzie audytujące dane MUSI zostać przy swoim — inaczej bramka mierzyłaby
inne dane niż ta, którą kalibrowano.

Komunikaty są po ANGIELSKU (kontrakt `CONTRIBUTING`: „anything that tells you
what a tool does, how to run it, or why it failed is in English") i przechodzą
kategorię `fatal` bramki kontraktu.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, NoReturn

import yaml

#: Sygnatura parsera: tekst pliku → korzeń YAML-a.
Parser = Callable[[str], Any]


def parser_pyyaml() -> Parser:
    """Domyślny parser: `yaml.safe_load` (YAML 1.1, tak jak silnik aplikacji)."""
    return yaml.safe_load


def parser_ruamel_safe() -> Parser:
    """Parser `ruamel.yaml.YAML(typ="safe").load` — dla rodziny autotłumaczy.

    Instancja jest reużywalna między plikami, więc tworzymy ją raz na wywołanie
    tej funkcji (wołający trzyma wynik w stałej modułu).
    """
    from ruamel.yaml import YAML

    return YAML(typ="safe").load


def padnij_na_pliku(plik: Path | str, powod: str, *, narzedzie: str) -> NoReturn:
    """Jednolity komunikat fatalny: tego pliku NIE przeczytaliśmy.

    Jedno zdanie dla wszystkich powierzchni, bo wniosek jest zawsze ten sam —
    narzędzie nie ma prawa pracować dalej na danych, których nie sparsowało,
    ani meldować „czysto" o pliku, którego nie widziało.
    """
    raise SystemExit(
        f"❌ {narzedzie}: cannot read {plik} ({powod}) — continuing would mean "
        f"working on data this tool never parsed."
    )


def _sprawdz_ksztalt(dane: Any, plik: Path, oczekiwany: type | tuple[type, ...],
                     narzedzie: str) -> Any:
    """Weryfikuje KSZTAŁT korzenia; niezgodność = błąd fatalny."""
    if isinstance(dane, oczekiwany):
        return dane
    nazwy = (oczekiwany.__name__ if isinstance(oczekiwany, type)
             else " / ".join(t.__name__ for t in oczekiwany))
    padnij_na_pliku(
        plik,
        f"the file parses as {type(dane).__name__}, but this tool expects {nazwy}",
        narzedzie=narzedzie,
    )


def wczytaj_lub_padnij(
    plik: Path,
    *,
    narzedzie: str,
    oczekiwany: type | tuple[type, ...] = dict,
    parser: Parser | None = None,
) -> Any:
    """Parsuje YAML i sprawdza kształt korzenia. Każde odstępstwo = FATAL.

    Args:
        plik: Ścieżka do pliku. BRAK pliku też jest tu błędem — użyj
            :func:`wczytaj_jesli_jest`, gdy nieobecność jest legalna (nie każda
            paczka ma każdy szablon).
        narzedzie: Nazwa narzędzia do komunikatu (stała modułu wołającego).
        oczekiwany: Oczekiwany typ korzenia (domyślnie mapa).
        parser: Parser YAML-a; domyślnie `pyyaml`.

    Returns:
        Skontrolowany korzeń pliku.
    """
    czytaj = parser or parser_pyyaml()
    try:
        tekst = plik.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # `UnicodeDecodeError` jest podklasą `ValueError`, NIE `OSError`, więc
        # sam `except OSError` przepuszczał go jako surowy traceback (audyt
        # v18.28.0). A to najzwyklejszy błąd użytkownika: plik reguł zapisany
        # w Notatniku jako ANSI albo UTF-16 zamiast UTF-8.
        padnij_na_pliku(plik, f"unreadable: {exc}", narzedzie=narzedzie)
    try:
        dane = czytaj(tekst)
    except Exception as exc:  # noqa: BLE001 — YAMLError obu parserów + Unicode
        padnij_na_pliku(plik, f"invalid YAML: {_jednolinijkowo(exc)}",
                        narzedzie=narzedzie)
    return _sprawdz_ksztalt(dane, plik, oczekiwany, narzedzie)


def wczytaj_jesli_jest(
    plik: Path,
    *,
    narzedzie: str,
    oczekiwany: type | tuple[type, ...] = dict,
    parser: Parser | None = None,
) -> Any | None:
    """Jak :func:`wczytaj_lub_padnij`, ale BRAK pliku zwraca ``None``.

    Rozdzielenie jest celowe: tylko wołający wie, co znaczy nieobecność JEGO
    pliku (nowa paczka bez akcentu, szablon jeszcze nieprzetłumaczony), ale
    nikt nie ma prawa uznać za nieobecny pliku, który JEST, tylko jest zepsuty.
    """
    if not plik.is_file():
        return None
    return wczytaj_lub_padnij(plik, narzedzie=narzedzie, oczekiwany=oczekiwany,
                              parser=parser)


def _jednolinijkowo(exc: Exception) -> str:
    """Wyjątek parsera jako JEDNA linia (surowy `str` pyyaml ma ich cztery)."""
    problem = getattr(exc, "problem", "") or ""
    marker = getattr(exc, "problem_mark", None)
    if marker is not None:
        pozycja = f"line {marker.line + 1}, column {marker.column + 1}"
        return f"{problem} ({pozycja})" if problem else pozycja
    return " ".join(str(exc).split())
