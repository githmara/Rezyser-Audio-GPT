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
w górnym lub dolnym marginesie, na co najmniej ćwierci stron. ATA chroni nagłówki scen listą słów w sześciu językach;
tu ochrona wynika z geometrii — „SCENA 2" w środku strony nie jest w marginesie,
a lista słów w Pythonie byłaby wzorcem §6.7b (języki wypisane ręcznie w kodzie).
"""

from __future__ import annotations

import math
import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass, field


class BrakWarstwyTekstu(Exception):
    """PDF bez warstwy tekstu (skan / obraz). Reżyser nie ma OCR — GUI mówi to wprost."""


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

    @property
    def tekst(self) -> str:
        """Akapity rozdzielone PUSTĄ LINIĄ — granica akapitu ścieżki `.txt`."""
        return "\n\n".join(self.akapity)


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
#: Ułamek wystąpień rdzenia, którego numer musi rosnąć razem ze stroną.
ZGODNOSC_NUMERU = 0.8

_RZYMSKIE = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


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


def _linie_strony(strona) -> list[_Linia]:
    """Linie WIZUALNE strony w kolejności strumienia treści.

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
            tekst = _RE_BIALE.sub(" ", _czysc("".join(znaki))).strip()
            if tekst:
                linie.append(_Linia(tekst, *ramka,
                                    czcionka=statistics.median(wysokosci)))
            znaki.clear()
            ramka.clear()
            wysokosci.clear()

        for i, z in _znaki_strony(tp):
            if z.isspace():
                if znaki and znaki[-1] != " ":
                    znaki.append(" ")
                continue
            l, d, p, g = tp.get_charbox(i, loose=True)
            if ramka:
                lewo, dol, prawo, gora = ramka
                wys = max(gora - dol, g - d, 1.0)
                # Ta sama linia = pionowe POKRYCIE co najmniej połowy niższej
                # ramki. Kryterium środka rozcinało linię na odnośniku przypisu
                # w indeksie górnym („…Шанский и А¹ | . Однако…").
                pokrycie = min(gora, g) - max(dol, d)
                inna_wysokosc = pokrycie < min(gora - dol, g - d, wys) * 0.5
                rtl = unicodedata.bidirectional(z) in ("R", "AL")
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
            znaki.append(z)
            wysokosci.append(g - d)
        zamknij()
        return linie
    finally:
        tp.close()


def _linie_bez_geometrii(strona) -> list[_Linia]:
    """Strona obrócona o 90°/270°: linie z kolejności tekstu, bez geometrii.

    Ramki znaków PDFium są w układzie NIEOBRÓCONYM, więc na takiej stronie
    „pionowe pokrycie” i „cofnięcie” mierzą niewłaściwą oś (audyt 19.13:
    kolejność linii odwrócona przy 90°). Linie bierzemy z łamań PDFium i
    nadajemy im współrzędne środka strony — akapity dzielą wtedy wyłącznie
    reguły tekstowe, a kolontytuły i numery stron nie są tu usuwane.
    """
    tp = strona.get_textpage()
    try:
        tekst = "".join(z for _, z in _znaki_strony(tp))
    finally:
        tp.close()
    linie = []
    for nr, kawalek in enumerate(re.split(r"\r\n|\n|\r", tekst)):
        czysty = _RE_BIALE.sub(" ", _czysc(kawalek)).strip()
        if czysty:
            linie.append(_Linia(czysty, 0.0, -12.0 * nr, 1000.0, -12.0 * nr + 10, czcionka=10.0))
    return linie


@dataclass
class _Strona:
    linie: list[_Linia]
    dol: float
    gora: float
    #: False dla stron obróconych o 90°/270° — margines nie jest wtedy znany.
    geometria: bool = True

    def w_marginesie(self, linia: _Linia) -> bool:
        if not self.geometria:
            return False
        pas = (self.gora - self.dol) * PAS_MARGINESU
        return linia.gora >= self.gora - pas or linia.dol <= self.dol + pas


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
            if not strona.w_marginesie(linia):
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
    naglowki = {k for k, c in dokladne.items() if c >= prog}
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


def wyciagnij(sciezka: str) -> WynikPdf:
    """Czyta warstwę tekstu PDF i zwraca akapity.

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
                    s = _Strona(_linie_bez_geometrii(strona), dol, gora, geometria=False)
                else:
                    s = _Strona(_linie_strony(strona), dol, gora)
            finally:
                strona.close()
            strony.append(s)
            if not s.linie:
                bez_tekstu.append(nr + 1)
        liczba = len(pdf)
    finally:
        pdf.close()

    if liczba == 0 or len(bez_tekstu) == liczba:
        raise BrakWarstwyTekstu(sciezka)

    dzielenie_auto = any("\u00ad" in l.tekst for s in strony for l in s.linie)
    oczyszczone, kolontytuly = _usun_kolontytuly(strony)
    akapity: list[str] = []
    for linie in oczyszczone:
        nowe = _podziel_na_akapity(linie, dzielenie_auto)
        # Akapit przerwany granicą strony: poprzedni nie kończy zdania, a nowy
        # zaczyna się małą literą — to jedno zdanie, nie dwa akapity.
        if akapity and nowe and not _RE_KONIEC_ZDANIA.search(akapity[-1]) \
                and nowe[0][:1].islower():
            akapity[-1] = _sklej(akapity[-1], nowe.pop(0), dzielenie_auto)
        akapity.extend(nowe)
    if not akapity:
        raise BrakWarstwyTekstu(sciezka)
    return WynikPdf(akapity, liczba, bez_tekstu, kolontytuly)
