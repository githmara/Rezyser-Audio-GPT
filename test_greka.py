"""
test_greka.py - greka w pre-passie paczek i nazwy samotnych liter (v19.17).

Greka trafia do tekstu kazdej paczki: wzory (pi, delta), medycyna
(beta-blokery, mikrogramy), cytaty klasyczne. Do v19.17 przechodzila
pre-pass nietknieta, wiec akcent podawal glosowi obce litery, a szyfr
zostawial je jawnym tekstem w szyfrogramie.

Umowa (decyzja maintainera 2026-11-08):
  * litera, ktora jest JEDYNA litera wyrazu, w AKCENCIE, `oczyszczenie*`
    i przepuscie natywnym staje sie nazwa (`2pi`, `beta-blokery`), zeby glos
    przeczytal wzor (pomiar Cerence 2026-11-09: litera zostawiona glosowi jest
    przemilczana albo czytana "mikro pi" ze zmiana glosu);
  * kazda inna jest transliterowana tablica `polskie_znaki`;
  * SZYFR nazwy nigdy nie rozwija - po odszyfrowaniu zostaje transliteracja.

Od 2026-11-09 `oczyszczenie*` i przepust natywny dostaja PELNY pre-pass
paczki (takze obca lacinke), nie sama greke: teoria przepustu natywnego
obalona pomiarem - glos splaszcza albo przemilcza litery spoza swojego
jezyka. Wlasny alfabet paczki zostaje nietkniety.

Uruchom:  .venv/Scripts/python -m pytest test_greka.py -q
"""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import audyt_podstaw as ap
import core_poliglota as cp
import detektor_pism as dp

PACZKI = ["pl", "en", "de", "es", "fi", "fr", "is", "it", "ru"]
GREKA = set(cp.GRECKIE_MALE + cp.GRECKIE_WIELKIE)

ALFA, BETA, DELTA, MI, PI = (chr(0x03B1), chr(0x03B2), chr(0x0394),
                             chr(0x03BC), chr(0x03C0))


def _greka(tekst: str) -> str:
    return "".join(z for z in tekst if z in GREKA or z in cp.MAPA_WARIANTOW_GREKI)


def test_warianty_sprowadzane_do_liter_bazowych():
    """Tonos, politonik, symbol matematyczny, znak mikro i omu, kursywa."""
    oczekiwane = {
        chr(0x03AC): ALFA,             # alfa z tonosem
        chr(0x1FB3): ALFA,             # alfa z jota subscriptum
        chr(0x03D5): chr(0x03C6),      # symbol fi
        chr(0x00B5): MI,               # znak mikro z klawiatury
        chr(0x2126): chr(0x03A9),      # znak omu
        chr(0x1D6FC): ALFA,            # matematyczna kursywa alfa
        chr(0x03C2): chr(0x03C3),      # sigma koncowa
    }
    for znak, baza in oczekiwane.items():
        assert cp.MAPA_WARIANTOW_GREKI.get(znak) == baza, f"U+{ord(znak):04X}"


@pytest.mark.parametrize("kod", PACZKI)
def test_zadna_greka_nie_wychodzi_z_pre_passu(kod):
    podstawy = cp._zaladuj_podstawy(kod)
    for znak in sorted(GREKA | set(cp.MAPA_WARIANTOW_GREKI)):
        wynik = cp._usun_polskie_znaki(znak, podstawy)
        assert not _greka(wynik), f"{kod}: `{znak}` -> `{wynik}`"


@pytest.mark.parametrize("kod", PACZKI)
def test_kazda_paczka_ma_komplet_nazw(kod):
    podstawy = cp._zaladuj_podstawy(kod)
    nazwy = {w["wzor"] for w in podstawy["nazwy_liter"]}
    assert nazwy == set(cp.GRECKIE_MALE)


def test_akcent_rozwija_samotna_litere_i_transliteruje_reszte():
    tekst = f"Obwod to 2{PI}r, a 2{PI} to kat. {BETA}-blokery i 5 {MI}g, {DELTA}."
    wynik = cp.zastosuj_reguly_fonetyczne(tekst, "angielski", "pl")
    assert not _greka(wynik), wynik
    assert " pi " in wynik, f"samotne `2pi` bez nazwy albo sklejone: {wynik!r}"
    assert "beta-" in wynik, wynik
    assert "mg" in wynik and "mig" not in wynik, wynik
    assert "delta" in wynik.lower(), wynik
    # `2 pi r` bez spacji: pi ma sasiada-litere, wiec zostaje JEDNA litera `p`.
    assert "pr," in wynik and "pipr" not in wynik, wynik


def test_wielka_litera_dostaje_te_sama_nazwe():
    podstawy = cp._zaladuj_podstawy("pl")
    assert cp._rozwin_nazwy_liter(f"{DELTA} i {DELTA.lower()}", podstawy) \
        == "delta i delta"


@pytest.mark.parametrize("kod", ["pl", "ru"])
def test_szyfr_nigdy_nie_rozwija_nazwy(kod):
    """Po odszyfrowaniu samotna pi wraca JEDNA litera, nie nazwa."""
    opcje = {"przesuniecie": 3, "wymus_jezyk": kod}
    tekst = f"x {PI} x"
    szyfr = cp.przetworz(tekst, cp.TRYB_SZYFRANT, kod, "cezar", dict(opcje))
    assert not _greka(szyfr), f"greka jawnym tekstem w szyfrogramie: {szyfr!r}"
    odwrot = cp.przetworz(szyfr, cp.TRYB_SZYFRANT, kod, "cezar",
                          {**opcje, "przesuniecie": -3})
    srodek = odwrot.split()[1]
    assert len(srodek) == 1, f"{kod}: szyfr rozwinal nazwe: {odwrot!r}"


def test_litera_z_alfabetu_paczki_zostaje():
    """Przyszla paczka `el`: wlasna litera z tonosem nie jest splaszczana."""
    alfa_tonos = chr(0x03AC)
    podstawy = {"alfabet": cp.GRECKIE_WIELKIE + alfa_tonos.upper()}
    assert cp._sprowadz_greke(alfa_tonos, podstawy) == alfa_tonos


def _znaleziska(kod: str, dane: dict) -> list[tuple[str, str]]:
    wynik: list[tuple[str, str]] = []
    ap._sprawdz_greke(kod, dane, lambda k, s: wynik.append((k, s)))
    return wynik


@pytest.mark.parametrize("kod", PACZKI)
def test_bramka_czysta_na_paczkach(kod):
    assert _znaleziska(kod, ap.wczytaj_podstawy(kod)) == []


def test_bramka_lapie_wycieta_litere():
    dane = copy.deepcopy(ap.wczytaj_podstawy("pl"))
    dane["polskie_znaki"] = [w for w in dane["polskie_znaki"] if w["wzor"] != ALFA]
    assert [k for k, _ in _znaleziska("pl", dane)] == ["greka-dziura"]


def test_bramka_lapie_brak_nazwy_i_zly_ksztalt():
    dane = copy.deepcopy(ap.wczytaj_podstawy("pl"))
    dane["nazwy_liter"] = [w for w in dane["nazwy_liter"] if w["wzor"] != PI]
    dane["nazwy_liter"].append({"wzor": DELTA, "nazwa": "delta"})  # wielka
    klasy = sorted(k for k, _ in _znaleziska("pl", dane))
    assert klasy == ["nazwy-dziura", "nazwy-ksztalt"]


def test_bramka_lapie_nazwe_z_obcym_znakiem():
    dane = copy.deepcopy(ap.wczytaj_podstawy("en"))
    for w in dane["nazwy_liter"]:
        if w["wzor"] == ALFA:
            w["nazwa"] = "альфа"
    assert [k for k, _ in _znaleziska("en", dane)] == ["nazwy-cel-obcy"]


def test_bramka_bez_nazw_w_ogole():
    dane = copy.deepcopy(ap.wczytaj_podstawy("pl"))
    del dane["nazwy_liter"]
    assert [k for k, _ in _znaleziska("pl", dane)] == ["nazwy-dziura"]


# ---------------------------------------------------------------------------
# Tekst bez akcentu: narzedzie `oczyszczenie` i przepust natywny (2026-11-09)
# ---------------------------------------------------------------------------
# Pomiar maintainera na Cerence: grecka litera bez greckiego glosu jest
# przemilczana, z greckim glosem czytana "2 mikro pi" ze zmiana glosu - wiec
# greka nie moze dojsc do syntezatora takze wtedy, gdy akapit nie ma akcentu.

def _rezyser(jezyk, wariant, tekst, wymus=None):
    cfg = cp.wariant_po_id(cp.TRYB_REZYSER, jezyk, wariant)
    assert cfg is not None, f"{jezyk}/{wariant}"
    opcje = {"wymus_jezyk": wymus} if wymus else {}
    return cp._przetworz_rezyser(tekst, jezyk, cfg, opcje)


@pytest.mark.parametrize("kod", PACZKI)
@pytest.mark.parametrize("wariant", ["oczyszczenie", "oczyszczenie_bez_liczb"])
def test_oczyszczenie_nie_przepuszcza_greki(kod, wariant):
    tekst = f"2{PI} {BETA}-x {MI}g {DELTA} " + chr(0x03BB) + chr(0x03CC) + chr(0x03B3) + chr(0x03BF) + chr(0x03C2)
    wynik = _rezyser(kod, wariant, tekst, wymus=kod)
    assert not _greka(wynik), f"{kod}/{wariant}: {wynik!r}"


def test_oczyszczenie_rozwija_nazwy_przed_liczbami():
    wynik = _rezyser("pl", "oczyszczenie", f"Obwod to 2{PI}, a {BETA}-blokery i 5 {MI}g.", wymus="pl")
    assert "dwa pi" in wynik and "beta-blokery" in wynik and "mg" in wynik, wynik


def test_przepust_natywny_nie_przepuszcza_greki():
    """Akapit angielski pod akcentem `angielski` = przepust natywny."""
    wynik = _rezyser("pl", "angielski", f"Take {BETA}-blockers and 5 {MI}g of Mueller.", wymus="en")
    assert wynik == "Take beta-blockers and 5 mg of Mueller.", wynik


U_UML, S_HACEK, A_UML, O_UML, A_RING = (chr(0x00FC), chr(0x0161), chr(0x00E4),
                                         chr(0x00F6), chr(0x00E5))


def test_przepust_natywny_splaszcza_obca_lacinke():
    """Pelny pre-pass paczki (decyzja 2026-11-09): glos i tak splaszcza
    `Muller` albo przemilcza obca litere - pre-pass robi to deterministycznie."""
    wynik = _rezyser("pl", "angielski", f"M{U_UML}ller wrote {DELTA}.", wymus="en")
    assert U_UML not in wynik and wynik.endswith("ller wrote delta."), wynik


def test_przepust_natywny_zostawia_wlasny_alfabet():
    """Regresja v19.4.1: przepust nie moze zjesc liter WLASNEJ paczki."""
    tekst = f"P{A_UML}iv{A_UML} on h{O_UML}yry{A_RING} ja {S_HACEK}akki."
    wynik = _rezyser("pl", "finski", tekst, wymus="fi")
    alfabet = str(cp._zaladuj_podstawy("fi").get("alfabet") or "").lower()
    for z in (A_UML, O_UML, S_HACEK):
        if z in alfabet:
            assert z in wynik, f"fi stracil wlasne `{z}`: {wynik!r}"
        else:
            assert z not in wynik, f"fi przepuscil obce `{z}`: {wynik!r}"


@pytest.mark.parametrize("kod", PACZKI)
@pytest.mark.parametrize("wariant", ["oczyszczenie", "oczyszczenie_bez_liczb"])
def test_oczyszczenie_splaszcza_obca_lacinke(kod, wariant):
    """Litery spoza alfabetu paczki nie dochodza do glosu; wlasne zostaja."""
    podstawy = cp._zaladuj_podstawy(kod)
    alfabet = str(podstawy.get("alfabet") or "")
    wlasne = set(alfabet) | set(alfabet.lower())
    obce = [z for z in (U_UML, S_HACEK, A_UML, O_UML, A_RING) if z not in wlasne]
    tekst = " ".join(f"x{z}x" for z in (U_UML, S_HACEK, A_UML, O_UML, A_RING))
    wynik = _rezyser(kod, wariant, tekst, wymus=kod)
    if _dwupismowa(alfabet):
        # Paczka dwupismowa (ru): slowo lacinskie zostaje jak w zrodle, bo
        # tablica mapuje jego diakrytyki na cyrylice (audyt S1).
        assert wynik.split() == tekst.split(), wynik
        return
    for z in obce:
        assert z not in wynik, f"{kod}/{wariant}: obce `{z}` przeszlo: {wynik!r}"
    for z in set((U_UML, S_HACEK, A_UML, O_UML, A_RING)) - set(obce):
        assert z in wynik, f"{kod}/{wariant}: wlasne `{z}` zjedzone: {wynik!r}"


def _dwupismowa(alfabet: str) -> bool:
    return len({dp.pismo_znaku(z) for z in alfabet} - {None}) > 1


def _slowa_mieszane(tekst: str) -> list[str]:
    return [s for s in tekst.split()
            if len({dp.pismo_znaku(z) for z in s} - {None}) > 1]


@pytest.mark.parametrize("wariant", ["oczyszczenie", "oczyszczenie_bez_liczb"])
def test_ru_nie_tworzy_slow_z_dwoch_pism(wariant):
    """Audyt S1: `Walesa` z diakrytykami nie moze wyjsc jako `Waлэнsa`."""
    tekst = ("Президент Wa" + chr(0x0142) + chr(0x0119) + "sa приехал в M"
             + U_UML + "nchen, " + chr(0x010C) + "apek.")
    wynik = _rezyser("ru", wariant, tekst, wymus="ru")
    assert not _slowa_mieszane(wynik), wynik


def test_przepust_natywny_ru_nie_tworzy_slow_z_dwoch_pism():
    tekst = "Президент Wa" + chr(0x0142) + chr(0x0119) + "sa приехал."
    wynik = _rezyser("pl", "rosyjski", tekst, wymus="ru")
    assert not _slowa_mieszane(wynik), wynik


def test_wieloznakowy_wzor_nazwy_nie_wywraca_dokumentu():
    """Audyt S2: paczka edytowana recznie z `wzor: ou` - wpis pominiety."""
    podstawy = copy.deepcopy(cp._zaladuj_podstawy("pl"))
    podstawy["nazwy_liter"] = [{"wzor": "ou", "nazwa": "x"}, {"wzor": PI, "nazwa": "pi"}]
    assert cp._rozwin_nazwy_liter(f"a o b {PI}", podstawy) == "a o b pi"


def test_oczyszczenie_ru_daje_cyrylice():
    wynik = _rezyser("ru", "oczyszczenie", f"{PI} " + chr(0x03BB) + chr(0x03CC) + chr(0x03B3) + chr(0x03BF) + chr(0x03C2), wymus="ru")
    assert not _greka(wynik) and not any("a" <= z.lower() <= "z" for z in wynik), wynik


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
