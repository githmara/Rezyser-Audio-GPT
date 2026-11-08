"""
test_pogranicze_pism.py - litery POGRANICZA w pre-passie paczek (v19.17).

Detektor jezykow zna wylacznie jezyki paczek, wiec akapit ukrainski,
bialoruski czy kazachski jest rozpoznawany jako `ru` i idzie przez akcenty
paczki `ru` do glosu obcego. Do v19.17 litery spoza rosyjskiego alfabetu
(i, yi, ye, g z haczykiem...) przechodzily pre-pass nietkniete i akcent
polski wydawal cyrylice w srodku lacinki. To samo dotyczylo lacinki spoza
zakresu U+00C0-U+017F: rumunskie s/t z PRZECINKIEM i saamskie litery
inari/skolt.

Testy mierza dwie strony umowy:
  * SKUTEK w silniku - realny akcent na realnym tekscie nie wydaje
    zadnej litery pogranicza,
  * CZULOSC bramki `audyt_podstaw` - wyciecie jednej pary z paczki daje
    trafienie, a litera, ktora paczka deklaruje jako wlasna, nie daje.

Uruchom:  .venv/Scripts/python -m pytest test_pogranicze_pism.py -q
"""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import audyt_podstaw as ap
import core_poliglota as cp
import manager_regul_szablony as mrs

# Prawdziwy ukrainski akapit: wszystkie cztery litery wyrozniajace w obu
# wielkosciach, dlugi na tyle, zeby detektor go nie przepuscil jako zbyt krotki.
_UKRAINSKI = ("Київ є столицею України. Їхній ґанок стоїть біля річки, "
              "і діти грають там щодня. Ґудзик, Єва та Ірина теж там.")

_POGRANICZE = set(mrs.ZNAKI_POGRANICZA_CYRYLICY) | {
    z.upper() for z in mrs.ZNAKI_POGRANICZA_CYRYLICY}


def _cyrylica(tekst: str) -> str:
    return "".join(z for z in tekst if ap._czy_pismo_cyrylickie(z))


@pytest.mark.parametrize("akcent", ["polski", "angielski", "niemiecki", "finski"])
def test_ukrainski_akapit_nie_zostawia_cyrylicy_w_akcencie(akcent):
    """Ukrainski tekst przez akcent paczki `ru` wychodzi CALY w lacince."""
    opcje: dict = {}
    wynik = cp.przetworz(_UKRAINSKI, cp.TRYB_REZYSER, "ru", akcent, opcje)
    assert [s[0] for s in opcje["_segmenty_wynikowe"]] != ["ru"], \
        "akcent nie zostal nalozony - test nic by nie mierzyl"
    assert not _cyrylica(wynik), \
        f"{akcent}: cyrylica przezyla akcent: {_cyrylica(wynik)!r} w {wynik!r}"


def test_pre_pass_ru_obejmuje_cala_liste_pogranicza():
    """Kazda litera pogranicza znika w pre-passie `ru` i zostaje pismem paczki."""
    podstawy = cp._zaladuj_podstawy("ru")
    alfabet = set(podstawy["alfabet"]) | set(podstawy["alfabet"].lower())
    for znak in sorted(_POGRANICZE):
        cel = cp._usun_polskie_znaki(znak, podstawy)
        assert cel != znak, f"`{znak}` przechodzi pre-pass `ru` nietkniety"
        assert set(cel) <= alfabet, f"`{znak}` -> `{cel}`: cel spoza alfabetu `ru`"


def _znaleziska(kod: str, dane: dict, kontrola) -> list[tuple[str, str]]:
    wynik: list[tuple[str, str]] = []
    kontrola(kod, dane, lambda klasa, szczegol: wynik.append((klasa, szczegol)))
    return wynik


def test_bramka_lapie_wycieta_litere_cyrylicy():
    dane = copy.deepcopy(ap.wczytaj_podstawy("ru"))
    assert _znaleziska("ru", dane, ap._sprawdz_pokrycie_cyrylicy) == []
    dane["polskie_znaki"] = [w for w in dane["polskie_znaki"]
                             if w["wzor"] not in ("ї", "Ї")]
    trafienia = _znaleziska("ru", dane, ap._sprawdz_pokrycie_cyrylicy)
    assert [k for k, _ in trafienia] == ["cyrylica-dziura"]
    assert "ї" in trafienia[0][1] and "Ї" in trafienia[0][1]


def test_bramka_nie_wymaga_wlasnych_liter_paczki():
    """Przyszla paczka `uk` ma i/yi/ye/g w alfabecie i NIE musi ich splaszczac."""
    dane = copy.deepcopy(ap.wczytaj_podstawy("ru"))
    wlasne = ("і", "ї", "є", "ґ")
    dane["polskie_znaki"] = [w for w in dane["polskie_znaki"]
                             if w["wzor"].lower() not in wlasne]
    dane["alfabet"] += "".join(z.upper() for z in wlasne)
    assert _znaleziska("uk", dane, ap._sprawdz_pokrycie_cyrylicy) == []


def test_paczka_lacinska_nie_przechodzi_kontroli_cyrylicy():
    """Cyrylica w tekscie paczki lacinskiej to transliteracja CALEGO pisma."""
    dane = ap.wczytaj_podstawy("pl")
    assert _znaleziska("pl", dane, ap._sprawdz_pokrycie_cyrylicy) == []


@pytest.mark.parametrize("kod", ["pl", "en", "de", "es", "fi", "fr", "is", "it", "ru"])
def test_lacinka_pogranicza_wychodzi_z_pre_passu(kod):
    """Rumunskie s/t z przecinkiem i saamskie litery - w kazdej paczce."""
    podstawy = cp._zaladuj_podstawy(kod)
    for mala in mrs.ZNAKI_POGRANICZA_LACINKI:
        for znak in (mala, mala.upper()):
            assert cp._usun_polskie_znaki(znak, podstawy) != znak, \
                f"{kod}: `{znak}` przechodzi pre-pass nietkniety"


def test_bramka_lapie_wycieta_litere_lacinki_pogranicza():
    dane = copy.deepcopy(ap.wczytaj_podstawy("pl"))
    assert _znaleziska("pl", dane, ap._sprawdz_pokrycie_lacinki) == []
    dane["polskie_znaki"] = [w for w in dane["polskie_znaki"] if w["wzor"] != "ș"]
    trafienia = _znaleziska("pl", dane, ap._sprawdz_pokrycie_lacinki)
    assert [k for k, _ in trafienia] == ["lacinka-dziura"]
    assert "ș" in trafienia[0][1]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
