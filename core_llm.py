"""core_llm.py — provider-agnostic warstwa wywołań LLM (Anthropic ⟷ OpenAI-compatible).

POJEDYNCZE źródło prawdy dla „zbuduj klienta + wywołaj model". Dotąd każdy panel
(`gui_rezyser`, `gui_opowiesci`, `gui_poliglota`) budował klienta `anthropic.Anthropic`
na sztywno, a moduły `*_ai.py` wołały `klient.messages.create(...)` bezpośrednio. Od
v18.4 cała warstwa runtime przechodzi przez ten moduł, dzięki czemu reżyser może wskazać
DOWOLNY endpoint zgodny z OpenAI (`base_url` + klucz + nazwa modelu) — OpenRouter,
Cerebras, Fireworks, DeepSeek, Groq, endpoint OpenAI-compat Gemini, lokalne Ollama —
JEDNĄ ścieżką kodu, bez utrzymywania osobnej integracji per provider.

Zasada: **Anthropic / Claude = domyślny, rekomendowany filar jakości** (prompty są pod
niego dostrojone). OpenAI-compat = opcja zaawansowana (bring-your-own-endpoint); inne
modele mogą dać niższą jakość — to świadomy wybór reżysera (koszt↔jakość).

Moduł jest wx-free i SDK-lazy: `anthropic`/`openai` importujemy dopiero w
:func:`zbuduj_klienta`, więc gdy end-user zostaje na Anthropic, `openai` nie jest
wciągany do `.exe` (lekki bundla single-provider — patrz CLAUDE.md pkt 7).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

# Identyfikatory providerów (wartość pola `LLM_PROVIDER` w golden_key.env).
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI_COMPAT = "openai_compat"

# Brak/niepoprawny `LLM_PROVIDER` → Anthropic (end-user z samym ANTHROPIC_API_KEY
# nie zauważa żadnej zmiany względem ≤v18.3).
DOMYSLNY_PROVIDER = PROVIDER_ANTHROPIC


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


# ---------------------------------------------------------------------------
# Konfiguracja czytana z golden_key.env (po load_dotenv przez wołającego)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KonfiguracjaLLM:
    """Migawka konfiguracji LLM z ``golden_key.env``.

    Pola ``base_url``/``model`` mają znaczenie wyłącznie dla ``openai_compat``.
    W trybie ``anthropic`` model bierze się z YAML przepisu (``claude-sonnet-4-6``).
    """

    provider: str = DOMYSLNY_PROVIDER
    anthropic_key: str = ""
    openai_key: str = ""
    base_url: str = ""
    model: str = ""   # LLM_MODEL — nadpisuje `przepis.model` w trybie compat

    @property
    def kompletna(self) -> bool:
        """Czy konfiguracja wystarcza do zbudowania działającego klienta."""
        if self.provider == PROVIDER_OPENAI_COMPAT:
            return bool(self.openai_key and self.base_url and self.model)
        # Anthropic: ten sam warunek co dawny `_init_api` (`sk-ant-`).
        return bool(self.anthropic_key and self.anthropic_key.startswith("sk-ant-"))


def wczytaj_konfiguracje() -> KonfiguracjaLLM:
    """Czyta konfigurację z ``os.environ`` (wołający robi ``load_dotenv`` PRZED).

    Nieznana wartość ``LLM_PROVIDER`` → cichy fallback do Anthropic (bezpieczny
    default, zgodny ze stanem ≤v18.3).
    """
    provider = (os.getenv("LLM_PROVIDER", "") or DOMYSLNY_PROVIDER).strip().lower()
    if provider not in (PROVIDER_ANTHROPIC, PROVIDER_OPENAI_COMPAT):
        provider = DOMYSLNY_PROVIDER
    return KonfiguracjaLLM(
        provider=provider,
        anthropic_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        openai_key=os.getenv("OPENAI_API_KEY", "").strip(),
        base_url=os.getenv("LLM_BASE_URL", "").strip(),
        model=os.getenv("LLM_MODEL", "").strip(),
    )


# ---------------------------------------------------------------------------
# Klient + budowa
# ---------------------------------------------------------------------------
@dataclass
class KlientLLM:
    """Lekki wrapper nad klientem SDK + znacznik providera.

    ``model_override`` (z ``LLM_MODEL``) służy tylko trybowi ``openai_compat`` —
    nadpisuje nazwę modelu z przepisu YAML (na cudzym endpoincie ``claude-sonnet-4-6``
    nie istnieje). W trybie Anthropic pozostaje pusty i model bierze się z przepisu.
    """

    provider: str
    sdk: Any
    model_override: str = ""


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
        import anthropic  # noqa: PLC0415
        sdk = anthropic.Anthropic(api_key=konfig.anthropic_key)
        return KlientLLM(PROVIDER_ANTHROPIC, sdk)
    except Exception:  # noqa: BLE001 — zły klucz/URL/SDK = brak klienta, nie crash startu
        return None


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
    return status == 429


def _czy_timeout(exc: Exception) -> bool:
    """Czy wyjątek to przekroczenie czasu (``APITimeoutError`` w obu SDK)."""
    return type(exc).__name__ == "APITimeoutError"


def wywolaj_llm(
    klient: KlientLLM,
    *,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> tuple[str, str | None]:
    """Wywołuje LLM i zwraca ``(tekst, stop_reason)`` — wspólnie dla obu providerów.

    Różnice API ukryte tu:
      * **prompt systemowy** — Anthropic ma osobny ``system=``; OpenAI dokleja go
        jako pierwszą wiadomość ``role=system`` (gdy niepusty).
      * **reasoning** — Anthropic ``thinking={"type":"disabled"}`` (proza, bez
        narzutu); w OpenAI param pomijany.
      * **odpowiedź** — Anthropic skleja bloki ``content[].text``; OpenAI bierze
        ``choices[0].message.content``.
      * **stop_reason** — OpenAI ``finish_reason=="length"`` mapujemy na
        ``"max_tokens"`` (jak Anthropic), żeby wołający trzymali JEDEN warunek
        ucięcia (guard urwanej prozy, tytuły).

    W trybie ``openai_compat`` nazwę modelu nadpisuje ``klient.model_override``
    (``LLM_MODEL``) — argument ``model`` (z przepisu YAML) jest wtedy ignorowany.

    Rate-limit (429) → :class:`BladLimituLLM`, timeout → :class:`BladTimeoutLLM`
    (oba dla dowolnego providera). Pozostałe wyjątki SDK propagują natywnie
    (łapie je szeroki ``except`` wołającego).
    """
    if klient.provider == PROVIDER_OPENAI_COMPAT and klient.model_override:
        mdl = klient.model_override
    else:
        mdl = model

    try:
        if klient.provider == PROVIDER_OPENAI_COMPAT:
            msgs: list[dict] = list(messages)
            if system:
                msgs = [{"role": "system", "content": system}, *msgs]
            resp = klient.sdk.with_options(timeout=timeout).chat.completions.create(
                model=mdl,
                messages=msgs,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            choice = resp.choices[0]
            tekst = choice.message.content or ""
            finish = getattr(choice, "finish_reason", None)
            return tekst, ("max_tokens" if finish == "length" else finish)

        # Anthropic (domyślny filar jakości)
        resp = klient.sdk.with_options(timeout=timeout).messages.create(
            model=mdl,
            system=system,
            messages=list(messages),
            max_tokens=max_tokens,
            temperature=temperature,
            thinking={"type": "disabled"},
        )
        tekst = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        )
        return tekst, getattr(resp, "stop_reason", None)

    except Exception as exc:  # noqa: BLE001 — 429/timeout opakowujemy; reszta leci dalej
        if _czy_rate_limit(exc):
            raise BladLimituLLM(str(exc)) from exc
        if _czy_timeout(exc):
            raise BladTimeoutLLM(str(exc)) from exc
        raise
