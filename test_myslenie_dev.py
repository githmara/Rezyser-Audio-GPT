"""
test_myslenie_dev.py - płatne myślenie rodziny tłumaczy jest do przeczytania (audyt 19.20).

Pilnuje trzech rzeczy, których nie widzi żadna bramka treści:
  1. brat od AKCENTÓW (jedyny z `myslenie=True` w `tlumacz_rdzen`) prosi
     o streszczenie myślenia (`display: summarized`) - bez niego Sonnet 5.5
     oddaje myślenie pominięte, za które płacimy, a nie ma czego zapisać;
     streszczenie trafia do `skrypty/myslenie_akcent_*.md`, także po próbie
     zakończonej wyjątkiem, a plik poprzedniego przebiegu nie przeżywa nowego;
  2. odrzucone `reasoning` OpenRoutera rozpoznaje wskazane pole (`param`),
     a nie samo słowo w treści błędu (bliźniak ATA 2.0.1, Z1);
  3. pamięć odrzuceń `reasoning` ma effort w kluczu (bliźniak ATA 2.0.1, Z3):
     odrzucone `high` dev-toola nie zdejmuje `low` runtime'u.

Mock SDK, zero wywołań API.

Uruchom:  .venv/Scripts/python -m pytest test_myslenie_dev.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_myslenie_dev.py
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import buduj_wielojezyczne_akcenty as ak
import core_llm as cl
import tlumacz_rdzen as tr
from test_openrouter import _Sdk


class BadRequestError(Exception):
    """Nazwa klasy jak w SDK; `param` jak w `openai.APIError`."""

    def __init__(self, tresc: str, status: int = 400, param: str | None = None) -> None:
        super().__init__(tresc)
        self.status_code = status
        self.param = param


class RateLimitError(BadRequestError):
    """429 - nazwa klasy jak w SDK (`_czy_zla_struktura` patrzy na nazwę)."""


ODP = '{"translations": [{"id": 1, "target": "Talo"}]}'


class _Anthropic:
    """`messages.create`: kolejne odpowiedzi = tekst myślenia albo wyjątek."""

    def __init__(self, odpowiedzi: list) -> None:
        self.odpowiedzi = list(odpowiedzi)
        self.wyslane: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.wyslane.append(dict(kwargs))
        nastepna = self.odpowiedzi.pop(0)
        if isinstance(nastepna, Exception):
            raise nastepna
        bloki = [SimpleNamespace(type="thinking", thinking=nastepna)] if nastepna else []
        bloki.append(SimpleNamespace(type="text", text=ODP))
        return SimpleNamespace(content=bloki, stop_reason="end_turn")

    def with_options(self, **_kw):
        return self


def _rdzen(odpowiedzi: list, myslenie: bool = True, zbieraj: bool = True):
    sdk = _Anthropic(odpowiedzi)
    klient = cl.KlientLLM(cl.PROVIDER_ANTHROPIC, sdk)
    if zbieraj:
        klient.myslenie_zapis = []
    wynik = tr.wywolaj_llm(klient, model="claude-sonnet-5-5", system="T.",
                           nazwa_celu="Suomi", kod="fi",
                           pozycje=[(1, "pole", "Dom")], max_tokens=1000,
                           myslenie=myslenie)
    return wynik, klient, sdk.wyslane


@pytest.fixture(autouse=True)
def _czysta_pamiec_sesji():
    cl._BEZ_REASONING.clear()
    cl._BEZ_JSON_SCHEMA.clear()
    yield
    cl._BEZ_REASONING.clear()


# --- 1. rdzeń: myślenie akcentów czytelne i zbierane -------------------------
def test_rdzen_prosi_o_streszczenie_i_je_zbiera():
    wynik, klient, wyslane = _rdzen(["Rozważam pismo celu."])
    assert wynik == {1: "Talo"}
    assert wyslane[0]["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert klient.myslenie_zapis == ["Rozważam pismo celu."]


def test_rdzen_bez_zbierajacego_nie_pada():
    wynik, klient, _ = _rdzen(["Myślę."], zbieraj=False)
    assert wynik == {1: "Talo"} and klient.myslenie_zapis is None


def test_odrzucony_display_jedno_ponowienie_z_golym_adaptive():
    wynik, _, wyslane = _rdzen([
        BadRequestError("thinking.display: Extra inputs are not permitted"), "",
    ])
    assert wynik == {1: "Talo"}
    assert wyslane[1]["thinking"] == {"type": "adaptive"}


def test_bez_myslenia_nie_prosi_o_streszczenie():
    _, _, wyslane = _rdzen([""], myslenie=False)
    assert wyslane[0]["thinking"] != cl.MYSLENIE_CZYTELNE


# --- 1b. brat od akcentów: zapis obok draftu --------------------------------
def test_para_zapisuje_myslenie_takze_po_bledzie_i_sprzata_stare(tmp_path, monkeypatch):
    monkeypatch.setattr(ak, "ROOT", tmp_path)
    akcent = "testowy_nieistniejacy"
    stary = ak.sciezka_myslenia_pary("pl", akcent)
    stary.parent.mkdir(parents=True)
    stary.write_text("myślenie z poprzedniego przebiegu", encoding="utf-8")

    def _llm_bez_myslenia(klient, **_kw):
        raise RuntimeError("chunk padł")

    monkeypatch.setattr(ak.tlumacz_rdzen, "wywolaj_llm", _llm_bez_myslenia)
    klient = SimpleNamespace(myslenie_zapis=None)
    pary = ak.pary_akcentowe()
    assert ak.generuj_pare(klient, "pl", akcent, "fi", model="m", dry_run=False,
                           pary=pary, cp=None) is False
    assert not stary.exists()   # stare myślenie nie leży przy nowym przebiegu

    def _llm_mysli_i_pada(klient, **_kw):
        klient.myslenie_zapis.append("Reguła dla ä.")
        raise RuntimeError("chunk padł")

    monkeypatch.setattr(ak.tlumacz_rdzen, "wywolaj_llm", _llm_mysli_i_pada)
    assert ak.generuj_pare(klient, "pl", akcent, "fi", model="m", dry_run=False,
                           pary=pary, cp=None) is False
    tekst = ak.sciezka_myslenia_pary("pl", akcent).read_text(encoding="utf-8")
    assert "## Próba 1" in tekst and "Reguła dla ä." in tekst
    assert klient.myslenie_zapis is None


# --- 2. Z1: o odrzuceniu `reasoning` rozstrzyga wskazane pole ---------------
@pytest.mark.parametrize("blad, wynik", [
    (BadRequestError("json_schema unsupported with reasoning models",
                     param="response_format"), False),
    (BadRequestError("Invalid value", param="reasoning.effort"), True),
    (BadRequestError("Unrecognized request argument: reasoning"), True),
    (RateLimitError("Rate limited: reasoning", status=429), False),
])
def test_odrzucone_reasoning_rozpoznaje_pole(blad, wynik):
    assert cl._czy_odrzucono_reasoning(blad) is wynik


def test_cudze_pole_nie_zdejmuje_reasoning():
    sdk = _Sdk([
        BadRequestError("json_schema unsupported with reasoning", param="response_format"),
        ('{"opcje": []}', "stop"),
    ])
    klient = cl.KlientLLM(cl.PROVIDER_OPENROUTER, sdk)
    klient.myslenie_dev = "high"
    schemat = {"type": "object", "properties": {"opcje": {"type": "array"}}}
    cl.wywolaj_llm(klient, model="claude-sonnet-5-5", system="s",
                   messages=[{"role": "user", "content": "x"}], max_tokens=100,
                   temperature=1.0, timeout=5.0, schema_json=schemat, wymusz_json=True)
    wyslane = sdk.chat.completions.wyslane
    assert wyslane[1]["extra_body"] == {"reasoning": {"effort": "high"}}
    assert not cl._BEZ_REASONING


# --- 3. Z3: pamięć odrzuceń per effort --------------------------------------
def test_odrzucone_high_nie_zdejmuje_low():
    sdk = _Sdk([
        BadRequestError("Invalid value for reasoning.effort", param="reasoning.effort"),
        ("przeklad", "stop"),
        ("tekst", "stop"),
        ("przeklad 2", "stop"),
    ])
    klient = cl.KlientLLM(cl.PROVIDER_OPENROUTER, sdk)

    def _wywolaj():
        cl.wywolaj_llm(klient, model="claude-sonnet-5-5", system="s",
                       messages=[{"role": "user", "content": "x"}], max_tokens=100,
                       temperature=1.0, timeout=5.0)

    klient.myslenie_dev = "high"
    _wywolaj()
    klient.myslenie_dev = ""
    _wywolaj()
    klient.myslenie_dev = "high"
    _wywolaj()
    wyslane = sdk.chat.completions.wyslane
    assert wyslane[1].get("extra_body") is None                       # high zdjęte
    assert wyslane[2]["extra_body"] == {"reasoning": {"effort": "low"}}  # low żyje
    assert wyslane[3].get("extra_body") is None                       # high zapamiętane


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
