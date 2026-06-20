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
(git-ignored). Set at least `ANTHROPIC_API_KEY` (`sk-ant-…`). Since v18.4 you may
instead point the engine at any OpenAI-compatible endpoint with
`LLM_PROVIDER=openai_compat` + `LLM_BASE_URL` + `OPENAI_API_KEY` + `LLM_MODEL`
(Claude stays the recommended quality baseline — prompts are tuned for it).

## Developer tools you may need

Run any of these from the repo root with `.venv/Scripts/python`. Pass `--help`
for full usage (help text is in English).

| Tool | What it does |
|------|--------------|
| `generuj_dokumentacje.py [--waliduj]` | Regenerates `docs/*.txt` from `dictionaries/*/gui/dokumentacja/*.yaml`. `--waliduj` = generate **and** hard-check. Run before committing doc changes. |
| `buduj_wielojezyczne_ui.py` | Batch-translates UI strings (`gui/ui.yaml`) from the Polish source into the other languages. Surgical mode: `--klucz <dotted.key>`. Review workflow: `--draft` → review → `--finalizuj`. |
| `buduj_wielojezyczne_docs.py` | Batch-translates the manuals (`gui/dokumentacja/*.yaml`) pl → others. Same `--draft`/`--finalizuj` review workflow. |
| `refresh_languages.py` | Syncs the target-language registry (`jezyki_docelowe.yaml`) with the `dictionaries/<code>/` folders. Run after adding/removing a language. `--strict` for a CI guard. |
| `build_release.py` | Builds the PyInstaller release and the Inno Setup installer. |

> Machine translations are **always** reviewed for hallucinations before being
> finalized. The `--draft` mode writes a review checklist to `skrypty/` for that.

## Adding a UI language

1. Create `dictionaries/<code>/` with at least `podstawy.yaml` (incl. the native
   `etykieta`) and the four language sub-folders (`akcenty/`, `szyfry/`,
   `rezyser/`, `opowiesci/`) plus `gui/ui.yaml`.
2. `python refresh_languages.py` — registers the new code.
3. `python buduj_wielojezyczne_ui.py --jezyki <code>` then
   `python buduj_wielojezyczne_docs.py --jezyki <code>` — translate UI + manuals.
4. Review the drafts, `--finalizuj`, then regenerate docs with
   `python generuj_dokumentacje.py --waliduj`.

## Pull requests

Open an issue or PR describing the change. Keep accessibility (keyboard
navigation, screen-reader labels) in mind for any GUI work.
