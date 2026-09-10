"""
test_zrodlo_pl_raz.py - Regresja: diagnoza paczki ZRODLOWEJ pada RAZ, nie raz
na jezyk (18.32).

Trzy kontrakty, wszystkie mierzone przez WYKONANIE na KOPII slownikow w katalogu
tymczasowym (`--slowniki`), zero sieci, zero dotykania repo:

  1. PRE-FLIGHT. Zepsuty przepis w `pl/rezyser/` zatrzymuje przebieg PRZED petla
     jezykow. Przed 18.32 kontrola stala w `waliduj_silnikiem`, wolanym per
     (jezyk, plik): jeden zepsuty plik dawal 8 identycznych zdan i werdykt
     „8 error(s) in total", ktory oskarzal osiem paczek DOCELOWYCH. W sciezce
     tlumaczacej ta sama walidacja jest wolana PO ZAPISIE, wiec placilismy za
     przeklad N jezykow, zeby dowiedziec sie N razy, ze zrodlo jest zepsute.
  2. KANONICZNE ZDANIE. Niepoprawny YAML w zrodle wraca zdaniem `dev_yaml`
     („cannot read ... continuing would mean working on data this tool never
     parsed"), a nie surowym tracebackiem - tryb `--tylko-walidacja` czytal
     zrodlo golym `open()` + `load()`.
  3. OSTRZEZENIE RAZ NA PRZEBIEG. Brak `rezyser.naglowek_*` w ZRODLOWYM
     `ui.yaml` to jedna usterka, nie N usterek. Nota o skutku dla konkretnej
     pary (jezyk, plik) zostaje per jezyk, bo tam jest na miejscu.

Test jest REGRESJA, nie tautologia: kontrakt 1 sprawdza rowniez, ze zdrowe
zrodlo przechodzi bez wyjatku i ze przy zepsutym NIE POJAWIA sie ani jedna linia
o paczce docelowej, a kontrakt 3 liczy OBA rodzaje komunikatow naraz (globalny
i per para) - gdyby dedup zjadl za duzo, licznik not per jezyk spadlby do zera.

Uruchom:  .venv/Scripts/python test_zrodlo_pl_raz.py
"""

import contextlib
import io
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import buduj_wielojezyczne_tryby as bwt

ZRODLO_REPO = Path(__file__).parent / "dictionaries"
PRZEPIS = "tryb_skrypt.yaml"
FRAZA_SILNIKA = "the engine does not load it as a recipe"
FRAZA_DEV_YAML = "continuing would mean working on data this tool never parsed"
FRAZA_ZRODLA = "has no `rezyser.naglowek_*`"


@contextlib.contextmanager
def _kopia_pl():
    """Kopia SAMEJ paczki `pl` w katalogu tymczasowym + przestawione `DICT_DIR`.

    Kopiujemy realna paczke, a nie atrape: pre-flight rozstrzyga SILNIKIEM
    (`przepisy_rezysera.zaladuj_przepis`), wiec test na recznie zlozonym YAML-u
    mierzylby wlasne wyobrazenie o walidacjach silnika, nie silnik.
    """
    katalog = Path(tempfile.mkdtemp())
    stary = bwt.DICT_DIR
    try:
        shutil.copytree(ZRODLO_REPO / "pl", katalog / "dictionaries" / "pl")
        bwt.DICT_DIR = katalog / "dictionaries"
        bwt.zapomnij_ostrzezenia_o_zrodle()
        yield bwt.DICT_DIR
    finally:
        bwt.DICT_DIR = stary
        bwt.zapomnij_ostrzezenia_o_zrodle()
        shutil.rmtree(katalog, ignore_errors=True)


def _zepsuj_etykiete(dict_dir: Path, nazwa: str = PRZEPIS) -> None:
    """Wyzerowanie `etykieta` - silnik odrzuca przepis, YAML zostaje poprawny."""
    plik = dict_dir / "pl" / "rezyser" / nazwa
    tekst = plik.read_text(encoding="utf-8")
    nowy = re.sub(r"^etykieta:.*$", 'etykieta: ""', tekst, count=1, flags=re.MULTILINE)
    assert nowy != tekst, "nie znaleziono pola `etykieta` do zepsucia"
    plik.write_text(nowy, encoding="utf-8", newline="")


def _dosyp_paczki_docelowe(dict_dir: Path, nazwa: str = PRZEPIS) -> list[str]:
    """Kopiuje przepis PL do KAZDEJ paczki docelowej. Zwraca liste kodow.

    Bez plikow docelowych `--tylko-walidacja` pomija jezyk („no target file"),
    wiec stary kod konczyl przebieg zerem i test mierzylby lagodniejszy ksztalt
    wady niz ten zmierzony w praktyce. Z plikami wchodzi w gre PELNY mnoznik:
    diagnoza zrodla raz na (jezyk, przepis).
    """
    zrodlo = dict_dir / "pl" / "rezyser" / nazwa
    kody = list(bwt.MAPA_JEZYKOW)
    for kod in kody:
        cel = dict_dir / kod / "rezyser" / nazwa
        cel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(zrodlo, cel)
    return kody


def _przebieg_walidacji(dict_dir: Path, nazwa: str = PRZEPIS) -> tuple[int, str]:
    """`main()` w trybie `--tylko-walidacja --wszystkie`. Zwraca (kod, log)."""
    argv = ["buduj_wielojezyczne_tryby.py", "--tylko-walidacja", "--wszystkie",
            "--przepisy", nazwa, "--slowniki", str(dict_dir)]
    buf = io.StringIO()
    stary_argv = sys.argv
    sys.argv = argv
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                kod = bwt.main() or 0
            except SystemExit as exc:
                kod = exc.code if isinstance(exc.code, int) else 1
                if isinstance(exc.code, str):
                    buf.write(exc.code + "\n")
    finally:
        sys.argv = stary_argv
    return kod, buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Pre-flight zatrzymuje przebieg przed petla jezykow
# ---------------------------------------------------------------------------
def test_zepsute_zrodlo_diagnozowane_raz():
    """Jeden zepsuty przepis PL = JEDNA diagnoza, zero linii o paczkach docelowych."""
    with _kopia_pl() as dict_dir:
        kody = _dosyp_paczki_docelowe(dict_dir)
        _zepsuj_etykiete(dict_dir)
        kod, log = _przebieg_walidacji(dict_dir)
        assert kod != 0, f"zepsute zrodlo musi konczyc sie bledem, kod={kod}"
        assert log.count(FRAZA_SILNIKA) == 1, (
            f"diagnoza zrodla ma padnac RAZ przy {len(kody)} jezykach, padla "
            f"{log.count(FRAZA_SILNIKA)}x:\n{log}")
        # Zaden jezyk docelowy nie ma prawa byc wymieniony - to nie jego wina.
        oskarzone = [k for k in kody if f"{k}/{PRZEPIS}" in log]
        assert not oskarzone, f"pre-flight oskarzyl paczki docelowe: {oskarzone}\n{log}"
        assert PRZEPIS in log and "pl/rezyser" in log, log
        # Werdykt tez nie ma prawa liczyc bledow paczkom docelowym.
        assert "error(s) in total" not in log, log


def test_zdrowe_zrodlo_przechodzi_preflight():
    """Nietkniete zrodlo: pre-flight milczy i praca idzie dalej."""
    with _kopia_pl() as dict_dir:
        bwt.sprawdz_zrodla_pl([PRZEPIS])   # brak wyjatku = kontrakt spelniony
        kod, log = _przebieg_walidacji(dict_dir)
        assert FRAZA_SILNIKA not in log, log
        # Brak paczek docelowych w kopii `pl`-only jest LEGALNY i raportowany
        # per jezyk ("no target file"), a nie jako usterka zrodla.
        assert kod == 0, f"zdrowe zrodlo bez celow ma konczyc sie zerem, kod={kod}\n{log}"


# ---------------------------------------------------------------------------
# 2. Niepoprawny YAML w zrodle = kanoniczne zdanie `dev_yaml`
# ---------------------------------------------------------------------------
def test_zepsuty_yaml_zrodla_daje_zdanie_dev_yaml():
    """Zamiast surowego tracebacku: zdanie o pliku, ktorego nie przeczytalismy."""
    with _kopia_pl() as dict_dir:
        (dict_dir / "pl" / "rezyser" / PRZEPIS).write_text(
            'id: skrypt\netykieta: "x\n  - zepsute: [\n', encoding="utf-8", newline="")
        kod, log = _przebieg_walidacji(dict_dir)
        assert kod != 0, kod
        assert FRAZA_DEV_YAML in log, log
        assert "Traceback" not in log, log


# ---------------------------------------------------------------------------
# 3. Ostrzezenie o paczce zrodlowej: raz na przebieg, nota per para zostaje
# ---------------------------------------------------------------------------
def test_ostrzezenie_o_zrodle_raz_a_nota_per_jezyk():
    """8 jezykow x 2 konsumentow naglowkow = 2 ostrzezenia i 8 not o skutku."""
    with _kopia_pl() as dict_dir:
        ui_pl = dict_dir / "pl" / "gui" / "ui.yaml"
        tekst = ui_pl.read_text(encoding="utf-8")
        bez_naglowkow = re.sub(r"^\s+naglowek_\w+:.*\n", "", tekst, flags=re.MULTILINE)
        assert bez_naglowkow != tekst, "nie znaleziono kluczy `naglowek_*` w ui.yaml"
        ui_pl.write_text(bez_naglowkow, encoding="utf-8", newline="")
        assert bwt.naglowki_struktury("pl") == {}, "zrodlo mialo zostac bez naglowkow"

        # Paczki docelowe: minimalny `ui.yaml` z pelnym zestawem naglowkow, zeby
        # brakowala WYLACZNIE polowa zrodlowa (inaczej test mierzylby dwie
        # degradacje naraz i nie wiedzialby, ktora zdedupowala).
        kody = list(bwt.MAPA_JEZYKOW)
        naglowki = "\n".join(f"  {k}: Naglowek{i}"
                             for i, k in enumerate(bwt._KLUCZE_NAGLOWKOW))
        for kod in kody:
            plik = dict_dir / kod / "gui" / "ui.yaml"
            plik.parent.mkdir(parents=True, exist_ok=True)
            plik.write_text(f"rezyser:\n{naglowki}\n", encoding="utf-8", newline="")

        regex_pl = r"(?i)\n*(?:Prolog|Rozdzial\s+\d+|Epilog)"
        buf = io.StringIO()
        noty = 0
        with contextlib.redirect_stdout(buf):
            for kod in kody:
                _regex, uwagi = bwt.wyprowadz_regex(regex_pl, kod)
                noty += len(uwagi)
                bwt._sprawdz_naglowki_struktury(
                    kod, PRZEPIS, 'prompt cytuje "Rozdzial 1"', "kappale 1")
        log = buf.getvalue()
        assert log.count(FRAZA_ZRODLA) == 2, (
            f"oczekiwano 2 ostrzezen o zrodle (po jednym na konsumenta), jest "
            f"{log.count(FRAZA_ZRODLA)} przy {len(kody)} jezykach:\n{log}")
        assert noty == len(kody), (
            f"nota o skutku dla pary ma zostac per jezyk: {noty} wobec {len(kody)}")


if __name__ == "__main__":
    bwt.tlumacz_rdzen.skonfiguruj_stdout()
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
