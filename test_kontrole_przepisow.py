"""
test_kontrole_przepisow.py - dowod bojowy kontroli loadera Rezysera (v19.7).

Do v19.6 loader egzekwowal `kategoria`, `zakres`, `rola` i `sufiks_pliku_wyniku`,
a pozostale pola sterujace silnikiem bral takimi, jakie sa. Literowka w nich nie
byla cicha „troche" - byla cicha CALKIEM: plik wczytywal sie bez ani jednego
zgloszenia, a tryb pracowal inaczej, niz mowil jego wlasny YAML. Zmierzone przed
zmiana:

  * `struktura: akty_scen` - markery pamieci splaszczaly sie z zagniezdzenia
    akt->scena do plaskiej listy naglowkow, czyli Rezyser „widzial rozdzialy"
    w projekcie Skryptu, i to wylacznie z powodu jednej zgubionej litery;
  * `regex_podzial_rozdzialow` PUSTY - `re.split("", tekst)` tnie miedzy kazdym
    znakiem: 636 znakow dalo 638 fragmentow, czyli 319 platnych wywolan LLM po
    jednym znaku;
  * ten sam wzorzec BEZ GRUPY przechwytujacej - `re.split` zwraca same tresci,
    a `rezyser_ai.nadaj_tytuly_rozdzialom` czyta nieparzyste pozycje jak
    naglowki, wiec tytuly powstaja dla przesunietego fragmentu;
  * `max_dlugosc_probki` pominiete - `tresc[:0]` to pusty lancuch, wiec model
    dostawal sam naglowek i wymyslal tytul rozdzialu, ktorego nie przeczytal.

Zielony przebieg na czystym repo nie dowodzi tu niczego (tak samo zielona
bylaby kontrola, ktorej nie ma), wiec kazda klasa dostaje WSTRZYKNIETY defekt
i musi zostac zlapana po kodzie powodu. Kontrole odwrotne pilnuja drugiej
polowy umowy: wartosci legalne, shimy wstecznej zgodnosci, niewypelniony szkic
kreatora (kanon v19.4: szkic ma prawo zyc) i wszystkie dziewiec shippowanych
paczek musza przechodzic bez zastrzezen.

Uruchom:  .venv/Scripts/python -m pytest test_kontrole_przepisow.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_kontrole_przepisow.py
"""

import inspect
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import przepisy_rezysera as pr

_DICT = Path(__file__).parent / "dictionaries"


def _zaladuj(**pola):
    """Buduje przepis z pol nadpisujacych minimalny, poprawny tryb.

    Zwraca `(przepis, powody)` - `przepis` jest `None`, gdy loader pominal plik.
    """
    pr.wyczysc_pominiecia()
    dane = {"id": "zzsonda", "etykieta": "Zzsonda", "kategoria": pr.KATEGORIA_TRYB}
    dane.update(pola)
    przepis = pr._yaml_to_przepis(dane, "zzsonda.yaml")
    return przepis, pr.pominiete_pliki()


def _postprodukcja(**pola):
    dane = {"kategoria": pr.KATEGORIA_POSTPROD, "zakres": pr.ZAKRES_PER_ROZDZIAL,
            "regex_podzial_rozdzialow": r"(?i)\n*(Rozdzial \d+)\n*"}
    dane.update(pola)
    return _zaladuj(**dane)


# ---------------------------------------------------------------------------
# Wstrzykniete defekty - kazdy MUSI pominac plik z kodem POWOD_WARTOSC
# ---------------------------------------------------------------------------
def test_literowka_struktury_pomija_plik():
    przepis, powody = _zaladuj(struktura="akty_scen")
    assert przepis is None, "tryb z nieznana `struktura` wszedl do aplikacji"
    assert [w.powod for w in powody] == [pr.POWOD_WARTOSC], powody
    # Szczegol musi NAZWAC pole - uzytkownik dostaje go zamiast tlumaczenia,
    # a raport inaczej nie mowi, ktore z kilkunastu pol pliku poprawic.
    assert "struktura" in powody[0].szczegol, powody[0].szczegol
    assert "akty_sceny" in powody[0].szczegol, "brak zbioru dozwolonych wartosci"


def test_literowka_formatu_wyjscia_pomija_plik():
    przepis, powody = _zaladuj(format_wyjscia="skrypt_jsno")
    assert przepis is None, "tryb z nieznanym `format_wyjscia` wszedl do aplikacji"
    assert [w.powod for w in powody] == [pr.POWOD_WARTOSC], powody
    assert "format_wyjscia" in powody[0].szczegol, powody[0].szczegol


def test_temperatura_poza_zakresem_pomija_plik():
    # `85` zamiast `0.85` to jeden zgubiony znak, a API odpowiada 400 przy
    # KAZDYM wywolaniu tego przepisu - uzytkownik widzi blad sieci, nie pliku.
    przepis, powody = _zaladuj(temperatura=85)
    assert przepis is None, "przepis z temperatura 85 wszedl do aplikacji"
    assert [w.powod for w in powody] == [pr.POWOD_WARTOSC], powody
    assert "temperatura" in powody[0].szczegol, powody[0].szczegol


def test_wzorzec_rozdzialow_pusty_pomija_plik():
    przepis, powody = _postprodukcja(regex_podzial_rozdzialow="")
    assert przepis is None, "postprodukcja per_rozdzial bez wzorca wszedla do GUI"
    assert [w.powod for w in powody] == [pr.POWOD_WARTOSC], powody


def test_wzorzec_rozdzialow_bez_grupy_pomija_plik():
    przepis, powody = _postprodukcja(regex_podzial_rozdzialow=r"Rozdzial \d+")
    assert przepis is None, "wzorzec bez grupy przechwytujacej wszedl do GUI"
    assert [w.powod for w in powody] == [pr.POWOD_WARTOSC], powody


def test_wzorzec_rozdzialow_niekompilowalny_pomija_plik():
    przepis, powody = _postprodukcja(regex_podzial_rozdzialow="(Rozdzial")
    assert przepis is None, "niekompilowalny wzorzec wszedl do GUI"
    assert [w.powod for w in powody] == [pr.POWOD_WARTOSC], powody
    assert "re.error" in powody[0].szczegol, powody[0].szczegol


@pytest.mark.parametrize("wzor", [
    r"(?i)\n*(Prolog|Rozdzial \d+|Epilog|)\n*",   # wiszacy | w liscie nazw
    r"(?i)\n*(Rozdzial \d+)?\n*",                 # caly wzorzec opcjonalny
    "()",                                          # grupa pusta
])
def test_wzorzec_dopasowujacy_pustke_pomija_plik(wzor):
    """„Pusty" to za waskie pytanie - tnie `re.split`, nie tekst pola (v19.7 audyt)."""
    przepis, powody = _postprodukcja(regex_podzial_rozdzialow=wzor)
    assert przepis is None, f"wzorzec matchujacy pustke wszedl do GUI: {wzor!r}"
    assert [w.powod for w in powody] == [pr.POWOD_WARTOSC], powody


def test_wzorzec_z_dwiema_grupami_pomija_plik():
    """Obie strony umowy musza liczyc JEDNA enumeracja (kanon v19.2.0)."""
    przepis, powody = _postprodukcja(
        regex_podzial_rozdzialow=r"(?i)\n*(Prolog|Rozdzial (\d+)|Epilog)\n*")
    assert przepis is None, "wzorzec z druga grupa wszedl do GUI"
    assert [w.powod for w in powody] == [pr.POWOD_WARTOSC], powody
    assert "groups=2 ≠ 1" in powody[0].szczegol, powody[0].szczegol


def test_powod_bledu_wzorca_nazywa_kazdy_ksztalt():
    """Piec ksztaltow usterki ma ROZNE opisy - jeden komunikat nie uczy niczego."""
    opisy = {
        "pusty": pr._blad_wzorca_rozdzialow(""),
        "zly": pr._blad_wzorca_rozdzialow("(Rozdzial"),
        "bez_grupy": pr._blad_wzorca_rozdzialow(r"Rozdzial \d+"),
        "dwie_grupy": pr._blad_wzorca_rozdzialow(r"(Rozdzial (\d+))"),
        "pustka": pr._blad_wzorca_rozdzialow(r"(Rozdzial \d+)?"),
    }
    assert all(opisy.values()), opisy
    assert len(set(opisy.values())) == 5, opisy
    assert pr._blad_wzorca_rozdzialow(r"(Rozdzial \d+)") == ""


def test_werdykt_wzorca_nie_niesie_prozy():
    """Ten tekst czyta user w DZIEWIECIU jezykach, wiec nie ma w nim zdania.

    `szczegol` pominiecia idzie 1:1 do rejestru „Pominiete reguly"
    (`gui_diagnostyka` -> `t("diag.szczegol", …)`), a klase tlumaczy klucz
    `diag.powod.wartosc`. Sasiednie pola (`struktura`, `zakres`, `rola`,
    `sufiks_pliku_wyniku`) sa symboliczne wlasnie dlatego - ta kontrola przez
    caly cykl v19.7 byla jedynym wyjatkiem i wstrzykiwala tam angielska proze.
    Wyjatkiem zostaje `re.error`, bo komunikat pisze Python, nie my.
    """
    for wzor in ("", r"Rozdzial \d+", r"(Rozdzial (\d+))", r"(Rozdzial \d+)?"):
        werdykt = pr._blad_wzorca_rozdzialow(wzor)
        assert werdykt, f"brak werdyktu dla {wzor!r}"
        slowa = re.findall(r"[A-Za-z]{2,}", werdykt)
        assert len(slowa) <= 2, (wzor, werdykt)
        assert "—" not in werdykt, werdykt


# ---------------------------------------------------------------------------
# Dlaczego brak grupy przechwytujacej jest usterka, a nie gustem
# ---------------------------------------------------------------------------
def test_split_bez_grupy_gubi_naglowki():
    """Powod kontroli, zmierzony na `re.split`, a nie zadeklarowany w komentarzu.

    `rezyser_ai.nadaj_tytuly_rozdzialom` czyta `fragmenty[1::2]` jak naglowki,
    a `fragmenty[2::2]` jak tresci. Ta umowa trzyma sie WYLACZNIE wtedy, gdy
    wzorzec ma grupe - inaczej `re.split` naglowki wyrzuca.
    """
    tekst = "Rozdzial 1\ntresc pierwsza\nRozdzial 2\ntresc druga\n"
    z_grupa = re.split(r"(?i)\n*(Rozdzial \d+)\n*", tekst)
    bez_grupy = re.split(r"(?i)\n*Rozdzial \d+\n*", tekst)
    assert z_grupa[1::2] == ["Rozdzial 1", "Rozdzial 2"], z_grupa
    assert "Rozdzial 1" not in bez_grupy, bez_grupy
    # Pusty wzorzec: kazdy znak staje sie osobnym, platnym „rozdzialem".
    assert len(re.split("", tekst)) == len(tekst) + 2


def test_split_dopasowujacy_pustke_kosztuje_liniowo():
    """Koszt wisi na DLUGOSCI tekstu, nie na liczbie rozdzialow - stad bramka.

    Wzorzec z wiszacym `|` kompiluje sie, ma grupe i przechodzil trzy kontrole
    z v19.7. `re.split` tnie wtedy miedzy kazdym znakiem, a iteracja tytulow
    czyta `fragmenty[1::2]`, wiec liczba PLATNYCH wywolan rosnie razem z plikiem
    - i nie ma jej jak przerwac (postprodukcja nie ma przycisku „Przerwij").
    """
    tekst = "Rozdzial 1\ntresc pierwsza\nRozdzial 2\ntresc druga\n"
    zdrowy = re.split(r"(?i)\n*(Rozdzial \d+)\n*", tekst)
    chory = re.split(r"(?i)\n*(Rozdzial \d+|)\n*", tekst)
    assert len(zdrowy[1::2]) == 2, zdrowy
    assert len(chory[1::2]) > len(tekst) // 2, len(chory[1::2])
    assert pr._blad_wzorca_rozdzialow(r"(?i)\n*(Rozdzial \d+|)\n*") != ""


def test_split_z_dwiema_grupami_przesuwa_dane():
    """Krok `re.split` to `1 + liczba_grup`, a petla tytulow chodzi krokiem 2.

    Rozjazd nie podnosi wyjatku - przesuwa dane: jako „naglowki" ida tresci
    rozdzialow i gole numery, a przebieg jest normalnie platny. Gdy druga grupa
    nie uczestniczy w dopasowaniu, `re.split` wstawia `None`.
    """
    tekst = "Rozdzial 1\ntresc pierwsza\nRozdzial 2\ntresc druga\n"
    dwie = re.split(r"(?i)\n*(Rozdzial (\d+))\n*", tekst)
    assert dwie[1::2] != ["Rozdzial 1", "Rozdzial 2"], dwie
    z_alternatywa = re.split(r"(?i)\n*(Prolog|Rozdzial (\d+))\n*", "Prolog\ntresc\n")
    assert None in z_alternatywa, z_alternatywa


# ---------------------------------------------------------------------------
# Kontrole odwrotne - co MUSI przejsc
# ---------------------------------------------------------------------------
def test_kazda_legalna_kombinacja_przechodzi():
    for struktura in pr.STRUKTURY:
        for format_wyjscia in pr.FORMATY_WYJSCIA:
            przepis, powody = _zaladuj(struktura=struktura,
                                       format_wyjscia=format_wyjscia)
            assert przepis is not None, (struktura, format_wyjscia, powody)
            assert not powody, (struktura, format_wyjscia, powody)


def test_granice_temperatury_sa_legalne():
    for wartosc in (pr.TEMPERATURA_MIN, 0.85, pr.TEMPERATURA_MAX):
        przepis, powody = _zaladuj(temperatura=wartosc)
        assert przepis is not None, (wartosc, powody)


def test_shimy_legacy_daja_wartosci_legalne():
    """Shim wstecznej zgodnosci nie moze pomijac plikow, ktore ma ratowac.

    Wartosc spoza zbioru w mapie legacy zabilaby KAZDY plik paczki sprzed pola -
    dokladnie te, dla ktorych shim istnieje.
    """
    assert set(pr._STRUKTURA_LEGACY.values()) <= set(pr.STRUKTURY)
    assert set(pr._ZAKRES_LEGACY.values()) <= set(pr.ZAKRESY_DOZWOLONE)


def test_postprodukcja_nie_umiera_na_polach_trybu():
    """`struktura`/`format_wyjscia` postprodukcji silnik IGNORUJE.

    Pomijanie dzialajacego narzedzia za martwe pole byloby halasem, nie
    kontrola - a halasliwa bramka uczy uzytkownika ignorowac raport.
    """
    przepis, powody = _postprodukcja(struktura="akty_scen",
                                     format_wyjscia="skrypt_jsno")
    assert przepis is not None, powody
    assert not powody, powody


def test_szkic_kreatora_zostaje_zywy():
    """Niewypelniony szablon ma marker `<FILL ...>` i wlasny kanal (POWOD_SZKIC).

    Marker kompiluje sie jako regex i ma zero grup, wiec bez wyjatku kontrola
    wzorca zabilaby plik, o ktorym kanon v19.4 mowi, ze ma prawo zyc.
    """
    przepis, powody = _postprodukcja(
        regex_podzial_rozdzialow="<FILL IN: regex matching chapter headers>")
    assert przepis is not None, powody
    assert not powody, powody


def test_pusta_probka_dostaje_wartosc_domyslna():
    przepis, _ = _postprodukcja()
    assert przepis.max_dlugosc_probki == pr.MAX_DLUGOSC_PROBKI_DOMYSLNA
    jawna, _ = _postprodukcja(max_dlugosc_probki=1234)
    assert jawna.max_dlugosc_probki == 1234
    # Zakres `calosc` probki nie czyta - nie wmawiamy mu limitu, ktorego nie ma.
    calosc, _ = _zaladuj(kategoria=pr.KATEGORIA_POSTPROD, zakres=pr.ZAKRES_CALOSC)
    assert calosc.max_dlugosc_probki == 0


def test_wszystkie_shippowane_paczki_przechodza():
    """Kontrola za ostra jest tym samym bledem, co jej brak - tylko glosniejszym."""
    pr.wyczysc_pominiecia()
    pr.wyczysc_cache()
    kody = sorted(p.name for p in _DICT.iterdir()
                  if p.is_dir() and (p / "rezyser").is_dir())
    for kod in kody:
        assert pr.lista_trybow(kod), f"{kod}: zero trybow"
        assert pr.lista_postprodukcji(kod), f"{kod}: zero postprodukcji"
    zastrzezenia = [(w.sciezka, w.powod, w.szczegol) for w in pr.pominiete_pliki()]
    assert not zastrzezenia, zastrzezenia


# ---------------------------------------------------------------------------
# 4. Kontrola bez odbiorcy to polowa roboty (v19.7 runda 4)
# ---------------------------------------------------------------------------
# Loader ma racje od etapu 8, ale mowi ja do rejestru — a rejestr czyta ten,
# kto zada pytanie. W Managerze Regul pyta przycisk „Odswiez" i do v19.7 pytal
# o paczke JEZYKA INTERFEJSU, podczas gdy autor pracuje w paczce z filtra
# drzewa. Zmierzone: UI `pl`, literowka w `de` → „brak zastrzezen".
_ZLA_STRUKTURA = ("kategoria: tryb", "kategoria: tryb\nstruktura: rozdzialty")


def _paczki_probne(katalog: Path, *kody: str) -> None:
    """Kopia realnych trybow dwoch paczek do katalogu tymczasowego."""
    for kod in kody:
        (katalog / kod / "rezyser").mkdir(parents=True)
        for plik in ("tryb_skrypt.yaml", "tryb_audiobook.yaml"):
            shutil.copy(_DICT / kod / "rezyser" / plik,
                        katalog / kod / "rezyser" / plik)


def _zepsuj(sciezka: Path) -> None:
    sciezka.write_text(sciezka.read_text(encoding="utf-8").replace(*_ZLA_STRUKTURA, 1),
                       encoding="utf-8")


@pytest.fixture()
def paczki_tymczasowe(tmp_path, monkeypatch):
    """Podmienia `dictionaries/` w obu loaderach na kopie robocza.

    SPRZATANIE OBEJMUJE CACHE, nie tylko sciezke. `monkeypatch` cofa stala, ale
    loadery trzymaja juz WCZYTANA tresc z katalogu tymczasowego — bez czyszczenia
    kolejne testy w tej samej sesji dostawaly dwie paczki zamiast dziewieciu
    (zmierzone: 11 czerwonych plikow po pierwszej wersji tej fikstury).
    """
    import core_poliglota as cp
    import gui_diagnostyka as gd
    import i18n

    jezyk_pierwotny = i18n.aktualny_jezyk()
    katalog = tmp_path / "dictionaries"
    _paczki_probne(katalog, "pl", "de")
    monkeypatch.setattr(pr, "DICTIONARIES_DIR", str(katalog))
    monkeypatch.setattr(cp, "DICTIONARIES_DIR", str(katalog))
    yield katalog
    monkeypatch.undo()
    i18n.ustaw_jezyk(jezyk_pierwotny)
    gd._swiezy_start()
    pr.wyczysc_pominiecia()


def test_skan_po_jezyku_ui_nie_widzi_paczki_z_drzewa(paczki_tymczasowe):
    """Defekt wstrzykniety: literowka w `de`, interfejs po polsku."""
    import gui_diagnostyka as gd
    import i18n

    _zepsuj(paczki_tymczasowe / "de" / "rezyser" / "tryb_audiobook.yaml")
    i18n.ustaw_jezyk("pl")
    assert gd.przeskanuj_reguly() == (), (
        "skan po jezyku interfejsu nagle widzi obca paczke — "
        "to zmienia sens `przeskanuj_reguly` dla paneli runtime")


def test_skan_w_zakresie_drzewa_lapie_literowke(paczki_tymczasowe):
    """Kontrola tej samej sytuacji przez wejscie, ktorego uzywa Manager."""
    import gui_diagnostyka as gd

    _zepsuj(paczki_tymczasowe / "de" / "rezyser" / "tryb_audiobook.yaml")
    wpisy = gd.przeskanuj_reguly_paczek(["de"])
    trafienia = [w for w in wpisy if w.powod == pr.POWOD_WARTOSC]
    assert len(trafienia) == 1, [(w.sciezka, w.powod) for w in wpisy]
    assert Path(trafienia[0].sciezka).name == "tryb_audiobook.yaml"
    assert "rozdzialty" in trafienia[0].szczegol


def test_zakres_drzewa_nie_zglasza_paczki_zdrowej(paczki_tymczasowe):
    """Kontrola odwrotna: nietkniete paczki nie produkuja trafien."""
    import gui_diagnostyka as gd

    assert gd.przeskanuj_reguly_paczek(["pl", "de"]) == ()
    assert gd.przeskanuj_reguly_paczek(["nie_ma_takiej"]) == ()


def test_pusty_zakres_spada_do_jezyka_interfejsu(paczki_tymczasowe):
    """Przycisk, ktory po nacisnieciu nie sprawdza niczego, jest gorszy od braku przycisku."""
    import gui_diagnostyka as gd
    import i18n

    _zepsuj(paczki_tymczasowe / "pl" / "rezyser" / "tryb_audiobook.yaml")
    i18n.ustaw_jezyk("pl")
    wpisy = gd.przeskanuj_reguly_paczek([])
    assert [w.powod for w in wpisy] == [pr.POWOD_WARTOSC]


def test_naglowek_z_niedopasowanej_grupy_nie_wywraca_iteracji(monkeypatch):
    """Jedna grupa w alternatywie PRZECHODZI bramke i nadal daje `None`.

    `(?:(Prolog)|Epilog)` ma dokladnie jedna grupe i nie matchuje pustki, wiec
    loader przyjmuje go slusznie - ale przy trafieniu w „Epilog" grupa nie
    uczestniczy w dopasowaniu i `re.split` wstawia `None`. Przed utwardzeniem
    `.strip()` padal `AttributeError` W WATKU postprodukcji, gdzie siatka
    `gui_rezyser._tytuly_worker` pokazuje go jako BLAD AI: uzytkownik dostawal
    komunikat o modelu za ksztalt wlasnego pliku.
    """
    import core_llm as cl
    import rezyser_ai as rai

    wzor = r"(?i)\n*(?:(Prolog)|Epilog)\n*"
    assert pr._blad_wzorca_rozdzialow(wzor) == "", "bramka odrzucila legalny wzorzec"
    przepis, powody = _postprodukcja(regex_podzial_rozdzialow=wzor,
                                     min_dlugosc_fragmentu=1)
    assert przepis is not None, powody

    wywolania = []

    def _atrapa(_klient, **kwargi):
        wywolania.append(kwargi)
        return "Tytul", "end_turn"

    monkeypatch.setattr(cl, "wywolaj_llm", _atrapa)
    wynik = rai.nadaj_tytuly_rozdzialom(
        object(), przepis, "Prolog\naaa bbb ccc\nEpilog\nddd eee fff\n")

    assert not wynik.przerwano_bledem, wynik.blad
    assert len(wynik.tytuly) == 2, wynik.tytuly
    assert len(wywolania) == 2, wywolania


def test_manager_daje_obu_skanom_ten_sam_zakres():
    """Rdzen usterki: dwa skany pod jednym przyciskiem, dwa rozne zbiory plikow."""
    import gui_manager_regul as gmr

    zrodlo = inspect.getsource(gmr.ManagerRegulPanel._on_odswiez)
    assert "przeskanuj_reguly_paczek(kody)" in zrodlo, (
        "skan regul wrocil do zakresu z jezyka interfejsu")
    assert "przeskanuj_szkice(kody)" in zrodlo, (
        "skan szkicow przestal brac zakres z drzewa")


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
