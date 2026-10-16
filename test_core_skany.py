"""
test_core_skany.py — odczyt stron-skanów PDF modelem z obrazem (v19.14).

Kontrakty `core_skany`, których nie sprawdza żadna bramka danych:
  A. cięcie: jednostronicowy PDF z właściwej strony, bez Pillow;
  B. strona: odmowa / pusta odpowiedź / urwanie / błąd strony mają STATUS
     i powód (zero ciszy), płot ``` zdjęty, znaczniki policzone; błąd
     krytyczny (limit, klucz, nieznany model) leci wyżej;
  C. seria: strony PO KOLEI z kontekstem poprzedniej (warstwa tekstu albo
     odczytany skan, nigdy strona nieodczytana); błąd krytyczny i anulowanie
     dają wynik KAŻDEJ strony z powodem;
  D. scalanie: kolejność stron, akapit pochodzenia, tekst ze skanu
     escapowany PRZED renderem (wejście niezaufane — `<script>` z obrazu nie
     może trafić do pliku), znaczniki podmienione PO renderze (nie stają się
     linkami), nieznany token zostaje dosłownie;
  E. każdy token z `ZNACZNIKI` ma klucz w `ui.yaml` paczki `pl`.

Mock modelu, zero wywołań API.

Uruchom:  .venv/Scripts/python -m pytest test_core_skany.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_core_skany.py
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

import core_llm as cl
import core_skany as cs
from test_core_pdf import _zbuduj_pdf


@pytest.fixture(autouse=True)
def _t_jawne(monkeypatch):
    """`t` zwraca klucz i parametry — test widzi, CO wstawiono, bez paczki językowej."""
    def t(klucz, **kw):
        return klucz + "".join(f"|{k}={v}" for k, v in sorted(kw.items()))
    monkeypatch.setattr(cs, "t", t)


def _model(monkeypatch, odpowiedzi):
    """Podmienia wywołanie modelu; zwraca listę kwargów kolejnych wywołań."""
    wyslane = []

    def wywolaj(klient, **kw):
        wyslane.append(kw)
        nastepna = odpowiedzi.pop(0)
        if isinstance(nastepna, Exception):
            raise nastepna
        return nastepna

    monkeypatch.setattr(cl, "wywolaj_llm_z_pdf", wywolaj)
    monkeypatch.setattr(cs, "wytnij_strone", lambda _s, n: f"PDF{n}".encode())
    return wyslane


KLIENT = cl.KlientLLM(cl.PROVIDER_ANTHROPIC, None)


# --------------------------------------------------------------------- A ---

def test_wytnij_strone_daje_jedna_wlasciwa_strone(tmp_path):
    import pypdfium2 as pdfium
    p = tmp_path / "trzy.pdf"
    _zbuduj_pdf(p, [[(f"Strona {i}.", 72, 700)] for i in (1, 2, 3)])
    dane = cs.wytnij_strone(str(p), 2)
    pdf = pdfium.PdfDocument(dane)
    try:
        assert len(pdf) == 1
        assert pdf[0].get_textpage().get_text_range().strip() == "Strona 2."
    finally:
        pdf.close()


# --------------------------------------------------------------------- B ---

def test_strona_ok_bez_plotu_ze_znacznikami(monkeypatch):
    wyslane = _model(monkeypatch, [(
        "```markdown\n**Imię:** [[ILLEGIBLE]]\n**Kod:** [[EMPTY]]\n[[ILLEGIBLE]]\n```",
        "end_turn")])
    w = cs.odczytaj_strone(KLIENT, b"PDF", 2, kontekst="koniec strony 1")
    assert w.status == cs.STATUS_OK
    assert w.markdown.startswith("**Imię:**") and "```" not in w.markdown
    assert w.znaczniki == {"ILLEGIBLE": 2, "EMPTY": 1}
    kw = wyslane[0]
    assert kw["system"] == cs.SYSTEM_SKANY and kw["tekst_po"] == cs.INSTRUKCJA
    assert kw["tekst_przed"] == "<previous_page>\nkoniec strony 1\n</previous_page>"
    assert kw["model"] == cs.MODEL_SKANY and kw["pdf"] == b"PDF"


def test_instrukcja_nie_podaje_numeru_strony():
    # „Transcribe page 2." przy PDF-ie po cięciu (1 strona) dawało wstęp
    # „nie ma strony 2" w wyniku czytanym na głos (zmierzone 2026-10-16).
    assert not any(z.isdigit() for z in cs.INSTRUKCJA)


def test_kontekst_przyciety_do_konca_poprzedniej(monkeypatch):
    wyslane = _model(monkeypatch, [("x", "end_turn")])
    cs.odczytaj_strone(KLIENT, b"PDF", 2, kontekst="a" * 5000 + "KONIEC")
    przed = wyslane[0]["tekst_przed"]
    assert przed.endswith("KONIEC\n</previous_page>")
    assert len(przed) < cs.KONTEKST_ZNAKI + 50


def test_bez_kontekstu_bez_bloku(monkeypatch):
    wyslane = _model(monkeypatch, [("x", "end_turn")])
    cs.odczytaj_strone(KLIENT, b"PDF", 1, kontekst="  \n")
    assert wyslane[0]["tekst_przed"] == ""


@pytest.mark.parametrize("odpowiedz, status, powod", [
    (("", cl.STOP_ODRZUCENIE), cs.STATUS_ODMOWA, "poliglota.skan_powod_odmowa"),
    ((" \n ", "end_turn"), cs.STATUS_BLAD, "poliglota.skan_powod_pusta"),
    (cl.BladTimeoutLLM("timeout"), cs.STATUS_BLAD, "poliglota.skan_powod_blad"),
])
def test_strona_nieodczytana_ma_status_i_powod(monkeypatch, odpowiedz, status, powod):
    _model(monkeypatch, [odpowiedz])
    w = cs.odczytaj_strone(KLIENT, b"PDF", 4)
    assert (w.status, w.powod, w.markdown) == (status, powod, "")


def test_surowy_wyjatek_tylko_w_szczegole_nie_w_powodzie(monkeypatch):
    # Angielski JSON błędu SDK z `request_id` trafiał do treści dokumentu,
    # którą syntezator czyta na głos (audyt 19.14).
    _model(monkeypatch, [cl.BladTimeoutLLM('{"error": {"request_id": "req_X"}}')])
    w = cs.odczytaj_strone(KLIENT, b"PDF", 4)
    assert "req_X" not in w.powod and "req_X" in w.szczegol
    assert w.szczegol.startswith("BladTimeoutLLM: ")


def test_urwana_strona_zachowuje_odczytana_czesc(monkeypatch):
    _model(monkeypatch, [("# Tytuł\n\nPoczątek", "max_tokens")])
    w = cs.odczytaj_strone(KLIENT, b"PDF", 4)
    assert w.status == cs.STATUS_UCIETA and w.markdown == "# Tytuł\n\nPoczątek"


@pytest.mark.parametrize("blad", [
    cl.BladLimituLLM("429"),
    cl.BladModeluLLM("claude-x", cl.PROVIDER_OPENROUTER),
    cl.BladFunkcjiNiedostepnej("pdf", cl.PROVIDER_OPENAI_COMPAT),
])
def test_blad_krytyczny_leci_wyzej(monkeypatch, blad):
    _model(monkeypatch, [blad])
    with pytest.raises(type(blad)):
        cs.odczytaj_strone(KLIENT, b"PDF", 4)


# --------------------------------------------------------------------- C ---

AKAPITY = [["Strona pierwsza."], [], [], ["Strona czwarta."], []]


def test_seria_kontekst_z_tekstu_albo_poprzedniego_skanu(monkeypatch):
    wyslane = _model(monkeypatch, [("SKAN 2", "end_turn"), ("SKAN 3", "end_turn"),
                                   ("SKAN 5", "end_turn")])
    postep = []
    wyniki, blad = cs.odczytaj_strony(KLIENT, "x.pdf", AKAPITY, [2, 3, 5],
                                      postep=lambda *a: postep.append(a))
    assert blad is None and [w.numer for w in wyniki] == [2, 3, 5]
    konteksty = [kw["tekst_przed"] for kw in wyslane]
    assert "Strona pierwsza." in konteksty[0]
    assert "SKAN 2" in konteksty[1]
    assert "Strona czwarta." in konteksty[2]
    assert [kw["pdf"] for kw in wyslane] == [b"PDF2", b"PDF3", b"PDF5"]
    assert postep == [(0, 3, 2), (1, 3, 3), (2, 3, 5)]


def test_strona_nieodczytana_nie_jest_kontekstem(monkeypatch):
    wyslane = _model(monkeypatch, [("", cl.STOP_ODRZUCENIE), ("SKAN 3", "end_turn")])
    cs.odczytaj_strony(KLIENT, "x.pdf", AKAPITY, [2, 3])
    assert wyslane[1]["tekst_przed"] == ""


def test_blad_krytyczny_daje_powod_kazdej_pozostalej_stronie(monkeypatch):
    limit = cl.BladLimituLLM("brak kredytów")
    _model(monkeypatch, [("SKAN 2", "end_turn"), limit])
    wyniki, blad = cs.odczytaj_strony(KLIENT, "x.pdf", AKAPITY, [2, 3, 5])
    assert blad is limit
    assert [(w.numer, w.status) for w in wyniki] == [
        (2, cs.STATUS_OK), (3, cs.STATUS_BLAD), (5, cs.STATUS_BLAD)]
    assert wyniki[2].powod == "poliglota.skan_powod_blad"
    assert wyniki[2].szczegol == "BladLimituLLM: brak kredytów"


def test_anuluj_w_trakcie_strony_nie_wysyla_nastepnej(monkeypatch):
    # Audyt 19.14 [WYSOKA]: „Anuluj" w trakcie strony 2 przepuszczało stronę 3
    # do zewnętrznej usługi — płatnie i z danymi osobowymi po cofnięciu zgody.
    anulowane = []
    wyslane = []

    def wywolaj(klient, **kw):
        wyslane.append(kw["pdf"])
        anulowane.append(True)          # użytkownik klika „Anuluj" w trakcie
        return "SKAN", "end_turn"

    monkeypatch.setattr(cl, "wywolaj_llm_z_pdf", wywolaj)
    monkeypatch.setattr(cs, "wytnij_strone", lambda _s, n: f"PDF{n}".encode())
    wyniki, blad = cs.odczytaj_strony(KLIENT, "x.pdf", AKAPITY, [2, 3, 5],
                                      przerwij=lambda: bool(anulowane))
    assert blad is None
    assert [(w.numer, w.status, w.powod) for w in wyniki] == [
        (2, cs.STATUS_OK, ""),
        (3, cs.STATUS_BLAD, "poliglota.skan_powod_anulowano"),
        (5, cs.STATUS_BLAD, "poliglota.skan_powod_anulowano")]
    assert wyslane == [b"PDF2"]


def test_zla_strona_przy_cieciu_nie_kasuje_odczytanych(monkeypatch):
    # Audyt 19.14: wyjątek `wytnij_strone` w środku serii wywracał cały
    # (opłacony) odczyt — zostawał sam tekst warstwy.
    _model(monkeypatch, [("SKAN 2", "end_turn"), ("SKAN 5", "end_turn")])

    def tnij(_s, n):
        if n == 3:
            raise OSError("damaged page")
        return f"PDF{n}".encode()

    monkeypatch.setattr(cs, "wytnij_strone", tnij)
    wyniki, blad = cs.odczytaj_strony(KLIENT, "x.pdf", AKAPITY, [2, 3, 5])
    assert blad is None
    assert [(w.numer, w.status) for w in wyniki] == [
        (2, cs.STATUS_OK), (3, cs.STATUS_BLAD), (5, cs.STATUS_OK)]
    assert wyniki[1].szczegol == "OSError: damaged page"


def test_kontekst_przez_strone_doklejona_do_wczesniejszej(monkeypatch):
    # Strona 2 jest pusta, bo jej tekst doklejono do akapitu strony 1 —
    # skan na stronie 3 ma dostać koniec tego akapitu, nie pustkę.
    wyslane = _model(monkeypatch, [("SKAN 3", "end_turn")])
    cs.odczytaj_strony(KLIENT, "x.pdf", [["Zdanie przez dwie strony."], [], []], [3])
    assert "Zdanie przez dwie strony." in wyslane[0]["tekst_przed"]


def test_kontekst_nie_przechodzi_przez_nieodczytany_skan():
    assert cs._kontekst(3, [["Tekst."], [], []], {2, 3}, {}) == ""


def test_tekst_tresci_bez_pochodzenia_i_znacznikow():
    wyniki = [cs.WynikStrony(2, cs.STATUS_OK, "Name: [[ILLEGIBLE]] Smith"),
              cs.WynikStrony(3, cs.STATUS_ODMOWA, powod="r")]
    tekst = cs.tekst_tresci([["Intro."], [], [], ["End."]], wyniki)
    assert tekst == "Intro.\n\nName:   Smith\n\nEnd."


def test_zakresy_stron():
    assert cs.zakresy([2, 3, 4, 5, 9, 11, 12]) == "2–5, 9, 11–12"
    assert cs.zakresy([7]) == "7" and cs.zakresy([]) == ""


@pytest.mark.parametrize("plot", ["```", "~~~"])
def test_plot_obu_rodzajow_zdjety(plot):
    assert cs._zdejmij_plot(f"{plot}markdown\n# A\n{plot}") == "# A"


# --------------------------------------------------------------------- D ---

def _body(dokument):
    return dokument.split("<body>\n", 1)[1].split("\n</body>", 1)[0]


def test_scal_kolejnosc_stron_i_pochodzenie():
    wyniki = [cs.WynikStrony(2, cs.STATUS_OK, "## Akt\n\n**Imię:** Jan")]
    html = cs.scal([["Wstęp."], [], ["Koniec."]], wyniki, "pl", "doc")
    body = _body(html)
    assert body.index("Wstęp.") < body.index("skan_pochodzenie|numer_strony=2") \
        < body.index("<h2>Akt</h2>") < body.index("Koniec.")
    assert "<strong>Imię:</strong> Jan" in body
    assert "<title>doc</title>" in html and '<html lang="pl">' in html


def test_scal_escapuje_html_ze_skanu_i_z_warstwy_tekstu():
    wyniki = [cs.WynikStrony(1, cs.STATUS_OK,
                             "<script>alert(1)</script> & <b>x</b>\n\nP<RUS<<JAN<<<")]
    body = _body(cs.scal([[], ["a < b & c"]], wyniki, "pl", "doc"))
    assert "<script" not in body and "<b>" not in body
    assert "<p>&lt;script&gt;alert(1)&lt;/script&gt; &amp; &lt;b&gt;x&lt;/b&gt;</p>" in body
    assert "P&lt;RUS&lt;&lt;JAN" in body
    assert "<p>a &lt; b &amp; c</p>" in body


def test_scal_zdejmuje_markdownowy_escape_modelu():
    # Model pisze `\<script>` — bez zdjęcia w wyniku zostawał czytany `\`.
    wyniki = [cs.WynikStrony(1, cs.STATUS_OK, "\\<script>x\\</script> \\& Co")]
    body = _body(cs.scal([[]], wyniki, "pl", "doc"))
    assert "<p>&lt;script&gt;x&lt;/script&gt; &amp; Co</p>" in body


def test_scal_bez_linkow_obrazow_i_podwojnego_escape():
    # Audyt 19.14: `[x](javascript:…)` dawał działający `<a href>`, `![](…)`
    # zdalny `<img>`, a kod dostawał `&amp;amp;` (czytane na głos „amp").
    wyniki = [cs.WynikStrony(1, cs.STATUS_OK,
                             "[x](javascript:alert(1)) ![o](http://evil/x.png) <http://e>\n\n"
                             "[r][1]\n\n[1]: javascript:y\n\n"
                             "Kod `a & <b>` i &amp; encja\n\n    wciety & <i>")]
    body = _body(cs.scal([[]], wyniki, "pl", "doc"))
    assert "<a " not in body and "<img" not in body and "href" not in body
    assert "[x](javascript:alert(1))" in body and "[1]: javascript:y" in body
    assert "&amp;amp;" not in body and "&amp;lt;" not in body
    assert "<code>a &amp; &lt;b&gt;</code>" in body
    assert "wciety &amp; &lt;i&gt;" in body


def test_sentinele_w_tekscie_modelu_nie_udaja_znacznika():
    tekst = chr(0xE000) + "FOO" + chr(0xE001) + " [[ILLEGIBLE]]"
    body = _body(cs.scal([[]], [cs.WynikStrony(1, cs.STATUS_OK, tekst)], "pl", "doc"))
    assert "skan_znacznik_foo" not in body
    assert "FOO poliglota.skan_znacznik_illegible" in body


def test_scal_znaczniki_po_renderze_nie_staja_sie_linkami():
    wyniki = [cs.WynikStrony(1, cs.STATUS_OK,
                             "**Nr:** [[ILLEGIBLE]](http://x)\n\n[[SIGNATURE]] [[NIEZNANY]]")]
    body = _body(cs.scal([[]], wyniki, "pl", "doc"))
    assert "<a " not in body
    assert "poliglota.skan_znacznik_illegible(http://x)" in body
    assert "poliglota.skan_znacznik_signature [[NIEZNANY]]" in body
    assert chr(0xE000) not in body and chr(0xE001) not in body


def test_scal_strona_nieodczytana_i_urwana_sa_jawne():
    wyniki = [cs.WynikStrony(1, cs.STATUS_BLAD, powod="Timeout <x>"),
              cs.WynikStrony(2, cs.STATUS_UCIETA, "Początek")]
    body = _body(cs.scal([[], []], wyniki, "pl", "doc"))
    assert "skan_nieodczytana|numer_strony=1|powod=Timeout &lt;x&gt;" in body
    assert body.index("Początek") < body.index("skan_ucieta|numer_strony=2")


# --------------------------------------------------------------------- E ---

PACZKI = sorted(p.name for p in (Path(__file__).parent / "dictionaries").iterdir()
                if (p / "gui" / "ui.yaml").is_file())


@pytest.mark.parametrize("kod", PACZKI)
def test_kazdy_znacznik_ma_klucz_w_ui_kazdej_paczki(kod):
    # Brak klucza nie wywraca odczytu, tylko wstawia `[poliglota.skan_…]`
    # w wynik czytany na głos — tego nie złapie żadna inna bramka.
    ui = yaml.safe_load((Path(__file__).parent / "dictionaries" / kod / "gui" / "ui.yaml")
                        .read_text(encoding="utf-8"))["poliglota"]
    brak = [z for z in cs.ZNACZNIKI if f"skan_znacznik_{z.lower()}" not in ui]
    assert brak == []


@pytest.mark.parametrize("provider, dostepny", [
    (cl.PROVIDER_ANTHROPIC, True), (cl.PROVIDER_OPENROUTER, True),
    (cl.PROVIDER_OPENAI_COMPAT, False)])
def test_odczyt_dostepny_per_provider(provider, dostepny):
    assert cs.odczyt_dostepny(cl.KlientLLM(provider, None)) is dostepny
    assert cs.odczyt_dostepny(None) is False


def test_szacunek_kosztu_po_modelu_natywnym():
    anthropic = cl.KlientLLM(cl.PROVIDER_ANTHROPIC, None)
    assert cs.szacuj_koszt(anthropic, 10) == pytest.approx(0.12)
    # OpenRouter: id `anthropic/claude-sonnet-5.5` mapowane z powrotem na natywne.
    assert cs.szacuj_koszt(cl.KlientLLM(cl.PROVIDER_OPENROUTER, None), 10) \
        == pytest.approx(0.12)
    # `LLM_MODEL` spoza cennika → koszt nieznany, nie zero.
    obcy = cl.KlientLLM(cl.PROVIDER_OPENROUTER, None, model_override="google/gemini-x")
    assert cs.szacuj_koszt(obcy, 10) is None


@pytest.mark.parametrize("koszt, wynik", [
    (None, "poliglota.skan_zgoda_koszt_nieznany"),
    (0.004, "poliglota.skan_zgoda_koszt_ponizej_centa"),
    (0.012, "poliglota.skan_zgoda_koszt_centy|liczba_centow=1"),
    (0.24, "poliglota.skan_zgoda_koszt_centy|liczba_centow=24"),
    (0.995, "poliglota.skan_zgoda_koszt|kwota=0.99"),     # nie „100 centów"
    (1.2, "poliglota.skan_zgoda_koszt|kwota=1.20"),
])
def test_opis_kosztu_w_centach_ponizej_dolara(koszt, wynik):
    # „około 0.01 USD" czytnik podawał jak „zero dolarów" (uwaga maintainera).
    assert cs.opis_kosztu(koszt) == wynik


def test_kazdy_klucz_skan_uzyty_w_kodzie_jest_w_kazdej_paczce():
    # Brak klucza nie wywraca niczego: `t()` oddaje `[klucz]`, który trafia
    # do dialogu albo do dokumentu czytanego na głos.
    import re
    korzen = Path(__file__).parent
    kod = "".join((korzen / f).read_text(encoding="utf-8")
                  for f in ("core_skany.py", "gui_poliglota.py"))
    uzyte = set(re.findall(r'"poliglota\.(skan_[a-z_]+)"', kod))
    uzyte |= {f"skan_znacznik_{z.lower()}" for z in cs.ZNACZNIKI}
    assert len(uzyte) > 20
    for kod_paczki in PACZKI:
        ui = yaml.safe_load((korzen / "dictionaries" / kod_paczki / "gui" / "ui.yaml")
                            .read_text(encoding="utf-8"))["poliglota"]
        assert sorted(uzyte - set(ui)) == [], kod_paczki


def test_podsumowanie_kazda_strona_w_jednej_grupie():
    p = cs.podsumuj([
        cs.WynikStrony(1, cs.STATUS_OK, "x", znaczniki={"ILLEGIBLE": 2, "EMPTY": 1}),
        cs.WynikStrony(2, cs.STATUS_UCIETA, "y", znaczniki={"ILLEGIBLE": 1}),
        cs.WynikStrony(3, cs.STATUS_ODMOWA, powod="r"),
        cs.WynikStrony(4, cs.STATUS_BLAD, powod="b"),
    ])
    assert p.odczytane == 2 and p.urwane == [2]
    assert [w.numer for w in p.nieodczytane] == [3, 4]
    assert p.znaczniki == {"ILLEGIBLE": 3, "EMPTY": 1}


def test_kazdy_znacznik_jest_w_prompcie():
    assert all(f"[[{z}]]" in cs.SYSTEM_SKANY for z in cs.ZNACZNIKI)


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
