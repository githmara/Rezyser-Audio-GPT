"""
test_markdown_poliglota.py — Regresja: Markdown wchodzi do Poligloty jako
DOKUMENT, nie jako tekst ze znaczkami (v19.1).

Do v19.0 `.md` wchodziło do Poligloty przez wildcard „Wszystkie pliki (*.*)"
bez żadnej kontroli, a ścieżka zapisu miała dla niego gałąź traktującą go jak
`.txt`. Skutek zmierzony na `skrypty/audyt_starego_modelu.md` (4 kB):

  * 18 linii z surową składnią (`---`, `- `, `> `) w treści wynikowego HTML-a —
    syntezator mowy czyta je na głos;
  * zero nagłówków w wyniku (`## Ocena` zostawało akapitem), więc czytnik
    ekranu tracił nawigację 1–6/H — tę samą, dla której v18.8 przeniosło
    podręczniki z `.txt` na HTML;
  * `oczysc_tekst_tts` kasował DWA znaczniki (`*`, `#`), co maskowało problem
    w akapitach i pogłębiało go w listach.

Cztery kontrakty, mierzone WYKONANIEM pełnej ścieżki (render → `przetworz` →
`zapisz_wynik`) na prawdziwych paczkach:

  A. Render daje elementy blokowe, a pipeline akcentu ich NIE rusza: tagi
     przechodzą 1:1, mieli się tylko tekst między nimi.
  B. Po pełnej ścieżce w widocznym tekście nie ma ANI JEDNEJ linii z surową
     składnią Markdowna, a każdy element blokowy ma `lang` = `iso` wariantu.
  C. Wildcard okna wyboru pliku w KAŻDEJ paczce wymienia każde rozszerzenie
     z `core_poliglota.EXT_OBSLUGIWANE` — kod i dane nie mogą się rozjechać
     (rozszerzenie obsługiwane, ale niewidoczne w oknie, to defekt UI;
     wzorzec `*.md` w przetłumaczonym pliku to literał, nie tekst).
  D. Renderer jest WSPÓLNY z generatorem docs, ale konfiguracja różna:
     podręczniki dostają arkusz stylów i `viewport`, Poliglota nie —
     segmentacja chroni TAGI, a nie tekst w ich środku, więc CSS przeszedłby
     przez reguły fonetyczne akcentu i wyszedłby połamany.

Bajtowej zgodności `docs/` po wydzieleniu renderera pilnuje osobno procedura
wydawnicza (regeneracja + pusty `git diff docs/` przed commitem docs).

Uruchom:  .venv/Scripts/python test_markdown_poliglota.py
"""

import collections
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import yaml

import core_markdown
import core_poliglota as cp
import generuj_dokumentacje as gd

KATALOG = Path(__file__).parent
KAT_WY = Path(tempfile.mkdtemp())

PROBKA_MD = """# Tytuł dokumentu

Akapit pierwszy, dostatecznie długi, żeby detektor języka miał na czym pracować.

---

## Sekcja druga

- punkt pierwszy z treścią
- punkt drugi z treścią

> cytat blokowy o wyraźnej treści

### Sekcja trzecia

Akapit z **pogrubieniem**, `literałem` i [linkiem](https://example.org).
"""

#: Linia, która w widocznym tekście znaczy „składnia Markdowna wyciekła".
_RE_SKLADNIA = re.compile(r"^\s*(---|===|-\s+\S|\*\s+\S|>\s+\S|#{1,6}\s+\S|\|)")

TAGI_BLOKOWE = ("h1", "h2", "h3", "ul", "li", "blockquote", "hr", "p")


def _pelna_sciezka(wariant: str, tresc_md: str) -> str:
    """Render → `przetworz` → `zapisz_wynik`; zwraca zawartość pliku wyniku."""
    html = core_markdown.renderuj(tresc_md, "pl")
    opcje: dict = {}
    wynik = cp.przetworz(html, cp.TRYB_REZYSER, "pl", wariant, opcje)
    cfg = cp.wariant_po_id(cp.TRYB_REZYSER, "pl", wariant)
    sciezka = cp.zapisz_wynik(
        wynik, str(KAT_WY), f"md_{wariant}", ".html",
        cp.kod_iso(cp.TRYB_REZYSER, "pl", wariant, opcje),
        cp.TRYB_REZYSER, cfg, html, None,
        segmenty_wynikowe=opcje.get("_segmenty_wynikowe"))
    assert sciezka.endswith(".html"), (
        f"wynik dla .md ma byc dokumentem HTML, a jest {sciezka}")
    return Path(sciezka).read_text(encoding="utf-8")


def test_a_render_daje_elementy_blokowe() -> None:
    """A: render tworzy strukturę, a akcent przepisuje tagi 1:1."""
    html = core_markdown.renderuj(PROBKA_MD, "pl")
    braki = [tag for tag in TAGI_BLOKOWE if f"<{tag}" not in html]
    assert not braki, f"render nie wyprodukowal elementow: {braki}"

    tagi_przed = collections.Counter(re.findall(r"<(/?\w+)", html))
    out = _pelna_sciezka("finski", PROBKA_MD)
    tagi_po = collections.Counter(re.findall(r"<(/?\w+)", out))
    for tag, ile in tagi_przed.items():
        assert tagi_po.get(tag, 0) == ile, (
            f"akcent zmienil liczbe tagow <{tag}>: {ile} → "
            f"{tagi_po.get(tag, 0)} — pipeline ma mielic TEKST, nie znaczniki")


def test_b_zero_skladni_i_lang_z_wariantu() -> None:
    """B: brak surowej składni w treści + `lang` z `iso` w każdym bloku."""
    for wariant, iso in (("finski", "fi"), ("wloski", "it"),
                         ("oczyszczenie", "pl")):
        out = _pelna_sciezka(wariant, PROBKA_MD)
        widoczny = re.sub(r"<[^>]+>", "\n", out)
        wycieki = [l.strip() for l in widoczny.split("\n")
                   if _RE_SKLADNIA.match(l)]
        assert not wycieki, (
            f"{wariant}: skladnia Markdowna wyciekla do TRESCI (syntezator to "
            f"przeczyta): {wycieki[:3]}")
        langi = dict(collections.Counter(re.findall(r'lang="([^"]+)"', out)))
        assert set(langi) == {iso}, (
            f"{wariant}: jezyki w pliku {langi} zamiast wylacznie {iso}")
        assert langi[iso] >= 10, (
            f"{wariant}: tylko {langi[iso]} elementow z `lang` — kazdy blok "
            f"(naglowek, akapit, punkt listy, cytat) ma dostac swoj tag")


def test_c_wildcard_wymienia_kazde_obslugiwane_rozszerzenie() -> None:
    """C: okno wyboru pliku w każdej paczce zna każde rozszerzenie z kodu."""
    kody = cp.dostepne_jezyki_bazowe()
    assert kody, "brak kompletnych paczek w dictionaries/"
    for kod in kody:
        plik = KATALOG / "dictionaries" / kod / "gui" / "ui.yaml"
        dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
        # Bez `or {}` — puste albo skalarne korzenie mają się ODEZWAĆ własnym
        # zdaniem, a nie zamienić w „brak klucza" (bramka `audyt_ciszy`).
        assert isinstance(dane, dict), (
            f"{kod}/gui/ui.yaml wczytal sie jako {type(dane).__name__}, nie mapa")
        sekcja = dane.get("poliglota")
        assert isinstance(sekcja, dict), (
            f"{kod}/gui/ui.yaml: sekcja `poliglota` to "
            f"{type(sekcja).__name__}, nie mapa")
        wildcard = sekcja.get("file_dlg_wildcard")
        assert isinstance(wildcard, str) and wildcard.strip(), (
            f"{kod}/gui/ui.yaml: brak `poliglota.file_dlg_wildcard`")
        braki = [ext for ext in cp.EXT_OBSLUGIWANE if f"*{ext}" not in wildcard]
        assert not braki, (
            f"{kod}/gui/ui.yaml: wildcard nie wymienia {braki} — silnik te "
            f"pliki obsluguje, wiec okno wyboru ma je pokazywac "
            f"(wzorce `*{braki[0]}` to LITERAL, nie tekst do tlumaczenia)")


def test_d_wspolny_renderer_dwie_konfiguracje() -> None:
    """D: jeden renderer, dwie konfiguracje — docs ze stylem, Poliglota bez."""
    docsowy = gd._renderuj_html(PROBKA_MD, "pl")
    poliglotowy = core_markdown.renderuj(PROBKA_MD, "pl")

    assert "<style>" in docsowy and "viewport" in docsowy, (
        "podrecznik stracil arkusz stylow albo `viewport` — to regresja v18.8")
    assert "<style>" not in poliglotowy, (
        "render Poligloty NIE MOZE nosic CSS: segmentacja chroni tagi, ale nie "
        "tekst w ich srodku, wiec reguły akcentu przemielilyby arkusz stylow")
    assert "viewport" not in poliglotowy, (
        "render Poligloty nie potrzebuje `viewport` — to dokument do czytania "
        "przez syntezator, nie strona mobilna")

    # Serce renderu jest WSPÓLNE: ta sama treść `<body>` w obu wyjściach.
    cialo = re.search(r"<body>\n(.*)\n</body>", docsowy, re.S)
    assert cialo and cialo.group(1) in poliglotowy, (
        "docs i Poliglota rozjechaly sie na SAMYM renderze Markdowna — "
        "`core_markdown.ROZSZERZENIA` ma byc jednym zrodlem prawdy")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                       # pragma: no cover
        pass
    testy = [(nazwa, obiekt) for nazwa, obiekt in sorted(globals().items())
             if nazwa.startswith("test_") and callable(obiekt)]
    bledy = []
    for nazwa, funkcja in testy:
        try:
            funkcja()
            print(f"  OK   {nazwa}")
        except AssertionError as exc:
            bledy.append(nazwa)
            print(f"  FAIL {nazwa}: {exc}")
    print(f"\n{len(testy) - len(bledy)}/{len(testy)} zaliczonych.")
    sys.exit(1 if bledy else 0)
