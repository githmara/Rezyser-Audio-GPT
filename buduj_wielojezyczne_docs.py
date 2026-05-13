#!/usr/bin/env python
"""
buduj_wielojezyczne_docs.py — Batchowy autotłumacz dokumentacji (i18n, Etap 5/5).

Czyta WSZYSTKIE szablony z `dictionaries/pl/gui/dokumentacja/*.yaml`
(13.4: ``manual.yaml``, ``dictionaries.yaml``, każdy kolejny YAML wrzucony
do tego folderu w przyszłości), przepuszcza pole `tresc` przez silnik
OpenAI (`tlumacz_ai.py`) z zamrożeniem placeholderów `{klucz.zagniezdzony}`
(np. `{app.wersja}`, `{rezyser.btn_prolog_label}`) i zapisuje wynik jako
`dictionaries/<kod>/gui/dokumentacja/<plik>.yaml` dla każdego języka
docelowego — z zachowaniem oryginalnej nazwy pliku PL.

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
  python buduj_wielojezyczne_docs.py --wszystkie --szablony dictionaries
                                                                # tylko jeden szablon
                                                                # (np. gdy manual.yaml jest
                                                                #  już przetłumaczony i nie
                                                                #  chcesz spalać API-billa
                                                                #  na rerun)

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
KOD_ZRODLOWY = "pl"

# 13.4: skrypt obsługuje WSZYSTKIE szablony z ``dictionaries/pl/gui/dokumentacja/``
# (manual.yaml + dictionaries.yaml + przyszłe). Wcześniej wpis ``NAZWA_MANUAL``
# zamykał generację na jednym pliku; teraz iterujemy po katalogu — dorzucenie
# nowego YAML-a do paczki PL zaowocuje automatycznym tłumaczeniem we wszystkich
# językach docelowych przy najbliższym ``--wszystkie`` (bez zmian w kodzie).

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
    "de": "niemiecki",
    "fr": "francuski",
    "es": "hiszpański",
}


# ---------------------------------------------------------------------------
# 13.4: tabela skrótowców per język docelowy (do custom system promptu)
# ---------------------------------------------------------------------------
# Zaczerpnięte z `TODO_wielojezycznosc.md` § 3.1 (notebook autora projektu).
# Po 5 najpopularniejszych pozycji per język — nie chcemy obciążać promptu
# pełnymi tabelami (10-16 pozycji), bo to zwiększa koszt każdego call'a API
# bez znaczącej poprawy wyniku. Lista służy LLM jako konkretne dane do
# wstrzyknięcia w sekcję „Cipher: Text Reverser" wynikowego dokumentu —
# zastępują polskie m.in./np./tzw./tzn./dr.
ABBREV_BY_LANG: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("e.g.",   "for example"),
        ("i.e.",   "that is"),
        ("etc.",   "et cetera"),
        ("U.S.",   "United States"),
        ("U.K.",   "United Kingdom"),
    ],
    "ru": [
        ("т.е.",   "то есть"),
        ("т.д.",   "так далее"),
        ("т.н.",   "так называемый"),
        ("т.к.",   "так как"),
        ("и.о.",   "исполняющий обязанности"),
    ],
    "it": [
        ("ad es.", "ad esempio"),
        ("ecc.",   "eccetera"),
        ("dott.",  "dottore"),
        ("prof.",  "professore"),
        ("pag.",   "pagina"),
    ],
    "fi": [
        ("esim.",  "esimerkiksi"),
        ("jne.",   "ja niin edelleen"),
        ("ym.",    "ynnä muuta"),
        ("ns.",    "niin sanottu"),
        ("tms.",   "tai muuta sellaista"),
    ],
    "is": [
        ("t.d.",      "til dæmis"),
        ("þ.e.",      "það er"),
        ("m.a.",      "meðal annars"),
        ("u.þ.b.",    "um það bil"),
        ("o.s.frv.",  "og svo framvegis"),
    ],
    "de": [
        ("z.B.",   "zum Beispiel"),
        ("d.h.",   "das heißt"),
        ("usw.",   "und so weiter"),
        ("bzw.",   "beziehungsweise"),
        ("ggf.",   "gegebenenfalls"),
    ],
    "fr": [
        ("p. ex.",   "par exemple"),
        ("c.-à-d.",  "c'est-à-dire"),
        ("etc.",     "et cetera"),
        ("M.",       "Monsieur"),
        ("Dr",       "Docteur"),
    ],
}


# ---------------------------------------------------------------------------
# 13.4: builder customowego system-promptu per (kod_docelowy, nazwa_natywna)
# ---------------------------------------------------------------------------
# Dokleja się do `_PROMPT_SYSTEMOWY_TEMPLATE` z `tlumacz_ai.py` przez nowy
# parametr `prompt_dodatkowy`. Wymusza na modelu trzy nieoczywiste rzeczy
# zidentyfikowane podczas review wyników pierwszego batchu (13.4):
#
#   1. NIE pisać że wsparcie kodu_docelowego jest „w przyszłości" —
#      paczka `dictionaries/<kod>/` jest już kompletna w 13.4.
#   2. W liście akcentów PODMIENIĆ pozycję dla języka docelowego
#      (no-op dla użytkownika natywnego) na akcent polski (Ewa/Paulina).
#   3. W sekcjach szyfrów (Odwracacz, Typoglikemia) — nie kopiować
#      polskich przykładów dosłownie, tylko zlokalizować je pod
#      docelową fonetykę.
PROMPT_TEMPLATE_DOKUMENTACJA = """\
## Project context (CRITICAL — read carefully)
This documentation describes "Reżyser Audio GPT", a Polish desktop tool for writers
and voice-over creators. The translation is for a {nazwa_natywna} user who already
has the "dictionaries/{kod}/" package installed and complete in version 13.4.
DO NOT write that {nazwa_natywna} support is "coming in a future version" — it is
already shipped and the user is reading these docs in {nazwa_natywna} right now.

The application supports MULTIPLE source languages (today: Polish and English; more
in 13.4+). Each "dictionaries/<source>/" folder is a self-contained rule pack that
operates on input text written in that source language. The application uses
langdetect to pick the right pack automatically — you must NOT claim that the rules
apply to Polish source only.

### Accent list — REPLACE the native accent
The docs include a list of available accents like:
  - English (Samantha/Mark in Vocalizer, Zira/Hazel in OneCore)
  - Finnish (Satu/Mikko in Vocalizer, Heidi in OneCore)
  - Italian (Alice/Luca in Vocalizer, Elsa in OneCore)
  ...

One entry matches the TARGET language ({nazwa_natywna}). That entry is meaningless
for this reader — applying e.g. an English accent to text already in English is a
no-op. REPLACE the {nazwa_natywna} entry with a POLISH accent entry, using these
voice names:
    Polish (Ewa in Vocalizer, Paulina in OneCore)

Keep ALL OTHER entries (translate language NAMES to {nazwa_natywna}, but preserve
voice names like Samantha, Markus, Heidi, Gudrun, Milena 1:1 — product names).

### Cipher: Text Reverser — replace abbreviations with target-language equivalents
The Reverser cipher section lists Polish abbreviations (m.in., np., tzw., tzn., dr.)
that the script expands BEFORE reversing the sentence — without expansion, dotted
abbreviations would reverse into phonetic nonsense (Polish example: ".nim").

You MUST localize this:
  1. REPLACE the 5 Polish abbreviations with these {nazwa_natywna} equivalents:
{abbreviation_list}
  2. RE-COMPUTE the nonsense example (".nim" in Polish): take the FIRST abbreviation
     from your replacement list, reverse it character-by-character, and present that
     as the new nonsense example for the target language.

### Cipher: Typoglycemia — DECODE, TRANSLATE, RE-SCRAMBLE
The Typoglycemia section contains an example sentence that is ITSELF an output of
the cipher (Polish, scrambled middles):
   "Nie meossż peyrzcztać tkstueu w trkirej klojoinseęci letir, jśeli pszeriwa i
    otsnatia leritea są na wscłaoyicwh mscjaieh"

The unscrambled meaning is roughly: "You can read text in any letter order as long
as the first and last letters of each word are in the right place."

You MUST:
  1. RECOGNIZE that the example is itself scrambled — do NOT copy it verbatim.
  2. TRANSLATE the unscrambled meaning into {nazwa_natywna} naturally.
  3. RE-SCRAMBLE the translation: keep the FIRST and LAST character of every word
     longer than 3 characters; randomly permute the middle characters. Words of 3
     or fewer characters stay unchanged.

For English, a well-known canonical version exists you can use as a reference:
   "Aoccdrnig to a rscheearch at Cmabrigde Uinervtisy, it deosn't mttaer in waht
    oredr the ltteers in a wrod are, the olny iprmoatnt tihng is taht the frist
    and lsat ltteer be at the rghit pclae."

For other languages, generate an equivalent in the same spirit.

### Filenames and voice names — KEEP 1:1
Polish filenames (angielski.yaml, cezar.yaml, podstawy.yaml, finski.yaml, islandzki.yaml,
naprawiacz_tagow.yaml, oczyszczenie.yaml, oczyszczenie_bez_liczb.yaml, rosyjski.yaml,
wloski.yaml, niemiecki.yaml, francuski.yaml, hiszpanski.yaml, polski.yaml) are PHYSICAL
filenames in the package — keep them verbatim, do NOT translate.

Voice product names (Samantha, Mark, Markus, Hedda, Heidi, Gudrun, Milena, Irina,
Pavel, Yuri, Satu, Mikko, Thomas, Amelie, Julie, Stefan, Katja, Jorge, Monica, Helena,
Alice, Luca, Elsa, Zira, Hazel, Ewa, Paulina) are product names — keep 1:1.

### Frozen markers ⟦i⟧
Every ⟦N⟧ marker is a frozen placeholder. Copy character-for-character; do not
translate, do not renumber, do not insert new ones.\
"""


def _zbuduj_prompt_dodatkowy(kod: str, nazwa_natywna: str) -> str:
    """Buduje custom system-prompt dla pary (kod_docelowy, nazwa_natywna).

    Zwraca pusty string, gdy nie mamy tabeli skrótowców dla danego języka —
    wtedy autotłumacz korzysta z bazowego promptu z `tlumacz_ai.py` bez modyfikacji.
    """
    abbrev = ABBREV_BY_LANG.get(kod)
    if not abbrev:
        return ""
    bullety = "\n".join(f'     - "{skr}" → "{exp}"' for skr, exp in abbrev)
    return PROMPT_TEMPLATE_DOKUMENTACJA.format(
        kod=kod,
        nazwa_natywna=nazwa_natywna,
        abbreviation_list=bullety,
    )


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
def _wcetnij_blok_scalar(tresc: str, wciecie: int = 2) -> list[str]:
    """Wcina każdą linię o `wciecie` spacji, pust linie zostawia jako puste."""
    linie = tresc.split("\n")
    # Usuń ostatnią pustą linię (artefakt rstrip + "\n" w buduj sekcji)
    if linie and linie[-1] == "":
        linie = linie[:-1]
    prefix = " " * wciecie
    return [prefix + l if l.strip() else "" for l in linie]


def zbuduj_yaml_wynikowy(
    kod_jezyka: str,
    id_szablonu: str,
    tresc: str | dict[str, str],
    nazwa_pliku: str,
) -> str:
    """Składa ``dictionaries/<kod>/gui/dokumentacja/<plik>.yaml`` do zapisu.

    Nie używamy `yaml.dump` — nie gwarantuje on block-scalar stylu `|`
    w ładnej formie, zwłaszcza dla treści z nawiasami klamrowymi
    (wymusiłby cudzysłowy). Budujemy ręcznie.

    Tresc może być:
      * stringiem — stary schemat z jednego block-scalar `|`. Wynik:
        ``id: <id>\\ntresc: |\\n  <treść wcięta 2 spacjami>``.
      * słownikiem ``{klucz_sekcji: tresc_sekcji}`` — nowy schemat (v15.2+).
        Każda wartość zapisana jako osobny block-scalar `|` wcięty 4 spacjami
        (klucz sekcji wcięty 2 spaceami pod `tresc:`).
    """
    naglowek = (
        "# =============================================================================\n"
        f"# dictionaries/{kod_jezyka}/gui/dokumentacja/{nazwa_pliku}\n"
        "#\n"
        "# Plik wygenerowany automatycznie przez buduj_wielojezyczne_docs.py\n"
        f"# ze źródła dictionaries/{KOD_ZRODLOWY}/gui/dokumentacja/{nazwa_pliku}\n"
        "# (język bazowy PL, wersja 13.x). NIE edytuj ręcznie — zmiany wprowadzaj\n"
        "# w pliku źródłowym PL i uruchom ponownie skrypt tłumacza.\n"
        "#\n"
        "# Silnik: OpenAI (tlumacz_ai.py). Placeholdery {klucz.zagniezdzony}\n"
        "# zostały zamrożone tokenami ⟦i⟧ na czas tłumaczenia i odtworzone 1:1\n"
        "# po weryfikacji parzystości multisetu markerów.\n"
        "# =============================================================================\n"
        "\n"
    )

    if isinstance(tresc, str):
        # Stary schemat: jeden block-scalar `|`
        wciete = _wcetnij_blok_scalar(tresc, wciecie=2)
        cialo = f"id: {id_szablonu}\ntresc: |\n" + "\n".join(wciete)
        if not cialo.endswith("\n"):
            cialo += "\n"
        return naglowek + cialo

    if isinstance(tresc, dict):
        # Nowy schemat: tresc jako dict sekcji. Każda sekcja to osobny `|` scalar.
        cialo = f"id: {id_szablonu}\ntresc:\n"
        for klucz, sekcja in tresc.items():
            cialo += f"  {klucz}: |\n"
            wciete = _wcetnij_blok_scalar(sekcja, wciecie=4)
            for linia in wciete:
                cialo += linia + "\n"
        return naglowek + cialo

    raise TypeError(f"`tresc` musi być stringiem albo dict-em, dostałem {type(tresc).__name__}")


# ---------------------------------------------------------------------------
# Wczytanie źródła PL
# ---------------------------------------------------------------------------
# Klucz „_legacy" dla starych yaml-ów (string tresc): pakujemy do dict z jednym
# kluczem, żeby downstream miał spójny interfejs. Dict z jednym kluczem
# „_legacy" odpowiada zachowaniu sprzed v15.2 (jedno wywołanie LLM dla całości).
KLUCZ_LEGACY = "_legacy"


def wczytaj_szablony_pl() -> list[tuple[str, str, dict[str, str]]]:
    """Zwraca listę ``(nazwa_pliku, id, sekcje)`` z PL-owej dokumentacji.

    Od v15.2 (task #3) szablony PL mają ``tresc`` jako dict sekcji
    (``{krok_1: |..., krok_2: |..., ...}``) — pozwala to na surgical update
    pojedynczej sekcji (``--klucz`` w CLI) zamiast retłumaczania całego
    manuala 8 razy przy każdej drobnej zmianie.

    Backward-compat: jeśli ``tresc`` jest stringiem (stary schemat z v15.1
    i wcześniej), opakowujemy w dict z jednym kluczem ``_legacy``. Downstream
    nie musi rozróżniać — ten sam pipeline tokenizacji + tłumaczenia.

    Returns:
        Lista trójek (nazwa pliku jak ``manual.yaml``, id szablonu, dict sekcji).
        Posortowana alfabetycznie po nazwie pliku, żeby kolejność tłumaczenia
        była deterministyczna (cache wznawiania w runtime/ jest po niej kluczowany).
    """
    folder = DICT_DIR / KOD_ZRODLOWY / FOLDER_GUI / FOLDER_DOKUMENTACJA
    if not folder.is_dir():
        raise FileNotFoundError(f"Brak folderu źródłowego PL: {folder}")

    szablony: list[tuple[str, str, dict[str, str]]] = []
    for plik in sorted(folder.glob("*.yaml")):
        with open(plik, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
        if not isinstance(dane, dict):
            print(f"⚠️  Pomijam {plik.name}: nie parsuje się do słownika YAML.")
            continue
        id_szablonu = dane.get("id")
        if not isinstance(id_szablonu, str):
            print(f"⚠️  Pomijam {plik.name}: brak stringowego pola `id`.")
            continue
        tresc = dane.get("tresc")
        if isinstance(tresc, str):
            sekcje = {KLUCZ_LEGACY: tresc}
        elif isinstance(tresc, dict):
            # Filtruj tylko stringowe wartości (inne typy — pomiń z ostrzeżeniem)
            sekcje = {}
            for k, v in tresc.items():
                if isinstance(v, str):
                    sekcje[k] = v
                else:
                    print(f"⚠️  {plik.name}: sekcja '{k}' nie jest stringiem — pomijam.")
            if not sekcje:
                print(f"⚠️  Pomijam {plik.name}: dict `tresc` nie ma żadnych stringowych sekcji.")
                continue
        else:
            print(f"⚠️  Pomijam {plik.name}: `tresc` musi być stringiem albo dictem.")
            continue
        szablony.append((plik.name, id_szablonu, sekcje))

    if not szablony:
        raise ValueError(
            f"Folder {folder} nie zawiera żadnego poprawnego szablonu *.yaml."
        )
    return szablony


def wczytaj_istniejacy_docelowy(plik_docelowy: Path) -> dict[str, str] | None:
    """Wczytuje istniejący <kod>/gui/dokumentacja/<plik>.yaml jako dict sekcji.

    Używane przez tryb ``--klucz`` (surgical update): tłumaczymy TYLKO wybrane
    sekcje, reszta zostaje z istniejącego pliku docelowego. Zwraca dict sekcji
    lub None, gdy plik nie istnieje / nie da się sparsować.

    Konwersja starego schematu (string tresc) → dict: opakowujemy w
    ``{_legacy: str}`` — to znaczy że plik docelowy jest w starym schemacie.
    Surgical update na pojedynczy klucz z dictu PL nie zadziała w takim
    przypadku (klucz PL nie istnieje w docelowym), więc wywołujący musi
    poradzić sobie z fallback-iem (najczęściej: retłumacz cały plik bez --klucz).
    """
    if not plik_docelowy.is_file():
        return None
    try:
        with open(plik_docelowy, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(dane, dict):
        return None
    tresc = dane.get("tresc")
    if isinstance(tresc, str):
        return {KLUCZ_LEGACY: tresc}
    if isinstance(tresc, dict):
        return {k: v for k, v in tresc.items() if isinstance(v, str)}
    return None


# ---------------------------------------------------------------------------
# Pipeline dla jednego języka docelowego
# ---------------------------------------------------------------------------
def _tlumacz_pojedyncza_sekcje(
    kod: str,
    nazwa_pl: str,
    klient: Any,
    nazwa_pliku: str,
    rdzen: str,
    klucz_sekcji: str,
    tresc_pl: str,
    *,
    dry_run: bool,
    model: str,
    prompt_dodatkowy: str,
) -> tuple[bool, str | None]:
    """Tłumaczy pojedynczą sekcję (tokenizacja + LLM + walidacja + detokenizacja).

    Zwraca (success, przetłumaczona_tresc). Cache wznawiania w runtime/ jest
    kluczowany przez `{rdzen}_{klucz_sekcji}_{KOD_ZRODLOWY}_to_{kod}` —
    dzięki temu temp_manual_krok_5_vocalizer_pl_to_en_*.jsonl żyje obok
    temp_manual_krok_5_onecore_pl_to_en_*.jsonl, a częściowy progres jednej
    sekcji nie psuje drugiej.
    """
    tresc_tok, mapa = tokenizuj(tresc_pl)
    liczba_ph = len(mapa)
    sufiks = f" ({klucz_sekcji})" if klucz_sekcji != KLUCZ_LEGACY else ""
    print(
        f"ℹ️  {kod}/{nazwa_pliku}{sufiks}: zamrożono {liczba_ph} placeholderów → "
        f"tokeny ⟦0..{max(liczba_ph - 1, 0)}⟧, {len(tresc_pl):,} znaków źródła."
    )
    if dry_run:
        oryginalne = Counter(PLACEHOLDER_REGEX.findall(tresc_pl))
        ok_sanity = sum(oryginalne.values()) == liczba_ph
        marker = "✅" if ok_sanity else "⚠️"
        print(f"    {marker} Sanity check: {sum(oryginalne.values())} wystąpień ph, mapa {liczba_ph}.")
        return True, None

    payload = PREFIX_INSTRUKCJA + tresc_tok
    blad_kryt: dict[str, Any] = {"msg": None, "partial": None}
    cache_key = (
        f"{rdzen}_{klucz_sekcji}_{KOD_ZRODLOWY}_to_{kod}"
        if klucz_sekcji != KLUCZ_LEGACY
        else f"{rdzen}_{KOD_ZRODLOWY}_to_{kod}"
    )

    def _on_postep(msg: str, pct: int) -> None:
        sys.stderr.write(f"   [{kod}/{rdzen}{sufiks} {pct:3d}%] {msg}\n")

    def _on_blad_krytyczny(msg: str, partial: str) -> None:
        blad_kryt["msg"] = msg
        blad_kryt["partial"] = partial

    def _on_blad_miekki(msg: str, tytul: str) -> None:
        print(f"⚠️  {kod}/{nazwa_pliku}{sufiks}: {tytul} — {msg.splitlines()[0]}")

    wynik = tlumacz_dlugi_tekst(
        tresc=payload,
        jezyk_docelowy=nazwa_pl,
        klient=klient,
        runtime_dir=str(RUNTIME_DIR),
        oryginalna_nazwa=cache_key,
        on_postep=_on_postep,
        on_blad_krytyczny=_on_blad_krytyczny,
        on_blad_miekki=_on_blad_miekki,
        model_tlumacz=model,
        prompt_dodatkowy=prompt_dodatkowy,
    )
    if wynik is None:
        komunikat = blad_kryt["msg"] or "nieznany błąd silnika tlumacz_ai.py"
        print(f"❌  {kod}/{nazwa_pliku}{sufiks}: przerwano tłumaczenie.\n    {komunikat.splitlines()[0]}")
        return False, None

    tekst_wy = utnij_prefix_z_wyniku(wynik.tekst)
    ok, problemy = sprawdz_parzystosc(tresc_tok, tekst_wy)
    if not ok:
        print(f"❌  {kod}/{nazwa_pliku}{sufiks}: NARUSZONA parzystość markerów ⟦i⟧.")
        for diag in problemy[:10]:
            print(f"     {diag}")
        if len(problemy) > 10:
            print(f"     ... (+{len(problemy) - 10} kolejnych)")
        return False, None

    tekst_final = detokenizuj(tekst_wy, mapa)
    return True, tekst_final


def tlumacz_szablon(
    kod: str,
    nazwa_pl: str,
    nazwa_natywna: str,
    klient: Any,
    nazwa_pliku: str,
    id_szablonu: str,
    sekcje_pl: dict[str, str],
    *,
    skip_existing: bool,
    dry_run: bool,
    model: str,
    klucze_filtru: list[str] | None = None,
) -> bool:
    """Pełny przebieg tłumaczenia jednego pliku-szablonu na jeden język.

    Od v15.2 (task #3) przyjmuje ``sekcje_pl`` jako dict (zamiast pojedynczego
    stringa). Każda sekcja przepuszczana osobno przez tlumacz_ai z osobnym
    cache wznawiania w ``runtime/``. Argument ``nazwa_natywna`` wchodzi do
    customowego system-promptu z :func:`_zbuduj_prompt_dodatkowy`.

    Tryby pracy:

      * **FULL** (``klucze_filtru=None``): tłumaczy wszystkie sekcje z ``sekcje_pl``
        i zapisuje cały plik na nowo (overwrite). To tradycyjne zachowanie
        przed v15.2 + obsługa nowego dict-schematu.

      * **SURGICAL** (``klucze_filtru=['krok_5_vocalizer', ...]``): tłumaczy
        TYLKO wskazane klucze, wczytuje istniejący plik docelowy, podmienia
        w nim wskazane sekcje i zapisuje całość. Wymaga, by plik docelowy
        już istniał W NOWYM SCHEMACIE (dict tresc). Stare pliki ze stringiem
        tresc nie obsłużą surgical update — najpierw FULL retłumacz.
    """
    cel = DICT_DIR / kod / FOLDER_GUI / FOLDER_DOKUMENTACJA / nazwa_pliku
    if klucze_filtru is None and cel.exists() and skip_existing:
        print(f"⏭️  {kod}/{nazwa_pliku}: już istnieje — pomijam (--skip-existing).")
        return True

    # SURGICAL: filtruj sekcje + wczytaj istniejący plik docelowy do scalenia
    sekcje_do_tlumaczenia: dict[str, str] = sekcje_pl
    sekcje_istniejace: dict[str, str] | None = None
    if klucze_filtru is not None:
        nieznane = [k for k in klucze_filtru if k not in sekcje_pl]
        if nieznane:
            print(f"❌ {kod}/{nazwa_pliku}: nieznane klucze w PL: {nieznane}")
            print(f"   Dostępne klucze PL: {sorted(sekcje_pl.keys())}")
            return False
        sekcje_do_tlumaczenia = {k: sekcje_pl[k] for k in klucze_filtru}
        sekcje_istniejace = wczytaj_istniejacy_docelowy(cel)
        if sekcje_istniejace is None:
            print(f"❌ {kod}/{nazwa_pliku}: brak istniejącego pliku docelowego — uruchom najpierw bez --klucz.")
            return False
        if KLUCZ_LEGACY in sekcje_istniejace:
            print(
                f"❌ {kod}/{nazwa_pliku}: docelowy plik w starym schemacie (string tresc).\n"
                f"   Surgical update niemożliwy — uruchom najpierw bez --klucz, żeby przemigrować na dict-schemat."
            )
            return False

    rdzen = nazwa_pliku.rsplit(".", 1)[0]
    prompt_dodatkowy = _zbuduj_prompt_dodatkowy(kod, nazwa_natywna)

    # Tłumaczenie sekcja-po-sekcji
    sekcje_przetlumaczone: dict[str, str] = {}
    for klucz, tresc_pl in sekcje_do_tlumaczenia.items():
        ok, tekst = _tlumacz_pojedyncza_sekcje(
            kod, nazwa_pl, klient, nazwa_pliku, rdzen, klucz, tresc_pl,
            dry_run=dry_run, model=model, prompt_dodatkowy=prompt_dodatkowy,
        )
        if not ok:
            print(f"❌  {kod}/{nazwa_pliku}: sekcja '{klucz}' nie udała się — NIE zapisuję pliku.")
            return False
        if not dry_run:
            sekcje_przetlumaczone[klucz] = tekst or ""

    if dry_run:
        print(f"    (dry-run) Nie wywołuję API, nie zapisuję {kod}/{nazwa_pliku}.")
        return True

    # Złóż wynikowy dict: SURGICAL = scal z istniejącymi, FULL = same przetłumaczone
    if sekcje_istniejace is not None:
        wynikowy_dict = dict(sekcje_istniejace)
        wynikowy_dict.update(sekcje_przetlumaczone)
    else:
        wynikowy_dict = sekcje_przetlumaczone

    # Decyzja schematu zapisu:
    # * Jeśli to legacy (jeden klucz _legacy) → zapisz jako string (stary schemat).
    # * W przeciwnym razie → zapisz jako dict.
    if list(wynikowy_dict.keys()) == [KLUCZ_LEGACY]:
        tresc_do_zapisu: str | dict[str, str] = wynikowy_dict[KLUCZ_LEGACY]
    else:
        tresc_do_zapisu = wynikowy_dict

    zawartosc_yaml = zbuduj_yaml_wynikowy(kod, id_szablonu, tresc_do_zapisu, nazwa_pliku)
    cel.parent.mkdir(parents=True, exist_ok=True)
    with open(cel, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(zawartosc_yaml)

    tryb = "SURGICAL" if klucze_filtru else "FULL"
    n_sekcji = len(sekcje_przetlumaczone)
    print(
        f"✅  {kod}/{nazwa_pliku}: zapisano {cel.relative_to(ROOT)} "
        f"({tryb}, {n_sekcji} sekcji przetłumaczonych, {len(zawartosc_yaml):,} znaków)."
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
        "--szablony",
        type=str,
        default="",
        help="CSV nazw szablonów do przetłumaczenia (np. `dictionaries.yaml` "
             "lub bare-name `dictionaries`; rozszerzenie `.yaml` jest "
             "dosztukowywane automatycznie). Pusta wartość = wszystkie szablony "
             "z `dictionaries/pl/gui/dokumentacja/`. Sensowne, gdy część "
             "szablonów ma już aktualne tłumaczenia na dysku i nie chcesz "
             "ponownie spalać API-billa (np. `--szablony dictionaries`, gdy "
             "`manual.yaml` jest już przetłumaczony we wszystkich językach).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Pomiń SZABLONY, dla których "
             "`dictionaries/<kod>/gui/dokumentacja/<plik>.yaml` już istnieje "
             "(idempotentny rerun na poziomie pojedynczego pliku — gdy dorzucisz "
             "nowy szablon do PL, wystarczy `--wszystkie --skip-existing`, żeby "
             "dotłumaczyć tylko brakujące pozycje bez ponownego API-billingu na "
             "manual.yaml).",
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
    parser.add_argument(
        "--klucz",
        type=str,
        default=None,
        metavar="KLUCZ[,KLUCZ...]",
        help="Tłumacz TYLKO wskazane klucze sekcji (np. `krok_5_vocalizer,krok_5_alarm_nvda_2026`), "
             "reszta pliku zostaje z istniejącego tłumaczenia. "
             "Wymaga, by docelowy `<kod>/gui/dokumentacja/<plik>.yaml` już istniał W NOWYM SCHEMACIE "
             "(dict `tresc:` z sekcjami) — najpierw zrób FULL tłumaczenie bez --klucz, "
             "żeby plik nabrał nowego schematu. Surgical update jest tańszy API-wise: "
             "tłumaczysz np. tylko sekcję Vocalizer (~2 kB) zamiast całego manuala (~68 kB).",
    )
    args = parser.parse_args()
    if args.klucz and args.skip_existing:
        parser.error("--klucz i --skip-existing wzajemnie się wykluczają "
                     "(--klucz celowo nadpisuje wybrane sekcje w istniejącym pliku).")
    return args


def _filtruj_szablony(
    wszystkie: list[tuple[str, str, str]],
    wybor_csv: str,
) -> list[tuple[str, str, str]]:
    """Zostawia tylko te szablony PL, których nazwy figurują w ``wybor_csv``.

    Pusty CSV = brak filtrowania (zachowanie domyślne — wszystkie szablony).
    Akceptuje zarówno pełne nazwy plików (``manual.yaml``), jak i bare-names
    (``manual``); rozszerzenie ``.yaml`` jest dosztukowywane automatycznie.

    Twardy SystemExit, gdy CSV referuje do nieistniejącego szablonu — lepiej
    wcześnie wywalić niż cicho zrobić nic, bo użytkownik mógł pomylić nazwę.
    """
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

    dostepne = {s[0] for s in wszystkie}
    nieznane = sorted(wybrane - dostepne)
    if nieznane:
        raise SystemExit(
            f"❌ Nieznane szablony: {nieznane}.\n"
            f"   Dostępne w dictionaries/{KOD_ZRODLOWY}/{FOLDER_GUI}/{FOLDER_DOKUMENTACJA}/: "
            f"{sorted(dostepne)}"
        )

    return [s for s in wszystkie if s[0] in wybrane]


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
        wszystkie_szablony = wczytaj_szablony_pl()
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ {exc}")
        return 2

    szablony = _filtruj_szablony(wszystkie_szablony, args.szablony)
    if not szablony:
        print("❌ Filtr `--szablony` zostawił pustą listę — nic do roboty.")
        return 2

    pelna_lista = ", ".join(s[0] for s in wszystkie_szablony)
    wybrana_lista = ", ".join(s[0] for s in szablony)
    if len(szablony) == len(wszystkie_szablony):
        print(f"ℹ️  Szablony PL do przetłumaczenia: {wybrana_lista} (razem {len(szablony)}).")
    else:
        print(
            f"ℹ️  Szablony PL: filtr `--szablony` wybrał {wybrana_lista} "
            f"({len(szablony)}/{len(wszystkie_szablony)} dostępnych: {pelna_lista})."
        )

    klient: Any = None if args.dry_run else _zainicjuj_klienta_openai()

    sukcesy: list[str] = []
    porazki: list[str] = []
    # 13.4: import lazy — `core_poliglota` dorzuca docx/num2words. Skrypt
    # uruchamiany w czystym kontekście CLI nie powinien płacić za to przy
    # imporcie modułu, tylko gdy faktycznie idzie tłumaczyć.
    from core_poliglota import natywna_nazwa

    klucze_filtru: list[str] | None = None
    if args.klucz:
        klucze_filtru = [k.strip() for k in args.klucz.split(",") if k.strip()]
        if not klucze_filtru:
            print("❌ Flag --klucz podany, ale CSV jest pusty.")
            return 2
        print(f"🔎 Filtr --klucz ({len(klucze_filtru)} klucz/y): {klucze_filtru}")
        print(f"   Surgical update — pozostałe sekcje zostaną z istniejących tłumaczeń.")

    for kod in kody:
        nazwa_pl = MAPA_JEZYKOW[kod]
        nazwa_natywna = natywna_nazwa(kod)
        print(f"\n========== {kod.upper()} ({nazwa_pl} / {nazwa_natywna}) ==========")
        wszystko_ok = True
        for nazwa_pliku, id_szablonu, sekcje_pl in szablony:
            ok = tlumacz_szablon(
                kod,
                nazwa_pl,
                nazwa_natywna,
                klient,
                nazwa_pliku,
                id_szablonu,
                sekcje_pl,
                skip_existing=args.skip_existing,
                dry_run=args.dry_run,
                model=args.model,
                klucze_filtru=klucze_filtru,
            )
            if not ok:
                wszystko_ok = False
        (sukcesy if wszystko_ok else porazki).append(kod)

    print("\n========== PODSUMOWANIE ==========")
    print(f"✅ Sukces: {len(sukcesy)}/{len(kody)}  ({', '.join(sukcesy) or '—'})")
    if porazki:
        print(f"❌ Porażki (≥1 szablon nie powiódł się): {', '.join(porazki)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
