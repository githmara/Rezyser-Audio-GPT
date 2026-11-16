"""Sonda produkcyjnej ścieżki Sami (2026-11-17) — atrapy, zero sieci.

Otwór, który zamyka: żywe wywołanie z lokalnego golden_key.env meldowało zieleń
dla Sami, choć bot w produkcji czyta SEKRET repozytorium. Pilnujemy, że sonda
idzie tą samą funkcją co bot, czerwieni przy każdym błędzie, nie drukuje treści
błędu (publiczny log) i że workflow podaje jej właśnie sekret.
"""
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
SKRYPTY = ROOT / ".github" / "scripts"
sys.path.insert(0, str(SKRYPTY))

sami = importlib.import_module("issue_intake_sami")
sonda = importlib.import_module("sonda_sami")

KONCOWKA_KLUCZA = "Kq9z"


class _Odpowiedz:
    def __init__(self, tekst):
        wiad = type("M", (), {"content": tekst})()
        self.choices = [type("C", (), {"message": wiad, "finish_reason": "stop"})()]


class _BladAutoryzacji(Exception):
    status_code = 401


def _atrapa(monkeypatch, wynik):
    wywolania = []

    class _Klient:
        def __init__(self, api_key):
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            wywolania.append(kwargs)
            if isinstance(wynik, Exception):
                raise wynik
            return _Odpowiedz(wynik)

    import openai
    monkeypatch.setattr(openai, "OpenAI", _Klient)
    return wywolania


def test_sonda_wola_te_sama_funkcje_co_bot(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    wywolania = _atrapa(monkeypatch, "Helsinki")
    assert sonda.main() == 0
    (kw,) = wywolania
    assert kw["model"] == sami.MODEL_SAMI
    assert "temperature" not in kw
    assert sonda.sami.zapytaj_model is sami.zapytaj_model


def test_odmowa_klucza_to_czerwien_bez_tresci_bledu(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _atrapa(monkeypatch, _BladAutoryzacji(f"Incorrect API key provided: sk-****{KONCOWKA_KLUCZA}"))
    assert sonda.main() == 1
    wyj = capsys.readouterr().out
    assert "HTTP 401" in wyj
    assert KONCOWKA_KLUCZA not in wyj


@pytest.mark.parametrize("klucz, odpowiedz", [("", "Helsinki"), ("sk-test", ""), ("sk-test", "Oslo")])
def test_brak_sekretu_i_zla_odpowiedz_to_czerwien(monkeypatch, klucz, odpowiedz):
    monkeypatch.setenv("OPENAI_API_KEY", klucz)
    _atrapa(monkeypatch, odpowiedz)
    assert sonda.main() == 1


def test_workflow_podaje_sekret_i_ma_tylko_reczny_wyzwalacz():
    yml = (ROOT / ".github" / "workflows" / "sonda-sami.yml").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in yml
    assert "python .github/scripts/sonda_sami.py" in yml
    wyzwalacze = yml.split("on:", 1)[1].split("permissions:", 1)[0]
    assert wyzwalacze.split() == ["workflow_dispatch:"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
