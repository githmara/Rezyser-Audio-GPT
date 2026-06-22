# Audio Director GPT

**Hybrid Recording Studio for Radio Plays, Audiobooks, and Interactive Stories**

**Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


A set of self-contained AI-powered tools for automatic writing, planning, formatting, and translating extensive scripts, as well as conducting interactive text games. The project is a native desktop application (wxPython) designed from the ground up with full accessibility for screen readers (NVDA, VoiceOver) and compatibility with professional text-to-speech synthesizers (TTS). It operates without a browser and without a local server — it launches as a regular program window.

Version: **18.5.2** · Supported languages natively (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Main Modules

The application combines five tools in a single window, switchable via keyboard shortcuts (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 / Ctrl+5) or toolbar buttons. Each module operates independently, but they all share dictionary packages from the `dictionaries/` folder (accents, ciphers, AI creative modes) and central settings.


### 1. Directing (Ctrl+1)

The main studio for writing radio plays and audiobooks. You choose a mode — Brainstorming, Script (with `[SFX]`/`[Character: emotion]` tags), Audiobook (traditional prose) — and direct dialogue with the model through the Instruction field + World Book + Long-Term Memory:

* **Multi-Project World Book:** The system automatically loads dedicated universe rules (`.md`) in the background based on the active source file, ensuring full isolation (zero-click context loading).
* **Plot Accumulator:** The "infinite memory" algorithm. When the memory indicator enters a red alert state, the system automatically generates a plot summary and saves it to the Long-Term Memory field.
* **4 creative modes:** Each file in `dictionaries/<lang>/rezyser/` describes a separate AI director "personality" (Brainstorming, Script, Audiobook, Title Postproduction). You can tune their tone without programming — see the Rule Manager below.


### 2. Stories (Ctrl+2, second main mode since v15.0)

Interactive text games run by AI in the role of a narrative engine. Unlike the Director mode (where you generate a finished audiobook), Stories is a turn-by-turn dynamic plot:

* **Choices Mode:** each turn ends with 3-5 numbered options A-E. The most intuitive mode for blind players — NVDA reads the options, you press Tab and Enter.
* **Lesser Evil Mode:** like Choices, but every option is unfavorable — morally, physically, or strategically. Since v15.2, an additional "vial" — a reusable ZERO-numbered option of last-resort rescue, whose effects are pseudo-random (60% harmful / 30% perception-distorting / 10% rarely beneficial, distribution enforced by Python, the LLM has no way to invent a saving outcome).
* **Free Mode:** any action in free text ("I'll try to open the door"), the engine suggests 1-3 hints but does not force a choice.
* **One AI model for all modes:** since v18.1 all Stories modes use the same shared model (default and recommended: Anthropic Claude Sonnet 4.6) — a more powerful model rigorously adheres to the rules of the world (especially critical in Lesser Evil Mode, where every option must be genuinely unfavorable).


### 3. Polyglot (Ctrl+3, AI Translator + TTS Accents)

* **Safe Translator:** Long texts are automatically split into blocks measured in model tokens (safe also for densely written languages, e.g. Chinese) and translated sequentially; a truncated model response is detected and retried on smaller fragments. Each block is immediately saved to a hidden `.jsonl` file. Resumption after API limits are exhausted is fully automatic.
* **NVDA Automation:** Translations are saved as ready `.html` files with an embedded language tag or `.docx` files with tags injected directly into the XML structure.
* **8 local accents:** Ability to deliberately enforce a broken accent for local synthesizers (Tiflotecnia Voices, eSpeak, OneCore) through advanced regex rules. Supported foreign accents: Polish, Russian (with transliteration to Cyrillic), French, German, Spanish, Italian, Finnish, Icelandic.
* **Cipher Mode:** 6 local text-distorting algorithms — from reading backwards, through typoglycemia, to the classic Caesar cipher. Each with the local alphabet of the language pack (e.g., Caesar cipher on a 35-character Polish alphabet with diacritics).
* **Tag Fixer:** Non-invasively injects the provided ISO language code — including regional ones, e.g. pt-BR or zh-CN — into existing files.


### 4. Converter / Audiobook Architect (Ctrl+4)

* Processes raw `.txt` or `.docx` files for keyboard navigation for NVDA and systems like ElevenLabs.
* Automatically converts keywords (Act, Chapter, Prologue) into "Heading 1" headers in a Word document, and also cleans unnecessary HTML tags and Markdown markers.
* From v15.1, groups 5 turns into scenes with H1 headers (auto-detection of Stories) — prepares a file generated by Story mode for traditional audiobook publication.


### 5. Rule Manager (Ctrl+5, new from v13.0)

* **Dictionary Explorer without Python:** A visual tree of all YAML files in the `dictionaries/` folder — phonetic accents, ciphers, creative modes for Director and Story. A linguist or translator can browse, duplicate, edit, and delete rules directly from the GUI.
* **New Rule Creator:** A form with a type selection (accent, pure substitution cipher, Director mode, new base language, algorithmic cipher) creating a ready-made YAML template, and for more complex cases, generating a formatted prompt to paste into ChatGPT / Claude.
* **Refactor v13.0 — rules in YAMLs:** All accents, ciphers, and AI modes that until version 12.0 existed as "hardcoded" constants in Python code have been moved to declarative `.yaml` files loaded dynamically at application startup. Anyone who can handle Notepad can fine-tune an accent (e.g., change `sz → sh` to `sz → sch`), add a new language, or even change the system prompt tone for AI — without compiling code.


## Multilingual Support (9 languages natively)

From version 14.0, the application natively supports 9 base languages: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Each `dictionaries/<code>/` package contains diacritics, alphabet, and phonetic rules operating on text in that specific language — the application automatically detects the source language using the lingua-language-detector (per paragraph) and loads the appropriate package for each fragment separately.

The entire GUI interface, documentation (`docs/manual.<iso>.txt`), and most system messages are natively available in each of the supported languages. AI system prompts in Director and Story modes are written in the target languages (manually, not auto-translated — see `dictionaries/<code>/rezyser/` and `dictionaries/<code>/opowiesci/`).


## AI Architecture and Models Used

The recommended and default AI provider is Anthropic (Claude) — all system prompts are tuned for it, so it delivers the highest narrative quality, the best adherence to world-building rules, and the most natural prose. Consolidation on Claude happened in stages (Director in v18.0, Stories in v18.1, Polyglot and post-production in v18.2) — it resulted from empirically confirmed superiority in adhering to world rules, naturalness of prose, and avoiding clichés.

* **Anthropic Claude Sonnet 4.6 (default quality pillar):** The engine of ALL the application's intelligence. Responsible for creative narration (directing scripts, writing traditional Audiobook prose, Brainstorming, and ALL Stories modes — Choices, Lesser Evil, Freeform — along with generating summaries and Cinematic interludes), advanced translations with multi-block context preservation (Polyglot), and micro-tasks: iterative assignment of literary chapter titles and detection of content language codes.

* **Custom OpenAI-compatible endpoint (advanced option, from v18.4):** Instead of Anthropic, you can point to any endpoint compatible with the OpenAI API (OpenRouter, Groq, Fireworks, DeepSeek, local Ollama, OpenAI-compatible Gemini, and others) — through a single, shared code path, with no separate per-provider integration. Configuration in the `golden_key.env` file (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `OPENAI_API_KEY`); full instructions in the main manual (STEP 2B). Other models may deliver lower quality than Claude, for which the prompts are tuned — this is a conscious cost↔quality trade-off on the user's part.


### Known Model Limitations (Anti-Closure)

Despite the implementation of strict system directives mandating the cutting off of actions at moments of tension (known as the Anti-Closure directive), contemporary LLM models have a strong, inherent tendency to "close" stories. This often results in the inclusion of unwanted conclusions, morals, or false "happy endings," especially in Traditional Audiobook Mode.

This is a fundamental limitation of the current generation of artificial intelligence. For this reason, the application saves projects in regular, easily editable text files (`.txt`). This requires the user to assume the role of a live editor — occasionally manually removing the last, "closing" sentences generated by AI, then syncing memory with the corrected file via the "Refresh from disk" button, and continuing work.


## Installation and Launch

### For End Users (Windows)

1. Download the latest release from the **Releases** tab (the package marked as *Latest*) — the file `Rezyser_Audio_v<numer>_Installer.exe`. Launch it with a double-click. The installer lands by default in your account's local directory (`%LocalAppData%\Programs\Reżyser Audio GPT`) and does not require administrator rights; you can choose your own path using the "Browse" button. When finished, it creates shortcuts in the Start Menu and on the desktop, and optionally opens the user manual in the default `.txt` file editor.
2. **Anthropic API Configuration:** On first launch, the application will signal a missing key in the System Check section. Click the visible button to generate the `golden_key.env` file, open it in a text editor, and paste your Anthropic key (starting with `sk-ant-`).
3. **First Steps:** Open the file `docs/manual.pl.txt` (or in another language) in the installation folder — this is the complete user manual written in language accessible to every user, not just developers.


### For Developers (clone + setup)

1. Clone the repository to your disk.
2. Run the `setup_dev.bat` file to automatically create a virtual environment (`.venv/`) and download dependencies from `requirements.txt`.
3. Launch the application with the command `python main.py` or through the `run_dev.bat` file.

`.sh` scripts for macOS/Linux were removed in v13.1 — the development environment is focused on Windows due to the specifics of NVDA accessibility testing. Working with the code on other systems is possible but requires manual setup: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Scripts for building release packages** (`build_release.py`, `rezyser_audio.spec`, `installer.iss`) are used exclusively for creating packages for Windows. From version 17.0, `build_release.py` freezes the application with PyInstaller (onedir + windowed) according to `rezyser_audio.spec` — it produces `dist/` with a native `.exe` and a `runtime/` bundle folder (interpreter + libraries). No portable Python manually uploaded to the repository is needed anymore; the `dist/` and `build/` directories are in `.gitignore`.


## Full Documentation

This README is only an architectural outline of the project. To learn advanced techniques for preventing AI hallucinations, installation instructions for compatible speech synthesizers (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices), a full description of the Vial Story modes, and a complete user guide, refer to the files in the `docs/` folder:

* `docs/manual.<iso>.txt` — main user manual (written for the end user).
* `docs/tales.<iso>.txt` — Story mode manual (interactive text games).
* `docs/dictionaries.<iso>.txt` — guide for linguists without Python on how to add custom accents/ciphers/AI modes.

Each of these files is available in 9 languages — suffix `.<iso>.txt` (e.g., `manual.pl.txt`, `manual.en.txt`, `manual.de.txt`).


### Polish Naming — Guide for Non-Polish Speakers

The primary language of this project is Polish. Module names, class names, code comments, as well as directory and data file names are in Polish and — for backward compatibility and multilingual engine contract reasons — are intentionally NOT translated or changed. The following glossary will help developers and macOS/Linux system users navigate the structure.

**User Data Directories (next to the executable file or in the project directory):**

* `skrypty/` — *scripts*: Director module projects (`.txt` with narration, `.md` with the Book of the World, `_streszczenie.txt`).
* `opowiesci/` — *stories*: records of interactive Stories.
* `runtime/` — dual role: frozen application bundle directory (interpreter + libraries) AND container of hidden project metadata (`runtime/skrypty/`, `runtime/opowiesci/`).

**Source Data Subfolders in `dictionaries/<language-code>/` (visible in the Rule Manager):**

* `podstawy.yaml` — *basics*: language pack configuration and metadata.
* `akcenty/` — *accents*: phonetic rules for speech synthesizers.
* `szyfry/` — *ciphers*: text encryption modes.
* `rezyser/` — *director*: creative modes of the Director module.
* `opowiesci/` — *stories*: interactive Story modes.
* `gui/` — interface texts (`ui.yaml`) and documentation templates.


## License

The project is released under the **MIT** license — the full text is available in the [`LICENSE`](LICENSE) file in the main repository directory. In short: you are free to use, copy, modify, and distribute the software (including commercially), provided that you retain the copyright notice. The software is provided "as is," without any warranty.
