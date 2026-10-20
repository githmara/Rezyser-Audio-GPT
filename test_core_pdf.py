"""
test_core_pdf.py — kontrakty ekstrakcji warstwy tekstu PDF (19.13).

Każdy przypadek poniżej to defekt ZMIERZONY przy budowie `core_pdf` na PDF-ach
z maszyny maintainera (91-stronicowa praca, wstęp kwartalnika, PDF z Worda
z dzieleniem wyrazów, kolontytułem, numerami stron i dwiema szpaltami):

  A. Linie wizualne z ramek ZNAKÓW: przypis w indeksie górnym nie rozcina
     linii, `\\r\\n` PDFium jest tylko odstępem, zawinięcie (cofnięcie w lewo)
     zaczyna nową linię, dywiz dzielenia (U+FFFE) przeżywa czyszczenie.
  B. Akapity z geometrii: nagłówek po zmianie czcionki, akapit Worda bez
     odstępu, myślnik w środku zdania to ciąg dalszy, dialog to nowy akapit,
     pogrubione hasło słownikowe NIE jest nagłówkiem, skok szpalty w środku
     zdania to ciąg dalszy, przeniesienia sklejane tylko tam, gdzie trzeba.
  C. Kolontytuły po POZYCJI: ta sama linia w tym samym pasie marginesu na
     ćwierci stron znika, „SCENA 2" w środku strony i tag `[scena 1]`
     w marginesie zostają, goły numer strony w marginesie znika.
  D. PDF bez warstwy tekstu podnosi `BrakWarstwyTekstu` (GUI mówi „skan,
     brak OCR"), zamiast oddać pusty dokument. Od 19.14 akapity są też per
     strona (`akapity_stron`), żeby odczytany skan wszedł na swoje miejsce,
     a zdanie nie skleja się przez stronę-skan.
  F. (19.15) Zniekształcona warstwa tekstu: flaga błędu mapowania PDFium
     i litera spoza paczek RAZEM; prawdziwy PDF z uciętą mapą ToUnicode
     odtwarza słownik z macOS Quartz, a lingua dostaje tylko strony dobre.
  G. (19.15, etap 2) Naprawa z osadzonego fontu zbudowanego w teście:
     `cmap` + `post`, akcent przy literze, naprawa częściowa zgłaszana,
     font nieosadzony i bez map nienaprawiany.

Uruchom:  .venv/Scripts/python -m pytest test_core_pdf.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_core_pdf.py
"""

import sys

import pytest

import core_pdf
from core_pdf import _Linia

WYS_STRONY = 842.0


def L(tekst, lewo, dol, prawo, wys=12.0, czcionka=None):
    return _Linia(tekst, lewo, dol, prawo, dol + wys,
                  czcionka=wys if czcionka is None else czcionka)


def kolumna(*wiersze, lewo=90.0, gora=700.0, krok=16.0, pelna=500.0):
    """Linie jednej szpalty: (tekst, czy_pelna_szerokosc)."""
    out = []
    for i, (tekst, pelny) in enumerate(wiersze):
        out.append(L(tekst, lewo, gora - i * krok, pelna if pelny else lewo + 150))
    return out


# --------------------------------------------------------------------- A ---

class _AtrapaTp:
    def __init__(self, tekst, ramki):
        self.tekst, self.ramki = tekst, ramki

    def count_chars(self):
        return len(self.tekst)

    def get_text_range(self):
        return self.tekst

    def get_charbox(self, i, loose=False):
        return self.ramki[i]

    def close(self):
        pass


class _AtrapaStrony:
    def __init__(self, tekst, ramki):
        self.tp = _AtrapaTp(tekst, ramki)

    def get_textpage(self):
        return self.tp


def _strona(*biegi):
    """biegi: (tekst, lewo, dol, wysokosc) — znaki po 5 pt szerokości."""
    tekst, ramki = "", []
    for kawalek, lewo, dol, wys in biegi:
        for j, z in enumerate(kawalek):
            tekst += z
            ramki.append((lewo + 5 * j, dol, lewo + 5 * j + 5, dol + wys))
    return _AtrapaStrony(tekst, ramki)


def test_przypis_w_indeksie_gornym_nie_rozcina_linii():
    # Zmierzone: „словопроизводство⁷\r\n. Однако" — PDFium łamie po odnośniku.
    strona = _strona(("abc", 90, 500, 11), ("7", 105, 505.5, 7.3),
                     ("\r\n", 110, 507, 0), (". Dalej", 110, 500, 11))
    linie = core_pdf._linie_strony(strona)
    assert [x.tekst for x in linie] == ["abc7. Dalej"]


def test_zawiniecie_akapitu_bez_crlf_daje_osobne_linie():
    # Zmierzone: PDF z Worda — PDFium NIE wstawia \r\n między wierszami akapitu.
    strona = _strona(("pierwszy wiersz ", 90, 600, 12), ("drugi wiersz", 90, 584, 12))
    assert [x.tekst for x in core_pdf._linie_strony(strona)] == [
        "pierwszy wiersz", "drugi wiersz"]


def test_dywiz_dzielenia_ufffe_skleja_wyraz():
    strona = _strona(("granicy wier\ufffe", 90, 600, 12), ("sza. Koniec", 90, 584, 12))
    linie = core_pdf._linie_strony(strona)
    assert core_pdf._podziel_na_akapity(linie) == ["granicy wiersza. Koniec"]


def test_czcionka_linii_to_mediana_znakow_nie_ramka():
    # Pogrubione hasło (wyższa ramka) na początku zwykłego wiersza.
    strona = _strona(("HASLO", 90, 600, 13.4), (", a, m. opis", 115, 600, 11))
    (linia,) = core_pdf._linie_strony(strona)
    assert linia.czcionka == 11
    assert linia.wysokosc == pytest.approx(13.4)


# --------------------------------------------------------------------- B ---

def test_nagłowek_po_zmianie_czcionki():
    linie = [L("ROZDZIAŁ 1", 90, 720, 160, wys=16)] + kolumna(
        ("Tekst akapitu, który ciągnie", True), ("się dalej i kończy.", False))
    assert core_pdf._podziel_na_akapity(linie) == [
        "ROZDZIAŁ 1", "Tekst akapitu, który ciągnie się dalej i kończy."]


def test_nagłowek_w_tym_samym_kroju():
    linie = kolumna(("ROZDZIAŁ 1", False), ("Niniejszy akapit jest długi", True),
                    ("i się kończy.", False))
    assert core_pdf._podziel_na_akapity(linie)[0] == "ROZDZIAŁ 1"


def test_akapity_worda_bez_odstepu():
    linie = kolumna(("Pierwszy akapit ma kilka", True), ("słów i koniec.", False),
                    ("Drugi akapit też.", False))
    assert core_pdf._podziel_na_akapity(linie) == [
        "Pierwszy akapit ma kilka słów i koniec.", "Drugi akapit też."]


def test_myslnik_w_srodku_zdania_to_ciag_dalszy():
    # Zmierzone: „kwartalnika „Niepełnosprawność | – Zagadnienia, Problemy…"
    linie = kolumna(("numer kwartalnika „Niepełnosprawność", True),
                    ("– Zagadnienia, Problemy”. Koniec.", False))
    assert core_pdf._podziel_na_akapity(linie) == [
        "numer kwartalnika „Niepełnosprawność – Zagadnienia, Problemy”. Koniec."]


def test_dialog_od_myslnika_to_nowe_akapity():
    linie = kolumna(("Krótko.", False), ("– Dzień dobry – powiedziała Anna.", False),
                    ("– Czy to już koniec? – zapytał.", False))
    assert core_pdf._podziel_na_akapity(linie) == [
        "Krótko.", "– Dzień dobry – powiedziała Anna.", "– Czy to już koniec? – zapytał."]


def test_lista_numerowana_po_dwukropku_a_rok_w_srodku_zdania():
    linie = kolumna(("Trzy zasady obowiązują wszystkich czytelników:", True),
                    ("1. Nie mogę Ci obiecać szybkich decyzji.", False),
                    ("2. Lubię, gdy pytasz mnie o zdanie, a w roku", True),
                    ("2026 r. będzie inaczej.", False))
    assert core_pdf._podziel_na_akapity(linie) == [
        "Trzy zasady obowiązują wszystkich czytelników:",
        "1. Nie mogę Ci obiecać szybkich decyzji.",
        "2. Lubię, gdy pytasz mnie o zdanie, a w roku 2026 r. będzie inaczej."]


def test_skok_szpalty_w_srodku_zdania_to_ciag_dalszy():
    lewa = kolumna(("Tekst lewej szpalty, który", True), ("ciągnie się i", True))
    prawa = kolumna(("przechodzi do prawej.", False), lewo=320, gora=700)
    assert core_pdf._podziel_na_akapity(lewa + prawa) == [
        "Tekst lewej szpalty, który ciągnie się i przechodzi do prawej."]


MIEKKI = chr(0xAD)


@pytest.mark.parametrize("lewy,prawy,auto,wynik", [
    ("przy" + MIEKKI, "Kład", False, "przyKład"),   # miękki dywiz skleja zawsze
    ("przy-", "kład", False, "przykład"),            # bez dzielenia auto: przeniesienie
    ("Jean-", "Paul", False, "Jean-Paul"),           # łącznik przed wielką, bez spacji
    ("biało-", "czerwona", True, "biało-czerwona"),  # Word: zwykły dywiz jest prawdziwy
    ("e-", "mail", True, "e-mail"),
])
def test_sklejanie_przeniesien(lewy, prawy, auto, wynik):
    assert core_pdf._sklej(lewy, prawy, auto) == wynik


def test_pozycja_spisu_tresci_konczy_akapit():
    linie = kolumna(("1.1. Pojęcie ............ 10", True), ("1.2. Sposoby ............ 12", True))
    assert len(core_pdf._podziel_na_akapity(linie)) == 2


# --------------------------------------------------------------------- C ---

def S(*linie):
    return core_pdf._Strona(list(linie), 0.0, WYS_STRONY)


def _strony_z_kolontytulem(n=4):
    return [S(
        L("Kwartalnik Testowy", 90, 815, 300),        # górny margines (7% = 59 pt)
        L("[scena 1]", 90, 800, 160),                 # tag w marginesie
        L("SCENA 2", 90, 400, 160),                   # środek strony
        L(f"Treść strony {nr}.", 90, 380, 300),
        L(str(nr), 290, 25, 300),                     # numer strony = indeks + 1
    ) for nr in range(1, n + 1)]


def test_kolontytul_i_numery_stron_znikaja_tresc_zostaje():
    wynik, kolontytuly = core_pdf._usun_kolontytuly(_strony_z_kolontytulem())
    assert [x.tekst for x in wynik[0]] == ["[scena 1]", "SCENA 2", "Treść strony 1."]
    assert kolontytuly == ["Kwartalnik Testowy"]


def test_rozdzial_w_marginesie_nie_jest_kolontytulem():
    # Audyt 19.13: „Rozdział N” traciło numer w kluczu i znikało ze wszystkich
    # stron. Numer, który NIE rośnie razem ze stroną, to treść.
    numery = [1, 1, 2, 2, 3, 3]
    strony = [S(L(f"Rozdział {n}", 90, 815, 200), L("Proza.", 90, 400, 300)) for n in numery]
    wynik, kolontytuly = core_pdf._usun_kolontytuly(strony)
    assert kolontytuly == []
    assert [s[0].tekst for s in wynik] == [f"Rozdział {n}" for n in numery]


def test_kolontytul_numerowany_rosnacy_ze_strona_znika():
    strony = [S(L(f"Historia Polski {i + 11}", 90, 815, 300), L("Proza.", 90, 400, 300))
              for i in range(5)]
    wynik, kolontytuly = core_pdf._usun_kolontytuly(strony)
    assert all([x.tekst for x in s] == ["Proza."] for s in wynik)
    assert kolontytuly == ["Historia Polski 11"]


@pytest.mark.parametrize("slowo", ["II", "MIX", "did", "2026", "Ill"])
def test_pojedyncze_slowo_w_marginesie_zostaje(slowo):
    # Audyt 19.13: kształt numeru wystarczał do usunięcia — „II” (rzymski
    # nagłówek), „MIX”, „did” znikały z jednej strony bez żadnego powtórzenia.
    strony = [S(L(slowo, 90, 815, 120), L("Proza.", 90, 400, 300)),
              S(L("Proza dalej.", 90, 400, 300)), S(L("Koniec.", 90, 400, 300))]
    wynik, _ = core_pdf._usun_kolontytuly(strony)
    assert wynik[0][0].tekst == slowo


def test_rzymska_numeracja_wstepu_znika():
    strony = [S(L(r, 290, 25, 300), L("Proza.", 90, 400, 300))
              for r in ("i", "ii", "iii", "iv")]
    wynik, _ = core_pdf._usun_kolontytuly(strony)
    assert all([x.tekst for x in s] == ["Proza."] for s in wynik)


def test_rzymska_niekanoniczna_to_nie_liczba():
    assert core_pdf._rzymska("XIV") == 14
    assert core_pdf._rzymska("IIII") is None and core_pdf._rzymska("did") is None


def test_ta_sama_linia_na_innej_wysokosci_to_nie_kolontytul():
    # Refren w środku stron — powtarza się, ale nie w marginesie.
    strony = [S(L("Hej, sokoły, omijajcie", 90, 300 + 40 * i, 400)) for i in range(4)]
    wynik, kolontytuly = core_pdf._usun_kolontytuly(strony)
    assert kolontytuly == [] and all(len(s) == 1 for s in wynik)


def test_dwie_strony_z_ta_sama_pierwsza_linia_zostaja():
    # Audyt 19.13: przy progu 2 dwie strony traciły wspólną pierwszą linię prozy.
    strony = [S(L("kropka, żeby silnik miał co sklejać", 90, 815, 400), L("Proza.", 90, 400, 300))
              for _ in range(2)]
    wynik, kolontytuly = core_pdf._usun_kolontytuly(strony)
    assert kolontytuly == [] and all(len(s) == 2 for s in wynik)


# --------------------------------------------------------------------- D ---

class _AtrapaPdf:
    def __init__(self, strony):
        self.strony = strony

    def __len__(self):
        return len(self.strony)

    def __getitem__(self, i):
        strona = self.strony[i]
        strona.get_cropbox = lambda: (0.0, 0.0, 595.0, WYS_STRONY)
        strona.get_rotation = lambda: 0
        strona.close = lambda: None
        return strona

    def close(self):
        pass


def test_pdf_bez_warstwy_tekstu_to_blad_nie_pusty_dokument(monkeypatch):
    import pypdfium2
    puste = [_strona(), _strona()]
    monkeypatch.setattr(pypdfium2, "PdfDocument", lambda _p: _AtrapaPdf(puste))
    with pytest.raises(core_pdf.BrakWarstwyTekstu):
        core_pdf.wyciagnij("skan.pdf")


def test_strony_bez_tekstu_sa_raportowane(monkeypatch):
    import pypdfium2
    strony = [_strona(("Tekst.", 90, 400, 12)), _strona()]
    monkeypatch.setattr(pypdfium2, "PdfDocument", lambda _p: _AtrapaPdf(strony))
    wynik = core_pdf.wyciagnij("mieszany.pdf")
    assert wynik.akapity == ["Tekst."]
    assert wynik.strony_bez_tekstu == [2]
    assert wynik.tekst == "Tekst."
    assert wynik.akapity_stron == [["Tekst."], []]


def test_pdf_bez_warstwy_tekstu_niesie_strony_do_odczytu(monkeypatch):
    # 19.14: całkowicie zeskanowany PDF dostaje tę samą ofertę odczytu
    # modelem z obrazem co mieszany — GUI potrzebuje numerów stron.
    import pypdfium2
    puste = [_strona(), _strona(), _strona()]
    monkeypatch.setattr(pypdfium2, "PdfDocument", lambda _p: _AtrapaPdf(puste))
    with pytest.raises(core_pdf.BrakWarstwyTekstu) as exc:
        core_pdf.wyciagnij("skan.pdf")
    assert exc.value.liczba_stron == 3
    assert exc.value.strony_bez_tekstu == [1, 2, 3]
    assert str(exc.value) == "skan.pdf"


def _zdanie_przez_strone(srodek):
    """Strona 1 kończy się w pół zdania, strona 3 zaczyna małą literą."""
    return [_strona(("Zdanie urwane na", 90, 400, 12)), srodek,
            _strona(("dalszy ciąg.", 90, 700, 12))]


def test_akapit_przez_granice_strony_nalezy_do_strony_poczatku(monkeypatch):
    import pypdfium2
    strony = [_strona(("Zdanie urwane na", 90, 400, 12)),
              _strona(("granicy strony.", 90, 700, 12), ("Nowy akapit.", 90, 600, 12))]
    monkeypatch.setattr(pypdfium2, "PdfDocument", lambda _p: _AtrapaPdf(strony))
    w = core_pdf.wyciagnij("doc.pdf")
    assert w.akapity_stron == [["Zdanie urwane na granicy strony."], ["Nowy akapit."]]
    assert w.akapity == [a for s in w.akapity_stron for a in s]


def test_skan_miedzy_stronami_blokuje_sklejanie(monkeypatch):
    # Treść skanu leży MIĘDZY urwanym zdaniem a małą literą — sklejenie
    # stworzyłoby zdanie, którego w dokumencie nie ma.
    import pypdfium2
    monkeypatch.setattr(pypdfium2, "PdfDocument",
                        lambda _p: _AtrapaPdf(_zdanie_przez_strone(_strona())))
    w = core_pdf.wyciagnij("mieszany.pdf")
    assert w.strony_bez_tekstu == [2]
    assert w.akapity_stron == [["Zdanie urwane na"], [], ["dalszy ciąg."]]


def test_strona_z_samym_numerem_nie_blokuje_sklejania(tmp_path):
    # Pusta PO czyszczeniu (sam numer strony) to nie skan: warstwa tekstu
    # jest, zdanie przez nią przechodzi.
    p = tmp_path / "numer.pdf"
    _zbuduj_pdf(p, [[("Zdanie urwane na", 72, 400), ("1", 290, 25)],
                    [("2", 290, 25)],
                    [("dalszy ciag.", 72, 700), ("3", 290, 25)]])
    w = core_pdf.wyciagnij(str(p))
    assert w.strony_bez_tekstu == []
    assert w.akapity_stron == [["Zdanie urwane na dalszy ciag."], [], []]


def test_glif_bez_unicode_nie_przesuwa_ramek(monkeypatch):
    # Audyt 19.13: znak bez Unicode (0) wypada z get_text_range(), więc indeksy
    # tekstu i ramek się rozjeżdżały. Ścieżka znak po znaku go pomija.
    import pypdfium2.raw as pdfium_c
    kody = [ord("a"), 0, ord("b"), 0xD83D, 0xDE00]       # a, glif bez Unicode, b, emoji

    class Tp:
        raw = None

        def count_chars(self):
            return len(kody)

        def get_text_range(self):
            return "ab" + chr(0x1F600)

    monkeypatch.setattr(pdfium_c, "FPDFText_GetUnicode", lambda _r, i: kody[i])
    assert core_pdf._znaki_strony(Tp()) == [(0, "a"), (2, "b"), (3, chr(0x1F600))]


# --------------------------------------------------------------------- E ---
# Prawdziwe PDF-y z surowego API PDFium (builder z audytu 19.13) — reszta
# testów idzie na atrapach, więc to jest jedyny dowód na prawdziwym pliku.

def _zbuduj_pdf(sciezka, strony, rotacja=0):
    import ctypes
    import pypdfium2 as pdfium
    import pypdfium2.raw as c
    pdf = pdfium.PdfDocument.new()
    font = c.FPDFText_LoadStandardFont(pdf.raw, b"Helvetica")
    bufory = []
    for linie in strony:
        page = pdf.new_page(595, 842)
        for tekst, x, y in linie:
            obj = c.FPDFPageObj_CreateTextObj(pdf.raw, font, 11.0)
            b = (tekst + "\0").encode("utf-16-le")
            buf = ctypes.create_string_buffer(b, len(b))
            bufory.append(buf)
            assert c.FPDFText_SetText(obj, ctypes.cast(buf, c.FPDF_WIDESTRING))
            c.FPDFPageObj_Transform(obj, 1, 0, 0, 1, float(x), float(y))
            c.FPDFPage_InsertObject(page.raw, obj)
        if rotacja:
            page.set_rotation(rotacja)
        page.gen_content()
        page.close()
    pdf.save(str(sciezka))
    pdf.close()


def test_prawdziwy_pdf_kolontytul_numery_i_tresc(tmp_path):
    p = tmp_path / "doc.pdf"
    _zbuduj_pdf(p, [[("Kwartalnik Testowy", 72, 815), (f"Akapit strony {i}.", 72, 700),
                     ("Rozdzial II", 72, 650), (str(i), 290, 25)] for i in range(1, 5)])
    w = core_pdf.wyciagnij(str(p))
    assert w.kolontytuly == ["Kwartalnik Testowy"]
    assert w.akapity[:2] == ["Akapit strony 1.", "Rozdzial II"]
    assert not any(a.strip().isdigit() for a in w.akapity)


def test_prawdziwy_pdf_obrocony_nie_traci_tresci(tmp_path):
    p = tmp_path / "rot.pdf"
    _zbuduj_pdf(p, [[("Naglowek", 72, 815), ("Tresc strony.", 72, 400)]], rotacja=90)
    w = core_pdf.wyciagnij(str(p))
    assert "Naglowek" in " ".join(w.akapity) and "Tresc strony." in " ".join(w.akapity)


def test_prawdziwy_pdf_z_samymi_numerami_to_brak_tekstu(tmp_path):
    p = tmp_path / "numery.pdf"
    _zbuduj_pdf(p, [[(str(i), 290, 25)] for i in range(1, 4)])
    with pytest.raises(core_pdf.BrakWarstwyTekstu) as exc:
        core_pdf.wyciagnij(str(p))
    # Warstwa tekstu JEST — odczyt obrazu nie ma tu czego ratować.
    assert exc.value.liczba_stron == 3 and exc.value.strony_bez_tekstu == []


# --------------------------------------------------------------------- F ---
# 19.15: zniekształcona warstwa tekstu. Słownik z macOS Quartz (551 stron):
# mapa ToUnicode czcionki urwana na „М”, reszta cyrylicy wychodzi z PDFium
# jako numery glifów = litery IPA, a lingua zgaduje `de`. Builder poniżej
# odtwarza to 1:1 — font Type0/Identity-H, kod = punkt kodowy cyrylicy − 470.

_CMAP_UCIETA = (
    "/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
    "/CMapName /X def 1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
    "1 beginbfrange <023a> <0246> <0410> endbfrange\n"
    "endcmap CMapName currentdict /CMap defineresource pop end end")


def _pdf_cid(sciezka, wiersze, tounicode=_CMAP_UCIETA):
    """Strona z fontem Type0 bez programu fontu; `wiersze`: (tekst, y)."""
    tresc = b"".join(
        b"BT /F1 12 Tf 72 %d Td <%s> Tj ET\n" % (y, "".join(
            f"{ord(z) - 470:04x}" if ord(z) >= 0x410 else f"{ord(z):04x}"
            for z in tekst).encode())
        for tekst, y in wiersze)
    cmap = tounicode.encode() if tounicode else b""
    obiekty = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /ABCDEF+TimesNewRoman "
        b"/Encoding /Identity-H /DescendantFonts [6 0 R]"
        + (b" /ToUnicode 7 0 R" if cmap else b"") + b" >>",
        b"<< /Length %d >>\nstream\n" % len(tresc) + tresc + b"\nendstream",
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /ABCDEF+TimesNewRoman "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        b"/DW 500 /CIDToGIDMap /Identity >>",
    ]
    if cmap:
        obiekty.append(b"<< /Length %d >>\nstream\n" % len(cmap) + cmap + b"\nendstream")
    out = bytearray(b"%PDF-1.7\n")
    offsety = []
    for i, obj in enumerate(obiekty, 1):
        offsety.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(obiekty) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsety)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(obiekty) + 1, xref)
    sciezka.write_bytes(bytes(out))


def _scal_pdf(cel, *zrodla):
    import pypdfium2 as pdfium
    nowy = pdfium.PdfDocument.new()
    for z in zrodla:
        d = pdfium.PdfDocument(str(z))
        nowy.import_pages(d)
        d.close()
    nowy.save(str(cel))
    nowy.close()


ZNANE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                  "ĄĆĘŁŃÓŚŹŻąćęłńóśźżÉéАБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
                  "абвгдежзийклмнопрстуфхцчшщъыьэюя")


class _TpZFlaga:
    raw = object()


@pytest.mark.parametrize("tekst, flaga, podejrzane", [
    # Polski PDF z Worda (zmierzone 2026-10-20): PDFium flaguje poprawnie
    # odgadnięte „ą”, „ł” — litery paczki nie są podejrzane mimo flagi.
    ("Zażółć gęślą jaźń", True, 0),
    # Numery glifów cyrylicy jako IPA: podejrzane, bo z flagą i spoza paczek.
    ("ɍɬɜɟɪɠɞɟɧɨ", True, 10),
    # Ten sam IPA z poprawną mapą (praca językoznawcza) — bez flagi nic.
    ("ɍɬɜɟɪɠɞɟɧɨ", False, 0),
    # Strona tytułowa słownika: „Ȅ” to NIE „E” z akcentem (NFD by przepuścił).
    ("СЛОВАРȄ ȇЗȃКА", True, 3),
])
def test_podejrzane_litery_to_flaga_pdfium_i_litera_spoza_paczek(
        monkeypatch, tekst, flaga, podejrzane):
    monkeypatch.setattr(core_pdf, "_blad_mapowania", lambda _tp, _i: flaga)
    znaki = list(enumerate(tekst))
    litery = sum(z.isalpha() for z in tekst)
    assert core_pdf._policz_litery(_TpZFlaga(), znaki, ZNANE) == (litery, podejrzane)


def test_prog_strony_znieksztalconej():
    assert core_pdf.czy_znieksztalcona(100, 3)          # tytułowa słownika: 4 na ~100
    assert not core_pdf.czy_znieksztalcona(100, 2)      # pojedynczy glif symbolu
    assert not core_pdf.czy_znieksztalcona(2000, 30)    # 1,5% — poniżej udziału
    assert core_pdf.czy_znieksztalcona(2000, 1800)


def test_litery_paczek_maja_akcenty_a_nie_ipa():
    # Bramka danych: miara stoi na tym, że paczki NIE piszą literami IPA. Gdy
    # ktoś wklei opis fonetyki do `ui.yaml`, zniekształcony słownik zacznie
    # przechodzić jako dobry tekst — ten test to wtedy powie.
    litery = core_pdf.litery_paczek()
    for z in "ąłéèçñßÞðöäåАяЁё":
        assert z in litery, z
    for z in "ɍɬɜɟɪɠɞɧɨɛɝɚɢɡɥɤɩɱɲɳɭɯɵɶɷɸɹȄȇȃȅғ":
        assert z not in litery, z


def test_prawdziwy_pdf_ucieta_mapa_tounicode_to_strona_znieksztalcona(tmp_path):
    zla, dobra, cala = tmp_path / "zla.pdf", tmp_path / "dobra.pdf", tmp_path / "cala.pdf"
    _pdf_cid(zla, [("Утверждено к печати Ученым советом", 700)])
    _zbuduj_pdf(dobra, [[("Tresc poprawnej strony.", 72, 700)]])
    _scal_pdf(cala, dobra, zla, dobra)
    w = core_pdf.wyciagnij(str(cala), ZNANE)
    assert w.strony_znieksztalcone == [2]
    assert w.strony_bez_tekstu == []
    assert w.strony_do_odczytu == [2]
    # Śmieci są w wyniku (ostrzega GUI), ale nie w tekście dla lingua.
    assert "ɍɬɜɟɪɠɞɟɧɨ" in w.tekst
    assert "ɍ" not in w.tekst_wiarygodny and "Tresc poprawnej strony." in w.tekst_wiarygodny
    assert len(w.znaki_stron) == 3 and w.znaki_stron[1] > 20


def test_prawdziwy_pdf_pelna_mapa_tounicode_jest_czysty(tmp_path):
    # Ta sama czcionka z PEŁNĄ mapą: cyrylica poprawna, flag brak.
    pelna = _CMAP_UCIETA.replace("<023a> <0246> <0410>", "<023a> <0279> <0410>")
    p = tmp_path / "pelna.pdf"
    _pdf_cid(p, [("Утверждено к печати", 700)], tounicode=pelna)
    w = core_pdf.wyciagnij(str(p), ZNANE)
    assert w.strony_znieksztalcone == []
    assert w.akapity == ["Утверждено к печати"]


def test_strona_znieksztalcona_blokuje_sklejanie(monkeypatch):
    # Jej akapity zastąpi odczyt obrazu — nie mogą wchłonąć zdania sąsiada.
    import pypdfium2
    monkeypatch.setattr(core_pdf, "_blad_mapowania", lambda _tp, _i: True)
    srodek = _strona(("ɢ ɞɚɥɶɲɟ ɬɟɤɫɬ", 90, 700, 12))
    monkeypatch.setattr(pypdfium2, "PdfDocument",
                        lambda _p: _AtrapaPdf(_zdanie_przez_strone(srodek)))
    w = core_pdf.wyciagnij("zly.pdf", ZNANE)
    assert w.strony_znieksztalcone == [2]
    assert w.akapity_stron == [["Zdanie urwane na"], ["ɢ ɞɚɥɶɲɟ ɬɟɤɫɬ"], ["dalszy ciąg."]]
    assert w.tekst_wiarygodny == "Zdanie urwane na\n\ndalszy ciąg."


# --------------------------------------------------------------------- G ---
# 19.15, etap 2: naprawa z osadzonego fontu. Font budujemy w teście
# (fontTools `FontBuilder`), więc fixtura nie wozi cudzego fontu: glify
# cyrylicy mają numery od 600 (kody wypadają w IPA jak w słowniku), akcent
# U+0301 jest TYLKO w `post` (`uni0301`) i ma zerową szerokość.

_TEKST_G = "Утверждено к печати"


def _font_ttf(*, cmap=True, nazwy=True, polowa=False):
    import io
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    litery = sorted(set(_TEKST_G.replace(" ", "")))
    kolejnosc = [".notdef"] + [f"pusty{i}" for i in range(1, 600)]
    gid = {}
    for z in litery:
        gid[z] = len(kolejnosc)
        kolejnosc.append(f"uni{ord(z):04X}")
    gid["akcent"] = len(kolejnosc)
    kolejnosc.append("uni0301")
    w_cmap = litery[: len(litery) // 2] if polowa else litery
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(kolejnosc)
    fb.setupCharacterMap({ord(z): f"uni{ord(z):04X}" for z in w_cmap} if cmap else {})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((0, 500))
    pen.lineTo((400, 500))
    pen.closePath()
    glif = pen.glyph()
    fb.setupGlyf({n: glif for n in kolejnosc})
    fb.setupHorizontalMetrics({n: (0 if n == "uni0301" else 500, 0) for n in kolejnosc})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Proba", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost(keepGlyphNames=nazwy and not polowa)
    bufor = io.BytesIO()
    fb.save(bufor)
    return bufor.getvalue(), gid


def _pdf_osadzony(sciezka, **opcje_fontu):
    """Słowa jako osobne biegi (PDFium generuje spacje), akcent po „Утве”."""
    ttf, gid = _font_ttf(**opcje_fontu)
    x, tresc = 72, b""
    for nr, slowo in enumerate(_TEKST_G.split()):
        kody = []
        for z in slowo:
            kody.append(f"{gid[z]:04x}")
            if nr == 0 and len(kody) == 4:
                kody.append(f"{gid['akcent']:04x}")
        tresc += f"BT /F1 12 Tf {x} 700 Td <{''.join(kody)}> Tj ET ".encode()
        x += len(kody) * 6 + 4          # `/DW 500` daje szerokość także akcentowi
    cmap = _CMAP_UCIETA.encode()
    obiekty = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /ABCDEF+Proba /Encoding /Identity-H "
        b"/DescendantFonts [6 0 R] /ToUnicode 8 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(tresc) + tresc + b"\nendstream",
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /ABCDEF+Proba "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        b"/FontDescriptor 7 0 R /DW 500 /CIDToGIDMap /Identity >>",
        b"<< /Type /FontDescriptor /FontName /ABCDEF+Proba /Flags 32 "
        b"/FontBBox [0 -200 1000 800] /ItalicAngle 0 /Ascent 800 /Descent -200 "
        b"/CapHeight 700 /StemV 80 /FontFile2 9 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(cmap) + cmap + b"\nendstream",
        b"<< /Length %d /Length1 %d >>\nstream\n" % (len(ttf), len(ttf)) + ttf + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.7\n")
    offsety = []
    for i, obj in enumerate(obiekty, 1):
        offsety.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(obiekty) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsety)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(obiekty) + 1, xref)
    sciezka.write_bytes(bytes(out))


def test_naprawa_z_osadzonego_fontu_cmap_i_post(tmp_path):
    import unicodedata
    p = tmp_path / "osadzony.pdf"
    _pdf_osadzony(p)
    w = core_pdf.wyciagnij(str(p), ZNANE)
    # Akcent z nazwy `post` siedzi PRZY literze — bez spacji („Утве ́рждено”)
    # i bez rozcięcia słowa („Утве́ рждено”).
    akcent = chr(0x301)
    assert w.akapity == [f"Утве{akcent}рждено к печати"]
    assert unicodedata.normalize("NFC", w.akapity[0]) == w.akapity[0]
    assert w.strony_naprawione == [1] and w.strony_znieksztalcone == []
    assert w.tekst_wiarygodny == w.tekst


def test_naprawa_czesciowa_zostaje_zgloszona(tmp_path):
    # `cmap` zna połowę liter, `post` bez nazw: strona lepsza, ale wciąż
    # zniekształcona — bramka ją zgłasza, a GUI oferuje odczyt obrazu.
    p = tmp_path / "polowa.pdf"
    _pdf_osadzony(p, polowa=True)
    w = core_pdf.wyciagnij(str(p), ZNANE)
    assert w.strony_znieksztalcone == [1] and w.strony_naprawione == []


def test_font_bez_cmap_i_nazw_nie_naprawia(tmp_path):
    p = tmp_path / "pusty.pdf"
    _pdf_osadzony(p, cmap=False, nazwy=False)
    w = core_pdf.wyciagnij(str(p), ZNANE)
    assert w.strony_znieksztalcone == [1] and w.strony_naprawione == []
    assert "ɍ" not in w.tekst_wiarygodny


def test_font_nieosadzony_nie_jest_naprawiany(tmp_path):
    # PDFium oddaje wtedy dane fontu SYSTEMOWEGO; Times z Windows ma tę samą
    # numerację co podzbiór ze słownika i „naprawiał” przypadkiem — przypadek
    # to nie kontrakt (fixtura `_pdf_cid` nie osadza programu fontu).
    p = tmp_path / "nieosadzony.pdf"
    _pdf_cid(p, [("Утверждено к печати", 700)])
    w = core_pdf.wyciagnij(str(p), ZNANE)
    assert w.strony_znieksztalcone == [1] and w.strony_naprawione == []


def test_mapa_glifow_nieczytelny_font_to_brak_naprawy():
    assert core_pdf.mapa_glifow(b"") == {}
    assert core_pdf.mapa_glifow(b"to nie jest font" * 10) == {}


# --------------------------------------------------------------------- H ---
# 19.15, etap 3: kolontytuł poza pasem 7% i tekst rozstrzelony w PDF-ie.

def _strona_slownika(naglowek, numer, tresc=("Treść strony pierwsza.", "Treść dalej.")):
    """Jak w słowniku z macOS Quartz: nagłówek górą na 7,7%, numer dołem
    na 7,4% wysokości — oba tuż POZA pasem marginesu 7%."""
    linie = [L(naglowek, 90, 762, 300, wys=15)]
    linie += [L(t, 90, 726 - 16 * i, 500, wys=15) for i, t in enumerate(tresc)]
    linie += [L("Ostatnia linia treści.", 90, 80, 500, wys=15), L(str(numer), 290, 62, 300, wys=15)]
    return S(*linie)


def test_kolontytul_poza_pasem_i_przemienny_na_parzystych():
    # Strony nieparzyste (indeks parzysty): tytuł książki; parzyste: „Часть I”,
    # w połowie przełączone na „Часть II” — żaden nie ma ćwierci WSZYSTKICH stron.
    strony = []
    for i in range(20):                # „Część I”: 4 z 20 stron (20%), 4 z 10 parzystych
        nagl = "Słownik języka" if i % 2 == 0 else ("Część I" if i < 9 else "Część II")
        strony.append(_strona_slownika(nagl, i + 1))
    wynik, kolontytuly = core_pdf._usun_kolontytuly(strony)
    assert sorted(kolontytuly) == ["Część I", "Część II", "Słownik języka"]
    assert all([x.tekst for x in s] == ["Treść strony pierwsza.", "Treść dalej.",
                                        "Ostatnia linia treści."] for s in wynik)


def test_skrajna_linia_przy_tresci_nie_jest_kolontytulem():
    # Ta sama pierwsza linia na każdej stronie, ale przyklejona do treści
    # (odstęp 1 pt) i poza pasem: to treść, nie nagłówek.
    strony = [S(L("Wstęp do rozdziału", 90, 726, 300, wys=15),
                L("Treść.", 90, 710, 300, wys=15), L("Dalej.", 90, 694, 300, wys=15))
              for _ in range(6)]
    wynik, kolontytuly = core_pdf._usun_kolontytuly(strony)
    assert kolontytuly == [] and all(len(s) == 3 for s in wynik)


def _znaki_rozstrzelone(slowa, krok=4.0, przerwa=13.0):
    znaki, luki = [], {}
    for n, slowo in enumerate(slowa):
        for k, z in enumerate(slowo):
            if znaki:
                luki[len(znaki)] = przerwa if k == 0 else krok
                znaki.append(" ")
            znaki.append(z)
    return znaki, luki


def test_granice_rozstrzelenia_z_geometrii():
    znaki, luki = _znaki_rozstrzelone(["социальное", "дистанция"])
    core_pdf._oznacz_granice_rozstrzelenia(znaki, luki)
    assert "".join(znaki).split(core_pdf._GRANICA) == [
        "с о ц и а л ь н о е", "д и с т а н ц и я"]


def test_rowne_przerwy_bez_granic_i_bez_granicy_po_akcencie():
    znaki, luki = _znaki_rozstrzelone(["а", "и", "в", "к"], przerwa=4.0)
    core_pdf._oznacz_granice_rozstrzelenia(znaki, luki)
    assert core_pdf._GRANICA not in znaki
    # „ф о р м а́ т”: po akcencie przerwa rośnie, ale to nie granica słowa.
    znaki, luki = _znaki_rozstrzelone(["формат"])
    znaki.insert(znaki.index("а") + 1, chr(0x301))
    luki = {i + (1 if i > znaki.index("а") else 0): v for i, v in luki.items()}
    luki[znaki.index("т") - 1] = 13.0
    core_pdf._oznacz_granice_rozstrzelenia(znaki, luki)
    assert core_pdf._GRANICA not in znaki


def _rozstrzel(slowa, x0, y, krok=11, przerwa=22):
    linie, x = [], x0
    for slowo in slowa:
        for z in slowo:
            linie.append((z, x, y))
            x += krok
        x += przerwa - krok
    return linie


def test_prawdziwy_pdf_rozstrzelony_sklejony_wg_slownika(tmp_path, monkeypatch):
    p = tmp_path / "rozstrzelony.pdf"
    _zbuduj_pdf(p, [[("Termin: socjalny dystans.", 72, 700)]
                    + _rozstrzel(["socjalny", "dystans"], 72, 650)
                    + _rozstrzel(["xqzw"], 72, 400)])
    assert core_pdf.wyciagnij(str(p)).akapity == [
        "Termin: socjalny dystans.", "socjalny dystans", "x q z w"]
    # Kontrola: bez reguły słownikowej ten sam PDF zostaje rozstrzelony.
    import core_poliglota
    monkeypatch.setattr(core_poliglota, "scal_rozstrzelone",
                        lambda a: (list(a), {"sklejone": 0}))
    assert core_pdf.wyciagnij(str(p)).akapity[1] == "s o c j a l n y d y s t a n s"


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
