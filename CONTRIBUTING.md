# Contributing

Thanks for your interest in **Reżyser Audio GPT** — an accessibility-first
(NVDA/screen-reader) desktop app built with wxPython. The project is rooted in
Polish: the application UI ships in 9 languages, but the **developer tooling and
most code comments are written in Polish**, because that is the maintainer's
working language.

To keep the repo approachable for non-Polish-speaking contributors, the dev
tools follow one rule: **anything that tells you what a tool does, how to run it,
or why it failed is in English.** Routine progress chatter may still appear in
Polish — use the emoji and the English error/summary lines to navigate it.

Concretely, these are English: `--help` texts (including `metavar`), every `❌`
and `⚠️` line, the `====` banner of a result block and the verdict lines under it.
These may stay Polish: per-item progress (`🌍 fi/manual.yaml …`, `✅ fi/manual.yaml:
OK`, `⏭️ skipping`, `ℹ️ 14 units`) and code comments. `audyt_leakow.py
--bramka-kontrakt` checks the first group and warns on a regression; it never
blocks a build, and it deliberately ignores the second group, because a verdict
`✅` and a progress `✅` cannot be told apart mechanically. Polish **code
identifiers** quoted inside an English sentence (flag names such as
`--tylko-walidacja`, file names such as `finski.yaml`, constants such as
`KLASY_POL`) are correct and are masked by the gate rather than reported.

## Emoji status legend (canonical)

Every dev tool uses the same status emoji. Read them first:

| Emoji | Meaning |
|-------|---------|
| ✅ | success |
| ⚠️ | warning (often actionable — read it) |
| ❌ | error / fatal (the run stopped or a step failed) |
| ℹ️ | informational note |
| ⏭️ | skipped (nothing to do for this item) |

Other emoji (🌍 per-language, 🔎 filter, 📄 loaded, 📋 checklist, 💾 saved, 🎬/📚/🎙️ …)
are decorative step markers — they label a phase, not a status.

## Setup

```sh
# Windows
setup_dev.bat
# Linux / macOS (the SOURCE runs cross-platform; only the frozen release is Windows-only)
./setup_dev.sh
```

Always invoke the project interpreter explicitly (the venv is **not**
auto-activated in plain Bash):

```sh
.venv/Scripts/python <script>.py        # Windows venv layout
```

AI-backed tooling reads keys from **`golden_key.env`** in the repo root
(git-ignored). Set `ANTHROPIC_API_KEY` (`sk-ant-…`) — for the dev tooling this is
not optional, see the contract below. Since v18.4 the **application at runtime**
can instead be pointed at any OpenAI-compatible endpoint with
`LLM_PROVIDER=openai_compat` + `LLM_BASE_URL` + `OPENAI_API_KEY` + `LLM_MODEL`
(Claude stays the recommended quality baseline — prompts are tuned for it).

**Provider contract for the dev tooling.** `LLM_PROVIDER` is a global switch, but
in the translator family exactly one tool honors it: `buduj_wielojezyczne_docs.py`.
That is a consequence of protocol, not preference. The docs tool translates long
*prose* through the same engine the shipped app uses (text in, text out), so it
rides the provider-agnostic layer for free. Every other translator exchanges
*item lists* (`{id, source}` → `{id, target}`) whose shape is enforced by Anthropic
structured outputs — something the OpenAI-compatible branch cannot send today. So:

* the other translators **ignore** `LLM_PROVIDER` and need `ANTHROPIC_API_KEY`
  regardless of what you set (they say so on startup rather than failing silently);
* on the docs tool, a compat endpoint works but is **not** shape-checked by the API,
  and the prompts are tuned for Claude — read that draft with extra care. Because
  that warning would otherwise scroll away under minutes of progress output, the
  docs tool asks you to confirm the endpoint before it spends anything; pass
  `-y`/`--yes` to accept the contract up front (CI, automation, or simply a run you
  have confirmed before);
* none of this affects the audit and validation modes (`--audyt`,
  `--tylko-walidacja`, `audyt_leakow.py`), which need **no key at all**. If you are
  reviewing packs rather than generating them, you can work without any API access.

## Developer tools you may need

Run any of these from the repo root with `.venv/Scripts/python`. Pass `--help`
for full usage (help text is in English).

| Tool | What it does |
|------|--------------|
| `generuj_dokumentacje.py [-v | --waliduj]` | Regenerates `docs/*.txt` from `dictionaries/*/gui/dokumentacja/*.yaml`. `-v` = generate **and** hard-check. Run before committing doc changes. |
| `buduj_wielojezyczne_ui.py` | Batch-translates UI strings (`gui/ui.yaml`) from the Polish source into the other languages. Surgical mode: `-k <dotted.key>`. Review workflow: a full run always lands as a draft → review → `-f`/`--finalizuj`. |
| `buduj_wielojezyczne_docs.py` | Batch-translates the manuals (`gui/dokumentacja/*.yaml`) pl → others. Same draft → review → `-f` workflow. |
| `buduj_wielojezyczne_tryby.py` | Batch-translates the Director's **recipes** (`<code>/rezyser/*.yaml` — prompt templates, GUI labels, developer comments) pl → others. Same draft → review → `-f` workflow, plus `--tylko-walidacja` (no API) to audit existing packs against each other. |
| `buduj_wielojezyczne_opowiesci.py` | Batch-translates the **Tales** recipes (`<code>/opowiesci/*.yaml` — the narrative engine's system prompts, the vial mechanic, Quick Start presets) pl → others. Same draft → review → `-f` workflow and `--tylko-walidacja` (no API). Light `--fiolka` mode translates only the vial effect seeds a pack is MISSING and appends them, touching nothing else. `zaczatki.yaml` is excluded from `--wszystkie`: the presets are literature written per language, so name them explicitly if you really want a machine starting point. |
| `buduj_wielojezyczne_poliglota.py` | Batch-translates the **Polyglot** rules (`<code>/szyfry/*.yaml` plus the three cleanup tools in `<code>/akcenty/`) pl → others. Same draft → review → `-f` workflow and `--tylko-walidacja` (no API). Two things are special: worked examples in `opis` are COMPUTED by the real engine and injected into the prompt (the model never does the arithmetic), and LANGUAGE DATA (vowel sets, abbreviation tables, hissing pattern, Caesar shift range, ISO code) is never rewritten in an existing pack — for a new one the tool derives what is computable and asks the model once for the rest. |
| `buduj_wielojezyczne_akcenty.py` | Audits and derives the **accent pairs** (`<code>/akcenty/<accent>.yaml`). Not a translator: an accent file is a phonetic rule for one ordered pair (language of the text → language of the synthesizer), so `de/akcenty/finski.yaml` shares nothing with `pl/akcenty/finski.yaml` but its target. `--audyt` (default, no API) is the only check that compares all 72 pairs against each other and against the real engine: file contract, dead rules — including rules the diacritic pre-pass silently eats — sequential shadowing, case parity, script coverage, and every worked example in `opis` recomputed by the engine. `--nowy-jezyk <code>` derives the pairs a new language is missing, in both directions, and never overwrites a pair that already exists; `--replay <pack>/<accent>` re-derives an existing pair against its hand-written original and restores it afterwards. |
| `tlumacz_rdzen.py`, `tlumacz_bramki.py`, `dev_konsola.py` | Shared engine room of every tool above — API client and structured-output call, the target-language registry, literal freezing, YAML comment surgery, round-trip dumping, draft banners (`_rdzen`), the anti-"meta instruction skip" prompt block, the structural fingerprint gate and the provider contract (`_bramki`), UTF-8 console setup for all dev tools (`_konsola`). Dev-only, no GUI imports; edit here rather than copying code into one more tool. |
| `audyt_leakow.py` | Leak detector and release **gate**: `--bramka` (docs + `ui.yaml`), `--bramka-py` (Polish hard-coded strings in `*.py`), `--bramka-kontrakt` (the language contract below, in the dev tools themselves — **warning only, never blocks**). All three compare against a committed baseline; regenerate with `--zapisz-baseline[-py|-kontrakt]` only after reviewing the diff. Needs the optional `lingua` dependency — without it the gate is skipped with a warning, never blocked. |
| `refresh_languages.py` | Syncs the target-language registry (`jezyki_docelowe.yaml`) with the `dictionaries/<code>/` folders. Run after adding/removing a language. `--strict` for a CI guard. |
| `build_release.py` | Builds the PyInstaller release and the Inno Setup installer. |

> Machine translations are **always** reviewed for hallucinations before being
> finalized. A full (re)translation always lands as a draft and writes a review
> checklist to `skrypty/` (`przeglad_ui.md` / `przeglad_docs.md` /
> `przeglad_tryby.md` / `przeglad_opowiesci.md` / `przeglad_poliglota.md` /
> `przeglad_akcenty.md`); finalize with `-f` once reviewed.

## Adding a UI language

1. Create `dictionaries/<code>/` with at least `podstawy.yaml` (incl. the native
   `etykieta`) and the four language sub-folders (`akcenty/`, `szyfry/`,
   `rezyser/`, `opowiesci/`).
2. `python refresh_languages.py` — registers the new code.
3. `python buduj_wielojezyczne_ui.py -l <code>` then
   `python buduj_wielojezyczne_docs.py -l <code>` — translate UI + manuals.
4. `python buduj_wielojezyczne_poliglota.py -l <code>` — the cipher and cleanup
   rules. The tool derives the language data it can compute and asks the model
   once for the rest (vowels, abbreviations, hissing letters); expect to write
   `samogloskowiec.yaml` by hand if your language has no Polish-style softening
   (see the Finnish pack) — the gate will tell you.
5. `python buduj_wielojezyczne_akcenty.py --nowy-jezyk <code>` — the accent
   pairs, in both directions (your language read by the other synthesizers, and
   the other languages read by yours). Every pair lands as a draft: read the
   rule table, and **listen to a paragraph through the target synthesizer** —
   the gates are mechanical and none of them can hear.
6. Review the drafts, finalize with `-f`, then regenerate docs with
   `python generuj_dokumentacje.py -v`.

### Writing systems the engine handles today — and the ones to ask about first

Polyglot works on the written form of a language, so what it can do depends on
the script, not on the language's popularity. Before starting a pack, find your
script below.

**Ready today, data only (no Python).** Alphabetic scripts written with spaces
between words, whose letters map one-to-one to sounds: Latin, Cyrillic, Greek,
Armenian, Georgian. The Russian pack is the proof that a non-Latin alphabet
needs no engine change at all — it ships a 135-rule transliteration table and
nothing else.

**Please open an issue (or write to the maintainer / post on the forum) BEFORE
you start.** These need engine work, and part of Polyglot would have to be
masked for your language rather than shipped broken:

- **No spaces between words** — Chinese, Japanese, Thai, Khmer, Lao. Word-based
  rules (the stutter's minimum word length, Typoglycemia's "keep the first and
  last letter", single-letter merging) have nothing to cut on, so the engine
  would need a word segmenter — a heavy new dependency inside the frozen build.
- **No written vowels** — Arabic, Hebrew, Persian, Urdu. The vowel cipher has
  nothing to replace, and the reverse-the-sentence cipher plus the screen-reader
  HTML both need right-to-left handling (`dir`), which the output layer does not
  emit yet.
- **Syllable blocks or combining vowel marks** — Korean, Hindi, Bengali, Tamil.
  Here the letters exist but are composed into one character, so a rule for a
  single letter never matches until the text is decomposed first. This is the
  smallest of the three gaps — often one normalization step plus a review of the
  character classes — and Korean is the likeliest first candidate.
- **Logographic** — Chinese. Beyond the spacing problem, the Caesar cipher needs
  an alphabet and the vowel cipher needs vowels; neither exists. A Chinese pack
  is possible with those two rules hidden, and that decision is the
  maintainer's, not a detail to discover in review.

One trap worth stating even for accents: when the target synthesizer's language
is written in another script, the accent must OUTPUT that script. A romanized
approximation (`sukuriputo` in Latin letters for a Japanese voice) is read by
the synthesizer with English phonemes and sounds like a caricature — the
Japanese equivalent has to come out as kana.

## Pull requests

Open an issue or PR describing the change. Keep accessibility (keyboard
navigation, screen-reader labels) in mind for any GUI work.
