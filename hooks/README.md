# hooks/ — śledzone hooki git projektu

Katalog ze śledzonymi (commitowanymi) hookami git. Standardowy `.git/hooks/`
nie jest wersjonowany, dlatego trzymamy hooki tutaj i wskazujemy je gitowi
przez `core.hooksPath`.

## Aktywacja (jednorazowo, w roocie repo)

```sh
git config core.hooksPath hooks
```

Od tego momentu git używa hooków z tego katalogu zamiast `.git/hooks/`.
W repo nie ma dziś żadnych aktywnych hooków `.git/hooks/` (same `.sample`),
więc przełączenie jest bezkolizyjne. Konfiguracja jest lokalna dla klona —
po `git clone` na nowej maszynie trzeba ją powtórzyć.

## `pre-commit` — auto-reset flag debugowych

Pilnuje, by techniczne flagi debug (zaszyte w źródle, domyślnie `False`) nie
trafiły do commita z wartością `True`. Jeśli zaindeksowana wersja pliku ma
flagę = `True`, hook przepisuje ją na `False`, re-stage'uje plik i przepuszcza
commit ("robi to za Ciebie").

Obecnie pilnowane:

| Plik | Flaga |
|------|-------|
| `gui_opowiesci.py` | `EDYCJA_STANU_GRY_WIDOCZNA` |

Nowe flagi dodaje się w `pre-commit` (zmienna `FLAGI`) oraz w bliźniaczym
strażniku buildu `build_release.py::_weryfikuj_flagi_debug` (lista `_FLAGI_DEBUG`).

Uwaga: gdy w drzewie roboczym masz w tym samym pliku INNE, niezaindeksowane
zmiany, `git add` przy auto-resecie dołączy je do commita. W praktyce rzadkie
(flaga to eksperyment lokalny), ale warto wiedzieć.

## Dwie warstwy obrony

1. **`pre-commit`** (tu) — pilnuje commitów (auto-fix).
2. **`build_release.py::_weryfikuj_flagi_debug`** — twardo odmawia buildu, gdy
   flaga = `True` (działa niezależnie od tego, czy hook był aktywny).
