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
wyprowadza się z niej foldem `buduj_wielojezyczne_akcenty.nazwa_pliku_akcentu`
(NFKD + ręczne `ł`) — jedno źródło, obie formy, fold sprawdzony na 72
istniejących parach akcentowych (`fiński` → `finski`, `włoski` → `wloski`).
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

Konsumenci kanonu (v18.29.0):
  * `buduj_wielojezyczne_akcenty` — nazwa pliku nowej pary akcentowej
    (kolejność: konsensus istniejących par → kanon → zadanie dla modelu),
  * `manager_regul_szablony` — prefill pola `lingua:` w szablonie `podstawy.yaml`
    (a dla kodu poza kanonem jawne „detektor tego języka nie obsługuje"),
  * `core_poliglota` — podpowiedź nazwy enuma przy `POWOD_LINGUA` wyliczana
    z ISO FOLDERA, więc jednoznaczna, a nie zgadywana `difflib`-em,
  * `audyt_leakow` — rozróżnienie „paczka poza Lingua" (legalnie obniżone
    pokrycie) od „paczka Z Lingui bez zadeklarowanego pola" (usterka),
  * `refresh_languages` — wartość wpisywana do `jezyki_docelowe.yaml`,
  * `audyt_podstaw` — orakuł dla kontroli pola `lingua:` oraz bramka 1:1.

Moduł jest CELOWO bezzależnościowy: żadnego importu `lingua`, `yaml`,
`argparse` ani dev-toola. Runtime importuje go bezpośrednio, a PyInstaller
wciąga też importy z ciał funkcji — każdy dev-import zaciągnąłby dev-toola do
paczki użytkownika (zmierzone 2026-08-30, patrz [[reguly_architektury]]).
"""
from __future__ import annotations

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
    `buduj_wielojezyczne_akcenty.nazwa_pliku_akcentu` — patrz docstring modułu.
    """
    wpis = KANON.get(_norm(iso))
    return wpis[1] if wpis else None


def iso_dla_enuma(nazwa: str) -> str | None:
    """Kod ISO 639-1 dla nazwy enuma (``"SWEDISH"`` → `sv`); ``None`` gdy nieznana.

    Odwrotny kierunek jest potrzebny tam, gdzie znamy tylko wartość pola
    `lingua:` z paczki i pytamy, do którego folderu ona pasuje — czyli przy
    diagnozie „ta nazwa jest poprawna, ale należy do innego języka".
    """
    if not isinstance(nazwa, str):
        return None
    return _ISO_PO_ENUMIE.get(nazwa.strip().upper())
