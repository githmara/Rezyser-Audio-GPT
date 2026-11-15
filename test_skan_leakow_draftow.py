"""
test_skan_leakow_draftow.py - fail-open skanu PL-leakow na draftach (v19.20.0).

Do 19.19 oba post-procesory (`tlumacz_rdzen.zbierz_leaki` dla pieciu braci i
`buduj_wielojezyczne_docs._zbierz_leaki_draftow`) lapaly `except Exception`.
Tak przez trzy wydania ukrywal sie martwy `audyt_leakow._zbuduj_detektor`:
`AttributeError` zamienial sie w jedno ostrzezenie, a checklista meldowala
"0 kandydatow na leak" dla kazdego draftu.

Kontrakt od 19.20: blad srodowiska lub danych (import, plik, kodowanie, YAML)
-> ostrzezenie i dalej; kazdy inny wyjatek (blad KODU skanera) -> `raise`.

Uruchom:  .venv/Scripts/python -m pytest test_skan_leakow_draftow.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_skan_leakow_draftow.py
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

import audyt_leakow
import buduj_wielojezyczne_docs as bd
import tlumacz_rdzen


def _psuj_detektor(monkeypatch, wyjatek):
    def detektor_dla(kod):
        raise wyjatek
    monkeypatch.setattr(audyt_leakow, "detektor_dla", detektor_dla)


@pytest.mark.parametrize("wyjatek", [
    AttributeError("module 'audyt_leakow' has no attribute '_zbuduj_detektor'"),
    TypeError("wykryj_leaki_w_tekscie() missing 1 required positional argument"),
    NameError("name 'detektor' is not defined"),
])
def test_blad_kodu_leci_glosno_w_obu_post_procesorach(monkeypatch, capsys, wyjatek):
    _psuj_detektor(monkeypatch, wyjatek)
    with pytest.raises(type(wyjatek)):
        tlumacz_rdzen.zbierz_leaki({("fi", "x.yaml"): []}, {})
    with pytest.raises(type(wyjatek)):
        bd._zbierz_leaki_draftow([("fi", "x.yaml")])
    assert "checklist was NOT written" in capsys.readouterr().out


@pytest.mark.parametrize("wyjatek", [
    ImportError("No module named 'lingua'"),
    OSError("draft unreadable"),
    yaml.YAMLError("broken draft"),
])
def test_blad_srodowiska_jest_pomijany(monkeypatch, capsys, wyjatek):
    _psuj_detektor(monkeypatch, wyjatek)
    assert tlumacz_rdzen.zbierz_leaki({("fi", "x.yaml"): []}, {}) == {}
    assert bd._zbierz_leaki_draftow([("fi", "x.yaml")]) == {}
    out = capsys.readouterr().out
    assert out.count("audyt_leakow skipped for fi/x.yaml") == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
