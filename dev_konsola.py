#!/usr/bin/env python
"""
dev_konsola.py — konfiguracja konsoli dla narzędzi deweloperskich.

Jedno zdanie kodu, siedem konsumentów. Każdy dev-tool w tym repo wypisuje na
stdout treści z dziewięciu paczek językowych (islandzkie `Þ`, cyrylica, emoji
statusu z legendy `CONTRIBUTING.md`), a Windows uruchamia Pythona z lokalnym
cp1250. Pierwszy taki znak wywracał cały przebieg `UnicodeEncodeError` — zanim
narzędzie zdążyło wypisać cokolwiek sensownego. Stąd wymuszenie UTF-8 przed
pierwszym `print`, powtarzane dotąd inline w siedmiu plikach.

Moduł jest DEV-ONLY i celowo **bez zależności** (sam `sys`) — dokładnie jak
`przeglad_tlumaczen` i `tlumacz_bramki`. To nie kosmetyka: konsumentami są też
narzędzia spoza rodziny tłumaczy (`build_release`, `generuj_dokumentacje`,
`audyt_leakow`, `refresh_languages`), a one nie mają powodu ciągnąć ruamel ani
`core_llm` po jedną funkcję konsolową. `tlumacz_rdzen` re-eksportuje
:func:`skonfiguruj_stdout`, więc rodzina `buduj_wielojezyczne_*` woła ją dalej
przez rdzeń — bez zmiany w czterech braciach.

Nie jest częścią aplikacji: `main.py` go nie osiąga, więc nie wchodzi do bundla
PyInstallera (runtime w paczce ma `stdout=None` i tak nie ma czego konfigurować).
"""
from __future__ import annotations

import sys


def skonfiguruj_stdout() -> None:
    """Przełącza stdout/stderr na UTF-8 na Windows (fail-soft, idempotentnie).

    Woła się z poziomu MODUŁU wołającego (nie z `main()`), bo pierwszy `print`
    bywa wcześniej niż `main` — np. w komunikacie fail-soft przy wczytywaniu
    rejestru języków. Poza Windowsem no-op: tam strumienie są UTF-8 z domyślnej
    lokalizacji. Błędy połykamy — narzędzie ma działać także pod strumieniem
    przekierowanym do pliku albo pod potokiem, który `reconfigure` odrzuca.
    """
    if sys.platform != "win32":
        return
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8")   # type: ignore[union-attr]
        except (AttributeError, OSError):
            pass
