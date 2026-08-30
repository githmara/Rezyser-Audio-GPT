#!/usr/bin/env python
"""
buduj_wielojezyczne_opowiesci.py — Batchowy autotłumacz PRZEPISÓW Opowieści (i18n).

Czwarty brat rodziny `buduj_wielojezyczne_*`: po interfejsie (`_ui.py`),
dokumentacji (`_docs.py`) i przepisach Reżysera (`_tryby.py`) bierze na siebie
`dictionaries/pl/opowiesci/*.yaml` — prompty silnika narracyjnego gry
interaktywnej. Materiał jest bliski bratu od Reżysera (`prompt_systemowy` to
PROMPT SYSTEMOWY dla innego modelu, więc grozi „meta instruction skip"), ale
schemat jest INNY i prostszy: brak pól pochodnych typu `regex_podzial_rozdzialow`
i `sufiks_pliku_wyniku`, w zamian dwa PODRZEWA — mechanika `fiolka` i presety
`zaczatki`.

Maszyneria (klient, zamrażanie, komentarze YAML, round-trip, drafty) mieszka we
wspólnym :mod:`tlumacz_rdzen`, bramki anty-meta-skip w :mod:`tlumacz_bramki`.
Tutaj zostaje wyłącznie wiedza o TYM materiale:

  1. KLASYFIKACJA PO ŚCIEŻCE (:data:`KLASY_SCIEZEK`) — nie po samym kluczu, bo
     ten schemat ma podrzewa: `fiolka.wagi_skutkow.*` jest techniczne, a
     `fiolka.opisy_skutkow.*.*` to proza. Ścieżka NIEZNANA to twardy błąd, nie
     cicha kopia (nowe pole w PL musi przejść przez decyzję „czy to się
     lokalizuje", zanim tłumacz je zobaczy).

  2. KOTWICE Z SILNIKA — klucze JSON-a tury wyprowadzane z
     `opowiesci_ai.SCHEMA_TURA` (rekurencyjnie, w formie cytowanej `"narracja"`),
     bloki payloadu fiolki, tag `[ODRZUCENIE_AI]` i marker Cinematic Meta
     Warningu. Python szuka ich w odpowiedzi modelu DOSŁOWNIE, więc prompt jest
     ich jedynym wzorcem.

  3. KONTRAKT ETYKIETY FIOLKI (bramka NOWA w v18.17) —
     `fiolka.etykieta_wyboru` jest cytowana DOSŁOWNIE **4×** w
     `prompt_systemowy` tego samego pliku (dziś zgadza się w 9/9 paczkach).
     To ta sama klasa kontraktu co `regex_podzial_rozdzialow` u brata, gdzie
     rozjazd żył niewykryty przez wiele wydań — dlatego bramka wchodzi PRZED
     pierwszym maszynowym tłumaczeniem, nie po rozjazdach.

  4. WARTOŚCI `etap_luku` JAKO POLE POCHODNE — `baza.yaml` cytuje w prompcie
     zbiór `ekspozycja|narastanie|kulminacja|rozwiazanie`, ale wszystkie osiem
     obcych paczek uzgodniło angielski kanon `exposition|rising_action|climax|
     resolution` (PL jest wyspą; Python tych wartości nie czyta — idą do `meta`
     w `.story.jsonl`). Zamiast pytać model, PODMIENIAMY zbiór na kanon paczek
     i zamrażamy go jako kotwicę.

  5. TERMINY KULTUROWE (:data:`TERMINY_KULTUROWE`) — opisy skutków fiolki
     cytują nazwy własne i terminy folklorystyczne (`Joulupukki`,
     `metsänpeitto`, `fylgja`). Autotłumacz chętnie podstawia lokalny
     odpowiednik (`Santa Claus`, `Дед Мороз`) — a to INNA postać i inna
     kultura. Terminu NIE zamrażamy (zamrożony mianownik zablokowałby odmianę,
     lekcja `--kotwica` z v18.15): bramka wymaga obecności RDZENIA, więc
     fińskie „Joulupukilta" przechodzi, a „Santa Claus" nie.

  6. TRYB `--fiolka` (lekki, surgical) — zakres wyłącznie
     `fiolka.opisy_skutkow.*` i tylko elementy BRAKUJĄCE w paczce docelowej
     (dopisywane na koniec puli, pozycyjnie zgodnie z PL). Istniejące,
     zrecenzowane tłumaczenia zostają nietknięte; drzewem bazowym jest plik
     DOCELOWY, nie klon PL. Prompt lekki (ziarno narracyjne, druga osoba,
     sensorycznie, mechaniczna konsekwencja zachowana), bramki bez odcisku
     szkieletu — to jednoakapitowa proza, nie prompt z nagłówkami.

Znane kosmetyki round-tripu (semantycznie bez znaczenia, ale widoczne w `git
diff` po propagacji — sprawdzone testem tożsamościowym na paczce PL):

  * block-scalar z wiodącą pustą linią dostaje jawny wskaźnik wcięcia
    (`|` → `|2`) — to samo zjawisko co w `_tryby.py`,
  * kolumnowe wyrównanie wartości w `fiolka.wagi_skutkow` znika (`harmful:
    0.6` zamiast `harmful:          0.6`); komentarze końcowe i wartości
    zostają nietknięte.

Zakres: `dictionaries/<kod>/opowiesci/`. `zaczatki.yaml` NIE wchodzi do
`--wszystkie` (patrz :data:`PLIKI_TYLKO_JAWNIE`) — presety Quick Start są
pisane RĘCZNIE per język, bo to literatura z lokalnymi motywami kulturowymi,
a nie i18n techniczne. Maszynowy przekład jest tam co najwyżej punktem
startowym dla lingwisty i wymaga jawnego `--przepisy zaczatki`.

Użycie:
  python buduj_wielojezyczne_opowiesci.py --wszystkie
  python buduj_wielojezyczne_opowiesci.py --jezyki de,fi --przepisy tryb_mniejsze_zlo
  python buduj_wielojezyczne_opowiesci.py --wszystkie --fiolka     # tylko nowe skutki
  python buduj_wielojezyczne_opowiesci.py --jezyki de --dry-run    # zero API
  python buduj_wielojezyczne_opowiesci.py --wszystkie --tylko-walidacja  # zero API
  python buduj_wielojezyczne_opowiesci.py --wszystkie --finalizuj       # zero API

Wymaga `ANTHROPIC_API_KEY` w `golden_key.env` (ten sam plik co GUI).
Moduł NIE zależy od wxPython — uruchamialny w CLI bez inicjalizacji GUI.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

import przeglad_tlumaczen
import tlumacz_bramki
import tlumacz_rdzen


tlumacz_rdzen.skonfiguruj_stdout()


# ---------------------------------------------------------------------------
# Ścieżki i zakres
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
# Katalog słowników jest ZMIENNY (`--slowniki`): ten sam pipeline obsługuje repo
# (seed) ORAZ zainstalowaną paczkę, w której żyją prywatne pliki usera.
DICT_DIR = ROOT / "dictionaries"

FOLDER_OPOWIESCI = "opowiesci"
KOD_ZRODLOWY = "pl"

# `zaczatki.yaml` — 5 presetów Quick Start. Własny nagłówek pliku: „KAŻDY preset
# jest pisany RĘCZNIE per język — to literatura, nie i18n techniczne. Język
# docelowy ma własne motywy kulturowe; nie kalkujemy z polskiego". Narzędzie
# potrafi je przetłumaczyć (przydatne przy NOWYM języku, żeby lingwista miał od
# czego zacząć), ale nigdy samo z siebie: trzeba podać `--przepisy zaczatki`.
PLIKI_TYLKO_JAWNIE = frozenset({"zaczatki.yaml"})


# ---------------------------------------------------------------------------
# Parametry wywołań LLM
# ---------------------------------------------------------------------------
# Największy plik (`tryb_mniejsze_zlo.yaml`, ~10 kB) mieści się w jednym
# wywołaniu, a model widzący pełny kontekst trzyma spójną terminologię między
# etykietą, promptem, opisami skutków i komentarzami. Tniemy dopiero, gdy suma
# źródeł chunku przekroczy próg — z zapasem pod cyrylicę i fińską aglutynację.
BATCH_MAX_ZNAKOW = 12_000
MAX_TOKENS_OUT = 16_000
MODEL_DOMYSLNY = "claude-sonnet-5"

MAPA_JEZYKOW: dict[str, str] = tlumacz_rdzen.wczytaj_mape_jezykow(
    ROOT, KOD_ZRODLOWY)


def _natywna_nazwa(kod: str) -> str:
    """Natywna nazwa celu (wrapper — `DICT_DIR` bywa przestawiony przez CLI)."""
    return tlumacz_rdzen.natywna_nazwa(DICT_DIR, kod)


# ---------------------------------------------------------------------------
# KLASYFIKACJA PÓL — PO ŚCIEŻCE, NIE PO KLUCZU
# ---------------------------------------------------------------------------
# Powód, dla którego brat od Reżysera wystarczał sobie płaską mapą kluczy, a tu
# jej nie ma: `fiolka` i `zaczatki` to PODRZEWA, w których ten sam klucz znaczy
# różne rzeczy w zależności od miejsca (`etykieta` na górze pliku to nazwa trybu
# w GUI, `zaczatki.<id>.etykieta` to nazwa presetu w liście Quick Start).
# `*` w wzorcu dopasowuje DOKŁADNIE JEDEN segment (klucz mapy albo indeks listy).
KLASA_TECHNICZNA = "techniczne"    # kopia 1:1 (id, dispatch, liczby, wagi)
KLASA_ETYKIETA = "etykieta"        # krótki napis GUI
KLASA_PROMPT = "prompt"            # prompt systemowy (odcisk struktury!)
KLASA_PROZA = "proza"              # wrapper/rama tekstowa doklejana przez silnik
KLASA_SKUTEK = "skutek_fiolki"     # ziarno narracyjne z puli fiolki
KLASA_ZIARNO = "ziarno_swiata"     # literatura presetu Quick Start
KLASA_KONTENER = "kontener"        # wchodzimy głębiej, sam węzeł się nie tłumaczy

KLASY_SCIEZEK: dict[str, str] = {
    # --- Techniczne: identyfikatory, dispatch silnika, parametry modelu
    "id": KLASA_TECHNICZNA,
    "kategoria": KLASA_TECHNICZNA,
    "kolejnosc": KLASA_TECHNICZNA,
    "model": KLASA_TECHNICZNA,
    "temperatura": KLASA_TECHNICZNA,
    "max_tokens": KLASA_TECHNICZNA,
    "timeout_s": KLASA_TECHNICZNA,
    # --- Krótkie napisy i długi prompt
    "etykieta": KLASA_ETYKIETA,
    "prompt_systemowy": KLASA_PROMPT,
    # --- Rama tekstowa wiadomości role=user (wyniesiona z hard-kodu Pythona,
    #     żeby jedna tura nie mieszała języków — patrz `opowiesci_ai`)
    "instrukcja_payload": KLASA_PROZA,
    "zasady_swiata_naglowek": KLASA_PROZA,
    "zasady_swiata_instrukcja": KLASA_PROZA,
    # --- Mechanika fiolki (tryb Mniejsze zło)
    "fiolka": KLASA_KONTENER,
    "fiolka.prog_aktywacji_tur": KLASA_TECHNICZNA,
    "fiolka.etykieta_wyboru": KLASA_ETYKIETA,
    "fiolka.wagi_skutkow": KLASA_KONTENER,
    "fiolka.wagi_skutkow.*": KLASA_TECHNICZNA,
    "fiolka.opisy_skutkow": KLASA_KONTENER,
    "fiolka.opisy_skutkow.*": KLASA_KONTENER,        # lista per kategoria
    "fiolka.opisy_skutkow.*.*": KLASA_SKUTEK,        # element puli
    # --- Presety Quick Start
    "zaczatki": KLASA_KONTENER,
    "zaczatki.*": KLASA_KONTENER,
    "zaczatki.*.etykieta": KLASA_ETYKIETA,
    "zaczatki.*.opis_krotki": KLASA_ZIARNO,
    "zaczatki.*.seed_swiata": KLASA_ZIARNO,
    "zaczatki.*.tryb_domyslny": KLASA_TECHNICZNA,
}

# `kind` mówi MODELOWI, z czym ma do czynienia; klasa mówi BRAMCE, jak ostro
# walidować. Rozdzielone, bo ziarno świata i opis skutku to dla bramki ta sama
# proza, a dla modelu dwa różne zadania pisarskie.
RODZAJ_PER_KLASA: dict[str, str] = {
    KLASA_ETYKIETA: "label",
    KLASA_PROMPT: "prompt",
    KLASA_PROZA: "prose",
    KLASA_SKUTEK: "vial_effect",
    KLASA_ZIARNO: "world_seed",
}

# Klasy, których treść jest materiałem SZTYWNYM (prompt/rama sklejana przez
# silnik) — tam naruszenia miękkie odcisku blokują zapis na równi z twardymi.
KLASY_SZTYWNE = frozenset({KLASA_PROMPT, KLASA_PROZA})


def klasa_sciezki(kroki: tuple) -> str | None:
    """Klasa dla ścieżki w drzewie. ``None`` = ścieżka NIEZNANA (twardy błąd).

    Dopasowanie dokładne ma priorytet nad wildcardem, żeby dopisanie
    `fiolka.opisy_skutkow.rare_beneficial` jako wyjątku nie wymagało zmiany
    reguły ogólnej.
    """
    segmenty = [str(k) for k in kroki]
    dokladna = ".".join(segmenty)
    if dokladna in KLASY_SCIEZEK:
        return KLASY_SCIEZEK[dokladna]
    for wzorzec, klasa in KLASY_SCIEZEK.items():
        czesci = wzorzec.split(".")
        if len(czesci) != len(segmenty):
            continue
        if all(c == "*" or c == s for c, s in zip(czesci, segmenty)):
            return klasa
    return None


# ---------------------------------------------------------------------------
# KOTWICE Z SILNIKA — literały, których Python szuka DOSŁOWNIE
# ---------------------------------------------------------------------------
# Marker Cinematic Meta Warningu. Silnik wycina nim blok z `.txt` przed TTS
# (`core_opowiesci._REGEX_META_WARNING`), więc prompt MUSI kazać modelowi
# emitować dokładnie ten ciąg emoji. Trzymamy literał tutaj i sprawdzamy niżej,
# że regex silnika naprawdę go używa — inaczej cicho rozjechalibyśmy się z nim.
MARKER_META_WARNING = "⚠️🚨⚠️"

# Bloki, które Python wstrzykuje do user payloadu fiolki (`_zbuduj_user_payload`)
# oraz gałąź stanu, po której czyta obecność fiolki (`czy_fiolka_powinna_sie_pojawic`).
_KLUCZE_PAYLOADU_FIOLKI = (
    "fiolka_aktywacja_w_tej_turze",
    "fiolka_efekt_seed",
    "stan.fiolka",
)


def _klucze_schematu(schemat: Any) -> set[str]:
    """Rekurencyjnie zbiera nazwy pól z JSON-schemy tury."""
    klucze: set[str] = set()
    if not isinstance(schemat, dict):
        return klucze
    wlasciwosci = schemat.get("properties")
    if isinstance(wlasciwosci, dict):
        for nazwa, pod in wlasciwosci.items():
            klucze.add(str(nazwa))
            klucze |= _klucze_schematu(pod)
    elementy = schemat.get("items")
    if isinstance(elementy, dict):
        klucze |= _klucze_schematu(elementy)
    return klucze


def _kotwice_z_silnika() -> tuple[str, ...]:
    """Literały, po których PYTHON odnajduje wartości w odpowiedzi modelu.

    Twarde źródła (nie heurystyka): `opowiesci_ai.SCHEMA_TURA` (walidacja
    `jsonschema` każdej tury — nazwa pola przetłumaczona na `Erzählung` znaczy
    turę odrzuconą), `przepisy_rezysera.TAG_ODRZUCENIA_AI` i marker
    Cinematic Meta Warningu.

    Klucze podajemy W FORMIE CYTOWANEJ (`"narracja"`), bo tak stoją w prompcie:
    goły `id` czy `meta` trafiłby w środek zwykłego słowa i rozjechał tekst.
    Fail-soft: gdy import silnika padnie (środowisko bez zależności), zostaje
    sama heurystyka kandydatów + orakuł jednomyślności, o czym mówimy w logu.
    """
    literaly: list[str] = [MARKER_META_WARNING]
    try:
        import opowiesci_ai
        import przepisy_rezysera
    except Exception as exc:  # noqa: BLE001 — dev-tool ma działać też bez silnika
        print(f"⚠️  Cannot import the Tales engine ({exc}) — JSON-key anchors "
              f"now rest on the heuristic + oracle alone.")
        return tuple(literaly)

    literaly.append(przepisy_rezysera.TAG_ODRZUCENIA_AI)
    literaly += [f'"{k}"' for k in sorted(_klucze_schematu(opowiesci_ai.SCHEMA_TURA))]
    literaly += list(_KLUCZE_PAYLOADU_FIOLKI)
    return tuple(literaly)


def sprawdz_marker_meta_warning() -> list[str]:
    """Czy :data:`MARKER_META_WARNING` zgadza się z regexem silnika?

    Kontrola spójności DEV-TOOLA ze silnikiem, nie treści paczki: gdyby ktoś
    zmienił markery w `core_opowiesci`, nasza kotwica zamrażałaby nieaktualny
    ciąg i przepuściła plik, którego filtr TTS już nie rozpoznaje.
    """
    try:
        import core_opowiesci
    except Exception:  # noqa: BLE001 — brak silnika obsłużony wyżej
        return []
    wzorzec = getattr(core_opowiesci, "_REGEX_META_WARNING", None)
    if wzorzec is None or MARKER_META_WARNING in wzorzec.pattern:
        return []
    return [
        f"marker Cinematic Meta Warningu {MARKER_META_WARNING!r} nie występuje "
        f"w `core_opowiesci._REGEX_META_WARNING` ({wzorzec.pattern!r}) — "
        f"zaktualizuj stałą w tym narzędziu"
    ]


# ---------------------------------------------------------------------------
# TERMINY KULTUROWE — nie podstawiać lokalnego odpowiednika
# ---------------------------------------------------------------------------
# Nazwy własne i terminy folklorystyczne z opisów skutków fiolki. Autotłumacz
# chętnie „pomaga", wstawiając rodzimy ekwiwalent (`Joulupukki` → `Santa Claus`
# / `Weihnachtsmann` / `Дед Мороз`) — a to INNA postać, z innym obyczajem, więc
# ziarno narracyjne przestaje znaczyć to, co znaczyło.
#
# Terminu NIE zamrażamy tokenem (lekcja `--kotwica` z v18.15: zamrożony
# mianownik blokuje odmianę i utrwala tautologiczny gloss). Zamiast tego bramka
# sprawdza obecność RDZENIA — fińskie „Joulupukilta" czy islandzkie
# „landvættinum" przechodzą, „Santa Claus" nie.
#
# Lista jest JAWNA i wymaga decyzji człowieka; nowy termin w PL (pogrubienie,
# którego tu nie ma) jest RAPORTOWANY, nie zgadywany.
TERMINY_KULTUROWE: dict[str, int] = {
    # termin → długość rdzenia sprawdzanego w tłumaczeniu (bez końcówek)
    "routa": 4,
    "móða": 3,             # is; w odmianie „móðu"
    "metsänpeitto": 9,     # fi; „metsänpeittoon", „metsänpeitossa"
    "fylgja": 5,           # is; „fylgjan", „fylgju"
    "landvættur": 8,       # is; „landvættinum", „landvættir"
    "Joulupukki": 9,       # fi; „Joulupukilta", „Joulupukin"
    "Korvatunturi": 10,    # fi; nazwa miejsca, „Korvatunturilta"
    "Mause": 5,            # nazwa własna firmy z żartu reklamowego
}

_RE_POGRUBIENIE = re.compile(r"\*\*(.+?)\*\*", re.S)


def terminy_w_tekscie(tekst: str) -> list[str]:
    """Terminy kulturowe obecne w tekście źródłowym (dopasowanie po rdzeniu)."""
    return [
        t for t, dl in TERMINY_KULTUROWE.items()
        if t.lower()[:dl] in tekst.lower()
    ]


def nowe_pogrubienia(tekst: str) -> list[str]:
    """Pogrubienia, których nie ma na liście terminów — kandydaci do decyzji.

    Świadomie tylko RAPORT: pogrubić można też zwykłe słowo („**zachowaj**"),
    a wymuszanie jego rdzenia w tłumaczeniu byłoby fałszywym alarmem. Recenzent
    (albo maintainer dopisujący nowe ziarno) decyduje, czy to termin.
    """
    znane = {t.lower() for t in TERMINY_KULTUROWE}
    obce: list[str] = []
    for m in _RE_POGRUBIENIE.finditer(tekst):
        fraza = m.group(1).strip()
        if fraza.lower() in znane or terminy_w_tekscie(fraza):
            continue
        obce.append(fraza)
    return obce


# ---------------------------------------------------------------------------
# POLE POCHODNE: zbiór wartości `etap_luku`
# ---------------------------------------------------------------------------
# `baza.yaml::prompt_systemowy` cytuje zamknięty zbiór etapów łuku. PL trzyma
# polskie wartości, ale WSZYSTKIE osiem obcych paczek uzgodniło angielskie —
# i to one są kanonem (Python wartości nie czyta, idą do `meta` w `.story.jsonl`,
# więc nie ma czego migrować, ale rozjazd wewnątrz paczek byłby czystym długiem).
# Dlatego zbiór jest POCHODNY: podmieniamy go przed tłumaczeniem i zamrażamy.
KANON_ETAPOW_FALLBACK = "exposition|rising_action|climax|resolution"
_RE_ETAPY = re.compile(r'"etap_luku":\s*"([^"]+)"')


def kanon_etapow_luku(kod_odniesienia: str = "en") -> str:
    """Zbiór etapów łuku z paczki odniesienia (single source, fallback: stała)."""
    plik = DICT_DIR / kod_odniesienia / FOLDER_OPOWIESCI / "baza.yaml"
    try:
        m = _RE_ETAPY.search(plik.read_text(encoding="utf-8"))
    except OSError:
        return KANON_ETAPOW_FALLBACK
    return m.group(1) if m else KANON_ETAPOW_FALLBACK


def podmien_etapy_luku(tekst: str, kanon: str) -> tuple[str, bool]:
    """Podmienia zbiór etapów łuku na kanon paczek. Zwraca (tekst, czy_podmieniono)."""
    m = _RE_ETAPY.search(tekst)
    if not m or m.group(1) == kanon:
        return tekst, False
    return tekst.replace(m.group(1), kanon), True


# ---------------------------------------------------------------------------
# PROMPT SYSTEMOWY TŁUMACZA — ANGIELSKI (jak u wszystkich braci)
# ---------------------------------------------------------------------------
# EN framing jest udokumentowaną decyzją projektu (neutralny dla wszystkich par
# językowych, nie kotwiczy modelu w polszczyźnie — audyt buildera UI 2026-06-16).
_RODZAJE_OPIS = (
    "- `prompt` — a multi-line SYSTEM PROMPT for the game's narrative engine. "
    "Preserve the skeleton EXACTLY: markdown headings (`#`, `###`), the "
    "numbering of rule lists, `**bold**` spans, blank lines, block order, and "
    "the JSON output-format block. As a rule of thumb: one source line = one "
    "target line.\n"
    "- `prose` — a short instruction or heading that the ENGINE glues onto the "
    "message it sends to the narrative model (or onto the player's own world "
    "rules). Keep it an instruction; keep its line breaks.\n"
    "- `label` — a short GUI label (a mode name, a button caption, the name of "
    "a Quick Start preset).\n"
    "- `vial_effect` — one NARRATIVE SEED from the vial mechanic: 1-3 sentences, "
    "second person singular, sensory, describing what happens to the player. "
    "It is a seed the narrative model expands, so keep the MECHANICAL "
    "CONSEQUENCE intact (how long it lasts, how many things are lost, who "
    "decides what) and keep it diegetic — never mention game mechanics, turns "
    "as game units, or the player as a player.\n"
    "- `world_seed` — literary opening material for a Quick Start preset "
    "(setting, characters with their accents, atmosphere). Write it as a native "
    "author of the target language would: keep the GENRE, the dramatic "
    "situation, the number of named characters and roughly the length, but let "
    "place names, personal names and cultural references be plausible for the "
    "target culture instead of transliterated Polish ones.\n"
    "- `comment` — YAML developer documentation (a comment block for the person "
    "maintaining this language pack). Translate it as documentation. Lines made "
    "up only of `=`, `-` or `*` are decoration: copy them unchanged, same "
    "length. Keep code identifiers, file names and YAML key names as they are. "
    "WRAP the prose at about 78 characters per line, the way the source block "
    "does — rewrap freely (line count may differ) but keep blank lines and the "
    "leading indentation of continuation lines.\n"
)

_ZASADY_TERMINOW = (
    "- CULTURAL TERMS AND PROPER NAMES stay THEMSELVES. When the source names a "
    "specific folkloric being, place or brand (e.g. Finnish `Joulupukki` from "
    "`Korvatunturi`, Icelandic `fylgja`, `landvættur`), do NOT swap in your "
    "language's nearest equivalent (`Santa Claus`, `Weihnachtsmann`, "
    "`Дед Мороз`, `guardian angel`): that is a DIFFERENT figure with different "
    "customs, and the seed would stop meaning what it means. You MAY inflect "
    "the term to fit the sentence grammatically — that is expected in Finnish, "
    "Icelandic and Russian. A parent script checks that the term's stem is "
    "still there.\n"
    "- REDUNDANT GLOSSES: the Polish source explains foreign terms for its "
    "Polish reader (`metsänpeitto: a place that stops accepting you`). If that "
    "term is NATIVE in the target language, the gloss becomes a tautology — "
    "drop it and let the term stand alone. Conversely, keep the gloss where the "
    "term is foreign to the target reader too.\n"
)


def _PROMPT_SYSTEMOWY(nazwa_celu: str, kod: str) -> str:
    """Prompt pełnego tłumaczenia pliku (tryb normalny)."""
    return (
        "# Role\n"
        "You are a senior localization engineer for a desktop wxPython "
        "application. You localize RECIPE FILES of an interactive-fiction "
        "engine: YAML files holding system prompts for a narrative AI, GUI "
        "labels, narrative seeds and developer comments. The source strings are "
        "in Polish.\n"
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
        "placeholders the engine fills in, JSON KEYS that Python validates the "
        "model's answer against, engine tags and payload field names. Copy every "
        "marker into `target` VERBATIM — same letters, same digits, same "
        "brackets — and exactly as many times as in `source`. Do NOT invent "
        "markers, do not renumber them, do not translate them. The sentence "
        "AROUND a marker is translated normally.\n"
        "2. **Do not translate** technical literals: AI model names "
        "(`claude-sonnet-5`, `Anthropic`), file and folder names and extensions "
        "(`opowiesci/`, `runtime/`, `baza.yaml`, `.txt`, `.jsonl`), Python "
        "identifiers and YAML keys (`opowiesci_ai.py`, `prompt_systemowy`, "
        "`prog_aktywacji_tur`), the product brand \"Reżyser Audio GPT\", version "
        "numbers, and the fixed category names of the vial mechanic "
        "(`harmful`, `distortion`, `rare_beneficial`).\n"
        "3. **The JSON schema of a game turn is a contract.** Key names inside "
        "the output-format block stay in their original spelling (they arrive "
        "frozen as markers); only the DESCRIPTIONS around them are translated. "
        "The same holds for the closed set of narrative-arc stages.\n"
        "4. **Whitespace is contractual.** The engine concatenates these "
        "strings, so preserve every line break, blank line and indentation "
        "exactly — including leading blank lines at the start of a string.\n"
        "5. **Emoji** — copy 1:1 and keep their position relative to the text. "
        "The warning marker made of emoji is a parsing anchor, not decoration.\n"
        "6. **Register.** These prompts speak to an AI in the second-person "
        "imperative (\"You are the narrative engine…\", \"You never break the "
        "fourth wall\"). Keep that voice, written the way a native prompt "
        "engineer of the target language would write it — do NOT calque Polish "
        "syntax or word order.\n"
        "7. **Content is fixed.** Do not add, drop, merge, split or reorder "
        "rules, sentences or blocks. No preamble, no commentary, no code fences.\n"
        "8. **The narrative voice is second-person singular.** The engine writes "
        "\"You walk\", \"You feel\" — where the target language distinguishes "
        "formal and informal address, use the INFORMAL one a novel would use.\n\n"
        "## Localization quality\n"
        + _ZASADY_TERMINOW +
        "- Use the established native terminology a published game or novel of "
        "the target language would use — not a word-for-word rendering.\n"
        "- Stay CONSISTENT inside the batch: the vial (its label, the prompt "
        "rules about it, the effect descriptions and the comments) must use ONE "
        "native word for the object, in every item.\n"
        "- **`existing_terminology` IN THE INPUT WINS.** When the payload "
        "carries that field, this language pack ALREADY ships those strings and "
        "its manual, readme and tutorials have used them for releases. REUSE "
        "them verbatim — same word for the vial, same mode name — instead of "
        "coining a better-sounding synonym. You cannot see the pack's other "
        "files; a fresh coinage would make the button say one thing and the "
        "manual another.\n"
        "- THE VIAL CHOICE LABEL IS A CONTRACT. The short label of the "
        "`Uncork the vial` choice appears BOTH as its own item AND quoted "
        "verbatim several times inside the mode's system prompt (in a JSON "
        "example, in the rule fixing its position, in the format examples). "
        "Translate it ONCE and then use that exact same wording — same letters, "
        "same case — in every single quotation. The engine shows the label to "
        "the player from one place and matches the model's output from another; "
        "two variants mean the choice stops working. A parent script counts the "
        "quotations and rejects the file if the count changes.\n"
        "- Grammatical correctness of the target language comes first: full "
        "diacritics, correct case/gender/number. For inflected languages "
        "(Icelandic, Finnish, Russian) anchor the declension to forms already "
        "present in the batch.\n\n"
        "## Response format\n"
        "Return ONLY valid JSON `{\"translations\": [...]}`."
    )


def _PROMPT_FIOLKA(nazwa_celu: str, kod: str) -> str:
    """Prompt lekki trybu `--fiolka` (same ziarna narracyjne).

    Osobny, bo pełny prompt pisze o strukturze markdownu, JSON-schemie i
    komentarzach YAML — czyli o rzeczach, których w tym zadaniu NIE MA. Model
    dostający listę reguł nie dotyczących materiału zaczyna ich szukać
    w tekście i „poprawiać" prozę pod nieistniejący szkielet.
    """
    return (
        "# Role\n"
        "You are a literary translator working on an interactive-fiction game "
        "for blind players. You translate NARRATIVE SEEDS: short descriptions "
        "of what happens when the player uncorks a mysterious vial. The source "
        "strings are in Polish.\n"
        f"Target language: **{nazwa_celu}** (ISO 639 code: {kod}).\n\n"
        + tlumacz_bramki.blok_anty_meta_skip(przewaga_promptow=False) + "\n"
        "## Task\n"
        "You receive a JSON object with an `items` field — a list of "
        "`{\"id\": int, \"kind\": str, \"source\": str}` objects, all of kind "
        "`vial_effect`. Translate each `source` and return JSON of the shape:\n"
        "  `{\"translations\": [{\"id\": int, \"target\": str}, ...]}`\n"
        "Each object MUST carry exactly the same `id` as the input.\n\n"
        "## What a seed is\n"
        "1-3 sentences, SECOND PERSON SINGULAR, sensory (sound, smell, touch, "
        "temperature — not only sight), informal address. The narrative AI "
        "expands the seed into a scene, so it must stay a seed: concrete, "
        "diegetic, unfinished.\n\n"
        "## Rules (a violation blocks the file from being written)\n"
        "1. **Keep the MECHANICAL CONSEQUENCE exactly.** How long the effect "
        "lasts, how many things are lost or helped, who decides what, whether "
        "it resolves the scene (it never does). If the source says the gift is "
        "useful for exactly one turn and takes nothing off the scene's weight, "
        "the translation says the same.\n"
        "2. **Never break the fourth wall.** No game mechanics, no "
        "probabilities, no addressing the player as a player. Where the source "
        "motivates a limit in-world (a craft rule of the being who grants it), "
        "keep that motivation in-world — do not turn it into a meta comment. "
        "The engine's base prompt forbids the fourth wall; a seed that breaks it "
        "would make the narrator break it too.\n"
        "3. **Markers ⟦P<n>⟧ / ⟦K<n>⟧** (if present) are frozen fragments: copy "
        "them verbatim, same count as in the source.\n"
        "4. **`**bold**` spans stay bold and stay on the same term.**\n"
        "5. Keep the length in the same ballpark as the source. Do not add a "
        "sentence, do not summarize, no commentary, no code fences.\n\n"
        "## Localization quality\n"
        + _ZASADY_TERMINOW +
        "- **TERMINOLOGY COMES FROM `existing_terminology` IN THE INPUT, not "
        "from your judgement.** That field carries strings this language pack "
        "already ships: the label of the \"uncork\" choice (e.g. German `Phiole "
        "entkorken`) and one already-translated effect per category. Mine them "
        "for the words this pack uses — for the VIAL, for a game TURN, for the "
        "player's INVENTORY, for a SCENE — and reuse those exact words "
        "(inflected as the sentence needs), even where you would have picked a "
        "different synonym. The pack's manual and its other effects have used "
        "them for releases, and you cannot see those files. Getting this wrong "
        "is the single most likely way to spoil an otherwise good translation.\n"
        "- Full diacritics, correct case/gender/number; for inflected languages "
        "inflect the cultural terms naturally instead of leaving bare "
        "nominatives.\n\n"
        "## Response format\n"
        "Return ONLY valid JSON `{\"translations\": [...]}`."
    )


# ---------------------------------------------------------------------------
# JEDNOSTKI TŁUMACZENIA
# ---------------------------------------------------------------------------
Jednostka = tlumacz_rdzen.Jednostka


def zbierz_jednostki_pol(
    drzewo: Any, sciezka_opisowa: str, *, licznik_od: int = 0,
) -> list[Jednostka]:
    """Wyłuskuje z drzewa wszystkie jednostki tłumaczenia (bez komentarzy).

    Rzuca ``SystemExit`` na ścieżce, której nie ma w :data:`KLASY_SCIEZEK` —
    nowe pole w PL musi przejść przez świadomą decyzję klasyfikacyjną, zanim
    tłumacz je zobaczy. Cicha kopia 1:1 byłaby polskim leakiem w ośmiu paczkach,
    którego żadna bramka nie widzi (twardy stop, wzorzec z `_tryby.py`).
    """
    jednostki: list[Jednostka] = []
    licznik = licznik_od
    nieznane: list[str] = []

    def zejdz(wezel: Any, kroki: tuple) -> None:
        nonlocal licznik
        if kroki:
            klasa = klasa_sciezki(kroki)
            if klasa is None:
                nieznane.append(".".join(str(k) for k in kroki))
                return
        else:
            klasa = KLASA_KONTENER
        if isinstance(wezel, dict):
            if kroki and klasa != KLASA_KONTENER:
                nieznane.append(".".join(str(k) for k in kroki) + " (mapa, a nie tekst)")
                return
            for klucz in list(wezel.keys()):
                zejdz(wezel[klucz], kroki + (str(klucz),))
            return
        if isinstance(wezel, list):
            if klasa != KLASA_KONTENER:
                nieznane.append(".".join(str(k) for k in kroki) + " (lista, a nie tekst)")
                return
            for idx in range(len(wezel)):
                zejdz(wezel[idx], kroki + (idx,))
            return
        # Liść.
        if klasa in (KLASA_TECHNICZNA, KLASA_KONTENER):
            return
        if not isinstance(wezel, str) or not wezel.strip():
            return
        jednostki.append(Jednostka(
            licznik, RODZAJ_PER_KLASA[klasa], klasa, ("sciezka",) + kroki, wezel))
        licznik += 1

    zejdz(drzewo, ())
    if nieznane:
        raise SystemExit(
            f"❌ {sciezka_opisowa}: unknown Tales recipe fields: {nieznane}.\n"
            f"   Add each one to KLASY_SCIEZEK in buduj_wielojezyczne_opowiesci.py "
            f"(techniczne / etykieta / prompt / proza / skutek_fiolki / "
            f"ziarno_swiata / kontener) — the translator does not guess whether "
            f"a field gets localized."
        )
    return jednostki


def waliduj_jednostke(src_tok: str, tgt: str, klasa: str) -> tuple[bool, list[str]]:
    """Bramka jednej jednostki: parzystość tokenów, odcisk, terminy kulturowe.

    Zwraca ``(ok, lista_diagnostyk)``. Odcisk struktury liczymy dla materiału
    sztywnego (prompt, rama tekstowa) ORAZ — w części twardej — dla prozy:
    ziarno, które wróciło jako ``{"narracja": …}``, to model, który WYKONAŁ
    tekst zamiast go przetłumaczyć, i to trzeba złapać wszędzie.
    """
    problemy = tlumacz_rdzen.parzystosc_tokenow(src_tok, tgt)

    twarde, miekkie = tlumacz_bramki.waliduj_odcisk(src_tok, tgt)
    problemy += twarde
    if klasa in KLASY_SZTYWNE or klasa == KLASA_SKUTEK:
        # Prompt i rama nie mają prawa „urosnąć" ani „schudnąć"; ziarno fiolki
        # też nie — jego długość i pogrubienia niosą treść mechaniczną.
        problemy += miekkie

    for termin in terminy_w_tekscie(src_tok):
        rdzen = termin.lower()[:TERMINY_KULTUROWE[termin]]
        if rdzen not in tgt.lower():
            problemy.append(
                f"termin kulturowy {termin!r} zniknął z tłumaczenia (szukam "
                f"rdzenia {rdzen!r}) — model prawdopodobnie podstawił lokalny "
                f"odpowiednik, a to inna postać/rzecz"
            )
    return (len(problemy) == 0), problemy


# ---------------------------------------------------------------------------
# NAGŁÓWEK PLIKU WYNIKOWEGO (baner draftu)
# ---------------------------------------------------------------------------
# ŚWIADOMA RÓŻNICA wobec `_ui.py`/`_docs.py`, wspólna z `_tryby.py`: kanoniczny
# przepis Opowieści NIE dostaje banera „plik wygenerowany automatycznie, nie
# edytuj ręcznie" — `opowiesci/*.yaml` jest EDYTOWALNY w Managerze Reguł (to
# jeden z pięciu folderów, które Manager skanuje). Zakaz edycji byłby kłamstwem
# wobec architektury, więc draft dostaje baner do recenzji, a `--finalizuj`
# go ZDEJMUJE, zostawiając przetłumaczony nagłówek autorski.
_NOTA_FINALIZACJI = (
    "# (After approval the maintainer runs\n"
    "# `buduj_wielojezyczne_opowiesci.py --finalizuj`, which just REMOVES this\n"
    "# banner and keeps everything below — including your manual fixes. This\n"
    "# file stays hand-editable afterwards: story recipes are meant to be tuned\n"
    "# by the language pack's linguist in the in-app Rules Manager, so it never\n"
    "# gets a \"do not edit\" header. Do NOT re-run the translation: it would\n"
    "# overwrite the file and bring the hallucinations back.)\n"
)


def _baner_draftu(kod: str, nazwa_pliku: str) -> str:
    sciezka_rel = f"dictionaries/{kod}/{FOLDER_OPOWIESCI}/{nazwa_pliku}"
    zrodlo_rel = f"dictionaries/{KOD_ZRODLOWY}/{FOLDER_OPOWIESCI}/{nazwa_pliku}"
    return przeglad_tlumaczen.naglowek_roboczy(
        sciezka_rel, zrodlo_rel, "buduj_wielojezyczne_opowiesci.py",
        nota_finalizacji=_NOTA_FINALIZACJI)


zdejmij_baner_draftu = tlumacz_rdzen.zdejmij_baner_draftu


# ---------------------------------------------------------------------------
# WALIDACJA SILNIKIEM — najostrzejsza bramka (zero API)
# ---------------------------------------------------------------------------
# Bramki wcześniejsze pilnują TREŚCI jednostek. Ta sprawdza, czy z jednostek
# powstał plik, który silnik naprawdę wczyta i użyje tak samo jak polski
# (lekcja v18.9: zielone bramki treściowe ≠ działający plik).
_POLA_TECHNICZNE = tuple(
    k for k, klasa in KLASY_SCIEZEK.items()
    if klasa == KLASA_TECHNICZNA and "." not in k
)

# Nazwa pliku → numer trybu w silniku (`opowiesci_ai._NAZWA_PLIKU_PER_TRYB`).
# `baza.yaml` sama trybem nie jest — walidujemy ją przez tryb Wyborów, który ją
# doklejа jako prefiks.
_TRYB_DLA_PLIKU: dict[str, int] = {
    "baza.yaml": 4,
    "tryb_swobodny.yaml": 3,
    "tryb_wyborow.yaml": 4,
    "tryb_mniejsze_zlo.yaml": 5,
    "tryb_burza.yaml": 0,
}


def _ustaw_silnik() -> Any:
    """Przestawia silnik Opowieści na :data:`DICT_DIR` i czyści jego cache.

    `opowiesci_ai` liczy ścieżki po `sciezki.KATALOG_BAZOWY` (repo), a my możemy
    pracować na `--slowniki` wskazującym instalację. `lru_cache` przepisów
    trzeba czyścić, bo w jednym przebiegu czytamy ten sam plik przed i po zapisie.
    """
    import opowiesci_ai
    opowiesci_ai.ROOT_DICT = DICT_DIR
    opowiesci_ai._zaladuj_przepis.cache_clear()
    return opowiesci_ai


def _sprawdz_kontrakt_etykiety_fiolki(
    kod: str, dane_pl: dict, dane_cel: dict,
) -> list[str]:
    """Etykieta wyboru `0` musi być cytowana w prompcie tyle razy, co w PL.

    KLASA KONTRAKTU, nie stylu: Python rozpoznaje wybór po `id="0"`, ale to
    prompt każe modelowi wypisać etykietę DOSŁOWNIE — a lista wyborów w GUI
    bierze napis z `fiolka.etykieta_wyboru`. Rozbieżność znaczy, że gracz widzi
    jeden napis, a model generuje inny; w trybach 4/5 wybór przestaje się
    mapować. Ta sama pułapka co `regex_podzial_rozdzialow` u brata, gdzie
    prolog przez wiele wydań nie był wykrywany w trzech paczkach — dlatego
    bramka wchodzi PRZED pierwszym maszynowym tłumaczeniem.
    """
    fiolka_pl = (dane_pl.get("fiolka") or {})
    fiolka_cel = (dane_cel.get("fiolka") or {})
    etykieta_pl = str(fiolka_pl.get("etykieta_wyboru", "")).strip()
    etykieta_cel = str(fiolka_cel.get("etykieta_wyboru", "")).strip()
    if not etykieta_pl:
        return []
    if not etykieta_cel:
        return [f"`fiolka.etykieta_wyboru` jest puste w {kod}, a niepuste w PL"]
    ile_pl = str(dane_pl.get("prompt_systemowy", "")).count(etykieta_pl)
    ile_cel = str(dane_cel.get("prompt_systemowy", "")).count(etykieta_cel)
    if ile_pl != ile_cel:
        return [
            f"KONTRAKT etykiety fiolki: PL cytuje {etykieta_pl!r} w prompcie "
            f"{ile_pl}×, a {kod} cytuje {etykieta_cel!r} {ile_cel}× — gracz "
            f"zobaczyłby inny napis, niż model wypisuje w `wybory[]`"
        ]
    return []


def _sprawdz_fiolke(kod: str, dane_pl: dict, dane_cel: dict) -> list[str]:
    """Parametry mechaniki fiolki: próg, wagi, długości pul, losowalność."""
    fiolka_pl = dane_pl.get("fiolka")
    if not isinstance(fiolka_pl, dict):
        return []
    fiolka_cel = dane_cel.get("fiolka")
    if not isinstance(fiolka_cel, dict):
        return [f"brak sekcji `fiolka` w {kod}, a PL ją ma"]

    bledy: list[str] = []
    if fiolka_pl.get("prog_aktywacji_tur") != fiolka_cel.get("prog_aktywacji_tur"):
        bledy.append(
            f"`fiolka.prog_aktywacji_tur`: PL={fiolka_pl.get('prog_aktywacji_tur')!r}, "
            f"{kod}={fiolka_cel.get('prog_aktywacji_tur')!r}"
        )
    wagi_pl = dict(fiolka_pl.get("wagi_skutkow") or {})
    wagi_cel = dict(fiolka_cel.get("wagi_skutkow") or {})
    if wagi_pl != wagi_cel:
        bledy.append(
            f"`fiolka.wagi_skutkow` rozjechały się: PL={wagi_pl}, {kod}={wagi_cel} "
            f"(rozkład prawdopodobieństwa jest mechaniką, nie treścią)"
        )
    pule_pl = fiolka_pl.get("opisy_skutkow") or {}
    pule_cel = fiolka_cel.get("opisy_skutkow") or {}
    if set(pule_pl) != set(pule_cel):
        bledy.append(
            f"`fiolka.opisy_skutkow`: kategorie różne — PL={sorted(pule_pl)}, "
            f"{kod}={sorted(pule_cel)}"
        )
    for kategoria, pula_pl in pule_pl.items():
        pula_cel = pule_cel.get(kategoria) or []
        if len(pula_pl) != len(pula_cel):
            bledy.append(
                f"`fiolka.opisy_skutkow.{kategoria}`: PL ma {len(pula_pl)} ziaren, "
                f"{kod} ma {len(pula_cel)} — rozkład skutków przestaje być ten sam"
            )
        for idx, ziarno in enumerate(pula_cel):
            if not isinstance(ziarno, str) or not ziarno.strip():
                bledy.append(
                    f"`fiolka.opisy_skutkow.{kategoria}[{idx}]` w {kod} jest puste")
    return bledy


def _sprawdz_zaczatki(kod: str, dane_pl: dict, dane_cel: dict) -> list[str]:
    """Presety Quick Start: te same klucze, ten sam tryb domyślny, nic puste.

    GUI (`gui_opowiesci`) buduje listę wyboru z KOLEJNOŚCI kluczy paczki i czyta
    z presetu `etykieta`, `seed_swiata` i `tryb_domyslny` — brak któregokolwiek
    to pusta pozycja na liście albo świat bez ziarna.
    """
    presety_pl = (dane_pl.get("zaczatki") or {})
    if not presety_pl:
        return []
    presety_cel = (dane_cel.get("zaczatki") or {})
    bledy: list[str] = []
    if set(presety_pl) != set(presety_cel):
        bledy.append(
            f"`zaczatki`: klucze presetów różne — PL={sorted(presety_pl)}, "
            f"{kod}={sorted(presety_cel)} (klucz jest identyfikatorem, nie treścią)"
        )
    for klucz, preset_pl in presety_pl.items():
        preset_cel = presety_cel.get(klucz) or {}
        if preset_pl.get("tryb_domyslny") != preset_cel.get("tryb_domyslny"):
            bledy.append(
                f"`zaczatki.{klucz}.tryb_domyslny`: PL="
                f"{preset_pl.get('tryb_domyslny')!r}, "
                f"{kod}={preset_cel.get('tryb_domyslny')!r}"
            )
        for pole in ("etykieta", "opis_krotki", "seed_swiata"):
            wartosc = preset_cel.get(pole)
            if not isinstance(wartosc, str) or not wartosc.strip():
                bledy.append(f"`zaczatki.{klucz}.{pole}` w {kod} jest puste")
    return bledy


def waliduj_silnikiem(
    kod: str, nazwa_pliku: str, dane_pl: dict, kotwice: list[str],
) -> list[str]:
    """Ładuje wynikowy przepis SILNIKIEM i porównuje z polskim.

    Sprawdza kolejno:
      1. plik istnieje w paczce (nie fallbackuje po cichu do `en`),
      2. pola techniczne identyczne z PL (id, kategoria, kolejność, parametry
         modelu),
      3. zbiór placeholderów `{…}` i krotności kotwic w każdym polu tekstowym,
      4. terminy kulturowe (rdzeń obecny) w ziarnach fiolki,
      5. zbiór wartości `etap_luku` = kanon paczek,
      6. mechanika fiolki + KONTRAKT etykiety wyboru,
      7. presety `zaczatki`,
      8. marker Cinematic Meta Warningu (liczba wystąpień jak w PL),
      9. `_zbuduj_prompt_systemowy` składa się, ma tag odrzucenia i nie zostawia
         nierozwiniętych `{…}`,
     10. paczka nadal jest KOMPLETNA dla silnika (`_jezyk_kompletny`) + crosscheck
         baz referencyjnych pl/en.
    """
    bledy: list[str] = []
    plik_cel = DICT_DIR / kod / FOLDER_OPOWIESCI / nazwa_pliku
    if not plik_cel.is_file():
        return [f"brak pliku {kod}/{FOLDER_OPOWIESCI}/{nazwa_pliku} — silnik "
                f"fallbackowałby na `en` (cichy rozjazd języka w grze)"]

    oai = _ustaw_silnik()
    rdzen = nazwa_pliku.rsplit(".", 1)[0]
    try:
        dane_cel = oai._zaladuj_przepis(kod, rdzen)
    except Exception as exc:  # noqa: BLE001 — dowolna wpadka ładowania = błąd pliku
        return [f"silnik nie wczytał pliku ({type(exc).__name__}: {exc})"]
    if not isinstance(dane_cel, dict) or not dane_cel:
        return ["silnik wczytał pusty przepis"]

    for pole in _POLA_TECHNICZNE:
        if pole not in dane_pl:
            continue
        if dane_pl.get(pole) != dane_cel.get(pole):
            bledy.append(
                f"pole techniczne `{pole}` rozjechało się: "
                f"PL={dane_pl.get(pole)!r}, {kod}={dane_cel.get(pole)!r}"
            )

    # Pola tekstowe: liczymy na WARTOŚCIACH Z DYSKU (nie na jednostkach) —
    # łapiemy też błąd wstawiania/dumpowania, nie tylko kreatywność modelu.
    kanon = kanon_etapow_luku()
    for jednostka in zbierz_jednostki_pol(dane_pl, f"{KOD_ZRODLOWY}/{nazwa_pliku}"):
        nazwa = jednostka.opis()
        t_pl = jednostka.zrodlo
        wartosc = tlumacz_rdzen.wartosc_po_sciezce(dane_cel, jednostka.kroki)
        t_cel = wartosc if isinstance(wartosc, str) else ""
        if not t_cel.strip():
            bledy.append(f"pole `{nazwa}` jest puste w {kod}, a niepuste w PL")
            continue
        ph_pl = set(tlumacz_rdzen.PLACEHOLDER_REGEX.findall(t_pl))
        ph_cel = set(tlumacz_rdzen.PLACEHOLDER_REGEX.findall(t_cel))
        if ph_pl != ph_cel:
            bledy.append(
                f"pole `{nazwa}`: zbiór placeholderów różny — brakuje "
                f"{sorted(ph_pl - ph_cel)}, nadmiar {sorted(ph_cel - ph_pl)}"
            )
        t_pl_kanon, _ = podmien_etapy_luku(t_pl, kanon)
        for kotwica in kotwice:
            ile_pl = t_pl_kanon.count(kotwica)
            ile_cel = t_cel.count(kotwica)
            if ile_pl != ile_cel:
                bledy.append(
                    f"pole `{nazwa}`: kotwica {kotwica!r} — PL {ile_pl}×, "
                    f"{kod} {ile_cel}×"
                )
        if _RE_ETAPY.search(t_pl):
            etapy_cel = _RE_ETAPY.search(t_cel)
            znalezione = etapy_cel.group(1) if etapy_cel else None
            if znalezione != kanon:
                bledy.append(
                    f"pole `{nazwa}`: zbiór etapów łuku w {kod} to "
                    f"{znalezione!r}, a kanon paczek to {kanon!r} "
                    f"(pole POCHODNE, nie tłumaczone)"
                )
        for termin in terminy_w_tekscie(t_pl):
            rdzen_terminu = termin.lower()[:TERMINY_KULTUROWE[termin]]
            if rdzen_terminu not in t_cel.lower():
                bledy.append(
                    f"pole `{nazwa}`: termin kulturowy {termin!r} nie ma w {kod} "
                    f"nawet rdzenia {rdzen_terminu!r} — podstawiony lokalny "
                    f"odpowiednik znaczy co innego"
                )

    bledy += _sprawdz_fiolke(kod, dane_pl, dane_cel)
    bledy += _sprawdz_kontrakt_etykiety_fiolki(kod, dane_pl, dane_cel)
    bledy += _sprawdz_zaczatki(kod, dane_pl, dane_cel)

    ile_markerow_pl = str(dane_pl.get("prompt_systemowy", "")).count(MARKER_META_WARNING)
    if ile_markerow_pl:
        ile_markerow_cel = str(
            dane_cel.get("prompt_systemowy", "")).count(MARKER_META_WARNING)
        if ile_markerow_pl != ile_markerow_cel:
            bledy.append(
                f"marker {MARKER_META_WARNING} — PL {ile_markerow_pl}×, "
                f"{kod} {ile_markerow_cel}×; filtr TTS wycina blok po tych "
                f"emoji, więc gracz usłyszałby meta-komentarz"
            )

    tryb = _TRYB_DLA_PLIKU.get(nazwa_pliku)
    if tryb is not None:
        try:
            sysp = oai._zbuduj_prompt_systemowy(tryb, kod)
        except Exception as exc:  # noqa: BLE001
            bledy.append(
                f"`_zbuduj_prompt_systemowy({tryb}, {kod!r})` rzucił "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            import przepisy_rezysera as pr
            if pr.TAG_ODRZUCENIA_AI not in sysp:
                bledy.append(
                    f"złożony prompt systemowy trybu {tryb} nie zawiera "
                    f"{pr.TAG_ODRZUCENIA_AI} (klauzula odrzucenia)"
                )
            nierozwiniete = set(tlumacz_rdzen.PLACEHOLDER_REGEX.findall(sysp))
            if nierozwiniete:
                bledy.append(
                    f"złożony prompt systemowy trybu {tryb} ma nierozwinięte "
                    f"placeholdery: {sorted(nierozwiniete)}"
                )

    try:
        import core_poliglota as cp
        cp.DICTIONARIES_DIR = str(DICT_DIR)
        if cp._jezyk_kompletny(kod) is not True:
            bledy.append(
                f"`core_poliglota._jezyk_kompletny({kod!r})` ≠ True — paczka niekompletna")
        if kod in (KOD_ZRODLOWY, "en"):
            bazowe = cp.dostepne_jezyki_bazowe()
            if not {KOD_ZRODLOWY, "en"} <= set(bazowe):
                bledy.append(
                    f"crosscheck baz referencyjnych zerwany — dostępne bazowe: {bazowe}")
    except ImportError as exc:
        print(f"⚠️  {kod}/{nazwa_pliku}: skipping the pack completeness check ({exc}).")

    return bledy


# ---------------------------------------------------------------------------
# PIPELINE: jeden plik → jeden język
# ---------------------------------------------------------------------------
_yaml_io = tlumacz_rdzen.yaml_io


def _chunkuj(jednostki: list[Jednostka]) -> list[list[Jednostka]]:
    """Dzieli jednostki na porcje po ~:data:`BATCH_MAX_ZNAKOW` znaków źródła."""
    return tlumacz_rdzen.chunkuj(jednostki, BATCH_MAX_ZNAKOW)


def wczytaj_orakuly(
    pliki: list[str], *, dopusc_drafty: bool = False,
) -> dict[str, dict[str, str]]:
    """Wczytuje pliki paczek odniesienia PRZED zapisem (implementacja w rdzeniu)."""
    return tlumacz_rdzen.wczytaj_orakuly(
        DICT_DIR, FOLDER_OPOWIESCI, pliki,
        kod_zrodlowy=KOD_ZRODLOWY, dopusc_drafty=dopusc_drafty)


def kontekst_paczki(
    kod: str, nazwa_pliku: str, *, z_ziarnami: bool = False,
) -> dict[str, str]:
    """Terminologia, którą paczka docelowa JUŻ ma (pusta, gdy pliku nie ma).

    Model nie widzi sąsiednich plików paczki, więc nazwę fiolki wymyśla za
    każdym razem od nowa. Test bojowy v18.17 pokazał, do czego to prowadzi:
    świeży przekład `de` nazwał ją „Fläschchen", choć `readme`, `tales`
    i `dictionaries` tej paczki od wydań mówią „Phiole" — paczka zaczęłaby
    mówić dwoma głosami, a gracz zobaczyłby w przycisku inne słowo niż
    w podręczniku. Dlatego istniejące napisy podajemy modelowi JAWNIE, z
    instrukcją „użyj ponownie, nie wymyślaj".

    ``z_ziarnami=True`` (tryb `--fiolka`) dokłada po jednym ISTNIEJĄCYM ziarnie
    z każdej kategorii. Tam model dostaje wyłącznie nowe opisy, więc nie ma
    skąd wziąć terminologii mechanicznej — a właśnie na niej poległ test bojowy
    `is` (termin tury `umferð` zamieniony na `skipti`, ekwipunek `eigur` na
    `farangur`). Ziarno-przykład jest najtańszym możliwym słownikiem: pokazuje
    te słowa w naturalnym zdaniu i w odpowiednim przypadku.
    """
    plik = DICT_DIR / kod / FOLDER_OPOWIESCI / nazwa_pliku
    if not plik.is_file():
        return {}
    try:
        dane = YAML(typ="safe").load(plik.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — fail-soft: wskazówka to wygoda, nie bramka
        return {}
    if not isinstance(dane, dict):
        return {}
    wynik: dict[str, str] = {}
    etykieta = dane.get("etykieta")
    if isinstance(etykieta, str) and etykieta.strip():
        wynik["mode_label"] = etykieta.strip()
    fiolka = dane.get("fiolka") or {}
    etykieta_fiolki = fiolka.get("etykieta_wyboru")
    if isinstance(etykieta_fiolki, str) and etykieta_fiolki.strip():
        wynik["vial_choice_label"] = etykieta_fiolki.strip()
    if z_ziarnami:
        for kategoria, pula in (fiolka.get("opisy_skutkow") or {}).items():
            if isinstance(pula, list) and pula and isinstance(pula[0], str):
                wynik[f"existing_effect_{kategoria}"] = pula[0].strip()
    return wynik


def _wywolaj(
    klient: Any, model: str, nazwa_celu: str, kod: str,
    pozycje: list[tuple[int, str, str]], *, tryb_fiolka: bool,
    kontekst: dict[str, str] | None = None,
) -> dict[int, str]:
    """Jedno wywołanie LLM z promptem właściwym dla trybu."""
    system = (_PROMPT_FIOLKA if tryb_fiolka else _PROMPT_SYSTEMOWY)(nazwa_celu, kod)
    return tlumacz_rdzen.wywolaj_llm(
        klient,
        model=model,
        system=system,
        nazwa_celu=nazwa_celu,
        kod=kod,
        pozycje=pozycje,
        max_tokens=MAX_TOKENS_OUT,
        wskazowka_limitu=(
            f"Zmniejsz BATCH_MAX_ZNAKOW (obecnie {BATCH_MAX_ZNAKOW}) "
            f"i uruchom ponownie."
        ),
        kontekst_paczki=kontekst,
    )


def _brakujace_ziarna_fiolki(
    drzewo_pl: Any, drzewo_cel: Any,
) -> list[tuple[tuple, str]]:
    """Ziarna fiolki obecne w PL, a brakujące w paczce docelowej.

    Zwraca listę ``(kroki_docelowe, tekst_pl)``. Porównujemy DŁUGOŚCIĄ PULI,
    nie treścią: paczki są pozycyjnie zgodne z PL (5/5/3 od v15.2), więc
    „brakujące" = elementy o indeksie ≥ długość puli docelowej. Dopisujemy je na
    KONIEC puli, zachowując pozycyjność — istniejące, zrecenzowane tłumaczenia
    zostają nietknięte, bo tryb `--fiolka` jest surgical z definicji.
    """
    braki: list[tuple[tuple, str]] = []
    pule_pl = (drzewo_pl.get("fiolka") or {}).get("opisy_skutkow") or {}
    fiolka_cel = drzewo_cel.get("fiolka") or {}
    pule_cel = fiolka_cel.get("opisy_skutkow") or {}
    for kategoria in pule_pl:
        pula_pl = pule_pl[kategoria] or []
        pula_cel = pule_cel.get(kategoria)
        ile_cel = len(pula_cel) if pula_cel is not None else 0
        for idx in range(ile_cel, len(pula_pl)):
            tekst = pula_pl[idx]
            if isinstance(tekst, str) and tekst.strip():
                braki.append((("fiolka", "opisy_skutkow", kategoria, idx), tekst))
    return braki


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
    tryb_fiolka: bool = False,
) -> tuple[bool, list[Jednostka]]:
    """Tłumaczy jeden plik na jeden język. Zwraca (sukces, jednostki).

    Nie zapisuje NICZEGO, dopóki wszystkie bramki nie przejdą; przy porażce
    walidacji silnikiem przywraca poprzednią treść pliku (albo go usuwa, jeśli
    powstał w tym przebiegu) — połowicznie przetłumaczony przepis byłby gorszy
    od jego braku, bo mógłby wypchnąć paczkę z listy kompletnych.

    W trybie ``tryb_fiolka`` drzewem bazowym jest plik DOCELOWY (a nie klon PL)
    i tłumaczymy wyłącznie brakujące ziarna puli — patrz
    :func:`_brakujace_ziarna_fiolki`.
    """
    zrodlo = DICT_DIR / KOD_ZRODLOWY / FOLDER_OPOWIESCI / nazwa_pliku
    cel = DICT_DIR / kod / FOLDER_OPOWIESCI / nazwa_pliku
    if cel.exists() and skip_existing and not tryb_fiolka:
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
    kanon = kanon_etapow_luku()

    if tryb_fiolka:
        return _tlumacz_fiolke(
            kod, nazwa_pliku, klient, model=model, dry_run=dry_run,
            drzewo_pl=drzewo_pl, dane_pl=dane_pl, yaml_io=yaml_io,
            kotwice_extra=kotwice_extra, orakuly=orakuly, kanon=kanon)

    # Dump PL-a jest ODNIESIENIEM LAYOUTU: komentarze wyciągamy z niego (nie
    # z pliku źródłowego), bo dump celu będzie miał identyczne komentarze
    # i identyczną ich kolejność — inaczej indeksowanie bloków mogłoby się rozjechać.
    buf = io.StringIO()
    yaml_io.dump(drzewo_pl, buf)
    dump_pl = buf.getvalue()
    bloki_pl = tlumacz_rdzen.bloki_komentarzy(dump_pl, pomin_naglowek=False)
    koncowe_pl = tlumacz_rdzen.komentarze_koncowe(dump_pl)

    # --- Jednostki -----------------------------------------------------------
    jednostki = zbierz_jednostki_pol(drzewo_pl, f"{KOD_ZRODLOWY}/{nazwa_pliku}")
    licznik = len(jednostki)
    for idx, blok in enumerate(bloki_pl):
        if not blok["tresc"].strip() or tlumacz_rdzen.RE_DEKORACJA.match(blok["tresc"]):
            continue
        jednostki.append(Jednostka(
            licznik, "comment", KLASA_ETYKIETA, ("komentarz", idx), blok["tresc"]))
        licznik += 1
    for idx, wpis in enumerate(koncowe_pl):
        jednostki.append(Jednostka(
            licznik, "comment", KLASA_ETYKIETA,
            ("komentarz_koncowy", idx), wpis["tresc"]))
        licznik += 1

    # --- Pole pochodne: zbiór etapów łuku PRZED tokenizacją ------------------
    for j in jednostki:
        nowe, podmieniono = podmien_etapy_luku(j.zrodlo, kanon)
        if podmieniono:
            j.zrodlo = nowe
            print(f"ℹ️  {kod}/{nazwa_pliku}: `{j.opis()}` — zbiór etapów łuku "
                  f"podmieniony na kanon paczek {kanon!r} (pole pochodne).")

    # --- Kotwice -------------------------------------------------------------
    # Paczka docelowa nie jest orakułem dla samej siebie (tłumacząc `de` nie
    # bierzemy jej starej wersji za arbitra własnego tłumaczenia).
    odniesienia = {k: v for k, v in orakuly.items() if k != kod}
    wymuszone = kotwice_extra + (kanon,)
    kotwice = wykryj_kotwice([j.zrodlo for j in jednostki], odniesienia, wymuszone)
    if not odniesienia:
        print(
            f"⚠️  {kod}/{nazwa_pliku}: no other pack has this file — the anchor "
            f"oracle is inactive, freezing ALL {len(kotwice)} candidates. The "
            f"reviewer must check whether any of them should have been "
            f"translated instead."
        )
    else:
        print(f"🔎 {kod}/{nazwa_pliku}: orakuł kotwic = jednomyślność paczek "
              f"{sorted(odniesienia)}.")

    for j in jednostki:
        j.zrodlo_tok, j.mapa = tlumacz_rdzen.tokenizuj(j.zrodlo, kotwice)

    # Raport TYLKO dla ziaren fiolki: tam pogrubienie niesie termin kulturowy.
    # W prompcie systemowym `**bold**` jest zwykłym wyróżnieniem prozy
    # („**drugiej osobie…**") i lista kandydatów byłaby czystym szumem.
    nowe_terminy = sorted({
        fraza for j in jednostki if j.klasa == KLASA_SKUTEK
        for fraza in nowe_pogrubienia(j.zrodlo)
    })
    if nowe_terminy:
        print(f"ℹ️  {kod}/{nazwa_pliku}: pogrubienia poza listą TERMINY_KULTUROWE "
              f"({len(nowe_terminy)}): {nowe_terminy[:6]}"
              + (" …" if len(nowe_terminy) > 6 else "")
              + " — jeśli któreś jest nazwą własną albo terminem folkloru, dopisz "
                "je do listy w tym skrypcie.")

    print(
        f"ℹ️  {kod}/{nazwa_pliku}: {len(jednostki)} jednostek "
        f"({sum(1 for j in jednostki if j.rodzaj == 'prompt')} promptów, "
        f"{sum(1 for j in jednostki if j.rodzaj == 'vial_effect')} ziaren fiolki, "
        f"{sum(1 for j in jednostki if j.rodzaj == 'comment')} komentarzy), "
        f"{len(kotwice)} kotwic, {sum(len(j.mapa) for j in jednostki)} zamrożeń, "
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
    kontekst = kontekst_paczki(kod, nazwa_pliku)
    if kontekst:
        print(f"🔤 {kod}/{nazwa_pliku}: terminologia paczki podana modelowi: "
              f"{kontekst}")
    chunki = _chunkuj(jednostki)
    mapa_tgt: dict[int, str] = {}
    print(f"🌍 {kod}/{nazwa_pliku}: {model} (cel: {nazwa_cel}), {len(chunki)} chunk(ów)…")
    for nr, chunk in enumerate(chunki, start=1):
        pozycje = [(j.id, j.rodzaj, j.zrodlo_tok) for j in chunk]
        print(f"   {kod}: chunk {nr}/{len(chunki)} "
              f"(id {chunk[0].id}..{chunk[-1].id}, {len(chunk)} jednostek)…")
        try:
            mapa_tgt.update(_wywolaj(klient, model, nazwa_cel, kod, pozycje,
                                     tryb_fiolka=False, kontekst=kontekst))
        except RuntimeError as exc:
            print(f"❌ {kod}/{nazwa_pliku}: LLM error in chunk {nr}/{len(chunki)} — {exc}")
            return False, []

    brakujace = {j.id for j in jednostki} - set(mapa_tgt)
    if brakujace:
        print(f"❌ {kod}/{nazwa_pliku}: the model skipped id {sorted(brakujace)[:20]} "
              f"(total {len(brakujace)}). NOT saving.")
        return False, []

    if not _bramki_z_powtorka(jednostki, mapa_tgt, kod, nazwa_pliku, klient,
                              model, nazwa_cel, tryb_fiolka=False,
                              kontekst=kontekst):
        return False, []

    # --- Detokenizacja + iniekcja do klona drzewa PL ------------------------
    for j in jednostki:
        j.cel = tlumacz_rdzen.detokenizuj(j.cel, j.mapa)

    drzewo_cel = yaml_io.load(dump_pl)
    for j in jednostki:
        if j.adres[0] == "sciezka":
            tlumacz_rdzen.wstaw_po_sciezce(drzewo_cel, j.kroki, j.cel)

    # --- Dump + podmiana komentarzy ------------------------------------------
    buf = io.StringIO()
    yaml_io.dump(drzewo_cel, buf)
    dump_cel = buf.getvalue()
    dump_cel = _podmien_komentarze(
        dump_cel, jednostki, bloki_pl, koncowe_pl, kod, nazwa_pliku)
    if dump_cel is None:
        return False, []

    zawartosc = _baner_draftu(kod, nazwa_pliku) + dump_cel
    if not _zapisz_z_walidacja(cel, zawartosc, kod, nazwa_pliku, dane_pl, kotwice):
        return False, []
    print(f"✅ {kod}/{nazwa_pliku}: zapisano DRAFT "
          f"({len(jednostki)} jednostek, {len(zawartosc):,} znaków).")
    return True, jednostki


def _tlumacz_fiolke(
    kod: str,
    nazwa_pliku: str,
    klient: Any,
    *,
    model: str,
    dry_run: bool,
    drzewo_pl: Any,
    dane_pl: dict,
    yaml_io: YAML,
    kotwice_extra: tuple[str, ...],
    orakuly: dict[str, str],
    kanon: str,
) -> tuple[bool, list[Jednostka]]:
    """Tryb `--fiolka`: dopisuje BRAKUJĄCE ziarna puli do istniejącej paczki.

    Świadomie NIE tyka niczego innego: ani prompta, ani komentarzy, ani ziaren
    już przetłumaczonych. Dlatego drzewem bazowym jest plik DOCELOWY — pełne
    tłumaczenie zdeptałoby recenzję, którą ta paczka już przeszła.
    """
    cel = DICT_DIR / kod / FOLDER_OPOWIESCI / nazwa_pliku
    if not cel.is_file():
        print(f"⚠️  {kod}/{nazwa_pliku}: no target file — the --fiolka mode appends "
              f"seeds to an EXISTING pack. Do the full translation first.")
        return False, []

    with open(cel, "r", encoding="utf-8") as fh:
        tekst_celu = fh.read()
    drzewo_cel = yaml_io.load(tekst_celu)
    if not isinstance(drzewo_cel, dict):
        print(f"❌ {cel}: the file does not parse into a YAML mapping.")
        return False, []

    braki = _brakujace_ziarna_fiolki(drzewo_pl, drzewo_cel)
    if not braki:
        print(f"⏭️  {kod}/{nazwa_pliku}: pule ziaren są już równe PL — nic do zrobienia.")
        return True, []

    jednostki = [
        Jednostka(i, RODZAJ_PER_KLASA[KLASA_SKUTEK], KLASA_SKUTEK,
                  ("sciezka",) + kroki, tekst)
        for i, (kroki, tekst) in enumerate(braki)
    ]

    odniesienia = {k: v for k, v in orakuly.items() if k != kod}
    kotwice = wykryj_kotwice(
        [j.zrodlo for j in jednostki], odniesienia, kotwice_extra + (kanon,))
    for j in jednostki:
        j.zrodlo_tok, j.mapa = tlumacz_rdzen.tokenizuj(j.zrodlo, kotwice)

    nowe_terminy = sorted({f for j in jednostki for f in nowe_pogrubienia(j.zrodlo)})
    print(f"ℹ️  {kod}/{nazwa_pliku}: {len(jednostki)} nowych ziaren fiolki "
          f"({', '.join(sorted({str(k[2]) for k, _ in braki}))}), "
          f"{len(kotwice)} kotwic.")
    if nowe_terminy:
        print(f"    Pogrubienia poza listą TERMINY_KULTUROWE: {nowe_terminy}")

    if dry_run:
        for j in jednostki:
            print(f"      [{j.id}] {j.opis()} → {j.zrodlo_tok[:110]!r}")
        print(f"    (dry-run) Nie wywołuję API, nie zapisuję {kod}/{nazwa_pliku}.")
        return True, []

    nazwa_cel = _natywna_nazwa(kod)
    kontekst = kontekst_paczki(kod, nazwa_pliku, z_ziarnami=True)
    print(f"🧪 {kod}/{nazwa_pliku}: {model} (cel: {nazwa_cel}), tryb --fiolka "
          f"(fiolka w tej paczce: {kontekst.get('vial_choice_label', '—')!r}, "
          f"{sum(1 for k in kontekst if k.startswith('existing_effect_'))} ziaren "
          f"jako wzorzec terminologii)…")
    try:
        mapa_tgt = _wywolaj(
            klient, model, nazwa_cel, kod,
            [(j.id, j.rodzaj, j.zrodlo_tok) for j in jednostki],
            tryb_fiolka=True, kontekst=kontekst)
    except RuntimeError as exc:
        print(f"❌ {kod}/{nazwa_pliku}: LLM error — {exc}")
        return False, []

    brakujace_id = {j.id for j in jednostki} - set(mapa_tgt)
    if brakujace_id:
        print(f"❌ {kod}/{nazwa_pliku}: the model skipped id {sorted(brakujace_id)}. "
              f"NOT saving.")
        return False, []

    if not _bramki_z_powtorka(jednostki, mapa_tgt, kod, nazwa_pliku, klient,
                              model, nazwa_cel, tryb_fiolka=True,
                              kontekst=kontekst):
        return False, []

    for j in jednostki:
        j.cel = tlumacz_rdzen.detokenizuj(j.cel, j.mapa)

    # Dopisujemy na koniec właściwej puli — pozycyjność wobec PL zachowana.
    pule = drzewo_cel["fiolka"]["opisy_skutkow"]
    for j in jednostki:
        kategoria = j.kroki[2]
        if pule.get(kategoria) is None:
            pule[kategoria] = []
        pule[kategoria].append(j.cel)

    buf = io.StringIO()
    yaml_io.dump(drzewo_cel, buf)
    # Nagłówka NIE doklejamy: round-trip ruamel wczytał go razem z drzewem
    # (wiodące komentarze wracają w dumpie 1:1) i doklejenie zdublowałoby cały
    # blok — złapane testem ścieżki zapisu przed pierwszym opłaconym callem.
    # Skutek uboczny jest tu POŻĄDANY: nagłówek pliku docelowego zostaje taki,
    # jaki był (kanoniczny albo draft), bo surgical update nie zmienia statusu
    # finalizacji — wzorzec `--klucz` z v18.6.
    zawartosc = buf.getvalue()
    if not _zapisz_z_walidacja(cel, zawartosc, kod, nazwa_pliku, dane_pl, kotwice):
        return False, []
    print(f"✅ {kod}/{nazwa_pliku}: dopisano {len(jednostki)} ziaren fiolki "
          f"(nagłówek i reszta pliku nietknięte).")
    return True, jednostki


def _bramki_z_powtorka(
    jednostki: list[Jednostka],
    mapa_tgt: dict[int, str],
    kod: str,
    nazwa_pliku: str,
    klient: Any,
    model: str,
    nazwa_cel: str,
    *,
    tryb_fiolka: bool,
    kontekst: dict[str, str] | None = None,
) -> bool:
    """Bramki per jednostka + jednorazowa powtórka z czystym kontekstem."""
    porazki: list[tuple[Jednostka, list[str]]] = []
    for j in jednostki:
        j.cel = mapa_tgt[j.id]
        ok, problemy = waliduj_jednostke(j.zrodlo_tok, j.cel, j.klasa)
        if not ok:
            porazki.append((j, problemy))
    if not porazki:
        return True

    print(f"⚠️  {kod}/{nazwa_pliku}: {len(porazki)} units queued for a retry…")
    for j, problemy in porazki[:6]:
        print(f"     [{j.id}] {j.opis()}: {problemy[0]}")
    do_retry = [(j.id, j.rodzaj, j.zrodlo_tok) for j, _ in porazki]
    try:
        retry = _wywolaj(klient, model, nazwa_cel, kod, do_retry,
                         tryb_fiolka=tryb_fiolka, kontekst=kontekst)
    except RuntimeError as exc:
        print(f"❌ {kod}/{nazwa_pliku}: the retry failed — {exc}")
        return False
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
        return False
    print(f"✅ {kod}/{nazwa_pliku}: powtórka naprawiła wszystkie "
          f"{len(porazki)} jednostek.")
    return True


def _podmien_komentarze(
    dump_cel: str,
    jednostki: list[Jednostka],
    bloki_pl: list[dict],
    koncowe_pl: list[dict],
    kod: str,
    nazwa_pliku: str,
) -> str | None:
    """Wstawia przetłumaczone komentarze do dumpu. ``None`` = rozjazd layoutu."""
    bloki_cel = tlumacz_rdzen.bloki_komentarzy(dump_cel, pomin_naglowek=False)
    koncowe_cel = tlumacz_rdzen.komentarze_koncowe(dump_cel)
    if len(bloki_cel) != len(bloki_pl) or len(koncowe_cel) != len(koncowe_pl):
        print(f"❌ {kod}/{nazwa_pliku}: the comment layout drifted between the PL "
              f"and target dumps ({len(bloki_pl)}→{len(bloki_cel)} blocks, "
              f"{len(koncowe_pl)}→{len(koncowe_cel)} trailing). NOT saving.")
        return None

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
            return None
        if idx not in tlum_bloki:
            continue
        linie[blok_cel["start"]:blok_cel["koniec"]] = \
            tlumacz_rdzen.zloz_blok_komentarza(tlum_bloki[idx], blok_cel["wciecie"])
    dump_cel = "\n".join(linie)

    # Komentarze końcowe podmieniamy po ponownym wydobyciu (numeracja linii
    # zmieniła się przy blokach, ale kolejność wpisów nie).
    linie = dump_cel.split("\n")
    for idx, wpis in enumerate(tlumacz_rdzen.komentarze_koncowe(dump_cel)):
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
    return "\n".join(linie)


def _zapisz_z_walidacja(
    cel: Path, zawartosc: str, kod: str, nazwa_pliku: str,
    dane_pl: dict, kotwice: list[str],
) -> bool:
    """Zapisuje plik i uruchamia walidację silnikiem; przy błędach ROLLBACK."""
    kopia = cel.read_text(encoding="utf-8") if cel.is_file() else None
    cel.parent.mkdir(parents=True, exist_ok=True)
    with open(cel, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(zawartosc)

    bledy = waliduj_silnikiem(kod, nazwa_pliku, dane_pl, kotwice)
    if not bledy:
        return True
    print(f"❌ {kod}/{nazwa_pliku}: engine validation rejected the file "
          f"({len(bledy)} error(s)):")
    for b in bledy[:12]:
        print(f"     • {b}")
    if kopia is None:
        cel.unlink(missing_ok=True)
        print("     ↩ usunięto świeżo zapisany plik (paczka wraca do stanu przed).")
    else:
        cel.write_text(kopia, encoding="utf-8", newline="\n")
        print(f"     ↩ przywrócono poprzednią treść {cel.name}.")
    return False


def wykryj_kotwice(
    teksty_pl: list[str],
    odniesienia: dict[str, str] | None,
    dodatkowe: tuple[str, ...] = (),
) -> list[str]:
    """Kotwice pliku: heurystyka + orakuł jednomyślności + literały silnika."""
    return tlumacz_rdzen.wykryj_kotwice(
        teksty_pl, odniesienia, dodatkowe, _kotwice_z_silnika())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _pliki_zrodlowe(*, z_jawnymi: bool = False) -> list[str]:
    """Nazwy plików przepisów w paczce PL, alfabetycznie."""
    folder = DICT_DIR / KOD_ZRODLOWY / FOLDER_OPOWIESCI
    if not folder.is_dir():
        raise SystemExit(f"❌ Missing source folder: {folder}")
    nazwy = [
        p.name for p in sorted(folder.glob("*.yaml"))
        if z_jawnymi or p.name not in PLIKI_TYLKO_JAWNIE
    ]
    if not nazwy:
        raise SystemExit(f"❌ Folder {folder} contains no recipe.")
    return nazwy


def _filtruj_pliki(wybor_csv: str) -> list[str]:
    """Zawęża listę plików do CSV z `--przepisy` (bare-name dozwolony)."""
    wszystkie = _pliki_zrodlowe(z_jawnymi=True)
    if not wybor_csv.strip():
        return _pliki_zrodlowe()
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
            f"   Available in dictionaries/{KOD_ZRODLOWY}/{FOLDER_OPOWIESCI}/: "
            f"{wszystkie}"
        )
    jawne = sorted(wybrane & PLIKI_TYLKO_JAWNIE)
    if jawne:
        print(f"⚠️  {', '.join(jawne)}: the Quick Start presets are written BY HAND "
              f"per language (literature with local motifs, not technical i18n). "
              f"Treat a machine translation as a STARTING POINT for the linguist "
              f"of a new pack, never as finished canon.")
    return [n for n in wszystkie if n in wybrane]


def _parsuj_argumenty() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batch auto-translator for the Tales recipes "
            f"(dictionaries/<code>/opowiesci/*.yaml) into: "
            f"{', '.join(MAPA_JEZYKOW)}. ruamel round-trip (comments and block "
            "scalars preserved), placeholder and anchor freezing, anti-meta-skip "
            "gates, vial label contract, engine validation."
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
        help="CSV of file names (e.g. `tryb_mniejsze_zlo` or `baza.yaml`). Empty = "
             "every file in the PL pack EXCEPT `zaczatki.yaml` (the Quick Start "
             "presets are written by hand per language — name them explicitly).")
    parser.add_argument(
        "--slowniki", type=str, default="",
        help="Path to a `dictionaries` directory OTHER than the repo one — e.g. the "
             "pack of an installed application. Defaults to the repo directory.")
    parser.add_argument(
        "--fiolka", action="store_true",
        help="LIGHT MODE: translates only the MISSING "
             "`fiolka.opisy_skutkow.*` seeds and appends them to the end of the "
             "pool in the target pack. Touches neither the prompt, nor the "
             "comments, nor already translated seeds, and leaves the file header "
             "alone. The right mode after new effects enter the PL canon.")
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip (language, file) pairs whose target file already exists.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only the split into units, anchors and tokens. No API calls.")
    parser.add_argument(
        "--model", default=MODEL_DOMYSLNY,
        help=f"Anthropic model used for the translation (default: {MODEL_DOMYSLNY}).")
    parser.add_argument(
        "--kotwica", type=str, default="", metavar="LITERAL[,LITERAL...]",
        help="Extra literals forced as anchors (frozen without asking the oracle). "
             "CAUTION: do NOT force a term that is a native word in the TARGET "
             "language — a frozen nominative blocks inflection. Cultural terms "
             "from the vial seeds have their own, gentler gate (stem matching "
             "instead of freezing).")
    parser.add_argument(
        "--orakul-drafty", action="store_true",
        help="Allow DRAFT packs to act as the anchor oracle (use it when a file has "
             "just been propagated to N languages and you are tuning the base pack).")
    parser.add_argument(
        "--tylko-walidacja", action="store_true",
        help="No API: for the chosen languages/files runs ENGINE VALIDATION alone "
             "over the existing target files (technical fields, placeholders, "
             "anchors, vial, label contract, starting points, pack completeness). "
             "The only audit that compares the packs against each other.")
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
    if args.fiolka and tryby_lokalne:
        parser.error("--fiolka jest trybem tłumaczenia — nie łącz go z "
                     "--finalizuj/--tylko-walidacja.")
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

    for uwaga in sprawdz_marker_meta_warning():
        print(f"⚠️  {uwaga}")

    kody = _wybierz_jezyki(args)
    if args.fiolka:
        # Mechanika fiolki żyje wyłącznie w trybie Mniejsze zło; wskazywanie
        # innych plików w tym trybie byłoby po cichu bezczynne.
        pliki = ["tryb_mniejsze_zlo.yaml"]
        if args.przepisy.strip():
            print("ℹ️  --fiolka ignoruje --przepisy: pule ziaren są tylko "
                  "w `tryb_mniejsze_zlo.yaml`.")
    else:
        pliki = _filtruj_pliki(args.przepisy)
    print(f"ℹ️  Pliki do przetworzenia ({len(pliki)}): {', '.join(pliki)}")

    # --- Tryby lokalne (zero API) -------------------------------------------
    if args.finalizuj:
        zmienione = nie_drafty = braki = 0
        for kod in kody:
            for nazwa in pliki:
                cel = DICT_DIR / kod / FOLDER_OPOWIESCI / nazwa
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
        print("\n========== PODSUMOWANIE (--finalizuj) ==========")
        print(f"✅ finalized: {zmienione} | ⏭️ already final: {nie_drafty} "
              f"| ⚠️ file missing: {braki}")
        return 0

    if args.tylko_walidacja:
        yaml_io = _yaml_io()
        wszystkie_bledy = 0
        extra = tuple(k.strip() for k in args.kotwica.split(",") if k.strip())
        for nazwa in pliki:
            zrodlo = DICT_DIR / KOD_ZRODLOWY / FOLDER_OPOWIESCI / nazwa
            with open(zrodlo, "r", encoding="utf-8") as fh:
                drzewo_pl = yaml_io.load(fh)
            dane_pl = {str(k): drzewo_pl[k] for k in drzewo_pl.keys()}
            jednostki = zbierz_jednostki_pol(drzewo_pl, f"{KOD_ZRODLOWY}/{nazwa}")
            odn = wczytaj_orakuly(
                [nazwa], dopusc_drafty=args.orakul_drafty).get(nazwa, {})
            kanon = kanon_etapow_luku()
            for kod in kody:
                # Kotwice liczone per język: walidowana paczka nie jest orakułem
                # dla samej siebie (inaczej każdy jej literał byłby „kotwicą").
                kotwice = wykryj_kotwice(
                    [j.zrodlo for j in jednostki],
                    {k: v for k, v in odn.items() if k != kod}, extra + (kanon,))
                bledy = waliduj_silnikiem(kod, nazwa, dane_pl, kotwice)
                wszystkie_bledy += len(bledy)
                if bledy:
                    print(f"❌ {kod}/{nazwa}: {len(bledy)} error(s)")
                    for b in bledy[:12]:
                        print(f"     • {b}")
                else:
                    print(f"✅ {kod}/{nazwa}: OK")
        print("\n========== PODSUMOWANIE (--tylko-walidacja) ==========")
        print("✅ Bez zastrzeżeń." if not wszystkie_bledy
              else f"❌ {wszystkie_bledy} error(s) in total.")
        return 1 if wszystkie_bledy else 0

    # --- Tłumaczenie ---------------------------------------------------------
    klient: Any = None if args.dry_run else tlumacz_rdzen.zainicjuj_klienta_anthropic(ROOT)
    kotwice_extra = tuple(k.strip() for k in args.kotwica.split(",") if k.strip())
    if kotwice_extra:
        print(f"🔒 Kotwice wymuszone z CLI: {list(kotwice_extra)}")

    sukcesy: list[str] = []
    porazki: list[str] = []
    wytworzone: dict[tuple[str, str], list[Jednostka]] = {}
    kotwice_per_plik: dict[tuple[str, str], list[str]] = {}
    orakuly = wczytaj_orakuly(pliki, dopusc_drafty=args.orakul_drafty)
    braki_orakulow = [n for n, t in orakuly.items() if not t]
    if braki_orakulow:
        print(f"⚠️  No reference pack has: {braki_orakulow} — for those files the "
              f"anchor oracle is inactive (conservative mode).")

    for kod in kody:
        print(f"\n========== {kod.upper()} "
              f"({MAPA_JEZYKOW[kod]} / {_natywna_nazwa(kod)}) ==========")
        wszystko_ok = True
        for nazwa in pliki:
            ok, jednostki = tlumacz_plik(
                kod, nazwa, klient,
                model=args.model,
                skip_existing=args.skip_existing,
                dry_run=args.dry_run,
                kotwice_extra=kotwice_extra,
                orakuly=orakuly.get(nazwa, {}),
                tryb_fiolka=args.fiolka,
            )
            if not ok:
                wszystko_ok = False
            elif jednostki:
                wytworzone[(kod, nazwa)] = jednostki
                kotwice_per_plik[(kod, nazwa)] = wykryj_kotwice(
                    [j.zrodlo for j in jednostki], None, kotwice_extra)  # maska: nadzbiór
        (sukcesy if wszystko_ok else porazki).append(kod)

    if wytworzone:
        print("\n🔎 DRAFT: skan audyt_leakow na wytworzonych draftach…")
        leaki = tlumacz_rdzen.zbierz_leaki(wytworzone, kotwice_per_plik)
        sciezka = przeglad_tlumaczen.zapisz_prompt_przegladu(
            "buduj_wielojezyczne_opowiesci.py", sorted(wytworzone.keys()), ROOT,
            leaki_per_plik=leaki,
        )
        if sciezka is not None:
            ile = sum(len(v) for per in leaki.values() for v in per.values())
            print(f"📋 DRAFT: checklista przeglądu → {sciezka.relative_to(ROOT)} "
                  f"({len(wytworzone)} plik(ów) do recenzji, {ile} kandydat(ów) na leak).")

    print("\n========== PODSUMOWANIE ==========")
    print(f"✅ Sukces: {len(sukcesy)}/{len(kody)}  ({', '.join(sukcesy) or '—'})")
    if porazki:
        print(f"❌ Failures (≥1 file failed): {', '.join(porazki)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
