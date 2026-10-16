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


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
