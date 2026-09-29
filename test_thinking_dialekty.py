"""test_thinking_dialekty.py - "bez myslenia" w dialekcie modelu (migracja Sonnet 5.5, v19.9).

Sonnet 5.5 odrzuca `thinking={"type": "disabled"}` (400) i chce `between_tools`;
kazdy inny model odrzuca `between_tools`; Opus 5.5 / Fable nie pozwalaja
wylaczyc myslenia wcale. Kontrakty, wszystkie przez WYKONANIE na atrapie SDK
(zero sieci):

  1. payload startowy trafia w dialekt modelu (oba klienty: `core_llm`
     i `tlumacz_rdzen`), wiec domyslny model nie placi jalowym 400;
  2. 400 na jednym dialekcie -> nastepny, NIGDY dwa razy ten sam (bez petli),
     a po wyczerpaniu - oryginalny wyjatek;
  3. komunikat 400 o `disabled` wspomina `output_config` - NIE moze zdjac
     structured outputs (regresja kolejnosci w `_co_odrzucono`);
  4. tryb quality = adaptive + effort (nie `budget_tokens`, ktory jest 400
     od Sonnet 5), a jego odrzucenie schodzi na "bez myslenia" bez effort.
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

import core_llm as cl

# Tresc wzieta z przewodnika migracji Anthropic (Sonnet 5.5, breaking change 1).
BLAD_DISABLED = (
    '"thinking.type.disabled" is not supported for this model. Use '
    '"thinking.type.between_tools" for the lowest thinking setting, or '
    '"thinking.type.adaptive" and "output_config.effort" to control thinking '
    'behavior.'
)
BLAD_BETWEEN = '"thinking.type.between_tools" is not supported for this model.'
BLAD_BUDGET = (
    '"thinking.type.enabled" is not supported for this model. Use '
    '"thinking.type.adaptive" and "output_config.effort" to control thinking.'
)
SCHEMAT = {"type": "object", "properties": {"a": {"type": "string"}},
           "required": ["a"], "additionalProperties": False}


class _Blad400(Exception):
    status_code = 400

    def __init__(self, tresc):
        super().__init__(f"Error code: 400 - {tresc}")


class _MockSDK:
    def __init__(self, odpowiedzi, wyslane):
        self._odpowiedzi = list(odpowiedzi)
        self._wyslane = wyslane
        self.messages = self

    def with_options(self, **_kwargs):
        return self

    def create(self, **kwargs):
        # Kopia: drabina mutuje kwargs miedzy probami.
        self._wyslane.append(json.loads(json.dumps(kwargs)))
        pozycja = self._odpowiedzi.pop(0)
        if isinstance(pozycja, Exception):
            raise pozycja
        resp = SimpleNamespace(
            content=[SimpleNamespace(type="thinking", thinking=""),
                     SimpleNamespace(type="text", text=pozycja)],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
        resp._request_id = "req_TEST"
        return resp


def _anthropic(model, odpowiedzi, **extra):
    wyslane = []
    klient = cl.KlientLLM(provider=cl.PROVIDER_ANTHROPIC,
                          sdk=_MockSDK(odpowiedzi, wyslane))
    tekst, _stop = cl._wywolaj_anthropic(
        klient, model, "System.", [{"role": "user", "content": "Hi"}],
        max_tokens=1000, temperature=0.85, timeout=30.0, **extra)
    return tekst, wyslane


def _rdzen(model, odpowiedzi):
    import tlumacz_rdzen as tr

    wyslane = []
    odp = json.dumps({"translations": [{"id": 1, "target": "Talo"}]})
    mapa = tr.wywolaj_llm(
        _MockSDK([o if isinstance(o, Exception) else odp for o in odpowiedzi],
                 wyslane),
        model=model, system="Translate.", nazwa_celu="Suomi", kod="fi",
        pozycje=[(1, "pole", "Dom")], max_tokens=1000,
    )
    return mapa, wyslane


# --- 1. dialekt startowy ----------------------------------------------------

def test_dialekt_per_model():
    assert cl.thinking_bez_myslenia("claude-sonnet-5-5") == {"type": "between_tools"}
    # Kolizja prefiksow: `claude-sonnet-5` NIE moze dostac dialektu 5.5.
    assert cl.thinking_bez_myslenia("claude-sonnet-5") == {"type": "disabled"}
    assert cl.thinking_bez_myslenia("claude-haiku-4-5") == {"type": "disabled"}
    assert cl.thinking_bez_myslenia("claude-opus-5-5") is None
    assert cl.thinking_bez_myslenia("claude-fable-5-1") is None
    # Opus 5 (bez `-5`) to wciaz `disabled` - kolizja prefiksow w druga strone.
    assert cl.thinking_bez_myslenia("claude-opus-5") == {"type": "disabled"}


def test_core_llm_sonnet55_jedna_proba_between_tools():
    tekst, wyslane = _anthropic("claude-sonnet-5-5", ["ok"])
    assert tekst == "ok", "the thinking block leaked into the text"
    assert len(wyslane) == 1
    assert wyslane[0]["thinking"] == {"type": "between_tools"}
    assert "extra_body" not in wyslane[0], "temperature sent to a model that rejects it"


def test_core_llm_opus55_bez_parametru_thinking():
    _t, wyslane = _anthropic("claude-opus-5-5", ["ok"])
    assert len(wyslane) == 1 and "thinking" not in wyslane[0]


def test_rdzen_sonnet55_jedna_proba_between_tools():
    mapa, wyslane = _rdzen("claude-sonnet-5-5", ["ok"])
    assert mapa == {1: "Talo"} and len(wyslane) == 1
    assert wyslane[0]["thinking"] == {"type": "between_tools"}


def test_rdzen_stary_model_dalej_disabled():
    _m, wyslane = _rdzen("claude-sonnet-5", ["ok"])
    assert wyslane[0]["thinking"] == {"type": "disabled"}


# --- 2. drabina bez petli -----------------------------------------------------

def test_rozpoznanie_thinking_przed_output_config():
    assert cl._co_odrzucono(_Blad400(BLAD_DISABLED)) == "thinking"
    assert cl._co_odrzucono(_Blad400(BLAD_BETWEEN)) == "thinking"
    assert cl.czy_odrzucono_thinking(_Blad400(BLAD_DISABLED))


def test_core_llm_nieznany_model_przechodzi_dialekty_po_kolei():
    _t, wyslane = _anthropic(
        "egzotyk-1", [_Blad400(BLAD_DISABLED), _Blad400(BLAD_BETWEEN), "ok"])
    assert [w.get("thinking") for w in wyslane] == [
        {"type": "disabled"}, {"type": "between_tools"}, None]


def test_core_llm_wyczerpane_dialekty_rzucaja_zamiast_petli():
    try:
        _anthropic("egzotyk-2", [_Blad400(BLAD_DISABLED)] * 3 + ["ok"])
    except _Blad400:
        return
    raise AssertionError("after all three variants the original error must propagate")


def test_blad_disabled_nie_zdejmuje_structured_outputs():
    _t, wyslane = _anthropic(
        "egzotyk-3", [_Blad400(BLAD_DISABLED), "ok"], schema_json=SCHEMAT)
    assert len(wyslane) == 2
    assert "format" in wyslane[1]["output_config"], "the thinking 400 cost structured outputs"


def test_rdzen_nieznany_model_przechodzi_dialekty():
    _m, wyslane = _rdzen("egzotyk-4", [_Blad400(BLAD_DISABLED), "ok"])
    assert [w.get("thinking") for w in wyslane] == [
        {"type": "disabled"}, {"type": "between_tools"}]


def test_rdzen_wyczerpane_dialekty_rzucaja():
    try:
        _rdzen("egzotyk-5", [_Blad400(BLAD_DISABLED)] * 3 + ["ok"])
    except _Blad400:
        return
    raise AssertionError("tlumacz_rdzen must not loop on thinking rejections")


# --- 3. tryb quality -----------------------------------------------------------

def test_quality_to_adaptive_z_effort_a_nie_budget():
    _t, wyslane = _anthropic("claude-sonnet-5-5", ["ok"], thinking_budget=4096)
    w = wyslane[0]
    assert w["thinking"] == {"type": "adaptive"}
    assert w["output_config"]["effort"] == cl.EFFORT_QUALITY
    assert w["max_tokens"] == 1000 + 4096
    assert "budget_tokens" not in json.dumps(w)


def test_quality_ze_schematem_trzyma_oba_pola():
    _t, wyslane = _anthropic("claude-sonnet-5-5", ["ok"], thinking_budget=4096,
                             schema_json=SCHEMAT)
    oc = wyslane[0]["output_config"]
    assert "format" in oc and oc["effort"] == cl.EFFORT_QUALITY


def test_odrzucone_quality_schodzi_na_bez_myslenia_bez_effort():
    _t, wyslane = _anthropic("claude-sonnet-5-5", [_Blad400(BLAD_BUDGET), "ok"],
                             thinking_budget=4096, schema_json=SCHEMAT)
    druga = wyslane[1]
    assert druga["thinking"] == {"type": "between_tools"}
    assert "effort" not in druga["output_config"] and "format" in druga["output_config"]
    assert druga["max_tokens"] == 1000


def test_odcisk_schematu_nie_zalezy_od_effort():
    slad_a, slad_b = [], []
    for slad, budzet in ((slad_a, 0), (slad_b, 4096)):
        klient = cl.KlientLLM(provider=cl.PROVIDER_ANTHROPIC,
                              sdk=_MockSDK(["ok"], []))
        cl._wywolaj_anthropic(
            klient, "claude-sonnet-5-5", "S.", [{"role": "user", "content": "x"}],
            max_tokens=10, temperature=1.0, timeout=5.0, thinking_budget=budzet,
            schema_json=SCHEMAT, slad=slad)
    assert slad_a[0]["schemat"] == slad_b[0]["schemat"] != "no"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
