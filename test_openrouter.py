"""
test_openrouter.py - gałąź providera `openrouter` w `core_llm` (v19.11).

Pilnuje kontraktu, którego nie sprawdza żadna bramka danych:
  1. mapowanie id modelu z przepisu na id OpenRoutera (prefiks `anthropic/`,
     kropka w numerze wersji, bez sufiksu daty) - lista zweryfikowana na
     `/api/v1/models` 2026-10-13;
  2. dwie drogi aktywacji: jawne `LLM_PROVIDER=openrouter` ORAZ stara
     konfiguracja `openai_compat` + adres OpenRoutera, która ma działać bez
     edycji pliku - przy czym host porównujemy po nazwie, nie substringiem;
  3. klucz przywiązany do hosta: `OPENAI_API_KEY` trafia do OpenRoutera
     wyłącznie w drodze zgodności wstecznej i tylko przy braku dedykowanej
     zmiennej;
  4. drabina: `json_schema` na szczycie, degradacja zapamiętana w sesji,
     `temperature` zdejmowana CELOWANIE (bez utraty formatu), a nieznany model
     i brak kredytów nie przechodzą jałowo przez wszystkie szczeble.

Mock SDK, zero wywołań API.

Uruchom:  .venv/Scripts/python -m pytest test_openrouter.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_openrouter.py
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_llm as cl

# IZOLACJA autocache samplingu (trwały plik w `runtime/`) - jak w
# test_json_structured: wymuszone 400 o temperaturze nie może zapisać się
# do prawdziwej instalacji.
cl._sciezka_cache_samplingu = lambda: str(
    Path(tempfile.gettempdir()) / "test_openrouter_sampling.json")
cl._NAUCZONE_BEZ_TEMPERATURY = set()


# ---------------------------------------------------------------------------
# Mock SDK `openai`
# ---------------------------------------------------------------------------
class BadRequestError(Exception):
    """Nazwa klasy jak w SDK - `_czy_zla_struktura` patrzy też na nazwę."""

    def __init__(self, tresc: str, status: int = 400) -> None:
        super().__init__(tresc)
        self.status_code = status


class _Completions:
    def __init__(self, odpowiedzi: list) -> None:
        self.odpowiedzi = list(odpowiedzi)
        self.wyslane: list[dict] = []

    def create(self, **kwargs):
        self.wyslane.append(kwargs)
        nastepna = self.odpowiedzi.pop(0)
        if isinstance(nastepna, Exception):
            raise nastepna
        tekst, finish, *reszta = nastepna
        wiadomosc = SimpleNamespace(content=tekst,
                                    refusal=reszta[0] if reszta else None)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=wiadomosc, finish_reason=finish)])


class _Sdk:
    def __init__(self, odpowiedzi: list) -> None:
        self.chat = SimpleNamespace(completions=_Completions(odpowiedzi))

    def with_options(self, **_kw):
        return self


def _klient(odpowiedzi: list, model_override: str = "") -> tuple:
    sdk = _Sdk(odpowiedzi)
    klient = cl.KlientLLM(cl.PROVIDER_OPENROUTER, sdk, model_override=model_override)
    return klient, sdk.chat.completions.wyslane


SCHEMAT = cl.schemat_z_dyskryminatorem(
    {"type": "object", "properties": {"opcje": {"type": "array",
                                                "items": {"type": "string"}}},
     "required": ["opcje"]},
    "[ODRZUCENIE_AI]",
)


def _wywolaj(klient, model="claude-sonnet-5-5", temperature=0.85, **extra):
    return cl.wywolaj_llm(
        klient, model=model, system="sys", messages=[{"role": "user", "content": "x"}],
        max_tokens=100, temperature=temperature, timeout=5.0, **extra)


@pytest.fixture(autouse=True)
def _czysta_pamiec_sesji():
    cl._BEZ_JSON_SCHEMA.clear()
    cl._NAUCZONE_BEZ_TEMPERATURY.clear()
    yield


# ---------------------------------------------------------------------------
# 1. Mapowanie modelu
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("natywny, openrouter", [
    ("claude-sonnet-5-5", "anthropic/claude-sonnet-5.5"),
    ("claude-fable-5-1", "anthropic/claude-fable-5.1"),
    ("claude-opus-4-8", "anthropic/claude-opus-4.8"),
    ("claude-sonnet-5", "anthropic/claude-sonnet-5"),
    ("claude-haiku-4-5-20251001", "anthropic/claude-haiku-4.5"),
    ("anthropic/claude-opus-5.5", "anthropic/claude-opus-5.5"),
    ("openai/gpt-6.1-sol", "openai/gpt-6.1-sol"),
])
def test_mapowanie_modelu(natywny, openrouter):
    assert cl.model_dla_openroutera(natywny) == openrouter


def test_model_natywny_odwraca_mapowanie_dla_baselineu():
    assert cl.model_natywny("anthropic/claude-sonnet-5.5") == "claude-sonnet-5-5"
    assert cl.model_natywny("openai/gpt-6.1-sol") == "openai/gpt-6.1-sol"


# ---------------------------------------------------------------------------
# 2-3. Rozstrzyganie providera i klucza
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("surowy, url, wynik", [
    ("openrouter", "", cl.PROVIDER_OPENROUTER),
    ("OpenRouter ", "", cl.PROVIDER_OPENROUTER),
    ("openai_compat", "https://openrouter.ai/api/v1", cl.PROVIDER_OPENROUTER),
    ("openai_compat", "https://api.groq.com/openai/v1", cl.PROVIDER_OPENAI_COMPAT),
    # Substring nie wystarcza - od wyniku zależy, dokąd poleci klucz.
    ("openai_compat", "https://openrouter.ai.evil.example/v1",
     cl.PROVIDER_OPENAI_COMPAT),
    ("cokolwiek", "https://openrouter.ai/api/v1", cl.PROVIDER_ANTHROPIC),
    ("", "", cl.PROVIDER_ANTHROPIC),
])
def test_rozstrzygnij_providera(surowy, url, wynik):
    assert cl.rozstrzygnij_providera(surowy, url) == wynik


def _env(monkeypatch, **zmienne):
    for nazwa in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "OPENAI_API_KEY",
                  "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(nazwa, raising=False)
    for nazwa, wartosc in zmienne.items():
        monkeypatch.setenv(nazwa, wartosc)


def test_stara_konfiguracja_compat_dziala_dalej(monkeypatch):
    _env(monkeypatch, LLM_PROVIDER="openai_compat",
         LLM_BASE_URL="https://openrouter.ai/api/v1",
         OPENAI_API_KEY="sk-or-stary", LLM_MODEL="anthropic/claude-sonnet-5")
    k = cl.wczytaj_konfiguracje()
    assert k.provider == cl.PROVIDER_OPENROUTER
    assert k.openrouter_key == "sk-or-stary" and k.kompletna
    assert k.model == "anthropic/claude-sonnet-5"


def test_dedykowany_klucz_wygrywa_ze_starym(monkeypatch):
    _env(monkeypatch, LLM_PROVIDER="openai_compat",
         LLM_BASE_URL="https://openrouter.ai/api/v1",
         OPENAI_API_KEY="sk-proj-prawdziwy-openai", OPENROUTER_API_KEY="sk-or-nowy")
    assert cl.wczytaj_konfiguracje().openrouter_key == "sk-or-nowy"


def test_jawny_openrouter_nie_bierze_klucza_openai(monkeypatch):
    _env(monkeypatch, LLM_PROVIDER="openrouter", OPENAI_API_KEY="sk-proj-x")
    k = cl.wczytaj_konfiguracje()
    assert k.openrouter_key == "" and not k.kompletna


def test_openrouter_nie_wymaga_llm_model(monkeypatch):
    _env(monkeypatch, LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-x")
    assert cl.wczytaj_konfiguracje().kompletna


def test_klient_ma_staly_adres(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gdzies.indziej.example/v1")
    klient = cl.zbuduj_klienta_openrouter("sk-or-x")
    assert str(klient.sdk.base_url).startswith(cl.OPENROUTER_BASE_URL)


# ---------------------------------------------------------------------------
# 4. Drabina wywołania
# ---------------------------------------------------------------------------
def test_model_z_przepisu_jest_mapowany_i_schemat_idzie_na_szczycie():
    klient, wyslane = _klient([('{"typ": "tura", "opcje": []}', "stop")])
    tekst, stop = _wywolaj(klient, schema_json=SCHEMAT, wymusz_json=True)
    assert stop == "stop" and '"tura"' in tekst
    assert wyslane[0]["model"] == "anthropic/claude-sonnet-5.5"
    rf = wyslane[0]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"] == SCHEMAT


def test_llm_model_nadpisuje_mapowanie():
    klient, wyslane = _klient([("ok", "stop")], model_override="openai/gpt-6.1-sol")
    _wywolaj(klient)
    assert wyslane[0]["model"] == "openai/gpt-6.1-sol"


def test_baseline_temperatury_pyta_o_nazwe_natywna():
    # `claude-sonnet-5-5` jest w baseline: niedomyślnej temperatury nie wysyłamy.
    klient, wyslane = _klient([("ok", "stop")])
    _wywolaj(klient, temperature=0.85)
    assert "temperature" not in wyslane[0]


def test_odrzucona_temperatura_nie_zabiera_formatu():
    klient, wyslane = _klient([
        BadRequestError("`temperature` is deprecated for this model."),
        ('{"typ": "tura", "opcje": []}', "stop"),
    ], model_override="egzotyk/model-1")
    _wywolaj(klient, schema_json=SCHEMAT, wymusz_json=True)
    assert wyslane[0]["temperature"] == 0.85
    assert "temperature" not in wyslane[1]
    assert wyslane[1]["response_format"]["type"] == "json_schema"


def test_odrzucony_schemat_schodzi_do_json_object_i_zostaje_zapamietany():
    klient, wyslane = _klient([
        BadRequestError("response_format json_schema is not supported"),
        ('{"opcje": []}', "stop"),
        ('{"opcje": []}', "stop"),
    ])
    _wywolaj(klient, schema_json=SCHEMAT, wymusz_json=True)
    assert wyslane[1]["response_format"] == {"type": "json_object"}
    _wywolaj(klient, schema_json=SCHEMAT, wymusz_json=True)
    assert wyslane[2]["response_format"] == {"type": "json_object"}


def test_nieznany_model_bez_drabiny():
    klient, wyslane = _klient([BadRequestError(
        "Error code: 400 - {'error': {'message': 'anthropic/claude-sonnet-9.9 "
        "is not a valid model ID', 'code': 400}}")])
    with pytest.raises(cl.BladModeluLLM) as info:
        _wywolaj(klient, model="claude-sonnet-9-9", schema_json=SCHEMAT,
                 wymusz_json=True)
    assert len(wyslane) == 1
    assert info.value.model == "anthropic/claude-sonnet-9.9"
    assert "anthropic/claude-sonnet-9.9" in str(info.value)


@pytest.mark.parametrize("blad", [
    BadRequestError("Insufficient credits. Add more using ...", status=402),
    BadRequestError("Your credit balance is too low to access the Anthropic API."),
])
def test_brak_kredytow_to_limit_bez_drabiny(blad):
    klient, wyslane = _klient([blad])
    with pytest.raises(cl.BladLimituLLM):
        _wywolaj(klient, schema_json=SCHEMAT, wymusz_json=True)
    assert len(wyslane) == 1


def test_content_filter_to_odmowa():
    klient, _ = _klient([("", "content_filter", "violative content")])
    assert _wywolaj(klient)[1] == cl.STOP_ODRZUCENIE


# ---------------------------------------------------------------------------
# 5. Fallback autotłumaczy (decyzja maintainera 2026-10-13): start = auto
#    (cicho bez klucza, głośno przy złym), w trakcie pracy = opt-in
# ---------------------------------------------------------------------------
import tlumacz_bramki as tb  # noqa: E402
import tlumacz_rdzen as tr  # noqa: E402


class RateLimitError(Exception):
    status_code = 429


class AuthenticationError(Exception):
    status_code = 401


class _AnthropicMock:
    """Surowe SDK Anthropic: `messages.create` rzuca przygotowane wyjątki."""

    def __init__(self, bledy: list) -> None:
        self.bledy = list(bledy)
        self.wywolania = 0
        self.messages = self

    def create(self, **_kwargs):
        self.wywolania += 1
        raise self.bledy.pop(0)

    def with_options(self, **_kw):
        return self


ODP_JSON = '{"translations": [{"id": 1, "target": "Talo"}]}'


@pytest.fixture
def zapasowy(monkeypatch):
    """Podmienia budowę klienta OpenRoutera na atrapę; zwraca listę wysłanych."""
    sdk = _Sdk([(ODP_JSON, "stop")] * 5)
    monkeypatch.setattr(cl, "zbuduj_klienta_openrouter",
                        lambda klucz, model_override="": cl.KlientLLM(
                            cl.PROVIDER_OPENROUTER, sdk, model_override))
    monkeypatch.setattr(tr, "_ZGODA_Z_FLAGI", False)
    return sdk.chat.completions.wyslane


def _konfig(**pola):
    return cl.KonfiguracjaLLM(**pola)


def test_start_bez_klucza_anthropic_cicho_na_openrouter(zapasowy, capsys):
    k = tr.zbuduj_klienta_tlumacza(_konfig(openrouter_key="sk-or-x"))
    assert k.provider == cl.PROVIDER_OPENROUTER
    assert capsys.readouterr().out == ""


def test_start_z_placeholderem_to_brak_klucza(zapasowy, capsys):
    k = tr.zbuduj_klienta_tlumacza(_konfig(anthropic_key="PASTE_YOUR_KEY_HERE",
                                           openrouter_key="sk-or-x"))
    assert k.provider == cl.PROVIDER_OPENROUTER and capsys.readouterr().out == ""


def test_start_ze_zlym_kluczem_glosno_na_openrouter(zapasowy, capsys):
    k = tr.zbuduj_klienta_tlumacza(_konfig(anthropic_key="sk-proj-pomylka",
                                           openrouter_key="sk-or-x"))
    assert k.provider == cl.PROVIDER_OPENROUTER
    assert "sk-ant-" in capsys.readouterr().out


def test_start_z_dobrym_kluczem_to_anthropic_z_zapasem():
    k = tr.zbuduj_klienta_tlumacza(_konfig(anthropic_key="sk-ant-x",
                                           openrouter_key="sk-or-x"))
    assert k.provider == cl.PROVIDER_ANTHROPIC and k.zapas is not None
    bez = tr.zbuduj_klienta_tlumacza(_konfig(anthropic_key="sk-ant-x"))
    assert bez.zapas is None


def test_start_bez_zadnego_klucza_to_none():
    assert tr.zbuduj_klienta_tlumacza(_konfig()) is None


def _klient_anthropic(bledy):
    sdk = _AnthropicMock(bledy)
    k = cl.KlientLLM(cl.PROVIDER_ANTHROPIC, sdk,
                     zapas=tr._zapas_openrouter("sk-or-x"))
    return k, sdk


def _rdzen(klient):
    return tr.wywolaj_llm(klient, model="claude-sonnet-5-5", system="T.",
                          nazwa_celu="Suomi", kod="fi",
                          pozycje=[(1, "pole", "Dom")], max_tokens=1000)


def test_401_przelacza_bez_pytania(zapasowy, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("asked"))
    klient, _ = _klient_anthropic([AuthenticationError("invalid x-api-key")])
    assert _rdzen(klient) == {1: "Talo"}
    assert klient.provider == cl.PROVIDER_OPENROUTER and klient.zapas is None
    assert zapasowy[0]["model"] == "anthropic/claude-sonnet-5.5"
    assert zapasowy[0]["response_format"]["type"] == "json_schema"


def test_limit_pyta_i_po_zgodzie_jedzie_dalej(zapasowy, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    klient, sdk = _klient_anthropic([RateLimitError("429")])
    assert _rdzen(klient) == {1: "Talo"}
    # Kolejny chunk idzie od razu przez OpenRoutera — bez drugiego pytania.
    assert _rdzen(klient) == {1: "Talo"} and sdk.wywolania == 1


def test_limit_w_sesji_nieinteraktywnej_bez_flagi_zatrzymuje(zapasowy, monkeypatch):
    def _eof(*_):
        raise EOFError
    monkeypatch.setattr("builtins.input", _eof)
    klient, _ = _klient_anthropic([RateLimitError("429"), RateLimitError("429")])
    with pytest.raises(RateLimitError):
        _rdzen(klient)
    assert klient.zapas is None, "would ask again on every chunk"
    assert not zapasowy


def test_flaga_daje_zgode_z_gory(zapasowy, monkeypatch):
    import argparse

    parser = argparse.ArgumentParser()
    tr.dodaj_flage_fallbacku(parser)
    assert parser.parse_args([tr.FLAGA_FALLBACKU]).openrouter_fallback is True
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("asked"))
    klient, _ = _klient_anthropic([BadRequestError(
        "Your credit balance is too low to access the Anthropic API.")])
    assert _rdzen(klient) == {1: "Talo"}


def test_fallback_w_core_llm_dla_buildera_docsow(zapasowy, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    klient, _ = _klient_anthropic([RateLimitError("429")])
    tekst, stop = _wywolaj(klient, temperature=0.0)
    assert stop == "stop" and klient.provider == cl.PROVIDER_OPENROUTER


@pytest.mark.parametrize("env, wynik", [
    ({"LLM_PROVIDER": "openai_compat", "LLM_BASE_URL": "https://api.groq.com/v1"}, True),
    ({"LLM_PROVIDER": "openai_compat", "LLM_BASE_URL": "https://openrouter.ai/api/v1"},
     False),
    ({"LLM_PROVIDER": "openrouter"}, False),
    ({"LLM_PROVIDER": "openrouter", "LLM_MODEL": "anthropic/claude-opus-5.5"}, False),
    ({"LLM_PROVIDER": "openrouter", "LLM_MODEL": "openai/gpt-6.1-sol"}, True),
    ({}, False),
])
def test_bramki_pytaja_tylko_o_model_spoza_claudea(monkeypatch, env, wynik):
    _env(monkeypatch, **env)
    assert tb.wybrano_endpoint_obcy() is wynik
    # Lustro `core_llm`: ta sama decyzja o providerze po obu stronach.
    provider = cl.rozstrzygnij_providera(env.get("LLM_PROVIDER", ""),
                                         env.get("LLM_BASE_URL", ""))
    assert (provider == cl.PROVIDER_OPENROUTER) == (
        env.get("LLM_PROVIDER") == "openrouter"
        or "openrouter.ai" in env.get("LLM_BASE_URL", ""))


# ---------------------------------------------------------------------------
# 6. Bramka mojibake w rdzeniu (złapana w przeglądzie `fi` 19.11)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tekst", [
    "OpenRouter ei ehkä ole vielä ottanut sitÃ¤ kÃ¤yttÃ¶Ã¶n.",
    "mallia â€ž{model}\".",
    "Ð¿Ñ€Ð¸Ð²ÐµÑ‚",          # „привет" przepuszczone przez cp1252
    "zaÅ‚Ã³Å¼ projekt",
])
def test_mojibake_wykryty(tekst):
    assert tb.mojibake(tekst)


@pytest.mark.parametrize("tekst", [
    "OpenRouter ei ehkä ole vielä ottanut sitä käyttöön.",
    "Der Fuß“ und „Straße“ — Größe, Äpfel, Übung.",
    "Поставщик ИИ не знает модель «{model}».",
    "AI-þjónustuveitandinn þekkir ekki líkanið „{model}“.",
    "Załóż projekt — „cudzysłów” i «jodełki»",
    "✅ ⚠️ ℹ️",
    "São Tomé, naïve façade, cañón, Ærø.",
])
def test_mojibake_bez_falszywych_alarmow(tekst):
    assert tb.mojibake(tekst) == []


def test_rdzen_zamawia_zepsute_pozycje_jeszcze_raz():
    zepsuta = '{"translations": [{"id": 1, "target": "sitÃ¤"}, {"id": 2, "target": "ok"}]}'
    dobra = '{"translations": [{"id": 1, "target": "sitä"}]}'
    sdk = _Sdk([(zepsuta, "stop"), (dobra, "stop")])
    klient = cl.KlientLLM(cl.PROVIDER_OPENROUTER, sdk)
    mapa = tr.wywolaj_llm(klient, model="claude-sonnet-5-5", system="T.",
                          nazwa_celu="Suomi", kod="fi",
                          pozycje=[(1, "pole", "to"), (2, "pole", "ok")],
                          max_tokens=1000)
    assert mapa == {1: "sitä", 2: "ok"}
    druga = sdk.chat.completions.wyslane[1]["messages"][-1]["content"]
    assert '"id": 1' in druga and '"id": 2' not in druga


def test_rdzen_dwa_razy_mojibake_to_blad_chunku():
    zepsuta = '{"translations": [{"id": 1, "target": "sitÃ¤"}]}'
    klient = cl.KlientLLM(cl.PROVIDER_OPENROUTER, _Sdk([(zepsuta, "stop")] * 2))
    with pytest.raises(RuntimeError, match="mojibake twice"):
        tr.wywolaj_llm(klient, model="claude-sonnet-5-5", system="T.",
                       nazwa_celu="Suomi", kod="fi", pozycje=[(1, "pole", "to")],
                       max_tokens=1000)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
