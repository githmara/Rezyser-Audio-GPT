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

import hashlib
import json
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


# ---------------------------------------------------------------------------
# Konfiguracja czytana z golden_key.env (po load_dotenv przez wołającego)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KonfiguracjaLLM:
    """Migawka konfiguracji LLM z ``golden_key.env``.

    Pola ``base_url``/``model`` mają znaczenie wyłącznie dla ``openai_compat``.
    W trybie ``anthropic`` model bierze się z YAML przepisu (``claude-sonnet-5``).
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
    nadpisuje nazwę modelu z przepisu YAML (na cudzym endpoincie ``claude-sonnet-5``
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
# Do v18.22 degradacja `temperature` była REAKTYWNA: wysyłamy z przepisu →
# 400 → ponawiamy bez. Na dziś domyślny model runtime'u (`claude-sonnet-5`)
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


def _dopisz_do_cache_samplingu(mdl: str) -> None:
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


def _honoruje_temperature(mdl: str, temperatura: float) -> bool:
    """Czy wysyłać ``temperature`` do tego modelu.

    ``temperatura`` równa domyślnej jest no-opem i przechodzi wszędzie, więc nie
    ma po co jej wycinać (ani uczyć się o niej czegokolwiek).
    """
    if temperatura == _TEMPERATURA_DOMYSLNA:
        return True
    if mdl in _NAUCZONE_BEZ_TEMPERATURY:
        return False
    return not any(mdl.startswith(prefiks) for prefiks in _MODELE_BEZ_TEMPERATURY)


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
    """
    tresc = str(exc).lower()
    if "temperature" in tresc:
        return "temperature"
    if "output_config" in tresc or "json_schema" in tresc:
        return "output_config"
    if "thinking" in tresc or "budget_tokens" in tresc:
        return "thinking"
    return None


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
      * ``powod`` wpada wprost do diagnostyki (model wypełnia go bez proszenia).

    ``description`` pól NIE jest tłumaczone — to jedyny opis, jaki model widzi
    poza promptem, więc trzyma też kardynalność zdjętą ze schematu API.
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
            "description": "Normalna odpowiedź — wypełnij WSZYSTKIE pola tury.",
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
                    "Odmowa wykonania polecenia — patrz SYSTEM RULE na końcu "
                    "promptu systemowego."
                ),
            },
            "odrzucenie": {
                "type": "string",
                "description": f"Wartość dosłownie: {tag_odrzucenia}",
            },
            "powod": {
                "enum": list(_POWODY_ODRZUCENIA),
                "description": "Kategoria odmowy (diagnostyka aplikacji).",
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


# ---------------------------------------------------------------------------
# Wskazówki self-correction (v18.23) — NIE cytujemy komunikatu parsera
# ---------------------------------------------------------------------------
# Zgłoszenie z 2026-08-29 pokazało, dlaczego to ma znaczenie. Model wstawił
# przecinek wiszący; `json.loads` zwrócił „Expecting property name enclosed in
# double quotes"; kod odesłał tę treść modelowi jako wskazówkę — a ona wskazuje
# na CUDZYSŁOWY, które były bezbłędne. Model trzy razy „naprawiał" nie tę winę
# i trzy razy powtórzył przecinek. Komunikat parsera opisuje POZYCJĘ w tekście,
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

    Po szczeblach KSZTAŁTU idą jeszcze szczeble PARAMETRÓW (v18.9): bez
    ``temperature`` i z ``max_completion_tokens`` zamiast ``max_tokens``.
    Gałąź Anthropic miała degradację ``temperature`` od v18.7, compat nie —
    wszystkie jej szczeble wysyłały te same parametry, więc modele wymagające
    domyślnego samplingu (rodziny o-*, gpt-5) padały na KAŻDYM z nich surowym,
    angielskim wyjątkiem, wbrew obietnicy „dowolny endpoint zgodny z OpenAI"
    z v18.4.
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

    # Szczeble KSZTAŁTU: od najpełniejszego do „flat bez formatu" (= v18.3).
    # Płaski user-only zamyka tę grupę — gwarantuje powrót do dotychczasowego
    # zachowania. Krotka: (wiadomości, response_format, opis, bez_temperatury,
    # klucz limitu tokenów).
    proby: list[tuple[list[dict], dict | None, str, bool, str]] = []
    if rf is not None:
        proby.append(
            (glowny, rf, "json" + ("+role" if bogate is not None else ""),
             False, "max_tokens"))
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

    ostatni = len(proby) - 1
    for i, (msgs, fmt, opis, bez_temp, klucz_tok) in enumerate(proby):
        try:
            return _openai_chat(
                klient, mdl, msgs, max_tokens, temperature, timeout, fmt,
                bez_temperatury=bez_temp, klucz_tokenow=klucz_tok,
            )
        except Exception as exc:  # noqa: BLE001 — degradujemy TYLKO błąd struktury
            if i == ostatni or not _czy_zla_struktura(exc):
                raise  # wyczerpana drabina ALBO 429/timeout/sieć → wyżej
            _dev_log(
                f"openai_compat: endpoint odrzucił payload '{opis}' "
                f"({type(exc).__name__}) — degraduję do prostszego."
            )
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

    ``thinking_budget`` > 0 (18.11, tryb quality tłumacza AI) włącza extended
    thinking: model dostaje budżet tokenów na wewnętrzne rozumowanie PRZED
    odpowiedzią. Wymogi API: ``temperature`` musi zostać domyślna (parametr
    POMIJAMY) i ``max_tokens`` > ``budget_tokens`` — budżet dokładamy PONAD
    limit odpowiedzi wołającego, żeby semantyka ``stop_reason=="max_tokens"``
    (guard uciętej odpowiedzi / bisekcja tłumacza) nie drgnęła. Bloki
    ``thinking`` w odpowiedzi odfiltrowuje istniejąca sklejka ``type=="text"``.
    Odrzucenie konfiguracji thinking przez model/endpoint (400/422) → retry
    bez thinking i bez ``temperature`` (najbezpieczniejszy wariant — default
    sampling akceptują wszystkie modele Claude).

    ``schema_json`` (v18.23) → ``output_config.format`` (structured outputs):
    kształt odpowiedzi egzekwuje API. Schemat musi być już przepuszczony przez
    :func:`schemat_do_api`. Zdejmujemy go WYŁĄCZNIE wtedy, gdy 400 dotyczy jego
    samego (patrz :func:`_co_odrzucono`) — po zdjęciu wracamy do zachowania
    ≤v18.22, czyli wymuszania JSON promptem + retry u wołającego.

    **Degradacja jest CELOWANA, nie kolejnościowa.** Wcześniejszy wariant „zdejmij
    następny element listy" wyglądał bezpiecznie, ale przy modelu nieprzyjmującym
    ``temperature`` (dziś: domyślny `claude-sonnet-5`) zdejmowałby najpierw
    ``output_config`` — czyli structured outputs nie zadziałałyby ANI RAZU
    w produkcji, a wyjście wracałoby do stanu, który wywołał zgłoszenie
    z 2026-08-29. Dodatkowo ``temperature`` nie jest już wysyłana do modeli
    z :data:`_MODELE_BEZ_TEMPERATURY` ani z trwałego autocache'u, więc typowe
    wywołanie nie płaci nawet jednym jałowym round-tripem.

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
        thinking={"type": "disabled"},
    )
    # `temperature` wysyłamy TYLKO tam, gdzie ma szansę zadziałać (baseline +
    # autocache). Dla `claude-sonnet-5` i pokrewnych pomijamy ją od razu, więc
    # nie płacimy jałowym round-tripem przy każdej generacji.
    if _honoruje_temperature(mdl, temperature):
        kwargs["temperature"] = temperature
    else:
        _dev_log(
            f"anthropic: model '{mdl}' nie honoruje niedomyślnej 'temperature' "
            f"({temperature}) — pomijam parametr bez próby (baseline/cache)."
        )
    if thinking_budget > 0:
        kwargs.pop("temperature", None)
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
        kwargs["max_tokens"] = max_tokens + thinking_budget
    if schema_json is not None:
        kwargs["output_config"] = {
            "format": {"type": "json_schema", "schema": schema_json},
        }

    # Degradacja CELOWANA: zdejmujemy to, co API wskazało w komunikacie 400
    # (patrz `_co_odrzucono`), a nie kolejny element listy. Ślepa kolejność
    # kosztowałaby structured outputs przy KAŻDYM modelu nieprzyjmującym
    # `temperature`. Nierozpoznany komunikat → jedna próba awaryjna, w której
    # zdejmujemy wszystko naraz (najbezpieczniejszy payload: default sampling,
    # bez thinking, bez schematu = zachowanie ≤v18.22).
    resp = None
    zdjete: set[str] = set()
    for _krok in range(4):
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
                kwargs.pop("temperature", None)
                _dopisz_do_cache_samplingu(mdl)
            elif winowajca == "output_config":
                _dev_log(
                    f"anthropic: model/endpoint '{mdl}' odrzucił 'output_config' "
                    f"({type(exc).__name__}) — ponawiam bez structured outputs "
                    "(JSON wymuszany samym promptem, jak ≤v18.22)."
                )
                kwargs.pop("output_config", None)
            elif winowajca == "thinking":
                _dev_log(
                    f"anthropic: model '{mdl}' odrzucił 'thinking' "
                    f"({type(exc).__name__}) — ponawiam bez trybu quality."
                )
                kwargs["thinking"] = {"type": "disabled"}
                kwargs["max_tokens"] = max_tokens
            else:
                _dev_log(
                    f"anthropic: model '{mdl}' odrzucił payload komunikatem, "
                    f"którego nie rozpoznaję ({type(exc).__name__}: "
                    f"{str(exc)[:120]}) — ponawiam z najprostszym payloadem."
                )
                kwargs.pop("temperature", None)
                kwargs.pop("output_config", None)
                kwargs["thinking"] = {"type": "disabled"}
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
            "schemat":    _odcisk_schematu(kwargs.get("output_config")),
            "wejscie_tok":  getattr(uzycie, "input_tokens", None),
            "wyjscie_tok":  getattr(uzycie, "output_tokens", None),
        })
    return tekst, stop


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
      * **reasoning** — Anthropic ``thinking``: domyślnie disabled (proza, bez
        narzutu); ``thinking_budget`` > 0 włącza extended thinking (18.11,
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

    ``schema_json`` (v18.23, TYLKO Anthropic) — schemat structured outputs
    (``output_config.format``), już okrojony przez :func:`schemat_do_api`. To on
    zastąpił dawne „Anthropic IGNORUJE ``wymusz_json`` — wymusza JSON promptem":
    kształt egzekwuje teraz API. ``openai_compat`` go IGNORUJE i zostaje przy
    ``response_format`` + tolerancyjnym parsowaniu (:func:`napraw_luzny_json`)
    u wołającego — ten sam wzorzec cichej degradacji, co ``segmenty``.

    ``slad`` (v18.23, TYLKO Anthropic) — lista, do której dopisujemy metrykę
    każdego wywołania (próba, ``request_id``, ``stop_reason``, tokeny). Wyłącznie
    dane NIE-treściowe: log trafia do publicznego zgłoszenia, a payload zawiera
    nieopublikowaną prozę użytkownika.

    W trybie ``openai_compat`` nazwę modelu nadpisuje ``klient.model_override``
    (``LLM_MODEL``) — argument ``model`` (z przepisu YAML) jest wtedy ignorowany.

    ``temperature`` w gałęzi Anthropic ma degradację (patrz :func:`_wywolaj_anthropic`):
    modele, które odrzucają niedomyślną wartość (Claude Sonnet 5 i nowsze), dostają
    retry bez tego parametru zamiast wywalać wyjątek — patrz [[reguly_architektury]].

    Rate-limit (429) → :class:`BladLimituLLM`, timeout → :class:`BladTimeoutLLM`,
    przepełnione okno kontekstowe (400 z frazą / 413) → :class:`BladKontekstuLLM`
    (wszystkie dla dowolnego providera). Pozostałe wyjątki SDK propagują natywnie
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

        # Anthropic (domyślny filar jakości) — `segmenty`/`wymusz_json` celowo
        # nieużywane; kształt JSON wymusza `schema_json` (structured outputs).
        return _wywolaj_anthropic(
            klient, mdl, system, messages, max_tokens, temperature, timeout,
            thinking_budget=thinking_budget,
            schema_json=schema_json,
            slad=slad,
        )

    except Exception as exc:  # noqa: BLE001 — 429/timeout/kontekst opakowujemy; reszta leci dalej
        if _czy_rate_limit(exc):
            raise BladLimituLLM(str(exc)) from exc
        if _czy_timeout(exc):
            raise BladTimeoutLLM(str(exc)) from exc
        if _czy_przepelniony_kontekst(exc):
            raise BladKontekstuLLM(str(exc)) from exc
        raise
