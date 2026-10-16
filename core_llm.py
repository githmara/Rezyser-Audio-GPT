"""core_llm.py — provider-agnostic warstwa wywołań LLM (Anthropic ⟷ OpenAI-compatible).

POJEDYNCZE źródło prawdy dla „zbuduj klienta + wywołaj model". Dotąd każdy panel
(`gui_rezyser`, `gui_opowiesci`, `gui_poliglota`) budował klienta `anthropic.Anthropic`
na sztywno, a moduły `*_ai.py` wołały `klient.messages.create(...)` bezpośrednio. Od
v18.4 cała warstwa runtime przechodzi przez ten moduł, dzięki czemu reżyser może wskazać
DOWOLNY endpoint zgodny z OpenAI (`base_url` + klucz + nazwa modelu) — OpenRouter,
Cerebras, Fireworks, DeepSeek, Groq, endpoint OpenAI-compat Gemini, lokalne Ollama —
JEDNĄ ścieżką kodu, bez utrzymywania osobnej integracji per provider.

Od v19.11 OpenRouter ma WŁASNĄ gałąź (``LLM_PROVIDER=openrouter``): ta sama drabina
co compat, ale stały adres, osobny klucz ``OPENROUTER_API_KEY``, mapowanie modelu
z przepisu (``claude-sonnet-5-5`` → ``anthropic/claude-sonnet-5.5``) i schemat JSON
przez ``response_format``. Z tej gałęzi korzysta też fallback autotłumaczy.

Zasada: **Anthropic / Claude = domyślny, rekomendowany filar jakości** (prompty są pod
niego dostrojone). OpenAI-compat = opcja zaawansowana (bring-your-own-endpoint); inne
modele mogą dać niższą jakość — to świadomy wybór reżysera (koszt↔jakość).

Moduł jest wx-free i SDK-lazy: `anthropic`/`openai` importujemy dopiero w
:func:`zbuduj_klienta`, więc gdy end-user zostaje na Anthropic, `openai` nie jest
wciągany do `.exe` (lekki bundla single-provider — patrz CLAUDE.md pkt 7).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any

# Identyfikatory providerów (wartość pola `LLM_PROVIDER` w golden_key.env).
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI_COMPAT = "openai_compat"
PROVIDER_OPENROUTER = "openrouter"
PROVIDERZY = (PROVIDER_ANTHROPIC, PROVIDER_OPENAI_COMPAT, PROVIDER_OPENROUTER)

# Brak/niepoprawny `LLM_PROVIDER` → Anthropic (end-user z samym ANTHROPIC_API_KEY
# nie zauważa żadnej zmiany względem ≤v18.3).
DOMYSLNY_PROVIDER = PROVIDER_ANTHROPIC

# OpenRouter (v19.11): adres NA SZTYWNO, klucz we WŁASNEJ zmiennej. Zasada przeniesiona
# z `accessible_text_analyst` v1.7.0: zmienna z kluczem jest przywiązana do jednego
# hosta, więc `OPENROUTER_API_KEY` nigdy nie poleci pod `LLM_BASE_URL` ani odwrotnie.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_HOST_OPENROUTER = "openrouter.ai"


# ---------------------------------------------------------------------------
# Wyjątki (provider-agnostic) — wołający łapią JE, nie typy z SDK konkretnego
# providera (inaczej `gui_rezyser` musiałby importować i anthropic, i openai).
# ---------------------------------------------------------------------------
class BladLLM(Exception):
    """Bazowy błąd warstwy LLM (niezależny od providera)."""


class BladLimituLLM(BladLLM):
    """Przekroczony limit zapytań / brak kredytów (HTTP 429) — dowolny provider.

    Zastępuje dawne łapanie ``anthropic.RateLimitError`` w GUI/`rezyser_ai`/`tlumacz_ai`.
    """


class BladTimeoutLLM(BladLLM):
    """Przekroczony limit czasu wywołania (``APITimeoutError``) — dowolny provider.

    Zastępuje dawne ``anthropic.APITimeoutError`` (Opowieści rozróżniają ten błąd od
    limitu osobnym komunikatem). Pozostałe błędy SDK (API/sieć) NIE są opakowywane —
    propagują natywnie i łapie je istniejący szeroki ``except Exception``.
    """


class BladKontekstuLLM(BladLLM):
    """Payload nie zmieścił się w oknie kontekstowym modelu (v18.13).

    Provider zwraca to jako HTTP 400/413 z komunikatem typu „prompt is too long:
    N tokens > M maximum" (Anthropic) albo ``context_length_exceeded`` (OpenAI-compat)
    — czyli tym samym kodem, co błąd STRUKTURY payloadu. Bez rozróżnienia wpadało to
    w :func:`_czy_zla_struktura` i uruchamiało bezcelowe retry: gałąź Anthropic
    ponawiała ten sam za duży payload bez ``temperature``, a compat przechodziła całą
    drabinę degradacji — kilka wywołań, kilka opóźnień, ten sam wynik. Na końcu user
    dostawał surową, angielską treść wyjątku.

    Filar jakości (Claude, okno 1M) trafia tu wyjątkowo; realnym adresatem jest
    reżyser, który wskazał własny endpoint ``openai_compat`` z modelem o małym oknie
    (32k/64k) i uruchomił postprodukcję ``zakres: calosc`` na dużym projekcie.
    """


class BladModeluLLM(BladLLM):
    """Endpoint nie zna modelu (v19.11) — typowo OpenRouter po migracji silnika.

    Scenariusz, dla którego to istnieje: Anthropic ogłasza nowy model, maintainer
    przenosi na niego przepisy (``model: claude-…``), a OpenRouter jeszcze go nie
    wystawił. Odpowiedź to 400 „… is not a valid model ID", czyli TEN SAM kod,
    którym endpoint zgłasza zły kształt payloadu — bez rozróżnienia drabina
    w :func:`_wywolaj_openai_compat` przeszłaby wszystkie szczeble z tym samym,
    nieistniejącym modelem, a użytkownik dostałby surowy, angielski wyjątek
    z identyfikatorem konta OpenRoutera w treści.

    ``str()`` to już komunikat zlokalizowany (``common.llm_nieznany_model``), bo
    większość handlerów GUI pokazuje nieznane wyjątki przez ``str(exc)`` — nowy
    typ nie wymaga więc zmian w żadnym z nich.
    """

    def __init__(self, model: str, provider: str) -> None:
        self.model = model
        self.provider = provider
        super().__init__(self._komunikat())

    def _komunikat(self) -> str:
        try:
            import i18n

            return i18n.t("common.llm_nieznany_model", model=self.model)
        except Exception:  # noqa: BLE001 — dev-tooling bez paczki GUI też musi coś powiedzieć
            return (
                f"The endpoint does not know the model '{self.model}'. If the "
                "engine was just migrated to a new Claude model, OpenRouter may "
                "not list it yet — set LLM_MODEL in golden_key.env to a model "
                "it does list (e.g. anthropic/claude-sonnet-5.5)."
            )


class BladFunkcjiNiedostepnej(BladLLM):
    """Provider nie umie tej funkcji (v19.14: PDF dla ``openai_compat``).

    Strażnik, nie komunikat dla użytkownika: GUI sprawdza providera, ZANIM
    zaproponuje funkcję, więc ten wyjątek oznacza błąd wołającego.
    """

    def __init__(self, funkcja: str, provider: str) -> None:
        self.funkcja = funkcja
        self.provider = provider
        super().__init__(f"'{funkcja}' is not available for provider '{provider}'.")


# ---------------------------------------------------------------------------
# Konfiguracja czytana z golden_key.env (po load_dotenv przez wołającego)
# ---------------------------------------------------------------------------
def czy_adres_openroutera(base_url: str) -> bool:
    """Czy ``LLM_BASE_URL`` wskazuje host OpenRoutera (porównanie po HOŚCIE, nie substringu).

    Substring przepuściłby ``https://openrouter.ai.evil.example/`` — a od wyniku
    zależy, czy wyślemy tam ``OPENROUTER_API_KEY``.
    """
    from urllib.parse import urlparse

    try:
        host = (urlparse(base_url.strip()).hostname or "").lower()
    except ValueError:
        return False
    return host == _HOST_OPENROUTER or host.endswith("." + _HOST_OPENROUTER)


def rozstrzygnij_providera(provider_surowy: str, base_url: str) -> str:
    """Jedno źródło decyzji „który provider" — dla runtime'u i dla System Check.

    Dwie drogi do ``openrouter`` (decyzja maintainera 2026-10-13):
      * jawna: ``LLM_PROVIDER=openrouter``;
      * zgodność wsteczna: ``LLM_PROVIDER=openai_compat`` + ``LLM_BASE_URL`` na
        hoście OpenRoutera — tak wyglądała każda konfiguracja OpenRoutera sprzed
        v19.11 (podręcznik podawał ten adres jako przykład). Działa dalej bez
        edycji pliku, a przy okazji dostaje mapowanie modelu i ``json_schema``.

    Nieznana wartość → cichy fallback do Anthropic (stan ≤v18.3).
    """
    provider = (provider_surowy or DOMYSLNY_PROVIDER).strip().lower()
    if provider not in PROVIDERZY:
        return DOMYSLNY_PROVIDER
    if provider == PROVIDER_OPENAI_COMPAT and czy_adres_openroutera(base_url):
        return PROVIDER_OPENROUTER
    return provider


@dataclass(frozen=True)
class KonfiguracjaLLM:
    """Migawka konfiguracji LLM z ``golden_key.env``.

    Pola ``base_url``/``model`` mają znaczenie wyłącznie dla ``openai_compat``
    (``model`` także dla ``openrouter``, gdzie jest OPCJONALNY — patrz
    :func:`model_dla_openroutera`). W trybie ``anthropic`` model bierze się
    z YAML przepisu (``claude-sonnet-5-5``).
    """

    provider: str = DOMYSLNY_PROVIDER
    anthropic_key: str = ""
    openai_key: str = ""
    base_url: str = ""
    model: str = ""   # LLM_MODEL — nadpisuje `przepis.model` w trybie compat/openrouter
    openrouter_key: str = ""

    @property
    def kompletna(self) -> bool:
        """Czy konfiguracja wystarcza do zbudowania działającego klienta."""
        if self.provider == PROVIDER_OPENAI_COMPAT:
            return bool(self.openai_key and self.base_url and self.model)
        if self.provider == PROVIDER_OPENROUTER:
            # Bez `LLM_MODEL`: model wynika z przepisu (mapowanie id).
            return bool(self.openrouter_key)
        # Anthropic: ten sam warunek co dawny `_init_api` (`sk-ant-`).
        return bool(self.anthropic_key and self.anthropic_key.startswith("sk-ant-"))


def wczytaj_konfiguracje() -> KonfiguracjaLLM:
    """Czyta konfigurację z ``os.environ`` (wołający robi ``load_dotenv`` PRZED).

    Nieznana wartość ``LLM_PROVIDER`` → cichy fallback do Anthropic (bezpieczny
    default, zgodny ze stanem ≤v18.3).

    Klucz OpenRoutera: ``OPENROUTER_API_KEY``. W drodze zgodności wstecznej
    (``openai_compat`` + adres OpenRoutera, patrz :func:`rozstrzygnij_providera`)
    stara konfiguracja trzymała go w ``OPENAI_API_KEY`` — bierzemy go stamtąd
    TYLKO wtedy, gdy dedykowanej zmiennej brak. To nie jest wyciek, przed którym
    chroni stały adres: użytkownik sam wskazał ten host dla tego klucza.
    """
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    surowy = os.getenv("LLM_PROVIDER", "")
    provider = rozstrzygnij_providera(surowy, base_url)
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if (provider == PROVIDER_OPENROUTER and not openrouter_key
            and surowy.strip().lower() == PROVIDER_OPENAI_COMPAT):
        openrouter_key = openai_key
    return KonfiguracjaLLM(
        provider=provider,
        anthropic_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        openai_key=openai_key,
        base_url=base_url,
        model=os.getenv("LLM_MODEL", "").strip(),
        openrouter_key=openrouter_key,
    )


# Sufiks daty w id Anthropic (`claude-haiku-4-5-20251001`) — OpenRouter go nie zna.
_SUFIKS_DATY_MODELU = re.compile(r"-\d{8}$")
# Myślnik MIĘDZY cyframi = separator numeru wersji (`5-5` → `5.5`, `4-5` → `4.5`).
_MYSLNIK_WERSJI = re.compile(r"(?<=\d)-(?=\d)")


def model_dla_openroutera(mdl: str) -> str:
    """Id modelu z przepisu → id OpenRoutera: ``claude-sonnet-5-5`` → ``anthropic/claude-sonnet-5.5``.

    Przepisy Reżysera (YAML ``model:``) i stałe ``MODEL_*`` zawsze nazywają model
    Anthropic, więc prefiks ``anthropic/`` jest stały. OpenRouter pisze numer
    wersji z KROPKĄ i bez sufiksu daty — zweryfikowane na liście
    ``/api/v1/models`` 2026-10-13 (``claude-fable-5.1``, ``claude-haiku-4.5``,
    ``claude-opus-4.8``; wersja jednocyfrowa bez zmian: ``claude-sonnet-5``).

    Id zawierające ``/`` jest już identyfikatorem OpenRoutera (np. wpisanym
    w YAML albo w ``LLM_MODEL``) i przechodzi nietknięte. Model, którego
    OpenRouter jeszcze nie ma, NIE jest tu wykrywany — wiedzę daje dopiero
    odpowiedź API (:class:`BladModeluLLM`), lista modeli zmienia się bez nas.
    """
    m = (mdl or "").strip()
    if not m or "/" in m:
        return m
    m = _SUFIKS_DATY_MODELU.sub("", m)
    return "anthropic/" + _MYSLNIK_WERSJI.sub(".", m)


def model_natywny(mdl: str) -> str:
    """Odwrotność :func:`model_dla_openroutera` dla modeli Anthropic (dla baseline'ów).

    Listy :data:`_MODELE_BEZ_TEMPERATURY` i dialektów „bez myślenia" znają nazwy
    natywne (``claude-sonnet-5-5``), więc decyzja o ``temperature`` na OpenRouterze
    pyta je o model w tej postaci. Id spoza ``anthropic/`` wraca bez zmian.
    """
    if not mdl.startswith("anthropic/"):
        return mdl
    return re.sub(r"(?<=\d)\.(?=\d)", "-", mdl[len("anthropic/"):])


# ---------------------------------------------------------------------------
# Klient + budowa
# ---------------------------------------------------------------------------
@dataclass
class KlientLLM:
    """Lekki wrapper nad klientem SDK + znacznik providera.

    ``model_override`` (z ``LLM_MODEL``) służy trybom ``openai_compat`` i
    ``openrouter`` — nadpisuje nazwę modelu z przepisu YAML (na cudzym endpoincie
    ``claude-sonnet-5-5`` nie istnieje). W trybie Anthropic runtime zostawia go
    pustym (model z przepisu); ustawia go tylko zapas autotłumaczy z trybu
    OpenRouter, żeby ``anthropic/claude-opus-5.5`` z ``LLM_MODEL`` został Opusem.
    """

    provider: str
    sdk: Any
    model_override: str = ""
    # Fallback autotłumaczy (v19.11, WYŁĄCZNIE dev-tooling — runtime GUI go nie
    # ustawia). Wołane z powodem (`ZAPAS_*`), zwraca klienta DRUGIEGO konta albo
    # `None` (brak zgody/klucza). Polityka zgody żyje w `tlumacz_rdzen`, nie
    # tu: `core_llm` nie pyta człowieka o nic.
    zapas: Any = None
    # Czy to konto odpowiedziało już choć raz (v19.11, audyt). Rozdziela 401
    # „na starcie" (zły klucz — automat) od 401 „w trakcie" (klucz unieważniony
    # po udanych chunkach — przełączenie na inne konto wymaga zgody).
    udane: bool = False

    def przelacz_na(self, inny: "KlientLLM") -> None:
        """Podmienia klienta W MIEJSCU, żeby każdy, kto trzyma referencję, jechał dalej nowym.

        Bracia tłumaczy trzymają klienta w zmiennych lokalnych i listach
        (``_klient.append(...)``) — nowy obiekt nie dotarłby do nich, mutacja tak.
        Zapas jest jednorazowy: po przełączeniu nie ma już dokąd uciekać.
        """
        self.provider = inny.provider
        self.sdk = inny.sdk
        self.model_override = inny.model_override
        self.zapas = None
        self.udane = False


# Powody, z którymi `KlientLLM.zapas` jest wołany. `klucz` = klucz pierwszego konta
# odrzucony (401) PRZED pierwszą udaną odpowiedzią — przełączenie AUTOMATYCZNE
# (decyzja maintainera 2026-10-13); `limit` = 429 albo wyczerpane kredyty w trakcie
# pracy, `klucz_w_trakcie` = 401 po udanych wywołaniach — oba OPT-IN.
ZAPAS_KLUCZ = "klucz"
ZAPAS_KLUCZ_W_TRAKCIE = "klucz_w_trakcie"
ZAPAS_LIMIT = "limit"


def czy_odrzucony_klucz(exc: Exception) -> bool:
    """Czy wyjątek to odrzucony klucz API (401, ``AuthenticationError`` w obu SDK)."""
    if type(exc).__name__ == "AuthenticationError":
        return True
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status == 401


def powod_zapasu(exc: Exception) -> str | None:
    """Czy ten wyjątek uzasadnia fallback — i z jakim powodem (``None`` = nie)."""
    if czy_odrzucony_klucz(exc):
        return ZAPAS_KLUCZ
    if isinstance(exc, BladLimituLLM) or _czy_rate_limit(exc):
        return ZAPAS_LIMIT
    return None


def przelacz_na_zapas(klient: KlientLLM, exc: Exception) -> bool:
    """Próbuje przełączyć klienta na drugie konto (Anthropic ⟷ OpenRouter) po tym wyjątku.

    Kierunek zna tylko polityka w ``klient.zapas`` (``tlumacz_rdzen``); runtime
    GUI zapasu nie ustawia, więc dla niego to zawsze ``False``. Publiczne, bo
    woła je też ``tlumacz_rdzen``, który ma WŁASNĄ ścieżkę przez SDK Anthropic
    (structured outputs) poza :func:`wywolaj_llm`.
    """
    if klient.zapas is None:
        return False
    powod = powod_zapasu(exc)
    if powod is None:
        return False
    if powod == ZAPAS_KLUCZ and klient.udane:
        powod = ZAPAS_KLUCZ_W_TRAKCIE
    nowy = klient.zapas(powod)
    if nowy is None:
        # Brak zgody albo brak klucza: nie pytamy przy każdym kolejnym chunku.
        klient.zapas = None
        return False
    klient.przelacz_na(nowy)
    return True



def zbuduj_klienta(konfig: KonfiguracjaLLM) -> "KlientLLM | None":
    """Buduje :class:`KlientLLM` wg konfiguracji.

    Zwraca ``None`` gdy konfiguracja niekompletna LUB SDK rzuci przy inicjalizacji —
    mirror dawnego wzorca ``self._klient_claude = None`` (panel pozostaje wyłączony,
    ``_api_dostepne = klient is not None``). SDK importowane leniwie.
    """
    if not konfig.kompletna:
        return None
    try:
        if konfig.provider == PROVIDER_OPENAI_COMPAT:
            import openai  # noqa: PLC0415
            sdk = openai.OpenAI(api_key=konfig.openai_key, base_url=konfig.base_url)
            return KlientLLM(PROVIDER_OPENAI_COMPAT, sdk, model_override=konfig.model)
        if konfig.provider == PROVIDER_OPENROUTER:
            return zbuduj_klienta_openrouter(konfig.openrouter_key, konfig.model)
        import anthropic  # noqa: PLC0415
        sdk = anthropic.Anthropic(api_key=konfig.anthropic_key)
        return KlientLLM(PROVIDER_ANTHROPIC, sdk)
    except Exception:  # noqa: BLE001 — zły klucz/URL/SDK = brak klienta, nie crash startu
        return None


def zbuduj_klienta_openrouter(klucz: str, model_override: str = "") -> KlientLLM:
    """Klient OpenRoutera ze STAŁYM adresem — także dla fallbacku autotłumaczy.

    ``base_url`` podajemy jawnie: SDK ``openai`` samo czyta ``OPENAI_BASE_URL``
    ze środowiska, a ta zmienna nie może przekierować klucza OpenRoutera gdzie
    indziej. Rzuca, gdy SDK nie wstanie — :func:`zbuduj_klienta` zamienia to na
    ``None``, a dev-tooling chce przyczyny.
    """
    import openai  # noqa: PLC0415

    sdk = openai.OpenAI(api_key=klucz, base_url=OPENROUTER_BASE_URL)
    return KlientLLM(PROVIDER_OPENROUTER, sdk, model_override=model_override)


# ---------------------------------------------------------------------------
# Wywołanie — wspólny kształt wejścia/wyjścia dla obu API
# ---------------------------------------------------------------------------
def _czy_rate_limit(exc: Exception) -> bool:
    """Czy wyjątek to limit zapytań (429), niezależnie od SDK.

    Bez importu obu SDK: oba (anthropic, openai) nazywają klasę ``RateLimitError``
    i wystawiają ``status_code``/``response.status_code == 429``.
    """
    if type(exc).__name__ == "RateLimitError":
        return True
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status == 429 or czy_brak_kredytow(exc)


# Wyczerpane kredyty NIE przychodzą jako 429 (v19.11). Anthropic odpowiada 400
# „Your credit balance is too low to access the Anthropic API", OpenRouter 402
# „Insufficient credits" / „requires more credits". Bez rozpoznania 400 wpadało
# w `_czy_zla_struktura` i uruchamiało drabinę degradacji payloadu, której żaden
# szczebel nie mógł pomóc — a fallback autotłumaczy na OpenRouter, który ma
# osobne konto, nie dostawał sygnału, na który czeka.
_FRAZY_BRAKU_KREDYTOW = (
    "credit balance is too low",
    "insufficient credits",
    "requires more credits",
)


def czy_brak_kredytow(exc: Exception) -> bool:
    """Czy wyjątek to wyczerpane kredyty konta (400 Anthropic / 402 OpenRouter)."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 402:
        return True
    tresc = str(exc).lower()
    return any(fraza in tresc for fraza in _FRAZY_BRAKU_KREDYTOW)


# Odpowiedzi „nie znam tego modelu" (v19.11) — zebrane z realnych komunikatów:
#   OpenRouter (zmierzone 2026-10-13): 400 „anthropic/claude-sonnet-9.9 is not
#              a valid model ID"
#   OpenAI:    404 code „model_not_found", „The model `x` does not exist or you
#              do not have access to it."
_FRAZY_NIEZNANEGO_MODELU = (
    "is not a valid model id",
    "model_not_found",
    "does not exist or you do not have access",
)


def _czy_nieznany_model(exc: Exception) -> bool:
    """Czy endpoint odrzucił samą NAZWĘ modelu (patrz :class:`BladModeluLLM`)."""
    tresc = str(exc).lower()
    return any(fraza in tresc for fraza in _FRAZY_NIEZNANEGO_MODELU)


def _czy_timeout(exc: Exception) -> bool:
    """Czy wyjątek to przekroczenie czasu (``APITimeoutError`` w obu SDK)."""
    return type(exc).__name__ == "APITimeoutError"


# Frazy rozpoznające przepełnienie okna kontekstowego w treści błędu — zebrane
# z realnych komunikatów obu rodzin API (nie z domysłów):
#   Anthropic: „prompt is too long: 1234 tokens > 200000 maximum",
#              „input length and `max_tokens` exceed context limit: … decrease
#               input length or max_tokens and try again"
#   OpenAI:    code „context_length_exceeded" + „This model's maximum context
#              length is 8192 tokens. However, your messages resulted in …
#              Please reduce the length of the messages."
# Porównanie na lowercase substring — treść bywa opakowana w JSON błędu SDK,
# więc dopasowujemy fragment, nie cały komunikat.
_FRAZY_PRZEPELNIENIA = (
    "prompt is too long",
    "context_length_exceeded",
    "maximum context length",
    "exceed context limit",
    "context window",
    "too many tokens",
    "reduce the length of the messages",
)


def _czy_przepelniony_kontekst(exc: Exception) -> bool:
    """Czy błąd to przekroczenie okna kontekstowego modelu (v18.13).

    Rozpoznajemy po TREŚCI (:data:`_FRAZY_PRZEPELNIENIA`) albo po statusie 413
    („Request Entity Too Large" — payload odrzucony przez gateway zanim model go
    zobaczył). Sam status 400 NIE wystarcza: to ten sam kod, którym provider zgłasza
    błąd struktury payloadu, a pomylenie tych dwóch przypadków kosztuje albo jałowe
    retry (gdybyśmy uznali przepełnienie za strukturę), albo utratę działającej
    degradacji (gdybyśmy uznali strukturę za przepełnienie).
    """
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 413:
        return True
    tresc = str(exc).lower()
    return any(fraza in tresc for fraza in _FRAZY_PRZEPELNIENIA)


def _czy_zla_struktura(exc: Exception) -> bool:
    """Czy błąd to odrzucenie STRUKTURY payloadu (zła rola/kolejność), nie limit/sieć.

    Heurystyka bez importu SDK: nazwa klasy (``BadRequestError`` /
    ``UnprocessableEntityError``) lub status 400/422. 429/timeout/5xx świadomie
    NIE są tu łapane — to nie problem struktury, więc nie chcemy ich maskować
    fallbackiem (lecą wyżej do :func:`wywolaj_llm` → ``BladLimituLLM`` itp.).
    Używane w gałęzi ``openai_compat`` (degradacja payloadu z rolami do pojedynczego
    bloku ``user``) ORAZ w gałęzi ``anthropic`` (degradacja `temperature` — patrz
    :func:`_wywolaj_anthropic`).

    v18.13: przepełnienie okna kontekstowego przychodzi tym SAMYM kodem 400, ale NIE
    jest problemem struktury — żadna degradacja go nie naprawi, bo payload zostaje
    tak samo długi. Wykluczamy je tu jawnie, żeby Anthropic nie ponawiał bez
    ``temperature``, a compat nie przechodził całej drabiny; błąd leci prosto do
    :func:`wywolaj_llm` → :class:`BladKontekstuLLM`.
    """
    if _czy_przepelniony_kontekst(exc):
        return False
    # v19.11: nieznany model i brak kredytów też przychodzą jako 400, a żadna
    # degradacja payloadu ich nie naprawi — tak samo jak przepełnienia.
    if _czy_nieznany_model(exc) or czy_brak_kredytow(exc):
        return False
    if type(exc).__name__ in ("BadRequestError", "UnprocessableEntityError"):
        return True
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status in (400, 422)


def _dev_log(komunikat: str) -> None:
    """Strażowany ``print`` na stdout dewelopera (packaged: stdout None → milczy).

    ``core_llm`` jest wx-free i NIE importuje ``core_rezyser`` (uniknięcie cyklu),
    więc ma własny guard analogiczny do ``core_rezyser._dev_log_runtime`` — w paczce
    release apka chodzi bez konsoli, goły ``print`` mógłby ubić proces.
    """
    try:
        if sys.stdout is not None:
            print(f"[core_llm] {komunikat}", file=sys.stdout)
    except Exception:  # noqa: BLE001 — log nigdy nie może ubić wywołania
        pass


# Role akceptowane w segmentach `openai_compat` (poza nimi → degradacja do "user").
_ROLE_DOZWOLONE = ("system", "assistant", "user")


# ---------------------------------------------------------------------------
# Structured outputs (v18.23) — schematy dla trybów, które WALIDUJĄ JSON
# ---------------------------------------------------------------------------
# Do v18.22 tryby JSON (Burza/Skrypt/tura Opowieści) wymuszały kształt WYŁĄCZNIE
# promptem, a `wymusz_json` gałąź Anthropic ignorowała. Realny skutek (zgłoszenie
# 2026-08-29, projekt `helsinki_story`): model wstawił PRZECINEK WISZĄCY po
# ostatnim polu opcji, `json.loads` rzucił „Expecting property name enclosed in
# double quotes", a self-correction odesłał modelowi ten komunikat — więc trzy
# razy z rzędu „naprawiał" cudzysłowy, które były bezbłędne. Przy wymuszonym
# schemacie takie wyjście nie może powstać: kształt egzekwuje API, nie perswazja.
# (Cytat jest HISTORYCZNY — CPython 3.14 mówi na to samo wejście „Illegal
# trailing comma before end of object". Nie szukaj starego brzmienia w kodzie:
# nigdzie go nie porównujemy, a fixture w `test_json_structured` zna oba.)
#
# Wzorzec przyszedł z WŁASNEGO repo — `buduj_wielojezyczne_ui.py` używa
# `output_config.format` od dawna. Runtime po prostu nigdy go nie dostał.
#
# Słowa kluczowe JSON Schema, których structured outputs NIE przyjmuje. UWAGA:
# SDK czyści schematy, które GENERUJE (z Pydantic) — surowy dict podany w
# `output_config` leci do API bez zmian, więc czyścimy sami. Zmierzone żywo
# (2026-08-29): `SCHEMA_BURZA` as-is → 400 „property 'maxItems' is not supported".
_KLUCZE_NIEWSPIERANE = frozenset({
    "minItems", "maxItems", "minLength", "maxLength",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf", "pattern", "minProperties", "maxProperties", "uniqueItems",
})

# `stop_reason`, którym API sygnalizuje odmowę klasyfikatora bezpieczeństwa.
# Do v18.22 nieobsługiwany NIGDZIE — wołający sprawdzali tylko "max_tokens",
# więc odmowa (pusta treść) szła jako „błąd struktury" po wyczerpaniu retry.
STOP_ODRZUCENIE = "refusal"

# Wartości dyskryminatora `typ` w schemacie z gałęzią odrzucenia.
TYP_TURA = "tura"
TYP_ODRZUCENIE = "odrzucenie"

_POWODY_ODRZUCENIA = ("safety", "brak_informacji", "niejednoznacznosc", "inne")


# ---------------------------------------------------------------------------
# Sampling: modele, które odrzucają niedomyślną `temperature` (v18.23)
# ---------------------------------------------------------------------------
# PUBLICZNE API TEJ SEKCJI (v18.24, rozszerzone przy migracji środowiska
# 2026-09-11): DECYZJA — `honoruje_temperature`, `czy_odrzucono_temperature`,
# `zapamietaj_odrzucenie_temperatury`; WYKONANIE — `temperatura_w_payloadzie`,
# `wstaw_temperature`, `zdejmij_temperature`. `_co_odrzucono` ma jednego
# konsumenta (drabinę niżej) i zostaje prywatne.
# Nie uprywatniać żadnej z tych szóstki: poza runtimem korzysta
# z nich RODZINA AUTOTŁUMACZY, która ma własnych klientów
# Anthropic (`tlumacz_rdzen`, `buduj_wielojezyczne_ui`) i bez tego płaciła
# jałowym round-tripem 400 przy KAŻDYM chunku: wszystkie sześć narzędzi jedzie
# domyślnie na `claude-sonnet-5-5`, a tłumaczenie wysyła `temperature=0.0`
# (determinizm), czyli wartość niedomyślną. Baseline + autocache poniżej są
# więc wspólne dla runtime'u i dev-toolingu — jeden plik nauki, jedna prawda.
# Do v18.22 degradacja `temperature` była REAKTYWNA: wysyłamy z przepisu →
# 400 → ponawiamy bez. Na dziś domyślny model runtime'u (`claude-sonnet-5-5`)
# NIE honoruje `temperature` w ogóle, więc ten scenariusz zachodził przy KAŻDYM
# wywołaniu — czyli każda generacja płaciła dodatkowym round-tripem HTTP
# (samo 400 to błąd walidacji przed inferencją, więc bez kosztu tokenów, ale
# z kosztem latencji i limitu zapytań).
#
# Zmierzone żywo 2026-08-29 (`claude-sonnet-5`):
#   temperature=0.85 → 400 „`temperature` is deprecated for this model."
#   temperature=1.0  → OK   (wartość domyślna przechodzi jako no-op)
#   bez parametru    → OK
# Honorują: `claude-sonnet-4-6`, `claude-haiku-4-5`. Odrzucają: `claude-sonnet-5`,
# `claude-opus-5`.
#
# Lista jest ZAHARDKODOWANA świadomie, zgodnie z regułą kciuka projektu
# („hardkod, gdy lista = zewnętrzny rejestr" — jak `build_release.INNO_LANG_MAP`):
# to lustro cudzej macierzy modeli, nie dane naszego projektu. Plik w `datas`
# bundla nie dałby tu nic — zawartość bundla jest niezmienna bez rebuildu EXE,
# więc rozszerzenie baseline'u i tak wymaga mikropatcha. Modele Anthropic
# śledzi maintainer; nietypowe endpointy `openai_compat` domyka autocache niżej,
# więc reżyser z egzotycznym providerem nie musi czekać na patch.
_MODELE_BEZ_TEMPERATURY: tuple[str, ...] = (
    "claude-fable-5",
    "claude-mythos-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    # `claude-sonnet-5-5` łapie też prefiks niżej — wpis jawny, żeby nikt
    # nie musiał wiedzieć o kolizji prefiksów (ani jej przypadkiem zepsuć).
    "claude-sonnet-5-5",
    "claude-sonnet-5",
)

# Wartość, którą API przyjmuje nawet od modeli z listy wyżej (no-op samplingu).
_TEMPERATURA_DOMYSLNA = 1.0

_PLIK_CACHE_SAMPLINGU = "modele_bez_temperatury.json"


def _sciezka_cache_samplingu() -> str:
    """``runtime/modele_bez_temperatury.json`` — obok pozostałych metadanych.

    Import lokalny: ``core_llm`` jest wx-free i nie może wciągać ``core_rezyser``
    (cykl), a ``sciezki`` to czysty helper ścieżek.
    """
    import sciezki

    return os.path.join(
        sciezki.KATALOG_BAZOWY_STR, "runtime", _PLIK_CACHE_SAMPLINGU,
    )


def _wczytaj_cache_samplingu() -> set[str]:
    """Modele, które JUŻ raz odrzuciły ``temperature`` (nauka poza baseline).

    Trwały (przeżywa restart), bo jałowe 400 na każdym starcie aplikacji byłoby
    dokładnie tym kosztem, który usuwamy. Unieważniany przy zmianie wersji
    aplikacji — inaczej utrwalilibyśmy zachowanie modelu, które provider może
    zmienić (a wtedy `temperature` z przepisu nigdy by nie wróciła do gry).

    Nigdy nie rzuca — cache to optymalizacja, nie źródło prawdy.
    """
    try:
        with open(_sciezka_cache_samplingu(), encoding="utf-8") as fh:
            dane = json.load(fh)
        if not isinstance(dane, dict):
            return set()
        import i18n

        if str(dane.get("wersja_app", "")) != str(i18n.NUMER_WERSJI):
            return set()
        return {str(m) for m in dane.get("modele", [])}
    except Exception:  # noqa: BLE001 — brak/uszkodzony/niedostępny cache = pusty
        return set()


def zapamietaj_odrzucenie_temperatury(mdl: str) -> None:
    """Dopisuje model do trwałego cache'u — PRZYROSTOWO (read-modify-write).

    Zapis atomowy (tmp + ``os.replace``), wzorem
    ``core_rezyser.zapisz_cache_iso``. Błąd I/O połykamy: brak zapisu oznacza
    tylko jedno jałowe 400 przy następnym starcie, nie awarię generacji.

    Modeli objętych już :data:`_MODELE_BEZ_TEMPERATURY` nie zapisujemy — plik ma
    trzymać wyłącznie to, czego baseline NIE wie (w praktyce: cudze endpointy
    ``openai_compat``). Dla modelu z baseline'u i tak nie wysyłamy
    ``temperature``, więc 400 o nią nie ma skąd przyjść.
    """
    if any(mdl.startswith(prefiks) for prefiks in _MODELE_BEZ_TEMPERATURY):
        return
    _NAUCZONE_BEZ_TEMPERATURY.add(mdl)
    try:
        import i18n

        sciezka = _sciezka_cache_samplingu()
        os.makedirs(os.path.dirname(sciezka), exist_ok=True)
        tmp = sciezka + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "wersja_app": str(i18n.NUMER_WERSJI),
                    "modele": sorted(_NAUCZONE_BEZ_TEMPERATURY),
                },
                fh, ensure_ascii=False, indent=2, sort_keys=True,
            )
        os.replace(tmp, sciezka)
    except Exception:  # noqa: BLE001 — cache best-effort
        pass


# Nauczone w tej instalacji (baseline + to, co dopisał autocache).
_NAUCZONE_BEZ_TEMPERATURY: set[str] = _wczytaj_cache_samplingu()


def honoruje_temperature(mdl: str, temperatura: float) -> bool:
    """Czy wysyłać ``temperature`` do tego modelu.

    ``temperatura`` równa domyślnej jest no-opem i przechodzi wszędzie, więc nie
    ma po co jej wycinać (ani uczyć się o niej czegokolwiek).
    """
    if temperatura == _TEMPERATURA_DOMYSLNA:
        return True
    if mdl in _NAUCZONE_BEZ_TEMPERATURY:
        return False
    return not any(mdl.startswith(prefiks) for prefiks in _MODELE_BEZ_TEMPERATURY)


# ---------------------------------------------------------------------------
# `temperature` jedzie przez `extra_body` — SDK 1.x wyciął ją z sygnatury
# ---------------------------------------------------------------------------
# `anthropic` 1.x nie przyjmuje już `temperature` (ani `top_p`/`top_k`) jako
# kwargu `messages.create` — poleciałby `TypeError`, czyli wyjątek SPRZED HTTP,
# którego reaktywna połowa kontraktu (`czy_odrzucono_temperature`, oparta na
# kodzie 400) nie ma jak złapać. Parametr zniknął z SDK, NIE z API: `extra_body`
# wkleja go do JSON-a żądania as-is.
#
# Zmierzone żywo 2026-09-11 na `anthropic` 1.5.0:
#   claude-haiku-4-5 + extra_body{"temperature": 0.2}  → OK
#   claude-sonnet-5  + extra_body{"temperature": 0.85} → 400 „`temperature` is
#                                                        deprecated for this model."
#   claude-sonnet-5  bez parametru                     → OK
# Komunikat 400 jest ZNAK W ZNAK ten sam, na którym stoi `_co_odrzucono`, więc
# baseline, autocache i drabina degradacji działają dalej bez zmiany w logice —
# przenosimy wyłącznie miejsce, w które wstawiamy wartość. Gałąź `openai_compat`
# tego nie dotyczy (OpenAI dalej ma `temperature` w sygnaturze).
#
# Ta trójka jest PUBLICZNA z tego samego powodu co trójka wyżej: rodzina
# autotłumaczy ma własnych klientów Anthropic i nie może składać tego idiomu
# z prymitywów u siebie.
def temperatura_w_payloadzie(kwargs: dict[str, Any]) -> bool:
    """Czy ``kwargs`` niesie jeszcze ``temperature`` (do wysłania lub zdjęcia)."""
    return "temperature" in kwargs.get("extra_body", {})


def wstaw_temperature(kwargs: dict[str, Any], wartosc: float) -> None:
    """Dokłada ``temperature`` do ``extra_body``, nie gubiąc innych jego pól."""
    kwargs["extra_body"] = {**kwargs.get("extra_body", {}), "temperature": wartosc}


def zdejmij_temperature(kwargs: dict[str, Any]) -> None:
    """Zdejmuje ``temperature``; pusty ``extra_body`` znika razem z nią.

    Pustego dicta nie zostawiamy, żeby payload po degradacji był DOKŁADNIE tym,
    czym był przed przejściem na ``extra_body`` — inaczej porównania „ten sam
    request" (ślad, cache) widziałyby różnicę tam, gdzie jej nie ma.

    ``extra_body`` PODMIENIAMY na nowy dict zamiast robić ``pop`` na starym.
    Ten sam zagnieżdżony dict bywa współdzielony przez zapis payloadu sprzed
    degradacji (płytka kopia ``dict(kwargs)`` w logu, w śladzie, w atrapie
    testowej); mutacja w miejscu cofnęłaby czas także tamtym zapisom i kazała
    im twierdzić, że pierwsza próba też poszła bez parametru.
    """
    cialo = kwargs.get("extra_body")
    if not cialo or "temperature" not in cialo:
        return
    reszta = {k: v for k, v in cialo.items() if k != "temperature"}
    if reszta:
        kwargs["extra_body"] = reszta
    else:
        kwargs.pop("extra_body", None)


def czy_odrzucono_temperature(exc: Exception) -> bool:
    """Czy ten wyjątek to odrzucenie parametru ``temperature`` przez API.

    Reaktywna połowa kontraktu samplingu — dla modelu SPOZA
    :data:`_MODELE_BEZ_TEMPERATURY` (np. podanego przez reżysera w `--model`),
    o którym baseline nic nie wie. Wołający ma po ``True`` zdjąć parametr,
    ponowić i wywołać :func:`zapamietaj_odrzucenie_temperatury`.

    Złożone z dwóch warunków celowo: sam komunikat nie wystarcza (429 albo błąd
    sieci też może zawierać słowo „temperature" w cudzym tekście), a sam kod 400
    tym bardziej nie — tym samym kodem API zgłasza zły schemat, a pomylenie tych
    dwóch przypadków kosztowałoby structured outputs (patrz :func:`_co_odrzucono`).

    Wystawione jako API, żeby rodzina autotłumaczy — która ma WŁASNYCH klientów
    Anthropic, poza :func:`wywolaj_llm` — nie musiała ani składać tej decyzji
    z prymitywów, ani sięgać po prywatne funkcje modułu.
    """
    return _czy_zla_struktura(exc) and _co_odrzucono(exc) == "temperature"


def _co_odrzucono(exc: Exception) -> str | None:
    """Który PARAMETR odrzuciło API — z treści komunikatu 400, nie ze zgadywania.

    Bez tego degradacja jest ślepa i zdejmuje nie to, co trzeba. Konkretny
    scenariusz, na którym to złapaliśmy (2026-08-29): przepisy mają
    ``temperatura: 0.85``, a `claude-sonnet-5` jej nie honoruje, więc 400 dotyczy
    TEMPERATURY — ale drabina „po kolei" zdejmowała najpierw ``output_config``.
    Efekt: structured outputs nie zadziałałyby ANI RAZU w produkcji, a wyjście
    wracałoby do wymuszania JSON promptem, czyli do stanu, który wywołał
    zgłoszenie. Komunikaty API są rozłączne i stabilne:
      * „`temperature` is deprecated for this model."
      * „output_config.format.schema: For 'array' type, property 'maxItems' …"
    Gdy wadliwe jest jedno i drugie, API zgłasza NAJPIERW schemat (zmierzone).

    **`thinking.type` sprawdzamy PRZED `output_config` (migracja na Sonnet 5.5).**
    Odrzucenie ``disabled`` brzmi: „"thinking.type.disabled" is not supported
    for this model. Use "thinking.type.between_tools" … or "thinking.type.adaptive"
    and "output_config.effort" …" — czyli zawiera słowo ``output_config``. Przy
    starej kolejności drabina zdjęłaby structured outputs, a ``thinking`` zostałby
    ten sam, co dało drugie 400. Z tej samej rodziny jest ``output_config.effort``
    (effort nieprzyjęty przy danym trybie myślenia), więc też idzie jako „thinking".
    **Zmierzone żywo 2026-09-29: prawdziwe 400 brzmi INACZEJ niż w przewodniku** —
    „To turn thinking off on this model, send "thinking": {"type": "between_tools"}
    instead of {"type": "disabled"}. …" (bez ``thinking.type`` i bez
    ``output_config``). Łapie je dopiero ogólne sprawdzenie ``"thinking"`` niżej,
    więc tamto zostaje — oba warianty treści siedzą w ``test_thinking_dialekty``.
    """
    tresc = str(exc).lower()
    if "temperature" in tresc:
        return "temperature"
    if ("thinking.type" in tresc or "output_config.effort" in tresc
            or re.search(r"\beffort\b", tresc)):
        return "thinking"
    if "output_config" in tresc or "json_schema" in tresc:
        return "output_config"
    if "thinking" in tresc or "budget_tokens" in tresc:
        return "thinking"
    return None


# ---------------------------------------------------------------------------
# „Bez myślenia" zależy od modelu (migracja na Sonnet 5.5, v19.9)
# ---------------------------------------------------------------------------
# Runtime i rodzina autotłumaczy chodzą BEZ rozszerzonego myślenia (proza/JSON,
# prompty dostrojone pod brak reasoningu — patrz uwaga przy `thinking` niżej).
# Do Sonnet 5 wyrażało się to jednym payloadem `{"type": "disabled"}`. Od Sonnet
# 5.5 są TRZY rozłączne dialekty i każdy model przyjmuje dokładnie jeden:
#   * `disabled`       — Sonnet 5, Opus 5 (≤ high), 4.x, Haiku 4.5;
#   * `between_tools`  — WYŁĄCZNIE Sonnet 5.5 (`disabled` = 400). Myślenie tylko
#                        między wywołaniami narzędzi, a narzędzi nie używamy, więc
#                        to ścisły odpowiednik dawnego `disabled`. Żadnych innych
#                        pól w `thinking`, effort ≤ `high` (nie wysyłamy go);
#   * pominięty param  — Opus 5.5, Fable, Mythos: myślenia nie da się wyłączyć,
#                        każda jawna konfiguracja poza adaptive to 400.
# Hardkod z tego samego powodu co `_MODELE_BEZ_TEMPERATURY`: lustro cudzej
# macierzy modeli. Model spoza list (np. wpisany przez reżysera w YAML) dostaje
# `disabled`, a gdy API go odrzuci, :func:`kolejny_wariant_bez_myslenia` podaje
# następny wariant — drabina przejdzie wszystkie trzy, zanim się podda.
# UWAGA na prefiksy: `claude-sonnet-5-5` zaczyna się od `claude-sonnet-5`, więc
# listy sprawdzamy od najbardziej szczegółowej.
_MODELE_BETWEEN_TOOLS: tuple[str, ...] = (
    "claude-sonnet-5-5",
)
_MODELE_BEZ_WYLACZANIA_MYSLENIA: tuple[str, ...] = (
    "claude-opus-5-5",
    "claude-fable-5",
    "claude-mythos-5",
)

THINKING_WYLACZONE: dict[str, str] = {"type": "disabled"}
THINKING_MIEDZY_NARZEDZIAMI: dict[str, str] = {"type": "between_tools"}

# Effort trybu quality (adaptive thinking). `high` = domyślny poziom Sonnet 5.5
# podany JAWNIE, bo poziomy są rekalibrowane między modelami, a domyślny bywa
# inny (Opus 5.5: `medium`) — jawna wartość nie zmieni się pod nami po cichu.
EFFORT_QUALITY = "high"


def _zdejmij_effort(kwargs: dict[str, Any]) -> None:
    """Zdejmuje ``output_config.effort``; pusty ``output_config`` znika z nim.

    Podmiana zamiast ``pop`` w miejscu — z tego samego powodu co w
    :func:`zdejmij_temperature` (współdzielone płytkie kopie payloadu).
    """
    oc = kwargs.get("output_config")
    if not oc or "effort" not in oc:
        return
    reszta = {k: v for k, v in oc.items() if k != "effort"}
    if reszta:
        kwargs["output_config"] = reszta
    else:
        kwargs.pop("output_config", None)


def thinking_bez_myslenia(mdl: str) -> dict[str, str] | None:
    """Payload ``thinking`` oznaczający „bez myślenia" dla tego modelu.

    ``None`` = parametr POMIJAMY (model nie pozwala wyłączyć myślenia). Zwraca
    świeżą kopię, żeby wołający mógł ją mutować bez ruszania stałych.
    """
    if any(mdl.startswith(p) for p in _MODELE_BETWEEN_TOOLS):
        return dict(THINKING_MIEDZY_NARZEDZIAMI)
    if any(mdl.startswith(p) for p in _MODELE_BEZ_WYLACZANIA_MYSLENIA):
        return None
    return dict(THINKING_WYLACZONE)


def kolejny_wariant_bez_myslenia(
    mdl: str, wyprobowane: list[dict[str, str] | None],
) -> tuple[bool, dict[str, str] | None]:
    """Następny nieprzetestowany wariant „bez myślenia" po odrzuceniu przez API.

    Zwraca ``(jest, wariant)``; ``jest=False`` = wszystkie trzy już padły,
    wołający ma rzucić oryginalny wyjątek. Kolejność: preferowany dla modelu,
    potem pozostałe z :func:`thinking_bez_myslenia` — decyzja NIE opiera się na
    parsowaniu komunikatu (ten wymienia kilka typów naraz), tylko na tym, co już
    wysłaliśmy, więc pętla jest niemożliwa z konstrukcji.
    """
    kandydaci: list[dict[str, str] | None] = [thinking_bez_myslenia(mdl)]
    for k in (dict(THINKING_WYLACZONE), dict(THINKING_MIEDZY_NARZEDZIAMI), None):
        if k not in kandydaci:
            kandydaci.append(k)
    for k in kandydaci:
        if k not in wyprobowane:
            return True, k
    return False, None


def ustaw_thinking(kwargs: dict[str, Any], wariant: dict[str, str] | None) -> None:
    """Wkłada wariant do payloadu; ``None`` zdejmuje klucz ``thinking``."""
    if wariant is None:
        kwargs.pop("thinking", None)
    else:
        kwargs["thinking"] = wariant


def czy_odrzucono_thinking(exc: Exception) -> bool:
    """Czy 400 dotyczy konfiguracji ``thinking`` — odpowiednik
    :func:`czy_odrzucono_temperature` dla rodziny autotłumaczy z własnym klientem.
    """
    return _czy_zla_struktura(exc) and _co_odrzucono(exc) == "thinking"


def schemat_do_api(schema: Any) -> Any:
    """Zwraca KOPIĘ schematu okrojoną do podzbioru akceptowanego przez API.

    Dwie transformacje, obie wymuszone przez structured outputs:
      * zdjęcie :data:`_KLUCZE_NIEWSPIERANE` (rekurencyjnie — także w ``items``,
        ``$defs``, ``properties`` i każdej gałęzi ``anyOf``/``allOf``);
      * ``additionalProperties: false`` w KAŻDYM obiekcie — API odrzuca każdą inną
        wartość, a ``SCHEMA_TURA`` miała tam świadomie ``True``.

    Schemat KANONICZNY (ten w module wołającego) zostaje nietknięty i nadal służy
    do ``jsonschema.validate`` po naszej stronie — czyli kardynalność (``minItems``)
    i długości (``minLength``) są dalej pilnowane, tylko lokalnie, nie przez API.
    """
    if isinstance(schema, dict):
        wynik = {
            k: schemat_do_api(v)
            for k, v in schema.items()
            if k not in _KLUCZE_NIEWSPIERANE
        }
        if wynik.get("type") == "object":
            wynik["additionalProperties"] = False
        notka = _notka_o_ograniczeniach(schema)
        if notka:
            istniejacy = str(wynik.get("description", "")).strip()
            wynik["description"] = f"{istniejacy} {notka}".strip()
        return wynik
    if isinstance(schema, list):
        return [schemat_do_api(v) for v in schema]
    return schema


def _notka_o_ograniczeniach(wezel: dict) -> str:
    """Przenosi zdejmowane limity do ``description`` — po angielsku, zwięźle.

    Po co: API nie przyjmuje ``minItems``/``maxLength``, więc po oczyszczeniu
    schematu model przestaje o nich WIEDZIEĆ (``jsonschema`` je nadal sprawdza,
    ale dopiero po fakcie — czyli kosztem retry). ``description`` jest jedynym
    kanałem, którym możemy mu tę informację podać, a modele te opisy czytają.
    Prompt YAML mówi swoje („3 opcje"); to jest pas bezpieczeństwa na wypadek,
    gdy prompt i schemat się rozjadą.
    """
    czesci: list[str] = []
    dolny, gorny = wezel.get("minItems"), wezel.get("maxItems")
    if dolny is not None and gorny is not None:
        czesci.append(
            f"Provide exactly {dolny} items." if dolny == gorny
            else f"Provide between {dolny} and {gorny} items."
        )
    elif dolny is not None:
        czesci.append(f"Provide at least {dolny} item(s).")
    elif gorny is not None:
        czesci.append(f"Provide at most {gorny} items.")
    if wezel.get("minLength"):
        czesci.append("Must not be empty.")
    if wezel.get("maxLength") is not None:
        czesci.append(f"Keep it under {wezel['maxLength']} characters.")
    return " ".join(czesci)


def schemat_z_dyskryminatorem(schema: dict, tag_odrzucenia: str) -> dict:
    """Schemat API: pola tury + jawna gałąź odmowy, rozdzielone polem ``typ``.

    Problem, który to rozwiązuje: klauzula odrzucenia (``przepisy_rezysera``)
    każe modelowi zwrócić sam tag jako „EXACTLY ONE LINE and NOTHING else" —
    czego wymuszony schemat fizycznie nie dopuszcza. Zmierzone żywo (2026-08-29,
    3 języki): bez tej gałęzi model **rozsmarowuje tag po wszystkich wymaganych
    polach** (``{"opcje":[{"tytul":"[ODRZUCENIE_AI]","opis":"[ODRZUCENIE_AI]"…}]}``).
    Wykrywanie odmowy to przeżywa (``wykryto_odrzucenie`` szuka tagu substringiem
    w surowym tekście, PRZED ``json.loads``), ale zachowanie jest przypadkowe —
    nic nie gwarantuje, że model nie wpisze tagu tylko w jedno pole albo nie
    zacznie improwizować treści zamiast odmówić. Gałąź zamienia to na kontrakt.

    Kształt: ``anyOf`` na ROOT (dwie gałęzie) + pole ``typ`` jako ``const``
    w każdej z nich. To połączenie dwóch wariantów, które zmierzyliśmy osobno,
    i każdy element ma powód:
      * **``anyOf``** — bo tylko osobna gałąź może zachować ``required`` pól tury.
        Wariant „jeden obiekt, ``required: [typ]``" wyglądał prościej, ale model
        POMIJAŁ wtedy pola (tura Opowieści bez ``wybory``), skoro API ich nie
        wymagało — każda taka odpowiedź kosztowałaby jałowe retry na walidacji
        kanonicznej. ``anyOf`` jako rodzeństwo ``properties``/``type`` daje 400,
        więc union MUSI być na root.
      * **``typ`` (dyskryminator)** — bo błędy ``jsonschema`` przy samym ``anyOf``
        raportują porażkę OBU gałęzi i log staje się nieczytelny. Mając ``typ``,
        rozstrzygamy gałąź SAMI (:func:`rozpakuj_dyskryminator`) i walidujemy
        tylko właściwą, schematem kanonicznym.
      * **nietrywialny sentinel** (``typ`` + ``odrzucenie`` wymagane) — zmniejsza
        bias modelu w stronę „tańszej gałęzi" przy długich promptach twórczych.
      * ``powod`` model wypełnia bez proszenia; wołający oddaje go do konsoli
        dewelopera przez :func:`zaloguj_odmowe`. Do ``error_log.txt`` NIE trafia:
        odmowa jest obsłużoną ścieżką, nie awarią, a plik ten użytkownik
        załącza do zgłoszeń i nie chcemy go rozcieńczać nie-błędami.

    ``description`` pól jest po ANGIELSKU i NIE jest tłumaczone — dokładnie jak
    klucze payloadu w ``buduj_wielojezyczne_ui`` („kolejna kotwica PL usunięta",
    audyt 2026-06-16). Schemat leci do modelu przy KAŻDYM wywołaniu w każdym
    z 9 języków, więc polski opis byłby kotwicą ciągnącą fińską czy rosyjską
    generację w stronę polszczyzny — ten sam rozjazd, którego pilnują bramki
    językowe. Złapane bramką ``audyt_leakow --bramka-py``. Opis trzyma też
    kardynalność zdjętą ze schematu API (patrz :func:`_notka_o_ograniczeniach`).

    Kolejność kluczy jest deterministyczna i nic nie jest interpolowane
    per-request: kompilacja schematu po stronie API jest cache'owana bajtowo
    (24 h), a każda zmienna treść zabijałaby ten cache.

    Args:
        schema:          Schemat KANONICZNY tury (np. ``rezyser_ai.SCHEMA_BURZA``).
        tag_odrzucenia:  ``przepisy_rezysera.TAG_ODRZUCENIA_AI`` — podawany
                         parametrem, żeby ``core_llm`` nie importował warstwy
                         przepisów (uniknięcie cyklu).

    Returns:
        Schemat gotowy do ``output_config.format`` — już przepuszczony przez
        :func:`schemat_do_api`.
    """
    baza = schemat_do_api(schema)

    # Gałąź TURY — pola i `required` DOKŁADNIE z kanonicznego schematu, plus
    # `typ` jako const. Zmierzone 2026-08-29: wariant „jeden obiekt, required
    # tylko dla `typ`" powodował, że model POMIJAŁ pola tury (tura Opowieści
    # wróciła bez `wybory`), bo API ich nie wymagało — a walidacja kanoniczna
    # wymaga, więc każda taka odpowiedź kosztowałaby jedno jałowe retry. Dwie
    # gałęzie `anyOf` na ROOT rozwiązują to strukturalnie: wymagalność wraca
    # do API, a odmowa nadal ma legalną drogę wyjścia.
    galaz_tury = dict(baza)
    galaz_tury["properties"] = {
        "typ": {
            "const": TYP_TURA,
            "description": "A normal answer — fill in ALL fields of this branch.",
        },
        **baza.get("properties", {}),
    }
    galaz_tury["required"] = ["typ", *baza.get("required", [])]
    galaz_tury["additionalProperties"] = False

    # Gałąź ODMOWY — sentinel jest NIEtrywialny (`typ` + `odrzucenie` wymagane,
    # `powod` do diagnostyki), żeby model nie uciekał w nią jako „tańszą".
    galaz_odmowy = {
        "type": "object",
        "required": ["typ", "odrzucenie"],
        "additionalProperties": False,
        "properties": {
            "typ": {
                "const": TYP_ODRZUCENIE,
                "description": (
                    "Refusal to carry out the request — see the SYSTEM RULE at "
                    "the end of the system prompt."
                ),
            },
            "odrzucenie": {
                "type": "string",
                "description": f"Verbatim value: {tag_odrzucenia}",
            },
            "powod": {
                "enum": list(_POWODY_ODRZUCENIA),
                "description": "Refusal category (application diagnostics).",
            },
        },
    }
    return {"anyOf": [galaz_tury, galaz_odmowy]}


def rozpakuj_dyskryminator(dane: Any) -> tuple[bool, Any, str]:
    """Normalizuje odpowiedź z dyskryminatorem → ``(czy_odmowa, dane, powod)``.

    Granica parsowania: dalej w kodzie union NIE istnieje — mapowanie do dataclass
    i ``jsonschema.validate`` widzą dokładnie ten kształt, co przed v18.23
    (``typ``/``odrzucenie``/``powod`` są zdjęte). Dzięki temu włączenie schematu
    nie dotknęło ani walidacji, ani GUI.

    Odpowiedź BEZ pola ``typ`` (gałąź ``openai_compat``, która structured outputs
    nie ma, albo model, który dyskryminator zignorował) przechodzi nietknięta —
    czyli stare zachowanie zostaje wariantem domyślnym.
    """
    if not isinstance(dane, dict) or "typ" not in dane:
        return False, dane, ""
    typ = dane.get("typ")
    powod = str(dane.get("powod") or "")
    okrojone = {k: v for k, v in dane.items() if k not in ("typ", "odrzucenie", "powod")}
    return typ == TYP_ODRZUCENIE, okrojone, powod


def zaloguj_odmowe(powod: str, gdzie: str) -> None:
    """Oddaje kategorię odmowy do konsoli dewelopera (nic więcej).

    Trzeci element krotki z :func:`rozpakuj_dyskryminator` był dotąd porzucany
    we wszystkich trzech wołaniach (``_powod``), mimo że schemat prosi model
    o jego wypełnienie, a docstring :func:`schemat_z_dyskryminatorem` obiecywał
    „diagnostykę". Ta funkcja domyka obietnicę najmniejszym możliwym kosztem.

    Świadomie NIE piszemy do ``error_log.txt``: odmowa ma własną, łagodną
    ścieżkę w GUI (stan projektu nietknięty), a plik diagnostyczny użytkownik
    załącza do publicznego zgłoszenia — wpisy o nie-awariach rozcieńczałyby go.
    ``gdzie`` to identyfikator trybu (``"burza"``/``"skrypt"``/``"tura"``), żeby
    log rozróżniał ścieżki bez zaglądania w stack.

    Kategoria pochodzi z zamkniętego zbioru :data:`_POWODY_ODRZUCENIA`, więc
    nie może przenieść ani znaku prozy użytkownika. Nieznaną wartość (model
    zignorował ``enum``) wypisujemy jako ``"?"`` — nie wpuszczamy do logu
    dowolnego stringu od modelu.
    """
    kategoria = powod if powod in _POWODY_ODRZUCENIA else "?"
    _dev_log(f"{gdzie}: model odmówił wykonania (powod={kategoria})")


# ---------------------------------------------------------------------------
# Wskazówki self-correction (v18.23) — NIE cytujemy komunikatu parsera
# ---------------------------------------------------------------------------
# Zgłoszenie z 2026-08-29 pokazało, dlaczego to ma znaczenie. Model wstawił
# przecinek wiszący; `json.loads` zwrócił „Expecting property name enclosed in
# double quotes"; kod odesłał tę treść modelowi jako wskazówkę — a ona wskazuje
# na CUDZYSŁOWY, które były bezbłędne. Model trzy razy „naprawiał" nie tę winę
# i trzy razy powtórzył przecinek. (Cytat historyczny — od CPythona 3.14 ten sam
# przecinek daje „Illegal trailing comma before end of object"; reguła niżej
# tego nie dotyka, bo nie zależy od BRZMIENIA, tylko od tego, co komunikat
# w ogóle opisuje.) Komunikat parsera opisuje POZYCJĘ w tekście,
# którego model już nie widzi; wskazówka musi opisywać WYMAGANĄ STRUKTURĘ
# i prosić o czystą re-emisję całości.
#
# Wspólne dla trzech trybów JSON (Burza, Skrypt, tura Opowieści) — do v18.22
# każdy z nich miał własną kopię tego samego, wadliwego szablonu.
RETRY_NIEPARSOWALNY = (
    "YOUR PREVIOUS OUTPUT WAS NOT VALID JSON and could not be parsed at all. "
    "Do not try to guess which character was wrong — simply emit the whole "
    "response again, from scratch, as ONE valid JSON object. Most common causes: "
    "a trailing comma after the last field or element, markdown code fences "
    "(```json), comments (// or /* */), single quotes instead of double quotes, "
    "or an unescaped double quote inside a string value. Return ONLY the JSON "
    "object — no prose, no fences, no commentary."
)


def komunikat_retry_schema(exc: Exception) -> str:
    """Wskazówka dla modelu przy porażce SCHEMY (nie składni).

    Tu ścieżka pola jest bezpieczna i użyteczna — mówi o polach, nie o pozycji
    w bajtach, więc nie wprowadza modelu w błąd (inaczej niż komunikat parsera).
    """
    sciezka = "/".join(str(krok) for krok in getattr(exc, "absolute_path", [])) or "(root)"
    return (
        "YOUR PREVIOUS OUTPUT WAS VALID JSON BUT DID NOT MATCH THE REQUIRED "
        f"SCHEMA. Offending location: {sciezka}. Constraint violated: "
        f"{getattr(exc, 'validator', '?')}. Regenerate the ENTIRE response so that "
        "every required field is present and has the correct type. Return ONLY "
        "the JSON object."
    )


def _odcisk_schematu(output_config: dict | None) -> str:
    """Krótki hash schematu wysłanego do API (albo ``"no"``, gdy go nie było).

    Po co hash, a nie sama flaga: kompilacja schematu po stronie API jest
    cache'owana bajtowo, więc przy diagnozie trzeba wiedzieć, czy dwie próby
    poszły z DOKŁADNIE tym samym schematem. Hash jest też odporny na to, czego
    do logu nie chcemy — nie ujawnia treści (schemat jej nie zawiera, ale
    wypisywanie całości zaśmiecałoby zgłoszenie).
    """
    if not output_config:
        return "no"
    try:
        surowy = json.dumps(output_config, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return "unserializable"
    return hashlib.sha256(surowy.encode("utf-8")).hexdigest()[:10]


def opisz_srodowisko() -> str:
    """Wersje i locale do nagłówka ``error_log.txt`` — wyłącznie nietreściowe.

    Zbierane tutaj, a nie w ``bledy_ai``, bo tylko warstwa LLM zna wersję SDK
    (``anthropic`` jest importowany leniwie — patrz :func:`zbuduj_klienta`).
    Każdy element odpowiada na inne pytanie z realnej diagnozy: wersja aplikacji
    („czy user ma już patch"), wersja SDK („czy to nie zmiana zachowania
    klienta"), wersja Pythona (środowisko zamrożone vs źródło), locale („czy
    rozjazd nie jest językowy"), provider („Anthropic czy cudzy endpoint").
    """
    czesci = [f"Python: {sys.version.split()[0]}"]
    try:
        import i18n

        czesci.append(f"App: {i18n.NUMER_WERSJI}")
        czesci.append(f"UI locale: {i18n.aktualny_jezyk()}")
    except Exception:  # noqa: BLE001 — diagnostyka nie może wywrócić obsługi błędu
        pass
    try:
        import anthropic

        czesci.append(f"anthropic SDK: {anthropic.__version__}")
    except Exception:  # noqa: BLE001
        pass
    try:
        czesci.append(f"provider: {wczytaj_konfiguracje().provider}")
    except Exception:  # noqa: BLE001
        pass
    return " | ".join(czesci)


def formatuj_slad(slad: list[dict]) -> str:
    """Renderuje ślad wywołań do logu — WYŁĄCZNIE dane nietreściowe.

    Trafia do ``error_log.txt``, czyli do pliku, który komunikat ``err_struktura``
    każe użytkownikowi **dołączyć do publicznego zgłoszenia** — a payload zawiera
    jego nieopublikowaną prozę. Dlatego tu nie ma ani znaku treści: tylko numer
    próby, ``request_id``, ``stop_reason``, obecność schematu i liczniki tokenów.

    ``request_id`` jest identyfikatorem KORELACYJNYM (Messages API nie ma odczytu
    wiadomości po ID) — użyteczny tylko wtedy, gdy maintainer zgłasza problem do
    Anthropic. Wypisujemy KAŻDĄ próbę, bo dopiero zestaw ID odróżnia „trzy razy
    ta sama pętla" od „trzy różne halucynacje" — zwykły użytkownik załączy log po
    pierwszym napotkanym błędzie, więc musi on wystarczyć do tej diagnozy.
    """
    if not slad:
        return "Call trace: (empty)"
    linie = ["Call trace (no content — safe for a public issue):"]
    for wpis in slad:
        linie.append(
            f"  attempt {wpis.get('proba')}: "
            f"model={wpis.get('model')} "
            f"request_id={wpis.get('request_id')} "
            f"stop_reason={wpis.get('stop_reason')} "
            f"schema={wpis.get('schemat')} "
            f"tokens_in={wpis.get('wejscie_tok')} "
            f"tokens_out={wpis.get('wyjscie_tok')}"
        )
    return "\n".join(linie)


def opisz_porazke_json(exc: Exception) -> str:
    """Opisuje porażkę parsowania/walidacji — bez cytowania treści użytkownika.

    Rozróżnienie, które kosztowało zgłoszenie z 2026-08-29: komunikat parsera
    jest bezpieczny i przydatny w LOGU (mówi o pozycji w bajtach, nie o fabule),
    ale NIE WOLNO go wysyłać modelowi jako wskazówki — patrz
    ``rezyser_ai._RETRY_NIEPARSOWALNY``.

    Przy ``ValidationError`` świadomie pomijamy ``exc.message``: potrafi cytować
    wartość, która zawiodła (``'…' is too short``), czyli prozę. Zostaje ścieżka
    + naruszone słowo kluczowe + metryka KSZTAŁTU wartości (typ i długość) —
    ta ostatnia diagnozuje „pusta lista opcji" czy „ucięty string" bez ujawniania,
    co w nim było.
    """
    if isinstance(exc, json.JSONDecodeError):
        return (
            f"Parse failure: {exc.msg} at line {exc.lineno} column {exc.colno} "
            f"(char {exc.pos})."
        )
    sciezka = "/".join(str(krok) for krok in getattr(exc, "absolute_path", [])) or "(root)"
    instancja = getattr(exc, "instance", None)
    ksztalt = type(instancja).__name__
    try:
        ksztalt += f", len={len(instancja)}"
    except TypeError:
        pass
    return (
        f"Schema failure at {sciezka}: constraint '{getattr(exc, 'validator', '?')}' "
        f"violated; offending value shape: {ksztalt}."
    )


def napraw_luzny_json(tekst: str) -> str:
    """Usuwa dwie kosmetyczne skazy, które psują ``json.loads``: fence i przecinek wiszący.

    Pas i szelki dla gałęzi ``openai_compat``, która structured outputs NIE ma
    (i dla modelu, który zignorował schemat). Na Anthropic ze schematem ta funkcja
    nie ma czego naprawiać — API nie dopuszcza takiego wyjścia.

    Naprawiamy WYŁĄCZNIE składnię, nigdy treść:
      * ` ```json … ``` ` — owinięcie w blok kodu (``Expecting value: line 1``);
      * przecinek przed ``}``/``]`` — dokładnie ta skaza, która wywróciła Burzę
        w zgłoszeniu z 2026-08-29.

    Przecinki zdejmuje SKANER, nie regex: naiwne ``,(\\s*[}\\]])`` → ``\\1``
    zjadłoby też przecinek WEWNĄTRZ wartości (``"opis": "wyszli, a potem ]"``),
    czyli cicho zmieniłoby prozę użytkownika. Skaner śledzi, czy jest w stringu,
    i honoruje ``\\"`` — poza stringami zachowanie jest identyczne jak regex.
    """
    czysty = (tekst or "").strip()
    if czysty.startswith("```"):
        # Zdejmujemy pierwszą linię (``` albo ```json) i domykający fence.
        bez_pierwszej = czysty.split("\n", 1)[1] if "\n" in czysty else ""
        koniec = bez_pierwszej.rfind("```")
        czysty = (bez_pierwszej[:koniec] if koniec != -1 else bez_pierwszej).strip()

    wynik: list[str] = []
    w_stringu = False
    ucieczka = False
    for znak in czysty:
        if ucieczka:
            wynik.append(znak)
            ucieczka = False
            continue
        if znak == "\\" and w_stringu:
            wynik.append(znak)
            ucieczka = True
            continue
        if znak == '"':
            w_stringu = not w_stringu
            wynik.append(znak)
            continue
        if not w_stringu and znak in "}]":
            # Cofamy się przez białe znaki; jeśli natrafimy na przecinek — znika.
            i = len(wynik) - 1
            while i >= 0 and wynik[i] in " \t\r\n":
                i -= 1
            if i >= 0 and wynik[i] == ",":
                del wynik[i]
        wynik.append(znak)
    return "".join(wynik)


def _openai_chat(
    klient: "KlientLLM",
    mdl: str,
    msgs: list[dict],
    max_tokens: int,
    temperature: float,
    timeout: float,
    response_format: dict | None = None,
    *,
    bez_temperatury: bool = False,
    klucz_tokenow: str = "max_tokens",
    extra_body: dict | None = None,
) -> tuple[str, str | None]:
    """Pojedyncze wywołanie ``chat.completions`` + normalizacja wyniku/stop_reason.

    ``response_format`` (``{"type": "json_object"}`` dla trybów JSON) doklejamy
    tylko, gdy podane — endpoint, który go nie obsłuży, rzuci 400/422, a drabina
    w :func:`_wywolaj_openai_compat` zdegraduje wywołanie. ``finish_reason=="length"``
    mapujemy na ``"max_tokens"`` (jak Anthropic), żeby wołający trzymali JEDEN warunek
    ucięcia (guard urwanej prozy, tytuły).

    ``bez_temperatury`` / ``klucz_tokenow`` obsługują rodziny modeli, które
    przyjmują wyłącznie domyślny sampling albo nazywają limit tokenów
    ``max_completion_tokens`` (o-*, gpt-5) — używa ich ostatni szczebel drabiny
    degradacji w :func:`_wywolaj_openai_compat`.
    """
    kwargs: dict[str, Any] = dict(
        model=mdl,
        messages=msgs,
    )
    kwargs[klucz_tokenow] = max_tokens
    if not bez_temperatury:
        kwargs["temperature"] = temperature
    if response_format is not None:
        kwargs["response_format"] = response_format
    if extra_body:
        kwargs["extra_body"] = extra_body
    resp = klient.sdk.with_options(timeout=timeout).chat.completions.create(**kwargs)
    choice = resp.choices[0]
    tekst = choice.message.content or ""
    finish = getattr(choice, "finish_reason", None)
    if finish == "length":
        return tekst, "max_tokens"
    # v19.11: Anthropic przez OpenRoutera potrafi zwrócić `content_filter`
    # z pustą treścią i polem `message.refusal` (zmierzone w analizatorze
    # 2026-10-13). To ta sama odmowa klasyfikatora, którą natywne API zgłasza
    # jako `stop_reason="refusal"` — normalizujemy, żeby wołający trzymali JEDEN
    # warunek (inaczej pusta odpowiedź szłaby jako „błąd struktury").
    if finish == "content_filter" or (
            not tekst and getattr(choice.message, "refusal", None)):
        return tekst, STOP_ODRZUCENIE
    return tekst, finish


# Szczebel `json_schema` odrzucony w tej sesji per (provider, model) — kolejne
# wywołania zaczynają od `json_object` i nie płacą jałowym 400 (wzorzec
# `_WORKING_MODE` z `accessible_text_analyst.llm_klient`). Tylko w pamięci:
# endpoint może zacząć wspierać schemat, a sesja to rozsądny horyzont nauki.
_BEZ_JSON_SCHEMA: set[tuple[str, str]] = set()

# Nazwa schematu w `response_format.json_schema.name` — stała, bo kompilacja
# schematu po stronie providera bywa cache'owana bajtowo (jak u Anthropic).
_NAZWA_SCHEMATU = "odpowiedz"


def _wywolaj_openai_compat(
    klient: "KlientLLM",
    mdl: str,
    system: str,
    messages: list[dict],
    segmenty: list[dict] | None,
    wymusz_json: bool,
    max_tokens: int,
    temperature: float,
    timeout: float,
    schema_json: dict | None = None,
    model_baseline: str = "",
) -> tuple[str, str | None]:
    """Gałąź OpenAI-compatible (także OpenRouter) z payloadem ROL + formatem JSON + drabiną degradacji.

    Trzy „zaawansowane" cechy payloadu (każda z cichym fallbackiem, bo egzotyczny
    gateway może jej nie obsłużyć):
      * **role** (gdy ``segmenty`` podane): kontekst narracyjny jako ``assistant``,
        retry/korekty języka jako ``system``, instrukcja jako ``user`` — odtwarza
        jakość utraconą przez zwijanie do jednego ``user``.
      * **json_schema** (v19.11, gdy ``schema_json``): ten sam schemat, który gałąź
        Anthropic wysyła w ``output_config.format``, tu jako
        ``response_format={"type": "json_schema", "json_schema": {..., "strict": true}}``.
        Zmierzone 2026-10-13: OpenRouter przepuszcza go do Claude'a razem
        z ``anyOf`` na roocie (gałąź odmowy z :func:`schemat_z_dyskryminatorem`).
        Do v19.10 compat miał tylko ``json_object``, więc kształt odpowiedzi
        trzymał wyłącznie prompt.
      * **json_object** (gdy ``wymusz_json`` albo schemat odpadł): sygnał JAWNY
        (flaga wołającego), NIE heurystyka „json w prompcie" — ta dawałaby
        false-positive np. na /visualize, którego prompt zawiera „Format: czysty
        tekst (nie JSON)".

    Drabina degradacji (najpełniejszy → zachowanie v18.3): ``json_schema`` →
    ``json_object`` → same role → płaski ``user`` bez formatu. Każdy szczebel niżej
    po błędzie STRUKTURY (400/422 via :func:`_czy_zla_struktura`). Na OSTATNIM
    szczeblu błąd leci wyżej; nie-struktura (429/timeout/sieć/kontekst/nieznany
    model) leci wyżej NATYCHMIAST (→ :func:`wywolaj_llm`).

    Po szczeblach KSZTAŁTU idą szczeble PARAMETRÓW (v18.9): bez ``temperature``
    i z ``max_completion_tokens`` zamiast ``max_tokens`` (rodziny o-*, gpt-5).

    **``temperature`` degraduje się CELOWANIE (v19.11), jak w gałęzi Anthropic.**
    Do v19.10 400 o ``temperature`` zdejmowało najpierw FORMAT i role, bo
    parametry stały na końcu drabiny — na modelu odrzucającym niedomyślną wartość
    każde wywołanie kończyło jako płaski tekst bez JSON-a. Teraz: decyzja wstępna
    z baseline'u (:func:`honoruje_temperature` pytane o ``model_baseline``, czyli
    nazwę natywną — na OpenRouterze ``anthropic/claude-sonnet-5.5`` to
    ``claude-sonnet-5-5``), a 400 rozpoznane przez :func:`_co_odrzucono` jako
    ``temperature`` powtarza TEN SAM szczebel bez parametru.
    """
    plaskie: list[dict] = list(messages)
    if system:
        plaskie = [{"role": "system", "content": system}, *plaskie]

    bogate: list[dict] | None = None
    if segmenty:
        bogate = [{"role": "system", "content": system}] if system else []
        for s in segmenty:
            rola = s.get("rola") or "user"
            if rola not in _ROLE_DOZWOLONE:
                rola = "user"
            bogate.append({"role": rola, "content": s.get("content", "")})

    klucz_schematu = (klient.provider, mdl)
    rs: dict | None = None
    if schema_json is not None and klucz_schematu not in _BEZ_JSON_SCHEMA:
        rs = {
            "type": "json_schema",
            "json_schema": {
                "name": _NAZWA_SCHEMATU, "strict": True, "schema": schema_json,
            },
        }
    rf: dict | None = (
        {"type": "json_object"} if (wymusz_json or schema_json is not None) else None
    )
    glowny = bogate if bogate is not None else plaskie
    sufiks_rol = "+role" if bogate is not None else ""

    # Szczeble KSZTAŁTU: od najpełniejszego do „flat bez formatu" (= v18.3).
    # Krotka: (wiadomości, response_format, opis, bez_temperatury, klucz limitu).
    proby: list[tuple[list[dict], dict | None, str, bool, str]] = []
    if rs is not None:
        proby.append((glowny, rs, "json_schema" + sufiks_rol, False, "max_tokens"))
    if rf is not None:
        proby.append((glowny, rf, "json" + sufiks_rol, False, "max_tokens"))
    if bogate is not None:
        proby.append((bogate, None, "role", False, "max_tokens"))
    proby.append((plaskie, None, "flat", False, "max_tokens"))
    # Szczeble PARAMETRÓW (v18.9) — kształt już najprostszy, więc winne jest
    # coś w parametrach: najpierw zdejmujemy `temperature`, potem zmieniamy
    # nazwę limitu tokenów na `max_completion_tokens`.
    proby.append((plaskie, None, "flat bez temperature", True, "max_tokens"))
    proby.append(
        (plaskie, None, "flat bez temperature + max_completion_tokens",
         True, "max_completion_tokens"))

    bez_temp = not honoruje_temperature(model_baseline or mdl, temperature)
    ostatni = len(proby) - 1
    i = 0
    while i <= ostatni:
        msgs, fmt, opis, bez_temp_szczebla, klucz_tok = proby[i]
        try:
            return _openai_chat(
                klient, mdl, msgs, max_tokens, temperature, timeout, fmt,
                bez_temperatury=bez_temp or bez_temp_szczebla,
                klucz_tokenow=klucz_tok,
            )
        except Exception as exc:  # noqa: BLE001 — degradujemy TYLKO błąd struktury
            if not _czy_zla_struktura(exc):
                raise  # 429/timeout/sieć/kontekst/nieznany model → wyżej
            if not (bez_temp or bez_temp_szczebla) and _co_odrzucono(exc) == "temperature":
                _dev_log(
                    f"{klient.provider}: model '{mdl}' odrzucił 'temperature' — "
                    f"powtarzam szczebel '{opis}' bez tego parametru."
                )
                bez_temp = True
                # Zapis pod TĄ SAMĄ nazwą, o którą pyta `honoruje_temperature`
                # wyżej (audyt v19.11: zapis pod id OpenRoutera, odczyt pod
                # natywnym = jałowe 400 przy każdym wywołaniu).
                zapamietaj_odrzucenie_temperatury(model_baseline or mdl)
                continue   # ten sam szczebel, bez `temperature`
            if i == ostatni:
                raise  # wyczerpana drabina
            if fmt is rs and rs is not None:
                _BEZ_JSON_SCHEMA.add(klucz_schematu)
            _dev_log(
                f"{klient.provider}: endpoint odrzucił payload '{opis}' "
                f"({type(exc).__name__}) — degraduję do prostszego."
            )
            i += 1
    raise RuntimeError("unreachable")  # pętla zawsze zwraca lub rzuca


def _wywolaj_anthropic(
    klient: "KlientLLM",
    mdl: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    timeout: float,
    thinking_budget: int = 0,
    schema_json: dict | None = None,
    slad: list[dict] | None = None,
) -> tuple[str, str | None]:
    """Gałąź Anthropic z degradacją ``temperature`` dla modeli, które ją odrzucają.

    Od Claude Sonnet 5 (i Opus 4.7+/Fable 5) niedomyślna wartość ``temperature``
    zwraca 400 zamiast być po prostu zignorowana. Reżyser może podmienić `model:`
    w YAML na taki model punktowo (patrz :mod:`przepisy_rezysera`) — bez tej
    degradacji dostałby gołego wyjątku zamiast wygenerowanego tekstu. Próbujemy
    NAJPIERW z ``temperature`` z przepisu (kontrola kreatywności per tryb, patrz
    ``temperatura:`` w YAML); dopiero przy błędzie STRUKTURY (400/422, via
    :func:`_czy_zla_struktura`) ponawiamy BEZ tego parametru — model wraca do
    własnego samplingu domyślnego. Modele, które ``temperature`` honorują
    (np. Sonnet 4.6), nigdy nie trafiają w tę ścieżkę.

    ``thinking_budget`` > 0 (18.11, tryb quality tłumacza AI) włącza myślenie:
    od v19.9 adaptive + ``output_config.effort`` = :data:`EFFORT_QUALITY`
    (``budget_tokens`` zwraca 400 od Sonnet 5). ``temperature`` POMIJAMY,
    a ``thinking_budget`` dokładamy PONAD limit odpowiedzi wołającego jako zapas
    na namysł, żeby semantyka ``stop_reason=="max_tokens"`` (guard uciętej
    odpowiedzi / bisekcja tłumacza) nie drgnęła. Bloki ``thinking`` w odpowiedzi
    odfiltrowuje istniejąca sklejka ``type=="text"``. Odrzucenie konfiguracji
    thinking (400/422) → retry z wariantem „bez myślenia" właściwym dla modelu
    (:func:`kolejny_wariant_bez_myslenia` — ``disabled`` / ``between_tools`` /
    pominięty), bez effort i bez ``temperature``.

    ``schema_json`` (v18.23) → ``output_config.format`` (structured outputs):
    kształt odpowiedzi egzekwuje API. Schemat musi być już przepuszczony przez
    :func:`schemat_do_api`. Zdejmujemy go WYŁĄCZNIE wtedy, gdy 400 dotyczy jego
    samego (patrz :func:`_co_odrzucono`) — po zdjęciu wracamy do zachowania
    ≤v18.22, czyli wymuszania JSON promptem + retry u wołającego.

    **Degradacja jest CELOWANA, nie kolejnościowa.** Wcześniejszy wariant „zdejmij
    następny element listy" wyglądał bezpiecznie, ale przy modelu nieprzyjmującym
    ``temperature`` (dziś: domyślny `claude-sonnet-5-5`) zdejmowałby najpierw
    ``output_config`` — czyli structured outputs nie zadziałałyby ANI RAZU
    w produkcji, a wyjście wracałoby do stanu, który wywołał zgłoszenie
    z 2026-08-29. Dodatkowo ``temperature`` nie jest już wysyłana do modeli
    z :data:`_MODELE_BEZ_TEMPERATURY` ani z trwałego autocache'u, więc typowe
    wywołanie nie płaci nawet jednym jałowym round-tripem.

    ``temperature`` wkładamy do payloadu przez :func:`wstaw_temperature`
    (``extra_body``), bo SDK 1.x nie ma jej już w sygnaturze — pomiar i pełne
    uzasadnienie stoją przy tamtej funkcji. Dla drabiny to zmiana bez znaczenia:
    komunikat 400 pozostał ten sam, więc :func:`_co_odrzucono` rozpoznaje
    winowajcę dokładnie jak dotąd.

    ``slad`` (v18.23) → lista, do której dopisujemy metrykę KAŻDEGO wywołania
    (numer próby, ``request_id``, ``stop_reason``, liczniki tokenów). Nie zmienia
    zwracanej krotki, więc żaden z 19 istniejących wołających nie wymaga zmian;
    korzysta z niej diagnostyka ``bledy_ai`` — po ID widać, czy trzy próby to
    ta sama pętla, czy trzy różne halucynacje.
    """
    kwargs: dict[str, Any] = dict(
        model=mdl,
        system=system,
        messages=list(messages),
        max_tokens=max_tokens,
    )
    # „Bez myślenia" per model (`disabled` / `between_tools` / pominięty) —
    # dialekty i uzasadnienie przy `thinking_bez_myslenia`.
    bez_myslenia = thinking_bez_myslenia(mdl)
    ustaw_thinking(kwargs, bez_myslenia)
    wyprobowane_thinking: list[dict[str, str] | None] = [bez_myslenia]
    # `temperature` wysyłamy TYLKO tam, gdzie ma szansę zadziałać (baseline +
    # autocache). Dla `claude-sonnet-5-5` i pokrewnych pomijamy ją od razu, więc
    # nie płacimy jałowym round-tripem przy każdej generacji.
    if honoruje_temperature(mdl, temperature):
        wstaw_temperature(kwargs, temperature)
    else:
        _dev_log(
            f"anthropic: model '{mdl}' nie honoruje niedomyślnej 'temperature' "
            f"({temperature}) — pomijam parametr bez próby (baseline/cache)."
        )
    if schema_json is not None:
        kwargs["output_config"] = {
            "format": {"type": "json_schema", "schema": schema_json},
        }
    if thinking_budget > 0:
        # Tryb quality. `budget_tokens` zwraca 400 od Sonnet 5 (do v19.9 drabina
        # po cichu spadała na `disabled`, więc „quality" = zwykły tryb + jałowy
        # round-trip). Dziś: adaptive thinking + jawny effort, a budżet zostaje
        # ZAPASEM `max_tokens` — myślenie wlicza się w limit, więc bez zapasu
        # guard `stop_reason=="max_tokens"` łapałby odpowiedzi ucięte namysłem.
        zdejmij_temperature(kwargs)
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {
            **kwargs.get("output_config", {}), "effort": EFFORT_QUALITY,
        }
        kwargs["max_tokens"] = max_tokens + thinking_budget
        # Wysłany jest adaptive, NIE `bez_myslenia` — gdyby ten ostatni stał na
        # liście wypróbowanych, drabina po odrzuceniu quality pominęłaby
        # właściwy dialekt modelu (złapane testem: 5.5 spadał na `disabled`).
        wyprobowane_thinking = [dict(kwargs["thinking"])]

    # Degradacja CELOWANA: zdejmujemy to, co API wskazało w komunikacie 400
    # (patrz `_co_odrzucono`), a nie kolejny element listy. Ślepa kolejność
    # kosztowałaby structured outputs przy KAŻDYM modelu nieprzyjmującym
    # `temperature`. Nierozpoznany komunikat → jedna próba awaryjna, w której
    # zdejmujemy wszystko naraz (najbezpieczniejszy payload: default sampling,
    # bez thinking, bez schematu = zachowanie ≤v18.22).
    resp = None
    zdjete: set[str] = set()
    # 7 = temperature + output_config + do trzech wariantów thinking (plus
    # wyjście z quality) + próba awaryjna. Każdy szczebel jest jednorazowy,
    # więc limit tylko zabezpiecza, pętli nie ogranicza.
    for _krok in range(7):
        try:
            resp = klient.sdk.with_options(timeout=timeout).messages.create(**kwargs)
            break
        except Exception as exc:  # noqa: BLE001 — degradujemy TYLKO błąd struktury
            if not _czy_zla_struktura(exc):
                raise
            winowajca = _co_odrzucono(exc)
            if winowajca in zdjete or (
                winowajca is None and "awaryjnie" in zdjete
            ):
                raise   # już to zdjęliśmy, a błąd wraca — nie ma czego degradować
            if winowajca == "temperature":
                _dev_log(
                    f"anthropic: model '{mdl}' odrzucił 'temperature' "
                    f"({type(exc).__name__}) — ponawiam bez tego parametru "
                    "i zapamiętuję model w cache."
                )
                zdejmij_temperature(kwargs)
                zapamietaj_odrzucenie_temperatury(mdl)
            elif winowajca == "output_config":
                _dev_log(
                    f"anthropic: model/endpoint '{mdl}' odrzucił 'output_config' "
                    f"({type(exc).__name__}) — ponawiam bez structured outputs "
                    "(JSON wymuszany samym promptem, jak ≤v18.22)."
                )
                kwargs.pop("output_config", None)
            elif winowajca == "thinking":
                # Z quality (adaptive + effort) schodzimy na „bez myślenia";
                # z „bez myślenia" — na następny dialekt. Nigdy dwa razy ten sam.
                jest, wariant = kolejny_wariant_bez_myslenia(
                    mdl, wyprobowane_thinking)
                if not jest:
                    raise
                _dev_log(
                    f"anthropic: model '{mdl}' odrzucił 'thinking' "
                    f"{kwargs.get('thinking')} ({type(exc).__name__}) — "
                    f"ponawiam z {wariant} (bez trybu quality)."
                )
                wyprobowane_thinking.append(wariant)
                ustaw_thinking(kwargs, wariant)
                _zdejmij_effort(kwargs)
                kwargs["max_tokens"] = max_tokens
                continue   # szczebel thinking rozlicza `wyprobowane_thinking`
            else:
                _dev_log(
                    f"anthropic: model '{mdl}' odrzucił payload komunikatem, "
                    f"którego nie rozpoznaję ({type(exc).__name__}: "
                    f"{str(exc)[:120]}) — ponawiam z najprostszym payloadem."
                )
                zdejmij_temperature(kwargs)
                kwargs.pop("output_config", None)
                # Wariant „bez myślenia", który JUŻ przeszedł walidację, zostaje
                # (reset do `bez_myslenia` wskrzeszał dialekt odrzucony wcześniej
                # — audyt v19.9). Z quality schodzimy na NASTĘPNY niewypróbowany.
                if kwargs.get("thinking") == {"type": "adaptive"}:
                    jest, wariant = kolejny_wariant_bez_myslenia(
                        mdl, wyprobowane_thinking)
                    if jest:
                        wyprobowane_thinking.append(wariant)
                        ustaw_thinking(kwargs, wariant)
                kwargs["max_tokens"] = max_tokens
                winowajca = "awaryjnie"
            zdjete.add(winowajca)

    tekst = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    )
    stop = getattr(resp, "stop_reason", None)
    if slad is not None:
        uzycie = getattr(resp, "usage", None)
        slad.append({
            "proba":      len(slad) + 1,
            "model":      mdl,
            "request_id": getattr(resp, "_request_id", None),
            "stop_reason": stop,
            # Sam `format` — `effort` trybu quality to nie schemat, a jego
            # obecność zmieniłaby odcisk i udawała „inny schemat" w diagnozie.
            "schemat":    _odcisk_schematu(
                {"format": kwargs["output_config"]["format"]}
                if "format" in kwargs.get("output_config", {}) else None),
            "wejscie_tok":  getattr(uzycie, "input_tokens", None),
            "wyjscie_tok":  getattr(uzycie, "output_tokens", None),
        })
    return tekst, stop


def model_wywolania(klient: KlientLLM, model: str) -> str:
    """Nazwa modelu, która faktycznie pójdzie do endpointu tego klienta."""
    if klient.provider == PROVIDER_OPENAI_COMPAT and klient.model_override:
        return klient.model_override
    if klient.provider == PROVIDER_OPENROUTER:
        # Mapowanie także dla `LLM_MODEL` (audyt v19.11): `claude-opus-5-5`
        # w configu to ten sam Opus; id z `/` przechodzi nietknięte.
        return model_dla_openroutera(klient.model_override or model)
    # Anthropic: override ustawia WYŁĄCZNIE zapas autotłumaczy z trybu
    # OpenRouter (natywny odpowiednik `anthropic/…` z `LLM_MODEL`).
    return klient.model_override or model


def _opakuj_blad(exc: Exception, mdl: str, provider: str) -> BladLLM | None:
    """Wyjątek SDK → nasz typ (limit, timeout, kontekst, nieznany model).

    ``None`` = nie opakowujemy, wołający robi gołe ``raise``. JEDNA mapa dla
    :func:`wywolaj_llm` i :func:`wywolaj_llm_z_pdf` — druga kopia tej
    kolejności rozjechałaby się przy pierwszej nowej klasie błędu.
    """
    if _czy_nieznany_model(exc):
        return BladModeluLLM(mdl, provider)
    if _czy_rate_limit(exc):
        return BladLimituLLM(str(exc))
    if _czy_timeout(exc):
        return BladTimeoutLLM(str(exc))
    if _czy_przepelniony_kontekst(exc):
        return BladKontekstuLLM(str(exc))
    return None


def wywolaj_llm(
    klient: KlientLLM,
    *,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    timeout: float,
    segmenty: list[dict] | None = None,
    wymusz_json: bool = False,
    thinking_budget: int = 0,
    schema_json: dict | None = None,
    slad: list[dict] | None = None,
) -> tuple[str, str | None]:
    """Wywołuje LLM i zwraca ``(tekst, stop_reason)`` — wspólnie dla obu providerów.

    Różnice API ukryte tu:
      * **prompt systemowy** — Anthropic ma osobny ``system=``; OpenAI dokleja go
        jako pierwszą wiadomość ``role=system`` (gdy niepusty).
      * **reasoning** — Anthropic ``thinking``: domyślnie „bez myślenia" w
        dialekcie modelu (``disabled``, na Sonnet 5.5 ``between_tools`` — patrz
        :func:`thinking_bez_myslenia`); ``thinking_budget`` > 0 włącza myślenie (18.11,
        tryb quality tłumacza AI — patrz :func:`_wywolaj_anthropic`).
        W ``openai_compat`` parametr IGNOROWANY — cicha degradacja, ten sam
        wzorzec co ``segmenty``/``wymusz_json`` niżej.
      * **odpowiedź** — Anthropic skleja bloki ``content[].text``; OpenAI bierze
        ``choices[0].message.content``.
      * **stop_reason** — OpenAI ``finish_reason=="length"`` mapujemy na
        ``"max_tokens"`` (jak Anthropic), żeby wołający trzymali JEDEN warunek
        ucięcia (guard urwanej prozy, tytuły).

    ``segmenty`` (opcjonalne) — równoległa reprezentacja ``messages`` z PRAWDZIWYMI
    rolami (``[{"rola": "system"|"assistant"|"user", "content": str}, ...]``).
    Czyta je **wyłącznie** gałąź ``openai_compat`` (przywrócenie ról pre-v18 — patrz
    :func:`_wywolaj_openai_compat`). Gałąź **Anthropic IGNORUJE** ``segmenty`` i
    używa ``messages`` dokładnie jak dotąd (filar jakości pozostaje nietknięty;
    Anthropic wymaga pierwszej wiadomości ``user`` i nie przyjmuje luźnych ``system``).
    Brak ``segmenty`` → compat działa po staremu (płaski blok ``user``).

    ``wymusz_json`` (opcjonalne) — JAWNY sygnał, że wołający WALIDUJE JSON (Burza/
    Skrypt/tura Opowieści). W ``openai_compat`` przekłada się na
    ``response_format={"type": "json_object"}`` (z degradacją gdy endpoint go nie
    obsłuży). NIE używamy heurystyki „json w prompcie": /visualize ma prompt
    „czysty tekst (nie JSON)", więc substring dałby false-positive i zepsuł prozę.

    ``schema_json`` (v18.23) — schemat structured outputs, już okrojony przez
    :func:`schemat_do_api`. Anthropic wysyła go w ``output_config.format``; od
    v19.11 gałąź compat/OpenRouter wysyła ten sam schemat jako
    ``response_format`` typu ``json_schema`` (strict) na szczycie drabiny, a gdy
    endpoint go odrzuci, schodzi do ``json_object`` + tolerancyjnego parsowania
    (:func:`napraw_luzny_json`) u wołającego — ten sam wzorzec cichej
    degradacji, co ``segmenty``.

    ``slad`` (v18.23, TYLKO Anthropic) — lista, do której dopisujemy metrykę
    każdego wywołania (próba, ``request_id``, ``stop_reason``, tokeny). Wyłącznie
    dane NIE-treściowe: log trafia do publicznego zgłoszenia, a payload zawiera
    nieopublikowaną prozę użytkownika.

    W trybie ``openai_compat`` nazwę modelu nadpisuje ``klient.model_override``
    (``LLM_MODEL``) — argument ``model`` (z przepisu YAML) jest wtedy ignorowany.
    W trybie ``openrouter`` ``LLM_MODEL`` jest OPCJONALNY: bez niego model
    z przepisu przechodzi przez :func:`model_dla_openroutera`. Endpoint, który
    modelu nie zna, daje :class:`BladModeluLLM` (zlokalizowany ``str``).

    ``temperature`` w gałęzi Anthropic ma degradację (patrz :func:`_wywolaj_anthropic`):
    modele, które odrzucają niedomyślną wartość (Claude Sonnet 5 i nowsze), dostają
    retry bez tego parametru zamiast wywalać wyjątek — patrz [[reguly_architektury]].

    Rate-limit (429) i wyczerpane kredyty (400/402, :func:`czy_brak_kredytow`)
    → :class:`BladLimituLLM`, timeout → :class:`BladTimeoutLLM`,
    przepełnione okno kontekstowe (400 z frazą / 413) → :class:`BladKontekstuLLM`
    (wszystkie dla dowolnego providera). Pozostałe wyjątki SDK propagują natywnie
    (łapie je szeroki ``except`` wołającego).
    """
    mdl = model_wywolania(klient, model)

    try:
        if klient.provider in (PROVIDER_OPENAI_COMPAT, PROVIDER_OPENROUTER):
            wynik = _wywolaj_openai_compat(
                klient, mdl, system, messages, segmenty, wymusz_json,
                max_tokens, temperature, timeout,
                schema_json=schema_json,
                model_baseline=model_natywny(mdl),
            )
        else:
            # Anthropic (domyślny filar jakości) — `segmenty`/`wymusz_json` celowo
            # nieużywane; kształt JSON wymusza `schema_json` (structured outputs).
            wynik = _wywolaj_anthropic(
                klient, mdl, system, messages, max_tokens, temperature, timeout,
                thinking_budget=thinking_budget,
                schema_json=schema_json,
                slad=slad,
            )
        klient.udane = True
        return wynik

    except Exception as exc:  # noqa: BLE001 — 429/timeout/kontekst opakowujemy; reszta leci dalej
        if przelacz_na_zapas(klient, exc):
            # Ten sam request, już przez OpenRoutera. `zapas` jest po
            # przełączeniu `None`, więc rekurencja ma dokładnie jeden poziom.
            return wywolaj_llm(
                klient, model=model, system=system, messages=messages,
                max_tokens=max_tokens, temperature=temperature, timeout=timeout,
                segmenty=segmenty, wymusz_json=wymusz_json,
                thinking_budget=thinking_budget, schema_json=schema_json,
                slad=slad,
            )
        opakowany = _opakuj_blad(exc, mdl, klient.provider)
        if opakowany is None:
            raise
        raise opakowany from exc


# ---------------------------------------------------------------------------
# PDF jako wejście (v19.14) — strony bez warstwy tekstu czytane modelem z obrazem
# ---------------------------------------------------------------------------
#: Silnik parsera PDF w OpenRouterze. `native` = PDF trafia do modelu tak jak
#: w natywnym API (zmierzone 2026-10-16: 1993 tokeny wejścia po obu stronach).
#: Bez jawnego silnika OpenRouter wybiera go sam: dla modelu bez natywnego
#: PDF-a byłby to płatny OCR albo `pdf-text`, który ze skanu oddaje pustkę.
_OPENROUTER_PDF_PLUGIN: dict = {"id": "file-parser", "pdf": {"engine": "native"}}

#: Myślenie przez OpenRoutera. Wyłączyć się go nie da: `enabled: false`
#: i `effort: none` kończą się 400 „Reasoning is mandatory for this endpoint”.
#: Domyślne kosztowało ok. 1100 tokenów wyjścia na stronę skanu, a `low`
#: 577, czyli tyle, co natywne `between_tools` (zmierzone 2026-10-16).
_OPENROUTER_REASONING_PDF: dict = {"effort": "low"}


def _pdf_openrouter(
    klient: KlientLLM, mdl: str, system: str, b64: str,
    tekst_przed: str, tekst_po: str, max_tokens: int, timeout: float,
) -> tuple[str, str | None]:
    """PDF jako część ``file`` (data URL) w ``chat.completions`` OpenRoutera."""
    czesci: list[dict] = []
    if tekst_przed:
        czesci.append({"type": "text", "text": tekst_przed})
    czesci.append({"type": "file", "file": {
        "filename": "strona.pdf",
        "file_data": "data:application/pdf;base64," + b64,
    }})
    czesci.append({"type": "text", "text": tekst_po})
    msgs: list[dict] = [{"role": "system", "content": system}] if system else []
    msgs.append({"role": "user", "content": czesci})
    extra = {"plugins": [_OPENROUTER_PDF_PLUGIN], "reasoning": _OPENROUTER_REASONING_PDF}
    # Sampling domyślny: transkrypcja nie ma czego stroić, a rodzina 5.x
    # i tak odrzuca niedomyślną `temperature`.
    try:
        return _openai_chat(klient, mdl, msgs, max_tokens, _TEMPERATURA_DOMYSLNA,
                            timeout, bez_temperatury=True, extra_body=extra)
    except Exception as exc:  # noqa: BLE001 — degradujemy TYLKO odrzucone `reasoning`
        # Model bez myślenia wskazany przez `LLM_MODEL` może odrzucić sam
        # parametr — wtedy jedno ponowienie bez niego. Każdy inny 400 leci
        # wyżej, bo żadne ponowienie go nie naprawi.
        if not (_czy_zla_struktura(exc) and "reasoning" in str(exc).lower()):
            raise
        _dev_log(f"openrouter: model '{mdl}' odrzucił 'reasoning' — ponawiam bez niego.")
        return _openai_chat(klient, mdl, msgs, max_tokens, _TEMPERATURA_DOMYSLNA,
                            timeout, bez_temperatury=True,
                            extra_body={"plugins": [_OPENROUTER_PDF_PLUGIN]})


def wywolaj_llm_z_pdf(
    klient: KlientLLM,
    *,
    model: str,
    system: str,
    pdf: bytes,
    tekst_po: str,
    max_tokens: int,
    timeout: float,
    tekst_przed: str = "",
    slad: list[dict] | None = None,
) -> tuple[str, str | None]:
    """Wywołanie z PDF-em w treści, ``(tekst, stop_reason)`` jak w :func:`wywolaj_llm`.

    Użycie: odczyt strony bez warstwy tekstu (`core_skany`, v19.14). Treść
    wiadomości ``user`` = ``tekst_przed`` (opcjonalny kontekst) → PDF →
    ``tekst_po`` (instrukcja). Tę kolejność zaleca dokumentacja Anthropic:
    dokument przed pytaniem.

      * **anthropic**: blok ``document`` (base64) przez :func:`_wywolaj_anthropic`,
        czyli tę samą drabinę ``thinking`` / ``temperature`` (na Sonnet 5.5
        ``between_tools``: 420–610 tokenów wyjścia na stronę, zmierzone);
      * **openrouter**: część ``file`` + parser ``native`` + ``reasoning`` low
        (:func:`_pdf_openrouter`);
      * **openai_compat**: :class:`BladFunkcjiNiedostepnej`. Obsługa PDF-ów
        i obrazów na cudzym endpoincie to loteria, której nie umiemy zmierzyć
        (decyzja D3, 2026-10-16).

    Błędy SDK przechodzą przez :func:`_opakuj_blad`, tę samą mapę co
    w :func:`wywolaj_llm`. Zapasu autotłumaczy (``klient.zapas``) tu nie ma:
    ustawia go tylko dev-tooling, a ta funkcja jest runtime'owa.
    """
    if klient.provider == PROVIDER_OPENAI_COMPAT:
        raise BladFunkcjiNiedostepnej("pdf", klient.provider)
    mdl = model_wywolania(klient, model)
    b64 = base64.standard_b64encode(pdf).decode("ascii")
    try:
        if klient.provider == PROVIDER_OPENROUTER:
            wynik = _pdf_openrouter(klient, mdl, system, b64, tekst_przed,
                                    tekst_po, max_tokens, timeout)
        else:
            tresc: list[dict] = []
            if tekst_przed:
                tresc.append({"type": "text", "text": tekst_przed})
            tresc.append({"type": "document", "source": {
                "type": "base64", "media_type": "application/pdf", "data": b64,
            }})
            tresc.append({"type": "text", "text": tekst_po})
            wynik = _wywolaj_anthropic(
                klient, mdl, system, [{"role": "user", "content": tresc}],
                max_tokens, _TEMPERATURA_DOMYSLNA, timeout, slad=slad,
            )
        klient.udane = True
        return wynik
    except Exception as exc:  # noqa: BLE001 — 429/timeout/kontekst opakowujemy; reszta leci dalej
        opakowany = _opakuj_blad(exc, mdl, klient.provider)
        if opakowany is None:
            raise
        raise opakowany from exc
