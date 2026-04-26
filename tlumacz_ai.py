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
  1. Tekst dzielony jest na bloki po maksymalnie ``max_znakow_na_blok`` znaków,
     z zachowaniem podziału na akapity (``\\n``).
  2. Jeśli ostatni blok jest krótki, sklejany jest z przedostatnim.
  3. Dla każdego bloku wysyłane jest zapytanie ``chat.completions`` do modelu
     ``model_tlumacz``. Ostatni tłumaczony blok podawany jest jako kontekst
     do kolejnego wywołania – dzięki temu model trzyma spójną terminologię.
  4. Po każdym udanym bloku treść dopisywana jest do pliku tymczasowego
     ``runtime/temp_<nazwa_bazowa>.jsonl``. Jeśli użytkownik przerwie
     tłumaczenie i ponownie je uruchomi z tym samym plikiem źródłowym,
     gotowe bloki są odtwarzane z tego pliku (oszczędność kredytów API).
  5. Na końcu wywoływana jest druga, tania konsultacja (``model_iso``)
     w celu ustalenia dwuliterowego kodu ISO języka docelowego.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable


# =============================================================================
# Typ wynikowy
# =============================================================================

@dataclass
class WynikTlumaczenia:
    """Zbiorczy rezultat przekazywany do GUI po zakończeniu tłumaczenia."""

    tekst: str                     # pełna, sklejona treść tłumaczenia
    iso: str                       # kod ISO 639-1 języka docelowego
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
def _podziel_na_bloki(tekst: str, max_znakow: int = 10_000) -> list[str]:
    """Dzieli długi tekst na bloki ≤ ``max_znakow`` znaków, respektując linie."""
    akapity = tekst.split("\n")
    bloki: list[str] = []
    obecny = ""
    for akapit in akapity:
        if len(obecny) + len(akapit) < max_znakow:
            obecny += akapit + "\n"
        else:
            if obecny.strip():
                bloki.append(obecny.strip())
            obecny = akapit + "\n"
    if obecny.strip():
        bloki.append(obecny.strip())

    # Sklej ostatni krótki blok z przedostatnim (gdy się mieszczą), by uniknąć
    # marnowania jednego zapytania na kilka zdań końcowych.
    if len(bloki) > 1 and len(bloki[-1]) < 4_000:
        if len(bloki[-2]) + len(bloki[-1]) < 16_000:
            bloki[-2] += "\n\n" + bloki[-1]
            bloki.pop()
    return bloki


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
# Pobranie kodu ISO docelowego (drugie, tańsze zapytanie)
# =============================================================================
def _pobierz_iso(klient: Any, jezyk_docelowy: str, model: str) -> tuple[str, str]:
    """Pobiera kod ISO 639-1 dla podanego języka. Zwraca (iso, surowa_odpowiedz)."""
    prompt = (
        f"Podaj WYŁĄCZNIE dwuliterowy kod języka ISO 639-1 "
        f"dla języka: {jezyk_docelowy}. "
        f"Odpowiedź musi zawierać tylko dwuliterowy kod, np.: fi, it, en."
    )
    resp = klient.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    surowa = (resp.choices[0].message.content or "").strip()
    iso = re.sub(r"[^a-z]", "", surowa.lower())
    if not iso or len(iso) > 3:
        return "", surowa
    return iso, surowa


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
    max_znakow_na_blok: int = 10_000,
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
        model_iso:         Nazwa tańszego modelu do wykrycia kodu ISO.
        max_znakow_na_blok: Rozmiar bloku przy dzieleniu długiego tekstu.
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
    bloki = _podziel_na_bloki(tresc, max_znakow=max_znakow_na_blok)

    # -------- Odzyskanie wcześniej opłaconych bloków ----------------------
    wczytane: dict[int, str] = {}
    if os.path.exists(plik_temp):
        if on_postep:
            on_postep("Wykryto plik zapisu – odtwarzanie opłaconego postępu…", 0)
        try:
            with open(plik_temp, "r", encoding="utf-8") as fh:
                for linia in fh:
                    if linia.strip():
                        dane = json.loads(linia)
                        wczytane[dane["id"]] = dane["text"]
        except Exception as exc:  # noqa: BLE001
            if on_blad_krytyczny:
                on_blad_krytyczny(
                    f"Błąd odczytu pliku tymczasowego ({plik_temp}):\n{exc}",
                    "",
                )
            return None

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

        payload: list[dict[str, str]] = [{"role": "system", "content": sys_prompt}]
        if i > 0 and (i - 1) in wczytane:
            payload.append({"role": "assistant", "content": wczytane[i - 1]})
            user_content = (
                "[KRYTYCZNE: Kontynuuj tłumaczenie poniższego tekstu. "
                "Zachowaj absolutną spójność terminologii, tonu i stylu "
                "z Twoją poprzednią odpowiedzią.]\n\n" + blok
            )
        else:
            user_content = blok
        payload.append({"role": "user", "content": user_content})

        try:
            response = klient.chat.completions.create(
                model=model_tlumacz,
                messages=payload,
                temperature=0.3,
            )
            fragment = (response.choices[0].message.content or "").strip()
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
