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
                 `<ol>` z liczb w naturalnym tekście).
"""

from __future__ import annotations

import re

#: Rozszerzenia renderu — jedno źródło prawdy dla obu konsumentów.
ROZSZERZENIA = ["nl2br", "sane_lists"]

_RE_TYTUL = re.compile(r"^#{1,2} +(.+)$", re.MULTILINE)


def tytul_dokumentu(tresc_md: str) -> str:
    """Wyciąga tytuł do ``<title>``: pierwszy nagłówek `# ` albo pierwsza linia."""
    m = _RE_TYTUL.search(tresc_md)
    tytul = m.group(1) if m else (tresc_md.strip().splitlines() or ["Dokument"])[0]
    return tytul.strip().lstrip("#").strip()


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
        RuntimeError: gdy biblioteki `markdown` nie ma w środowisku —
            celowo GŁOŚNO. W buildzie/`--waliduj` cicha degradacja
            zostawiłaby paczkę bez plików, na które wskazuje menu Pomoc;
            w runtime — wczytany plik bez treści.
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

    body = markdown.markdown(
        tresc_md, extensions=ROZSZERZENIA, output_format="html5",
    )
    tytul = tytul_dokumentu(tresc_md)
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
