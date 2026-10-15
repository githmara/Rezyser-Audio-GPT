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
cyfr) w tym samym pasie wysokości, w górnym lub dolnym marginesie, na co
najmniej ćwierci stron. ATA chroni nagłówki scen listą słów w sześciu językach;
tu ochrona wynika z geometrii — „SCENA 2" w środku strony nie jest w marginesie,
a lista słów w Pythonie byłaby wzorcem §6.7b (języki wypisane ręcznie w kodzie).
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field


class BrakWarstwyTekstu(Exception):
    """PDF bez warstwy tekstu (skan / obraz). Reżyser nie ma OCR — GUI mówi to wprost."""


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
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
    "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
    # Dywiz automatycznego dzielenia wyrazów (Word) PDFium oddaje jako
    # U+FFFE (pypdfium2 5.14, zmierzone); \x02 to wariant opisywany dla
    # innych buildów PDFium, niezweryfikowany — mapowany na wszelki wypadek. Bez tej
    # zamiany wypadał razem ze sterującymi i w środku słowa zostawała spacja:
    # „wier sza".
    "￾": "­", "\x02": "­",
})
# Znaki sterujące poza \n i \t (PDFium potrafi oddać \x00 itp.).
_RE_STERUJACE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f￿]")
# Przeniesienie: litera + dywiz (zwykły, miękki, U+2010) na KOŃCU linii.
_RE_PRZENIESIENIE = re.compile(r"(\w)[-­‐]$")
_RE_KONIEC_ZDANIA = re.compile(r"[.!?…:;»”\"')\]]$")
# Punktor graficzny zaczyna punkt listy zawsze; myślnik i numer — tylko po
# zakończonym zdaniu albo krótkiej linii, bo „– Zagadnienia…" w środku zdania
# (zmierzone na wstępie kwartalnika) i „2026 r." to zwykła kontynuacja.
_RE_PUNKTOR = re.compile(r"^[•●▪◦‣∙·*]\s")
_RE_PUNKT_SLABY = re.compile(r"^(?:[–—-]\s|\(?\d{1,3}[.)]\s|[a-zA-Z][.)]\s)")
# Pozycja spisu treści: kropki prowadzące + numer strony na końcu linii.
_RE_POZYCJA_SPISU = re.compile(r"(?:\.\s?){4,}\s*\d{1,4}$")
_RE_NUMER_STRONY = re.compile(
    r"^[-–—\s]*(?:\d{1,4}|[ivxlcdmIVXLCDM]{1,6})(?:\s*(?:/|z|of|из|af)\s*\d{1,4})?[-–—\s]*$")
_RE_TAG_NAWIASOWY = re.compile(r"^\s*(?:\[[^\]]+\]|\([^)]+\))\s*$")

_RE_BIALE = re.compile(r"[ \t]+")
_DOKLEJANE = frozenset(",.;:!?)]»”…")

#: Pas marginesu (ułamek wysokości strony od góry i od dołu), w którym szukamy
#: kolontytułów i numerów stron.
PAS_MARGINESU = 0.12
#: Minimalny ułamek stron z tym samym kolontytułem (jak `min_fraction` w ATA).
UDZIAL_STRON = 0.25


def _czysc(tekst: str) -> str:
    return _RE_STERUJACE.sub("", tekst.translate(_LIGATURY).replace("\r", ""))


def _linie_strony(strona) -> list[_Linia]:
    """Linie WIZUALNE strony w kolejności strumienia treści.

    Tekst bierzemy JEDNYM `get_text_range()` (indeksy tekstu i znaków są 1:1,
    zmierzone na 93 stronach), a linie budujemy z ramki KAŻDEGO znaku
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
    („…как | , словообразование") zostaje w tej samej linii.
    """
    tp = strona.get_textpage()
    try:
        pelny = tp.get_text_range()
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

        for i, z in enumerate(pelny):
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
                cofniecie = l < prawo - wys
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


def _klucz_kolontytulu(tekst: str) -> str:
    """Tekst do porównania między stronami: bez cyfr na brzegach, małe litery."""
    s = re.sub(r"^\s*\d+\s*", "", tekst)
    s = re.sub(r"\s*\d+\s*$", "", s)
    return re.sub(r"\s+", " ", s).lower().strip()


def _w_marginesie(linia: _Linia, wys_strony: float) -> bool:
    pas = wys_strony * PAS_MARGINESU
    return linia.gora >= wys_strony - pas or linia.dol <= pas


def _usun_kolontytuly(strony: list[tuple[list[_Linia], float]]) -> tuple[list[list[_Linia]], list[str]]:
    """Usuwa kolontytuły (pozycja + powtórzenie) i gołe numery stron z marginesu.

    Kolontytuł = ten sam klucz tekstu w tym samym pasie wysokości (±3 pt,
    zaokrąglenie do 6 pt) na co najmniej `UDZIAL_STRON` stron, ale nie mniej
    niż 2. Linie-tagi `[...]`/`(...)` są chronione zawsze — to składnia
    Reżysera i didaskalia, nie stopka.
    """
    prog = max(2, int(len(strony) * UDZIAL_STRON))
    licznik: Counter = Counter()
    # Pierwsze wystąpienie W ORYGINALE — do komunikatu. Klucz porównania
    # (małe litery, bez cyfr na brzegach) czytany na głos brzmiał jak błąd:
    # „kwartalnik testowy – nr 3/".
    oryginal: dict[str, str] = {}
    for linie, wys in strony:
        widziane = set()
        for linia in linie:
            if not _w_marginesie(linia, wys) or _RE_TAG_NAWIASOWY.match(linia.tekst):
                continue
            klucz = (_klucz_kolontytulu(linia.tekst), round(linia.dol / 6))
            if len(klucz[0]) >= 3 and klucz not in widziane:
                licznik[klucz] += 1
                widziane.add(klucz)
                oryginal.setdefault(klucz[0], linia.tekst)
    kolontytuly = {k for k, n in licznik.items() if n >= prog}
    # Pas ±1 kroku zaokrąglenia — ta sama stopka bywa przesunięta o ułamek punktu.
    rozmyte = {(t, y + dy) for t, y in kolontytuly for dy in (-1, 0, 1)}

    wynik: list[list[_Linia]] = []
    for linie, wys in strony:
        zostaja = []
        for linia in linie:
            if _w_marginesie(linia, wys) and not _RE_TAG_NAWIASOWY.match(linia.tekst):
                if (_klucz_kolontytulu(linia.tekst), round(linia.dol / 6)) in rozmyte:
                    continue
                if _RE_NUMER_STRONY.match(linia.tekst):
                    continue
            zostaja.append(linia)
        wynik.append(zostaja)
    return wynik, sorted({oryginal[t] for t, _ in kolontytuly})


def _sklej(lewy: str, prawy: str) -> str:
    """Łączy dwie linie akapitu, zdejmując przeniesienie wyrazu.

    Miękki dywiz (z dzielenia automatycznego) skleja zawsze. Zwykły dywiz —
    tylko przed małą literą, bo „Jean-|Paul" i „PKO-|BP" to łączniki.
    """
    if lewy.endswith("­"):
        return lewy[:-1] + prawy
    if _RE_PRZENIESIENIE.search(lewy) and prawy[:1].islower():
        return lewy[:-1] + prawy
    return lewy + " " + prawy


def _podziel_na_akapity(linie: list[_Linia]) -> list[str]:
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
    Przeniesienie wyrazu („przy-\\nkład") skleja się bez dywizu tylko wtedy,
    gdy następna linia zaczyna się małą literą — „Jean-\\nPaul" zostaje.
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
            # Zmiana wielkości czcionki: nagłówek „ROZDZIAŁ 1" nad akapitem.
            or abs(nast.czcionka - poprz.czcionka) > wys * 0.2
            or (konczy and krotka)
            # Krótka linia bez kropki przed wielką literą: tytuł albo nagłówek
            # w tym samym kroju co tekst. Przecinek i dywiz na końcu = ciąg dalszy.
            or (krotka and not poprz.tekst.endswith((",", "-", "­"))
                and (nast.tekst[:1].isupper() or nast.tekst[:1].isdigit()))
            or _RE_POZYCJA_SPISU.search(poprz.tekst)
            or _RE_PUNKTOR.match(nast.tekst)
            or ((konczy or krotka) and _RE_PUNKT_SLABY.match(nast.tekst))
        )
        if granica:
            akapity.append(biezacy)
            biezacy = nast.tekst
            continue
        biezacy = _sklej(biezacy, nast.tekst)
    akapity.append(biezacy)
    wynik: list[str] = []
    # Miękki dywiz w środku linii nic nie znaczy dla syntezatora — wypada.
    for a in (x.replace("­", "").strip() for x in akapity):
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
        BrakWarstwyTekstu: żadna strona nie ma tekstu (skan / obraz).
        RuntimeError: brak `pypdfium2` w środowisku — głośno, nie ciszą.
        pypdfium2.PdfiumError: plik uszkodzony albo zaszyfrowany hasłem
            (GUI pokazuje treść błędu w ogólnym dialogu odczytu).
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:                              # pragma: no cover
        raise RuntimeError(
            "Missing the `pypdfium2` package (PDF text layer, since 19.13). "
            "Fix: .venv/Scripts/pip install pypdfium2 (it is listed in "
            "requirements.txt)."
        ) from exc

    pdf = pdfium.PdfDocument(sciezka)
    try:
        strony: list[tuple[list[_Linia], float]] = []
        bez_tekstu: list[int] = []
        for nr in range(len(pdf)):
            strona = pdf[nr]
            try:
                linie = _linie_strony(strona)
                strony.append((linie, strona.get_height()))
            finally:
                strona.close()
            if not linie:
                bez_tekstu.append(nr + 1)
        liczba = len(pdf)
    finally:
        pdf.close()

    if liczba == 0 or len(bez_tekstu) == liczba:
        raise BrakWarstwyTekstu(sciezka)

    oczyszczone, kolontytuly = _usun_kolontytuly(strony)
    akapity: list[str] = []
    for linie in oczyszczone:
        nowe = _podziel_na_akapity(linie)
        # Akapit przerwany granicą strony: poprzedni nie kończy zdania, a nowy
        # zaczyna się małą literą — to jedno zdanie, nie dwa akapity.
        if akapity and nowe and not _RE_KONIEC_ZDANIA.search(akapity[-1]) \
                and nowe[0][:1].islower():
            akapity[-1] = _sklej(akapity[-1], nowe.pop(0))
        akapity.extend(nowe)
    return WynikPdf(akapity, liczba, bez_tekstu, kolontytuly)
