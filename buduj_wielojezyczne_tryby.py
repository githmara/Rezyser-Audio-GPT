#!/usr/bin/env python
"""
buduj_wielojezyczne_tryby.py — Batchowy autotłumacz PRZEPISÓW Reżysera (i18n).

Trzeci brat rodziny `buduj_wielojezyczne_*`: po interfejsie (`_ui.py`)
i dokumentacji (`_docs.py`) bierze na siebie `dictionaries/pl/rezyser/*.yaml`,
czyli PRZEPISY trybów twórczych i narzędzi postprodukcji. Materiał jest
z założenia najtrudniejszy w całym projekcie: pola `prompt_systemowy` to
PROMPTY SYSTEMOWE dla innego modelu, więc naiwne tłumaczenie kończy się
„meta instruction skip" — model wykonuje instrukcję zamiast ją przetłumaczyć.
Stąd status EKSPERYMENTU i cały aparat bramek niżej.

Architektura (v18.15, Etap 3 roadmapy 18.13):

  1. ROUND-TRIP ruamel (`typ='rt'`) — jak w builderze UI. Klucze, kolejność,
     styl block-scalar (`|`) i komentarze sekcyjne przechodzą 1:1; podmieniamy
     WYŁĄCZNIE wartości. Jedyna zmiana kosmetyczna, jaką wprowadza dumper:
     block-scalar z wiodącymi pustymi liniami dostaje jawny wskaźnik wcięcia
     (`|` → `|2`) — semantycznie identyczne, sprawdzone empirycznie na 6
     przepisach PL.

  2. KLASYFIKACJA PÓL (:data:`KLASY_POL`) — każdy klucz przepisu ma jawnie
     przypisaną klasę: techniczny (kopia 1:1), krótka etykieta, długi prompt,
     mapa tekstów, mapa słów-wyzwalaczy, pole pochodne (liczone bez LLM).
     Klucz NIEZNANY to twardy błąd, nie cicha kopia — nowe pole w PL musi
     przejść przez decyzję „czy to się tłumaczy", zanim tłumacz je zobaczy.

  3. POLA POCHODNE liczone DETERMINISTYCZNIE, bez pytania modelu:
       * `kod_jezyka`  = kod paczki docelowej,
       * `jezyk_odpowiedzi` = wartość z siostrzanego przepisu tej paczki
         (cała paczka mówi jednym głosem: „English", „suomeksi", „Deutsch"),
       * `regex_podzial_rozdzialow` = regex PL z podmienionymi nazwami
         nagłówków struktury na te z `dictionaries/<kod>/gui/ui.yaml`
         (`rezyser.naglowek_prolog|rozdzial|epilog|akt|scena`).
     Ostatnie jest KRYTYCZNE: regex dzieli plik projektu po nagłówkach, które
     silnik wpisał z i18n. Wolne tłumaczenie tego pola rozjechało już fi
     (`Johdanto` vs `Prologi`), is (`Formáli`/`Eftirorð` vs `Prolog`/`Epilog`)
     i ru (`Введение` vs `Пролог`) — Prolog przestawał być wykrywany.

  4. ZAMRAŻANIE (dwie klasy tokenów, oba `⟦…⟧` jak u braci):
       * `⟦P{n}⟧` — placeholdery `{klucz}` ORAZ escapowane bloki `{{…}}`
         (przykład JSON-a w prompcie: `{{"tury":[{{"mowca","tekst"}}]}}`),
       * `⟦K{n}⟧` — KOTWICE, czyli literały, które muszą przeżyć tłumaczenie
         bit w bit: tag `[ODRZUCENIE_AI]`, wrappery z `rezyser/baza.yaml`,
         angielskie nazwy pól formularza ElevenReadera (`Genres:`,
         `Target audience:` — po nich szuka `rezyser_ai.waliduj_karte_publikacji`),
         audio-tagi v3 (`[whispers]`), klucze JSON (`"mowca"`).
     Kandydatów na kotwice wyłuskują regexy (backticki, nawiasy kwadratowe,
     `"cytat"`, `Nazwa pola:`), a ROZSTRZYGA je ORAKUŁ: literał jest kotwicą,
     jeśli występuje DOSŁOWNIE w ręcznie zrecenzowanej paczce odniesienia (`en`).
     To samoutrzymujące się kryterium — literał, który przeżył tłumaczenie
     człowieka, jest nietłumaczalny z definicji; `[do uzupełnienia ręcznie]`
     (en: `[to be filled in manually]`) orakuł odrzuca i pole leci do modelu.
     Brak paczki odniesienia = tryb zachowawczy: zamrażamy WSZYSTKICH kandydatów
     i mówimy o tym głośno w logu.

  5. JEDNO WYWOŁANIE na (plik, język) — structured outputs Anthropic
     (`output_config.format` + :data:`SCHEMA_TLUMACZENIA`), jak w builderze UI.
     Wszystkie jednostki pliku (bloki komentarzy + etykiety + prompty + słowa
     wyzwalające) jadą w jednym payloadzie: model widzi CAŁY przepis, więc
     etykieta trzyma terminologię prompta. Za duży plik dzielimy po
     :data:`BATCH_MAX_ZNAKOW`.

  6. BRAMKI PO STRONIE SKRYPTU (nic nie zapisujemy przy foulu):
       * parzystość multisetu `⟦P{n}⟧`/`⟦K{n}⟧` per jednostka,
       * ODCISK STRUKTURY dla długich promptów (liczba nagłówków `#`, punktów
         numerowanych, par `**`, linii niepustych, stosunek długości) —
         to detektor „meta instruction skip": model, który WYKONAŁ prompt
         zamiast go przetłumaczyć, zwraca gotową kartę publikacyjną, a nie
         instrukcję, i odcisk się nie zgadza,
       * sanityzacja `sufiks_pliku_wyniku` (nazwa pliku na dysku!),
       * walidacja regexa (`re.compile` + liczba alternatyw),
       * po zapisie: WALIDACJA SILNIKIEM (`przepisy_rezysera.zaladuj_przepis`
         + `core_poliglota._jezyk_kompletny`) — pola techniczne muszą być
         identyczne z PL, prompt musi się złożyć bez nierozwiniętych `{…}`,
         a paczka nie może wypaść z listy języków kompletnych.
     Jedna nieudana jednostka → jednorazowy retry z czystym kontekstem
     (wzorzec buildera UI), dalej porażka → plik NIE jest zapisywany.

  7. DRAFT + CHECKLISTA — każde tłumaczenie ląduje jako draft z banerem
     `przeglad_tlumaczen.naglowek_roboczy` i emituje `skrypty/przeglad_tryby.md`.
     RÓŻNICA wobec braci: kanoniczny stan przepisu NIE ma banera „nie edytuj
     ręcznie", bo `rezyser/*.yaml` to plik edytowalny przez lingwistę w Managerze
     Reguł. `--finalizuj` po prostu ZDEJMUJE baner draftu, zostawiając
     przetłumaczony nagłówek autorski (tak wyglądają paczki pisane ręcznie).

Zakres: `dictionaries/<kod>/rezyser/`. `baza.yaml` jest POMIJANY — to tagi-kotwice
identyczne we wszystkich paczkach (patrz jego własny nagłówek). Przepisy
`opowiesci/` mają inny schemat (`core_opowiesci`) i świadomie zostają poza
zakresem tego narzędzia.

Użycie:
  python buduj_wielojezyczne_tryby.py --wszystkie
  python buduj_wielojezyczne_tryby.py --jezyki de,fi --przepisy postprod_publikacja
  python buduj_wielojezyczne_tryby.py --jezyki de --dry-run     # zero API
  python buduj_wielojezyczne_tryby.py --wszystkie --tylko-walidacja   # zero API
  python buduj_wielojezyczne_tryby.py --wszystkie --finalizuj         # zero API
  python buduj_wielojezyczne_tryby.py --jezyki fi --slowniki "%LOCALAPPDATA%\\Programs\\Reżyser Audio GPT\\dictionaries" \\
      --przepisy postprod_audyt_hsl        # propagacja prywatnego przepisu w INSTALACJI

Wymaga `ANTHROPIC_API_KEY` w `golden_key.env` (ten sam plik co GUI).
Moduł NIE zależy od wxPython — uruchamialny w CLI bez inicjalizacji GUI.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

import przeglad_tlumaczen
import tlumacz_bramki
import tlumacz_rdzen


# ---------------------------------------------------------------------------
# STDOUT UTF-8 (spójnie z braćmi — cmd.exe vs cp1250)
# ---------------------------------------------------------------------------
tlumacz_rdzen.skonfiguruj_stdout()


# ---------------------------------------------------------------------------
# Ścieżki
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
# Katalog słowników jest ZMIENNY (`--slowniki`): ten sam pipeline obsługuje
# repo (seed) ORAZ zainstalowaną paczkę, w której żyją prywatne przepisy usera
# (user-data, w repo ich nie ma — patrz `skrypty/walidacja_audyt_hsl.py`).
DICT_DIR = ROOT / "dictionaries"

FOLDER_REZYSER = "rezyser"
FOLDER_GUI = "gui"
NAZWA_UI = "ui.yaml"
KOD_ZRODLOWY = "pl"
# Paczka, której ręczne tłumaczenie służy za ORAKUŁ kotwic (patrz `wykryj_kotwice`).
KOD_ODNIESIENIA = "en"

# `baza.yaml` to wrappery kontekstu LLM — tagi identyczne we WSZYSTKICH paczkach
# (jego własny nagłówek: „DO NOT TRANSLATE / KEEP IDENTICAL"). Tłumaczenie
# rozjechałoby odwołania z `tryb_burza.yaml`, który cytuje je dosłownie.
PLIKI_POMIJANE = frozenset({"baza.yaml"})


# ---------------------------------------------------------------------------
# Parametry wywołań LLM
# ---------------------------------------------------------------------------
# Cały przepis (~8 kB PL) mieści się w jednym wywołaniu, a model widzący pełny
# kontekst trzyma spójną terminologię między etykietą, promptem i komentarzami.
# Tniemy dopiero, gdy suma źródeł chunku przekroczy próg — z zapasem pod
# rozwlekłe języki i cyrylicę (ru puchnie ~1,5× wobec PL).
BATCH_MAX_ZNAKOW = 12_000
MAX_TOKENS_OUT = 16_000
MODEL_DOMYSLNY = "claude-sonnet-5"

# Schemat structured-outputs — wspólny kontrakt id→target całej rodziny.
SCHEMA_TLUMACZENIA = tlumacz_rdzen.SCHEMA_TLUMACZENIA


# ---------------------------------------------------------------------------
# Mapa języków docelowych — wspólny rejestr `jezyki_docelowe.yaml`
# ---------------------------------------------------------------------------
# Ten sam plik i ta sama semantyka co u braci (single source: kontrybutor dodaje
# język bez dotykania Pythona). Implementacja w `tlumacz_rdzen` (v18.17).
MAPA_JEZYKOW: dict[str, str] = tlumacz_rdzen.wczytaj_mape_jezykow(
    ROOT, KOD_ZRODLOWY)


def _natywna_nazwa(kod: str) -> str:
    """Natywna nazwa celu z `<kod>/podstawy.yaml::etykieta` (przez rdzeń).

    Cienki wrapper, bo :data:`DICT_DIR` jest przestawiane przez `--slowniki`
    w trakcie działania — rdzeń dostaje katalog jawnym argumentem.
    """
    return tlumacz_rdzen.natywna_nazwa(DICT_DIR, kod)


# ---------------------------------------------------------------------------
# KLASYFIKACJA PÓL PRZEPISU
# ---------------------------------------------------------------------------
# Źródłem prawdy o polach jest `przepisy_rezysera.PrzepisRezysera`. Każdy klucz
# MUSI stać w dokładnie jednej klasie — nieznany klucz zatrzymuje przebieg
# (patrz `zbierz_jednostki`). Powód: pole dopisane w PL i po cichu skopiowane
# 1:1 to polski leak w ośmiu paczkach, którego żadna bramka nie widzi.
KLASA_TECHNICZNA = "techniczne"    # kopia 1:1 (id, model, liczby, bool, kanony)
KLASA_ETYKIETA = "etykieta"        # krótki napis GUI / komunikat jednolinijkowy
KLASA_PROMPT = "prompt"            # długi tekst dla modelu (odcisk struktury!)
KLASA_MAPA_TEKSTOW = "mapa_tekstow"    # dict klucz→tekst (tłumaczymy WARTOŚCI)
KLASA_MAPA_SLOW = "mapa_slow"      # dict klucz→lista słów (tłumaczymy słowa)
KLASA_SUFIKS = "sufiks_pliku"      # fragment nazwy pliku na dysku (sanityzacja)
KLASA_POCHODNA = "pochodna"        # liczona deterministycznie, bez LLM

KLASY_POL: dict[str, str] = {
    # --- Techniczne: identyfikatory, dispatch silnika, liczby, zamknięte kanony
    "id": KLASA_TECHNICZNA,
    "kategoria": KLASA_TECHNICZNA,
    "kolejnosc": KLASA_TECHNICZNA,
    "model": KLASA_TECHNICZNA,
    "temperatura": KLASA_TECHNICZNA,
    "format_wyjscia": KLASA_TECHNICZNA,
    "struktura": KLASA_TECHNICZNA,
    "zapis_do_pliku": KLASA_TECHNICZNA,
    "stosuj_akcenty_fonetyczne": KLASA_TECHNICZNA,
    "dla_trybow": KLASA_TECHNICZNA,
    "zakres": KLASA_TECHNICZNA,
    "rola": KLASA_TECHNICZNA,
    "max_tokens_wyjscia": KLASA_TECHNICZNA,
    "min_dlugosc_fragmentu": KLASA_TECHNICZNA,
    "max_dlugosc_probki": KLASA_TECHNICZNA,
    # Kanony formularza platformy publikacyjnej — wartości angielskie,
    # przepisywane do formularza 1:1 i walidowane w Pythonie. NIE tłumaczymy.
    "gatunki_dozwolone": KLASA_TECHNICZNA,
    "odbiorcy_dozwoleni": KLASA_TECHNICZNA,
    "limit_znakow_opisu": KLASA_TECHNICZNA,
    # --- Krótkie napisy
    "etykieta": KLASA_ETYKIETA,
    "etykieta_fragment_zbyt_krotki": KLASA_ETYKIETA,
    "etykieta_bled_brak_kredytow": KLASA_ETYKIETA,
    "etykieta_odrzucenie": KLASA_ETYKIETA,
    "etykieta_blad_fragment": KLASA_ETYKIETA,
    # --- Długie teksty dla modelu
    "prompt_systemowy": KLASA_PROMPT,
    "prompt_uzytkownika_szablon": KLASA_PROMPT,
    "prompt_ksiegi_szablon": KLASA_PROMPT,
    "przypomnienie_uzytkownika": KLASA_PROMPT,
    "klauzula_odrzucenia": KLASA_PROMPT,
    "doklejka_celu_sceny": KLASA_PROMPT,
    # --- Struktury
    "sufiksy": KLASA_MAPA_TEKSTOW,
    "slowa_wyzwalajace": KLASA_MAPA_SLOW,
    "sufiks_pliku_wyniku": KLASA_SUFIKS,
    # --- Pochodne (bez LLM)
    "kod_jezyka": KLASA_POCHODNA,
    "jezyk_odpowiedzi": KLASA_POCHODNA,
    "regex_podzial_rozdzialow": KLASA_POCHODNA,
}


# ---------------------------------------------------------------------------
# Tokenizacja: placeholdery + kotwice (implementacja we wspólnym `tlumacz_rdzen`)
# ---------------------------------------------------------------------------
# Definicje `{klucz}`, `{{…}}`, tokeny `⟦P{n}⟧`/`⟦K{n}⟧` i heurystyka kandydatów
# są identyczne u wszystkich braci — od v18.17 mają jedno miejsce. Aliasy zostają,
# bo nazwy występują w tym module kilkanaście razy (mniejszy diff, ten sam sens).
PLACEHOLDER_REGEX = tlumacz_rdzen.PLACEHOLDER_REGEX
PODWOJNE_KLAMRY_REGEX = tlumacz_rdzen.PODWOJNE_KLAMRY_REGEX

TOKEN_PH = tlumacz_rdzen.TOKEN_PH
TOKEN_KOTWICA = tlumacz_rdzen.TOKEN_KOTWICA
TOKEN_PARITY_REGEX = tlumacz_rdzen.TOKEN_PARITY_REGEX

_KANDYDACI_KOTWIC = tlumacz_rdzen.KANDYDACI_KOTWIC
# ODRZUCONY wzorzec (notatka na przyszłość): „pojedyncze Słowo przed ` (`" miał
# wyłapać `Description (<n>/1000 characters):` z karty publikacyjnej. Łapał też
# `Audiobook (Proza, …)` z pola `etykieta` — a orakuł go POTWIERDZAŁ, bo w paczce
# en to oczywiście „Audiobook". Efekt: fińska etykieta zostałaby „Audiobook"
# zamiast „Äänikirja". Nazwy pól formularza pokrywa dziś twarde źródło
# `_kotwice_z_silnika` (stałe `KOTWICA_*`), więc heurystyka nie jest potrzebna.


def _kotwice_z_silnika() -> tuple[str, ...]:
    """Literały, po których PYTHON odnajduje wartości w wyniku modelu.

    Jedyne twarde źródło: stałe `KOTWICA_*` w :mod:`rezyser_ai` (walidator karty
    publikacyjnej). Heurystyka kandydatów + orakuł `en` zwykle je wyłapią, ale
    tutaj nie chcemy „zwykle" — zmiana nazwy pola w prompcie wyłącza walidator
    BEZ ŻADNEGO objawu (ostrzeżenia po prostu przestają się pojawiać).
    Fail-soft: gdy import padnie (środowisko bez zależności silnika), zostaje
    sama heurystyka i komunikat w logu.
    """
    try:
        import rezyser_ai
    except Exception as exc:  # noqa: BLE001 — dev-tool ma działać też bez silnika
        print(f"⚠️  Cannot import `rezyser_ai` ({exc}) — publication-card validator "
              f"anchors now rest on the heuristic + oracle alone.")
        return ()
    return tuple(
        getattr(rezyser_ai, nazwa)
        for nazwa in dir(rezyser_ai)
        if nazwa.startswith("KOTWICA_") and isinstance(getattr(rezyser_ai, nazwa), str)
    )


def _wartosci_slowne() -> tuple[str, ...]:
    """Literały pilnowane GRANICĄ SŁOWA, a nie zamrażaniem.

    `Yes`/`No` z pola „Mature content" silnik dopasowuje case-insensitive
    (`rezyser_ai._WARTOSCI_DOJRZALOSCI`), więc prompt musi je zachować po
    angielsku — ale zamrozić ich NIE WOLNO: `str.replace("No", …)` weszłoby
    w środek polskiego „Nowy" i rozjechało tekst. Dlatego zamiast tokenu
    stawiamy bramkę: liczba wystąpień JAKO OSOBNE SŁOWO musi się zgadzać
    (+ jawna reguła w prompcie systemowym tłumacza).
    """
    try:
        import rezyser_ai
        surowe = getattr(rezyser_ai, "_WARTOSCI_DOJRZALOSCI", ("yes", "no"))
    except Exception:  # noqa: BLE001 — fail-soft, jak `_kotwice_z_silnika`
        surowe = ("yes", "no")
    return tuple(str(w).capitalize() for w in surowe)


_kandydaci_kotwic = tlumacz_rdzen.kandydaci_kotwic


def wykryj_kotwice(
    teksty_pl: list[str],
    odniesienia: dict[str, str] | None,
    dodatkowe: tuple[str, ...] = (),
) -> list[str]:
    """Ustala listę literałów zamrażanych jako kotwice `⟦K{n}⟧`.

    Args:
        teksty_pl: wszystkie tłumaczone teksty źródłowe pliku (pola + komentarze).
        odniesienia: SUROWE treści odpowiadającego pliku w paczkach odniesienia
            (`{kod: tekst}`, bez paczki źródłowej i bez języka docelowego) albo
            ``None`` / pusty słownik, gdy żadnej nie ma. Kandydat jest kotwicą
            tylko wtedy, gdy występuje DOSŁOWNIE we WSZYSTKICH orakułach.
        dodatkowe: literały wymuszone z CLI (`--kotwica`).

    JEDNOMYŚLNOŚĆ, nie sam `en` — poprawka po pierwszym audycie kanonu. Kryterium
    „przeżył ręczne tłumaczenie" jest PUSTE dla literału, który w źródle już jest
    angielski: `[Speaker]`, `"Narrator"`, `"deus ex machina"` trywialnie „przeżyły"
    tłumaczenie PL→EN, choć niemieckie/rosyjskie paczki słusznie je lokalizują
    (`[Sprecher]`, `Рассказчик`). Wymaganie obecności we wszystkich paczkach
    odsiewa tę klasę (35 fałszywych alarmów na 74 w audycie), a zachowuje kotwice
    prawdziwe — te są identyczne w każdej paczce z definicji (`[ODRZUCENIE_AI]`,
    `[whispers]`, `"mowca"`, `Genres:`).

    Returns:
        Lista kotwic posortowana malejąco po długości — podstawienie musi
        zaczynać od najdłuższych, żeby `` `[do uzupełnienia]` `` nie rozpadło
        się na dwie krótsze kotwice.
    """
    # Rozstrzyganie kandydatów żyje w rdzeniu; TUTAJ dokładamy jedyną rzecz
    # specyficzną dla przepisów Reżysera — literały, których walidator karty
    # publikacyjnej szuka dosłownie (stałe `KOTWICA_*` w `rezyser_ai`).
    return tlumacz_rdzen.wykryj_kotwice(
        teksty_pl, odniesienia, dodatkowe, _kotwice_z_silnika())


tokenizuj = tlumacz_rdzen.tokenizuj
detokenizuj = tlumacz_rdzen.detokenizuj


# ---------------------------------------------------------------------------
# Odcisk struktury — detektor „meta instruction skip"
# ---------------------------------------------------------------------------
# Implementacja żyje we wspólnym `tlumacz_bramki` (v18.16) — ten builder był jej
# pierwszym konsumentem, ale bracia `_docs.py`/`_ui.py` potrzebują dokładnie tego
# samego. Alias zostaje, bo nazwa jest w tym module używana w kilku miejscach.
odcisk_struktury = tlumacz_bramki.odcisk_struktury


def waliduj_jednostke(
    src_tok: str, tgt: str, klasa: str,
) -> tuple[bool, list[str]]:
    """Bramka jednej jednostki: parzystość tokenów + (dla promptów) odcisk.

    Zwraca ``(ok, lista_diagnostyk)``. Diagnostyka jest po angielsku tylko
    tam, gdzie cytuje dane techniczne — reszta logu narzędzia jest polska.
    """
    problemy: list[str] = tlumacz_rdzen.parzystosc_tokenow(src_tok, tgt)

    if klasa in (KLASA_PROMPT, KLASA_MAPA_TEKSTOW):
        # Przepis jest materiałem sztywnym: TU naruszenia miękkie (pogrubienia,
        # liczba linii, stosunek długości) blokują zapis na równi z twardymi —
        # prompt nie ma prawa „urosnąć" ani „schudnąć". Brat prozatorski
        # (`_docs.py`) tej samej pary list używa inaczej.
        twarde, miekkie = tlumacz_bramki.waliduj_odcisk(src_tok, tgt)
        problemy += twarde + miekkie

    return (len(problemy) == 0), problemy


# ---------------------------------------------------------------------------
# Sanityzacja sufiksu nazwy pliku
# ---------------------------------------------------------------------------
# Znaki zakazane w nazwie pliku Windows — lustro `przepisy_rezysera`.
_ZNAKI_ZAKAZANE_SUFIKSU = '\\/:*?"<>|'


def _zloz_do_ascii(znak: str) -> str:
    """Ściąga diakrytykę z liter ŁACIŃSKICH, resztę pisma zostawia w spokoju.

    Konwencja paczek shippowanych (v18.13/18.14): de `_veroffentlichung`,
    is `_utgafa`, es `_publicacion` — łacińska diakrytyka złożona do ASCII
    (nazwa pliku jedzie przez różne systemy plików), ale ru `_пересказ`
    zostaje cyrylicą (user i tak wpisuje cyrylicę w nazwę projektu).
    """
    rozlozony = unicodedata.normalize("NFKD", znak)
    baza = rozlozony[0]
    if "a" <= baza.lower() <= "z":
        return "".join(c for c in rozlozony if not unicodedata.combining(c))
    return znak


def sanityzuj_sufiks(surowy: str) -> tuple[str, list[str]]:
    """Normalizuje `sufiks_pliku_wyniku`. Zwraca (sufiks, lista_uwag).

    Reguły z konwencji paczek: wiodące podkreślenie, małe litery, jedno słowo
    (spacje i myślniki → podkreślenie), bez znaków zakazanych, bez łacińskiej
    diakrytyki. Uwagi są informacyjne — trafiają do logu, nie blokują zapisu
    (blokuje dopiero walidacja silnikiem, gdyby sanityzacja nie pomogła).
    """
    uwagi: list[str] = []
    sufiks = surowy.strip().strip("`\"'")
    sufiks = "".join(_zloz_do_ascii(z) for z in sufiks)
    sufiks = re.sub(r"[\s\-–—]+", "_", sufiks)
    bez_zakazanych = "".join(z for z in sufiks if z not in _ZNAKI_ZAKAZANE_SUFIKSU)
    if bez_zakazanych != sufiks:
        uwagi.append("usunięto znaki zakazane w nazwie pliku")
        sufiks = bez_zakazanych
    sufiks = sufiks.lower()
    if not sufiks.startswith("_"):
        sufiks = "_" + sufiks.lstrip("_")
        uwagi.append("dodano wiodące podkreślenie")
    sufiks = re.sub(r"_{2,}", "_", sufiks)
    if len(sufiks) > 32:
        sufiks = sufiks[:32].rstrip("_")
        uwagi.append("skrócono do 32 znaków")
    if sufiks != surowy.strip():
        uwagi.append(f"model zwrócił {surowy.strip()!r}")
    return sufiks, uwagi


# ---------------------------------------------------------------------------
# POLA POCHODNE — liczone z danych paczki, bez pytania modelu
# ---------------------------------------------------------------------------
# Klucze i18n nagłówków struktury. To TE SAME napisy, które `gui_rezyser` wpisuje
# do pliku projektu przez `t(..., jezyk_override=kod)` — regex podziału musi je
# rozpoznawać, więc jedynym poprawnym źródłem jest `ui.yaml` paczki docelowej.
_KLUCZE_NAGLOWKOW = (
    "naglowek_prolog", "naglowek_epilog", "naglowek_rozdzial",
    "naglowek_akt", "naglowek_scena",
)


def naglowki_struktury(kod: str) -> dict[str, str]:
    """Zwraca `{klucz_naglowka: napis}` z `dictionaries/<kod>/gui/ui.yaml`.

    Czytamy plik bezpośrednio (safe-load), a nie przez `i18n` — dev-tool ma
    działać także z `--slowniki` wskazującym instalację, gdzie `i18n` liczyłby
    ścieżki po `sciezki.KATALOG_BAZOWY` repo. Brak klucza = pusty słownik
    (wołający degraduje: zostawia regex PL i mówi o tym w logu).
    """
    plik = DICT_DIR / kod / FOLDER_GUI / NAZWA_UI
    try:
        with open(plik, "r", encoding="utf-8") as fh:
            dane = YAML(typ="safe").load(fh)
    except Exception:  # noqa: BLE001 — brak/zły ui.yaml → degradacja u wołającego
        return {}
    sekcja = (dane or {}).get("rezyser") if isinstance(dane, dict) else None
    if not isinstance(sekcja, dict):
        return {}
    return {
        k: str(sekcja[k]).strip()
        for k in _KLUCZE_NAGLOWKOW
        if isinstance(sekcja.get(k), str) and str(sekcja[k]).strip()
    }


def wyprowadz_regex(regex_pl: str, kod: str) -> tuple[str, list[str]]:
    """Przenosi `regex_podzial_rozdzialow` na język `kod` PODMIANĄ nagłówków.

    Zamiast tłumaczyć regex (co rozjechało już fi/is/ru — `Johdanto` wobec
    i18n-owego `Prologi`), bierzemy regex PL i podmieniamy w nim polskie nazwy
    nagłówków na natywne z `ui.yaml` paczki docelowej. Szkielet regexa
    (`(?i)`, `\\n*`, `\\d+`, alternatywy) zostaje nietknięty.

    Zwraca (regex, lista_uwag). Uwaga na liście = coś degradowało (brak
    nagłówków w paczce, nieudana kompilacja) i regex PL został bez zmian.
    """
    uwagi: list[str] = []
    if not regex_pl.strip():
        return regex_pl, uwagi
    zrodlowe = naglowki_struktury(KOD_ZRODLOWY)
    docelowe = naglowki_struktury(kod)
    if not zrodlowe or not docelowe:
        uwagi.append(
            f"brak nagłówków struktury w ui.yaml ({KOD_ZRODLOWY}: "
            f"{len(zrodlowe)}, {kod}: {len(docelowe)}) — regex zostaje jak w PL"
        )
        return regex_pl, uwagi

    wynik = regex_pl
    podmienione: list[str] = []
    # Od najdłuższego napisu PL — „Rozdział" przed „Akt", żeby krótsza nazwa
    # nie weszła w środek dłuższej.
    for klucz in sorted(zrodlowe, key=lambda k: -len(zrodlowe[k])):
        slowo_pl = zrodlowe[klucz]
        slowo_cel = docelowe.get(klucz)
        if not slowo_cel or slowo_pl not in wynik:
            continue
        wynik = wynik.replace(slowo_pl, slowo_cel)
        podmienione.append(f"{slowo_pl}→{slowo_cel}")

    if not podmienione:
        uwagi.append("żadna nazwa nagłówka nie wystąpiła w regexie — bez zmian")
        return regex_pl, uwagi

    try:
        re.compile(wynik)
    except re.error as exc:
        uwagi.append(f"wynik nie kompiluje się jako regex ({exc}) — zostaje PL")
        return regex_pl, uwagi
    if wynik.count("|") != regex_pl.count("|"):
        uwagi.append("zmieniła się liczba alternatyw `|` — zostaje PL")
        return regex_pl, uwagi

    uwagi.append("podmiana nagłówków: " + ", ".join(podmienione))
    return wynik, uwagi


def jezyk_odpowiedzi_paczki(kod: str) -> str | None:
    """Wyciąga `jezyk_odpowiedzi` z dowolnego istniejącego przepisu paczki.

    Cała paczka mówi o sobie jednym napisem („English", „suomeksi", „Deutsch"),
    więc kopiujemy go z siostrzanego przepisu zamiast pytać model o formę
    gramatyczną. ``None`` = paczka jest pusta (pierwszy przepis w nowym
    języku) → wołający dokłada jednostkę do tłumaczenia.
    """
    folder = DICT_DIR / kod / FOLDER_REZYSER
    if not folder.is_dir():
        return None
    for plik in sorted(folder.glob("*.yaml")):
        if plik.name in PLIKI_POMIJANE:
            continue
        try:
            with open(plik, "r", encoding="utf-8") as fh:
                dane = YAML(typ="safe").load(fh)
        except Exception:  # noqa: BLE001 — uszkodzony plik obcej paczki pomijamy
            continue
        wartosc = (dane or {}).get("jezyk_odpowiedzi") if isinstance(dane, dict) else None
        if isinstance(wartosc, str) and wartosc.strip():
            return wartosc.strip()
    return None


# ---------------------------------------------------------------------------
# Komentarze YAML — wydobycie i wstawienie (implementacja w `tlumacz_rdzen`)
# ---------------------------------------------------------------------------
# Komentarze w `rezyser/*.yaml` to dokumentacja dla LINGWISTY (co wolno zmieniać,
# czego nie tykać, skąd wzięły się limity) — paczki pisane ręcznie mają je
# przetłumaczone, więc tłumaczymy je też tutaj. Maszyneria (maska ciał
# block-scalarów, bloki `#`, komentarze końcowe) jest wspólna dla całej rodziny
# od v18.17; aliasy zostają, bo nazwy są używane niżej w kilku miejscach.
_RE_DEKORACJA = tlumacz_rdzen.RE_DEKORACJA
_linie_w_blokach_scalarnych = tlumacz_rdzen.linie_w_blokach_scalarnych
bloki_komentarzy = tlumacz_rdzen.bloki_komentarzy
zloz_blok_komentarza = tlumacz_rdzen.zloz_blok_komentarza
komentarze_koncowe = tlumacz_rdzen.komentarze_koncowe


# ---------------------------------------------------------------------------
# Prompt systemowy tłumacza — ANGIELSKI (jak u obu braci)
# ---------------------------------------------------------------------------
# EN framing jest udokumentowaną decyzją projektu (neutralny dla wszystkich par
# językowych, nie kotwiczy modelu w polszczyźnie — audyt buildera UI 2026-06-16).
# Tutaj dochodzi rdzeń EKSPERYMENTU: blok „What you are looking at", czyli jawne
# zdjęcie z modelu roli adresata tłumaczonych promptów. Bez niego materiał
# `prompt_systemowy` wywołuje „meta instruction skip" — model wykonuje instrukcję.
_RODZAJE_OPIS = (
    "- `prompt` — a multi-line PROMPT TEMPLATE for the engine's model. Preserve "
    "the skeleton EXACTLY: markdown headings (`#`, `###`), the numbering of the "
    "rule list, `**bold**` spans, blank lines, emoji, block order, and the "
    "output-format block at the end. As a rule of thumb: one source line = one "
    "target line.\n"
    "- `label` — a short GUI label or a one-line status/error message.\n"
    "- `words` — a single trigger word or short phrase that a HUMAN USER types "
    "into the app. Give the word native speakers would actually type, not a "
    "literal gloss of the Polish one.\n"
    "- `comment` — YAML developer documentation (a comment block for the person "
    "maintaining this language pack). Translate it as documentation. Lines made "
    "up only of `=`, `-` or `*` are decoration: copy them unchanged, same "
    "length. Keep code identifiers, file names and YAML key names as they are. "
    "WRAP the prose at about 78 characters per line, the way the source block "
    "does — rewrap freely (line count may differ) but keep the leading "
    "indentation of continuation lines in numbered or bulleted items, and keep "
    "blank lines where the source has them. When the comment CITES a closed "
    "value or a form field name (`Yes`/`No`, `Genres:`), cite it in English "
    "exactly as the prompt does — do not localize the citation.\n"
    "- `filename_suffix` — a fragment of a FILE NAME on disk. Return ONE "
    "lowercase word starting with an underscore, no spaces: `_publication`, "
    "`_zusammenfassung`, `_utgafa`. For Latin-script languages strip diacritics "
    "(`_utgafa`, not `_útgáfa`); non-Latin scripts keep their own script "
    "(`_пересказ`).\n"
    "- `language_name` — the name of the target language in the grammatical form "
    "that fits the sentence \"write the answer in ___\" in that language "
    "(e.g. English → `English`, Suomi → `suomeksi`, Deutsch → `Deutsch`).\n"
)


def _PROMPT_SYSTEMOWY(nazwa_celu: str, kod: str) -> str:
    return (
        "# Role\n"
        "You are a senior localization engineer for a desktop wxPython "
        "application. You localize RECIPE FILES that configure a creative-writing "
        "engine: YAML files holding prompt templates, GUI labels and developer "
        "comments. The source strings are in Polish.\n"
        f"Target language: **{nazwa_celu}** (ISO 639 code: {kod}).\n\n"
        + tlumacz_bramki.blok_anty_meta_skip(przewaga_promptow=True) + "\n"
        "## Task\n"
        "You receive a JSON object with an `items` field — a list of "
        "`{\"id\": int, \"kind\": str, \"source\": str}` objects. Translate each "
        "`source` and return JSON of the shape:\n"
        "  `{\"translations\": [{\"id\": int, \"target\": str}, ...]}`\n"
        "Each object MUST carry exactly the same `id` as the input. Skipping ids, "
        "adding new ones or changing their order is not allowed.\n\n"
        "## Item kinds\n"
        + _RODZAJE_OPIS +
        "\n## Technical rules (CRITICAL — a violation blocks the file from being written)\n"
        "1. **Markers ⟦P<n>⟧ and ⟦K<n>⟧** are frozen program fragments: "
        "placeholders the engine fills in, escaped JSON examples, engine tags, "
        "and English form-field names that a validator locates by their exact "
        "spelling. Copy every marker into `target` VERBATIM — same letters, same "
        "digits, same brackets. Each marker must appear in `target` exactly as "
        "many times as in `source`. Do NOT invent markers that are not in the "
        "source, do not renumber them, do not translate them. The sentence AROUND "
        "a marker is still translated normally.\n"
        "2. **Do not translate** technical literals: AI model names "
        "(`claude-sonnet-5`, `Anthropic`), file and folder names and extensions "
        "(`skrypty/`, `runtime/`, `baza.yaml`, `.txt`, `.md`), Python identifiers "
        "and YAML keys (`przepisy_rezysera.py`, `prompt_systemowy`, "
        "`sufiks_pliku_wyniku`), the product brand \"Reżyser Audio GPT\", version "
        "numbers, and product names (`NVDA`, `ElevenReader`, `ElevenLabs`).\n"
        "3. **Closed-set values stay in English even when NOT frozen.** Where a "
        "prompt tells the engine's model to answer with one of a fixed set of "
        "values that an English-only publishing form accepts — `Yes` / `No` for "
        "mature content, the genre names, the target-audience names — those "
        "VALUES keep their English spelling (a Python validator matches them "
        "case-insensitively). The sentence around them is translated; the values "
        "are not. Same for the meta-slot text: `<Yes or No>` keeps `Yes`/`No`.\n"
        "4. **Whitespace is contractual.** The engine concatenates these strings, "
        "so preserve every line break, blank line and indentation exactly — "
        "including leading blank lines at the start of a string.\n"
        "5. **Emoji** — copy 1:1 and keep their position relative to the text.\n"
        "6. **Register.** Keep the second-person imperative voice of a prompt "
        "(\"You write…\", \"You never invent…\"). Write it the way a native prompt "
        "engineer of the target language would — do NOT calque Polish syntax or "
        "word order.\n"
        "7. **Content is fixed.** Do not add, drop, merge, split or reorder "
        "rules, sentences or blocks. No preamble, no commentary, no code fences.\n\n"
        "## Localization quality\n"
        "- REDUNDANT GLOSSES: the Polish source sometimes explains a "
        "foreign-language term for its Polish reader — `suomenruotsalaiset "
        "(Swedish-speaking Finns)`, `HSL (Helsingin seudun liikenne — Helsinki "
        "regional transport)`. If that term is NATIVE in the target language, the "
        "gloss becomes a tautology there: drop it and keep the term alone, or "
        "replace it with information the target reader actually lacks. Never "
        "produce `suomenruotsalaiset (ruotsinkieliset suomalaiset)`.\n"
        "- Use the established native terminology of the target language for "
        "software, audio and publishing concepts — the words a native product "
        "would use, not a word-for-word rendering of the Polish.\n"
        "- Stay CONSISTENT inside the batch: the GUI label, the prompt and the "
        "comments describing the same tool must use the same native term.\n"
        "- Grammatical correctness of the target language comes first: full "
        "diacritics, correct case/gender/number. For inflected languages "
        "(Icelandic, Finnish, Russian) anchor the declension to forms already "
        "present in the batch.\n\n"
        "## Response format\n"
        "Return ONLY valid JSON `{\"translations\": [...]}`."
    )


# ---------------------------------------------------------------------------
# Wywołanie LLM (jeden chunk, structured outputs) — maszyneria w `tlumacz_rdzen`
# ---------------------------------------------------------------------------
# Klient Anthropic, degradacja `temperature` (400 od Sonnet 5), guard ucięcia
# na `max_tokens` i parsowanie `id`→`target` są identyczne u wszystkich braci.
# Tutaj zostaje jedyna rzecz własna: prompt systemowy `_PROMPT_SYSTEMOWY`.
def _zainicjuj_klienta_anthropic() -> Any:
    return tlumacz_rdzen.zainicjuj_klienta_anthropic(ROOT)


def wywolaj_llm(
    klient: Any,
    model: str,
    nazwa_celu: str,
    kod: str,
    pozycje: list[tuple[int, str, str]],
) -> dict[int, str]:
    """Wysyła jeden chunk `(id, kind, source)`. Zwraca mapę id → target.

    Kontrakt błędów dziedziczony z rdzenia: `RuntimeError` = wpadka tego chunku
    (łapana wyżej, reszta języków leci dalej), `SystemExit` = sygnał
    konfiguracyjny (ucięcie limitem wyjścia — zmniejsz `BATCH_MAX_ZNAKOW`).
    """
    return tlumacz_rdzen.wywolaj_llm(
        klient,
        model=model,
        system=_PROMPT_SYSTEMOWY(nazwa_celu, kod),
        nazwa_celu=nazwa_celu,
        kod=kod,
        pozycje=pozycje,
        max_tokens=MAX_TOKENS_OUT,
        wskazowka_limitu=(
            f"Zmniejsz BATCH_MAX_ZNAKOW (obecnie {BATCH_MAX_ZNAKOW}) "
            f"i uruchom ponownie."
        ),
    )


# ---------------------------------------------------------------------------
# Jednostki tłumaczenia
# ---------------------------------------------------------------------------
# Rodzaj (`kind`) mówi MODELOWI, z czym ma do czynienia; klasa (`KLASA_*`) mówi
# BRAMCE, jak ostro walidować. Rozdzielone, bo mapa sufiksów kontekstowych
# (`sufiksy:`) to dla modelu ten sam materiał co prompt, a dla bramki — pole
# wymagające odcisku struktury, choć nie jest polem `prompt_*`.
RODZAJ_PER_KLASA: dict[str, str] = {
    KLASA_ETYKIETA: "label",
    KLASA_PROMPT: "prompt",
    KLASA_MAPA_TEKSTOW: "prompt",
    KLASA_MAPA_SLOW: "words",
    KLASA_SUFIKS: "filename_suffix",
}


# Jednostka (identyfikator, rodzaj dla modelu, klasa dla bramki, adres w drzewie)
# jest wspólna dla rodziny od v18.17 — patrz `tlumacz_rdzen.Jednostka`, które zna
# także adresy głębokie (`("sciezka", …)`) potrzebne bratu od Opowieści.
Jednostka = tlumacz_rdzen.Jednostka


def zbierz_jednostki_pol(drzewo: Any, sciezka_opisowa: str) -> list[Jednostka]:
    """Wyłuskuje z drzewa przepisu wszystkie jednostki tłumaczenia (bez komentarzy).

    Rzuca ``SystemExit`` na kluczu, którego nie ma w :data:`KLASY_POL` — nowe
    pole w PL musi przejść przez świadomą decyzję klasyfikacyjną, zanim
    tłumacz je zobaczy. Cicha kopia 1:1 byłaby polskim leakiem w 8 paczkach.
    """
    jednostki: list[Jednostka] = []
    nieznane = [k for k in drzewo.keys() if str(k) not in KLASY_POL]
    if nieznane:
        raise SystemExit(
            f"❌ {sciezka_opisowa}: unknown recipe fields: {nieznane}.\n"
            f"   Add each one to KLASY_POL in buduj_wielojezyczne_tryby.py "
            f"(techniczne / etykieta / prompt / mapa / sufiks / pochodna) — the "
            f"translator does not guess whether a field gets localized."
        )

    licznik = 0
    for klucz in drzewo.keys():
        klasa = KLASY_POL[str(klucz)]
        wartosc = drzewo[klucz]
        if klasa in (KLASA_TECHNICZNA, KLASA_POCHODNA):
            continue
        if klasa in (KLASA_ETYKIETA, KLASA_PROMPT, KLASA_SUFIKS):
            if not isinstance(wartosc, str) or not wartosc.strip():
                continue
            jednostki.append(Jednostka(
                licznik, RODZAJ_PER_KLASA[klasa], klasa, ("pole", str(klucz)), wartosc))
            licznik += 1
        elif klasa == KLASA_MAPA_TEKSTOW:
            for podklucz in list((wartosc or {}).keys()):
                tekst = wartosc[podklucz]
                if not isinstance(tekst, str) or not tekst.strip():
                    continue
                jednostki.append(Jednostka(
                    licznik, RODZAJ_PER_KLASA[klasa], klasa,
                    ("mapa", str(klucz), podklucz), tekst))
                licznik += 1
        elif klasa == KLASA_MAPA_SLOW:
            for podklucz in list((wartosc or {}).keys()):
                lista = wartosc[podklucz] or []
                for idx, slowo in enumerate(lista):
                    if not isinstance(slowo, str) or not slowo.strip():
                        continue
                    jednostki.append(Jednostka(
                        licznik, RODZAJ_PER_KLASA[klasa], klasa,
                        ("slowo", str(klucz), podklucz, idx), slowo))
                    licznik += 1
    return jednostki


_zachowaj_styl = tlumacz_rdzen.zachowaj_styl


def wstaw_jednostke(drzewo: Any, jednostka: Jednostka) -> None:
    """Wstawia przetłumaczoną wartość pod adres jednostki (mutuje drzewo)."""
    typ = jednostka.adres[0]
    if typ == "pole":
        klucz = jednostka.adres[1]
        if klucz not in drzewo:
            # Jedyny realny przypadek: `jezyk_odpowiedzi` dołożone jako jednostka,
            # bo źródło PL go nie ma ANI paczka docelowa nie ma siostrzanego
            # przepisu, z którego dałoby się je skopiować. Dopisujemy klucz.
            drzewo[klucz] = jednostka.cel
            return
        drzewo[klucz] = _zachowaj_styl(drzewo[klucz], jednostka.cel)
    elif typ == "mapa":
        _, klucz, podklucz = jednostka.adres
        drzewo[klucz][podklucz] = _zachowaj_styl(drzewo[klucz][podklucz], jednostka.cel)
    elif typ == "slowo":
        _, klucz, podklucz, idx = jednostka.adres
        lista = drzewo[klucz][podklucz]
        lista[idx] = _zachowaj_styl(lista[idx], jednostka.cel)


# ---------------------------------------------------------------------------
# Nagłówek pliku wynikowego (baner draftu)
# ---------------------------------------------------------------------------
# ŚWIADOMA RÓŻNICA wobec braci: kanoniczny przepis NIE dostaje banera „plik
# wygenerowany automatycznie, nie edytuj ręcznie". `rezyser/*.yaml` to plik
# EDYTOWALNY przez lingwistę w Managerze Reguł (i przez usera z prywatnym
# przepisem) — banner zakazujący edycji byłby kłamstwem wobec architektury.
# Dlatego draft dostaje baner do recenzji, a `--finalizuj` go ZDEJMUJE,
# zostawiając przetłumaczony nagłówek autorski (jak w paczkach pisanych ręcznie).
_NOTA_FINALIZACJI = (
    "# (After approval the maintainer runs\n"
    "# `buduj_wielojezyczne_tryby.py --finalizuj`, which just REMOVES this\n"
    "# banner and keeps everything below — including your manual fixes. This\n"
    "# file stays hand-editable afterwards: recipes are meant to be tuned by the\n"
    "# language pack's linguist in the in-app Rules Manager, so it never gets a\n"
    "# \"do not edit\" header. Do NOT re-run the translation: it would overwrite\n"
    "# the file and bring the hallucinations back.)\n"
)


def _baner_draftu(kod: str, nazwa_pliku: str) -> str:
    sciezka_rel = f"dictionaries/{kod}/{FOLDER_REZYSER}/{nazwa_pliku}"
    zrodlo_rel = f"dictionaries/{KOD_ZRODLOWY}/{FOLDER_REZYSER}/{nazwa_pliku}"
    return przeglad_tlumaczen.naglowek_roboczy(
        sciezka_rel, zrodlo_rel, "buduj_wielojezyczne_tryby.py",
        nota_finalizacji=_NOTA_FINALIZACJI)


zdejmij_baner_draftu = tlumacz_rdzen.zdejmij_baner_draftu


# ---------------------------------------------------------------------------
# WALIDACJA SILNIKIEM — najostrzejsza bramka (zero API)
# ---------------------------------------------------------------------------
# Bramki wcześniejsze pilnują TREŚCI jednostek. Ta sprawdza, czy z jednostek
# powstał plik, który silnik naprawdę wczyta i użyje tak samo jak polski
# (lekcja v18.9: zielone bramki treściowe ≠ działający plik).
_ATRYBUTY_TECHNICZNE = tuple(
    k for k, klasa in KLASY_POL.items() if klasa == KLASA_TECHNICZNA
)

# Spacja (także niełamliwa) przed dwukropkiem — typografia francuska.
_RE_SPACJA_PRZED_DWUKROPKIEM = re.compile(r"[   ]+:")


def _sprawdz_wartosci_zamkniete(
    nazwa: str, t_pl: str, t_cel: str, kod: str,
) -> list[str]:
    """Pilnuje `Yes`/`No` TYLKO w LINIACH Z KOTWICĄ POLA FORMULARZA.

    Dwa wcześniejsze podejścia były błędne i oba wyłapał test bojowy karty
    publikacyjnej — warto to zapisać, bo pułapka jest niebanalna:
      * liczenie w całym polu, case-insensitive → hiszpańskie „no" 16× wobec
        polskich 2×, poprawny plik odrzucony;
      * liczenie w całym polu z wielkością liter → hiszpańskie zdania
        zaczynające się od „No creas…" nadal dawały 5× wobec 2×.
    Wartość zamknięta ma znaczenie WYŁĄCZNIE tam, gdzie stoi obok nazwy pola
    formularza (`Mature content: <Yes albo No>`), bo tylko tę linię czyta potem
    `rezyser_ai._fragment_po_kotwicy`. Poza nią „no"/„No" to zwykłe słowo języka
    docelowego i nie jest naszą sprawą.
    """
    kotwice_pol = [k for k in _kotwice_z_silnika() if k.endswith(":")]
    if not kotwice_pol:
        return []

    def _linie_z_kotwica(tekst: str) -> str:
        return "\n".join(
            l for l in tekst.split("\n") if any(k in l for k in kotwice_pol))

    linie_pl, linie_cel = _linie_z_kotwica(t_pl), _linie_z_kotwica(t_cel)
    bledy: list[str] = []
    for slowo in _wartosci_slowne():
        rx = re.compile(rf"\b{re.escape(slowo)}\b")
        ile_pl, ile_cel = len(rx.findall(linie_pl)), len(rx.findall(linie_cel))
        if ile_pl and ile_pl != ile_cel:
            bledy.append(
                f"pole `{nazwa}`: wartość zamknięta {slowo!r} w linii pola "
                f"formularza (platforma przyjmuje ją tylko po angielsku) — "
                f"PL {ile_pl}×, {kod} {ile_cel}×"
            )
    return bledy


def _sprawdz_naglowki_struktury(
    nazwa: str, t_pl: str, t_cel: str, kod: str,
) -> list[str]:
    """Pilnuje CYTOWANYCH nazw nagłówków struktury (`„Rozdział 1"` w prompcie).

    Ta sama klasa błędu co rozjazd `regex_podzial_rozdzialow`, tylko trudniejsza
    do zauważenia: prompt tłumaczy modelowi, jakiego nagłówka ma się spodziewać
    w pliku projektu („Użytkownik przed każdą sekcją wstawi nagłówek np.
    «Rozdział 1»"). Nagłówek wpisuje tam silnik z `ui.yaml::rezyser.naglowek_*`,
    więc cytat MUSI używać dokładnie tego słowa dla paczki docelowej — swobodne
    tłumaczenie (albo, jak w propagacji `it`, zostawienie polskiego „Rozdział 1")
    każe modelowi szukać nagłówka, którego nigdy nie zobaczy.

    Liczy się WYŁĄCZNIE cytat, nie każde wystąpienie słowa (patrz
    :func:`_klucze_cytowanych_naglowkow`) — inaczej bramka krzyczy na prozę
    („Scena nie może dziać się w próżni" to zdanie o scenie, nie o nagłówku).
    Po stronie docelowej dopasowujemy PREFIKS słowa, nie całe słowo: fiński
    i islandzki odmieniają nagłówek w zdaniu („Epilogia", „Þáttarins"), a to
    jest poprawne.
    """
    zrodlowe = naglowki_struktury(KOD_ZRODLOWY)
    docelowe = naglowki_struktury(kod)
    if not zrodlowe or not docelowe:
        return []
    bledy: list[str] = []
    for klucz in _klucze_cytowanych_naglowkow(t_pl, zrodlowe):
        slowo_cel = docelowe.get(klucz)
        if not slowo_cel:
            continue
        if not re.search(rf"\b{re.escape(slowo_cel)}", t_cel, re.IGNORECASE):
            bledy.append(
                f"pole `{nazwa}`: cytat nagłówka struktury — PL cytuje "
                f"{zrodlowe[klucz]!r}, a {kod} nie zawiera {slowo_cel!r} "
                f"(ui.yaml::rezyser.{klucz}); model szukałby nagłówka, którego "
                f"silnik nie wpisuje"
            )
    return bledy


def _klucze_cytowanych_naglowkow(
    tekst: str, slowa_pl: dict[str, str],
) -> list[str]:
    """Zwraca klucze nagłówków CYTOWANYCH w tekście (nie zwykłych wzmianek).

    Cytat rozpoznajemy po kontekście, bo tylko on niesie kontrakt z silnikiem:
      * słowo w cudzysłowie albo nawiasie — `„Rozdział 1"`,
      * słowo z następującym numerem lub placeholderem — `Rozdział 1`,
      * słowo w liście rozdzielonej ukośnikami — `(Prolog/Akt/Scena/Epilog)`.
    Zwykła wzmianka w prozie („prosi o Epilog lub zakończenie") kontraktem nie
    jest — model niczego wtedy nie szuka w pliku.
    """
    znalezione: list[str] = []
    for klucz, slowo in slowa_pl.items():
        for m in re.finditer(rf"\b{re.escape(slowo)}\b", tekst):
            po = tekst[m.end():m.end() + 3]
            przed = tekst[max(0, m.start() - 1):m.start()]
            if (re.match(r"\s*[\d{]", po) or po.startswith("/")
                    or przed in "/„\"«(»"):
                znalezione.append(klucz)
                break
    return znalezione


def waliduj_silnikiem(
    kod: str, nazwa_pliku: str, dane_pl: dict, kotwice: list[str],
) -> list[str]:
    """Ładuje wynikowy przepis SILNIKIEM i porównuje z polskim. Zwraca listę błędów.

    Sprawdza kolejno:
      1. przepis wczytuje się (nie odpadł na walidacjach `_yaml_to_przepis`),
      2. pola techniczne identyczne z PL (id, dispatch, limity, kanony),
      3. `kod_jezyka` == paczka,
      4. zbiór placeholderów `{…}` w każdym polu tekstowym identyczny z PL,
      5. krotności kotwic identyczne z PL,
      6. `buduj_prompt_systemowy` składa się bez wyjątku i rozwija
         `{jezyk_odpowiedzi}`,
      7. `sufiks_pliku_wyniku` nie koliduje z innym przepisem tej paczki,
      8. paczka nadal jest KOMPLETNA dla silnika (`_jezyk_kompletny`).
    """
    bledy: list[str] = []
    import przepisy_rezysera as pr

    pr.DICTIONARIES_DIR = str(DICT_DIR)
    pr.wyczysc_cache()

    id_ = str(dane_pl.get("id", ""))
    kategoria = str(dane_pl.get("kategoria", ""))
    p_pl = pr.zaladuj_przepis(id_, KOD_ZRODLOWY, kategoria)
    p_cel = pr.zaladuj_przepis(id_, kod, kategoria)
    if p_pl is None:
        return [f"źródło PL nie wczytuje się jako przepis (id={id_!r}) — przerwana walidacja"]
    if p_cel is None:
        return [
            f"silnik ODRZUCIŁ wynikowy plik (zaladuj_przepis({id_!r}, {kod!r}) → None) "
            f"— sprawdź stderr powyżej: zakres/sufiks/typy pól"
        ]

    for atrybut in _ATRYBUTY_TECHNICZNE:
        if atrybut not in dane_pl:
            continue           # pole nieobecne w tym przepisie
        a, b = getattr(p_pl, atrybut, None), getattr(p_cel, atrybut, None)
        if a != b:
            bledy.append(f"pole techniczne `{atrybut}` rozjechało się: PL={a!r}, {kod}={b!r}")

    if p_cel.kod_jezyka != kod:
        bledy.append(f"`kod_jezyka`={p_cel.kod_jezyka!r} ≠ paczka {kod!r}")

    # Pola tekstowe: placeholdery i kotwice liczymy na WARTOŚCIACH Z DYSKU
    # (nie na jednostkach) — łapiemy też błąd wstawiania/dumpowania, nie tylko
    # kreatywność modelu.
    pary_tekstowe: list[tuple[str, str, str]] = []
    for klucz, klasa in KLASY_POL.items():
        if klasa not in (KLASA_ETYKIETA, KLASA_PROMPT):
            continue
        t_pl, t_cel = getattr(p_pl, klucz, ""), getattr(p_cel, klucz, "")
        if isinstance(t_pl, str) and t_pl.strip():
            pary_tekstowe.append((klucz, t_pl, t_cel if isinstance(t_cel, str) else ""))
    for nazwa_mapy in ("sufiksy",):
        mapa_pl = getattr(p_pl, nazwa_mapy, {}) or {}
        mapa_cel = getattr(p_cel, nazwa_mapy, {}) or {}
        for podklucz, t_pl in mapa_pl.items():
            pary_tekstowe.append(
                (f"{nazwa_mapy}.{podklucz}", t_pl, mapa_cel.get(podklucz, "")))

    for nazwa, t_pl, t_cel in pary_tekstowe:
        if not t_cel.strip():
            bledy.append(f"pole `{nazwa}` jest puste w {kod}, a niepuste w PL")
            continue
        ph_pl = set(PLACEHOLDER_REGEX.findall(t_pl))
        ph_cel = set(PLACEHOLDER_REGEX.findall(t_cel))
        if ph_pl != ph_cel:
            bledy.append(
                f"pole `{nazwa}`: zbiór placeholderów różny — brakuje "
                f"{sorted(ph_pl - ph_cel)}, nadmiar {sorted(ph_cel - ph_pl)}"
            )
        # Liczenie kotwic na tekście z ZNORMALIZOWANĄ spacją przed dwukropkiem:
        # francuski stawia ją zgodnie z własną typografią („Display mode :"),
        # co w prozie przypominającej userowi o polach formularza jest POPRAWNE
        # i nie może wywracać walidacji. Formę dosłowną, której naprawdę szuka
        # Python, egzekwuje osobno pętla `_kotwice_z_silnika` niżej.
        norm_pl, norm_cel = _RE_SPACJA_PRZED_DWUKROPKIEM.sub(":", t_pl), \
            _RE_SPACJA_PRZED_DWUKROPKIEM.sub(":", t_cel)
        for kotwica in kotwice:
            ile_pl, ile_cel = norm_pl.count(kotwica), norm_cel.count(kotwica)
            if ile_pl != ile_cel:
                bledy.append(
                    f"pole `{nazwa}`: kotwica {kotwica!r} — PL {ile_pl}×, "
                    f"{kod} {ile_cel}×"
                )
        # Kotwice silnika muszą wystąpić DOSŁOWNIE (bez spacji przed dwukropkiem)
        # przynajmniej raz — `rezyser_ai._fragment_po_kotwicy` szuka dokładnie
        # tego napisu w odpowiedzi modelu, a prompt jest jego jedynym wzorcem.
        for kotwica in _kotwice_z_silnika():
            if kotwica in t_pl and kotwica not in t_cel:
                bledy.append(
                    f"pole `{nazwa}`: kotwica walidatora {kotwica!r} nie występuje "
                    f"w {kod} w formie dosłownej — Python nie znajdzie tego pola "
                    f"w odpowiedzi modelu"
                )
        bledy += _sprawdz_wartosci_zamkniete(nazwa, t_pl, t_cel, kod)
        bledy += _sprawdz_naglowki_struktury(nazwa, t_pl, t_cel, kod)

    try:
        sysp = pr.buduj_prompt_systemowy(p_cel)
    except Exception as exc:  # noqa: BLE001 — dowolna wpadka składania = błąd pliku
        bledy.append(f"`buduj_prompt_systemowy` rzucił {type(exc).__name__}: {exc}")
    else:
        if "{jezyk_odpowiedzi}" in sysp:
            bledy.append("prompt systemowy: `{jezyk_odpowiedzi}` nie został rozwinięty")
        if pr.TAG_ODRZUCENIA_AI not in sysp:
            bledy.append(
                f"prompt systemowy: brak tagu {pr.TAG_ODRZUCENIA_AI} "
                f"(klauzula odrzucenia powinna go doklejać)"
            )

    if p_cel.sufiks_pliku_wyniku:
        for inny in pr.lista_postprodukcji(kod) + pr.lista_trybow(kod):
            if inny.id == p_cel.id:
                continue
            if inny.sufiks_pliku_wyniku == p_cel.sufiks_pliku_wyniku:
                bledy.append(
                    f"`sufiks_pliku_wyniku`={p_cel.sufiks_pliku_wyniku!r} koliduje "
                    f"z przepisem {inny.id!r} tej samej paczki"
                )

    # Kompletność paczki — plik dodany tylko do jednej bazy referencyjnej
    # odfiltrowuje OBA języki bazowe (mina z v18.10, patrz walidacja_audyt_hsl).
    try:
        import core_poliglota as cp
        cp.DICTIONARIES_DIR = str(DICT_DIR)
        if cp._jezyk_kompletny(kod) is not True:
            bledy.append(f"`core_poliglota._jezyk_kompletny({kod!r})` ≠ True — paczka niekompletna")
        if kod in (KOD_ZRODLOWY, KOD_ODNIESIENIA):
            bazowe = cp.dostepne_jezyki_bazowe()
            if not {KOD_ZRODLOWY, KOD_ODNIESIENIA} <= set(bazowe):
                bledy.append(
                    f"crosscheck baz referencyjnych zerwany — dostępne bazowe: {bazowe}")
    except ImportError as exc:
        print(f"⚠️  {kod}/{nazwa_pliku}: skipping the pack completeness check ({exc}).")

    return bledy


# ---------------------------------------------------------------------------
# Pipeline: jeden plik → jeden język
# ---------------------------------------------------------------------------
_yaml_io = tlumacz_rdzen.yaml_io


def _chunkuj(jednostki: list[Jednostka]) -> list[list[Jednostka]]:
    """Dzieli jednostki na porcje po ~:data:`BATCH_MAX_ZNAKOW` znaków źródła."""
    return tlumacz_rdzen.chunkuj(jednostki, BATCH_MAX_ZNAKOW)


def wczytaj_orakuly(
    przepisy: list[str], *, dopusc_drafty: bool = False,
) -> dict[str, dict[str, str]]:
    """Wczytuje pliki paczek odniesienia PRZED zapisem (implementacja w rdzeniu).

    Sens i dwa warunki bojowe (czytamy wszystko na wejściu; orakułem może być
    tylko plik PO recenzji) opisuje `tlumacz_rdzen.wczytaj_orakuly`. Tutaj
    zostaje samo wskazanie katalogu i podfolderu — `DICT_DIR` bywa przestawione
    przez `--slowniki` na instalację.
    """
    return tlumacz_rdzen.wczytaj_orakuly(
        DICT_DIR, FOLDER_REZYSER, przepisy,
        kod_zrodlowy=KOD_ZRODLOWY, dopusc_drafty=dopusc_drafty)


def tlumacz_plik(
    kod: str,
    nazwa_pliku: str,
    klient: Any,
    *,
    model: str,
    skip_existing: bool,
    dry_run: bool,
    kotwice_extra: tuple[str, ...],
    orakuly: dict[str, str],
) -> tuple[bool, list[Jednostka]]:
    """Tłumaczy jeden przepis na jeden język. Zwraca (sukces, jednostki).

    Nie zapisuje NICZEGO, dopóki wszystkie bramki nie przejdą; przy porażce
    walidacji silnikiem przywraca poprzednią treść pliku (albo go usuwa, jeśli
    powstał w tym przebiegu) — połowicznie przetłumaczony przepis w paczce
    byłby gorszy od jego braku, bo mógłby wypchnąć paczkę z listy kompletnych.
    """
    zrodlo = DICT_DIR / KOD_ZRODLOWY / FOLDER_REZYSER / nazwa_pliku
    cel = DICT_DIR / kod / FOLDER_REZYSER / nazwa_pliku
    if cel.exists() and skip_existing:
        print(f"⏭️  {kod}/{nazwa_pliku}: już istnieje — pomijam (--skip-existing).")
        return True, []

    yaml_io = _yaml_io()
    with open(zrodlo, "r", encoding="utf-8") as fh:
        tekst_zrodla = fh.read()
    drzewo_pl = yaml_io.load(tekst_zrodla)
    if not isinstance(drzewo_pl, dict):
        print(f"❌ {zrodlo}: the file does not parse into a YAML mapping.")
        return False, []
    dane_pl = {str(k): drzewo_pl[k] for k in drzewo_pl.keys()}

    # Dump PL-a jest ODNIESIENIEM LAYOUTU: komentarze wyciągamy z niego (nie
    # z pliku źródłowego), bo dump celu będzie miał identyczne komentarze
    # i identyczną ich kolejność — inaczej indeksowanie bloków mogłoby się rozjechać.
    buf = io.StringIO()
    yaml_io.dump(drzewo_pl, buf)
    dump_pl = buf.getvalue()
    bloki_pl = bloki_komentarzy(dump_pl, pomin_naglowek=False)
    koncowe_pl = komentarze_koncowe(dump_pl)

    # --- Jednostki -----------------------------------------------------------
    jednostki = zbierz_jednostki_pol(drzewo_pl, f"{KOD_ZRODLOWY}/{nazwa_pliku}")
    licznik = len(jednostki)
    for idx, blok in enumerate(bloki_pl):
        if not blok["tresc"].strip() or _RE_DEKORACJA.match(blok["tresc"]):
            continue
        jednostki.append(Jednostka(
            licznik, "comment", KLASA_ETYKIETA, ("komentarz", idx), blok["tresc"]))
        licznik += 1
    for idx, wpis in enumerate(koncowe_pl):
        jednostki.append(Jednostka(
            licznik, "comment", KLASA_ETYKIETA, ("komentarz_koncowy", idx), wpis["tresc"]))
        licznik += 1

    # `jezyk_odpowiedzi`: kopiujemy z siostrzanego przepisu paczki, a gdy paczka
    # jest pusta — dokładamy jednostkę i pytamy model o formę gramatyczną.
    jezyk_odp = jezyk_odpowiedzi_paczki(kod)
    if jezyk_odp is None:
        jednostki.append(Jednostka(
            licznik, "language_name", KLASA_ETYKIETA,
            ("pole", "jezyk_odpowiedzi"), str(dane_pl.get("jezyk_odpowiedzi", "polsku"))))
        licznik += 1
        print(f"ℹ️  {kod}: paczka nie ma jeszcze przepisu z `jezyk_odpowiedzi` "
              f"— pytam model o natywną formę.")

    # --- Kotwice -------------------------------------------------------------
    # Paczka docelowa nie jest orakułem dla samej siebie (tłumacząc `de` nie
    # bierzemy jej starej wersji za arbitra własnego tłumaczenia).
    odniesienia = {k: v for k, v in orakuly.items() if k != kod}
    kotwice = wykryj_kotwice(
        [j.zrodlo for j in jednostki], odniesienia, kotwice_extra)
    if not odniesienia:
        print(
            f"⚠️  {kod}/{nazwa_pliku}: no other pack has this recipe — the anchor "
            f"oracle is inactive, freezing ALL {len(kotwice)} candidates. The "
            f"reviewer must check whether any of them should have been "
            f"translated instead."
        )
    else:
        print(f"🔎 {kod}/{nazwa_pliku}: orakuł kotwic = jednomyślność paczek "
              f"{sorted(odniesienia)}.")

    for j in jednostki:
        j.zrodlo_tok, j.mapa = tokenizuj(j.zrodlo, kotwice)

    liczba_tokenow = sum(len(j.mapa) for j in jednostki)
    print(
        f"ℹ️  {kod}/{nazwa_pliku}: {len(jednostki)} jednostek "
        f"({sum(1 for j in jednostki if j.rodzaj == 'prompt')} promptów, "
        f"{sum(1 for j in jednostki if j.rodzaj == 'comment')} komentarzy), "
        f"{len(kotwice)} kotwic, {liczba_tokenow} zamrożeń, "
        f"{len(tekst_zrodla):,} znaków źródła."
    )

    if dry_run:
        print(f"    Kotwice ({len(kotwice)}): "
              + ", ".join(repr(k) for k in kotwice[:12])
              + (" …" if len(kotwice) > 12 else ""))
        for j in jednostki[:4]:
            print(f"      [{j.id}] {j.opis()} ({j.rodzaj}) → {j.zrodlo_tok[:110]!r}")
        print(f"    Chunków do wysłania: {len(_chunkuj(jednostki))}")
        print(f"    (dry-run) Nie wywołuję API, nie zapisuję {kod}/{nazwa_pliku}.")
        return True, []

    # --- Wywołania LLM -------------------------------------------------------
    nazwa_cel = _natywna_nazwa(kod)
    chunki = _chunkuj(jednostki)
    mapa_tgt: dict[int, str] = {}
    print(f"🌍 {kod}/{nazwa_pliku}: {model} (cel: {nazwa_cel}), {len(chunki)} chunk(ów)…")
    for nr, chunk in enumerate(chunki, start=1):
        pozycje = [(j.id, j.rodzaj, j.zrodlo_tok) for j in chunk]
        print(f"   {kod}: chunk {nr}/{len(chunki)} "
              f"(id {chunk[0].id}..{chunk[-1].id}, {len(chunk)} jednostek)…")
        try:
            mapa_tgt.update(wywolaj_llm(klient, model, nazwa_cel, kod, pozycje))
        except RuntimeError as exc:
            print(f"❌ {kod}/{nazwa_pliku}: LLM error in chunk {nr}/{len(chunki)} — {exc}")
            return False, []

    brakujace = {j.id for j in jednostki} - set(mapa_tgt)
    if brakujace:
        print(f"❌ {kod}/{nazwa_pliku}: the model skipped id {sorted(brakujace)[:20]} "
              f"(total {len(brakujace)}). NOT saving.")
        return False, []

    # --- Bramki per jednostka + jednorazowy retry ----------------------------
    porazki: list[tuple[Jednostka, list[str]]] = []
    for j in jednostki:
        j.cel = mapa_tgt[j.id]
        ok, problemy = waliduj_jednostke(j.zrodlo_tok, j.cel, j.klasa)
        if not ok:
            porazki.append((j, problemy))

    if porazki:
        print(f"⚠️  {kod}/{nazwa_pliku}: {len(porazki)} units queued for a retry…")
        for j, problemy in porazki[:6]:
            print(f"     [{j.id}] {j.opis()}: {problemy[0]}")
        do_retry = [(j.id, j.rodzaj, j.zrodlo_tok) for j, _ in porazki]
        try:
            retry = wywolaj_llm(klient, model, nazwa_cel, kod, do_retry)
        except RuntimeError as exc:
            print(f"❌ {kod}/{nazwa_pliku}: the retry failed — {exc}")
            return False, []
        zamowione = {j.id for j, _ in porazki}
        porazki_v2: list[tuple[Jednostka, list[str]]] = []
        for j, _ in porazki:
            if j.id in retry:
                j.cel = retry[j.id]
            ok, problemy = waliduj_jednostke(j.zrodlo_tok, j.cel, j.klasa)
            if not ok:
                porazki_v2.append((j, problemy))
        nieproszone = set(retry) - zamowione
        if nieproszone:
            print(f"⚠️  {kod}: the retry returned {len(nieproszone)} unrequested id "
                  f"— ignoring: {sorted(nieproszone)[:10]}")
        if porazki_v2:
            print(f"❌ {kod}/{nazwa_pliku}: after the retry {len(porazki_v2)} units "
                  f"still fail the gates. NOT saving.")
            for j, problemy in porazki_v2[:10]:
                print(f"     [{j.id}] {j.opis()} ({j.rodzaj})")
                for diag in problemy[:4]:
                    print(f"       • {diag}")
            return False, []
        print(f"✅ {kod}/{nazwa_pliku}: powtórka naprawiła wszystkie "
              f"{len(porazki)} jednostek.")

    # --- Detokenizacja + iniekcja do klona drzewa PL ------------------------
    for j in jednostki:
        j.cel = detokenizuj(j.cel, j.mapa)

    # Sufiks pliku wyniku: sanityzacja PRZED wstawieniem (idzie do nazwy pliku).
    for j in jednostki:
        if j.klasa == KLASA_SUFIKS:
            czysty, uwagi = sanityzuj_sufiks(j.cel)
            if czysty != j.cel:
                print(f"ℹ️  {kod}/{nazwa_pliku}: `{j.opis()}` → {czysty!r} "
                      f"({'; '.join(uwagi)})")
            j.cel = czysty

    drzewo_cel = yaml_io.load(dump_pl)
    for j in jednostki:
        if j.adres[0] in ("pole", "mapa", "slowo"):
            wstaw_jednostke(drzewo_cel, j)

    # Pola pochodne (bez LLM). Klucza BRAKUJĄCEGO w źródle NIE pomijamy — obie
    # deklaracje języka mają defaulty celujące w polski (`jezyk_odpowiedzi:
    # "polsku"`, `kod_jezyka: ""` → GUI zgaduje kod mikrorequestem LLM), więc
    # obca paczka bez nich odpowiadałaby po polsku albo losowała kod. Prywatne
    # przepisy usera bywają pisane skrótowo i realnie tych kluczy nie mają
    # (`postprod_audyt_hsl.yaml` w instalacji), dlatego dopisujemy je jawnie.
    for klucz, wartosc in (("kod_jezyka", kod), ("jezyk_odpowiedzi", jezyk_odp)):
        if wartosc is None:
            continue          # `jezyk_odpowiedzi` przyszło od modelu jako jednostka
        if klucz in drzewo_cel:
            drzewo_cel[klucz] = _zachowaj_styl(drzewo_cel[klucz], wartosc)
        else:
            drzewo_cel[klucz] = wartosc
            print(f"ℹ️  {kod}/{nazwa_pliku}: dopisano brakujące `{klucz}: {wartosc}` "
                  f"(źródło PL nie deklaruje tego pola).")
    if "regex_podzial_rozdzialow" in drzewo_cel:
        nowy_regex, uwagi_regex = wyprowadz_regex(
            str(drzewo_cel["regex_podzial_rozdzialow"]), kod)
        drzewo_cel["regex_podzial_rozdzialow"] = _zachowaj_styl(
            drzewo_cel["regex_podzial_rozdzialow"], nowy_regex)
        for uwaga in uwagi_regex:
            print(f"ℹ️  {kod}/{nazwa_pliku}: regex podziału — {uwaga}")

    # --- Dump + podmiana komentarzy ------------------------------------------
    buf = io.StringIO()
    yaml_io.dump(drzewo_cel, buf)
    dump_cel = buf.getvalue()

    bloki_cel = bloki_komentarzy(dump_cel, pomin_naglowek=False)
    koncowe_cel = komentarze_koncowe(dump_cel)
    if len(bloki_cel) != len(bloki_pl) or len(koncowe_cel) != len(koncowe_pl):
        print(f"❌ {kod}/{nazwa_pliku}: the comment layout drifted between the PL "
              f"and target dumps ({len(bloki_pl)}→{len(bloki_cel)} blocks, "
              f"{len(koncowe_pl)}→{len(koncowe_cel)} trailing). NOT saving.")
        return False, []

    tlum_bloki = {j.adres[1]: j.cel for j in jednostki if j.adres[0] == "komentarz"}
    tlum_koncowe = {
        j.adres[1]: j.cel for j in jednostki if j.adres[0] == "komentarz_koncowy"}

    linie = dump_cel.split("\n")
    # Od końca — podmiana bloku zmienia numerację linii poniżej.
    for idx in range(len(bloki_cel) - 1, -1, -1):
        blok_cel, blok_pl = bloki_cel[idx], bloki_pl[idx]
        if blok_cel["tresc"] != blok_pl["tresc"]:
            print(f"❌ {kod}/{nazwa_pliku}: comment block #{idx} in the target dump is "
                  f"not identical to PL — aborting (risk of inserting it in the wrong place).")
            return False, []
        if idx not in tlum_bloki:
            continue
        linie[blok_cel["start"]:blok_cel["koniec"]] = zloz_blok_komentarza(
            tlum_bloki[idx], blok_cel["wciecie"])
    dump_cel = "\n".join(linie)

    # Komentarze końcowe podmieniamy po ponownym wydobyciu (numeracja linii
    # zmieniła się przy blokach, ale kolejność wpisów nie).
    linie = dump_cel.split("\n")
    for idx, wpis in enumerate(komentarze_koncowe(dump_cel)):
        if idx not in tlum_koncowe:
            continue
        if wpis["tresc"] != koncowe_pl[idx]["tresc"]:
            # Kolejność wpisów się rozjechała — zostawiamy komentarz PL zamiast
            # wstawić tłumaczenie w niewłaściwą linię (komentarz to dokumentacja,
            # nie kontrakt: degradacja jest tu tańsza niż utrata pliku).
            print(f"⚠️  {kod}/{nazwa_pliku}: trailing comment #{idx} does not match "
                  f"PL — leaving the Polish one in place.")
            continue
        linie[wpis["linia"]] = (
            f"{wpis['przed']}{wpis['odstep']}# {tlum_koncowe[idx].strip()}")
    dump_cel = "\n".join(linie)

    zawartosc = _baner_draftu(kod, nazwa_pliku) + dump_cel

    # --- Zapis + walidacja silnikiem (z rollbackiem) -------------------------
    kopia = cel.read_text(encoding="utf-8") if cel.is_file() else None
    cel.parent.mkdir(parents=True, exist_ok=True)
    with open(cel, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(zawartosc)

    bledy = waliduj_silnikiem(kod, nazwa_pliku, dane_pl, kotwice)
    if bledy:
        print(f"❌ {kod}/{nazwa_pliku}: engine validation rejected the file "
              f"({len(bledy)} error(s)):")
        for b in bledy[:12]:
            print(f"     • {b}")
        if kopia is None:
            cel.unlink(missing_ok=True)
            print(f"     ↩ usunięto świeżo zapisany plik (paczka wraca do stanu przed).")
        else:
            cel.write_text(kopia, encoding="utf-8", newline="\n")
            print(f"     ↩ przywrócono poprzednią treść {cel.name}.")
        return False, []

    print(f"✅ {kod}/{nazwa_pliku}: zapisano {cel.relative_to(ROOT) if ROOT in cel.parents else cel} "
          f"DRAFT ({len(jednostki)} jednostek, {len(zawartosc):,} znaków).")
    return True, jednostki


# ---------------------------------------------------------------------------
# Post-processor: skan PL-leaków na świeżych draftach
# ---------------------------------------------------------------------------
zbierz_leaki = tlumacz_rdzen.zbierz_leaki


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _przepisy_zrodlowe() -> list[str]:
    """Nazwy plików przepisów w paczce PL (bez `baza.yaml`), alfabetycznie."""
    folder = DICT_DIR / KOD_ZRODLOWY / FOLDER_REZYSER
    if not folder.is_dir():
        raise SystemExit(f"❌ Missing source folder: {folder}")
    nazwy = [
        p.name for p in sorted(folder.glob("*.yaml"))
        if p.name not in PLIKI_POMIJANE
    ]
    if not nazwy:
        raise SystemExit(f"❌ Folder {folder} contains no recipe.")
    return nazwy


def _filtruj_przepisy(wszystkie: list[str], wybor_csv: str) -> list[str]:
    """Zawęża listę przepisów do CSV z `--przepisy` (bare-name dozwolony)."""
    if not wybor_csv.strip():
        return wszystkie
    wybrane: set[str] = set()
    for pozycja in wybor_csv.split(","):
        nazwa = pozycja.strip()
        if not nazwa:
            continue
        if not nazwa.endswith((".yaml", ".yml")):
            nazwa += ".yaml"
        wybrane.add(nazwa)
    nieznane = sorted(wybrane - set(wszystkie))
    if nieznane:
        raise SystemExit(
            f"❌ Unknown recipes: {nieznane}.\n"
            f"   Available in dictionaries/{KOD_ZRODLOWY}/{FOLDER_REZYSER}/: {wszystkie}"
        )
    return [n for n in wszystkie if n in wybrane]


def _parsuj_argumenty() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batch auto-translator for the Director recipes "
            f"(dictionaries/<code>/rezyser/*.yaml) into: {', '.join(MAPA_JEZYKOW)}. "
            "ruamel round-trip (comments and block scalars preserved), placeholder "
            "and anchor freezing, prompt structure-fingerprint gate, engine "
            "validation after saving."
        ),
    )
    grupa = parser.add_mutually_exclusive_group(required=True)
    grupa.add_argument(
        "-l", "--jezyki", type=str, default="",
        help=f"CSV of ISO codes (e.g. `de,fi`). Allowed: {', '.join(MAPA_JEZYKOW)}.")
    grupa.add_argument(
        "-a", "--wszystkie", action="store_true",
        help=f"All target languages ({', '.join(MAPA_JEZYKOW)}).")
    parser.add_argument(
        "-p", "--przepisy", type=str, default="",
        help="CSV of recipe names (e.g. `postprod_publikacja` or "
             "`tryb_burza.yaml`). Empty = every recipe in the PL pack. `baza.yaml` "
             "is always skipped (its anchor tags are identical in every pack).")
    parser.add_argument(
        "--slowniki", type=str, default="",
        help="Path to a `dictionaries` directory OTHER than the repo one — e.g. the "
             "pack of an installed application, where the user's private recipes "
             "live (user data, absent from the repo). Defaults to the repo directory.")
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip (language, recipe) pairs whose target file already exists.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only the split into units, anchors and tokens. No API calls.")
    parser.add_argument(
        "--model", default=MODEL_DOMYSLNY,
        help=f"Anthropic model used for the translation (default: {MODEL_DOMYSLNY}).")
    parser.add_argument(
        "--kotwica", type=str, default="", metavar="LITERAL[,LITERAL...]",
        help="Extra literals forced as anchors (frozen without asking the oracle). "
             "Useful when the recipe is not in the `en` reference pack yet — e.g. "
             "proper nouns of a private world. CAUTION: do NOT force a term that "
             "is a native word in the TARGET language (e.g. `suomenruotsalaiset` "
             "when translating into Finnish). A frozen nominative blocks inflection "
             "and cements a tautological gloss, and once the reviewer fixes it by "
             "hand, `--tylko-walidacja` reports a lost anchor — simply drop that "
             "literal from the next run.")
    parser.add_argument(
        "--orakul-drafty", action="store_true",
        help="Allow DRAFT packs to act as the anchor oracle. Needed when a recipe has "
             "just been propagated to N languages (all of them drafts) and you are "
             "now tuning the BASE pack against them — unanimity across N drafts is "
             "a better arbiter than the conservative mode, which would also freeze "
             "the Polish phrases that still need translating.")
    parser.add_argument(
        "--tylko-walidacja", action="store_true",
        help="No API: for the chosen languages/recipes runs ENGINE VALIDATION alone "
             "over the existing target files (technical fields, placeholders, "
             "anchors, pack completeness). Run it after every application upgrade "
             "when you work against an installation via `--slowniki`.")
    parser.add_argument(
        "-f", "--finalizuj", action="store_true",
        help="No API: strips the DRAFT banner from the chosen files, keeping the "
             "content (including the reviewer's manual fixes) and the translated "
             "author header. This is the right step once the review is accepted.")
    args = parser.parse_args()
    tryby_lokalne = sum(bool(x) for x in (args.finalizuj, args.tylko_walidacja))
    if tryby_lokalne and (args.skip_existing or args.dry_run):
        parser.error("--finalizuj / --tylko-walidacja to operacje lokalne (zero API) "
                     "— nie łącz ich z --skip-existing/--dry-run.")
    if tryby_lokalne > 1:
        parser.error("--finalizuj i --tylko-walidacja wykluczają się wzajemnie.")
    return args


def _wybierz_jezyki(args: argparse.Namespace) -> list[str]:
    if args.wszystkie:
        return list(MAPA_JEZYKOW.keys())
    kody = [k.strip() for k in args.jezyki.split(",") if k.strip()]
    nieznane = [k for k in kody if k not in MAPA_JEZYKOW]
    if nieznane:
        raise SystemExit(
            f"❌ Unknown language codes: {', '.join(nieznane)}.\n"
            f"   Allowed: {', '.join(MAPA_JEZYKOW)}."
        )
    return kody


def main() -> int:
    global DICT_DIR
    args = _parsuj_argumenty()

    if args.slowniki:
        DICT_DIR = Path(os.path.expandvars(args.slowniki)).expanduser().resolve()
        if not DICT_DIR.is_dir():
            print(f"❌ --slowniki: {DICT_DIR} is not a directory.")
            return 2
        print(f"📁 Katalog słowników: {DICT_DIR} (poza repo — tryb user-data).")

    kody = _wybierz_jezyki(args)
    przepisy = _filtruj_przepisy(_przepisy_zrodlowe(), args.przepisy)
    print(f"ℹ️  Przepisy do przetworzenia ({len(przepisy)}): {', '.join(przepisy)}")

    # --- Tryby lokalne (zero API) -------------------------------------------
    if args.finalizuj:
        zmienione = nie_drafty = braki = 0
        for kod in kody:
            for nazwa in przepisy:
                cel = DICT_DIR / kod / FOLDER_REZYSER / nazwa
                if not cel.is_file():
                    braki += 1
                    print(f"⚠️  {kod}/{nazwa}: the file does not exist — skipping.")
                    continue
                tresc, zdjeto = zdejmij_baner_draftu(cel.read_text(encoding="utf-8"))
                if not zdjeto:
                    nie_drafty += 1
                    print(f"⏭️  {kod}/{nazwa}: brak banera draftu — pomijam.")
                    continue
                cel.write_text(tresc, encoding="utf-8", newline="\n")
                zmienione += 1
                print(f"✅ {kod}/{nazwa}: baner draftu zdjęty (treść nietknięta).")
        print("\n========== SUMMARY (--finalizuj) ==========")
        print(f"✅ finalized: {zmienione} | ⏭️ already final: {nie_drafty} "
              f"| ⚠️ file missing: {braki}")
        return 0

    if args.tylko_walidacja:
        yaml_io = _yaml_io()
        wszystkie_bledy = 0
        for nazwa in przepisy:
            zrodlo = DICT_DIR / KOD_ZRODLOWY / FOLDER_REZYSER / nazwa
            with open(zrodlo, "r", encoding="utf-8") as fh:
                drzewo_pl = yaml_io.load(fh)
            dane_pl = {str(k): drzewo_pl[k] for k in drzewo_pl.keys()}
            jednostki = zbierz_jednostki_pol(drzewo_pl, f"{KOD_ZRODLOWY}/{nazwa}")
            odn = wczytaj_orakuly(
                [nazwa], dopusc_drafty=args.orakul_drafty).get(nazwa, {})
            extra = tuple(k.strip() for k in args.kotwica.split(",") if k.strip())
            for kod in kody:
                if not (DICT_DIR / kod / FOLDER_REZYSER / nazwa).is_file():
                    print(f"⚠️  {kod}/{nazwa}: no target file — skipping.")
                    continue
                # Kotwice liczone per język: walidowana paczka nie jest orakułem
                # dla samej siebie (inaczej każdy jej literał byłby „kotwicą").
                kotwice = wykryj_kotwice(
                    [j.zrodlo for j in jednostki],
                    {k: v for k, v in odn.items() if k != kod}, extra)
                bledy = waliduj_silnikiem(kod, nazwa, dane_pl, kotwice)
                wszystkie_bledy += len(bledy)
                if bledy:
                    print(f"❌ {kod}/{nazwa}: {len(bledy)} error(s)")
                    for b in bledy[:12]:
                        print(f"     • {b}")
                else:
                    print(f"✅ {kod}/{nazwa}: OK")
        print("\n========== SUMMARY (--tylko-walidacja) ==========")
        print("✅ No findings." if not wszystkie_bledy
              else f"❌ {wszystkie_bledy} error(s) in total.")
        return 1 if wszystkie_bledy else 0

    # --- Tłumaczenie ---------------------------------------------------------
    klient: Any = None if args.dry_run else _zainicjuj_klienta_anthropic()
    kotwice_extra = tuple(k.strip() for k in args.kotwica.split(",") if k.strip())
    if kotwice_extra:
        print(f"🔒 Kotwice wymuszone z CLI: {list(kotwice_extra)}")

    sukcesy: list[str] = []
    porazki: list[str] = []
    wytworzone: dict[tuple[str, str], list[Jednostka]] = {}
    kotwice_per_plik: dict[tuple[str, str], list[str]] = {}
    # Orakuły kotwic czytamy RAZ, przed jakimkolwiek zapisem (patrz `wczytaj_orakuly`).
    orakuly = wczytaj_orakuly(przepisy, dopusc_drafty=args.orakul_drafty)
    braki_orakulow = [n for n, t in orakuly.items() if not t]
    if braki_orakulow:
        print(f"⚠️  No reference pack has: {braki_orakulow} — for those files the "
              f"anchor oracle is inactive (conservative mode).")

    for kod in kody:
        print(f"\n========== {kod.upper()} "
              f"({MAPA_JEZYKOW[kod]} / {_natywna_nazwa(kod)}) ==========")
        wszystko_ok = True
        for nazwa in przepisy:
            ok, jednostki = tlumacz_plik(
                kod, nazwa, klient,
                model=args.model,
                skip_existing=args.skip_existing,
                dry_run=args.dry_run,
                kotwice_extra=kotwice_extra,
                orakuly=orakuly.get(nazwa, {}),
            )
            if not ok:
                wszystko_ok = False
            elif jednostki:
                wytworzone[(kod, nazwa)] = jednostki
                kotwice_per_plik[(kod, nazwa)] = wykryj_kotwice(
                    [j.zrodlo for j in jednostki], None, kotwice_extra)   # maska: nadzbiór
        (sukcesy if wszystko_ok else porazki).append(kod)

    if wytworzone:
        print("\n🔎 DRAFT: skan audyt_leakow na wytworzonych draftach…")
        leaki = zbierz_leaki(wytworzone, kotwice_per_plik)
        sciezka = przeglad_tlumaczen.zapisz_prompt_przegladu(
            "buduj_wielojezyczne_tryby.py", sorted(wytworzone.keys()), ROOT,
            leaki_per_plik=leaki,
        )
        if sciezka is not None:
            ile = sum(len(v) for per in leaki.values() for v in per.values())
            print(f"📋 DRAFT: checklista przeglądu → {sciezka.relative_to(ROOT)} "
                  f"({len(wytworzone)} plik(ów) do recenzji, {ile} kandydat(ów) na leak).")

    print("\n========== SUMMARY ==========")
    print(f"✅ Success: {len(sukcesy)}/{len(kody)}  ({', '.join(sukcesy) or '—'})")
    if porazki:
        print(f"❌ Failures (≥1 recipe failed): {', '.join(porazki)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
