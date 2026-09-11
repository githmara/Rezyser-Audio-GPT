"""
test_lang_wyniku.py — Regresja: język PLIKU WYNIKOWEGO pochodzi z danych,
nigdy z detekcji (v19.1).

Do v19.0 ścieżka zapisu Poligloty ustawiała atrybut ``lang`` dwoma sposobami
i oba były złe dla akcentu — wariantu, w którym język wyniku RÓŻNI SIĘ od
języka źródła:

  * side-channel ``_segmenty_wynikowe`` niósł język ŹRÓDŁA akapitu, więc
    akcent fiński zapisywał ``<html lang="fi">`` i 30 × ``<p lang="pl">``
    (zmierzone na `skrypty/audyt_starego_modelu.md`) — czytnik ekranu wracał
    na polski głos w każdym akapicie i kasował cały efekt;
  * ścieżka pełnego HTML zgadywała język każdego bloku z tekstu JUŻ
    przemielonego: akcent włoski (`iso: it`) dawał ``pl``×25, ``en``×3,
    ``es``×1, ``fi``×1 — cztery języki, żaden docelowy.

Pięć kontraktów, wszystkie mierzone WYKONANIEM prawdziwego silnika na
prawdziwych paczkach z `dictionaries/` (zero atrap — atrapa mierzyłaby nasze
wyobrażenie o polach YAML, nie paczki):

  A. Akcent daje w całym pliku JEDEN język, równy polu ``iso`` wariantu —
     dla wszystkich paczek i wszystkich wariantów, jakie w nich są.
  B. `zapisz_wynik` NIE WYKRYWA JĘZYKA: z podmienionym
     `_wykryj_jezyk_fragmentu`, który natychmiast rzuca, przechodzą wszystkie
     ścieżki zapisu (.md, .html, .htm, .txt, .docx, naprawiacz, szyfr,
     wywołanie bez side-channelu).
  C. Niezmiennik paczek: ``iso`` wariantu, który NIE zmienia języka
     (oczyszczenie, szyfry) = kod paczki; ``iso`` akcentu = kod języka głosu;
     naprawiacz ma ``iso`` puste (kod podaje użytkownik).
  D. Dokument mieszany językowo: oczyszczenie ZACHOWUJE język per akapit,
     akcent go spłaszcza do celu, a wymuszenie języka spłaszcza wszystko.
  E. Naprawiacz stempluje ręczny kod (także regionalny, `pt-BR`) w każdy
     akapit i w nagłówek — bez detekcji i bez wyjątków.

Test jest REGRESJĄ, nie tautologią: kontrakt A sprawdza JEDNOCZEŚNIE, że
zbiór języków w pliku jest jednoelementowy i że ten język to `iso` wariantu
(stary kod przechodził tylko drugi warunek — dla `<html>` — a pierwszy łamał
w 30 akapitach), kontrakt B pada na każdym powrocie detekcji do ścieżki
zapisu, a kontrakt D pilnuje, żeby lekarstwo („jeden język na dokument") nie
zjadło przypadku, w którym różne akapity naprawdę mają różne `iso`.

Uruchom:  .venv/Scripts/python test_lang_wyniku.py
"""

import collections
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import docx

import core_poliglota as cp

# Krótkie próbki: poniżej progu `_MIN_TEKST_DLA_DETEKCJI`, więc segmentacja
# oddaje fallback = język paczki BEZ pytania lingua. Kontrakt A ma mierzyć
# regułę zapisu, nie celność detektora na dziewięciu językach.
PROBKA_KROTKA = "Ala ma kota.\n\nKot ma Ale.\n\nOboje wychodza."

# Próbki długie (powyżej progu) — tu detekcja NAPRAWDĘ pracuje na wejściu.
PL = ("Ala ma kota, a kot ma Ale i oboje wychodza razem na dlugi spacer "
      "po lesie, gdzie nikt ich nie szuka.")
RU = ("Мелкий дождь стучал по жестяной крыше, и никто не поднимал головы "
      "от бумаг, разложенных по всему столу.")

KAT = Path(tempfile.mkdtemp())


def _langi(sciezka: Path) -> dict[str, int]:
    """Licznik wartości atrybutu ``lang`` w zapisanym HTML-u."""
    return dict(collections.Counter(
        re.findall(r'lang="([^"]+)"', sciezka.read_text(encoding="utf-8"))))


def _langi_docx(sciezka: Path) -> dict[str, int]:
    """Licznik wartości ``w:lang`` w biegach zapisanego .docx."""
    from docx.oxml.ns import qn
    licznik: collections.Counter = collections.Counter()
    for para in docx.Document(str(sciezka)).paragraphs:
        for run in para.runs:
            el = run._r.get_or_add_rPr().find(qn("w:lang"))
            if el is not None:
                licznik[el.get(qn("w:val"))] += 1
    return dict(licznik)


def _zapisz(tryb: str, kod: str, wariant: str, ext: str, tresc: str,
            opcje: dict | None = None, iso_nadpis: str | None = None,
            blokuj_detekcje: bool = True) -> Path:
    """Pełny przebieg: `przetworz` → `zapisz_wynik` → ścieżka pliku.

    ``blokuj_detekcje`` podmienia `_wykryj_jezyk_fragmentu` na wersję
    rzucającą — ale WYŁĄCZNIE na czas `zapisz_wynik`, bo na wejściu detekcja
    per akapit jest funkcją (wybiera alfabet Cezara i plik akcentu), nie
    usterką. To jest kontrakt B, wpleciony we wszystkie pozostałe.
    """
    o = dict(opcje or {})
    wynik = cp.przetworz(tresc, tryb, kod, wariant, o)
    cfg = cp.wariant_po_id(tryb, kod, wariant)
    iso = iso_nadpis or cp.kod_iso(tryb, kod, wariant, o)
    nazwa = f"{kod}_{tryb}_{wariant}_{ext.lstrip('.')}"

    oryginal = cp._wykryj_jezyk_fragmentu

    def _zakaz(tekst: str, fallback: str) -> str:
        raise AssertionError(
            "`zapisz_wynik` called language DETECTION on the RESULT text "
            f"(fragment: {tekst[:40]!r}). Contract B (v19.1) forbids it: the "
            "output of an accent or a cipher is not text in any language, so "
            "the answer must come from data (the variant's `iso`), not a guess")

    if blokuj_detekcje:
        cp._wykryj_jezyk_fragmentu = _zakaz
    try:
        return Path(cp.zapisz_wynik(
            wynik, str(KAT), nazwa, ext, iso, tryb, cfg, tresc, None,
            segmenty_wynikowe=o.get("_segmenty_wynikowe")))
    finally:
        cp._wykryj_jezyk_fragmentu = oryginal


def test_a_akcent_daje_jeden_jezyk_rowny_iso() -> None:
    """A: każdy akcent w każdej paczce → jeden język w pliku, równy `iso`."""
    kody = cp.dostepne_jezyki_bazowe()
    assert len(kody) >= 2, f"oczekiwano kompletu paczek, jest {kody}"
    sprawdzonych = 0
    for kod in kody:
        for cfg in cp.lista_wariantow(cp.TRYB_REZYSER, kod):
            if cfg.get("kategoria") != "akcent":
                continue
            iso = str(cfg.get("iso") or "").strip()
            assert iso, f"{kod}/akcenty/{cfg['id']}.yaml nie ma pola `iso`"
            for ext in (".md", ".txt"):
                plik = _zapisz(cp.TRYB_REZYSER, kod, cfg["id"], ext,
                               PROBKA_KROTKA)
                langi = _langi(plik)
                assert set(langi) == {iso}, (
                    f"{kod}/{cfg['id']} ({ext}): w pliku sa jezyki {langi}, "
                    f"a akcent deklaruje `iso: {iso}` — dokument ma byc "
                    f"czytany JEDNYM glosem docelowym")
                sprawdzonych += 1
    assert sprawdzonych >= 2 * 8, (
        f"bramka objela tylko {sprawdzonych} przebiegow — za malo, zeby "
        f"mowic o wszystkich paczkach")


def test_a2_pelny_html_tez_dostaje_jezyk_celu() -> None:
    """A2: ścieżka pełnego HTML (bs4) — ta, która dawała cztery języki."""
    html = (f'<!DOCTYPE html><html lang="pl"><body>'
            f'<h2>Ocena redaktorska</h2><p>{PL}</p>'
            f'<ul><li>{PL}</li></ul><blockquote>{PL}</blockquote>'
            f'</body></html>')
    for wariant, iso in (("wloski", "it"), ("finski", "fi"),
                         ("rosyjski", "ru"), ("islandzki", "is")):
        plik = _zapisz(cp.TRYB_REZYSER, "pl", wariant, ".html", html)
        langi = _langi(plik)
        assert set(langi) == {iso}, (
            f"pl/{wariant} (pelny HTML): {langi} zamiast wylacznie {iso}")
        assert langi[iso] >= 5, (
            f"pl/{wariant}: tag trafil tylko w {langi[iso]} elementow — "
            f"blokowe elementy (h2/p/li/blockquote) maja dostac swoj `lang`")


def test_b_docx_i_wywolanie_bez_side_channelu() -> None:
    """B: .docx oraz wywołanie bez side-channelu — również bez detekcji."""
    plik = _zapisz(cp.TRYB_REZYSER, "pl", "finski", ".docx", PROBKA_KROTKA)
    assert set(_langi_docx(plik)) == {"fi"}, (
        f".docx + akcent finski: {_langi_docx(plik)} zamiast {{'fi'}}")

    # Wywołanie w stylu Tłumacza AI: brak side-channelu, jeden zadeklarowany
    # kod docelowy. Detekcja jest zablokowana, więc jedyne poprawne źródło
    # języka to `iso_code` od wywołującego.
    oryginal = cp._wykryj_jezyk_fragmentu

    def _zakaz(tekst: str, fallback: str) -> str:
        raise AssertionError(
            "`zapisz_wynik` called language detection on a call with NO "
            "side channel — there `iso_code` from the caller is the only "
            "declared truth (AI translator, tag fixer)")

    cp._wykryj_jezyk_fragmentu = _zakaz
    try:
        sciezka = Path(cp.zapisz_wynik(
            f"{PL}\n\n{PL}", str(KAT), "tlumacz_bez_kanalu", ".md",
            "fi", "Tlumacz", None, PL, None, segmenty_wynikowe=None))
    finally:
        cp._wykryj_jezyk_fragmentu = oryginal
    assert set(_langi(sciezka)) == {"fi"}, (
        f"zapis bez side-channelu: {_langi(sciezka)} zamiast {{'fi'}}")


def test_c_niezmiennik_iso_w_paczkach() -> None:
    """C: `iso` = język GŁOSU — akcent deklaruje cel, reszta własną paczkę."""
    znane = set(cp.dostepne_jezyki_bazowe())
    for kod in cp.dostepne_jezyki_bazowe():
        warianty = (cp.lista_wariantow(cp.TRYB_REZYSER, kod)
                    + cp.lista_wariantow(cp.TRYB_SZYFRANT, kod))
        for cfg in warianty:
            iso = str(cfg.get("iso") or "").strip()
            kategoria = cfg.get("kategoria", "")
            gdzie = f"{kod}/{cfg.get('id')} (kategoria: {kategoria or '—'})"
            if kategoria == "naprawiacz":
                assert iso == "", (
                    f"{gdzie}: `iso` ma byc PUSTE — kod podaje uzytkownik")
            elif kategoria == "akcent":
                assert iso in znane, (
                    f"{gdzie}: `iso: {iso}` nie jest kodem zadnej paczki, "
                    f"wiec nie ma glosu, ktory przeczyta wynik")
            else:
                assert iso == kod, (
                    f"{gdzie}: wariant nie zmienia jezyka tekstu, wiec "
                    f"`iso` musi rownac sie kodowi paczki, a jest `{iso}`")


def test_d_dokument_mieszany() -> None:
    """D: oczyszczenie zachowuje języki, akcent spłaszcza, wymuszenie ucina."""
    frag = f"{PL}\n\n{RU}\n\n{PL}"
    html = f'<html lang="pl"><body><p>{PL}</p><p>{RU}</p><p>{PL}</p></body></html>'

    for ext, tresc in ((".md", frag), (".html", html)):
        langi = _langi(_zapisz(cp.TRYB_REZYSER, "pl", "oczyszczenie", ext, tresc))
        assert set(langi) == {"pl", "ru"}, (
            f"oczyszczenie ({ext}) ma ZACHOWAC jezyk akapitow, a dalo {langi}")
        assert langi["ru"] == 1, (
            f"oczyszczenie ({ext}): rosyjski akapit jest jeden, a otagowano "
            f"{langi['ru']}")

    langi = _langi(_zapisz(cp.TRYB_REZYSER, "pl", "finski", ".html", html))
    assert set(langi) == {"fi"}, (
        f"akcent ma spłaszczyc dokument do jezyka celu, a dal {langi}")

    langi = _langi(_zapisz(cp.TRYB_SZYFRANT, "pl", "cezar", ".html", html,
                           {"przesuniecie": 5, "wymus_jezyk": "pl"}))
    assert set(langi) == {"pl"}, (
        f"wymuszenie jezyka ma wylaczyc detekcje na WEJSCIU, a dalo {langi}")

    langi = _langi(_zapisz(cp.TRYB_SZYFRANT, "pl", "cezar", ".html", html,
                           {"przesuniecie": 5}))
    assert set(langi) == {"pl", "ru"}, (
        f"szyfr bez wymuszenia szyfruje kazdy akapit alfabetem JEGO jezyka, "
        f"wiec tagi maja to odbic, a sa {langi}")


def test_e_naprawiacz_stempluje_reczny_kod() -> None:
    """E: naprawiacz — ręczny kod wszędzie, w tym regionalny `pt-BR`."""
    frag = f"{PL}\n\n{RU}"
    html = f'<html lang="pl"><body><p>{PL}</p><p>{RU}</p></body></html>'
    opcje = {"iso_reczne": "pt-BR"}
    for ext, tresc in ((".md", frag), (".html", html), (".txt", frag)):
        langi = _langi(_zapisz(cp.TRYB_REZYSER, "pl", "naprawiacz_tagow", ext,
                               tresc, opcje, iso_nadpis="pt-BR"))
        assert set(langi) == {"pt-BR"}, (
            f"naprawiacz ({ext}): {langi} zamiast wylacznie {{'pt-BR'}} — "
            f"kod z pola ISO obowiazuje caly dokument")

    plik = _zapisz(cp.TRYB_REZYSER, "pl", "naprawiacz_tagow", ".docx", frag,
                   opcje, iso_nadpis="pt-BR")
    assert set(_langi_docx(plik)) == {"pt-BR"}, (
        f"naprawiacz (.docx): {_langi_docx(plik)} zamiast {{'pt-BR'}}")


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
