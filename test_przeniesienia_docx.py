"""
test_przeniesienia_docx.py — czyszczenie `.docx` z konwersji PDF→Word (19.15).

Semantyka WSPÓLNA z ATA (kanon synchronizacji, klasa `formaty_zrodel`), więc
wektory testowe przeniesień są przepisane 1:1 ze wspólnej specyfikacji:
  A. przeniesienie w akapicie — reguły 1–4 (`napraw_przeniesienia`);
  B. spacja z fontu Symbol U+F020 → zwykła spacja;
  C. tekst rozstrzelony — sklejany tylko, gdy dokument zna słowo
     (`scal_rozstrzelone`), plus ograniczenie: ciąg przyklejony pojedynczą
     spacją do innego tokenu to urwany kawałek i zostaje.
Obie ścieżki `.docx` (Poliglota `tekst_docx`, Konwerter) idą przez
`oczysc_akapity_docx`.

Uruchom:  .venv/Scripts/python -m pytest test_przeniesienia_docx.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_przeniesienia_docx.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_poliglota as cp  # noqa: E402

# Tło dokumentu dla wektorów: słowa, które występują GDZIE INDZIEJ.
TLO = "Ковид-диссидентов много. Голубых домов. Двух домов и трёхкомнатный."


# Wektory wspólnej specyfikacji (ATA ma te same, co do znaku).
@pytest.mark.parametrize("wejscie, wynik, regula", [
    ("по- священного", "посвященного", "3"),             # R nie jest słowem dokumentu
    ("государст- венный", "государственный", "3"),
    ("бело- голубых", "бело- голубых", "4"),             # „голубых” jest słowem
    ("двух- и трёхкомнатный", "двух- и трёхкомнатный", "4"),   # „и” jest słowem
    ("ковид- диссидентов", "ковид-диссидентов", "2"),    # „ковид-диссидентов” jest słowem
    ("по-английски", "по-английски", None),             # łącznik bez spacji: nie kandydat
    ("obozrenie- birulevo.ru", "obozrenie- birulevo.ru", "wykluczone"),
    ("ПО- СВЯЩЕННОГО", "ПО- СВЯЩЕННОГО", "wykluczone"),  # wielka litera R
])
def test_wektory_wspolnej_specyfikacji(wejscie, wynik, regula):
    akapity, liczniki = cp.napraw_przeniesienia([TLO, wejscie])
    assert akapity == [TLO, wynik]
    trafione = {k for k, v in liczniki.items() if v}
    assert trafione == ({regula} if regula else set())


def test_regula_1_przed_regula_2():
    akapity, liczniki = cp.napraw_przeniesienia(["Онлайн и он-лайн.", "Урок он- лайн."])
    assert akapity[1] == "Урок онлайн." and liczniki["1"] == 1


@pytest.mark.parametrize("akapit", [
    "Вирус COVID- выплаты.",          # różne pisma
    "Сайт www.ru- новости.",          # kropka w słowie L
    "Код ab_c- def.",                 # podkreślnik w słowie L
    "Вирус ко2вид- ные.",             # cyfra w słowie L
    "Адрес site- ru2.",               # cyfra w słowie R
])
def test_wykluczenia(akapit):
    akapity, liczniki = cp.napraw_przeniesienia([akapit])
    assert akapity == [akapit] and liczniki["wykluczone"] == 1


def test_interpunkcja_na_brzegu_nie_wyklucza():
    akapity, liczniki = cp.napraw_przeniesienia(["Издание («по- священного», 2020)."])
    assert akapity == ["Издание («посвященного», 2020)."] and liczniki["3"] == 1


def test_liczba_akapitow_i_granica_akapitu_bez_zmian():
    # Naprawiacz tagów nakłada kody PO INDEKSIE akapitu oryginału.
    akapity = ["Конец строки по-", "священного начало.", ""]
    assert cp.napraw_przeniesienia(akapity)[0] == akapity


def test_spacja_z_fontu_symbol():
    spacja = chr(0xF020)
    akapity, liczniki = cp.oczysc_akapity_docx([f"{spacja} {spacja}\t— пункт"])
    assert akapity == ["   \t— пункт"] and liczniki["spacja_symbol"] == 2


def test_rozstrzelone_sklejone_gdy_slowo_jest_w_dokumencie():
    akapity, liczniki = cp.scal_rozstrzelone(
        ["Социальное дистанцирование — термин.",
         "С о ц и а л ь н о е   д и с т а н ц и р о в а н и е"])
    assert akapity[1] == "Социальное   дистанцирование"
    assert liczniki["sklejone"] == 2


def test_rozstrzelone_bez_slowa_i_jednoliterowe_slowa_zostaja():
    # „а и в к” to cztery jednoliterowe słowa; „аивк” nie jest słowem.
    akapity, liczniki = cp.scal_rozstrzelone(["Слова а и в к стоят рядом."])
    assert akapity == ["Слова а и в к стоят рядом."] and liczniki["sklejone"] == 0


@pytest.mark.parametrize("akapit", [
    "Маск сказал. Защитная м а с к а.",            # „а.” urywa ciąg: nie „маск а.”
    "Асоциальный. А с о ц и а ' л ь н а я",       # akcent apostrofem w środku
])
def test_rozstrzelone_przyklejone_zostaja(akapit):
    akapity, liczniki = cp.scal_rozstrzelone([akapit])
    assert akapity == [akapit] and liczniki["przyklejone"] >= 1


def test_slownik_bez_urywkow_przy_apostrofie():
    # „КОВИ'ДНЫЙ” nie zatwierdza sklejenia rozstrzelonego „К о в и”.
    akapity, _ = cp.scal_rozstrzelone(["КОВИ'ДНЫЙ хвост.", "К о в и"])
    assert akapity[1] == "К о в и"


def _docx(sciezka, *akapity):
    import docx
    d = docx.Document()
    for a in akapity:
        d.add_paragraph(a)
    d.save(str(sciezka))


def test_tekst_docx_poligloty(tmp_path):
    p = tmp_path / "slownik.docx"
    _docx(p, TLO, "Издание, по- священного теме.", "Квартиры двух- и трёхкомнатный.")
    assert cp.tekst_docx(str(p)).split("\n")[1:] == [
        "Издание, посвященного теме.", "Квартиры двух- и трёхкомнатный."]


def test_konwerter_czysci_tak_samo(tmp_path, monkeypatch):
    wx = pytest.importorskip("wx")
    import docx
    import gui_konwerter as gk
    import i18n
    p = tmp_path / "slownik.docx"
    _docx(p, TLO, "Издание, по- священного теме.")
    zapisane = []
    monkeypatch.setattr(docx.document.Document, "save",
                        lambda self, _p: zapisane.append([x.text for x in self.paragraphs]))
    monkeypatch.setattr(wx, "MessageBox", lambda *_a, **_k: wx.OK)
    app = wx.App(False)
    jezyk_przed = i18n.aktualny_jezyk()
    i18n.ustaw_jezyk("pl")
    ramka = wx.Frame(None)
    try:
        panel = gk.KonwerterPanel(ramka)
        panel._txt_file.SetValue(str(p))
        panel._on_build(None)
    finally:
        ramka.Destroy()
        app.Destroy()
        i18n.ustaw_jezyk(jezyk_przed)
    assert zapisane, "Konwerter nic nie zapisał"
    tekst = "\n".join(zapisane[-1])
    assert "посвященного" in tekst and "по- священного" not in tekst


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
