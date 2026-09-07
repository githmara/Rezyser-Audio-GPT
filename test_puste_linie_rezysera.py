"""
test_puste_linie_rezysera.py - Regresja ksztaltu pliku projektu Rezysera (18.26.1).

Plik `skrypty/<nazwa>.txt` powstaje z blokow dopisywanych po kolei (naglowek
struktury albo fragment od modelu). Do v18.26.0 kazdy blok nosil wlasna obwodke
`\\n\\n`, a fragment jeszcze `\\n\\n` na koncu, wiec obwodki sie SUMOWALY: plik
zaczynal sie dwiema pustymi liniami, przed kazdym naglowkiem byly trzy z rzedu,
a akapity prozy dawaly staly rytm „linia - pusta - linia" (zmierzone: 11 pustych
linii z 17). Dla czytnika ekranu dluzsza seria pustych linii jest nieodroznialna
od konca pliku, wiec to problem DOSTEPNOSCI, nie estetyki.

Niezmiennik pilnowany przez te testy: plik to bloki rozdzielone DOKLADNIE jedna
pusta linia, bez pustej linii na poczatku, bez ciagow pustych linii wewnatrz
bloku, z jednym zlamaniem wiersza na koncu. Regula zyje w JEDNYM miejscu
(`ProjektRezysera._doklej_blok`) - wczesniej byla zdublowana w panelu GUI, ktory
mial wlasna kopie skladania i to jego wersje widzial uzytkownik.

Testy pisza do katalogu tymczasowego - projektow uzytkownika nie dotykaja.

Uruchom:  .venv/Scripts/python test_puste_linie_rezysera.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import core_rezyser as cr

# Proza modelu w realnym ksztalcie: akapity rozdzielone pusta linia.
FRAGMENT_DWA_AKAPITY = "Pierwszy akapit prozy.\n\nDrugi akapit prozy."


class Sesja:
    """Projekt w katalogu tymczasowym + odczyt wynikowego pliku."""

    def __init__(self, nazwa="proba"):
        self.katalog = Path(tempfile.mkdtemp())
        self.projekt = cr.ProjektRezysera(app_dir=str(self.katalog))
        self.projekt.nazwa_pliku = nazwa
        self.sciezka = self.katalog / cr.SKRYPTY_DIR / f"{nazwa}.txt"

    def tresc(self):
        return self.sciezka.read_text(encoding="utf-8") if self.sciezka.exists() else ""

    def linie(self):
        """Linie pliku BEZ artefaktu koncowego zlamania wiersza."""
        surowe = self.tresc().split("\n")
        return surowe[:-1] if surowe and surowe[-1] == "" else surowe

    def sprzataj(self):
        shutil.rmtree(self.katalog, ignore_errors=True)


def maks_pustych_pod_rzad(linie):
    biezaca = najwieksza = 0
    for linia in linie:
        biezaca = biezaca + 1 if not linia.strip() else 0
        najwieksza = max(najwieksza, biezaca)
    return najwieksza


# ---------------------------------------------------------------------------
# Normalizator bloku
# ---------------------------------------------------------------------------
def test_normalizator_zwija_ciag_pustych_linii():
    assert cr.znormalizuj_blok("a\n\nb") == "a\nb"
    assert cr.znormalizuj_blok("a\n\n\n\nb") == "a\nb"


def test_normalizator_widzi_puste_linie_ze_spacjami_i_tabami():
    assert cr.znormalizuj_blok("a\n   \nb") == "a\nb"
    assert cr.znormalizuj_blok("a\n\t\n \nb") == "a\nb"


def test_normalizator_zdejmuje_obwodke_bloku():
    assert cr.znormalizuj_blok("\n\n  tekst  \n\n") == "tekst"
    assert cr.znormalizuj_blok("   \n\n ") == ""


def test_normalizator_nie_rusza_pojedynczych_zlaman():
    assert cr.znormalizuj_blok("a\nb\nc") == "a\nb\nc"


# ---------------------------------------------------------------------------
# Ksztalt pliku
# ---------------------------------------------------------------------------
def test_plik_nie_zaczyna_sie_pusta_linia():
    s = Sesja()
    try:
        s.projekt.wstaw_rozdzial(naglowek_bazowy="Rozdzial")
        assert s.linie()[0].strip(), s.linie()
        assert s.tresc().startswith("Rozdzial 1"), repr(s.tresc())
    finally:
        s.sprzataj()


def test_akapity_fragmentu_sa_sasiadujace():
    s = Sesja()
    try:
        s.projekt.dopisz_odpowiedz_ai(FRAGMENT_DWA_AKAPITY)
        assert s.linie() == ["Pierwszy akapit prozy.", "Drugi akapit prozy."], s.linie()
    finally:
        s.sprzataj()


def test_naglowek_po_fragmencie_ma_dokladnie_jedna_pusta_linie():
    s = Sesja()
    try:
        s.projekt.wstaw_rozdzial(naglowek_bazowy="Rozdzial")
        s.projekt.dopisz_odpowiedz_ai(FRAGMENT_DWA_AKAPITY)
        s.projekt.wstaw_rozdzial(naglowek_bazowy="Rozdzial")
        s.projekt.dopisz_odpowiedz_ai(FRAGMENT_DWA_AKAPITY)
        assert maks_pustych_pod_rzad(s.linie()) == 1, s.linie()
        assert s.linie() == [
            "Rozdzial 1", "",
            "Pierwszy akapit prozy.", "Drugi akapit prozy.", "",
            "Rozdzial 2", "",
            "Pierwszy akapit prozy.", "Drugi akapit prozy.",
        ], s.linie()
    finally:
        s.sprzataj()


def test_akt_i_scena_rozdzielone_jedna_pusta_linia():
    s = Sesja()
    try:
        s.projekt.wstaw_akt(naglowek_akt="Akt", naglowek_scena="Scena")
        s.projekt.wstaw_scena(naglowek_bazowy="Scena")
        assert s.linie() == ["Akt 1", "", "Scena 1", "", "Scena 2"], s.linie()
    finally:
        s.sprzataj()


def test_prolog_i_epilog_bez_serii_pustych():
    s = Sesja()
    try:
        s.projekt.wstaw_prolog(naglowek="Prolog")
        s.projekt.dopisz_odpowiedz_ai(FRAGMENT_DWA_AKAPITY)
        s.projekt.wstaw_epilog(naglowek="Epilog")
        assert maks_pustych_pod_rzad(s.linie()) == 1, s.linie()
        assert s.linie()[0] == "Prolog"
        assert s.linie()[-1] == "Epilog"
    finally:
        s.sprzataj()


def test_plik_konczy_sie_jednym_zlamaniem_wiersza():
    s = Sesja()
    try:
        s.projekt.wstaw_rozdzial(naglowek_bazowy="Rozdzial")
        s.projekt.dopisz_odpowiedz_ai(FRAGMENT_DWA_AKAPITY)
        tresc = s.tresc()
        assert tresc.endswith("\n") and not tresc.endswith("\n\n"), repr(tresc[-6:])
    finally:
        s.sprzataj()


def test_blok_z_samych_bialych_znakow_nie_zmienia_pliku():
    s = Sesja()
    try:
        s.projekt.wstaw_rozdzial(naglowek_bazowy="Rozdzial")
        przed = s.tresc()
        s.projekt.dopisz_odpowiedz_ai("   \n\n  ")
        assert s.tresc() == przed, repr(s.tresc())
    finally:
        s.sprzataj()


def test_dluga_sesja_mieszana_trzyma_niezmiennik():
    s = Sesja()
    try:
        s.projekt.wstaw_prolog(naglowek="Prolog")
        for _ in range(3):
            s.projekt.dopisz_odpowiedz_ai(FRAGMENT_DWA_AKAPITY)
            s.projekt.wstaw_rozdzial(naglowek_bazowy="Rozdzial")
        s.projekt.dopisz_odpowiedz_ai(FRAGMENT_DWA_AKAPITY)
        s.projekt.wstaw_epilog(naglowek="Epilog")
        linie = s.linie()
        assert maks_pustych_pod_rzad(linie) == 1, linie
        assert linie[0].strip(), linie
        assert linie[-1].strip(), linie
        # Pamiec i plik nie moga sie rozjechac - payload AI idzie z pamieci.
        assert s.projekt.full_story == s.tresc(), (
            repr(s.projekt.full_story[-40:]), repr(s.tresc()[-40:]))
    finally:
        s.sprzataj()


# ---------------------------------------------------------------------------
# Pliki z wczesniejszych wersji
# ---------------------------------------------------------------------------
def test_stary_plik_nie_jest_przepisywany_pod_nowy_kanon():
    """Cudzej tresci nie ruszamy - dopisujemy tylko tak, by NIE dodac wiecej."""
    s = Sesja(nazwa="legacy")
    try:
        s.sciezka.parent.mkdir(parents=True, exist_ok=True)
        stara = "Rozdzial 1\n\n\n\nStary tekst.\n\n\n"
        s.sciezka.write_text(stara, encoding="utf-8")
        s.projekt.full_story = stara          # stan po wczytaniu z dysku
        s.projekt.dopisz_odpowiedz_ai("Nowy fragment.")
        tresc = s.tresc()
        assert tresc.startswith(stara), repr(tresc[:len(stara) + 10])
        assert tresc.endswith("Nowy fragment.\n"), repr(tresc[-25:])
        # Zadnej pustej linii PONAD to, co juz bylo w pliku.
        assert tresc.count("\n") == stara.count("\n") + 1, repr(tresc)
    finally:
        s.sprzataj()


if __name__ == "__main__":
    testy = [(nazwa, obiekt) for nazwa, obiekt in sorted(globals().items())
             if nazwa.startswith("test_") and callable(obiekt)]
    bledy = []
    for nazwa, funkcja in testy:
        try:
            funkcja()
            print(f"  OK   {nazwa}")
        except AssertionError as exc:
            bledy.append(nazwa)
            print(f"  FAIL {nazwa}: {exc}")
    print(f"\n{len(testy) - len(bledy)}/{len(testy)} zaliczonych.")
    sys.exit(1 if bledy else 0)
