#!/usr/bin/env python
"""
test_prompty_markery.py — bramka na INSTRUKCJĘ, która mówi o materiale
niewidocznym dla modelu.

Dwa niezmienniki rodziny `buduj_wielojezyczne_*`, oba wykryte po fakcie i oba
mechanicznie sprawdzalne, więc od 19.2.2 mają bramkę zamiast noty:

1. **Żaden prompt systemowy nie cytuje markera z CYFRĄ** (`⟦P0⟧`, `⟦S1⟧`, `⟦3⟧`).
   Pomiar 18.12 (claude-sonnet-5) u brata od docsów: przy zerze tokenów
   w tłumaczonej jednostce model „zachowuje" marker, który zobaczył w samej
   instrukcji, po czym bramka parzystości ubija jednostkę deterministycznie.
   Opis markera wolno podawać wyłącznie symbolicznie (`⟦P{n}⟧`, `⟦i⟧`).

2. **Numer wersji nigdy nie dochodzi do modelu**, więc prompt nie ma prawa
   instruować o jego cyfrach. `app.wersja` w paczce PL to
   `"{numer_wersji} – Wersja Wydawnicza"`: numer wstrzykuje `i18n.t()`
   w RUNTIME'IE z pliku `VERSION`, a tokenizer zamraża sam placeholder. Reguła 6
   promptu `_ui` prosiła przez wiele wydań o „zachowaj cyfry i kreskę"
   i cytowała `"13.1 – Wersja Wydawnicza"` — instrukcja martwa w każdym
   przebiegu każdego języka, a przy tym łamiąca niezmiennik 1.

Testy są bez API: budują same prompty i tokenizują realną wartość z paczki.

Uruchom:  .venv/Scripts/python -m pytest test_prompty_markery.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_prompty_markery.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from ruamel.yaml import YAML

import buduj_wielojezyczne_akcenty  # noqa: F401  (import sanity dla całej rodziny)
import buduj_wielojezyczne_docs as docs
import buduj_wielojezyczne_opowiesci as opowiesci
import buduj_wielojezyczne_poliglota as poliglota
import buduj_wielojezyczne_tryby as tryby
import buduj_wielojezyczne_ui as ui
import tlumacz_ai

# Marker frozen-token z JAKĄKOLWIEK cyfrą w środku — to jest rzecz, której model
# nie ma prawa zobaczyć w instrukcji (patrz niezmiennik 1 w docstringu modułu).
MARKER_Z_CYFRA = re.compile(r"⟦[^⟧]*\d[^⟧]*⟧")

# Marker dowolny — do wycięcia z JEDNOSTKI (nie z promptu) przed szukaniem cyfr.
MARKER_DOWOLNY = re.compile(r"⟦[^⟧]*⟧")

# Numer w formie „19.2" / „13.1" — kształt, w którym wersja aplikacji NIE dociera
# do modelu. Sprawdzany wyłącznie w prompcie `_ui`, bo tylko on tłumaczy
# `ui.yaml`, gdzie ta wartość mieszka; prompty docsów legalnie cytują numery
# wydań w zdaniach o historii formatu szablonów.
NUMER_WERSJI_LITERALNY = re.compile(r"\b\d+\.\d+\b")

NAZWA_CELU = "Finnish"
KOD_CELU = "fi"


def _prompty() -> dict[str, str]:
    """Wszystkie prompty systemowe rodziny + rdzeń runtime'owego tłumacza."""
    return {
        "ui": ui._PROMPT_SYSTEMOWY(NAZWA_CELU, KOD_CELU),
        "ui/persona": ui._PROMPT_SYSTEMOWY(NAZWA_CELU, KOD_CELU, persona_hint=True),
        "tryby": tryby._PROMPT_SYSTEMOWY(NAZWA_CELU, KOD_CELU),
        "opowiesci": opowiesci._PROMPT_SYSTEMOWY(NAZWA_CELU, KOD_CELU),
        "opowiesci/fiolka": opowiesci._PROMPT_FIOLKA(NAZWA_CELU, KOD_CELU),
        "poliglota": poliglota._PROMPT_SYSTEMOWY(NAZWA_CELU, KOD_CELU),
        "poliglota/dane": poliglota._PROMPT_DANE_JEZYKA(NAZWA_CELU, KOD_CELU),
        "docs/kontekst": docs._PROMPT_CORE_KONTEKST,
        "docs/literaly": docs._PROMPT_CORE_LITERALY,
        "tlumacz_ai": tlumacz_ai._prompt_systemowy(NAZWA_CELU),
    }


@pytest.mark.parametrize("nazwa", sorted(_prompty()))
def test_prompt_nie_cytuje_markera_z_cyfra(nazwa: str) -> None:
    """Niezmiennik 1: marker opisujemy symbolicznie, nigdy z cyfrą."""
    tresc = _prompty()[nazwa]
    trafienia = MARKER_Z_CYFRA.findall(tresc)
    assert not trafienia, (
        f"prompt '{nazwa}' quotes a numbered frozen marker {trafienia} — the model "
        "can copy it into an answer with zero tokens of its own and the parity gate "
        "will then discard the whole unit. Describe the marker symbolically instead."
    )


def test_prompt_ui_nie_instruuje_o_cyfrach_wersji() -> None:
    """Niezmiennik 2, strona promptu: zero literalnych numerów wersji w `_ui`."""
    tresc = ui._PROMPT_SYSTEMOWY(NAZWA_CELU, KOD_CELU)
    trafienia = NUMER_WERSJI_LITERALNY.findall(tresc)
    assert not trafienia, (
        f"the _ui prompt quotes version-shaped literals {trafienia}; the version "
        "number is injected by i18n.t() at runtime and frozen by the tokenizer, so "
        "the model never sees it and any instruction about its digits is dead."
    )


def test_numer_wersji_nie_dochodzi_do_modelu() -> None:
    """Niezmiennik 2, strona danych: realna wartość z paczki PL po tokenizacji."""
    sciezka = Path(__file__).parent / "dictionaries" / "pl" / "gui" / "ui.yaml"
    dane = YAML().load(sciezka.read_text(encoding="utf-8"))
    wartosc = str(dane["app"]["wersja"])
    assert "{numer_wersji}" in wartosc, (
        f"{sciezka.name}::app.wersja no longer carries the {{numer_wersji}} "
        f"placeholder ({wartosc!r}) — this test and the _ui prompt rule both assume it."
    )

    tok, mapa = ui.tokenizuj_liscia(wartosc)
    assert "{numer_wersji}" in mapa.values(), (
        f"the tokenizer did not freeze the version placeholder: {mapa!r}")

    # Sam marker NOSI cyfrę (`⟦P0⟧` to jego indeks w mapie), więc liczy się to,
    # co zostaje POZA markerami — tam żadnej cyfry być nie może.
    poza_markerami = MARKER_DOWOLNY.sub("", tok)
    assert not any(znak.isdigit() for znak in poza_markerami), (
        f"the tokenized value {tok!r} carries a digit outside the frozen markers — "
        "what the model receives must be free of the version number."
    )


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
