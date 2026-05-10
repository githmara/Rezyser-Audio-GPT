"""
opowiesci_ai.py — Silnik LLM dla trybu „Interaktywne Opowieści" (v15.0 Faza 2).

Funkcja główna :func:`generuj_ture` wysyła snapshot stanu opowieści + akcję
gracza i otrzymuje strukturyzowany JSON (narracja + wybory + postacie +
stan + meta). Strukturę wymusza ``response_format={"type": "json_object"}``
po stronie OpenAI oraz walidacja przez :mod:`jsonschema` po stronie naszej.
Halucynacja struktury → retry max 2× z błędem jako wskazówką dla modelu;
trzeci błąd → ``RuntimeError`` (GUI łapie i pokazuje w dialogu).

Pomocnicza :func:`wygeneruj_wizualizacje` służy slash-komendzie
``/visualize`` (tryb 0/Burza) — multisensoryczny opis sceny do GUI bez
schemy, bez zapisu do plików (lifecycle dochodzi w Fazie 3).

Wzorzec architektoniczny: funkcyjny (jak :mod:`buduj_wielojezyczne_ui`),
nie obj-obj (jak :mod:`rezyser_ai`). Klient OpenAI przekazywany jawnie
przez parametr ``klient``; brak globalnego state.

Faza 2 świadomie nie zapisuje plików — stan trzymany w pamięci panelu
(``OpowiesciPanel._snapshot``). Lifecycle plików (.txt/.md/.game.json/
.story.jsonl/.mode) dochodzi w Fazie 3 (``core_opowiesci.py``).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import jsonschema
from dotenv import load_dotenv

# =============================================================================
# Stałe konfiguracyjne
# =============================================================================

ENV_FILENAME       = "golden_key.env"
MODEL_DOMYSLNY     = "gpt-4o-mini"
MODEL_QUALITY      = "gpt-4o"
TIMEOUT_S          = 120.0
MAX_TOKENS_OUT     = 2000
MAX_RETRIES        = 2          # +1 oryginalna próba = 3 wywołania w pesymistycznym scenariuszu
TEMPERATURE_TURA   = 0.85       # narracja kreatywna
TEMPERATURE_VIS    = 0.95       # wizualizacja jeszcze swobodniejsza

# Numeracja trybów spójna z `.mode` plain-text (jak Reżyser):
TRYB_BURZA         = 0          # /visualize — bez zapisu do plików
TRYB_SWOBODNY      = 3          # free-text input, wybory opcjonalne
TRYB_WYBOROW       = 4          # ZAWSZE 3-5 wyborów A-E
TRYB_MNIEJSZE_ZLO  = 5          # jak 4, ale wszystkie wybory niekorzystne

# =============================================================================
# JSON-schema dla strukturyzowanej tury
# =============================================================================
# Egzekwowane DWUKROTNIE — raz przez OpenAI (response_format=json_object daje
# nam gwarancję że odpowiedź parsuje się jako JSON, NIE że trzyma się tej
# konkretnej schemy), drugi raz przez `jsonschema.validate` po naszej
# stronie. Dwa kroki, bo OpenAI gwarantuje tylko składnię JSON, a my chcemy
# też walidację typów + obecności kluczy + długości tablic.
# -----------------------------------------------------------------------------

SCHEMA_TURA: dict[str, Any] = {
    "type": "object",
    "required": ["narracja", "wybory", "postacie_aktywne", "stan", "meta"],
    "additionalProperties": False,
    "properties": {
        "narracja": {
            "type": "string",
            "minLength": 1,
        },
        "wybory": {
            "type": "array",
            # W trybie 3 (Swobodny) tablica może być pusta. W trybach 4/5
            # GUI sprawdza po walidacji czy len(wybory) ∈ [3, 5] — schema
            # tutaj jest liberalna, bo ten sam JSON obsługuje wszystkie tryby.
            "items": {
                "type": "object",
                "required": ["id", "tekst"],
                "additionalProperties": False,
                "properties": {
                    "id":    {"type": "string", "minLength": 1, "maxLength": 3},
                    "tekst": {"type": "string", "minLength": 1},
                },
            },
        },
        "postacie_aktywne": {
            # Format kompatybilny z parserem Księgi Świata Reżysera
            # (`core_rezyser.py:199` — regex `[Imię: cechy]`). Faza 3
            # zbuduje z tej tablicy plik `skrypty/[gra].md` przez
            # idempotentny rebuild — output Opowieści = wejście Reżysera.
            "type": "array",
            "items": {
                "type": "object",
                "required": ["imie", "cechy"],
                "additionalProperties": False,
                "properties": {
                    "imie":  {"type": "string", "minLength": 1},
                    "cechy": {"type": "string", "minLength": 1},
                },
            },
        },
        "stan": {
            "type": "object",
            "required": ["lokacja"],
            "additionalProperties": True,   # silnik może rozszerzać; Python ignoruje nieznane
            "properties": {
                "lokacja":           {"type": "string"},
                "ekwipunek_zmiany":  {"type": "array", "items": {"type": "string"}},
                "watki_otwarte":     {"type": "array", "items": {"type": "string"}},
            },
        },
        "meta": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "etap_luku":     {"type": "string"},
                "powod_wyborow": {"type": "string"},
            },
        },
    },
}


# =============================================================================
# Snapshot stanu i wynik tury (dataclasses — GIL-safe, niezmienne payloady
# do wątku tła; wzorzec jak :class:`core_rezyser.SnapshotProjektu`)
# =============================================================================

@dataclass
class SnapshotOpowiesci:
    """Niezmienny payload do wątku tła AI.

    Tworzony przez :class:`OpowiesciPanel` przed `_wyslij_worker`. Wątek nigdy
    nie dotyka żywego stanu panelu — tylko tego snapshotu — więc równoczesne
    mutacje GUI nie wpływają na payload zapytania OpenAI, które jest w locie.

    Atrybuty:
        nazwa_gry        : etykieta projektu (do logu, do prompt-context)
        numer_tury       : licznik (Python, nie LLM); 1-indexed
        ostatnie_tury    : skondensowana historia, lista par (akcja, narracja);
                           Faza 3 doda streszczenie po przekroczeniu 70% okna
        postacie_aktywne : lista postaci z poprzedniej tury (kontynuacja)
        stan_poprzedni   : `stan` z poprzedniej tury (lokacja, watki, ekwipunek)
        seed_swiata      : opcjonalny opis świata gracza (przy /nowa); pusty
                           string jeśli świat ma być wylosowany przez LLM
        jezyk_projektu   : kod języka narracji ("pl"/"en"/...); Faza 5 użyje
                           do doboru promptu systemowego z YAML
    """
    nazwa_gry:        str
    numer_tury:       int
    ostatnie_tury:    list[dict[str, str]] = field(default_factory=list)
    postacie_aktywne: list[dict[str, str]] = field(default_factory=list)
    stan_poprzedni:   dict[str, Any]       = field(default_factory=dict)
    seed_swiata:      str                   = ""
    jezyk_projektu:   str                   = "pl"


@dataclass
class WynikTury:
    """Wynik :func:`generuj_ture` — strukturyzowana tura po walidacji."""
    narracja:         str
    wybory:           list[dict[str, str]]
    postacie_aktywne: list[dict[str, str]]
    stan:             dict[str, Any]
    meta:             dict[str, Any]
    surowy_json:      str   # do zapisu w `.story.jsonl` (Faza 3)


# =============================================================================
# Inicjalizacja klienta OpenAI
# =============================================================================

def inicjalizuj_klienta(app_dir: str | None = None) -> Any | None:
    """Ładuje ``golden_key.env`` z roota repo i zwraca skonfigurowanego klienta.

    Zwraca ``None`` jeśli klucz nieobecny lub niewłaściwy (panel pokaże
    wtedy ``brak_api_tresc`` w MessageBox przy próbie wysyłki). Nigdy nie
    rzuca — błąd inicjalizacji nie powinien blokować otwarcia panelu.
    """
    base = app_dir or os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base, ENV_FILENAME)
    if not os.path.exists(env_path):
        return None
    load_dotenv(env_path)
    klucz = os.getenv("OPENAI_API_KEY", "")
    if not klucz or not klucz.startswith("sk-"):
        return None
    try:
        from openai import OpenAI  # noqa: PLC0415  (lazy import — brak openai nie blokuje GUI)
        return OpenAI(api_key=klucz)
    except Exception:
        return None


# =============================================================================
# Prompt systemowy — Faza 2: hardkodowany PL stub.
# Faza 5 przeniesie treść do `dictionaries/<kod>/opowiesci/przepisy/*.yaml`
# i będzie wybierać wariant per `snapshot.jezyk_projektu`.
# =============================================================================

_PROMPT_BAZA = """Jesteś silnikiem narracyjnym interaktywnej opowieści. Piszesz w drugiej osobie liczby pojedynczej („Idziesz", „Czujesz", „Widzisz"). Narracja immersyjna, zmysłowa (nie tylko wzrok — dźwięk, zapach, dotyk), 200-400 słów per tura. Nigdy nie wychodź z postaci narratora.

ZASADY ŚWIATA:
- Konsekwencje wyborów są realne i pamiętane. Postać może zginąć, jeśli gracz podejmie ryzykowną akcję.
- NIE łamiesz czwartej ściany. Nie cytujesz mechaniki gry, nie używasz zwrotów typu „w tym RPG", „w tym scenariuszu".
- Postacie mówią naturalnie — dialogi w cudzysłowie pisanym (np. „— Co tu robisz? — pyta strażnik.").
- Gdy gracz wykonuje akcję bezsensowną z perspektywy postaci, pokazujesz konsekwencję — postać się waha, dziwi, otoczenie reaguje.

FORMAT ODPOWIEDZI (JSON, ZAWSZE — bez wstępu, bez komentarza, surowy JSON):
{
  "narracja": "tekst opowieści w drugiej osobie",
  "wybory": [{"id": "A", "tekst": "..."}, ...],
  "postacie_aktywne": [{"imie": "Imię", "cechy": "krótki opis cech, akcent, charakter"}],
  "stan": {"lokacja": "miejsce", "ekwipunek_zmiany": [...], "watki_otwarte": [...]},
  "meta": {"etap_luku": "ekspozycja|narastanie|kulminacja|rozwiazanie", "powod_wyborow": "uzasadnienie wyborów"}
}

POLE `postacie_aktywne` — lista wszystkich postaci aktualnie obecnych w scenie. Cechy w stylu Księgi Świata: zwięźle, fonetycznie sensownie ("starszy strażnik z chrapliwym głosem, mówi krótkimi zdaniami"). Te postacie zostaną zachowane do następnej tury jako kontekst.

POLE `stan.ekwipunek_zmiany` — co gracz właśnie zdobył lub stracił w tej turze ("+latarnia", "-klucz"); pusta tablica jeśli bez zmian.

POLE `stan.watki_otwarte` — niedokończone wątki które gracz powinien pamiętać.
"""

_PROMPT_TRYB_3 = """TRYB: SWOBODNY. Pole `wybory` może być puste albo zawierać 1-3 sugestie (gracz pisze własną akcję, więc wybory są tylko podpowiedzią — nie obowiązkową ścieżką)."""

_PROMPT_TRYB_4 = """TRYB: WYBORÓW. Pole `wybory` ZAWSZE zawiera 3-5 elementów oznaczonych literami A, B, C, D, E. Każdy wybór to konkretna akcja, którą gracz może podjąć — różne, nie pozorne. Free-text gracza zostanie zmapowany na najbliższy wybór semantycznie."""

_PROMPT_TRYB_5 = """TRYB: MNIEJSZE ZŁO. Pole `wybory` zawiera 3-5 elementów A-E, gdzie KAŻDY wybór jest niekorzystny moralnie, fizycznie albo strategicznie — gracz wybiera mniejsze zło, nie dobro. Brak „neutralnej" opcji. Brak „happy endingu" w danej turze."""

_PROMPT_VISUALIZE = """Jesteś asystentem multisensorycznej wizualizacji sceny dla niewidomego gracza interaktywnej opowieści. Otrzymasz aktualny stan gry oraz pytanie/akcję gracza. Wygeneruj 150-300 słów immersyjnego opisu sceny korzystając ze wszystkich zmysłów: wzrok (kolory, kontrast światła), słuch (cisza, szmery, oddechy), zapach, dotyk powierzchni, temperatura, smak (jeśli pasuje). Format: czysty tekst (nie JSON), w drugiej osobie. To NIE jest tura gry — nie zmieniasz stanu, nie proponujesz wyborów, tylko opisujesz aktualną scenę z większą głębią."""


def _zbuduj_prompt_systemowy(tryb: int) -> str:
    """Składa prompt systemowy z bazy + dopisku trybu."""
    if tryb == TRYB_SWOBODNY:
        return _PROMPT_BAZA + "\n\n" + _PROMPT_TRYB_3
    if tryb == TRYB_WYBOROW:
        return _PROMPT_BAZA + "\n\n" + _PROMPT_TRYB_4
    if tryb == TRYB_MNIEJSZE_ZLO:
        return _PROMPT_BAZA + "\n\n" + _PROMPT_TRYB_5
    raise ValueError(f"Nieznany tryb opowieści: {tryb} (oczekiwane 3/4/5)")


def _zbuduj_user_payload(snapshot: SnapshotOpowiesci, user_input: str) -> str:
    """Konwertuje snapshot + input gracza na JSON payload dla LLM.

    Wstrzykiwany jako `role: user`; baza prompt-systemowy pokazuje strukturę
    wyjściową, a payload tutaj — strukturę wejściową.
    """
    payload = {
        "tura_numer":       snapshot.numer_tury,
        "jezyk_narracji":   snapshot.jezyk_projektu,
        "seed_swiata":      snapshot.seed_swiata,
        "ostatnie_tury":    snapshot.ostatnie_tury,
        "postacie_aktywne": snapshot.postacie_aktywne,
        "stan":             snapshot.stan_poprzedni,
        "akcja_gracza":     user_input,
    }
    return (
        "Stan gry i akcja gracza poniżej. Wygeneruj kolejną turę zgodnie "
        "ze schemą JSON podaną w prompt-systemowy.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


# =============================================================================
# Główna funkcja: generuj_ture (z retry + walidacja jsonschema)
# =============================================================================

def generuj_ture(
    klient:     Any,
    snapshot:   SnapshotOpowiesci,
    user_input: str,
    tryb:       int,
    model:      str = MODEL_DOMYSLNY,
) -> WynikTury:
    """Wysyła turę do LLM i zwraca strukturyzowany wynik.

    Args:
        klient     : skonfigurowany klient OpenAI (z :func:`inicjalizuj_klienta`)
        snapshot   : niezmienny stan gry
        user_input : akcja gracza (dowolny tekst lub mapowany wybór z przycisku)
        tryb       : 3/4/5 (Swobodny/Wyborów/Mniejsze zło)
        model      : ``MODEL_DOMYSLNY`` lub ``MODEL_QUALITY``

    Returns:
        :class:`WynikTury` z zwalidowaną zawartością.

    Raises:
        RuntimeError: po wyczerpaniu prób retry (halucynacja struktury)
                      ALBO przy ucięciu odpowiedzi (max_tokens hit).
        Wyjątki OpenAI (RateLimitError, APITimeoutError, ...) są
        propagowane — GUI łapie i pokazuje w :func:`_wyswietl_blad_ai`.
    """
    prompt_systemowy = _zbuduj_prompt_systemowy(tryb)
    user_payload     = _zbuduj_user_payload(snapshot, user_input)

    ostatni_blad: str | None = None
    for proba in range(MAX_RETRIES + 1):
        # Przy retry dodajemy do payloadu informację o błędzie z poprzedniej
        # próby — model może skorygować strukturę. To wzorzec z OpenAI
        # cookbook „self-correction via error feedback".
        messages = [
            {"role": "system", "content": prompt_systemowy},
            {"role": "user",   "content": user_payload},
        ]
        if ostatni_blad is not None:
            messages.append({
                "role": "system",
                "content": (
                    f"POPRZEDNIA PRÓBA NIE PRZESZŁA WALIDACJI. Błąd: {ostatni_blad}. "
                    f"Wygeneruj ponownie ZGODNIE ze schemą JSON z prompt-systemowy. "
                    f"Wszystkie pola wymagane MUSZĄ być obecne i mieć właściwy typ."
                ),
            })

        resp = klient.chat.completions.create(
            model=model,
            messages=messages,
            temperature=TEMPERATURE_TURA,
            max_tokens=MAX_TOKENS_OUT,
            timeout=TIMEOUT_S,
            response_format={"type": "json_object"},
        )

        finish = getattr(resp.choices[0], "finish_reason", None)
        if finish == "length":
            raise RuntimeError(
                f"Model osiągnął limit max_tokens={MAX_TOKENS_OUT} — odpowiedź "
                f"została ucięta przed zamknięciem JSON. Skróć kontekst lub "
                f"zwiększ MAX_TOKENS_OUT."
            )

        surowa = resp.choices[0].message.content or ""
        try:
            dane = json.loads(surowa)
            jsonschema.validate(instance=dane, schema=SCHEMA_TURA)
        except json.JSONDecodeError as exc:
            ostatni_blad = f"JSONDecodeError: {exc.msg}"
            continue
        except jsonschema.ValidationError as exc:
            ostatni_blad = f"ValidationError: {exc.message} (path: {list(exc.absolute_path)})"
            continue

        # Sukces — żaden błąd schemy.
        return WynikTury(
            narracja=dane["narracja"],
            wybory=dane["wybory"],
            postacie_aktywne=dane["postacie_aktywne"],
            stan=dane["stan"],
            meta=dane["meta"],
            surowy_json=surowa,
        )

    raise RuntimeError(
        f"LLM wygenerował niewłaściwą strukturę JSON {MAX_RETRIES + 1} razy z rzędu. "
        f"Ostatni błąd: {ostatni_blad}"
    )


# =============================================================================
# Pomocnicza funkcja: wygeneruj_wizualizacje (tryb 0/Burza dla /visualize)
# =============================================================================

def wygeneruj_wizualizacje(
    klient:     Any,
    snapshot:   SnapshotOpowiesci,
    user_input: str,
    model:      str = MODEL_DOMYSLNY,
) -> str:
    """Multisensoryczny opis sceny dla slash-komendy ``/visualize``.

    Bez schemy JSON — zwraca surowy tekst do GUI. Bez zapisu do plików
    (tryb 0/Burza). Krótszy timeout (60s), niższy max_tokens (1000) — to
    nie jest tura gry, więc oszczędzamy budżet.
    """
    payload = {
        "stan":             snapshot.stan_poprzedni,
        "postacie_aktywne": snapshot.postacie_aktywne,
        "ostatnia_tura":    snapshot.ostatnie_tury[-1] if snapshot.ostatnie_tury else None,
        "akcja_gracza":     user_input,
    }
    user_msg = (
        "Stan gry poniżej. Wygeneruj multisensoryczny opis sceny.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    resp = klient.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _PROMPT_VISUALIZE},
            {"role": "user",   "content": user_msg},
        ],
        temperature=TEMPERATURE_VIS,
        max_tokens=1000,
        timeout=60.0,
    )
    return resp.choices[0].message.content or ""
