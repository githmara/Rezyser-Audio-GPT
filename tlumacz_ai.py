"""
tlumacz_ai.py – Silnik tłumaczenia OpenAI GPT-4o (moduł pomocniczy Poligloty).

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
  3. Dla każdego bloku wysyłane jest zapytanie ``chat.completions`` do modelu
     ``model_tlumacz``. Ostatni tłumaczony blok podawany jest jako kontekst
     do kolejnego wywołania – dzięki temu model trzyma spójną terminologię.
     Odpowiedź ucięta limitem wyjścia (``finish_reason == "length"``) NIE
     jest akceptowana — blok jest dzielony na pół i tłumaczony rekurencyjnie
     (:func:`_tlumacz_blok`), zamiast bezgłośnie gubić końcówkę tekstu.
  4. Po każdym udanym bloku treść dopisywana jest do pliku tymczasowego
     ``runtime/temp_<nazwa_bazowa>.jsonl``. Jeśli użytkownik przerwie
     tłumaczenie i ponownie je uruchomi z tym samym plikiem źródłowym,
     gotowe bloki są odtwarzane z tego pliku (oszczędność kredytów API).
     Pierwsza linia pliku to metryka zgodności (wersja chunkowania +
     liczba bloków) — cache z innego podziału jest odrzucany w całości.
  5. Na końcu wywoływana jest druga, tania konsultacja (``model_iso``)
     w celu ustalenia kodu języka BCP-47 (dwuliterowy ISO 639-1,
     dla odmian regionalnych/pisma z podtagiem, np. ``pt-BR``, ``zh-Hans``).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import core_tokeny as ct


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
    ostrzezenia: list[str] = field(default_factory=list)   # miękkie błędy ISO itp.


# =============================================================================
# Callbacki
# =============================================================================
# Wszystkie callbacki są opcjonalne – gdy nie zostaną podane, moduł po prostu
# ich nie wywoła. GUI z wxPython zwykle zawija każdy callback w ``wx.CallAfter``.

PostepCallback    = Callable[[str, int], None]   # (komunikat, procent 0–100)
BladKrytyczny     = Callable[[str, str], None]   # (pełna treść błędu, częściowe tłumaczenie)
BladMiekki        = Callable[[str, str], None]   # (szczegóły, tytuł dialogu)


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
                      model: str = "gpt-4o") -> list[str]:
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
def _slugify_ascii(tekst: str) -> str:
    """Prosty slugifier ASCII (usuwa polskie znaki, spacje → puste)."""
    mapa = {
        "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n",
        "ó": "o", "ś": "s", "ź": "z", "ż": "z",
        "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N",
        "Ó": "O", "Ś": "S", "Ź": "Z", "Ż": "Z",
    }
    for k, v in mapa.items():
        tekst = tekst.replace(k, v)
    return re.sub(r"[^a-zA-Z0-9]", "", tekst)


def zbuduj_nazwe_bazowa(oryginalna_nazwa: str, jezyk_docelowy: str) -> str:
    """Zwraca nazwę pliku wynikowego (bez rozszerzenia) dla trybu Tłumacza AI."""
    slug = _slugify_ascii(jezyk_docelowy.split()[0]).lower() or "tlumaczenie"
    return f"{oryginalna_nazwa}_tlumaczenie_{slug}"


def _sciezka_pliku_tymczasowego(runtime_dir: str, base_name: str) -> str:
    """Zwraca ścieżkę ``runtime/temp_<base>.jsonl`` (tworzy katalog, jeśli trzeba)."""
    os.makedirs(runtime_dir, exist_ok=True)
    return os.path.join(runtime_dir, f"temp_{base_name}.jsonl")


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
    prompt = (
        f"Podaj WYŁĄCZNIE kod języka w formacie BCP-47 "
        f"dla języka: {jezyk_docelowy}. "
        f"Dla zwykłych języków zwróć sam dwuliterowy kod ISO 639-1, np.: fi, it, en. "
        f"Dla odmiany regionalnej lub odmiany pisma dodaj podtag, np.: pt-BR, zh-CN, zh-Hans. "
        f"Odpowiedź ma zawierać wyłącznie sam kod — bez kropki i bez komentarza."
    )
    resp = klient.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    surowa = (resp.choices[0].message.content or "").strip()
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
) -> str:
    """Tłumaczy jeden blok; odpowiedź uciętą limitem wyjścia ponawia bisekcją.

    ``finish_reason == "length"`` oznacza, że model wyczerpał limit tokenów
    WYJŚCIA zanim dokończył tłumaczenie. Do v17.2 taka odpowiedź była
    bezgłośnie sklejana z resztą — bug „uciętej końcówki" przy językach
    token-gęstych (issue #16). Bisekcja: blok dzielimy możliwie po granicy
    akapitu/zdania (:func:`_podziel_blok_na_pol`); lewa połowa dziedziczy
    dotychczasowy kontekst, prawa dostaje jako kontekst świeżo
    przetłumaczoną lewą (spójność terminologii). Wyjątki sieciowe
    (RateLimitError itp.) przepuszczamy wyżej — obsługuje je pętla główna.
    """
    payload: list[dict[str, str]] = [{"role": "system", "content": sys_prompt}]
    if kontekst:
        payload.append({"role": "assistant", "content": kontekst})
        user_content = (
            "[KRYTYCZNE: Kontynuuj tłumaczenie poniższego tekstu. "
            "Zachowaj absolutną spójność terminologii, tonu i stylu "
            "z Twoją poprzednią odpowiedzią.]\n\n" + blok
        )
    else:
        user_content = blok
    payload.append({"role": "user", "content": user_content})

    response = klient.chat.completions.create(
        model=model,
        messages=payload,
        temperature=0.3,
    )
    wybor = response.choices[0]
    fragment = (wybor.message.content or "").strip()
    if getattr(wybor, "finish_reason", "") != "length":
        return fragment

    if glebokosc <= 0:
        raise RuntimeError(
            "Model uciął tłumaczenie bloku (limit tokenów wyjścia) i nie udało "
            "się go dokończyć mimo wielokrotnego podziału na mniejsze części. "
            "Podziel plik źródłowy na mniejsze fragmenty i spróbuj ponownie."
        )
    lewa, prawa = _podziel_blok_na_pol(blok)
    if not lewa or not prawa:
        raise RuntimeError(
            "Model uciął tłumaczenie bloku (limit tokenów wyjścia), a bloku "
            "nie da się już podzielić na mniejsze części. Podziel plik "
            "źródłowy na mniejsze fragmenty i spróbuj ponownie."
        )
    czesc_lewa = _tlumacz_blok(klient, model, sys_prompt, lewa, kontekst, glebokosc - 1)
    czesc_prawa = _tlumacz_blok(klient, model, sys_prompt, prawa, czesc_lewa, glebokosc - 1)
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
    model_tlumacz: str = "gpt-4o",
    model_iso: str = "gpt-4o-mini",
    max_tokenow_na_blok: int = 2_500,
    prompt_dodatkowy: str = "",
) -> WynikTlumaczenia | None:
    """Tłumaczy długi tekst przez OpenAI z wznawianiem po przerwaniu.

    Args:
        tresc:            Pełny tekst źródłowy do przetłumaczenia.
        jezyk_docelowy:   Nazwa języka docelowego wpisana przez użytkownika
                          (np. ``"Fiński"``, ``"Angielski"``, ``"Arabski"``).
        klient:           Zainicjowana instancja ``openai.OpenAI``.
        runtime_dir:      Katalog na plik tymczasowy ``temp_*.jsonl``
                          (zalecany: ``<app>/runtime``).
        oryginalna_nazwa: Nazwa pliku źródłowego bez rozszerzenia – trafia
                          do nazwy cache'u i nazwy pliku wynikowego.

    Keyword Args:
        on_postep:         Callback ``(msg, procent)`` wołany po każdym bloku.
        on_blad_krytyczny: Callback ``(msg, partial_text)`` przy przerwaniu.
                           Gdy użyty – funkcja zwraca ``None``.
        on_blad_miekki:    Callback ``(msg, tytul)`` dla problemów z ISO
                           (nie przerywają tłumaczenia).
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

    Returns:
        :class:`WynikTlumaczenia` po sukcesie, albo ``None`` po błędzie
        krytycznym (wtedy callback ``on_blad_krytyczny`` już został wywołany).
    """
    # Import openai wewnątrz funkcji – odciąża moduł przy testach jednostkowych
    import openai

    base_name = zbuduj_nazwe_bazowa(oryginalna_nazwa, jezyk_docelowy)
    plik_temp = _sciezka_pliku_tymczasowego(runtime_dir, base_name)

    sys_prompt = _prompt_systemowy(jezyk_docelowy)
    if prompt_dodatkowy:
        # Doklejony jako kolejna sekcja system-message — model traktuje całość
        # jako jeden blok instrukcji, więc nie ma ryzyka „I'm just an AI" itp.
        sys_prompt = sys_prompt + "\n\n" + prompt_dodatkowy
    bloki = _podziel_na_bloki(
        tresc, max_tokenow=max_tokenow_na_blok, model=model_tlumacz,
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
                    f"Błąd odczytu pliku tymczasowego ({plik_temp}):\n{exc}",
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
                on_postep("Wykryto plik zapisu – odtwarzanie opłaconego postępu…", 0)
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
                on_postep(f"Blok {i + 1}/{n} odzyskany z pliku zapisu.",
                          int((i + 1) / n * 100))
            continue

        if on_postep:
            on_postep(
                f"Tłumaczenie bloku {i + 1} z {n}… ({len(blok)} znaków)",
                int(i / n * 100),
            )

        kontekst = wczytane.get(i - 1, "") if i > 0 else ""

        try:
            fragment = _tlumacz_blok(
                klient, model_tlumacz, sys_prompt, blok, kontekst,
            )
            wczytane[i] = fragment
            with open(plik_temp, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": i, "text": fragment}, ensure_ascii=False) + "\n")

        except openai.RateLimitError:
            partial = "\n\n".join(wczytane[k] for k in sorted(wczytane))
            if on_blad_krytyczny:
                on_blad_krytyczny(
                    f"BRAK ŚRODKÓW LUB LIMIT API! Przerwano na bloku {i + 1}.\n\n"
                    "Postęp został automatycznie zabezpieczony.\n"
                    "Zasil konto API i wczytaj oryginał ponownie, "
                    "by kontynuować od tego miejsca.",
                    partial,
                )
            return None
        except Exception as exc:  # noqa: BLE001
            partial = "\n\n".join(wczytane[k] for k in sorted(wczytane))
            if on_blad_krytyczny:
                on_blad_krytyczny(str(exc), partial)
            return None

    # -------- Pobranie kodu ISO -----------------------------------------
    if on_postep:
        on_postep("Generowanie tagu językowego dla czytników ekranu…", 95)

    ostrzezenia: list[str] = []
    iso_code = "pl"
    try:
        iso_code_pobrany, surowa = _pobierz_iso(klient, jezyk_docelowy, model_iso)
        if iso_code_pobrany:
            iso_code = iso_code_pobrany
        else:
            komunikat = (
                "Nie udało się automatycznie pobrać kodu ISO z API. "
                "Użyto domyślnego tagu 'pl'. W razie problemów z czytnikiem ekranu, "
                "użyj 'Naprawiacza Tagów' w Trybie Reżysera.\n\n"
                f"Odpowiedź modelu: {surowa}"
            )
            ostrzezenia.append(komunikat)
            if on_blad_miekki:
                on_blad_miekki(komunikat, "Ostrzeżenie tagu językowego")
    except Exception as iso_exc:  # noqa: BLE001
        komunikat = (
            "Nie udało się automatycznie pobrać kodu ISO z API. "
            "Użyto domyślnego tagu 'pl'. W razie problemów z czytnikiem ekranu, "
            "użyj 'Naprawiacza Tagów' w Trybie Reżysera.\n\n"
            f"Szczegóły błędu: {iso_exc}"
        )
        ostrzezenia.append(komunikat)
        if on_blad_miekki:
            on_blad_miekki(komunikat, "Ostrzeżenie tagu językowego")

    # -------- Posprzątanie cache'u i złożenie wyniku --------------------
    if os.path.exists(plik_temp):
        try:
            os.remove(plik_temp)
        except Exception:   # noqa: BLE001
            pass

    if on_postep:
        on_postep("Zapis pliku wynikowego…", 99)

    tekst_wynikowy = "\n\n".join(wczytane[k] for k in sorted(wczytane)).strip()

    return WynikTlumaczenia(
        tekst=tekst_wynikowy,
        iso=iso_code,
        base_name=base_name,
        jezyk_docelowy=jezyk_docelowy,
        ostrzezenia=ostrzezenia,
    )
