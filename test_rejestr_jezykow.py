"""
test_rejestr_jezykow.py - Rejestr `jezyki_docelowe.yaml` niesie jawny prog rozdmuchania (19.8).

Decyzja maintainera 2026-09-23: zaakceptowany iloraz dlugosci przekladu dla
konkretnego jezyka zyje jako pole wpisu rejestru, nie w Pythonie. Kontrakty:

  1. Wpis ma dwa ksztalty: `kod: nazwa` i slownik `{nazwa, prog_rozdmuchania}`.
     Kazdy inny ksztalt, nieznane pole albo prog, ktory nie jest liczba > 1.0,
     PRZERYWA prace - do 19.8 wpis nie-napisowy byl po cichu pomijany, czyli
     jezyk wypadal z propagacji calej rodziny.
  2. `refresh_languages` zachowuje wpis-slownik przy zapisie (dawne `str(v)`
     utrwalilo by go jako napis „{'nazwa': ...}").
  3. `buduj_wielojezyczne_docs` stosuje prog z rejestru: sekcja z ilorazem
     miedzy domyslnym 1.40 a progiem jezyka PRZECHODZI, bez niego - nie.

Uruchom:  .venv/Scripts/python -m pytest test_rejestr_jezykow.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_rejestr_jezykow.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import refresh_languages
import tlumacz_rdzen
import test_cache_powtorki as tcp
import buduj_wielojezyczne_docs as bd


def _rejestr(katalog: Path, tresc: str) -> Path:
    (katalog / "jezyki_docelowe.yaml").write_text(tresc, encoding="utf-8")
    return katalog


DWA_KSZTALTY = "de: niemiecki\nfi:\n  nazwa: fiński\n  prog_rozdmuchania: 1.55\n"


def test_dwa_ksztalty_wpisu(tmp_path):
    katalog = _rejestr(tmp_path, DWA_KSZTALTY)
    assert tlumacz_rdzen.wczytaj_mape_jezykow(katalog) == {
        "de": "niemiecki", "fi": "fiński"}
    assert tlumacz_rdzen.wczytaj_progi_rozdmuchania(katalog) == {"fi": 1.55}


@pytest.mark.parametrize("tresc,fraza", [
    ("fi:\n  nazwa: fiński\n  prog_rozdmuchnia: 1.5\n", "unknown field"),
    ("fi:\n  prog_rozdmuchania: 1.5\n", "without a `nazwa:`"),
    ("fi:\n  nazwa: fiński\n  prog_rozdmuchania: 1.0\n", "above 1.0"),
    ("fi:\n  nazwa: fiński\n  prog_rozdmuchania: dużo\n", "above 1.0"),
    ("fi:\n  nazwa: fiński\n  prog_rozdmuchania: true\n", "above 1.0"),
    ("fi: [fiński]\n", "must be `code: name`"),
])
def test_zly_wpis_przerywa_prace(tmp_path, tresc, fraza):
    katalog = _rejestr(tmp_path, tresc)
    for czytnik in (tlumacz_rdzen.wczytaj_mape_jezykow,
                    tlumacz_rdzen.wczytaj_progi_rozdmuchania):
        with pytest.raises(SystemExit) as exc:
            czytnik(katalog)
        assert fraza in str(exc.value), exc.value


def test_refresh_zachowuje_wpis_slownik(tmp_path):
    katalog = _rejestr(tmp_path, DWA_KSZTALTY)
    stary = refresh_languages.REJESTR
    refresh_languages.REJESTR = katalog / "jezyki_docelowe.yaml"
    try:
        refresh_languages.zapisz_rejestr(refresh_languages.wczytaj_rejestr())
    finally:
        refresh_languages.REJESTR = stary
    assert tlumacz_rdzen.wczytaj_progi_rozdmuchania(katalog) == {"fi": 1.55}
    assert tlumacz_rdzen.wczytaj_mape_jezykow(katalog)["fi"] == "fiński"


def test_prog_z_rejestru_zmienia_werdykt_bramki():
    """Ten sam rozdmuchany przeklad: odrzucony przy 1.40, przyjety przy progu jezyka."""
    iloraz = len(tcp.TRESC_PL + tcp.DOSYPKA) / len(tcp.TRESC_PL)
    assert iloraz > bd.PROG_ROZDMUCHANIA, "stub musi rozdmuchiwac ponad domyslny prog"
    stare = dict(bd.PROGI_ROZDMUCHANIA)
    try:
        with tcp._srodowisko():
            bd.PROGI_ROZDMUCHANIA.clear()
            ok_domyslny, _ = tcp._przebieg()
        with tcp._srodowisko():
            bd.PROGI_ROZDMUCHANIA[tcp.KOD] = iloraz + 0.5
            ok_jawny, log = tcp._przebieg()
    finally:
        bd.PROGI_ROZDMUCHANIA.clear()
        bd.PROGI_ROZDMUCHANIA.update(stare)
    assert not ok_domyslny
    assert ok_jawny, log


# Uruchomienie jako skrypt - deleguje do pytesta (kanon v19.2.1, §6.11).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
