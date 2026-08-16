#!/usr/bin/env python
"""
przeglad_tlumaczen.py — wspólny helper trybu ``--draft`` autotłumaczy.

Wszystkie buildery rodziny (`buduj_wielojezyczne_ui.py`, `_docs.py`, od v18.15
`_tryby.py`) w trybie roboczym zamiast kanonicznego nagłówka „NIE edytuj
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

import re
from pathlib import Path


# Sygnatura nagłówka draftu — pojedyncza, jednoznaczna linia w bloku nagłówkowym
# pliku roboczego. Oba buildery rozpoznają po niej, że plik jest jeszcze draftem
# (tryb `--finalizuj` podmienia nagłówek na kanoniczny TYLKO gdy marker obecny —
# zapewnia idempotencję i chroni przed „finalizacją" pliku już kanonicznego).
MARKER_DRAFTU = "⚠ WORKING DRAFT FOR REVIEW"

# Sygnatura nagłówka KANONICZNEGO („finalizacja"). Wstrzykiwana w blok nagłówkowy
# wyłącznie przez `--finalizuj` (po recenzji halucynacji) — świeże maszynowe
# tłumaczenie całego pliku NIGDY jej nie dostaje (zawsze idzie ścieżką draft).
# `_kanoniczny_naglowek`/`_auto_naglowek` w obu builderach interpolują tę stałą,
# a `generuj_dokumentacje._status_naglowka` egzekwuje jej obecność przed
# wygenerowaniem docs/*.html (guard przeciw wpuszczeniu draftu do buildu).
# Frazą po polsku celowo — kanon dotyczy WYŁĄCZNIE plików maintainera; draft
# (recenzent zewnętrzny / agent bez konstytucji) dostaje neutralny baner EN.
MARKER_KANONICZNY = "NIE edytuj ręcznie"


def czy_plik_jest_draftem(sciezka: Path) -> bool:
    """True, gdy plik nosi w bloku nagłówkowym ``MARKER_DRAFTU``.

    Wspólny helper obu builderów (od v18.6): chirurgiczny update (--klucz/
    --input/--retry) NIE zmienia statusu finalizacji — zachowuje istniejący
    nagłówek. Skanujemy WYŁĄCZNIE wiodące komentarze `#`. Brak/nieczytelny plik
    → traktujemy jak draft (bezpieczniejsza strona: guard buildu i tak odmówi,
    maintainer zauważy, zamiast wpuścić niesprawdzony nagłówek kanoniczny).
    """
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            for surowa in fh:
                striped = surowa.strip()
                if striped == "" or striped.startswith("#"):
                    if MARKER_DRAFTU in surowa:
                        return True
                    continue
                break
    except OSError:
        return True
    return False


def naglowek_roboczy(
    sciezka_rel: str, zrodlo_rel: str, narzedzie: str,
    nota_finalizacji: str | None = None,
) -> str:
    """Neutralny nagłówek YAML dla pliku-draftu (zachęca do edycji).

    Args:
        sciezka_rel: ścieżka wynikowa względem roota repo, np.
            ``dictionaries/it/gui/dokumentacja/manual.yaml``.
        zrodlo_rel: ścieżka źródła PL względem roota, np.
            ``dictionaries/pl/gui/dokumentacja/manual.yaml``.
        narzedzie: nazwa skryptu-generatora (do treści nagłówka).
        nota_finalizacji: opcjonalne nadpisanie akapitu o ``--finalizuj``.
            Domyślny mówi o PODMIANIE nagłówka na kanoniczny „do not edit by
            hand" — prawdziwe dla docs i ui. Builder przepisów (`_tryby.py`)
            podaje własną notę, bo tam finalizacja tylko ZDEJMUJE baner:
            `rezyser/*.yaml` zostaje plikiem edytowalnym przez lingwistę
            w Managerze Reguł, więc zakaz edycji byłby w nim kłamstwem.

    Zwraca blok komentarzy `#` zakończony pustą linią — drop-in zamiennik
    kanonicznego nagłówka „NIE edytuj ręcznie" w obu builderach.

    Treść PO ANGIELSKU — recenzentem draftu bywa nie-polskojęzyczny kontrybutor
    lub agent; polski nagłówek byłby dla niego barierą (spójnie z konwencją
    „cała infra kontrybutorska mówi po angielsku" i z checklistą poniżej).
    """
    nota = nota_finalizacji if nota_finalizacji is not None else (
        "# (After approval the maintainer runs `" + narzedzie + " --finalizuj`,\n"
        "# which swaps THIS header for the canonical \"do not edit by hand\" one\n"
        "# WITHOUT re-translating — your manual fixes are preserved. Do NOT\n"
        "# re-run with --draft / without it: a full re-translation would overwrite\n"
        "# this file and bring the hallucinations back.)\n"
    )
    return (
        "# =============================================================================\n"
        f"# {sciezka_rel}\n"
        "#\n"
        f"# {MARKER_DRAFTU} — preliminary machine translation.\n"
        f"# Generated by `{narzedzie}` from {zrodlo_rel} (Polish source).\n"
        "#\n"
        "# You MAY and SHOULD edit this file by hand: fix hallucinations, language\n"
        "# calques and inconsistencies against the Polish source. This is NOT the\n"
        "# final version — it exists for review before inclusion in a release.\n"
        + nota +
        "#\n"
        "# Keep 1:1 (do NOT translate): placeholders {key}, file/folder names\n"
        "# (skrypty/, opowiesci/, runtime/), extensions, the brand \"Reżyser Audio GPT\",\n"
        "# proper names (voices, Vocalizer, Tiflotecnia…) and version numbers.\n"
        f"# Full review checklist: skrypty/przeglad_{_rdzen_narzedzia(narzedzie)}.md\n"
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

## Names that must come from the engine, not the model's imagination

- CIPHER NAMES: take the label from
  `dictionaries/<code>/szyfry/<id>.yaml::etykieta` — never invent a descriptive
  one. The "Jąkanie" (stutter) cipher is it "Balbuzie", es "Tartamudeo" — NOT
  `inceppamento` / `cortes` (= a mechanism jamming). When in doubt, open the file.
- HARDCODED UI TAGS: `[CEL SCENY]` and `[ODRZUCENIE_AI]` are emitted VERBATIM by
  the Python engine in every language. Keep them 1:1 — do NOT translate to
  `[SCENE GOAL]` etc.; the user would search for a tag the engine never produces.

## Common calques — use the NATIVE term, never the literal

These slip past automatic leak detection (no Polish characters), yet they are
mistranslations. For each, pick the native target-language term — do NOT calque
from PL/EN. Canon (de / es / fr / it / ru):

| concept (PL) | de | es | fr | it | ru |
|---|---|---|---|---|---|
| wizard (kreator) | Assistent | asistente | assistant | procedura guidata | мастер |
| Python dict (mapy) | Dictionaries | diccionarios | mappages | mappe | словари |
| wire up code (okablować) | eingebunden | integrado | intégré | integrato | — |
| release suffix ("Wersja Wydawnicza") | Release-Version | Versión de Lanzamiento | Version de Lancement | Versione di Rilascio | Релизная версия |
| screen reader (czytnik ekranu) | Screenreader | lector de pantalla | lecteur d'écran | lettore di schermo | скринридер |

- "mapy" here means a Python dict → NEVER ru `карты` / de `Karten` (= playing
  cards / geographic maps). NEVER es `mapas` (use `diccionarios`).
- "kreator" is a wizard → NEVER `создатель` / `creatore` / `Schöpfer` / `creator`
  (= a creator/God).
- For the app-version suffix translate ONLY the suffix and keep
  `{numer_wersji} – ` unchanged — NEVER ru `Издательская` / it `di Pubblicazione`
  (= "for a book publisher").
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
- STEP HEADERS: section openers "KROK <n>:" must be localized to the native
  step word (de SCHRITT, es PASO, fr ÉTAPE, fi VAIHE, is SKREF, it PASSO,
  ru ШАГ). Models often leave "KROK" untranslated, treating it as a marker.
- ALGORITHM EXAMPLES must match the ENGINE, not intuition or another language.
  When you localize the example word in a cipher demo (e.g. the stutter cipher),
  RE-COMPUTE the output against the actual rule — a different native word can
  have a different second letter and break the very rule the example illustrates.
- INFLECTED LANGUAGES (Icelandic, Finnish): the machine output frequently gets
  the grammatical CASE/gender wrong (case is NOT frozen the way {placeholders}
  are). For is/fi a second, independent native/AI reviewer focused purely on
  declension is worth it — anchor every form to one already in the file.
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

_CHECKLIST_TRYBY = """\
## Director recipe hotspots (rezyser/*.yaml — prompt templates)

These files are NOT user-facing prose: they are PROMPTS that drive another AI
model, plus the developer comments documenting them. Two failure modes matter
more than style here.

- META-INSTRUCTION SKIP (the big one): check that every `prompt_systemowy` is
  still an INSTRUCTION, not its result. If a prompt that told the model to
  "produce a publication card with Title:, Genres:, …" came back as an actual
  filled-in card (or as a summary/commentary about the prompt), the model
  executed it instead of translating it. Reject that file.
- STRUCTURE 1:1 with the Polish source: same markdown headings, same NUMBER of
  numbered rules in the same order, same blocks, same blank lines. A rule that
  vanished is a behaviour change in the engine, not a style choice.
- ANCHOR LITERALS stay VERBATIM in every language, because Python looks for them
  by exact spelling:
  * `[ODRZUCENIE_AI]` (refusal tag) and the wrappers from `rezyser/baza.yaml`
    (`[STRESZCZENIE POPRZEDNICH WYDARZEŃ]:`, `[OBECNA FABUŁA]:`) — yes, they stay
    Polish in Finnish and Russian packs too;
  * the ElevenReader form field names in the publication card (`Title:`,
    `Description`, `Genres:`, `Target audience:`, `Mature content:`,
    `Sample chapters:`, `Publisher:`, `ISBN:`, `Author profile:`) and the closed
    value sets (the 22 genres, `Children`/`Young adult`/`Adult`/`All ages`,
    `Yes`/`No`) — the author copies them into an English-only form and
    `rezyser_ai.waliduj_karte_publikacji` matches on them;
  * ElevenLabs v3 audio tags (`[whispers]`, `[pauses]`) and the JSON KEYS of the
    Script mode (`"tury"`, `"mowca"`, `"tekst"`).
  What SHOULD be localized: placeholder values the model is told to write, e.g.
  `[do uzupełnienia ręcznie]` → `[to be filled in manually]`, and the speaker
  VALUE `"Narrator"` — the keys are a contract with Python, the narrator's name
  is spoken text and every shipped pack translates it (`Erzähler`, `Рассказчик`).
- TRIGGER WORDS (`slowa_wyzwalajace`): these are words the USER TYPES. Give the
  words a native speaker would actually type ("summarize"/"recap"), not a gloss
  of the Polish ones. Watch bilingual regions: a Swedish-speaking Finn typing in
  Finnish still types Finnish here — do not mix languages in one list.
- `sufiks_pliku_wyniku` becomes part of a FILE NAME on disk: one lowercase word
  with a leading underscore, no spaces, Latin diacritics folded
  (`_veroffentlichung`, `_utgafa`), non-Latin scripts kept (`_пересказ`). It must
  not collide with another recipe's suffix inside the same pack.
- `regex_podzial_rozdzialow` is DERIVED, not translated: the header words must be
  byte-identical to `dictionaries/<code>/gui/ui.yaml::rezyser.naglowek_*`, because
  the engine wrote those headers into the project file. A "nicer" native synonym
  silently breaks chapter detection (this is exactly how fi `Johdanto`, is
  `Formáli`/`Eftirorð` and ru `Введение` drifted from `Prologi`/`Prolog`/`Пролог`).
- REDUNDANT GLOSS: where the Polish prompt explains a foreign term for its Polish
  reader (`suomenruotsalaiset (Swedish-speaking Finns)`, `HSL (Helsingin seudun
  liikenne — …)`), the explanation is pointless — or a tautology — in a language
  where that term is native. Finnish must NOT read
  `suomenruotsalaiset (ruotsinkieliset suomalaiset)`. Drop the gloss or replace it
  with something the target reader really lacks.
- COMMENTS are documentation for the linguist maintaining the pack — they should
  read natively, but keep code identifiers, YAML key names, file names and
  decoration lines (`---`, `===`) unchanged.
"""


# Rdzeń nazwy buildera → blok hotspotów. Trzeci brat (`_tryby.py`, v18.15) wymusił
# generalizację dawnego `if narzedzie.endswith("docs.py")`: nowe narzędzie z tej
# rodziny dopisuje tu jedną parę i nie tyka reszty modułu. Nieznany rdzeń spada na
# checklistę UI (najbardziej ogólną) — appendix to wygoda, nie bramka.
_RE_RDZEN_NARZEDZIA = re.compile(r"buduj_wielojezyczne_([a-z_]+)\.py$")

_HOTSPOTY: dict[str, str] = {
    "docs": _CHECKLIST_DOCS,
    "ui": _CHECKLIST_UI,
    "tryby": _CHECKLIST_TRYBY,
}


def _rdzen_narzedzia(narzedzie: str) -> str:
    """`buduj_wielojezyczne_docs.py` → `docs`; nieznany wzorzec → `ui`."""
    m = _RE_RDZEN_NARZEDZIA.search(narzedzie)
    return m.group(1) if m else "ui"


def _formatuj_leaki(leaki_per_plik) -> str:
    """Formatuje wykryte PL-leaki (post-processor `audyt_leakow`) jako appendix.

    `leaki_per_plik`: ``{(kod, plik): {sekcja: [Leak, ...]}}``. NIE importujemy
    tu `audyt_leakow` — obiekty Leak są kacze-typowane po atrybutach
    (`linia_nr`, `powod`, `tekst`), więc moduł zostaje wolny od `lingua`.

    Detektor ŚWIADOMIE over-reportuje (dydaktyczne „ą ę ł", nazwy własne,
    linie z alfabetem → false-positive lingua), dlatego appendix triażuje po
    klasie powodu i jawnie ostrzega recenzenta. Zwraca "" gdy brak leaków.
    """
    if not leaki_per_plik:
        return ""
    bloki: list[str] = []
    for kod, plik in sorted(leaki_per_plik):
        per_sekcja = leaki_per_plik[(kod, plik)]
        prawdopodobne: list[str] = []
        mozliwe: list[str] = []
        for sekcja in sorted(per_sekcja):
            for l in per_sekcja[sekcja]:
                klasa = l.powod.split(":", 1)[0]
                wiersz = f"  - `{sekcja}` L{l.linia_nr} [{l.powod}]: {l.tekst}"
                (mozliwe if klasa == "znak-PL" else prawdopodobne).append(wiersz)
        if not prawdopodobne and not mozliwe:
            continue
        czesci = [f"### `{kod}` / {plik}"]
        if prawdopodobne:
            czesci.append("- LIKELY (whole-line drift / known Polish module name) — verify & translate:")
            czesci.extend(prawdopodobne)
        if mozliwe:
            czesci.append("- POSSIBLE (stray Polish characters — OFTEN a false positive):")
            czesci.extend(mozliwe)
        bloki.append("\n".join(czesci))
    if not bloki:
        return ""
    return (
        "## Auto-detected Polish-leak candidates (audyt_leakow)\n\n"
        "These lines were flagged AUTOMATICALLY after translation. This is a FUNNEL,\n"
        "not a verdict — the detector over-reports. Triage each one:\n\n"
        "- **LIKELY** rows (a whole line drifted back to Polish, or a known Polish\n"
        "  module name slipped through: „Reżyser\", „Poliglota\", „Księga Świata\",\n"
        "  „KROK\") are probably real — translate / inflect them.\n"
        "- **POSSIBLE** rows (stray Polish characters) are OFTEN FALSE POSITIVES:\n"
        "  Polish letters legitimately appear in didactic alphabet demos (ą, ę, ł),\n"
        "  in proper nouns (place names) and in cipher illustrations. Skip those.\n\n"
        "If you do NOT read Polish: paste a flagged fragment into a translator or a\n"
        "chatbot to decide whether it is stray Polish prose (fix it) or an intended\n"
        "literal (leave it). Line numbers are relative to the section's text.\n\n"
        + "\n\n".join(bloki)
        + "\n\n"
    )


def _tekst_promptu(
    narzedzie: str,
    wytworzone: list[tuple[str, str]],
    leaki_per_plik=None,
) -> str:
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

    hotspoty = _HOTSPOTY.get(_rdzen_narzedzia(narzedzie), _CHECKLIST_UI)

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
        f"{_formatuj_leaki(leaki_per_plik)}"
        "## How to return\n\n"
        "Edit the draft files in place and send them back. Do not touch the\n"
        "Polish source. When in doubt about a native idiom, leave a `# REVIEW:`\n"
        "comment rather than guessing.\n"
    )


def zapisz_prompt_przegladu(
    narzedzie: str,
    wytworzone: list[tuple[str, str]],
    root: Path,
    leaki_per_plik=None,
) -> Path | None:
    """Zapisuje checklistę przeglądu do ``skrypty/przeglad_<rdzen>.md``.

    Args:
        narzedzie: nazwa skryptu-generatora (np. ``buduj_wielojezyczne_docs.py``).
        wytworzone: lista par ``(kod_jezyka, nazwa_pliku)`` draftów z tego runu.
        root: katalog bazowy repo (``Path(__file__).parent`` buildera).
        leaki_per_plik: opcjonalnie ``{(kod, plik): {sekcja: [Leak]}}`` z
            post-processora ``audyt_leakow`` (builder docs liczy i przekazuje
            jako dane — patrz ``_formatuj_leaki``). UI woła bez tego argumentu.

    Returns:
        Ścieżkę zapisanego pliku, albo ``None`` gdy nic nie wytworzono lub
        zapis się nie powiódł (emisja checklisty to wygoda, nie część krytyczna —
        fail open, nie wywracamy buildu tłumaczeń).
    """
    if not wytworzone:
        return None
    # rdzeń nazwy: buduj_wielojezyczne_docs.py → docs, *_ui.py → ui, *_tryby.py → tryby
    rdzen = _rdzen_narzedzia(narzedzie)
    katalog = root / "skrypty"
    cel = katalog / f"przeglad_{rdzen}.md"
    try:
        katalog.mkdir(parents=True, exist_ok=True)
        cel.write_text(
            _tekst_promptu(narzedzie, wytworzone, leaki_per_plik),
            encoding="utf-8",
        )
    except OSError:
        return None
    return cel
