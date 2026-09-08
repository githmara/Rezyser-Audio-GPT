"""
test_cisza_yaml.py - Regresja standardu „zero ciszy" nad plikami YAML (18.28.0).

Standard: plik, ktorego nie umiemy przeczytac ALBO ktory parsuje sie do czegos
innego niz oczekiwany ksztalt (goly skalar, lista, `null` po wykasowaniu
tresci), NIGDY nie wypada bez slowa. W dev-toolu konczy sie to bledem FATALNYM
(`dev_yaml`), w runtime wpisem w rejestrze pominiec (`przepisy_rezysera.
zglos_pominiecie`) albo w rejestrze awarii tlumaczen (`i18n`).

Testy sprawdzaja OBIE strony tego kontraktu na ZYWO (kryterium przez wykonanie,
nie przez czytanie kodu) plus sama bramke `audyt_ciszy`: ostatni test podaje jej
dwa warianty tego samego loadera - cichy i naprawiony - bo bramka, ktora nie
lapie regresji, jest tylko dekoracja, a bramka, ktora zglasza poprawny kod,
zostanie wylaczona po tygodniu.

Wszystko dzieje sie w katalogu tymczasowym; paczki `dictionaries/` sa czytane
tylko do odczytu albo kopiowane.

Uruchom:  .venv/Scripts/python test_cisza_yaml.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import audyt_ciszy
import core_poliglota as cp
import dev_yaml
import opowiesci_ai
import przepisy_rezysera as pr
import refresh_languages
import tlumacz_rdzen

# Trzy ksztalty korzenia, ktore parsuja sie POPRAWNIE, ale nie sa mapa. Kazdy
# powstaje realnie: skalar po skasowaniu wszystkiego oprocz jednej linii, lista
# po wcieciu calego pliku pod myslnik, `null` po wyczyszczeniu tresci.
GOLY_SKALAR = "tylko jedna linijka tekstu bez dwukropka\n"
LISTA = "- pierwszy\n- drugi\n"
PUSTY = "# sam komentarz, zero tresci\n"
ZLA_SKLADNIA = 'etykieta: "niezamkniety cudzyslow\nid: cos\n'


def _plik(katalog, nazwa, tresc):
    p = Path(katalog) / nazwa
    p.write_text(tresc, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# RUNTIME: rejestr pominiec zamiast ciszy
# ---------------------------------------------------------------------------
def test_przepisy_ksztalt_trafia_do_rejestru():
    """Goly skalar w pliku przepisu = wpis `ksztalt`, nie ciche {}."""
    katalog = tempfile.mkdtemp()
    try:
        pr.wyczysc_pominiecia()
        for nazwa, tresc in (("skalar.yaml", GOLY_SKALAR),
                             ("lista.yaml", LISTA),
                             ("pusty.yaml", PUSTY)):
            plik = _plik(katalog, nazwa, tresc)
            assert pr._wczytaj_yaml(str(plik)) == {}, nazwa
        powody = {Path(w.sciezka).name: w for w in pr.pominiete_pliki()}
        assert set(powody) == {"skalar.yaml", "lista.yaml", "pusty.yaml"}, powody
        assert all(w.powod == pr.POWOD_KSZTALT for w in powody.values()), powody
        # Szczegol musi nazywac TYP korzenia - to jedyna informacja, ktora
        # odroznia „plik pusty" od „pliku z jedna linijka".
        assert powody["skalar.yaml"].szczegol == "str", powody["skalar.yaml"]
        assert powody["lista.yaml"].szczegol == "list", powody["lista.yaml"]
        assert powody["pusty.yaml"].szczegol == "NoneType", powody["pusty.yaml"]
    finally:
        pr.wyczysc_pominiecia()
        shutil.rmtree(katalog, ignore_errors=True)


def test_poliglota_ksztalt_trafia_do_rejestru():
    """Ta sama regula w loaderze akcentow/szyfrow Poligloty."""
    katalog = tempfile.mkdtemp()
    try:
        pr.wyczysc_pominiecia()
        plik = _plik(katalog, "finski.yaml", GOLY_SKALAR)
        assert cp._zaladuj_yaml(str(plik)) == {}
        wpisy = pr.pominiete_pliki()
        assert len(wpisy) == 1 and wpisy[0].powod == pr.POWOD_KSZTALT, wpisy
        assert wpisy[0].szczegol == "str", wpisy[0]
    finally:
        pr.wyczysc_pominiecia()
        shutil.rmtree(katalog, ignore_errors=True)


def test_jeden_wpis_na_plik_nie_dwa():
    """Zly ksztalt nie generuje wtornego powodu „brak wymaganych pol"."""
    katalog = tempfile.mkdtemp()
    try:
        pr.wyczysc_pominiecia()
        plik = _plik(katalog, "tryb_cos.yaml", GOLY_SKALAR)
        pr._wczytaj_yaml(str(plik))
        assert pr._zgloszono_blad_parsera(str(plik)) is True
        assert len(pr.pominiete_pliki()) == 1, pr.pominiete_pliki()
    finally:
        pr.wyczysc_pominiecia()
        shutil.rmtree(katalog, ignore_errors=True)


def test_opowiesci_skalar_spada_na_en_bez_crasha():
    """Skalarny przepis Opowiesci: fallback na `en`, wpis w rejestrze, ZERO wyjatku.

    Do v18.27.0 `return dane or {}` oddawalo w tym miejscu STRINGA (goly skalar
    jest prawdziwy), a wolajacy robi na wyniku `.get(...)` - czyli panel
    wywracal sie na AttributeError zamiast siegnac po paczke `en`.
    """
    katalog = Path(tempfile.mkdtemp())
    stare = opowiesci_ai.ROOT_DICT
    try:
        pr.wyczysc_pominiecia()
        (katalog / "pl" / "opowiesci").mkdir(parents=True)
        (katalog / "en" / "opowiesci").mkdir(parents=True)
        _plik(katalog / "pl" / "opowiesci", "baza.yaml", GOLY_SKALAR)
        _plik(katalog / "en" / "opowiesci", "baza.yaml", "prompt: from en pack\n")
        opowiesci_ai.ROOT_DICT = katalog
        opowiesci_ai._zaladuj_przepis.cache_clear()
        wynik = opowiesci_ai._zaladuj_przepis("pl", "baza")
        assert isinstance(wynik, dict), type(wynik)
        assert wynik.get("prompt") == "from en pack", wynik
        wpisy = [w for w in pr.pominiete_pliki() if w.powod == pr.POWOD_KSZTALT]
        assert len(wpisy) == 1 and wpisy[0].szczegol == "str", pr.pominiete_pliki()
    finally:
        opowiesci_ai.ROOT_DICT = stare
        opowiesci_ai._zaladuj_przepis.cache_clear()
        pr.wyczysc_pominiecia()
        shutil.rmtree(katalog, ignore_errors=True)


def test_konwerter_zepsuta_paczka_zglasza_powod():
    """Zepsuty `ui.yaml` obcej paczki: konwerter traci slowa naglowkow GLOSNO."""
    import wx

    app = wx.App(False)
    try:
        import gui_konwerter

        katalog = Path(tempfile.mkdtemp())
        stare = gui_konwerter._DICTIONARIES_DIR
        try:
            pr.wyczysc_pominiecia()
            for kod, tresc in (("pl", "konwerter:\n  naglowki_rozdzialow: [Rozdzial]\n"),
                               ("xx", ZLA_SKLADNIA),
                               ("yy", GOLY_SKALAR)):
                (katalog / kod / "gui").mkdir(parents=True)
                _plik(katalog / kod / "gui", "ui.yaml", tresc)
            # Zly zapis znakowy: do audytu v18.28.0 wywracal KONWERSJE, bo
            # `UnicodeDecodeError` nie jest podklasa `OSError`.
            (katalog / "zz" / "gui").mkdir(parents=True)
            _plik_ansi(katalog / "zz" / "gui", "ui.yaml")
            gui_konwerter._DICTIONARIES_DIR = katalog
            gui_konwerter._slowa_kluczowe_konwertera.cache_clear()
            zbiory = gui_konwerter._slowa_kluczowe_konwertera()
            assert "Rozdzial" in zbiory["rozdzial"], zbiory
            powody = {Path(w.sciezka).parent.parent.name: w.powod
                      for w in pr.pominiete_pliki()}
            assert powody == {"xx": pr.POWOD_PARSE, "yy": pr.POWOD_KSZTALT,
                              "zz": pr.POWOD_PARSE}, powody
        finally:
            gui_konwerter._DICTIONARIES_DIR = stare
            gui_konwerter._slowa_kluczowe_konwertera.cache_clear()
            pr.wyczysc_pominiecia()
            shutil.rmtree(katalog, ignore_errors=True)
    finally:
        app.Destroy()


def test_szablony_managera_zglaszaja_powod():
    """Loader szablonow Managera Regul melduje zepsuty plik paczki."""
    import manager_regul_szablony as mrs

    katalog = tempfile.mkdtemp()
    try:
        pr.wyczysc_pominiecia()
        assert mrs._wczytaj_yaml(_plik(katalog, "podstawy.yaml", ZLA_SKLADNIA)) == {}
        assert mrs._wczytaj_yaml(_plik(katalog, "inne.yaml", LISTA)) == {}
        powody = sorted(w.powod for w in pr.pominiete_pliki())
        assert powody == [pr.POWOD_KSZTALT, pr.POWOD_PARSE], powody
    finally:
        pr.wyczysc_pominiecia()
        shutil.rmtree(katalog, ignore_errors=True)


def test_klucz_i18n_dla_nowego_powodu_istnieje_w_kazdej_paczce():
    """Kod powodu bez klucza `diag.powod.*` daloby userowi goly identyfikator."""
    import i18n

    dict_dir = Path(__file__).parent / "dictionaries"
    braki = []
    for paczka in sorted(p for p in dict_dir.iterdir() if p.is_dir()):
        if not (paczka / "gui" / "ui.yaml").is_file():
            continue
        i18n._CACHE.pop(paczka.name, None)
        dane = i18n.zaladuj(paczka.name)
        wartosc = ((dane.get("diag") or {}).get("powod") or {}).get(pr.POWOD_KSZTALT)
        if not isinstance(wartosc, str) or not wartosc.strip():
            braki.append(paczka.name)
    assert not braki, f"brak `diag.powod.{pr.POWOD_KSZTALT}` w paczkach: {braki}"


# ---------------------------------------------------------------------------
# DEV-TOOLE: blad fatalny zamiast ciszy
# ---------------------------------------------------------------------------
def test_dev_yaml_pada_na_ksztalcie_i_skladni():
    katalog = tempfile.mkdtemp()
    try:
        for nazwa, tresc in (("skalar.yaml", GOLY_SKALAR),
                             ("lista.yaml", LISTA),
                             ("pusty.yaml", PUSTY),
                             ("zla.yaml", ZLA_SKLADNIA)):
            plik = _plik(katalog, nazwa, tresc)
            for funkcja in (dev_yaml.wczytaj_lub_padnij, dev_yaml.wczytaj_jesli_jest):
                try:
                    funkcja(plik, narzedzie="test")
                except SystemExit as exc:
                    assert str(plik) in str(exc), (nazwa, exc)
                else:
                    raise AssertionError(f"{nazwa}: brak SystemExit ({funkcja.__name__})")
        # Poprawny plik przechodzi, brak pliku to NIE awaria dla `_jesli_jest`.
        dobry = _plik(katalog, "dobry.yaml", "id: cos\n")
        assert dev_yaml.wczytaj_lub_padnij(dobry, narzedzie="test") == {"id": "cos"}
        assert dev_yaml.wczytaj_jesli_jest(
            Path(katalog) / "nie_ma.yaml", narzedzie="test") is None
        try:
            dev_yaml.wczytaj_lub_padnij(Path(katalog) / "nie_ma.yaml", narzedzie="test")
        except SystemExit:
            pass
        else:
            raise AssertionError("a missing file must be fatal for `wczytaj_lub_padnij`")
    finally:
        shutil.rmtree(katalog, ignore_errors=True)


def test_refresh_nie_kasuje_zepsutego_rejestru():
    """Nieczytelny rejestr = STOP, nie regeneracja z utrata recznych nazw."""
    katalog = Path(tempfile.mkdtemp())
    stary = refresh_languages.REJESTR
    try:
        zepsuty = _plik(katalog, "jezyki_docelowe.yaml", ZLA_SKLADNIA)
        refresh_languages.REJESTR = zepsuty
        try:
            refresh_languages.wczytaj_rejestr()
        except SystemExit as exc:
            assert "jezyki_docelowe.yaml" in str(exc), exc
        else:
            raise AssertionError("a broken registry passed without a word")
        # Plik zostaje NIETKNIETY - to jest sens tego stopu.
        assert zepsuty.read_text(encoding="utf-8") == ZLA_SKLADNIA
    finally:
        refresh_languages.REJESTR = stary
        shutil.rmtree(katalog, ignore_errors=True)


def test_rdzen_nie_zaweza_zasiegu_po_cichu():
    """Zepsuty rejestr NIE moze cofnac rodziny do wbudowanych osmiu jezykow."""
    katalog = Path(tempfile.mkdtemp())
    try:
        _plik(katalog, "jezyki_docelowe.yaml", ZLA_SKLADNIA)
        try:
            tlumacz_rdzen.wczytaj_mape_jezykow(katalog)
        except SystemExit as exc:
            assert "jezyki_docelowe.yaml" in str(exc), exc
        else:
            raise AssertionError("a broken registry silently fell back to 8 languages")
        # Rejestr obecny, ale bez celow (sam jezyk zrodlowy) tez jest bledem.
        _plik(katalog, "jezyki_docelowe.yaml", "pl: polski\n")
        try:
            tlumacz_rdzen.wczytaj_mape_jezykow(katalog)
        except SystemExit:
            pass
        else:
            raise AssertionError("a registry with no target languages passed")
        # BRAK pliku zostaje stanem obslugiwanym (swiezy checkout) - z fallbackiem.
        (katalog / "jezyki_docelowe.yaml").unlink()
        mapa = tlumacz_rdzen.wczytaj_mape_jezykow(katalog)
        assert mapa == dict(tlumacz_rdzen.FALLBACK_JEZYKOW), mapa
    finally:
        shutil.rmtree(katalog, ignore_errors=True)


# ---------------------------------------------------------------------------
# BRAMKA: lapie regresje, milczy o kodzie naprawionym
# ---------------------------------------------------------------------------
CICHY_LOADER = '''
import yaml

def wczytaj(plik):
    try:
        dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dane if isinstance(dane, dict) else {}

def wczytaj_or(plik):
    dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
    return dane or {}
'''

NAPRAWIONY_LOADER = '''
import yaml

def wczytaj(plik):
    try:
        dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"cannot read {plik}: {exc}")
    if not isinstance(dane, dict):
        raise SystemExit(f"cannot read {plik}: root is {type(dane).__name__}")
    return dane

def wczytaj_zgloszeniem(plik):
    try:
        dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
    except Exception as exc:
        zglos_pominiecie(str(plik), "parse", str(exc))
        return {}
    if not isinstance(dane, dict):
        zglos_pominiecie(str(plik), "ksztalt", type(dane).__name__)
        return {}
    return dane
'''


def test_bramka_lapie_cisze_i_milczy_o_naprawie():
    katalog = Path(tempfile.mkdtemp())
    try:
        cichy = _plik(katalog, "cichy_modul.py", CICHY_LOADER)
        klasy = sorted({z.klasa for z in audyt_ciszy.skanuj_plik(cichy)})
        assert klasy == ["except-cichy", "ksztalt-cichy", "or-domyslny"], klasy

        naprawiony = _plik(katalog, "naprawiony_modul.py", NAPRAWIONY_LOADER)
        assert audyt_ciszy.skanuj_plik(naprawiony) == [], \
            audyt_ciszy.skanuj_plik(naprawiony)
    finally:
        shutil.rmtree(katalog, ignore_errors=True)


def test_bramka_nie_sciga_kontroli_pol():
    """Kontrola POLA (nie korzenia) to nie pominiecie pliku - zero trafien.

    Pierwsza wersja bramki zglaszala `isinstance(etykieta, str)` i produkowala
    30 trafien tam, gdzie realnych bylo 20; zawezenie do zmiennej z korzeniem
    pliku bylo pomiarem, nie przeczuciem.
    """
    katalog = Path(tempfile.mkdtemp())
    try:
        modul = _plik(katalog, "pola_modul.py", '''
import yaml

def wczytaj(plik):
    dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
    if not isinstance(dane, dict):
        raise SystemExit("root is not a mapping")
    etykieta = dane.get("etykieta")
    if isinstance(etykieta, str) and etykieta.strip():
        return etykieta.strip()
    sekcja = dane.get("sekcja")
    if not isinstance(sekcja, dict):
        return ""
    return str(sekcja.get("id") or "")
''')
        assert audyt_ciszy.skanuj_plik(modul) == [], audyt_ciszy.skanuj_plik(modul)
    finally:
        shutil.rmtree(katalog, ignore_errors=True)


# Trzy wzorce z audytu v18.28.0: dwa przepuszczane przez pierwsza wersje bramki
# i jeden zglaszany przez nia FALSZYWIE. Czwarta funkcja jest kontrola dodatnia:
# kod PO instrukcji `if` liczy sie jako sciezka porazki tylko wtedy, gdy galaz
# pozytywna konczy przeplyw - inaczej jest wspolny dla obu sciezek.
WZORCE_Z_AUDYTU = '''
import contextlib
import yaml
import wx


def fall_through(plik):
    dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
    if isinstance(dane, dict):
        return dane
    return {}


def tlumik(plik):
    dane = None
    with contextlib.suppress(OSError, yaml.YAMLError):
        dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
    return dane


def handler_z_messageboxem(plik):
    try:
        dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        wx.MessageBox(f"blad: {exc}")
        return {}
    if not isinstance(dane, dict):
        wx.MessageBox("plik nie jest mapa")
        return {}
    return dane


def wspolny_kod_po_if(plik):
    dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
    if isinstance(dane, dict):
        licznik = len(dane)
    else:
        raise SystemExit("root is not a mapping")
    return licznik
'''


def test_bramka_lapie_wzorce_z_audytu():
    """Fall-through i `contextlib.suppress` = trafienia; `wx.MessageBox` = glos."""
    katalog = Path(tempfile.mkdtemp())
    try:
        plik = _plik(katalog, "wzorce_modul.py", WZORCE_Z_AUDYTU)
        wyniki = audyt_ciszy.skanuj_plik(plik)
        zakresy = {(z.zakres, z.klasa) for z in wyniki}
        # Ta sama semantyka co `dane if isinstance(dane, dict) else {}`, tylko
        # zapisana instrukcja `if` bez gałęzi `else`.
        assert ("fall_through", "ksztalt-cichy") in zakresy, wyniki
        # Polkniecie wyjatku bez `except` - `ast.Try` w ogole nie istnieje.
        assert ("tlumik", "except-cichy") in zakresy, wyniki
        # Handler, ktory MOWI uzytkownikowi kanalem z Konstytucji, nie jest cichy.
        assert not [z for z in wyniki if z.zakres == "handler_z_messageboxem"], wyniki
        # Kod wspolny dla obu sciezek nie jest galezia porazki.
        assert not [z for z in wyniki if z.zakres == "wspolny_kod_po_if"], wyniki
    finally:
        shutil.rmtree(katalog, ignore_errors=True)


# ---------------------------------------------------------------------------
# ZLY ZAPIS ZNAKOWY (UnicodeDecodeError) - podklasa ValueError, nie OSError
# ---------------------------------------------------------------------------
# Plik reguly zapisany w Notatniku jako ANSI zamiast UTF-8 to najzwyklejszy blad
# uzytkownika, a `except OSError` go NIE lapie. Audyt v18.28.0 znalazl te klase
# w czterech miejscach naraz - w tym w dwoch napisanych tym samym wydaniem.
ANSI_YAML = "etykieta: zażółć gęślą jaźń\n".encode("cp1250")


def _plik_ansi(katalog, nazwa):
    p = Path(katalog) / nazwa
    p.write_bytes(ANSI_YAML)
    return p


def test_dev_yaml_pada_na_zlym_zapisie_znakowym():
    katalog = tempfile.mkdtemp()
    try:
        plik = _plik_ansi(katalog, "podstawy.yaml")
        try:
            dev_yaml.wczytaj_lub_padnij(plik, narzedzie="test")
        except SystemExit as exc:
            assert "unreadable" in str(exc), exc
        else:
            raise AssertionError("a non-UTF-8 file passed the loader")
    finally:
        shutil.rmtree(katalog, ignore_errors=True)


def test_i18n_zly_zapis_znakowy_trafia_do_rejestru_awarii():
    """Nie-UTF-8 `ui.yaml` NIE moze wywracac startu aplikacji."""
    import i18n

    katalog = Path(tempfile.mkdtemp())
    stare = i18n._DICTIONARIES_DIR
    try:
        (katalog / "xx" / "gui").mkdir(parents=True)
        _plik_ansi(katalog / "xx" / "gui", "ui.yaml")
        i18n._DICTIONARIES_DIR = katalog
        i18n._CACHE.pop("xx", None)
        assert i18n._wczytaj_yaml("xx") == {}
        awarie = [w for w in i18n.awarie_ui() if w.jezyk == "xx"]
        assert len(awarie) == 1 and awarie[0].powod == i18n.POWOD_ODCZYT, awarie
    finally:
        i18n._DICTIONARIES_DIR = stare
        i18n._CACHE.pop("xx", None)
        i18n._AWARIE.pop("xx", None)
        shutil.rmtree(katalog, ignore_errors=True)


def test_szablony_managera_milcza_o_braku_pliku():
    """Brak pliku swiezej paczki NIE jest bledem skladni - to normalny stan.

    Kreator nowego jezyka bazowego czyta dane paczki, ktorej jeszcze nie ma;
    wpis „niepoprawna skladnia YAML" o nieistniejacym pliku byl dla uzytkownika
    komunikatem wprost falszywym (audyt v18.28.0).
    """
    import manager_regul_szablony as mrs

    katalog = Path(tempfile.mkdtemp())
    try:
        pr.wyczysc_pominiecia()
        assert mrs._wczytaj_yaml(katalog / "nie_ma.yaml") == {}
        assert pr.pominiete_pliki() == (), pr.pominiete_pliki()
        # Ale plik, ktory JEST, tylko w zlym zapisie znakowym, juz raportujemy.
        assert mrs._wczytaj_yaml(_plik_ansi(katalog, "podstawy.yaml")) == {}
        wpisy = pr.pominiete_pliki()
        assert len(wpisy) == 1 and wpisy[0].powod == pr.POWOD_PARSE, wpisy
    finally:
        pr.wyczysc_pominiecia()
        shutil.rmtree(katalog, ignore_errors=True)


def test_baza_rezysera_bez_pliku_nie_zglasza_powodu():
    """Paczka bez `rezyser/baza.yaml` to stan przewidziany, nie awaria."""
    stare = pr.DICTIONARIES_DIR
    katalog = Path(tempfile.mkdtemp())
    try:
        pr.wyczysc_pominiecia()
        pr._CACHE_BAZA.clear()
        (katalog / "xx" / pr.FOLDER_REZYSER).mkdir(parents=True)
        pr.DICTIONARIES_DIR = str(katalog)
        assert pr._zaladuj_baze("xx") == {}
        assert pr.pominiete_pliki() == (), pr.pominiete_pliki()
    finally:
        pr.DICTIONARIES_DIR = stare
        pr._CACHE_BAZA.clear()
        pr.wyczysc_pominiecia()
        shutil.rmtree(katalog, ignore_errors=True)


def test_drzewo_jest_czyste():
    """Cale repo bez ani jednego cichego pominiecia (baseline pusty)."""
    aktualne = audyt_ciszy.zbierz()
    assert aktualne == {}, aktualne


if __name__ == "__main__":
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
