Ciao, e prima di tutto: mi dispiace sinceramente per la perdita di sei mesi del tuo lavoro. Trenta regole regex per file × due file, accumulate gradualmente durante l'uso quotidiano con Alice (Vocalizer) per i tuoi audiolibri, non sono qualcosa che si ricrea in un pomeriggio — sono il risultato di mesi di ascolto, regolazioni fini, ritocchi dopo ogni nuovo libro. Capisco che la perdita di quei file fa molto male.

## Cosa è cambiato in v15.2.8 — la lacuna UX che ha causato il tuo incidente

La tua segnalazione ha esposto una lacuna concreta nell'esperienza utente che era sfuggita a tutti i nostri smoke-test precedenti (otto lingue, cinque release patch nell'ultimo mese). Da v15.2.8 il dialogo che propone l'aggiornamento NON è più un semplice `wx.MessageBox` con due pulsanti Sì/No — è una finestra di dialogo con tre pulsanti:

- **Scarica e installa** (default, focus iniziale — premi Invio per accettare)
- **Apri cartella dictionaries** — apre Esplora risorse direttamente sulla cartella dell'installazione, SENZA chiudere il dialogo
- **Annulla**

Nel testo del dialogo, prima della domanda finale „Vuoi scaricare e installare?", c'è ora un paragrafo ATTENZIONE inline che spiega esplicitamente: se hai personalizzato file in `dictionaries/` tramite il Gestore delle Regole, il programma di installazione li sovrascriverà con le versioni predefinite. Fai un backup PRIMA di confermare — clicca „Apri cartella dictionaries", copia l'intera cartella in un luogo sicuro, poi torna al dialogo e clicca „Scarica e installa".

Questo elimina il problema che hai descritto: l'avvertimento nel manuale v15.2.5+ era corretto, ma TU stavi leggendo il vecchio manuale v15.2.4 nel momento della decisione (perché il manuale si aggiorna insieme al software, quindi PRIMA dell'aggiornamento è sempre visibile la versione vecchia). Da v15.2.8 l'informazione critica è nel dialogo stesso, indipendentemente da quale versione del manuale stai leggendo in quel momento.

## Recovery — alcune cose da provare prima di rassegnarti

Il fatto che tu abbia trovato una versione cache nel cestino è già una buona notizia. Ecco una checklist in ordine di probabilità di successo:

1. **Cestino di Windows (`$Recycle.Bin`)**: hai già scoperto questa traccia — esplora a fondo. Apri Esplora risorse, mostra elementi nascosti (Visualizza → Mostra → Elementi nascosti), naviga su `C:\$Recycle.Bin\<tuo SID>\` e cerca i file `.yaml` o file con nomi simili a `polski` / `niemiecki`. Windows rinomina i file eliminati con prefissi tipo `$R...` — apri qualsiasi `.yaml` con il Blocco note per verificarne il contenuto. Se trovi i tuoi file, copiali fuori dal cestino prima di ripristinarli (alcuni antivirus bloccano l'estrazione diretta dal `$Recycle.Bin`).

2. **Ricerca di Windows**: apri il menu Start, digita `polski.yaml` (e separatamente `niemiecki.yaml`). Windows Search indicizza anche file fuori dalle cartelle utente predefinite — può rivelare copie cache che Windows ha creato in `%LocalAppData%\Microsoft\Windows\INetCache\` o in cartelle temporanee di antivirus / backup tools.

3. **Cronologia file / Punti di ripristino**: apri Pannello di controllo → Sistema → Protezione del sistema. Se hai i punti di ripristino attivi, fai clic destro sulla cartella dell'installazione di Reżyser Audio AI e scegli „Ripristina versioni precedenti". Potresti trovare uno snapshot pre-aggiornamento con i tuoi file. Anche se i punti di ripristino non erano attivi, Windows a volte crea Shadow Copy implicite — verifica in PowerShell come amministratore: `vssadmin list shadows`.

4. **OneDrive / Google Drive / Dropbox**: se la cartella dell'installazione di Reżyser Audio AI era (anche indirettamente) sincronizzata con uno di questi servizi cloud, controlla la cronologia delle versioni nel pannello web del servizio. OneDrive in particolare conserva 30 giorni di cronologia per file modificati anche se non li hai sincronizzati esplicitamente.

5. **Recuva o PhotoRec** (last resort, software gratuito di terze parti): se nessun metodo sopra funziona, questi strumenti scansionano il disco a livello di settori e possono recuperare file eliminati la cui voce nel filesystem è stata cancellata ma i blocchi dati sono ancora intatti. Funzionano meglio se NON hai fatto molte scritture sul disco dopo l'aggiornamento — quindi prova prima i metodi sopra, poi questo come ultima opzione.

Se nessuno di questi metodi funziona, almeno avrai una checklist ordinata da seguire la prossima volta che qualcosa simile capita a un altro utente — la prossima volta sarà preventiva grazie al nuovo dialogo v15.2.8.

## P.S. — perché non abbiamo implementato il controllo mtime che hai suggerito

La tua proposta in P.S. (un flag in `core_updater.py` che confronta mtime dei file in `dictionaries/*/akcenty/*.yaml` con la data di installazione e mostra un avvertimento aggiuntivo se rileva modifiche) era logica, ma dopo l'analisi non è entrata in v15.2.8 per tre motivi:

1. **Falsi positivi**: apri `polski.yaml` nel Blocco note, premi Ctrl+S per abitudine senza cambiare nulla → mtime aggiornato → il dialogo grida „MODIFICHE RILEVATE!" anche se non c'è nulla. Ogni falso allarme insegna l'utente a ignorare gli avvertimenti (boy crying wolf).

2. **Falsi negativi con scrittura atomica**: il Gestore delle Regole salva i file YAML atomicamente (write su `*.tmp` → `rename(*.tmp, *.yaml)`). A seconda del filesystem e delle hook di sicurezza (Defender, antivirus), mtime del nuovo file può ereditare il timestamp originale invece di aggiornarsi — quindi nessun avvertimento nonostante modifiche reali.

3. **mtime non distingue user-data da seed-data**: i file nel pacchetto installer ereditano un mtime sintetico al momento dell'unpack (Inno Setup usa il tempo corrente di default). Una installazione fresca ha tutti i file con mtime identico, ma per l'euristica sembra „intera cartella modificata 1 secondo fa".

L'avvertimento statico nel testo del dialogo (sempre visibile, indipendente dallo stato dei file) è una base più solida dell'euristica che può introdurre rumore.

Il refactor completo (separazione strutturale user-data vs seed-data per `dictionaries/`, con meccanismo first-launch che copia seed → user-data al primo avvio e ignora seed durante l'upgrade se user-data esiste già) rimane nella roadmap v15.3+. Quello eliminerà strutturalmente il problema (user-data fuori dal percorso dell'installer, impossibile da sovrascrivere). v15.2.8 è la patch UX che protegge gli utenti fino al refactor.

## Grazie per la segnalazione

Sei stato il nono e ultimo smoke-test del flusso „Da Sud a Nord" implementato in v15.2.4 — l'italiano era l'ultima lingua su cui non avevamo ancora ricevuto una segnalazione reale. Senza la tua segnalazione il nuovo dialogo v15.2.8 non sarebbe esistito, e altri utenti italiani / di altre lingue avrebbero perso anche loro le proprie regole. Concretamente: ogni persona che eviterà la stessa perdita in futuro sarà debitrice a te.

In bocca al lupo con il recovery. E un grazie sentito per il pazienza con cui hai descritto l'incidente — la diagnosi dettagliata (cronologia esatta, riferimenti al manuale, P.S. con la proposta tecnica) ha reso la nostra risposta molto più veloce e mirata.
