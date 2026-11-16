"""
test_stempel_wersji.py — numer wersji w docs/readme w trakcie cyklu (2026-11-16).

`VERSION` z jakimkolwiek sufiksem (`-WIP`) = cykl otwarty: generator zachowuje
w wygenerowanych plikach numer, który już noszą, więc docs da się regenerować
i commitować razem ze zmianą szablonu; commit wydania (bez sufiksu) zmienia
w nich tylko linie z numerem.

Uruchom:  .venv/Scripts/python -m pytest test_stempel_wersji.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_stempel_wersji.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import generuj_dokumentacje as gd  # noqa: E402

Z = gd._ZNACZNIK_WERSJI


@pytest.mark.parametrize("numer,sufiks", [
    ("19.20.0", False), ("19.20", False), ("19.20.0-WIP", True),
    ("19.20.0-vip", True), ("19.20.0rc1", True), ("?", True),
])
def test_co_jest_sufiksem(numer, sufiks):
    assert gd.wersja_z_sufiksem(numer) is sufiks


def test_bez_sufiksu_stempluje_numer():
    tresc, bez = gd._stempluj_wersje(f"<h1>App ({Z} – Release)</h1>\nx", "<h1>App (1.0.0 – Release)</h1>", "2.0.0")
    assert tresc == "<h1>App (2.0.0 – Release)</h1>\nx" and bez == []


def test_z_sufiksem_linia_zostaje_jak_w_starym_pliku():
    stara = "<title>App (19.19.0 – Release)</title>\nstary akapit\n<h1>App (19.19.0 – Release)</h1>"
    nowa = f"<title>App ({Z} – Release)</title>\nnowy akapit\n<h1>App ({Z} – Release)</h1>"
    tresc, bez = gd._stempluj_wersje(nowa, stara, "19.20.0-WIP")
    assert tresc == "<title>App (19.19.0 – Release)</title>\nnowy akapit\n<h1>App (19.19.0 – Release)</h1>"
    assert bez == []


def test_z_sufiksem_zmieniony_naglowek_bierze_numer_z_sparowanej_linii():
    stara = "Version: **19.19.0** · 9 languages\n<h1>Stary tytuł 19.19.0</h1>"
    nowa = f"Version: **{Z}** · 9 languages\n<h1>Nowy tytuł {Z}</h1>"
    tresc, bez = gd._stempluj_wersje(nowa, stara, "19.20.0-WIP")
    assert tresc == "Version: **19.19.0** · 9 languages\n<h1>Nowy tytuł 19.19.0</h1>" and bez == []


def test_z_sufiksem_nowy_plik_dostaje_numer_z_sufiksem_i_zgloszenie():
    tresc, bez = gd._stempluj_wersje(f"<h1>App {Z}</h1>", None, "19.20.0-WIP")
    assert tresc == "<h1>App 19.20.0-WIP</h1>" and bez == ["<h1>App 19.20.0-WIP</h1>"]


def test_znacznik_nigdy_nie_zostaje_w_wyniku():
    for numer in ("1.0.0", "1.1.0-WIP"):
        tresc, _ = gd._stempluj_wersje(f"a {Z}\nb {Z} {Z}", "a 1.0.0\nb 1.0.0 1.0.0", numer)
        assert Z not in tresc


def test_cykl_generatora_od_wydania_do_wydania(tmp_path, monkeypatch):
    """Wydanie → WIP (tylko treść) → wydanie (tylko linie z numerem), na prawdziwych szablonach.

    Katalog tymczasowy przy prawdziwych słownikach = przebieg porównawczy,
    więc readme też ląduje w `tmp_path` (bramka higieny pilnuje korzenia repo).
    """

    def przebieg(numer: str) -> dict[str, str]:
        monkeypatch.setattr(gd, "NUMER_WERSJI", numer)
        pliki = gd.generuj(tmp_path, cicho=True)
        assert pliki
        return {p.name: p.read_text(encoding="utf-8") for p in pliki}

    wydanie = przebieg("1.2.3")
    assert all(Z not in t for t in wydanie.values())
    assert sum("1.2.3" in t for t in wydanie.values()) >= 9

    w_cyklu = przebieg("1.3.0-WIP")
    assert w_cyklu == wydanie, "regeneracja w cyklu zmieniła plik mimo braku zmian szablonu"

    nastepne = przebieg("1.3.0")
    for nazwa, tresc in nastepne.items():
        roznice = [(a, b) for a, b in zip(wydanie[nazwa].split("\n"), tresc.split("\n")) if a != b]
        assert all(a.replace("1.2.3", "1.3.0") == b for a, b in roznice), (nazwa, roznice[:2])
        assert ("1.2.3" in wydanie[nazwa]) == bool(roznice), nazwa


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
