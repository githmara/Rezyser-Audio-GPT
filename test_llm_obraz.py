"""
test_llm_obraz.py - `core_llm.wywolaj_llm_z_obrazem`: obraz w tresci wywolania (v19.21).

Obrazy wstawione w .docx ida do modelu JAKO OBRAZY (decyzja maintainera
2026-11-22: bez skladania jednostronicowego PDF-a). Kontrakt per provider:
  1. anthropic: blok `image` (base64, media type z SYGNATURY bajtow) miedzy
     kontekstem a instrukcja, ta sama drabina co `wywolaj_llm_z_pdf`;
  2. openrouter: czesc `image_url` z data URL, `reasoning` low, BEZ pluginu
     parsera plikow (ten dotyczy PDF-ow); odrzucone `reasoning` = jedno
     ponowienie bez niego;
  3. openai_compat: `BladFunkcjiNiedostepnej` przed wywolaniem;
  4. format spoza PNG/JPEG/GIF/WebP (EMF, BMP): `ValueError` przed wywolaniem.

Atrapy SDK z test_llm_pdf, zero wywolan API.

Uruchom:  .venv/Scripts/python -m pytest test_llm_obraz.py -q
"""

import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_llm as cl
from test_llm_pdf import BadRequestError, _klient

PNG = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"atrapa png"
JPG = bytes([255, 216, 255, 224]) + b"atrapa jpg"


def _wywolaj(klient, obraz=PNG, **extra):
    return cl.wywolaj_llm_z_obrazem(
        klient, model="claude-sonnet-5-5", system="SYS", obraz=obraz,
        tekst_po="Transcribe the attached image.", max_tokens=8000, timeout=60,
        **extra)


def test_anthropic_blok_image_z_typem_z_sygnatury():
    klient, sdk = _klient(cl.PROVIDER_ANTHROPIC, [("# Slajd", "end_turn")])
    assert _wywolaj(klient, obraz=JPG, tekst_przed="<previous_image>x</previous_image>") \
        == ("# Slajd", "end_turn")
    tresc = sdk.wyslane[0]["messages"][0]["content"]
    assert [b["type"] for b in tresc] == ["text", "image", "text"]
    assert tresc[1]["source"]["media_type"] == "image/jpeg"
    assert base64.standard_b64decode(tresc[1]["source"]["data"]) == JPG
    assert klient.udane


def test_anthropic_bez_kontekstu_bez_pustego_bloku():
    klient, sdk = _klient(cl.PROVIDER_ANTHROPIC, [("ok", "end_turn")])
    _wywolaj(klient)
    assert [b["type"] for b in sdk.wyslane[0]["messages"][0]["content"]] == ["image", "text"]


def test_openrouter_image_url_bez_pluginu_pdf():
    klient, sdk = _klient(cl.PROVIDER_OPENROUTER, [("ok", "stop")])
    _wywolaj(klient)
    kw = sdk.wyslane[0]
    czesci = kw["messages"][-1]["content"]
    assert czesci[0]["type"] == "image_url"
    assert czesci[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert kw["extra_body"] == {"reasoning": {"effort": "low"}}
    assert "temperature" not in kw


def test_openrouter_odrzucone_reasoning_jedno_ponowienie():
    klient, sdk = _klient(cl.PROVIDER_OPENROUTER, [
        BadRequestError("reasoning is not supported for this model"), ("ok", "stop")])
    assert _wywolaj(klient)[0] == "ok"
    assert len(sdk.wyslane) == 2 and "extra_body" not in sdk.wyslane[1]


def test_openai_compat_niedostepne_przed_wywolaniem():
    klient, sdk = _klient(cl.PROVIDER_OPENAI_COMPAT, [])
    with pytest.raises(cl.BladFunkcjiNiedostepnej):
        _wywolaj(klient)
    assert sdk.wyslane == []


def test_nieobslugiwany_format_przed_wywolaniem():
    klient, sdk = _klient(cl.PROVIDER_ANTHROPIC, [])
    with pytest.raises(ValueError):
        _wywolaj(klient, obraz=b"BM" + bytes(20))
    assert sdk.wyslane == []


def test_typ_obrazu_po_sygnaturze():
    assert cl.typ_obrazu(PNG) == "image/png"
    assert cl.typ_obrazu(JPG) == "image/jpeg"
    assert cl.typ_obrazu(b"GIF89a....") == "image/gif"
    assert cl.typ_obrazu(b"RIFF1234WEBPVP8 ") == "image/webp"
    assert cl.typ_obrazu(bytes([1, 0, 0, 0]) + b" EMF") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
