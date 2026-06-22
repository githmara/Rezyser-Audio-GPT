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
import sys
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


def _czy_zla_struktura(exc: Exception) -> bool:
    """Czy błąd to odrzucenie STRUKTURY payloadu (zła rola/kolejność), nie limit/sieć.

    Heurystyka bez importu SDK: nazwa klasy (``BadRequestError`` /
    ``UnprocessableEntityError``) lub status 400/422. 429/timeout/5xx świadomie
    NIE są tu łapane — to nie problem struktury, więc nie chcemy ich maskować
    fallbackiem (lecą wyżej do :func:`wywolaj_llm` → ``BladLimituLLM`` itp.).
    Używane wyłącznie w gałęzi ``openai_compat`` do decyzji o cichym fallbacku
    z payloadu z rolami (system/assistant/user) na pojedynczy blok ``user``.
    """
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


def _openai_chat(
    klient: "KlientLLM",
    mdl: str,
    msgs: list[dict],
    max_tokens: int,
    temperature: float,
    timeout: float,
    response_format: dict | None = None,
) -> tuple[str, str | None]:
    """Pojedyncze wywołanie ``chat.completions`` + normalizacja wyniku/stop_reason.

    ``response_format`` (``{"type": "json_object"}`` dla trybów JSON) doklejamy
    tylko, gdy podane — endpoint, który go nie obsłuży, rzuci 400/422, a drabina
    w :func:`_wywolaj_openai_compat` zdegraduje wywołanie. ``finish_reason=="length"``
    mapujemy na ``"max_tokens"`` (jak Anthropic), żeby wołający trzymali JEDEN warunek
    ucięcia (guard urwanej prozy, tytuły).
    """
    kwargs: dict[str, Any] = dict(
        model=mdl,
        messages=msgs,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = klient.sdk.with_options(timeout=timeout).chat.completions.create(**kwargs)
    choice = resp.choices[0]
    tekst = choice.message.content or ""
    finish = getattr(choice, "finish_reason", None)
    return tekst, ("max_tokens" if finish == "length" else finish)


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
) -> tuple[str, str | None]:
    """Gałąź OpenAI-compatible z payloadem ROL + ``response_format`` + drabiną degradacji.

    Dwie „zaawansowane" cechy payloadu przywrócone z ery pre-v18 (obie z cichym
    fallbackiem, bo egzotyczny gateway może ich nie obsłużyć):
      * **role** (gdy ``segmenty`` podane): kontekst narracyjny jako ``assistant``,
        retry/korekty języka jako ``system``, instrukcja jako ``user`` — odtwarza
        jakość utraconą przez zwijanie do jednego ``user``.
      * **response_format** (gdy ``wymusz_json``): ``{"type": "json_object"}`` dla
        trybów, które WALIDUJĄ JSON (Burza/Skrypt/tura Opowieści). Sygnał jest
        JAWNY (flaga wołającego), NIE heurystyką „json w prompcie" — ta dawałaby
        false-positive np. na /visualize, którego prompt zawiera „Format: czysty
        tekst (nie JSON)".

    Drabina degradacji (najpełniejszy → dotychczasowe zachowanie v18.3): degradujemy
    NAJPIERW ``response_format`` (najczęściej nieobsługiwany), potem role, aż do
    płaskiego ``user`` bez formatu. Każdy szczebel niżej po błędzie STRUKTURY
    (400/422 via :func:`_czy_zla_struktura`). Na OSTATNIM szczeblu błąd leci wyżej;
    nie-struktura (429/timeout/sieć) leci wyżej NATYCHMIAST (→ :func:`wywolaj_llm`).
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

    rf: dict | None = {"type": "json_object"} if wymusz_json else None
    glowny = bogate if bogate is not None else plaskie

    # Szczeble od najpełniejszego do „flat bez formatu" (= v18.3). Płaski user-only
    # ZAWSZE jest ostatni — gwarantuje powrót do dotychczasowego zachowania.
    proby: list[tuple[list[dict], dict | None, str]] = []
    if rf is not None:
        proby.append((glowny, rf, "json" + ("+role" if bogate is not None else "")))
    if bogate is not None:
        proby.append((bogate, None, "role"))
    proby.append((plaskie, None, "flat"))

    ostatni = len(proby) - 1
    for i, (msgs, fmt, opis) in enumerate(proby):
        try:
            return _openai_chat(klient, mdl, msgs, max_tokens, temperature, timeout, fmt)
        except Exception as exc:  # noqa: BLE001 — degradujemy TYLKO błąd struktury
            if i == ostatni or not _czy_zla_struktura(exc):
                raise  # wyczerpana drabina ALBO 429/timeout/sieć → wyżej
            _dev_log(
                f"openai_compat: endpoint odrzucił payload '{opis}' "
                f"({type(exc).__name__}) — degraduję do prostszego."
            )
    raise RuntimeError("unreachable")  # pętla zawsze zwraca lub rzuca


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
    obsłuży). Anthropic IGNORUJE — wymusza JSON promptem, nie parametrem. NIE używamy
    heurystyki „json w prompcie": /visualize ma prompt „czysty tekst (nie JSON)",
    więc substring dałby false-positive i zepsuł prozę.

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
            return _wywolaj_openai_compat(
                klient, mdl, system, messages, segmenty, wymusz_json,
                max_tokens, temperature, timeout,
            )

        # Anthropic (domyślny filar jakości) — `segmenty`/`wymusz_json` celowo nieużywane
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
