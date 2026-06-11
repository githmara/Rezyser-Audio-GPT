#!/usr/bin/env python
"""
przeglad_tlumaczen.py — wspólny helper trybu ``--draft`` autotłumaczy.

Oba buildery (`buduj_wielojezyczne_ui.py`, `buduj_wielojezyczne_docs.py`)
w trybie roboczym (`--draft`) zamiast kanonicznego nagłówka „NIE edytuj
ręcznie" wstrzykują NEUTRALNY nagłówek zachęcający do edycji oraz emitują
plik-towarzysz z checklistą przeglądu halucynacji. Cel: paczka kontrybucji
języka, którą maintainer wysyła osobie trzeciej / agentowi do recenzji —
recenzent bez naszej konstytucji/pamięci NIE może dostać sprzecznego rozkazu
(„plik wygenerowany automatycznie, nie edytuj") dokładnie wtedy, gdy chcemy,
żeby halucynacje poprawił.

Decyzja architektoniczna (2026-06-11, ścieżka D bez D3): paczka end-usera
zostaje czysta (v17.0 — szablony docs i dev-skrypty NIE wchodzą do bundla);
ulepszamy WYŁĄCZNIE tooling maintainera odpalany ze źródła. Ten moduł jest
dev-toolem (jak build_release / generuj_dokumentacje) — NIE importuje
`sciezki`, chodzi tylko ze źródła przez `Path(__file__).parent`.

Checklist celowo PO ANGIELSKU — spójnie z konwencją „cała infrastruktura
kontrybutorska mówi po angielsku, zerowy próg dla zagranicznych kontrybutorów"
(patrz nagłówki build_release.py od 13.1). Recenzent włoskiego/islandzkiego
docs to zwykle native danego języka albo agent — angielski jest najmniej
wykluczający. Hotspoty zaczerpnięte z [[reguly_tlumaczen]] (podświadomość agenta).
"""
from __future__ import annotations

from pathlib import Path


def naglowek_roboczy(sciezka_rel: str, zrodlo_rel: str, narzedzie: str) -> str:
    """Neutralny nagłówek YAML dla pliku-draftu (zachęca do edycji).

    Args:
        sciezka_rel: ścieżka wynikowa względem roota repo, np.
            ``dictionaries/it/gui/dokumentacja/manual.yaml``.
        zrodlo_rel: ścieżka źródła PL względem roota, np.
            ``dictionaries/pl/gui/dokumentacja/manual.yaml``.
        narzedzie: nazwa skryptu-generatora (do treści nagłówka).

    Zwraca blok komentarzy `#` zakończony pustą linią — drop-in zamiennik
    kanonicznego nagłówka „NIE edytuj ręcznie" w obu builderach.
    """
    return (
        "# =============================================================================\n"
        f"# {sciezka_rel}\n"
        "#\n"
        "# ⚠ PLIK ROBOCZY DO PRZEGLĄDU (DRAFT) — wstępne tłumaczenie maszynowe.\n"
        f"# Wygenerowany przez `{narzedzie} --draft` ze źródła {zrodlo_rel} (baza PL).\n"
        "#\n"
        "# MOŻESZ i POWINIENEŚ edytować ten plik ręcznie: popraw halucynacje,\n"
        "# kalki językowe i niespójności względem źródła PL. To NIE jest wersja\n"
        "# finalna — służy recenzji przed włączeniem do wydania. (Po akceptacji\n"
        "# maintainer regeneruje plik bez --draft, przywracając kanoniczny nagłówek.)\n"
        "#\n"
        "# Zachowaj 1:1 (NIE tłumacz): placeholdery {klucz}, nazwy plików/folderów\n"
        "# (skrypty/, opowiesci/, runtime/), rozszerzenia, markę „Reżyser Audio GPT”,\n"
        "# nazwy własne (głosy, Vocalizer, Tiflotecnia…) i numery wersji.\n"
        "# Pełna checklista przeglądu: skrypty/przeglad_<narzedzie>.md\n"
        "# =============================================================================\n"
        "\n"
    )


# Wspólny rdzeń checklisty (reguły niezależne od typu pliku).
_CHECKLIST_WSPOLNA = """\
## Keep these 1:1 — do NOT translate or alter

- `{curly_placeholders}` — copy verbatim, including the braces. Same multiset
  in the translation as in the Polish source.
- File/folder names and extensions: `skrypty/`, `opowiesci/`, `runtime/`,
  `.txt`, `.md`, `.yaml`. Never localize a path to a native word
  (`historias/`, `sögur/`, `script/` are BUGS — must stay `opowiesci/` etc.).
- The product brand "Reżyser Audio GPT" stays as-is in every language.
- Proper names: voices and engines (Vocalizer, Tiflotecnia, Cerrence,
  Eloquence, Samantha, Alice, Milena, …) and version numbers (e.g. 17.2.2).
"""

_CHECKLIST_DOCS = """\
## Documentation hotspots (manual / dictionaries / tales templates)

- FIRST LINE / TITLE must be in the target language — never leave a Polish
  title (`Podręcznik`, `Reżyser`, `Kompletny…`). A Polish first line is a leak.
- INVENTED SECTIONS: if a translated section is noticeably longer than the
  Polish source (rule of thumb: > 1.5×), the model probably bolted on an extra
  chapter. Compare against the PL source and delete anything with no PL counterpart.
- CAESAR CIPHER: the alphabet string and its character count MUST match THIS
  language's `dictionaries/<code>/podstawy.yaml` alphabet — do NOT blindly copy
  the Polish "35 chars / AĄBCĆ…". English = 26, Italian = 21, Russian uses
  Cyrillic, etc.
- TIPOGLICEMIA (scrambled-letters demo): the example sentence must STAY
  scrambled (inner letters shuffled). If it reads as grammatically correct
  prose, the effect was lost — re-scramble it natively.
- TERMINOLOGY CONSISTENCY: pick ONE native word for recurring terms (e.g. the
  "vial"/fiolka) and use it across every section and file in the pack.
- META-INSTRUCTION SKIP: for prompt-like passages ("You are a narrative
  engine…"), make sure the FIRST paragraph was actually translated — models
  tend to leave the opening lines in the source language, reading them as
  instructions to themselves instead of data.
"""

_CHECKLIST_UI = """\
## UI hotspots (ui.yaml)

- MENU ACCELERATOR `&`: exactly one per label, same count as the source. Move
  it onto a sensible letter of the TARGET-language word (do not just keep the
  Polish position).
- KEYBOARD SHORTCUTS `\\tCtrl+...`, `Alt`, `Shift`, `Cmd`: keep verbatim. Never
  localize modifier names.
- PATHS IN TOOLTIPS/MESSAGES: folder references (`skrypty/`, `runtime/skrypty/`,
  `opowiesci/`) must stay literal — the folder on disk is not localized.
- BUTTON-NAME CITATIONS: avoid quoting a literal button label inside a message;
  describe the action instead (future-proof + no hallucinated label).
- TOOLTIP vs LABEL are SEPARATE keys for the same control — translate both.
"""


def _tekst_promptu(narzedzie: str, wytworzone: list[tuple[str, str]]) -> str:
    """Składa treść markdown checklisty przeglądu."""
    # Grupuj wytworzone drafty per język dla czytelnej listy.
    per_jezyk: dict[str, list[str]] = {}
    for kod, plik in wytworzone:
        per_jezyk.setdefault(kod, []).append(plik)

    linie_plikow: list[str] = []
    for kod in sorted(per_jezyk):
        pliki = ", ".join(sorted(per_jezyk[kod]))
        linie_plikow.append(f"- `{kod}`: {pliki}")
    lista_plikow = "\n".join(linie_plikow) if linie_plikow else "- (none)"

    hotspoty = _CHECKLIST_DOCS if narzedzie.endswith("docs.py") else _CHECKLIST_UI

    return (
        f"# Translation review — draft batch from `{narzedzie} --draft`\n\n"
        "These files are MACHINE-TRANSLATED DRAFTS, not final. You are explicitly\n"
        "expected to EDIT them: fix mistranslations, calques and inconsistencies\n"
        "against the Polish source, then return the corrected files. The draft\n"
        "header inside each file says the same — ignore any \"do not edit\" wording\n"
        "you may know from canonical generated files; it does not apply here.\n\n"
        "## Draft files produced in this run\n\n"
        f"{lista_plikow}\n\n"
        "Compare each against its Polish source under\n"
        "`dictionaries/pl/gui/...` (same relative path, `pl` swapped in).\n\n"
        f"{_CHECKLIST_WSPOLNA}\n"
        f"{hotspoty}\n"
        "## How to return\n\n"
        "Edit the draft files in place and send them back. Do not touch the\n"
        "Polish source. When in doubt about a native idiom, leave a `# REVIEW:`\n"
        "comment rather than guessing.\n"
    )


def zapisz_prompt_przegladu(
    narzedzie: str,
    wytworzone: list[tuple[str, str]],
    root: Path,
) -> Path | None:
    """Zapisuje checklistę przeglądu do ``skrypty/przeglad_<rdzen>.md``.

    Args:
        narzedzie: nazwa skryptu-generatora (np. ``buduj_wielojezyczne_docs.py``).
        wytworzone: lista par ``(kod_jezyka, nazwa_pliku)`` draftów z tego runu.
        root: katalog bazowy repo (``Path(__file__).parent`` buildera).

    Returns:
        Ścieżkę zapisanego pliku, albo ``None`` gdy nic nie wytworzono lub
        zapis się nie powiódł (emisja checklisty to wygoda, nie część krytyczna —
        fail open, nie wywracamy buildu tłumaczeń).
    """
    if not wytworzone:
        return None
    # rdzeń nazwy: buduj_wielojezyczne_docs.py → docs, *_ui.py → ui
    rdzen = "docs" if narzedzie.endswith("docs.py") else "ui"
    katalog = root / "skrypty"
    cel = katalog / f"przeglad_{rdzen}.md"
    try:
        katalog.mkdir(parents=True, exist_ok=True)
        cel.write_text(_tekst_promptu(narzedzie, wytworzone), encoding="utf-8")
    except OSError:
        return None
    return cel
