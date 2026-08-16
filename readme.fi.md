# Reżyser Audio GPT

**Hybridinen studiotyötila äänelle — kuunnelmille, äänikirjoille ja interaktiivisille tarinoille**

**Muut kieliversiot / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Itsenäinen tekoälyllä toimivien työkalujen kokoelma laajojen käsikirjoitusten automaattiseen kirjoittamiseen, suunnitteluun, muotoiluun ja kääntämiseen sekä interaktiivisten tekstipelien johtamiseen. Projekti on natiivi työpöytäsovellus (wxPython), joka on suunniteltu alusta alkaen täysin saavutettavaksi ruudunlukijoille (NVDA, VoiceOver) ja yhteensopivaksi ammattimaisten puhesynteesien (TTS) kanssa. Toimii ilman selainta ja ilman paikallista palvelinta — käynnistyy tavallisena ohjelmaikkunana.

Versio: **18.15.0** · Tuetut kielet alkuperäisesti (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Päämoduulit

Sovellus yhdistää yhteen ikkunaan viisi työkalua, joita voi vaihtaa pikanäppäimillä (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 / Ctrl+5) tai työkalupalkin painikkeilla. Jokainen moduuli toimii itsenäisesti, mutta kaikki jakavat sanakirjapaketit `dictionaries/`-kansiosta (aksentit, salakirjoitukset, AI-luovat tilat) ja keskeiset asetukset.


### 1. Ohjaus (Ctrl+1)

Päästudio kuunnelmien ja äänikirjojen kirjoittamiseen. Valitset tilan — Aivoriihi, Käsikirjoitus (tageilla `[SFX]`/`[Hahmo: tunne]`), Äänikirja (perinteinen proosa) — ja ohjaat dialogia mallin kanssa ohjeiden kentän + Maailman Kirjojen + Pitkäaikaisen Muistin avulla:

* **Moniprojektinen Maailman Kirja:** Järjestelmä lataa automaattisesti taustalla omistetut universumin säännöt (`.md`) aktiivisen lähdetiedoston perusteella, tarjoten täydellisen eristyksen (kontekstin lataus ilman klikkauksia).
* **Juonen Akut:** Algoritmi "loputtomalle muistille". Juonitiivistelmän luo erillinen jälkituotantotyökalu (versiosta 18.13), ja kun muistin osoitin saavuttaa punaisen hälytyksen tilan, järjestelmä käynnistää sen itse ja tallentaa tuloksen sekä tiedostoon että Pysyvän Muistin kenttään. Seuraavat tiivistelmät ovat inkrementaalisia — malli saa edellisen muistin ja vain kerronnan uuden osan.
* **6 luovaa tilaa:** Jokainen tiedosto `dictionaries/<jzk>/rezyser/` -hakemistossa kuvaa erillisen AI-ohjaajan "persoonallisuuden" (Aivoriihi, Käsikirjoitus, Äänikirja) tai jälkituotantotyökalun (Lukujen otsikot, Pysyvä Muisti). Voit hienosäätää niiden sävyä ilman ohjelmointia — katso Sääntöjen Hallinta alla.


### 2. Tarinat (Ctrl+5, toinen päätila versiosta 15.0 alkaen)

Interaktiivisia tekstipelejä, joita AI ohjaa kerronnallisen moottorin roolissa. Toisin kuin Ohjaus-tilassa (jossa luodaan valmis äänikirja), Tarinat on vuoro vuorolta etenevä dynaaminen juoni:

* **Valintatila:** jokainen vuoro päättyy 3-5 numeroituun vaihtoehtoon A-E. Intuitiivisin tila näkövammaisille pelaajille — NVDA lukee vaihtoehdot, painat Tabia ja Enteriä.
* **Pienempi Paha -tila:** kuten Valinnat, mutta jokainen vaihtoehto on epäedullinen moraalisesti, fyysisesti tai strategisesti. Versiosta 15.2 alkaen lisätty "pikkupullo" — uudelleenkäytettävä NOLLA-numeroitu vaihtoehto epätoivoiselle pelastautumiselle, jonka vaikutukset ovat pseudosatunnaisia (60% haitallisia / 30% havaintoa häiritseviä / 10% harvinaisen edullisia, jakauma pakotettu Pythonilla, LLM ei pysty keksimään pelastavaa lopputulosta).
* **Vapaa tila:** mikä tahansa toiminto vapaana tekstinä ("yritän avata oven"), moottori ehdottaa 1-3 vaihtoehtoa mutta ei pakota valitsemaan.
* **Yksi AI-malli kaikille tiloille:** versiosta 18.1 alkaen kaikki Tarinat-tilat käyttävät samaa, yhteistä mallia (oletuksena ja suositeltuna Anthropic Claude Sonnet 5) — vahvempi malli noudattaa tiukasti maailman sääntöjä (avainasemassa erityisesti Pienempi Paha -tilassa, jossa jokaisen vaihtoehdon on oltava aidosti epäedullinen).


### 3. Polyglootti (Ctrl+2, Tekoälykääntäjä + TTS-aksentit)

* **Turvallinen Kääntäjä:** Pitkät tekstit jaetaan automaattisesti lohkoihin, jotka mitataan mallin tokeneina (turvallista myös tiheästi kirjoitetuille kielille, esim. kiinalle), ja käännetään peräkkäin; katkennut mallin vastaus tunnistetaan ja yritetään uudelleen pienemmissä osissa. Jokainen lohko tallennetaan välittömästi piilotettuun `.jsonl`-tiedostoon. API-rajoitusten täyttyessä jatkaminen on täysin automaattista.
* **NVDA Automaatio:** Käännökset tallennetaan valmiina `.html`-tiedostoina, joissa on sisäänrakennettu kielitagi, tai `.docx`-tiedostoina, joissa tagit on injektoitu suoraan XML-rakenteeseen.
* **8 paikallista aksenttia:** Mahdollisuus tarkoituksellisesti pakottaa murrettu aksentti paikallisille synteesilaitteille (Tiflotecnia Voices, eSpeak, OneCore) kehittyneiden regex-sääntöjen avulla. Tuetut vieraskieliset aksentit: englanti, venäjä (kyrilliseen translitterointi), ranska, saksa, espanja, italia, puola, islanti.
* **Koodinmurtajan tila:** 6 paikallista tekstin vääristämisalgoritmia — tekstin kääntämisestä taaksepäin, typoglykemiaan ja klassiseen Caesarin salaukseen. Jokainen toimii kielipaketin omalla aakkostolla (esim. Caesarin salaus 29-merkkisellä FI-aakkostolla diakriittisillä merkeillä).
* **Tunnisteiden korjaaja:** Injektoi häiritsemättä annetun ISO-kielikoodin — myös alueellisen, esim. pt-BR tai zh-CN — olemassa oleviin tiedostoihin.


### 4. Muunnin / Äänikirjojen Arkkitehti (Ctrl+3)

* Käsittelee raakoja `.txt`- tai `.docx`-tiedostoja NVDA:n ja sellaisten järjestelmien kuin ElevenLabs näppäimistönavigointia varten.
* Muuntaa automaattisesti avainsanat (Näytös, Luku, Prologi) Word-dokumentin "Heading 1" -otsikoiksi ja puhdistaa tarpeettomat HTML-tagit ja Markdown-merkinnät.
* Versiosta 15.1 alkaen ryhmittelee 5 kierrosta kohtauksiin H1-otsikoilla (Tarinoiden automaattinen tunnistus) — valmistelee Tarina-tilan luoman tiedoston perinteistä äänikirjajulkaisua varten.


### 5. Sääntöjen Hallinta (Ctrl+4, uutta versiosta 13.0 alkaen)

* **Sanakirjojen selain ilman Pythonia:** Visuaalinen puu kaikista YAML-tiedostoista `dictionaries/`-kansiossa — foneettiset aksentit, salakirjoitukset, Ohjaajan ja Tarinoiden luovat tilat. Kielitieteilijä tai kääntäjä voi tarkastella, kopioida, muokata ja poistaa sääntöjä suoraan käyttöliittymästä.
* **Uusien sääntöjen luonti:** Lomake, jossa valitaan tyyppi (aksentti, yksinkertainen korvaussalakirjoitus, Ohjaajan tila, uusi peruskieli, algoritminen salakirjoitus), luo valmiin YAML-mallin, ja vaikeammissa tapauksissa generoi muotoillun kehotteen liitettäväksi ChatGPT:hen / Claudeen.
* **Refaktorointi v13.0 — säännöt YAML-tiedostoissa:** Kaikki aksentit, salakirjoitukset ja AI-tilat, jotka versioon 12.0 asti olivat "kovakoodattuja" vakioita Python-koodissa, on siirretty deklaratiivisiin `.yaml`-tiedostoihin, jotka ladataan dynaamisesti sovelluksen käynnistyessä. Jokainen, joka osaa käyttää Muistiota, voi hienosäätää aksenttia (esim. vaihtaa `sz → sh` muotoon `sz → sch`), lisätä uuden kielen tai jopa muuttaa AI:n järjestelmäkehotteen ääntä — ilman koodin kääntämistä.


## Monikielisyys (9 kieltä luonnollisesti)

Versiosta v14.0 lähtien sovellus tukee luonnollisesti 9 peruskieltä: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Jokainen `dictionaries/<kod>/`-paketti sisältää diakriittiset merkit, aakkoset ja foneettiset säännöt, jotka toimivat kyseisen kielen tekstissä — sovellus tunnistaa lähdekielen automaattisesti lingua-language-detectorin avulla (kappaleittain) ja lataa sopivan paketin jokaiselle osalle erikseen.

Koko käyttöliittymä, dokumentaatio (`docs/manual.<iso>.html`) ja suurin osa järjestelmäviesteistä ovat luonnollisesti saatavilla kaikilla tuetuilla kielillä. AI-järjestelmäkehotteet Ohjaajan ja Tarinan tiloissa on kirjoitettu kohdekielillä (käsin, ei automaattisesti käännettynä — katso `dictionaries/<kod>/rezyser/` ja `dictionaries/<kod>/opowiesci/`).


## AI-arkkitehtuuri ja käytetyt mallit

Suositeltu ja oletusarvoinen AI-palveluntarjoaja on Anthropic (Claude) — kaikki järjestelmäpromptit on hienosäädetty juuri sitä varten, joten se tuottaa korkealaatuisimman narratiivin, maailman sääntöjen parhaan noudattamisen ja luonnollisimman proosan. Siirtyminen Claudeen tapahtui vaiheittain (Ohjaaja versiossa 18.0, Tarinat versiossa 18.1, Polyglootti ja jälkituotanto versiossa 18.2) — muutos perustui empiirisesti vahvistettuun etuun maailman sääntöjen noudattamisessa, proosan luonnollisuudessa ja kliseiden välttämisessä.

* **Anthropic Claude Sonnet 5 (oletusarvoinen laadun peruspilari):** Koko sovelluksen älyn moottori. Vastaa luovasta narraatiosta (skriptien ohjaamisesta, perinteisen Äänikirjaproosan kirjoittamisesta, Aivoriihestä sekä KAIKISTA Tarinat-tiloista — Valinnat, Pienempi Paha, Vapaa — mukaan lukien Cinematic-yhteenvetojen ja välikohtausten generointi), edistyneistä käännöksistä säilyttäen monilohkoisen kontekstin (Polyglootti), sekä pienemmistä osatehtävistä: lukujen iteratiivisesta kirjallisesta nimeämisestä ja sisällön kielikoodin tunnistamisesta.

* **Oma OpenAI-yhteensopiva päätepiste (edistynyt vaihtoehto, versiosta 18.4 alkaen):** Anthropicin sijaan voi käyttää mitä tahansa OpenAI:n API:n kanssa yhteensopivaa päätepistettä (OpenRouter, Groq, Fireworks, DeepSeek, paikallinen Ollama, OpenAI-yhteensopiva Gemini ja muut) — yhdellä, yhteisellä koodipolulla, ilman erillistä integraatiota kutakin palveluntarjoajaa varten. Asetukset tehdään `golden_key.env`-tiedostossa (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `OPENAI_API_KEY`); täydelliset ohjeet löytyvät pääkäyttöoppaasta (VAIHE 2B). Muut mallit saattavat tuottaa Claudea heikomman laadun, sillä promptit on hienosäädetty juuri sitä varten — tämä on käyttäjän tietoinen valinta kustannusten ja laadun välillä.


### Tunnetut mallien rajoitukset (Anti-Closure)

Huolimatta tiukkojen järjestelmäohjeiden toteuttamisesta, jotka edellyttävät toiminnan katkaisemista jännityksen hetkellä (ns. Anti-Closure-direktiivi), nykyaikaisilla LLM-malleilla on vahva, synnynnäinen taipumus "sulkea" tarinoita. Tämä johtaa usein ei-toivottujen johtopäätösten, moraalien tai väärien "onnellisten loppujen" sisällyttämiseen, erityisesti Perinteisen Äänikirjan Tilassa.

Tämä on nykyisen sukupolven tekoälyn perustavanlaatuinen rajoitus. Tästä syystä sovellus tallentaa projektit tavallisina, helposti muokattavina tekstimuotoisina tiedostoina (`.txt`). Tämä edellyttää käyttäjältä elävän leikkaajan roolin omaksumista — AI:n luomien viimeisten, "sulkevien" lauseiden satunnaista, manuaalista poistamista, minkä jälkeen muisti synkronoidaan korjatun tiedoston kanssa „Päivitä levyltä" -painikkeella, ja työtä jatketaan.


## Asennus ja käynnistys

### Loppukäyttäjille (Windows)

1. Lataa uusin julkaisu **Releases**-välilehdeltä (paketti merkitty *Latest*) — tiedosto `Rezyser_Audio_v<numer>_Installer.exe`. Käynnistä se kaksoisnapsauttamalla. Asennusohjelma sijoittuu oletuksena käyttäjätilisi paikalliseen hakemistoon (`%LocalAppData%\Programs\Reżyser Audio GPT`) eikä vaadi järjestelmänvalvojan oikeuksia; voit valita oman polun "Przeglądaj"-painikkeella. Asennuksen jälkeen ohjelma luo pikakuvakkeet Käynnistä-valikkoon ja työpöydälle, ja vaihtoehtoisesti avaa käyttöohjeen oletuksena määritetyssä `.txt`-tiedostojen editorissa.
2. **Anthropic API -määritys:** Ensimmäisellä käynnistyskerralla sovellus ilmoittaa puuttuvasta avaimesta System Check -osiossa. Napsauta näkyvää painiketta luodaksesi `golden_key.env`-tiedoston, avaa se tekstieditorissa ja liitä Anthropic-avaimesi (joka alkaa merkkijonolla `sk-ant-`).
3. **Ensiaskeleet:** Avaa tiedosto `docs/manual.pl.html` (tai muunkielinen versio) asennuskansiosta — se on täydellinen käyttöohje, joka on kirjoitettu kaikkien käyttäjien ymmärtämällä kielellä, ei pelkästään kehittäjille.


### Kehittäjille (clone + setup)

1. Kloonaa arkisto levyllesi.
2. Suorita tiedosto `setup_dev.bat` luodaksesi automaattisesti virtuaalisen ympäristön (`.venv/`) ja ladataksesi riippuvuudet `requirements.txt`-tiedostosta.
3. Käynnistä sovellus komennolla `python main.py` tai tiedoston `run_dev.bat` kautta.

`.sh`-skriptit macOS/Linuxille poistettiin versiossa 13.1 — kehitysympäristö keskittyy Windowsiin NVDA:n saavutettavuustestien erityispiirteiden vuoksi. Koodin kanssa työskentely muilla järjestelmillä on mahdollista, mutta vaatii manuaalista asennusta: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Julkaisupakettien rakennusskriptit** (`build_release.py`, `rezyser_audio.spec`, `installer.iss`) on tarkoitettu ainoastaan Windows-pakettien luomiseen. Versiosta 17.0 alkaen `build_release.py` jäädyttää sovelluksen PyInstallerilla (onedir + windowed) `rezyser_audio.spec`-tiedoston mukaisesti — tuottaa `dist/`-hakemiston, jossa on alkuperäinen `.exe` ja bundlen `runtime/`-kansio (tulkki + kirjastot). Manuaalisesti ladattua siirrettävää Pythonia ei enää tarvita arkistoon; `dist/` ja `build/`-hakemistot ovat `.gitignore`-tiedostossa.


## Täydellinen dokumentaatio

Tämä README on vain projektin arkkitehtoninen luonnos. Jos haluat oppia kehittyneitä tekniikoita AI-harhojen estämiseksi, yhteensopivien puhesyntetisaattoreiden (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices) asennusohjeita, täydellisen kuvauksen Tarinat-tiloista sekä täydellisen käyttöoppaan, tutustu `docs/`-kansiossa oleviin tiedostoihin:

* `docs/manual.<iso>.html` — pääasiallinen käyttöohje (kirjoitettu loppukäyttäjälle).
* `docs/tales.<iso>.html` — Tarinat-tilan ohjekirja (interaktiiviset tekstipelit).
* `docs/dictionaries.<iso>.html` — ohjeet lingvisteille ilman Pythonia, kuinka lisätä omia aksentteja/salauksia/AI-tiloja.

Jokainen näistä tiedostoista on saatavilla 9 kielellä — suffiksi `.<iso>.html` (esim. `manual.pl.html`, `manual.en.html`, `manual.de.html`).


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
