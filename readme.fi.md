# Reżyser Audio GPT

**Hybrid Studioäänityötila kuunnelmille, äänikirjoille ja interaktiivisille tarinoille**

**Muut kieliversiot / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Itsenäinen tekoälyllä toimivien työkalujen kokoelma laajojen käsikirjoitusten automaattiseen kirjoittamiseen, suunnitteluun, muotoiluun ja kääntämiseen sekä interaktiivisten tekstipelien johtamiseen. Projekti on natiivi työpöytäsovellus (wxPython), joka on suunniteltu alusta alkaen täysin saavutettavaksi ruudunlukijoille (NVDA, VoiceOver) ja yhteensopivaksi ammattimaisten puhesynteesien (TTS) kanssa. Toimii ilman selainta ja ilman paikallista palvelinta — käynnistyy tavallisena ohjelmaikkunana.

Versio: **18.2.2** · Tuetut kielet alkuperäisesti (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Päämoduulit

Sovellus yhdistää yhteen ikkunaan viisi työkalua, joita voi vaihtaa pikanäppäimillä (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 / Ctrl+5) tai työkalupalkin painikkeilla. Jokainen moduuli toimii itsenäisesti, mutta kaikki jakavat sanakirjapaketit `dictionaries/`-kansiosta (aksentit, salakirjoitukset, AI-luovat tilat) ja keskeiset asetukset.


### 1. Ohjaus (Ctrl+1)

Päästudio kuunnelmien ja äänikirjojen kirjoittamiseen. Valitset tilan — Aivoriihi, Käsikirjoitus (tageilla `[SFX]`/`[Hahmo: tunne]`), Äänikirja (perinteinen proosa) — ja ohjaat dialogia mallin kanssa ohjeiden kentän + Maailman Kirjojen + Pitkäaikaisen Muistin avulla:

* **Moniprojektinen Maailman Kirja:** Järjestelmä lataa automaattisesti taustalla omistetut universumin säännöt (`.md`) aktiivisen lähdetiedoston perusteella, tarjoten täydellisen eristyksen (nollaklikkauskontekstin lataus).
* **Juonen Akut:** Algoritmi "loputtomalle muistille". Kun muistin osoitin saavuttaa punaisen hälytyksen tilan, järjestelmä luo automaattisesti juonitiivistelmän ja tallentaa sen Pitkäaikaisen Muistin kenttään.
* **4 luovat tilat:** Jokainen tiedosto `dictionaries/<jzk>/rezyser/` -hakemistossa kuvaa erillisen AI-ohjaajan "persoonallisuuden" (Aivoriihi, Käsikirjoitus, Äänikirja, Otsikoiden Jälkituotanto). Voit hienosäätää niiden sävyä ilman ohjelmointia — katso Sääntöjen Hallinta alla.


### 2. Opowieści (Ctrl+2, toinen päätila v15.0 alkaen)

Interaktiiviset tekstipelit, joissa AI toimii kerrontamoottorina. Toisin kuin Reżyseria (jossa tuotat valmiin äänikirjan), Opowieści tarjoaa vuoropohjaista dynaamista juonta:

* **Valintatila:** jokainen vuoro päättyy 3-5 numeroituun vaihtoehtoon A-E. Intuitiivisin tila näkövammaisille pelaajille — NVDA lukee vaihtoehdot, painat Tab ja Enter.
* **Pienempi paha -tila:** kuten Valinnat, mutta jokainen vaihtoehto on moraalisesti, fyysisesti tai strategisesti epäsuotuisa. V15.2 alkaen lisätty "fiolka" — uudelleenkäytettävä NOLLA-numeroitu epätoivoinen pelastusvaihtoehto, jonka vaikutukset ovat pseudolosiaalisia (60% haitallisia / 30% havainnointia häiritseviä / 10% harvoin hyödyllisiä, Python pakottaa jakauman, LLM ei voi keksiä pelastavaa vaikutusta).
* **Vapaa tila:** mikä tahansa toiminta vapaalla tekstillä ("yritän avata oven"), moottori ehdottaa 1-3 ehdotusta, mutta ei pakota valintaa.
* **Yksi AI-malli kaikille tiloille:** v18.1 alkaen kaikki Opowieści-tilat käyttävät Anthropic Claude Sonnet 4.6:ta — voimakkaampi malli, joka noudattaa tiukasti maailman sääntöjä (erityisen tärkeää Pienempi paha -tilassa, jossa jokaisen vaihtoehdon on oltava todellisesti epäsuotuisa).


### 3. Polyglot (Ctrl+3, AI-kääntäjä + TTS-aksentit)

* **Turvallinen Kääntäjä:** Pitkät tekstit jaetaan automaattisesti lohkoihin, jotka mitataan mallin tokeneina (turvallista myös tiheästi kirjoitetuille kielille, esim. kiinalle), ja käännetään peräkkäin; katkennut mallin vastaus tunnistetaan ja yritetään uudelleen pienemmissä osissa. Jokainen lohko tallennetaan välittömästi piilotettuun `.jsonl`-tiedostoon. API-rajoitusten täyttyessä jatkaminen on täysin automaattista.
* **NVDA Automaatio:** Käännökset tallennetaan valmiina `.html`-tiedostoina, joissa on sisäänrakennettu kielitagi, tai `.docx`-tiedostoina, joissa tagit on injektoitu suoraan XML-rakenteeseen.
* **8 paikallisia aksentteja:** Mahdollisuus tarkoituksellisesti pakottaa murrettu aksentti paikallisille synteesilaitteille (Tiflotecnia Voices, eSpeak, OneCore) kehittyneiden regex-sääntöjen avulla. Tuetut vieraskieliset aksentit: englanti, venäjä (kyrilliseen translitterointi), ranska, saksa, espanja, italia, puola, islanti.
* **Siffrin tila:** 6 paikallisia tekstin vääristämisalgoritmeja — tekstin kääntämisestä taaksepäin, typoglykemiaan ja klassiseen Caesarin salaukseen. Jokainen paikallisella kielipaketin aakkostolla (esim. Caesarin salaus 35-merkkisellä FI-aakkostolla diakriittisillä merkeillä).
* **Tagien Korjaaja:** Injektoi häiritsemättä annetun ISO-kielikoodin — myös alueellisen, esim. pt-BR tai zh-CN — olemassa oleviin tiedostoihin.


### 4. Muuntaja / Äänikirjojen Arkkitehti (Ctrl+4)

* Käsittelee raakoja `.txt` tai `.docx` tiedostoja NVDA:n ja sellaisten järjestelmien kuin ElevenLabs näppäimistönavigointia varten.
* Muuntaa automaattisesti avainsanat (Näytös, Luku, Prologi) Word-dokumentin "Heading 1" -otsikoiksi ja puhdistaa tarpeettomat HTML-tagit ja Markdown-merkinnät.
* Versiosta 15.1 alkaen ryhmittelee 5 kierrosta kohtauksiin H1-otsikoilla (Tarinoiden automaattinen tunnistus) — valmistelee Tarinatilan luoman tiedoston perinteistä äänikirjajulkaisua varten.


### 5. Sääntöjen Hallinta (Ctrl+5, uutta v13.0 alkaen)

* **Sanakirjojen tutkija ilman Pythonia:** Visuaalinen puu kaikista YAML-tiedostoista `dictionaries/`-kansiossa — foneettiset aksentit, salakirjoitukset, Ohjaajan ja Tarinoiden luovat tilat. Kielitieteilijä tai kääntäjä voi tarkastella, kopioida, muokata ja poistaa sääntöjä suoraan käyttöliittymästä.
* **Uusien sääntöjen luonti:** Lomake, jossa valitaan tyyppi (aksentti, yksinkertainen korvaussalakirjoitus, Ohjaajan tila, uusi peruskieli, algoritminen salakirjoitus), luo valmiin YAML-mallin, ja vaikeammissa tapauksissa generoi muotoillun kehotteen liitettäväksi ChatGPT:hen / Claudeen.
* **Refaktorointi v13.0 — säännöt YAML-tiedostoissa:** Kaikki aksentit, salakirjoitukset ja AI-tilat, jotka versioon 12.0 asti olivat "kovakoodattuja" vakioita Python-koodissa, on siirretty deklaratiivisiin `.yaml`-tiedostoihin, jotka ladataan dynaamisesti sovelluksen käynnistyessä. Jokainen, joka osaa käyttää Muistikirjaa, voi hienosäätää aksenttia (esim. vaihtaa `sz → sh` `sz → sch`), lisätä uuden kielen tai jopa muuttaa AI:n järjestelmäkehotteen ääntä — ilman koodin kääntämistä.


## Monikielisyys (9 kieltä luonnollisesti)

Versiosta v14.0 lähtien sovellus tukee luonnollisesti 9 peruskieltä: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Jokainen `dictionaries/<kod>/`-paketti sisältää diakriittiset merkit, aakkoset ja foneettiset säännöt, jotka toimivat kyseisen kielen tekstissä — sovellus tunnistaa lähdekielen automaattisesti lingua-language-detectorin avulla (kappaleittain) ja lataa sopivan paketin jokaiselle osalle erikseen.

Koko käyttöliittymä, dokumentaatio (`docs/manual.<iso>.txt`) ja suurin osa järjestelmäviesteistä ovat luonnollisesti saatavilla kaikilla tuetuilla kielillä. AI-järjestelmäkehotteet Ohjaajan ja Tarinan tiloissa on kirjoitettu kohdekielillä (käsin, ei automaattisesti käännettynä — katso `dictionaries/<kod>/rezyser/` ja `dictionaries/<kod>/opowiesci/`).


## Tekoälyarkkitehtuuri ja käytetyt mallit

Versiosta 18.2 lähtien sovellus käyttää yhtä API-palveluntarjoajaa — Anthropicia — ja yhtä mallia kaikkiin tekoälytehtäviin:

* **Anthropic Claude Sonnet 4.6:** Sovelluksen KAIKEN älykkyyden moottori. Se vastaa luovasta kerronnasta (skriptien ohjaamisesta, perinteisen äänikirjaproosan kirjoittamisesta, Aivoriihistä sekä KAIKISTA Tarinoiden tiloista — Valinnat, Pienempi Paha, Vapaa — mukaan lukien yhteenvetojen ja Cinematic-välikohtausten generointi), edistyneistä käännöksistä monilohkoisen kontekstin säilyttämisellä (Poliglota), sekä mikrotöistä: lukujen kirjallisten otsikoiden iteratiivisesta luomisesta ja sisällön kielikoodin tunnistamisesta. Konsolidointi Claudeen tapahtui vaiheittain (Reżyser versiossa v18.0, Opowiesci versiossa v18.1, Poliglota ja jälkituotanto versiossa v18.2) — se johtui empiirisesti vahvistetusta ylivoimaisuudesta maailman sääntöjen noudattamisessa, proosan luontevuudessa ja kliseiden välttämisessä.


### Tunnetut mallien rajoitukset (Anti-Closure)

Huolimatta tiukkojen järjestelmäohjeiden toteuttamisesta, jotka edellyttävät toiminnan katkaisemista jännityksen hetkellä (ns. Anti-Closure-direktiivi), nykyaikaisilla LLM-malleilla on vahva, synnynnäinen taipumus "sulkea" tarinoita. Tämä johtaa usein ei-toivottujen johtopäätösten, moraalien tai väärien "onnellisten loppujen" sisällyttämiseen, erityisesti Perinteisen Äänikirjan Tilassa.

Tämä on nykyisen sukupolven tekoälyn perustavanlaatuinen rajoitus. Tästä syystä sovellus tallentaa projektit tavallisina, helposti muokattavina tekstimuotoisina tiedostoina (`.txt`). Tämä edellyttää käyttäjältä elävän leikkaajan roolin omaksumista — AI:n luomien viimeisten, "sulkevien" lauseiden satunnaista, manuaalista poistamista, minkä jälkeen muisti synkronoidaan korjatun tiedoston kanssa „Päivitä levyltä" -painikkeella, ja työtä jatketaan.


## Asennus ja käynnistys

### Loppukäyttäjille (Windows)

1. Lataa uusin julkaisu **Releases**-välilehdeltä (paketti merkitty *Latest*) — tiedosto `Rezyser_Audio_v<numer>_Installer.exe`. Käynnistä se kaksoisnapsauttamalla. Asennusohjelma sijoittuu oletuksena käyttäjätilisi paikalliseen hakemistoon (`%LocalAppData%\Programs\Reżyser Audio GPT`) eikä vaadi järjestelmänvalvojan oikeuksia; voit valita oman polun "Przeglądaj"-painikkeella. Asennuksen jälkeen ohjelma luo pikakuvakkeet Käynnistä-valikkoon ja työpöydälle, ja vaihtoehtoisesti avaa käyttöohjeen oletuksena määritetyssä `.txt`-tiedostojen editorissa.
2. **Anthropic API -määritys:** Ensimmäisellä käynnistyskerralla sovellus ilmoittaa puuttuvasta avaimesta System Check -osiossa. Napsauta näkyvää painiketta luodaksesi `golden_key.env`-tiedoston, avaa se tekstieditorissa ja liitä Anthropic-avaimesi (joka alkaa merkkijonolla `sk-ant-`).
3. **Ensiaskeleet:** Avaa tiedosto `docs/manual.pl.txt` (tai muunkielinen versio) asennuskansiosta — se on täydellinen käyttöohje, joka on kirjoitettu kaikkien käyttäjien ymmärtämällä kielellä, ei pelkästään kehittäjille.


### Kehittäjille (clone + setup)

1. Kloonaa arkisto levyllesi.
2. Suorita tiedosto `setup_dev.bat` luodaksesi automaattisesti virtuaalisen ympäristön (`.venv/`) ja ladataksesi riippuvuudet `requirements.txt`-tiedostosta.
3. Käynnistä sovellus komennolla `python main.py` tai tiedoston `run_dev.bat` kautta.

`.sh`-skriptit macOS/Linuxille poistettiin versiossa 13.1 — kehitysympäristö keskittyy Windowsiin NVDA:n saavutettavuustestien erityispiirteiden vuoksi. Koodin kanssa työskentely muilla järjestelmillä on mahdollista, mutta vaatii manuaalista asennusta: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Julkaisupakettien rakennusskriptit** (`build_release.py`, `rezyser_audio.spec`, `installer.iss`) on tarkoitettu ainoastaan Windows-pakettien luomiseen. Versiosta 17.0 alkaen `build_release.py` jäädyttää sovelluksen PyInstallerilla (onedir + windowed) `rezyser_audio.spec`-tiedoston mukaisesti — tuottaa `dist/`-hakemiston, jossa on alkuperäinen `.exe` ja bundlen `runtime/`-kansio (tulkki + kirjastot). Manuaalisesti ladattua siirrettävää Pythonia ei enää tarvita arkistoon; `dist/` ja `build/`-hakemistot ovat `.gitignore`-tiedostossa.


## Täydellinen dokumentaatio

Tämä README on vain projektin arkkitehtoninen luonnos. Jos haluat oppia kehittyneitä tekniikoita AI-harhojen estämiseksi, yhteensopivien puhesyntetisaattoreiden (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices) asennusohjeita, täydellisen kuvauksen Fiolitarinoiden tiloista sekä täydellisen käyttöoppaan, tutustu `docs/`-kansiossa oleviin tiedostoihin:

* `docs/manual.<iso>.txt` — pääasiallinen käyttöohje (kirjoitettu loppukäyttäjälle).
* `docs/tales.<iso>.txt` — Fiolitarinoiden tilan ohjekirja (interaktiiviset tekstipelit).
* `docs/dictionaries.<iso>.txt` — ohjeet lingvisteille ilman Pythonia, kuinka lisätä omia aksentteja/salauksia/AI-tiloja.

Jokainen näistä tiedostoista on saatavilla 9 kielellä — suffiksi `.<iso>.txt` (esim. `manual.pl.txt`, `manual.en.txt`, `manual.de.txt`).


### Puolan kielinen nimistö — opas ei-puolankielisille käyttäjille

Tämän projektin pääkieli on puola. Moduulien nimet, luokat, koodikommentit sekä hakemistojen ja datatiedostojen nimet ovat puolankielisiä, ja — taaksepäin yhteensopivuuden ja monikielimoottorin sopimuksen vuoksi — niitä EI tarkoituksella käännetä tai muuteta. Seuraava sanasto auttaa kehittäjiä ja macOS/Linux-käyttäjiä hahmottamaan rakennetta.

**Käyttäjädatan hakemistot (suoritettavan tiedoston vieressä tai projektihakemistossa):**

* `skrypty/` — *scripts*: Ohjaaja-moduulin projektit (`.txt` kerronta, `.md` Maailman Kirja, `_streszczenie.txt`).
* `opowiesci/` — *stories*: interaktiivisten Tarinoiden tallenteet.
* `runtime/` — kaksoisrooli: jäädytetyn sovelluksen bundlen hakemisto (tulkki + kirjastot) SEKÄ projektien piilotettujen metatietojen säiliö (`runtime/skrypty/`, `runtime/opowiesci/`).

**Lähdedatan alikansiot `dictionaries/<kod>/` (näkyvissä Sääntöjen Hallinnassa):**

* `podstawy.yaml` — *basics*: kielipaketin konfiguraatio ja metatiedot.
* `akcenty/` — *accents*: fonetiikan säännöt puhesyntetisaattoreille.
* `szyfry/` — *ciphers*: tekstin salausmoodit.
* `rezyser/` — *director*: Ohjaaja-moduulin luovat tilat.
* `opowiesci/` — *stories*: interaktiivisten Tarinoiden tilat.
* `gui/` — käyttöliittymän tekstit (`ui.yaml`) ja dokumentaatiomallit.


## Lisenssi

Projekti on julkaistu **MIT**-lisenssillä — täydellinen teksti löytyy tiedostosta [`LICENSE`](LICENSE) pääkansiossa. Lyhyesti: voit vapaasti käyttää, kopioida, muokata ja levittää ohjelmistoa (myös kaupallisesti), kunhan säilytät tekijänoikeusilmoituksen. Ohjelmisto toimitetaan "sellaisena kuin se on", ilman minkäänlaista takuuta.
