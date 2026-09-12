"""
core_poliglota.py – Silnik modułu „Poliglota AI".

Cały Python-owy „brain" modułu Poliglota: ładowanie reguł z plików YAML
w folderze ``dictionaries/`` i ich stosowanie wg wskazanego trybu i języka.

Publiczne API (prosty, wysokopoziomowy interfejs używany przez GUI):

    import core_poliglota

    # lista dostępnych wariantów (do wypełnienia ComboBoxa w GUI):
    core_poliglota.lista_wariantow(tryb="Rezyser",  jezyk="pl")
    core_poliglota.lista_wariantow(tryb="Szyfrant", jezyk="pl")

    # przetwarzanie tekstu (opcje to MUTOWALNY dict — silnik dopisuje do
    # niego kanał zwrotny: _segmenty_wynikowe, przesuniecie_faktyczne):
    opcje = {"przesuniecie": 7}          # parametry zależne od algorytmu
    wynik = core_poliglota.przetworz(
        tekst,
        tryb="Szyfrant",       # lub "Rezyser"
        jezyk="pl",
        wariant="cezar",       # id z YAML (np. "islandzki", "odwracanie")
        opcje=opcje,
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

import difflib
import os
import random
import re
import sys
from typing import Any, Callable

import yaml

# python-docx potrzebne tylko do zapisu .docx – importujemy globalnie,
# bo GUI i tak ma tę zależność.
import docx
from docx.oxml.ns import qn
from docx.oxml.shared import OxmlElement

from num2words import num2words

import jezyki_lingua
import sciezki
# v18.24.2: wspólny rejestr powodów pominięcia pliku reguł (patrz
# `gui_diagnostyka`). Import jest jednokierunkowy i bez ryzyka cyklu —
# `przepisy_rezysera` ciągnie tylko `os`/`sys`/`yaml`/`sciezki`.
from przepisy_rezysera import (
    POWOD_KSZTALT,
    POWOD_LINGUA,
    POWOD_PARSE,
    opis_bledu_yaml,
    zglos_pominiecie,
)

# 13.5: detekcja języka oparta na ``lingua-language-detector``.
# Lingua jest deterministyczna z założenia (operuje na n-gramowych modelach
# statystycznych, nie na losowych próbkach), znacznie dokładniejsza dla
# krótkich tekstów niż dawne ``langdetect``, i — co dla nas kluczowe — pozwala
# zawęzić zestaw rozpoznawanych języków do tych, dla których faktycznie mamy
# słowniki w ``dictionaries/``. Dzięki temu detektor nigdy nie zwróci kodu
# języka, którego silnik i tak nie umiałby przetworzyć.
#
# Builder ładuje modele leniwie przy pierwszej detekcji (~1–2 s, ~100 MB RAM),
# dlatego trzymamy go za lazy singletonem ``_zbuduj_detektor_lingua``,
# uruchamianym dopiero przy realnym wywołaniu, nie w czasie importu modułu.
try:
    from lingua import Language as _LinguaLanguage
    from lingua import LanguageDetectorBuilder as _LinguaBuilder
except ImportError:                                             # pragma: no cover
    _LinguaLanguage = None   # type: ignore[assignment]
    _LinguaBuilder = None    # type: ignore[assignment]


# =============================================================================
# Ścieżki, stałe i cache
# =============================================================================
_ROOT_DIR = sciezki.KATALOG_BAZOWY_STR
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

def normalizuj_liczby(tekst: str, jezyk: str = "pl") -> str:
    """Zamienia cyfrowe zapisy liczb na słowa (np. ``123`` → ``sto dwadzieścia trzy``).

    13.3: parametr ``jezyk`` decyduje, w jakim języku ``num2words`` rozwija
    cyfrę. Domyślnie ``"pl"`` — backward-compat. Akcent angielski musi
    przekazać ``"en"`` (``123`` → ``one hundred and twenty-three``), bo
    inaczej w angielski tekst wkleilibyśmy polskie słowa.

    Liczby, których biblioteka nie potrafi zapisać dla danego języka
    (nieznane locale, bardzo duże wartości), zostawiamy w oryginale —
    lepiej zostawić cyfry niż wybuchnąć.
    """
    def zamien(match: re.Match[str]) -> str:
        try:
            return num2words(match.group(), lang=jezyk)
        except Exception:
            return match.group()
    return re.sub(r"\d+", zamien, tekst)


def sklej_pojedyncze_litery(tekst: str) -> str:
    """Scala SERIE wiszących pojedynczych liter (np. „w y s” → „wys”).

    Audyt 18.12 (W-2): dawny wzorzec ``\\b([a-z])\\s+`` sklejał KAŻDĄ
    pojedynczą literę z następnym wyrazem — a jednoliterowe SŁOWA to
    codzienność (pl „w/z/i/a/o/u”, es „y”, it „e”, transliteracje ru
    „v/i/u/s/k”): „brzmi w trzcinie”→„bzhmi vtzhcinie”, „couldn't say”→
    „couldn'tsay” (apostrof tworzy granicę słowa). Sklejamy więc tylko
    ciąg CO NAJMNIEJ DWÓCH samotnych liter — faktyczne rozstrzelenie
    („s z c z y t”→„szczyt”), nie słowo-literę przed normalnym wyrazem.
    """
    def _sklej(m: re.Match[str]) -> str:
        return re.sub(r"\s+", "", m.group(0))
    return re.sub(r"(?i)\b[a-z](?:\s+[a-z]\b)+(?!\w)", _sklej, tekst)


# Didaskalia nawiasowe usuwamy po KSZTAŁCIE (para nawiasów), nigdy po treści:
# rodzina ASCII ``()`` i pełnej szerokości ``（）`` (pismo CJK), żeby przyszła
# paczka nie potrzebowała linijki Pythona. Treść dopasowania nie przekracza
# PUSTEJ linii, więc twardo zawijany nawias łapie się cały, ale sierocy „("
# nie zje dwóch akapitów (zmierzone przed 18.27: akapit z otwarciem nawiasu,
# pusta linia, drugi akapit z domknięciem — całość schodziła do jednego
# zdania). Nawiasy OTWIERAJĄCE są wyłączone z treści: dopasowanie startuje od
# najgłębszego otwarcia, więc niedomknięty nawias nie pochłania prozy w drodze
# do następnego domknięcia.
_RE_DIDASKALIA = re.compile(
    r"[(（](?:[^()（）\n]|\n(?!\s*\n))*[)）]"
)

# Wielokropek typograficzny: cała higiena kropek niżej jest zapisana na ASCII,
# a „…" (U+2026) sypią i książki, i model. Zwijamy go przed regułami kropek,
# żeby te same reguły objęły oba zapisy.
_WIELOKROPEK = "…"


def _usun_didaskalia(tekst: str) -> str:
    """Usuwa nawiasowe didaskalia, także zagnieżdżone, do punktu stałego.

    Jeden przebieg zostawiłby po „(mówi (cicho))" resztkę „(mówi )" — czyli
    słowo, które syntezator PRZECZYTA. Powtarzamy więc podstawienie, dopóki
    coś ubywa; limit iteracji chroni przed patologicznym wejściem. Tekst bez
    domknięcia nie daje trafienia, więc pętla kończy się od razu.
    """
    for _ in range(10):
        nowy = _RE_DIDASKALIA.sub("", tekst)
        if nowy == tekst:
            break
        tekst = nowy
    return tekst


def oczysc_tekst_tts(tekst: str, z_normalizacja: bool = True,
                     jezyk: str = "pl") -> str:
    """Oczyszcza tekst pod syntezator mowy (TTS).

    Etapy — wszystkie poza pierwszym są NIEZALEŻNE od języka wejścia:
      1. (opcjonalnie) normalizacja liczb w języku ``jezyk`` — jedyny etap
         językowy, por. :func:`normalizuj_liczby`;
      2. znaczniki zapisu: gwiazdki, znaki ``=``, hashtagi nagłówków
         Markdown (składnia zapisu nie ma języka);
      3. nawiasowe didaskalia (:func:`_usun_didaskalia`);
      4. higiena interpunkcji: wielokropki (ASCII i „…"), osierocone
         przecinki, wielokrotne spacje.

    Nawiasów KWADRATOWYCH nie tyka — tam żyją tagi mówców (``[Anna]``)
    i audio-tagi ElevenLabs (``[whispers]``). Dawny docstring obiecywał ich
    usuwanie, czego ten kod nigdy nie robił (i nie może).

    18.27: z etapów wypadły reguły zależne od polszczyzny — lista wykrzykników
    (``khh|hh|pff|ahh|ehh``) i frazy „z wplecionymi wdechami" (artefakty
    gpt-4, których model w trybie teatru czytanego już nie produkuje).
    Zmierzone: dla ``ru`` („Кхх", „Пфф") i ``fi`` („Öhh") były no-opem, a dla
    ``is`` szkodliwe — kasowały autorskie „Pff," i „Ahh," z dialogu, bo te
    przypadkiem stoją w liście ASCII. Lista wykrzykników per język byłaby
    długiem bez końca, a wejściem Poligloty jest DOWOLNY plik z dysku, gdzie
    taki dźwięk bywa treścią autora, nie artefaktem. Paczka, która chce wyciąć
    własną frazę, robi to danymi: ``zamiany:`` w ``akcenty/oczyszczenie*.yaml``
    przyjmuje ``regex: true`` z pustą ``zamiana``. Niezmiennika pilnuje
    ``test_oczyszczanie_tts.py`` (bramki: G1 — brak literału językowego
    w ścieżce czyszczenia, G2 — symetria wyniku między paczkami).
    """
    if z_normalizacja:
        tekst = normalizuj_liczby(tekst, jezyk)
    tekst = re.sub(r"[\*=]+", "", tekst)
    tekst = re.sub(r"^#+\s*", "", tekst, flags=re.MULTILINE)
    tekst = _usun_didaskalia(tekst)
    tekst = tekst.replace(_WIELOKROPEK, "...")
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


def _kontekst_wersalikami(tekst: str, poczatek: int, koniec: int) -> bool:
    """Czy trafienie ``[poczatek, koniec)`` leży w słowie pisanym WERSALIKAMI.

    Rozszerza trafienie do granic wyrazu (maksymalny ciąg liter dowolnego
    pisma) i pyta o małą literę: jej brak przy co najmniej dwóch literach,
    z których co najmniej jedna jest wielka, to tekst pisany wersalikami.
    Wzorzec ze spacją (`` SP`` → ``ШП`` w ``de/rosyjski``) dotyka DWÓCH
    wyrazów — wtedy wersalikami musi być całość, inaczej podniesienia nie ma.

    Progu „dwie litery" pilnuje świadomie: samotne „Ж" to inicjał albo
    początek zdania, nie krzyk, więc zostaje przy „Zh".
    """
    i = poczatek
    while i > 0 and tekst[i - 1].isalpha():
        i -= 1
    j = koniec
    while j < len(tekst) and tekst[j].isalpha():
        j += 1
    litery = [z for z in tekst[i:j] if z.isalpha()]
    if len(litery) < 2 or any(z.islower() for z in litery):
        return False
    return any(z.isupper() for z in litery)


def _moze_podniesc_wersaliki(wzor: str, zamiana: str, *, regex: bool) -> bool:
    """Czy dla tej reguły podnoszenie wyniku ma szansę cokolwiek zmienić.

    Dwa warunki wykluczające — oba dokładne, nie heurystyczne — trzymają
    ścieżkę wolną (skanowanie trafień) przy garstce reguł z klasy „jedna
    litera źródła, wiele znaków wyniku" (`Ж` → `Zh`), a całą resztę
    zostawiają szybkiemu ``str.replace``/``re.sub``:

      * wynik bez małej litery → podniesienie jest tożsamością;
      * wzorzec z małą literą → trafi wyłącznie w tekst z małą literą,
        więc kontekstem nigdy nie będą wersaliki. Dla ``regex: true`` tego
        warunku NIE stosujemy: mała litera we wzorcu bywa częścią klasy
        (``[a-z]``), a flaga ``(?i)`` pozwala jej dopasować wielką.
    """
    if not wzor or not any(z.islower() for z in zamiana):
        return False
    if regex:
        return True
    return not any(z.islower() for z in wzor)


def _zamien_literalnie(tekst: str, wzor: str, zamiana: str) -> str:
    """``str.replace`` z podniesieniem wyniku w wyrazach pisanym wersalikami."""
    wynik: list[str] = []
    poz = 0
    while True:
        trafienie = tekst.find(wzor, poz)
        if trafienie < 0:
            wynik.append(tekst[poz:])
            return "".join(wynik)
        koniec = trafienie + len(wzor)
        wynik.append(tekst[poz:trafienie])
        wynik.append(zamiana.upper()
                     if _kontekst_wersalikami(tekst, trafienie, koniec)
                     else zamiana)
        poz = koniec


def _zastosuj_zamiany(tekst: str, zamiany: list[dict]) -> str:
    """Stosuje listę par ``{wzor, zamiana, regex?}`` z pliku YAML.

    Wzory oznaczone ``regex: true`` używają ``re.sub``, pozostałe są
    traktowane jako zwykłe stringi i zamieniane przez ``str.replace``.

    18.22: **wynik reguły trafionej w wyrazie pisanym WERSALIKAMI jest
    podnoszony do wersalików.** Reguła jednoliterowa z wielo-znakowym
    wynikiem (`Ж` → `Zh`, `Þ` → `Th`, `ß` → `ss`) jest poprawna dla
    „Ждать", a dla „ЖДАТЬ" dawała „ZhDAT'". Wariantu w danych dosypać się
    nie da (wzorzec ma tylko jedną literę, więc nie ma czego odmieniać
    wielkością — patrz kanon ALL-CAPS z v18.21, który domknął wzorce
    WIELOLITEROWE), a reguła pozycyjna na literę byłaby ~120 pozycjami
    długu w danych. Krok jest bezwarunkowy: dotyczy zarówno pre-passu
    ``usun_polskie_znaki``, jak i właściwych ``zamiany``, w Reżyserze
    i w Poliglocie jednakowo.
    """
    for para in zamiany:
        wzor    = para.get("wzor", "")
        zamiana = para.get("zamiana", "")
        regex   = bool(para.get("regex"))
        if not _moze_podniesc_wersaliki(wzor, zamiana, regex=regex):
            tekst = re.sub(wzor, zamiana, tekst) if regex else tekst.replace(wzor, zamiana)
            continue
        if regex:
            tekst = re.sub(
                wzor,
                lambda m: (m.expand(zamiana).upper()
                           if _kontekst_wersalikami(m.string, m.start(), m.end())
                           else m.expand(zamiana)),
                tekst,
            )
        else:
            tekst = _zamien_literalnie(tekst, wzor, zamiana)
    return tekst


def _ostrzez_o_lancuchu_zamian(zamiany: list[dict], kontekst: str) -> None:
    """Loguje WARN, gdy ``zamiana`` reguły #i zawiera ``wzor`` reguły #j>i.

    Wykrywa klasyczną pułapkę sekwencyjnego ``str.replace``: reguła
    wprowadzająca znak, który łapie późniejsza reguła w tej samej liście,
    daje niezamierzony wynik (np. ``ñ → nj`` PRZED ``j → x`` produkuje
    ``ñ → nx``, nie ``nj``). Pomija pary z ``regex: true`` — heurystyka
    substring jest tam zwodnicza (np. ``\\d`` zawsze pasuje do każdej
    zamiana zawierającej cyfrę).

    Wywoływana raz przy ładowaniu wariantu (akcent / szyfr) w
    :func:`_zaladuj_warianty`. Tylko log WARN — nigdy nie blokuje
    ładowania pliku, bo niektóre „pętle" są celowe (np. transliteracja
    diakrytyków: ``ó → o``, potem dla docelowego TTS ``o → u``;
    rozpad dwuznaku ``szcz → shch``, potem ``ch → h``).

    Format outputu: JEDNA linia agregatu per plik. Listujemy maksymalnie
    3 pierwsze trafienia + ile dodatkowych pominęliśmy. Nie spamujemy
    stdout przy 60+ regułach w jednym akcencie.

    Issue #15 (v15.3.1): autor paczki ES wpadł w pętlę w GUI Managera
    Reguł, który nie ostrzegał o sekwencyjności listy. Walidacja w silniku
    daje WARN w stdout/logu przy starcie aplikacji z konsoli.
    """
    pary = [(p.get("wzor", ""), p.get("zamiana", ""), bool(p.get("regex")))
            for p in zamiany if isinstance(p, dict)]
    trafienia: list[str] = []
    for i, (wzor_i, zam_i, regex_i) in enumerate(pary):
        if not zam_i or regex_i:
            continue
        for j in range(i + 1, len(pary)):
            wzor_j, _, regex_j = pary[j]
            if not wzor_j or regex_j:
                continue
            if wzor_j in zam_i:
                trafienia.append(
                    f"#{i+1} ({wzor_i!r}->{zam_i!r}) -> #{j+1} ({wzor_j!r}->...)"
                )
                break  # pierwszy match per regula i — nie dubluj diagnostyki
    if not trafienia:
        return
    podglad = "; ".join(trafienia[:3])
    reszta = f" (+{len(trafienia) - 3} kolejnych)" if len(trafienia) > 3 else ""
    _dev_log(
        f"WARN {kontekst}: {len(trafienia)} potencjalnych "
        f"petli sekwencyjnego str.replace -> {podglad}{reszta}. "
        f"Jesli celowe (rozpad dwuznaku w pipeline) - zignoruj; jesli niezamierzone "
        f"(klasyk: ñ->nj przed j->x daje nx) - zamien TARGET pierwszy, SOURCE potem."
    )


def _usun_polskie_znaki(tekst: str, podstawy: dict) -> str:
    """Transliteruje polskie diakrytyki wg listy z ``podstawy.yaml``.

    Funkcja NIE normalizuje liczb samodzielnie – to robi pipeline akcentu
    (flaga ``normalizuj_liczby`` w YAML-u akcentu).
    """
    return _zastosuj_zamiany(tekst, podstawy.get("polskie_znaki", []))


# =============================================================================
# Ładowanie plików YAML
# =============================================================================

def _dev_log(komunikat: str) -> None:
    """Strażowany ``print`` na konsolę dewelopera (wzorzec ``core_llm._dev_log``).

    v18.24.2: goły ``print`` w tym module milczał w buildzie ``--windowed``
    (``sys.stdout`` jest tam ``None``, a ``print`` z takim celem nic nie robi),
    więc diagnostyka i tak nie docierała — a przy stdout ZAMKNIĘTYM mogła rzucić
    ``ValueError`` z loadera danych. Guard usuwa oba ryzyka; kanałem dla
    UŻYTKOWNIKA jest rejestr pominięć (:mod:`gui_diagnostyka`).
    """
    try:
        if sys.stdout is not None:
            print(f"[core_poliglota] {komunikat}", file=sys.stdout)
    except Exception:  # noqa: BLE001 — log nigdy nie może ubić wywołania
        pass


def _zaladuj_yaml(sciezka: str) -> dict:
    """Wczytuje pojedynczy plik YAML i zwraca słownik (lub ``{}``).

    v18.24.2: błąd składni trafia do wspólnego rejestru pominięć, bo
    ``akcenty/`` i ``szyfry/`` to pliki, które Manager Reguł sam wystawia
    użytkownikowi do edycji w edytorze tekstu. Bez tego akcent albo szyfr
    znikał z listy Poligloty bez ani jednego słowa wyjaśnienia (w paczce
    ``--windowed`` konsoli nie ma), a raport „reguły sprawdzone" w Managerze
    Reguł obejmowałby tylko część kategorii, które ten Manager pokazuje.
    """
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        zglos_pominiecie(sciezka, POWOD_PARSE, opis_bledu_yaml(exc))
        return {}
    except Exception as exc:  # noqa: BLE001 — OSError / UnicodeDecodeError
        zglos_pominiecie(sciezka, POWOD_PARSE, str(exc).replace("\n", " "))
        return {}
    # Plik PUSTY (``null`` po wykasowaniu treści) i plik sparsowany do czegoś
    # innego niż mapa (goły skalar, lista) dostają od v18.28.0 wpis o KSZTAŁCIE.
    # Do v18.27.0 obie te ścieżki wracały jako ciche ``{}``, z argumentem „nie
    # umiemy wskazać brakującego pola" — a to był argument za milczeniem o
    # SZCZEGÓLE, nie za milczeniem o pominięciu: akcent albo szyfr znikał
    # z listy Poligloty, choć w Managerze Reguł plik był widoczny i wyglądał na
    # sprawny. Szczegół podajemy uczciwie techniczny (typ korzenia).
    if not isinstance(data, dict):
        zglos_pominiecie(sciezka, POWOD_KSZTALT, type(data).__name__)
        return {}
    return data


def wyczysc_cache() -> None:
    """Zapomina wczytane podstawy i warianty (akcenty/szyfry).

    Odpowiednik ``przepisy_rezysera.wyczysc_cache`` — wołany przez „Odśwież"
    w Managerze Reguł (v18.24.2), żeby poprawka pliku akcentu albo szyfru
    działała bez zamykania aplikacji. Rejestr powodów pominięcia czyści
    ``przepisy_rezysera``, bo jest wspólny dla wszystkich loaderów.

    Od v18.26.1 zeruje TAKŻE mapowanie i singleton detektora ``lingua``.
    Wcześniej „Odśwież" nie dotykało ani jednego, ani drugiego, więc obietnica
    „naprawa bez restartu" nie obejmowała detekcji języka: paczka DODANA
    w Managerze Reguł nie wchodziła do detektora do zamknięcia aplikacji,
    a poprawiona wartość ``lingua:`` (np. ``NORWEGIAN`` → ``BOKMAL``) nadal
    była tą błędną — przy czym NIC tego użytkownikowi nie mówiło.

    Budowa detektora ładuje modele n-gramowe i jest kosztowna, ale ta funkcja
    chodzi wyłącznie z jawnej akcji użytkownika (jedyny wołający to
    ``gui_diagnostyka.przeskanuj_reguly``), więc koszt jest zamierzony. Worker
    w tle, który trzyma referencję do starego detektora, dokończy nią pracę —
    obiekt jest niemutowalny, a kolejne wywołanie zbuduje świeży.
    """
    global _LINGUA_MAPOWANIE_CACHE, _LINGUA_DETEKTOR, _LINGUA_DETEKTOR_BLD_FAILED
    _CACHE_PODSTAWY.clear()
    _CACHE_WARIANTOW.clear()
    _LINGUA_MAPOWANIE_CACHE = None
    _LINGUA_DETEKTOR = None
    _LINGUA_DETEKTOR_BLD_FAILED = False


def _zaladuj_podstawy(jezyk: str) -> dict:
    """Zwraca dict z ``<jezyk>/podstawy.yaml`` (cache w pamięci)."""
    if jezyk in _CACHE_PODSTAWY:
        return _CACHE_PODSTAWY[jezyk]

    sciezka = os.path.join(DICTIONARIES_DIR, jezyk, "podstawy.yaml")
    if not os.path.exists(sciezka):
        _dev_log(f"Brak pliku podstaw dla jezyka {jezyk}: {sciezka}")
        _CACHE_PODSTAWY[jezyk] = {}
        return _CACHE_PODSTAWY[jezyk]

    _CACHE_PODSTAWY[jezyk] = _zaladuj_yaml(sciezka)
    return _CACHE_PODSTAWY[jezyk]


def slowa_akcentu(jezyk: str) -> list[str]:
    """Zwraca listę słów-wyzwalaczy parsera akcentów dla danego języka.

    13.3+: pole ``slowo_akcent`` w ``dictionaries/<jezyk>/podstawy.yaml``
    zawiera listę słów (lower-case), które ``core_rezyser`` traktuje jako
    znacznik „tu mowa o akcencie X" w Księdze Świata. Funkcja zwraca:

      * listę z YAML-a, gdy pole istnieje i jest niepuste,
      * fallback ``["akcent"]`` dla starszych paczek bez pola lub gdy
        plik podstaw nie istnieje (zachowanie sprzed 13.3).

    Wynik jest płaską listą stringów; wpisy nie-stringowe filtrujemy
    defensywnie (gdyby ktoś wpisał liczbę albo zagnieżdżoną listę).
    """
    podstawy = _zaladuj_podstawy(jezyk)
    surowe = podstawy.get("slowo_akcent")
    if not isinstance(surowe, list):
        return ["akcent"]
    czyste = [str(s).strip().lower() for s in surowe if isinstance(s, str) and s.strip()]
    return czyste or ["akcent"]


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
        # 15.3.1: WARN dla potencjalnych pętli sekwencyjnego str.replace.
        # OPT-IN przez ENV var REZYSER_VALIDATE_ZAMIANY=1 — bo wiele celowych
        # pipeline'ów (rozpad dwuznaków typu szcz→shch→sh) trygruje fałszywie
        # pozytywne WARN-y, które spamowałyby stdout NVDA-userów przy każdym
        # starcie aplikacji. Autor paczki debugujący pętlę a la #15
        # (ñ→nj/j→x) świadomie ustawia ENV var w VS Code / batchu i widzi
        # diagnostykę zaraz po starcie aplikacji z konsoli.
        if os.environ.get("REZYSER_VALIDATE_ZAMIANY"):
            zamiany_cfg = cfg.get("zamiany")
            if isinstance(zamiany_cfg, list) and zamiany_cfg:
                _ostrzez_o_lancuchu_zamian(
                    zamiany_cfg, f"{jezyk}/{podfolder}/{nazwa_pliku}",
                )
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

# 15.3: dwie bazy referencyjne (pl rdzeń projektu + en międzynarodowy fallback)
# muszą zawierać identyczny zestaw plików konceptualnie wspólnych. Eliminacja
# stuba referencyjnego — gdyby en zabrakło pliku `opowiesci/baza.yaml`, fallback
# `opowiesci_ai._zaladuj_przepis` (pl → en) ciszą zawiedzie.
_JEZYKI_REFERENCYJNE: tuple[str, ...] = ("pl", "en")

# 15.3: cztery podfoldery językowe + dodatkowy `opowiesci/` (wymóg silnika 5).
_PODFOLDERY_JEZYKOWE: tuple[str, ...] = ("akcenty", "szyfry", "rezyser", "opowiesci")

# 15.3: pliki w `akcenty/` wspólne dla wszystkich języków (narzędzia czyszczenia).
# Pozostałe `akcenty/<jezyk>.yaml` to akcenty obcojęzyczne — reguła natywności
# (każdy z N wdrożonych języków minus własny natywny = N-1 plików) sprawia, że
# zawartość per-język się różni i nie nadaje się do crosschecku 1:1 między
# bazami referencyjnymi pl ↔ en.
_NARZEDZIA_AKCENTOW: frozenset[str] = frozenset({
    "oczyszczenie.yaml",
    "oczyszczenie_bez_liczb.yaml",
    "naprawiacz_tagow.yaml",
})


def _pliki_yaml_jezyka(kod: str) -> set[str]:
    """Względne ścieżki wszystkich plików ``*.yaml`` w ``dictionaries/<kod>/``.

    Zwraca posixowe ścieżki (``"podstawy.yaml"``, ``"gui/ui.yaml"``,
    ``"akcenty/angielski.yaml"``, ...) niezależnie od OS-a — porównanie między
    językami musi być deterministyczne.
    """
    folder = os.path.join(DICTIONARIES_DIR, kod)
    pliki: set[str] = set()
    if os.path.isfile(os.path.join(folder, "podstawy.yaml")):
        pliki.add("podstawy.yaml")
    if os.path.isfile(os.path.join(folder, "gui", "ui.yaml")):
        pliki.add("gui/ui.yaml")
    for pod in _PODFOLDERY_JEZYKOWE:
        pod_dir = os.path.join(folder, pod)
        if not os.path.isdir(pod_dir):
            continue
        for nazwa in os.listdir(pod_dir):
            if nazwa.endswith(".yaml"):
                pliki.add(f"{pod}/{nazwa}")
    return pliki


def _zestaw_referencyjny(kod: str) -> set[str]:
    """Podzbiór plików języka który MUSI być identyczny między pl i en.

    Pomija akcenty obcojęzyczne (``akcenty/<jezyk>.yaml`` poza whitelistą
    ``_NARZEDZIA_AKCENTOW``), bo te są z definicji per-język inne.
    """
    return {
        p for p in _pliki_yaml_jezyka(kod)
        if not p.startswith("akcenty/")
        or os.path.basename(p) in _NARZEDZIA_AKCENTOW
    }


def _jezyk_kompletny(kod: str) -> bool:
    """Czy folder ``dictionaries/<kod>/`` ma komplet plików pełnej obsługi?

    Kryterium bazowe (każdy język):

      1. ``podstawy.yaml``             – alfabet + transliteracja (Cezar)
      2. ``gui/ui.yaml``               – tłumaczenie warstwy interfejsu
      3. ``akcenty/<id>.yaml``  ≥ 1   – tryb Poligloty
      4. ``szyfry/<id>.yaml``   ≥ 1   – tryb Szyfranta
      5. ``rezyser/<id>.yaml``  ≥ 1   – tryb Reżysera
      6. ``opowiesci/<id>.yaml`` ≥ 1  – tryb Opowieści (15.3)

    Wzmocniony kontrakt dla języków referencyjnych (pl, en):

      Oba muszą zawierać **identyczny zestaw plików** poza akcentami
      obcojęzycznymi (``_zestaw_referencyjny``). Powód: silnik Opowieści
      fallbackuje brakujące przepisy ``<jezyk>/opowiesci/X.yaml`` na
      ``en/opowiesci/X.yaml`` (15.3 zmiana z pl→en, dla parytetu
      międzynarodowego). Jeśli en byłoby stubem fallback cicho zawodzi
      mid-game. Symetrycznie pl jest rdzeniem projektu — brak czegoś
      w pl względem en oznacza niedokończony rdzeń. Crosscheck pomija
      akcenty obcojęzyczne, bo reguła natywności wyklucza akcent własnego
      języka (pl/akcenty/angielski.yaml vs en/akcenty/polski.yaml).

      Jeśli pl LUB en nie spełnia kontraktu — żaden z nich nie pojawi się
      w :func:`dostepne_jezyki_bazowe`. Reszta języków NIE jest filtrowana
      crosscheckiem (brakujące pliki rozwiązuje fallback do en).

    13.9: dodany 5. warunek (``rezyser/``).
    15.3: dodany 6. warunek (``opowiesci/``) + crosscheck pl/en.

    Args:
        kod: dwuliterowy kod języka (nazwa folderu w ``dictionaries/``).

    Returns:
        True gdy wszystkie warunki spełnione, False przy stubach.
    """
    folder = os.path.join(DICTIONARIES_DIR, kod)
    if not os.path.isfile(os.path.join(folder, "podstawy.yaml")):
        return False
    if not os.path.isfile(os.path.join(folder, "gui", "ui.yaml")):
        return False
    for pod in _PODFOLDERY_JEZYKOWE:
        pod_dir = os.path.join(folder, pod)
        if not os.path.isdir(pod_dir):
            return False
        if not any(p.endswith(".yaml") for p in os.listdir(pod_dir)):
            return False
    if kod in _JEZYKI_REFERENCYJNE:
        druga_baza = next(j for j in _JEZYKI_REFERENCYJNE if j != kod)
        if _zestaw_referencyjny(kod) != _zestaw_referencyjny(druga_baza):
            return False
    return True


def dostepne_jezyki_bazowe() -> list[str]:
    """Zwraca posortowaną listę kodów KOMPLETNYCH języków w ``dictionaries/``.

    „Kompletny" oznacza folder spełniający wszystkie sześć warunków
    z :func:`_jezyk_kompletny` (podstawy + gui/ui.yaml + akcenty/ + szyfry/
    + rezyser/ + opowiesci/, każdy z minimum jednym plikiem ``*.yaml``).
    Bazy referencyjne pl/en dodatkowo crosscheckują się 1:1 na zestawie
    plików (poza akcentami obcojęzycznymi). Stuby (np. folder z samym
    ``podstawy.yaml`` bez podfolderów) są filtrowane — silnik nie umiałby
    przetwarzać tekstu w takim języku, więc nie powinny pojawiać się
    w komunikatach typu „obsługiwane języki" ani w selektorze języka
    interfejsu w GUI.

    Returns:
        Listę kodów ISO języków gotowych do użycia, np. ``["de", "en",
        "es", "fi", "fr", "is", "it", "pl", "ru"]`` po 14.0.
    """
    if not os.path.isdir(DICTIONARIES_DIR):
        return []
    wynik: list[str] = []
    for nazwa in sorted(os.listdir(DICTIONARIES_DIR)):
        if not os.path.isdir(os.path.join(DICTIONARIES_DIR, nazwa)):
            continue
        if _jezyk_kompletny(nazwa):
            wynik.append(nazwa)
    return wynik


def natywna_nazwa(kod: str) -> str:
    """Natywna nazwa języka (prefiks `etykieta` w `<kod>/podstawy.yaml`).

    Przykład: dla ``kod="fi"`` zwraca ``"Suomi"`` (z etykiety
    ``"Suomi – foneettiset perusteet"``). Fallback na sam kod ISO,
    gdy etykieta nie ma separatora ` – ` lub nie istnieje.

    13.4: wyciągnięte z ``main._natywna_nazwa`` na poziom modułu, żeby GUI
    Poligloty mogło użyć tego helpera w komunikacie A11Y o zmianie języka
    pipeline'u (NVDA odczytuje pełne natywne nazwy zamiast kodów ISO).
    """
    etyk = _zaladuj_podstawy(kod).get("etykieta", "")
    if isinstance(etyk, str) and etyk:
        nazwa = etyk.split(" – ", 1)[0].strip()
        if nazwa:
            return nazwa
    return kod


def lista_wspieranych_jezykow_natywnie(jezyk_pierwszy: str | None = None) -> str:
    """Zwraca natywne nazwy wspieranych języków, gotowe do komunikatu GUI.

    Skanuje `dictionaries/<kod>/podstawy.yaml`, czyta pole `etykieta`
    i bierze prefiks przed separatorem ` – ` (em-dash z otaczającymi
    spacjami — konwencja przyjęta we WSZYSTKICH plikach `podstawy.yaml`).
    Format zwrotny to natywne nazwy języków rozdzielone przecinkami,
    z zachowaniem oryginalnych znaków (cyrylica, Þ, Æ itp.).

    Sortowanie hybrydowe:
      * gdy ``jezyk_pierwszy`` jest podany i obecny w wyniku
        :func:`dostepne_jezyki_bazowe` — ten kod idzie na pierwszą
        pozycję, reszta alfabetycznie po kodzie ISO. Pozwala GUI
        priorytetyzować język interfejsu użytkownika w komunikatach
        (np. dla użytkownika EN: „English, Polski, Suomi…" zamiast
        twardego „Polski, …").
      * w przeciwnym razie — PL twardo na pierwszym miejscu (rdzeń
        projektu, bezpieczny domyślny), reszta po ISO.

    Args:
        jezyk_pierwszy: Opcjonalny dwuliterowy kod ISO języka, który
                        ma się pojawić jako pierwszy element listy.
                        Najczęściej `i18n.aktualny_jezyk()`.
                        Jeśli None lub kod nieobecny w `dictionaries/` —
                        spadamy na PL-hardcode.

    Returns:
        Po 13.1: ``"Polski"`` (jedyny w pełni wdrożony język).
        Po 13.2 z fińskim, gdy `jezyk_pierwszy="fi"`: ``"Suomi, Polski"``.
        Pusty string, gdy `dictionaries/` nie istnieje lub żaden język
        nie przechodzi filtra kompletności z :func:`dostepne_jezyki_bazowe`.
    """
    kody = dostepne_jezyki_bazowe()
    if not kody:
        return ""

    if jezyk_pierwszy and jezyk_pierwszy in kody:
        kolejnosc = [jezyk_pierwszy] + sorted(k for k in kody if k != jezyk_pierwszy)
    elif "pl" in kody:
        kolejnosc = ["pl"] + sorted(k for k in kody if k != "pl")
    else:
        kolejnosc = sorted(kody)

    natywne: list[str] = []
    for kod in kolejnosc:
        nazwa = natywna_nazwa(kod)
        if nazwa and nazwa != kod:
            natywne.append(nazwa)
    return ", ".join(natywne)


# Minimalna długość tekstu (po strip), przy której uznajemy detekcję za
# wiarygodną. Lingua dla krótszych próbek miewa fałszywe alarmy (np. „OK"
# bywa klasyfikowane jako fiński). Niżej operujemy na sticky-fallbacku: zbyt
# krótki akapit dziedziczy język po poprzednim (a na samym początku pliku —
# po parametrze ``jezyk`` przekazanym do :func:`przetworz`).
_MIN_TEKST_DLA_DETEKCJI = 20


# ---------------------------------------------------------------------------
# Mapowania ISO ↔ ``lingua.Language`` i lazy singleton detektora
# ---------------------------------------------------------------------------
# 13.4.3: mapowanie nie jest już zhardkodowane w Pythonie. Każdy
# ``dictionaries/<kod>/podstawy.yaml`` deklaruje własne pole ``lingua:``
# (wartość = nazwa enum-a ``lingua.Language``, np. ``POLISH``, ``GERMAN``).
# Dzięki temu dodanie nowego języka bazowego (de/es/fr → 13.5+) sprowadza się
# do utworzenia folderu z plikami YAML — bez zmian w kodzie Pythona, spójnie
# z obietnicą „nowy język = nowy folder", którą trzymamy też dla dynamicznego
# dispatchu akcentów (``zastosuj_reguly_fonetyczne``) i ``dostepne_jezyki_bazowe``.

_LINGUA_MAPOWANIE_CACHE: dict[str, Any] | None = None

# Nazwy, które człowiek wpisuje odruchowo, a których enum ``lingua.Language``
# NIE ZNA, choć sam język obsługuje pod inną nazwą. To nie literówki (te łapie
# `difflib` niżej), a rozjazdy NAZEWNICTWA — i najgroźniejsza klasa, bo paczka
# wygląda na poprawną: „norweski" w lingua istnieje wyłącznie jako dwa odrębne
# standardy pisane, a „flamandzki" jako niderlandzki.
_LINGUA_ALIASY: dict[str, tuple[str, ...]] = {
    "NORWEGIAN": ("BOKMAL", "NYNORSK"),
    "SLOVENIAN": ("SLOVENE",),
    "FLEMISH": ("DUTCH",),
    "FILIPINO": ("TAGALOG",),
    "MANDARIN": ("CHINESE",),
    "FARSI": ("PERSIAN",),
    "MOLDOVAN": ("ROMANIAN",),
    "BRAZILIAN": ("PORTUGUESE",),
}


def _podpowiedz_nazwe_lingua(wartosc: str, kod: str = "") -> list[str]:
    """Nazwy enuma, które user prawdopodobnie miał na myśli (może być pusta).

    TRZY źródła, w tej kolejności. Pierwszym jest od v18.29.0 KANON po kodzie
    ISO folderu (:mod:`jezyki_lingua`) i to nie jest kolejna heurystyka:
    folder nazywa się ``sv``, więc jedyną poprawną wartością pola jest
    ``SWEDISH``. Podpowiedź przestaje być zgadywaniem podobieństwa nazw i staje
    się odpowiedzią — a użytkownik Managera Reguł, który wpisał ``NORWEGIAN``
    w folderze ``nb``, dostaje ``BOKMAL`` zamiast trzech kandydatów do
    samodzielnej weryfikacji.

    Dopiero dla folderu POZA kanonem (kod, którego detektor nie zna, albo
    nietypowa nazwa folderu) zostają dwa dawne źródła: kuratorska mapa
    :data:`_LINGUA_ALIASY` (rozjazd nazewnictwa) i ``difflib`` (literówka).
    Kandydaci z obu są weryfikowani przez ``hasattr``, żeby zmiana enuma
    w nowszej wersji lingua nie zaczęła produkować martwych podpowiedzi.

    Wynik ``difflib`` jest DODATKOWO filtrowany po pierwszej literze i to nie
    jest ozdoba — zmierzone na wersji 2.1.1: bez tego filtra „NORWEGIAN"
    dostaje podpowiedź „GEORGIAN", a „FLEMISH" (przy luźniejszym progu)
    „POLISH". Podpowiedź semantycznie absurdalna jest gorsza niż jej brak, bo
    użytkownik nie ma jak jej zweryfikować. Filtr zachowuje przy tym WSZYSTKIE
    trafienia prawdziwe (POLSIH→POLISH, GERMEN→GERMAN, ICELANDIAN→ICELANDIC,
    SLOVENIAN→SLOVENE).
    """
    if _LinguaLanguage is None:
        return []
    nazwa = wartosc.strip().upper()
    z_kanonu = jezyki_lingua.nazwa_enuma(kod) if kod else None
    # `getattr` obowiązuje TAKŻE kandydata z kanonu: kanon jest lustrem enuma,
    # ale lustrem STATYCZNYM, więc po aktualizacji biblioteki u kogoś, kto nie
    # odpalił `audyt_podstaw --bramka`, mógłby podpowiadać martwą nazwę
    # (audyt 2026-09-08, N4).
    if (z_kanonu and z_kanonu != nazwa
            and getattr(_LinguaLanguage, z_kanonu, None) is not None):
        return [z_kanonu]
    kandydaci: list[str] = [
        n for n in _LINGUA_ALIASY.get(nazwa, ())
        if getattr(_LinguaLanguage, n, None) is not None
    ]
    if kandydaci:
        return kandydaci
    if not nazwa[:1].isalpha():
        return []
    wszystkie = [n for n in dir(_LinguaLanguage) if n.isupper()]
    return [
        n for n in difflib.get_close_matches(nazwa, wszystkie, n=3, cutoff=0.7)
        if n[:1] == nazwa[:1]
    ]


def _zbuduj_mapowanie_lingua() -> dict[str, Any]:
    """Skanuje ``dictionaries/<kod>/podstawy.yaml`` i zwraca mapę ISO → ``Language``.

    Pomija języki, których ``podstawy.yaml`` nie deklaruje pola ``lingua``,
    deklaruje je pustym stringiem albo wartością nieznaną dla aktualnej
    wersji ``lingua-language-detector`` (np. literówka, nowsze enum-y, jeszcze
    nieobsługiwany przez paczkę). Wynik jest cache'owany — pierwszy skan
    woła się przy budowie detektora, kolejne wywołania są O(1).

    Te dwa pominięcia różnią się jednak stopniem winy i od v18.26.1 różnią się
    też widocznością. BRAK pola to świadoma decyzja autora paczki, której
    `lingua` nie obsługuje (szablon Managera Reguł każe wtedy pole
    zakomentować) — zostaje ciche. Wartość, której detektor NIE ZNA, jest
    usterką i trafia do rejestru `PominietyPlik`, czyli do raportu, który
    użytkownik zobaczy — razem z podpowiedzią najbliższych poprawnych nazw.

    Wynik ``{}`` (np. brak ``lingua-py`` w środowisku albo żaden
    ``podstawy.yaml`` nie ma pola ``lingua``) prowadzi do całkowitego wyłączenia
    detektora — :func:`_wykryj_jezyk_fragmentu` zwróci wtedy każdorazowo
    ``fallback`` (czyli język aktywny w GUI).
    """
    global _LINGUA_MAPOWANIE_CACHE
    if _LINGUA_MAPOWANIE_CACHE is not None:
        return _LINGUA_MAPOWANIE_CACHE
    if _LinguaLanguage is None:
        _LINGUA_MAPOWANIE_CACHE = {}
        return _LINGUA_MAPOWANIE_CACHE

    mapa: dict[str, Any] = {}
    for kod in _jezyki_obecne_w_dictionaries():
        wartosc = _zaladuj_podstawy(kod).get("lingua")
        if not isinstance(wartosc, str) or not wartosc.strip():
            continue
        nazwa_enuma = wartosc.strip().upper()
        # `getattr` zamiast `Language[...]`, żeby nieznana nazwa nie wyrzucała
        # KeyError na każdym imporcie modułu — defensywnie pomijamy.
        kandydat = getattr(_LinguaLanguage, nazwa_enuma, None)
        if kandydat is None:
            # Do v18.26.0 szedł tu wyłącznie `_dev_log`, czyli konsola
            # dewelopera — w paczce release NIEISTNIEJĄCA. Użytkownik, który
            # dodał język Managerem Reguł i wpisał nazwę nieznaną detektorowi,
            # nie dostawał ŻADNEGO sygnału: paczka po prostu nie brała udziału
            # w detekcji. Rejestr `PominietyPlik` (v18.24.2) jest tym kanałem.
            podpowiedzi = _podpowiedz_nazwe_lingua(wartosc, kod)
            szczegol = f"lingua: {wartosc.strip()}"
            if podpowiedzi:
                szczegol += " -> " + ", ".join(podpowiedzi)
            zglos_pominiecie(
                os.path.join(DICTIONARIES_DIR, kod, "podstawy.yaml"),
                POWOD_LINGUA,
                szczegol,
            )
            continue
        mapa[kod] = kandydat

    _LINGUA_MAPOWANIE_CACHE = mapa
    return _LINGUA_MAPOWANIE_CACHE


def jezyki_w_detekcji() -> list[str]:
    """Kody ISO paczek, które BIORĄ UDZIAŁ w automatycznej detekcji języka.

    Publiczne wejście dla diagnostyki (``gui_diagnostyka.przeskanuj_reguly``):
    wywołanie wymusza skan WSZYSTKICH paczek, więc rejestr powodów dowiaduje
    się o niezmapowanym polu ``lingua:`` niezależnie od tego, w które narzędzia
    użytkownik zdążył wejść. Różnica wobec reguł Reżysera jest tu istotna:
    tamte są per język interfejsu, a detektor jest JEDEN dla całej aplikacji,
    więc pytanie „czy moje pliki są dobre" musi obejmować każdą paczkę.

    Paczka poza wynikiem nadal działa — traci tylko rozpoznawanie po treści
    (język wybiera się wtedy w Poligloci ręcznie, z wymuszeniem na cały
    dokument).
    """
    return sorted(_zbuduj_mapowanie_lingua())


def _zbuduj_mapowanie_lingua_to_iso() -> dict[str, str]:
    """Odwrócone mapowanie ``Language.name → ISO 639-1`` na bazie tej samej mapy."""
    return {lang.name: iso for iso, lang in _zbuduj_mapowanie_lingua().items()}


def _jezyki_obecne_w_dictionaries() -> list[str]:
    """Zwraca listę kodów języków, które mają chociaż ``podstawy.yaml``.

    Rozluźniona wersja :func:`dostepne_jezyki_bazowe` — nie wymaga ``szyfry/``
    ani ``akcenty/``, a jedynie obecności pliku ``podstawy.yaml``. Używana
    tylko do nakarmienia ``LanguageDetectorBuilder`` zestawem języków, który
    chcemy rozpoznawać; rzeczywista weryfikacja kompletności reguł odbywa
    się dopiero w dyspozytorach (``_przetworz_rezyser`` / ``_przetworz_szyfrant``)
    przy pomocy :class:`BrakRegulyDlaJezykaError`.
    """
    if not os.path.isdir(DICTIONARIES_DIR):
        return []
    wynik: list[str] = []
    for nazwa in sorted(os.listdir(DICTIONARIES_DIR)):
        folder = os.path.join(DICTIONARIES_DIR, nazwa)
        if not os.path.isdir(folder):
            continue
        if os.path.isfile(os.path.join(folder, "podstawy.yaml")):
            wynik.append(nazwa)
    return wynik


_LINGUA_DETEKTOR: Any = None       # cache singletona; budowa leniwa
_LINGUA_DETEKTOR_BLD_FAILED = False  # flaga, by nie powtarzać próby budowy


def _zbuduj_detektor_lingua() -> Any:
    """Lazy singleton ``LanguageDetector`` z lingua.

    Buduje detektor przy pierwszym wywołaniu, używając zestawu języków
    z :func:`_zbuduj_mapowanie_lingua` (czyli tych ``dictionaries/<kod>/``,
    których ``podstawy.yaml`` deklaruje pole ``lingua: <NAZWA_ENUMA>``).

    Lingua wymaga ≥ 2 języków w builderze – gdy w ``dictionaries/`` jest tylko
    jeden (lub zero) język z poprawnym polem ``lingua``, zwracamy ``None``
    i wywołujący spada na ``fallback``. Zwroty ``None`` są cache'owane przez
    flagę ``_LINGUA_DETEKTOR_BLD_FAILED``, żeby nie powtarzać prób budowy
    przy każdej detekcji fragmentu.
    """
    global _LINGUA_DETEKTOR, _LINGUA_DETEKTOR_BLD_FAILED

    if _LINGUA_DETEKTOR is not None:
        return _LINGUA_DETEKTOR
    if _LINGUA_DETEKTOR_BLD_FAILED:
        return None
    if _LinguaBuilder is None:
        _LINGUA_DETEKTOR_BLD_FAILED = True
        return None

    mapowanie = _zbuduj_mapowanie_lingua()
    if len(mapowanie) < 2:
        _LINGUA_DETEKTOR_BLD_FAILED = True
        return None

    _LINGUA_DETEKTOR = _LinguaBuilder.from_languages(*mapowanie.values()).build()
    return _LINGUA_DETEKTOR


def _wykryj_jezyk_fragmentu(tekst: str, fallback: str) -> str:
    """Wykrywa kod ISO języka pojedynczego fragmentu (akapitu).

    Zasady (każda w innym warunku):
      1. Tekst pusty / krótszy niż ``_MIN_TEKST_DLA_DETEKCJI`` → ``fallback``
         (dla A11y: pojedyncze „OK." nie powinno przerywać przetwarzania).
      2. Brak instancji lingua (import się nie udał, < 2 języki w
         ``dictionaries/``) → ``fallback``.
      3. ``detect_language_of`` zwraca ``None`` (lingua nie jest pewna) →
         ``fallback``.
      4. Wynik mapowany przez :func:`_zbuduj_mapowanie_lingua_to_iso`. Gdy
         ``Language.name`` nie ma odpowiednika w ``dictionaries/`` (teoretycznie
         nie powinno się zdarzyć — ten sam zestaw karmił builder) → ``fallback``.
    """
    if not isinstance(tekst, str) or len(tekst.strip()) < _MIN_TEKST_DLA_DETEKCJI:
        return fallback

    detektor = _zbuduj_detektor_lingua()
    if detektor is None:
        return fallback

    wynik = detektor.detect_language_of(tekst)
    if wynik is None:
        return fallback

    iso = _zbuduj_mapowanie_lingua_to_iso().get(wynik.name)
    if not iso:
        return fallback
    return iso if iso in _jezyki_obecne_w_dictionaries() else fallback


# ---------------------------------------------------------------------------
# Detektor PEŁNEGO kanonu Lingui — wyłącznie jako OPINIA dla użytkownika
# ---------------------------------------------------------------------------

_LINGUA_DETEKTOR_PELNY: Any = None      # cache singletona; budowa leniwa
_LINGUA_PELNY_BLD_FAILED = False        # flaga, by nie powtarzać próby budowy


def _zbuduj_detektor_pelny() -> Any:
    """Lazy singleton detektora znającego WSZYSTKIE języki z `jezyki_lingua`.

    Różnica wobec :func:`_zbuduj_detektor_lingua` jest różnicą ROLI, nie
    optymalizacji. Tamten detektor WYBIERA REGUŁY, więc musi być zawężony do
    paczek obecnych w ``dictionaries/`` — kod języka, dla którego nie ma
    reguł, byłby dla silnika bezużyteczny. Ten detektor niczego nie wybiera:
    jest OPINIĄ pokazywaną użytkownikowi w dialogu „Kody języka per akapit"
    Naprawiacza Tagów, a Naprawiacz istnieje właśnie dla języków, których
    paczki NIE MA (wstrzykuje sam tag, bez reguł fonetycznych). Zawężenie do
    dziewięciu paczek dawałoby tu opinię pewną i błędną: akapit islandzki
    w pliku bez paczki `is` zostałby nazwany niemieckim.

    Zmierzone 2026-09-12 na `lingua-language-detector`: build jest darmowy
    (modele ładują się leniwie, przy pierwszej detekcji), a koszt rośnie
    z LICZBĄ RÓŻNYCH języków, które detektor realnie dotknie. Na 30 akapitach
    w 5 językach: 2.8 ms/akapit i ~52 MB RSS ponad import; po 200 detekcjach
    w 15 językach: 2.4 ms/akapit i ~105 MB (dalej już nie rośnie). Rozmiar
    paczki nie rośnie ani o bajt — modele siedzą w rozszerzeniu Rust, które
    i tak jest w bundlu. Tryb ``with_low_accuracy_mode`` (1.0 ms, ~23 MB)
    odrzucony świadomie: patrzy tylko na trigramy, a akapit to często
    jedno–dwa zdania.

    Ten singleton NIE jest czyszczony przez :func:`wyczysc_cache_regul` —
    i to jest zamierzone. Tamten cache unieważnia stan czytany z
    ``dictionaries/``, a kanon Lingui jest statycznym lustrem biblioteki:
    zmienia się przy aktualizacji zależności, nie przy edycji paczki.
    """
    global _LINGUA_DETEKTOR_PELNY, _LINGUA_PELNY_BLD_FAILED

    if _LINGUA_DETEKTOR_PELNY is not None:
        return _LINGUA_DETEKTOR_PELNY
    if _LINGUA_PELNY_BLD_FAILED:
        return None
    if _LinguaBuilder is None or _LinguaLanguage is None:
        _LINGUA_PELNY_BLD_FAILED = True
        return None

    jezyki = []
    for nazwa_enuma, _ in jezyki_lingua.KANON.values():
        kandydat = getattr(_LinguaLanguage, nazwa_enuma, None)
        if kandydat is not None:
            jezyki.append(kandydat)
    if len(jezyki) < 2:                                     # pragma: no cover
        # Kanon rozjechany z biblioteką — pilnuje tego `audyt_podstaw --bramka`,
        # a tutaj po prostu nie ma z czego zbudować detektora.
        _LINGUA_PELNY_BLD_FAILED = True
        return None

    _LINGUA_DETEKTOR_PELNY = _LinguaBuilder.from_languages(*jezyki).build()
    return _LINGUA_DETEKTOR_PELNY


def opinia_detektora(tekst: str) -> str | None:
    """Kod ISO języka fragmentu w opinii detektora; ``None`` gdy brak opinii.

    ``None`` (a nie „jakiś kod") dostajesz w każdym przypadku, w którym
    opinia byłaby udawaniem wiedzy: fragment krótszy niż
    ``_MIN_TEKST_DLA_DETEKCJI`` znaków, brak ``lingua`` w środowisku,
    detektor niepewny, albo wykryty enum bez odpowiednika w kanonie. GUI
    pokazuje wtedy myślnik — użytkownik ma widzieć różnicę między „detektor
    mówi: fiński" a „detektor nie ma zdania".

    To funkcja WYŁĄCZNIE informacyjna: nie zasila wyboru reguł ani nie
    wchodzi do pliku wynikowego bez jawnej decyzji użytkownika (kanon 19.1:
    język wyniku jest danymi, nie zgadywaniem).
    """
    if not isinstance(tekst, str) or len(tekst.strip()) < _MIN_TEKST_DLA_DETEKCJI:
        return None

    detektor = _zbuduj_detektor_pelny()
    if detektor is None:
        return None

    wynik = detektor.detect_language_of(tekst)
    if wynik is None:
        return None

    return jezyki_lingua.iso_dla_enuma(wynik.name)


def nazwa_dla_opinii(kod: str) -> str:
    """Nazwa języka do POKAZANIA obok kodu ISO (bez wycieku polszczyzny).

    Kolejność źródeł jest kolejnością jakości:
      1. natywna nazwa z ``<kod>/podstawy.yaml`` (``Suomi``, ``Русский``) —
         dostępna dla dziewięciu paczek i z definicji w dobrym języku,
      2. nazwa enuma z kanonu Lingui, w formie tytułowej (``Icelandic``) —
         dla pozostałych 66 języków, których paczki nie ma.

    Dlaczego NIE `jezyki_lingua.nazwa_polska`: ta jest identyfikatorem dla
    dev-toolingu (nazwy plików akcentów) i po polsku. W interfejsie
    niemieckim czy rosyjskim „islandzki" byłoby wyciekiem PL, a runtime
    używa z kanonu wyłącznie `nazwa_enuma` (tak samo robi
    `manager_regul_szablony`).
    """
    if not kod:
        return ""
    if kod in _jezyki_obecne_w_dictionaries():
        natywna = natywna_nazwa(kod)
        if natywna and natywna != kod:
            return natywna
    enum = jezyki_lingua.nazwa_enuma(kod)
    if enum:
        return enum.replace("_", " ").title()
    return kod


# ---------------------------------------------------------------------------
# Wyjątek: brak reguły dla wykrytego języka fragmentu
# ---------------------------------------------------------------------------

class BrakRegulyDlaJezykaError(RuntimeError):
    """Lingua wykryła w tekście język, dla którego brakuje żądanej reguły.

    Podnoszony przez :func:`_przetworz_rezyser` / :func:`_przetworz_szyfrant`,
    gdy w tekście wejściowym znajdzie się akapit w języku ``L``, a w
    ``dictionaries/L/<podfolder>/<wariant>.yaml`` nie istnieje plik z regułą.
    GUI łapie ten wyjątek osobno i wyświetla **długi techniczny komunikat
    w ``wx.Dialog`` z ``TextCtrl`` ``TE_READONLY``** (zgodnie z konwencją
    A11y: krótkie powiadomienia → ``wx.MessageBox``, długie techniczne →
    ``wx.Dialog`` z polem do skopiowania).

    Atrybuty:
        jezyk_kod:        Kod ISO 639-1 wykrytego języka (np. ``"ru"``).
        jezyk_natywna:    Nazwa języka w jego natywnym brzmieniu
                          (np. ``"Русский"``); jeżeli nie ma ``podstawy.yaml``
                          — równe ``jezyk_kod``.
        tryb:             ``"Rezyser"`` lub ``"Szyfrant"``.
        wariant:          ``id`` wariantu (np. ``"jakanie"``).
        oczekiwany_folder: Względna ścieżka brakującej reguły, np.
                          ``"dictionaries/ru/szyfry"``. Pomaga użytkownikowi
                          natychmiast trafić do miejsca, w którym powinien
                          dorzucić plik YAML.
    """

    def __init__(self, jezyk_kod: str, jezyk_natywna: str, tryb: str,
                 wariant: str, oczekiwany_folder: str) -> None:
        self.jezyk_kod = jezyk_kod
        self.jezyk_natywna = jezyk_natywna
        self.tryb = tryb
        self.wariant = wariant
        self.oczekiwany_folder = oczekiwany_folder
        komunikat = (
            f"Wykryto fragment w języku {jezyk_natywna} (kod '{jezyk_kod}'), "
            f"ale brakuje reguły '{wariant}' w folderze {oczekiwany_folder}.\n\n"
            f"Utwórz plik {oczekiwany_folder}/{wariant}.yaml przed "
            f"kontynuowaniem przetwarzania, albo usuń fragmenty w tym "
            f"języku z tekstu wejściowego."
        )
        super().__init__(komunikat)


# ---------------------------------------------------------------------------
# Segmentacja tekstu na akapity z ochroną tagów HTML
# ---------------------------------------------------------------------------

# Segment to trójka ``(jezyk_iso, tresc, czy_przetwarzac)``:
#   * ``jezyk_iso``       – kod języka (sticky-fallback dla krótkich akapitów),
#   * ``tresc``           – dosłowny fragment tekstu (akapit, separator, tag),
#   * ``czy_przetwarzac`` – ``True`` tylko dla właściwych akapitów tekstowych;
#                            ``False`` dla tagów HTML i separatorów ``\n\n``,
#                            które należy przepisać 1:1 do wyniku.
#
# UWAGA (v19.1) — ``jezyk_iso`` znaczy CO INNEGO na wejściu i na wyjściu:
#   * lista z :func:`_segmentuj_z_ochrona_tagow` (WEJŚCIE) niesie język
#     ŹRÓDŁA akapitu — tym wybieramy reguły (alfabet Cezara, plik akcentu);
#   * lista w side-channelu ``opcje["_segmenty_wynikowe"]`` (WYJŚCIE) niesie
#     język GŁOSU, który ma przeczytać wynik, czyli pole ``iso`` wariantu
#     zastosowanego do tego akapitu. Dla akcentu to język CELU (``pl`` → ``fi``),
#     dla szyfru i oczyszczenia — własny język paczki, więc równy źródłowemu.
#     Zamiana tych dwóch znaczeń miejscami była defektem do v19.0: akcent
#     fiński zapisywał ``<html lang="fi">`` i 30 × ``<p lang="pl">``, czyli
#     kasował własny efekt (czytnik wracał na polski głos w każdym akapicie).
Segment = tuple[str, str, bool]


def _segmentuj_z_ochrona_tagow(
    tekst: str,
    fallback_jezyk: str,
    wymus_jezyk: str | None = None,
) -> list[Segment]:
    """Dzieli tekst na segmenty z wykrytym językiem; chroni tagi HTML i separatory.

    Algorytm dwuwarstwowy:
      1. ``re.split(r"(<[^>]+>)", tekst)`` → naprzemienne pozycje tekst/tag.
         Tagi (indeksy nieparzyste) trafiają do wyniku z flagą ``False``
         i nie są nigdy poddawane detekcji ani transformacjom.
      2. Każdy fragment-tekst (indeksy parzyste) dzielimy ponownie:
         ``re.split(r"(\\n\\s*\\n)", ...)`` → akapity i pomiędzy nimi
         dosłowne separatory ``\\n\\s*\\n``. Separatory zachowujemy 1:1.
      3. Dla każdego niepustego akapitu wywołujemy
         :func:`_wykryj_jezyk_fragmentu` z fallbackiem na język poprzedniego
         akapitu – tym samym krótka linia („Tak.", „OK.") dziedziczy język
         po sąsiadach zamiast wymuszać reset na ``fallback_jezyk``.

    Pierwszy akapit (gdy nie ma jeszcze „poprzedniego") używa
    ``fallback_jezyk`` – zwykle parametr ``jezyk`` przekazany do
    :func:`przetworz`, czyli język aktywny w GUI.

    ``wymus_jezyk`` (18.11): kod języka WYŁĄCZAJĄCY detekcję — każdy akapit
    dostaje wskazany język bez pytania lingua. Zasilany przez
    ``opcje["wymus_jezyk"]`` z checkboxa „wymuś język" w GUI Poligloty;
    kluczowy dla odwracalnego szyfrowania wielowarstwowego (jeden alfabet
    Cezara na cały dokument zamiast alfabetu per wykryty język akapitu).

    Zwraca listę gotową do iteracji w dyspozytorach – wszystko jest tam
    gotowe: kod języka per akapit, dosłowna treść, flaga „przetwarzaj".
    """
    if not isinstance(tekst, str) or not tekst:
        return []

    if wymus_jezyk:
        fallback_jezyk = wymus_jezyk

    czesci = re.split(r"(<[^>]+>)", tekst)
    wynik: list[Segment] = []
    poprzedni_jezyk = fallback_jezyk

    for i, czesc in enumerate(czesci):
        if i % 2 == 1:
            # Tag HTML – zachowaj 1:1, nie analizuj.
            wynik.append((poprzedni_jezyk, czesc, False))
            continue
        if not czesc:
            continue
        # Drugi poziom: akapity (\n\n) z zachowaniem separatora.
        akapity = re.split(r"(\n\s*\n)", czesc)
        for j, akapit in enumerate(akapity):
            if j % 2 == 1:
                # Separator między akapitami – nie tłumaczymy.
                wynik.append((poprzedni_jezyk, akapit, False))
                continue
            if not akapit:
                continue
            jez = wymus_jezyk or _wykryj_jezyk_fragmentu(
                akapit, fallback=poprzedni_jezyk)
            wynik.append((jez, akapit, True))
            poprzedni_jezyk = jez

    return wynik


def wykryj_jezyk_zrodlowy(
    tekst: str,
    *,
    fallback: str = "pl",
    dostepne: list[str] | None = None,
) -> str:
    """Wykrywa kod języka tekstu; waliduje wynik wobec ``dictionaries/``.

    Funkcja jest „konserwatywna" – zwraca ``fallback`` w każdym z wypadków,
    w których wynik detekcji byłby niemiarodajny:

      1. ``lingua`` nie zostało zainstalowane (brak importu na starcie),
      2. ``tekst`` jest za krótki (<``_MIN_TEKST_DLA_DETEKCJI`` znaków
         po strip),
      3. detektor zwraca ``None`` (zbyt mało sygnału do klasyfikacji),
      4. wykryty kod NIE występuje w liście ``dostepne`` – nawet jeśli
         lingua trafiła, GUI musi pozostać przy języku, który ma komplet
         działających słowników (``szyfry/`` + ``akcenty/`` + ``gui/``).

    Dzięki punktowi (4) funkcja jest „multi-language ready": dziś zawsze
    zwraca ``"pl"`` (bo to jedyny *kompletny* język), ale gdy
    ``dictionaries/en/`` dostanie szyfry, zacznie zwracać ``"en"`` dla
    angielskich tekstów.

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
        >>> wykryj_jezyk_zrodlowy("The quick brown fox jumps over the lazy dog.",
        ...                       dostepne=["pl"])  # zawężone do PL
        'pl'
    """
    # Szybka ścieżka: za krótki tekst → fallback (bez budowania detektora).
    if not isinstance(tekst, str) or len(tekst.strip()) < _MIN_TEKST_DLA_DETEKCJI:
        return fallback

    detektor = _zbuduj_detektor_lingua()
    if detektor is None:
        return fallback

    wynik = detektor.detect_language_of(tekst)
    if wynik is None:
        return fallback

    kod_wykryty = _zbuduj_mapowanie_lingua_to_iso().get(wynik.name)
    if not kod_wykryty:
        return fallback

    if dostepne is None:
        dostepne = dostepne_jezyki_bazowe()

    return kod_wykryty if kod_wykryty in dostepne else fallback


# =============================================================================
# Tryb Reżysera – pipeline akcentu fonetycznego z pliku YAML
# =============================================================================

def _aplikuj_akcent_z_yaml(tekst: str, cfg: dict, podstawy: dict,
                           jezyk: str = "pl") -> str:
    """Uruchamia pięcioetapowy pipeline akcentu wg flag w ``cfg``.

    Etapy (wykonywane w stałej kolejności):
        1. ``czysc_tekst_tts``
        2. ``normalizuj_liczby``      (gdy nie użyto pełnego czyszczenia)
        3. ``usun_polskie_znaki``
        4. ``zamiany`` (właściwe reguły fonetyczne akcentu)
        5. ``skleja_pojedyncze_litery``

    13.3: ``jezyk`` decyduje o locale ``num2words`` — domyślnie ``"pl"``
    dla backward-compat, ale wywołujący (``_przetworz_rezyser``) przekazuje
    rzeczywisty język tekstu źródłowego.
    """
    if cfg.get("czysc_tekst_tts"):
        tekst = oczysc_tekst_tts(
            tekst,
            z_normalizacja=cfg.get("normalizuj_liczby", False),
            jezyk=jezyk,
        )
    elif cfg.get("normalizuj_liczby"):
        tekst = normalizuj_liczby(tekst, jezyk)

    if cfg.get("usun_polskie_znaki"):
        tekst = _usun_polskie_znaki(tekst, podstawy)

    tekst = _zastosuj_zamiany(tekst, cfg.get("zamiany", []))

    if cfg.get("skleja_pojedyncze_litery"):
        tekst = sklej_pojedyncze_litery(tekst)

    return tekst


# ---------------------------------------------------------------------------
# Silnik fonetyczny akcentów (publiczne API trybu Reżysera)
# ---------------------------------------------------------------------------
# ``zastosuj_reguly_fonetyczne`` stosuje WYŁĄCZNIE reguły fonetyczne wybranego
# akcentu (normalizacja liczb + transliteracja + zamiany + scalanie
# pojedynczych liter), bez pełnego oczyszczania TTS. Dzięki temu moduł
# Reżysera może wywoływać ją punktowo na pojedynczych kwestiach dialogowych
# bez ryzyka usunięcia ich zawartości (np. gwiazdek z didaskaliów). Od v17.5
# tryb Reżysera woła tę funkcję DYNAMICZNIE po id akcentu (= jego nazwie z
# Księgi Świata) — statyczne wrappery ``akcent_*`` oraz generator
# ``odswiez_rezysera.py`` zostały zlikwidowane (działały tylko ze źródła; w
# paczce frozen były martwe). Patrz [[reguly_architektury]].

def zastosuj_reguly_fonetyczne(tekst: str, wariant: str,
                               jezyk: str = "pl") -> str:
    """Stosuje reguły fonetyczne wybranego akcentu – bez czyszczenia TTS.

    Równoważne staremu ``akcent_*`` z pre-refaktorowej wersji: zachowuje
    gwiazdki, hashtagi i nawiasy kwadratowe (didaskalia), zmieniając
    wyłącznie fonetykę.
    """
    cfg = wariant_po_id(TRYB_REZYSER, jezyk, wariant) or {}
    podstawy = _zaladuj_podstawy(jezyk)
    # Audyt 18.12 (W-5): flagi YAML honorowane jak w `_aplikuj_akcent_z_yaml`
    # (ścieżka Poligloty) — dawniej normalizacja/transliteracja/sklejanie
    # szły tu BEZWARUNKOWO, więc ten sam akcent brzmiał inaczej w Reżyserze
    # i Poliglocie (pl/rosyjski z `usun_polskie_znaki: false` gubił
    # zmiękczenia: „jaźń”→„язн” zamiast „яжнь”, bo podstawy spłaszczały
    # ś/ź przed transliteracją). Jedyna zamierzona różnica ścieżek to brak
    # etapu `czysc_tekst_tts` (Reżyser zachowuje didaskalia).
    if cfg.get("normalizuj_liczby"):
        tekst = normalizuj_liczby(tekst, jezyk)
    if cfg.get("usun_polskie_znaki"):
        tekst = _usun_polskie_znaki(tekst, podstawy)
    tekst = _zastosuj_zamiany(tekst, cfg.get("zamiany", []))
    if cfg.get("skleja_pojedyncze_litery"):
        tekst = sklej_pojedyncze_litery(tekst)
    return tekst


def _przetworz_rezyser(tekst: str, jezyk: str, cfg: dict, opcje: dict) -> str:
    """Rezyser: akcent / oczyszczenie / naprawiacz – z dynamiczną detekcją języka.

    13.5: silnik segmentuje wejście na akapity (z ochroną tagów HTML),
    wykrywa język każdego osobno i pobiera dla niego *własną* konfigurację
    wariantu. Brak reguły dla wykrytego języka → :class:`BrakRegulyDlaJezykaError`.

    Side-channel: do ``opcje["_segmenty_wynikowe"]`` zapisywana jest lista
    krotek ``(jezyk_iso, fragment_wynikowy, czy_przetwarzany)`` zachowująca
    kolejność z wejścia. :func:`zapisz_wynik` używa jej do wstrzyknięcia
    tagu ``lang`` per akapit bez konieczności ponownej detekcji.
    """
    kategoria = cfg.get("kategoria", "")
    wariant_id = cfg.get("id", "")

    # Naprawiacz tagów nie modyfikuje treści – tylko wstrzykiwanie ISO
    # w :func:`zapisz_wynik`. Tam też dzieje się detekcja per akapit.
    if kategoria == "naprawiacz":
        return tekst

    # Oczyszczenie: pipeline TTS niezależny od reguł YAML konkretnego języka.
    # Detekcja per akapit potrzebna tylko dla locale ``num2words``.
    # Języka WYNIKU nie przeliczamy: oczyszczenie nie zmienia języka tekstu,
    # a niezmiennik paczek („``iso`` = język głosu, który ma przeczytać
    # wynik") daje tu wprost język akapitu — `<kod>/akcenty/oczyszczenie*.yaml`
    # deklaruje `iso: <kod>` w każdej z dziewięciu paczek. Pilnuje tego bramka
    # `test_lang_wyniku.py` (klasa „iso wariantu niezmieniającego języka").
    if kategoria == "oczyszczenie":
        segmenty_in = _segmentuj_z_ochrona_tagow(
            tekst, fallback_jezyk=jezyk,
            wymus_jezyk=opcje.get("wymus_jezyk"))
        wyniki: list[str] = []
        zapisane: list[Segment] = []
        for jez_seg, fragment, czy_przetwarzac in segmenty_in:
            if not czy_przetwarzac:
                wyniki.append(fragment)
                zapisane.append((jez_seg, fragment, False))
                continue
            wynik_fr = oczysc_tekst_tts(
                fragment,
                z_normalizacja=cfg.get("normalizuj_liczby", True),
                jezyk=jez_seg,
            )
            wyniki.append(wynik_fr)
            zapisane.append((jez_seg, wynik_fr, True))
        opcje["_segmenty_wynikowe"] = zapisane
        return "".join(wyniki)

    # Zwykły akcent – per fragment szukamy YAML-a dla wykrytego języka.
    segmenty_in = _segmentuj_z_ochrona_tagow(
        tekst, fallback_jezyk=jezyk,
        wymus_jezyk=opcje.get("wymus_jezyk"))
    wyniki = []
    zapisane = []
    iso_sticky = str(cfg.get("iso") or jezyk).strip() or jezyk
    for jez_seg, fragment, czy_przetwarzac in segmenty_in:
        if not czy_przetwarzac:
            wyniki.append(fragment)
            zapisane.append((iso_sticky, fragment, False))
            continue

        cfg_jez = wariant_po_id(TRYB_REZYSER, jez_seg, wariant_id)
        if cfg_jez is None:
            raise BrakRegulyDlaJezykaError(
                jezyk_kod=jez_seg,
                jezyk_natywna=natywna_nazwa(jez_seg),
                tryb=TRYB_REZYSER,
                wariant=wariant_id,
                oczekiwany_folder=f"dictionaries/{jez_seg}/akcenty",
            )
        podstawy_jez = _zaladuj_podstawy(jez_seg)
        wynik_fr = _aplikuj_akcent_z_yaml(fragment, cfg_jez, podstawy_jez, jez_seg)
        # v19.1: do side-channelu idzie ``iso`` WARIANTU (język głosu), nie
        # ``jez_seg`` (język źródła). Akcent po to istnieje, żeby wynik
        # przeczytał głos docelowy — ``pl/akcenty/finski.yaml`` i
        # ``ru/akcenty/finski.yaml`` deklarują oba ``iso: fi``, więc dokument
        # mieszany językowo i tak wychodzi jednojęzyczny dla czytnika.
        iso_sticky = str(cfg_jez.get("iso") or jez_seg).strip() or jez_seg
        wyniki.append(wynik_fr)
        zapisane.append((iso_sticky, wynik_fr, True))

    opcje["_segmenty_wynikowe"] = zapisane
    return "".join(wyniki)


# =============================================================================
# Tryb Szyfranta – algorytmy (parametryzowane YAML-em)
# =============================================================================
# Każdy algorytm dostaje (tekst, cfg, podstawy, opcje) i zwraca string.
# `cfg`      – słownik wczytany z <szyfr>.yaml,
# `podstawy` – słownik wczytany z <język>/podstawy.yaml,
# `opcje`    – kwargs przekazane przez GUI do :func:`przetworz` (np. przesuniecie).

# Regex łapiący pojedyncze słowa we WSZYSTKICH alfabetach Unicode (łacińskim,
# kirylickim, greckim, …). Klasa `[^\W\d_]+` to "litery dowolnego skryptu" — bez
# cyfr i bez `_`. Granice słów są implicit (klasa nie obejmuje spacji ani
# interpunkcji). 13.5: zmiana z `[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+` była konieczna,
# żeby `_algo_typoglikemia` i `_algo_jakanie` zadziałały na rosyjskim
# (cyrylica). Łatka analogiczna do tej w `core_rezyser.py` z 13.3.
_REGEX_SLOWA = r"[^\W\d_]+"


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
              "AĄBCĆDEĘFGHIJKLŁMNŃOÓPQRSŚTUVWXYZŹŻ"
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
    """Szyfrant: dispatcher na algorytm – z dynamiczną detekcją języka per akapit.

    13.5: dla każdego akapitu pobierane są reguły z ``dictionaries/<jezyk>/
    szyfry/<wariant>.yaml`` (gdzie ``<jezyk>`` = wynik detekcji lingua,
    ``<wariant>`` = id wybrane przez użytkownika w GUI). Brak pliku dla
    wykrytego języka → :class:`BrakRegulyDlaJezykaError`.

    Cezar: pole ``opcje["przesuniecie_faktyczne"]`` (zapisywane przez
    :func:`_algo_cezar` po pierwszym losowaniu) jest współdzielone między
    fragmentami przez referencję ``opcje`` – dzięki temu pierwszy akapit
    losuje, a kolejne reużywają tego samego przesunięcia. Każdy język ma
    własny alfabet (mod ``len(alfabet)`` różny), więc finalny shift na
    rosyjskim akapicie przy ``n=33`` da inny wynik niż na polskim akapicie
    przy ``n=32`` – to spójne z założeniem multi-language szyfrowania.
    """
    wariant_id = cfg.get("id", "")
    nazwa_algo_glob = cfg.get("algorytm", "")
    if nazwa_algo_glob and nazwa_algo_glob not in _ALGORYTMY_SZYFROW:
        raise ValueError(
            f"Nieznany algorytm szyfru: „{nazwa_algo_glob}”. "
            f"Dostępne: {sorted(_ALGORYTMY_SZYFROW)}"
        )

    segmenty_in = _segmentuj_z_ochrona_tagow(
        tekst, fallback_jezyk=jezyk,
        wymus_jezyk=opcje.get("wymus_jezyk"))
    wyniki: list[str] = []
    zapisane: list[Segment] = []
    iso_sticky = str(cfg.get("iso") or jezyk).strip() or jezyk

    for jez_seg, fragment, czy_przetwarzac in segmenty_in:
        if not czy_przetwarzac:
            wyniki.append(fragment)
            zapisane.append((iso_sticky, fragment, False))
            continue

        cfg_jez = wariant_po_id(TRYB_SZYFRANT, jez_seg, wariant_id)
        if cfg_jez is None:
            raise BrakRegulyDlaJezykaError(
                jezyk_kod=jez_seg,
                jezyk_natywna=natywna_nazwa(jez_seg),
                tryb=TRYB_SZYFRANT,
                wariant=wariant_id,
                oczekiwany_folder=f"dictionaries/{jez_seg}/szyfry",
            )
        podstawy_jez = _zaladuj_podstawy(jez_seg)

        # 13.3: normalizacja diakrytyki PRZED czyszczeniem i algorytmem.
        # 13.5: per fragment, używając podstaw języka FRAGMENTU – inaczej
        # rosyjski akapit dostałby polskie mapowania znaków.
        fragment_norm = _usun_polskie_znaki(fragment, podstawy_jez)
        fragment_czysty = oczysc_tekst_tts(fragment_norm, z_normalizacja=True,
                                            jezyk=jez_seg)

        nazwa_algo = cfg_jez.get("algorytm", "")
        funkcja = _ALGORYTMY_SZYFROW.get(nazwa_algo)
        if funkcja is None:
            raise ValueError(
                f"Nieznany algorytm szyfru: „{nazwa_algo}” "
                f"(plik dictionaries/{jez_seg}/szyfry/{wariant_id}.yaml). "
                f"Dostępne: {sorted(_ALGORYTMY_SZYFROW)}"
            )
        wynik_fr = funkcja(fragment_czysty, cfg_jez, podstawy_jez, opcje)
        # v19.1: język WYNIKU z pola ``iso`` wariantu — ta sama reguła co
        # w akcencie. Dla szyfrów `iso` = własny język paczki, więc dziś
        # wychodzi na to samo co ``jez_seg``; reguła jest jedna po to, żeby
        # szyfr o innym celu (np. transliteracja na inny alfabet) nie musiał
        # dopisywać wyjątku w ścieżce zapisu.
        iso_sticky = str(cfg_jez.get("iso") or jez_seg).strip() or jez_seg
        wyniki.append(wynik_fr)
        zapisane.append((iso_sticky, wynik_fr, True))

    opcje["_segmenty_wynikowe"] = zapisane
    return "".join(wyniki)


# =============================================================================
# Publiczne API – punkt wejścia dla GUI
# =============================================================================

def przetworz(
    tekst: str,
    tryb: str,
    jezyk: str = "pl",
    wariant: str | None = None,
    opcje: dict[str, Any] | None = None,
) -> str:
    """Uruchamia wybrane przetwarzanie i zwraca gotowy tekst.

    Args:
        tekst:   Tekst źródłowy (dowolnej długości).
        tryb:    ``"Rezyser"`` lub ``"Szyfrant"``.
        jezyk:   Kod ISO 639-1 języka bazowego (domyślnie ``"pl"``).
        wariant: ``id`` z YAML-a (np. ``"islandzki"``, ``"odwracanie"``),
                 ewentualnie etykieta widoczna w GUI.
        opcje:   MUTOWALNY słownik parametrów zależnych od algorytmu, np.
                 ``przesuniecie`` – int, dla szyfru Cezara (0 = losuj);
                 ``wymus_jezyk`` – str (18.11), pomija detekcję lingua per
                 akapit i przetwarza cały dokument regułami wskazanego
                 języka. To zarazem kanał ZWROTNY: silnik dopisuje do niego
                 ``_segmenty_wynikowe`` (mapa języków per akapit dla
                 :func:`zapisz_wynik`) oraz ``przesuniecie_faktyczne``
                 (wylosowany shift Cezara). Do v18.7.x parametry szły przez
                 ``**opcje`` — Python repakował je do nowego słownika i
                 mutacje silnika NIGDY nie wracały do GUI (side-channel był
                 martwy od 13.5; skutek: tag ``lang`` liczony ponownie na
                 tekście już zniekształconym transformacją).

    Returns:
        Przetworzony tekst jako string.

    Raises:
        ValueError: gdy tryb jest nieznany lub wariantu nie odnaleziono.
    """
    if opcje is None:
        opcje = {}
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
    """Zwraca kod języka dla pliku wynikowego (ISO 639-1 lub BCP-47).

    Dla naprawiacza tagów ``iso`` jest podawane ręcznie przez użytkownika
    (w ``opcje["iso_reczne"]``; od v17.2.1 może zawierać podtag regionu/pisma,
    np. ``pt-BR``). Dla pozostałych wariantów pochodzi z YAML-a.
    """
    cfg = wariant_po_id(tryb, jezyk, wariant) or wariant_po_etykiecie(tryb, jezyk, wariant)
    if cfg is None:
        return jezyk

    if cfg.get("kategoria") == "naprawiacz":
        return (opcje or {}).get("iso_reczne", jezyk) or jezyk

    iso = cfg.get("iso") or jezyk
    return str(iso).strip() or jezyk


# Polskie defaulty członów nazw plików wynikowych — zachowane 1:1 z nazewnictwem
# sprzed lokalizacji (fallback dla wywołań bez ``slowa``, np. headless/testy).
SLOWA_NAZW_DOMYSLNE = {
    "naprawiony":  "naprawiony",
    "oczyszczony": "oczyszczony",
    "akcent":      "akcent",
    "szyfr":       "szyfr",
}

# Znaki zakazane w nazwach plików — unia cross-platform (Windows + sterujące);
# ten sam zestaw co ``tlumacz_ai._RE_ZNAKI_ZAKAZANE``.
_RE_ZNAKI_ZAKAZANE_NAZW = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def bezpieczny_czlon_nazwy(slowo: Any, fallback: str) -> str:
    """Sanityzuje przetłumaczony człon nazwy pliku (Unicode-safe).

    Zachowuje litery Unicode (ä, þ, cyrylica — syntezatory czytają je
    natywnie, systemy plików akceptują), usuwa znaki zakazane w nazwach
    plików, zwija białe znaki do ``_`` i normalizuje do lowercase. Zwraca
    ``fallback`` (polski default), gdy wejście nie jest użytecznym stringiem —
    w tym dla nieprzetłumaczonego placeholdera i18n ``[sekcja.klucz]``.
    """
    if not isinstance(slowo, str):
        return fallback
    s = slowo.strip()
    if not s or (s.startswith("[") and s.endswith("]")):
        return fallback
    s = _RE_ZNAKI_ZAKAZANE_NAZW.sub("", s)
    s = re.sub(r"\s+", "_", s).strip("._")
    return s.lower() or fallback


def sufiks_nazwy_pliku(
    tryb: str,
    jezyk: str,
    wariant: str,
    oryginalna_nazwa: str,
    opcje: dict | None = None,
    *,
    slowa: dict[str, str] | None = None,
) -> str:
    """Buduje bazową nazwę pliku wynikowego (bez rozszerzenia).

    Schemat nazewnictwa (człony ``<...>`` lokalizowane od v18.8 przez GUI —
    klucze ``poliglota.filename_*`` w ``ui.yaml``, przekazywane w ``slowa``;
    bez ``slowa`` obowiązują polskie defaulty ``SLOWA_NAZW_DOMYSLNE``):
      * ``<oczyszczony>_<oryginał>``                  – oczyszczanie
      * ``<oryginał>_<akcent>_<id akcentu>``          – akcent fonetyczny
      * ``<naprawiony>_<oryginał>_<iso>``             – naprawiacz tagów
        (przy kodach per akapit ``<iso>`` to zbiór użytych kodów, np.
        ``de-en-fi``, do czterech pozycji plus licznik nadwyżki ``+N``)
      * ``<oryginał>_<szyfr>_<id>[<±przesunięcie>]``  – szyfry

    ``id`` wariantu pozostaje techniczne (wspólny klucz wszystkich paczek).
    Nie ma kropki w przyrostku – GUI doda ją razem z rozszerzeniem.
    """
    opcje = opcje or {}
    slowa = slowa or {}
    cfg   = wariant_po_id(tryb, jezyk, wariant) or wariant_po_etykiecie(tryb, jezyk, wariant)
    if cfg is None:
        return oryginalna_nazwa

    def slowo(klucz: str) -> str:
        return bezpieczny_czlon_nazwy(slowa.get(klucz), SLOWA_NAZW_DOMYSLNE[klucz])

    kategoria = cfg.get("kategoria", "")
    wariant_id = cfg.get("id", wariant)

    if kategoria == "naprawiacz":
        iso = (opcje.get("iso_reczne") or jezyk).strip()
        # v19.2 (audyt): przy kodach per akapit jeden kod w nazwie KŁAMAŁBY
        # o zawartości — `naprawiony_x_pl.html` z akapitami `en`/`de`/`fi` to
        # dokładnie to, czego 19.1 miało nie robić. Bierzemy więc zbiór użytych
        # kodów (do czterech, dalej licznik nadwyżki); przy jednym kodzie
        # nazwa zostaje bez zmian.
        kody = [k for k in (opcje.get("kody_jednostek") or []) if k]
        unikalne = sorted(set(kody))
        if len(unikalne) > 1:
            iso = "-".join(unikalne[:4])
            if len(unikalne) > 4:
                iso = f"{iso}+{len(unikalne) - 4}"
        return f"{slowo('naprawiony')}_{oryginalna_nazwa}_{iso}"

    if kategoria == "oczyszczenie":
        return f"{slowo('oczyszczony')}_{oryginalna_nazwa}"

    if kategoria == "akcent":
        return f"{oryginalna_nazwa}_{slowo('akcent')}_{wariant_id}"

    if kategoria == "szyfr":
        base = f"{oryginalna_nazwa}_{slowo('szyfr')}_{wariant_id}"
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

# Rozszerzenia, dla których ścieżka zapisu ma JAWNĄ gałąź (czyli takie, gdzie
# wiemy, co zrobić z treścią). Wszystko inne `zapisz_wynik` zapisuje surowo,
# a GUI musi o tym uprzedzić — patrz `gui_poliglota._on_load`. Jedno źródło
# prawdy dla silnika, wildcardu w `ui.yaml` i ostrzeżenia w GUI.
EXT_OBSLUGIWANE: tuple[str, ...] = (".txt", ".md", ".html", ".htm", ".docx")

# Lista tagów blokowych, dla których ma sens lokalny atrybut ``lang``.
# Wybrane spośród elementów HTML5, które typowo zawierają samodzielną
# jednostkę tekstu (czytniki ekranu przełączają silnik mowy na granicy
# zmiany ``lang`` właśnie tutaj). Inline'y (``span``, ``a``) celowo poza
# listą — generowałyby setki krótkich detekcji o niskiej wiarygodności.
_PARA_TAGS_LANG = (
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "blockquote", "dt", "dd",
    "td", "th", "caption", "figcaption", "summary",
)


class _KodyPerJednostka:
    """Kursor po liście kodów ISO nadawanych jednostkom PO KOLEI.

    Kontrakt: liczba i kolejność jednostek widzianych przez
    :func:`jednostki_jezykowe` (czyli lista, którą użytkownik miał przed
    sobą w GUI) musi się ZGADZAĆ z liczbą i kolejnością stempli nakładanych
    przez :func:`zapisz_wynik`. Rozjazd choćby o jedną pozycję znaczy, że
    kod nr 7 wylądował na akapicie nr 8 — i jest to defekt NIEWIDOCZNY
    w pliku wynikowym, bo plik pozostaje poprawnym HTML-em czy DOCX-em.
    Dlatego kursor pilnuje obu kierunków rozjazdu i zamiast cicho spaść na
    wartość domyślną — podnosi wyjątek (standard „zero ciszy").
    """

    def __init__(self, kody: list[str]) -> None:
        self._kody = list(kody)
        self._i = 0

    def nastepny(self) -> str:
        if self._i >= len(self._kody):
            raise ValueError(
                f"Too few per-unit language codes: {len(self._kody)} given, "
                f"but the file has more units — the caller's unit list drifted "
                f"from the one the writer walks (see `jednostki_jezykowe`)."
            )
        kod = self._kody[self._i]
        self._i += 1
        return kod

    def zamknij(self) -> None:
        """Sprawdza, że zużyto WSZYSTKIE kody (nadwyżka = ten sam rozjazd)."""
        if self._i != len(self._kody):
            raise ValueError(
                f"Too many per-unit language codes: {len(self._kody)} given, "
                f"{self._i} consumed — the caller's unit list drifted from the "
                f"one the writer walks (see `jednostki_jezykowe`)."
            )


def _zbuduj_soup(html_text: str) -> Any | None:
    """Parsuje HTML do ``BeautifulSoup``; ``None`` gdy ``bs4`` nie ma w środowisku.

    Parser: ``lxml`` (szybki i tolerancyjny dla niedomkniętego HTML, w
    ``requirements.txt`` od 13.4.3), fallback na wbudowany ``html.parser``.
    ``None`` jest stanem WYŁĄCZNIE deweloperskim — paczka release zawsze ma
    ``bs4``, więc wywołujący może na tej ścieżce zejść do regexa albo, gdy
    obietnica wymaga DOM-u, głośno odmówić.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:                                     # pragma: no cover
        return None
    try:
        return BeautifulSoup(html_text, "lxml")
    except Exception:                                       # pragma: no cover
        return BeautifulSoup(html_text, "html.parser")


def _tekst_bezposredni(el: Any) -> str:
    """Tekst WŁASNY elementu — bez treści zagnieżdżonych w nim bloków.

    Inline'y (``<b>``, ``<a>``) należą do tekstu własnego, bo nie są osobną
    jednostką języka; blok w bloku ma swój wiersz na liście, więc jego treść
    tu nie wchodzi.
    """
    czesci: list[str] = []
    for tekst in el.find_all(string=True):
        rodzic = tekst.parent
        wlasny = True
        while rodzic is not None and rodzic is not el:
            if rodzic.name in _PARA_TAGS_LANG:
                wlasny = False
                break
            rodzic = rodzic.parent
        if wlasny:
            czesci.append(str(tekst))
    return re.sub(r"\s+", " ", "".join(czesci)).strip()


def _tekst_jednostki(el: Any) -> str:
    """Tekst jednostki do POKAZANIA: całość dla liścia, własny dla bloku z blokiem."""
    if el.find(list(_PARA_TAGS_LANG)) is None:
        return el.get_text(separator=" ", strip=True)
    return _tekst_bezposredni(el)


def _bloki_jednostki(soup: Any) -> list[Any]:
    """Blokowe JEDNOSTKI języka z niepustym tekstem, w kolejności dokumentu.

    Jednostką jest element z :data:`_PARA_TAGS_LANG`, który ma własny tekst:
      * liść (nie zawiera innego takiego elementu) — całą swoją treścią,
      * blok zawierający inne bloki — o ile ma tekst BEZPOŚREDNI.

    Drugi warunek jest poprawką z audytu v19.2. Sama „liściowość" wycinała
    z listy tekst, który użytkownik widzi w pliku: zagnieżdżona lista
    Markdowna daje ``<li>Punkt pierwszy<ul><li>Podpunkt</li></ul></li>``,
    więc „Punkt pierwszy" nie był żadną jednostką i po cichu dostawał kod
    globalny. Tak samo ``<blockquote>Własny tekst<p>…</p></blockquote>``.
    Lista, która nie zawiera całego tekstu pliku, łamie standard „zero ciszy";
    HTML na tym nie traci, bo ``lang`` potomka nadpisuje przodka dla treści
    potomka.

    Kolejność jest DOKUMENTOWA, bo ``find_all`` z listą nazw przechodzi drzewo
    raz. Do v19.1 zapis iterował ``for tag_name in _PARA_TAGS_LANG:``, czyli
    grupami po nazwie tagu (wszystkie ``<p>``, potem wszystkie ``<h1>``…).
    Dopóki język brał się z mapy PO TREŚCI, było to nieszkodliwe; przy kodach
    nadawanych PO INDEKSIE byłoby zabójcze.
    """
    wynik: list[Any] = []
    for el in soup.find_all(list(_PARA_TAGS_LANG)):
        if _tekst_jednostki(el):
            wynik.append(el)
    return wynik


def _wstrzyknij_lang_w_pelnym_html(html_text: str, iso_fallback: str,
                                   *, mapa_iso: dict[str, str] | None = None,
                                   kody: _KodyPerJednostka | None = None) -> str:
    """Parsuje pełnoprawny HTML i ustawia atrybut ``lang`` per element blokowy.

    13.4.3: zastępuje wcześniejszy regex (działający tylko na ``<html>``).
    BeautifulSoup buduje DOM; każdy element z :data:`_PARA_TAGS_LANG` dostaje
    własny ``lang``, a ``<html>`` — wartość globalną.

    **v19.1: ta funkcja NIE WYKRYWA JĘZYKA.** Dostaje tekst JUŻ przetworzony,
    więc detekcja pytała tu o język zapisu fonetycznego albo szyfrogramu.
    Zmierzone na `skrypty/audyt_starego_modelu.md`: akcent włoski (`iso: it`)
    dawał akapity otagowane ``pl``×25, ``en``×3, ``es``×1, ``fi``×1 — czytnik
    przełączał syntezator na cztery języki i ani razu na docelowy. Język
    wyniku jest teraz DANYMI, nie zgadywaniem:

      * ``iso_fallback`` – wartość obowiązująca (``iso`` wariantu, ręczny kod
        naprawiacza albo język docelowy Tłumacza AI); dla dokumentu
        jednojęzycznego w wyniku to jedyna użyta wartość,
      * ``mapa_iso`` – opcjonalna mapa ``tekst akapitu → iso`` z side-channelu
        ``opcje["_segmenty_wynikowe"]``. Potrzebna tylko wtedy, gdy wariant
        daje RÓŻNE ``iso`` dla różnych akapitów (dokument mieszany językowo
        + oczyszczenie lub szyfr). Dopasowanie: najpierw dokładne, potem
        „zawiera" (element blokowy zawierający inline'y jest na wejściu
        pociętym na kilka segmentów), na końcu ``iso_fallback``.

    Parser: ``lxml`` (preferowany — szybki i tolerancyjny dla niedomkniętego
    HTML, a w środowisku 13.4.3 gwarantowany w ``requirements.txt``). Fallback
    na wbudowany ``html.parser`` w razie braku ``lxml`` w środowisku
    deweloperskim.
    """
    soup = _zbuduj_soup(html_text)
    if soup is None:                                        # pragma: no cover
        # bs4 niedostępne — wracamy do prostego ustawienia lang w <html>.
        if kody is not None:
            raise RuntimeError(
                "Per-paragraph language codes require `bs4` (missing in this "
                "environment) — without a DOM there are no units to stamp."
            )
        if "lang=" in html_text.lower():
            return re.sub(
                r'(<html[^>]*?)lang=["\'][^"\']+["\']',
                fr'\1lang="{iso_fallback}"',
                html_text, flags=re.IGNORECASE,
            )
        return re.sub(
            r"(<html[^>]*)>", fr'\1 lang="{iso_fallback}">',
            html_text, flags=re.IGNORECASE,
        )

    if soup.html is not None:
        soup.html["lang"] = iso_fallback

    if kody is None:
        for el in soup.find_all(list(_PARA_TAGS_LANG)):
            tekst = el.get_text(separator=" ", strip=True)
            if not tekst:
                continue
            el["lang"] = _iso_dla_tekstu(tekst, mapa_iso, iso_fallback)
    else:
        # v19.2: Naprawiacz z kodami per akapit. Każda JEDNOSTKA z listy w GUI
        # dostaje swój kod, w kolejności dokumentu — tej samej, w której
        # użytkownik ją zobaczył. Blok bez własnego tekstu (sam kontener dla
        # innych bloków) jednostką nie jest i dostaje kod globalny.
        jednostki = _bloki_jednostki(soup)
        id_jednostek = {id(el) for el in jednostki}
        for el in soup.find_all(list(_PARA_TAGS_LANG)):
            if id(el) in id_jednostek:
                continue
            if el.get_text(separator=" ", strip=True):
                el["lang"] = iso_fallback
        for el in jednostki:
            el["lang"] = kody.nastepny()

    return str(soup)


def _iso_dla_tekstu(tekst: str, mapa_iso: dict[str, str] | None,
                    iso_fallback: str) -> str:
    """Szuka ``iso`` akapitu w mapie z side-channelu; NIE wykrywa języka.

    Kolejność: dopasowanie dokładne → pierwszy klucz zawarty w ``tekst``
    (element blokowy z inline'ami jest na wejściu pocięty na kilka segmentów,
    więc jego ``get_text()`` jest dłuższy niż którykolwiek pojedynczy klucz)
    → ``iso_fallback``. Brak mapy = jednorodny dokument: sam fallback.
    """
    if not mapa_iso:
        return iso_fallback
    trafienie = mapa_iso.get(tekst)
    if trafienie:
        return trafienie
    for klucz, iso in mapa_iso.items():
        if klucz and klucz in tekst:
            return iso
    return iso_fallback


def _ustaw_lang_runa_xml(r_el: Any, iso: str) -> None:
    """Wstrzykuje ``<w:lang w:val=iso>`` do biegu (element ``w:r``)."""
    rPr = r_el.get_or_add_rPr()
    lang_el = rPr.find(qn("w:lang"))
    if lang_el is None:
        lang_el = OxmlElement("w:lang")
        rPr.append(lang_el)
    lang_el.set(qn("w:val"), iso)


def _ustaw_lang_runa(run: Any, iso: str) -> None:
    """Wstrzykuje ``<w:lang w:val=iso>`` do biegu Word, tworząc ``rPr`` jeśli brak."""
    _ustaw_lang_runa_xml(run._r, iso)


def _ustaw_lang_akapitu(para: Any, iso: str) -> None:
    """Stempluje ``w:lang`` na KAŻDYM biegu akapitu — także wewnątrz hiperlinku.

    Poprawka z audytu v19.2. ``Paragraph.runs`` w python-docx 1.2.0 NIE zwraca
    biegów zagnieżdżonych w ``w:hyperlink``, a ``Paragraph.text`` je liczy —
    więc akapit będący samym linkiem był jednostką na liście, zużywał swój kod
    i nie dostawał ŻADNEGO tagu (plik pozostawał poprawnym DOCX-em, liczba
    jednostek się zgadzała, więc nic nie krzyczało). Iterujemy po ``w:r``
    w drzewie akapitu, co obejmuje oba przypadki naraz.
    """
    for r_el in para._p.iter(qn("w:r")):
        _ustaw_lang_runa_xml(r_el, iso)


def _iteruj_akapity_docx(kontener: Any) -> Any:
    """Akapity dokumentu Word w KOLEJNOŚCI DOKUMENTU, wchodząc do tabel.

    ``Document.paragraphs`` z python-docx zwraca wyłącznie akapity leżące
    bezpośrednio w ``<w:body>`` — każdy akapit z komórki tabeli jest poza tą
    listą. Do v19.1 płaciły za to dwie rzeczy naraz: podgląd wczytanego
    ``.docx`` gubił całą treść tabel, a Naprawiacz Tagów nie wstrzykiwał
    ``w:lang`` do ani jednej komórki, więc czytnik ekranu czytał tabelę
    głosem poprzedniego języka. Zmierzone na dokumencie z tabelą 2×2,
    scaleniem poziomym i tabelą zagnieżdżoną: ``doc.paragraphs`` widziało
    2 akapity z 8.

    Chodzimy więc po XML-u: ``w:p`` → akapit, ``w:tbl`` → tabela, do której
    wchodzimy rekurencyjnie po ``tr_lst``/``tc_lst``. Iteracja po SUROWYCH
    ``w:tc`` (a nie po ``row.cells``) rozwiązuje przy okazji scalenia —
    komórka scalona poziomo jest w XML-u jedna, a ``row.cells`` pokazałoby
    ją tyle razy, ile kolumn obejmuje, i tyle razy nadałoby jej kod.
    """
    from docx.document import Document as _DocxDocument
    from docx.table import _Cell

    if isinstance(kontener, _DocxDocument):
        rodzic = kontener.element.body
    elif isinstance(kontener, _Cell):
        rodzic = kontener._tc
    else:                                                   # pragma: no cover
        raise TypeError(f"Unsupported paragraph container: {type(kontener)!r}")

    yield from _iteruj_akapity_xml(rodzic, kontener)


def _iteruj_akapity_xml(rodzic: Any, kontener: Any) -> Any:
    """Akapity spod elementu XML — rekurencyjnie przez tabele i kontrolki treści.

    Wydzielone z :func:`_iteruj_akapity_docx`, żeby dało się zejść pod element,
    który KONTENEREM python-docx nie jest: ``w:sdtContent`` (kontrolka
    zawartości, np. pole formularza). Znalezisko z audytu v19.2 — taki akapit
    nie trafiał ani do podglądu, ani do listy jednostek, ani pod stempel,
    a liczniki po obu stronach się zgadzały, więc nic nie krzyczało.
    """
    from docx.table import Table, _Cell
    from docx.text.paragraph import Paragraph

    for dziecko in rodzic.iterchildren():
        if dziecko.tag == qn("w:p"):
            yield Paragraph(dziecko, kontener)
        elif dziecko.tag == qn("w:tbl"):
            tabela = Table(dziecko, kontener)
            for wiersz in dziecko.tr_lst:
                for komorka_xml in wiersz.tc_lst:
                    yield from _iteruj_akapity_docx(_Cell(komorka_xml, tabela))
        elif dziecko.tag == qn("w:sdt"):
            for wnetrze in dziecko.iterchildren(qn("w:sdtContent")):
                yield from _iteruj_akapity_xml(wnetrze, kontener)


def tekst_docx(sciezka: str) -> str:
    """Cała treść tekstowa dokumentu Word, akapit na linię, w kolejności czytania.

    Publiczne wejście dla GUI (podgląd wczytanego pliku i licznik znaków).
    Różnica wobec naiwnego ``"\n".join(p.text for p in doc.paragraphs)``
    jest różnicą KOMPLETNOŚCI: tamta forma pomija każdą komórkę tabeli
    (patrz :func:`_iteruj_akapity_docx`), więc do v19.1 podgląd `.docx`
    z tabelą pokazywał ułamek treści, a użytkownik nie miał sygnału, że
    czegoś nie widzi.
    """
    doc = docx.Document(sciezka)
    return "\n".join(para.text for para in _iteruj_akapity_docx(doc))


def _iso_per_linia(tresc: str, segmenty: list[Segment] | None,
                   iso_fallback: str) -> list[str]:
    """Mapuje każdą linię ``tresc.split('\\n')`` na kod ISO języka.

    Strategia:
      1. Jeśli ``segmenty`` są dane (z side-channel ``opcje['_segmenty_wynikowe']``)
         i ich konkatenacja zgadza się z ``tresc`` – używamy ich. To jedyne
         wiarygodne źródło, bo niesie ``iso`` wariantu (język GŁOSU), a nie
         wynik detekcji na tekście już przemielonym przez akcent czy szyfr.
      2. W przeciwnym razie dzielimy ``tresc`` na akapity Z WYMUSZONYM
         ``iso_fallback`` — **bez detekcji** (v19.1). Wywołujący zawsze wie,
         jaki język zadeklarował: ``iso`` wariantu, ręczny kod naprawiacza
         albo język docelowy Tłumacza AI.
      3. Buduemy mapę offset→iso ze sticky-fallbackiem: separatory ``\\n\\s*\\n``
         dziedziczą iso po ostatnim segmencie tekstowym.
      4. Iterujemy linie, przesuwając kursor o ``len(linia)+1`` (znak ``\\n``).
    """
    if segmenty is None or "".join(s[1] for s in segmenty) != tresc:
        segmenty = _segmentuj_z_ochrona_tagow(
            tresc, fallback_jezyk=iso_fallback, wymus_jezyk=iso_fallback)

    # Mapa offset → iso (długość mapy == len(tresc))
    iso_per_offset: list[str] = []
    ostatni_iso = iso_fallback
    for jez, fr, czy_tekst in segmenty:
        if czy_tekst:
            ostatni_iso = jez
        iso_per_offset.extend([ostatni_iso] * len(fr))

    wynik: list[str] = []
    cursor = 0
    for linia in tresc.split("\n"):
        if 0 <= cursor < len(iso_per_offset):
            wynik.append(iso_per_offset[cursor])
        else:
            wynik.append(ostatni_iso)
        cursor += len(linia) + 1  # +1 za znak '\n'
    return wynik


def _bez_tagow(fragment: str) -> str:
    """Tekst akapitu bez tagów HTML, ze zwiniętymi białymi znakami (do LISTY).

    Służy WYŁĄCZNIE prezentacji: użytkownik ma w liście usłyszeć treść
    akapitu, nie jego znaczniki. Zapis operuje na oryginalnym fragmencie.
    """
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def jednostki_jezykowe(tresc: str, ext: str,
                       sciezka_oryginalu: str | None = None) -> list[str]:
    """Teksty jednostek, którym :func:`zapisz_wynik` nadaje ``lang``.

    **Kolejność jest kolejnością stemplowania** — to cały sens tej funkcji.
    GUI buduje z niej listę akapitów w dialogu „Kody języka per akapit", a
    zwróconą listę kodów oddaje do ``zapisz_wynik(kody_jednostek=...)``,
    które nakłada je PO INDEKSIE. Obie strony muszą więc liczyć jednostki
    tak samo, a „jednostka" znaczy co innego na każdej ścieżce zapisu:

      * ``.docx`` z istniejącym oryginałem — akapit Worda w kolejności
        dokumentu, **wliczając komórki tabel** (:func:`_iteruj_akapity_docx`),
      * ``.docx`` bez oryginału (plik zniknął między wczytaniem a zapisem) —
        linia treści, tak jak buduje ją wtedy ``zapisz_wynik``,
      * ``.html``/``.htm`` z ``<html>`` (tu wpada też wyrenderowany ``.md``) —
        blokowy element z własnym tekstem (:func:`_bloki_jednostki`),
      * fragment HTML / ``.txt`` / ``.md`` — akapit rozdzielony PUSTĄ LINIĄ,
      * każde inne rozszerzenie — **lista pusta**: zapis jest surowy, żadna
        jednostka nie dostaje tagu, więc nie ma czego wypełniać.

    Jednostki puste (sam biały znak) są pomijane PO OBU stronach: dostają
    kod globalny i nie zaśmiecają listy, którą użytkownik przesłuchuje.

    KONTRAKT WYWOŁANIA: ``sciezka_oryginalu`` podawaj tylko wtedy, gdy zapis
    też pójdzie po oryginale z dysku — czyli dla NAPRAWIACZA TAGÓW. Dla
    pozostałych wariantów ``zapisz_wynik`` buduje dokument z treści wynikowej,
    więc lista policzona z pliku źródłowego opisywałaby co innego.

    Returns:
        Teksty jednostek do POKAZANIA (bez tagów, białe znaki zwinięte).
        Zapis nie polega na tych stringach — wyłącznie na ich liczbie
        i kolejności.
    """
    ext = (ext or "").lower()

    if ext == ".docx":
        if sciezka_oryginalu and os.path.exists(sciezka_oryginalu):
            doc = docx.Document(sciezka_oryginalu)
            return [p.text.strip() for p in _iteruj_akapity_docx(doc)
                    if p.text.strip()]
        return [linia.strip() for linia in tresc.split("\n") if linia.strip()]

    if ext in (".html", ".htm") and "<html" in tresc.lower():
        soup = _zbuduj_soup(tresc)
        if soup is None:                                    # pragma: no cover
            raise RuntimeError(
                "Per-paragraph language codes require `bs4` (missing in this "
                "environment) — without a DOM there are no units to stamp."
            )
        return [_tekst_jednostki(el) for el in _bloki_jednostki(soup)]

    if ext in (".txt", ".md", ".html", ".htm"):
        # ``iso_fallback="und"`` (BCP-47: język nieokreślony) jest tu wartością
        # ATRAPĄ — interesuje nas wyłącznie PODZIAŁ na akapity, a niepusty kod
        # wyłącza detekcję lingua, której liczenie jednostek nie potrzebuje.
        return [_bez_tagow(body)
                for body, _ in _podziel_na_akapity_html(tresc, None, "und")]

    return []


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
    *,
    segmenty_wynikowe: list[Segment] | None = None,
    kody_jednostek: list[str] | None = None,
) -> str:
    """Zapisuje wynik do pliku i zwraca jego ścieżkę.

    13.5: tag ``lang`` jest wstrzykiwany **per akapit / per paragraf**, a nie
    globalnie. Dla trybów Reżysera i Szyfranta używana jest mapa
    ``segmenty_wynikowe`` (side-channel z :func:`przetworz`).

    **v19.1: ta funkcja NIE WYKRYWA JĘZYKA — ani razu, na żadnej ścieżce.**
    Język wyniku pochodzi wyłącznie z danych: ``iso`` wariantu (przez
    side-channel), ręczny kod naprawiacza albo język docelowy Tłumacza AI —
    wszystkie trzy docierają tu jako ``iso_code``. Detekcja na TREŚCI
    WYNIKOWEJ pytała o język zapisu fonetycznego albo szyfrogramu i zwracała
    losowe kody (dowód → :func:`_wstrzyknij_lang_w_pelnym_html`); detekcja
    per akapit ma sens tylko PRZED operacją, gdzie wybiera reguły, i tam
    została (patrz :func:`_segmentuj_z_ochrona_tagow`).

    Obsługiwane rozszerzenia:
      * ``.docx`` – dokument Word z tagiem ``<w:lang w:val=iso>`` per paragraf,
      * ``.html`` / ``.htm`` – HTML; jeżeli wejście ma ``<html>``, atrybut
        ``lang`` ustawiany na ``iso_code`` (jak dotąd); w pozostałych
        przypadkach budujemy nowy dokument z ``<p lang="...">`` per akapit
        (rozdzielany ``\\n\\s*\\n``),
      * ``.txt`` / ``.md`` – konwertowane do HTML; każdy akapit dostaje
        własny ``<p lang="...">``,
      * każde inne – surowy zapis tekstu z oryginalnym rozszerzeniem.

    Args:
        tresc_wynikowa:       Przetworzony tekst do zapisu.
        katalog_wyjscia:      Katalog docelowy (zwykle: katalog pliku źródłowego).
        base_name:            Nazwa pliku bez rozszerzenia
                              (wynik :func:`sufiks_nazwy_pliku`).
        ext:                  Rozszerzenie źródła (np. ``".docx"``) – decyduje
                              o formacie wyjścia.
        iso_code:             Zadeklarowany kod języka wyniku — ``<html lang>``
                              oraz każdy akapit, dla którego ``segmenty_wynikowe``
                              nie mówią czegoś innego. NIE jest już „fallbackiem
                              detekcji", bo detekcji tu nie ma (v19.1).
        tryb:                 ``"Rezyser"`` / ``"Szyfrant"`` / ``"Tlumacz"``.
        wariant_cfg:          Konfiguracja wariantu (z YAML) – potrzebna,
                              by rozpoznać „naprawiacz tagów".
        oryginalny_content:   Treść źródłowa (wykorzystywana przez naprawiacza
                              tagów, gdy ``sciezka_oryginalu`` nie istnieje).
        sciezka_oryginalu:    Pełna ścieżka oryginału (tylko dla naprawiacza
                              ``.docx`` – kopiujemy oryginalny dokument,
                              tylko wstrzykując tag ``w:lang``).
        segmenty_wynikowe:    *Keyword-only.* Side-channel z
                              :func:`przetworz` (``opcje['_segmenty_wynikowe']``).
                              Lista krotek ``(iso, fragment, czy_tekst)`` w
                              kolejności wynikowej, gdzie ``iso`` to język
                              GŁOSU (pole ``iso`` wariantu). ``None`` → cały
                              dokument dostaje ``iso_code`` (przypadek
                              naprawiacza tagów i Tłumacza AI, gdzie jeden
                              zadeklarowany kod obowiązuje wszędzie).
        kody_jednostek:       *Keyword-only.* v19.2 — kody ISO nadawane
                              jednostkom PO INDEKSIE, w kolejności
                              i liczbie z :func:`jednostki_jezykowe`.
                              Zasilane dialogiem „Kody języka per akapit"
                              Naprawiacza Tagów. ``None`` → cały dokument
                              dostaje ``iso_code`` (zachowanie sprzed 19.2).
                              Rozjazd liczby jednostek podnosi
                              ``ValueError`` — patrz :class:`_KodyPerJednostka`.

    Returns:
        Pełna ścieżka zapisanego pliku.
    """
    jest_naprawiacz = bool(wariant_cfg and wariant_cfg.get("kategoria") == "naprawiacz")
    kody = _KodyPerJednostka(kody_jednostek) if kody_jednostek is not None else None

    # v19.1: mapa ``tekst akapitu → iso`` dla ścieżki pełnego HTML. Budujemy ją
    # WYŁĄCZNIE wtedy, gdy wariant dał różne ``iso`` różnym akapitom (dokument
    # mieszany językowo + oczyszczenie albo szyfr). Przy jednorodnym wyniku —
    # a taki daje każdy akcent, bo `iso` akcentu jest wspólne dla wszystkich
    # paczek — mapa jest zbędna: wystarczy ``iso_code``. Naprawiacz zawsze
    # stempluje ręcznym kodem, więc mapy nie dostaje.
    mapa_iso: dict[str, str] | None = None
    if segmenty_wynikowe and not jest_naprawiacz:
        pary = {s[1].strip(): s[0] for s in segmenty_wynikowe if s[2] and s[1].strip()}
        if len(set(pary.values())) > 1:
            mapa_iso = pary

    # -------- DOCX ---------------------------------------------------------
    if ext == ".docx":
        out_path = os.path.join(katalog_wyjscia, f"{base_name}.docx")

        if jest_naprawiacz and sciezka_oryginalu and os.path.exists(sciezka_oryginalu):
            # Otwieramy oryginał i wstrzykujemy RĘCZNY kod w każdy bieg.
            # v19.1: bez detekcji per paragraf — naprawiacz dostaje kod od
            # użytkownika. v19.2: kod może być RÓŻNY per akapit (dialog
            # z listą akapitów), a iteracja idzie `_iteruj_akapity_docx`,
            # czyli wchodzi też do komórek tabel — `doc.paragraphs` pomijało
            # je co do jednej.
            doc = docx.Document(sciezka_oryginalu)
            for para in _iteruj_akapity_docx(doc):
                if not para.text.strip():
                    continue
                kod = kody.nastepny() if kody is not None else iso_code
                _ustaw_lang_akapitu(para, kod)
        else:
            # Nowy dokument: side-channel (tryb Rezyser/Szyfrant) lub live-detect
            # (naprawiacz bez pliku źródła, Tlumacz, inne wywołania).
            doc = docx.Document()
            zawartosc = oryginalny_content if jest_naprawiacz else tresc_wynikowa

            sgm = None if jest_naprawiacz else segmenty_wynikowe
            iso_lista = _iso_per_linia(zawartosc, sgm, iso_code)

            linie = zawartosc.split("\n")
            for linia, iso_lin in zip(linie, iso_lista):
                p = doc.add_paragraph(linia)
                kod = iso_lin
                if kody is not None and linia.strip():
                    kod = kody.nastepny()
                _ustaw_lang_akapitu(p, kod)
        if kody is not None:
            kody.zamknij()
        doc.save(out_path)
        return out_path

    # -------- HTML / HTM ---------------------------------------------------
    if ext in (".html", ".htm"):
        out_path = os.path.join(katalog_wyjscia, f"{base_name}{ext}")
        tekst = tresc_wynikowa
        ma_html = "<html" in tekst.lower()

        if ma_html:
            # 13.4.3: pełnoprawny HTML — bs4 + lxml wstrzykują ``lang``
            # per element blokowy (paragraf, nagłówek, lista, komórka),
            # zachowując resztę DOM-u. Globalny ``<html lang>`` to fallback.
            tekst = _wstrzyknij_lang_w_pelnym_html(tekst, iso_code,
                                                   mapa_iso=mapa_iso,
                                                   kody=kody)
        else:
            # Fragment HTML / czysty tekst — owijamy akapity (``\n\s*\n``) w
            # ``<p lang="...">`` z dynamicznym językiem.
            tekst = _zbuduj_html_z_akapitow(
                tekst,
                segmenty_wynikowe if not jest_naprawiacz else None,
                iso_code,
                kody=kody,
            )

        if kody is not None:
            kody.zamknij()
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(tekst)
        return out_path

    # -------- TXT / MD → HTML (z tagiem lang per akapit) ------------------
    if ext in (".txt", ".md"):
        out_path = os.path.join(katalog_wyjscia, f"{base_name}.html")
        linie = tresc_wynikowa.split("\n")
        tytul = linie[0].strip() if linie and linie[0].strip() else "Dokument"
        body = _zbuduj_html_z_akapitow(
            tresc_wynikowa,
            segmenty_wynikowe if not jest_naprawiacz else None,
            iso_code,
            kody=kody,
        )
        if kody is not None:
            kody.zamknij()
        html = (
            f'<!DOCTYPE html>\n<html lang="{iso_code}">\n'
            f'<head>\n<meta charset="utf-8">\n<title>{tytul}</title>\n</head>\n'
            f"<body>\n{body}\n</body>\n</html>"
        )
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        return out_path

    # -------- Inne – zapis surowy -----------------------------------------
    # Żadna jednostka nie dostaje tu tagu, więc kody per akapit są sprzeczne
    # z tą ścieżką — `zamknij()` podnosi ValueError, jeśli ktoś je podał.
    if kody is not None:
        kody.zamknij()
    out_path = os.path.join(katalog_wyjscia, f"{base_name}{ext if ext else '.txt'}")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(tresc_wynikowa)
    return out_path


def _podziel_na_akapity_html(tresc: str,
                             segmenty: list[Segment] | None,
                             iso_fallback: str) -> list[tuple[str, str]]:
    """Dzieli treść na akapity: lista ``(body, iso)`` w KOLEJNOŚCI WYNIKOWEJ.

    Jedno źródło prawdy dla dwóch stron tej samej umowy:
    :func:`_zbuduj_html_z_akapitow` (zapis) i :func:`jednostki_jezykowe`
    (lista w GUI) muszą widzieć te same jednostki w tej samej kolejności.
    Wydzielone z ciała buildera w v19.2 właśnie dlatego — dopóki podział
    siedział w środku pętli budującej HTML, GUI musiałoby go POWTÓRZYĆ,
    a powtórzony podział to podział, który kiedyś się rozjedzie.

    Akapity rozdziela pusta linia; pojedynczy ``chr(10)`` zostaje w treści
    akapitu. Tag HTML trafia do bieżącego akapitu, separator go domyka.
    Akapit z samych białych znaków jest pomijany.
    """
    if segmenty is None or "".join(s[1] for s in segmenty) != tresc:
        segmenty = _segmentuj_z_ochrona_tagow(
            tresc, fallback_jezyk=iso_fallback, wymus_jezyk=iso_fallback)

    akapity: list[tuple[str, str]] = []
    biezacy: list[str] = []
    biezacy_iso = iso_fallback

    def flush() -> None:
        if not biezacy:
            return
        body = "".join(biezacy)
        biezacy.clear()
        if body.strip():
            akapity.append((body, biezacy_iso))

    for jez, fr, czy_tekst in segmenty:
        if czy_tekst:
            biezacy_iso = jez
            biezacy.append(fr)
        else:
            # Separator pustej linii domyka akapit; tag HTML w środku akapitu
            # zachowujemy w jego treści.
            if re.fullmatch(r"\n\s*\n", fr):
                flush()
            else:
                biezacy.append(fr)
    flush()
    return akapity


def _zbuduj_html_z_akapitow(tresc: str,
                            segmenty: list[Segment] | None,
                            iso_fallback: str,
                            *,
                            kody: _KodyPerJednostka | None = None) -> str:
    """Buduje HTML, owijając każdy akapit w ``<p lang="...">``.

    Akapity są oddzielane wzorcem ``\\n\\s*\\n``. Wewnątrz akapitu pojedyncze
    ``\\n`` zostaje konwertowane na ``<br>`` (tak jak we wcześniejszym
    zachowaniu ``zapisz_wynik``). HTML-special chars (``<``, ``>``, ``&``)
    NIE są ekranowane — wynik często zawiera już własne tagi z naprawiacza
    lub akcentu, a wejście do trybów Poligloty pochodzi z zaufanego źródła
    (lokalny plik użytkownika).

    Mapowanie iso → akapit czerpie z ``segmenty`` (side-channel) gdy są
    dostępne; w przeciwnym razie dzieli ``tresc`` na akapity z WYMUSZONYM
    ``iso_fallback`` — **bez detekcji** (v19.1, patrz
    :func:`_wstrzyknij_lang_w_pelnym_html`).
    """
    czesci_html: list[str] = []
    for body, iso in _podziel_na_akapity_html(tresc, segmenty, iso_fallback):
        if kody is not None:
            iso = kody.nastepny()
        czesci_html.append(f'<p lang="{iso}">{body.replace(chr(10), "<br>")}</p>')
    return "\n".join(czesci_html)
