"""
tlumacz_ai.py – Silnik tłumaczenia Anthropic Claude (moduł pomocniczy Poligloty).

Wydzielony z ``gui_poliglota.py`` i ``core_poliglota.py``, by:
  * nie mieszać logiki „sieciowej” (OpenAI) z czystym przetwarzaniem tekstu,
  * ułatwić testowanie i ewentualną wymianę modelu,
  * mieć jedno miejsce na politykę podziału tekstu na bloki, zapis
    tymczasowy (``runtime/temp_*.jsonl``) i wznawianie po przerwaniu.

Moduł nie zależy od wxPython – komunikuje się z GUI wyłącznie przez
przekazane callbacki. Dzięki temu GUI może wywoływać :func:`tlumacz_dlugi_tekst`
w wątku tła i odbierać postęp/wyniki bez tzw. GUI freeze.

Szczegółowy przebieg:
  1. Tekst dzielony jest na bloki po maksymalnie ``max_tokenow_na_blok``
     tokenów (tiktoken przez ``core_tokeny`` — ten sam licznik co tryby
     Reżysera/Opowieści), z zachowaniem podziału na akapity (``\\n``).
     Limit tokenowy (nie znakowy!) chroni języki token-gęste (CJK itp.)
     przed przekroczeniem limitu tokenów WYJŚCIA modelu.
  2. Jeśli ostatni blok jest krótki, sklejany jest z przedostatnim.
  3. Dla każdego bloku wysyłane jest zapytanie ``messages.create`` (Anthropic
     Messages API) do modelu ``model_tlumacz``. Ostatni tłumaczony blok podawany
     jest jako kontekst do kolejnego wywołania – dzięki temu model trzyma spójną
     terminologię. Odpowiedź ucięta limitem wyjścia (``stop_reason == "max_tokens"``)
     NIE jest akceptowana — blok jest dzielony na pół i tłumaczony rekurencyjnie
     (:func:`_tlumacz_blok`), zamiast bezgłośnie gubić końcówkę tekstu.
  4. Po każdym udanym bloku treść dopisywana jest do pliku tymczasowego
     ``runtime/temp_<nazwa_bazowa>.jsonl``. Jeśli użytkownik przerwie
     tłumaczenie i ponownie je uruchomi z tym samym plikiem źródłowym,
     gotowe bloki są odtwarzane z tego pliku (oszczędność kredytów API).
     Pierwsza linia pliku to metryka zgodności (wersja chunkowania +
     liczba bloków) — cache z innego podziału jest odrzucany w całości.
  5. Na końcu wywoływana jest druga, krótka konsultacja (``model_iso``)
     w celu ustalenia kodu języka BCP-47 (dwuliterowy ISO 639-1,
     dla odmian regionalnych/pisma z podtagiem, np. ``pt-BR``, ``zh-Hans``).

Migracja na Anthropic (v18.x, Opcja A): silnik woła Claude Messages API
(``klient.messages.create``) zamiast OpenAI ``chat.completions``. Klient
przekazywany przez wołającego to instancja ``anthropic.Anthropic``. Tokenizer
chunkingu pozostaje tiktoken ``o200k_base`` (stała :data:`_MODEL_TOKENIZER`,
odpięta od modelu LLM) — to czysto logiczny budżet rozmiaru bloku, nie realny
tokenizer Claude'a; granice bloków bez zmian, więc bez bumpa wersji chunkowania.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import core_llm as cl
import core_tokeny as ct


# =============================================================================
# Konfiguracja modelu i limitów (Anthropic Claude — migracja v18.x, Opcja A)
# =============================================================================
# Jeden model dla głównego tłumaczenia i mikro-callu ISO (konsolidacja: koniec
# dual-providera). Domyślnie `thinking={"type":"disabled"}` — szybka proza bez
# narzutu; od 18.11 tryb quality (checkbox w GUI Poligloty) włącza extended
# thinking przez `thinking_budget` (patrz `THINKING_BUDGET_QUALITY` niżej).
MODEL_TLUMACZ = "claude-sonnet-5"

# Maks. tokenów WYJŚCIA pojedynczego bloku. Ceiling, nie target: blok wejściowy
# ma ≤ `max_tokenow_na_blok` tokenów (2 500 GUI / 4 000 docs), tłumaczenie bywa
# dłuższe dla języków rozwlekłych — 8 192 daje zapas, a pozostaje pod progiem
# non-streaming SDK (~16k → bez ryzyka HTTP-timeoutu). Przekroczenie limitu łapie
# `stop_reason == "max_tokens"` i domyka bisekcja (siatka bezpieczeństwa).
MAX_TOKENS_BLOK = 8192

# Timeout per-wywołanie (SDK Anthropic nie przyjmuje `timeout=` na `messages.create`
# — przez `with_options`). Blok ≤ 4k tokenów wejścia: 120 s z dużym zapasem.
TIMEOUT_S = 120.0

# 18.11: budżet extended thinking dla trybu quality. Gałąź Anthropic dokłada
# go PONAD `MAX_TOKENS_BLOK` (8192+4096 = 12k — wciąż pod progiem ~16k
# non-streaming SDK), więc bisekcja po `stop_reason == "max_tokens"` zachowuje
# dotychczasową semantykę (thinking nie podjada budżetu odpowiedzi). Na
# endpointach `openai_compat` parametr jest ignorowany — tryb quality bez
# efektu, zgodnie z etykietą checkboxa w GUI.
THINKING_BUDGET_QUALITY = 4096

# Tokenizer DO CHUNKINGU — celowo odpięty od modelu LLM. Claude nie używa tiktoken;
# `o200k_base` (alias `gpt-4o`) to logiczny licznik rozmiaru bloku, identyczny jak
# przed migracją (gpt-4o też był o200k_base) → granice bloków bez zmian → cache
# `temp_*.jsonl` zgodny, BEZ bumpa `_WERSJA_CHUNKOWANIA`. NIE podstawiaj tu modelu
# Claude — `kodowanie_dla_modelu` spadłby na ten sam o200k_base przez KeyError-fallback,
# ale jawna stała czyni niezmiennik widocznym dla przyszłego reviewera.
_MODEL_TOKENIZER = "gpt-4o"


# =============================================================================
# Typ wynikowy
# =============================================================================

@dataclass
class WynikTlumaczenia:
    """Zbiorczy rezultat przekazywany do GUI po zakończeniu tłumaczenia."""

    tekst: str                     # pełna, sklejona treść tłumaczenia
    iso: str                       # kod języka BCP-47 (ISO 639-1, opcjonalnie z podtagiem regionu/pisma)
    base_name: str                 # nazwa pliku wynikowego bez rozszerzenia
    jezyk_docelowy: str            # tekstowa nazwa języka (z pola GUI)
    ostrzezenia: list[str] = field(default_factory=list)   # miękkie błędy ISO itp. (techniczne, do logu)


# =============================================================================
# Mostek i18n: strukturalny sygnał błędu silnik → GUI (wzorem bledy_ai.py / v17.0)
# =============================================================================
# tlumacz_ai POZOSTAJE wolny od wxPython i i18n (moduł neutralny, woła go też
# batchowy `buduj_wielojezyczne_docs.py`). Zamiast budować polską prozę błędu,
# przekazuje GOŁĄ nazwę klucza w `ui.yaml` (namespace `poliglota.` dokłada GUI)
# plus kwargs do `t(...)` — komunikat staje się natywny w każdym z 9 języków.
# `detal` to techniczny opis po angielsku (log / dialog „szczegóły" / CLI docs);
# `__str__` go zwraca, więc `buduj_wielojezyczne_docs.py` (traktuje komunikat
# jak string: `.splitlines()`) działa bez zmian. Pusty `klucz_i18n` = błąd
# nieoczekiwany — GUI pokaże `detal` pod domyślnym nagłówkiem (do zgłoszenia).


@dataclass
class InfoBleduTlumaczenia:
    """Strukturalny sygnał błędu z silnika tłumacza (mostek i18n ↔ GUI)."""

    klucz_i18n: str                                  # goła nazwa klucza w `poliglota.` (pusta = błąd nieoczekiwany)
    detal: str = ""                                  # techniczny opis EN (log / dialog szczegółów / CLI)
    kwargs: dict[str, Any] = field(default_factory=dict)   # parametry do t(klucz, **kwargs)
    klucz_tytul: str = ""                            # opcjonalny klucz tytułu/nagłówka (soft-warning ISO)

    def __str__(self) -> str:                        # batchowy docs-autotłumacz traktuje błąd jak string
        return self.detal or self.klucz_i18n


@dataclass
class InfoPostepu:
    """Strukturalny sygnał postępu z silnika tłumacza (mostek i18n ↔ GUI).

    Bliźniak :class:`InfoBleduTlumaczenia` dla pasków postępu. `tlumacz_ai`
    pozostaje wolny od wxPython i i18n, więc zamiast budować polską prozę
    paska, przekazuje GOŁY `klucz_i18n` (namespace `poliglota.` dokłada GUI),
    kwargs do `t(...)` i `procent`. GUI renderuje natywny komunikat w języku
    interfejsu; nie-GUI konsument (CLI `buduj_wielojezyczne_docs.py`) bierze
    `str(self)` → `detal` (czytelny opis PL/EN do logu, jak przy błędach).
    Do v17.11 paski leciały surowym polskim stringiem przez `PostepCallback`,
    omijając ten mostek — user widział polszczyznę nawet przy obcym UI.
    """

    klucz_i18n: str                                  # goła nazwa klucza w `poliglota.`
    procent: int = 0                                 # 0–100 (pasek postępu)
    kwargs: dict[str, Any] = field(default_factory=dict)   # parametry do t(klucz, **kwargs)
    detal: str = ""                                  # czytelny opis dla nie-GUI (CLI/log)

    def __str__(self) -> str:                        # CLI dev-tool traktuje postęp jak string
        return self.detal or self.klucz_i18n


class BladUcietegoTlumaczenia(RuntimeError):
    """Model uciął tłumaczenie bloku (limit wyjścia) i bisekcja go nie domknęła.

    Treść (argument) zostaje po angielsku — trafia do `error_log.txt` / loga
    CLI. GUI mapuje TYP na `klucz_i18n` (`ai_blad_uciety`), więc user widzi
    komunikat natywny. Dziedziczy po `RuntimeError`, więc istniejące klauzule
    `except Exception` w pętli głównej łapią ją bez zmian.
    """

    klucz_i18n = "ai_blad_uciety"


# =============================================================================
# Callbacki
# =============================================================================
# Wszystkie callbacki są opcjonalne – gdy nie zostaną podane, moduł po prostu
# ich nie wywoła. GUI z wxPython zwykle zawija każdy callback w ``wx.CallAfter``.

PostepCallback    = Callable[[InfoPostepu], None]               # (info i18n — pasek postępu)
BladKrytyczny     = Callable[[InfoBleduTlumaczenia, str], None]  # (info i18n, częściowe tłumaczenie)
BladMiekki        = Callable[[InfoBleduTlumaczenia], None]       # (info i18n — miękki, nie przerywa)


# =============================================================================
# Prompt systemowy (literacki, zachowujący HTML/Markdown)
# =============================================================================
# Język promptu: angielski. Powód: tłumacz AI to wewnętrzne narzędzie bootstrap'owe
# uruchamiane przez autorów paczek językowych — nie jest user-facing. Angielski
# jest neutralny dla wszystkich par językowych (pl→fi, ru→is itd.) i nie wprowadza
# niepotrzebnego biasu modelu w stronę konkretnego języka źródłowego.
_PROMPT_SYSTEMOWY_TEMPLATE = (
    "# Role\n"
    "You are an expert literary and technical translator.\n\n"
    "## Task\n"
    "Translate the **entire** provided text into the following language: **{jezyk_docelowy}**.\n\n"
    "## Quality rules (mandatory)\n"
    "- The translation must be accurate, natural, and faithful to the original style.\n"
    "- Preserve paragraph structure and line breaks.\n"
    "- Render proper names and terminology according to the conventions of the target language.\n"
    "- Convey idioms and metaphors by sense, not literally.\n\n"
    "## Technical rules (critical)\n"
    "- ABSOLUTELY preserve every HTML and Markdown tag.\n"
    "- If the text contains HTML, translate ONLY the visible text content.\n"
    "- Do not add commentary, introductions, or notes of your own.\n\n"
    "## Response format\n"
    "Return ONLY the translated text."
)


def _prompt_systemowy(jezyk_docelowy: str) -> str:
    return _PROMPT_SYSTEMOWY_TEMPLATE.format(jezyk_docelowy=jezyk_docelowy)


# =============================================================================
# Podział tekstu na bloki
# =============================================================================
# Wersja algorytmu chunkowania — zapisywana w metryce pliku tymczasowego.
# Bump przy każdej zmianie podziału na bloki: cache z innym podziałem ma
# niekompatybilne indeksy i sklejony z nowymi blokami dałby tekst z dziurami.
# Wersja 2 = przejście ze znaków (10k) na tokeny (v17.2.1, issue #16).
_WERSJA_CHUNKOWANIA = 2


def _podziel_na_bloki(tekst: str, max_tokenow: int = 2_500,
                      model: str = _MODEL_TOKENIZER) -> list[str]:
    """Dzieli długi tekst na bloki ≤ ``max_tokenow`` tokenów, respektując linie.

    Do v17.2 limit liczony był w ZNAKACH (10k) — dla języków token-gęstych
    (chiński, japoński...) tłumaczenie takiego bloku potrafiło przekroczyć
    limit tokenów WYJŚCIA modelu i kończyło się bezgłośnym ucięciem
    końcówki. Tokeny tiktoken (ten sam licznik co Reżyser/Opowieści) dają
    przewidywalny rozmiar niezależnie od alfabetu. Proporcje sklejania
    ostatniego bloku odpowiadają staremu 4k/16k znaków (40% / 160% limitu).
    """
    encoder = ct.kodowanie_dla_modelu(model)

    def tokeny(fragment: str) -> int:
        return len(encoder.encode(fragment))

    akapity = tekst.split("\n")
    bloki: list[str] = []
    obecny = ""
    obecny_tok = 0
    for akapit in akapity:
        tok_akapitu = tokeny(akapit + "\n")
        if obecny_tok + tok_akapitu < max_tokenow:
            obecny += akapit + "\n"
            obecny_tok += tok_akapitu
        else:
            if obecny.strip():
                bloki.append(obecny.strip())
            obecny = akapit + "\n"
            obecny_tok = tok_akapitu
    if obecny.strip():
        bloki.append(obecny.strip())

    # Sklej ostatni krótki blok z przedostatnim (gdy się mieszczą), by uniknąć
    # marnowania jednego zapytania na kilka zdań końcowych.
    if len(bloki) > 1 and tokeny(bloki[-1]) < max_tokenow * 2 // 5:
        if tokeny(bloki[-2]) + tokeny(bloki[-1]) < max_tokenow * 8 // 5:
            bloki[-2] += "\n\n" + bloki[-1]
            bloki.pop()
    return bloki


def _podziel_blok_na_pol(blok: str) -> tuple[str, str]:
    """Dzieli blok na dwie niepuste połowy, możliwie blisko środka.

    Preferencja granic cięcia: koniec akapitu (``\\n``) → koniec zdania
    (``. ``) → twardy środek. Używane przy ponawianiu bloku, którego
    tłumaczenie zostało ucięte limitem tokenów wyjścia.
    """
    srodek = len(blok) // 2
    for separator in ("\n", ". "):
        idx = blok.rfind(separator, 0, srodek)
        if idx == -1:
            idx = blok.find(separator, srodek)
        if idx != -1:
            ciecie = idx + len(separator)
            lewa, prawa = blok[:ciecie].strip(), blok[ciecie:].strip()
            if lewa and prawa:
                return lewa, prawa
    return blok[:srodek].strip(), blok[srodek:].strip()


# =============================================================================
# Pomocnicze – nazwa pliku tymczasowego (cache wznawiania)
# =============================================================================
# Znaki zakazane w nazwach plików — UNIA cross-platform: zestaw Windows
# (`<>:"/\|?*`) + znaki sterujące. Linux/macOS zakazują tylko `/` i NUL, więc
# odsianie unii jest bezpieczne wszędzie (projekt ma dev na Linux/macOS przez
# `setup_dev.sh`/`run.sh`; zamrożony release jest Windows).
_RE_ZNAKI_ZAKAZANE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _bezpieczna_nazwa_pliku(tekst: str) -> str:
    """Sanityzuje fragment do bezpiecznej, cross-platform nazwy pliku (Unicode-safe).

    Zachowuje litery Unicode (cyrylica, CJK, diakrytyka — NTFS/ext4/APFS je
    akceptują); usuwa tylko znaki zakazane w nazwach plików i zwija białe znaki
    do ``_``.

    Do v17.11 funkcja (``_slugify_ascii``) mapowała WYŁĄCZNIE polskie znaki na
    ASCII i kasowała całą resztę (``[^a-zA-Z0-9]``). Dla nazw języków
    nie-łacińskich (np. „Русский", „中文", „العربية") slug kolapsował do pustego
    łańcucha → fallback ``"tlumaczenie"``. Skutek: tłumaczenia tego samego pliku
    źródłowego na dwa różne języki nie-łacińskie dzieliły JEDEN plik cache
    ``runtime/temp_*.jsonl`` (ta sama metryka wersja+bloki) → cache jednego
    języka był po cichu odtwarzany dla drugiego. Unicode-safe sanitizer
    eliminuje i ograniczenie „tylko PL", i tę kolizję.
    """
    oczyszczony = _RE_ZNAKI_ZAKAZANE.sub("", tekst)
    oczyszczony = re.sub(r"\s+", "_", oczyszczony.strip())
    return oczyszczony.strip("._")


def zbuduj_nazwe_bazowa(oryginalna_nazwa: str, jezyk_docelowy: str,
                        slowo_tlumaczenie: str = "tlumaczenie") -> str:
    """Zwraca nazwę pliku wynikowego (bez rozszerzenia) dla trybu Tłumacza AI.

    ``slowo_tlumaczenie`` to zlokalizowany człon nazwy (od v18.8 GUI podaje
    ``poliglota.filename_tlumaczenie`` z ``ui.yaml`` w języku UI); default
    zachowuje historyczne ``tlumaczenie`` — m.in. dla dev-toolingu
    (``buduj_wielojezyczne_*``), gdzie nazwa jest tylko kluczem cache.
    """
    slug = _bezpieczna_nazwa_pliku(jezyk_docelowy.split()[0]).lower() or "tlumaczenie"
    slowo = _bezpieczna_nazwa_pliku(slowo_tlumaczenie).lower() or "tlumaczenie"
    return f"{oryginalna_nazwa}_{slowo}_{slug}"


def _sciezka_pliku_tymczasowego(runtime_dir: str, base_name: str) -> str:
    """Zwraca ścieżkę ``runtime/temp_<base>.jsonl`` (tworzy katalog, jeśli trzeba)."""
    os.makedirs(runtime_dir, exist_ok=True)
    return os.path.join(runtime_dir, f"temp_{base_name}.jsonl")


def sciezka_cache_tlumaczenia(
    runtime_dir: str,
    oryginalna_nazwa: str,
    jezyk_docelowy: str,
    slowo_tlumaczenie: str = "tlumaczenie",
) -> str:
    """Ścieżka cache'u wznawiania dla danego tłumaczenia (18.9).

    Publiczna, bo wołający z ``zachowaj_cache=True`` musi wiedzieć, co
    posprzątać po udanym zapisie pliku wynikowego. Buduje nazwę dokładnie tak
    samo jak :func:`tlumacz_dlugi_tekst`, więc nie da się rozjechać obu miejsc.
    """
    base_name = zbuduj_nazwe_bazowa(
        oryginalna_nazwa, jezyk_docelowy, slowo_tlumaczenie)
    return _sciezka_pliku_tymczasowego(runtime_dir, base_name)


# =============================================================================
# Pobranie kodu języka docelowego (drugie, tańsze zapytanie)
# =============================================================================
# Kod języka w formacie BCP-47: 2-3-literowy kod ISO 639 + opcjonalny podtag
# regionu (2 litery) lub pisma (4 litery). Separator "_" tolerowany na wejściu,
# normalizowany do "-".
_WZORZEC_BCP47 = re.compile(r"^([A-Za-z]{2,3})(?:[-_]([A-Za-z]{2}|[A-Za-z]{4}))?$")


def normalizuj_kod_jezyka(surowy: str) -> str:
    """Waliduje i normalizuje kod języka BCP-47 (``pt-br`` → ``pt-BR``).

    Akceptuje sam kod ISO 639 (``zh`` → ``zh``) oraz podtag regionu
    (``zh-cn`` → ``zh-CN``) lub pisma (``zh_hans`` → ``zh-Hans``). Zwraca
    ``""``, gdy ciąg nie wygląda na poprawny kod — fallback wybiera
    wołający. Wspólny walidator Tłumacza AI (odpowiedź modelu) i pola
    „Kod ISO" Naprawiacza Tagów w GUI Poligloty; do v17.2 oba miejsca
    odrzucały kody regionalne (regex wycinał myślnik, pole GUI blokowało
    wpis po 2 znakach) — patrz issue #16.
    """
    kandydat = (surowy or "").strip().strip("\"'`.,;:()[]{}")
    dopasowanie = _WZORZEC_BCP47.match(kandydat)
    if not dopasowanie:
        return ""
    jezyk = dopasowanie.group(1).lower()
    podtag = dopasowanie.group(2)
    if not podtag:
        return jezyk
    if len(podtag) == 2:
        return f"{jezyk}-{podtag.upper()}"
    return f"{jezyk}-{podtag.capitalize()}"


def _pobierz_iso(klient: Any, jezyk_docelowy: str, model: str) -> tuple[str, str]:
    """Pobiera kod języka BCP-47. Zwraca (kod, surowa_odpowiedz).

    Dla zwykłych języków model zwraca dwuliterowy ISO 639-1; dla odmian
    regionalnych/pisma kod z podtagiem (``pt-BR``, ``zh-CN``, ``zh-Hans``)
    — HTML ``lang=`` i DOCX ``w:lang`` przyjmują oba formaty.
    """
    # Prompt po angielsku — spójnie z `_PROMPT_SYSTEMOWY_TEMPLATE` (narzędzie
    # bootstrap'owe, EN neutralny dla każdej pary językowej; patrz nagłówek sekcji).
    prompt = (
        f"Return ONLY the language code in BCP-47 format "
        f"for the language: {jezyk_docelowy}. "
        f"For ordinary languages return just the two-letter ISO 639-1 code, e.g.: fi, it, en. "
        f"For a regional or script variant add a subtag, e.g.: pt-BR, zh-CN, zh-Hans. "
        f"The response must contain only the code itself — no period and no comment."
    )
    surowa_raw, _stop = cl.wywolaj_llm(
        klient,
        model=model,
        system="",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=32,
        temperature=0.0,
        timeout=TIMEOUT_S,
    )
    surowa = surowa_raw.strip()
    iso = normalizuj_kod_jezyka(surowa)
    if not iso:
        return "", surowa
    return iso, surowa


# =============================================================================
# Tłumaczenie pojedynczego bloku (z bisekcją przy uciętej odpowiedzi)
# =============================================================================
def _tlumacz_blok(
    klient: Any,
    model: str,
    sys_prompt: str,
    blok: str,
    kontekst: str,
    glebokosc: int = 5,
    thinking_budget: int = 0,
) -> str:
    """Tłumaczy jeden blok; odpowiedź uciętą limitem wyjścia ponawia bisekcją.

    ``stop_reason == "max_tokens"`` oznacza, że model wyczerpał limit tokenów
    WYJŚCIA (:data:`MAX_TOKENS_BLOK`) zanim dokończył tłumaczenie. Do v17.2 taka
    odpowiedź była bezgłośnie sklejana z resztą — bug „uciętej końcówki" przy
    językach token-gęstych (issue #16). Bisekcja: blok dzielimy możliwie po
    granicy akapitu/zdania (:func:`_podziel_blok_na_pol`); lewa połowa dziedziczy
    dotychczasowy kontekst, prawa dostaje jako kontekst świeżo przetłumaczoną
    lewą (spójność terminologii).

    Anthropic rozdziela prompt systemowy (parametr ``system=``) od ``messages`` i
    NIE pozwala kończyć payloadu turą ``assistant`` (prefill = 400 na Sonnet 4.6).
    Dlatego kontekst poprzedniego bloku — w wariancie OpenAI podawany jako tura
    ``assistant`` — wkładamy do wiadomości ``user`` jako materiał referencyjny
    (oznaczony „NIE powtarzać"). ``thinking_budget`` (18.11): 0 = szybka proza
    bez reasoning (default); > 0 = tryb quality, extended thinking w gałęzi
    Anthropic (`openai_compat` ignoruje). Wyjątki sieciowe (RateLimitError
    itp.) przepuszczamy wyżej — obsługuje je pętla główna.
    """
    if kontekst:
        # Payload LLM jednojęzyczny (EN), spójnie z `_PROMPT_SYSTEMOWY_TEMPLATE`.
        # `messages` → zwinięty `user` (Anthropic, filar): poprzedni blok jako materiał
        # referencyjny „NIE powtarzać". `segmenty` → ten sam kontekst z rolą `assistant`
        # (wypowiedź modelu) + świeży tekst jako `user`, dla `openai_compat` — rozdział
        # ról sprzed v18 (Anthropic `segmenty` ignoruje).
        user_content = (
            "[CRITICAL: Continue translating the text below. Keep absolute "
            "consistency of terminology, tone and style with the already-translated "
            "preceding passage.]\n\n"
            "## Already-translated preceding passage "
            "(reference for consistency only — do NOT repeat or re-translate it):\n"
            f"{kontekst}\n\n"
            "## Text to translate now:\n"
            f"{blok}"
        )
        segmenty: list[dict] = [
            {"rola": "assistant", "content": kontekst},
            {"rola": "user", "content": (
                "[CRITICAL: Continue translating the text below. Keep absolute "
                "consistency of terminology, tone and style with your preceding "
                "translation above.]\n\n"
                "## Text to translate now:\n"
                f"{blok}"
            )},
        ]
    else:
        user_content = blok
        segmenty = [{"rola": "user", "content": blok}]

    fragment_raw, stop_reason = cl.wywolaj_llm(
        klient,
        model=model,
        system=sys_prompt,
        messages=[{"role": "user", "content": user_content}],
        max_tokens=MAX_TOKENS_BLOK,
        temperature=0.3,
        timeout=TIMEOUT_S,
        segmenty=segmenty,
        thinking_budget=thinking_budget,
    )
    fragment = fragment_raw.strip()
    if stop_reason != "max_tokens":
        return fragment

    if glebokosc <= 0:
        raise BladUcietegoTlumaczenia(
            "Output truncated (stop_reason='max_tokens'); recursive bisection "
            "depth exhausted without completing the block."
        )
    lewa, prawa = _podziel_blok_na_pol(blok)
    if not lewa or not prawa:
        raise BladUcietegoTlumaczenia(
            "Output truncated (stop_reason='max_tokens'); block can no longer "
            "be split into smaller parts."
        )
    czesc_lewa = _tlumacz_blok(klient, model, sys_prompt, lewa, kontekst,
                               glebokosc - 1, thinking_budget)
    czesc_prawa = _tlumacz_blok(klient, model, sys_prompt, prawa, czesc_lewa,
                                glebokosc - 1, thinking_budget)
    return f"{czesc_lewa}\n\n{czesc_prawa}"


# =============================================================================
# Główna pętla tłumaczenia (uruchamiana w wątku tła)
# =============================================================================
def tlumacz_dlugi_tekst(
    tresc: str,
    jezyk_docelowy: str,
    klient: Any,
    runtime_dir: str,
    oryginalna_nazwa: str,
    *,
    on_postep: PostepCallback | None = None,
    on_blad_krytyczny: BladKrytyczny | None = None,
    on_blad_miekki: BladMiekki | None = None,
    model_tlumacz: str = MODEL_TLUMACZ,
    model_iso: str = MODEL_TLUMACZ,
    max_tokenow_na_blok: int = 2_500,
    prompt_dodatkowy: str = "",
    slowo_tlumaczenie: str = "tlumaczenie",
    zachowaj_cache: bool = False,
    tryb_quality: bool = False,
) -> WynikTlumaczenia | None:
    """Tłumaczy długi tekst przez Anthropic Claude z wznawianiem po przerwaniu.

    Args:
        tresc:            Pełny tekst źródłowy do przetłumaczenia.
        jezyk_docelowy:   Nazwa języka docelowego wpisana przez użytkownika
                          (np. ``"Fiński"``, ``"Angielski"``, ``"Arabski"``).
        klient:           Zainicjowana instancja ``anthropic.Anthropic``.
        runtime_dir:      Katalog na plik tymczasowy ``temp_*.jsonl``
                          (zalecany: ``<app>/runtime``).
        oryginalna_nazwa: Nazwa pliku źródłowego bez rozszerzenia – trafia
                          do nazwy cache'u i nazwy pliku wynikowego.

    Keyword Args:
        on_postep:         Callback ``(info)`` wołany po każdym bloku, gdzie
                           ``info`` to :class:`InfoPostepu` (mostek i18n — GUI
                           mapuje ``klucz_i18n`` na natywny pasek; CLI bierze
                           ``str(info)``=detal).
        on_blad_krytyczny: Callback ``(info, partial_text)`` przy przerwaniu,
                           gdzie ``info`` to :class:`InfoBleduTlumaczenia`
                           (mostek i18n — GUI mapuje ``klucz_i18n`` na natywny
                           komunikat). Gdy użyty – funkcja zwraca ``None``.
        on_blad_miekki:    Callback ``(info)`` dla problemów z ISO (nie
                           przerywają tłumaczenia); ``info`` jak wyżej.
        model_tlumacz:     Nazwa modelu do głównego tłumaczenia.
        model_iso:         Nazwa tańszego modelu do wykrycia kodu języka.
        max_tokenow_na_blok: Rozmiar bloku (w tokenach tiktoken) przy
                           dzieleniu długiego tekstu.
        prompt_dodatkowy:  13.4. Doklejany do `_PROMPT_SYSTEMOWY_TEMPLATE` jako
                           dodatkowy kontekst projektowy — np. lista skrótowców
                           per język, wskazówki dotyczące szyfrów, polityka
                           podmiany akcentów. Pusty string = brak modyfikacji.
                           Używane przez batchowy autotłumacz dokumentacji
                           (`buduj_wielojezyczne_docs.py`); GUI Poligloty AI
                           dalej wywołuje funkcję bez tego argumentu.
        slowo_tlumaczenie: 18.8. Zlokalizowany człon nazwy pliku wynikowego
                           (GUI podaje ``poliglota.filename_tlumaczenie``
                           w języku UI, już zsanityzowany). Default zachowuje
                           historyczne ``tlumaczenie``. Uwaga: człon wchodzi
                           też do nazwy cache ``temp_*.jsonl`` — zmiana języka
                           UI między przerwanym a wznowionym tłumaczeniem
                           unieważnia cache (świadomy, rzadki koszt).
        tryb_quality:      18.11. Extended thinking dla każdego bloku
                           (``THINKING_BUDGET_QUALITY`` tokenów namysłu
                           w gałęzi Anthropic; ``openai_compat`` ignoruje).
                           Wolniej i drożej, staranniej przy trudnych
                           fragmentach. Nie zmienia podziału na bloki, więc
                           cache ``temp_*.jsonl`` pozostaje kompatybilny
                           (wznowienie może zmieszać bloki z obu trybów —
                           akceptowalne, to wciąż to samo tłumaczenie).
        zachowaj_cache:    18.9. Nie kasuj ``temp_*.jsonl`` po sukcesie —
                           dla wołających, którzy tłumaczą WIELE jednostek
                           i zapisują plik wynikowy dopiero na końcu
                           (``buduj_wielojezyczne_docs``: 68 sekcji → jeden
                           plik). Bez tego błąd sekcji 40/68 zostawiał
                           sekcje 1-39 bez cache'u i bez pliku, więc rerun
                           płacił za nie drugi raz. Wołający sprząta cache
                           sam (:func:`sciezka_cache_tlumaczenia`) po
                           faktycznym zapisie pliku.

    Returns:
        :class:`WynikTlumaczenia` po sukcesie, albo ``None`` po błędzie
        krytycznym (wtedy callback ``on_blad_krytyczny`` już został wywołany).
    """
    base_name = zbuduj_nazwe_bazowa(oryginalna_nazwa, jezyk_docelowy,
                                    slowo_tlumaczenie)
    plik_temp = _sciezka_pliku_tymczasowego(runtime_dir, base_name)

    sys_prompt = _prompt_systemowy(jezyk_docelowy)
    if prompt_dodatkowy:
        # Doklejony jako kolejna sekcja system-message — model traktuje całość
        # jako jeden blok instrukcji, więc nie ma ryzyka „I'm just an AI" itp.
        sys_prompt = sys_prompt + "\n\n" + prompt_dodatkowy
    bloki = _podziel_na_bloki(
        tresc, max_tokenow=max_tokenow_na_blok, model=_MODEL_TOKENIZER,
    )

    # -------- Odzyskanie wcześniej opłaconych bloków ----------------------
    # Pierwsza linia pliku zapisu to metryka {"meta": wersja, "bloki": n}.
    # Cache z innej wersji chunkowania (lub o innej liczbie bloków) ma
    # indeksy niekompatybilne z bieżącym podziałem — sklejenie go z nowymi
    # blokami dałoby tekst z dziurami/duplikatami, więc odrzucamy go w
    # całości i tłumaczymy od zera.
    wczytane: dict[int, str] = {}
    if os.path.exists(plik_temp):
        try:
            with open(plik_temp, "r", encoding="utf-8") as fh:
                wiersze = [json.loads(linia) for linia in fh if linia.strip()]
        except Exception as exc:  # noqa: BLE001
            if on_blad_krytyczny:
                on_blad_krytyczny(
                    InfoBleduTlumaczenia(
                        klucz_i18n="ai_blad_cache",
                        detal=f"Resume-cache read error ({plik_temp}): {exc}",
                        kwargs={"plik": plik_temp},
                    ),
                    "",
                )
            return None
        metryka = wiersze[0] if wiersze and "meta" in wiersze[0] else None
        if (
            metryka
            and metryka.get("meta") == _WERSJA_CHUNKOWANIA
            and metryka.get("bloki") == len(bloki)
        ):
            if on_postep:
                on_postep(InfoPostepu(
                    "ai_postep_odzysk", 0,
                    detal="Wykryto plik zapisu – odtwarzanie opłaconego postępu…",
                ))
            wczytane = {dane["id"]: dane["text"] for dane in wiersze[1:]}
        else:
            try:
                os.remove(plik_temp)
            except Exception:  # noqa: BLE001
                pass

    if not os.path.exists(plik_temp):
        with open(plik_temp, "w", encoding="utf-8") as fh:
            fh.write(
                json.dumps({"meta": _WERSJA_CHUNKOWANIA, "bloki": len(bloki)})
                + "\n"
            )

    # -------- Właściwe tłumaczenie ---------------------------------------
    n = len(bloki)
    for i, blok in enumerate(bloki):
        if i in wczytane:
            if on_postep:
                on_postep(InfoPostepu(
                    "ai_postep_blok_odzyskany", int((i + 1) / n * 100),
                    kwargs={"numer": i + 1, "ile": n},
                    detal=f"Blok {i + 1}/{n} odzyskany z pliku zapisu.",
                ))
            continue

        if on_postep:
            on_postep(InfoPostepu(
                "ai_postep_blok", int(i / n * 100),
                kwargs={"numer": i + 1, "ile": n, "znaki": len(blok)},
                detal=f"Tłumaczenie bloku {i + 1} z {n}… ({len(blok)} znaków)",
            ))

        kontekst = wczytane.get(i - 1, "") if i > 0 else ""

        try:
            fragment = _tlumacz_blok(
                klient, model_tlumacz, sys_prompt, blok, kontekst,
                thinking_budget=THINKING_BUDGET_QUALITY if tryb_quality else 0,
            )
            wczytane[i] = fragment
            with open(plik_temp, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": i, "text": fragment}, ensure_ascii=False) + "\n")

        except cl.BladLimituLLM:
            partial = "\n\n".join(wczytane[k] for k in sorted(wczytane))
            if on_blad_krytyczny:
                on_blad_krytyczny(
                    InfoBleduTlumaczenia(
                        klucz_i18n="ai_blad_limit_api",
                        detal=f"RateLimitError on block {i + 1}/{n} (out of credits or rate limit).",
                        kwargs={"blok": i + 1},
                    ),
                    partial,
                )
            return None
        except BladUcietegoTlumaczenia as exc:
            partial = "\n\n".join(wczytane[k] for k in sorted(wczytane))
            if on_blad_krytyczny:
                on_blad_krytyczny(
                    InfoBleduTlumaczenia(klucz_i18n=exc.klucz_i18n, detal=str(exc)),
                    partial,
                )
            return None
        except Exception as exc:  # noqa: BLE001
            # Błąd nieoczekiwany — pusty klucz: GUI pokaże techniczny `detal`
            # pod domyślnym nagłówkiem (do skopiowania / zgłoszenia jako issue).
            partial = "\n\n".join(wczytane[k] for k in sorted(wczytane))
            if on_blad_krytyczny:
                on_blad_krytyczny(
                    InfoBleduTlumaczenia(klucz_i18n="", detal=str(exc)),
                    partial,
                )
            return None

    # -------- Pobranie kodu ISO -----------------------------------------
    if on_postep:
        on_postep(InfoPostepu(
            "ai_postep_iso", 95,
            detal="Generowanie tagu językowego dla czytników ekranu…",
        ))

    ostrzezenia: list[str] = []
    iso_code = "pl"

    def _ostrzezenie_iso(szczegoly: str, detal: str) -> None:
        """Rejestruje miękkie ostrzeżenie ISO (struktura i18n + techniczny log)."""
        ostrzezenia.append(detal)
        if on_blad_miekki:
            on_blad_miekki(InfoBleduTlumaczenia(
                klucz_i18n="ai_ostrzezenie_iso",
                detal=detal,
                kwargs={"szczegoly": szczegoly},
                klucz_tytul="ai_ostrzezenie_iso_tytul",
            ))

    try:
        iso_code_pobrany, surowa = _pobierz_iso(klient, jezyk_docelowy, model_iso)
        if iso_code_pobrany:
            iso_code = iso_code_pobrany
        else:
            _ostrzezenie_iso(
                surowa,
                f"ISO autodetect returned no valid code; defaulted to 'pl'. "
                f"Model response: {surowa}",
            )
    except Exception as iso_exc:  # noqa: BLE001
        _ostrzezenie_iso(
            str(iso_exc),
            f"ISO autodetect raised an exception; defaulted to 'pl'. "
            f"Details: {iso_exc}",
        )

    # -------- Posprzątanie cache'u i złożenie wyniku --------------------
    # `zachowaj_cache` = wołający zapisuje plik wynikowy dopiero po wielu
    # jednostkach i sam skasuje cache po udanym zapisie (patrz docstring).
    if not zachowaj_cache and os.path.exists(plik_temp):
        try:
            os.remove(plik_temp)
        except Exception:   # noqa: BLE001
            pass

    if on_postep:
        on_postep(InfoPostepu(
            "ai_postep_zapis", 99,
            detal="Zapis pliku wynikowego…",
        ))

    tekst_wynikowy = "\n\n".join(wczytane[k] for k in sorted(wczytane)).strip()

    return WynikTlumaczenia(
        tekst=tekst_wynikowy,
        iso=iso_code,
        base_name=base_name,
        jezyk_docelowy=jezyk_docelowy,
        ostrzezenia=ostrzezenia,
    )
