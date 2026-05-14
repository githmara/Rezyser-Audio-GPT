# Audio GPT Regisseur

**Hybrides Aufnahmestudio für Hörspiele, Hörbücher und interaktive Geschichten**

**Andere Sprachversionen / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Ein tragbares Toolkit, das von KI angetrieben wird, um umfangreiche Skripte automatisch zu schreiben, zu planen, zu formatieren und zu übersetzen sowie interaktive Textspiele zu führen. Das Projekt ist eine native Desktop-Anwendung (wxPython), die von Grund auf für vollständige Zugänglichkeit mit Bildschirmlesern (NVDA, VoiceOver) und die Zusammenarbeit mit professionellen Sprachsynthesizern (TTS) entwickelt wurde. Es funktioniert ohne Browser und ohne lokalen Server — es startet als normales Programmfenster.

Version: **15.2.1** · Unterstützte Sprachen nativ (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Hauptmodule

Die Anwendung vereint in einem Fenster fünf Werkzeuge, die über Tastenkombinationen (Strg+1 / Strg+2 / Strg+3 / Strg+4 / Strg+5) oder Schaltflächen in der Symbolleiste umgeschaltet werden können. Jedes Modul funktioniert unabhängig, aber alle teilen sich die Wörterbuchpakete aus dem Ordner `dictionaries/` (Akzente, Chiffren, kreative AI-Modi) und zentrale Einstellungen.


### 1. Regie (Ctrl+1)

Das Hauptstudio zum Schreiben von Hörspielen und Hörbüchern. Du wählst einen Modus — Brainstorming, Skript (mit Tags `[SFX]`/`[Charakter: Emotion]`), Hörbuch (traditionelle Prosa) — und leitest den Dialog mit dem Modell durch das Instruktionsfeld + Weltbuch + Langzeitspeicher:

* **Multiprojekt-Weltbuch:** Das System lädt automatisch im Hintergrund die dedizierten Universumsregeln (`.md`) basierend auf der aktiven Quelldatei, um vollständige Isolation zu gewährleisten (Zero-Click-Kontextladen).
* **Handlungsakku:** Der Algorithmus des „unendlichen Gedächtnisses". Wenn der Speicherzeiger in den roten Alarmzustand wechselt, generiert das System automatisch eine Handlungszusammenfassung und speichert sie im Langzeitspeicherfeld.
* **4 kreative Modi:** Jede der Dateien in `dictionaries/<jzk>/rezyser/` beschreibt eine separate „Persönlichkeit" des KI-Regisseurs (Brainstorming, Skript, Hörbuch, Titel-Nachbearbeitung). Du kannst ihren Klang ohne Programmierung anpassen — siehe Regelmanager unten.


### 2. Erzählungen (Strg+2, zweiter Hauptmodus ab v15.0)

Interaktive Textspiele, die von KI als Erzählmotor geführt werden. Im Gegensatz zur Regie (wo du ein fertiges Hörbuch generierst), sind Erzählungen eine rundenbasierte dynamische Handlung:

* **Wahlmodus:** Jede Runde endet mit 3-5 nummerierten Optionen A-E. Der intuitivste Modus für blinde Spieler — NVDA liest die Optionen vor, du klickst Tab und Enter.
* **Modus Kleineres Übel:** Wie Wahlmodus, aber jede Option ist moralisch, physisch oder strategisch nachteilig. Ab v15.2 gibt es eine zusätzliche „Phiole" — eine wiederverwendbare, NULL-nummerierte Option der verzweifelten Rettung, deren Effekte pseudolos sind (60% schädlich / 30% Wahrnehmungsstörung / 10% selten-vorteilhaft, Verteilung erzwungen durch Python, LLM kann keinen rettenden Effekt erfinden).
* **Freier Modus:** Beliebige Aktion im freien Text („Ich versuche, die Tür zu öffnen"), der Motor schlägt 1-3 Vorschläge vor, erzwingt aber keine Wahl.
* **KI-Modell pro Modus:** Wahlmodus und Kleineres Übel verwenden gpt-4o (besseres moralisches Verständnis), Freier Modus verwendet gpt-4o-mini (kostengünstigere Improvisationsökonomie).


### 3. Polyglott (Ctrl+3, AI-Übersetzer + TTS-Akzente)

* **Sicherer Übersetzer:** Lange Texte werden automatisch in Blöcke von bis zu 10.000 Zeichen aufgeteilt und sequenziell übersetzt. Jeder Block wird sofort in einer versteckten `.jsonl`-Datei gespeichert. Die Wiederaufnahme nach Erschöpfung der API-Limits erfolgt vollautomatisch.
* **NVDA-Automatisierung:** Übersetzungen werden als fertige `.html`-Dateien mit eingebettetem Sprach-Tag oder `.docx`-Dateien mit direkt in die XML-Struktur injizierten Tags gespeichert.
* **8 lokale Akzente:** Möglichkeit, absichtlich einen gebrochenen Akzent für lokale Synthesizer (Tiflotecnia Voices, eSpeak, OneCore) durch fortgeschrittene Regex-Regeln zu erzwingen. Unterstützte fremdsprachige Akzente: Englisch, Russisch (mit Transliteration in Kyrillisch), Französisch, Spanisch, Italienisch, Finnisch, Isländisch, Polnisch.
* **Verschlüsselungsmodus:** 6 lokale Algorithmen zur Textverzerrung — von Rückwärtslesen über Typoglycämie bis hin zur klassischen Cäsar-Verschlüsselung. Jeder mit lokalem Alphabet des Sprachpakets (z.B. Cäsar-Verschlüsselung mit 35-Zeichen-Alphabet DE mit Diakritika).
* **Tag-Reparatur:** Injektiert nicht-invasiv den angegebenen zweibuchstabigen ISO-Sprachcode in bestehende Dateien.


### 4. Konverter / Audiobook-Architekt (Ctrl+4)

* Verarbeitet rohe `.txt`- oder `.docx`-Dateien für die Tastaturnavigation mit NVDA und Systemen wie ElevenLabs.
* Konvertiert automatisch Schlüsselwörter (Akt, Kapitel, Prolog) in „Heading 1"-Überschriften im Word-Dokument und bereinigt unnötige HTML-Tags und Markdown-Markierungen.
* Ab Version 15.1 Gruppierung von 5 Runden in Szenen mit H1-Überschriften (automatische Erkennung der Erzählung) — bereitet die im Erzählmodus generierte Datei für die traditionelle Audiobuchveröffentlichung vor.


### 5. Regel-Manager (Ctrl+5, neu ab v13.0)

* **Wörterbuch-Explorer ohne Python:** Visueller Baum aller YAML-Dateien im Ordner `dictionaries/` — phonetische Akzente, Chiffren, kreative Modi des Regisseurs und der Erzählungen. Ein Linguist oder Übersetzer kann Regeln direkt aus der GUI durchsuchen, duplizieren, bearbeiten und löschen.
* **Ersteller neuer Regeln:** Formular mit Typauswahl (Akzent, reine Austausch-Chiffre, Regisseur-Modus, neue Basissprache, algorithmische Chiffre), das eine fertige YAML-Vorlage erstellt, und für schwierigere Fälle einen formatierten Prompt zur Einfügung in ChatGPT / Claude generiert.
* **Refaktor v13.0 — Regeln in YAMLs:** Alle Akzente, Chiffren und AI-Modi, die bis Version 12.0 als „eingebettete“ Konstanten im Python-Code existierten, wurden in deklarative `.yaml`-Dateien verschoben, die beim Start der Anwendung dynamisch geladen werden. Jeder, der einen Texteditor bedienen kann, kann einen Akzent anpassen (z.B. `sz → sh` in `sz → sch` ändern), eine neue Sprache hinzufügen oder sogar den Klang des systemischen Prompts für die AI ändern — ohne den Code zu kompilieren.


## Mehrsprachigkeit (9 Sprachen nativ)

Ab Version 14.0 unterstützt die Anwendung nativ 9 Basissprachen: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Jedes Paket `dictionaries/<code>/` enthält Diakritika, Alphabet und phonetische Regeln, die auf Text in dieser spezifischen Sprache operieren — die Anwendung erkennt die Quellsprache automatisch durch den lingua-language-detector (pro Absatz) und lädt das entsprechende Paket für jeden Abschnitt separat.

Die gesamte GUI, die Dokumentation (`docs/manual.<iso>.txt`) und die meisten Systemmeldungen sind nativ in jeder der unterstützten Sprachen verfügbar. Die AI-Systemaufforderungen im Regisseur- und Erzählmodus sind in den Zielsprache verfasst (manuell, nicht automatisch übersetzt — siehe `dictionaries/<code>/rezyser/` und `dictionaries/<code>/opowiesci/`).


## Architektur der KI und verwendete Modelle

Die Anwendung verteilt Aufgaben intelligent, um die Kosten und die Geschwindigkeit der OpenAI-API zu optimieren:

* **gpt-4o:** Der Hauptmotor der Anwendung. Verantwortlich für anspruchsvolle generative Aufgaben: Regie von Skripten, Schreiben traditioneller Prosa (Hörbuch), Modi der Entscheidungen und des kleineren Übels in Geschichten, Generierung von Zusammenfassungen sowie fortgeschrittene Übersetzungen unter Beibehaltung des mehrblockigen Kontexts.
* **gpt-4o-mini:** Schnelles, leichtes Hilfsmodell. Wird im Hintergrund für Mikroaufgaben verwendet, die hohe Geschwindigkeit erfordern: iteratives Vergeben literarischer Titel an generierte Kapitel, Extraktion von ISO-Codes, Freier Modus in Geschichten (günstigere Ökonomie der Improvisation von freiem Text).


### Bekannte Einschränkungen von Modellen (Anti-Closure)

Trotz der Implementierung strenger Systemrichtlinien, die das Abbrechen von Aktionen in Spannungssituationen vorschreiben (sogenannte Anti-Closure-Richtlinie), besitzen moderne LLM-Modelle eine starke, angeborene Tendenz, Geschichten „abzuschließen". Dies führt häufig zur Einfügung unerwünschter Schlussfolgerungen, Moralbotschaften oder falscher „Happy Ends", insbesondere im Modus des traditionellen Hörbuchs.

Dies ist eine grundlegende Einschränkung der aktuellen Generation künstlicher Intelligenz. Aus diesem Grund speichert die Anwendung Projekte in einfachen, leicht editierbaren Textdateien (`.txt`). Dies erfordert vom Benutzer die Rolle eines lebendigen Editors zu übernehmen — das gelegentliche, manuelle Entfernen der letzten, von der KI generierten „abschließenden" Sätze, bevor die Datei erneut geladen und die Arbeit fortgesetzt wird.


## Installation und Start

### Für Endbenutzer (Windows)

1. Laden Sie die neueste Version aus dem **Releases**-Tab herunter (Paket mit der Bezeichnung *Latest*). Es stehen zwei Formen zur Verfügung:
   * **Installer EXE** — installiert in Program Files (oder einem ausgewählten Ordner), erstellt Verknüpfungen im Startmenü und auf dem Desktop. Nach Abschluss der Installation wird optional die Bedienungsanleitung im Standard-Handler für .txt-Dateien geöffnet.
   * **Portable ZIP** — entpacken Sie es in einen beliebigen Ordner, keine Administratorrechte erforderlich. Nach dem Entpacken führen Sie `run.bat` aus.
2. **OpenAI API-Konfiguration:** Beim ersten Start signalisiert die Anwendung das Fehlen eines Schlüssels im Abschnitt System Check. Klicken Sie auf die sichtbare Schaltfläche, um die Datei `golden_key.env` zu generieren, öffnen Sie sie in einem Texteditor und fügen Sie Ihren Schlüssel ein (beginnend mit `sk-proj-`).
3. **Erste Schritte:** Öffnen Sie die Datei `docs/manual.pl.txt` (oder in einer anderen Sprache) im Installationsordner — dies ist eine vollständige Bedienungsanleitung, die in einer Sprache verfasst ist, die für jeden Benutzer zugänglich ist, nicht nur für Entwickler.


### Für Entwickler (Klonen + Setup)

1. Klonen Sie das Repository auf Ihre Festplatte.
2. Führen Sie die Datei `setup_dev.bat` aus, um automatisch eine virtuelle Umgebung (`.venv/`) zu erstellen und die Abhängigkeiten aus `requirements.txt` herunterzuladen.
3. Starten Sie die Anwendung mit dem Befehl `python main.py` oder über die Datei `run_dev.bat`.

Die `.sh`-Skripte für macOS/Linux wurden in v13.1 entfernt — die Entwicklungsumgebung ist auf Windows konzentriert aufgrund der Spezifik der NVDA-Zugänglichkeitstests. Die Arbeit mit dem Code auf anderen Systemen ist möglich, erfordert jedoch ein manuelles Setup: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Skripte zum Erstellen von Release-Paketen** (`build_release.py`, `installer.iss`) dienen ausschließlich zur Erstellung von Paketen für Windows. Sie erfordern einen speziellen `runtime/`-Ordner mit einer portablen Version von Python — dieser Ordner ist absichtlich nicht Teil des Repositories (ist in `.gitignore`).


## Vollständige Dokumentation

Dieses README ist nur ein architektonischer Überblick über das Projekt. Um fortgeschrittene Techniken zur Vermeidung von KI-Halluzinationen, Installationsanweisungen für kompatible Sprachsynthesizer (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices), eine vollständige Beschreibung der Modi "Geschichten mit Fläschchen" sowie ein vollständiges Benutzerhandbuch kennenzulernen, konsultieren Sie die Dateien im Ordner `docs/`:

* `docs/manual.<iso>.txt` — Hauptbenutzerhandbuch (für Endbenutzer geschrieben).
* `docs/tales.<iso>.txt` — Handbuch für den Modus "Geschichten" (interaktive Textspiele).
* `docs/dictionaries.<iso>.txt` — Anleitung für Linguisten ohne Python, wie man eigene Akzente/Verschlüsselungen/AI-Modi hinzufügt.

Jede dieser Dateien ist in 9 Sprachen verfügbar — Suffix `.<iso>.txt` (z.B. `manual.pl.txt`, `manual.en.txt`, `manual.de.txt`).
