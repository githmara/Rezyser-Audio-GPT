"""
test_naglowki_paczek.py - Wzorce naglowkow struktury czytane Z PACZEK (19.3).

Do v19.2 `core_rezyser` mial cztery recznie wypisane regexy 9 jezykow plus
osobny, polsko-angielski `\\bprolog\\b` w `ma_prolog`. Dziesiaty jezyk wymagalby
wiec Pythona, a brak tej zmiany degradowal CICHO: `_znajdz_naglowki` zwracalo
pusta liste, `wytnij_od_anchora` oddawalo CALA narracje (koniec przyrostowosci
streszczenia), a punkt odniesienia pamieci roboczej spadal na ciecie znakowe.

Niezmiennik pilnowany tutaj: slowa naglowkow pochodza z `rezyser.naglowek_*`
KAZDEJ zainstalowanej paczki (`dictionaries/<kod>/gui/ui.yaml`) - tego samego
zrodla, ktorym silnik WSTAWIA naglowki. Nowa paczka = nowy jezyk naglowkow,
bez dotykania kodu.

Testy sa hermetyczne: pakiet-atrapa wstrzykiwany przez podmiane `i18n`
(`dostepne_jezyki_ui` + `t`), z przywracaniem stanu i czyszczeniem cache.

Uruchom:  .venv/Scripts/python test_naglowki_paczek.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import core_rezyser as cr
import i18n

# Szwedzki = dziesiaty jezyk, ktorego w repo NIE MA. Wlasnie o to chodzi:
# zaden z tych wyrazow nie stoi w zadnym regexie w Pythonie.
PACZKA_SV = {
    "rezyser.naglowek_rozdzial": "Kapitel",
    "rezyser.naglowek_akt":      "Akt",
    "rezyser.naglowek_scena":    "Scen",
    "rezyser.naglowek_prolog":   "Prolog",
    "rezyser.naglowek_epilog":   "Epilog",
}

# Dosc dlugi ogon, by przejsc guard `_ma_istotna_tresc` (MIN_TRESC_PO_NAGLOWKU).
OGON = "Innehall i scenen. " * 40


class Atrapa:
    """Podmienia zrodlo slow naglowkow na podana mape `{kod: {klucz: slowo}}`."""

    def __init__(self, paczki):
        self.paczki = paczki
        self._stare_jezyki = i18n.dostepne_jezyki_ui
        self._stare_t = i18n.t

    def __enter__(self):
        i18n.dostepne_jezyki_ui = lambda: sorted(self.paczki)
        i18n.t = lambda klucz, *, jezyk_override=None, **kw: (
            self.paczki.get(jezyk_override, {}).get(klucz, f"[{klucz}]")
        )
        cr.wyczysc_cache_naglowkow()
        return self

    def __exit__(self, *_exc):
        i18n.dostepne_jezyki_ui = self._stare_jezyki
        i18n.t = self._stare_t
        cr.wyczysc_cache_naglowkow()
        return False


def test_kazda_zainstalowana_paczka_jest_rozpoznawana():
    """Dla KAZDEGO jezyka w repo: „<slowo> 3" to naglowek wlasciwego typu."""
    kody = i18n.dostepne_jezyki_ui()
    assert kody, "no packs in dictionaries/ - this test has no subject"
    for kod in kody:
        for typ, klucz in cr._KLUCZE_NAGLOWKOW.items():
            # CALA wartosc klucza - dokladnie to, co silnik wstawia do pliku
            # (`wstaw_akt`: f"{naglowek_akt} {licznik}"). Asercja na pierwszym
            # tokenie byla lustrem implementacji, nie niezmiennika.
            slowo = i18n.t(klucz, jezyk_override=kod)
            linia = slowo if typ in ("prolog", "epilog") else f"{slowo} 3"
            assert re.match(cr.wzorzec_naglowka("linia"), linia), (kod, typ, linia)
            rozbity_typ, numer = cr._rozbij_naglowek(linia)
            assert rozbity_typ == typ, (kod, typ, rozbity_typ)
            assert numer == (None if typ in ("prolog", "epilog") else 3), (kod, typ)


def test_konwerter_zna_naglowki_ktore_rezyser_wstawia():
    """Lista `konwerter.naglowki_*` musi zawierac to, co silnik WSTAWIA.

    Rozjazd jest niewidoczny w aplikacji i slyszalny dopiero w wyniku: naglowek
    nieobjety lista nie zostaje „Heading 1" w DOCX, wiec czytnik ekranu traci po
    nim nawigacje. Zmierzone 2026-09-15 w paczce `is`: lista miala natywne
    „Formali"/„Eftirord", ktorych Rezyser nigdy nie wstawia, a brakowalo
    „Prolog"/„Epilog", ktore wstawia (paczka `en` od zawsze trzyma OBA warianty).
    """
    for kod in i18n.dostepne_jezyki_ui():
        rozdzialowe = i18n.t("konwerter.naglowki_rozdzialow", jezyk_override=kod)
        scenowe = i18n.t("konwerter.naglowki_scen", jezyk_override=kod)
        assert isinstance(rozdzialowe, list) and isinstance(scenowe, list), kod
        for typ in ("rozdzial", "akt", "prolog", "epilog"):
            slowo = i18n.t(f"rezyser.naglowek_{typ}", jezyk_override=kod)
            assert slowo in rozdzialowe, (kod, typ, slowo, rozdzialowe)
        scena = i18n.t("rezyser.naglowek_scena", jezyk_override=kod)
        assert scena in scenowe, (kod, scena, scenowe)


def test_nowy_jezyk_nie_wymaga_pythona():
    """Paczka-atrapa `sv` wystarcza, by „Scen 2" bylo naglowkiem sceny."""
    with Atrapa({"sv": PACZKA_SV}):
        assert re.match(cr.wzorzec_naglowka("linia"), "Scen 2")
        assert cr._rozbij_naglowek("Scen 2") == ("scena", 2)
        assert cr._rozbij_naglowek("Kapitel 7") == ("rozdzial", 7)
        # Rekoncyliacja widzi strukture, wiec anchor dziala przyrostowo.
        tekst = f"Prolog\n\nBorjan.\n\nScen 2\n{OGON}"
        fragment, uzyty = cr.wytnij_od_anchora(tekst, "Scen 2")
        assert uzyty == "Scen 2", (uzyty, fragment[:40])
        assert fragment.startswith("Scen 2")


def test_paczka_wypadajaca_przestaje_byc_rozpoznawana():
    """Lustro poprzedniego testu: bez paczki `sv` jej naglowki to proza."""
    with Atrapa({"pl": {
        "rezyser.naglowek_rozdzial": "Rozdzial",
        "rezyser.naglowek_akt":      "Akt",
        "rezyser.naglowek_scena":    "Scena",
        "rezyser.naglowek_prolog":   "Prolog",
        "rezyser.naglowek_epilog":   "Epilog",
    }}):
        assert re.match(cr.wzorzec_naglowka("linia"), "Scena 2")
        assert not re.match(cr.wzorzec_naglowka("linia"), "Scen 2")
        assert cr._rozbij_naglowek("Kapitel 7") == ("inny", None)


def test_naglowek_wielowyrazowy_jest_rozpoznawany():
    """Autor paczki ma prawo wpisac „Rozdzial numer" - silnik wstawia CALOSC.

    Parser brał kiedys `.split()[0]`, wiec taka wartosc dawala nagłowek,
    ktorego nie widzial ani licznik, ani rekoncyliacja - w ciszy.
    """
    with Atrapa({"xx": {**PACZKA_SV, "rezyser.naglowek_rozdzial": "Kapitel nummer"}}):
        assert cr._rozbij_naglowek("Kapitel nummer 4") == ("rozdzial", 4)
        assert re.match(cr.wzorzec_naglowka("linia"), "Kapitel nummer 4")
        assert re.findall(cr.wzorzec_naglowka("rozdzial"), "Kapitel nummer 4") == ["4"]


def test_placeholder_i18n_nie_wchodzi_do_wzorca():
    """Brak klucza daje `[klucz]` - to nie jest naglowek. Ale „[Prolog]" jest."""
    with Atrapa({"xx": {k: v for k, v in PACZKA_SV.items()
                        if k != "rezyser.naglowek_prolog"}}):
        wzorzec = cr.wzorzec_naglowka("prolog")
        assert "rezyser.naglowek_prolog" not in wzorzec, wzorzec
        assert "Prologue" in wzorzec, wzorzec   # fallback angielski
    with Atrapa({"xx": {**PACZKA_SV, "rezyser.naglowek_prolog": "[Prolog]"}}):
        assert re.match(cr.wzorzec_naglowka("linia"), "[Prolog]")


def test_slowo_w_prozie_nie_jest_naglowkiem():
    """Regresja z audytu 19.3: „epilogue" w zdaniu wylaczalo przycisk Wyslij.

    `ma_prolog`/`ma_epilog`/`epilog_ma_tresc` steruja `Enable` w GUI, a pytaly
    `re.search`iem po CALYM tekscie. Po przejsciu na slowa z paczek alternatywa
    zna „epilogue"/„epilogo"/„Эпилог", wiec zwykla proza ustawiala flage.
    """
    projekt = cr.ProjektRezysera(app_dir=str(Path(__file__).parent))
    projekt.full_story = (
        "She read the epilogue and closed the book.\n"
        "Il prologo del romanzo era breve.\n"
    )
    assert not projekt.ma_prolog
    assert not projekt.ma_epilog
    assert not projekt.epilog_ma_tresc
    # A prawdziwy naglowek dalej dziala - w kazdym zainstalowanym jezyku.
    for kod in i18n.dostepne_jezyki_ui():
        slowo = i18n.t("rezyser.naglowek_epilog", jezyk_override=kod)
        projekt.full_story = f"{slowo}\nTresc po epilogu."
        assert projekt.ma_epilog, kod
        assert projekt.epilog_ma_tresc, kod
        projekt.full_story = slowo
        assert projekt.ma_epilog, kod
        assert not projekt.epilog_ma_tresc, kod


def test_wariant_bez_diakrytykow():
    """Recznie dopisany „Rozdzial 7" (bez ogonka) liczy sie jak „Rozdzial 7"."""
    assert re.match(cr.wzorzec_naglowka("linia"), "Rozdzial 7")
    assert cr._rozbij_naglowek("Rozdzial 7") == ("rozdzial", 7)
    # To samo dla jezyka, ktorego ukladu klawiatury rezyser moze nie miec.
    assert cr._rozbij_naglowek("Naytos 2") == ("akt", 2)


def test_brak_paczek_spada_na_angielski_nie_na_polski():
    """Awaryjna sciezka mowi po angielsku - jak `i18n.JEZYK_FALLBACK`."""
    with Atrapa({}):
        wzorzec = cr.wzorzec_naglowka("rozdzial")
        assert "Chapter" in wzorzec, wzorzec
        assert "Rozdzia" not in wzorzec, wzorzec
        assert cr._rozbij_naglowek("Chapter 4") == ("rozdzial", 4)


def test_prolog_i_epilog_bez_wlasnego_hardkodu():
    """`ma_prolog`/`ma_epilog` widza slowa paczek, nie tylko pl/en."""
    with Atrapa({"fi": {
        "rezyser.naglowek_rozdzial": "Luku",
        "rezyser.naglowek_akt":      "Naytos",
        "rezyser.naglowek_scena":    "Kohtaus",
        "rezyser.naglowek_prolog":   "Prologi",
        "rezyser.naglowek_epilog":   "Epilogi",
    }}):
        projekt = cr.ProjektRezysera(app_dir=str(Path(__file__).parent))
        projekt.full_story = "Prologi\n\nTarina alkaa.\n\nEpilogi\n\nLoppu."
        assert projekt.ma_prolog
        assert projekt.ma_epilog
        assert projekt.epilog_ma_tresc


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
