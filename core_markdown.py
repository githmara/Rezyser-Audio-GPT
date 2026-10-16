"""
core_markdown.py – render Markdown → samodzielny dokument HTML5.

JEDNO źródło dla dwóch konsumentów o różnych potrzebach:

  * `generuj_dokumentacje.py` (dev/build-time) – szablony podręczników pisane
    w Markdownie od v18.8, wynik z arkuszem stylów do `docs/<id>.<iso>.html`;
  * `gui_poliglota.py` (RUNTIME, od v19.1) – plik `.md` wczytany przez
    użytkownika, renderowany PRZED wejściem w pipeline akcentów/szyfrów.
    Bez tego kroku surowa składnia (`---`, `- `, `> `, backticki, linki)
    jechała do wyniku jako treść i syntezator ją CZYTAŁ, a struktura ginęła:
    `## Nagłówek` stawał się zwykłym akapitem, więc dokument nie miał ani
    jednego `<h2>` — czytnik ekranu tracił nawigację 1–6/H, dokładnie tę,
    dla której v18.8 przeniosło podręczniki z `.txt` na HTML.

Dlaczego moduł `core_*`, a nie funkcja w generatorze: dev-tool NIE wchodzi do
paczki PyInstallera (patrz CLAUDE.md `# DEPLOYMENT`), więc runtime nie może go
importować. Kierunek odwrotny jest legalny i tak to jest spięte — generator
woła ten moduł, a jego wyjście musi zostać BAJT W BAJT takie, jak przed
wydzieleniem (warunek akceptacji: pusty `git diff docs/` po regeneracji).

Rozszerzenia python-markdown (wspólne dla obu konsumentów):
  * nl2br      – pojedynczy `\\n` = `<br>`; treść podręczników używa
                 „linia = krok/wiersz" bez pustych linii między nimi, a
                 odpowiedzi modeli (typowe wejście Poligloty) tak samo;
  * sane_lists – listy tylko z konsekwentnych markerów (mniej fałszywych
                 `<ol>` z liczb w naturalnym tekście);
  * tables, fenced_code, footnotes, def_list, abbr (od 19.13) – bez nich
                 syntezator czytał składnię jako treść: wiersze tabeli
                 „| kolumna | kolumna |", płoty ``` / ~~~ (a blok kodu lądował
                 w zwykłym akapicie), znaczniki przypisów `[^1]`, `: definicja`
                 i `*[SKRÓT]: …` (zmierzone na korpusie testowym ze wszystkimi
                 konstrukcjami). Podręczniki tych konstrukcji nie używają —
                 `docs/` po zmianie wyszły bajt w bajt identyczne.

Front matter YAML (`---` … `---` na samym początku pliku, Jekyll/Hugo/
Obsidian) jest zdejmowany przed renderem: bez tego zamykające `---` działało
jak podkreślenie nagłówka setext i metadane stawały się `<h2>`.
Nadal NIE są obsługiwane (brak rozszerzeń w python-markdown): listy zadań
`- [ ]` i przekreślenie `~~tekst~~` — zostają w tekście dosłownie.
"""

from __future__ import annotations

import re

#: Rozszerzenia renderu — jedno źródło prawdy dla obu konsumentów.
ROZSZERZENIA = ["nl2br", "sane_lists", "tables", "fenced_code", "footnotes",
                "def_list", "abbr"]

_RE_TYTUL = re.compile(r"^#{1,2} +(.+)$", re.MULTILINE)
# Reguła pandoca: `---` w PIERWSZEJ linii, bez pustej linii zaraz po nim,
# zamknięcie `---` albo `...`. Pusta linia po otwarciu to linia pozioma
# w treści, nie metadane.
_RE_FRONT_MATTER = re.compile(
    r"\A---[ \t]*\r?\n(?![ \t]*\r?\n)(.*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.S)
_BOM = chr(0xFEFF)
# Linia mapy YAML: `klucz:` (z wartością albo bez) albo element listy `- …`.
_RE_KLUCZ_YAML = re.compile(r"^(?:[A-Za-z_][\w.-]*[ \t]*:(?:[ \t]|$)|-[ \t])")


def zdejmij_front_matter(tresc_md: str) -> str:
    """Usuwa blok metadanych YAML z samego początku pliku.

    Blok znika wyłącznie wtedy, gdy ma kształt MAPY YAML
    (`title: …`, `tags: […]`). Audyt 19.13: sam regex zjadał treść — plik
    zaczynający się linią poziomą `---`, akapitami i drugim `---` zostawał
    z samym „Koniec.”. BOM na początku (Notatnik) jest zdejmowany, bo inaczej
    `---` nie stało w pierwszej kolumnie i metadane wracały jako `<h2>`.
    """
    tresc_md = tresc_md.lstrip(_BOM)
    m = _RE_FRONT_MATTER.match(tresc_md)
    if not m:
        return tresc_md
    # Kształt mapy YAML sprawdzany wzorcem, nie parserem: to fragment
    # dokumentu użytkownika, nie plik konfiguracji, więc „nie wygląda na
    # klucz: wartość” znaczy po prostu „to treść” (bramka `audyt_ciszy`
    # słusznie nie przepuściłaby cichego `except` wokół `yaml.safe_load`).
    linie = [l for l in m.group(1).splitlines() if l.strip()]
    if linie and all(_RE_KLUCZ_YAML.match(l) or l[:1] in " \t" for l in linie) \
            and _RE_KLUCZ_YAML.match(linie[0]):
        return tresc_md[m.end():]
    return tresc_md


def tytul_dokumentu(tresc_md: str) -> str:
    """Wyciąga tytuł do ``<title>``: pierwszy nagłówek `# ` albo pierwsza linia."""
    m = _RE_TYTUL.search(tresc_md)
    tytul = m.group(1) if m else (tresc_md.strip().splitlines() or ["Dokument"])[0]
    return tytul.strip().lstrip("#").strip()


def _modul_markdown():
    """Import `markdown` — celowo GŁOŚNO, gdy go brak.

    W buildzie/`--waliduj` cicha degradacja zostawiłaby paczkę bez plików, na
    które wskazuje menu Pomoc; w runtime — wczytany plik bez treści.
    """
    try:
        import markdown
    except ImportError as exc:                              # pragma: no cover
        raise RuntimeError(
            "Missing the `markdown` package (Markdown → HTML render: docs "
            "since v18.8, Polyglot `.md` input since v19.1). Fix: "
            ".venv/Scripts/pip install markdown (it is listed in "
            "requirements.txt)."
        ) from exc
    return markdown


def renderuj_fragment(tresc_md: str) -> str:
    """Markdown → sam fragment HTML (zawartość `<body>`), tymi samymi `ROZSZERZENIA`.

    Bez zdejmowania front matter: fragment to kawałek dokumentu (od 19.14
    odczytana strona-skan PDF-a, `core_skany`), nie plik z metadanymi.

    Raises:
        RuntimeError: brak biblioteki `markdown` (patrz `_modul_markdown`).
    """
    return _modul_markdown().markdown(
        tresc_md, extensions=ROZSZERZENIA, output_format="html5",
    )


def zloz_dokument(body: str, jezyk: str, tytul: str, *, styl: str | None = None,
                  viewport: bool = False) -> str:
    """Szkielet samodzielnego dokumentu HTML5 wokół gotowego `body`.

    Args:
        body:     Fragment HTML (już bezpieczny — nie escapujemy go tu).
        jezyk:    Kod do atrybutu ``<html lang>`` (patrz `renderuj`).
        tytul:    Zwykły tekst do ``<title>`` — escapowany tutaj.
        styl:     Treść arkusza do ``<style>`` albo ``None``.
        viewport: Czy dodać ``<meta name="viewport">``.
    """
    tytul_safe = (tytul.replace("&", "&amp;").replace("<", "&lt;")
                       .replace(">", "&gt;"))
    czesci = [
        "<!DOCTYPE html>\n",
        f'<html lang="{jezyk}">\n',
        "<head>\n",
        '<meta charset="utf-8">\n',
    ]
    if viewport:
        czesci.append(
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n')
    czesci.append(f"<title>{tytul_safe}</title>\n")
    if styl:
        czesci.append(f"<style>\n{styl}\n</style>\n")
    czesci += [
        "</head>\n",
        "<body>\n",
        f"{body}\n",
        "</body>\n",
        "</html>\n",
    ]
    return "".join(czesci)


def renderuj(tresc_md: str, jezyk: str, *, styl: str | None = None,
             viewport: bool = False) -> str:
    """Renderuje Markdown do pełnego, samodzielnego dokumentu HTML5.

    Args:
        tresc_md: Treść w Markdownie.
        jezyk:    Kod do atrybutu ``<html lang>``. Dla Poligloty to wartość
                  TYMCZASOWA — `core_poliglota.zapisz_wynik` nadpisze ją
                  językiem głosu (`iso` wariantu) przy zapisie wyniku.
        styl:     Treść arkusza do wstawienia w ``<style>``. ``None`` →
                  bez sekcji ``<style>``. Poliglota NIE podaje stylu celowo:
                  segmentacja chroni TAGI, ale nie tekst w ich środku, więc
                  CSS przeszedłby przez reguły fonetyczne akcentu i wyszedłby
                  z dokumentu połamany.
        viewport: Czy dodać ``<meta name="viewport">`` (podręczniki: tak).

    Raises:
        RuntimeError: gdy biblioteki `markdown` nie ma w środowisku
            (patrz `_modul_markdown`).
    """
    tresc_md = zdejmij_front_matter(tresc_md)
    return zloz_dokument(renderuj_fragment(tresc_md), jezyk,
                         tytul_dokumentu(tresc_md), styl=styl, viewport=viewport)
