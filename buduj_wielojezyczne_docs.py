#!/usr/bin/env python
"""
buduj_wielojezyczne_docs.py — Batchowy autotłumacz dokumentacji (i18n, Etap 5/5).

Czyta kanoniczne źródło `dictionaries/pl/gui/dokumentacja/manual.yaml`,
przepuszcza pole `tresc` przez silnik OpenAI (`tlumacz_ai.py`) z zamrożeniem
placeholderów `{klucz.zagniezdzony}` (np. `{app.wersja}`, `{rezyser.btn_prolog_label}`)
i zapisuje wynik jako `dictionaries/<kod>/gui/dokumentacja/manual.yaml` dla
każdego języka docelowego.

Architektura (decyzja 13.1 — Etap 5):

  1. Parsujemy źródło `yaml.safe_load`-em i wyciągamy pole `tresc`.
     Nagłówkowe komentarze `#` w pliku PL (notatki autora, ~60 linii)
     są IGNOROWANE — to nie jest treść dla użytkownika końcowego.

  2. TOKENIZACJA: każdy `{klucz}` → unikalny token Unicode `⟦i⟧`.
     Tokeny są neutralne — LLM nie rozpoznaje ich jako „etykieta do
     przetłumaczenia", w przeciwieństwie do `{english_looking_key}`.
     Mapa `i → oryginał` przechowywana w pamięci na czas tłumaczenia.

  3. PREFIX-INSTRUKCJA dla tłumacza (pas+szelki): kilka linii w nawiasach
     kwadratowych przed treścią — przypomina modelowi, żeby markery
     `⟦i⟧` kopiował 1:1. `_prompt_systemowy` w `tlumacz_ai.py` NIE jest
     modyfikowany (reguła projektowa 13.1 Etap 5).

  4. Tłumaczenie przez `tlumacz_dlugi_tekst` — reużywamy chunking, cache
     wznawiania (`runtime/temp_*.jsonl`), callbacki postępu. Z modułu
     nie dostajemy nic więcej niż reszta aplikacji (GUI Poligloty).

  5. WALIDACJA PARZYSTOŚCI tokenów — multiset `⟦i⟧` przed i po musi być
     identyczny. Mismatch = błąd krytyczny, plik NIE jest zapisywany,
     wypisujemy diagnostykę i przechodzimy do kolejnego języka.

  6. DETOKENIZACJA: każdy `⟦i⟧` → oryginalny `{klucz}` z mapy.
     Wynik to bezpieczny Polak-LLM-Polak round-trip: placeholdery
     wracają bit w bit, niezależnie od kreatywności modelu.

  7. Zapis `dictionaries/<kod>/gui/dokumentacja/manual.yaml` — nagłówek
     komentarza informujący, że plik jest wygenerowany automatycznie
     (nie edytować ręcznie), plus `id: manual` + `tresc: |` z 2-spacyjnym
     wcięciem block-scalar. Encoding UTF-8 + LF (tak jak `generuj_dokumentacje.py`).

Użycie:
  python buduj_wielojezyczne_docs.py --wszystkie                 # en, fi, ru, is, it
  python buduj_wielojezyczne_docs.py --jezyki en                 # tylko angielski
  python buduj_wielojezyczne_docs.py --jezyki en,fi --skip-existing
  python buduj_wielojezyczne_docs.py --jezyki en --dry-run       # sama tokenizacja, zero API

Wymaga: `OPENAI_API_KEY` w środowisku (to samo konto co GUI Poliglota).
Moduł NIE zależy od wxPython — uruchamialny w CLI / CI bez inicjalizacji GUI.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from tlumacz_ai import tlumacz_dlugi_tekst


# ---------------------------------------------------------------------------
# STDOUT UTF-8 (spójnie z `generuj_dokumentacje.py` — cmd.exe vs cp1250)
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


# ---------------------------------------------------------------------------
# Stałe ścieżek (wszystko względem pliku skryptu — tak samo jak generuj_docs)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DICT_DIR = ROOT / "dictionaries"
RUNTIME_DIR = ROOT / "runtime"

FOLDER_GUI = "gui"
FOLDER_DOKUMENTACJA = "dokumentacja"
NAZWA_MANUAL = "manual.yaml"
KOD_ZRODLOWY = "pl"

# Regex placeholdera — 1:1 jak w `generuj_dokumentacje.py`, żeby siatka
# {klucz.zagniezdzony} była definiowana w jednym kanonicznym miejscu
# semantycznym (jak go poszerzymy tam, poszerzamy i tu).
PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")

# Tokeny zamrożone. Unicode brackety ⟦ ⟧ (U+27E6, U+27E7) — nie kolidują
# z treścią (nie występują w manualu ani w żadnym naturalnym języku),
# LLM traktuje je jako znaczniki techniczne, nie jako placeholder do
# przetłumaczenia. Indeks monotoniczny od 0.
TOKEN_FORMAT = "⟦{}⟧"
TOKEN_REGEX = re.compile(r"⟦(\d+)⟧")


# ---------------------------------------------------------------------------
# Mapa języków docelowych (13.x)
# ---------------------------------------------------------------------------
# Polskie nazwy — `_prompt_systemowy` w tlumacz_ai.py składa prompt po polsku
# („Przetłumacz cały dostarczony tekst na język: **{jezyk_docelowy}**"),
# więc przekazujemy nazwę w tym samym języku co reszta promptu.
MAPA_JEZYKOW: dict[str, str] = {
    "en": "angielski",
    "fi": "fiński",
    "ru": "rosyjski",
    "is": "islandzki",
    "it": "włoski",
}


# ---------------------------------------------------------------------------
# Prefix-instrukcja dla LLM (dokleja się do samej treści, nie do systemu)
# ---------------------------------------------------------------------------
# `_prompt_systemowy` w tlumacz_ai.py NIE jest modyfikowany (reguła 13.1).
# Ten prefix jest doklejany jako pierwszy fragment user-promptu. Po stronie
# wyniku szukamy końcowego markera — jeżeli model go usunął (zgodnie
# z instrukcją „Zwróć WYŁĄCZNIE przetłumaczony tekst"), bierzemy wynik
# w całości. Jeżeli zostawił — utniemy prefix ręcznie.
MARKER_KONCA_PREFIXU = "[KONIEC INSTRUKCJI — TŁUMACZENIE ZACZYNA SIĘ PONIŻEJ]"

PREFIX_INSTRUKCJA = (
    "[INSTRUKCJA TECHNICZNA — USUŃ TEN BLOK Z ODPOWIEDZI, NIE TŁUMACZ GO]\n"
    "Poniższy tekst zawiera markery w formacie ⟦liczba⟧ (np. ⟦0⟧, ⟦12⟧, ⟦47⟧).\n"
    "To są zamrożone placeholdery programowe. Skopiuj je do odpowiedzi DOSŁOWNIE,\n"
    "znak w znak — nie zmieniaj cyfr, nie zmieniaj nawiasów, nie tłumacz.\n"
    "Każdy marker musi wystąpić w odpowiedzi dokładnie tyle samo razy,\n"
    "co w oryginale (skrypt nadrzędny weryfikuje parzystość po zakończeniu).\n"
    f"{MARKER_KONCA_PREFIXU}\n\n"
)


# ---------------------------------------------------------------------------
# Tokenizacja / detokenizacja / walidacja parzystości
# ---------------------------------------------------------------------------
def tokenizuj(tekst: str) -> tuple[str, dict[int, str]]:
    """Zastępuje każdy `{klucz}` unikalnym `⟦i⟧`. Zwraca (tekst, mapa i→oryginał)."""
    mapa: dict[int, str] = {}
    licznik = 0

    def _zamien(match: re.Match[str]) -> str:
        nonlocal licznik
        idx = licznik
        mapa[idx] = match.group(0)   # całość, razem z nawiasami klamrowymi
        licznik += 1
        return TOKEN_FORMAT.format(idx)

    tekst_tok = PLACEHOLDER_REGEX.sub(_zamien, tekst)
    return tekst_tok, mapa


def detokenizuj(tekst: str, mapa: dict[int, str]) -> str:
    """Przywraca `{klucz}` pod każdym `⟦i⟧`. Nieznane indeksy zostawia jak są."""
    def _zamien(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        return mapa.get(idx, match.group(0))

    return TOKEN_REGEX.sub(_zamien, tekst)


def sprawdz_parzystosc(
    tekst_we: str, tekst_wy: str
) -> tuple[bool, list[str]]:
    """Porównuje multiset tokenów ⟦i⟧ na wejściu i wyjściu.

    Zwraca ``(True, [])`` przy pełnej zgodności. W przeciwnym razie
    ``(False, lista_diagnostyk)`` — każda linia diagnostyki raportuje
    jeden problematyczny token (ile wystąpień mniej/więcej).
    """
    we = Counter(TOKEN_REGEX.findall(tekst_we))
    wy = Counter(TOKEN_REGEX.findall(tekst_wy))
    if we == wy:
        return True, []

    problemy: list[str] = []
    wszystkie = set(we) | set(wy)
    for idx in sorted(wszystkie, key=int):
        ile_we, ile_wy = we.get(idx, 0), wy.get(idx, 0)
        if ile_we != ile_wy:
            problemy.append(
                f"⟦{idx}⟧ — wejście: {ile_we}×, wyjście: {ile_wy}×"
            )
    return False, problemy


def utnij_prefix_z_wyniku(wynik: str) -> str:
    """Usuwa prefix-instrukcję z odpowiedzi LLM (jeśli nie usunął sam)."""
    idx = wynik.find(MARKER_KONCA_PREFIXU)
    if idx == -1:
        # Model posłuchał i usunął blok META — zostawiamy wynik w całości.
        return wynik.lstrip()
    return wynik[idx + len(MARKER_KONCA_PREFIXU):].lstrip()


# ---------------------------------------------------------------------------
# Budowanie wynikowego YAML-a (block scalar `|` + nagłówek-komentarz)
# ---------------------------------------------------------------------------
def zbuduj_yaml_wynikowy(kod_jezyka: str, id_szablonu: str, tresc: str) -> str:
    """Składa `dictionaries/<kod>/gui/dokumentacja/manual.yaml` do zapisu.

    Nie używamy `yaml.dump` — nie gwarantuje on block-scalar stylu `|`
    w ładnej formie, zwłaszcza dla treści z nawiasami klamrowymi
    (wymusiłby cudzysłowy). Budujemy ręcznie:

      * nagłówek komentarza (informacja, że plik jest wygenerowany);
      * `id: <id>`;
      * `tresc: |` + treść, każda linia wcięta 2 spacjami;
      * puste linie oryginału pozostają puste (bez końcowego whitespace).
    """
    linie = tresc.split("\n")
    wciete: list[str] = []
    for linia in linie:
        if linia.strip() == "":
            wciete.append("")
        else:
            wciete.append("  " + linia)

    naglowek = (
        "# =============================================================================\n"
        f"# dictionaries/{kod_jezyka}/gui/dokumentacja/manual.yaml\n"
        "#\n"
        "# Plik wygenerowany automatycznie przez buduj_wielojezyczne_docs.py\n"
        f"# ze źródła dictionaries/{KOD_ZRODLOWY}/gui/dokumentacja/manual.yaml\n"
        "# (język bazowy PL, wersja 13.x). NIE edytuj ręcznie — zmiany wprowadzaj\n"
        "# w pliku źródłowym PL i uruchom ponownie skrypt tłumacza.\n"
        "#\n"
        "# Silnik: OpenAI (tlumacz_ai.py). Placeholdery {klucz.zagniezdzony}\n"
        "# zostały zamrożone tokenami ⟦i⟧ na czas tłumaczenia i odtworzone 1:1\n"
        "# po weryfikacji parzystości multisetu markerów.\n"
        "# =============================================================================\n"
        "\n"
    )
    cialo = f"id: {id_szablonu}\ntresc: |\n" + "\n".join(wciete)
    if not cialo.endswith("\n"):
        cialo += "\n"
    return naglowek + cialo


# ---------------------------------------------------------------------------
# Wczytanie źródła PL
# ---------------------------------------------------------------------------
def wczytaj_zrodlo_pl() -> tuple[str, str]:
    """Zwraca (id, tresc) z `dictionaries/pl/gui/dokumentacja/manual.yaml`."""
    sciezka = DICT_DIR / KOD_ZRODLOWY / FOLDER_GUI / FOLDER_DOKUMENTACJA / NAZWA_MANUAL
    if not sciezka.is_file():
        raise FileNotFoundError(f"Brak pliku źródłowego PL: {sciezka}")
    with open(sciezka, "r", encoding="utf-8") as fh:
        dane = yaml.safe_load(fh)
    if not isinstance(dane, dict):
        raise ValueError(f"Plik {sciezka} nie parsuje się do słownika YAML.")
    id_szablonu = dane.get("id")
    tresc = dane.get("tresc")
    if not isinstance(id_szablonu, str) or not isinstance(tresc, str):
        raise ValueError(
            f"Plik {sciezka} musi mieć stringowe pola `id` oraz `tresc`."
        )
    return id_szablonu, tresc


# ---------------------------------------------------------------------------
# Pipeline dla jednego języka docelowego
# ---------------------------------------------------------------------------
def tlumacz_jezyk(
    kod: str,
    nazwa_pl: str,
    klient: Any,
    id_szablonu: str,
    tresc_pl: str,
    *,
    skip_existing: bool,
    dry_run: bool,
    model: str,
) -> bool:
    """Pełny przebieg dla jednego języka. Zwraca True przy sukcesie."""
    cel = DICT_DIR / kod / FOLDER_GUI / FOLDER_DOKUMENTACJA / NAZWA_MANUAL
    if cel.exists() and skip_existing:
        print(f"⏭️  {kod}: {cel.relative_to(ROOT)} już istnieje — pomijam (--skip-existing).")
        return True

    # --- Krok 1: tokenizacja --------------------------------------------------
    tresc_tok, mapa = tokenizuj(tresc_pl)
    liczba_ph = len(mapa)
    print(f"ℹ️  {kod}: zamrożono {liczba_ph} placeholderów → tokeny ⟦0..{liczba_ph - 1}⟧.")
    if dry_run:
        # Podgląd: kilka pierwszych mapowań i próbka tokenizowanej treści
        print(f"    Podgląd mapy (pierwsze 8):")
        for idx in list(mapa.keys())[:8]:
            print(f"      ⟦{idx}⟧ = {mapa[idx]}")
        if liczba_ph > 8:
            print(f"      ... (+{liczba_ph - 8} kolejnych)")
        # Szybki sanity check — mapa musi pokrywać 100% wystąpień w oryginale
        oryginalne = Counter(PLACEHOLDER_REGEX.findall(tresc_pl))
        z_mapy = Counter(
            re.findall(r"([a-zA-Z_][a-zA-Z0-9_.]*)", " ".join(v.strip("{}") for v in mapa.values()))
        )
        if sum(oryginalne.values()) == liczba_ph:
            print(f"    ✅ Sanity check: wszystkie {liczba_ph} wystąpień placeholderów trafiło do mapy.")
        else:
            print(
                f"    ⚠️  Sanity check: oryginał ma {sum(oryginalne.values())} wystąpień, "
                f"mapa ma {liczba_ph} wpisów — rozjazd!"
            )
        print(f"    (dry-run) Nie wywołuję API.")
        return True

    # --- Krok 2: tłumaczenie przez tlumacz_ai.py -----------------------------
    payload = PREFIX_INSTRUKCJA + tresc_tok
    blad_kryt: dict[str, Any] = {"msg": None, "partial": None}

    def _on_postep(msg: str, pct: int) -> None:
        sys.stderr.write(f"   [{kod} {pct:3d}%] {msg}\n")

    def _on_blad_krytyczny(msg: str, partial: str) -> None:
        blad_kryt["msg"] = msg
        blad_kryt["partial"] = partial

    def _on_blad_miekki(msg: str, tytul: str) -> None:
        # ISO i tak nie używamy (generujemy dictionaries/<kod>/..., mamy kod),
        # ale logujemy ostrzeżenie, żeby nie znikło w ciszy.
        print(f"⚠️  {kod}: {tytul} — {msg.splitlines()[0]}")

    wynik = tlumacz_dlugi_tekst(
        tresc=payload,
        jezyk_docelowy=nazwa_pl,
        klient=klient,
        runtime_dir=str(RUNTIME_DIR),
        oryginalna_nazwa=f"manual_{KOD_ZRODLOWY}_to_{kod}",
        on_postep=_on_postep,
        on_blad_krytyczny=_on_blad_krytyczny,
        on_blad_miekki=_on_blad_miekki,
        model_tlumacz=model,
    )

    if wynik is None:
        komunikat = blad_kryt["msg"] or "nieznany błąd silnika tlumacz_ai.py"
        print(f"❌  {kod}: przerwano tłumaczenie.\n    {komunikat.splitlines()[0]}")
        print(f"    Częściowy postęp w: {RUNTIME_DIR / f'temp_manual_{KOD_ZRODLOWY}_to_{kod}_tlumaczenie_{nazwa_pl}.jsonl'}")
        return False

    # --- Krok 3: obcięcie prefixu + walidacja parzystości --------------------
    tekst_wy = utnij_prefix_z_wyniku(wynik.tekst)
    ok, problemy = sprawdz_parzystosc(tresc_tok, tekst_wy)
    if not ok:
        print(f"❌  {kod}: NARUSZONA parzystość markerów ⟦i⟧. NIE zapisuję pliku.")
        for diag in problemy[:20]:
            print(f"     {diag}")
        if len(problemy) > 20:
            print(f"     ... (+{len(problemy) - 20} kolejnych)")
        print(
            f"    Cache wznawiania zachowany w runtime/ — po korekcie promptu\n"
            f"    uruchom ponownie z tym samym językiem, odzyska opłacone bloki."
        )
        return False

    # --- Krok 4: detokenizacja + zapis ---------------------------------------
    tekst_final = detokenizuj(tekst_wy, mapa)
    zawartosc_yaml = zbuduj_yaml_wynikowy(kod, id_szablonu, tekst_final)

    cel.parent.mkdir(parents=True, exist_ok=True)
    with open(cel, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(zawartosc_yaml)

    print(
        f"✅  {kod}: zapisano {cel.relative_to(ROOT)} "
        f"({liczba_ph} placeholderów OK, {len(tekst_final):,} znaków)."
    )
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parsuj_argumenty() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Batchowy autotłumacz dokumentacji manual.yaml na języki docelowe "
            f"({', '.join(MAPA_JEZYKOW)}). Używa tlumacz_ai.py z zamrożeniem "
            "placeholderów przez unikalne tokeny Unicode ⟦i⟧."
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
        help="Pomiń języki, dla których `dictionaries/<kod>/gui/dokumentacja/manual.yaml` "
             "już istnieje (idempotentny rerun).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tylko tokenizacja + podgląd mapy placeholderów. Zero wywołań API.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="Model OpenAI do głównego tłumaczenia (domyślnie: gpt-4o).",
    )
    return parser.parse_args()


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


def _zainicjuj_klienta_openai() -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(
            "❌ Brak modułu `openai`. Instalacja (venv projektu):\n"
            "   .venv/Scripts/pip install openai"
        ) from exc

    # Ładujemy `golden_key.env` z roota projektu — ten sam plik, którego
    # używa GUI (`gui_poliglota.py`, `gui_rezyser.py`, `main.py`).
    # Dzięki temu skrypt CLI nie wymaga ręcznego eksportowania zmiennych
    # środowiskowych — działa od razu, jeśli System Check w GUI przechodzi.
    try:
        from dotenv import load_dotenv
        env_path = ROOT / "golden_key.env"
        if env_path.is_file():
            load_dotenv(env_path)
    except ImportError:
        pass   # python-dotenv jest w requirements; fallback i tak ma sens

    klucz = os.environ.get("OPENAI_API_KEY")
    if not klucz or klucz == "TUTAJ_WKLEJ_SWOJ_KLUCZ":
        raise SystemExit(
            "❌ Brak prawidłowego OPENAI_API_KEY.\n"
            "   Sprawdź `golden_key.env` w katalogu projektu (ten sam plik,\n"
            "   którego używa GUI — System Check w trybie Reżysera)."
        )
    return OpenAI(api_key=klucz)


def main() -> int:
    args = _parsuj_argumenty()
    kody = _wybierz_jezyki(args)

    try:
        id_szablonu, tresc_pl = wczytaj_zrodlo_pl()
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ {exc}")
        return 2

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
            id_szablonu,
            tresc_pl,
            skip_existing=args.skip_existing,
            dry_run=args.dry_run,
            model=args.model,
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
