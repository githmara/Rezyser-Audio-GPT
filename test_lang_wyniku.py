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

Dziewięć kontraktów (A–I; F–I dopisane w v19.2 razem z kodami ISO per
akapit), wszystkie mierzone WYKONANIEM prawdziwego silnika na prawdziwych
paczkach z `dictionaries/` (zero atrap — atrapa mierzyłaby nasze wyobrażenie
o polach YAML, nie paczki):

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
  F. Kod per akapit (v19.2) ląduje na WŁASNEJ jednostce, w kolejności
     dokumentu — na czterech ścieżkach zapisu, wliczając komórki tabel
     w `.docx` i bloki zagnieżdżone w HTML-u.
  G. Rozjazd liczby kodów i jednostek podnosi `ValueError` w OBU kierunkach
     (za mało, za dużo, kody na ścieżce zapisu surowego).
  H. `jednostki_jezykowe` liczy dokładnie tyle, ile zapis stempluje — spoiwo
     obu stron umowy, sprawdzane wykonaniem na każdym rozszerzeniu.
  I. Opinia detektora obejmuje PEŁNY kanon Lingui (czeski, portugalski — bez
     paczek), a przy fragmencie za krótkim milczy, zamiast zgadywać.

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


def _langi_kolejnosc(sciezka: Path) -> list[str]:
    """Wartości ``lang`` bloków HTML w KOLEJNOŚCI WYSTĄPIENIA w pliku.

    Czyta plik REGEXEM po pozycji w tekście, a nie przez bs4 — celowo: bramka
    ma mierzyć kolejność zapisaną na dysku, niezależnie od tego, jak silnik
    chodzi po DOM-ie. Gdyby test iterował tym samym drzewem co kod, sprawdzałby
    sam siebie.
    """
    tresc = sciezka.read_text(encoding="utf-8")
    return re.findall(
        r'<(?:p|h1|h2|h3|h4|h5|h6|li|blockquote|dt|dd|td|th|caption'
        r'|figcaption|summary)[^>]*lang="([^"]+)"', tresc)


def _langi_docx_kolejnosc(sciezka: Path) -> list[str]:
    """Pierwszy ``w:lang`` każdego NIEPUSTEGO akapitu Worda, w kolejności dokumentu.

    Enumeracja jest NIEZALEŻNA od `core_poliglota._iteruj_akapity_docx`:
    surowe ``element.iter(w:p)`` z lxml przechodzi całe drzewo w kolejności
    dokumentu, więc widzi też akapity w komórkach tabel — i widzi je „swoją"
    drogą. Dzięki temu kontrakt F mierzy JEDNOCZEŚNIE kompletność iteratora
    silnika i poprawność kolejności stempli.
    """
    from docx.oxml.ns import qn
    wynik: list[str] = []
    doc = docx.Document(str(sciezka))
    for p_el in doc.element.body.iter(qn("w:p")):
        tekst = "".join(t_el.text or "" for t_el in p_el.iter(qn("w:t")))
        if not tekst.strip():
            continue
        lang = None
        for lang_el in p_el.iter(qn("w:lang")):
            lang = lang_el.get(qn("w:val"))
            break
        wynik.append(lang)
    return wynik


def _docx_z_tabela(sciezka: Path) -> None:
    """Dokument ze WSZYSTKIMI pojemnikami tekstu, które silnik ma widzieć.

    Kolejność czytania: akapit ciała, pusty akapit (pomijany), dwie komórki
    tabeli, akapit będący samym HIPERLINKIEM, akapit w KONTROLCE ZAWARTOŚCI
    (``w:sdt``), akapit po wszystkim. Trzy ostatnie pojemniki dorzucone po
    audycie v19.2: `doc.paragraphs` nie widzi komórek tabel, `Paragraph.runs`
    nie widzi biegów w ``w:hyperlink`` (a `Paragraph.text` je liczy, więc
    akapit-link zużywał kod i nie dostawał ŻADNEGO tagu), a `w:sdt` nie jest
    kontenerem python-docx i wypadał z obu stron naraz.
    """
    from docx.oxml.shared import OxmlElement

    d = docx.Document()
    d.add_paragraph(PL)
    d.add_paragraph("")
    tab = d.add_table(rows=1, cols=2)
    tab.cell(0, 0).text = "Komorka lewa z trescia."
    tab.cell(0, 1).text = "Komorka prawa z trescia."

    # Akapit, którego CAŁY tekst siedzi w hiperlinku (zero `runs`).
    p_link = d.add_paragraph()
    hl = OxmlElement("w:hyperlink")
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "Klikalny tekst linku w akapicie."
    r.append(t)
    hl.append(r)
    p_link._p.append(hl)

    # Akapit w kontrolce zawartości (np. pole formularza).
    sdt = OxmlElement("w:sdt")
    zawartosc = OxmlElement("w:sdtContent")
    p_sdt = OxmlElement("w:p")
    r_sdt = OxmlElement("w:r")
    t_sdt = OxmlElement("w:t")
    t_sdt.text = "Tekst w kontrolce zawartosci."
    r_sdt.append(t_sdt)
    p_sdt.append(r_sdt)
    zawartosc.append(p_sdt)
    sdt.append(zawartosc)
    d.element.body.append(sdt)

    d.add_paragraph(RU)
    d.save(str(sciezka))


def test_f_kody_per_akapit_trafiaja_we_wlasne_jednostki() -> None:
    """F: kod nr N ląduje na jednostce nr N — na każdej ścieżce zapisu.

    To kontrakt, którego złamanie jest NIEWIDOCZNE w pliku wynikowym: plik
    z kodami przesuniętymi o jedną pozycję pozostaje poprawnym HTML-em czy
    DOCX-em, a czytnik ekranu po prostu czyta obcym głosem sąsiedni akapit.
    """
    cfg = cp.wariant_po_id(cp.TRYB_REZYSER, "pl", "naprawiacz_tagow")

    # --- .docx z oryginalem: akapity ciala ORAZ komorki tabeli ---
    zrodlo = KAT / "kontrakt_f.docx"
    _docx_z_tabela(zrodlo)
    jednostki = cp.jednostki_jezykowe("", ".docx", str(zrodlo))
    assert len(jednostki) == 6, (
        f".docx units: {len(jednostki)} instead of 6 — body paragraph, two table "
        f"cells, the hyperlink-only paragraph, the content-control paragraph and "
        f"the closing one (the empty paragraph does not count); `doc.paragraphs` "
        f"would see only 2, because it skips every one of those containers")
    kody = ["pl", "en", "de", "fi", "es", "it"]
    plik = Path(cp.zapisz_wynik("", str(KAT), "kontrakt_f_out", ".docx", "xx",
                                cp.TRYB_REZYSER, cfg, "", str(zrodlo),
                                kody_jednostek=kody))
    assert _langi_docx_kolejnosc(plik) == kody, (
        f".docx stamping order: {_langi_docx_kolejnosc(plik)} instead of {kody}")

    # --- pelny HTML: jednostka to blok z WLASNYM tekstem, nie sam lisc ---
    html = ('<html lang="pl"><head><title>T</title></head><body>'
            f"<h1>{PL}</h1>"
            f"<blockquote><p>{RU}</p></blockquote>"
            f"<ul><li>{PL}</li><li>{RU}</li></ul>"
            f"<table><tr><td>{PL}</td></tr></table>"
            f"<p>{RU} <b>pogrubione</b></p>"
            "</body></html>")
    jednostki = cp.jednostki_jezykowe(html, ".html")
    assert len(jednostki) == 6, (
        f"full-HTML units: {len(jednostki)} instead of 6 (h1, the p inside the "
        f"quote, two li, td, the last p) — this `blockquote` is NOT a unit, "
        f"because it has no text of its own")
    kody = ["en", "de", "es", "fr", "it", "ru"]
    plik = Path(cp.zapisz_wynik(html, str(KAT), "kontrakt_f_html", ".html", "is",
                                cp.TRYB_REZYSER, cfg, html, None,
                                kody_jednostek=kody))
    # blockquote bez wlasnego tekstu dostaje kod GLOBALNY, wiec siedzi miedzy
    # kodem naglowka i kodem swojego wlasnego akapitu.
    assert _langi_kolejnosc(plik) == ["en", "is", "de", "es", "fr", "it", "ru"], (
        f"full-HTML order: {_langi_kolejnosc(plik)}")

    # Blok, ktory ZAWIERA blok, ale ma tez tekst wlasny, JEST jednostka —
    # inaczej ten tekst wypadal z listy i po cichu dostawal kod globalny
    # (audyt v19.2; sciezka masowa to zagniezdzona lista Markdowna).
    html_wlasny = ('<html lang="pl"><body>'
                   f"<ul><li>{PL}<ul><li>{RU}</li></ul></li></ul>"
                   f"<blockquote>{PL}<p>{RU}</p></blockquote>"
                   "</body></html>")
    jednostki = cp.jednostki_jezykowe(html_wlasny, ".html")
    assert len(jednostki) == 4, (
        f"units with own text: {len(jednostki)} instead of 4 — the outer `li` "
        f"and the `blockquote` carry text of their own, so each is a unit")
    plik = Path(cp.zapisz_wynik(html_wlasny, str(KAT), "kontrakt_f_wlasny",
                                ".html", "is", cp.TRYB_REZYSER, cfg,
                                html_wlasny, None,
                                kody_jednostek=["en", "de", "es", "fr"]))
    assert _langi_kolejnosc(plik) == ["en", "de", "es", "fr"], (
        f"own-text order: {_langi_kolejnosc(plik)}")
    assert re.search(r'<html lang="is"', plik.read_text(encoding="utf-8")), (
        "the <html> element must keep the GLOBAL code, not the first unit's one")

    # --- .txt: akapity rozdzielone pusta linia ---
    txt = f"{PL}\n\n{RU}\n\n{PL}"
    jednostki = cp.jednostki_jezykowe(txt, ".txt")
    assert len(jednostki) == 3, f".txt units: {len(jednostki)} instead of 3"
    plik = Path(cp.zapisz_wynik(txt, str(KAT), "kontrakt_f_txt", ".txt", "pl",
                                cp.TRYB_REZYSER, cfg, txt, None,
                                kody_jednostek=["en", "de", "fi"]))
    assert _langi_kolejnosc(plik) == ["en", "de", "fi"], (
        f".txt order: {_langi_kolejnosc(plik)}")

    # --- .docx BEZ oryginalu (plik zniknal miedzy wczytaniem a zapisem) ---
    jednostki = cp.jednostki_jezykowe(txt, ".docx", str(KAT / "nie_ma_mnie.docx"))
    assert len(jednostki) == 3, (
        f".docx units without the original file: {len(jednostki)} instead of 3 — "
        f"NON-EMPTY lines count, exactly as `zapisz_wynik` builds them then")
    plik = Path(cp.zapisz_wynik(txt, str(KAT), "kontrakt_f_nowy", ".docx", "pl",
                                cp.TRYB_REZYSER, cfg, txt,
                                str(KAT / "nie_ma_mnie.docx"),
                                kody_jednostek=["en", "de", "fi"]))
    assert _langi_docx_kolejnosc(plik) == ["en", "de", "fi"], (
        f"order in the freshly built .docx: {_langi_docx_kolejnosc(plik)}")


def test_g_rozjazd_licznosci_jest_glosny() -> None:
    """G: liczba kodów ≠ liczba jednostek → ``ValueError``, nigdy cisza.

    Oba kierunki rozjazdu, bo oba znaczą to samo: lista, którą widział
    użytkownik, przestała odpowiadać plikowi. Cichy fallback na `iso_code`
    dałby plik wyglądający poprawnie i otagowany nie tam, gdzie trzeba.
    """
    cfg = cp.wariant_po_id(cp.TRYB_REZYSER, "pl", "naprawiacz_tagow")
    txt = f"{PL}\n\n{RU}\n\n{PL}"

    for kody, opis in ((["en"], "too few"), (["en"] * 9, "too many")):
        try:
            cp.zapisz_wynik(txt, str(KAT), f"kontrakt_g_{len(kody)}", ".txt",
                            "pl", cp.TRYB_REZYSER, cfg, txt, None,
                            kody_jednostek=kody)
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"{opis} codes ({len(kody)} for 3 units) passed without an "
                f"exception")

    # Sciezka surowa nie stempluje niczego, wiec kody sa z nia sprzeczne.
    try:
        cp.zapisz_wynik(txt, str(KAT), "kontrakt_g_surowy", ".srt", "pl",
                        cp.TRYB_REZYSER, cfg, txt, None, kody_jednostek=["en"])
    except ValueError:
        pass
    else:
        raise AssertionError(
            "per-unit codes on the raw-write path passed without an exception")


def test_h_jednostki_zgadzaja_sie_z_liczba_stempli() -> None:
    """H: ``jednostki_jezykowe`` liczy dokładnie tyle, ile zapis stempluje.

    Kontrakt sprawdzany PRZEZ WYKONANIE: skoro rozjazd licznosci podnosi
    wyjątek (kontrakt G), to zapis z ``kody_jednostek`` długości
    ``len(jednostki_jezykowe(...))`` musi przejść — dla każdej ścieżki. Ten
    test jest więc spoiwem obu stron umowy, a nie powtórzeniem kontraktu F.
    """
    cfg = cp.wariant_po_id(cp.TRYB_REZYSER, "pl", "naprawiacz_tagow")
    txt = f"{PL}\n\n{RU}"
    html_frag = f"<p>{PL}</p>\n\n<p>{RU}</p>"
    html_pelny = f'<html lang="pl"><body><h1>{PL}</h1><p>{RU}</p></body></html>'
    zrodlo = KAT / "kontrakt_h.docx"
    _docx_z_tabela(zrodlo)

    przypadki = [
        (".txt", txt, None),
        (".md", txt, None),
        (".html", html_frag, None),
        (".html", html_pelny, None),
        (".htm", html_pelny, None),
        (".docx", "", str(zrodlo)),        # tabela + hiperlink + w:sdt
        (".docx", txt, None),
    ]
    for i, (ext, tresc, zrodlo_sc) in enumerate(przypadki):
        jednostki = cp.jednostki_jezykowe(tresc, ext, zrodlo_sc)
        assert jednostki, f"{ext}: zero units for non-empty content"
        cp.zapisz_wynik(tresc, str(KAT), f"kontrakt_h_{i}", ext, "pl",
                        cp.TRYB_REZYSER, cfg, tresc, zrodlo_sc,
                        kody_jednostek=["pl"] * len(jednostki))

    assert cp.jednostki_jezykowe(txt, ".srt") == [], (
        "an extension written raw has no units — the writer does not touch the "
        "content, so the list must be empty")


def test_i_opinia_detektora_zna_jezyki_bez_paczki() -> None:
    """I: opinia detektora obejmuje PEŁNY kanon Lingui, nie dziewięć paczek.

    Sens Naprawiacza Tagów to pliki w językach, dla których paczki NIE MA —
    detektor zawężony do `dictionaries/` odpowiadałby na nie pewnie i błędnie.
    Czeski i portugalski są tu dowodem: obu brakuje w paczkach, oba są
    w kanonie. Kontrakt pilnuje też ciszy tam, gdzie opinii nie ma.
    """
    czeski = ("Přišel jsem domů a našel jsem na stole dopis, který nikdo "
              "nečekal, a pak už bylo pozdě cokoliv měnit.")
    portugalski = ("O homem caminhou pela praia durante toda a tarde e "
                   "nunca encontrou aquilo que procurava com tanto empenho.")
    assert cp.opinia_detektora(czeski) == "cs", (
        f"Czech detected as {cp.opinia_detektora(czeski)!r}; there is no `cs` "
        f"pack, so a detector narrowed to packs could never return it")
    assert cp.opinia_detektora(portugalski) == "pt", (
        f"Portuguese detected as {cp.opinia_detektora(portugalski)!r}")
    assert "cs" not in cp.dostepne_jezyki_bazowe(), (
        "this contract loses its meaning once a `cs` pack exists — swap the "
        "sample for another language that has no pack")

    assert cp.opinia_detektora("Tak.") is None, (
        "a fragment below the detection threshold must have NO opinion, rather "
        "than receive a guessed code")
    assert cp.opinia_detektora("") is None
    assert cp.opinia_detektora(None) is None

    # Nazwa do pokazania: natywna dla paczki, enumowa dla reszty — nigdy
    # polski przymiotnik (to byloby wyciekiem PL w niemieckim interfejsie).
    assert cp.nazwa_dla_opinii("fi") == "Suomi", cp.nazwa_dla_opinii("fi")
    assert cp.nazwa_dla_opinii("cs") == "Czech", cp.nazwa_dla_opinii("cs")
    assert cp.nazwa_dla_opinii("") == ""


def test_j_nazwa_pliku_nie_klamie_o_jednym_jezyku() -> None:
    """J: przy kodach per akapit nazwa pliku pokazuje ZBIÓR użytych kodów.

    Znalezisko z audytu v19.2. `sufiks_nazwy_pliku` brało kod z pola „Kod ISO",
    więc plik z akapitami `en`/`de`/`fi` nazywał się `naprawiony_x_pl.html` —
    dokładnie ta klasa, którą v19.1 nazwało „plik wynikowy kłamie o swoim
    języku", tylko przeniesiona do nazwy. Jeden kod = nazwa bez zmian
    (kompatybilność z biegiem sprzed 19.2).
    """
    def nazwa(opcje: dict) -> str:
        return cp.sufiks_nazwy_pliku(cp.TRYB_REZYSER, "pl", "naprawiacz_tagow",
                                     "probka", opcje)

    assert nazwa({"iso_reczne": "pl"}).endswith("_pl"), nazwa({"iso_reczne": "pl"})
    assert nazwa({"iso_reczne": "pt-BR",
                  "kody_jednostek": ["pt-BR", "pt-BR"]}).endswith("_pt-BR"), (
        "one code repeated is still ONE language — the name must not change")

    wiele = nazwa({"iso_reczne": "pl", "kody_jednostek": ["en", "de", "fi", "en"]})
    assert wiele.endswith("_de-en-fi"), (
        f"name for a mixed file: {wiele} — expected the sorted set of codes")
    assert "_pl" not in wiele, (
        f"name still claims the ISO field's code: {wiele}")

    duzo = nazwa({"iso_reczne": "pl",
                  "kody_jednostek": ["en", "de", "fi", "is", "it", "ru"]})
    assert duzo.endswith("_de-en-fi-is+2"), (
        f"name for six codes: {duzo} — expected four codes plus an overflow count")


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
