"""
test_cezar_szczelnosc.py - zadna litera nie wychodzi z Cezara JAWNIE (v19.17).

Zmierzone 2026-11-09: pierscien Cezara paczki `it` (21 liter) przepuszczal
jawnie j k w x y, a paczki `is` (32 litery) c q w z - pre-pass ich nie lapie,
bo to zwykle ASCII, wiec "weekend" w szyfrogramie zostawial `w` i `k`.

Decyzja maintainera: pierscien rozszerzony w `szyfry/cezar.yaml` (pole
`alfabet`), a `podstawy.yaml::alfabet` zostaje natywny - jest tez detektorem
jezyka cyrylicy i granica pre-passu dla glosu. Kontrakty:
  * kazda litera a-z (po pre-passie paczki) lezy w pierscieniu;
  * natywny alfabet paczki jest PODCIAGIEM pierscienia - dopisane litery
    wchodza na swoje miejsca, natywna kolejnosc sie nie zmienia;
  * zakres przesuniecia w YAML pokrywa wszystkie rotacje: +-(n-1);
  * szyfr jest odwracalny na pelnym pierscieniu.

GUARDRAIL (decyzja maintainera 2026-11-09): PR, ktorego jedynym efektem jest
przywrocenie natywnego pierscienia (albo rosyjskiego bez lacinki) i czerwony
ten test - odrzucamy. PR z wartosciowym featurem/jezykiem, ktory przy okazji
cofa pierscienie - merge z przywroceniem pierscieni. Natywny pierscien to
sprawa KOPII ZAINSTALOWANEJ, gdzie pytest nie siega (CONTRIBUTING.md).

Uruchom:  .venv/Scripts/python -m pytest test_cezar_szczelnosc.py -q
"""

import string
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_poliglota as cp

PACZKI = sorted(cp.dostepne_jezyki_bazowe())


def _pierscien(kod: str) -> tuple[str, dict, dict]:
    cfg = cp.wariant_po_id(cp.TRYB_SZYFRANT, kod, "cezar")
    assert cfg is not None, f"{kod}: brak szyfry/cezar.yaml"
    podstawy = cp._zaladuj_podstawy(kod)
    return str(cfg.get("alfabet") or podstawy.get("alfabet") or ""), cfg, podstawy


def _cezar(tekst: str, kod: str, przes: int) -> str:
    return cp.przetworz(tekst, cp.TRYB_SZYFRANT, kod, "cezar",
                        {"przesuniecie": przes, "wymus_jezyk": kod})


@pytest.mark.parametrize("kod", PACZKI)
def test_kazda_litera_ascii_jest_w_pierscieniu(kod):
    pierscien, _, podstawy = _pierscien(kod)
    jawne = [z for z in string.ascii_uppercase
             if any(c.isalpha() and c.upper() not in pierscien
                    for c in cp._usun_polskie_znaki(z, podstawy))]
    assert not jawne, (f"{kod}: litery {jawne} wychodza z Cezara jawnie - "
                       f"dopisz je do `alfabet` w szyfry/cezar.yaml na ich "
                       f"miejscu w porzadku lacinskim")


@pytest.mark.parametrize("kod", PACZKI)
def test_szyfrogram_nie_zawiera_jawnych_liter(kod):
    """To samo zmierzone wykonaniem: przesuniecie 3, kazda litera osobno."""
    _, _, podstawy = _pierscien(kod)
    for z in string.ascii_lowercase:
        zrodlo = cp._usun_polskie_znaki(z, podstawy)
        wynik = _cezar(f"a {z} a", kod, 3).split()[1]
        assert wynik != zrodlo, f"{kod}: `{z}` -> `{wynik}` (jawnie)"


@pytest.mark.parametrize("kod", PACZKI)
def test_natywny_alfabet_jest_podciagiem_pierscienia(kod):
    pierscien, _, podstawy = _pierscien(kod)
    natywny = str(podstawy.get("alfabet") or "")
    it = iter(pierscien)
    assert all(z in it for z in natywny), \
        f"{kod}: pierscien {pierscien!r} zmienia kolejnosc alfabetu {natywny!r}"
    assert len(set(pierscien)) == len(pierscien), f"{kod}: duplikat w pierscieniu"


@pytest.mark.parametrize("kod", PACZKI)
def test_zakres_przesuniecia_pokrywa_pierscien(kod):
    pierscien, cfg, _ = _pierscien(kod)
    n = len(pierscien)
    assert (cfg.get("min_przesuniecie"), cfg.get("max_przesuniecie")) == (-(n - 1), n - 1), \
        f"{kod}: {n} liter, a zakres {cfg.get('min_przesuniecie')}..{cfg.get('max_przesuniecie')}"


@pytest.mark.parametrize("kod", PACZKI)
def test_cezar_odwracalny_na_pierscieniu(kod):
    pierscien, _, _ = _pierscien(kod)
    zrodlo = " ".join([pierscien, pierscien.lower()])
    for przes in (1, len(pierscien) // 2, len(pierscien) - 1):
        szyfr = _cezar(zrodlo, kod, przes)
        assert _cezar(szyfr, kod, -przes) == zrodlo, f"{kod}/{przes}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
