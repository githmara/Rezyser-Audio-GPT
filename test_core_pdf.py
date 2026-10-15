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
     brak OCR"), zamiast oddać pusty dokument.

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
    strona = _strona(("granicy wier￾", 90, 600, 12), ("sza. Koniec", 90, 584, 12))
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


@pytest.mark.parametrize("lewy,prawy,wynik", [
    ("przy­", "Kład", "przyKład"),       # miękki dywiz skleja zawsze
    ("przy-", "kład", "przykład"),            # zwykły — przed małą literą
    ("Jean-", "Paul", "Jean- Paul"),          # łącznik przed wielką zostaje
])
def test_sklejanie_przeniesien(lewy, prawy, wynik):
    assert core_pdf._sklej(lewy, prawy) == wynik


def test_pozycja_spisu_tresci_konczy_akapit():
    linie = kolumna(("1.1. Pojęcie ............ 10", True), ("1.2. Sposoby ............ 12", True))
    assert len(core_pdf._podziel_na_akapity(linie)) == 2


# --------------------------------------------------------------------- C ---

def _strony_z_kolontytulem(n=4):
    strony = []
    for nr in range(1, n + 1):
        linie = [
            L(f"Kwartalnik Testowy – Nr {nr}", 90, 790, 300),   # górny margines
            L("[scena 1]", 90, 770, 160),                      # tag w marginesie
            L("SCENA 2", 90, 400, 160),                        # środek strony
            L(f"Treść strony {nr}.", 90, 380, 300),
            L(str(nr), 290, 30, 300),                          # numer strony
        ]
        strony.append((linie, WYS_STRONY))
    return strony


def test_kolontytul_po_pozycji_znika_tresc_zostaje():
    wynik, kolontytuly = core_pdf._usun_kolontytuly(_strony_z_kolontytulem())
    teksty = [x.tekst for x in wynik[0]]
    assert "Kwartalnik Testowy – Nr 1" not in teksty
    assert "1" not in teksty
    assert teksty == ["[scena 1]", "SCENA 2", "Treść strony 1."]
    assert kolontytuly == ["Kwartalnik Testowy – Nr 1"]   # oryginał, nie klucz


def test_ta_sama_linia_na_innej_wysokosci_to_nie_kolontytul():
    # Refren w środku stron — powtarza się, ale nie w marginesie.
    strony = [([L("Hej, sokoły, omijajcie", 90, 300 + 40 * i, 400)], WYS_STRONY)
              for i in range(4)]
    wynik, kolontytuly = core_pdf._usun_kolontytuly(strony)
    assert kolontytuly == [] and all(len(s) == 1 for s in wynik)


# --------------------------------------------------------------------- D ---

class _AtrapaPdf:
    def __init__(self, strony):
        self.strony = strony

    def __len__(self):
        return len(self.strony)

    def __getitem__(self, i):
        strona = self.strony[i]
        strona.get_height = lambda: WYS_STRONY
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


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
