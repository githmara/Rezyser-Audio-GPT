"""
przepisy_rezysera.py – Loader „przepisów twórczych" modułu Reżyser Audio GPT.

Czym jest przepis?
    Zestaw danych opisujący JEDEN tryb pracy AI (Burza Mózgów / Skrypt /
    Audiobook) lub JEDNO narzędzie postprodukcyjne (np. nadawanie tytułów
    rozdziałom). Wszystko jest zapisane w plikach YAML w folderze
    ``dictionaries/<jezyk>/rezyser/``.

Dlaczego osobny plik?
    Historycznie prompty systemowe reżysera były zakute na sztywno w klasie
    ``RezyserPanel`` (``gui_rezyser.py``). Każda modyfikacja wymagała pracy
    programisty i budowania nowego release'u. Po refaktorze z wersji 13.0
    lingwista może:

      * zmienić język odpowiedzi (``jezyk_odpowiedzi: angielsku``),
      * osłabić lub wzmocnić Anti-Closure w trybie Audiobook,
      * podmienić model (``gpt-4o`` → ``gpt-4o-mini``) punktowo,
      * dodać zupełnie nowy tryb (np. ``tryb_poezja.yaml``) bez dotykania
        kodu Pythona – wystarczy nowy YAML i restart aplikacji.

Publiczne API (używane przez ``rezyser_ai.py`` i ``gui_rezyser.py``):

    import przepisy_rezysera as pr

    # Lista trybów do wypełnienia RadioBox w GUI:
    tryby = pr.lista_trybow(jezyk="pl")          # [PrzepisRezysera, ...]

    # Pojedynczy przepis po id:
    przepis = pr.zaladuj_przepis("audiobook")     # PrzepisRezysera | None
    postprod = pr.zaladuj_przepis("tytuly", kategoria="postprodukcja")

    # Zbudowanie końcowego prompt systemowego (podstawia {world_context}
    # i {jezyk_odpowiedzi} w szablonie z YAML-a):
    sys_prompt = pr.buduj_prompt_systemowy(przepis, world_context="...")

    # Zbudowanie sufiksu kontekstowego (np. "alarm" dla Burzy):
    sufiks = pr.buduj_sufiks(przepis, "alarm")

    # Zbudowanie przypomnienia doklejanego do treści użytkownika:
    przypom = pr.buduj_przypomnienie(przepis)

Moduł NIE zależy od wxPython ani od OpenAI – to czysty loader danych.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml


# =============================================================================
# Ścieżki i stałe
# =============================================================================
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DICTIONARIES_DIR = os.path.join(_ROOT_DIR, "dictionaries")

# Podfolder w ``dictionaries/<jezyk>/`` w którym trzymane są przepisy reżysera.
FOLDER_REZYSER = "rezyser"

# Kategorie przepisów. Lingwista może tworzyć własne (np. „scenariusz"),
# ale silnik domyślnie rozumie tylko te dwie.
KATEGORIA_TRYB = "tryb"
KATEGORIA_POSTPROD = "postprodukcja"


# -----------------------------------------------------------------------------
# Detekcja odrzucenia przez AI – niezależna od języka odpowiedzi
# -----------------------------------------------------------------------------
# Historia: pierwotnie utrzymywaliśmy listę fraz ("as an ai", "nie mogę...")
# w każdym YAML-u trybu zapisu. Gdy lingwista zmieniał `jezyk_odpowiedzi`
# na np. fiński, te frazy przestawały pasować i odmowa modelu mogła
# przedostać się do pliku historii.
#
# Rozwiązanie (od wersji 13.0): wymuszamy na modelu zwrócenie jednego,
# niezmiennego tagu (``[ODRZUCENIE_AI]``) — nawet gdy cała reszta
# odpowiedzi byłaby w obcym języku. Klauzula systemowa poniżej jest
# celowo po angielsku: GPT-4/4o traktuje angielskie "SYSTEM RULE"
# nadal z wyższym priorytetem niż treści w języku użytkownika.
TAG_ODRZUCENIA_AI = "[ODRZUCENIE_AI]"

KLAUZULA_ODRZUCENIA_DOMYSLNA = (
    "\n\n---\n"
    "SYSTEM RULE (do not translate, do not rephrase, do not localize):\n"
    "If you CANNOT or WILL NOT fulfill the request for ANY reason "
    "(safety policy, ethical refusal, content filters, missing information, "
    "ambiguity), respond with EXACTLY this ONE LINE and NOTHING else:\n"
    f"{TAG_ODRZUCENIA_AI}\n"
    "Do not translate the tag. Do not add apologies before or after it. "
    "Do not continue the scene. This tag is an infrastructure marker for "
    "the application – it must appear verbatim, in the Latin alphabet, "
    "regardless of the user's language of choice."
)


# =============================================================================
# Model danych
# =============================================================================
@dataclass
class PrzepisRezysera:
    """Pojedynczy przepis twórczy załadowany z YAML-a.

    Pola wspólne są zawsze wypełnione. Pola specyficzne (np. ``sufiksy``
    albo ``regex_podzial_rozdzialow``) mają sensowne wartości domyślne —
    dzięki temu YAML lingwisty może je po prostu pomijać, jeśli nie są
    mu potrzebne.

    Attributes:
        id:               Unikalny identyfikator (np. ``"audiobook"``).
        etykieta:         Tekst wyświetlany w RadioBox / menu GUI.
        kategoria:        ``"tryb"`` lub ``"postprodukcja"``.
        kolejnosc:        Sortowanie wyświetlania (rosnąco).
        model:            Nazwa modelu OpenAI (np. ``"gpt-4o"``).
        temperatura:      Parametr ``temperature`` wywołania API.
        jezyk_odpowiedzi: Rzeczownik w miejscowniku (``"polsku"``,
                          ``"angielsku"``) wstawiany jako placeholder
                          ``{jezyk_odpowiedzi}`` w promptach.
        prompt_systemowy: Główny prompt z ``role=system``. Może używać
                          placeholderów ``{world_context}``,
                          ``{jezyk_odpowiedzi}``.
        zapis_do_pliku:   (tylko tryb) True → odpowiedź trafia do
                          ``skrypty/<nazwa>.txt``.
        stosuj_akcenty_fonetyczne:
                          (tylko tryb) True → odpowiedź przechodzi przez
                          silnik akcentów (``core_poliglota.akcent_*``).
        przypomnienie_uzytkownika:
                          (tylko tryb) Tekst doklejany do treści
                          ``role=user`` tuż przed wysłaniem.
        sufiksy:          (tylko tryb) Mapa ``nazwa → tekst`` doklejana
                          do ``prompt_systemowy`` w zależności od stanu
                          pamięci / słów w instrukcji użytkownika.
                          Typowe nazwy: ``startowy``, ``kontynuacja``,
                          ``streszczenie``, ``alarm``, ``optymalizacja``.
        slowa_wyzwalajace:
                          (tylko tryb) Mapa ``kategoria → lista słów``.
                          ``streszczenie`` – słowa powodujące doklejenie
                          sufiksu ``streszczenie`` (Burza) lub blokadę
                          wysłania (Skrypt/Audiobook).
                          Detekcja odrzucenia przez AI NIE używa już tej
                          mapy – zastąpiono ją uniwersalnym tagiem
                          ``[ODRZUCENIE_AI]`` (patrz ``wykryto_odrzucenie``),
                          niezależnym od ``jezyk_odpowiedzi``.
        klauzula_odrzucenia:
                          Opcjonalna klauzula systemowa wymuszająca na AI
                          zwrócenie tagu ``[ODRZUCENIE_AI]`` przy odmowie.
                          Pusta wartość (domyślnie) = używaj wbudowanej
                          ``KLAUZULA_ODRZUCENIA_DOMYSLNA``. Pole istnieje
                          głównie po to, by lingwista-eksperymentator mógł
                          przetestować własne sformułowanie (np. bardziej
                          kategoryczne lub po fińsku) bez zmian w kodzie.
        prompt_uzytkownika_szablon:
                          (tylko postprodukcja) Szablon ``role=user``
                          z placeholderami takimi jak ``{naglowek}``,
                          ``{probka}``.
        regex_podzial_rozdzialow:
                          (tylko postprodukcja tytułów) Regex dzielący
                          plik projektu na nagłówki + treści.
        min_dlugosc_fragmentu:
                          (tylko postprodukcja) Fragmenty krótsze → skip.
        max_dlugosc_probki:
                          (tylko postprodukcja) Ile znaków próbki
                          przekazujemy modelowi z każdego rozdziału.
        etykieta_fragment_zbyt_krotki:
                          (tylko postprodukcja) Napis zastępczy gdy
                          rozdział jest za krótki by generować tytuł.
        etykieta_bled_brak_kredytow:
                          (tylko postprodukcja) Napis przy ``RateLimitError``.
    """

    # --- Wspólne ---
    id: str
    etykieta: str
    kategoria: str
    kolejnosc: int = 0
    model: str = "gpt-4o"
    temperatura: float = 0.85
    jezyk_odpowiedzi: str = "polsku"
    prompt_systemowy: str = ""

    # --- Tryb ---
    zapis_do_pliku: bool = False
    stosuj_akcenty_fonetyczne: bool = False
    przypomnienie_uzytkownika: str = ""
    sufiksy: dict[str, str] = field(default_factory=dict)
    slowa_wyzwalajace: dict[str, list[str]] = field(default_factory=dict)
    klauzula_odrzucenia: str = ""   # "" = użyj KLAUZULA_ODRZUCENIA_DOMYSLNA

    # --- Postprodukcja ---
    prompt_uzytkownika_szablon: str = ""
    regex_podzial_rozdzialow: str = ""
    min_dlugosc_fragmentu: int = 0
    max_dlugosc_probki: int = 0
    etykieta_fragment_zbyt_krotki: str = ""
    etykieta_bled_brak_kredytow: str = ""


# =============================================================================
# Cache wczytanych przepisów
# =============================================================================
# Klucz: język ("pl"). Wartość: lista przepisów w kolejności z dysku.
# yaml.safe_load zwraca świeży dict przy każdym wywołaniu, więc cache jest
# bezpieczny dla wielu wątków (nie modyfikujemy zawartości po wczytaniu).
_CACHE_PRZEPISOW: dict[str, list[PrzepisRezysera]] = {}


# =============================================================================
# Wczytywanie YAML-i
# =============================================================================
def _yaml_to_przepis(data: dict, sciezka: str) -> PrzepisRezysera | None:
    """Konwertuje słownik z YAML na :class:`PrzepisRezysera`.

    Zwraca ``None`` dla YAML-i bez wymaganych pól (``id``, ``etykieta``,
    ``kategoria``) lub dla YAML-i technicznych (``kategoria: oczyszczenie``),
    których nie chcemy pokazywać w liście trybów.
    """
    if not isinstance(data, dict):
        return None

    id_ = data.get("id")
    etykieta = data.get("etykieta")
    kategoria = data.get("kategoria")
    if not id_ or not etykieta or not kategoria:
        return None

    # Pomijamy kategorie pomocnicze, które mogłyby wylądować w tym samym
    # folderze przez pomyłkę (np. cudze YAML-e).
    if kategoria not in (KATEGORIA_TRYB, KATEGORIA_POSTPROD):
        return None

    return PrzepisRezysera(
        id=str(id_),
        etykieta=str(etykieta),
        kategoria=str(kategoria),
        kolejnosc=int(data.get("kolejnosc", 0)),
        model=str(data.get("model", "gpt-4o")),
        temperatura=float(data.get("temperatura", 0.85)),
        jezyk_odpowiedzi=str(data.get("jezyk_odpowiedzi", "polsku")),
        prompt_systemowy=str(data.get("prompt_systemowy", "")),
        zapis_do_pliku=bool(data.get("zapis_do_pliku", False)),
        stosuj_akcenty_fonetyczne=bool(data.get("stosuj_akcenty_fonetyczne", False)),
        przypomnienie_uzytkownika=str(data.get("przypomnienie_uzytkownika", "")),
        sufiksy={k: str(v) for k, v in (data.get("sufiksy") or {}).items()},
        slowa_wyzwalajace={
            k: [str(x) for x in (v or [])]
            for k, v in (data.get("slowa_wyzwalajace") or {}).items()
        },
        klauzula_odrzucenia=str(data.get("klauzula_odrzucenia", "")),
        prompt_uzytkownika_szablon=str(data.get("prompt_uzytkownika_szablon", "")),
        regex_podzial_rozdzialow=str(data.get("regex_podzial_rozdzialow", "")),
        min_dlugosc_fragmentu=int(data.get("min_dlugosc_fragmentu", 0)),
        max_dlugosc_probki=int(data.get("max_dlugosc_probki", 0)),
        etykieta_fragment_zbyt_krotki=str(
            data.get("etykieta_fragment_zbyt_krotki", "")),
        etykieta_bled_brak_kredytow=str(
            data.get("etykieta_bled_brak_kredytow", "")),
    )


def _wczytaj_yaml(sciezka: str) -> dict:
    """Bezpiecznie wczytuje plik YAML (zwraca pusty dict przy błędzie)."""
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _zaladuj_wszystkie(jezyk: str) -> list[PrzepisRezysera]:
    """Skanuje ``dictionaries/<jezyk>/rezyser/*.yaml`` i cache'uje wynik."""
    if jezyk in _CACHE_PRZEPISOW:
        return _CACHE_PRZEPISOW[jezyk]

    folder = os.path.join(DICTIONARIES_DIR, jezyk, FOLDER_REZYSER)
    przepisy: list[PrzepisRezysera] = []

    if os.path.isdir(folder):
        for nazwa_pliku in sorted(os.listdir(folder)):
            if not nazwa_pliku.lower().endswith((".yaml", ".yml")):
                continue
            sciezka = os.path.join(folder, nazwa_pliku)
            data = _wczytaj_yaml(sciezka)
            przepis = _yaml_to_przepis(data, sciezka)
            if przepis is not None:
                przepisy.append(przepis)

    przepisy.sort(key=lambda p: (p.kategoria, p.kolejnosc, p.id))
    _CACHE_PRZEPISOW[jezyk] = przepisy
    return przepisy


# =============================================================================
# Publiczne API
# =============================================================================
def lista_trybow(jezyk: str = "pl") -> list[PrzepisRezysera]:
    """Zwraca listę przepisów kategorii ``tryb`` (do wypełnienia RadioBox).

    Posortowane rosnąco po ``kolejnosc`` (a następnie po ``id`` dla stabilności).
    Gdy folder ``dictionaries/<jezyk>/rezyser/`` nie istnieje – zwraca ``[]``
    (GUI może wtedy pokazać ostrzeżenie „brak zainstalowanych trybów").
    """
    return [p for p in _zaladuj_wszystkie(jezyk) if p.kategoria == KATEGORIA_TRYB]


def lista_postprodukcji(jezyk: str = "pl") -> list[PrzepisRezysera]:
    """Zwraca listę przepisów kategorii ``postprodukcja``.

    Na razie używana tylko do nadawania tytułów rozdziałom w trybie
    Audiobook, ale kolejne narzędzia (np. „Automatyczna korekta", „Analiza
    statystyczna stylu") mogą być dokładane tak samo: YAML + jedno wpisanie
    ``kategoria: postprodukcja``.
    """
    return [p for p in _zaladuj_wszystkie(jezyk) if p.kategoria == KATEGORIA_POSTPROD]


def zaladuj_przepis(
    id_: str,
    jezyk: str = "pl",
    kategoria: str | None = None,
) -> PrzepisRezysera | None:
    """Zwraca pojedynczy przepis po ``id`` (lub ``None``, jeśli nie znaleziono).

    Args:
        id_:        Identyfikator (np. ``"audiobook"``, ``"tytuly"``).
        jezyk:      Kod języka (folder w ``dictionaries/``).
        kategoria:  Opcjonalne zawężenie wyszukiwania (``"tryb"``
                    lub ``"postprodukcja"``). Jeśli ``None`` – zwraca
                    pierwszy pasujący.
    """
    for p in _zaladuj_wszystkie(jezyk):
        if p.id != id_:
            continue
        if kategoria is not None and p.kategoria != kategoria:
            continue
        return p
    return None


def wyczysc_cache() -> None:
    """Zapomina wczytane przepisy – użyteczne po edycji YAML-i w runtime.

    Wywoływane m.in. przez ``odswiez_rezysera.py`` po aktualizacji akcentów
    (choć ten konkretny generator dotyka innych YAML-i, to cache może
    przedawnić się także tutaj).
    """
    _CACHE_PRZEPISOW.clear()


# =============================================================================
# Pomocnicze: podstawianie placeholderów
# =============================================================================
def _format_bezpiecznie(szablon: str, **kwargs: Any) -> str:
    """Jak ``str.format`` – ale nie wywala się na nieznanym kluczu.

    Python-owy ``.format`` wymaga, by WSZYSTKIE placeholdery w stringu
    miały odpowiednik w kwargs. Gdyby lingwista napisał w YAML-u
    ``{cos_nowego}`` i zapomniał to obsłużyć w kodzie – aplikacja by
    się wysypała. Tu zamiast tego zostawiamy oryginał ``{cos_nowego}``
    w wyniku, dzięki czemu błąd jest widoczny, ale nie blokujący.
    """
    class _SafeDict(dict):
        def __missing__(self, key: str) -> str:   # type: ignore[override]
            return "{" + key + "}"

    try:
        return szablon.format_map(_SafeDict(**kwargs))
    except (IndexError, ValueError):
        # np. samotne "{" w tekście – oddajemy oryginał, żeby nic nie gubić
        return szablon


def buduj_prompt_systemowy(przepis: PrzepisRezysera, world_context: str = "") -> str:
    """Prompt systemowy: baza + klauzula odrzucenia (bez sufiksu kontekstowego).

    Wariant dla trybów bez sufiksów (np. postprodukcja tytułów) lub gdy GUI
    chce pokazać podgląd. Dla trybów z sufiksami (Burza / Skrypt) silnik
    ``rezyser_ai`` używa :func:`buduj_pelny_prompt_systemowy`, bo tylko tam
    sufiks zostanie doklejony PRZED klauzulą.

    Placeholdery: ``{world_context}``, ``{jezyk_odpowiedzi}``.
    """
    return buduj_pelny_prompt_systemowy(przepis, world_context, sufiks_nazwa=None)


def buduj_pelny_prompt_systemowy(
    przepis: PrzepisRezysera,
    world_context: str = "",
    sufiks_nazwa: str | None = None,
) -> str:
    """Kompletny prompt systemowy z deterministyczną kolejnością sklejania.

    Kolejność (ostatnie wiadomości w systemie mają największy wpływ na
    model, więc klauzula musi być na końcu):

        1. **Baza** z pola ``prompt_systemowy`` (po podstawieniu placeholderów).
        2. **Sufiks kontekstowy** – opcjonalny, np. ``"alarm"`` / ``"startowy"``
           (podstawia placeholdery tak jak baza).
        3. **Klauzula odrzucenia** – z pola ``klauzula_odrzucenia`` lub,
           gdy puste, z :data:`KLAUZULA_ODRZUCENIA_DOMYSLNA`.

    Dzięki temu eksperymentalny sufiks w YAML-u może wpływać na zachowanie
    modelu (np. wymusić wygenerowanie ``<STRESZCZENIE>``) nie kolidując
    z infrastrukturalnym wymuszeniem tagu ``[ODRZUCENIE_AI]``.

    Args:
        przepis:        Załadowany :class:`PrzepisRezysera`.
        world_context:  Treść Księgi Świata (placeholder ``{world_context}``).
        sufiks_nazwa:   Klucz z ``przepis.sufiksy`` lub ``None`` = bez sufiksu.

    Returns:
        String gotowy do wysłania jako ``role=system``.
    """
    bazowy = _format_bezpiecznie(
        przepis.prompt_systemowy,
        world_context=world_context,
        jezyk_odpowiedzi=przepis.jezyk_odpowiedzi,
    )
    sufiks = ""
    if sufiks_nazwa:
        sufiks = buduj_sufiks(przepis, sufiks_nazwa, world_context=world_context)
    klauzula = przepis.klauzula_odrzucenia or KLAUZULA_ODRZUCENIA_DOMYSLNA
    return bazowy + sufiks + klauzula


def wykryto_odrzucenie(tekst: str) -> bool:
    """Rozpoznaje, czy odpowiedź AI jest odmową wygenerowania treści.

    Działa przez szukanie magicznego tagu :data:`TAG_ODRZUCENIA_AI`, który
    silnik wymusił na modelu w prompt_systemowy. Gdy go znajdzie –
    aplikacja NIE zapisuje odpowiedzi do pliku historii i pokazuje
    stosowny komunikat użytkownikowi.

    Metoda jest niezależna od ``jezyk_odpowiedzi`` (tag jest zawsze
    w alfabecie łacińskim i nie podlega tłumaczeniu).
    """
    return TAG_ODRZUCENIA_AI in (tekst or "")


def buduj_sufiks(przepis: PrzepisRezysera, nazwa: str, **extra: Any) -> str:
    """Zwraca tekst sufiksu ``nazwa`` lub pusty string, jeśli go nie ma.

    Dodatkowe argumenty (``**extra``) są przekazywane do podstawiania
    placeholderów – przydatne, gdy lingwista chce np. wstawić licznik
    rozdziałów w sufiksie kontynuacji.
    """
    szablon = przepis.sufiksy.get(nazwa, "")
    if not szablon:
        return ""
    return _format_bezpiecznie(
        szablon,
        world_context=extra.pop("world_context", ""),
        jezyk_odpowiedzi=przepis.jezyk_odpowiedzi,
        **extra,
    )


def buduj_przypomnienie(przepis: PrzepisRezysera, **extra: Any) -> str:
    """Zwraca przypomnienie doklejane do treści użytkownika (``role=user``)."""
    if not przepis.przypomnienie_uzytkownika:
        return ""
    return _format_bezpiecznie(
        przepis.przypomnienie_uzytkownika,
        jezyk_odpowiedzi=przepis.jezyk_odpowiedzi,
        **extra,
    )


def buduj_prompt_uzytkownika(przepis: PrzepisRezysera, **kwargs: Any) -> str:
    """Szablon z ``prompt_uzytkownika_szablon`` z podstawionymi wartościami.

    Używany przez narzędzia postprodukcyjne (np. tytułowanie rozdziałów),
    gdzie instrukcja ``role=user`` jest powtarzalna dla każdego fragmentu
    i wymaga podstawienia ``{naglowek}`` oraz ``{probka}``.
    """
    if not przepis.prompt_uzytkownika_szablon:
        return ""
    return _format_bezpiecznie(
        przepis.prompt_uzytkownika_szablon,
        jezyk_odpowiedzi=przepis.jezyk_odpowiedzi,
        **kwargs,
    )
