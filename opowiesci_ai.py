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

import functools
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml as _pyyaml
from dotenv import load_dotenv

import core_tokeny as ct

# =============================================================================
# Stałe konfiguracyjne
# =============================================================================

ENV_FILENAME       = "golden_key.env"
MODEL_DOMYSLNY     = ct.MODEL_DOMYSLNY_OPOWIESCI
MODEL_QUALITY      = ct.MODEL_DOMYSLNY_REZYSER
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

# Pamięć modelu — okno kontekstowe + progi + nazwy poziomów importowane
# z `core_tokeny` (wspólne dla Opowieści i Reżysera od v15.1).
OKNO_KONTEKSTU_MAX = ct.OKNO_KONTEKSTU_MAX
PROG_OSTRZEZENIE   = ct.PROG_OSTRZEZENIE
PROG_ALARM         = ct.PROG_ALARM
TURY_DO_CINEMATIC  = 150    # licznik tur (niezależny od tokenów)

POZIOM_CZYSTA      = ct.POZIOM_CZYSTA
POZIOM_OK          = ct.POZIOM_OK
POZIOM_OSTRZEZENIE = ct.POZIOM_OSTRZEZENIE
POZIOM_ALARM       = ct.POZIOM_ALARM

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
                # v15.2: mechanika fiolki w trybie Mniejsze zło. LLM zwraca
                # blok TYLKO gdy fiolka jest aktywna albo właśnie ją dodaje
                # (po N turach hardship — `prog_aktywacji_tur` w yaml). Pola
                # nieobecne → fiolka nigdy się nie pojawiła. `zniszczona=True`
                # jest definitywne (LLM decyduje w narracji), po czym `obecna`
                # zostaje True ale wybór 0 znika i nie wraca.
                "fiolka": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "obecna":     {"type": "boolean"},
                        "uzyto_razy": {"type": "integer", "minimum": 0},
                        "zniszczona": {"type": "boolean"},
                    },
                },
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
        zasady_swiata    : opcjonalny tekst z regułami świata zdefiniowanymi
                           przez gracza (v15.1+). Pusty string = stary tryb;
                           niepusty → wstrzykiwany przez
                           :func:`_zbuduj_prompt_systemowy` jako dodatkowa
                           sekcja między bazą a addonem trybu.
    """
    nazwa_gry:        str
    numer_tury:       int
    ostatnie_tury:    list[dict[str, str]] = field(default_factory=list)
    postacie_aktywne: list[dict[str, str]] = field(default_factory=list)
    stan_poprzedni:   dict[str, Any]       = field(default_factory=dict)
    seed_swiata:      str                   = ""
    jezyk_projektu:   str                   = "pl"
    zasady_swiata:    str                   = ""


@dataclass
class WynikTury:
    """Wynik :func:`generuj_ture` — strukturyzowana tura po walidacji."""
    narracja:         str
    wybory:           list[dict[str, str]]
    postacie_aktywne: list[dict[str, str]]
    stan:             dict[str, Any]
    meta:             dict[str, Any]
    surowy_json:      str   # do zapisu w `.story.jsonl` (Faza 3)


@dataclass
class StatusPamieci:
    """Status wskaźnika pamięci modelu — gotowe dane dla GUI.

    Pole ``poziom`` jest jednym z ``POZIOM_*`` — GUI dobiera kolor
    (zielony/pomarańczowy/czerwony) i decyduje czy auto-streszczenie
    odpalić w tle.
    """
    procent:        int          # 0–100, do `wx.Gauge.SetValue()`
    tokeny:         int          # surowa liczba tokenów wejściowych
    komunikat:      str          # pełny tekst (z emoji) do `_lbl_pamiec_status`
    poziom:         str          # POZIOM_CZYSTA/OK/OSTRZEZENIE/ALARM


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
# Ładowanie przepisów (prompty + parametry OpenAI) z YAML
# =============================================================================
# Anty-spaghetti: prompty systemowe trzymane w `dictionaries/<kod>/opowiesci/`,
# nie hardkodowane w Pythonie (patrz `feedback_yaml_prompty.md`). Wzorzec
# kopiuje strukturę `dictionaries/<kod>/rezyser/`. Faza 5 zmigrowała PL;
# pozostałe języki dochodzą RĘCZNIE per język (nie ma batch translatora dla
# promptów — LLM halucynuje na nich).
#
# Fallback do EN (15.3 zmiana z PL → EN): jeśli `<jezyk>/opowiesci/<plik>.yaml`
# nie istnieje (gracz wybrał język, dla którego paczka jeszcze niedopisana),
# używamy EN żeby aplikacja nie crashowała w trakcie tury — międzynarodowy
# fallback jest mniej ostentacyjny niż polski dla user-a niemówiącego po polsku
# i naturalniejszy dla modelu OpenAI. Crosscheck `_jezyk_kompletny` w
# `core_poliglota` gwarantuje że pl/en (bazy referencyjne) mają identyczny
# zestaw plików, więc EN nigdy nie jest stubem w którym fallback by ciszą
# zawiódł mid-game.

ROOT_DICT = Path(__file__).resolve().parent / "dictionaries"

_NAZWA_PLIKU_PER_TRYB = {
    TRYB_BURZA:        "tryb_burza",
    TRYB_SWOBODNY:     "tryb_swobodny",
    TRYB_WYBOROW:      "tryb_wyborow",
    TRYB_MNIEJSZE_ZLO: "tryb_mniejsze_zlo",
}


@functools.lru_cache(maxsize=128)
def _zaladuj_przepis(jezyk: str, nazwa: str) -> dict[str, Any]:
    """Ładuje plik `dictionaries/<jezyk>/opowiesci/<nazwa>.yaml` z fallbackiem do EN.

    LRU cache — w typowej grze odpalamy tę funkcję 1-2 razy per tura,
    ale uniknięcie I/O (każdy plik ~1-3 KB) jest tanim optymalizem.
    Cache invalidacja: programatycznie przez `_zaladuj_przepis.cache_clear()`
    (np. po zmianie języka w GUI), albo restart aplikacji.

    15.3 zmiana: fallback z PL na EN. Powód w bloku komentarza powyżej.
    Aktywacja fallbacku emituje WARN na stderr — pomaga maintainerom
    lokalizować nieuzupełnione paczki językowe (cisza znaczy że stuba
    nikt nie zauważy, dopóki gracz nie zgłosi obcojęzycznych odpowiedzi
    AI w grze, którą myślał że gra w swoim języku).
    """
    sciezka = ROOT_DICT / jezyk / "opowiesci" / f"{nazwa}.yaml"
    if not sciezka.exists() and jezyk != "en":
        sys.stderr.write(
            f"[opowiesci_ai] WARN: brak `{jezyk}/opowiesci/{nazwa}.yaml` — "
            f"fallback do `en/opowiesci/{nazwa}.yaml`. "
            f"Czy paczka `{jezyk}` jest kompletna?\n"
        )
        sciezka = ROOT_DICT / "en" / "opowiesci" / f"{nazwa}.yaml"
    if not sciezka.exists():
        raise FileNotFoundError(
            f"Brak przepisu opowieści `{nazwa}.yaml` ani w `{jezyk}/opowiesci/` "
            f"ani w `en/opowiesci/` (fallback). Czy folder dictionaries jest kompletny?"
        )
    with open(sciezka, "r", encoding="utf-8") as fh:
        return _pyyaml.safe_load(fh) or {}


def _zbuduj_prompt_systemowy(tryb: int, jezyk: str = "pl", zasady_swiata: str = "") -> str:
    """Składa prompt systemowy z bazy YAML + addonu trybu YAML.

    Tryby narracyjne (3/4/5) używają `baza.yaml` + `tryb_<nazwa>.yaml`.
    Tryb Burza (0) używa wyłącznie `tryb_burza.yaml` (visualize ma własny
    pełny prompt, bez bazy narracyjnej z JSON-schemą).

    Args:
        zasady_swiata: opcjonalny tekst gracza z regułami świata (v15.1+).
            Niepusty → wstrzykiwany jako sekcja BEZWZGLĘDNIE wiążąca między
            bazą a addonem trybu (tryby 3/4/5) lub na końcu (tryb 0/Burza).
            Pusty / sam whitespace → brak wstrzyknięcia, kompatybilność wsteczna.
    """
    nazwa = _NAZWA_PLIKU_PER_TRYB.get(tryb)
    if nazwa is None:
        raise ValueError(f"Nieznany tryb opowieści: {tryb} (oczekiwane 0/3/4/5)")

    zasady_blok = ""
    if zasady_swiata and zasady_swiata.strip():
        zasady_blok = (
            "\n\n## Zasady świata (zdefiniowane przez gracza)\n\n"
            f"{zasady_swiata.strip()}\n\n"
            "Te zasady są BEZWZGLĘDNIE wiążące przez całą grę. Respektuj je "
            "w narracji, dialogach, opisach postaci, wyborach i wizualizacjach."
        )

    if tryb == TRYB_BURZA:
        # Visualize stoi na własnych nogach — bez bazy narracyjnej.
        return _zaladuj_przepis(jezyk, "tryb_burza")["prompt_systemowy"] + zasady_blok

    baza   = _zaladuj_przepis(jezyk, "baza")["prompt_systemowy"]
    addon  = _zaladuj_przepis(jezyk, nazwa)["prompt_systemowy"]
    return baza + zasady_blok + "\n\n" + addon


def _parametr_z_yaml(jezyk: str, nazwa: str, klucz: str, default: Any) -> Any:
    """Czyta wartość parametru z `<jezyk>/opowiesci/<nazwa>.yaml::<klucz>` z fallbackiem.

    Używane do `model`, `temperatura`, `max_tokens`, `timeout_s` — pozwala
    lingwiście / autorowi przepisu strojenie LLM bez modyfikacji Pythona.
    """
    przepis = _zaladuj_przepis(jezyk, nazwa)
    return przepis.get(klucz, default)


def _zbuduj_user_payload(
    snapshot:         SnapshotOpowiesci,
    user_input:       str,
    fiolka_aktywacja: bool = False,
    fiolka_seed:      dict[str, str] | None = None,
) -> str:
    """Konwertuje snapshot + input gracza na JSON payload dla LLM.

    Wstrzykiwany jako `role: user`; baza prompt-systemowy pokazuje strukturę
    wyjściową, a payload tutaj — strukturę wejściową.

    Args:
        fiolka_aktywacja: True jeśli w tej turze fiolka MA się pojawić po raz
            pierwszy (próg ``prog_aktywacji_tur`` osiągnięty w trybie
            Mniejsze zło). LLM dostaje sygnał, że musi wprowadzić fiolkę
            diegetycznie do ekwipunku (znajdzona, podarowana, dostrzeżona).
        fiolka_seed: jeśli gracz wybrał ``id="0"`` (Odkorkuj fiolkę), Python
            losuje przed wysyłką kategorię i konkretny opis skutku z puli
            ``fiolka.opisy_skutkow.<kategoria>`` w yaml — LLM dostaje gotowy
            seed do znarracjonalizowania, NIE wymyśla skutku samodzielnie
            (anti-halucynacja, kontrola rozkładu prawdopodobieństw).
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

    # Fiolka — bloki tylko gdy istotne. LLM ignoruje brakujące klucze; obecne
    # interpretuje zgodnie z instrukcjami w `tryb_mniejsze_zlo.yaml::prompt_systemowy`.
    if fiolka_aktywacja:
        payload["fiolka_aktywacja_w_tej_turze"] = True
    if fiolka_seed is not None:
        payload["fiolka_efekt_seed"] = fiolka_seed

    return (
        "Stan gry i akcja gracza poniżej. Wygeneruj kolejną turę zgodnie "
        "ze schemą JSON podaną w prompt-systemowy.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


# =============================================================================
# Mechanika fiolki (v15.2 — tryb Mniejsze zło)
# =============================================================================
# Vial z `notatki_dev/tales_mechanics.md §4`: pojawia się po kilku turach
# hardship, listed jako stała pozycja `0) Odkorkuj fiolkę`. Reusable (nie
# znika po użyciu) ale nieprzewidywalna — może zaszkodzić, zniekształcić,
# rzadko pomóc, nigdy nie gwarantuje wybawienia. LLM decyduje w narracji
# o zniszczeniu (`fiolka.zniszczona=True`), po czym wybór 0 znika.
#
# Architektura: PYTHON losuje kategorię skutku (z wagami z yaml) i konkretny
# opis (z puli per-kategoria w yaml). LLM tylko narracjonalizuje gotowy seed.
# Wzorzec: deterministyczna kontrola rozkładu (Python) + diegetyczna swoboda
# w opisie (LLM) — odporne na halucynacje typu „deus ex machina".


def czy_fiolka_powinna_sie_pojawic(
    snapshot:            SnapshotOpowiesci,
    prog_aktywacji_tur:  int,
) -> bool:
    """True jeśli należy aktywować fiolkę w nadchodzącej turze.

    Warunki łączne:
    - numer tury >= próg aktywacji,
    - fiolka NIE jest jeszcze obecna w stanie,
    - fiolka NIE była zniszczona w narracji (definitywne — po zniszczeniu
      nie wraca).

    Wywołujący (GUI) sprawdza tę flagę przed budowaniem snapshotu i ustawia
    ``fiolka_aktywacja=True`` w wywołaniu :func:`generuj_ture`, żeby LLM
    wiedział że musi w tej turze wprowadzić fiolkę do ekwipunku.
    """
    fiolka = (snapshot.stan_poprzedni or {}).get("fiolka") or {}
    if fiolka.get("obecna"):
        return False
    if fiolka.get("zniszczona"):
        return False
    return snapshot.numer_tury >= prog_aktywacji_tur


def wylosuj_seed_fiolki(jezyk: str = "pl") -> dict[str, str]:
    """Losuje kategorię i konkretny opis skutku fiolki z puli yaml.

    Czyta `dictionaries/<jezyk>/opowiesci/tryb_mniejsze_zlo.yaml::fiolka`:
    - ``wagi_skutkow`` — rozkład prawdopodobieństwa (default 0.6/0.3/0.1
      dla harmful/distortion/rare_beneficial; „never guaranteed salvation").
    - ``opisy_skutkow.<kategoria>`` — lista 3-5 opisów per kategoria;
      `random.choice` losuje jeden, ten trafia do LLM jako seed.

    Returns:
        ``{"kategoria": "harmful"|"distortion"|"rare_beneficial",
            "opis": "konkretny opis skutku do narracjonalizacji"}``.
        Przy braku puli (yaml bez sekcji ``fiolka``) — pusty opis;
        LLM dostanie samą kategorię i sam ją zinterpretuje (graceful
        degradation, nie crash).
    """
    import random  # noqa: PLC0415  (lazy — losowanie używane tylko w trybie 5)

    przepis = _zaladuj_przepis(jezyk, "tryb_mniejsze_zlo")
    fiolka_cfg = przepis.get("fiolka", {}) or {}

    wagi_default = {"harmful": 0.6, "distortion": 0.3, "rare_beneficial": 0.1}
    wagi = fiolka_cfg.get("wagi_skutkow", wagi_default) or wagi_default
    kategorie = list(wagi.keys())
    wagi_lista = [float(wagi[k]) for k in kategorie]
    kategoria = random.choices(kategorie, weights=wagi_lista, k=1)[0]

    pula = (fiolka_cfg.get("opisy_skutkow") or {}).get(kategoria) or []
    opis = random.choice(pula) if pula else ""
    return {"kategoria": kategoria, "opis": opis}


def prog_aktywacji_fiolki(jezyk: str = "pl") -> int:
    """Czyta `fiolka.prog_aktywacji_tur` z yaml (default 4)."""
    przepis = _zaladuj_przepis(jezyk, "tryb_mniejsze_zlo")
    return int((przepis.get("fiolka") or {}).get("prog_aktywacji_tur", 4))


def etykieta_wyboru_fiolki(jezyk: str = "pl") -> str:
    """Lokalizowana etykieta przycisku id=0 — z yaml, default „Odkorkuj fiolkę"."""
    przepis = _zaladuj_przepis(jezyk, "tryb_mniejsze_zlo")
    return str((przepis.get("fiolka") or {}).get("etykieta_wyboru", "Odkorkuj fiolkę"))


# =============================================================================
# Główna funkcja: generuj_ture (z retry + walidacja jsonschema)
# =============================================================================

def generuj_ture(
    klient:           Any,
    snapshot:         SnapshotOpowiesci,
    user_input:       str,
    tryb:             int,
    model:            str | None = None,
    fiolka_aktywacja: bool = False,
    fiolka_seed:      dict[str, str] | None = None,
) -> WynikTury:
    """Wysyła turę do LLM i zwraca strukturyzowany wynik.

    Args:
        klient           : skonfigurowany klient OpenAI (z :func:`inicjalizuj_klienta`)
        snapshot         : niezmienny stan gry; ``snapshot.jezyk_projektu`` decyduje
                           z którego `dictionaries/<kod>/opowiesci/*.yaml` ładować prompt
        user_input       : akcja gracza (dowolny tekst lub mapowany wybór z przycisku)
        tryb             : 3/4/5 (Swobodny/Wyborów/Mniejsze zło)
        model            : nadpisuje YAML jeśli podany (np. po zmianie w `/ustawienia`);
                           ``None`` → bierzemy z `<jezyk>/opowiesci/baza.yaml::model`
        fiolka_aktywacja : tryb=5, fiolka jeszcze nie obecna, próg osiągnięty —
                           GUI wstawia ``True`` (patrz :func:`czy_fiolka_powinna_sie_pojawic`)
                           i LLM musi w tej turze wprowadzić fiolkę do ekwipunku
                           diegetycznie + ustawić ``stan.fiolka.obecna=True``.
        fiolka_seed      : gracz wybrał ``id="0"`` (Odkorkuj fiolkę). Python wylosował
                           ``{"kategoria","opis"}`` (patrz :func:`wylosuj_seed_fiolki`)
                           i wstrzykuje jako seed do narracjonalizacji. LLM ma się
                           trzymać KATEGORII i OPISU; nie wymyślać nowego skutku.

    Returns:
        :class:`WynikTury` z zwalidowaną zawartością.

    Raises:
        RuntimeError: po wyczerpaniu prób retry (halucynacja struktury)
                      ALBO przy ucięciu odpowiedzi (max_tokens hit).
        Wyjątki OpenAI (RateLimitError, APITimeoutError, ...) są
        propagowane — GUI łapie i pokazuje w :func:`_wyswietl_blad_ai`.
    """
    jezyk            = snapshot.jezyk_projektu or "pl"
    prompt_systemowy = _zbuduj_prompt_systemowy(tryb, jezyk, snapshot.zasady_swiata)
    user_payload     = _zbuduj_user_payload(
        snapshot,
        user_input,
        fiolka_aktywacja=fiolka_aktywacja,
        fiolka_seed=fiolka_seed,
    )

    # Parametry: priorytet to argument funkcji (GUI może override przez
    # `/ustawienia`), potem YAML trybu, na końcu hardkodowana stała.
    nazwa_pliku = _NAZWA_PLIKU_PER_TRYB[tryb]
    efektywny_model = model or _parametr_z_yaml(jezyk, nazwa_pliku, "model", MODEL_DOMYSLNY)
    temperatura     = _parametr_z_yaml(jezyk, nazwa_pliku, "temperatura", TEMPERATURE_TURA)

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
            model=efektywny_model,
            messages=messages,
            temperature=temperatura,
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
    model:      str | None = None,
) -> str:
    """Multisensoryczny opis sceny dla slash-komendy ``/visualize``.

    Bez schemy JSON — zwraca surowy tekst do GUI. Bez zapisu do plików
    (tryb 0/Burza). Parametry (model/temperatura/max_tokens/timeout)
    z `dictionaries/<jezyk>/opowiesci/tryb_burza.yaml`.
    """
    jezyk = snapshot.jezyk_projektu or "pl"
    przepis = _zaladuj_przepis(jezyk, "tryb_burza")
    efektywny_model = model or przepis.get("model", MODEL_DOMYSLNY)
    # v15.1+: zasady świata gracza trafiają też do prompt-systemowy
    # wizualizacji (fonetyczna tożsamość musi być respektowana także w
    # multisensorycznych opisach).
    prompt_systemowy = _zbuduj_prompt_systemowy(TRYB_BURZA, jezyk, snapshot.zasady_swiata)

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
        model=efektywny_model,
        messages=[
            {"role": "system", "content": prompt_systemowy},
            {"role": "user",   "content": user_msg},
        ],
        temperature=przepis.get("temperatura", TEMPERATURE_VIS),
        max_tokens=przepis.get("max_tokens", 1000),
        timeout=przepis.get("timeout_s", 60.0),
    )
    return resp.choices[0].message.content or ""


# =============================================================================
# FAZA 4 — Pamięć modelu (tiktoken) + auto-streszczenie + Cinematic Warning
# =============================================================================

def policz_tokeny(snapshot: SnapshotOpowiesci, tryb: int, model: str = MODEL_DOMYSLNY) -> int:
    """Liczy tokeny tego, co poszłoby w kolejnym wywołaniu :func:`generuj_ture`.

    Tylko **input** — output (max_tokens=2000) liczy się osobno po stronie
    OpenAI. Wartość użyteczna dla :func:`oblicz_status_pamieci` żeby
    pokazać user-owi % zapełnienia okna kontekstowego.

    Liczenie deleguje do :func:`core_tokeny.policz_tokeny_chat`, które
    sumuje tokeny ``content`` + narzut formatu chat (~4 tokeny per wiadomość
    + 2 tokeny na sygnaturę odpowiedzi).
    """
    jezyk   = snapshot.jezyk_projektu or "pl"
    # `_zbuduj_prompt_systemowy` obsługuje WSZYSTKIE tryby (0/3/4/5), więc
    # nie ma już potrzeby branch-owania na TRYB_BURZA.
    prompt_systemowy = _zbuduj_prompt_systemowy(tryb, jezyk, snapshot.zasady_swiata)
    user_payload     = _zbuduj_user_payload(snapshot, "")  # akcja gracza nieznana — szacunek przed wpisaniem
    return ct.policz_tokeny_chat([prompt_systemowy, user_payload], model)


def oblicz_status_pamieci(
    snapshot: SnapshotOpowiesci,
    tryb:     int,
    model:    str = MODEL_DOMYSLNY,
) -> StatusPamieci:
    """Zwraca status pamięci modelu dla wskaźnika GUI.

    Logika analogiczna do :meth:`core_rezyser.ProjektRezysera.status_pamieci_modelu`,
    ale liczy tokeny zamiast znaków (gpt-4o ma 128k token window — wartość
    znakowa byłaby gruba i nieprecyzyjna).
    """
    if snapshot.numer_tury == 0 and not snapshot.ostatnie_tury:
        return StatusPamieci(
            procent=0,
            tokeny=0,
            komunikat="🟢 Pamięć czysta. Maszyna gotowa na nową historię.",
            poziom=POZIOM_CZYSTA,
        )

    tokeny = policz_tokeny(snapshot, tryb, model)
    procent = min(int(tokeny / OKNO_KONTEKSTU_MAX * 100), 100)
    udzial  = tokeny / OKNO_KONTEKSTU_MAX

    if udzial >= PROG_ALARM:
        return StatusPamieci(
            procent=procent,
            tokeny=tokeny,
            komunikat=(
                f"🚨 KRYTYCZNE PRZEŁADOWANIE: {tokeny} z {OKNO_KONTEKSTU_MAX} tokenów. "
                "Auto-streszczenie nie zwolniło bufora — wpisz /streszczenie ręcznie albo "
                "zakończ grę i wczytaj nową."
            ),
            poziom=POZIOM_ALARM,
        )

    if udzial >= PROG_OSTRZEZENIE:
        return StatusPamieci(
            procent=procent,
            tokeny=tokeny,
            komunikat=(
                f"⚠️ STAN OSTRZEGAWCZY: {tokeny} z {OKNO_KONTEKSTU_MAX} tokenów. "
                "Auto-streszczenie zostanie odpalone przed kolejną turą."
            ),
            poziom=POZIOM_OSTRZEZENIE,
        )

    return StatusPamieci(
        procent=procent,
        tokeny=tokeny,
        komunikat=f"🟢 Zużycie pamięci: {tokeny} / {OKNO_KONTEKSTU_MAX} tokenów. Bezpieczny bufor.",
        poziom=POZIOM_OK,
    )


# =============================================================================
# Auto-streszczenie kontekstu (wywoływane po przekroczeniu PROG_OSTRZEZENIE)
# =============================================================================

def streszczaj_kontekst(
    klient:   Any,
    snapshot: SnapshotOpowiesci,
    model:    str | None = None,
) -> str:
    """Generuje streszczenie ``snapshot.ostatnie_tury`` jako pamięć długotrwałą.

    Parametry z `dictionaries/<jezyk>/opowiesci/streszczenie.yaml` (niska
    temperatura → wierne streszczenie, nie kreatywne). GUI po sukcesie
    zastępuje ``ostatnie_tury`` tablicą z jednym dictem typu
    ``{"akcja_gracza": "(streszczenie poprzednich N tur)", "narracja_skrot": <streszczenie>}``,
    żeby kontekst dla LLM zmieścił się w oknie i jednocześnie zachował
    ciągłość fabularną.
    """
    jezyk = snapshot.jezyk_projektu or "pl"
    przepis = _zaladuj_przepis(jezyk, "streszczenie")
    efektywny_model = model or przepis.get("model", MODEL_DOMYSLNY)

    payload = {
        "ostatnie_tury":    snapshot.ostatnie_tury,
        "postacie_aktywne": snapshot.postacie_aktywne,
        "stan":             snapshot.stan_poprzedni,
        "tura_numer":       snapshot.numer_tury,
    }
    user_msg = (
        "Lista tur do streszczenia poniżej.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    resp = klient.chat.completions.create(
        model=efektywny_model,
        messages=[
            {"role": "system", "content": przepis["prompt_systemowy"]},
            {"role": "user",   "content": user_msg},
        ],
        temperature=przepis.get("temperatura", 0.3),
        max_tokens=przepis.get("max_tokens", 800),
        timeout=przepis.get("timeout_s", 60.0),
    )
    return (resp.choices[0].message.content or "").strip()


# =============================================================================
# Cinematic Meta Warning (po 150 turach)
# =============================================================================

def generuj_cinematic_warning(
    klient:   Any,
    snapshot: SnapshotOpowiesci,
    model:    str | None = None,
) -> str:
    """Generuje Cinematic Meta Warning — przerywnik dramatyczny po 150 turach.

    Parametry z `dictionaries/<jezyk>/opowiesci/cinematic_warning.yaml`.
    Zwraca tekst Z markerami ``⚠️🚨⚠️`` (tak jak rozumie filter
    :meth:`core_opowiesci.ProjektOpowiesci.czysc_meta_warningi`). GUI
    zapisuje surowy tekst do ``.story.jsonl`` (log), pokazuje w
    ``wx.Dialog`` z ``wx.Bell()``, ale NIE appenduje do ``.txt`` — filter
    `czysc_meta_warningi` wyciąłby treść jeśli ktoś by spróbował.
    """
    jezyk = snapshot.jezyk_projektu or "pl"
    przepis = _zaladuj_przepis(jezyk, "cinematic_warning")
    efektywny_model = model or przepis.get("model", MODEL_DOMYSLNY)

    payload = {
        "tura_numer":       snapshot.numer_tury,
        "postacie_aktywne": snapshot.postacie_aktywne,
        "stan":             snapshot.stan_poprzedni,
        "ostatnie_tury":    snapshot.ostatnie_tury[-3:],   # tylko 3 ostatnie dla kontekstu
    }
    user_msg = (
        "Stan gry poniżej. Wygeneruj Cinematic Meta Warning.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    resp = klient.chat.completions.create(
        model=efektywny_model,
        messages=[
            {"role": "system", "content": przepis["prompt_systemowy"]},
            {"role": "user",   "content": user_msg},
        ],
        temperature=przepis.get("temperatura", 0.85),
        max_tokens=przepis.get("max_tokens", 600),
        timeout=przepis.get("timeout_s", 60.0),
    )
    return (resp.choices[0].message.content or "").strip()
