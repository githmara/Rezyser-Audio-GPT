"""
test_poliglota_skany.py — Poliglota: wczytanie PDF-a ze stronami-skanami (v19.14).

Prawdziwy `PoliglotaPanel` bez `MainLoop` (wzorzec z CLAUDE.md): dialogi,
wątek i `wx.CallAfter` podmienione na synchroniczne atrapy, model na atrapę
`core_skany.odczytaj_strony`. Kontrakty:
  1. zgoda → wynik `.html` ze stroną-skanem na swoim miejscu + podsumowanie;
  2. „Pomiń" → dzisiejsza ścieżka `.txt`, ani jednego wywołania modelu;
  3. provider bez odczytu (`openai_compat`, brak klucza) → BEZ pytania
     o zgodę, a informacja mówi, dlaczego odczytu nie ma;
  4. PDF w całości zeskanowany dostaje tę samą ofertę;
  5. nieoczekiwany błąd wątku → komunikat + sam tekst warstwy (zero ciszy);
  6. drugi „Wczytaj" w trakcie odczytu nic nie startuje;
  7. „Anuluj" w oknie postępu ustawia przerwanie dla następnej strony.

Uruchom:  .venv/Scripts/python -m pytest test_poliglota_skany.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_poliglota_skany.py
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

wx = pytest.importorskip("wx")

import core_llm as cl  # noqa: E402
import core_skany as cs  # noqa: E402
import i18n  # noqa: E402
from test_core_pdf import _zbuduj_pdf  # noqa: E402


class _Zapis:
    def __init__(self):
        self.zgody: list[str] = []
        self.komunikaty: list[str] = []
        self.dlugie: list[tuple[str, str]] = []
        self.odczyty: list[tuple] = []
        self.odpowiedz_zgody = wx.ID_YES
        self.postep_dalej = True


@pytest.fixture
def srodowisko(monkeypatch):
    import gui_diagnostyka as gd
    import gui_poliglota as gp

    zapis = _Zapis()
    app = wx.App(False)
    jezyk_przed = i18n.aktualny_jezyk()
    i18n.ustaw_jezyk("pl")

    class Dialog:
        def __init__(self, _rodzic, tresc, *_a, **_k):
            zapis.zgody.append(tresc)

        def SetYesNoLabels(self, *_a):
            return True

        def ShowModal(self):
            return zapis.odpowiedz_zgody

        def Destroy(self):
            pass

    class Postep:
        def __init__(self, *_a, **_k):
            pass

        def Update(self, *_a):
            return zapis.postep_dalej, False

        def WasCancelled(self):
            return not zapis.postep_dalej

        def Destroy(self):
            pass

        def __bool__(self):
            return True

    class WatekSynchroniczny:
        def __init__(self, target, args=(), daemon=None):
            self._cel, self._args = target, args

        def start(self):
            self._cel(*self._args)

        def is_alive(self):
            return False

    monkeypatch.setattr(wx, "MessageBox", lambda tresc, *a, **k: zapis.komunikaty.append(tresc))
    monkeypatch.setattr(wx, "MessageDialog", Dialog)
    monkeypatch.setattr(wx, "ProgressDialog", Postep)
    monkeypatch.setattr(wx, "CallAfter", lambda f, *a, **k: f(*a, **k))
    monkeypatch.setattr(gp.threading, "Thread", WatekSynchroniczny)
    monkeypatch.setattr(gd, "pokaz_tekst", lambda _r, tytul, tresc: zapis.dlugie.append((tytul, tresc)))
    monkeypatch.setattr(gd, "pokaz_raport_raz", lambda _r: None)

    def odczytaj(klient, sciezka, akapity_stron, strony, **_kw):
        zapis.odczyty.append((sciezka, akapity_stron, strony))
        return [cs.WynikStrony(n, cs.STATUS_OK, f"**Imię:** [[ILLEGIBLE]] strona {n}",
                               znaczniki={"ILLEGIBLE": 1}) for n in strony], None

    monkeypatch.setattr(cs, "odczytaj_strony", odczytaj)

    ramka = wx.Frame(None)
    panel = gp.PoliglotaPanel(ramka)
    panel._client = cl.KlientLLM(cl.PROVIDER_ANTHROPIC, None)
    panel._api_dostepne = True
    try:
        yield panel, zapis
    finally:
        ramka.Destroy()
        app.Destroy()
        i18n.ustaw_jezyk(jezyk_przed)


def _wczytaj(panel, sciezka):
    panel._txt_file.SetValue(str(sciezka))
    panel._on_load(None)


def _mieszany(tmp_path):
    p = tmp_path / "mieszany.pdf"
    _zbuduj_pdf(p, [[("Wstep dokumentu.", 72, 700)], [], [("Koniec dokumentu.", 72, 700)]])
    return p


def test_zgoda_daje_html_ze_skanem_na_swoim_miejscu(srodowisko, tmp_path):
    panel, zapis = srodowisko
    _wczytaj(panel, _mieszany(tmp_path))
    assert len(zapis.zgody) == 1 and "2" in zapis.zgody[0]
    assert "Anthropic (api.anthropic.com)" in zapis.zgody[0]
    assert [o[2] for o in zapis.odczyty] == [[2]]
    assert panel._file_ext == ".html"
    tresc = panel._file_content
    assert tresc.index("Wstep dokumentu.") < tresc.index("strona 2") \
        < tresc.index("Koniec dokumentu.")
    assert "[nieczytelne]" in tresc and "[[ILLEGIBLE]]" not in tresc
    assert len(zapis.dlugie) == 1
    tytul, podsumowanie = zapis.dlugie[0]
    assert "Odczytano z obrazu stron: 1 z 1" in podsumowanie
    assert "nieczytelnych albo zamazanych: 1" in podsumowanie
    assert not panel._btn_load.IsEnabled()        # plik wczytany — jak dotąd


def test_pomin_zostawia_sciezke_txt_bez_modelu(srodowisko, tmp_path):
    panel, zapis = srodowisko
    zapis.odpowiedz_zgody = wx.ID_NO
    _wczytaj(panel, _mieszany(tmp_path))
    assert zapis.odczyty == []
    assert panel._file_ext == ".txt"
    assert panel._file_content == "Wstep dokumentu.\n\nKoniec dokumentu."
    assert any("ich treści nie będzie w wyniku: 2" in k for k in zapis.komunikaty)


@pytest.mark.parametrize("klient, fraza", [
    (cl.KlientLLM(cl.PROVIDER_OPENAI_COMPAT, None, model_override="x"), "openai_compat"),
    (None, "wymaga klucza API"),
])
def test_bez_odczytu_bez_pytania_ale_z_powodem(srodowisko, tmp_path, klient, fraza):
    panel, zapis = srodowisko
    panel._client = klient
    _wczytaj(panel, _mieszany(tmp_path))
    assert zapis.zgody == [] and zapis.odczyty == []
    assert any(fraza in k for k in zapis.komunikaty), zapis.komunikaty


def test_pdf_w_calosci_skanem_dostaje_oferte(srodowisko, tmp_path):
    panel, zapis = srodowisko
    p = tmp_path / "skan.pdf"
    _zbuduj_pdf(p, [[], []])
    _wczytaj(panel, p)
    assert zapis.odczyty[0][1:] == ([[], []], [1, 2])
    assert panel._file_ext == ".html" and "strona 2" in panel._file_content


def test_pdf_w_calosci_skanem_bez_zgody_mowi_jak_dotad(srodowisko, tmp_path):
    panel, zapis = srodowisko
    zapis.odpowiedz_zgody = wx.ID_NO
    p = tmp_path / "skan.pdf"
    _zbuduj_pdf(p, [[], []])
    _wczytaj(panel, p)
    assert panel._file_content == "" and panel._file_ext == ""
    assert len(zapis.komunikaty) == 1


def test_blad_watku_mowi_i_wczytuje_sam_tekst(srodowisko, tmp_path, monkeypatch):
    panel, zapis = srodowisko

    def pada(*_a, **_k):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(cs, "odczytaj_strony", pada)
    monkeypatch.setattr("bledy_ai.zapisz_diagnostyke", lambda *_a: None)
    _wczytaj(panel, _mieszany(tmp_path))
    assert zapis.dlugie[0][0] == "Odczyt stron-skanów nie powiódł się"
    assert "simulated failure" in zapis.dlugie[0][1]
    assert panel._file_ext == ".txt" and "Koniec dokumentu." in panel._file_content


def test_drugi_wczytaj_w_trakcie_odczytu_nic_nie_startuje(srodowisko, tmp_path):
    panel, zapis = srodowisko

    class Zywy:
        def is_alive(self):
            return True

    panel._worker_thread = Zywy()
    _wczytaj(panel, _mieszany(tmp_path))
    assert zapis.zgody == [] and zapis.komunikaty == [] and panel._file_content == ""


def test_nic_nie_odczytano_to_nie_sukces_tylko_sam_tekst(srodowisko, tmp_path, monkeypatch):
    # Audyt 19.14: 401 na pierwszej stronie dawało plik z samymi akapitami
    # błędów „wczytany" komunikatem o sukcesie.
    panel, zapis = srodowisko
    monkeypatch.setattr(cs, "odczytaj_strony", lambda _k, _s, _a, strony, **_kw: (
        [cs.WynikStrony(n, cs.STATUS_BLAD, powod="p", szczegol="AuthenticationError: 401")
         for n in strony], None))
    _wczytaj(panel, _mieszany(tmp_path))
    assert panel._file_ext == ".txt"
    assert panel._file_content == "Wstep dokumentu.\n\nKoniec dokumentu."
    assert "Odczytano z obrazu stron: 0 z 1" in zapis.dlugie[0][1]
    assert "AuthenticationError: 401" in zapis.dlugie[0][1]


def test_detekcja_jezyka_z_tresci_bez_akapitow_pochodzenia(srodowisko, tmp_path, monkeypatch):
    # Audyt 19.14: polskie akapity pochodzenia przestawiały wykryty język
    # krótkiego angielskiego formularza na `pl`.
    import core_poliglota
    panel, zapis = srodowisko
    widziane = []
    monkeypatch.setattr(core_poliglota, "wykryj_jezyk_zrodlowy",
                        lambda tekst, **_kw: widziane.append(tekst) or "pl")
    panel._combo_jezyk.SetSelection(0)
    _wczytaj(panel, _mieszany(tmp_path))
    assert widziane and "odczytany z obrazu" not in widziane[0]
    assert "strona 2" in widziane[0] and "[[ILLEGIBLE]]" not in widziane[0]
    panel._on_clear(None)
    assert panel._tekst_detekcji == ""


def test_timer_anulowania_czyta_dialog_w_trakcie_strony(srodowisko):
    # Audyt 19.14 [WYSOKA]: „Anuluj" czytane tylko w `Update()` na starcie
    # strony przepuszczało następną stronę. Timer odpytuje `WasCancelled`.
    panel, zapis = srodowisko
    panel._postep_skanow = wx.ProgressDialog("t", "m")
    panel._anuluj_skany.clear()
    panel._skany_sprawdz_anulowanie(None)
    assert not panel._anuluj_skany.is_set()
    zapis.postep_dalej = False
    panel._skany_sprawdz_anulowanie(None)
    assert panel._anuluj_skany.is_set()


def test_anuluj_w_oknie_postepu_ustawia_przerwanie(srodowisko):
    panel, zapis = srodowisko
    zapis.postep_dalej = False
    panel._postep_skanow = wx.ProgressDialog("t", "m")
    panel._anuluj_skany.clear()
    panel._skany_postep(1, 3, 5)
    assert panel._anuluj_skany.is_set()


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
