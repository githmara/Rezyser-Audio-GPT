"""jezyki_lingua.py — kanon języków, które zna detektor `lingua`.

Statyczne LUSTRO enuma `lingua.Language` (75 języków w
`lingua-language-detector` 2.1.1): kod ISO 639-1 → (nazwa enuma, tradycyjna
polska nazwa języka). Powstało w v18.29.0 jako drugi etap standardu „zero
ciszy" — pierwszy (v18.28.0) sprawił, że nieczytelny plik przestaje znikać bez
słowa, ten sprawia, że o granicy detektora nie musi już wiedzieć CZŁOWIEK.

DLACZEGO PYTHON, A NIE YAML (decyzja maintainera 2026-09-08). Repozytorium
trzyma dane w YAML-u, a kanon jest wyjątkiem, bo importują go i runtime
(`manager_regul_szablony`, `core_poliglota`), i dev-toole (`audyt_podstaw`,
`audyt_leakow`, `refresh_languages`, `buduj_wielojezyczne_akcenty`). Jako
moduł wchodzi do bundla PyInstallera sam, bez wpisu w `installer.iss` i bez
liczenia ścieżek przez `sciezki.KATALOG_BAZOWY`. To NIE łamie obietnicy
„dodanie języka NIE wymaga Pythona": dodanie PACZKI to nadal nowy folder
`dictionaries/<kod>/`. Ten plik zmienia się wyłącznie wtedy, gdy nowy język
doda `lingua` — a że jest lustrem, nie źródłem, pilnuje tego bramka
`python audyt_podstaw.py --bramka` (kanon 1:1 wobec zainstalowanej
biblioteki: te same kody, te same nazwy enumów, zero nadwyżek i braków).

DWIE FORMY POLSKIEJ NAZWY. Kanon trzyma nazwę Z diakrytykami, a formę plikową
wyprowadza się z niej foldem :func:`fold_nazwy` (NFKD + ręczne `ł`) — jedno
źródło, obie formy, fold sprawdzony na 72 istniejących parach akcentowych
(`fiński` → `finski`, `włoski` → `wloski`). Do v19.3.1 fold mieszkał
w `buduj_wielojezyczne_akcenty` (dev-tool), więc RUNTIME nie miał jak zapytać
„jak ma się nazywać plik akcentu dla `iso`" — a to jest pytanie Managera Reguł,
czyli narzędzia end-usera. Dlatego funkcja stoi tu, a dev-tool ją woła; dwie
implementacje tego samego foldu byłyby dokładnie tym długiem, przed którym
ostrzega docstring `_ISO_PO_ENUMIE`.
Nazwa jest tym, czym są nazwy plików akcentów: IDENTYFIKATOREM wspólnym dla
wszystkich paczek, niezależnym od języka interfejsu. Dlatego każda musi
foldować się do unikalnych ASCII-liter — i dlatego `nb`/`nn` mają nazwy
ODRĘBNE (`norweski`/`nynorski`): `lingua` zna dwa norweskie standardy pisane
jako dwa osobne języki, więc jedna nazwa dla obu dałaby dwa języki o jednym
pliku.

FORMA TRADYCYJNA, NIE ZMUSZONY PRZYMIOTNIK (decyzja maintainera 2026-09-08).
Dla większości języków polska nazwa to przymiotnik (`szwedzki`, `chorwacki`,
`gudżaracki`), ale tam, gdzie polszczyzna przymiotnika nie utarła, kanon bierze
nazwę języka taką, jaką się jej używa (`hindi`, `urdu`, `telugu`, `marathi`,
`ganda`, `sotho`, `tsonga`, `tswana`, `shona`, `khosa`, `joruba`). Ta sama
reguła obowiązuje model pytany o nazwę języka POZA kanonem: ma podać formę
tradycyjną, a nie wymyślać przymiotnik od nazwy, której się tak nie odmienia.

Konsumenci kanonu (v18.29.0, uzupełnione w 19.4):
  * `buduj_wielojezyczne_akcenty` — nazwa pliku nowej pary akcentowej
    (kolejność: konsensus istniejących par → kanon → zadanie dla modelu),
  * `manager_regul_szablony` — prefill pola `lingua:` w szablonie `podstawy.yaml`
    (a dla kodu poza kanonem jawne „detektor tego języka nie obsługuje"),
  * `gui_manager_regul` — nazwa pliku akcentu WYLICZANA z pola „Kod ISO"
    (:func:`plik_akcentu`) zamiast wpisywanej z klawiatury, oraz rozstrzygnięcie
    „ta nazwa należy do języka, więc plik musi być akcentem",
  * `core_poliglota` — podpowiedź nazwy enuma przy `POWOD_LINGUA` wyliczana
    z ISO FOLDERA, więc jednoznaczna, a nie zgadywana `difflib`-em,
  * `audyt_leakow` — rozróżnienie „paczka poza Lingua" (legalnie obniżone
    pokrycie) od „paczka Z Lingui bez zadeklarowanego pola" (usterka),
  * `refresh_languages` — wartość wpisywana do `jezyki_docelowe.yaml`,
  * `audyt_podstaw` — orakuł dla kontroli pola `lingua:` oraz bramka 1:1.

Moduł jest CELOWO bezzależnościowy: żadnego importu `lingua`, `yaml`,
`argparse` ani dev-toola (`unicodedata` to biblioteka standardowa i wchodzi
do bundla i tak). Runtime importuje go bezpośrednio, a PyInstaller wciąga też
importy z ciał funkcji — każdy dev-import zaciągnąłby dev-toola do paczki
użytkownika (zmierzone 2026-08-30, patrz [[reguly_architektury]]).
"""
from __future__ import annotations

import unicodedata

# Kod ISO 639-1 (= nazwa folderu w `dictionaries/`) → (nazwa enuma
# `lingua.Language`, tradycyjna polska nazwa języka). Kolejność alfabetyczna
# po NAZWIE ENUMA — tak wypisuje je `Language.all()`, więc diff po aktualizacji
# biblioteki czyta się linia w linię.
KANON: dict[str, tuple[str, str]] = {
    "af": ("AFRIKAANS", "afrykanerski"),
    "sq": ("ALBANIAN", "albański"),
    "ar": ("ARABIC", "arabski"),
    "hy": ("ARMENIAN", "ormiański"),
    "az": ("AZERBAIJANI", "azerski"),
    "eu": ("BASQUE", "baskijski"),
    "be": ("BELARUSIAN", "białoruski"),
    "bn": ("BENGALI", "bengalski"),
    "nb": ("BOKMAL", "norweski"),
    "bs": ("BOSNIAN", "bośniacki"),
    "bg": ("BULGARIAN", "bułgarski"),
    "ca": ("CATALAN", "kataloński"),
    "zh": ("CHINESE", "chiński"),
    "hr": ("CROATIAN", "chorwacki"),
    "cs": ("CZECH", "czeski"),
    "da": ("DANISH", "duński"),
    "nl": ("DUTCH", "niderlandzki"),
    "en": ("ENGLISH", "angielski"),
    "eo": ("ESPERANTO", "esperancki"),
    "et": ("ESTONIAN", "estoński"),
    "fi": ("FINNISH", "fiński"),
    "fr": ("FRENCH", "francuski"),
    "lg": ("GANDA", "ganda"),
    "ka": ("GEORGIAN", "gruziński"),
    "de": ("GERMAN", "niemiecki"),
    "el": ("GREEK", "grecki"),
    "gu": ("GUJARATI", "gudżaracki"),
    "he": ("HEBREW", "hebrajski"),
    "hi": ("HINDI", "hindi"),
    "hu": ("HUNGARIAN", "węgierski"),
    "is": ("ICELANDIC", "islandzki"),
    "id": ("INDONESIAN", "indonezyjski"),
    "ga": ("IRISH", "irlandzki"),
    "it": ("ITALIAN", "włoski"),
    "ja": ("JAPANESE", "japoński"),
    "kk": ("KAZAKH", "kazachski"),
    "ko": ("KOREAN", "koreański"),
    "la": ("LATIN", "łaciński"),
    "lv": ("LATVIAN", "łotewski"),
    "lt": ("LITHUANIAN", "litewski"),
    "mk": ("MACEDONIAN", "macedoński"),
    "ms": ("MALAY", "malajski"),
    "mi": ("MAORI", "maoryski"),
    "mr": ("MARATHI", "marathi"),
    "mn": ("MONGOLIAN", "mongolski"),
    "nn": ("NYNORSK", "nynorski"),
    "fa": ("PERSIAN", "perski"),
    "pl": ("POLISH", "polski"),
    "pt": ("PORTUGUESE", "portugalski"),
    "pa": ("PUNJABI", "pendżabski"),
    "ro": ("ROMANIAN", "rumuński"),
    "ru": ("RUSSIAN", "rosyjski"),
    "sr": ("SERBIAN", "serbski"),
    "sn": ("SHONA", "shona"),
    "sk": ("SLOVAK", "słowacki"),
    "sl": ("SLOVENE", "słoweński"),
    "so": ("SOMALI", "somalijski"),
    "st": ("SOTHO", "sotho"),
    "es": ("SPANISH", "hiszpański"),
    "sw": ("SWAHILI", "suahili"),
    "sv": ("SWEDISH", "szwedzki"),
    "tl": ("TAGALOG", "tagalski"),
    "ta": ("TAMIL", "tamilski"),
    "te": ("TELUGU", "telugu"),
    "th": ("THAI", "tajski"),
    "ts": ("TSONGA", "tsonga"),
    "tn": ("TSWANA", "tswana"),
    "tr": ("TURKISH", "turecki"),
    "uk": ("UKRAINIAN", "ukraiński"),
    "ur": ("URDU", "urdu"),
    "vi": ("VIETNAMESE", "wietnamski"),
    "cy": ("WELSH", "walijski"),
    "xh": ("XHOSA", "khosa"),
    "yo": ("YORUBA", "joruba"),
    "zu": ("ZULU", "zuluski"),
}

# Odwrotność kanonu: NAZWA_ENUMA → ISO. Nazwy enumów są w `lingua` unikalne
# (a bramka `audyt_podstaw` pilnuje, że kanon jest lustrem), więc mapa jest 1:1.
_ISO_PO_ENUMIE: dict[str, str] = {nazwa: iso for iso, (nazwa, _) in KANON.items()}


def _norm(iso: str) -> str:
    """Kod ISO w postaci klucza kanonu (`  SV ` → `sv`)."""
    return iso.strip().lower() if isinstance(iso, str) else ""


def czy_w_lingua(iso: str) -> bool:
    """Czy detektor `lingua` zna język o tym kodzie ISO 639-1?

    Odpowiedź jest tu ROZSTRZYGNIĘCIEM, nie zgadywaniem — i to jest cała
    wartość tego modułu. Wołający może wreszcie odróżnić paczkę, której język
    detektor obsługuje (brak pola `lingua:` = usterka), od paczki, dla której
    detektora po prostu nie ma (brak pola = poprawna decyzja autora).
    """
    return _norm(iso) in KANON


def nazwa_enuma(iso: str) -> str | None:
    """Nazwa enuma `lingua.Language` dla kodu ISO (`sv` → ``"SWEDISH"``).

    ``None`` = język poza kanonem, czyli poza detektorem. Nazwa wraca WIELKIMI
    literami, bo taką wartość ma nosić pole `lingua:` w `podstawy.yaml`.
    """
    wpis = KANON.get(_norm(iso))
    return wpis[0] if wpis else None


def nazwa_polska(iso: str) -> str | None:
    """Tradycyjna polska nazwa języka (`sv` → ``"szwedzki"``), z diakrytykami.

    Forma plikowa (nazwa pliku akcentu) wyprowadza się z tego foldem
    :func:`fold_nazwy` — patrz docstring modułu.
    """
    wpis = KANON.get(_norm(iso))
    return wpis[1] if wpis else None


def fold_nazwy(nazwa: str) -> str:
    """`fiński` → `finski`, `włoski` → `wloski` (nazwa pliku = identyfikator).

    Nazwy plików akcentów są polskimi nazwami języków BEZ diakrytyków —
    zweryfikowane na 72 parach (`finski`, `wloski`, `hiszpanski`). Fold robimy
    przez NFKD plus ręczne `ł`, którego dekompozycja NIE rozbija.

    Przyjmuje nazwę, a nie kod ISO, bo obsługuje też języki POZA kanonem (tam
    nazwę podaje model albo człowiek) — dla kodu z kanonu jest
    :func:`plik_akcentu`, która składa oba kroki.
    """
    if not isinstance(nazwa, str):
        return ""
    bez_l = nazwa.replace("ł", "l").replace("Ł", "L")
    rozlozone = unicodedata.normalize("NFKD", bez_l)
    return "".join(z for z in rozlozone if not unicodedata.combining(z)).lower()


def plik_akcentu(iso: str) -> str | None:
    """Kanoniczna nazwa pliku akcentu dla kodu ISO (`bg` → ``"bulgarski"``).

    ``None`` = język poza kanonem, czyli poza detektorem. Wtedy nazwy NIE MA
    czym rozstrzygnąć i wołający musi zapytać człowieka — to jest ta sama
    granica, co przy polu `lingua:` (patrz :func:`czy_w_lingua`), i tak samo
    nie jest usterką paczki: faroeskiego, maltańskiego ani luksemburskiego
    `lingua` po prostu nie zna.

    Bez tej funkcji nazwa pliku akcentu była polem tekstowym: Manager Reguł
    przyjmował `ucraine.yaml` przy `iso: uk` (kanon: `ukrainski`), a Księga
    Świata takiego akcentu nigdy nie zawoła, bo `rozwiaz_nazwe_akcentu`
    porównuje wpisaną nazwę z `id` pliku ORAZ z natywnym przymiotnikiem
    z `etykieta` — nie z fantazją autora.
    """
    nazwa = nazwa_polska(iso)
    return fold_nazwy(nazwa) if nazwa else None


def iso_dla_pliku_akcentu(nazwa_pliku: str) -> str | None:
    """Kod ISO dla nazwy pliku akcentu (``"bulgarski"`` → `bg`); ``None`` gdy obca.

    Kierunek potrzebny tam, gdzie pytanie brzmi „czy ta nazwa NALEŻY do
    jakiegoś języka" — bo jeśli należy, plik musi być akcentem tego języka,
    a nie narzędziem Poligloty pod cudzą nazwą (defekt zmierzony 2026-09-17:
    `pl/akcenty/bulgarski.yaml` z `kategoria: naprawiacz` to działający,
    DRUGI naprawiacz tagów zajmujący nazwę akcentu bułgarskiego).
    """
    szukana = fold_nazwy(nazwa_pliku).strip()
    if not szukana:
        return None
    for iso in KANON:
        if plik_akcentu(iso) == szukana:
            return iso
    return None


def iso_dla_enuma(nazwa: str) -> str | None:
    """Kod ISO 639-1 dla nazwy enuma (``"SWEDISH"`` → `sv`); ``None`` gdy nieznana.

    Odwrotny kierunek jest potrzebny tam, gdzie znamy tylko wartość pola
    `lingua:` z paczki i pytamy, do którego folderu ona pasuje — czyli przy
    diagnozie „ta nazwa jest poprawna, ale należy do innego języka".
    """
    if not isinstance(nazwa, str):
        return None
    return _ISO_PO_ENUMIE.get(nazwa.strip().upper())
