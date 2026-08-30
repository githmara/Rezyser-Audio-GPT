#!/usr/bin/env python
"""
release_notes_sekcja.py — wycinanie sekcji `## <wersja>` z RELEASE_NOTES.md.

`RELEASE_NOTES.md` jest JEDYNYM źródłem prawdy dla treści opisu wydania na
GitHubie (nie autogenerator GitHuba). Sekcję wycinają dziś dwa workflowy:

  * `draft-release.yml` — przy tworzeniu draftu nowego wydania,
  * `sync-dev-release.yml` — przy skróconej procedurze dev-tools-only, gdy
    treść opublikowanego wydania trzeba zsynchronizować z uzupełnionym wpisem.

Do v18.24 logika żyła w inline'owym heredocu pierwszego z nich, razem z dwiema
lekcjami wpisanymi w komentarze. Drugi workflow napisał ją od nowa i OBIE lekcje
zgubił — dokładnie ten rodzaj duplikatu, który rodzina dev-tooli likwidowała
u siebie w tym samym cyklu. Stąd jeden moduł, wołany przez oba workflowy.

Skrypt działa dwojako: jako biblioteka (`wytnij_sekcje`) i jako CLI
(`python .github/scripts/release_notes_sekcja.py <plik_wyjsciowy>`, wersja
z env `WERSJA`, notatki z `RELEASE_NOTES.md` w bieżącym katalogu). Bez zależności
zewnętrznych — workflowy nie instalują pod niego niczego.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

NAZWA_PLIKU_NOTES = "RELEASE_NOTES.md"


class BladSekcji(Exception):
    """Sekcji nie ma albo jest niesparsowalna — wołający kończy workflow."""


def wytnij_sekcje(notes: str, wersja: str) -> str:
    """Zwraca treść sekcji `## <wersja> …` gotową jako body wydania.

    Args:
        notes: cała treść `RELEASE_NOTES.md`.
        wersja: numer z pliku `VERSION` (np. `18.24.0`), bez prefiksu `v`.

    Raises:
        BladSekcji: gdy sekcji dla tej wersji nie ma w pliku.

    Dwie lekcje z historii, obie wpisane w wzorzec — nie upraszczaj go:

    * **Separator po numerze jest OBOWIĄZKOWY** (`\\s+—` albo `\\s+\\W`). Numery
      wersji są prefiksami innych numerów, a `re.search` bierze PIERWSZE
      trafienie w pliku posortowanym malejąco: dla wersji `18.2` goły wzorzec
      `^##\\s+18\\.2` dopasowuje nagłówek `## 18.24.0` i cicho podstawia treść
      nowszego wydania pod starsze. Zmierzone na realnym pliku (2026-08-31).
    * **Alternatywa `\\Z` w lookaheadzie** — bez niej sekcja będąca OSTATNIĄ
      w pliku nie zostaje znaleziona wcale (wpadka v18.9).

    Końcowy separator `---` należy MIĘDZY sekcje, nie do treści: zostaje
    obcięty, bo inaczej body wydania (a więc i changelog w Dialogu
    Aktualizacji) kończy się nieeleganckimi myślnikami.
    """
    escaped = re.escape(wersja)
    wzorzec = rf"(## {escaped}(?:\s+—|\s+\W).*?)(?=\n## |\Z)"
    m = re.search(wzorzec, notes, re.DOTALL)
    if not m:
        raise BladSekcji(
            f"Sekcja `## {wersja}` nie znaleziona w {NAZWA_PLIKU_NOTES}. "
            f"Dopisz pełną sekcję wersji (## <wersja> — minor/patch release ...) "
            f"przed odpaleniem workflow."
        )
    tresc = m.group(1).rstrip()
    tresc = re.sub(r"\n+-{3,}[ \t]*$", "", tresc).rstrip() + "\n"
    return tresc


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write(
            "::error::Użycie: release_notes_sekcja.py <plik_wyjściowy> "
            "(wersja przez zmienną środowiskową WERSJA)\n"
        )
        return 2
    wersja = os.environ.get("WERSJA", "").strip()
    if not wersja:
        sys.stderr.write("::error::Brak zmiennej środowiskowej WERSJA.\n")
        return 2
    zrodlo = pathlib.Path(NAZWA_PLIKU_NOTES)
    if not zrodlo.is_file():
        sys.stderr.write(f"::error::Brak pliku {NAZWA_PLIKU_NOTES} w roocie repo.\n")
        return 2
    try:
        tresc = wytnij_sekcje(zrodlo.read_text(encoding="utf-8"), wersja)
    except BladSekcji as exc:
        sys.stderr.write(f"::error::{exc}\n")
        return 2
    cel = pathlib.Path(sys.argv[1])
    cel.write_text(tresc, encoding="utf-8")
    print(f"OK: {len(tresc)} znaków z sekcji ## {wersja} zapisanych w {cel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
