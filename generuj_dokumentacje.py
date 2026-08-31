"""
generuj_dokumentacje.py — Generator dokumentacji użytkownika (i18n).

Czyta szablony z `dictionaries/<kod>/gui/dokumentacja/*.yaml` (treść w
Markdownie od v18.8), podstawia placeholdery z `dictionaries/<kod>/gui/ui.yaml`
i renderuje wynik do `docs/<id>.<kod>.html` (README: zapis surowego Markdownu,
renderuje go GitHub).

Model danych:
  * `id` (w szablonie YAML) → rdzeń nazwy pliku wynikowego
    (np. "manual" → `docs/manual.pl.html`).
  * `tresc` (w szablonie YAML, block-scalar "|") → treść dokumentu w Markdownie
    z placeholderami `{klucz.zagniezdzony}` odpowiadającymi strukturze
    `ui.yaml`. Kropka w kluczu = schodzenie po ścieżce zagnieżdżonej.
  * Wartości nieznalezione w `ui.yaml` zostają jako literał `{klucz}` +
    ostrzeżenie w konsoli (nie rzucamy wyjątku — łagodna degradacja,
    żeby brakujące tłumaczenie nie blokowało wygenerowania reszty).

Konwencja nazewnicza plików wynikowych (decyzja 13.1, format od v18.8):
  * Rdzeń nazwy po angielsku (ASCII-only) — `manual`, `dictionaries` —
    żeby zagraniczny użytkownik nie musiał parsować polskich słów
    w Eksploratorze plików / Finderze.
  * Kod ISO języka jako środkowy człon (`.pl`, `.en`, `.ru`, …) —
    od razu widoczne, w jakim języku jest treść.
  * Rozszerzenie `.html` (do v18.7: `.txt`) — otwiera się w przeglądarce
    (każdy system ją ma): `<html lang>` przełącza syntezator czytnika
    ekranu na język dokumentu, nagłówki dają nawigację klawiszami 1-6/h,
    a formatowanie (pogrubienia, listy) czyta się dobrze też wzrokiem.

Użycie:
  python generuj_dokumentacje.py                # wygeneruj wszystkie języki
  python generuj_dokumentacje.py --waliduj      # wygeneruj + twardy check
                                                #   (exit 1, jeśli jakikolwiek
                                                #    placeholder NIE został
                                                #    rozwinięty przez ui.yaml)

Historia trybów weryfikacji:
  * Etap 1/5 miał tryb `--sprawdz`, który porównywał wygenerowane pliki
    z historycznymi `instrukcja.txt` i `dictionaries/instrukcja.txt`
    (tolerancja: 1 linia z wersją, whitespace-only). W Etapie 2/5 oba
    referencyjne pliki zostały usunięte z repozytorium — `docs/*.txt`
    stały się jedyną kanoniczną formą. Zastąpiliśmy więc tryb porównawczy
    trybem `--waliduj`, który sprawdza, co realnie chroni spójność:
    czy każdy `{placeholder}` w szablonach ma wartość w `ui.yaml`.

Moduł NIE zależy od wxPython — można go wywołać w headlessowym kontekście
(np. z `buduj_wydanie.py` przed pakowaniem paczki ZIP) bez inicjalizacji GUI.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

import dev_konsola


# ---------------------------------------------------------------------------
# STDOUT UTF-8 (fix dla Windowsa — cp1250 nie umie emoji jak ✅ ⚠️ ℹ️ ❌)
# ---------------------------------------------------------------------------
# Bez tego `print("✅ ...")` wywala UnicodeEncodeError w natywnym CMD (dziedziczy
# lokalną cp1250 zamiast UTF-8), zanim cokolwiek innego zdąży się zalogować.
# Od v18.25 jedna implementacja dla wszystkich dev-tooli → `dev_konsola`.
dev_konsola.skonfiguruj_stdout()


# ---------------------------------------------------------------------------
# Stałe ścieżek (wszystko względem katalogu, w którym leży ten skrypt)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DICT_DIR = ROOT / "dictionaries"
DOCS_DIR = ROOT / "docs"

# Single source of truth dla numeru wersji (od 13.4) — plik VERSION w roocie.
# Wczytywane raz przy imporcie, używane do rozwinięcia placeholdera
# `{numer_wersji}` zagnieżdżonego w wartościach `app.wersja` w ui.yaml
# (regex `_rozwin_placeholdery` nie iteruje rekursywnie, więc po pobraniu
# wartości robimy explicit replace w `_zamien`).
_PLIK_WERSJI = ROOT / "VERSION"
try:
    NUMER_WERSJI = _PLIK_WERSJI.read_text(encoding="utf-8").strip()
except OSError:
    NUMER_WERSJI = "?"

# Podfoldery w dictionaries/<kod>/gui/
FOLDER_GUI = "gui"
FOLDER_DOKUMENTACJA = "dokumentacja"
NAZWA_UI = "ui.yaml"

# ---------------------------------------------------------------------------
# GUARD NAGŁÓWKA FINALIZACJI (od v18.6) — draft NIE wchodzi do buildu
# ---------------------------------------------------------------------------
# Problem: świeże maszynowe tłumaczenie `ui.yaml`/szablonu docs to DRAFT do
# recenzji halucynacji. Gdyby maintainer zapomniał go sfinalizować (a tym
# bardziej gdyby native zostawił w bloku nagłówkowym własną notatkę „tu wrócę"),
# build wypuściłby paczkę z draftowymi treściami i nikt by nie zauważył — zwłaszcza
# przy dorzucaniu 10. języka. Guard egzekwuje kontrakt `--draft`/`--finalizuj`
# (patrz `przeglad_tlumaczen`) na wejściu do generacji docs.
#
# Reguła (whitelist, NIE blacklist): generujemy docs dla danego pliku TYLKO gdy
# jego blok nagłówkowy (wiodące komentarze `#` przed treścią) niesie kanoniczny
# marker finalizacji. Każdy inny stan = draft → odmowa.
#   * `pl` (źródło referencyjne) jest ZWOLNIONY — ma ręcznie pisany, bespoke
#     nagłówek bez markera (single source of truth, nie produkt autotłumacza).
#   * pozostałe języki: wymagany `MARKER_KANONICZNY`, zakazany `MARKER_DRAFTU`.
#   * dodatkowa (druga) linia obrony — blacklist markerów roboczych skanowana
#     WYŁĄCZNIE w bloku nagłówkowym (nie w tytule/treści → zerowe ryzyko
#     fałszywych trafień w naturalnym tekście).
#
# Import `przeglad_tlumaczen` jest LAZY z fallbackiem na literały — ten sam wzorzec
# samowystarczalności co `core_poliglota` niżej (generator musi działać też w
# kontekście zdegradowanym / u nie-maintainera bez całego toolingu).
_MARKERY_ROBOCZE = ("TODO", "FIXME", "XXX", "WIP", "DRAFT", "???")


def _markery_finalizacji() -> tuple[str, str]:
    """Zwraca `(MARKER_KANONICZNY, MARKER_DRAFTU)` z `przeglad_tlumaczen`.

    Lazy import z fallbackiem na literały — gdy moduł dev-toolingu jest nieobecny
    (np. po `git clone` bez prywatnej pamięci maintainera), guard działa dalej na
    wbudowanych stałych, zamiast się wywalić.
    """
    try:
        import przeglad_tlumaczen as pt
        return pt.MARKER_KANONICZNY, pt.MARKER_DRAFTU
    except ImportError:
        return "NIE edytuj ręcznie", "⚠ WORKING DRAFT FOR REVIEW"


def _blok_naglowka(sciezka: Path) -> str:
    """Zwraca surowy blok wiodących komentarzy `#` pliku (przed pierwszą treścią).

    `yaml.safe_load` gubi komentarze, więc baner finalizacji/draftu czytamy
    wprost z tekstu. Zbieramy linie od początku pliku, dopóki są puste albo
    zaczynają się od `#`; pierwsza linia treści (np. `id:`) kończy blok.
    Zwraca "" przy braku pliku (wywołujący potraktuje jako brak kanonu).
    """
    if not sciezka.is_file():
        return ""
    linie: list[str] = []
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            for surowa in fh:
                striped = surowa.strip()
                if striped == "" or striped.startswith("#"):
                    linie.append(surowa)
                    continue
                break
    except OSError:
        return ""
    return "".join(linie)


def _status_naglowka(sciezka: Path, jezyk: str) -> tuple[bool, str]:
    """Sprawdza, czy plik jest sfinalizowany (kanoniczny), czy to draft.

    Returns:
        `(True, "")` — nagłówek kanoniczny (albo `pl`, zwolniony jako źródło);
        `(False, powod)` — draft / nagłówek niekanoniczny; `powod` to krótki
        opis po angielsku (ląduje w logu buildu, EN-only z założenia).
    """
    # Źródło referencyjne (pl): ręcznie pisany, ZAUFANY nagłówek — pełne
    # zwolnienie PRZED blacklistą. Guard celuje w maszynowe tłumaczenia i notatki
    # natywów w paczkach obcych, nie w bespoke komentarze maintainera (które
    # legalnie zawierają prozę typu „literały do osobnego TODO refaktoru").
    if jezyk == _FOLDER_REFERENCYJNY:
        return True, ""

    naglowek = _blok_naglowka(sciezka)
    marker_kanon, marker_draft = _markery_finalizacji()

    # 1) Świeży draft (jeszcze nie przepuszczony przez --finalizuj).
    if marker_draft in naglowek:
        return False, "still a WORKING DRAFT (not finalized via --finalizuj)"
    # 2) Brak kanonicznego markera finalizacji = zakładamy draft.
    if marker_kanon not in naglowek:
        return False, "no canonical finalization header (assumed draft)"
    # 3) Druga linia obrony: notatka robocza dopisana OBOK kanonicznego nagłówka
    #    (np. native zostawił sobie „TODO sprawdzić akcenty"). Skanujemy WYŁĄCZNIE
    #    blok komentarzy — zerowe ryzyko trafienia w naturalny tekst tytułu/treści.
    naglowek_upper = naglowek.upper()
    for token in _MARKERY_ROBOCZE:
        if token in naglowek_upper:
            return False, f"working-note marker '{token}' found in the header block"
    return True, ""

# 13.4: globalne placeholdery dynamiczne (liczone z dysku przy każdym wywołaniu
# `generuj()` — tanie, deterministyczne). Pozwalają w szablonach docs używać
# wartości typu `{liczba_szyfrow}` zamiast hardkodowanego "6", dzięki czemu
# dorzucenie nowego YAML-a do `dictionaries/pl/szyfry/` aktualizuje dokumentację
# wszystkich języków przy najbliższym `generuj_dokumentacje.py` — bez ponownego
# tłumaczenia (placeholdery są zamrożone w autotłumaczu jako `⟦i⟧` i wracają
# w wynikowych YAML-ach 1:1 — generator rozwija je dopiero przy renderze .txt).
_FOLDER_REFERENCYJNY = "pl"   # paczka, z której liczymy referencyjne wartości

# Sekcje trzymane w PL źródle WYŁĄCZNIE po to, by autotłumacz (buduj_wielojezyczne
# _docs.py) przełożył je na pozostałe języki — ale POMIJANE w wyjściu PL. Wzorzec:
# wyjaśnienie polskiego nazewnictwa katalogów/folderów (skrypty, opowiesci,
# podstawy, akcenty…) jest cenne dla użytkownika/dewelopera spoza PL, ale Polak
# go nie potrzebuje. Klucz mapy = `id` szablonu (== nazwa pliku bez .yaml dla
# readme/manual), wartość = zbiór nazw sekcji do pominięcia, gdy jezyk == 'pl'.
SEKCJE_POMIJANE_W_PL: dict[str, set[str]] = {
    "readme": {"polskie_nazewnictwo"},
    "manual": {"krok_7b_polskie_nazewnictwo"},
}

# 15.2: per-szablon override domyślnej lokalizacji + nazwy pliku wyjściowego.
# Od v18.8 szablony są pisane w Markdownie, a domyślnym wyjściem jest
# `docs/<id>.<iso>.html` (render MD → HTML, patrz `_renderuj_html`): plik
# otwiera się w przeglądarce z natywnym `<html lang="<iso>">` (czytnik ekranu
# dobiera syntezator), nawigacją nagłówkami (klawisze 1/h w NVDA) i pełnym
# Unicode — bez zależności od Notatnika/Worda. Wpis w `KONFIG_SZABLONOW`
# nadpisuje dla konkretnego id:
#   - katalog:        Path do katalogu docelowego (domyślnie DOCS_DIR)
#   - rozszerzenie:   'html' (domyślnie) | 'md' | dowolne inne
#   - render:         'html' (domyślnie — Markdown → pełny dokument HTML) |
#                     'surowy' (zapis 1:1 — README, którego Markdown renderuje
#                               GitHub, nie my)
#   - iso_w_nazwie:   'zawsze' (domyślnie, `<id>.<iso>.<ext>`) |
#                     'smart_en' (en bez ISO: `<id>.<ext>`, reszta z ISO:
#                                 `<id>.<iso>.<ext>`) — wzorzec README.md
#                                 (en jako kanoniczny GitHub landing) +
#                                 README.pl.md/README.de.md/... dla reszty.
# Lokalizacja+rozszerzenie czytane raz przy generacji; nie potrzebują reloadu
# między build'ami. Dorzucenie kolejnego szablonu = jeden wpis w tym słowniku
# + plik `dictionaries/pl/gui/dokumentacja/<id>.yaml` (i analogiczne dla
# pozostałych jzk po retranslate).
KONFIG_SZABLONOW: dict[str, dict] = {
    "readme": {
        "katalog": ROOT,
        "rozszerzenie": "md",
        "render": "surowy",
        "iso_w_nazwie": "smart_en",
    },
}


def _sciezka_wyjscia(
    id_szablonu: str,
    jezyk: str,
    docelowy_katalog: Path,
) -> Path:
    """Zwraca docelową ścieżkę pliku wynikowego wg `KONFIG_SZABLONOW`.

    Default (brak wpisu): `docelowy_katalog / "<id>.<jezyk>.html"`.
    """
    cfg = KONFIG_SZABLONOW.get(id_szablonu, {})
    katalog = cfg.get("katalog", docelowy_katalog)
    rozszerzenie = cfg.get("rozszerzenie", "html")
    tryb_iso = cfg.get("iso_w_nazwie", "zawsze")

    if tryb_iso == "smart_en" and jezyk == "en":
        nazwa = f"{id_szablonu}.{rozszerzenie}"
    else:
        nazwa = f"{id_szablonu}.{jezyk}.{rozszerzenie}"
    return katalog / nazwa


# ---------------------------------------------------------------------------
# Render Markdown → HTML (od v18.8)
# ---------------------------------------------------------------------------
# Szablony docs są pisane w Markdownie (nagłówki `#`/`##` per sekcja, backticki
# wokół literałów technicznych typu `skrypty/<nazwa>.txt`). Render daje trzy
# rzeczy, których .txt nie miał: (1) `<html lang="<iso>">` — czytnik ekranu
# przełącza syntezator na język dokumentu, (2) nawigację nagłówkami (NVDA:
# klawisze 1-6/h), (3) format czytelny też dla widzących (pogrubienia, listy).
#
# Rozszerzenia python-markdown:
#   * nl2br      — pojedynczy `\n` = `<br>`; historyczna treść manuali używa
#                  „linia = krok/wiersz" bez pustych linii między nimi, więc
#                  bez nl2br Markdown skleiłby je w jeden akapit.
#   * sane_lists — listy tylko z konsekwentnych markerów (mniej fałszywych
#                  <ol> z liczb w naturalnym tekście).
#
# Minimalny CSS: czytelna szerokość kolumny + tryb ciemny przez
# `prefers-color-scheme` (zero JS, zero zewnętrznych zasobów — plik działa
# offline z dysku, jak dotychczasowy .txt).
_HTML_STYL = """\
body { max-width: 75ch; margin: 2rem auto; padding: 0 1rem;
       font-family: system-ui, sans-serif; line-height: 1.5; }
code { font-family: ui-monospace, Consolas, monospace; }
@media (prefers-color-scheme: dark) {
  body { background: #1b1b1b; color: #e6e6e6; }
  a { color: #8ab4f8; }
}"""

# Tagi, które legalnie może wyprodukować nasz render (markdown + nl2br +
# sane_lists na treści szablonów). Wszystko spoza tej listy w wynikowym HTML
# oznacza, że surowy `<fragment>` z szablonu przeszedł do dokumentu jako
# nieznany tag (przeglądarka by go POŁKNĘŁA — treść znika dla usera).
# Egzekwowane w `waliduj()` — patrz bramka „RAW-HTML".
_TAGI_DOZWOLONE = frozenset({
    "html", "head", "meta", "title", "style", "body",
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "em", "strong", "code", "pre",
    "blockquote", "a",
})

_TAG_REGEX = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)")


def _tytul_dokumentu(tresc_md: str) -> str:
    """Wyciąga tytuł do ``<title>``: pierwszy nagłówek `# ` albo pierwsza linia."""
    m = re.search(r"^#{1,2} +(.+)$", tresc_md, flags=re.MULTILINE)
    tytul = m.group(1) if m else (tresc_md.strip().splitlines() or ["Dokument"])[0]
    return tytul.strip().lstrip("#").strip()


def _renderuj_html(tresc_md: str, jezyk: str) -> str:
    """Renderuje treść Markdown do pełnego, samodzielnego dokumentu HTML5.

    Raises:
        RuntimeError: gdy biblioteka `markdown` nie jest zainstalowana —
            celowo GŁOŚNO (build/`--waliduj` musi paść), bo cicha degradacja
            zostawiłaby paczkę bez plików, na które wskazuje menu Pomoc.
    """
    try:
        import markdown
    except ImportError as exc:                              # pragma: no cover
        raise RuntimeError(
            "Missing the `markdown` package (docs render Markdown → HTML "
            "since v18.8). Fix: .venv/Scripts/pip install markdown "
            "(it is listed in requirements.txt)."
        ) from exc

    body = markdown.markdown(
        tresc_md, extensions=["nl2br", "sane_lists"], output_format="html5",
    )
    tytul = _tytul_dokumentu(tresc_md)
    tytul_safe = (tytul.replace("&", "&amp;").replace("<", "&lt;")
                       .replace(">", "&gt;"))
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{jezyk}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{tytul_safe}</title>\n"
        f"<style>\n{_HTML_STYL}\n</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


# ---------------------------------------------------------------------------
# BRAMKA TAGÓW AKCENTU (od v18.25) — przykład, który user WPISUJE, musi działać
# ---------------------------------------------------------------------------
# Podręczniki uczą składni tagu Księgi Świata („[Marek] - ma akcent francuski").
# Zmierzone przy okazji v18.25: przykład był MARTWY we wszystkich dziewięciu
# paczkach — parser brał słowo z niewłaściwej strony wyzwalacza (pl/es/fr:
# „ma"/„tiene"/„un"), albo cytat podawał NAZWĘ JĘZYKA w języku paczki
# (en „swedish", de „schwedischen") zamiast identyfikatora pliku reguł, albo
# słowo-wyzwalacz stało w formie nieobecnej w `slowo_akcent` (is „hreim").
# Żadna dotychczasowa bramka tego nie widziała: cytat jest poprawnym językiem
# docelowym i nie ma w nim ani polskich znaków, ani placeholderów.
#
# Ta bramka puszcza każdy cytat z docsów przez PRAWDZIWY parser Księgi Świata
# i wymaga, żeby wyłuskana nazwa akcentu była identyfikatorem. Import silnika
# jest lazy z łagodną degradacją (jak leak gate) — kontrybutor bez pełnego
# dev-env dostaje notę, nie fałszywy błąd.

# Cytaty w szablonach: "…", „…", « … ». Wnętrze bez znaków cudzysłowu, więc
# dopasowanie kończy się na pierwszym zamknięciu.
_RE_CYTAT = re.compile(r'["„«]\s*([^"„«»\n]{5,200}?)\s*["»]')

# Identyfikatory akcentów, których podręcznik uczy dopiero UTWORZYĆ (POZIOM 2 —
# duplikacja `finski.yaml`), więc pliku o tej nazwie nie ma jeszcze na dysku.
# Bramka podstawia w ich miejsce akcent realnie obecny w tej paczce i puszcza
# cytat przez silnik — sprawdza więc SKŁADNIĘ zapisu (czy słowo stoi po dobrej
# stronie wyzwalacza), nie istnienie pliku, którego user dopiero utworzy.
_ID_AKCENTOW_Z_INSTRUKCJI = ("szwedzki", "dunski")


def _bramka_tagow_akcentu() -> dict[str, list[str]]:
    """Sprawdza w szablonach docs każdy cytat wyglądający jak tag akcentu.

    Kwalifikacja cytatu: zawiera nawias kwadratowy (tag mówcy) ORAZ
    słowo-wyzwalacz z ``podstawy.yaml::slowo_akcent`` — z DOWOLNEJ paczki, nie
    tylko tej sprawdzanej. Ta asymetria jest celowa: cytat, który został po
    polsku („[Joana] akcent fiński" w paczce islandzkiej i rosyjskiej), nie
    zawiera ani jednego wyzwalacza swojej paczki, więc kwalifikacja „tylko
    własne słowa" przepuściłaby go w milczeniu — a to najczęstszy wariant tej
    pomyłki. Parsujemy natomiast ZAWSZE w języku paczki, bo tak zrobi aplikacja.

    Przykład jest zdrowy, gdy parser wyłuska nazwę i jest ona identyfikatorem
    akcentu tej paczki (``czy_znany_akcent``). Identyfikatory z instrukcji
    tworzenia nowego akcentu podmieniamy przed parsowaniem na akcent realnie
    obecny w paczce — inaczej bramka zgłaszałaby własny podręcznik.

    Returns:
        ``{ścieżka_relatywna: [opisy znalezisk]}`` — pusty dict = czysto.
        Pusty dict zwracamy też przy braku silnika (degradacja) — powód
        raportuje ``waliduj`` osobno.
    """
    try:
        import core_poliglota as cp                              # noqa: PLC0415
        import core_rezyser as cr                                # noqa: PLC0415
    except ImportError:
        return {}

    kody = sorted(
        f.parent.parent.name
        for f in DICT_DIR.glob(f"*/{FOLDER_GUI}/{FOLDER_DOKUMENTACJA}")
    )
    slowa_per_kod = {k: [w.lower() for w in cp.slowa_akcentu(k)] for k in kody}
    wszystkie_slowa = {w for lista in slowa_per_kod.values() for w in lista}

    def _zastepnik(kod: str) -> str | None:
        """Pierwszy akcent realnie obecny w tej paczce (`finski`, `polski`…)."""
        for cfg in cp.lista_wariantow(cp.TRYB_REZYSER, kod):
            if cfg.get("kategoria") == "akcent" and cfg.get("id"):
                return str(cfg["id"])
        return None

    znaleziska: dict[str, list[str]] = {}
    for kod in kody:
        folder = DICT_DIR / kod / FOLDER_GUI / FOLDER_DOKUMENTACJA
        slowa = slowa_per_kod[kod]
        zastepnik = _zastepnik(kod)
        for szablon in sorted(folder.glob("*.yaml")):
            powody: list[str] = []
            tresc = szablon.read_text(encoding="utf-8")
            for cytat in _RE_CYTAT.findall(tresc):
                if "[" not in cytat or "]" not in cytat:
                    continue
                if not any(w in cytat.lower() for w in wszystkie_slowa):
                    continue
                probka = cytat
                if zastepnik:
                    for id_instrukcji in _ID_AKCENTOW_Z_INSTRUKCJI:
                        probka = re.sub(id_instrukcji, zastepnik, probka,
                                        flags=re.IGNORECASE)
                nazwy = [
                    dane["nazwa"]
                    for dane in cr.zbuduj_mape_akcentow(probka, kod).values()
                    if dane["nazwa"]
                ]
                if not nazwy:
                    powody.append(
                        f"{cytat!r}: the parser extracts NO accent name "
                        f"(trigger words for `{kod}`: {slowa})"
                    )
                    continue
                zle = [n for n in nazwy if not cr.czy_znany_akcent(n, kod)]
                if zle:
                    powody.append(
                        f"{cytat!r}: extracted {zle} — not an accent id of the "
                        f"`{kod}` pack (the word next to the trigger must be a "
                        f"RULE FILE name from `dictionaries/{kod}/akcenty/`)"
                    )
            if powody:
                znaleziska[str(szablon.relative_to(ROOT))] = powody
    return znaleziska


def _obce_tagi_w_html(tekst_html: str) -> list[str]:
    """Zwraca posortowaną listę tagów spoza `_TAGI_DOZWOLONE` (bramka RAW-HTML)."""
    znalezione = {m.group(1).lower() for m in _TAG_REGEX.finditer(tekst_html)}
    return sorted(znalezione - _TAGI_DOZWOLONE)

# Regex placeholdera: {klucz} albo {klucz.zagniezdzony.z.kropkami}
# - pierwszy znak: litera lub podkreślenie
# - dalej: litery, cyfry, podkreślenia, kropki (dla ścieżek zagnieżdżonych)
PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")

# Regex akceleratora wxPython: `&` przed dowolną literą Unicode (A-Z, a-z,
# także polskie Ą/ę/Ł itd.). `[^\W\d_]` w trybie domyślnym Pythona działa
# w Unicode, więc łapie akceleratory na przetłumaczonych literach w EN/RU/FI.
# Nie ruszamy `& ` z neutralnych kontekstów typu "Tom & Jerry" — bez litery
# po `&` regex się nie dopasuje.
AKCELERATOR_REGEX = re.compile(r"&([^\W\d_])", flags=re.UNICODE)



# ---------------------------------------------------------------------------
# Wczytywanie UI i szablonów dokumentacji
# ---------------------------------------------------------------------------
def _wczytaj_yaml(sciezka: Path) -> dict[str, Any]:
    """Wczytuje plik YAML jako dict. Zwraca {} przy awarii (nie rzuca)."""
    if not sciezka.is_file():
        return {}
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        print(f"⚠️  Failed to load {sciezka}: {exc}")
        return {}
    return dane if isinstance(dane, dict) else {}


def _wczytaj_ui(jezyk: str) -> dict[str, Any]:
    """Zwraca dict z ``dictionaries/<jezyk>/gui/ui.yaml`` (lub {} przy braku)."""
    return _wczytaj_yaml(DICT_DIR / jezyk / FOLDER_GUI / NAZWA_UI)


def _scal_tresc_sekcjami(tresc: Any) -> str | None:
    """Scala wartość ``tresc`` z szablonu YAML w jeden tekst dokumentu.

    Backward-compat dwa schematy:

    * **Stary** (do v15.1): ``tresc: |`` jako pojedynczy block-scalar z całym
      manualem w środku. Zwracamy 1:1 — nic do scalania.
    * **Nowy** (od v15.2): ``tresc`` jako słownik ``{klucz_sekcji: tresc_sekcji}``
      — każda wartość to block-scalar z jedną sekcją (np. ``krok_1``, ``vocalizer``,
      ``changelog_15``). Skalamy w kolejności WSTAWIENIA (Python 3.7+ dict zachowuje
      insertion order, ``yaml.safe_load`` ją honoruje). Między sekcjami wstawiamy
      DWIE puste linie (``\\n\\n\\n``) — historyczny separator manuala PL używany
      konsystentnie między KROKami i akapitami changelogowymi w stringowej wersji
      ``tresc:`` z v15.1. Normalizacja ``rstrip("\\n") + "\\n\\n\\n".join``
      daje deterministyczny output niezależnie od stylu block-scalar (``|`` clip
      vs ``|+`` keep): końcowe ``\\n`` z każdej sekcji są ucinane przed joinerem,
      więc finalnie zawsze są dokładnie dwie puste linie między sekcjami.

    Zwraca ``None`` przy nieobsługiwanym typie — wywołujący wypisuje ostrzeżenie
    i pomija ten plik (łagodna degradacja, jak reszta loadera).
    """
    if isinstance(tresc, str):
        return tresc
    if isinstance(tresc, dict):
        sekcje: list[str] = []
        for klucz, wartosc in tresc.items():
            if not isinstance(wartosc, str):
                print(f"⚠️  Section '{klucz}' is not a string — skipping.")
                continue
            sekcje.append(wartosc.rstrip("\n"))
        if not sekcje:
            return ""
        return "\n\n\n".join(sekcje) + "\n"
    return None


def _wczytaj_szablony(jezyk: str) -> list[tuple[str, str, Path]]:
    """Zwraca listę (id, tresc, sciezka) dla każdego szablonu w danym języku.

    Szablon = plik YAML w ``dictionaries/<jezyk>/gui/dokumentacja/``
    z polami ``id`` (rdzeń nazwy pliku wynikowego) oraz ``tresc``.

    Od v15.2 ``tresc`` może być:
      * stringiem (stary schemat — block-scalar z całością manuala);
      * słownikiem (nowy schemat — klucze sekcji w kolejności wstawiania).
    Zob. :func:`_scal_tresc_sekcjami` po szczegóły scalania.
    """
    folder = DICT_DIR / jezyk / FOLDER_GUI / FOLDER_DOKUMENTACJA
    if not folder.is_dir():
        return []

    szablony: list[tuple[str, str, Path]] = []
    for plik in sorted(folder.glob("*.yaml")):
        dane = _wczytaj_yaml(plik)
        if not dane:
            continue
        id_szablonu = dane.get("id") or plik.stem
        if not isinstance(id_szablonu, str):
            print(f"⚠️  Skipping {plik}: the 'id' field must be a string.")
            continue
        tresc_raw = dane.get("tresc", "")
        # Skip-w-PL: usuń sekcje trzymane wyłącznie pod autotłumacz, których
        # Polak nie potrzebuje (patrz SEKCJE_POMIJANE_W_PL). Tylko dla schematu
        # dict-sekcji i tylko gdy generujemy paczkę referencyjną (pl).
        if jezyk == _FOLDER_REFERENCYJNY and isinstance(tresc_raw, dict):
            do_pominiecia = SEKCJE_POMIJANE_W_PL.get(id_szablonu, set())
            if do_pominiecia:
                tresc_raw = {
                    k: v for k, v in tresc_raw.items() if k not in do_pominiecia
                }
        tresc_scalona = _scal_tresc_sekcjami(tresc_raw)
        if tresc_scalona is None:
            print(f"⚠️  Skipping {plik}: 'tresc' must be a string or a dict of sections.")
            continue
        szablony.append((id_szablonu, tresc_scalona, plik))
    return szablony


def _jezyki_ze_szablonami() -> list[str]:
    """Zwraca posortowaną listę kodów języków, dla których generujemy docs/.

    Od 13.1 stosujemy ten sam filtr kompletności co `dostepne_jezyki_bazowe()`
    w `core_poliglota.py` — generujemy `docs/<id>.<kod>.txt` tylko dla języków
    z PEŁNYM pakietem (`podstawy.yaml` + `gui/ui.yaml` + `akcenty/*.yaml` ≥ 1
    + `szyfry/*.yaml` ≥ 1). Stuby z samym podfolderem `gui/dokumentacja/`
    pomija — w aplikacji i tak są zafiltrowane z menu „Język interfejsu"
    i z listy „obsługiwanych języków", więc dorzucanie użytkownikowi
    instrukcji obsługi w „nieistniejącym" języku byłoby tylko *cosmetic
    confusion*.

    Import `core_poliglota` jest LAZY — generator może być wciąż wywoływany
    standalone (np. z CLI), zanim załadowane są wszystkie moduły aplikacji.
    Gdy import się nie uda (np. minimalny kontekst, brak `docx` lub
    `num2words`), wracamy do zachowania historycznego: wszystkie foldery
    z `gui/dokumentacja/` są generowane (niemaskowanie).
    """
    if not DICT_DIR.is_dir():
        return []

    try:
        from core_poliglota import _jezyk_kompletny
    except ImportError:
        _jezyk_kompletny = None

    wyniki = []
    for wpis in sorted(DICT_DIR.iterdir()):
        if not (wpis.is_dir() and (wpis / FOLDER_GUI / FOLDER_DOKUMENTACJA).is_dir()):
            continue
        if _jezyk_kompletny is not None and not _jezyk_kompletny(wpis.name):
            continue
        wyniki.append(wpis.name)
    return wyniki


# ---------------------------------------------------------------------------
# Podstawianie placeholderów (identyczna semantyka co i18n._pobierz)
# ---------------------------------------------------------------------------
def _pobierz_wartosc(dane: dict[str, Any], klucz: str) -> Any:
    """Zwraca wartość pod kluczem zagnieżdżonym (kropka = schodzenie w dół)."""
    aktualne: Any = dane
    for segment in klucz.split("."):
        if isinstance(aktualne, dict) and segment in aktualne:
            aktualne = aktualne[segment]
        else:
            return None
    return aktualne


def _normalizuj_etykiete(wartosc: str) -> str:
    """Usuwa z etykiety GUI dekoratory wxPython niepotrzebne w dokumentacji.

    Etykiety w ``ui.yaml`` są zapisane tak, jak wxPython ich oczekuje:
        * ``&Reżyser``         — `&` przed literą robi z niej akcelerator
                                 (Alt+R w GUI). W dokumentacji tekstowej
                                 `&` wygląda jak literówka.
        * ``Strona główna\tCtrl+0`` — znak tabulatora oddziela etykietę
                                       menu od skrótu klawiszowego.
                                       W docs interesuje nas tylko sama
                                       etykieta; skrót („Ctrl+0") cytujemy
                                       osobno w tekście opisowym.

    Ta funkcja jest wywoływana TYLKO tutaj — moduł `i18n.py`, używany przez
    runtime GUI, zachowuje oryginalne stringi z `&`/`\\t` bez zmian,
    bo wxPython ich potrzebuje.
    """
    # 1) Ucinamy skrót klawiszowy. Pierwszy `\t` jest separatorem.
    if "\t" in wartosc:
        wartosc = wartosc.split("\t", 1)[0].rstrip()
    # 2) Usuwamy `&` tylko wtedy, gdy działa jako akcelerator (przed literą).
    wartosc = AKCELERATOR_REGEX.sub(r"\1", wartosc)
    return wartosc


def _zbuduj_placeholdery_globalne() -> dict[str, str]:
    """Liczy globalne placeholdery dynamiczne z dysku.

    13.4: zamiast hardkodować w PL-szablonach „8 plików z akcentami" / „sześć
    sztuk" / „na razie tylko polski", używamy nazwanych tokenów (`{liczba_szyfrow}`,
    `{lista_kompletnych_jezykow_natywnie}`), a generator liczy ich wartości na
    żywo z dysku tuż przed renderem .txt. Dorzucenie nowego akcentu do paczki
    PL → kolejny `python generuj_dokumentacje.py` aktualizuje docs WSZYSTKICH
    języków bez ponownego tłumaczenia (placeholdery są zamrożone w autotłumaczu
    jako ⟦i⟧ i wracają w wynikowych YAML-ach 1:1 — generator rozwija je dopiero
    teraz, przy renderze).

    Wartości referencyjne brane są z `dictionaries/pl/` (rdzeń projektu, zawsze
    kompletny). Import `core_poliglota` jest LAZY (jak w `_jezyki_ze_szablonami`),
    żeby generator pozostał użyteczny w minimalnym kontekście CLI bez wxPython.
    """
    pusty: dict[str, str] = {}
    if not DICT_DIR.is_dir():
        return pusty

    try:
        import core_poliglota as cp
    except ImportError:
        return pusty

    pl_akcenty_dir = DICT_DIR / _FOLDER_REFERENCYJNY / "akcenty"
    pl_szyfry_dir  = DICT_DIR / _FOLDER_REFERENCYJNY / "szyfry"
    pl_rezyser_dir = DICT_DIR / _FOLDER_REFERENCYJNY / "rezyser"
    pl_opowiesci_dir = DICT_DIR / _FOLDER_REFERENCYJNY / "opowiesci"

    akcenty_lista = cp.lista_wariantow(cp.TRYB_REZYSER, _FOLDER_REFERENCYJNY)
    szyfry_lista  = cp.lista_wariantow(cp.TRYB_SZYFRANT, _FOLDER_REFERENCYJNY)
    kompletne_jezyki = cp.dostepne_jezyki_bazowe()

    return {
        # Numer wersji aplikacji — pojedyncze źródło prawdy w pliku VERSION.
        # Dotąd dostępny tylko nested (jako placeholder w wartości `app.wersja`
        # z ui.yaml); od 13.4 również standalone na poziomie szablonu.
        "numer_wersji": NUMER_WERSJI,
        # Liczba akcentów stricte fonetycznych (kategoria == "akcent");
        # pomija oczyszczenia i naprawiacz_tagow.
        "liczba_akcentow_jezykowych": str(
            sum(1 for a in akcenty_lista if a.get("kategoria") == "akcent")
        ),
        # Liczba wszystkich plików w katalogu (akcenty + utility).
        "liczba_plikow_w_akcentach": str(
            len([p for p in pl_akcenty_dir.glob("*.yaml")]) if pl_akcenty_dir.is_dir() else 0
        ),
        "liczba_szyfrow":          str(len(szyfry_lista)),
        # Wyklucz `baza.yaml` (od v17.10 — wspólne wrappery kontekstu LLM, NIE tryb
        # pracy): dokumentacja WYLICZA konkretne pliki (burza/skrypt/audiobook +
        # postprodukcje: postprod_tytuly, postprod_streszczenie od v18.13,
        # postprod_publikacja od v18.14), więc licznik musi pasować do tej listy
        # (dziś 6 = 3 tryby + 3 postprodukcje), nie do liczby wszystkich plików
        # w folderze. UWAGA dla lingwisty: zdanie z tym placeholderem w readme
        # musi znieść KAŻDĄ wartość — w językach z fleksją liczebnika (pl, ru)
        # trzymaj liczbę w nawiasie zamiast odmieniać rzeczownik po niej.
        "liczba_trybow_rezysera":  str(
            len([p for p in pl_rezyser_dir.glob("*.yaml") if p.stem != "baza"])
            if pl_rezyser_dir.is_dir() else 0
        ),
        "liczba_trybow_opowiesci": str(
            len([p for p in pl_opowiesci_dir.glob("*.yaml")]) if pl_opowiesci_dir.is_dir() else 0
        ),
        "liczba_kompletnych_jezykow":          str(len(kompletne_jezyki)),
        "lista_kompletnych_jezykow_natywnie":  cp.lista_wspieranych_jezykow_natywnie(),
    }


def _rozwin_placeholdery(
    szablon: str,
    ui_dane: dict[str, Any],
    placeholdery_globalne: dict[str, str] | None = None,
) -> tuple[str, list[str]]:
    """Podstawia wszystkie ``{klucz}`` wartościami z ``ui_dane`` i z placeholderów globalnych.

    Wartości przechodzą przez `_normalizuj_etykiete` — wstawiamy do
    dokumentacji „suchą" wersję etykiety bez `&` akceleratora i bez
    końcówki `\\tCtrl+…`, żeby tekst .txt czytało się naturalnie nawet
    dla przycisków/menu, które w GUI mają te dekoratory.

    Args:
        szablon:               Tekst z ``{placeholderami}`` do rozwinięcia.
        ui_dane:               Słownik z `dictionaries/<jezyk>/gui/ui.yaml`.
        placeholdery_globalne: Wartości liczone z dysku (liczba_szyfrow itd.) —
                               jeśli None, generator wywoła sam :func:`_zbuduj_placeholdery_globalne`.
                               Eksponowane jako parametr, żeby testy mogły wstrzyknąć
                               zmockowane wartości i `generuj()` mogło je policzyć
                               raz na cały batch (zamiast na każdy szablon).

    Returns:
        Krotka (wynikowa_tresc, lista_brakujacych_kluczy).
        Brakujące klucze zostają w tekście jako literał ``{klucz}`` i trafiają
        na listę — wywołujący może wypisać ostrzeżenie.
    """
    brakujace: list[str] = []
    globalne = placeholdery_globalne if placeholdery_globalne is not None else _zbuduj_placeholdery_globalne()

    def _zamien(match: re.Match[str]) -> str:
        klucz = match.group(1)

        # 1. Najpierw spróbuj rozwinąć przez globalny słownik dynamiczny —
        #    tu siedzą `numer_wersji`, `liczba_szyfrow` itd. Globalne placeholdery
        #    wygrywają z ui.yaml, gdyby ktoś przypadkiem zdefiniował klucz
        #    o tej samej nazwie (single source of truth = dysk, nie ui.yaml).
        if klucz in globalne:
            return globalne[klucz]

        # 2. Reszta — przez ścieżkę z ui.yaml.
        wartosc = _pobierz_wartosc(ui_dane, klucz)
        if wartosc is None or not isinstance(wartosc, str):
            brakujace.append(klucz)
            return match.group(0)   # zostaw oryginalny {klucz}
        # Drugi krok: rozwiń zagnieżdżony placeholder {numer_wersji}, jeśli
        # występuje w wartości (np. `app.wersja: "{numer_wersji} – Sufiks"`
        # w ui.yaml — od 13.4 numer wersji żyje w pliku VERSION).
        if "{numer_wersji}" in wartosc:
            wartosc = wartosc.replace("{numer_wersji}", NUMER_WERSJI)
        return _normalizuj_etykiete(wartosc)

    wynik = PLACEHOLDER_REGEX.sub(_zamien, szablon)
    return wynik, brakujace



# ---------------------------------------------------------------------------
# Główna funkcja generatora
# ---------------------------------------------------------------------------
def generuj(
    docelowy_katalog: Path = DOCS_DIR,
    *,
    cicho: bool = False,
    zbieraj_brakujace: dict[str, list[str]] | None = None,
    zbieraj_drafty: dict[str, str] | None = None,
) -> list[Path]:
    """Generuje wszystkie pliki ``docs/<id>.<kod>.html`` z szablonów YAML.

    Args:
        docelowy_katalog:   Gdzie zapisać wynikowe pliki (domyślnie ``docs/``).
        cicho:              Czy pominąć przyjazne komunikaty print (dla testów).
        zbieraj_brakujace:  Jeśli podasz pusty dict, funkcja wypełni go
                            mapowaniem ``"<jezyk>/<id_szablonu>"`` →
                            posortowana lista unikalnych brakujących placeholderów.
                            Używane przez tryb ``--waliduj`` do zwrócenia
                            twardego exit code po zakończeniu generacji.
        zbieraj_drafty:     Jeśli podasz pusty dict, funkcja wypełni go
                            mapowaniem ``"<jezyk>/ui.yaml"`` lub
                            ``"<jezyk>/<id_szablonu>"`` → powód (EN) odrzucenia
                            niesfinalizowanego (draftowego) nagłówka. Plik z
                            takim nagłówkiem NIE jest generowany (guard od v18.6).
                            Używane przez ``--waliduj`` (głośne ostrzeżenie + exit 1)
                            i ``build_release`` (bezwarunkowy FATAL).

    Returns:
        Lista ścieżek wygenerowanych plików.
    """
    docelowy_katalog.mkdir(exist_ok=True)
    wyniki: list[Path] = []

    jezyki = _jezyki_ze_szablonami()
    if not jezyki and not cicho:
        print("ℹ️  Brak folderów dictionaries/<kod>/gui/dokumentacja/ — nic do zrobienia.")
        return wyniki

    # 13.4: licz globalne placeholdery raz na batch — niezależne od języka
    # docelowego (wszystkie referowane wartości pochodzą z `dictionaries/pl/`,
    # paczki rdzennej projektu).
    placeholdery_globalne = _zbuduj_placeholdery_globalne()

    for jezyk in jezyki:
        # GUARD (poziom UI): niesfinalizowany `ui.yaml` ⇒ pomiń CAŁY język.
        # ui.yaml dostarcza wartości WSZYSTKim szablonom docs tego języka, więc
        # draftowy UI dyskwalifikuje całą paczkę językową (hierarchia: UI → doc).
        ui_path = DICT_DIR / jezyk / FOLDER_GUI / NAZWA_UI
        ok_ui, powod_ui = _status_naglowka(ui_path, jezyk)
        if not ok_ui:
            if not cicho:
                print(f"⚠️  {jezyk}: ui.yaml header is not finalized "
                      f"({powod_ui}) — skipping ALL docs for this language.")
            if zbieraj_drafty is not None:
                zbieraj_drafty[f"{jezyk}/{NAZWA_UI}"] = powod_ui
            continue

        ui = _wczytaj_ui(jezyk)
        szablony = _wczytaj_szablony(jezyk)
        if not szablony and not cicho:
            print(f"ℹ️  {jezyk}: brak szablonów w gui/dokumentacja/.")
            continue

        for id_szablonu, tresc_szablonu, sciezka_szablonu in szablony:
            # GUARD (poziom doc): niesfinalizowany szablon ⇒ nie zapisuj tego .txt
            # (UI tego języka jest już kanoniczny — odrzucamy tylko ten plik).
            ok_doc, powod_doc = _status_naglowka(sciezka_szablonu, jezyk)
            if not ok_doc:
                if not cicho:
                    print(f"⚠️  {jezyk}/{id_szablonu}: template header is not "
                          f"finalized ({powod_doc}) — not writing docs file.")
                if zbieraj_drafty is not None:
                    zbieraj_drafty[f"{jezyk}/{id_szablonu}"] = powod_doc
                continue

            wynik_tresc, brakujace = _rozwin_placeholdery(
                tresc_szablonu, ui, placeholdery_globalne)
            if brakujace and not cicho:
                unikalne = sorted(set(brakujace))
                print(f"⚠️  {jezyk}/{id_szablonu}: missing placeholders in ui.yaml: {unikalne}")
            if zbieraj_brakujace is not None and brakujace:
                zbieraj_brakujace[f"{jezyk}/{id_szablonu}"] = sorted(set(brakujace))

            # Od v18.8: default = render Markdown → pełny dokument HTML z
            # `lang="<iso>"`. README (render: 'surowy') zapisujemy 1:1 — jego
            # Markdown renderuje GitHub.
            tryb_renderu = KONFIG_SZABLONOW.get(id_szablonu, {}).get("render", "html")
            if tryb_renderu == "html":
                wynik_tresc = _renderuj_html(wynik_tresc, jezyk)

            sciezka_wyjscia = _sciezka_wyjscia(id_szablonu, jezyk, docelowy_katalog)
            # Piszemy z `newline="\n"` — celowo LF, nie platform-default.
            # Dzięki temu diff na Windowsie vs Linux zwraca ten sam wynik,
            # a `git` może sam zdecydować o konwersji przy checkoucie.
            with open(sciezka_wyjscia, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(wynik_tresc)
            wyniki.append(sciezka_wyjscia)
            if not cicho:
                print(f"✅  {sciezka_wyjscia.relative_to(ROOT)}")

    return wyniki


# ---------------------------------------------------------------------------
# Walidacja: czy wszystkie placeholdery rozwinięte przez ui.yaml?
# ---------------------------------------------------------------------------
def waliduj() -> int:
    """Twardy check spójności szablonów z ``ui.yaml``.

    Generuje pliki tak samo jak ``generuj()``, a następnie sprawdza,
    czy w którymkolwiek szablonie pozostał niesparowany placeholder
    ``{klucz.zagniezdzony}``, dla którego nie znaleziono wartości
    w ``dictionaries/<jezyk>/gui/ui.yaml``.

    To jest jedyny mechaniczny kontrakt między szablonami dokumentacji
    a warstwą i18n. Nie dba o stylistykę ani zawartość merytoryczną
    (tłumaczenia robi człowiek albo LLM), dba tylko o to, żeby żadna
    nazwa klucza nie zostawała w wynikowym .txt jako surowy `{coś}`.

    Od v18.6 sprawdza dodatkowo nagłówki finalizacji: plik z draftowym /
    niekanonicznym nagłówkiem nie został wygenerowany (guard) — tu raportujemy
    go głośno i również zwracamy exit 1.

    Od v18.25 dochodzi BRAMKA TAGÓW AKCENTU: każdy cytat z docsów wyglądający
    jak tag Księgi Świata przechodzi przez prawdziwy parser akcentów
    (`_bramka_tagow_akcentu`) — przykład, który użytkownik ma WPISAĆ, nie może
    być martwy. Ta klasa błędu jest niewidoczna dla bramki leaków, bo cytat
    jest poprawnym językiem docelowym.

    Od v18.5.3 dochodzi BRAMKA LEAKÓW (`audyt_leakow.bramka_docs`): skan szablonów
    docs pod kątem nieprzetłumaczonego polskiego tekstu względem zaakceptowanego
    baseline'u. Nowy/przesunięty leak (spoza baseline) → exit 1. Import jest LAZY
    z łagodną degradacją: gdy `audyt_leakow`/`lingua` są niedostępne (kontrybutor
    bez pełnego dev-env), bramka jest pomijana z notą, a nie blokuje walidacji.

    Returns:
        0 — wszystkie placeholdery rozwinięte, nagłówki kanoniczne i brak leaków
            ponad baseline; paczka gotowa do buildu.
        1 — znaleziono brakujące placeholdery, draftowe nagłówki LUB leaki ponad
            baseline; exit code dla CI / build_release.
    """
    brakujace_wedlug_pliku: dict[str, list[str]] = {}
    drafty_wedlug_pliku: dict[str, str] = {}
    wygenerowane = generuj(
        zbieraj_brakujace=brakujace_wedlug_pliku,
        zbieraj_drafty=drafty_wedlug_pliku,
    )

    print("\n========== FINALIZATION-HEADER GUARD ==========")
    if not drafty_wedlug_pliku:
        print("✅ Every generated file carries the canonical finalization header.")
    else:
        print(f"❌ Refused to generate {len(drafty_wedlug_pliku)} file(s) with a "
              f"draft / non-canonical header:")
        for nazwa, powod in sorted(drafty_wedlug_pliku.items()):
            print(f"  • {nazwa}: {powod}")
        print("Fix: review the machine translation, then run the matching builder "
              "with `--finalizuj` to swap the draft header for the canonical one "
              "(zero re-translation). A `<lang>/ui.yaml` entry skips the WHOLE "
              "language until its UI header is finalized.")
    print("===============================================")

    print("\n========== PLACEHOLDER VALIDATION ==========")
    if not brakujace_wedlug_pliku:
        print("✅ All {placeholdery} in the templates have values in ui.yaml.")
    else:
        print(f"❌ Found missing placeholders in {len(brakujace_wedlug_pliku)} "
              f"template(s):")
        for nazwa, brakujace in sorted(brakujace_wedlug_pliku.items()):
            print(f"  • {nazwa}")
            for klucz in brakujace:
                print(f"      - {{{klucz}}}")
        print(
            "Fix: add the missing keys to that language's ui.yaml OR remove the "
            "unused placeholders from the template. A raw `{coś}` in docs/*.html "
            "looks like a bug, so the build will not pass."
        )
    print("=============================================")

    # Bramka RAW-HTML (od v18.8): tag spoza whitelisty renderera w wynikowym
    # .html = surowy `<fragment>` z szablonu przepuszczony jako nieznany tag —
    # przeglądarka POŁKNĘŁABY go razem z treścią. Fix: otoczyć fragment
    # backtickami w szablonie (code span renderuje `<...>` literalnie).
    obce_tagi_wedlug_pliku: dict[str, list[str]] = {}
    for sciezka in wygenerowane:
        if sciezka.suffix != ".html":
            continue
        obce = _obce_tagi_w_html(sciezka.read_text(encoding="utf-8"))
        if obce:
            obce_tagi_wedlug_pliku[str(sciezka.relative_to(ROOT))] = obce
    print("\n========== RAW-HTML GATE (docs/*.html) ==========")
    if not obce_tagi_wedlug_pliku:
        print("✅ No raw HTML tags beyond the renderer's whitelist.")
    else:
        print(f"❌ Found unexpected tags in {len(obce_tagi_wedlug_pliku)} file(s) "
              f"(a raw `<fragment>` from the template would be EATEN by the browser):")
        for nazwa, tagi in sorted(obce_tagi_wedlug_pliku.items()):
            print(f"  • {nazwa}: {tagi}")
        print("Fix: wrap the `<fragment>` in backticks in the template "
              "(a code span renders it literally).")
    print("=================================================")

    # Bramka tagów akcentu (od v18.25) — przykład, który użytkownik ma WPISAĆ
    # do Księgi Świata, musi realnie działać w tej paczce.
    tagi_wedlug_pliku = _bramka_tagow_akcentu()
    print("\n========== ACCENT-TAG GATE (World Book examples) ==========")
    if not tagi_wedlug_pliku:
        print("✅ Every accent-tag example parses to a real accent id "
              "(or the engine is unavailable — see the leak gate note below).")
    else:
        print(f"❌ Found dead accent-tag example(s) in "
              f"{len(tagi_wedlug_pliku)} template(s):")
        for nazwa, powody in sorted(tagi_wedlug_pliku.items()):
            print(f"  • {nazwa}")
            for powod in powody:
                print(f"      - {powod}")
        print("Fix: put the accent's FILE NAME (an identifier, e.g. `francuski`) "
              "right next to a trigger word from that pack's "
              "`podstawy.yaml::slowo_akcent`. Add the missing inflected form of "
              "the trigger word to `slowo_akcent` if your language needs it.")
    print("==========================================================")

    # Bramka leaków (od v18.5.3) — lazy import + łagodna degradacja, jak guard
    # nagłówka. Skanuje szablony docs vs baseline; nowy/przesunięty PL-leak = exit 1.
    leaki_blokujace = False
    print("\n========== LEAK GATE (docs vs baseline) ==========")
    try:
        import audyt_leakow
    except ImportError:
        print("ℹ️  audyt_leakow/lingua not available — leak gate skipped "
              "(degraded context, e.g. a fresh clone without the dev toolchain).")
    else:
        wynik = audyt_leakow.bramka_docs()
        if wynik.pominieto:
            print(f"ℹ️  Leak gate skipped: {wynik.powod_pominiecia}. "
                  "Install `lingua` to run it (maintainer/CI).")
        elif wynik.czysto:
            print("✅ No Polish-text leaks beyond the accepted baseline "
                  f"({audyt_leakow.BASELINE_PATH.name}).")
        else:
            leaki_blokujace = True
            ile = sum(len(v) for v in wynik.nowe.values())
            print(f"❌ Found {ile} leak(s) ABOVE the baseline in "
                  f"{len(wynik.nowe)} section(s) (a new or shifted Polish fragment):")
            for klucz, powody in sorted(wynik.nowe.items()):
                print(f"  • {klucz}: {', '.join(powody)}")
            print("Fix: translate the leaked fragment in the template. If this is a "
                  "DELIBERATE, legitimate content change, regenerate the baseline "
                  "with `python audyt_leakow.py --zapisz-baseline` and commit the diff.")
    print("==================================================")

    return 1 if (brakujace_wedlug_pliku or drafty_wedlug_pliku
                 or leaki_blokujace or obce_tagi_wedlug_pliku
                 or tagi_wedlug_pliku) else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="User documentation generator (i18n).",
    )
    parser.add_argument(
        "-v", "--waliduj",
        action="store_true",
        help="After generating, check that all {placeholdery} were expanded "
             "via ui.yaml. Exit 1 if anything was left as a raw `{klucz}` in "
             "the resulting docs/*.txt.",
    )
    args = parser.parse_args()

    if args.waliduj:
        return waliduj()

    generuj()
    return 0


if __name__ == "__main__":
    sys.exit(main())
