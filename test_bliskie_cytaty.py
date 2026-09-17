"""
test_bliskie_cytaty.py - Baseline cytatow PRAWIE rownych etykiecie GUI (v19.4).

Klasa „cytat rozjechany z etykieta o jedno slowo" istnieje od v18.26, ale byla
gola UWAGA: `--waliduj` wypisywal wszystkie 49 trafien przy KAZDYM przebiegu,
bo rozstrzygniecie („poprawic cytat czy etykiete?") w obcym jezyku nalezy do
native'a. Werdykt „przepuszczone kryterium zrozumialosci" zyl wiec wylacznie
w pamieci czlowieka, a 50. trafienie - byc moze realnie martwy cytat - utonelo
by w wyliczance. Od v19.4.0 werdykty stoja w `bliskie_cytaty_baseline.json`,
a bramka pada TYLKO na trafienie ponad snapshot.

Testy pilnuja czterech rzeczy, wszystkie mierzone WYKONANIEM:
  1. KLUCZ JEST ODPORNY NA PRZESUNIECIE LINII - klucz snapshotu to
     `<kod>/<plik>/<sekcja>`, wiec przepisanie akapitu wyzej w pliku nie
     produkuje fali „nowych" trafien na NIEZMIENIONEJ tresci. Gdyby numer
     linii wszedl do klucza, baseline rozjechalby sie przy pierwszej edycji
     podrecznika i nikt by go wiecej nie przejrzal;
  2. NOWE TRAFIENIE BLOKUJE - nadwyzka nad snapshotem (takze DRUGIE takie samo
     trafienie w tej samej sekcji, bo roznica jest multisetowa) wraca
     z `bramka_bliskich_cytatow` jako „nowe";
  3. MARTWY WPIS JEST RAPORTOWANY - wpis, ktorego dzis nie ma, czyni snapshot
     LUZNIEJSZYM niz stan faktyczny. Bramka go NIE przepuszcza w milczeniu,
     bo dokladnie ta klasa (-4 martwe wpisy) wyszla przy regeneracji
     `audyt_leakow_baseline.json` w tym samym cyklu;
  4. ZGUBIONY SNAPSHOT JEST MAKSYMALNIE SUROWY, nie maksymalnie luzny - brak
     pliku znaczy „kazde trafienie nowe", jak w `audyt_leakow.wczytaj_baseline`.

Uruchom:  .venv/Scripts/python test_bliskie_cytaty.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import generuj_dokumentacje as gd

_KORZEN = Path(__file__).parent


def _trafienie(**nadpisania) -> dict:
    """Jedno trafienie w kszalcie, ktory zwraca `_znajdz_bliskie_cytaty`."""
    baza = {
        "kod": "xx",
        "plik": r"dictionaries\xx\gui\dokumentacja\manual.yaml",
        "linia": 100,
        "sekcja": "krok_3_glowne_studio",
        "cytat": "Send to AI",
        "rdzen": "send to ai",
        "etykieta": "send to the ai",
        "klucze": ["rezyser.btn_wyslij_label"],
    }
    baza.update(nadpisania)
    return baza


def _z_trafieniami(trafienia: list[dict], baseline: dict | None = None):
    """Uruchamia bramke na PODSTAWIONYM skanie i PODSTAWIONYM pliku snapshotu.

    Podstawiamy oba konce, bo inaczej test mierzylby stan dziewieciu paczek
    (zmiennny) zamiast semantyki roznicy (staly kontrakt).
    """
    oryginalny_skan = gd._znajdz_bliskie_cytaty
    oryginalna_sciezka = gd.BASELINE_BLISKICH_PATH
    with tempfile.TemporaryDirectory() as tmp:
        sciezka = Path(tmp) / "bliskie_cytaty_baseline.json"
        if baseline is not None:
            sciezka.write_text(json.dumps(baseline, ensure_ascii=False),
                               encoding="utf-8")
        gd._znajdz_bliskie_cytaty = lambda: list(trafienia)
        gd.BASELINE_BLISKICH_PATH = sciezka
        try:
            return gd.bramka_bliskich_cytatow()
        finally:
            gd._znajdz_bliskie_cytaty = oryginalny_skan
            gd.BASELINE_BLISKICH_PATH = oryginalna_sciezka


def test_klucz_bez_numeru_linii():
    """Ten sam cytat w innej linii tej samej sekcji = ten sam klucz i powod."""
    oryginalny = gd._znajdz_bliskie_cytaty
    try:
        gd._znajdz_bliskie_cytaty = lambda: [_trafienie(linia=100)]
        przed = gd.klucze_bliskich_cytatow()
        gd._znajdz_bliskie_cytaty = lambda: [_trafienie(linia=640)]
        po = gd.klucze_bliskich_cytatow()
    finally:
        gd._znajdz_bliskie_cytaty = oryginalny
    assert przed == po, f"przesuniecie linii zmienilo snapshot: {przed} vs {po}"
    assert list(przed) == ["xx/manual.yaml/krok_3_glowne_studio"], list(przed)
    assert przed["xx/manual.yaml/krok_3_glowne_studio"] == [
        "bliski:send to ai≈send to the ai"], przed


def test_trafienie_ponad_baseline_blokuje():
    """Cytat, ktorego nie ma w snapshocie, wraca jako nowy (= exit 1)."""
    nowe, martwe, znane = _z_trafieniami([_trafienie()], baseline={})
    assert nowe == {"xx/manual.yaml/krok_3_glowne_studio":
                    ["bliski:send to ai≈send to the ai"]}, nowe
    assert not martwe and znane == 0, (martwe, znane)


def test_drugie_takie_samo_trafienie_jest_nowe():
    """Roznica jest MULTISETOWA: dwa identyczne cytaty w sekcji to dwa wpisy.

    Bez tego dorzucenie w tej samej sekcji drugiego zdania z tym samym martwym
    cytatem wchodzilo by pod istniejacy wpis snapshotu i nikt by go nie zobaczyl.
    """
    baseline = {"xx/manual.yaml/krok_3_glowne_studio":
                ["bliski:send to ai≈send to the ai"]}
    nowe, martwe, znane = _z_trafieniami(
        [_trafienie(linia=100), _trafienie(linia=205)], baseline=baseline)
    assert nowe == {"xx/manual.yaml/krok_3_glowne_studio":
                    ["bliski:send to ai≈send to the ai"]}, nowe
    assert znane == 1 and not martwe, (znane, martwe)


def test_znane_trafienie_nie_blokuje():
    """Snapshot pokrywajacy stan = zero nowych, licznik do jednej linii raportu."""
    baseline = {"xx/manual.yaml/krok_3_glowne_studio":
                ["bliski:send to ai≈send to the ai"]}
    nowe, martwe, znane = _z_trafieniami([_trafienie()], baseline=baseline)
    assert not nowe and not martwe, (nowe, martwe)
    assert znane == 1, znane


def test_martwy_wpis_jest_raportowany():
    """Wpis, ktorego nie ma w skanie, wraca jako powod do skurczenia snapshotu."""
    baseline = {
        "xx/manual.yaml/krok_3_glowne_studio":
            ["bliski:send to ai≈send to the ai"],
        "xx/tales.yaml/krok_2_quick_start": ["bliski:new game≈new the game"],
    }
    nowe, martwe, znane = _z_trafieniami([_trafienie()], baseline=baseline)
    assert not nowe, nowe
    assert martwe == {"xx/tales.yaml/krok_2_quick_start":
                      ["bliski:new game≈new the game"]}, martwe
    assert znane == 1, znane


def test_zgubiony_snapshot_jest_surowy():
    """Brak pliku = kazde trafienie nowe (nie: kazde przepuszczone)."""
    nowe, _martwe, znane = _z_trafieniami([_trafienie()], baseline=None)
    assert nowe and znane == 0, (nowe, znane)


def test_uszkodzony_snapshot_nie_wysadza_bramki():
    """Niepoprawny JSON degraduje do pustego snapshotu, nie do wyjatku."""
    oryginalna = gd.BASELINE_BLISKICH_PATH
    with tempfile.TemporaryDirectory() as tmp:
        sciezka = Path(tmp) / "bliskie_cytaty_baseline.json"
        sciezka.write_text("{ to nie jest JSON", encoding="utf-8")
        gd.BASELINE_BLISKICH_PATH = sciezka
        try:
            assert gd.wczytaj_baseline_bliskich() == {}
        finally:
            gd.BASELINE_BLISKICH_PATH = oryginalna


def test_zacommitowany_snapshot_pokrywa_stan_paczek():
    """Snapshot w repozytorium musi byc AKTUALNY wobec dziewieciu paczek.

    Ten jeden test dotyka realnych `dictionaries/` - bo inaczej bramka moglaby
    wejsc do wydania z nieprzejrzanym trafieniem albo z martwym wpisem, a raport
    `--waliduj` zobaczylby to dopiero maintainer przy zamykaniu releasu.
    """
    assert gd.BASELINE_BLISKICH_PATH.is_file(), (
        f"brak {gd.BASELINE_BLISKICH_PATH.name} - bramka bylaby maksymalnie "
        f"surowa; wygeneruj go `--zapisz-baseline-cytatow`")
    nowe, martwe, znane = gd.bramka_bliskich_cytatow()
    assert not nowe, f"trafienia ponad snapshot: {nowe}"
    assert not martwe, f"martwe wpisy snapshotu (skurcz go): {martwe}"
    assert znane > 0, "snapshot pusty, a klasa nie zniknela sama z siebie"


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
