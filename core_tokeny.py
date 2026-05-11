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
# Encoder tiktoken — LRU-cached
# =============================================================================

@functools.lru_cache(maxsize=8)
def kodowanie_dla_modelu(model: str) -> tiktoken.Encoding:
    """Zwraca encoder tiktoken — fallback na ``o200k_base`` dla nowych modeli.

    ``gpt-4o``/``gpt-4o-mini`` używają tokenizera ``o200k_base``. Jeśli OpenAI
    wyda nowszy model, którego biblioteka jeszcze nie zna,
    ``encoding_for_model`` rzuci ``KeyError`` — łapiemy i używamy
    najsensowniejszego defaultu zamiast crashować GUI.

    LRU jest istotne: ``status_pamieci_modelu`` wywoływane jest po każdej
    regeneracji (gauge GUI), a ``tiktoken.encoding_for_model`` przy braku
    cache'u inicjalizuje encoder z dysku.
    """
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


# =============================================================================
# Liczenie tokenów — payload chat completions
# =============================================================================

# Narzut formatu chat (OpenAI cookbook „Counting tokens for chat completions"):
# każda wiadomość ma ~4 tokeny na metadane roli + separatory, plus 2 tokeny
# na sygnaturę odpowiedzi assistanta.
NAGLOWEK_CHAT_PER_MSG = 4
NAGLOWEK_RESPONSE     = 2


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
        osobno).
    """
    encoder = kodowanie_dla_modelu(model)
    suma = NAGLOWEK_RESPONSE
    for tresc in tresci:
        suma += NAGLOWEK_CHAT_PER_MSG + len(encoder.encode(tresc))
    return suma
