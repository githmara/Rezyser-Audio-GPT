"""
test_manager_kontrakt.py - Kontrakt nazw plikow w `dictionaries/` (v19.4).

Manager Regul jest JEDYNYM GUI, ktore mutuje `dictionaries/`, a do 19.3.1 ufal
wpisanej nazwie naiwnie. Cztery testy bojowe w zainstalowanej paczce
(2026-09-17) daly cztery artefakty, ktorych NIE zlapala zadna bramka
w repozytorium:

  * `pl/akcenty/ucraine.yaml`  (`iso: uk`, kanon: `ukrainski`),
  * `pl/akcenty/bulgarian.yaml` (`iso: bg`, kanon: `bulgarski`),
  * `pl/akcenty/bulgarski.yaml` z `kategoria: naprawiacz` - DZIALAJACY
    naprawiacz tagow pod nazwa zarezerwowana dla akcentu buglarskiego,
  * `{pl,en}/opowiesci/zaczatki_kopia_fi_test4.yaml` - martwy w obu paczkach,
    bo silnik Opowiesci czyta wylacznie stale nazwy.

Testy sprawdzaja trzy rzeczy, kazda przez WYKONANIE:
  1. kanon liczy nazwe pliku akcentu w obie strony i zgadza sie z foldem
     dev-toola (jedna implementacja, nie dwie),
  2. `ocen_cel` wydaje na tych czterech przypadkach dokladnie te werdykty,
     a na CALEJ realnej zawartosci `dictionaries/` nie wydaje zadnego
     (bramka, ktora odrzuca poprawne dane, zostanie wylaczona po tygodniu),
  3. kazdy komunikat kontraktu ISTNIEJE w KAZDEJ paczce i podstawia wszystkie
     swoje parametry - `i18n.t` cichnie przy rozjezdzie nazw pol i zwraca
     surowy szablon, wiec bez tego testu literowka w `{propozycja}` dawalaby
     uzytkownikowi dialog z widoczna klamra.

Uruchom:  .venv/Scripts/python -m pytest test_manager_kontrakt.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_manager_kontrakt.py
"""

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import yaml

import buduj_wielojezyczne_akcenty as bwa
import core_poliglota as cp
import dev_yaml
import i18n
import jezyki_lingua as jl
import manager_regul_kontrakt as mrk
import manager_regul_szablony as mrs
import opowiesci_ai as oai
import przepisy_rezysera as pr

_KORZEN = Path(__file__).parent
_DICT = _KORZEN / "dictionaries"
_NARZEDZIE = "test_manager_kontrakt"

# Klamra formatujaca, ktora zostala w tekscie = parametr, ktorego wolajacy nie
# podal (`i18n.t` lapie `KeyError` i zwraca surowy szablon - cicho).
_RE_KLAMRA = re.compile(r"\{[a-z_]+\}")


# ---------------------------------------------------------------------------
# 1. Kanon: nazwa pliku akcentu w obie strony
# ---------------------------------------------------------------------------
def test_plik_akcentu_z_kanonu():
    assert jl.plik_akcentu("bg") == "bulgarski"
    assert jl.plik_akcentu("uk") == "ukrainski"
    assert jl.plik_akcentu("it") == "wloski"      # fold NFKD
    assert jl.plik_akcentu("fi") == "finski"
    assert jl.plik_akcentu(" BG ") == "bulgarski"  # normalizacja kodu
    # Jezyki POZA kanonem Lingui (faroeski, maltanski) nie maja czym byc
    # rozstrzygniete i to jest stan poprawny, nie usterka.
    assert jl.plik_akcentu("fo") is None
    assert jl.plik_akcentu("mt") is None
    assert jl.plik_akcentu("") is None


def test_iso_dla_pliku_akcentu():
    assert jl.iso_dla_pliku_akcentu("bulgarski") == "bg"
    assert jl.iso_dla_pliku_akcentu("Fiński") == "fi"      # fold obu stron
    # Nazwy narzedzi Poligloty NIE naleza do zadnego jezyka - inaczej kontrakt
    # blokowalby wlasne, kanoniczne pliki paczki.
    assert jl.iso_dla_pliku_akcentu("oczyszczenie") is None
    assert jl.iso_dla_pliku_akcentu("naprawiacz_tagow") is None
    # Nazwy z testow bojowych 1 i 3: brzmia jak jezyk, nie sa nim.
    assert jl.iso_dla_pliku_akcentu("ucraine") is None
    assert jl.iso_dla_pliku_akcentu("bulgarian") is None


def test_kanon_round_trip_i_unikalnosc():
    """Kazdy kod kanonu wraca do siebie, a nazwy plikow sie nie zderzaja."""
    formy = {}
    for iso in jl.KANON:
        nazwa = jl.plik_akcentu(iso)
        assert nazwa, f"{iso}: kanon nie daje nazwy pliku"
        assert jl.iso_dla_pliku_akcentu(nazwa) == iso
        assert nazwa.isascii() and nazwa.replace("_", "").isalpha(), nazwa
        formy.setdefault(nazwa, []).append(iso)
    kolizje = {n: k for n, k in formy.items() if len(k) > 1}
    assert not kolizje, f"dwa jezyki o jednej nazwie pliku: {kolizje}"


def test_fold_ma_jedna_implementacje():
    """Dev-tool wola fold z kanonu, nie ma wlasnego (lekcja o lustrach pol)."""
    for iso, (_, nazwa_pl) in jl.KANON.items():
        assert bwa.nazwa_pliku_akcentu(nazwa_pl) == jl.fold_nazwy(nazwa_pl), iso


# ---------------------------------------------------------------------------
# 2. Werdykty
# ---------------------------------------------------------------------------
def _klucze(sciezka, cfg):
    return {(z.werdykt, z.klucz) for z in mrk.ocen_cel(sciezka, cfg)}


def test_werdykty_testow_bojowych():
    # Test 1: duplikat `rosyjski.yaml` nazwany `ucraine`, `iso` przepisane.
    assert ("blokada", "akcent_zla_nazwa") in _klucze(
        "pl/akcenty/ucraine.yaml", {"kategoria": "akcent", "iso": "uk"})
    # Test 3: kreator zapisal akcent pod angielska nazwa jezyka.
    assert ("blokada", "akcent_zla_nazwa") in _klucze(
        "pl/akcenty/bulgarian.yaml", {"kategoria": "akcent", "iso": "bg"})
    # Test 2: narzedzie pod nazwa jezyka.
    assert ("blokada", "nazwa_jezyka_nie_akcent") in _klucze(
        "pl/akcenty/bulgarski.yaml", {"kategoria": "naprawiacz", "iso": ""})
    # Test 4: kopia przepisu Opowiesci w tym samym folderze.
    assert ("ostrzezenie", "opowiesci_nazwa_nieczytana") in _klucze(
        "pl/opowiesci/zaczatki_kopia_fi_test4.yaml", {})


def test_werdykty_graniczne():
    # Nazwa z kanonu + `iso` innego jezyka: pole `iso` znaczy „glos wyniku",
    # wiec rozjazd kasuje caly produkt - blokada, nie ostrzezenie.
    assert ("blokada", "akcent_iso_rozjazd") in _klucze(
        "pl/akcenty/finski.yaml", {"kategoria": "akcent", "iso": "is"})
    # Jezyk poza kanonem: nazwa jest wolna, ale uzytkownik ma o tym uslyszec.
    graniczne = _klucze("pl/akcenty/faroeski.yaml",
                        {"kategoria": "akcent", "iso": "fo"})
    assert ("ostrzezenie", "akcent_iso_poza_kanonem") in graniczne
    assert not any(w == "blokada" for w, _ in graniczne)
    # Nowy tryb Opowiesci wymaga okablowania w Pythonie - blokada.
    assert ("blokada", "opowiesci_tryb_bez_okablowania") in _klucze(
        "pl/opowiesci/tryb_horror.yaml", {})
    # Przywrocenie brakujacego pliku z kanonu jest legalne.
    assert not mrk.ocen_cel("de/opowiesci/tryb_swobodny.yaml", {})
    # Klasa C: nazwa wolna, bo dispatch idzie z pol.
    assert not mrk.ocen_cel("pl/rezyser/tryb_cokolwiek.yaml", {})
    assert not mrk.ocen_cel("pl/szyfry/moj_szyfr.yaml", {"kategoria": "szyfr"})
    assert not mrk.ocen_cel("pl/podstawy.yaml", {})


def test_narzedzia_to_zamkniety_zbior():
    """Nazwy narzedzi pochodza z silnika, nie z wlasnej listy w GUI."""
    wszystkie = set(mrk.narzedzia_dla_typu("oczyszczenie")) | \
                set(mrk.narzedzia_dla_typu("naprawiacz"))
    assert wszystkie == {os.path.splitext(n)[0] for n in cp._NARZEDZIA_AKCENTOW}
    # Paczka wdrozona ma komplet, wiec kreator nie ma czego w niej tworzyc.
    assert mrk.narzedzia_brakujace("pl", "oczyszczenie") == []
    assert mrk.narzedzia_brakujace("pl", "naprawiacz") == []
    # Paczka, ktorej nie ma, potrzebuje wszystkiego.
    assert mrk.narzedzia_brakujace("nie_ma_takiej", "naprawiacz") == \
        ["naprawiacz_tagow"]
    assert mrk.narzedzia_brakujace("nie_ma_takiej", "oczyszczenie") == \
        ["oczyszczenie", "oczyszczenie_bez_liczb"]


def test_zero_zastrzezen_na_realnej_zawartosci():
    """Kontrakt nie odrzuca ani jednego pliku z dziewieciu paczek."""
    trafienia = []
    for korzen, _, pliki in os.walk(_DICT):
        for plik in pliki:
            if not plik.lower().endswith((".yaml", ".yml")):
                continue
            absolutna = Path(korzen) / plik
            rel = absolutna.relative_to(_DICT).as_posix()
            # Nieparsowalny YAML w `dictionaries/` jest tu FATALNY, a nie
            # cicho pomijany: to standard dev-toola (`dev_yaml`), a plik,
            # ktorego nie umiemy przeczytac, unieważniłby caly wynik tego
            # testu („zero zastrzezen" nad zbiorem, ktorego nie przeczytano).
            cfg = dev_yaml.wczytaj_lub_padnij(absolutna, narzedzie=_NARZEDZIE)
            trafienia += [(rel, z.klucz) for z in mrk.ocen_cel(rel, cfg)]
    assert not trafienia, f"kontrakt zglasza poprawne pliki: {trafienia}"


def test_szablony_kreatora_przechodza_kontrakt():
    """Kazdy szablon parsuje sie i nie jest przez kontrakt zablokowany."""
    for typ in mrs.LISTA_TYPOW:
        if typ == mrs.TYP_JEZYK_BAZOWY:
            kw = dict(id_pliku="bg", etykieta="Balgarski")
        else:
            kw = dict(id_pliku=jl.plik_akcentu("bg") if typ == mrs.TYP_AKCENT
                      else "probny", etykieta="Probny")
        pakiet = mrs.zbuduj_wynik(typ, iso="bg", jezyk_bazowy="pl",
                                  opis_efektu="opis", **kw)
        if not pakiet["yaml"]:
            continue                      # PROMPT-only: nic nie powstaje
        cfg = yaml.safe_load(pakiet["yaml"])
        assert isinstance(cfg, dict), f"{typ}: szablon nie parsuje sie do mapy"
        blokady = [z.klucz for z in mrk.ocen_cel(pakiet["docelowy"], cfg)
                   if z.blokuje]
        assert not blokady, f"{typ}: wlasny szablon zablokowany ({blokady})"


# ---------------------------------------------------------------------------
# 3. Zamkniety zbior nazw przepisow Opowiesci
# ---------------------------------------------------------------------------
def test_nazwy_przepisow_zgodne_z_paczka():
    """`NAZWY_PRZEPISOW` = zawartosc `pl/opowiesci/`, w OBIE strony.

    Zbior jest jawny, zeby Manager Regul mogl powiedziec „ten plik bedzie
    martwy" PRZED utworzeniem go. Jawny zbior starzeje sie jednak sam, wiec
    ten test jest jego jedyna gwarancja: nowy przepis dolozony do paczki bez
    wpisu tutaj przestaje byc rozpoznawany, a wpis bez pliku klamie
    uzytkownikowi w komunikacie blokady.
    """
    na_dysku = {p.stem for p in (_DICT / "pl" / "opowiesci").glob("*.yaml")}
    assert na_dysku == set(oai.NAZWY_PRZEPISOW), (
        f"nadwyzka w kodzie: {set(oai.NAZWY_PRZEPISOW) - na_dysku}, "
        f"brak w kodzie: {na_dysku - set(oai.NAZWY_PRZEPISOW)}")


# ---------------------------------------------------------------------------
# 4. Komunikaty: obecne w kazdej paczce i w pelni podstawione
# ---------------------------------------------------------------------------
def _wszystkie_zastrzezenia():
    """Po jednym egzemplarzu KAZDEJ klasy zastrzezenia, z parametrami."""
    przypadki = [
        ("pl/akcenty/bulgarski.yaml", {"kategoria": "naprawiacz", "iso": ""}),
        ("pl/akcenty/ucraine.yaml",   {"kategoria": "akcent", "iso": "uk"}),
        ("pl/akcenty/finski.yaml",    {"kategoria": "akcent", "iso": "is"}),
        ("pl/akcenty/faroeski.yaml",  {"kategoria": "akcent", "iso": "fo"}),
        ("pl/akcenty/oczyszczenie_inne.yaml", {"kategoria": "oczyszczenie"}),
        ("pl/opowiesci/tryb_horror.yaml", {}),
        ("pl/opowiesci/zaczatki_kopia.yaml", {}),
        ("pl/szyfry/moj.yaml", {"kategoria": "szyfr", "algorytm": "enigma"}),
    ]
    zebrane = {}
    for sciezka, cfg in przypadki:
        for z in mrk.ocen_cel(sciezka, cfg):
            zebrane.setdefault(z.klucz, z)
    return zebrane


def test_kazda_klasa_ma_komunikat():
    """Pokrycie: kazda klasa zastrzezenia z modulu ma reprezentanta w tescie."""
    zebrane = set(_wszystkie_zastrzezenia())
    w_paczce = set(yaml.safe_load(
        (_DICT / "pl" / "gui" / "ui.yaml").read_text(encoding="utf-8")
    )["manager"]["kontrakt"])
    assert zebrane == w_paczce, (
        f"bez komunikatu: {zebrane - w_paczce}, "
        f"komunikat bez klasy: {w_paczce - zebrane}")


def test_komunikat_o_nazwie_poza_kanonem_mowi_POLSKA():
    """Nazwa pliku akcentu jest identyfikatorem PO POLSKU w KAZDEJ paczce.

    Klasa halucynacji zmierzona 2026-09-17 przy pierwszym przebiegu
    autotlumacza: piec paczek (de, es, fr, it, ru) zlokalizowalo FAKT
    O FORMACIE DANYCH tak, jakby byl faktem o jezyku interfejsu — „kanon nie
    ma HISZPANSKIEJ nazwy tego jezyka… uzyj tradycyjnej HISZPANSKIEJ nazwy".
    Uzytkownik, ktory posluchal, nadalby plikowi nazwe w swoim jezyku, czyli
    zrobilby dokladnie ten defekt, przed ktorym ten komunikat ostrzega
    (`bulgarian.yaml` zamiast `bulgarski.yaml`).

    Bramka jest kuratorska, bo mechanicznie sprawdzalna jest tu tylko JEDNA
    rzecz: czy komunikat w ogole nazywa jezyk polski. Dziesiaty jezyk projektu
    dopisze tu jedno slowo — i o tym, ze musi, dowie sie z tego testu, a nie
    od uzytkownika.
    """
    slowo_polski = {
        "pl": "polsk", "en": "polish", "de": "polnisch", "es": "polac",
        "fi": "puola", "fr": "polon", "is": "pólsk", "it": "polacc",
        "ru": "польск",
    }
    braki = []
    for kod in sorted(p.name for p in _DICT.iterdir() if p.is_dir()):
        if not (_DICT / kod / "gui" / "ui.yaml").is_file():
            continue
        assert kod in slowo_polski, (
            f"{kod}: dopisz slowo „polski\" w tym jezyku do mapy testu")
        i18n.ustaw_jezyk(kod)
        tekst = i18n.t("manager.kontrakt.akcent_iso_poza_kanonem",
                       iso="fo", nazwa="faroeski").lower()
        if slowo_polski[kod] not in tekst:
            braki.append(f"{kod}: komunikat nie nazywa jezyka polskiego "
                         f"(szukano „{slowo_polski[kod]}\")")
    i18n.ustaw_jezyk("pl")
    assert not braki, "\n".join(braki)


def test_komunikaty_podstawiaja_parametry_w_kazdej_paczce():
    zebrane = _wszystkie_zastrzezenia()
    braki = []
    for kod in sorted(p.name for p in _DICT.iterdir() if p.is_dir()):
        if not (_DICT / kod / "gui" / "ui.yaml").is_file():
            continue
        i18n.ustaw_jezyk(kod)
        for klucz, z in zebrane.items():
            tekst = i18n.t(f"manager.kontrakt.{klucz}", **z.parametry)
            if tekst.startswith("["):
                braki.append(f"{kod}: brak klucza {klucz}")
            elif _RE_KLAMRA.search(tekst):
                braki.append(f"{kod}/{klucz}: niepodstawione "
                             f"{_RE_KLAMRA.findall(tekst)}")
        for klucz in ("kontrakt_blokada_tytul", "kontrakt_ostrzezenie_tytul",
                      "kontrakt_kontynuowac", "kreator_lbl_id_kanon",
                      "kreator_lbl_id_narzedzie", "kreator_id_narzedzie_name",
                      "kreator_blad_narzedzia_komplet", "dup_komentarz_akcent"):
            parametry = {"kanon": "x", "iso": "xx", "nazwa_pliku": "x.yaml"}
            tekst = i18n.t(f"manager.{klucz}", **parametry)
            if tekst.startswith("["):
                braki.append(f"{kod}: brak klucza {klucz}")
            elif _RE_KLAMRA.search(tekst):
                braki.append(f"{kod}/{klucz}: niepodstawione "
                             f"{_RE_KLAMRA.findall(tekst)}")
    i18n.ustaw_jezyk("pl")
    assert not braki, "\n".join(braki)


# ---------------------------------------------------------------------------
# 6. Prompty Managera nie moga sie zestarzec wzgledem silnika
# ---------------------------------------------------------------------------
def test_prompt_postprodukcji_wylicza_zakresy_z_kodu():
    """Prompt musi wymieniac KAZDY zakres z `pr.ZAKRESY_DOZWOLONE` i role pamieci.

    Geneza (przeglad edge-case'ow 2026-09-19): prompt wyliczal zakresy wlasnym
    literalem i utknal na dwoch z v18.12, choc silnik od v18.13 zna trzy. Agent,
    ktory zobaczyl w paczce `zakres: rekoncyliacja`, mial wiec instrukcje
    mowiaca, ze to wartosc NIELEGALNA - czyli ze gotowe narzedzie Pamieci
    Dlugotrwalej jest stubem do obejscia wlasnym trybem. Tego nie widziala
    zadna bramka, bo prompt jest tekstem, a nie danymi paczki.
    """
    tekst = mrs.prompt_postprodukcja("probny", "Probny", "pl")
    # Sama obecnosc slowa `rekoncyliacja` gdziekolwiek w promptcie to za slaba
    # asercja (opis bulletu zawiera je nawet wtedy, gdy WYLICZENIE sie cofnie),
    # wiec zadamy, by prompt cytowal helper DOSLOWNIE - a helper czyta z kodu.
    assert mrs._zakresy_postprodukcji() in tekst, (
        "prompt nie cytuje `_zakresy_postprodukcji()` - wyliczenie zakresow "
        "zyje wlasnym zyciem i zestarzeje sie przy nastepnym `ZAKRES_*`")
    braki = [z for z in pr.ZAKRESY_DOZWOLONE if f"`{z}`" not in tekst]
    assert not braki, f"prompt nie wymienia zakresow: {braki}"
    assert pr.ROLA_PAMIEC_DLUGOTRWALA in tekst, (
        "prompt nie mowi o roli `pamiec_dlugotrwala` - agent napisze narzedzie "
        "streszczajace bez roli, wiec plik powstanie obok Pamieci Dlugotrwalej")
    szablon = mrs.szablon_postprodukcja("probny", "Probny", "pl")
    braki_szablonu = [z for z in pr.ZAKRESY_DOZWOLONE if z not in szablon]
    assert not braki_szablonu, f"szablon nie wymienia zakresow: {braki_szablonu}"


def test_prompt_jezyka_bazowego_wylicza_podfoldery_z_kodu():
    """Prompt musi wymieniac KAZDY podfolder wymagany przez `_jezyk_kompletny`.

    Do v19.4.1 wyliczal `gui/` zamiast `opowiesci/`, wiec agent budowal paczke,
    ktora `dostepne_jezyki_bazowe()` po cichu odfiltrowuje - a user widzial
    tylko „nowego jezyka nie ma w aplikacji", bez ani jednego komunikatu.
    """
    tekst = mrs.prompt_jezyk_bazowy("bg", "Balgarski")
    assert mrs._podfoldery_jezykowe() in tekst, (
        "prompt nie cytuje `_podfoldery_jezykowe()` - lista podfolderow zyje "
        "wlasnym zyciem, a to ona decyduje, czy paczka w ogole sie pokaze")
    braki = [f"{pod}/" for pod in cp._PODFOLDERY_JEZYKOWE
             if f"`{pod}/`" not in tekst]
    assert not braki, f"prompt nie wymienia podfolderow: {braki}"
    assert "gui/ui.yaml" in tekst, "prompt nie wymienia wymaganego gui/ui.yaml"


def test_prompty_nie_licza_plikow_paczki_literalem():
    """Sklad `rezyser/` w promptach pochodzi z dysku, nie z recznej liczby.

    Wersja literalowa mowila „4 files (3 modes + 1 postproduction)" jeszcze
    w v19.4.1, gdy paczki mialy ich siedem.
    """
    # Dla paczki bazowej `de` helper liczy z `pl` (pomija paczke bazowa, zeby
    # agent nie brał za wzor struktury, ktora wlasnie powstaje) - wiec TE liczby
    # musza sie zgadzac z dyskiem `pl`.
    pliki = len(list((_DICT / "pl" / "rezyser").glob("*.yaml")))
    assert mrs._sklad_rezysera("de").startswith(f"{pliki} files"), \
        mrs._sklad_rezysera("de")
    # A prompty MUSZA cytowac helper, nie wlasna liczbe - niezaleznie od tego,
    # ktora paczke helper wybierze dla danego jezyka bazowego.
    sklad = mrs._sklad_rezysera("pl")
    assert re.match(r"^\d+ files", sklad), sklad
    for tekst in (mrs.prompt_postprodukcja("probny", "Probny", "pl"),
                  mrs.prompt_tryb_rezysera("probny", "Probny", "pl")):
        assert sklad in tekst, "prompt nie podaje realnego skladu `rezyser/`"


def test_tabela_lacinki_domyka_swoj_zakres():
    """`TABELA_LACINKI` pokrywa CALY `ZAKRES_LACINKI`, celami w ASCII.

    Ta tabela jest orakulem dwoch stron umowy naraz: `szablon_podstawy`
    renderuje ja jako pre-pass nowej paczki, a `audyt_podstaw` mierzy nia
    pokrycie paczek juz wdrozonych. Dziura w niej jest wiec dziura w obu
    miejscach jednoczesnie - i to cicha, bo bramka nie ma z czym porownac.
    """
    tabela = mrs.TABELA_LACINKI
    mapa = dict(tabela)
    assert len(mapa) == len(tabela), "tabela powtarza wzorzec"

    lo, hi = mrs.ZAKRES_LACINKI
    brak = [chr(c) for c in range(lo, hi + 1)
            if chr(c).isalpha() and chr(c) not in mapa]
    assert not brak, f"zakres niepokryty: {''.join(brak)}"

    for wzor, cel in tabela:
        assert cel.isascii(), f"`{wzor}` -> `{cel}`: cel nie jest ASCII"
        assert cel, f"`{wzor}`: pusty cel"
        assert wzor != cel, f"`{wzor}`: regula tozsamosciowa"

    # Wersalik NIE moze byc pominiety: pre-pass to doslowny `str.replace`,
    # wiec brak wariantu wielkiej litery przepuszcza znak do syntezatora.
    # Wyjatki sa dwa i oba maja powod w Unicode, nie w niedbalstwie: litera
    # puchnaca pod `.upper()` (`ss` -> „SS", wpis jawny `ẞ`) i litera, ktorej
    # wersalik jest zwyklym ASCII (`ı` -> „I", transliterowac nie ma czego).
    for wzor, _ in tabela:
        duza = wzor.upper()
        if len(duza) != 1 or duza == wzor or duza.isascii():
            continue
        assert duza in mapa, f"`{wzor}` nie ma wariantu `{duza}`"


def test_szablon_podstaw_liczy_tabela_z_kodu():
    """Szablon `podstawy.yaml` renderuje TABELE Z KODU, nie wlasna kopie.

    Ten sam wzorzec co przy `ZAKRESY_DOZWOLONE` (v19.4.2): dwie kopie
    wyliczenia rozjezdzaja sie przy pierwszym nowym znaku, a rozjazd widac
    dopiero w paczce, ktora ktos juz wydal.
    """
    tekst = mrs.szablon_podstawy("sv", "szwedzki")
    for wzor, cel in mrs.TABELA_LACINKI:
        assert f'wzor: "{wzor}", zamiana: "{cel}"' in tekst,             f"szablon nie renderuje pary `{wzor}` -> `{cel}`"
    assert yaml.safe_load(tekst) is not None


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
