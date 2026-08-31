"""
opowiesci_ai.py — Silnik LLM dla trybu „Interaktywne Opowieści" (v15.0 Faza 2).

Funkcja główna :func:`generuj_ture` wysyła snapshot stanu opowieści + akcję
gracza i otrzymuje strukturyzowany JSON (narracja + wybory + postacie +
stan + meta). Strukturę egzekwuje walidacja przez :mod:`jsonschema` po naszej
stronie (Anthropic nie ma ``response_format=json_object`` — o czysty JSON
prosimy w prompcie, a niezgodność naprawia self-correction).
Halucynacja struktury → retry max 2× z błędem jako wskazówką dla modelu;
trzeci błąd → ``RuntimeError`` (GUI łapie i pokazuje w dialogu).

Pomocnicza :func:`wygeneruj_wizualizacje` służy slash-komendzie
``/visualize`` (tryb 0/Burza) — multisensoryczny opis sceny do GUI bez
schemy, bez zapisu do plików (lifecycle dochodzi w Fazie 3).

Wzorzec architektoniczny: funkcyjny (jak :mod:`buduj_wielojezyczne_ui`),
nie obj-obj (jak :mod:`rezyser_ai`). Klient Anthropic (Claude) przekazywany
jawnie przez parametr ``klient``; brak globalnego state.

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

import core_llm as cl
import core_tokeny as ct
import sciezki
from bledy_ai import BladDlugosciOdpowiedzi, BladOdrzuceniaAI, BladStrukturyJSON

# v17.11.1: klauzula odrzucenia współdzielona z Reżyserem (single source —
# stała jest CELOWO po angielsku i trzymana w Pythonie, nie w YAML, żeby LLM
# jej nie tłumaczył/lokalizował; ten sam marker `[ODRZUCENIE_AI]` działa dla
# wszystkich języków). Opowieści dotąd nie miały żadnej klauzuli — `user_input`
# (free-text gracza) leciał prosto do payloadu, a odmowa LLM wracała jako
# nie-JSON i mylnie wyglądała jak `BladStrukturyJSON` po wyczerpaniu retry.
# `wykryto_odrzucenie` re-eksportowane, by GUI (`gui_opowiesci`) mogło wykryć
# tag w surowym tekście `/visualize` bez importu `przepisy_rezysera`.
from przepisy_rezysera import (  # noqa: F401  (re-eksport dla gui_opowiesci)
    KLAUZULA_ODRZUCENIA_DOMYSLNA,
    POWOD_KLUCZ,
    POWOD_PARSE,
    POWOD_WPIS,
    TAG_ODRZUCENIA_AI,
    opis_bledu_yaml,
    wykryto_odrzucenie,
    zglos_pominiecie,
)


def _dev_log(komunikat: str) -> None:
    """Strażowany ``print`` na konsolę dewelopera (packaged: stdout None → milczy).

    Wzorzec ``core_llm._dev_log``. Do v18.24.1 diagnostyka loadera przepisów
    Opowieści szła przez ``sys.stderr.write``, a w buildzie ``--windowed``
    ``sys.stderr`` jest ``None`` — komunikat przepadał (albo, przy gołym
    ``write``, wywracał wywołanie ``AttributeError``).
    """
    try:
        if sys.stdout is not None:
            print(f"[opowiesci_ai] {komunikat}", file=sys.stdout)
    except Exception:  # noqa: BLE001 — log nigdy nie może ubić wywołania
        pass

# =============================================================================
# Stałe konfiguracyjne
# =============================================================================

ENV_FILENAME       = "golden_key.env"
# v18.x (konsolidacja na Anthropic, Opcja A): WSZYSTKIE wywołania LLM Opowieści
# (tury 3/4/5, /visualize, streszczenie, cinematic) idą na jeden model Claude —
# koniec model-per-tryb (dawne MODEL_QUALITY/gpt-4o usunięte). Dispatch routuje
# na klienta Anthropic niezależnie od języka UI.
MODEL_NARRACJA     = "claude-sonnet-5"
# gpt-4o-mini ZOSTAJE wyłącznie do liczenia tokenów (tiktoken o200k_base) na
# pasku pamięci — NIE jest już modelem LLM. `OKNO_KONTEKSTU_MAX=128k` (core_tokeny)
# pozostaje LOGICZNYM budżetem kosztu/spójności (+ auto-streszczenie po 70%), nie
# realnym oknem 1M Sonneta 4.6.
MODEL_DOMYSLNY     = ct.MODEL_DOMYSLNY_OPOWIESCI
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

# v15.5 — sentinel-e wpisów `ostatnie_tury`. Po streszczeniu (>70% okna) lista
# zwija się do JEDNEGO wpisu z `akcja_gracza == AKCJA_STRESZCZENIE` (cały
# backstory w `narracja_skrot`). AKCJA_SYNC oznacza wpis-końcówkę dorzucony
# przy ręcznym odświeżeniu narracji z dysku. Stałe (zamiast literałów),
# żeby tworzenie i detekcja sentinela nie rozjechały się.
AKCJA_STRESZCZENIE = "(streszczenie poprzednich tur)"
AKCJA_SYNC         = "(narracja zsynchronizowana z dysku)"

# =============================================================================
# JSON-schema dla strukturyzowanej tury
# =============================================================================
# Egzekwowane przez `jsonschema.validate` po naszej stronie (typy + obecność
# kluczy + długości tablic). Anthropic nie ma `response_format=json_object`, więc
# NIE mamy gwarancji nawet samej składni JSON — o czysty JSON prosimy w prompcie,
# a niezgodność (parse error / złamana schema) wraca jako wskazówka self-correction
# i model regeneruje. ŚWIADOMIE bez `output_config`/json_schema: wymuszony schemat
# zablokowałby goły tag `[ODRZUCENIE_AI]` (klauzula odmowy), wykrywany substringiem
# PRZED `json.loads` (wzorzec 1:1 z `rezyser_ai`).
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
            # Lista postaci obecnych w bieżącej turze — część stanu gry
            # (snapshot LLM, persystowana w `.game.json`). v17.4 (P6A):
            # dawniej budowano z niej `.md` „Księgę Świata" jako most do
            # Reżysera; most usunięty (nigdy nie powstała ścieżka wczytania),
            # więc to pole służy już tylko jako pamięć postaci między turami.
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

# Schemat wysyłany do API (v18.23) — structured outputs zamiast wymuszania JSON
# samym promptem. Budowany RAZ przy imporcie (kompilacja schematu po stronie API
# jest cache'owana bajtowo, więc treść nie może się różnić między wywołaniami).
#
# UWAGA na `stan`: kanoniczny `SCHEMA_TURA` ma tam świadomie
# ``additionalProperties: True`` („silnik może rozszerzać; Python ignoruje
# nieznane"), a structured outputs dopuszcza WYŁĄCZNIE ``false`` — 400 bez tego.
# `schemat_do_api` domyka to w KOPII, więc rozkład odpowiedzialności jest taki:
# model NIE MOŻE już wymyślać kluczy stanu (przy 9 językach dawałby
# `stan.zdrowie`/`stan.health`/`stan.hp` zależnie od dryfu promptu — czego nic
# w dole nie skonsumuje), a nasza walidacja i czytnik `.game.json` pozostają
# tolerancyjne dla starych zapisów. Gdyby kiedyś potrzebny był otwarty slot,
# modeluj go jako DANE (lista par `{klucz, wartosc}` + `wersja_stanu`), nie jako
# otwarty schemat.
SCHEMA_TURA_API: dict[str, Any] = cl.schemat_z_dyskryminatorem(
    SCHEMA_TURA, TAG_ODRZUCENIA_AI,
)


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
    # v17.9 (Obszar 2): surowy JSON OSTATNIEJ tury — wstrzykiwany przez
    # `generuj_ture` jako wiadomość `role=assistant` PRZED user-payloadem.
    # Daje modelowi ciągłość (kontynuuję własną wypowiedź) i żywy wzorzec
    # poprawnej struktury wyjścia. Źródło: poprzedni `WynikTury.surowy_json`
    # (gra w toku) albo ostatnia linia `.story.jsonl` (po reloadzie z dysku).
    # Pusty string = brak (tura 1 / świeży start bufora po streszczeniu).
    ostatni_surowy_json: str               = ""


@dataclass
class WynikTury:
    """Wynik :func:`generuj_ture` — strukturyzowana tura po walidacji."""
    narracja:         str
    wybory:           list[dict[str, str]]
    postacie_aktywne: list[dict[str, str]]
    stan:             dict[str, Any]
    meta:             dict[str, Any]
    surowy_json:      str   # do zapisu w `.story.jsonl` (Faza 3)
    # v17.11.1: True → LLM odmówił obsłużenia akcji gracza (zwrócił marker
    # `[ODRZUCENIE_AI]` zamiast JSON-a). GUI pokazuje wtedy przyjazny komunikat,
    # NIE awansuje tury i NIE zapisuje plików (tura „się nie wydarzyła").
    # Pozostałe pola są pustymi placeholderami — nie wolno ich konsumować, gdy
    # `odrzucone=True`. Domyślne False → stare ścieżki sukcesu bez zmian.
    odrzucone:        bool = False


@dataclass
class StatusPamieci:
    """Status wskaźnika pamięci modelu — gotowe dane dla GUI.

    Pole ``poziom`` jest jednym z ``POZIOM_*`` — GUI dobiera kolor
    (zielony/pomarańczowy/czerwony) i decyduje czy auto-streszczenie
    odpalić w tle.
    """
    procent:        int          # 0–100, do `wx.Gauge.SetValue()`
    tokeny:         int          # surowa liczba tokenów wejściowych
    poziom:         str          # POZIOM_CZYSTA/OK/OSTRZEZENIE/ALARM
    # v17.9: pole `komunikat` USUNIĘTE — GUI (`gui_opowiesci._aktualizuj_pamiec_modelu`)
    # i tak budowało etykietę z i18n (`opowiesci.pamiec_status_format` + `pamiec_etap_*`
    # po `poziom`), a hard-kodowany polski `komunikat` w `oblicz_status_pamieci` był
    # martwy (niewyświetlany) — usunięty, by „oczyszczenie hard-kodów" było prawdziwe.


# =============================================================================
# Inicjalizacja klienta Anthropic (Claude)
# =============================================================================

def inicjalizuj_klienta(app_dir: str | None = None) -> Any | None:
    """Ładuje ``golden_key.env`` z roota repo i zwraca :class:`core_llm.KlientLLM`.

    Od v18.4 provider-agnostic (przez ``core_llm``): domyślnie Anthropic Claude
    (``ANTHROPIC_API_KEY``/``sk-ant-``), a przy ``LLM_PROVIDER=openai_compat`` —
    dowolny endpoint zgodny z OpenAI. Zwraca ``None`` gdy konfiguracja niekompletna
    (panel pokaże ``brak_api_tresc`` przy próbie wysyłki). Nigdy nie rzuca — błąd
    inicjalizacji nie powinien blokować otwarcia panelu.
    """
    base = app_dir or sciezki.KATALOG_BAZOWY_STR
    env_path = os.path.join(base, ENV_FILENAME)
    if not os.path.exists(env_path):
        return None
    load_dotenv(env_path)
    return cl.zbuduj_klienta(cl.wczytaj_konfiguracje())


# =============================================================================
# Wywołanie Claude Messages API (wspólny helper dla wszystkich trybów)
# =============================================================================

def _wywolaj_claude(
    klient:      Any,
    model:       str,
    system:      str,
    messages:    list[dict],
    *,
    max_tokens:  int,
    temperature: float,
    timeout:     float,
    segmenty:    list[dict] | None = None,
    wymusz_json: bool = False,
    schema_json: dict | None = None,
    slad:        list[dict] | None = None,
) -> tuple[str, str | None]:
    """Wywołuje warstwę LLM (proza/JSON, BEZ reasoningu) → (tekst, stop_reason).

    Klon ``rezyser_ai._wywolaj_claude`` dostrojony do Opowieści: model/temperatura/
    max_tokens podajemy jawnie, bo Opowieści nie mają dataclassy ``PrzepisRezysera``
    — parametry żyją w dictach YAML. ``thinking=disabled`` (narracja/JSON, reasoning
    tylko dodawałby latencję i koszt). ``temperature`` honoruje Sonnet 4.6 (jedyny
    parametr próbkowania — bez ``top_p``). Timeout per-wywołanie przez
    ``with_options`` (Messages API nie przyjmuje ``timeout=`` na ``create``).

    ``segmenty`` (role pre-v18 dla ``openai_compat``) przekazujemy bez zmian — na
    Anthropic ignorowane (nazwa „Claude" w sygnaturze jest historyczna).
    """
    return cl.wywolaj_llm(
        klient,
        model=model,
        system=system,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        segmenty=segmenty,
        wymusz_json=wymusz_json,
        schema_json=schema_json,
        slad=slad,
    )


# =============================================================================
# Ładowanie przepisów (prompty + parametry OpenAI) z YAML
# =============================================================================
# Anty-spaghetti: prompty systemowe trzymane w `dictionaries/<kod>/opowiesci/`,
# nie hardkodowane w Pythonie (patrz `reguly_architektury.md`). Wzorzec
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

ROOT_DICT = sciezki.KATALOG_BAZOWY / "dictionaries"

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
    Aktywacja fallbacku emituje WARN na konsolę dewelopera — pomaga maintainerom
    lokalizować nieuzupełnione paczki językowe (cisza znaczy że stuba
    nikt nie zauważy, dopóki gracz nie zgłosi obcojęzycznych odpowiedzi
    AI w grze, którą myślał że gra w swoim języku).

    v18.24.2: **błąd składni YAML zachowuje się jak brak pliku** — plik zepsuty
    w Managerze Reguł spada na paczkę `en` zamiast wywalać wyjątkiem konstruktor
    panelu Opowieści (zmierzone: niezamknięty cudzysłów w `zaczatki.yaml` →
    `ScannerError` z `_build_ui` → panel trwale niedostępny, bo `main` zniszczył
    już poprzedni). Powód pominięcia trafia do wspólnego rejestru
    (`przepisy_rezysera.zglos_pominiecie`), więc gracz zobaczy go w dialogu
    diagnostycznym. Gdy padną OBA pliki (język i `en`) — dopiero wtedy wyjątek,
    bo bez prompta systemowego nie ma czym karmić modelu.
    """
    kandydaci = [jezyk] if jezyk == "en" else [jezyk, "en"]
    powody: list[str] = []
    for kod in kandydaci:
        sciezka = ROOT_DICT / kod / "opowiesci" / f"{nazwa}.yaml"
        if not sciezka.exists():
            if kod != "en":
                _dev_log(
                    f"brak {kod}/opowiesci/{nazwa}.yaml — fallback do "
                    f"en/opowiesci/{nazwa}.yaml (paczka {kod} niekompletna?)"
                )
            powody.append(f"{sciezka}: brak pliku")
            continue
        try:
            with open(sciezka, "r", encoding="utf-8") as fh:
                dane = _pyyaml.safe_load(fh)
        except Exception as exc:  # noqa: BLE001 — YAMLError / OSError / Unicode
            opis = opis_bledu_yaml(exc)
            zglos_pominiecie(str(sciezka), POWOD_PARSE, opis)
            powody.append(f"{sciezka}: {opis}")
            continue
        return dane or {}
    # Treść wyjątku jest CELOWO techniczna i bez porady: wpada do komunikatu
    # błędu AI w panelu, a ten musi działać w dziewięciu językach. Poradę „co
    # zrobić" dostaje gracz z dialogu diagnostycznego (`diag.*`, zlokalizowany),
    # który zapala się z tego samego rejestru powodów.
    raise FileNotFoundError(f"opowiesci/{nazwa}.yaml: {'; '.join(powody)}")


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
        raise ValueError(f"Unknown story mode: {tryb} (expected 0/3/4/5)")

    zasady_blok = ""
    if zasady_swiata and zasady_swiata.strip():
        # Rama bloku (nagłówek + instrukcja wiążąca) z `baza.yaml` w języku
        # projektu — wyniesiona z hard-kodu PL, żeby blok nie był polski w
        # obcojęzycznej grze. {zasady} (treść gracza) wstawiamy między nie.
        zasady_naglowek = _tekst_przepisu(
            jezyk, "baza", "zasady_swiata_naglowek",
            "## World rules (defined by the player)",
        )
        zasady_instrukcja = _tekst_przepisu(
            jezyk, "baza", "zasady_swiata_instrukcja",
            "These rules are ABSOLUTELY binding for the entire game. Respect them "
            "in the narration, dialogue, character descriptions, choices and visualizations.",
        )
        zasady_blok = (
            f"\n\n{zasady_naglowek}\n\n"
            f"{zasady_swiata.strip()}\n\n"
            f"{zasady_instrukcja}"
        )

    if tryb == TRYB_BURZA:
        # Visualize stoi na własnych nogach — bez bazy narracyjnej.
        baza_prompt = _prompt_systemowy(jezyk, "tryb_burza")
        return baza_prompt + zasady_blok + KLAUZULA_ODRZUCENIA_DOMYSLNA

    baza   = _prompt_systemowy(jezyk, "baza")
    addon  = _prompt_systemowy(jezyk, nazwa)
    # v17.11.1: klauzula odrzucenia ZAWSZE na samym końcu (po addonie trybu i
    # po blokach zasad świata) — gracz wpisuje free-text, więc LLM musi mieć
    # jednoznaczną furtkę odmowy z markerem `[ODRZUCENIE_AI]` (wykrywanym przed
    # walidacją JSON w `generuj_ture`), zamiast generować nie-JSON / łamać się.
    return baza + zasady_blok + "\n\n" + addon + KLAUZULA_ODRZUCENIA_DOMYSLNA


def _prompt_systemowy(jezyk: str, nazwa: str) -> str:
    """Czyta `prompt_systemowy` z przepisu z fallbackiem lang→en (v18.24.2).

    Do v18.24.1 trzy wywołania w :func:`_zbuduj_prompt_systemowy` sięgały po ten
    klucz INDEKSEM (`[...]`), więc usunięcie go w Managerze Reguł kończyło się
    surowym ``KeyError: 'prompt_systemowy'`` w wątku tła — worker GUI to łapie,
    ale gracz widział komunikat bez nazwy pliku i bez wskazówki. Teraz brak
    klucza w paczce języka spada na `en` (jak przy braku całego pliku, patrz
    :func:`_zaladuj_przepis`) i zgłasza powód do wspólnego rejestru
    diagnostycznego; wyjątek zostaje tylko dla przypadku „nie ma nigdzie",
    bo bez prompta systemowego nie ma czym karmić modelu.
    """
    for kod in ([jezyk] if jezyk == "en" else [jezyk, "en"]):
        val = _zaladuj_przepis(kod, nazwa).get("prompt_systemowy")
        if isinstance(val, str) and val.strip():
            return val
        zglos_pominiecie(
            str(ROOT_DICT / kod / "opowiesci" / f"{nazwa}.yaml"),
            POWOD_KLUCZ, "prompt_systemowy",
        )
    # Jak wyżej: technicznie, bez polskiej porady — lokalizowany opis i wskazówka
    # naprawy idą kanałem diagnostycznym (`diag.powod.klucz`).
    raise KeyError(
        f"opowiesci/{nazwa}.yaml: prompt_systemowy ({jezyk}, en)"
    )


def zaczatki(jezyk: str) -> dict[str, dict]:
    """Zwraca WYŁĄCZNIE używalne zaczątki Quick Start z ``opowiesci/zaczatki.yaml``.

    Walidacja siedzi w silniku (nie w panelu), bo pytają o nią DWA miejsca:
    ``gui_opowiesci`` przy budowie listy presetów i skan diagnostyczny Managera
    Reguł. Gdy walidacja żyła tylko w panelu, Manager mówił „wczytane bez
    zastrzeżeń" o pliku z niekompletnym wpisem (zmierzone na własnym teście
    v18.24.2).

    Wpis bez ``etykieta`` pomijamy pojedynczo — reszta presetów działa, a powód
    trafia do wspólnego rejestru diagnostycznego. Zepsuty plik w całości
    (składnia) obsługuje :func:`_zaladuj_przepis`; tutaj wyjątek propaguje, żeby
    wywołujący zdecydował (panel: pusta lista presetów, skan: wpis w raporcie).
    """
    sciezka = str(ROOT_DICT / jezyk / "opowiesci" / "zaczatki.yaml")
    surowe = _zaladuj_przepis(jezyk, "zaczatki").get("zaczatki")
    if not isinstance(surowe, dict):
        zglos_pominiecie(sciezka, POWOD_KLUCZ, "zaczatki")
        return {}

    uzywalne: dict[str, dict] = {}
    for klucz, wpis in surowe.items():
        etykieta = wpis.get("etykieta") if isinstance(wpis, dict) else None
        if not etykieta:
            zglos_pominiecie(sciezka, POWOD_WPIS, f"zaczatki.{klucz}: etykieta")
            continue
        uzywalne[str(klucz)] = wpis
    return uzywalne


def _parametr_z_yaml(jezyk: str, nazwa: str, klucz: str, default: Any) -> Any:
    """Czyta wartość parametru z `<jezyk>/opowiesci/<nazwa>.yaml::<klucz>` z fallbackiem.

    Używane do `model`, `temperatura`, `max_tokens`, `timeout_s` — pozwala
    lingwiście / autorowi przepisu strojenie LLM bez modyfikacji Pythona.
    """
    przepis = _zaladuj_przepis(jezyk, nazwa)
    return przepis.get(klucz, default)


def _tekst_przepisu(jezyk: str, nazwa: str, klucz: str, default_en: str) -> str:
    """Czyta tekstowy klucz z przepisu z fallbackiem NA POZIOMIE KLUCZA: lang→en→literał.

    `_zaladuj_przepis` daje już fallback na poziomie PLIKU (brak
    `<jezyk>/opowiesci/<nazwa>.yaml` → `en/...`). Tu dokładamy fallback na
    poziomie KLUCZA: gdy plik języka istnieje, ale nie ma jeszcze danego klucza
    (np. paczka w trakcie tłumaczenia promptów), bierzemy klucz z `en`, a w
    ostateczności literał `default_en`. Zasada międzynarodowości spójna z
    `i18n.t` (lang → en → marker) — NIGDY polski przeciek do obcojęzycznej tury.

    Używane do wrapperów wiadomości role=user (`instrukcja_payload`) i ramy
    bloku „Zasady świata" (`zasady_swiata_*`), wyniesionych z hard-kodu Pythona,
    żeby pojedyncza tura nie mieszała języków.
    """
    val = _zaladuj_przepis(jezyk, nazwa).get(klucz)
    if val is None and jezyk != "en":
        val = _zaladuj_przepis("en", nazwa).get(klucz)
    return val if isinstance(val, str) else default_en


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
        "tura_numer":         snapshot.numer_tury,
        "jezyk_narracji":     snapshot.jezyk_projektu,
        "seed_swiata":        snapshot.seed_swiata,
        "ostatnie_tury":      snapshot.ostatnie_tury,
        "postacie_aktywne":   snapshot.postacie_aktywne,
        "stan":               snapshot.stan_poprzedni,
        "akcja_gracza":       user_input,
    }

    # Fiolka — bloki tylko gdy istotne. LLM ignoruje brakujące klucze; obecne
    # interpretuje zgodnie z instrukcjami w `tryb_mniejsze_zlo.yaml::prompt_systemowy`.
    if fiolka_aktywacja:
        payload["fiolka_aktywacja_w_tej_turze"] = True
    if fiolka_seed is not None:
        payload["fiolka_efekt_seed"] = fiolka_seed

    # Wrapper proceduralny w języku projektu (z `baza.yaml`, fallback en),
    # nie hard-kodowany polski — żeby tura nie mieszała języków.
    jezyk = snapshot.jezyk_projektu or "pl"
    instrukcja = _tekst_przepisu(
        jezyk, "baza", "instrukcja_payload",
        "The game state and player action are below. Generate the next turn "
        "according to the JSON schema defined in the system prompt.",
    )
    return instrukcja + "\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)


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
    - ``opisy_skutkow.<kategoria>`` — pula opisów per kategoria (od v18.17:
      8/7/5 dla harmful/distortion/rare_beneficial, wcześniej 5/5/3);
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
        klient           : skonfigurowany klient Anthropic (z :func:`inicjalizuj_klienta`)
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
        BladStrukturyJSON: po wyczerpaniu prób retry (halucynacja struktury).
        BladDlugosciOdpowiedzi: przy ucięciu odpowiedzi (stop_reason="max_tokens").
        Wyjątki Anthropic (RateLimitError, APITimeoutError, ...) są
        propagowane — GUI łapie i pokazuje w :func:`_obsluz_blad`.
    """
    jezyk            = snapshot.jezyk_projektu or "pl"
    prompt_systemowy = _zbuduj_prompt_systemowy(tryb, jezyk, snapshot.zasady_swiata)
    user_payload     = _zbuduj_user_payload(
        snapshot,
        user_input,
        fiolka_aktywacja=fiolka_aktywacja,
        fiolka_seed=fiolka_seed,
    )

    # Parametry: priorytet to argument funkcji (GUI override), potem YAML trybu,
    # na końcu stała MODEL_NARRACJA (Claude). YAML produkcyjnie zawiera już model
    # Claude — fallback chroni tylko testy izolowane / niekompletne paczki.
    nazwa_pliku = _NAZWA_PLIKU_PER_TRYB[tryb]
    efektywny_model = model or _parametr_z_yaml(jezyk, nazwa_pliku, "model", MODEL_NARRACJA)
    temperatura     = _parametr_z_yaml(jezyk, nazwa_pliku, "temperatura", TEMPERATURE_TURA)

    # Anthropic: `system` osobno (parametr), PIERWSZA wiadomość musi być `user`.
    # Ciągłość poprzedniej tury (dawniej role=assistant w OpenAI, v17.9 Obszar 2)
    # zwijamy do wiadomości `user` jako oznaczony blok — nie wolno zacząć od
    # `assistant`. Schema i tak siedzi w prompt-systemowym; tracimy tylko mikro-
    # optymalizację „model kontynuuje własną wypowiedź", spójnie z `buduj_payload`
    # Reżysera (cały kontekst w jednej wiadomości user).
    # `czesci` → zwinięty `user` (Anthropic, filar). `segmenty` → te same bloki z
    # rolą `assistant` (poprzedni JSON = wypowiedź modelu) / `user` (payload tury) dla
    # `openai_compat` — przywraca rozdział ról sprzed v18 na cudzych endpointach.
    czesci: list[str] = []
    segmenty: list[dict] = []
    if snapshot.ostatni_surowy_json and snapshot.ostatni_surowy_json.strip():
        blok_poprzedni = (
            "[PREVIOUS TURN — your last JSON output; keep continuity and the same "
            "structure]:\n" + snapshot.ostatni_surowy_json
        )
        czesci.append(blok_poprzedni)
        segmenty.append({"rola": "assistant", "content": blok_poprzedni})
    czesci.append(user_payload)
    segmenty.append({"rola": "user", "content": user_payload})
    messages: list[dict] = [{"role": "user", "content": "\n\n".join(czesci)}]

    ostatni_blad: str | None = None
    proby_struktury = 0
    slad: list[dict] = []   # v18.23 — metryka nietreściowa, patrz `core_llm.formatuj_slad`
    while True:
        # Self-correction: wskazówkę o poprzedniej porażce dopinamy jako wiadomość
        # `user` (Anthropic nie przyjmuje dowolnych `system` w `messages`; kolejne
        # `user` API skleja w jedną turę). Wzorzec 1:1 z `rezyser_ai.generuj_burze`.
        # v18.23: wskazówka opisuje STRUKTURĘ i NIE cytuje komunikatu parsera —
        # patrz `core_llm.RETRY_NIEPARSOWALNY`.
        if ostatni_blad is not None:
            komunikat = {"role": "user", "content": ostatni_blad}
            messages.append(komunikat)
            # Retry-walidacja = instrukcja meta → `system` w payloadzie z rolami (compat).
            segmenty.append({"rola": "system", "content": komunikat["content"]})

        surowa, stop_reason = _wywolaj_claude(
            klient, efektywny_model, prompt_systemowy, messages,
            max_tokens=MAX_TOKENS_OUT, temperature=temperatura, timeout=TIMEOUT_S,
            segmenty=segmenty, wymusz_json=True,
            schema_json=SCHEMA_TURA_API, slad=slad,
        )
        ostatni_blad = None   # zużyty — wiadomość już doklejona (jeśli była)

        if stop_reason == "max_tokens":
            raise BladDlugosciOdpowiedzi(
                f"The model hit its max_tokens={MAX_TOKENS_OUT} limit — the response "
                f"was cut off before the JSON could be closed. Shorten the context "
                f"or raise MAX_TOKENS_OUT."
            )

        # v18.23: odmowa KLASYFIKATORA (nie modelu) — treść bywa wtedy pusta, więc
        # bez tej gałęzi `json.loads("")` zużywał retry i user widział „błąd
        # struktury" tam, gdzie prawdą jest „model odmówił".
        if stop_reason == cl.STOP_ODRZUCENIE:
            return WynikTury(
                narracja="", wybory=[], postacie_aktywne=[],
                stan={}, meta={}, surowy_json=surowa, odrzucone=True,
            )

        # v17.11.1: odmowa LLM ma pierwszeństwo PRZED parsowaniem JSON (wzorzec
        # 1:1 z `rezyser_ai.generuj_burze/skrypt`). Substringowy `wykryto_odrzucenie`
        # łapie tag niezależnie od tego, czy przyszedł jako goła linia (bez
        # schematu), czy jako wartość pola gałęzi `typ=odrzucenie` (v18.23). Tag =
        # legalny wynik, NIE błąd retry; zwracamy pustą turę z flagą.
        if wykryto_odrzucenie(surowa):
            return WynikTury(
                narracja="", wybory=[], postacie_aktywne=[],
                stan={}, meta={}, surowy_json=surowa, odrzucone=True,
            )

        try:
            # `napraw_luzny_json` = pas i szelki dla `openai_compat` (structured
            # outputs tam nie ma). Potem granica parsowania: zdejmujemy dyskryminator,
            # żeby walidacja i mapowanie widziały kształt sprzed v18.23.
            dane = json.loads(cl.napraw_luzny_json(surowa))
            odmowa, dane, powod = cl.rozpakuj_dyskryminator(dane)
            if odmowa:
                cl.zaloguj_odmowe(powod, "tura")
                return WynikTury(
                    narracja="", wybory=[], postacie_aktywne=[],
                    stan={}, meta={}, surowy_json=surowa, odrzucone=True,
                )
            jsonschema.validate(instance=dane, schema=SCHEMA_TURA)
        except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
            proby_struktury += 1
            if proby_struktury > MAX_RETRIES:
                raise BladStrukturyJSON(
                    f"The AI returned a malformed JSON structure {MAX_RETRIES + 1} "
                    f"times in a row.\n{cl.opisz_porazke_json(exc)}\n"
                    f"{cl.formatuj_slad(slad)}"
                ) from exc
            ostatni_blad = (
                cl.RETRY_NIEPARSOWALNY
                if isinstance(exc, json.JSONDecodeError)
                else cl.komunikat_retry_schema(exc)
            )
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
    efektywny_model = model or przepis.get("model", MODEL_NARRACJA)
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
    instrukcja = _tekst_przepisu(
        jezyk, "tryb_burza", "instrukcja_payload",
        "The game state is below. Generate a multisensory scene description.",
    )
    user_msg = instrukcja + "\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    tekst, stop_reason = _wywolaj_claude(
        klient, efektywny_model, prompt_systemowy,
        [{"role": "user", "content": user_msg}],
        max_tokens=przepis.get("max_tokens", 1000),
        temperature=przepis.get("temperatura", TEMPERATURE_VIS),
        timeout=przepis.get("timeout_s", 60.0),
    )
    # v18.23: odmowa KLASYFIKATORA nie zwraca tagu (bo nie zwraca treści), więc
    # normalizujemy ją do tego samego sygnału, którego GUI już nasłuchuje
    # (`_visualize_worker` → `wykryto_odrzucenie` → przyjazny komunikat). Zero
    # zmian po stronie panelu; bez tego gracz dostawał PUSTY dialog opisu.
    if stop_reason == cl.STOP_ODRZUCENIE:
        return TAG_ODRZUCENIA_AI
    return tekst


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
    # v17.9: zwracamy WYŁĄCZNIE dane (procent/tokeny/poziom) — treść komunikatu
    # składa GUI z i18n (`gui_opowiesci._aktualizuj_pamiec_modelu`). Koniec
    # hard-kodowanego polskiego `komunikat` w silniku.
    if snapshot.numer_tury == 0 and not snapshot.ostatnie_tury:
        return StatusPamieci(procent=0, tokeny=0, poziom=POZIOM_CZYSTA)

    tokeny = policz_tokeny(snapshot, tryb, model)
    procent = min(int(tokeny / OKNO_KONTEKSTU_MAX * 100), 100)
    udzial  = tokeny / OKNO_KONTEKSTU_MAX

    if udzial >= PROG_ALARM:
        return StatusPamieci(procent=procent, tokeny=tokeny, poziom=POZIOM_ALARM)
    if udzial >= PROG_OSTRZEZENIE:
        return StatusPamieci(procent=procent, tokeny=tokeny, poziom=POZIOM_OSTRZEZENIE)
    return StatusPamieci(procent=procent, tokeny=tokeny, poziom=POZIOM_OK)


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
    efektywny_model = model or przepis.get("model", MODEL_NARRACJA)

    payload = {
        "ostatnie_tury":    snapshot.ostatnie_tury,
        "postacie_aktywne": snapshot.postacie_aktywne,
        "stan":             snapshot.stan_poprzedni,
        "tura_numer":       snapshot.numer_tury,
    }
    instrukcja = _tekst_przepisu(
        jezyk, "streszczenie", "instrukcja_payload",
        "The list of turns to summarize is below.",
    )
    user_msg = instrukcja + "\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    tekst, stop_reason = _wywolaj_claude(
        klient, efektywny_model, przepis["prompt_systemowy"],
        [{"role": "user", "content": user_msg}],
        max_tokens=przepis.get("max_tokens", 800),
        temperature=przepis.get("temperatura", 0.3),
        timeout=przepis.get("timeout_s", 60.0),
    )
    # v18.23: tu pusta treść jest NISZCZĄCA — `_streszczenie_done` zwija całą
    # historię (np. sześć tur) do JEDNEGO wpisu o treści streszczenia, więc
    # odmowa oznaczałaby bezpowrotną utratę kontekstu gry. Podnosimy błąd:
    # worker GUI ma `except Exception`, po którym gra zostaje nietknięta,
    # a alarm pamięci wraca przy kolejnej turze.
    if stop_reason == cl.STOP_ODRZUCENIE or (
        not tekst.strip() and stop_reason != "max_tokens"
    ):
        raise BladOdrzuceniaAI(
            "The model returned no summary (stop_reason="
            f"{stop_reason!r}). Refusing to collapse the game history into an "
            "empty entry — the turns would be lost irreversibly."
        )
    return tekst.strip()


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
    efektywny_model = model or przepis.get("model", MODEL_NARRACJA)

    payload = {
        "tura_numer":       snapshot.numer_tury,
        "postacie_aktywne": snapshot.postacie_aktywne,
        "stan":             snapshot.stan_poprzedni,
        "ostatnie_tury":    snapshot.ostatnie_tury[-3:],   # tylko 3 ostatnie dla kontekstu
    }
    instrukcja = _tekst_przepisu(
        jezyk, "cinematic_warning", "instrukcja_payload",
        "The game state is below. Generate the Cinematic Meta Warning.",
    )
    user_msg = instrukcja + "\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    tekst, stop_reason = _wywolaj_claude(
        klient, efektywny_model, przepis["prompt_systemowy"],
        [{"role": "user", "content": user_msg}],
        max_tokens=przepis.get("max_tokens", 600),
        temperature=przepis.get("temperatura", 0.85),
        timeout=przepis.get("timeout_s", 60.0),
    )
    # v18.23: pusty warning trafiał do `.story.jsonl` i ustawiał
    # `cinematic_pokazany`, więc ostrzeżenie nie wracało już NIGDY. Błąd jest
    # tu lepszy: `_cinematic_blad` zalicza to jako cichy fail (side-quest),
    # ale nie zapisuje pustego wpisu do historii gry.
    if stop_reason == cl.STOP_ODRZUCENIE or not tekst.strip():
        raise BladOdrzuceniaAI(
            "The model returned no Cinematic Meta Warning (stop_reason="
            f"{stop_reason!r})."
        )
    return tekst.strip()
