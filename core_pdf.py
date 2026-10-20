"""
core_pdf.py – warstwa tekstu PDF → akapity (Poliglota i Konwerter, od 19.13).

Reżyser NIE ZAPISUJE PDF-ów i nie robi OCR (decyzja 2026-10-15: stos OCR z ATA
to 4–5× instalatora). Ten moduł czyta wyłącznie WARSTWĘ TEKSTU i oddaje ją jako
akapity — Poliglota prowadzi je dalej ścieżką `.txt` (wynik `.html` z `<p lang>`
per akapit), Konwerter jak plik tekstowy.

Biblioteka: `pypdfium2` (PDFium, ~8 MB, zero zależności). `pdfplumber` z ATA
ciągnąłby pdfminer + Pillow + cryptography, razem ~45 MB bundla. PDFium oddaje
tekst w kolejności STRUMIENIA TREŚCI (dla dokumentów z Worda i większości
generatorów to kolejność czytania, także w kolumnach), więc kolejności linii
NIE sortujemy po współrzędnych — sortowanie z góry na dół przeplatałoby kolumny.

Dlaczego akapity, a nie jeden blok jak w ATA (`clean_pdf_text` skleja całą
stronę): ATA i tak dzieli korpus od nowa w `cell_para`, a Poliglota stempluje
`lang` PER AKAPIT i syntezator czyta wynik na głos — akapit jest tu jednostką
produktu. Podział z geometrii linii (`_podziel_na_akapity`).

Kolontytuły rozpoznajemy po POZYCJI, nie po słowach: ten sam tekst (po zdjęciu
numeru — albo z numerem rosnącym razem ze stroną) w tym samym pasie wysokości,
w górnym lub dolnym marginesie, na co najmniej ćwierci stron (od 19.15 także
ćwierci stron JEDNEJ parzystości — kolontytuł lewej i prawej strony — oraz
w skrajnej linii strony tuż poza pasem 7%, gdy odsunięta od treści; numer
strony w skrajnej linii zawsze, bo pilnuje go przyrost razem ze stroną).
Tekst rozstrzelony: granice słów z geometrii (`_oznacz_granice_rozstrzelenia`),
sklejenie według słownika dokumentu (`core_poliglota.scal_rozstrzelone`).
ATA chroni nagłówki scen listą słów w sześciu językach;
tu ochrona wynika z geometrii — „SCENA 2" w środku strony nie jest w marginesie,
a lista słów w Pythonie byłaby wzorcem §6.7b (języki wypisane ręcznie w kodzie).

Strony ze ZNIEKSZTAŁCONĄ warstwą tekstu (od 19.15): czcionka osadzona bez
pełnej mapy ToUnicode, więc PDFium oddaje numery glifów jako znaki. Zmierzone
na słowniku z macOS Quartz (551 stron): mapa kończy się na „М”, reszta
cyrylicy wychodzi jako litery IPA („ɍɬɜɟɪɠɞɟɧɨ” = „Утверждено”), a lingua
zgaduje `de`. Miara to DWA warunki naraz, oba z danych, nie z listy pism:
  * PDFium sam zgłasza błąd mapowania znaku (`FPDFText_HasUnicodeMapError`)
    — sama flaga nie wystarcza, bo przy polskim PDF-ie z Worda oznacza też
    poprawnie odgadnięte „ą”, „ś”, „ł” (zmierzone: 3,3% liter strony);
  * litery nie ma w ŻADNEJ paczce (`podstawy.yaml::alfabet` + litery
    `gui/ui.yaml`, patrz `litery_paczek`) — dziesiąta paczka rozszerza
    miarę bez zmiany kodu.
Zmierzone na 100 PDF-ach z dysku maintainera (pl, ru, en, pt): 0 podejrzanych
liter poza słownikiem; słownik: 550 z 551 stron (pierwsza to obraz okładki).

Naprawa (etap 2, `_napraw_z_fontu`): strona zniekształcona dostaje próbę
odtworzenia liter z OSADZONEGO programu fontu (fontTools: odwrócony `cmap`,
potem nazwy `post`). Słownik: 550 z 550 stron naprawionych, zgodność liter
z `.docx` uczelni 99,6–99,8% na typowej stronie, akcenty U+0301 wracają przy
literach. 99 innych PDF-ów z dysku: tekst bajt w bajt taki sam jak przed
naprawą. Bramka zostaje siatką bezpieczeństwa — strona naprawiona częściowo
dalej jest zgłaszana.
"""

from __future__ import annotations

import functools
import hashlib
import math
import os
import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass, field


class BrakWarstwyTekstu(Exception):
    """PDF, z którego warstwy tekstu nie zostaje ani jeden akapit.

    Najczęściej skan / obraz; lokalnego OCR Reżyser nie ma, GUI mówi to wprost.
    ``strony_bez_tekstu`` wymienia strony BEZ WARSTWY TEKSTU (kandydatki do
    odczytu modelem z obrazem). Dla PDF-a z samymi numerami stron jest PUSTA:
    tam warstwa tekstu jest, tylko nic z niej nie zostało, a takiej strony
    żaden odczyt obrazu nie uratuje.
    """

    def __init__(self, sciezka: str, liczba_stron: int = 0,
                 strony_bez_tekstu: list[int] | None = None) -> None:
        super().__init__(sciezka)
        self.sciezka = sciezka
        self.liczba_stron = liczba_stron
        self.strony_bez_tekstu = list(strony_bez_tekstu or [])


class PdfNieDoOtwarcia(Exception):
    """PDFium nie otworzył pliku: hasło (`haslo=True`) albo plik uszkodzony."""

    def __init__(self, sciezka: str, haslo: bool, szczegol: str) -> None:
        super().__init__(szczegol)
        self.sciezka, self.haslo, self.szczegol = sciezka, haslo, szczegol


@dataclass
class WynikPdf:
    akapity: list[str]
    liczba_stron: int
    #: Numery stron (od 1) bez ani jednego znaku tekstu — typowo wstawione skany.
    strony_bez_tekstu: list[int] = field(default_factory=list)
    #: Unikalne teksty usuniętych kolontytułów (do komunikatu, bez numerów stron).
    kolontytuly: list[str] = field(default_factory=list)
    #: Akapity per strona (indeks 0 = strona 1), `liczba_stron` list. Akapit
    #: sklejony przez granicę strony należy do strony, na której się ZACZĄŁ;
    #: strona bez warstwy tekstu ma listę pustą. Spłaszczenie daje `akapity`
    #: — po to, żeby odczytaną treść skanu wstawić we właściwe miejsce.
    akapity_stron: list[list[str]] = field(default_factory=list)
    #: Numery stron (od 1), których warstwa tekstu jest ZNIEKSZTAŁCONA
    #: (`czy_znieksztalcona`) — ich akapity są w wyniku, ale to śmieci.
    strony_znieksztalcone: list[int] = field(default_factory=list)
    #: Liczba znaków warstwy tekstu per strona (indeks 0 = strona 1), przed
    #: czyszczeniem — do szacunku kosztu odczytu strony modelem z obrazem.
    znaki_stron: list[int] = field(default_factory=list)
    #: Strony, których tekst odtworzono z osadzonego fontu i które po
    #: naprawie przechodzą bramkę (19.15, etap 2). Naprawa częściowa nie
    #: trafia tu — taka strona zostaje w `strony_znieksztalcone`.
    strony_naprawione: list[int] = field(default_factory=list)
    #: Strony w złej stronie kodowej (mojibake), przekodowane (19.15, etap 4)
    #: — i użyte pary kodowań („latin-1>cp1251”), do komunikatu.
    strony_przekodowane: list[int] = field(default_factory=list)
    kodowania: list[str] = field(default_factory=list)

    @property
    def tekst(self) -> str:
        """Akapity rozdzielone PUSTĄ LINIĄ — granica akapitu ścieżki `.txt`."""
        return "\n\n".join(self.akapity)

    @property
    def tekst_wiarygodny(self) -> str:
        """Akapity BEZ stron zniekształconych — jedyne wejście dla detekcji języka.

        Lingua na literach IPA ze słownika rosyjskiego zgadywała `de`; pusty
        wynik znaczy „języka nie da się wykryć”, a GUI mówi to wprost.
        """
        zle = set(self.strony_znieksztalcone)
        return "\n\n".join(a for nr, akapity in enumerate(self.akapity_stron, start=1)
                           if nr not in zle for a in akapity)

    @property
    def strony_do_odczytu(self) -> list[int]:
        """Skany i strony zniekształcone razem — kandydatki do odczytu obrazu."""
        return sorted(set(self.strony_bez_tekstu) | set(self.strony_znieksztalcone))


@dataclass
class _Linia:
    tekst: str
    lewo: float
    dol: float
    prawo: float
    gora: float
    #: Mediana wysokości znaków — rozmiar czcionki linii. Ramka całej linii
    #: myli: pogrubione hasło słownikowe ma wyższą ramkę (13,4 wobec 11 pt)
    #: i reguła „zmiana czcionki" cięła każde hasło po pierwszym wierszu.
    czcionka: float = 0.0
    #: Linia zaczyna się / kończy tekstem rozstrzelonym (19.15, etap 4b):
    #: przy sklejaniu linii w akapit stoi tam granica słowa, nie zwykła spacja.
    rozstrzelona_lewa: bool = False
    rozstrzelona_prawa: bool = False

    @property
    def wysokosc(self) -> float:
        return self.gora - self.dol

# Ligatury typograficzne PDFium oddaje jako jeden znak; syntezator i lingua
# potrzebują liter. Mapa celowo wąska (NFKC zmieniłby też ½, ², ℃ itd.).
_LIGATURY = str.maketrans({
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
    "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st",
    # Dywiz automatycznego dzielenia wyrazów (Word) PDFium oddaje jako
    # U+FFFE (pypdfium2 5.14, zmierzone); \x02 to wariant opisywany dla
    # innych buildów PDFium, niezweryfikowany — mapowany na wszelki wypadek.
    # Bez tej zamiany wypadał razem ze sterującymi i w środku słowa zostawała
    # spacja: „wier sza".
    "\ufffe": "\u00ad", "\x02": "\u00ad",
})
# Znaki sterujące poza \n i \t (PDFium potrafi oddać \x00 itp.).
_RE_STERUJACE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\uffff]")
# Przeniesienie: litera + dywiz (zwykły, miękki, U+2010) na KOŃCU linii.
_RE_PRZENIESIENIE = re.compile(r"(\w)[-\u00ad\u2010]$")
_RE_KONIEC_ZDANIA = re.compile(r"[.!?…:;»”\"')\]]$")
# Punktor graficzny zaczyna punkt listy zawsze; myślnik i numer — tylko po
# zakończonym zdaniu albo krótkiej linii, bo „– Zagadnienia…" w środku zdania
# (zmierzone na wstępie kwartalnika) i „2026 r." to zwykła kontynuacja.
_RE_PUNKTOR = re.compile(r"^[•●▪◦‣∙·*]\s")
_RE_PUNKT_SLABY = re.compile(r"^(?:[–—-]\s|\(?\d{1,3}[.)]\s|[a-zA-Z][.)]\s)")
# Pozycja spisu treści: kropki prowadzące + numer strony na końcu linii.
_RE_POZYCJA_SPISU = re.compile(r"(?:\.\s?){4,}\s*\d{1,4}$")
# Kształt gołego numeru strony: „7”, „- 7 -”, „xii”, „7 / 120”, „7 z 120”,
# „7 of 120”, „7 из 120”, „7 af 120”. SAM KSZTAŁT NIE WYSTARCZA do usunięcia
# (audyt 19.13: „II”, „MIX”, „did” z marginesu znikały) — patrz
# `_numery_stron_do_usuniecia`. Bliźniak 1:1: ATA `_PAGE_NUMBER_LINE`.
_RE_NUMER_STRONY = re.compile(
    r"^[-–—\s]*(\d{1,4}|[ivxlcdmIVXLCDM]{1,6})(?:\s*(?:/|z|of|из|af)\s*\d{1,4})?[-–—\s]*$")
_RE_TAG_NAWIASOWY = re.compile(r"^\s*(?:\[[^\]]+\]|\([^)]+\))\s*$")
_RE_NUMER_NA_BRZEGU = re.compile(r"^\s*(\d{1,4})\s+(.*\S)\s*$|^\s*(.*\S)\s+(\d{1,4})\s*$")

_RE_BIALE = re.compile(r"[ \t]+")
_DOKLEJANE = frozenset(",.;:!?)]»”…")

#: Pas marginesu (ułamek wysokości strony od góry i od dołu), w którym szukamy
#: kolontytułów i numerów stron. 7%, nie 12%: margines Worda to 72 pt, czyli
#: 8,5% strony A4, więc pas 12% obejmował pierwszą i ostatnią linię TREŚCI
#: każdej strony (audyt 19.13).
PAS_MARGINESU = 0.07
#: Minimalny ułamek stron z tym samym kolontytułem / numerem.
UDZIAL_STRON = 0.25
#: Skrajna linia strony poza pasem marginesu jest kandydatem na kolontytuł,
#: gdy odstaje od reszty o tyle wysokości swojej linii (19.15, słownik).
ODSUNIECIE_SKRAJNEJ = 0.8
#: Ułamek wystąpień rdzenia, którego numer musi rosnąć razem ze stroną.
ZGODNOSC_NUMERU = 0.8

_RZYMSKIE = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}

#: Strona jest zniekształcona, gdy podejrzanych liter jest co najmniej tyle
#: i co najmniej taki ułamek wszystkich liter strony. Próg jest niski, bo
#: czyste PDF-y mają podejrzanych liter ZERO (zmierzone na 100 plikach),
#: a strona tytułowa słownika („СЛОВАРȄ РУССКОГО ȇЗȃКА”) ma ich 4 na ok. 100:
#: wielkie А–М mapa obejmuje, zniekształcone są tylko Ь, Я, Ы, Э.
PROG_PODEJRZANYCH = 3
UDZIAL_PODEJRZANYCH = 0.02


def czy_znieksztalcona(litery: int, podejrzane: int) -> bool:
    return podejrzane >= PROG_PODEJRZANYCH and podejrzane >= UDZIAL_PODEJRZANYCH * litery


def litery_paczek() -> frozenset[str]:
    """Litery, którymi piszą paczki językowe — miara wiarygodności liter.

    Z danych, nie z listy pism w kodzie: `podstawy.yaml::alfabet` każdej
    kompletnej paczki plus litery jej `gui/ui.yaml` (tekst natywny), w obu
    wielkościach. Sam alfabet nie wystarcza, bo to alfabet SZYFRÓW (fr: A–Z
    bez „é”), a rozkład NFD był za luźny: „Ȅ” ze strony tytułowej słownika
    to „E” z dwoma akcentami i przechodził jako znana litera (zmierzone).
    `podstawy.yaml` w całości odpada: jego opisy fonetyki mają IPA („ɛ”, „ɲ”
    — ok. 16 tys. zniekształconych liter słownika przeszłoby jako znane).
    Brak paczek = zbiór pusty: podejrzana jest wtedy każda litera z flagą
    błędu mapowania PDFium (miara słabsza, ale nie cisza).
    """
    import core_poliglota
    # Suma alfabetów per paczka (`core_poliglota.alfabety_paczek`, z cache
    # po czasach modyfikacji) — ta sama, którą mojibake ocenia słowa.
    return frozenset().union(*core_poliglota.alfabety_paczek().values())


def _blad_mapowania(tp, i: int) -> bool:
    """PDFium: znak `i` nie ma mapowania Unicode w czcionce (wartość zgadnięta)."""
    if getattr(tp, "raw", None) is None:          # atrapa w testach
        return False
    import pypdfium2.raw as pdfium_c
    return pdfium_c.FPDFText_HasUnicodeMapError(tp.raw, i) == 1


def _flagi_strony(tp):
    """`_blad_mapowania` z pamięcią na jedną stronę: naprawa pyta o tę samą
    flagę trzy razy (przed, w trakcie, po) — 2 mln wywołań na słowniku."""
    pamiec: dict[int, bool] = {}

    def flaga(_tp, i: int) -> bool:
        if i not in pamiec:
            pamiec[i] = _blad_mapowania(tp, i)
        return pamiec[i]
    return flaga


def _policz_litery(tp, znaki: list[tuple[int, str]],
                   znane: frozenset[str] | None, flaga=None) -> tuple[int, int]:
    """(liter, podejrzanych) strony. Flagę PDFium pytamy tylko o litery spoza
    `litery_paczek()`, więc czysty dokument nie płaci za nią prawie nic."""
    if znane is None:
        return 0, 0
    flaga = flaga or _blad_mapowania
    litery = podejrzane = 0
    for i, z in znaki:
        if len(z) == 1:                       # szybka ścieżka: 99,9% znaków
            if z.isalpha():
                litery += 1
                if z not in znane and flaga(tp, i):
                    podejrzane += 1
            continue
        # `z` bywa kilkuznakowy: ligatura z fontu („f_f_i” → „ffi”), para
        # surogatów — liczymy jego litery, nie jego samego.
        ile = sum(c.isalpha() for c in z)
        if not ile:
            continue
        litery += ile
        if any(c.isalpha() and c not in znane for c in z) and flaga(tp, i):
            podejrzane += ile
    return litery, podejrzane


# ---------------------------------------------------------------------------
# Naprawa z osadzonego fontu (19.15, etap 2)
#
# Strona zniekształcona ma znaki, dla których PDFium nie znalazł Unicode
# w ToUnicode i oddał SAM KOD ZNAKU (zmierzone: „У” = U+0423 przychodzi jako
# U+024D, czyli kod 0x24D). W fontach Type0/Identity-H kod znaku to numer
# glifu, a sam program fontu (TrueType z PDF-a) zwykle wie, jaki znak rysuje
# ten glif: tablica `cmap` (Unicode → glif) odwrócona, a dla glifów spoza niej
# nazwa z tablicy `post` (`uni0430`, AGL). Bez przesunięć i bez list pism —
# słownik z macOS Quartz ma po prostu urwaną ToUnicode przy pełnym `cmap`.
# Naprawa jest PRÓBĄ: przyjmujemy ją tylko wtedy, gdy zmniejsza liczbę
# podejrzanych liter strony, a o tym, czy strona przestaje być zniekształcona,
# decyduje ta sama bramka co przed naprawą.
# ---------------------------------------------------------------------------

#: Font, którego znaki z flagą błędu mapowania są na stronie w co najmniej
#: takim ułamku podejrzane, uznajemy za oddający numery glifów. Niżej to font,
#: w którym PDFium zgadł dobrze (polski PDF z Worda: flaga na poprawnych
#: „ą”, „ł”) — jego znaków nie ruszamy, bo kod znaku nie musi tam być glifem.
UDZIAL_GLIFOW_FONTU = 0.5
#: Przerwa między literami (ułamek wysokości ramki), od której to odstęp
#: między słowami — tylko dla odstępu tuż po znaku łączącym z naprawy.
PRZERWA_SLOWA = 0.1


def _bajty_c(funkcja, *argumenty) -> bytes:
    """Dwuprzebiegowe API PDFium: pierwszy raz po długość, drugi po dane."""
    import ctypes
    n = ctypes.c_size_t(0)
    if not funkcja(*argumenty, None, 0, ctypes.byref(n)) or not n.value:
        return b""
    bufor = (ctypes.c_uint8 * n.value)()
    if not funkcja(*argumenty, bufor, n.value, ctypes.byref(n)):
        return b""
    return bytes(bufor[:n.value])


_RE_CID_DO_GID_STRUMIEN = re.compile(rb"/CIDToGIDMap\s*\d+\s+\d+\s+R")


def _mapa_cid_strumieniem(sciezka: str) -> bool:
    """Plik ma `CIDToGIDMap` jako strumień (kod znaku ≠ numer glifu).

    Naprawa z fontu bierze kod znaku Type0/Identity-H za numer glifu; przy
    takiej mapie dawała „ɗрадчпевдкн” zamiast „Утверждено” i zgłaszała to jako
    naprawione (audyt 19.15, zmierzone na PDF-ie z przesuniętą mapą). PDFium
    mapy nie udostępnia, więc taki dokument nie jest naprawiany — strony
    zostają zgłoszone jako zniekształcone. Ograniczenie: słownik fontu
    w skompresowanym strumieniu obiektów (`/ObjStm`) jest tu niewidoczny.
    """
    try:
        with open(sciezka, "rb") as fh:
            return _RE_CID_DO_GID_STRUMIEN.search(fh.read()) is not None
    except OSError:
        return False


def _dlugosc_danych(font) -> int:
    """Długość danych fontu — tylko zapytanie o rozmiar, bez kopiowania."""
    import ctypes
    import pypdfium2.raw as pdfium_c
    n = ctypes.c_size_t(0)
    return n.value if pdfium_c.FPDFFont_GetFontData(font, None, 0, ctypes.byref(n)) else 0


def _nazwa_fontu(font) -> str:
    import ctypes
    import pypdfium2.raw as pdfium_c
    n = pdfium_c.FPDFFont_GetBaseFontName(font, None, 0)
    if not n:
        return ""
    bufor = ctypes.create_string_buffer(n)
    pdfium_c.FPDFFont_GetBaseFontName(font, bufor, n)
    return bufor.value.decode("latin-1", "replace")


def mapa_glifow(dane: bytes) -> dict[int, str]:
    """Numer glifu → znak(i) wg programu fontu; `{}`, gdy fontu nie da się czytać.

    Odwrócony `cmap` ma pierwszeństwo (przy kilku punktach kodowych na glif
    bierzemy najniższy — spacja przed NBSP), nazwy `post` uzupełniają glify,
    których `cmap` nie zna (zmierzone: BoldItalic słownika, 40/51 z `cmap`).
    """
    if not dane:
        return {}
    try:
        import io
        from fontTools import agl
        from fontTools.ttLib import TTFont
        font = TTFont(io.BytesIO(dane), lazy=True)
        kolejnosc = font.getGlyphOrder()
        numery = {nazwa: nr for nr, nazwa in enumerate(kolejnosc)}
        mapa: dict[int, str] = {}
        for kod, nazwa in sorted((font.getBestCmap() or {}).items()):
            if nazwa in numery:
                mapa.setdefault(numery[nazwa], chr(kod))
        for nr, nazwa in enumerate(kolejnosc):
            if nr not in mapa:
                znak = agl.toUnicode(nazwa)
                if znak and not znak.isspace():
                    mapa[nr] = znak
        return mapa
    except Exception:  # noqa: BLE001 — font nieczytelny = brak naprawy, bramka zostaje
        return {}


def _napraw_z_fontu(tp, znaki: list[tuple[int, str]], znane: frozenset[str],
                    fonty: dict, flaga=None, potwierdzone: set[int] | None = None
                    ) -> list[tuple[int, str]] | None:
    """Znaki strony po podmianie kodów glifów na znaki z fontu; `None` = nic do zrobienia.

    `fonty` to pamięć podręczna całego dokumentu: klucz fontu → mapa glifów.
    Klucz to nazwa + długość + skrót DANYCH fontu, nie sama nazwa: w PDF-ach
    sklejonych z kilku plików, ze stałym prefiksem „AAAAAA+” albo bez nazwy
    dwa różne podzbiory noszą tę samą nazwę i drugi dostawał mapę pierwszego
    (audyt 19.15, M1: strona 2 „стуфх” wychodziła jako „абвгд”).
    """
    if getattr(tp, "raw", None) is None:
        return None
    import ctypes
    import pypdfium2.raw as pdfium_c
    zflagowane: dict[str, list[int]] = {}
    # Wskaźnik fontu → klucz, w obrębie strony: dane i nazwa fontu raz na
    # font strony, nie raz na znak (zmierzone na 880 tys. znaków słownika).
    nazwy: dict[int | None, tuple] = {}
    adresy: dict = fonty.setdefault("_adresy", {})
    flaga = flaga or _blad_mapowania
    for poz, (i, z) in enumerate(znaki):
        if z.isspace() or not flaga(tp, i):
            continue
        obiekt = pdfium_c.FPDFText_GetTextObject(tp.raw, i)
        font = pdfium_c.FPDFTextObj_GetFont(obiekt) if obiekt else None
        if not font:
            continue
        adres = ctypes.addressof(font.contents)   # 5× szybciej niż ctypes.cast
        if adres not in nazwy:
            # Tylko font OSADZONY: dla nieosadzonego PDFium oddaje dane fontu
            # systemowego, którego numeracja glifów nie musi mieć nic wspólnego
            # z kodami w PDF-ie (zmierzone: Times z Windows „pasował” przypadkiem).
            osadzony = pdfium_c.FPDFFont_GetIsEmbedded(font) == 1
            szybki = (_nazwa_fontu(font), _dlugosc_danych(font) if osadzony else 0)
            # Adres fontu → klucz na CAŁY dokument (PDFium trzyma font dokumentu
            # pod tym samym adresem): dane i skrót raz na font, nie raz na
            # stronę — słownik 11 → 28 s przy skrócie per strona (L2). Nazwa
            # i długość pilnują, czy pod adresem nie stoi już inny font.
            znany = adresy.get(adres)
            if znany is not None and znany[0] == szybki:
                klucz = znany[1]
            else:
                dane = _bajty_c(pdfium_c.FPDFFont_GetFontData, font) if osadzony else b""
                klucz = szybki + (hashlib.sha1(dane).digest(),)
                adresy[adres] = (szybki, klucz)
                if klucz not in fonty:
                    fonty[klucz] = mapa_glifow(dane) if osadzony else {}
            nazwy[adres] = klucz
        nazwa = nazwy[adres]
        zflagowane.setdefault(nazwa, []).append(poz)
    wynik = list(znaki)
    zmiana = False
    for nazwa, pozycje in zflagowane.items():
        mapa = fonty[nazwa]
        if mapa and potwierdzone is not None:
            # Font sam mówi, że glif rysuje dokładnie ten znak, który zgadł
            # PDFium: litera jest poprawna, choć flagowana. Bez tego poprawny
            # czeski („Příliš žluťoučký”) i grecki — języki bez paczki — szły
            # do bramki jako zniekształcone (audyt 19.15, zmierzone).
            potwierdzone.update(znaki[p][0] for p in pozycje
                                if len(znaki[p][1]) == 1 and znaki[p][1].isalpha()
                                and znaki[p][1] not in znane
                                and mapa.get(ord(znaki[p][1])) == znaki[p][1])
        litery = [znaki[p][1] for p in pozycje if znaki[p][1].isalpha()]
        if not mapa or not litery or \
                sum(z not in znane for z in litery) < UDZIAL_GLIFOW_FONTU * len(litery):
            continue
        for p in pozycje:
            i, z = znaki[p]
            nowy = mapa.get(ord(z)) if len(z) == 1 else None
            if nowy is not None and nowy != z:
                wynik[p] = (i, nowy)
                zmiana = True
    return wynik if zmiana else None


def _czysc(tekst: str) -> str:
    return _RE_STERUJACE.sub("", tekst.translate(_LIGATURY).replace("\r", ""))


def _rzymska(tekst: str) -> int | None:
    """Wartość POPRAWNEJ liczby rzymskiej (kanoniczny zapis), inaczej None."""
    s = tekst.lower()
    if not s or any(z not in _RZYMSKIE for z in s):
        return None
    wartosc = 0
    for a, b in zip(s, s[1:] + " "):
        va, vb = _RZYMSKIE[a], _RZYMSKIE.get(b, 0)
        wartosc += -va if va < vb else va
    if not 0 < wartosc < 4000:
        return None
    # Kanoniczność: „IIII”, „VX”, „DID” nie są numerami stron.
    kanon, reszta = "", wartosc
    for v, z in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"),
                 (90, "xc"), (50, "l"), (40, "xl"), (10, "x"), (9, "ix"),
                 (5, "v"), (4, "iv"), (1, "i")):
        while reszta >= v:
            kanon += z
            reszta -= v
    return wartosc if kanon == s else None


def _wartosc_numeru(tekst: str) -> int | None:
    m = _RE_NUMER_STRONY.match(tekst)
    if not m:
        return None
    rdzen = m.group(1)
    return int(rdzen) if rdzen.isdigit() else _rzymska(rdzen)


def _znaki_strony(tp) -> list[tuple[int, str]]:
    """(indeks znaku PDFium, znak) — indeks to argument dla `get_charbox`.

    Szybka ścieżka: jeden `get_text_range()`, gdy jego długość równa się
    `count_chars()` (indeksy 1:1, zmierzone na 93 stronach). Inaczej znak po
    znaku przez `FPDFText_GetUnicode`: glif bez Unicode (0) wypada z
    `get_text_range`, więc od tego miejsca indeksy się rozjeżdżały i ramki
    należały do sąsiednich znaków (audyt 19.13: „ko ncu wiersza”); znaki spoza
    BMP przychodzą jako pary surogatów i są sklejane.
    """
    n = tp.count_chars()
    pelny = tp.get_text_range()
    if len(pelny) == n:
        return list(enumerate(pelny))
    import pypdfium2.raw as pdfium_c
    wynik: list[tuple[int, str]] = []
    wysoki: tuple[int, int] | None = None
    for i in range(n):
        u = pdfium_c.FPDFText_GetUnicode(tp.raw, i)
        if u == 0:
            continue
        if 0xD800 <= u < 0xDC00:
            wysoki = (i, u)
            continue
        if 0xDC00 <= u < 0xE000 and wysoki is not None:
            wynik.append((wysoki[0], chr(0x10000 + ((wysoki[1] - 0xD800) << 10) + (u - 0xDC00))))
            wysoki = None
            continue
        wysoki = None
        wynik.append((i, chr(u)))
    return wynik


def _znaki_po_naprawie(tp, znane: frozenset[str] | None, fonty: dict | None
                       ) -> tuple[list[tuple[int, str]], int, int, bool]:
    """(znaki, liter, podejrzanych, naprawiona) strony, po próbie naprawy z fontu.

    Naprawę próbujemy tylko na stronie zniekształconej i przyjmujemy tylko
    wtedy, gdy zmniejsza liczbę podejrzanych liter — czysta strona zostaje
    co do bajta taka jak przed etapem 2.
    """
    wszystkie = _znaki_strony(tp)
    flaga = _flagi_strony(tp)
    litery, podejrzane = _policz_litery(tp, wszystkie, znane, flaga)
    if znane is None or fonty is None or not czy_znieksztalcona(litery, podejrzane):
        return wszystkie, litery, podejrzane, False
    potwierdzone: set[int] = set()
    nowe = _napraw_z_fontu(tp, wszystkie, znane, fonty, flaga, potwierdzone)
    if potwierdzone:
        flaga_strony = flaga
        flaga = lambda tp_, i: i not in potwierdzone and flaga_strony(tp_, i)  # noqa: E731
        litery, podejrzane = _policz_litery(tp, wszystkie, znane, flaga)
        if not czy_znieksztalcona(litery, podejrzane):
            return wszystkie, litery, podejrzane, False
    if nowe is None:
        return wszystkie, litery, podejrzane, False
    litery2, podejrzane2 = _policz_litery(tp, nowe, znane, flaga)
    if podejrzane2 >= podejrzane:
        return wszystkie, litery, podejrzane, False
    return nowe, litery2, podejrzane2, True


#: Granica słowa wewnątrz tekstu rozstrzelonego, wyznaczona geometrią linii
#: (nieznak Unicode — nie występuje w żadnym tekście, w przeciwieństwie do
#: obszaru prywatnego fontów Wingdings; przeżywa `_czysc` i zwijanie spacji).
#: `_scal_rozstrzelone_pdf` zamienia go na dwie spacje, potem znika.
_GRANICA = chr(0xFDD0)
#: Spacja WIRTUALNA (wstawiona z geometrii, `PRZERWA_ROZSTRZELENIA`) w tekście
#: linii — też nieznak. Moduł widzi ją jako zwykłą spację; w ciągu, którego
#: NIE skleił, `_scal_rozstrzelone_pdf` ją zdejmuje: tekst wraca do stanu
#: sprzed wirtualnych spacji zamiast „р а з б о р)”, „о д н а” (audyt M3).
_WIRTUALNA = chr(0xFDD1)
#: Odstęp większy od mediany odstępów ciągu o tyle razy to granica słowa.
#: Wspólne z ATA (etap 4b, pomiar PDFium 2026-10-20): Земская ma przerwy
#: międzyliterowe 0,8–1,3× mediany i granice słów 1,5–2,0× (większość
#: 1,8–1,9×) — przy 1,8 połowa granic ginęła („существительныхнеод…”);
#: słownik: litery ≈1,0×, granice 2,5–5,5×.
GRANICA_ROZSTRZELENIA = 1.5
#: Po literze z akcentem przerwa w słowie rośnie do 2,0× mediany (334 razy
#: w słowniku: rozstrzelenie dodaje odstęp także znakowi akcentu, „ф о р м а́ т”),
#: a granica słowa po akcencie to ~4× („В о й н а́  в а к ц и́ н”, 17,4 vs
#: 4,1 pt). Bezwzględny zakaz granicy po akcencie (do 4b) sklejał „Война́вакци́н”.
GRANICA_PO_AKCENCIE = 2.5
#: Brakująca spacja w rozstrzeleniu (ułamek wysokości ramki): Земская ma
#: 3,6–4,2 pt przy wysokości 10 pt tam, gdzie litery słowa dzielą 0,1–0,2 pt;
#: słownik ma ≥0,3 tylko 13 razy na 643 tys. par liter, „Повесть” 7 (brakujące
#: spacje między słowami: „ив неправдh” → „и в”), reszta 99 PDF-ów 0.
PRZERWA_ROZSTRZELENIA = 0.3


def _oznacz_granice_rozstrzelenia(znaki: list[str], luki: dict[int, float],
                                  wirtualne: frozenset[int] | set[int] = frozenset()) -> None:
    """W ciągu ≥4 pojedynczych liter zamienia spacje-granice słów na `_GRANICA`.

    `wirtualne` — indeksy spacji wstawionych z geometrii (`PRZERWA_ROZSTRZELENIA`).
    Zostaje tylko taka, która leży WEWNĄTRZ przyjętego ciągu; inna nie da się
    skleić z powrotem i psuła tekst (audyt 19.15, M3: „Гл а в а I I I”,
    „о д н а”), więc znika — linia wraca do stanu sprzed wirtualnych spacji.

    W PDF-ie między literami rozstrzelenia i między jego słowami stoi tak
    samo JEDNA spacja (generowana), a różni je tylko przerwa. Nie sklejamy
    tu niczego — o sklejeniu decyduje słownik dokumentu (`_scal_rozstrzelone_pdf`),
    jak w `.docx`. Ciąg o równych przerwach (np. „а и в к”) nie dostaje granic.
    """
    from czyszczenie_tekstu import MIN_ROZSTRZELENIE, OTWIERAJACE, ZAMYKAJACE
    zostaja: set[int] = set()

    def prog(s: int) -> float:
        # Po literze z akcentem przerwa rośnie (rozstrzelenie dodaje odstęp
        # także znakowi akcentu): przy progu ogólnym „ф о р м а́ т” dzieliło
        # się na „форма́” + „т”, więc tam próg jest wyższy.
        return GRANICA_PO_AKCENCIE if s > 0 and unicodedata.combining(znaki[s - 1][0]) \
            else GRANICA_ROZSTRZELENIA

    # Brzeg ciągu to też granica słowa, gdy sąsiad jest SŁOWEM: rozstrzelenie
    # wpisane w zdanie („…изучения - о п и с а т ь”, „Е.А. З е м с к а я”) było
    # dla modułu przyklejone pojedynczą spacją i nie sklejało się nigdy
    # (Земская: 509 ciągów, etap 4b). Przerwa tu nie rozstrzyga — zwykła
    # spacja (~3 pt) bywa węższa od odstępu liter rozstrzelenia (~4,9 pt).
    # Ciąg na brzegu LINII dostaje granicę zawsze: linie skleja potem
    # pojedyncza spacja.
    na_poczatku = na_koncu = False
    k, n = 0, len(znaki)
    while k < n:
        # Ciąg nie zaczyna się w ŚRODKU słowa: „межд|у  с л о в о” startował od
        # ostatniej litery „между”, był przyklejony do „д” i nie dostawał
        # żadnej granicy (Земская: 255 → 503 ciągi, etap 5b).
        if k > 0 and (znaki[k - 1][:1].isalpha() or unicodedata.combining(znaki[k - 1][0])):
            k += 1
            continue
        # Jednostka = jedna litera + jej znaki łączące; ciąg = jednostki
        # rozdzielone pojedynczą spacją, nieprzyklejone do liter z boku.
        poczatek, spacje, j = k, [], k
        while j < n and len(znaki[j]) == 1 and znaki[j].isalpha():
            j += 1
            while j < n and unicodedata.combining(znaki[j][0]):
                j += 1
            if j + 1 < n and znaki[j] == " " and j in luki and len(znaki[j + 1]) == 1 \
                    and znaki[j + 1].isalpha() and _jednoliterowa(znaki, j + 1):
                spacje.append(j)
                j += 1
                continue
            break
        przyklejony = (poczatek > 0 and znaki[poczatek - 1].isalpha()) or \
            (j < n and znaki[j][:1].isalpha())
        # Same wersaliki rzymskie („I I I” w „Г л а в а  I I I”) to numer, nie
        # słowo do sklejenia — wirtualne spacje w nim nie zostają.
        rzymska = all(znaki[s - 1] in "IVXLCDM" for s in spacje + [j]) if spacje else False
        if len(spacje) + 1 >= MIN_ROZSTRZELENIE and not przyklejony and not rzymska:
            zostaja.update(spacje)
            mediana = max(statistics.median(luki[s] for s in spacje), 0.1)
            for s in spacje:
                if luki[s] > prog(s) * mediana:
                    znaki[s] = _GRANICA
            # Lewy brzeg: zawsze granica — ciąg jest maksymalny, więc sąsiad po
            # lewej nie jest samotną literą, a urywek „litera + interpunkcja”
            # może być tylko KOŃCEM słowa („ж.  В о л н а́” to skrót przed
            # słowem). Prawy brzeg: granica, gdy sąsiad jest słowem albo
            # przerwa jest słowna; „м а́ с к а.” zostaje dla ograniczenia modułu.
            if poczatek > 0 and znaki[poczatek - 1] == " ":
                znaki[poczatek - 1] = _GRANICA
            elif poczatek > 1 and znaki[poczatek - 1] in OTWIERAJACE and znaki[poczatek - 2] == " ":
                # „(р а з б о р)”: nawias otwierający należy do ciągu (moduł,
                # etap 6), brzeg to spacja PRZED nim.
                znaki[poczatek - 2] = _GRANICA
            # Ogon interpunkcji („н и я.  Слова”) należy do ciągu (moduł przyjmuje
            # go od etapu 5), więc brzeg to spacja PO nim — bez tego ciąg
            # przed kolejnym słowem zostawał przyklejony (Земская, etap 5b).
            ogon = j
            while ogon < n and znaki[ogon] in ZAMYKAJACE:
                ogon += 1
            if ogon < n and znaki[ogon] == " " and (
                    _sasiad_jest_slowem(znaki, ogon + 1, 1)
                    or (ogon in luki and luki[ogon] > prog(ogon) * mediana)):
                znaki[ogon] = _GRANICA
            na_poczatku = na_poczatku or poczatek == 0
            na_koncu = na_koncu or ogon >= n
        k = max(j, k + 1)
    for s in wirtualne:
        if znaki[s] == " ":
            znaki[s] = _WIRTUALNA if s in zostaja else ""
    if na_koncu:
        znaki.append(_GRANICA)
    if na_poczatku:
        znaki.insert(0, _GRANICA)


def _jednoliterowa(znaki: list[str], k: int) -> bool:
    """Litera `znaki[k]` (z ewentualnymi znakami łączącymi) stoi SAMA: po niej
    nie ma kolejnej litery. Bez tego ciąg zjadał pierwszą literę następnego,
    zwykłego słowa („… е  к|онец”) i cały wychodził jako przyklejony (do 4b)."""
    k += 1
    while k < len(znaki) and unicodedata.combining(znaki[k][0]):
        k += 1
    return k >= len(znaki) or not znaki[k][:1].isalpha()


def _sasiad_jest_slowem(znaki: list[str], od: int, krok: int) -> bool:
    """Token zaczynający się w `znaki[od]` (w kierunku `krok`) to słowo, nie urywek.

    Urywek = jedna litera (z akcentem) i sama interpunkcja: „а.”, „а,”, „(я”.
    """
    token = []
    k = od
    while 0 <= k < len(znaki) and znaki[k] != " " and znaki[k] != _GRANICA:
        token.append(znaki[k])
        k += krok
    if krok < 0:
        token.reverse()
    tekst = "".join(token)
    litery = [z for z in tekst if z.isalpha()]
    return len(litery) != 1


def _scal_rozstrzelone_pdf(akapity: list[str]) -> tuple[list[str], dict[str, int]]:
    """Decyzja wspólnego modułu na tekście PDF z granicami słów z geometrii.

    Granice przychodzą jako dwie spacje (`_czytaj_strone`) — po `_RE_BIALE`
    to jedyne podwójne spacje w tekście, więc po decyzji zwijamy je do jednej.
    """
    import czyszczenie_tekstu
    wejscie = [a.replace(_WIRTUALNA, " ") for a in akapity]
    wynik, liczniki = czyszczenie_tekstu.scal_rozstrzelone(wejscie)
    wynik = [_bez_wirtualnych(a, w) if _WIRTUALNA in a else w for a, w in zip(akapity, wynik)]
    return [re.sub(" {2,}", " ", a) for a in wynik], liczniki


def _bez_wirtualnych(przed: str, po: str) -> str:
    """Akapit po decyzji modułu bez spacji wirtualnych w ciągach NIESKLEJONYCH.

    Moduł nie rusza tokenów ciągu, którego nie skleił, więc w blokach równych
    tokenów (przed → po) separator, który był spacją wirtualną, znika.
    """
    import difflib
    czesci_a = re.split(f"([ {_WIRTUALNA}]+)", przed)
    czesci_b = re.split("( +)", po)
    tokeny_a, tokeny_b = czesci_a[0::2], czesci_b[0::2]
    for tag, i1, i2, j1, _ in difflib.SequenceMatcher(
            None, tokeny_a, tokeny_b, autojunk=False).get_opcodes():
        if tag != "equal":
            continue
        for k in range(i2 - i1 - 1):
            if czesci_a[2 * (i1 + k) + 1] == _WIRTUALNA:
                czesci_b[2 * (j1 + k) + 1] = ""
    return "".join(czesci_b)


def _napraw_mojibake_stron(akapity_stron: list[list[str]]
                           ) -> tuple[list[list[str]], dict[int, str]]:
    """Strony zapisane w złej stronie kodowej („Áèáëèîòåêà”) → przekodowane.

    Decyzja per akapit strony (`czyszczenie_tekstu.napraw_mojibake_akapitow`, alfabety
    paczek per język); krótkie akapity dostają kodowanie, które wygrało
    na stronie. Strona, której nie umiemy przekodować, NIE jest zgłaszana — niska
    wiarygodność bez kandydata to zwykle język bez paczki (portugalski), nie
    mojibake. Zwraca też {numer strony: „latin-1>cp1251”}.
    """
    import core_poliglota
    import czyszczenie_tekstu as ct
    alfabety = list(core_poliglota.alfabety_paczek().values())
    przekodowane: dict[int, str] = {}
    wynik: list[list[str]] = []
    for nr, akapity in enumerate(akapity_stron, start=1):
        nowe, info = ct.napraw_mojibake_akapitow(akapity, alfabety)
        wynik.append(nowe)
        if info["kodowania"]:
            przekodowane[nr] = max(info["kodowania"], key=lambda k: info["kodowania"][k])
    return wynik, przekodowane


def _linie_strony(strona) -> list[_Linia]:
    return _czytaj_strone(strona, None)[0]


def _czytaj_strone(strona, znane: frozenset[str] | None, fonty: dict | None = None
                   ) -> tuple[list[_Linia], int, int, int, bool]:
    """(linie, liter, podejrzanych, znaków, naprawiona) — linie WIZUALNE w kolejności strumienia treści.

    Tekst bierzemy z `_znaki_strony`, a linie budujemy z ramki KAŻDEGO znaku
    (`loose=True` = wysokość czcionki, nie obrys glifu; 152 tys. znaków
    w 0,36 s). Dwa skróty okazały się błędne:
      * `get_rect` + `get_text_bounded` — prostokąty biegów zachodzą na siebie
        i ramka łapała znaki sąsiada: 244 zdublowane znaki na 91 stronach;
      * podział po `\\r\\n` z PDFium — w PDF-ach z Worda PDFium NIE łamie
        zawiniętych wierszy akapitu, więc „linia" obejmowała cztery wiersze,
        a za to łamie W ŚRODKU wiersza po odnośniku przypisu w indeksie
        górnym („словопроизводство⁷ | . Однако").
    Dlatego `\\r\\n` z PDFium jest tu tylko odstępem, a nową linię wyznacza
    wyłącznie geometria: brak pionowego pokrycia z bieżącą linią albo
    cofnięcie w lewo (zawinięcie). Bieg innym krojem na tej samej wysokości
    („…как | , словообразование") zostaje w tej samej linii. Pismo od prawej
    do lewej (hebrajski, arabski) idzie w lewo z natury, więc jego znaki nie
    liczą się jako cofnięcie — inaczej linia rozpadała się co 2–3 litery.
    """
    tp = strona.get_textpage()
    try:
        linie: list[_Linia] = []
        znaki: list[str] = []
        ramka: list[float] = []
        wysokosci: list[float] = []

        def zamknij() -> None:
            _oznacz_granice_rozstrzelenia(znaki, luki, wirtualne)
            wirtualne.clear()
            tekst = _RE_BIALE.sub(" ", _czysc("".join(znaki))).strip()
            luki.clear()
            # Granica na brzegu linii nie zostaje w jej tekście (podział na
            # akapity patrzy na pierwszy i ostatni znak), tylko we flagach.
            lewa, prawa = tekst.startswith(_GRANICA), tekst.endswith(_GRANICA)
            # W środku linii granica to DWIE spacje — jak w `.docx`; regexy
            # podziału na akapity widzą wtedy zwykły biały znak („4)  у с е…”
            # ze znakiem granicy nie był już punktem listy, etap 4b).
            tekst = tekst.strip(_GRANICA + " ").replace(_GRANICA, "  ")
            if naprawiona:
                tekst = unicodedata.normalize("NFC", tekst)
            if tekst:
                linie.append(_Linia(tekst, *ramka,
                                    czcionka=statistics.median(wysokosci),
                                    rozstrzelona_lewa=lewa, rozstrzelona_prawa=prawa))
            znaki.clear()
            ramka.clear()
            wysokosci.clear()

        wszystkie, litery, podejrzane, naprawiona = _znaki_po_naprawie(tp, znane, fonty)
        # Odstęp tuż po znaku łączącym czeka na geometrię następnej litery.
        odstep_po_laczacym = False
        # Indeks spacji w `znaki` → przerwa (pt) między sąsiednimi znakami;
        # prawa krawędź ostatniego znaku niebędącego spacją.
        luki: dict[int, float] = {}
        wirtualne: set[int] = set()
        prawy_ostatni: float | None = None
        for i, z in wszystkie:
            if z.isspace():
                if znaki and unicodedata.combining(znaki[-1][-1]) and naprawiona:
                    odstep_po_laczacym = True
                elif znaki and znaki[-1] != " ":
                    znaki.append(" ")
                continue
            # Znak łączący z naprawy (akcent U+0301 w słowniku) siedzi nad
            # literą: jego ramka rozcinałaby linię, a odstęp przed nim
            # dawał „ЛЯ ́ЦИЯ”. Dokleja się do poprzedniego znaku.
            if naprawiona and unicodedata.combining(z[0]):
                if znaki and znaki[-1] == " ":
                    znaki.pop()
                znaki.append(z)
                continue
            l, d, p, g = tp.get_charbox(i, loose=True)
            if odstep_po_laczacym:
                # PDFium łamie wiersz za akcentem (jego ramka cofa pozycję), więc
                # „бо́ льшая”. Spacja zostaje tylko przy realnej przerwie od
                # litery pod akcentem — tej samej, jaką mają słowa w linii.
                odstep_po_laczacym = False
                if ramka and l - ramka[2] > (g - d) * PRZERWA_SLOWA:
                    znaki.append(" ")
            if ramka:
                lewo, dol, prawo, gora = ramka
                wys = max(gora - dol, g - d, 1.0)
                # Ta sama linia = pionowe POKRYCIE co najmniej połowy niższej
                # ramki. Kryterium środka rozcinało linię na odnośniku przypisu
                # w indeksie górnym („…Шанский и А¹ | . Однако…").
                pokrycie = min(gora, g) - max(dol, d)
                inna_wysokosc = pokrycie < min(gora - dol, g - d, wys) * 0.5
                # z[0]: ligatura z fontu („ffi”) i znak spoza BMP mają >1 znak.
                rtl = unicodedata.bidirectional(z[0]) in ("R", "AL")
                cofniecie = not rtl and l < prawo - wys
                if inna_wysokosc or cofniecie:
                    zamknij()
            if not ramka:
                ramka[:] = [l, d, p, g]
            else:
                if z in _DOKLEJANE and znaki and znaki[-1] == " ":
                    znaki.pop()
                ramka[:] = [min(ramka[0], l), min(ramka[1], d),
                            max(ramka[2], p), max(ramka[3], g)]
            # Rozstrzelenie z DZIURAMI w warstwie tekstu: Земская ma jawne
            # spacje tylko między częścią liter („ме х а н из м”, „д и ах р о…”:
            # między „а” a „х” 4,2 pt i brak spacji, tyle co odstępy liter
            # obok). Litery słowa dzieli tam 0,1–0,2 pt; zmierzone wystąpienia
            # w 99 czystych PDF-ach → `PRZERWA_ROZSTRZELENIA` (etap 5b).
            if (prawy_ostatni is not None and z.isalpha() and znaki
                    and len(znaki[-1]) == 1 and znaki[-1].isalpha()
                    and l - prawy_ostatni >= (g - d) * PRZERWA_ROZSTRZELENIA):
                wirtualne.add(len(znaki))
                znaki.append(" ")
            if znaki and znaki[-1] == " " and prawy_ostatni is not None:
                luki[len(znaki) - 1] = l - prawy_ostatni
            znaki.append(z)
            wysokosci.append(g - d)
            prawy_ostatni = p
        zamknij()
        return linie, litery, podejrzane, len(wszystkie), naprawiona
    finally:
        tp.close()


def _linie_bez_geometrii(strona) -> list[_Linia]:
    return _czytaj_strone_bez_geometrii(strona, None)[0]


def _czytaj_strone_bez_geometrii(strona, znane: frozenset[str] | None,
                                 fonty: dict | None = None
                                 ) -> tuple[list[_Linia], int, int, int, bool]:
    """Strona obrócona o 90°/270°: linie z kolejności tekstu, bez geometrii.

    Ramki znaków PDFium są w układzie NIEOBRÓCONYM, więc na takiej stronie
    „pionowe pokrycie” i „cofnięcie” mierzą niewłaściwą oś (audyt 19.13:
    kolejność linii odwrócona przy 90°). Linie bierzemy z łamań PDFium i
    nadajemy im współrzędne środka strony — akapity dzielą wtedy wyłącznie
    reguły tekstowe, a kolontytuły i numery stron nie są tu usuwane.
    """
    tp = strona.get_textpage()
    try:
        wszystkie, litery, podejrzane, naprawiona = _znaki_po_naprawie(tp, znane, fonty)
        tekst = "".join(z for _, z in wszystkie)
        if naprawiona:
            tekst = unicodedata.normalize("NFC", tekst)
    finally:
        tp.close()
    linie = []
    for nr, kawalek in enumerate(re.split(r"\r\n|\n|\r", tekst)):
        czysty = _RE_BIALE.sub(" ", _czysc(kawalek)).strip()
        if czysty:
            linie.append(_Linia(czysty, 0.0, -12.0 * nr, 1000.0, -12.0 * nr + 10, czcionka=10.0))
    return linie, litery, podejrzane, len(wszystkie), naprawiona


@dataclass
class _Strona:
    linie: list[_Linia]
    dol: float
    gora: float
    #: False dla stron obróconych o 90°/270° — margines nie jest wtedy znany.
    geometria: bool = True
    litery: int = 0
    #: Litery z błędem mapowania PDFium spoza `litery_paczek()`.
    podejrzane: int = 0
    znaki: int = 0
    #: Znaki odtworzone z osadzonego fontu (`_napraw_z_fontu`).
    naprawiona: bool = False

    @property
    def znieksztalcona(self) -> bool:
        return czy_znieksztalcona(self.litery, self.podejrzane)

    def w_marginesie(self, linia: _Linia) -> bool:
        """Linia w pasie marginesu ALBO skrajna górna / dolna linia strony.

        Sam pas 7% gubił kolontytuł słownika z macOS Quartz („Часть I” górą
        na 7,7%, numer strony dołem na 7,4%; 412 stron). Szerszy pas łapał
        pierwszą i ostatnią linię treści (audyt 19.13), a skrajna linia to
        tylko JEDNA linia z każdej strony — o tym, czy to kolontytuł, dalej
        decyduje powtórzenie na ćwierci stron albo numer rosnący ze stroną.
        """
        if not self.geometria:
            return False
        pas = (self.gora - self.dol) * PAS_MARGINESU
        if linia.gora >= self.gora - pas or linia.dol <= self.dol + pas:
            return True
        return any(linia is x for x in self._skrajne_odsuniete)

    def skrajna(self, linia: _Linia) -> bool:
        """Najwyższa albo najniższa linia strony (bez warunku odsunięcia)."""
        return self.geometria and len(self.linie) >= 3 and any(
            linia is x for x in (max(self.linie, key=lambda x: x.gora),
                                 min(self.linie, key=lambda x: x.dol)))

    @functools.cached_property
    def _skrajne_odsuniete(self) -> list[_Linia]:
        """Skrajna górna i dolna linia, o ile ODSUNIĘTA od reszty strony.

        Odstęp do najbliższej linii ≥ `ODSUNIECIE_SKRAJNEJ` × wysokość tej
        linii (słownik: 1,2–1,4) i co najmniej 3 linie na stronie — przy
        dwóch liniach nie ma bloku treści, od którego kolontytuł się odcina.
        """
        if len(self.linie) < 3:
            return []
        wynik = []
        po_gorze = sorted(self.linie, key=lambda x: -x.gora)
        gorna, druga = po_gorze[0], po_gorze[1]
        if gorna.dol - druga.gora >= ODSUNIECIE_SKRAJNEJ * gorna.wysokosc:
            wynik.append(gorna)
        po_dole = sorted(self.linie, key=lambda x: x.dol)
        dolna, przedostatnia = po_dole[0], po_dole[1]
        if przedostatnia.dol - dolna.gora >= ODSUNIECIE_SKRAJNEJ * dolna.wysokosc:
            wynik.append(dolna)
        return wynik


def _numery_stron_do_usuniecia(strony: list[_Strona]) -> set[tuple[int, int]]:
    """(strona, indeks linii) gołych numerów stron, które wolno usunąć.

    Kształt numeru to za mało: linia w marginesie znika tylko wtedy, gdy jej
    wartość rośnie RAZEM ze stroną — ta sama różnica „numer − indeks strony”
    w tym samym pasie (góra/dół) na co najmniej max(2, ⌈UDZIAL_STRON·N⌉)
    stronach. Rzymski nagłówek „II” na jednej stronie, słowo „MIX” czy rok
    „2026” w stopce tej różnicy nie dzielą i zostają. Dokument jednostronicowy
    nie traci nic.
    """
    kandydaci: dict[tuple[str, int], list[tuple[int, int]]] = {}
    for s_nr, strona in enumerate(strony):
        for l_nr, linia in enumerate(strona.linie):
            # Numer ma własną bramkę (rośnie razem ze stroną), więc skrajna
            # linia wystarcza bez odsunięcia: na pełnej stronie słownika numer
            # stoi 0,14–0,64 wysokości linii pod tekstem (19.15).
            if not (strona.w_marginesie(linia) or strona.skrajna(linia)):
                continue
            wartosc = _wartosc_numeru(linia.tekst)
            if wartosc is None:
                continue
            pas = "gora" if linia.gora >= (strona.dol + strona.gora) / 2 else "dol"
            kandydaci.setdefault((pas, wartosc - s_nr), []).append((s_nr, l_nr))
    prog = max(2, math.ceil(len(strony) * UDZIAL_STRON))
    wynik: set[tuple[int, int]] = set()
    for miejsca in kandydaci.values():
        if len({s for s, _ in miejsca}) >= prog:
            wynik.update(miejsca)
    return wynik


def _usun_kolontytuly(strony: list[_Strona]) -> tuple[list[list[_Linia]], list[str]]:
    """Usuwa kolontytuły i gołe numery stron z pasa marginesu.

    Kolontytuł = linia w pasie marginesu (±1 krok 6 pt wysokości), której
    tekst powtarza się 1:1 na co najmniej max(3, ⌈UDZIAL_STRON·N⌉) stronach,
    albo której rdzeń bez numeru na brzegu powtarza się tak samo, a numer
    rośnie razem ze stroną (stała różnica numer − indeks w ≥ ZGODNOSC_NUMERU
    wystąpień). Do 19.13 numer był po prostu zdejmowany, więc „Rozdział 1…8”
    na górze kolejnych stron dawało jeden klucz i znikało jako kolontytuł
    (audyt 19.13) — dokładnie ta reguła zawiodła wcześniej w ATA. Dokumenty
    krótsze niż 3 strony są nietknięte. Linie-tagi `[...]`/`(...)` są
    chronione zawsze — to składnia Reżysera i didaskalia, nie stopka.
    """
    n = len(strony)
    numery = _numery_stron_do_usuniecia(strony)
    if n < 3:
        return ([[l for i, l in enumerate(s.linie) if (s_nr, i) not in numery]
                 for s_nr, s in enumerate(strony)], [])
    prog = max(3, math.ceil(n * UDZIAL_STRON))

    def kandydat(strona: _Strona, linia: _Linia) -> bool:
        return strona.w_marginesie(linia) and not _RE_TAG_NAWIASOWY.match(linia.tekst)

    def norm(t: str) -> str:
        return re.sub(r"\s+", " ", t).lower().strip()

    dokladne: Counter = Counter()
    # Ten sam licznik osobno dla stron parzystych i nieparzystych (19.15):
    # książka ma inny kolontytuł na lewej i prawej stronie, a słownik na
    # lewych przełącza go jeszcze w połowie („Часть I” 126, „Часть II” 88
    # z 275 stron parzystych) — żaden nie dochodził do ćwierci WSZYSTKICH.
    dokladne_par: Counter = Counter()
    rdzenie: dict[tuple[str, int], list[int]] = {}
    oryginal: dict[tuple, str] = {}
    for s_nr, strona in enumerate(strony):
        widziane = set()
        for linia in strona.linie:
            if not kandydat(strona, linia):
                continue
            y = round(linia.dol / 6)
            klucz = (norm(linia.tekst), y)
            if len(klucz[0]) >= 3 and klucz not in widziane:
                dokladne[klucz] += 1
                dokladne_par[(klucz, s_nr % 2)] += 1
                widziane.add(klucz)
                oryginal.setdefault(klucz, linia.tekst)
            m = _RE_NUMER_NA_BRZEGU.match(linia.tekst)
            if m:
                numer = int(m.group(1) or m.group(4))
                rdzen = norm(m.group(2) or m.group(3))
                if len(rdzen) >= 3 and (rdzen, y) not in widziane:
                    rdzenie.setdefault((rdzen, y), []).append(numer - s_nr)
                    widziane.add((rdzen, y))
                    oryginal.setdefault((rdzen, y), linia.tekst)
    prog_par = [max(3, math.ceil(len(strony[p::2]) * UDZIAL_STRON)) for p in (0, 1)]
    naglowki = {k for k, c in dokladne.items() if c >= prog}
    naglowki |= {k for (k, p), c in dokladne_par.items() if c >= prog_par[p]}
    numerowane = {k for k, off in rdzenie.items()
                  if len(off) >= prog
                  and Counter(off).most_common(1)[0][1] >= ZGODNOSC_NUMERU * len(off)}

    def pasuje(zbior: set, tekst: str, y: int) -> bool:
        return any((tekst, y + dy) in zbior for dy in (-1, 0, 1))

    wynik: list[list[_Linia]] = []
    for s_nr, strona in enumerate(strony):
        zostaja = []
        for l_nr, linia in enumerate(strona.linie):
            if (s_nr, l_nr) in numery:
                continue
            if kandydat(strona, linia):
                y = round(linia.dol / 6)
                if pasuje(naglowki, norm(linia.tekst), y):
                    continue
                m = _RE_NUMER_NA_BRZEGU.match(linia.tekst)
                if m and pasuje(numerowane, norm(m.group(2) or m.group(3)), y):
                    continue
            zostaja.append(linia)
        wynik.append(zostaja)
    usuniete = sorted({oryginal[k] for k in naglowki | numerowane})
    return wynik, usuniete


def _sklej(lewy: str, prawy: str, dzielenie_auto: bool = False) -> str:
    """Łączy dwie linie akapitu, zdejmując przeniesienie wyrazu.

    Miękki dywiz (dzielenie automatyczne) skleja zawsze. Zwykły dywiz:
      * gdy dokument ma dzielenie automatyczne (PDF z Worda), zwykły dywiz na
        końcu linii jest PRAWDZIWY — „biało-|czerwona” → „biało-czerwona”,
        „e-|mail” → „e-mail” (audyt 19.13: wychodziło „białoczerwona”);
      * bez dzielenia automatycznego przed małą literą to przeniesienie
        („przy-|kład” → „przykład”), przed wielką albo cyfrą łącznik bez
        spacji („Jean-|Paul” → „Jean-Paul”).
    """
    if lewy.endswith("\u00ad"):
        return lewy[:-1] + prawy
    if _RE_PRZENIESIENIE.search(lewy):
        if dzielenie_auto or not prawy[:1].islower():
            return lewy + prawy
        return lewy[:-1] + prawy
    return lewy + " " + prawy


def _podziel_na_akapity(linie: list[_Linia], dzielenie_auto: bool = False) -> list[str]:
    """Skleja linie jednej strony w akapity.

    Granica akapitu, gdy:
      * odstęp pionowy jest wyraźnie większy niż typowy na tej stronie,
      * kolejna linia jest WYŻEJ albo daleko w bok (nowa kolumna / blok),
      * zmienia się wielkość czcionki (nagłówek nad akapitem),
      * poprzednia linia kończy zdanie i jest wyraźnie krótsza od pełnej
        szerokości tekstu (akapity bez odstępu, typowe dla Worda),
      * kolejna linia zaczyna punkt listy (myślnik/numer — tylko po końcu
        zdania albo krótkiej linii),
      * poprzednia linia jest pozycją spisu treści (kropki + numer strony).
    Przeniesienia wyrazów skleja `_sklej`.
    """
    if not linie:
        return []
    wys = statistics.median(x.wysokosc for x in linie) or 1.0
    odstepy = [a.dol - b.gora for a, b in zip(linie, linie[1:])
               if b.gora <= a.gora and abs(b.lewo - a.lewo) < wys * 20]
    typowy = statistics.median(odstepy) if odstepy else wys * 0.3
    lewa_krawedz = min(x.lewo for x in linie)
    prawa_strony = max(x.prawo for x in linie)
    szer_strony = max(prawa_strony - lewa_krawedz, 1.0)

    def _krawedz(linia: _Linia) -> tuple[float, float]:
        """(prawa krawędź, szerokość) KOLUMNY tej linii.

        Liczona z linii o zbliżonym lewym brzegu — przy jednej krawędzi dla
        całej strony każda linia lewej kolumny wyglądała na „krótką" i układ
        dwuszpaltowy rozpadał się na akapity po jednym zdaniu (zmierzone).
        """
        tol = max(szer_strony * 0.08, wys * 3)
        kolumna = [x for x in linie if abs(x.lewo - linia.lewo) <= tol]
        prawe = sorted(x.prawo for x in kolumna)
        kraw = prawe[int(len(prawe) * 0.9)] if len(prawe) >= 3 else prawa_strony
        return kraw, max(kraw - min(x.lewo for x in kolumna), 1.0)

    akapity: list[str] = []
    biezacy = linie[0].tekst
    for poprz, nast in zip(linie, linie[1:]):
        odstep = poprz.dol - nast.gora
        konczy = bool(_RE_KONIEC_ZDANIA.search(poprz.tekst))
        kraw, szer = _krawedz(poprz)
        krotka = poprz.prawo < kraw - szer * 0.15
        # Skok do nowej szpalty w środku zdania („…lewej | kolumny") to ciąg
        # dalszy — ta sama reguła co na granicy strony w `wyciagnij`.
        ciag_dalszy = not konczy and nast.tekst[:1].islower()
        granica = (
            (nast.gora > poprz.gora + wys * 0.5 and not ciag_dalszy)
            or (abs(nast.lewo - poprz.lewo) > szer * 0.5 and not ciag_dalszy)
            or odstep > typowy + wys * 0.6
            # Bezwzględnie: przerwa na półtora wiersza to akapit. Na stronie
            # z dwiema liniami „typowy” odstęp to ten jeden, więc reguła
            # względna nigdy nie zadziałała (zmierzone na prawdziwym PDF-ie).
            # Podwójna interlinia to ok. jeden wiersz przerwy — mieści się.
            # Zdanie ciągnące się małą literą przez rozstrzeloną stronę
            # tytułową („…работа, | написанная…”) zostaje w całości.
            or (odstep > wys * 1.5 and not ciag_dalszy)
            # Zmiana wielkości czcionki: nagłówek „ROZDZIAŁ 1" nad akapitem.
            or abs(nast.czcionka - poprz.czcionka) > wys * 0.2
            or (konczy and krotka)
            # Krótka linia bez kropki przed wielką literą: tytuł albo nagłówek
            # w tym samym kroju co tekst. Przecinek i dywiz na końcu = ciąg dalszy.
            or (krotka and not poprz.tekst.endswith((",", "-", "\u00ad"))
                and (nast.tekst[:1].isupper() or nast.tekst[:1].isdigit()))
            or _RE_POZYCJA_SPISU.search(poprz.tekst)
            or _RE_PUNKTOR.match(nast.tekst)
            or ((konczy or krotka) and _RE_PUNKT_SLABY.match(nast.tekst))
        )
        if granica:
            akapity.append(biezacy)
            biezacy = nast.tekst
            continue
        # Brzeg linii przy rozstrzeleniu to granica słowa — chyba że poprzednia
        # linia kończy się przeniesieniem: „уве- | л и ч и в а е т” to jedno
        # słowo i skleja je `_sklej` (dictionary_language-1.pdf, etap 4b).
        przeniesienie = poprz.tekst.endswith(chr(0xAD)) or _RE_PRZENIESIENIE.search(poprz.tekst)
        if (poprz.rozstrzelona_prawa or nast.rozstrzelona_lewa) and not przeniesienie:
            biezacy = biezacy + "  " + nast.tekst
            continue
        biezacy = _sklej(biezacy, nast.tekst, dzielenie_auto)
    akapity.append(biezacy)
    wynik: list[str] = []
    # Miękki dywiz w środku linii nic nie znaczy dla syntezatora — wypada.
    for a in (x.replace("\u00ad", "").strip() for x in akapity):
        if not a:
            continue
        # Sama interpunkcja (osierocony przecinek po biegu kursywy) to koniec
        # poprzedniego akapitu, nie akapit dla syntezatora.
        if wynik and not any(z.isalnum() for z in a):
            wynik[-1] += a
            continue
        wynik.append(a)
    return wynik


def wyciagnij(sciezka: str, znane_litery: frozenset[str] | None = None) -> WynikPdf:
    """Czyta warstwę tekstu PDF i zwraca akapity.

    Args:
        znane_litery: litery wiarygodne mimo flagi błędu mapowania PDFium
            (domyślnie `litery_paczek()` z paczek; testy podają własne).

    Raises:
        BrakWarstwyTekstu: żadna strona nie daje tekstu — skan / obraz, ale też
            PDF, w którym po zdjęciu numerów stron nie zostaje ani jeden akapit
            (audyt 19.13: Poliglota „wczytywała” 0 akapitów, Konwerter
            zapisywał pusty .docx z dialogiem „Sukces”).
        RuntimeError: brak `pypdfium2` w środowisku — głośno, nie ciszą.
        PdfNieDoOtwarcia: plik chroniony hasłem albo uszkodzony
            (GUI zamienia to na przetłumaczony komunikat).
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:                              # pragma: no cover
        raise RuntimeError(
            "Missing the `pypdfium2` package (PDF text layer, since 19.13). "
            "Fix: .venv/Scripts/pip install pypdfium2 (it is listed in "
            "requirements.txt)."
        ) from exc

    try:
        pdf = pdfium.PdfDocument(sciezka)
    except pdfium.PdfiumError as exc:
        # Audyt 19.13: użytkownik dostawał surowe „Failed to load document
        # (PDFium: Incorrect password error)”, a dla PDF-a bez stron wręcz
        # „(PDFium: Success)”. GUI pokazuje przetłumaczony komunikat, techniczny
        # szczegół zostaje w osobnej linii.
        raise PdfNieDoOtwarcia(sciezka, "password" in str(exc).lower(), str(exc)) from exc
    if znane_litery is None:
        znane_litery = litery_paczek()
    # Mapy glifów osadzonych fontów — raz na dokument (19.15, etap 2).
    # `None` = bez naprawy: przy `CIDToGIDMap` jako strumieniu kod znaku nie
    # jest numerem glifu, a PDFium tej mapy nie oddaje (audyt 19.15).
    fonty: dict[tuple, dict[int, str]] | None = None if _mapa_cid_strumieniem(sciezka) else {}
    try:
        strony: list[_Strona] = []
        bez_tekstu: list[int] = []
        for nr in range(len(pdf)):
            strona = pdf[nr]
            try:
                # Pas marginesu z cropboxu w układzie NIEOBRÓCONYM — w tym
                # samym układzie PDFium podaje ramki znaków. `get_height()`
                # zwraca wysokość po obrocie (595 zamiast 842 przy 90°/270°),
                # więc „margines” trafiał w środek strony (audyt 19.13).
                _l, dol, _p, gora = strona.get_cropbox()
                if strona.get_rotation() in (90, 270):
                    linie, litery, podejrzane, znaki, naprawiona = (
                        _czytaj_strone_bez_geometrii(strona, znane_litery, fonty))
                    s = _Strona(linie, dol, gora, False, litery, podejrzane, znaki, naprawiona)
                else:
                    linie, litery, podejrzane, znaki, naprawiona = _czytaj_strone(
                        strona, znane_litery, fonty)
                    s = _Strona(linie, dol, gora, True, litery, podejrzane, znaki, naprawiona)
            finally:
                strona.close()
            strony.append(s)
            if not s.linie:
                bez_tekstu.append(nr + 1)
        liczba = len(pdf)
    finally:
        pdf.close()

    if liczba == 0 or len(bez_tekstu) == liczba:
        raise BrakWarstwyTekstu(sciezka, liczba, bez_tekstu)

    znieksztalcone = [nr for nr, s in enumerate(strony, start=1) if s.znieksztalcona]
    naprawione = [nr for nr, s in enumerate(strony, start=1)
                  if s.naprawiona and not s.znieksztalcona]
    dzielenie_auto = any("\u00ad" in l.tekst for s in strony for l in s.linie)
    oczyszczone, kolontytuly = _usun_kolontytuly(strony)
    akapity_stron: list[list[str]] = []
    # Strona, do której należy ostatni akapit, i czy od niej minął skan.
    ostatnia: list[str] | None = None
    skan_po_drodze = False
    for nr, linie in enumerate(oczyszczone):
        nowe = _podziel_na_akapity(linie, dzielenie_auto)
        # Akapit przerwany granicą strony: poprzedni nie kończy zdania, a nowy
        # zaczyna się małą literą — to jedno zdanie, nie dwa akapity. NIE przez
        # stronę bez tekstu: jej treść (skan) leży między nimi, więc sklejenie
        # tworzyłoby zdanie, którego w dokumencie nie ma, a odczytany skan
        # nie miałby gdzie wejść. Strona zniekształcona tak samo (19.15): jej
        # akapity zastąpi odczyt obrazu, więc nie mogą wchłonąć sąsiada.
        zla = nr + 1 in znieksztalcone
        if ostatnia and nowe and not skan_po_drodze and not zla \
                and not _RE_KONIEC_ZDANIA.search(ostatnia[-1]) \
                and nowe[0][:1].islower():
            ostatnia[-1] = _sklej(ostatnia[-1], nowe.pop(0), dzielenie_auto)
        akapity_stron.append(nowe)
        if nr + 1 in bez_tekstu or zla:
            skan_po_drodze = True
        elif nowe:
            ostatnia, skan_po_drodze = nowe, False
    # Mojibake (19.15): strona w złej stronie kodowej, ocena na całej stronie.
    akapity_stron, przekodowane = _napraw_mojibake_stron(akapity_stron)
    if len(set(przekodowane.values())) == 1:
        # Kolontytuły idą do komunikatu dla słuchacza — tą samą parą kodowań.
        import czyszczenie_tekstu
        zrodlo, cel = next(iter(przekodowane.values())).split(">")
        kolontytuly = [czyszczenie_tekstu.przekoduj(k, zrodlo, cel) for k in kolontytuly]
    # Tekst rozstrzelony (19.15): granice słów z geometrii, sklejenie wg
    # słownika dokumentu — ta sama reguła co w `.docx`.
    plaskie, rozstrzelone = _scal_rozstrzelone_pdf(
        [a for strona in akapity_stron for a in strona])
    it = iter(plaskie)
    akapity_stron = [[next(it) for _ in strona] for strona in akapity_stron]
    kolontytuly = [k.replace(_GRANICA, " ") for k in kolontytuly]
    akapity = [a for strona in akapity_stron for a in strona]
    if not akapity:
        raise BrakWarstwyTekstu(sciezka, liczba, bez_tekstu)
    return WynikPdf(akapity, liczba, bez_tekstu, kolontytuly, akapity_stron,
                    znieksztalcone, [s.znaki for s in strony], naprawione,
                    sorted(przekodowane), sorted(set(przekodowane.values())))
