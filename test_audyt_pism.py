"""
test_audyt_pism.py - Bramka: zadne slowo w paczkach nie miesza dwoch pism (19.16).

Autotlumacz co jakis czas pisze fragment slowa w nie tym alfabecie: `ru` mial
od 18.24.2 „donастроить" w podreczniku (lacinskie „don" zamiast „до"), a paczka
Manaboomu - cyrylice w finskim slowie. Legalna cyrylica i greka (akcent
rosyjski w kazdej paczce, „Русский" w README, litery IPA /θ/) sa w danych
wszedzie, wiec bramka pyta o JEDNO slowo z liter dwoch pism naraz.

Testy sprawdzaja detektor (`tlumacz_bramki`), oba wyjatki konstrukcyjne (pole
`alfabet`, sekwencje regexa) na sztucznej paczce w katalogu tymczasowym oraz
sama bramke na prawdziwym drzewie `dictionaries/`. Powtorke w rdzeniu
tlumaczy sprawdza `test_openrouter.py` (tam zyje atrapa SDK).

Uruchom:  .venv/Scripts/python -m pytest test_audyt_pism.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_audyt_pism.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import audyt_pism
import tlumacz_bramki as tb


@pytest.mark.parametrize("tekst, slowo", [
    ("может donастроить существующий", "donастроить"),   # zlapane w ru 19.16
    ("Hän sanoi kiitоs", "kiitоs"),                     # cyrylickie „о"
    ("καλημέρa", "καλημέρa"),                           # lacinskie „a" w grece
])
def test_slowo_z_dwoch_pism_wykryte(tekst, slowo):
    assert tb.slowa_mieszanego_pisma(tekst) == [slowo]


@pytest.mark.parametrize("tekst", [
    "Русский · English · Suomi",            # przelacznik jezykow README
    "the digraphs /θ/ /ð/, /ˈzøːnə/, /lʲ/",  # IPA: grecka litera osobno, modyfikatory
    "«Áèáëèîòåêà» zamiast «Библиотека»",     # przyklad naprawy kodowania
    "sch → ш, tsch → ч",                    # przyklady regul akcentu
    "уда́рение",                             # akcent wyrazowy U+0301 nie rozcina slowa
    "iPhone, Müller, Ærø — 59 знаков",
])
def test_legalne_obce_pismo_nie_jest_trafieniem(tekst):
    assert tb.slowa_mieszanego_pisma(tekst) == []


def test_sekwencje_regexa_nie_sklejaja_sie_ze_slowem():
    wzor = chr(92) + "bт" + chr(92) + ".?" + chr(92) + "s*д" + chr(92) + "b"
    assert tb.slowa_mieszanego_pisma(wzor) == []


def test_nowe_slowa_tylko_spoza_zrodla():
    assert tb.nowe_slowa_mieszanego_pisma("cytat «Шkoda»", "цитата «Шkoda»") == []
    assert tb.nowe_slowa_mieszanego_pisma("dostroić", "donастроить") == ["donастроить"]


@pytest.fixture
def paczka(tmp_path):
    """Sztuczne `dictionaries/` z jednym trafieniem i oboma wyjatkami."""
    katalog = tmp_path / "dictionaries" / "xx"
    katalog.mkdir(parents=True)
    (katalog / "podstawy.yaml").write_text(
        'alfabet: "АБВABC"\nopis: "zwykły tekst"\n', encoding="utf-8")
    (katalog / "regula.yaml").write_text(
        "zamiany:\n  - { wzor: '" + chr(92) + "bул" + chr(92) + ".?', zamiana: 'улица' }\n"
        "opis: |\n  można donастроить akcent\n",
        encoding="utf-8")
    return tmp_path / "dictionaries"


def test_bramka_lapie_slowo_i_szanuje_wyjatki(paczka, tmp_path):
    assert audyt_pism.zbierz(paczka) == {
        "dictionaries/xx/regula.yaml": ["opis|donастроить"],
    }
    wynik = audyt_pism.bramka(paczka, baseline=tmp_path / "brak.json")
    assert not wynik.czysto


def test_bramka_przepuszcza_trafienie_z_baseline(paczka, tmp_path):
    baseline = tmp_path / "baseline.json"
    audyt_pism.al.zapisz_baseline(audyt_pism.zbierz(paczka), baseline)
    assert audyt_pism.bramka(paczka, baseline=baseline).czysto


def test_pusty_zakres_to_blad_a_nie_czysto(tmp_path):
    with pytest.raises(SystemExit):
        audyt_pism.bramka(tmp_path / "dictionaries", baseline=tmp_path / "b.json")


def test_prawdziwe_paczki_sa_czyste():
    assert len(audyt_pism.pliki_skanu()) > 100
    wynik = audyt_pism.bramka()
    assert wynik.czysto, wynik.nowe


# Uruchomienie jako skrypt - deleguje do pytesta (kanon v19.2.1, §6.11).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
