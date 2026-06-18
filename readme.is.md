# Reżyser Audio GPT

**Híbríð Hljóðver fyrir Hljóðleiki, Hljóðbækur og Gagnvirkar Sögur**

**Aðrar tungumál útgáfur / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Safn sjálfstæðra verkfæra knúin af gervigreind til sjálfvirkrar ritunar, skipulagningar, sniðmáts og þýðingar á umfangsmiklum handritum og til að stýra gagnvirkum textaleikjum. Verkefnið er innfæddur skjáborðsforrit (wxPython) hannað frá grunni með fullu aðgengi fyrir skjálesara (NVDA, VoiceOver) og samhæfni við faglega talgervla (TTS). Það virkar án vafra og án staðbundins netþjóns — keyrir sem venjulegur gluggi forrits.

Útgáfa: **18.2** · Stutt tungumál innfædd (9): Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Helstu einingar

Forritið sameinar fimm verkfæri í einum glugga sem hægt er að skipta á milli með lyklaborðssamsetningum (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 / Ctrl+5) eða með hnöppum á tækjastikunni. Hver eining virkar sjálfstætt, en allar deila orðabókarskrám úr möppunni `dictionaries/` (hreim, dulmál, skapandi AI stillingar) og miðlægum stillingum.


### 1. Leikstjórn (Ctrl+1)

Aðalstúdíó fyrir skrif á hljóðleikritum og hljóðbókum. Þú velur ham — Hugstormun, Handrit (með merkjum `[SFX]`/`[Persóna: tilfinning]`), Hljóðbók (hefðbundið prósa) — og stýrir samtali við líkanið í gegnum leiðbeiningareitinn + Heimsbók + Langtímaminni:

* **Heimsbók margra verkefna:** Kerfið hleður sjálfkrafa í bakgrunni sérstökum reglum alheimsins (`.md`) á grundvelli virks upprunaskrár, sem tryggir fullkomna einangrun (núll-smell samhengishleðsla).
* **Sögugeymir:** „Óendanlegt minni“ reiknirit. Þegar minnivísirinn fer í rauða viðvörunarástandið, býr kerfið sjálfkrafa til sögusamantekt og skráir hana í Langtímaminni.
* **4 skapandi hamir:** Hver skrá í `dictionaries/<jzk>/rezyser/` lýsir sérstakri „persónuleika“ AI leikstjórans (Hugstormun, Handrit, Hljóðbók, Eftirvinnsla titla). Þú getur stillt hljóm þeirra án forritunar — sjá Reglustjóri hér að neðan.


### 2. Opowieści (Ctrl+2, annar aðalstilling frá v15.0)

Gagnvirkir textaleikir stjórnaðir af gervigreind sem gegnir hlutverki frásagnarmótors. Ólíkt Reżyserii (þar sem þú býrð til tilbúinn hljóðbók), eru Opowieści skref-fyrir-skref kvik frásögn:

* **Valmöguleikastilling:** hvert skref endar með 3-5 tölusettum valkostum A-E. Mest innsæi stilling fyrir blinda leikmenn — NVDA les valkostina, þú smellir á Tab og Enter.
* **Minna Illa Stilling:** eins og Valmöguleikar, en hver valkostur er siðferðilega, líkamlega eða strategískt óhagstæður. Frá v15.2 er viðbótar „flaska" — endurnýtanlegur NÚLL-númeraður valkostur örvæntingarfullrar björgunar, þar sem áhrifin eru gervilöng (60% skaðleg / 30% truflandi skynjun / 10% sjaldan-hagstæð, dreifing þvinguð af Python, LLM getur ekki fundið upp á bjargandi niðurstöðu).
* **Frjáls Stilling:** hvaða aðgerð sem er með frjálsum texta („ég mun reyna að opna dyrnar"), mótorinn leggur til 1-3 tillögur en þvingar ekki val.
* **Einn AI líkan fyrir allar stillingar:** frá v18.1 nota allar stillingar Opowieści Anthropic Claude Sonnet 4.6 — öflugra líkan sem fylgir ströngum reglum heimsins (sérstaklega mikilvægt í Minna Illa Stilling, þar sem hver valkostur verður að vera raunverulega óhagstæður).


### 3. Fjöltyngdur (Ctrl+3, AI Þýðandi + TTS Hreimur)

* **Öruggur Þýðandi:** Langir textar eru sjálfkrafa skiptir í einingar sem mældar eru í tókum líkansins (öruggt einnig fyrir þétt rituð tungumál, t.d. kínversku) og þýddir í röð; afklippt svar líkansins er greint og reynt aftur á minni hlutum. Hver eining er samstundis vistuð í falinni `.jsonl` skrá. Endurræsing eftir að API takmörk eru náð er fullkomlega sjálfvirk.
* **Sjálfvirkni NVDA:** Þýðingar eru vistaðar sem tilbúnar `.html` skrár með innbyggðum tungumálamerkjum eða `.docx` skrár með merkjum sem eru sprautað beint inn í XML uppbygginguna.
* **8 staðbundnir hreimar:** Möguleiki á að þvinga fram brotinn hreim fyrir staðbundna hljóðgjafa (Tiflotecnia Voices, eSpeak, OneCore) með háþróuðum regex reglum. Studdir erlendir hreimar: enska, rússneska (með transliteringu á kyrillísku), franska, þýska, spænska, ítalska, finnska, pólsku.
* **Dulkóðunarhamur:** 6 staðbundin reiknirit til að afmynda texta — frá því að lesa afturábak, í gegnum typoglycemíu, til klassískrar Cæsar dulkóðunar. Hvert með staðbundnu stafrófi tungumálapakkans (t.d. Cæsar dulkóðun með 35-stafa íslensku stafrófi með diakritískum merkjum).
* **Merkingarviðgerð:** Sprautar á óskaðlegan hátt inn gefnum ISO tungumálakóða — einnig svæðisbundnum, t.d. pt-BR eða zh-CN — í núverandi skrár.


### 4. Umbreytingartæki / Hljóðbókararkitekt (Ctrl+4)

* Vinnur úr hráum `.txt` eða `.docx` skrám fyrir lyklaborðsleiðsögn fyrir NVDA og kerfi eins og ElevenLabs.
* Breytir sjálfkrafa lykilorðum (Þáttur, Kafli, Formáli) í „Heading 1" fyrirsagnir í Word skjali og hreinsar einnig óþarfa HTML og Markdown merki.
* Frá og með v15.1 hópar 5 umferðir í senur með H1 fyrirsögnum (sjálfvirk greining á Sögu) — undirbýr skrá sem er búin til af Sögumáta fyrir hefðbundna útgáfu hljóðbóka.


### 5. Reglustjóri (Ctrl+5, nýjung frá v13.0)

* **Orðabókarleitari án Pythons:** Sjónrænt tré allra YAML skráa í `dictionaries/` möppunni — hljóðblæir, dulmál, skapandi hamir Leikstjóra og Sagna. Málfræðingur eða þýðandi getur skoðað, afritað, breytt og eytt reglum beint úr GUI.
* **Nýr reglusköpunarforritari:** Form með val á tegund (hljóðblær, hreint skiptidulmál, Leikstjórahamur, nýtt grunnmál, reikniritadulmál) sem býr til tilbúið YAML sniðmát, og fyrir erfiðari tilfelli býr til sniðinn prompt til að líma í ChatGPT / Claude.
* **Endurskipulagning v13.0 — reglur í YAML-skrám:** Allir hljóðblæir, dulmál og AI-stillingar, sem í útgáfu 12.0 voru „innbyggðar" fastar í Python kóða, hafa verið færðar yfir í lýsandi `.yaml` skrár sem eru lesnar inn á dynamískan hátt við ræsingu forritsins. Hver sem er sem getur notað Notepad getur stillt hljóðblæ (t.d. breytt `sz → sh` í `sz → sch`), bætt við nýju tungumáli, eða jafnvel breytt hljómi kerfisprompt fyrir AI — án þess að þurfa að umbreyta kóða.


## Fjöltyngd (9 tungumál innfædd)

Frá og með v14.0 styður forritið 9 innfædd tungumál: Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Hver pakki `dictionaries/<code>/` inniheldur kommur, stafróf og hljóðfræðireglur sem starfa á texta á því tiltekna tungumáli — forritið greinir sjálfkrafa upprunamál með lingua-language-detector (per málsgrein) og hleður viðeigandi pakka fyrir hvern hluta sérstaklega.

Allt GUI viðmót, skjöl (`docs/manual.<iso>.txt`) og flest kerfisskilaboð eru fáanleg innfædd á hverju af studdu tungumálunum. Kerfisboð AI í Leikstjóra og Söguham eru skrifuð á markmálinu (handvirkt, ekki sjálfvirkt þýdd — sjá `dictionaries/<code>/rezyser/` og `dictionaries/<code>/opowiesci/`).


## Gerð gervigreindar og notuð líkön

Frá og með útgáfu 18.2 notar forritið einn API-þjónustuaðila — Anthropic — og eitt líkan fyrir öll verkefni gervigreindar:

* **Anthropic Claude Sonnet 4.6:** Vélin á bak við ALLA greind forritsins. Hún sér um skapandi frásögn (leikstjórn handrita, ritun hefðbundinnar hljóðbókarprósu, Hugflóð og ALLAR Söguhamur — Val, Minna Illt, Frjálst — ásamt myndun samantekta og Cinematic-millileikja), háþróaðar þýðingar með varðveislu samhengis yfir mörg blokkir (Poliglota), auk smáverkefna: endurtekið úthlutun bókmenntalegs titils á kafla og greining á tungumálakóða innihalds. Samþjöppunin á Claude fór fram í áföngum (Reżyser í v18.0, Opowiesci í v18.1, Poliglota og eftirvinnsla í v18.2) — hún leiddi af reynslulegri staðfestri yfirburðum í því að fylgja reglum heimsins, náttúruleika prósu og forðast klisé.


### Þekkt takmörk módela (Anti-Closure)

Þrátt fyrir innleiðingu strangra kerfisleiðbeininga sem krefjast þess að stöðva aðgerðir á spennustundum (svokölluð Anti-Closure leiðbeining), hafa nútíma LLM módel sterka, meðfædda tilhneigingu til að „loka" sögum. Þetta leiðir oft til óæskilegra niðurstaðna, siðferðis eða falskra „hamingjusamra enda", sérstaklega í Hefðbundnum Hljóðbókaham.

Þetta er grundvallartakmörkun núverandi kynslóðar gervigreindar. Af þessum sökum geymir forritið verkefni í venjulegum, auðveldum til að breyta textaskrám (`.txt`). Þetta krefst þess að notandinn taki á sig hlutverk lifandi klippara — að fjarlægja handvirkt síðustu, „loka" setningar sem AI hefur búið til, og samstilla síðan minnið við leiðréttu skrána með hnappnum „Endurhlaða af diski", og halda vinnunni áfram.


## Uppsetning og ræsing

### Fyrir notendur (Windows)

1. Sæktu nýjustu útgáfuna í flipanum **Releases** (pakkinn merktur *Latest*) — skráin `Rezyser_Audio_v<numer>_Installer.exe`. Keyrðu hana með tvöföldu smelli. Uppsetningarforritið setur sjálfgefið upp í staðbundna möppuna á reikningnum þínum (`%LocalAppData%\Programs\Reżyser Audio GPT`) og krefst ekki stjórnandaheimilda; þú getur valið þína eigin slóð með hnappinum „Przeglądaj". Að uppsetningunni lokinni eru búin til flýtitákn í Start-valmyndinni og á skjáborðinu, og valfrjálst opnar forritið notendahandbókina í sjálfgefnum `.txt`-ritli.
2. **Stilling Anthropic API:** Við fyrstu ræsingu mun forritið gefa til kynna að lykill vanti í hlutanum System Check. Smelltu á sýnilega hnappinn til að búa til skrána `golden_key.env`, opnaðu hana í textaritli og límdu inn Anthropic-lykilinn þinn (sem byrjar á `sk-ant-`).
3. **Fyrstu skref:** Opnaðu skrána `docs/manual.pl.txt` (eða á öðru tungumáli) í uppsetningarmöppunni — þetta er full notendahandbók skrifuð á tungumáli sem er aðgengilegt öllum notendum, ekki bara forritarar.


### Fyrir forritara (afrita + uppsetning)

1. Afritaðu geymsluna á diskinn þinn.
2. Keyrðu skrána `setup_dev.bat` til að búa sjálfkrafa til sýndarumhverfi (`.venv/`) og sækja nauðsynjar úr `requirements.txt`.
3. Keyrðu forritið með skipuninni `python main.py` eða í gegnum skrána `run_dev.bat`.

`.sh` skriftur fyrir macOS/Linux voru fjarlægðar í v13.1 — þróunarumhverfið er einbeitt á Windows vegna sérstöðu NVDA aðgengisprófa. Vinna með kóðann á öðrum kerfum er möguleg, en krefst handvirkrar uppsetningar: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Byggingarskriftur fyrir útgáfupakka** (`build_release.py`, `rezyser_audio.spec`, `installer.iss`) eru eingöngu til að búa til pakka fyrir Windows. Frá útgáfu 17.0 frystir `build_release.py` forritið með PyInstaller (onedir + windowed) samkvæmt `rezyser_audio.spec` — framleiðir `dist/` með innfæddri `.exe` og möppu `runtime/` (túlkur + bókasöfn). Engin þörf er lengur á flutningshæfu Python sem er hlaðið handvirkt inn í geymsluna; möppur `dist/` og `build/` eru í `.gitignore`.


## Full skjal

Þetta README er aðeins uppbyggingarútdráttur verkefnisins. Til að læra um háþróaðar aðferðir til að koma í veg fyrir ofskynjanir AI, uppsetningarleiðbeiningar fyrir samhæfða talgervla (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices), fulla lýsingu á sögumódum með flösku, og fullkomna notendahandbók, skoðaðu skrárnar í `docs/` möppunni:

* `docs/manual.<iso>.txt` — aðalnotendahandbókin (skrifuð fyrir endanotanda).
* `docs/tales.<iso>.txt` — handbók fyrir sögumóða (gagnvirkir textaleikir).
* `docs/dictionaries.<iso>.txt` — leiðbeiningar fyrir málfræðinga án Python, um hvernig á að bæta við eigin hreim/sifrum/AI-móda.

Hver af þessum skrám er fáanleg á 9 tungumálum — viðskeyti `.<iso>.txt` (t.d. `manual.pl.txt`, `manual.en.txt`, `manual.de.txt`).


### Pólskt heiti — leiðarvísir fyrir þá sem eru utan pólska tungumálasvæðisins

Aðaltungumál þessa verkefnis er pólska. Nöfn eininga, flokka, athugasemdir í kóða, sem og nöfn skráa og gagnamöppur eru á pólsku og — vegna afturvirkrar samhæfni og margmálavélar — eru vísvitandi EKKI þýdd eða breytt. Eftirfarandi orðalisti mun hjálpa forriturum og notendum macOS/Linux kerfa að átta sig á uppbyggingunni.

**Notendagagnamöppur (við hlið keyranlegrar skráar eða í verkefnamöppu):**

* `skrypty/` — *scripts*: verkefni Leikstjóraeiningarinnar (`.txt` með frásögn, `.md` með Heimsbók, `_streszczenie.txt`).
* `opowiesci/` — *stories*: skráningar á gagnvirkum sögum.
* `runtime/` — tvíþætt hlutverk: möppubúnt frystu forritsins (túlkur + bókasöfn) OG ílát fyrir falin verkefnagögn (`runtime/skrypty/`, `runtime/opowiesci/`).

**Undirmöppur fyrir frumgögn í `dictionaries/<tungumálakóði>/` (sýnilegt í Reglustjóra):**

* `podstawy.yaml` — *basics*: uppsetning og lýsigögn tungumálapakka.
* `akcenty/` — *accents*: hljóðreglur fyrir talgervla.
* `szyfry/` — *ciphers*: textadulkóðunarstillingar.
* `rezyser/` — *director*: skapandi hamir Leikstjóraeiningarinnar.
* `opowiesci/` — *stories*: hamir fyrir gagnvirkar sögur.
* `gui/` — viðmótstextar (`ui.yaml`) og skjalasniðmát.


## Leyfi

Verkefnið er gefið út undir **MIT** leyfi — fullur texti er í skránni [`LICENSE`](LICENSE) í aðalmöppu geymslunnar. Í stuttu máli: þú getur frjálst notað, afritað, breytt og dreift hugbúnaðinum (einnig í viðskiptalegum tilgangi), að því tilskildu að höfundarréttartilkynningin sé varðveitt. Hugbúnaðurinn er afhentur „eins og hann er", án nokkurrar ábyrgðar.
