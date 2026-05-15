# Reżyser Audio GPT

**Híbríð Hljóðver fyrir Hljóðleiki, Hljóðbækur og Gagnvirkar Sögur**

**Aðrar tungumál útgáfur / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Safn sjálfstæðra verkfæra knúin af gervigreind til sjálfvirkrar ritunar, skipulagningar, sniðmáts og þýðingar á umfangsmiklum handritum og til að stýra gagnvirkum textaleikjum. Verkefnið er innfæddur skjáborðsforrit (wxPython) hannað frá grunni með fullu aðgengi fyrir skjálesara (NVDA, VoiceOver) og samhæfni við faglega talgervla (TTS). Það virkar án vafra og án staðbundins netþjóns — keyrir sem venjulegur gluggi forrits.

Útgáfa: **15.2.6** · Stutt tungumál innfædd (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Helstu einingar

Forritið sameinar fimm verkfæri í einum glugga sem hægt er að skipta á milli með lyklaborðssamsetningum (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 / Ctrl+5) eða með hnöppum á tækjastikunni. Hver eining virkar sjálfstætt, en allar deila orðabókarskrám úr möppunni `dictionaries/` (hreim, dulmál, skapandi AI stillingar) og miðlægum stillingum.


### 1. Leikstjórn (Ctrl+1)

Aðalstúdíó fyrir skrif á hljóðleikritum og hljóðbókum. Þú velur ham — Hugstormun, Handrit (með merkjum `[SFX]`/`[Persóna: tilfinning]`), Hljóðbók (hefðbundið prósa) — og stýrir samtali við líkanið í gegnum leiðbeiningareitinn + Heimabók + Langtímaminni:

* **Heimabók margra verkefna:** Kerfið hleður sjálfkrafa í bakgrunni sérstökum reglum alheimsins (`.md`) á grundvelli virks upprunaskrár, sem tryggir fullkomna einangrun (núll-smell samhengishleðsla).
* **Sögugeymir:** „Óendanlegt minni“ reiknirit. Þegar minnivísirinn fer í rauða viðvörunarástandið, býr kerfið sjálfkrafa til sögusamantekt og skráir hana í Langtímaminni.
* **4 skapandi hamir:** Hver skrá í `dictionaries/<jzk>/rezyser/` lýsir sérstakri „persónuleika“ AI leikstjórans (Hugstormun, Handrit, Hljóðbók, Eftirvinnsla titla). Þú getur stillt hljóm þeirra án forritunar — sjá Reglustjóri hér að neðan.


### 2. Sögur (Ctrl+2, annar aðalhamur frá v15.0)

Gagnvirkir textaleikir stjórnaðir af AI sem frásagnavél. Ólíkt Leikstjórn (þar sem þú býrð til fullunninn hljóðbók), eru Sögur skref-fyrir-skref kvik frásögn:

* **Valhamur:** hvert skref endar með 3-5 tölusettum valkostum A-E. Mest innsæi hamur fyrir blinda leikmenn — NVDA les valkostina, þú smellir á Tab og Enter.
* **Minna Illa Hamur:** eins og Val, en hver valkostur er siðferðilega, líkamlega eða strategískt óhagstæður. Frá v15.2 er viðbótar „flaska" — endurnýtanlegur NÚLL-númeraður valkostur örvæntingarfullrar björgunar, þar sem áhrifin eru gervilöguð (60% skaðleg / 30% truflandi skynjun / 10% sjaldan-hagstæð, dreifing þvinguð af Python, LLM getur ekki fundið upp bjargandi áhrif).
* **Frjáls Hamur:** hvaða aðgerð sem er með frjálsum texta („ég reyni að opna dyrnar"), vélin leggur til 1-3 tillögur en þvingar ekki val.
* **AI-líkan per hamur:** Val og Minna Illa nota gpt-4o (betri siðferðileg röksemdafærsla), Frjáls notar gpt-4o-mini (ódýrari hagfræði spuna).


### 3. Fjöltyngdur (Ctrl+3, AI Þýðandi + TTS Hreimur)

* **Öruggur Þýðandi:** Langir textar eru sjálfkrafa skiptir í einingar allt að 10.000 stöfum og þýddir í röð. Hver eining er samstundis vistuð í falinni `.jsonl` skrá. Endurræsing eftir að API takmörk eru náð er fullkomlega sjálfvirk.
* **Sjálfvirkni NVDA:** Þýðingar eru vistaðar sem tilbúnar `.html` skrár með innbyggðum tungumálamerkjum eða `.docx` skrár með merkjum sem eru sprautað beint inn í XML uppbygginguna.
* **8 staðbundnir hreimar:** Möguleiki á að þvinga fram brotinn hreim fyrir staðbundna hljóðgjafa (Tiflotecnia Voices, eSpeak, OneCore) með háþróuðum regex reglum. Studdir erlendir hreimar: enska, rússneska (með transliteringu á kyrillísku), franska, þýska, spænska, ítalska, finnska, pólsku.
* **Dulkóðunarhamur:** 6 staðbundin reiknirit til að afmynda texta — frá því að lesa afturábak, í gegnum typoglycemíu, til klassískrar Cæsar dulkóðunar. Hvert með staðbundnu stafrófi tungumálapakkans (t.d. Cæsar dulkóðun með 35-stafa íslensku stafrófi með diakritískum merkjum).
* **Merkingarviðgerð:** Sprautar á óskaðlegan hátt inn gefnum tveggja stafa ISO tungumálakóða í núverandi skrár.


### 4. Umbreytingartæki / Hljóðbókararkitekt (Ctrl+4)

* Vinnur úr hráum `.txt` eða `.docx` skrám fyrir lyklaborðsleiðsögn fyrir NVDA og kerfi eins og ElevenLabs.
* Breytir sjálfkrafa lykilorðum (Þáttur, Kafli, Formáli) í „Heading 1" fyrirsagnir í Word skjali og hreinsar einnig óþarfa HTML og Markdown merki.
* Frá og með v15.1 hópar 5 umferðir í senur með H1 fyrirsögnum (sjálfvirk greining á Sögu) — undirbýr skrá sem er búin til af Sögumáta fyrir hefðbundna útgáfu hljóðbóka.


### 5. Reglustjóri (Ctrl+5, nýjung frá v13.0)

* **Orðabókarleitari án Pythons:** Sjónrænt tré allra YAML skráa í `dictionaries/` möppunni — hljóðblæir, dulmál, skapandi stillingar Leikstjóra og Sagna. Málfræðingur eða þýðandi getur skoðað, afritað, breytt og eytt reglum beint úr GUI.
* **Nýr reglusköpunarforritari:** Form með val á tegund (hljóðblær, hreint skiptidulmál, Leikstjórastilling, nýtt grunnmál, reikniritadulmál) sem býr til tilbúið YAML sniðmát, og fyrir erfiðari tilfelli býr til sniðinn prompt til að líma í ChatGPT / Claude.
* **Endurskipulagning v13.0 — reglur í YAML-skrám:** Allir hljóðblæir, dulmál og AI-stillingar, sem í útgáfu 12.0 voru „innbyggðar" fastar í Python kóða, hafa verið færðar yfir í lýsandi `.yaml` skrár sem eru lesnar inn á dynamískan hátt við ræsingu forritsins. Hver sem er sem getur notað Notepad getur stillt hljóðblæ (t.d. breytt `sz → sh` í `sz → sch`), bætt við nýju tungumáli, eða jafnvel breytt hljómi kerfisprompt fyrir AI — án þess að þurfa að umbreyta kóða.


## Fjöltyngd (9 tungumál innfædd)

Frá og með v14.0 styður forritið 9 innfædd tungumál: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Hver pakki `dictionaries/<code>/` inniheldur kommur, stafróf og hljóðfræðireglur sem starfa á texta á því tiltekna tungumáli — forritið greinir sjálfkrafa upprunamál með lingua-language-detector (per málsgrein) og hleður viðeigandi pakka fyrir hvern hluta sérstaklega.

Allt GUI viðmót, skjöl (`docs/manual.<iso>.txt`) og flest kerfisskilaboð eru fáanleg innfædd á hverju af studdu tungumálunum. Kerfisboð AI í Leikstjóra og Söguham eru skrifuð á markmálinu (handvirkt, ekki sjálfvirkt þýdd — sjá `dictionaries/<code>/rezyser/` og `dictionaries/<code>/opowiesci/`).


## Arkitektúr AI og notuð líkön

Forritið skiptir verkefnum á snjallan hátt til að hámarka kostnað og hraða OpenAI API:

* **gpt-4o:** Aðalvél forritsins. Sér um þung verkefni sem krefjast sköpunargáfu: leikstjórn handrita, skrif á hefðbundinni prósa (Hljóðbók), valmöguleikar og Minna Illa í Sögum, samantektargerð og háþróuð þýðing með varðveislu margra samhengisblokka.
* **gpt-4o-mini:** Hratt, létt hjálparlíkan. Notað í bakgrunni fyrir örverkefni sem krefjast mikils hraða: endurtekin úthlutun bókmenntatitla til búinna kafla, útdráttur ISO kóða, Frjáls hamur í Sögum (hagkvæmari efnahagsleg frjáls texta spuni).


### Þekkt takmörk módela (Anti-Closure)

Þrátt fyrir innleiðingu strangra kerfisleiðbeininga sem krefjast þess að stöðva aðgerðir á spennustundum (svokölluð Anti-Closure leiðbeining), hafa nútíma LLM módel sterka, meðfædda tilhneigingu til að „loka" sögum. Þetta leiðir oft til óæskilegra niðurstaðna, siðferðis eða falskra „hamingjusamra enda", sérstaklega í Hefðbundnum Hljóðbókaham.

Þetta er grundvallartakmörkun núverandi kynslóðar gervigreindar. Af þessum sökum geymir forritið verkefni í venjulegum, auðveldum til að breyta textaskrám (`.txt`). Þetta krefst þess að notandinn taki á sig hlutverk lifandi klippara — að fjarlægja handvirkt síðustu, „loka" setningar sem AI hefur búið til, áður en skráin er hlaðin aftur og vinnan heldur áfram.


## Uppsetning og keyrsla

### Fyrir endanotendur (Windows)

1. Sæktu nýjustu útgáfuna úr **Útgáfur** flipanum (pakki merktur sem *Nýjasta*) — skrána `Rezyser_Audio_v<númer>_Installer.exe`. Keyrðu hana með tvísmelli. Uppsetningarforritið lendir sjálfgefið í staðbundinni möppu notandareiknings þíns (`%LocalAppData%\Programs\Reżyser Audio GPT`) og krefst ekki stjórnandaaðgangs; þú getur valið þína eigin slóð með „Vafra"-hnappinum. Eftir uppsetningu býr það til flýtileiðir í Start-valmyndinni og á skjáborðinu, og opnar valfrjálst notendahandbók í sjálfgefnum ritli fyrir `.txt`-skrár.
2. **Stilling OpenAI API:** Við fyrstu keyrslu mun forritið gefa til kynna skort á lykli í System Check hlutanum. Smelltu á sýnilegan hnapp til að búa til skrána `golden_key.env`, opnaðu hana í textaritli og límdu inn lykilinn þinn (sem byrjar á `sk-proj-`).
3. **Fyrstu skrefin:** Opnaðu skrána `docs/manual.pl.txt` (eða á öðru tungumáli) í uppsetningarmöppunni — þetta er full leiðarvísir skrifaður á tungumáli sem allir notendur geta skilið, ekki bara forritarar.


### Fyrir þróunaraðila (afrit + uppsetning)

1. Afritaðu geymsluna á diskinn þinn.
2. Keyrðu skrána `setup_dev.bat` til að búa sjálfkrafa til sýndarumhverfi (`.venv/`) og sækja nauðsynlegar skrár úr `requirements.txt`.
3. Keyrðu forritið með skipuninni `python main.py` eða með skránni `run_dev.bat`.

`.sh` skriftur fyrir macOS/Linux voru fjarlægðar í v13.1 — þróunarumhverfið er einbeitt á Windows vegna sérkenna NVDA aðgengisprófa. Vinna með kóðann á öðrum kerfum er möguleg, en krefst handvirkrar uppsetningar: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Skráir til að byggja útgáfupakka** (`build_release.py`, `installer.iss`) eru eingöngu ætlaðar til að búa til pakka fyrir Windows. Þær krefjast sérstaks möppu `runtime/` með flytjanlegri útgáfu af Python — þessi mappa er viljandi ekki hluti af geymslunni (hún er í `.gitignore`).


## Full skjal

Þetta README er aðeins uppbyggingarútdráttur verkefnisins. Til að læra um háþróaðar aðferðir til að koma í veg fyrir ofskynjanir AI, uppsetningarleiðbeiningar fyrir samhæfða talgervla (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices), fulla lýsingu á sögumódum með flösku, og fullkomna notendahandbók, skoðaðu skrárnar í `docs/` möppunni:

* `docs/manual.<iso>.txt` — aðalnotendahandbókin (skrifuð fyrir endanotanda).
* `docs/tales.<iso>.txt` — handbók fyrir sögumóða (gagnvirkir textaleikir).
* `docs/dictionaries.<iso>.txt` — leiðbeiningar fyrir málfræðinga án Python, um hvernig á að bæta við eigin hreim/sifrum/AI-móda.

Hver af þessum skrám er fáanleg á 9 tungumálum — viðskeyti `.<iso>.txt` (t.d. `manual.pl.txt`, `manual.en.txt`, `manual.de.txt`).
