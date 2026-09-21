"""
test_szkice_szablonow.py - Niewypelniony szablon Managera Regul (v19.4).

Kreator Managera zapisuje pliki z markerami ``<FILL ...>`` w miejscach, ktorych
nie potrafi wypelnic sam. To stan ROBOCZY i legalny na dysku autora paczki -
ale nie w paczce, ktora ktos dostaje w instalatorze.

DLACZEGO TO MA WLASNY TEST, a nie jest kosmetyka: niewypelniony szablon NIE JEST
martwy. `szablon_akcent` zapisuje dwie realne reguly (`ch -> h`, `Ch -> H`),
a silnik dispatchuje warianty po polu `kategoria`, nie po nazwie - wiec taki plik
wchodzi do paczki jako ZYWY akcent robiacy jedna bezsensowna zamiane, a jego
`opis:` (orakul bramki G6 przykladow, wiec i ona wtedy milczy) zawiera angielska
instrukcje dla modelu. Zmierzone 2026-09-17: przed ta zmiana markera nie scigal
NIKT - `grep` po „FILL" w calym repozytorium trafial wylacznie w producenta,
czyli `manager_regul_szablony`.

Testy pilnuja trzech rzeczy:
  1. PRODUCENT I DETEKTOR SIE ZGADZAJA - kazdy szablon, ktory realnie powstaje
     na dysku, jest przez detektor widziany jako szkic; oba typy PROMPT-only nie
     zapisuja niczego. Bez tego wzorzec w detektorze mogloby rozjechac sie
     z f-stringami szablonow po cichu;
  2. ZAKRES SKANU - `gui/` jest poza nim, bo tam nie pisze kreator, a `ui.yaml`
     MUSI moc o markerze mowic (nota „Dalsze kroki" dla nowego jezyka bazowego
     go cytuje; pierwszy przebieg bramki dal z tego powodu 9 trafien);
  3. DWA KANALY MOWIA TO SAMO - rejestr pominiec w aplikacji
     (`gui_diagnostyka.przeskanuj_szkice`) i bramka dev
     (`audyt_podstaw.sprawdz_szkice`) czytaja ten sam skan, wiec nie moga
     wydac rozbieznego werdyktu o tej samej paczce.

Uruchom:  .venv/Scripts/python -m pytest test_szkice_szablonow.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_szkice_szablonow.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import audyt_podstaw
import gui_diagnostyka as gd
import i18n
import manager_regul_szablony as mrs
import przepisy_rezysera as pr

_KORZEN = Path(__file__).parent
_DICT = _KORZEN / "dictionaries"

# Typy kreatora, ktore NIE zapisuja pliku (wymagaja Pythona od programisty),
# wiec nie maja szablonu i nie moga zostawic szkicu na dysku.
_TYLKO_PROMPT = {mrs.TYP_TRYB_OPOWIESCI, mrs.TYP_SZYFR_ALGORYTM}


def _pakiet(typ: str) -> dict:
    """Realny wynik kreatora dla danego typu (z poprawnymi polami)."""
    if typ == mrs.TYP_JEZYK_BAZOWY:
        kw = dict(id_pliku="bg", etykieta="Balgarski")
    elif typ == mrs.TYP_AKCENT:
        kw = dict(id_pliku="bulgarski", etykieta="Akcent bulgarski")
    else:
        kw = dict(id_pliku="probny", etykieta="Probny")
    return mrs.zbuduj_wynik(typ, iso="bg", jezyk_bazowy="pl",
                            opis_efektu="opis", **kw)


# ---------------------------------------------------------------------------
# 1. Producent i detektor
# ---------------------------------------------------------------------------
def test_kazdy_szablon_ma_marker():
    """Kazdy zapisywany szablon jest widziany jako szkic; PROMPT-only milczy."""
    for typ in mrs.LISTA_TYPOW:
        pakiet = _pakiet(typ)
        if typ in _TYLKO_PROMPT:
            assert not pakiet["yaml"], f"{typ}: PROMPT-only zapisuje plik"
            continue
        assert pakiet["yaml"], f"{typ}: brak szablonu do zapisania"
        markery = mrs.znajdz_markery_szkicu(pakiet["yaml"])
        assert markery, (
            f"{typ}: detektor nie widzi ani jednego markera w szablonie — "
            f"wzorzec `_RE_MARKER_SZKICU` rozjechal sie z f-stringami szablonu")


def test_detektor_lapie_oba_warianty_i_wieloliniowe():
    # `<FILL NATIVELY in X: ...>` — tresc, ktora ma byc natywna.
    assert mrs.znajdz_markery_szkicu("# <FILL NATIVELY in Polski: naglowek>")
    # `<FILL IN: ...>` — lista do dopisania.
    assert mrs.znajdz_markery_szkicu("  # <FILL IN: dalsze pary>")
    # Bez „in <jezyk>" (szablon `podstawy.yaml`).
    assert mrs.znajdz_markery_szkicu("# <FILL NATIVELY: endonim + sufiks>")
    # Marker rozciagniety na wiele linii — instrukcja dla wykonawcy bywa akapitem.
    wieloliniowy = "opis: |\n  <FILL NATIVELY in Polski: dwa\n  zdania o czyms>\n"
    assert len(mrs.znajdz_markery_szkicu(wieloliniowy)) == 1
    # Liczy WSZYSTKIE, nie pierwszy.
    assert len(mrs.znajdz_markery_szkicu("<FILL A> x <FILL B>")) == 2
    # Czysty plik i nie-tekst.
    assert mrs.znajdz_markery_szkicu("id: finski\niso: fi\n") == []
    assert mrs.znajdz_markery_szkicu(None) == []


def test_opis_markerow_skraca_i_nie_gubi_liczby():
    markery = mrs.znajdz_markery_szkicu(_pakiet(mrs.TYP_AKCENT)["yaml"])
    opis = mrs.opis_markerow(markery)
    assert opis.startswith(f"{len(markery)} × <FILL …>")
    assert "\n" not in opis, "szczegol techniczny musi byc jednoliniowy"
    assert len(opis) < 200
    assert mrs.opis_markerow([]) == ""


# ---------------------------------------------------------------------------
# 2. Zakres skanu
# ---------------------------------------------------------------------------
def test_zakres_skanu_pomija_gui_a_obejmuje_reszte():
    pliki = mrs.pliki_do_skanu_szkicow(_DICT / "pl")
    wzgledne = {p.relative_to(_DICT / "pl").as_posix() for p in pliki}
    assert "podstawy.yaml" in wzgledne
    for pod in ("akcenty", "szyfry", "rezyser", "opowiesci"):
        assert any(w.startswith(f"{pod}/") for w in wzgledne), pod
    # `gui/ui.yaml` MUSI moc cytowac marker (nota „Dalsze kroki" go cytuje),
    # a `gui/dokumentacja/` pisza autotlumacze, nie kreator.
    assert not any(w.startswith("gui/") for w in wzgledne), \
        "gui/ w zakresie — bramka zablokuje wydanie na cytacie markera w ui.yaml"
    # Paczka, ktorej nie ma, nie jest bledem.
    assert mrs.pliki_do_skanu_szkicow(_DICT / "nie_ma_takiej") == []


def test_ui_yaml_realnie_cytuje_marker():
    """Uzasadnienie wykluczenia `gui/` jest FAKTEM, nie przypuszczeniem.

    Gdy ten test kiedys padnie, znaczy to, ze nota przestala cytowac marker —
    i wtedy wykluczenie `gui/` trzeba przemyslec od nowa, a nie utrzymywac
    „bo tak bylo".
    """
    ui = (_DICT / "pl" / "gui" / "ui.yaml").read_text(encoding="utf-8")
    assert mrs.znajdz_markery_szkicu(ui), (
        "pl/ui.yaml nie cytuje juz markera — wyklucznie `gui/` ze skanu "
        "stracilo swoje uzasadnienie")


# ---------------------------------------------------------------------------
# 3. Dwa kanaly, jeden werdykt
# ---------------------------------------------------------------------------
def test_repozytorium_nie_ma_szkicow():
    """Bramka dev na zywej zawartosci repo (lustro `audyt_podstaw --bramka`)."""
    znaleziska = audyt_podstaw.sprawdz_szkice()
    assert not znaleziska, "\n".join(f"{z.zakres}: {z.szczegol}"
                                     for z in znaleziska)


def test_rejestr_w_aplikacji_zglasza_szkic():
    """Ścieżka runtime: szkic → rejestr, plik dokonczony → cisza, idempotentnie."""
    pierwotny = pr.DICTIONARIES_DIR
    tmp = Path(tempfile.mkdtemp())
    try:
        paczka = tmp / "dictionaries" / "pl"
        (paczka / "akcenty").mkdir(parents=True)
        (paczka / "gui").mkdir(parents=True)
        (paczka / "akcenty" / "bulgarski.yaml").write_text(
            _pakiet(mrs.TYP_AKCENT)["yaml"], encoding="utf-8")
        shutil.copy(_DICT / "pl" / "akcenty" / "finski.yaml",
                    paczka / "akcenty" / "finski.yaml")
        (paczka / "gui" / "ui.yaml").write_text(
            'x: "szablon ma markery `<FILL NATIVELY>`"\n', encoding="utf-8")

        pr.DICTIONARIES_DIR = str(tmp / "dictionaries")
        pr.wyczysc_pominiecia()
        wpisy = gd.przeskanuj_szkice(["pl"])

        szkice = [w for w in wpisy if w.powod == pr.POWOD_SZKIC]
        assert len(szkice) == 1, [(w.sciezka, w.powod) for w in wpisy]
        assert Path(szkice[0].sciezka).name == "bulgarski.yaml"
        assert "<FILL" in szkice[0].szczegol
        # Drugi przebieg nie dubluje wpisu (rejestr idempotentny po trojce).
        assert len(gd.przeskanuj_szkice(["pl"])) == len(wpisy)
        # Paczka nieistniejaca i pusta lista kodow nie rzucaja.
        assert gd.przeskanuj_szkice([]) == wpisy
        assert gd.przeskanuj_szkice(["nie_ma_takiej"]) == wpisy
    finally:
        pr.DICTIONARIES_DIR = pierwotny
        pr.wyczysc_pominiecia()
        shutil.rmtree(tmp, ignore_errors=True)


def test_komunikat_powodu_jest_w_kazdej_paczce():
    """`diag.powod.szkic` musi istniec w kazdej paczce — inaczej raport milczy.

    `sformatuj_raport` sklada `t(f"diag.powod.{powod}")`, wiec brak klucza daje
    uzytkownikowi `[diag.powod.szkic]` w miejscu wyjasnienia.
    """
    braki = []
    for kod in sorted(p.name for p in _DICT.iterdir() if p.is_dir()):
        if not (_DICT / kod / "gui" / "ui.yaml").is_file():
            continue
        i18n.ustaw_jezyk(kod)
        for klucz in ("diag.powod.szkic", "diag.tytul", "diag.wstep"):
            if i18n.t(klucz).startswith("["):
                braki.append(f"{kod}: brak klucza {klucz}")
        # `<FILL` jest LITERALEM, nie slowem: to dokladnie ten ciag, ktorego
        # uzytkownik ma szukac w swoim pliku. Przetlumaczony („WYPELNIJ") albo
        # zgubiony zostawia go z opisem, po ktorym nie da sie nic znalezc.
        if "<FILL" not in i18n.t("diag.powod.szkic"):
            braki.append(f"{kod}: `diag.powod.szkic` zgubil literal `<FILL`")
    i18n.ustaw_jezyk("pl")
    assert not braki, "\n".join(braki)


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
