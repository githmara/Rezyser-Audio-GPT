"""
core_tokeny.py — Wspólny utility liczenia tokenów (tiktoken) dla obu trybów AI.

Po v15.0 mieliśmy dwa równoległe systemy pomiaru zużycia pamięci modelu:

* **Opowieści** (``opowiesci_ai.policz_tokeny``): tiktoken → liczy faktyczne
  tokeny payloadu, próg w procentach okna kontekstowego.
* **Reżyser** (``core_rezyser.status_pamieci_modelu``): ``len(full_story)`` →
  liczy znaki, próg w sztywnych liczbach (200k/175k/150k) z heurystyką
  „~4 znaki na token".

v15.1 ujednolica obie ścieżki — oba moduły importują z tego pliku:
* :func:`kodowanie_dla_modelu`  – LRU-cached encoder tiktoken
* :func:`policz_tokeny_chat`    – sumuje tokeny listy wiadomości chat
* stałe progowe (``OKNO_KONTEKSTU_MAX``, ``PROG_OSTRZEZENIE``, ``PROG_ALARM``)
* nazwy poziomów (``POZIOM_*``) dla GUI

Nie zawiera logiki specyficznej dla projektu — żadnych SnapshotOpowiesci ani
SnapshotProjektu. To czyste utility, więc oba moduły wyższego poziomu mogą
go importować bez ryzyka cyklu.
"""

from __future__ import annotations

import functools

import tiktoken

# =============================================================================
# Modele i okno kontekstowe
# =============================================================================

# Domyślne modele dla obu trybów. Oba mają to samo okno kontekstowe 128k,
# więc próg jest wspólny — różnią się tylko tokenizatorem (i tak ten sam
# ``o200k_base`` dla rodziny gpt-4o).
MODEL_DOMYSLNY_OPOWIESCI = "gpt-4o-mini"
MODEL_DOMYSLNY_REZYSER   = "gpt-4o"

# 128k context window dla gpt-4o / gpt-4o-mini. Liczymy TYLKO input —
# output (max_tokens) rezerwujemy ~5k osobno po stronie API.
OKNO_KONTEKSTU_MAX = 128_000

# Procenty zapełnienia okna — wspólne dla obu trybów.
# 70% → ostrzeżenie + (w opowieściach) auto-streszczenie przed kolejną turą.
# 90% → alarm, nie wysyłaj kolejnego promptu bez interwencji.
PROG_OSTRZEZENIE = 0.70
PROG_ALARM       = 0.90

# =============================================================================
# Poziomy statusu pamięci — wspólne nazwy dla obu modułów GUI
# =============================================================================
POZIOM_CZYSTA      = "czysta"
POZIOM_OK          = "ok"
POZIOM_OSTRZEZENIE = "ostrzezenie"
POZIOM_ALARM       = "alarm"

# =============================================================================
# Encoder tiktoken — LRU-cached + guard offline (od v18.10)
# =============================================================================

class BladTokenizeraOffline(RuntimeError):
    """tiktoken BPE tables unavailable (no Internet and no local cache).

    ``collect_all("tiktoken")`` nie pakuje tabel BPE do bundla — słownik
    pobiera się z sieci przy PIERWSZYM liczeniu tokenów (cache w
    ``%TEMP%\\data-gym-cache``). W zamkniętej sieci pobranie pada wyjątkiem
    sieciowym (nie ``KeyError``!), który do v18.9 leciał nietknięty do wątku
    GUI (crash konstruktora panelu Reżysera / EVT_TEXT). Świadoma decyzja
    v18.10: NIE bundlujemy tabel (filar jakości — API — i tak wymaga sieci),
    tylko degradujemy pomiar i komunikujemy brak Internetu w statusie.
    """


# Sticky-flaga: po pierwszej porażce pobrania NIE ponawiamy prób przy każdym
# wywołaniu (licznik odpala się z EVT_TEXT — retry z timeoutem sieciowym
# zamrażałby GUI na flaky łączu). Reset dopiero przy restarcie aplikacji.
_TOKENIZER_OFFLINE = False


def tokenizer_dostepny() -> bool:
    """Czy tabele BPE są dostępne (False = pomiar zdegradowany do heurystyki)."""
    return not _TOKENIZER_OFFLINE


@functools.lru_cache(maxsize=8)
def _zbuduj_encoder(model: str) -> tiktoken.Encoding:
    """Surowa budowa encodera; ``KeyError`` (nieznany model) → ``o200k_base``."""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


def kodowanie_dla_modelu(model: str) -> tiktoken.Encoding:
    """Zwraca encoder tiktoken — fallback na ``o200k_base`` dla nowych modeli.

    ``gpt-4o``/``gpt-4o-mini`` używają tokenizera ``o200k_base``. Jeśli OpenAI
    wyda nowszy model, którego biblioteka jeszcze nie zna,
    ``encoding_for_model`` rzuci ``KeyError`` — łapiemy i używamy
    najsensowniejszego defaultu zamiast crashować GUI.

    LRU jest istotne: ``status_pamieci_modelu`` wywoływane jest po każdej
    regeneracji (gauge GUI), a ``tiktoken.encoding_for_model`` przy braku
    cache'u inicjalizuje encoder z dysku.

    Raises:
        BladTokenizeraOffline: brak tabel BPE (offline + pusty cache).
            Konsumenci pomiaru pamięci NIE powinni jej propagować do GUI —
            ``policz_tokeny_chat`` degraduje się sam; bezpośredni użytkownicy
            encodera (chunking ``tlumacz_ai``) mapują ją na komunikat i18n.
    """
    global _TOKENIZER_OFFLINE
    if _TOKENIZER_OFFLINE:
        raise BladTokenizeraOffline(
            "tiktoken BPE tables unavailable (offline, no local cache)")
    try:
        return _zbuduj_encoder(model)
    except Exception as exc:  # noqa: BLE001 — requests.ConnectionError/HTTPError/OSError
        _TOKENIZER_OFFLINE = True
        raise BladTokenizeraOffline(
            "tiktoken BPE tables unavailable (offline, no local cache)"
        ) from exc


# =============================================================================
# Liczenie tokenów — payload chat completions
# =============================================================================

# Narzut formatu chat (OpenAI cookbook „Counting tokens for chat completions"):
# każda wiadomość ma ~4 tokeny na metadane roli + separatory, plus 2 tokeny
# na sygnaturę odpowiedzi assistanta.
NAGLOWEK_CHAT_PER_MSG = 4
NAGLOWEK_RESPONSE     = 2

# Heurystyka awaryjna sprzed v15.1: ~4 znaki na token. Używana WYŁĄCZNIE gdy
# tabele BPE są niepobieralne (offline) — pomiar pamięci nie może wtedy ubić
# przepływów, które od niego zależą (sufiks alarmu Burzy, rekoncyliacja przy
# wczytaniu projektu, bramka ALARM Opowieści). GUI sygnalizuje degradację
# przez `tokenizer_dostepny()`.
_ZNAKI_NA_TOKEN = 4


def policz_tokeny_chat(tresci: list[str], model: str) -> int:
    """Liczy tokeny payloadu chat.completions na podstawie samego ``content``.

    Args:
        tresci: Lista stringów — pole ``content`` każdej wiadomości chat
            (system / user / assistant) w docelowym payloadzie. Kolejność
            i role nie mają znaczenia dla liczby tokenów — istotny jest
            tylko sumaryczny rozmiar.
        model:  Nazwa modelu, dobiera tokenizator.

    Returns:
        Liczbę tokenów inputu (bez output / max_tokens — to liczy OpenAI
        osobno). Przy braku tabel BPE (offline) — przybliżenie znakowe
        (``_ZNAKI_NA_TOKEN``), nigdy wyjątek.
    """
    try:
        encoder = kodowanie_dla_modelu(model)
    except BladTokenizeraOffline:
        suma = NAGLOWEK_RESPONSE
        for tresc in tresci:
            suma += NAGLOWEK_CHAT_PER_MSG + max(1, len(tresc) // _ZNAKI_NA_TOKEN)
        return suma
    suma = NAGLOWEK_RESPONSE
    for tresc in tresci:
        suma += NAGLOWEK_CHAT_PER_MSG + len(encoder.encode(tresc))
    return suma
