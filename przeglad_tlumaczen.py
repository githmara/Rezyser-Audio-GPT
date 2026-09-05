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
- APP-VERSION SUFFIX (`app.wersja`): translate ONLY the suffix and keep
  `{numer_wersji} – ` unchanged. It denotes a SOFTWARE RELEASE — never a
  book/print edition (NEVER ru `Издательская` / it `di Pubblicazione` /
  de `Verlags-`), and never a tautology like is `Útgáfuútgáfa`
  ("edition-edition"). This checklist is the canon; the value shipped in
  `dictionaries/<code>/gui/ui.yaml::app.wersja` is the source of truth:
  pl `Wersja Wydawnicza` · en `Release Edition` · de `Release-Version` ·
  es `Versión de Lanzamiento` · fi `Julkaisuversio` · fr `Version de Lancement` ·
  is `Fullbúin útgáfa` · it `Versione di Rilascio` · ru `Релизная версия`.
  For a NEW language: pick the native phrase a released product would use,
  then add it to this list.
- SECOND REVIEWER (is/fi, the v17.8.0 rule) — DONE for both suffixes in 18.22,
  verdict KEEP for each, so do not reopen either without a new argument. What
  the review added, both for these packs and for any new language: the phrase
  must not imply a PRODUCT TIER that does not exist (NEVER is `Almenn útgáfa` —
  reads as the basic tier as opposed to a Pro edition this application has no
  such thing as), must not imply END OF LIFE (NEVER is `Lokaútgáfa` = "the last
  version ever released"), and must not raise the register to officialdom
  (NEVER is `Opinber útgáfa`, which reads as government-sanctioned). Where the
  native word for "version" is ambiguous between software and a printed
  publication (is `útgáfa`, fi `julkaisu`), the mild redundancy of naming the
  version twice (fi `julkaisu` + `versio`) is the LESSER EVIL — it anchors the
  phrase to software. Note also that a suffix asserting completeness (is
  `fullbúin` = feature-complete) says something slightly different from
  "publicly released"; it stays acceptable only because the product ships no
  visible beta channel to contrast with.

## When the passage is IMPERATIVE (numbered steps, "click X, save, go back")

Instructions behave differently from descriptive prose: the model starts
reading them as addressed to itself. Every item below was observed in a real
batch, and none of them is visible to the leak gate — the damage is written in
correct target language.

- SELF-DIRECTED INSTRUCTION PASTED INTO THE OUTPUT. The tool's own system
  prompt can come back translated and embedded in the section — one batch put
  a whole Italian block about the `⟦i⟧` markers plus "[FINE ISTRUZIONE — LA
  TRADUZIONE INIZIA QUI SOTTO]" into `it/dictionaries.yaml`, twice, and again
  on a retry. Grep EVERY pack (not only the ones a gate flagged) for
  `FINE ISTRUZIONE|END OF INSTRUCTION|marker|marcatori`. If a retry repeats it,
  finish that section by hand from the previous revision.
- REFUSAL-SHAPED PREAMBLE. The section may open with an apology for not being
  able to "execute" the instructions inside the text (`is`: "Fyrirgefðu, en ég
  get ekki »framkvæmt« leiðbeiningar…") and then translate perfectly. Delete
  the preamble, keep the translation.
- NEVER QUOTE A GUI LABEL LITERALLY. "Keep 1:1" outranks translating, so a
  Polish label quoted in the source walks into every pack untouched (observed:
  `kliknij "Odśwież drzewo"` kept verbatim in fi, it and ru). Write the
  placeholder instead — `{manager.btn_odswiez_label}` — and the generator
  expands it per language, so the quote can never drift from the real button.
  Since v18.26 a gate enforces this (`--waliduj` → GUI-LABEL GATE): it compares
  every quote AND every menu name next to a "→" arrow against that pack's
  `ui.yaml`, so a translated-but-hard-coded label is caught too, not just a
  Polish one. Two exceptions are legitimate and live in `_LITERALY_SWIADOME`
  keyed by (template section, key tail): the INSTALLER's own Browse button and
  NVDA's own Tools menu are not our labels — quoting them is correct, and
  placeholdering them would print our label in a sentence about someone else's
  window. If you add such a case, add the reason with it.
- A QUOTE THAT MISSES BY ONE WORD IS ALSO DEAD, and the gate can only WARN
  about it (it prints "quote(s) ALMOST equal to a label"). Read that list every
  release: half of those cases are the manual being RIGHT and the label being
  wrong (`de/ui.yaml` says "Senden an AI" where the manual says "Senden an KI";
  `it` "Invia all'AI", `fr` "pour AI"), the other half are inflection
  („Ný leikur" vs the real „Nýr leikur"). Fixing the label is a `ui.yaml`
  change in nine packs, so decide which side is wrong BEFORE you touch either.
- DO NOT let a placeholder swallow sentence punctuation. In English typography
  the full stop lives INSIDE the quotes (`a title such as "Error." NVDA will…`),
  so a quote of a label plus a period is not the label. The gate deliberately
  ignores a trailing single dot for this reason — one earlier revision did not,
  and the fix glued two sentences together.
- AN EXAMPLE THE USER HAS TO TYPE IS FUNCTIONAL, NOT PROSE. The World Book
  accent tag is the canonical trap: the word next to the trigger must be the
  accent's FILE NAME (`finski`, not "Finnish"/"finnischer"), the trigger word
  must exist in that pack's `podstawy.yaml::slowo_akcent` (Icelandic needed the
  inflected `hreim`, not just `hreimur`), and the accent must EXIST in that pack
  — the native-parity rule means `fi` has no `finski` and `fr` has no
  `francuski`. Since v18.25 a gate re-runs the real parser over every such quote
  (`python generuj_dokumentacje.py --waliduj` → ACCENT-TAG GATE). Since v18.26
  the same command covers three more channels of the SAME class: menu paths
  (GUI-LABEL GATE), Tales `/commands` against the real dispatcher
  (SLASH-COMMAND GATE) and every `X → Y` cipher/accent pair recomputed by the
  engine (EXAMPLE-PAIR GATE, moved in from `buduj_wielojezyczne_docs --audyt`,
  which you had to remember to run). What is STILL yours to verify by hand:
  file and folder names the user types, keyboard shortcuts, and anything the
  engine cannot recompute.
- A TRANSLATED COMMAND IS A DEAD COMMAND. The Tales dispatcher is
  single-language BY DESIGN (Polish plus an always-on English fallback), so a
  localized slash command does nothing. Two packs shipped one as a helpful
  gloss in parentheses — `es` "(/visualiza cómo es el guardia)" and `ru`
  "(/визуализируй, как выглядит страж)" — next to the real `/wizualizuj`.
  Follow `de`/`is`/`it`: keep the real command, translate only its ARGUMENT
  („/wizualizuj wie der Wächter aussieht").
- HEADINGS COUNT AS CONTENT when you retranslate a whole section. Compare the
  first line against the other headings of the SAME pack (`git show
  HEAD:<file>` gives you the pattern): a regenerated section likes to come back
  with the Polish step word ("KROK 7b" instead of VAIHE / ÉTAPE / PASSO).
- YAML FIELD NAMES STAY IN THE ORIGINAL — `kategoria`, `zakres`, `rola`,
  `sufiks_pliku_wyniku`. One batch translated them in five packs
  (`Ergebnisdatei_Suffix`, `sufijo_archivo_resultado`, `суффикс_файла_результата`).
  They are identifiers the user edits in the Rules Manager, not words.
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


_CHECKLIST_OPOWIESCI = """\
## Story recipe hotspots (opowiesci/*.yaml — interactive-fiction prompts)

These files drive the narrative engine of a game played by BLIND players: system
prompts for the storytelling model, the vial mechanic and the Quick Start
presets. Everything below has been observed at least once in a real batch.

- META-INSTRUCTION SKIP (the big one): every `prompt_systemowy` must still be an
  INSTRUCTION, not its result. If a prompt that told the model to "write the next
  turn as JSON" came back as an actual generated turn (a `{"narracja": …}`
  block), the model executed it instead of translating it. Reject that file.
- THE VIAL CHOICE LABEL IS A CONTRACT. `fiolka.etykieta_wyboru` is quoted
  VERBATIM four times inside `prompt_systemowy` (a JSON example, the rule fixing
  its position, two format examples). All five places must carry the SAME
  wording, letter for letter: the player reads the label from the YAML field
  while the engine matches the model's output against the prompt. A gate counts
  the quotations, but only YOU can tell whether the wording is idiomatic.
- CULTURAL TERMS AND PROPER NAMES (`routa`, `móða`, `metsänpeitto`, `fylgja`,
  `landvættur`, `Joulupukki`, `Korvatunturi`, the `Mause` company) stay
  THEMSELVES. Do NOT substitute your language's nearest equivalent
  (`Santa Claus`, `Weihnachtsmann`, `Дед Мороз`, `guardian angel`) — that is a
  different figure with different customs. You MAY inflect them; that is
  expected in Finnish, Icelandic and Russian. Do NOT demote the term to a
  parenthesis behind a native word (`Rauhreif (routa)` is wrong; `routa —
  Rauhreif that …` is right), and never translate it outright (one batch turned
  `routa` into French `rue`, "street").
- REDUNDANT GLOSS: the Polish source explains foreign terms for its Polish
  reader. Where the term is NATIVE in the target language the gloss becomes a
  tautology — drop it (Icelandic must not read `landvættur, guardian of this
  land`). Keep the gloss where it carries FICTIONAL information ("a yellowish
  fog smelling of matches") rather than a dictionary definition.
- PACK TERMINOLOGY WINS over your own taste. The words for the VIAL, a game
  TURN, the player's INVENTORY and a SCENE must be the ones this pack already
  uses — check the older effects in the same pool and the pack's manual. Observed
  drift: Spanish `frasco` against the pack's own `ampolla` (24 hits), Icelandic
  `skipti` for a turn where the pack says `umferð`.
- MEASURES AND COUNTS IN PROSE ARE DATA: "a step and a half", "two turns", "one
  item", "exactly once". Five packs mangled "a step and a half" in one batch
  (into "a metre and a half" and into "half a step"). Re-read every number.
- MECHANICAL CONSEQUENCE of a vial seed must survive: how long it lasts, how
  many things are lost, who decides what, and that a `rare_beneficial` effect
  NEVER resolves the scene. If the Polish gift is useful "for exactly this one
  turn and takes nothing off the weight of the scene", so is yours.
- FOURTH WALL: the base prompt forbids citing game mechanics. Where the source
  motivates a limit in-world (the craft rule of the being who grants it), keep it
  in-world — do not turn it into a meta comment about turns or probabilities.
- ENGINE CONTRACTS, verbatim: the JSON keys of a turn (`"narracja"`, `"wybory"`,
  `"id"`, `"tekst"`, `"postacie_aktywne"`, `"stan"`, `"meta"`, `"etap_luku"`…),
  the payload fields (`fiolka_aktywacja_w_tej_turze`, `fiolka_efekt_seed`,
  `stan.fiolka.*`), the category names (`harmful` / `distortion` /
  `rare_beneficial`), `id="0"`, the refusal tag `[ODRZUCENIE_AI]` and the
  Cinematic Meta Warning emoji marker ⚠️🚨⚠️ (the TTS filter cuts the block by
  those emoji — lose them and a blind player HEARS the meta commentary).
- THE NARRATIVE-ARC STAGE SET IS DERIVED, not translated: every pack ships
  `exposition|rising_action|climax|resolution`. The tool substitutes it; if you
  see localized stage names, something bypassed the tool.
- SECOND PERSON, INFORMAL: the engine narrates "You walk", "You feel". Where the
  target language distinguishes formal and informal address, use the one a novel
  would use — consistently across prompts and seeds.
- `zaczatki.yaml` (Quick Start presets) is LITERATURE written per language, not
  i18n. A machine draft is a starting point only: names, places and cultural
  references should be plausible for the target culture, while the genre, the
  dramatic situation, the number of named characters and `tryb_domyslny` stay as
  in the source. The preset KEYS are identifiers — never translate them.
"""


_CHECKLIST_POLIGLOTA = """\
## Polyglot rule hotspots (szyfry/*.yaml + the three tools in akcenty/)

These files define TEXT TRANSFORMATIONS: ciphers and screen-reader cleanup tools.
Their teaching text is checked by a PYTHON ENGINE, not by taste — a "nicer"
sentence that disagrees with the algorithm is a bug in the manual, not a style
choice. Everything below has been observed at least once in a real run.

- WORKED EXAMPLES ARE ARITHMETIC. Every `"word" → "result"` pair in `opis` must
  be exactly what `core_poliglota._algo_*` produces for THIS language pack. The
  tool computes them and injects them as `computed_examples`; a gate re-runs the
  engine on your text. Concretely: the stutter repeats ONE leading letter when
  the second letter is a vowel (`"Computer" → "C-c-c-computer"`) and TWO when it
  is a consonant (`"Straße" → "St-st-straße"`); the rest of the word ALWAYS goes
  lowercase (German nouns are the trap); a word is skipped only when it is
  SHORTER than `min_dlugosc_slowa` — a three-letter word at threshold 3 IS
  stuttered (this is how German „Ich" and French « moi » were wrong for years).
- EXAMPLE WORDS MUST BE NATIVE. A Polish `komputer`/`prysznic`/`dzień` left in
  your pack is a leak that NO character-based detector can see (no Polish
  diacritics in them) and that the arithmetic gate happily accepts. If the tool
  gave you a computed pair, use that word; if you replace it, the replacement
  must still satisfy the rule's branch.
- NUMBERS BELONG TO THIS PACK: the Caesar alphabet length and shift range come
  from `<code>/podstawy.yaml`, never from the Polish text (Polish has 35 letters,
  almost no other language does). Allowed shifts are ±(length−1): a shift equal
  to the alphabet length is the identity, i.e. plain text instead of a cipher.
- YAML FIELD NAMES STAY POLISH in every language: `min_dlugosc_slowa`,
  `samogloski`, `rozwiniecia`, `wzor_syku`, `min_przesuniecie`, `zamiany`. The
  user edits those very fields in the in-app Rules Manager, so a localized name
  points at a field that does not exist. Same for algorithm ids (`cezar`,
  `jakanie`, `odwracanie`, `samogloskowiec`, `typoglikemia`, `waz`) and category
  values (`szyfr`, `oczyszczenie`, `naprawiacz`).
- THE LABEL IS THE CANONICAL NAME of this cipher for the whole pack — `ui.yaml`
  and the manual quote it. The tool refuses to change an existing one; if you
  change it by hand, update those quotations in the same commit.
- A STEP WHOSE DATA IS EMPTY HERE MUST NOT BE DOCUMENTED AS WORKING. Most
  languages have empty `zmiekszenia_*` (they have no Polish `dzi→dź` softening),
  so their vowel-cipher description should say the step does not apply — the way
  the Finnish pack does — instead of translating the Polish example.
- LANGUAGE DATA IS NOT TRANSLATION and the tool never rewrites it in an existing
  pack: vowel sets, abbreviation tables, the hissing pattern and the ISO code
  belong to your language. If you see Polish letters (ą, ę, ł, ń, ś, ź, ż, ć) in
  any of them, something bypassed the tool.
- ABBREVIATIONS (`rozwiniecia`) are read by a text-to-speech engine: give the
  real written forms of YOUR language with their dots (`t.ex.`, `o.s.frv.`,
  `ул.`) and spell the expansion out in full. The reversed-abbreviation example
  in `opis` has to match your own table, not the Polish `m.in.` → `.nim`.
"""


_CHECKLIST_AKCENTY = """\
## Accent-pair hotspots (akcenty/<accent>.yaml)

An accent file is NOT a translation of anything. It is a PHONETIC RULE derived
for one ordered pair — the language of the text and the language of the speech
synthesizer that will read it. `de/akcenty/finski.yaml` and
`pl/akcenty/finski.yaml` share a target and nothing else: their rule tables are
disjoint, because one rewrites German spelling and the other Polish. Never
"translate" a sibling pack's file into yours.

- LISTEN TO IT. Every gate in this tool is mechanical; none of them can hear.
  Read a paragraph of your own language through the target synthesizer before
  approving the file — a table can satisfy every check and still sound like
  nothing in particular.
- WORKED EXAMPLES ARE RE-RUN BY THE ENGINE. Every `"x" → "y"` pair in `opis` is
  recomputed; the file is rejected when the engine disagrees. Chains
  (`"a" → "b" → "c"`) are checked end-to-end, and alternatives (`"au/eau" → "o"`)
  per member. A promise the rules cannot keep is a bug in the description.
- RULE ORDER IS A CONTRACT. The engine applies `zamiany` sequentially with
  `str.replace`, so a multi-character pattern must stand BEFORE any shorter
  pattern contained in it, and a rule that introduces a character a later rule
  consumes creates a cascade. Cascades are sometimes intended — say so in a
  comment when they are.
- THE PRE-PASS RUNS FIRST AND EATS RULES. With `usun_polskie_znaki: true` the
  engine flattens your language's own diacritics BEFORE `zamiany` (the field name
  is historical; it removes ALL diacritics). A rule whose pattern contains one of
  them is unreachable, and its promise in `opis` becomes a lie — this is how 43
  German umlaut rules stayed dead across seven accents. Either set the flag to
  `false` for that pair (as the Spanish and French packs do) or drop the rule and
  the prose about it.
- CASE: give every letter rule its capitalized counterpart, and remember that
  ALL-CAPS text (headings) needs the fully upper-cased form of a digraph as a
  third rule — `Sz` does not catch `SZ`.
- NON-LATIN OUTPUT: a transliterating accent (e.g. to Cyrillic) must cover the
  whole source alphabet — a leftover Latin letter is a hole in the table — and it
  must set `skleja_pojedyncze_litery: false`, because the engine's merging regex
  matches `[a-z]` only.
- VOICE NAMES IN `etykieta` ARE REAL PRODUCTS (NVDA/Vocalizer/OneCore). Keep the
  ones you were given or replace them with voices that actually exist for that
  language; an invented name is untestable for the next reviewer.
- `iso` IS THE CODE OF THE SYNTHESIZER's LANGUAGE, not of the text. It drives the
  `lang` tag of the output file, so a wrong value makes a screen reader read the
  result with the wrong voice.
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
    "opowiesci": _CHECKLIST_OPOWIESCI,
    "poliglota": _CHECKLIST_POLIGLOTA,
    "akcenty": _CHECKLIST_AKCENTY,
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
