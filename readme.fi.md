# Reżyser Audio GPT

**Hybrid Studioäänityötila kuunnelmille, äänikirjoille ja interaktiivisille tarinoille**

**Muut kieliversiot / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Zestaw przenośnych narzędzi napędzanych przez AI do automatycznego pisania, planowania, formatowania i tłumaczenia obszernych skryptów oraz prowadzenia interaktywnych gier tekstowych. Projekt jest natywną aplikacją desktopową (wxPython) zaprojektowaną od podstaw z myślą o pełnej dostępności dla czytników ekranu (NVDA, VoiceOver) i współpracy z profesjonalnymi syntezatorami mowy (TTS). Działa bez przeglądarki i bez lokalnego serwera — uruchamia się jako zwykłe okno programu.

Versio: **15.2.4** · Tuetut kielet alkuperäisesti (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Päämoduulit

Sovellus yhdistää yhteen ikkunaan viisi työkalua, joita voi vaihtaa pikanäppäimillä (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 / Ctrl+5) tai työkalupalkin painikkeilla. Jokainen moduuli toimii itsenäisesti, mutta kaikki jakavat sanakirjapaketit `dictionaries/`-kansiosta (aksentit, salakirjoitukset, AI-luovat tilat) ja keskeiset asetukset.


### 1. Ohjaus (Ctrl+1)

Päästudio kuunnelmien ja äänikirjojen kirjoittamiseen. Valitset tilan — Aivoriihi, Käsikirjoitus (tageilla `[SFX]`/`[Hahmo: tunne]`), Äänikirja (perinteinen proosa) — ja ohjaat dialogia mallin kanssa ohjeiden kentän + Maailman Kirjojen + Pitkäaikaisen Muistin avulla:

* **Moniprojektinen Maailman Kirja:** Järjestelmä lataa automaattisesti taustalla omistetut universumin säännöt (`.md`) aktiivisen lähdetiedoston perusteella, tarjoten täydellisen eristyksen (nollaklikkauskontekstin lataus).
* **Juonen Akut:** Algoritmi "loputtomalle muistille". Kun muistin osoitin saavuttaa punaisen hälytyksen tilan, järjestelmä luo automaattisesti juonitiivistelmän ja tallentaa sen Pitkäaikaisen Muistin kenttään.
* **4 luovat tilat:** Jokainen tiedosto `dictionaries/<jzk>/rezyser/` -hakemistossa kuvaa erillisen AI-ohjaajan "persoonallisuuden" (Aivoriihi, Käsikirjoitus, Äänikirja, Otsikoiden Jälkituotanto). Voit hienosäätää niiden sävyä ilman ohjelmointia — katso Sääntöjen Hallinta alla.


### 2. Tarinoita (Ctrl+2, toinen päätila v15.0 alkaen)

Interaktiivisia tekstipelejä, joissa AI toimii kertomuksen moottorina. Toisin kuin Ohjauksessa (jossa luot valmiin äänikirjan), Tarinoita on vuoropohjainen dynaaminen juoni:

* **Valintatila:** jokainen vuoro päättyy 3-5 numeroituun vaihtoehtoon A-E. Intuitiivisin tila näkövammaisille pelaajille — NVDA lukee vaihtoehdot, napsautat Tab ja Enter.
* **Pienempi paha -tila:** kuten Valinnat, mutta jokainen vaihtoehto on moraalisesti, fyysisesti tai strategisesti epäedullinen. V15.2 alkaen lisätty "pullo" — uudelleenkäytettävä NOLLA-numeroitu epätoivoinen pelastusvaihtoehto, jonka vaikutukset ovat pseudolosiaalisia (60% haitallisia / 30% havainnointia häiritseviä / 10% harvoin hyödyllisiä, Python pakottaa jakauman, LLM ei voi keksiä pelastavaa vaikutusta).
* **Vapaa tila:** mikä tahansa toiminta vapaalla tekstillä ("yritän avata oven"), moottori ehdottaa 1-3 ehdotusta mutta ei pakota valintaa.
* **AI-malli per tila:** Valinnat ja Pienempi paha käyttävät gpt-4o (parempi moraalinen päättely), Vapaa käyttää gpt-4o-mini (edullisempi improvisaatioekonomia).


### 3. Polyglot (Ctrl+3, AI-kääntäjä + TTS-aksentit)

* **Turvallinen Kääntäjä:** Pitkät tekstit jaetaan automaattisesti enintään 10 000 merkin lohkoihin ja käännetään peräkkäin. Jokainen lohko tallennetaan välittömästi piilotettuun `.jsonl`-tiedostoon. API-rajoitusten täyttyessä jatkaminen on täysin automaattista.
* **NVDA Automaatio:** Käännökset tallennetaan valmiina `.html`-tiedostoina, joissa on sisäänrakennettu kielitagi, tai `.docx`-tiedostoina, joissa tagit on injektoitu suoraan XML-rakenteeseen.
* **8 paikallisia aksentteja:** Mahdollisuus tarkoituksellisesti pakottaa murrettu aksentti paikallisille synteesilaitteille (Tiflotecnia Voices, eSpeak, OneCore) kehittyneiden regex-sääntöjen avulla. Tuetut vieraskieliset aksentit: englanti, venäjä (kyrilliseen translitterointi), ranska, saksa, espanja, italia, puola, islanti.
* **Siffrin tila:** 6 paikallisia tekstin vääristämisalgoritmeja — tekstin kääntämisestä taaksepäin, typoglykemiaan ja klassiseen Caesarin salaukseen. Jokainen paikallisella kielipaketin aakkostolla (esim. Caesarin salaus 35-merkkisellä FI-aakkostolla diakriittisillä merkeillä).
* **Tagien Korjaaja:** Injektoi häiritsemättä annetun kaksikirjaimisen ISO-kielikoodin olemassa oleviin tiedostoihin.


### 4. Muuntaja / Äänikirjojen Arkkitehti (Ctrl+4)

* Käsittelee raakoja `.txt` tai `.docx` tiedostoja NVDA:n ja sellaisten järjestelmien kuin ElevenLabs näppäimistönavigointia varten.
* Muuntaa automaattisesti avainsanat (Näytös, Luku, Prologi) Word-dokumentin "Heading 1" -otsikoiksi ja puhdistaa tarpeettomat HTML-tagit ja Markdown-merkinnät.
* Versiosta 15.1 alkaen ryhmittelee 5 kierrosta kohtauksiin H1-otsikoilla (Tarinoiden automaattinen tunnistus) — valmistelee Tarinatilan luoman tiedoston perinteistä äänikirjajulkaisua varten.


### 5. Sääntöjen Hallinta (Ctrl+5, uutta v13.0 alkaen)

* **Sanakirjojen tutkija ilman Pythonia:** Visuaalinen puu kaikista YAML-tiedostoista `dictionaries/`-kansiossa — foneettiset aksentit, salakirjoitukset, Ohjaajan ja Tarinoiden luovat tilat. Kielitieteilijä tai kääntäjä voi tarkastella, kopioida, muokata ja poistaa sääntöjä suoraan käyttöliittymästä.
* **Uusien sääntöjen luonti:** Lomake, jossa valitaan tyyppi (aksentti, yksinkertainen korvaussalakirjoitus, Ohjaajan tila, uusi peruskieli, algoritminen salakirjoitus), luo valmiin YAML-mallin, ja vaikeammissa tapauksissa generoi muotoillun kehotteen liitettäväksi ChatGPT:hen / Claudeen.
* **Refaktorointi v13.0 — säännöt YAML-tiedostoissa:** Kaikki aksentit, salakirjoitukset ja AI-tilat, jotka versioon 12.0 asti olivat "kovakoodattuja" vakioita Python-koodissa, on siirretty deklaratiivisiin `.yaml`-tiedostoihin, jotka ladataan dynaamisesti sovelluksen käynnistyessä. Jokainen, joka osaa käyttää Muistikirjaa, voi hienosäätää aksenttia (esim. vaihtaa `sz → sh` `sz → sch`), lisätä uuden kielen tai jopa muuttaa AI:n järjestelmäkehotteen ääntä — ilman koodin kääntämistä.


## Monikielisyys (9 kieltä luonnollisesti)

Versiosta v14.0 lähtien sovellus tukee luonnollisesti 9 peruskieltä: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Jokainen `dictionaries/<koodi>/`-paketti sisältää diakriittiset merkit, aakkoset ja foneettiset säännöt, jotka toimivat kyseisen kielen tekstissä — sovellus tunnistaa lähdekielen automaattisesti lingua-language-detectorin avulla (kappaleittain) ja lataa sopivan paketin jokaiselle osalle erikseen.

Koko käyttöliittymä, dokumentaatio (`docs/manual.<iso>.txt`) ja suurin osa järjestelmäviesteistä ovat luonnollisesti saatavilla kaikilla tuetuilla kielillä. AI-järjestelmäkehotteet Ohjaajan ja Tarinan tiloissa on kirjoitettu kohdekielillä (käsin, ei automaattisesti käännettynä — katso `dictionaries/<koodi>/rezyser/` ja `dictionaries/<koodi>/opowiesci/`).


## AI-arkkitehtuuri ja käytetyt mallit

Sovellus jakaa tehtävät älykkäästi, optimoiden OpenAI:n API:n kustannukset ja nopeuden:

* **gpt-4o:** Sovelluksen päämoottori. Vastaa raskaista generatiivisista tehtävistä: käsikirjoitusten ohjaaminen, perinteisen proosan kirjoittaminen (äänikirja), Valintojen ja Pienemmän Pahan tilat Kertomuksissa, tiivistelmien luominen sekä edistyneet käännökset monilohkokontekstin säilyttämisellä.
* **gpt-4o-mini:** Nopea, kevyt apumalli. Käytetään taustalla mikrotehtäviin, jotka vaativat suurta nopeutta: luotujen lukujen kirjallisten otsikoiden iteratiivinen antaminen, ISO-koodien poiminta, Vapaa tila Kertomuksissa (halvempi improvisoidun vapaan tekstin talous).


### Tunnetut mallien rajoitukset (Anti-Closure)

Huolimatta tiukkojen järjestelmäohjeiden toteuttamisesta, jotka edellyttävät toiminnan katkaisemista jännityksen hetkellä (ns. Anti-Closure-direktiivi), nykyaikaisilla LLM-malleilla on vahva, synnynnäinen taipumus "sulkea" tarinoita. Tämä johtaa usein ei-toivottujen johtopäätösten, moraalien tai väärien "onnellisten loppujen" sisällyttämiseen, erityisesti Perinteisen Äänikirjan Tilassa.

Tämä on nykyisen sukupolven tekoälyn perustavanlaatuinen rajoitus. Tästä syystä sovellus tallentaa projektit tavallisina, helposti muokattavina tekstimuotoisina tiedostoina (`.txt`). Tämä edellyttää käyttäjältä elävän leikkaajan roolin omaksumista — AI:n luomien viimeisten, "sulkevien" lauseiden satunnaista, manuaalista poistamista ennen tiedoston uudelleen lataamista ja työn jatkamista.


## Asennus ja käynnistys

### Loppukäyttäjille (Windows)

1. Lataa uusin julkaisu **Releases**-välilehdeltä (paketti merkitty *Latest*). Saatavilla on kaksi muotoa:
   * **Installer EXE** — asentaa Program Files -kansioon (tai valittuun kansioon), luo pikakuvakkeet Käynnistä-valikkoon ja työpöydälle. Asennuksen päätyttyä avaa valinnaisesti käyttöohjeen oletustekstinkäsittelyohjelmassa.
   * **Portable ZIP** — pura mihin tahansa kansioon, ei vaadi järjestelmänvalvojan oikeuksia. Purkamisen jälkeen suorita `run.bat`.
2. **OpenAI API:n konfigurointi:** Ensimmäisellä käynnistyskerralla sovellus ilmoittaa avaimen puuttumisesta System Check -osiossa. Napsauta näkyvää painiketta luodaksesi `golden_key.env`-tiedoston, avaa se tekstieditorissa ja liitä avain (alkaen `sk-proj-`).
3. **Ensimmäiset askeleet:** Avaa tiedosto `docs/manual.pl.txt` (tai muulla kielellä) asennuskansiosta — se on täydellinen käyttöohje, joka on kirjoitettu kielellä, joka on kaikkien käyttäjien, ei vain kehittäjien, ymmärrettävissä.


### Kehittäjille (clone + setup)

1. Kloonaa arkisto levyllesi.
2. Suorita `setup_dev.bat` -tiedosto luodaksesi automaattisesti virtuaalisen ympäristön (`.venv/`) ja ladataksesi riippuvuudet `requirements.txt` -tiedostosta.
3. Käynnistä sovellus komennolla `python main.py` tai `run_dev.bat` -tiedoston kautta.

`.sh`-skriptit macOS/Linuxille poistettiin versiossa v13.1 — kehitysympäristö keskittyy Windowsiin NVDA:n saavutettavuustestien erityispiirteiden vuoksi. Koodin kanssa työskentely muilla järjestelmillä on mahdollista, mutta vaatii manuaalista asennusta: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Julkaisupakettien rakennusskriptit** (`build_release.py`, `installer.iss`) on tarkoitettu vain Windows-pakettien luomiseen. Ne vaativat erityisen `runtime/`-kansion siirrettävällä Python-versiolla — tämä kansio ei ole tarkoituksella osa arkistoa (se on `.gitignore`-tiedostossa).


## Täydellinen dokumentaatio

Tämä README on vain projektin arkkitehtoninen luonnos. Jos haluat oppia kehittyneitä tekniikoita AI-harhojen estämiseksi, yhteensopivien puhesyntetisaattoreiden (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices) asennusohjeita, täydellisen kuvauksen Fiolitarinoiden tiloista sekä täydellisen käyttöoppaan, tutustu `docs/`-kansiossa oleviin tiedostoihin:

* `docs/manual.<iso>.txt` — pääasiallinen käyttöohje (kirjoitettu loppukäyttäjälle).
* `docs/tales.<iso>.txt` — Fiolitarinoiden tilan ohjekirja (interaktiiviset tekstipelit).
* `docs/dictionaries.<iso>.txt` — ohjeet lingvisteille ilman Pythonia, kuinka lisätä omia aksentteja/salauksia/AI-tiloja.

Jokainen näistä tiedostoista on saatavilla 9 kielellä — suffiksi `.<iso>.txt` (esim. `manual.pl.txt`, `manual.en.txt`, `manual.de.txt`).
