# Audio GPT Regisseur

**Hybrides Aufnahmestudio für Hörspiele, Hörbücher und interaktive Geschichten**

**Andere Sprachversionen / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Ein eigenständiges Toolkit, das von KI angetrieben wird, um umfangreiche Skripte automatisch zu schreiben, zu planen, zu formatieren und zu übersetzen sowie interaktive Textspiele zu führen. Das Projekt ist eine native Desktop-Anwendung (wxPython), die von Grund auf für vollständige Zugänglichkeit mit Bildschirmlesern (NVDA, VoiceOver) und die Zusammenarbeit mit professionellen Sprachsynthesizern (TTS) entwickelt wurde. Es funktioniert ohne Browser und ohne lokalen Server — es startet als normales Programmfenster.

Version: **18.11.0** · Unterstützte Sprachen nativ (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Hauptmodule

Die Anwendung vereint in einem Fenster fünf Werkzeuge, die über Tastenkombinationen (Strg+1 / Strg+2 / Strg+3 / Strg+4 / Strg+5) oder Schaltflächen in der Symbolleiste umgeschaltet werden können. Jedes Modul funktioniert unabhängig, aber alle teilen sich die Wörterbuchpakete aus dem Ordner `dictionaries/` (Akzente, Chiffren, kreative AI-Modi) und zentrale Einstellungen.


### 1. Regie (Ctrl+1)

Das Hauptstudio zum Schreiben von Hörspielen und Hörbüchern. Du wählst einen Modus — Brainstorming, Skript (mit Tags `[SFX]`/`[Charakter: Emotion]`), Hörbuch (traditionelle Prosa) — und leitest den Dialog mit dem Modell durch das Instruktionsfeld + Weltbuch + Langzeitspeicher:

* **Multiprojekt-Weltbuch:** Das System lädt automatisch im Hintergrund die dedizierten Universumsregeln (`.md`) basierend auf der aktiven Quelldatei, um vollständige Isolation zu gewährleisten (Zero-Click-Kontextladen).
* **Handlungsakku:** Der Algorithmus des „unendlichen Gedächtnisses". Wenn der Speicherzeiger in den roten Alarmzustand wechselt, generiert das System automatisch eine Handlungszusammenfassung und speichert sie im Langzeitspeicherfeld.
* **4 kreative Modi:** Jede der Dateien in `dictionaries/<jzk>/rezyser/` beschreibt eine separate „Persönlichkeit" des KI-Regisseurs (Brainstorming, Skript, Hörbuch, Titel-Nachbearbeitung). Du kannst ihren Klang ohne Programmierung anpassen — siehe Regelmanager unten.


### 2. Geschichten (Strg+2, zweiter Hauptmodus ab v15.0)

Interaktive Textspiele, geleitet von der KI in der Rolle einer Erzähl-Engine. Im Unterschied zur Regie (wo man ein fertiges Hörbuch generiert) sind Geschichten eine dynamische, rundenbasierte Handlung:

* **Auswahlmodus:** jede Runde endet mit 3-5 nummerierten Optionen A-E. Der intuitivste Modus für blinde Spieler — NVDA liest die Optionen vor, man klickt Tab und Enter.
* **Modus Kleineres Übel:** wie Auswahl, aber jede Option ist moralisch, körperlich oder strategisch nachteilig. Ab v15.2 zusätzliche „Fläschchen" — eine wiederverwendbare, mit NULL nummerierte Option der verzweifelten Rettung, deren Effekte pseudozufällig sind (60 % schädlich / 30 % wahrnehmungsstörend / 10 % selten-günstig, die Verteilung wird von Python erzwungen, das LLM hat keine Möglichkeit, sich einen heilsamen Ausgang auszudenken).
* **Freier Modus:** beliebige Aktion in freiem Text („ich versuche, die Tür zu öffnen"), die Engine schlägt 1-3 Vorschläge vor, erzwingt aber keine Auswahl.
* **Ein KI-Modell für alle Modi:** ab v18.1 nutzen alle Modi der Geschichten dasselbe, gemeinsame Modell (standardmäßig und empfohlen Anthropic Claude Sonnet 5) — ein stärkeres Modell hält sich rigoros an die Regeln der Welt (besonders entscheidend im Modus Kleineres Übel, wo jede Option real nachteilig sein muss).


### 3. Polyglott (Ctrl+3, AI-Übersetzer + TTS-Akzente)

* **Sicherer Übersetzer:** Lange Texte werden automatisch in Blöcke aufgeteilt, die in Modell-Tokens gemessen werden (sicher auch für dicht geschriebene Sprachen, z.B. Chinesisch), und sequenziell übersetzt; eine abgeschnittene Modellantwort wird erkannt und auf kleineren Fragmenten wiederholt. Jeder Block wird sofort in einer versteckten `.jsonl`-Datei gespeichert. Die Wiederaufnahme nach Erschöpfung der API-Limits erfolgt vollautomatisch.
* **NVDA-Automatisierung:** Übersetzungen werden als fertige `.html`-Dateien mit eingebettetem Sprach-Tag oder `.docx`-Dateien mit direkt in die XML-Struktur injizierten Tags gespeichert.
* **8 lokale Akzente:** Möglichkeit, absichtlich einen gebrochenen Akzent für lokale Synthesizer (Tiflotecnia Voices, eSpeak, OneCore) durch fortgeschrittene Regex-Regeln zu erzwingen. Unterstützte fremdsprachige Akzente: Englisch, Russisch (mit Transliteration in Kyrillisch), Französisch, Spanisch, Italienisch, Finnisch, Isländisch, Polnisch.
* **Verschlüsselungsmodus:** 6 lokale Algorithmen zur Textverzerrung — von Rückwärtslesen über Typoglycämie bis hin zur klassischen Cäsar-Verschlüsselung. Jeder mit lokalem Alphabet des Sprachpakets (z.B. Cäsar-Verschlüsselung mit 35-Zeichen-Alphabet DE mit Diakritika).
* **Tag-Reparatur:** Injektiert nicht-invasiv den angegebenen ISO-Sprachcode — auch regionale Codes, z.B. pt-BR oder zh-CN — in bestehende Dateien.


### 4. Konverter / Audiobook-Architekt (Ctrl+4)

* Verarbeitet rohe `.txt`- oder `.docx`-Dateien für die Tastaturnavigation mit NVDA und Systemen wie ElevenLabs.
* Konvertiert automatisch Schlüsselwörter (Akt, Kapitel, Prolog) in „Heading 1"-Überschriften im Word-Dokument und bereinigt unnötige HTML-Tags und Markdown-Markierungen.
* Ab Version 15.1 Gruppierung von 5 Runden in Szenen mit H1-Überschriften (automatische Erkennung der Erzählung) — bereitet die im Erzählmodus generierte Datei für die traditionelle Audiobuchveröffentlichung vor.


### 5. Regel-Manager (Ctrl+5, neu ab v13.0)

* **Wörterbuch-Explorer ohne Python:** Visueller Baum aller YAML-Dateien im Ordner `dictionaries/` — phonetische Akzente, Chiffren, kreative Modi des Regisseurs und der Erzählungen. Ein Linguist oder Übersetzer kann Regeln direkt aus der GUI durchsuchen, duplizieren, bearbeiten und löschen.
* **Ersteller neuer Regeln:** Formular mit Typauswahl (Akzent, reine Austausch-Chiffre, Regisseur-Modus, neue Basissprache, algorithmische Chiffre), das eine fertige YAML-Vorlage erstellt, und für schwierigere Fälle einen formatierten Prompt zur Einfügung in ChatGPT / Claude generiert.
* **Refaktor v13.0 — Regeln in YAMLs:** Alle Akzente, Chiffren und AI-Modi, die bis Version 12.0 als „eingebettete“ Konstanten im Python-Code existierten, wurden in deklarative `.yaml`-Dateien verschoben, die beim Start der Anwendung dynamisch geladen werden. Jeder, der einen Texteditor bedienen kann, kann einen Akzent anpassen (z.B. `sz → sh` in `sz → sch` ändern), eine neue Sprache hinzufügen oder sogar den Klang des systemischen Prompts für die AI ändern — ohne den Code zu kompilieren.


## Mehrsprachigkeit (9 Sprachen nativ)

Ab Version 14.0 unterstützt die Anwendung nativ 9 Basissprachen: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Jedes Paket `dictionaries/<kod>/` enthält Diakritika, Alphabet und phonetische Regeln, die auf Text in dieser spezifischen Sprache operieren — die Anwendung erkennt die Quellsprache automatisch durch den lingua-language-detector (pro Absatz) und lädt das entsprechende Paket für jeden Abschnitt separat.

Die gesamte GUI, die Dokumentation (`docs/manual.<iso>.html`) und die meisten Systemmeldungen sind nativ in jeder der unterstützten Sprachen verfügbar. Die AI-Systemaufforderungen im Regisseur- und Erzählmodus sind in den Zielsprache verfasst (manuell, nicht automatisch übersetzt — siehe `dictionaries/<kod>/rezyser/` und `dictionaries/<kod>/opowiesci/`).


## KI-Architektur und eingesetzte Modelle

Der empfohlene und standardmäßige KI-Anbieter ist Anthropic (Claude) — alle System-Prompts sind auf ihn abgestimmt, weshalb er die höchste Qualität der Narration, die beste Einhaltung der Weltregeln und die natürlichste Prosa liefert. Die Konsolidierung auf Claude erfolgte in Etappen (Regisseur in v18.0, Geschichten in v18.1, Polyglot und Postproduktion in v18.2) — resultierend aus einer empirisch bestätigten Überlegenheit bei der Einhaltung der Weltregeln, der Natürlichkeit der Prosa und der Vermeidung von Klischees.

* **Anthropic Claude Sonnet 5 (Standard-Qualitätssäule):** Motor der GESAMTEN Intelligenz der Anwendung. Verantwortlich für die kreative Narration (Regie von Skripten, Verfassen traditioneller Hörbuch-Prosa, Brainstorming sowie ALLE Modi der Geschichten — Entscheidungen, Das kleinere Übel, Frei — samt Erstellung von Zusammenfassungen und Cinematic-Zwischensequenzen), fortgeschrittene Übersetzungen unter Wahrung des mehrblockigen Kontexts (Polyglot), sowie Mikroaufgaben: iterative Vergabe literarischer Kapiteltitel und Erkennung des Sprachcodes des Inhalts.

* **Eigener OpenAI-kompatibler Endpoint (erweiterte Option, ab v18.4):** Anstelle von Anthropic kann ein beliebiger, mit der OpenAI-API kompatibler Endpoint angegeben werden (OpenRouter, Groq, Fireworks, DeepSeek, lokales Ollama, OpenAI-kompatibles Gemini und andere) — über einen einzigen, gemeinsamen Codepfad, ohne separate Integration pro Anbieter. Konfiguration in der Datei `golden_key.env` (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `OPENAI_API_KEY`); die vollständige Anleitung befindet sich im Hauptmanual (SCHRITT 2B). Andere Modelle können eine niedrigere Qualität als Claude liefern, auf den die Prompts abgestimmt sind — dies ist eine bewusste Kosten-Qualitäts-Entscheidung seitens des Nutzers.


### Bekannte Einschränkungen von Modellen (Anti-Closure)

Trotz der Implementierung strenger Systemrichtlinien, die das Abbrechen von Aktionen in Spannungssituationen vorschreiben (sogenannte Anti-Closure-Richtlinie), besitzen moderne LLM-Modelle eine starke, angeborene Tendenz, Geschichten „abzuschließen". Dies führt häufig zur Einfügung unerwünschter Schlussfolgerungen, Moralbotschaften oder falscher „Happy Ends", insbesondere im Modus des traditionellen Hörbuchs.

Dies ist eine grundlegende Einschränkung der aktuellen Generation künstlicher Intelligenz. Aus diesem Grund speichert die Anwendung Projekte in einfachen, leicht editierbaren Textdateien (`.txt`). Dies erfordert vom Benutzer die Rolle eines lebendigen Editors zu übernehmen — das gelegentliche, manuelle Entfernen der letzten, von der KI generierten „abschließenden" Sätze, bevor die Datei erneut geladen und die Arbeit fortgesetzt wird.


## Installation und Inbetriebnahme

### Für Endbenutzer (Windows)

1. Laden Sie die neueste Version aus dem Bereich **Releases** herunter (das als *Latest* gekennzeichnete Paket) — Datei `Rezyser_Audio_v<numer>_Installer.exe`. Starten Sie sie mit einem Doppelklick. Das Installationsprogramm landet standardmäßig im lokalen Verzeichnis Ihres Kontos (`%LocalAppData%\Programs\Reżyser Audio GPT`) und erfordert keine Administratorrechte; Sie können über die Schaltfläche „Durchsuchen" einen eigenen Pfad wählen. Nach Abschluss werden Verknüpfungen im Startmenü und auf dem Desktop erstellt, und optional wird die Bedienungsanleitung im Standard-Editor für `.txt`-Dateien geöffnet.
2. **Anthropic-API-Konfiguration:** Beim ersten Start signalisiert die Anwendung das Fehlen des Schlüssels im Bereich „System Check". Klicken Sie auf die angezeigte Schaltfläche, um die Datei `golden_key.env` zu generieren, öffnen Sie sie in einem Texteditor und fügen Sie Ihren Anthropic-Schlüssel ein (der mit `sk-ant-` beginnt).
3. **Erste Schritte:** Öffnen Sie die Datei `docs/manual.pl.html` (oder in einer anderen Sprache) im Installationsordner — das ist die vollständige Bedienungsanleitung, verfasst in einer für jeden Benutzer verständlichen Sprache, nicht nur für Entwickler.


### Für Entwickler (Klonen + Einrichtung)

1. Klonen Sie das Repository auf Ihre Festplatte.
2. Führen Sie die Datei `setup_dev.bat` aus, um automatisch eine virtuelle Umgebung (`.venv/`) zu erstellen und die Abhängigkeiten aus `requirements.txt` herunterzuladen.
3. Starten Sie die Anwendung mit dem Befehl `python main.py` oder durch die Datei `run_dev.bat`.

Die `.sh`-Skripte für macOS/Linux wurden in v13.1 entfernt — die Entwicklungsumgebung konzentriert sich auf Windows aufgrund der Spezifik der NVDA-Zugänglichkeitstests. Die Arbeit mit dem Code auf anderen Systemen ist möglich, erfordert jedoch eine manuelle Einrichtung: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Skripte zum Erstellen von Release-Paketen** (`build_release.py`, `rezyser_audio.spec`, `installer.iss`) dienen ausschließlich zum Erstellen von Paketen für Windows. Ab Version 17.0 friert `build_release.py` die Anwendung mit PyInstaller ein (onedir + windowed) gemäß `rezyser_audio.spec` — es erzeugt `dist/` mit einer nativen `.exe` und einem Bundle-Ordner `runtime/` (Interpreter + Bibliotheken). Es ist kein tragbares Python mehr erforderlich, das manuell in das Repository geladen wird; die Verzeichnisse `dist/` und `build/` sind in `.gitignore`.


## Vollständige Dokumentation

Dieses README ist nur ein architektonischer Überblick über das Projekt. Um fortgeschrittene Techniken zur Vermeidung von KI-Halluzinationen, Installationsanweisungen für kompatible Sprachsynthesizer (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices), eine vollständige Beschreibung der Modi "Geschichten mit Fläschchen" sowie ein vollständiges Benutzerhandbuch kennenzulernen, konsultieren Sie die Dateien im Ordner `docs/`:

* `docs/manual.<iso>.html` — Hauptbenutzerhandbuch (für Endbenutzer geschrieben).
* `docs/tales.<iso>.html` — Handbuch für den Modus "Geschichten" (interaktive Textspiele).
* `docs/dictionaries.<iso>.html` — Anleitung für Linguisten ohne Python, wie man eigene Akzente/Verschlüsselungen/AI-Modi hinzufügt.

Jede dieser Dateien ist in 9 Sprachen verfügbar — Suffix `.<iso>.html` (z.B. `manual.pl.html`, `manual.en.html`, `manual.de.html`).


### Polnische Benennungen — Leitfaden für Personen außerhalb des polnischen Sprachraums

Die Hauptsprache dieses Projekts ist Polnisch. Die Namen der Module, Klassen, Kommentare im Code sowie die Namen der Verzeichnisse und Datendateien sind polnisch und werden — aus Gründen der Rückwärtskompatibilität und des Mehrsprachigkeits-Engines — bewusst NICHT übersetzt oder geändert. Das folgende Glossar hilft Entwicklern und Nutzern von macOS/Linux-Systemen, sich in der Struktur zurechtzufinden.

**Benutzerdatenverzeichnisse (neben der ausführbaren Datei oder im Projektverzeichnis):**

* `skrypty/` — *Skripte*: Projekte des Moduls Regisseur (`.txt` mit Erzählung, `.md` mit Weltbuch, `_streszczenie.txt`).
* `opowiesci/` — *Geschichten*: Aufzeichnungen interaktiver Geschichten.
* `runtime/` — doppelte Rolle: Verzeichnis des gebündelten, eingefrorenen Anwendungspakets (Interpreter + Bibliotheken) UND Container für versteckte Projektdaten (`runtime/skrypty/`, `runtime/opowiesci/`).

**Unterordner der Quelldaten in `dictionaries/<kod>/` (sichtbar im Regelmanager):**

* `podstawy.yaml` — *Grundlagen*: Konfiguration und Metadaten des Sprachpakets.
* `akcenty/` — *Akzente*: phonetische Regeln für Sprachsynthesizer.
* `szyfry/` — *Chiffren*: Textverschlüsselungsmodi.
* `rezyser/` — *Regisseur*: kreative Modi des Regisseur-Moduls.
* `opowiesci/` — *Geschichten*: Modi interaktiver Geschichten.
* `gui/` — Benutzeroberflächentexte (`ui.yaml`) und Dokumentationsvorlagen.


## Lizenz

Das Projekt wird unter der **MIT**-Lizenz bereitgestellt — der vollständige Text befindet sich in der Datei [`LICENSE`](LICENSE) im Hauptverzeichnis des Repositories. Kurz gesagt: Du kannst die Software frei verwenden, kopieren, modifizieren und verbreiten (auch kommerziell), vorausgesetzt, dass der Urheberrechtshinweis beibehalten wird. Die Software wird „wie besehen“ bereitgestellt, ohne jegliche Gewährleistung.
