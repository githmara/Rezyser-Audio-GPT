#!/usr/bin/env python
"""
buduj_wielojezyczne_ui.py — Batchowy autotłumacz interfejsu (i18n, Etap 2/5).

Czyta kanoniczne źródło `dictionaries/pl/gui/ui.yaml`, tłumaczy WYŁĄCZNIE
wartości stringowe (klucze nienaruszone) na języki docelowe i zapisuje
wynik w `dictionaries/<kod>/gui/ui.yaml` z zachowaniem komentarzy
sekcyjnych z oryginału.

Architektura (decyzja 13.1 — Etap 2):

  1. Wczytanie przez `ruamel.yaml.YAML(typ='rt')` (round-trip mode) —
     komentarze sekcyjne (np. `# COMMON – elementy wielokrotnego użytku`)
     i style block-scalar (`|-`, `|`) są zachowane bit w bit. Nagłówek
     z konwencjami PL jest podmieniany na auto-generowaną notkę
     „plik wygenerowany — nie edytuj ręcznie", analogicznie do `manual.yaml`.

  2. Walker drzewa zbiera wszystkie liście stringowe wraz z dotted-path
     (`app.nazwa`, `main.menu.narzedzia`, ...). Klucze, integery i listy
     są pomijane — w obecnym ui.yaml nie występują, ale walker nie
     przewraca się, gdy się pojawią (przejdzie obok).

  3. TOKENIZACJA dwuwarstwowa per-liść:
       * `{nazwa_parametru}` (placeholder dynamiczny) → `⟦P{i}⟧`
       * `\\t(?:Ctrl|Alt|Shift|Cmd)+...` (skrót wxPython)  → `⟦S{j}⟧`
     Znak `&` (akcelerator menu) jest CELOWO niezatokenizowany —
     LLM dostaje go widocznego, z explicit instrukcją relokacji
     (zob. `_PROMPT_SYSTEMOWY`). Tokenizacja `&` byłaby błędem —
     model nie miałby jak przesunąć ampersanda na sensowną literę.

  4. Wszystkie liście trafiają do JEDNEGO requesta `chat.completions`
     z `response_format={"type": "json_object"}`. Plik ui.yaml ma
     ~450 liści / ~26 kB tekstu — bezpiecznie mieści się w jednym
     kontekście. Eliminuje to ryzyko, że chunker rozetnie strukturę
     w połowie linii.

  5. WALIDACJE per-liść (przed iniekcją):
       * Multiset tokenów `⟦P\\d+⟧` i `⟦S\\d+⟧` w `tgt` musi być
         identyczny jak w `src` (parity check — reuzywamy semantykę
         z `buduj_wielojezyczne_docs.py`).
       * `tgt.count('&') == src.count('&')` — akcelerator nie może
         zniknąć ani się zduplikować.
       * Wszystkie id z requestu MUSZĄ być w odpowiedzi (no missing,
         no extra). Każda niezgodność blokuje zapis pliku.

  6. DETOKENIZACJA + ITERACYJNE NADPISANIE liści w drzewie ruamel
     (set_path po dotted-path). Dump przez `ruamel.yaml.dump()` →
     StringIO, podmiana topowego comment-block na auto-nagłówek,
     zapis UTF-8 + LF.

Użycie:
  python buduj_wielojezyczne_ui.py --wszystkie                 # en, fi, ru, is, it
  python buduj_wielojezyczne_ui.py --jezyki en                 # tylko angielski
  python buduj_wielojezyczne_ui.py --jezyki en,fi --skip-existing
  python buduj_wielojezyczne_ui.py --jezyki en --dry-run       # tokenizacja, zero API

Wymaga: `OPENAI_API_KEY` w środowisku (to samo konto co GUI Poliglota /
`buduj_wielojezyczne_docs.py`). Moduł NIE zależy od wxPython —
uruchamialny w CLI / CI bez inicjalizacji GUI.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


# ---------------------------------------------------------------------------
# STDOUT UTF-8 (spójnie z resztą skryptów buildowych — cmd.exe vs cp1250)
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


# ---------------------------------------------------------------------------
# Stałe ścieżek (analogicznie do buduj_wielojezyczne_docs.py)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DICT_DIR = ROOT / "dictionaries"

FOLDER_GUI = "gui"
NAZWA_UI = "ui.yaml"
KOD_ZRODLOWY = "pl"

# Chunking — gpt-4o ma twardy limit 16 384 tokenów na pojedynczą odpowiedź,
# a sformatowany JSON `{"tlumaczenia": [...]}` dla 450 liści cyrylicy
# przekracza ten próg (testowo: RU ~46k znaków ≈ ~25k tokenów outputu).
# 150 liści/chunk ≈ ~12-15k znaków JSON ≈ ~6-10k tokenów outputu — bezpiecznie
# w limicie nawet dla rosyjskiego. 3 requesty per język × 5 języków = 15
# wywołań total; każde walidowane niezależnie, jeden bad-batch nie zwala
# pozostałych chunków danego języka.
BATCH_SIZE = 150
MAX_TOKENS_OUT = 16_384


# ---------------------------------------------------------------------------
# Tokenizacja — dwa typy markerów
# ---------------------------------------------------------------------------
# Placeholder dynamiczny `{nazwa_parametru}` — semantyka tożsama z
# `buduj_wielojezyczne_docs.py` (`PLACEHOLDER_REGEX` tam vs. tu).
PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")

# Skrót klawiszowy wxPython w etykietach menu: tabulator + modyfikator(y) +
# klawisz, np. `\tCtrl+1`, `\tAlt+F4`, `\tCtrl+Shift+P`. wxPython parsuje
# ten suffix automatycznie i NIE wyświetla go w GUI (zamienia na natywny
# accelerator OS), ale string MUSI dotrzeć do wxPython 1:1 — modyfikatory
# `Ctrl`, `Alt`, `Shift` nie są lokalizowane (`.clinerules`).
SHORTCUT_REGEX = re.compile(
    r"\t(?:Ctrl|Alt|Shift|Cmd|Super)(?:\+(?:Ctrl|Alt|Shift|Cmd|Super))*\+\S+"
)

TOKEN_PH = "⟦P{}⟧"   # tokenizowany placeholder (n.p. ⟦P0⟧)
TOKEN_SC = "⟦S{}⟧"   # tokenizowany skrót klawiszowy (n.p. ⟦S0⟧)
# Wspólny regex do walidacji parzystości — łapie obie klasy markerów.
TOKEN_PARITY_REGEX = re.compile(r"⟦([PS]\d+)⟧")


# ---------------------------------------------------------------------------
# Mapa języków docelowych (spójna z buduj_wielojezyczne_docs.py)
# ---------------------------------------------------------------------------
MAPA_JEZYKOW: dict[str, str] = {
    "en": "angielski",
    "fi": "fiński",
    "ru": "rosyjski",
    "is": "islandzki",
    "it": "włoski",
}


# ---------------------------------------------------------------------------
# Prompt systemowy dla LLM
# ---------------------------------------------------------------------------
# Słowo "JSON" musi wystąpić w prompcie, by `response_format=json_object`
# było zaakceptowane przez OpenAI API (twardy wymóg API z błędem inaczej).
def _PROMPT_SYSTEMOWY(jezyk_docelowy: str) -> str:
    return (
        "# Rola\n"
        "Jesteś tłumaczem profesjonalnego interfejsu desktopowej aplikacji "
        f"wxPython. Tłumaczysz WYŁĄCZNIE wartości — klucze i struktura JSON "
        "są niezmienne.\n\n"
        "## Zadanie\n"
        f"Otrzymasz JSON z polem `liscie` — listą obiektów `{{\"id\": int, \"src\": str}}`.\n"
        f"Przetłumacz każde pole `src` na język: **{jezyk_docelowy}**.\n"
        "Zwróć JSON o strukturze:\n"
        "  `{\"tlumaczenia\": [{\"id\": int, \"tgt\": str}, ...]}`\n"
        "Każdy obiekt MUSI zawierać dokładnie to samo `id` co wejście. "
        "Pomijanie id, dodawanie nowych ani zmiana ich kolejności nie są "
        "dopuszczalne.\n\n"
        "## Zasady techniczne (KRYTYCZNE — naruszenie blokuje zapis pliku)\n"
        "1. **Markery ⟦P{n}⟧ i ⟦S{n}⟧** to zamrożone fragmenty programowe "
        "(placeholdery i skróty klawiszowe). Skopiuj je do `tgt` DOSŁOWNIE — "
        "litera w literę, cyfra w cyfrę. Liczba wystąpień każdego markera "
        "w `tgt` musi być identyczna jak w `src` (skrypt nadrzędny "
        "weryfikuje parzystość).\n"
        "2. **Znak `&`** to akcelerator menu wxPython (Alt+litera). Zachowaj "
        "DOKŁADNIE TAKĄ SAMĄ LICZBĘ ampersandów jak w `src` (zwykle 0 lub 1). "
        "Przesuń `&` przed literę dającą sensowny skrót w języku docelowym "
        "— preferuj pierwszą literę głównego słowa. Kolizje akceleratorów "
        "w obrębie menu nie są Twoim problemem (review je rozwiąże).\n"
        "3. **Emoji** (🎬 📄 📚 🌍 ✅ ⚠️ 🚨 ℹ️ ✂️ 🎭 🔄 📝 📋 🧠 🎙️ 🔐 🎛️ 🏁 📜 📖) "
        "— kopiuj 1:1 i zachowaj ich pozycję względem reszty tekstu.\n"
        "4. **Literały techniczne** — NIE tłumacz: nazw plików "
        "(`golden_key.env`, `.docx`, `.exe`), ścieżek (`dictionaries/`, "
        "`runtime/`), nazw modeli AI (`gpt-4o`, `OpenAI`), produktów "
        "(`NVDA`, `Vocalizer`, `Microsoft Word`), prefiksów kluczy (`sk-`), "
        "skrótów Ctrl/Alt/Shift w skrótach klawiszowych.\n"
        "5. **Białe znaki** — zachowaj wszystkie `\\n`, podwójne spacje, "
        "wcięcia. Łamanie linii w komunikatach jest celowo dobrane "
        "do szerokości okna dialogowego.\n"
        "6. **Wersja aplikacji** — w polu `wersja` (np. `\"13.1 – Wersja "
        "Wydawnicza\"`) zachowaj numer (cyfry + kropka) i myślnik, "
        "ale przetłumacz frazę „Wersja Wydawnicza” na odpowiednik "
        "w docelowym języku (np. „Release Edition” / „Julkaisuversio”).\n\n"
        "## Format odpowiedzi\n"
        "ZWRÓĆ WYŁĄCZNIE poprawny JSON `{\"tlumaczenia\": [...]}`. Bez "
        "code-fences, bez wstępu, bez podsumowania."
    )


# ---------------------------------------------------------------------------
# Walker po drzewie ruamel — zbiera (dotted_path, str_value)
# ---------------------------------------------------------------------------
def zbierz_liscie(node: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Rekurencyjnie zbiera wszystkie liście stringowe z dotted-path.

    ruamel `CommentedMap` dziedziczy po `dict`, więc `isinstance(_, dict)`
    łapie zarówno czyste dicty, jak i ruamel-owe round-trip mapy.
    Listy są obsługiwane symbolicznie (`[i]` w path), choć w obecnym
    ui.yaml nie występują — zostawiamy zaczepienie na przyszłość.
    """
    out: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for k in list(node.keys()):
            sub = f"{prefix}.{k}" if prefix else str(k)
            out += zbierz_liscie(node[k], sub)
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            out += zbierz_liscie(v, f"{prefix}[{idx}]")
    elif isinstance(node, str):
        out.append((prefix, node))
    # Inne typy (int, bool, None) ignorujemy — nie ma czego tłumaczyć.
    return out


def ustaw_po_sciezce(node: Any, sciezka: str, nowa_wartosc: str) -> None:
    """Nadpisuje liść w drzewie po dotted-path (mutuje `node` w miejscu).

    Wspiera notację `[i]` dla indeksu listy (zobacz `zbierz_liscie`).
    Rzuca `KeyError`/`IndexError` przy niezgodnej strukturze — to celowo
    twardy błąd (oznacza, że LLM zwrócił path niepasujący do wejścia).
    """
    # Rozkład path-a na segmenty: "a.b[0].c" → ["a", "b", "[0]", "c"]
    segmenty = re.findall(r"[^.\[\]]+|\[\d+\]", sciezka)
    if not segmenty:
        raise ValueError(f"Pusta ścieżka: {sciezka!r}")
    for seg in segmenty[:-1]:
        if seg.startswith("[") and seg.endswith("]"):
            node = node[int(seg[1:-1])]
        else:
            node = node[seg]
    ostatni = segmenty[-1]
    if ostatni.startswith("[") and ostatni.endswith("]"):
        node[int(ostatni[1:-1])] = nowa_wartosc
    else:
        node[ostatni] = nowa_wartosc


# ---------------------------------------------------------------------------
# Tokenizacja per-liść (placeholder + shortcut, niezależne liczniki)
# ---------------------------------------------------------------------------
def tokenizuj_liscia(tekst: str) -> tuple[str, dict[str, str]]:
    """Zamienia `{...}` na `⟦P{i}⟧` i `\\tCtrl+...` na `⟦S{j}⟧`.

    Zwraca (tekst_tok, mapa). Klucze mapy mają prefix `P`/`S` —
    np. `mapa["P0"] = "{nazwa_aplikacji}"`, `mapa["S3"] = "\\tCtrl+1"`.
    """
    mapa: dict[str, str] = {}

    licznik_p = 0
    def _zamien_ph(match: re.Match[str]) -> str:
        nonlocal licznik_p
        klucz = f"P{licznik_p}"
        mapa[klucz] = match.group(0)
        licznik_p += 1
        return TOKEN_PH.format(licznik_p - 1)

    licznik_s = 0
    def _zamien_sc(match: re.Match[str]) -> str:
        nonlocal licznik_s
        klucz = f"S{licznik_s}"
        mapa[klucz] = match.group(0)
        licznik_s += 1
        return TOKEN_SC.format(licznik_s - 1)

    # Skróty NAJPIERW — bo zawierają znaki, które mogłyby zostać
    # niechcący zinterpretowane jako placeholder, gdyby ktoś dał
    # `\tCtrl+{X}` (dziś nie występuje, ale tańsza wersja regexa
    # placeholdera nie szuka po tabulatorze, więc kolizji i tak nie ma).
    tekst_tok = SHORTCUT_REGEX.sub(_zamien_sc, tekst)
    tekst_tok = PLACEHOLDER_REGEX.sub(_zamien_ph, tekst_tok)
    return tekst_tok, mapa


def detokenizuj_liscia(tekst: str, mapa: dict[str, str]) -> str:
    """Zamienia wszystkie `⟦P{i}⟧` i `⟦S{j}⟧` z powrotem na oryginały."""
    def _zamien(match: re.Match[str]) -> str:
        klucz = match.group(1)   # np. "P3" / "S1"
        return mapa.get(klucz, match.group(0))
    return TOKEN_PARITY_REGEX.sub(_zamien, tekst)


def waliduj_liscia(src_tok: str, tgt: str) -> tuple[bool, list[str]]:
    """Sprawdza parity tokenów + count('&'). Zwraca (ok, lista_problemow)."""
    problemy: list[str] = []

    we = Counter(TOKEN_PARITY_REGEX.findall(src_tok))
    wy = Counter(TOKEN_PARITY_REGEX.findall(tgt))
    if we != wy:
        wszystkie = set(we) | set(wy)
        for klucz in sorted(wszystkie):
            if we.get(klucz, 0) != wy.get(klucz, 0):
                problemy.append(
                    f"token ⟦{klucz}⟧ — src: {we.get(klucz, 0)}×, "
                    f"tgt: {wy.get(klucz, 0)}×"
                )

    # Akcelerator wxPython — liczba ampersandów musi być zachowana.
    # Tokenizacja nie zaczepia `&`, więc liczymy bezpośrednio na src/tgt.
    src_oryg = src_tok   # tokenizacja nie modyfikuje `&`
    if src_oryg.count("&") != tgt.count("&"):
        problemy.append(
            f"akcelerator `&` — src: {src_oryg.count('&')}×, "
            f"tgt: {tgt.count('&')}×"
        )

    return (len(problemy) == 0), problemy


# ---------------------------------------------------------------------------
# Inicjalizacja klienta OpenAI (kopia 1:1 z buduj_wielojezyczne_docs.py)
# ---------------------------------------------------------------------------
def _zainicjuj_klienta_openai() -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(
            "❌ Brak modułu `openai`. Instalacja (venv projektu):\n"
            "   .venv/Scripts/pip install openai"
        ) from exc

    try:
        from dotenv import load_dotenv
        env_path = ROOT / "golden_key.env"
        if env_path.is_file():
            load_dotenv(env_path)
    except ImportError:
        pass

    klucz = os.environ.get("OPENAI_API_KEY")
    if not klucz or klucz == "TUTAJ_WKLEJ_SWOJ_KLUCZ":
        raise SystemExit(
            "❌ Brak prawidłowego OPENAI_API_KEY.\n"
            "   Sprawdź `golden_key.env` w katalogu projektu (ten sam plik,\n"
            "   którego używa GUI — System Check w trybie Reżysera)."
        )
    return OpenAI(api_key=klucz)


# ---------------------------------------------------------------------------
# Wywołanie LLM (jednorazowe, response_format=json_object)
# ---------------------------------------------------------------------------
def wywolaj_llm(
    klient: Any,
    model: str,
    jezyk_docelowy: str,
    liscie_tok: list[tuple[int, str]],
) -> dict[int, str]:
    """Wysyła JEDEN request, zwraca mapę id → tgt.

    `response_format={"type": "json_object"}` gwarantuje, że odpowiedź
    parsuje się jako JSON. Walidacje strukturalne (klucze, typy) robimy
    po naszej stronie — model bywa kreatywny w nazwach pól.

    Rzuca `RuntimeError` przy nieparowalnej odpowiedzi lub strukturze,
    której nie umiemy zinterpretować — wyżej (w `tlumacz_jezyk`) jest
    to złapane jako miękki błąd dla danego języka, reszta języków
    leci dalej.
    """
    payload = {
        "jezyk_docelowy": jezyk_docelowy,
        "liscie": [{"id": i, "src": s} for i, s in liscie_tok],
    }

    resp = klient.chat.completions.create(
        model=model,
        temperature=0.0,
        max_tokens=MAX_TOKENS_OUT,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _PROMPT_SYSTEMOWY(jezyk_docelowy)},
            {
                "role": "user",
                "content": (
                    "Oto JSON z liśćmi do tłumaczenia. Zwróć JSON z polem "
                    "`tlumaczenia`.\n\n"
                    + json.dumps(payload, ensure_ascii=False, indent=2)
                ),
            },
        ],
    )

    # Sanity check: model trafił w max_tokens i ucięło odpowiedź?
    # `finish_reason='length'` to sygnał, że JSON jest niekompletny —
    # zgłaszamy explicit, żeby trening „output cut off" nie wyglądał jak
    # zwykły błąd parsera.
    finish = getattr(resp.choices[0], "finish_reason", None)
    if finish == "length":
        raise RuntimeError(
            f"Model osiągnął limit max_tokens={MAX_TOKENS_OUT} — odpowiedź "
            f"została ucięta. Zmniejsz BATCH_SIZE (obecnie {BATCH_SIZE}) "
            f"lub przejdź na model z większym oknem wyjściowym."
        )

    surowa = resp.choices[0].message.content or ""
    try:
        dane = json.loads(surowa)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Odpowiedź LLM nie jest poprawnym JSON: {exc}\n"
            f"Pierwsze 200 znaków: {surowa[:200]!r}"
        ) from exc

    # Tolerancja drobnych wariacji nazwy korzenia: `tlumaczenia`,
    # `translations`, lub bezpośrednio lista/słownik na top-levelu.
    arr: Any
    if isinstance(dane, dict):
        arr = (
            dane.get("tlumaczenia")
            or dane.get("translations")
            or dane.get("results")
            or dane
        )
    else:
        arr = dane

    mapa_tgt: dict[int, str] = {}
    if isinstance(arr, list):
        for item in arr:
            if not isinstance(item, dict):
                continue
            if "id" not in item or "tgt" not in item:
                continue
            try:
                mapa_tgt[int(item["id"])] = str(item["tgt"])
            except (TypeError, ValueError):
                continue
    elif isinstance(arr, dict):
        # Wariant degradacyjny: `{"0": "...", "1": "..."}`
        for k, v in arr.items():
            if not isinstance(v, str):
                continue
            try:
                mapa_tgt[int(k)] = v
            except (TypeError, ValueError):
                continue

    if not mapa_tgt:
        raise RuntimeError(
            f"Nie udało się sparsować żadnego id→tgt z odpowiedzi.\n"
            f"Pierwsze 400 znaków surowej: {surowa[:400]!r}"
        )

    return mapa_tgt


# ---------------------------------------------------------------------------
# Podmiana topowego comment-block na auto-nagłówek
# ---------------------------------------------------------------------------
def _auto_naglowek(kod_jezyka: str) -> str:
    """Buduje top-of-file komentarz dla wynikowego ui.yaml danego języka."""
    return (
        "# =============================================================================\n"
        f"# dictionaries/{kod_jezyka}/gui/ui.yaml\n"
        "#\n"
        "# Plik wygenerowany automatycznie przez buduj_wielojezyczne_ui.py\n"
        f"# ze źródła dictionaries/{KOD_ZRODLOWY}/gui/ui.yaml\n"
        "# (język bazowy PL, wersja 13.x). NIE edytuj ręcznie — zmiany\n"
        "# wprowadzaj w pliku źródłowym PL i uruchom ponownie skrypt.\n"
        "#\n"
        "# Tłumaczone są WYŁĄCZNIE wartości; klucze, struktura, komentarze\n"
        "# sekcyjne i style block-scalar (`|-`, `|`) są zachowane przez\n"
        "# round-trip ruamel.yaml. Placeholdery {nazwa} i skróty \\tCtrl+...\n"
        "# zostały zamrożone tokenami ⟦P{i}⟧/⟦S{j}⟧ na czas tłumaczenia,\n"
        "# odtworzone 1:1 po weryfikacji parzystości multisetu markerów.\n"
        "# =============================================================================\n"
        "\n"
    )


def podmien_top_comment(yaml_str: str, kod_jezyka: str) -> str:
    """Usuwa nagłówkowy blok komentarzy i wstawia auto-nagłówek.

    Top-of-file w PL ui.yaml ma strukturę:
      [komentarze nagłówkowe / konwencje]
      <pusta linia>
      [komentarz sekcyjny # APP – ...]
      app: ...

    Pierwsza pusta linia jest separatorem nagłówka — STOP tam, żeby
    zachować sekcyjny komentarz `# APP – ...` (i jego separator).
    Bez tego stop-warunku zjadalibyśmy też pierwszy sekcyjny komentarz,
    a kolejne 7 (zaczepione do węzłów podrzędnych przez ruamel) zostają.
    """
    linie = yaml_str.split("\n")
    i = 0
    while i < len(linie) and linie[i].lstrip().startswith("#"):
        i += 1
    # Pomiń ewentualną pojedynczą pustą linię — separator nagłówka.
    # Auto-nagłówek ma już własną pustą linię na końcu, więc nie
    # gubimy formatowania.
    if i < len(linie) and linie[i].strip() == "":
        i += 1
    reszta = "\n".join(linie[i:])
    return _auto_naglowek(kod_jezyka) + reszta


# ---------------------------------------------------------------------------
# Pipeline dla jednego języka
# ---------------------------------------------------------------------------
def tlumacz_jezyk(
    kod: str,
    nazwa_pl: str,
    klient: Any,
    drzewo_pl: Any,
    liscie_pl: list[tuple[str, str]],
    yaml_io: YAML,
    *,
    skip_existing: bool,
    dry_run: bool,
    model: str,
    klucz: str | None = None,
) -> bool:
    """Pełen pipeline dla jednego języka. Zwraca True przy sukcesie.

    Tryb FULL (`klucz=None`): tłumaczy wszystkie liście, klonuje drzewo PL
    do iniekcji, nadpisuje cały plik `<kod>/gui/ui.yaml`.

    Tryb UPDATE (`klucz="dotted.path"`): tłumaczy TYLKO podany klucz
    (lub całe poddrzewo, gdy klucz wskazuje na gałąź), wczytuje już
    istniejący `<kod>/gui/ui.yaml` jako bazę iniekcji, nadpisuje wybrane
    liście — pozostałe są zachowane bit w bit. Wymaga, żeby plik
    docelowy istniał (najpierw FULL, potem UPDATE).
    """
    cel = DICT_DIR / kod / FOLDER_GUI / NAZWA_UI
    if klucz is None and cel.exists() and skip_existing:
        print(f"⏭️  {kod}: {cel.relative_to(ROOT)} już istnieje — pomijam (--skip-existing).")
        return True
    if klucz is not None and not cel.exists():
        print(f"❌ {kod}: brak {cel.relative_to(ROOT)} — uruchom najpierw bez --klucz.")
        return False

    # --- Krok 1: tokenizacja per-liść -----------------------------------------
    liscie_tok: list[tuple[int, str]] = []
    mapy_per_id: dict[int, dict[str, str]] = {}
    statystyki_p = 0
    statystyki_s = 0
    for idx, (path, wartosc) in enumerate(liscie_pl):
        wartosc_tok, mapa = tokenizuj_liscia(wartosc)
        liscie_tok.append((idx, wartosc_tok))
        mapy_per_id[idx] = mapa
        statystyki_p += sum(1 for k in mapa if k.startswith("P"))
        statystyki_s += sum(1 for k in mapa if k.startswith("S"))

    print(
        f"ℹ️  {kod}: {len(liscie_pl)} liści, "
        f"zamrożono {statystyki_p} placeholderów + {statystyki_s} skrótów."
    )

    if dry_run:
        # Podgląd kilku pierwszych mapowań (sanity check tokenizacji)
        print(f"    Podgląd 5 pierwszych liści:")
        for idx, src_tok in liscie_tok[:5]:
            path, oryg = liscie_pl[idx]
            mapa = mapy_per_id[idx]
            print(f"      [{idx}] {path}")
            print(f"          oryg: {oryg[:80]!r}")
            print(f"          tok:  {src_tok[:80]!r}")
            if mapa:
                print(f"          mapa: {mapa}")
        # Sanity: zlicz `&` w całym pliku — pomocna metryka
        n_amp = sum(s.count("&") for _, s in liscie_pl)
        print(f"    Łączna liczba akceleratorów `&`: {n_amp}")
        print(f"    (dry-run) Nie wywołuję API.")
        return True

    # --- Krok 2: wywołania LLM (chunked po BATCH_SIZE liści) ------------------
    # Chunking gwarantuje, że żadna pojedyncza odpowiedź nie przekroczy
    # MAX_TOKENS_OUT (16 384 dla gpt-4o). Wyniki łączymy w jedną mapę id→tgt
    # — id-y są unikalne globalnie, bo pochodzą z `enumerate(liscie_pl)`.
    total = len(liscie_tok)
    n_chunkow = (total + BATCH_SIZE - 1) // BATCH_SIZE
    mapa_tgt: dict[int, str] = {}
    print(f"🌍 {kod}: {model} ({nazwa_pl}), {n_chunkow} chunków po max {BATCH_SIZE} liści...")
    for nr, start in enumerate(range(0, total, BATCH_SIZE), start=1):
        chunk = liscie_tok[start:start + BATCH_SIZE]
        print(f"   {kod}: chunk {nr}/{n_chunkow} (id {chunk[0][0]}..{chunk[-1][0]}, {len(chunk)} liści)...")
        try:
            mapa_tgt.update(wywolaj_llm(klient, model, nazwa_pl, chunk))
        except RuntimeError as exc:
            print(f"❌ {kod}: błąd LLM w chunk {nr}/{n_chunkow} — {exc}")
            return False

    # --- Krok 3: walidacja kompletności + parity per-liść ---------------------
    oczekiwane = set(idx for idx, _ in liscie_tok)
    otrzymane = set(mapa_tgt.keys())
    brakujace = oczekiwane - otrzymane
    nadmiarowe = otrzymane - oczekiwane
    if brakujace or nadmiarowe:
        print(f"❌ {kod}: niezgodny zbiór id w odpowiedzi.")
        if brakujace:
            print(f"     brakuje: {sorted(brakujace)[:20]} (łącznie {len(brakujace)})")
        if nadmiarowe:
            print(f"     nadmiarowe: {sorted(nadmiarowe)[:20]} (łącznie {len(nadmiarowe)})")
        return False

    porazki: list[tuple[int, list[str]]] = []
    src_po_idx = {idx: src for idx, src in liscie_tok}
    for idx, src_tok in liscie_tok:
        tgt = mapa_tgt[idx]
        ok, problemy = waliduj_liscia(src_tok, tgt)
        if not ok:
            porazki.append((idx, problemy))

    # --- Krok 3.5: jednorazowy RETRY dla problematycznych liści ---------------
    # LLM bywa kreatywny w pojedynczych przypadkach (np. zgubi `&`, zmieni
    # token). Drugie podejście z czystym kontekstem (tylko same problematyczne
    # liście, mniejszy batch) zwykle to naprawia. Bez tego sieć by traciła
    # pełen plik z powodu jednej wpadki na 450 stringach.
    if porazki:
        print(f"⚠️  {kod}: {len(porazki)} liści wymaga retry...")
        do_retry = [(idx, src_po_idx[idx]) for idx, _ in porazki]
        try:
            retry_tgt = wywolaj_llm(klient, model, nazwa_pl, do_retry)
        except RuntimeError as exc:
            print(f"❌ {kod}: retry się wywalił — {exc}")
            return False
        mapa_tgt.update(retry_tgt)

        porazki_v2: list[tuple[int, list[str]]] = []
        for idx, _ in porazki:
            tgt = mapa_tgt.get(idx, "")
            ok, problemy = waliduj_liscia(src_po_idx[idx], tgt)
            if not ok:
                porazki_v2.append((idx, problemy))

        if porazki_v2:
            print(f"❌ {kod}: po retry nadal {len(porazki_v2)} liści jest niepoprawnych. NIE zapisuję.")
            for idx, problemy in porazki_v2[:10]:
                path, _ = liscie_pl[idx]
                print(f"     [{idx}] {path}")
                for diag in problemy:
                    print(f"       • {diag}")
            if len(porazki_v2) > 10:
                print(f"     ... (+{len(porazki_v2) - 10} kolejnych)")
            return False
        print(f"✅ {kod}: retry naprawił wszystkie {len(porazki)} problematycznych liści.")

    # --- Krok 4: detokenizacja + iniekcja w drzewo ruamel ---------------------
    # Tryb FULL: klonujemy drzewo PL przez round-trip dump+load — bazą
    #            jest pełna struktura PL ze wszystkimi komentarzami.
    # Tryb UPDATE: wczytujemy istniejące <kod>/gui/ui.yaml — tłumaczenia
    #              pozostałych liści są zachowane, podmieniamy tylko wybrane.
    if klucz is not None:
        with open(cel, "r", encoding="utf-8") as fh:
            drzewo_kopia = yaml_io.load(fh)
    else:
        buf_clone = io.StringIO()
        yaml_io.dump(drzewo_pl, buf_clone)
        drzewo_kopia = yaml_io.load(buf_clone.getvalue())

    for idx, src_tok in liscie_tok:
        path, _ = liscie_pl[idx]
        tgt_raw = mapa_tgt[idx]
        tgt = detokenizuj_liscia(tgt_raw, mapy_per_id[idx])
        ustaw_po_sciezce(drzewo_kopia, path, tgt)

    # --- Krok 5: dump + podmiana topowego komentarza + zapis ------------------
    buf = io.StringIO()
    yaml_io.dump(drzewo_kopia, buf)
    yaml_str = buf.getvalue()
    yaml_str = podmien_top_comment(yaml_str, kod)

    cel.parent.mkdir(parents=True, exist_ok=True)
    with open(cel, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(yaml_str)

    print(
        f"✅ {kod}: zapisano {cel.relative_to(ROOT)} "
        f"({len(liscie_pl)} liści OK, {len(yaml_str):,} znaków)."
    )
    return True


# ---------------------------------------------------------------------------
# CLI (symetryczne do buduj_wielojezyczne_docs.py)
# ---------------------------------------------------------------------------
def _parsuj_argumenty() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batchowy autotłumacz interfejsu ui.yaml na języki docelowe "
            f"({', '.join(MAPA_JEZYKOW)}). Zachowuje komentarze sekcyjne "
            "(ruamel.yaml round-trip), tokenizuje placeholdery i skróty "
            "klawiszowe, weryfikuje parzystość markerów + akceleratora `&`."
        ),
    )
    grupa = parser.add_mutually_exclusive_group(required=True)
    grupa.add_argument(
        "--jezyki",
        type=str,
        default="",
        help=f"Lista kodów ISO oddzielona przecinkami (np. `en,fi`). "
             f"Dozwolone: {', '.join(MAPA_JEZYKOW)}.",
    )
    grupa.add_argument(
        "--wszystkie",
        action="store_true",
        help=f"Tłumacz na wszystkie języki ({', '.join(MAPA_JEZYKOW)}).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Pomiń języki, dla których `dictionaries/<kod>/gui/ui.yaml` "
             "już istnieje (idempotentny rerun).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tylko walk + tokenizacja + podgląd. Zero wywołań API.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="Model OpenAI do tłumaczenia (domyślnie: gpt-4o).",
    )
    parser.add_argument(
        "--klucz",
        type=str,
        default=None,
        help="Tłumacz tylko liście, których dotted-path zaczyna się od podanego "
             "klucza (np. `poliglota.ostrzezenie_jezyk` lub całe poddrzewo "
             "`poliglota`). Wymaga, by `<kod>/gui/ui.yaml` już istniał — "
             "pozostałe liście są zachowane bit w bit. Pozwala na surgical "
             "update jednej etykiety bez retłumaczenia całego pliku.",
    )
    args = parser.parse_args()
    if args.klucz and args.skip_existing:
        parser.error("--klucz i --skip-existing wzajemnie się wykluczają "
                     "(--klucz celowo nadpisuje wybrane liście w istniejącym pliku).")
    return args


def _wybierz_jezyki(args: argparse.Namespace) -> list[str]:
    if args.wszystkie:
        return list(MAPA_JEZYKOW.keys())
    kody = [k.strip() for k in args.jezyki.split(",") if k.strip()]
    nieznane = [k for k in kody if k not in MAPA_JEZYKOW]
    if nieznane:
        raise SystemExit(
            f"❌ Nieznane kody języków: {', '.join(nieznane)}.\n"
            f"   Dozwolone: {', '.join(MAPA_JEZYKOW)}."
        )
    return kody


def main() -> int:
    args = _parsuj_argumenty()
    kody = _wybierz_jezyki(args)

    # Wczytanie źródła PL przez ruamel round-trip (komentarze zachowane).
    # `width=10**9` zapobiega zawijaniu długich linii (welcome_text itp.).
    yaml_io = YAML(typ="rt")
    yaml_io.preserve_quotes = True
    yaml_io.width = 10 ** 9
    yaml_io.indent(mapping=2, sequence=4, offset=2)

    sciezka_pl = DICT_DIR / KOD_ZRODLOWY / FOLDER_GUI / NAZWA_UI
    if not sciezka_pl.is_file():
        print(f"❌ Brak pliku źródłowego PL: {sciezka_pl}")
        return 2
    with open(sciezka_pl, "r", encoding="utf-8") as fh:
        drzewo_pl = yaml_io.load(fh)

    liscie_pl = zbierz_liscie(drzewo_pl)
    if not liscie_pl:
        print(f"❌ Plik {sciezka_pl} nie zawiera żadnych liści stringowych.")
        return 2
    print(f"📄 Wczytano {sciezka_pl.relative_to(ROOT)}: {len(liscie_pl)} liści.")

    # Filtr `--klucz`: zostaw tylko liście, których dotted-path zaczyna się
    # od podanego prefiksu (sam klucz LUB klucz + "." → poddrzewo).
    if args.klucz:
        przed = len(liscie_pl)
        liscie_pl = [
            (p, v) for p, v in liscie_pl
            if p == args.klucz or p.startswith(args.klucz + ".")
        ]
        if not liscie_pl:
            print(f"❌ Brak liści dla klucza `{args.klucz}` w {sciezka_pl.relative_to(ROOT)}. "
                  f"Sprawdź dotted-path (np. `poliglota.ostrzezenie_jezyk`).")
            return 2
        print(f"🔎 Filtr --klucz='{args.klucz}': {len(liscie_pl)}/{przed} liści.")

    klient: Any = None if args.dry_run else _zainicjuj_klienta_openai()

    sukcesy: list[str] = []
    porazki: list[str] = []
    for kod in kody:
        nazwa_pl = MAPA_JEZYKOW[kod]
        print(f"\n========== {kod.upper()} ({nazwa_pl}) ==========")
        ok = tlumacz_jezyk(
            kod,
            nazwa_pl,
            klient,
            drzewo_pl,
            liscie_pl,
            yaml_io,
            skip_existing=args.skip_existing,
            dry_run=args.dry_run,
            model=args.model,
            klucz=args.klucz,
        )
        (sukcesy if ok else porazki).append(kod)

    print("\n========== PODSUMOWANIE ==========")
    print(f"✅ Sukces: {len(sukcesy)}/{len(kody)}  ({', '.join(sukcesy) or '—'})")
    if porazki:
        print(f"❌ Porażki: {', '.join(porazki)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
