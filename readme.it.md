# Reżyser Audio GPT

**Studio di Registrazione Ibrido per Radiodrammi, Audiolibri e Racconti Interattivi**

**Altre versioni linguistiche / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Strumenti autonomi alimentati da AI per la scrittura automatica, pianificazione, formattazione e traduzione di script estesi, oltre alla conduzione di giochi di testo interattivi. Il progetto è un'applicazione desktop nativa (wxPython) progettata da zero per garantire piena accessibilità ai lettori di schermo (NVDA, VoiceOver) e compatibilità con sintetizzatori vocali professionali (TTS). Funziona senza browser e senza server locale — si avvia come una normale finestra di programma.

Versione: **18.16.0** · Lingue supportate nativamente (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Moduli principali

L'applicazione combina in una finestra cinque strumenti commutabili tramite scorciatoie da tastiera (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 / Ctrl+5) o pulsanti sulla barra degli strumenti. Ogni modulo funziona in modo indipendente, ma tutti condividono i pacchetti di dizionari dalla cartella `dictionaries/` (accenti, cifrari, modalità creative AI) e impostazioni centrali.


### 1. Regia (Ctrl+1)

Studio principale per scrivere radiodrammi e audiolibri. Scegli la modalità — Brainstorming, Script (con tag `[SFX]`/`[Personaggio: emozione]`), Audiolibro (prosa tradizionale) — e dirigi il dialogo con il modello attraverso il campo Istruzioni + Libro del Mondo + Memoria a Lungo Termine:

* **Libro del Mondo Multiprogetto:** Il sistema carica automaticamente in background le regole dedicate dell'universo (`.md`) basate sul file sorgente attivo, garantendo un'isolamento completo (caricamento del contesto senza clic).
* **Accumulatore di Trama:** Algoritmo di "memoria infinita". Il riassunto della trama lo genera uno strumento di postproduzione a sé (dalla v18.13) e, quando l'indicatore di memoria entra in stato di allarme rosso, il sistema lo avvia da solo e salva il risultato sia nel file sia nel campo Memoria a Lungo Termine. I riassunti successivi sono incrementali: il modello riceve la memoria precedente e solo la parte nuova della narrazione.
* **6 modalità creative:** Ogni file in `dictionaries/<jzk>/rezyser/` descrive una diversa "personalità" del regista AI (Brainstorming, Script, Audiolibro) oppure uno strumento di postproduzione (Titoli dei Capitoli, Memoria a Lungo Termine). Puoi regolare il loro tono senza programmazione — vedi Gestore Regole di seguito.


### 2. Racconti (Ctrl+5, secondo modo principale dalla v15.0)

Giochi testuali interattivi condotti dall'IA nel ruolo di motore narrativo. A differenza della Regia (dove generi un audiolibro pronto), i Racconti sono una trama dinamica turno-per-turno:

* **Modalità Scelte:** ogni turno si conclude con 3-5 opzioni numerate A-E. La modalità più intuitiva per i giocatori non vedenti — NVDA legge le opzioni, premi Tab ed Enter.
* **Modalità Male Minore:** come Scelte, ma ogni opzione è sfavorevole moralmente, fisicamente o strategicamente. Dalla v15.2 è stata aggiunta la "fiala" — un'opzione riutilizzabile numerata ZERO di salvezza disperata, i cui effetti sono pseudocasuali (60% dannosi / 30% alteranti la percezione / 10% raramente favorevoli, distribuzione imposta da Python, l'LLM non ha modo di inventare un esito salvifico).
* **Modalità Libera:** qualsiasi azione in testo libero ("provo ad aprire la porta"), il motore propone 1-3 suggerimenti ma non impone una scelta.
* **Un unico modello IA per tutte le modalità:** dalla v18.1 tutte le modalità di Racconti utilizzano lo stesso modello condiviso (predefinito e consigliato Anthropic Claude Sonnet 5) — un modello più potente si attiene rigorosamente alle regole del mondo (particolarmente cruciale nella modalità Male Minore, dove ogni opzione deve essere realmente sfavorevole).


### 3. Poliglotta (Ctrl+2, Traduttore AI + Accenti TTS)

* **Traduttore Sicuro:** I testi lunghi vengono automaticamente suddivisi in blocchi misurati in token del modello (sicuro anche per lingue a scrittura densa, ad es. il cinese) e tradotti sequenzialmente; una risposta troncata del modello viene rilevata e ritentata su frammenti più piccoli. Ogni blocco viene immediatamente salvato in un file nascosto `.jsonl`. Il ripristino dopo l'esaurimento dei limiti API è completamente automatico.
* **Automazione NVDA:** Le traduzioni vengono salvate come file `.html` pronti con tag di lingua incorporato o file `.docx` con tag iniettati direttamente nella struttura XML.
* **8 accenti locali:** Possibilità di forzare intenzionalmente un accento spezzato per i sintetizzatori locali (Tiflotecnia Voices, eSpeak, OneCore) grazie a regole regex avanzate. Accenti stranieri supportati: inglese, russo (con traslitterazione in cirillico), francese, tedesco, spagnolo, polacco, finlandese, islandese.
* **Modalità Cifrario:** 6 algoritmi locali di distorsione del testo — dalla lettura al contrario, attraverso la tipoglicemia, fino al classico cifrario di Cesare. Ognuno con l'alfabeto locale del pacchetto linguistico (ad esempio, cifrario di Cesare su alfabeto IT di 21 caratteri).
* **Riparatore di Tag:** Inietta in modo non invasivo il codice ISO della lingua fornito — anche regionale, ad es. pt-BR o zh-CN — nei file esistenti.


### 4. Convertitore / Architetto Audiolibri (Ctrl+3)

* Elabora file `.txt` o `.docx` grezzi per la navigazione tramite tastiera per NVDA e sistemi come ElevenLabs.
* Converte automaticamente le parole chiave (Atto, Capitolo, Prologo) in intestazioni "Heading 1" nel documento Word e pulisce i tag HTML superflui e i marcatori Markdown.
* Dalla versione 15.1 raggruppa 5 turni in scene con intestazioni H1 (rilevamento automatico dei Racconti) — prepara il file generato dalla modalità Racconti per la pubblicazione tradizionale di audiolibri.


### 5. Gestore Regole (Ctrl+4, novità dalla v13.0)

* **Esploratore di dizionari senza Python:** Albero visivo di tutti i file YAML nella cartella `dictionaries/` — accenti fonetici, cifrari, modalità creative del Regista e Racconti. Un linguista o traduttore può visualizzare, duplicare, modificare e eliminare regole direttamente dall'interfaccia grafica.
* **Creatore di nuove regole:** Modulo con selezione del tipo (accento, cifrario di sostituzioni pure, modalità del Regista, nuova lingua di base, cifrario algoritmico) che crea un modello YAML pronto all'uso e, per i casi più complessi, genera un prompt formattato da incollare in ChatGPT / Claude.
* **Refactoring v13.0 — regole nei YAML:** Tutti gli accenti, i cifrari e le modalità AI, che fino alla versione 12.0 erano "incorporati" come costanti nel codice Python, sono stati trasferiti in file `.yaml` dichiarativi caricati dinamicamente all'avvio dell'applicazione. Chiunque sappia usare un editor di testo può regolare un accento (ad esempio, cambiare `sz → sh` in `sz → sch`), aggiungere una nuova lingua o persino modificare il tono del prompt di sistema per l'AI — senza compilare il codice.


## Multilinguismo (9 lingue nativamente)

Dalla versione v14.0 l'applicazione supporta nativamente 9 lingue di base: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Ogni pacchetto `dictionaries/<kod>/` contiene diacritici, alfabeto e regole fonetiche che operano sul testo in quella specifica lingua — l'applicazione rileva automaticamente la lingua di origine tramite lingua-language-detector (per paragrafo) e carica il pacchetto appropriato per ogni frammento separatamente.

L'interfaccia GUI, la documentazione (`docs/manual.<iso>.html`) e la maggior parte dei messaggi di sistema sono disponibili nativamente in ciascuna delle lingue supportate. I prompt di sistema AI nelle modalità Regista e Racconti sono scritti nelle lingue di destinazione (manualmente, non auto-tradotti — vedi `dictionaries/<kod>/rezyser/` e `dictionaries/<kod>/opowiesci/`).


## Architettura AI e modelli utilizzati

Il provider AI consigliato e predefinito è Anthropic (Claude) — tutti i prompt di sistema sono calibrati su di esso, quindi è lui a garantire la massima qualità narrativa, la migliore aderenza alle regole del mondo narrativo e la prosa più naturale. Il consolidamento su Claude è avvenuto per fasi (Regista nella v18.0, Racconti nella v18.1, Poliglotta e post-produzione nella v18.2) — frutto di un vantaggio empiricamente confermato nell'aderenza alle regole del mondo narrativo, nella naturalezza della prosa e nell'evitare i cliché.

* **Anthropic Claude Sonnet 5 (pilastro predefinito della qualità):** Il motore di TUTTA l'intelligenza dell'applicazione. È responsabile della narrazione creativa (la regia degli script, la scrittura della prosa tradizionale dell'Audiolibro, il Brainstorming e TUTTE le modalità Racconti — Scelte, Male Minore, Libero — insieme alla generazione dei riepiloghi e degli intermezzi Cinematic), delle traduzioni avanzate con mantenimento del contesto multi-blocco (Poliglotta), oltre a micro-task quali: l'assegnazione iterativa di titoli letterari ai capitoli e il rilevamento del codice della lingua del contenuto.

* **Endpoint personalizzato compatibile con OpenAI (opzione avanzata, dalla v18.4):** Al posto di Anthropic è possibile indicare un qualsiasi endpoint compatibile con l'API OpenAI (OpenRouter, Groq, Fireworks, DeepSeek, Ollama locale, Gemini compatibile con OpenAI e altri) — attraverso un unico percorso di codice condiviso, senza integrazione separata per ciascun provider. Configurazione nel file `golden_key.env` (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `OPENAI_API_KEY`); le istruzioni complete si trovano nel manuale principale (PASSO 2B). Altri modelli possono offrire una qualità inferiore rispetto a Claude, su cui sono calibrati i prompt — si tratta di una scelta consapevole costo↔qualità da parte dell'utente.


### Limitazioni conosciute dei modelli (Anti-Closure)

Nonostante l'implementazione di rigorose direttive di sistema che impongono di interrompere l'azione nei momenti di tensione (cosiddetta direttiva Anti-Closure), i modelli LLM contemporanei possiedono una forte tendenza innata a "chiudere" le storie. Ciò si traduce in frequenti inserimenti di conclusioni indesiderate, morali o falsi "happy end", specialmente in Modalità Audiolibro Tradizionale.

Questa è una limitazione fondamentale dell'attuale generazione di intelligenza artificiale. Per questo motivo, l'applicazione salva i progetti in normali file di testo facili da modificare (`.txt`). Ciò richiede all'utente di assumere il ruolo di montatore umano — rimuovendo occasionalmente e manualmente le frasi "conclusive" generate dall'IA, poi sincronizzando la memoria con il file corretto tramite il pulsante "Aggiorna dal disco", e continuando il lavoro.


## Installazione e avvio

### Per gli utenti finali (Windows)

1. Scarica l'ultima versione dalla scheda **Releases** (pacchetto contrassegnato come *Latest*) — file `Rezyser_Audio_v<numer>_Installer.exe`. Avvialo con un doppio clic. Il programma di installazione si posiziona per impostazione predefinita nella directory locale del tuo account (`%LocalAppData%\Programs\Reżyser Audio GPT`) e non richiede diritti di amministratore; puoi scegliere un percorso personalizzato tramite il pulsante "Sfoglia". Al termine crea collegamenti nel Menu Start e sul desktop, e facoltativamente apre il manuale d'uso nell'editor predefinito per i file `.txt`.
2. **Configurazione API Anthropic:** Al primo avvio, l'applicazione segnalerà l'assenza della chiave nella sezione System Check. Fai clic sul pulsante visualizzato per generare il file `golden_key.env`, aprilo in un editor di testo e incolla la tua chiave Anthropic (che inizia con `sk-ant-`).
3. **Primi passi:** Apri il file `docs/manual.pl.html` (o in un'altra lingua) nella cartella di installazione — è il manuale d'uso completo, scritto in un linguaggio accessibile a ogni utente, non solo agli sviluppatori.


### Per sviluppatori (clone + setup)

1. Clona il repository sul tuo disco.
2. Esegui il file `setup_dev.bat` per creare automaticamente un ambiente virtuale (`.venv/`) e scaricare le dipendenze da `requirements.txt`.
3. Avvia l'applicazione con il comando `python main.py` o tramite il file `run_dev.bat`.

Gli script `.sh` per macOS/Linux sono stati rimossi nella v13.1 — l'ambiente di sviluppo è concentrato su Windows a causa delle specifiche dei test di accessibilità NVDA. È possibile lavorare con il codice su altri sistemi, ma richiede un setup manuale: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Gli script per costruire i pacchetti di rilascio** (`build_release.py`, `rezyser_audio.spec`, `installer.iss`) sono utilizzati esclusivamente per creare pacchetti per Windows. Dalla versione 17.0 `build_release.py` congela l'applicazione con PyInstaller (onedir + windowed) secondo `rezyser_audio.spec` — produce `dist/` con un `.exe` nativo e una cartella bundle `runtime/` (interprete + librerie). Non è più necessario alcun Python portatile caricato manualmente nel repository; le directory `dist/` e `build/` sono in `.gitignore`.


## Documentazione completa

Questo README è solo un contorno architettonico del progetto. Per conoscere le tecniche avanzate per prevenire le allucinazioni dell'IA, le istruzioni per l'installazione di sintetizzatori vocali compatibili (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices), la descrizione completa delle modalità Racconti con la fiala e il manuale completo dell'utente, consulta i file nella cartella `docs/`:

* `docs/manual.<iso>.html` — manuale principale dell'utente (scritto per l'utente finale).
* `docs/tales.<iso>.html` — manuale della modalità Racconti (giochi di testo interattivi).
* `docs/dictionaries.<iso>.html` — istruzioni per linguisti senza Python su come aggiungere accenti/cifrari/modalità AI personalizzati.

Ognuno di questi file è disponibile in 9 lingue — suffisso `.<iso>.html` (ad es. `manual.pl.html`, `manual.en.html`, `manual.de.html`).


### Guida alla nomenclatura polacca — per chi non parla polacco

La lingua principale di questo progetto è il polacco. I nomi dei moduli, delle classi, i commenti nel codice, così come i nomi delle cartelle e dei file di dati sono in polacco e — per garantire la retrocompatibilità e il contratto del motore multilingue — NON vengono tradotti né modificati intenzionalmente. Il seguente glossario aiuterà gli sviluppatori e gli utenti dei sistemi macOS/Linux a orientarsi nella struttura.

**Cartelle dati utente (accanto al file eseguibile o nella cartella del progetto):**

* `skrypty/` — *scripts*: progetti del modulo Regista (`.txt` con narrazione, `.md` con il Libro del Mondo, `_streszczenie.txt`).
* `opowiesci/` — *stories*: registrazioni di Racconti interattivi.
* `runtime/` — doppio ruolo: cartella del bundle dell'applicazione congelata (interprete + librerie) E contenitore di metadati nascosti dei progetti (`runtime/skrypty/`, `runtime/opowiesci/`).

**Sottocartelle dei dati sorgente in `dictionaries/<codice-lingua>/` (visibili nel Gestore Regole):**

* `podstawy.yaml` — *basics*: configurazione e metadati del pacchetto linguistico.
* `akcenty/` — *accents*: regole fonetiche per i sintetizzatori vocali.
* `szyfry/` — *ciphers*: modalità di cifratura del testo.
* `rezyser/` — *director*: modalità creative del modulo Regista.
* `opowiesci/` — *stories*: modalità di Racconti interattivi.
* `gui/` — testi dell'interfaccia (`ui.yaml`) e modelli di documentazione.


## Licenza

Il progetto è distribuito sotto la licenza **MIT** — il testo completo si trova nel file [`LICENSE`](LICENSE) nella directory principale del repository. In sintesi: puoi utilizzare, copiare, modificare e distribuire liberamente il software (anche a fini commerciali), a condizione di mantenere l'avviso di copyright. Il software è fornito "così com'è", senza alcuna garanzia.
