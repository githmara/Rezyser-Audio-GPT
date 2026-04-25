"""
core_poliglota.py – Silnik modułu „Poliglota AI".

Cały Python-owy „brain" modułu Poliglota: ładowanie reguł z plików YAML
w folderze ``dictionaries/`` i ich stosowanie wg wskazanego trybu i języka.

Publiczne API (prosty, wysokopoziomowy interfejs używany przez GUI):

    import core_poliglota

    # lista dostępnych wariantów (do wypełnienia ComboBoxa w GUI):
    core_poliglota.lista_wariantow(tryb="Rezyser",  jezyk="pl")
    core_poliglota.lista_wariantow(tryb="Szyfrant", jezyk="pl")

    # przetwarzanie tekstu:
    wynik = core_poliglota.przetworz(
        tekst,
        tryb="Szyfrant",       # lub "Rezyser"
        jezyk="pl",
        wariant="cezar",       # id z YAML (np. "islandzki", "odwracanie")
        przesuniecie=7,        # parametr zależny od algorytmu
    )

    # metadane pomocne przy zapisie pliku wynikowego:
    core_poliglota.kod_iso(tryb="Rezyser", jezyk="pl",
                           wariant="islandzki", opcje={})
    core_poliglota.sufiks_nazwy_pliku(tryb, jezyk, wariant,
                                      oryginalna_nazwa, opcje)
    core_poliglota.zapisz_wynik(...)          # HTML / DOCX / TXT z tagiem lang

Tłumacz AI (OpenAI) znajduje się w osobnym module: ``tlumacz_ai.py``.

Konwencja nazewnicza w YAML-ach (dictionaries/):

    dictionaries/
    └── <jezyk>/                          # "pl" (docelowo też "en", "de", …)
        ├── podstawy.yaml                  # polskie_znaki + alfabet
        ├── akcenty/                       # Tryb Reżysera
        │   └── <id>.yaml                  # np. islandzki.yaml
        └── szyfry/                        # Tryb Szyfranta
            └── <id>.yaml                  # np. odwracanie.yaml

Silnik skanuje te foldery leniwie (cache) i nie wymaga żadnej rejestracji
nowych plików w kodzie – wystarczy wrzucić YAML i uruchomić aplikację.
"""

from __future__ import annotations

import os
import random
import re
from typing import Any, Callable

import yaml

# python-docx potrzebne tylko do zapisu .docx – importujemy globalnie,
# bo GUI i tak ma tę zależność.
import docx
from docx.oxml.ns import qn
from docx.oxml.shared import OxmlElement

from num2words import num2words

# ``langdetect`` jest niedeterministyczny z założenia – ustawiamy seed, żeby
# w testach i walidacji dostawać powtarzalny wynik. Import leniwy: do funkcji
# ``wykryj_jezyk_zrodlowy`` – nigdzie indziej w module z niego nie korzystamy.
try:
    from langdetect import detect as _ld_detect, LangDetectException as _LdErr
    from langdetect import DetectorFactory as _LdFactory
    _LdFactory.seed = 0
except ImportError:                                             # pragma: no cover
    _ld_detect = None       # type: ignore[assignment]
    _LdErr = Exception      # type: ignore[misc,assignment]


# =============================================================================
# Ścieżki, stałe i cache
# =============================================================================
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DICTIONARIES_DIR = os.path.join(_ROOT_DIR, "dictionaries")

# Mapowanie nazw trybów → podfolderów języka
TRYB_REZYSER = "Rezyser"
TRYB_SZYFRANT = "Szyfrant"

_FOLDER_DLA_TRYBU: dict[str, str] = {
    TRYB_REZYSER:  "akcenty",
    TRYB_SZYFRANT: "szyfry",
}

# Cache wczytanych danych (thread-safe dla odczytu – yaml.safe_load zwraca kopię)
_CACHE_PODSTAWY:  dict[str, dict]       = {}          # jezyk → dict
_CACHE_WARIANTOW: dict[tuple[str, str], list[dict]] = {}   # (tryb, jezyk) → lista


# =============================================================================
# Funkcje niskiego poziomu – czyste, bezstanowe, używane przez akcenty i szyfry
# =============================================================================

def normalizuj_liczby(tekst: str) -> str:
    """Zamienia cyfrowe zapisy liczb na słowa (np. ``123`` → ``sto dwadzieścia trzy``).

    Używa ``num2words`` dla języka polskiego. Liczby, których biblioteka nie
    potrafi zapisać (np. bardzo duże), zostawia w oryginale.
    """
    def zamien(match: re.Match[str]) -> str:
        try:
            return num2words(match.group(), lang="pl")
        except Exception:
            return match.group()
    return re.sub(r"\d+", zamien, tekst)


def sklej_pojedyncze_litery(tekst: str) -> str:
    """Scala wiszące pojedyncze litery oddzielone spacją (np. „w y s” → „wys”)."""
    return re.sub(r"(?i)\b([a-z])\s+", r"\1", tekst)


def oczysc_tekst_tts(tekst: str, z_normalizacja: bool = True) -> str:
    """Oczyszcza tekst pod syntezator mowy (TTS).

    Usuwa:
      * bełkot onomatopeiczny („khh”, „pff”, „ahh”, …),
      * gwiazdki, znaki `=`, znaczniki Markdown (nagłówki),
      * nawiasy kwadratowe z przypisami reżyserskimi,
      * wielokrotne kropki i spacje,
      * frazy typu „z wplecionymi wdechami” (artefakty gpt-4).

    Jeśli ``z_normalizacja`` jest prawdziwe – dodatkowo zamienia cyfry
    na słowa (por. :func:`normalizuj_liczby`).
    """
    if z_normalizacja:
        tekst = normalizuj_liczby(tekst)
    tekst = re.sub(r"[\*=]+", "", tekst)
    tekst = re.sub(r"^#+\s*", "", tekst, flags=re.MULTILINE)
    tekst = re.sub(r"\([^)]*\)", "", tekst)
    tekst = re.sub(r"\b(khh|hh|pff|ahh|ehh)\b[\.\s]*", "... ", tekst, flags=re.IGNORECASE)
    tekst = re.sub(r"(?i)[,\s]*z\s*wplecionymi\s*wdechami", "", tekst)
    tekst = re.sub(r"(?i)[,\s]*z\s*wdech(em|ami)", "", tekst)
    tekst = re.sub(r"^\s*,\s*", "", tekst, flags=re.MULTILINE)
    tekst = re.sub(r"([!\?\.])\s*,\s*", r"\1 ", tekst)
    tekst = re.sub(r",\s*\.\.\.", "...", tekst)
    tekst = re.sub(r"(?:\.\s*){4,}", "... ", tekst)
    tekst = re.sub(r"([!\?\.])\s*\.\.\.\s*", r"\1 ", tekst)
    tekst = re.sub(r"^\s*\.\.\.\s*", "", tekst, flags=re.MULTILINE)
    tekst = re.sub(r"\.\.\.([^\s\.])", r"... \1", tekst)
    tekst = re.sub(r" {2,}", " ", tekst)
    return tekst.strip()


def procesuj_z_ochrona_tagow(tekst: str, funkcja: Callable[[str], str]) -> str:
    """Stosuje ``funkcja`` tylko do zwykłego tekstu, pomijając tagi HTML.

    Dzieli wejście na naprzemienne fragmenty „tekst” / „<tag>”; funkcja
    przetwarzająca trafia wyłącznie na pozycje parzyste listy.
    """
    parts = re.split(r"(<[^>]+>)", tekst)
    for i in range(0, len(parts), 2):
        parts[i] = funkcja(parts[i])
    return "".join(parts)


def _zastosuj_zamiany(tekst: str, zamiany: list[dict]) -> str:
    """Stosuje listę par ``{wzor, zamiana, regex?}`` z pliku YAML.

    Wzory oznaczone ``regex: true`` używają ``re.sub``, pozostałe są
    traktowane jako zwykłe stringi i zamieniane przez ``str.replace``.
    """
    for para in zamiany:
        wzor    = para.get("wzor", "")
        zamiana = para.get("zamiana", "")
        if para.get("regex"):
            tekst = re.sub(wzor, zamiana, tekst)
        else:
            tekst = tekst.replace(wzor, zamiana)
    return tekst


def _usun_polskie_znaki(tekst: str, podstawy: dict) -> str:
    """Transliteruje polskie diakrytyki wg listy z ``podstawy.yaml``.

    Funkcja NIE normalizuje liczb samodzielnie – to robi pipeline akcentu
    (flaga ``normalizuj_liczby`` w YAML-u akcentu).
    """
    return _zastosuj_zamiany(tekst, podstawy.get("polskie_znaki", []))


# =============================================================================
# Ładowanie plików YAML
# =============================================================================

def _zaladuj_yaml(sciezka: str) -> dict:
    """Wczytuje pojedynczy plik YAML i zwraca słownik (lub ``{}``)."""
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:  # noqa: BLE001
        print(f"[core_poliglota] Błąd wczytywania {sciezka}: {exc}")
        return {}
    return data if isinstance(data, dict) else {}


def _zaladuj_podstawy(jezyk: str) -> dict:
    """Zwraca dict z ``<jezyk>/podstawy.yaml`` (cache w pamięci)."""
    if jezyk in _CACHE_PODSTAWY:
        return _CACHE_PODSTAWY[jezyk]

    sciezka = os.path.join(DICTIONARIES_DIR, jezyk, "podstawy.yaml")
    if not os.path.exists(sciezka):
        print(f"[core_poliglota] Brak pliku podstaw dla jezyka {jezyk}: {sciezka}")
        _CACHE_PODSTAWY[jezyk] = {}
        return _CACHE_PODSTAWY[jezyk]

    _CACHE_PODSTAWY[jezyk] = _zaladuj_yaml(sciezka)
    return _CACHE_PODSTAWY[jezyk]


def _zaladuj_warianty(tryb: str, jezyk: str) -> list[dict]:
    """Zwraca listę wszystkich wariantów (akcentów/szyfrów) dla pary tryb+język.

    Rezultat jest sortowany wg pola ``kolejnosc`` (rosnąco) z YAML-i,
    a jako tie-breaker używana jest etykieta (alfabetycznie).
    """
    klucz = (tryb, jezyk)
    if klucz in _CACHE_WARIANTOW:
        return _CACHE_WARIANTOW[klucz]

    podfolder = _FOLDER_DLA_TRYBU.get(tryb)
    if podfolder is None:
        _CACHE_WARIANTOW[klucz] = []
        return []

    katalog = os.path.join(DICTIONARIES_DIR, jezyk, podfolder)
    if not os.path.isdir(katalog):
        _CACHE_WARIANTOW[klucz] = []
        return []

    warianty: list[dict] = []
    for nazwa_pliku in os.listdir(katalog):
        if not nazwa_pliku.lower().endswith((".yaml", ".yml")):
            continue
        cfg = _zaladuj_yaml(os.path.join(katalog, nazwa_pliku))
        if not cfg:
            continue
        if "id" not in cfg:
            cfg["id"] = os.path.splitext(nazwa_pliku)[0]
        if "etykieta" not in cfg:
            cfg["etykieta"] = cfg["id"]
        cfg.setdefault("kolejnosc", 999)
        warianty.append(cfg)

    warianty.sort(key=lambda c: (c.get("kolejnosc", 999), c.get("etykieta", "")))
    _CACHE_WARIANTOW[klucz] = warianty
    return warianty


# =============================================================================
# Publiczne API – listowanie i wyszukiwanie wariantów
# =============================================================================

def lista_wariantow(tryb: str, jezyk: str = "pl") -> list[dict]:
    """Zwraca listę wariantów do wypełnienia ComboBox w GUI.

    Każdy element to słownik z *przynajmniej* kluczami ``id``, ``etykieta``,
    ``opis``, ``iso``, ``kategoria``. GUI zazwyczaj interesuje tylko
    ``etykieta`` (widoczna w liście) i ``id`` (przekazywane do
    :func:`przetworz`). Pozostałe pola mogą być przydatne w tooltipach.
    """
    return list(_zaladuj_warianty(tryb, jezyk))


def wariant_po_id(tryb: str, jezyk: str, id_: str) -> dict | None:
    """Zwraca surową konfigurację wariantu (z YAML) po jego ``id``, lub ``None``."""
    for cfg in _zaladuj_warianty(tryb, jezyk):
        if cfg.get("id") == id_:
            return cfg
    return None


def wariant_po_etykiecie(tryb: str, jezyk: str, etykieta: str) -> dict | None:
    """Zwraca surową konfigurację wariantu po jego ``etykieta`` (widocznej w GUI)."""
    for cfg in _zaladuj_warianty(tryb, jezyk):
        if cfg.get("etykieta") == etykieta:
            return cfg
    return None


# =============================================================================
# Publiczne API – detekcja języka tekstu źródłowego (multi-language ready)
# =============================================================================
#
# Kontekst: dziś GUI Poligloty hardkoduje ``JEZYK_BAZOWY = "pl"`` i wywołuje
# ``langdetect.detect()`` tylko do ostrzegania użytkownika. Gdy powstaną
# drugie, trzecie `dictionaries/<kod>/`, GUI będzie musiał podmienić hardkod
# na wynik :func:`wykryj_jezyk_zrodlowy` – infrastruktura jest już gotowa.

def dostepne_jezyki_bazowe() -> list[str]:
    """Zwraca posortowaną listę kodów języków z folderów w ``dictionaries/``.

    Każdy folder musi zawierać plik ``podstawy.yaml`` – w przeciwnym razie
    zostaje pominięty (jest „niekompletnym" językiem, bo silnik Cezara
    potrzebuje jego alfabetu).

    Returns:
        np. ``["pl"]`` dziś, a po dodaniu ``dictionaries/en/`` → ``["en", "pl"]``.
    """
    if not os.path.isdir(DICTIONARIES_DIR):
        return []
    wynik: list[str] = []
    for nazwa in sorted(os.listdir(DICTIONARIES_DIR)):
        sciezka_jezyka = os.path.join(DICTIONARIES_DIR, nazwa)
        if not os.path.isdir(sciezka_jezyka):
            continue
        if os.path.isfile(os.path.join(sciezka_jezyka, "podstawy.yaml")):
            wynik.append(nazwa)
    return wynik


def lista_wspieranych_jezykow_natywnie() -> str:
    """Zwraca natywne nazwy wspieranych języków, gotowe do komunikatu GUI.

    Skanuje `dictionaries/<kod>/podstawy.yaml`, czyta pole `etykieta`
    i bierze prefiks przed separatorem ` – ` (em-dash z otaczającymi
    spacjami — konwencja przyjęta we WSZYSTKICH plikach `podstawy.yaml`).
    Format zwrotny to natywne nazwy języków rozdzielone przecinkami,
    z zachowaniem oryginalnych znaków (cyrylica, Þ, Æ itp.).

    Sortowanie hybrydowe: PL twardo na pierwszym miejscu (język bazowy
    i rdzeń projektu), pozostałe alfabetycznie po kodzie ISO. Dzięki
    temu wynik jest deterministyczny, a każdy nowo dodany folder
    `dictionaries/<kod>/` automatycznie wpada na właściwą pozycję
    w komunikacie — bez edycji żadnego stringa.

    Returns:
        Np. ``"Polski, English, Suomi, Русский, Íslenska, Italiano"``.
        Pusty string, gdy `dictionaries/` nie istnieje lub żaden
        język nie ma kompletnego `podstawy.yaml`.
    """
    kody = dostepne_jezyki_bazowe()
    if not kody:
        return ""

    if "pl" in kody:
        kolejnosc = ["pl"] + sorted(k for k in kody if k != "pl")
    else:
        kolejnosc = sorted(kody)

    natywne: list[str] = []
    for kod in kolejnosc:
        etyk = _zaladuj_podstawy(kod).get("etykieta", "")
        if not isinstance(etyk, str):
            continue
        # Splitujemy po em-dashu; gdy go brak (np. ktoś wpisał krótką
        # etykietę "Polski"), zostawiamy całość — fallback na cały string.
        nazwa = etyk.split(" – ", 1)[0].strip()
        if nazwa:
            natywne.append(nazwa)
    return ", ".join(natywne)


# Minimalna długość tekstu, przy której uznajemy ``langdetect`` za wiarygodny.
# Krótsze fragmenty często trafiają na „en" albo „af" bo model trenowany na
# Wikipedii ma przewagę angielskich słów (nawet w polskim tekście).
_MIN_TEKST_DLA_DETEKCJI = 20


def wykryj_jezyk_zrodlowy(
    tekst: str,
    *,
    fallback: str = "pl",
    dostepne: list[str] | None = None,
) -> str:
    """Wykrywa kod języka tekstu; waliduje wynik wobec ``dictionaries/``.

    Funkcja jest „konserwatywna" – zwraca ``fallback`` w każdym z wypadków,
    w których wynik langdetect byłby niemiarodajny:

      1. ``langdetect`` nie zostało zainstalowane (brak importu na starcie),
      2. ``tekst`` jest za krótki (<``_MIN_TEKST_DLA_DETEKCJI`` znaków
         po strip),
      3. ``langdetect`` rzuca ``LangDetectException`` (tekst bez liter,
         same emotikony itp.),
      4. wykryty kod NIE ma swojego folderu w ``dictionaries/`` – nawet
         jeśli langdetect trafił, silnik nie ma reguł dla tego języka,
         więc GUI musi pozostać przy języku, który ma działające słowniki.

    Dzięki punktowi (4) funkcja jest „multi-language ready": dziś zawsze
    zwraca ``"pl"`` (bo to jedyny dostępny język), ale gdy powstanie
    ``dictionaries/en/``, zacznie zwracać ``"en"`` dla angielskich tekstów.

    Args:
        tekst:    Tekst do zbadania (zwykle wczytana zawartość pliku).
        fallback: Co zwrócić, gdy detekcja się nie powiedzie lub wynik nie
                  ma swojego folderu w ``dictionaries/`` (domyślnie ``"pl"``).
        dostepne: Opcjonalna lista dozwolonych kodów. Jeśli ``None`` – funkcja
                  sama zawoła :func:`dostepne_jezyki_bazowe`. Zdefiniowanie
                  pozwala GUI odfiltrować języki, które akurat są wyłączone.

    Returns:
        Dwuliterowy kod ISO 639-1 (np. ``"pl"``, ``"en"``, ``"de"``).

    Example:
        >>> wykryj_jezyk_zrodlowy("Ala ma kota, a kot ma Alę i wychodzą razem.")
        'pl'
        >>> wykryj_jezyk_zrodlowy("???")          # za krótki + brak liter
        'pl'
        >>> wykryj_jezyk_zrodlowy("Hello world")  # „en" nie ma folderu
        'pl'
    """
    if _ld_detect is None:
        return fallback

    if not isinstance(tekst, str) or len(tekst.strip()) < _MIN_TEKST_DLA_DETEKCJI:
        return fallback

    try:
        kod_wykryty = _ld_detect(tekst)
    except _LdErr:
        return fallback

    if dostepne is None:
        dostepne = dostepne_jezyki_bazowe()

    return kod_wykryty if kod_wykryty in dostepne else fallback


# =============================================================================
# Tryb Reżysera – pipeline akcentu fonetycznego z pliku YAML
# =============================================================================

def _aplikuj_akcent_z_yaml(tekst: str, cfg: dict, podstawy: dict) -> str:
    """Uruchamia pięcioetapowy pipeline akcentu wg flag w ``cfg``.

    Etapy (wykonywane w stałej kolejności):
        1. ``czysc_tekst_tts``
        2. ``normalizuj_liczby``      (gdy nie użyto pełnego czyszczenia)
        3. ``usun_polskie_znaki``
        4. ``zamiany`` (właściwe reguły fonetyczne akcentu)
        5. ``skleja_pojedyncze_litery``
    """
    if cfg.get("czysc_tekst_tts"):
        tekst = oczysc_tekst_tts(tekst, z_normalizacja=cfg.get("normalizuj_liczby", False))
    elif cfg.get("normalizuj_liczby"):
        tekst = normalizuj_liczby(tekst)

    if cfg.get("usun_polskie_znaki"):
        tekst = _usun_polskie_znaki(tekst, podstawy)

    tekst = _zastosuj_zamiany(tekst, cfg.get("zamiany", []))

    if cfg.get("skleja_pojedyncze_litery"):
        tekst = sklej_pojedyncze_litery(tekst)

    return tekst


# ---------------------------------------------------------------------------
# Aliasy publiczne: akcent_* (kompatybilność wsteczna z gui_rezyser.py)
# ---------------------------------------------------------------------------
# Funkcje ``akcent_<język>`` stosują WYŁĄCZNIE reguły fonetyczne danego
# akcentu (normalizacja liczb + transliteracja + zamiany + scalanie
# pojedynczych liter), bez pełnego oczyszczania TTS. Dzięki temu moduł
# Reżysera może wywoływać je punktowo na pojedynczych kwestiach dialogowych
# bez ryzyka usunięcia ich zawartości (np. gwiazdek z didaskaliów).

def zastosuj_reguly_fonetyczne(tekst: str, wariant: str,
                               jezyk: str = "pl") -> str:
    """Stosuje reguły fonetyczne wybranego akcentu – bez czyszczenia TTS.

    Równoważne staremu ``akcent_*`` z pre-refaktorowej wersji: zachowuje
    gwiazdki, hashtagi i nawiasy kwadratowe (didaskalia), zmieniając
    wyłącznie fonetykę.
    """
    cfg = wariant_po_id(TRYB_REZYSER, jezyk, wariant) or {}
    podstawy = _zaladuj_podstawy(jezyk)
    tekst = normalizuj_liczby(tekst)
    tekst = _usun_polskie_znaki(tekst, podstawy)
    tekst = _zastosuj_zamiany(tekst, cfg.get("zamiany", []))
    return sklej_pojedyncze_litery(tekst)


# <GENEROWANE_AKCENTY_REZYSERA_START>
# UWAGA: Blok poniżej jest generowany automatycznie przez skrypt
# ``odswiez_rezysera.py``. NIE edytuj go ręcznie — edycje zostaną
# nadpisane przy najbliższym uruchomieniu skryptu (po dodaniu
# nowego pliku YAML w dictionaries/<język>/akcenty/).


def akcent_islandzki(tekst: str) -> str:
    """Alias: reguły fonetyczne akcentu ``islandzki`` (z ``dictionaries/pl/akcenty/islandzki.yaml``)."""
    return zastosuj_reguly_fonetyczne(tekst, "islandzki")


def akcent_angielski(tekst: str) -> str:
    """Alias: reguły fonetyczne akcentu ``angielski`` (z ``dictionaries/pl/akcenty/angielski.yaml``)."""
    return zastosuj_reguly_fonetyczne(tekst, "angielski")


def akcent_rosyjski(tekst: str) -> str:
    """Alias: reguły fonetyczne akcentu ``rosyjski`` (z ``dictionaries/pl/akcenty/rosyjski.yaml``)."""
    return zastosuj_reguly_fonetyczne(tekst, "rosyjski")


def akcent_francuski(tekst: str) -> str:
    """Alias: reguły fonetyczne akcentu ``francuski`` (z ``dictionaries/pl/akcenty/francuski.yaml``)."""
    return zastosuj_reguly_fonetyczne(tekst, "francuski")


def akcent_niemiecki(tekst: str) -> str:
    """Alias: reguły fonetyczne akcentu ``niemiecki`` (z ``dictionaries/pl/akcenty/niemiecki.yaml``)."""
    return zastosuj_reguly_fonetyczne(tekst, "niemiecki")


def akcent_hiszpanski(tekst: str) -> str:
    """Alias: reguły fonetyczne akcentu ``hiszpanski`` (z ``dictionaries/pl/akcenty/hiszpanski.yaml``)."""
    return zastosuj_reguly_fonetyczne(tekst, "hiszpanski")


def akcent_wloski(tekst: str) -> str:
    """Alias: reguły fonetyczne akcentu ``wloski`` (z ``dictionaries/pl/akcenty/wloski.yaml``)."""
    return zastosuj_reguly_fonetyczne(tekst, "wloski")


def akcent_finski(tekst: str) -> str:
    """Alias: reguły fonetyczne akcentu ``finski`` (z ``dictionaries/pl/akcenty/finski.yaml``)."""
    return zastosuj_reguly_fonetyczne(tekst, "finski")

# <GENEROWANE_AKCENTY_REZYSERA_END>


def _przetworz_rezyser(tekst: str, jezyk: str, cfg: dict, opcje: dict) -> str:
    """Rezyser: akcent / oczyszczenie / naprawiacz."""
    kategoria = cfg.get("kategoria", "")
    podstawy  = _zaladuj_podstawy(jezyk)

    # Naprawiacz tagów nie modyfikuje treści – wstrzyknięcie ISO dzieje
    # się na etapie :func:`zapisz_wynik`.
    if kategoria == "naprawiacz":
        return tekst

    # Oczyszczenie: brak zamian, ewentualnie bez normalizacji liczb.
    if kategoria == "oczyszczenie":
        return oczysc_tekst_tts(tekst, z_normalizacja=cfg.get("normalizuj_liczby", True))

    # Zwykły akcent – pipeline z ochroną tagów HTML.
    def _pipeline(fragment: str) -> str:
        return _aplikuj_akcent_z_yaml(fragment, cfg, podstawy)

    # Najpierw pełne oczyszczenie (z/bez normalizacji), potem zamiany –
    # tak, by oczyszczenie zdążyło usunąć bełkot jeszcze przed transliteracją.
    return procesuj_z_ochrona_tagow(tekst, _pipeline)


# =============================================================================
# Tryb Szyfranta – algorytmy (parametryzowane YAML-em)
# =============================================================================
# Każdy algorytm dostaje (tekst, cfg, podstawy, opcje) i zwraca string.
# `cfg`      – słownik wczytany z <szyfr>.yaml,
# `podstawy` – słownik wczytany z <język>/podstawy.yaml,
# `opcje`    – kwargs przekazane przez GUI do :func:`przetworz` (np. przesuniecie).

# Regex łapiący pojedyncze słowa (także z polskimi znakami diakrytycznymi)
_REGEX_SLOWA = r"\b[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+\b"


def _algo_odwracanie(tekst: str, cfg: dict, podstawy: dict, opcje: dict) -> str:
    """Rozwija skrótowce z YAML-a, a potem odwraca każde zdanie wspak.

    Kolejność:
      1. aplikuje listę ``rozwiniecia`` (regex, case-insensitive),
      2. usuwa powtórzenia słów (np. „bardzo bardzo” → „bardzo”),
      3. dzieli tekst na zdania i każde odwraca znak po znaku,
      4. zachowuje znak interpunkcyjny na końcu i kapitalizację pierwszej
         litery nowego (odwróconego) zdania.
    """
    for para in cfg.get("rozwiniecia", []):
        tekst = re.sub(para.get("wzor", ""), para.get("zamiana", ""),
                       tekst, flags=re.IGNORECASE)

    tekst = re.sub(r"\b(\w{2,})\s+\1\b", r"\1", tekst, flags=re.IGNORECASE)
    tekst = re.sub(r" +", " ", tekst)

    def odwracaj_zdanie(zdanie: str) -> str:
        if not zdanie.strip():
            return zdanie
        znak = ""
        if zdanie[-1] in ".?!":
            znak = zdanie[-1]
            zdanie = zdanie[:-1]
        odwrocone = zdanie[::-1].lower()
        if odwrocone:
            odwrocone = odwrocone[0].upper() + odwrocone[1:]
        return odwrocone + znak

    fragmenty = re.split(r"(?<=[.!?])(\s+)", tekst)
    wynik: list[str] = []
    for frag in fragmenty:
        if frag.isspace() or not frag:
            wynik.append(frag)
        else:
            wynik.append(odwracaj_zdanie(frag))
    return "".join(wynik)


def _algo_typoglikemia(tekst: str, cfg: dict, podstawy: dict, opcje: dict) -> str:
    """Miesza środek każdego słowa; pierwsza i ostatnia litera pozostaje.

    Słowa krótsze niż ``cfg['min_dlugosc_slowa']`` nie są zmieniane.
    """
    min_len = int(cfg.get("min_dlugosc_slowa", 4))

    def wymieszaj(match: re.Match[str]) -> str:
        slowo = match.group(0)
        if len(slowo) < min_len:
            return slowo
        srodek = list(slowo[1:-1])
        random.shuffle(srodek)
        return slowo[0] + "".join(srodek) + slowo[-1]

    return re.sub(_REGEX_SLOWA, wymieszaj, tekst)


def _algo_samogloskowiec(tekst: str, cfg: dict, podstawy: dict, opcje: dict) -> str:
    """Zamienia samogłoski na ``o``, zachowując polskie zmiękczenia."""
    # Krok 1 – zmiękczenia PRZED samogłoską (regex z lookahead)
    for para in cfg.get("zmiekszenia_przed_samogloska", []):
        tekst = re.sub(para.get("wzor", ""), para.get("zamiana", ""), tekst)

    # Krok 2 – zmiękczenia PRZED spółgłoską (plain string replace)
    for para in cfg.get("zmiekszenia_przed_spolgloska", []):
        tekst = tekst.replace(para.get("wzor", ""), para.get("zamiana", ""))

    # Krok 3 – samogłoski → 'o' / 'O'
    male  = cfg.get("samogloski_male", "aeiyuąęó")
    duze  = cfg.get("samogloski_wielkie", "AEIYUĄĘÓ")
    tekst = re.sub(f"[{male}]", cfg.get("zamiana_samogloski_male", "o"),    tekst)
    tekst = re.sub(f"[{duze}]", cfg.get("zamiana_samogloski_wielkie", "O"), tekst)
    return tekst


def _algo_jakanie(tekst: str, cfg: dict, podstawy: dict, opcje: dict) -> str:
    """Dokleja losowe zająknięcia przed każdym dłuższym słowem.

    Parametry z YAML-a:
      ``min_dlugosc_slowa`` – krótsze słowa są pomijane,
      ``min_powtorzen`` / ``max_powtorzen`` – liczba „k-k-k” dla słowa,
      ``samogloski`` – jeśli drugi znak to samogłoska → jąkamy jedną literę,
                       w przeciwnym razie → dwie (np. „pr-pr-prysznic”).
    """
    min_len  = int(cfg.get("min_dlugosc_slowa", 3))
    min_pow  = int(cfg.get("min_powtorzen", 1))
    max_pow  = int(cfg.get("max_powtorzen", 3))
    samogl   = cfg.get("samogloski", "aeiouyąęóAEIOUYĄĘÓ")

    def zacinaj(match: re.Match[str]) -> str:
        slowo = match.group(0)
        if len(slowo) < min_len:
            return slowo
        ile_powtorzen = random.randint(min_pow, max_pow)
        prefiks = slowo[:2] if len(slowo) > min_len and slowo[1] not in samogl else slowo[0]
        powtorzenia = "-".join([prefiks.lower()] * ile_powtorzen)
        if slowo[0].isupper():
            powtorzenia = powtorzenia.capitalize()
            reszta_slowa = slowo[len(prefiks):]
            return f"{powtorzenia}-{prefiks.lower()}{reszta_slowa}"
        return f"{powtorzenia}-{slowo}"

    return re.sub(_REGEX_SLOWA, zacinaj, tekst)


def _algo_waz(tekst: str, cfg: dict, podstawy: dict, opcje: dict) -> str:
    """Wydłuża ``s``/``z``/``sz`` w losowy długi syk (efekt „Snecko”)."""
    min_syk = int(cfg.get("min_syk", 4))
    max_syk = int(cfg.get("max_syk", 8))
    wzor    = cfg.get("wzor_syku", "(?i)(sz|s|z)")

    def sycz(match: re.Match[str]) -> str:
        znak = match.group(0)
        ile  = random.randint(min_syk, max_syk)
        if znak.lower() == "sz":
            syk = "s" * ile + "z"
            return syk.capitalize() if znak[0].isupper() else syk
        syk = znak[0].lower() * ile
        return syk.capitalize() if znak.isupper() else syk

    return re.sub(wzor, sycz, tekst)


def _algo_cezar(tekst: str, cfg: dict, podstawy: dict, opcje: dict) -> str:
    """Klasyczny szyfr Cezara na alfabecie z ``cfg['alfabet']`` lub ``podstawy``.

    Wartość przesunięcia pobierana jest w kolejności:
      1. ``opcje['przesuniecie_faktyczne']`` (użyteczne, gdy GUI wylosowało
         przesunięcie i chce odtworzyć ten sam wynik),
      2. ``opcje['przesuniecie']`` (pole z SpinCtrl),
      3. domyślnie 0.

    Jeśli wynikowe przesunięcie wynosi 0 – losowane jest z zakresu
    ``1..len(alfabet)-1``.
    """
    alfabet = cfg.get("alfabet") or podstawy.get("alfabet") or \
              "AĄBCĆDEĘFGHIJKLŁMNŃOÓPQRSTUVWXYZŹŻ"
    n = len(alfabet)

    przes = int(opcje.get("przesuniecie_faktyczne",
                          opcje.get("przesuniecie", 0)))
    if przes == 0:
        przes = random.randint(1, n - 1)
    # Zapisz faktyczne przesunięcie z powrotem do opcji – GUI użyje tego
    # do zbudowania nazwy pliku wynikowego (patrz :func:`sufiks_nazwy_pliku`).
    opcje["przesuniecie_faktyczne"] = przes

    def przesun_znak(char: str) -> str:
        upper = char.upper()
        idx = alfabet.find(upper)
        if idx == -1:
            return char
        nowy = alfabet[(idx + przes) % n]
        return nowy if char.isupper() else nowy.lower()

    return "".join(przesun_znak(c) for c in tekst)


# =============================================================================
# Dispatcher szyfrów
# =============================================================================
_ALGORYTMY_SZYFROW: dict[str, Callable[[str, dict, dict, dict], str]] = {
    "odwracanie":     _algo_odwracanie,
    "typoglikemia":   _algo_typoglikemia,
    "samogloskowiec": _algo_samogloskowiec,
    "jakanie":        _algo_jakanie,
    "waz":            _algo_waz,
    "cezar":          _algo_cezar,
}


def _przetworz_szyfrant(tekst: str, jezyk: str, cfg: dict, opcje: dict) -> str:
    """Szyfrant: dispatcher na algorytm wskazany w ``cfg['algorytm']``."""
    podstawy = _zaladuj_podstawy(jezyk)

    # Najpierw zawsze oczyszczamy tekst z bełkotu TTS i normalizujemy liczby –
    # to zgodne z dotychczasowym zachowaniem Trybu Szyfranta.
    tekst_czysty = oczysc_tekst_tts(tekst, z_normalizacja=True)

    nazwa_algo = cfg.get("algorytm", "")
    funkcja = _ALGORYTMY_SZYFROW.get(nazwa_algo)
    if funkcja is None:
        raise ValueError(
            f"Nieznany algorytm szyfru: „{nazwa_algo}”. "
            f"Dostępne: {sorted(_ALGORYTMY_SZYFROW)}"
        )

    def _pipeline(fragment: str) -> str:
        return funkcja(fragment, cfg, podstawy, opcje)

    return procesuj_z_ochrona_tagow(tekst_czysty, _pipeline)


# =============================================================================
# Publiczne API – punkt wejścia dla GUI
# =============================================================================

def przetworz(
    tekst: str,
    tryb: str,
    jezyk: str = "pl",
    wariant: str | None = None,
    **opcje: Any,
) -> str:
    """Uruchamia wybrane przetwarzanie i zwraca gotowy tekst.

    Args:
        tekst:   Tekst źródłowy (dowolnej długości).
        tryb:    ``"Rezyser"`` lub ``"Szyfrant"``.
        jezyk:   Kod ISO 639-1 języka bazowego (domyślnie ``"pl"``).
        wariant: ``id`` z YAML-a (np. ``"islandzki"``, ``"odwracanie"``),
                 ewentualnie etykieta widoczna w GUI.
        **opcje: Dodatkowe parametry zależne od algorytmu, np.:

            ``przesuniecie`` – int, dla szyfru Cezara (0 = losuj).

    Returns:
        Przetworzony tekst jako string.

    Raises:
        ValueError: gdy tryb jest nieznany lub wariantu nie odnaleziono.
    """
    if not wariant:
        raise ValueError("Parametr `wariant` jest wymagany.")

    cfg = wariant_po_id(tryb, jezyk, wariant)
    if cfg is None:
        cfg = wariant_po_etykiecie(tryb, jezyk, wariant)
    if cfg is None:
        raise ValueError(
            f"Nie znaleziono wariantu „{wariant}” dla trybu „{tryb}” "
            f"i języka „{jezyk}”."
        )

    if tryb == TRYB_REZYSER:
        return _przetworz_rezyser(tekst, jezyk, cfg, opcje)
    if tryb == TRYB_SZYFRANT:
        return _przetworz_szyfrant(tekst, jezyk, cfg, opcje)

    raise ValueError(f"Nieznany tryb: „{tryb}”. Oczekiwano „Rezyser” lub „Szyfrant”.")


# =============================================================================
# Pomocnicze – kod ISO i nazwa pliku wynikowego
# =============================================================================

def kod_iso(tryb: str, jezyk: str, wariant: str, opcje: dict | None = None) -> str:
    """Zwraca dwuliterowy kod ISO języka dla pliku wynikowego.

    Dla naprawiacza tagów ``iso`` jest podawane ręcznie przez użytkownika
    (w ``opcje["iso_reczne"]``). Dla pozostałych wariantów pochodzi z YAML-a.
    """
    cfg = wariant_po_id(tryb, jezyk, wariant) or wariant_po_etykiecie(tryb, jezyk, wariant)
    if cfg is None:
        return jezyk

    if cfg.get("kategoria") == "naprawiacz":
        return (opcje or {}).get("iso_reczne", jezyk) or jezyk

    iso = cfg.get("iso") or jezyk
    return str(iso).strip() or jezyk


def sufiks_nazwy_pliku(
    tryb: str,
    jezyk: str,
    wariant: str,
    oryginalna_nazwa: str,
    opcje: dict | None = None,
) -> str:
    """Buduje bazową nazwę pliku wynikowego (bez rozszerzenia).

    Odtwarza nazewnictwo ze starego GUI:
      * ``oczyszczony_<oryginał>``                  – oczyszczanie
      * ``<oryginał>_akcent_<akcent>``              – akcent fonetyczny
      * ``naprawiony_<oryginał>_<iso>``             – naprawiacz tagów
      * ``<oryginał>_szyfr_<szyfr>[<±przesunięcie>]`` – szyfry

    Nie ma kropki w przyrostku – GUI doda ją razem z rozszerzeniem.
    """
    opcje = opcje or {}
    cfg   = wariant_po_id(tryb, jezyk, wariant) or wariant_po_etykiecie(tryb, jezyk, wariant)
    if cfg is None:
        return oryginalna_nazwa

    kategoria = cfg.get("kategoria", "")
    wariant_id = cfg.get("id", wariant)

    if kategoria == "naprawiacz":
        iso = (opcje.get("iso_reczne") or jezyk).strip()
        return f"naprawiony_{oryginalna_nazwa}_{iso}"

    if kategoria == "oczyszczenie":
        return f"oczyszczony_{oryginalna_nazwa}"

    if kategoria == "akcent":
        return f"{oryginalna_nazwa}_akcent_{wariant_id}"

    if kategoria == "szyfr":
        base = f"{oryginalna_nazwa}_szyfr_{wariant_id}"
        # Cezar dopisuje informację o przesunięciu (np. +7, -12)
        if cfg.get("algorytm") == "cezar":
            przes = int(opcje.get("przesuniecie_faktyczne", opcje.get("przesuniecie", 0)))
            if przes != 0:
                base = f"{base}{przes:+d}"
        return base

    return f"{oryginalna_nazwa}_{wariant_id}"


# =============================================================================
# Zapis pliku wynikowego (HTML / DOCX / TXT z tagiem lang)
# =============================================================================

def zapisz_wynik(
    tresc_wynikowa: str,
    katalog_wyjscia: str,
    base_name: str,
    ext: str,
    iso_code: str,
    tryb: str,
    wariant_cfg: dict | None,
    oryginalny_content: str,
    sciezka_oryginalu: str | None = None,
) -> str:
    """Zapisuje wynik do pliku i zwraca jego ścieżkę.

    Obsługiwane rozszerzenia:
      * ``.docx`` – dokument Word z tagiem ``<w:lang w:val=iso>``,
      * ``.html`` / ``.htm`` – HTML z atrybutem ``lang="iso"`` w ``<html>``,
      * ``.txt`` / ``.md`` – konwertowane do HTML z taggiem ``lang``
        (tak, by czytnik ekranu znał język).
      * każde inne – surowy zapis tekstu z oryginalnym rozszerzeniem.

    Args:
        tresc_wynikowa:       Przetworzony tekst do zapisu.
        katalog_wyjscia:      Katalog docelowy (zwykle: katalog pliku źródłowego).
        base_name:            Nazwa pliku bez rozszerzenia
                              (wynik :func:`sufiks_nazwy_pliku`).
        ext:                  Rozszerzenie źródła (np. ``".docx"``) – decyduje
                              o formacie wyjścia.
        iso_code:             Dwuliterowy kod języka do tagu ``lang``.
        tryb:                 ``"Rezyser"`` / ``"Szyfrant"`` / ``"Tlumacz"``.
        wariant_cfg:          Konfiguracja wariantu (z YAML) – potrzebna,
                              by rozpoznać „naprawiacz tagów”.
        oryginalny_content:   Treść źródłowa (wykorzystywana przez naprawiacza
                              tagów, gdy ``sciezka_oryginalu`` nie istnieje).
        sciezka_oryginalu:    Pełna ścieżka oryginału (tylko dla naprawiacza
                              ``.docx`` – kopiujemy oryginalny dokument,
                              tylko wstrzykując tag ``w:lang``).

    Returns:
        Pełna ścieżka zapisanego pliku.
    """
    jest_naprawiacz = bool(wariant_cfg and wariant_cfg.get("kategoria") == "naprawiacz")

    # -------- DOCX ---------------------------------------------------------
    if ext == ".docx":
        out_path = os.path.join(katalog_wyjscia, f"{base_name}.docx")

        if jest_naprawiacz and sciezka_oryginalu and os.path.exists(sciezka_oryginalu):
            # Otwieramy oryginał i wstrzykujemy tag lang do każdego biegu.
            doc = docx.Document(sciezka_oryginalu)
        else:
            # Tworzymy nowy dokument z przetworzoną treścią (lub z oryginalną
            # treścią, gdy naprawiacz nie znalazł pliku źródłowego).
            doc = docx.Document()
            zawartosc = oryginalny_content if jest_naprawiacz else tresc_wynikowa
            for linia in zawartosc.split("\n"):
                doc.add_paragraph(linia)

        for para in doc.paragraphs:
            for run in para.runs:
                rPr = run._r.get_or_add_rPr()
                lang_el = rPr.find(qn("w:lang"))
                if lang_el is None:
                    lang_el = OxmlElement("w:lang")
                    rPr.append(lang_el)
                lang_el.set(qn("w:val"), iso_code)
        doc.save(out_path)
        return out_path

    # -------- HTML / HTM ---------------------------------------------------
    if ext in (".html", ".htm"):
        out_path = os.path.join(katalog_wyjscia, f"{base_name}{ext}")
        tekst = tresc_wynikowa
        if "lang=" in tekst.lower():
            tekst = re.sub(
                r'(<html[^>]*?)lang=["\'][^"\']+["\']',
                fr'\1lang="{iso_code}"',
                tekst,
                flags=re.IGNORECASE,
            )
        elif "<html" in tekst.lower():
            tekst = re.sub(
                r"(<html[^>]*)>",
                fr'\1 lang="{iso_code}">',
                tekst,
                flags=re.IGNORECASE,
            )
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(tekst)
        return out_path

    # -------- TXT / MD → HTML (z tagiem lang) -----------------------------
    if ext in (".txt", ".md"):
        out_path = os.path.join(katalog_wyjscia, f"{base_name}.html")
        linie  = tresc_wynikowa.split("\n")
        tytul  = linie[0].strip() if linie and linie[0].strip() else "Dokument"
        body   = tresc_wynikowa.replace("\n", "<br>\n")
        html = (
            f'<!DOCTYPE html>\n<html lang="{iso_code}">\n'
            f"<head>\n<meta charset=\"utf-8\">\n<title>{tytul}</title>\n</head>\n"
            f"<body>\n{body}\n</body>\n</html>"
        )
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        return out_path

    # -------- Inne – zapis surowy -----------------------------------------
    out_path = os.path.join(katalog_wyjscia, f"{base_name}{ext if ext else '.txt'}")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(tresc_wynikowa)
    return out_path
