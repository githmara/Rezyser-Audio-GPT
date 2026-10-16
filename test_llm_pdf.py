"""
test_llm_pdf.py — `core_llm.wywolaj_llm_z_pdf`: PDF w treści wywołania (v19.14).

Kontrakt odczytu stron bez warstwy tekstu modelem z obrazem, per provider:
  1. anthropic: blok `document` (base64, application/pdf) MIĘDZY kontekstem
     a instrukcją, ta sama drabina `thinking` co `wywolaj_llm`
     (`between_tools` na Sonnet 5.5), bez niedomyślnej `temperature`;
  2. openrouter: część `file` z data URL, parser `native` (bez niego
     OpenRouter sam dobiera silnik, a `pdf-text` ze skanu oddaje pustkę),
     `reasoning` low (wyłączyć się nie da, domyślne = 2× tokenów wyjścia);
     odrzucone `reasoning` = jedno ponowienie bez niego, inny 400 = bez
     ponowień;
  3. openai_compat: `BladFunkcjiNiedostepnej` PRZED jakimkolwiek wywołaniem;
  4. mapa błędów wspólna z `wywolaj_llm` (`_opakuj_blad`): limit, nieznany
     model; odmowa wraca jako `stop_reason`, nie jako pusty tekst.

Mock SDK, zero wywołań API.

Uruchom:  .venv/Scripts/python -m pytest test_llm_pdf.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_llm_pdf.py
"""

import base64
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_llm as cl

# Izolacja autocache samplingu jak w test_openrouter.
cl._sciezka_cache_samplingu = lambda: str(
    Path(tempfile.gettempdir()) / "test_llm_pdf_sampling.json")
cl._NAUCZONE_BEZ_TEMPERATURY = set()

PDF = b"%PDF-1.7 atrapa jednej strony"


class BadRequestError(Exception):
    """Nazwa klasy jak w SDK — `_czy_zla_struktura` patrzy też na nazwę."""

    def __init__(self, tresc: str, status: int = 400) -> None:
        super().__init__(tresc)
        self.status_code = status


class RateLimitError(Exception):
    status_code = 429


class _Sdk:
    """Wspólna atrapa obu SDK: `messages.create` i `chat.completions.create`."""

    def __init__(self, odpowiedzi: list) -> None:
        self.odpowiedzi = list(odpowiedzi)
        self.wyslane: list[dict] = []
        self.messages = SimpleNamespace(create=self._anthropic)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._openai))

    def with_options(self, **_kw):
        return self

    def _nastepna(self, kwargs):
        self.wyslane.append(kwargs)
        nastepna = self.odpowiedzi.pop(0)
        if isinstance(nastepna, Exception):
            raise nastepna
        return nastepna

    def _anthropic(self, **kwargs):
        tekst, stop = self._nastepna(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=tekst)] if tekst else [],
            stop_reason=stop,
            usage=SimpleNamespace(input_tokens=2000, output_tokens=500))

    def _openai(self, **kwargs):
        tekst, finish = self._nastepna(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=tekst, refusal=None),
            finish_reason=finish)])


def _klient(provider, odpowiedzi, model_override=""):
    sdk = _Sdk(odpowiedzi)
    return cl.KlientLLM(provider, sdk, model_override=model_override), sdk


def _wywolaj(klient, **extra):
    return cl.wywolaj_llm_z_pdf(
        klient, model="claude-sonnet-5-5", system="SYS", pdf=PDF,
        tekst_po="Transcribe the attached page.", max_tokens=8000, timeout=60,
        **extra)


# ------------------------------------------------------------ anthropic ---

def test_anthropic_dokument_miedzy_kontekstem_a_instrukcja():
    klient, sdk = _klient(cl.PROVIDER_ANTHROPIC, [("# Tytul", "end_turn")])
    assert _wywolaj(klient, tekst_przed="<previous_page>x</previous_page>") \
        == ("# Tytul", "end_turn")
    kw = sdk.wyslane[0]
    typy = [b["type"] for b in kw["messages"][0]["content"]]
    assert typy == ["text", "document", "text"]
    zrodlo = kw["messages"][0]["content"][1]["source"]
    assert zrodlo["media_type"] == "application/pdf"
    assert base64.standard_b64decode(zrodlo["data"]) == PDF
    assert kw["system"] == "SYS" and kw["model"] == "claude-sonnet-5-5"
    assert kw["thinking"] == {"type": "between_tools"}
    assert klient.udane


def test_anthropic_bez_kontekstu_nie_wysyla_pustego_bloku():
    # Pusty blok `text` to 400 w API — strona pierwsza nie ma poprzedniej.
    klient, sdk = _klient(cl.PROVIDER_ANTHROPIC, [("ok", "end_turn")])
    _wywolaj(klient)
    typy = [b["type"] for b in sdk.wyslane[0]["messages"][0]["content"]]
    assert typy == ["document", "text"]


def test_anthropic_odmowa_wraca_jako_stop_reason():
    klient, _ = _klient(cl.PROVIDER_ANTHROPIC, [("", "refusal")])
    assert _wywolaj(klient) == ("", cl.STOP_ODRZUCENIE)


def test_anthropic_limit_to_blad_limitu():
    klient, _ = _klient(cl.PROVIDER_ANTHROPIC, [RateLimitError("429")])
    with pytest.raises(cl.BladLimituLLM):
        _wywolaj(klient)


# ----------------------------------------------------------- openrouter ---

def test_openrouter_plik_parser_native_i_reasoning_low():
    klient, sdk = _klient(cl.PROVIDER_OPENROUTER, [("# Tytul", "stop")])
    assert _wywolaj(klient, tekst_przed="ctx") == ("# Tytul", "stop")
    kw = sdk.wyslane[0]
    assert kw["model"] == "anthropic/claude-sonnet-5.5"
    assert kw["messages"][0] == {"role": "system", "content": "SYS"}
    czesci = kw["messages"][1]["content"]
    assert [c["type"] for c in czesci] == ["text", "file", "text"]
    url = czesci[1]["file"]["file_data"]
    assert url.startswith("data:application/pdf;base64,")
    assert base64.standard_b64decode(url.split(",", 1)[1]) == PDF
    assert kw["extra_body"] == {
        "plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}],
        "reasoning": {"effort": "low"},
    }
    assert "temperature" not in kw


def test_openrouter_odrzucone_reasoning_jedno_ponowienie_bez_niego():
    klient, sdk = _klient(cl.PROVIDER_OPENROUTER, [
        BadRequestError("Reasoning is not supported for this model"), ("ok", "stop")])
    assert _wywolaj(klient) == ("ok", "stop")
    assert len(sdk.wyslane) == 2
    assert "reasoning" not in sdk.wyslane[1]["extra_body"]
    assert sdk.wyslane[1]["extra_body"]["plugins"][0]["pdf"]["engine"] == "native"


def test_openrouter_inny_400_bez_ponowien():
    klient, sdk = _klient(cl.PROVIDER_OPENROUTER, [BadRequestError("bad pdf"), ("ok", "stop")])
    with pytest.raises(BadRequestError):
        _wywolaj(klient)
    assert len(sdk.wyslane) == 1


def test_openrouter_nieznany_model_to_blad_modelu():
    klient, _ = _klient(cl.PROVIDER_OPENROUTER, [
        BadRequestError("anthropic/claude-sonnet-9 is not a valid model ID")])
    with pytest.raises(cl.BladModeluLLM):
        _wywolaj(klient)


def test_openrouter_content_filter_to_odmowa():
    klient, _ = _klient(cl.PROVIDER_OPENROUTER, [("", "content_filter")])
    assert _wywolaj(klient) == ("", cl.STOP_ODRZUCENIE)


# -------------------------------------------------------- openai_compat ---

def test_compat_odmawia_przed_wywolaniem():
    klient, sdk = _klient(cl.PROVIDER_OPENAI_COMPAT, [], model_override="gpt-x")
    with pytest.raises(cl.BladFunkcjiNiedostepnej) as exc:
        _wywolaj(klient)
    assert exc.value.provider == cl.PROVIDER_OPENAI_COMPAT
    assert sdk.wyslane == []


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
