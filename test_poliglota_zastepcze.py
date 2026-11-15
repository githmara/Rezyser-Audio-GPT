"""
test_poliglota_zastepcze.py — Poliglota: litery zastąpione przez generator PDF znakiem ■ (19.19).

Prawdziwy `PoliglotaPanel` bez `MainLoop` (to samo środowisko co
`test_poliglota_skany.py`: dialogi, wątek i `wx.CallAfter` synchroniczne),
model podmieniony na atrapę `core_zastepcze.odtworz`. Kontrakty:
  1. zgoda → tekst z odtworzonymi słowami + komunikat z liczbą słów;
  2. „Pomiń” → tekst ze znakami ■, ani jednego wywołania modelu;
  3. błąd modelu → komunikat, a plik i tak się wczytuje (ze znakami ■);
  4. PDF bez ■ albo provider bez odczytu → bez pytania o zgodę.

Uruchom:  .venv/Scripts/python -m pytest test_poliglota_zastepcze.py -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

wx = pytest.importorskip("wx")

import core_llm as cl  # noqa: E402
import core_pdf  # noqa: E402
import core_zastepcze as cz  # noqa: E402
from test_poliglota_skany import srodowisko  # noqa: E402,F401 — fixture

Z = cz.ZASTEPCZY
_TEKSTY: dict[str, str] = {}


@pytest.fixture(autouse=True)
def _wyciagnij(monkeypatch):
    # PDF z ■ i literami w jednym foncie da się zrobić tylko generatorem bez
    # fontu (tak powstał prawdziwy plik audytu, sprawdzony na żywo 2026-11-15);
    # PDFium oddaje wtedy ■ wprost — tu podajemy gotowy wynik `wyciagnij`.
    def wyciagnij(sciezka, postep=None, **_k):
        t = _TEKSTY[str(sciezka)]
        return core_pdf.WynikPdf([t], 1, akapity_stron=[[t]], znaki_stron=[len(t)])

    monkeypatch.setattr(core_pdf, "wyciagnij", wyciagnij)


def _pdf(tmp_path, tekst):
    p = tmp_path / f"audyt{len(_TEKSTY)}.pdf"
    p.write_bytes(b"%PDF-1.7")
    _TEKSTY[str(p)] = tekst
    return p


def _wczytaj(panel, sciezka):
    panel._txt_file.SetValue(str(sciezka))
    panel._on_load(None)


@pytest.fixture
def model(monkeypatch):
    wywolania = []

    def odtworz(klient, tekst, litery, slad=None):
        wywolania.append(tekst)
        return {f"G{Z}ÓWNEJ": "GŁÓWNEJ"}

    monkeypatch.setattr(cz, "odtworz", odtworz)
    return wywolania


def test_zgoda_odtwarza_slowa(srodowisko, tmp_path, model):
    panel, zapis = srodowisko
    _wczytaj(panel, _pdf(tmp_path, f"SALA G{Z}ÓWNEJ STACJI."))
    assert len(zapis.zgody) == 1 and f"G{Z}ÓWNEJ" in zapis.zgody[0]
    assert "Anthropic (api.anthropic.com)" in zapis.zgody[0]
    assert len(model) == 1
    assert "GŁÓWNEJ" in panel._file_content and Z not in panel._file_content
    assert any("Odtworzono litery w 1 z 1" in k for k in zapis.komunikaty)
    assert not panel._btn_load.IsEnabled()        # plik wczytany — jak dotąd


def test_pomin_zostawia_znaki(srodowisko, tmp_path, model):
    panel, zapis = srodowisko
    zapis.odpowiedz_zgody = wx.ID_NO
    _wczytaj(panel, _pdf(tmp_path, f"SALA G{Z}ÓWNEJ STACJI."))
    assert model == []
    assert f"G{Z}ÓWNEJ" in panel._file_content and panel._file_ext == ".txt"


def test_blad_modelu_mowi_i_wczytuje(srodowisko, tmp_path, monkeypatch):
    panel, zapis = srodowisko

    def pada(*_a, **_k):
        raise cl.BladTimeoutLLM("timeout")

    monkeypatch.setattr(cz, "odtworz", pada)
    _wczytaj(panel, _pdf(tmp_path, f"SALA G{Z}ÓWNEJ STACJI."))
    assert any("Nie udało się odtworzyć liter" in tresc for _t, tresc in zapis.dlugie)
    assert f"G{Z}ÓWNEJ" in panel._file_content and panel._file_ext == ".txt"
    assert not panel._btn_load.IsEnabled()


def test_bez_znakow_albo_bez_odczytu_bez_pytania(srodowisko, tmp_path, model):
    panel, zapis = srodowisko
    _wczytaj(panel, _pdf(tmp_path, "Zwykly tekst."))
    assert zapis.zgody == [] and model == []
    panel._file_content = ""
    panel._client = cl.KlientLLM(cl.PROVIDER_OPENAI_COMPAT, None, model_override="x")
    _wczytaj(panel, _pdf(tmp_path, f"SALA G{Z}ÓWNEJ STACJI."))
    assert zapis.zgody == [] and model == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
