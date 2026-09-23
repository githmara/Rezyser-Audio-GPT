"""
test_tryby_narzedzia.py - Regresje `buduj_wielojezyczne_tryby.py` z propagacji 19.8.

Audyt przed domknieciem 19.8 zmierzyl, ze ZADNA z pieciu poprawek narzedzia nie
miala testu: usuniecie kazdej z osobna zostawialo zielony caly zestaw. Ten plik
zamyka te luke. Przebiegi `tlumacz_plik` ida HERMETYCZNIE: kopia `dictionaries/`
w katalogu tymczasowym, stub `wywolaj_llm` (zero sieci), bez `main()` - bo
`main()` zapisuje checkliste do prawdziwego `skrypty/` nawet przy `--slowniki`.

  1. Cytat naglowka struktury idzie do modelu jako kotwica o DOCELOWEJ tresci,
     takze przy nieaktywnym orakule (nowy przepis: wszystkie kandydatki
     zamrazane, wiec kotwica `"Rozdzial 1"` zamrazala naglowek po polsku).
  2. Nazwy pol JSON (`mowca=`) przezywaja przeklad, ale tylko na granicy slowa
     (`kontekst=` nie jest kotwica `tekst=`).
  3. Model pomijajacy jednostki (i zamykajacy tablice atrapa `id 999`) dostaje
     jedna dogrywke samych brakow; atrapa nie wchodzi do wyniku.
  4. Komentarz koncowy oddany na dwoch liniach jest sklejany - plik sie parsuje.
  5. Niewidoczny znak w jednostce = zarzut bramki jednostki.

Uruchom:  .venv/Scripts/python -m pytest test_tryby_narzedzia.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_tryby_narzedzia.py
"""

import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))

import buduj_wielojezyczne_tryby as bt
import tlumacz_rdzen

REPO = Path(__file__).parent


@contextlib.contextmanager
def _paczki(stub):
    katalog = Path(tempfile.mkdtemp())
    shutil.copytree(REPO / "dictionaries", katalog / "dictionaries")
    stary_dict, stary_llm = bt.DICT_DIR, bt.wywolaj_llm
    bt.DICT_DIR, bt.wywolaj_llm = katalog / "dictionaries", stub
    try:
        yield katalog / "dictionaries"
    finally:
        bt.DICT_DIR, bt.wywolaj_llm = stary_dict, stary_llm
        shutil.rmtree(katalog, ignore_errors=True)


def _tlumacz(kod: str, plik: str, orakuly=None):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok, _ = bt.tlumacz_plik(kod, plik, None, model="stub", skip_existing=False,
                                dry_run=False, kotwice_extra=("[CEL SCENY]",),
                                orakuly=orakuly or {})
    return ok, buf.getvalue()


def _echo(klient, model, nazwa, kod, pozycje):
    return {i: src for i, _r, src in pozycje}


@pytest.mark.parametrize("plik", ["tryb_audiobook.yaml", "tryb_skrypt.yaml"])
def test_naglowek_cytowany_bez_orakula_dostaje_slowo_paczki(plik):
    with _paczki(_echo) as dicts:
        ok, log = _tlumacz("is", plik)
        assert ok, log
        tekst = (dicts / "is" / "rezyser" / plik).read_text(encoding="utf-8")
    assert "Atriði" in tekst, "cytat `Scena` musi dostać słowo z is/ui.yaml"


def test_pole_json_przezywa_i_tylko_na_granicy_slowa():
    kotwice = bt._kotwice_z_silnika()
    assert {"mowca=", '"mowca"', "`tekst`"} <= set(kotwice)
    tok, mapa = tlumacz_rdzen.tokenizuj(
        'kontekst=ciemny, mowca="Narrator"', ["tekst=", "mowca="])
    assert tok.startswith("kontekst=ciemny"), tok
    assert list(mapa.values()) == ["mowca="]
    assert tlumacz_rdzen.wystapienia_kotwicy("tekst=", "kontekst= tekst=") == 1


def test_skrypt_zachowuje_mowca_w_prozie():
    with _paczki(_echo) as dicts:
        ok, log = _tlumacz("fi", "tryb_skrypt.yaml")
        assert ok, log
        tekst = (dicts / "fi" / "rezyser" / "tryb_skrypt.yaml").read_text(encoding="utf-8")
    assert tekst.count("mowca=") == (REPO / "dictionaries/pl/rezyser/tryb_skrypt.yaml") \
        .read_text(encoding="utf-8").count("mowca=")


def test_dogrywka_brakujacych_jednostek_i_odrzut_atrapy():
    wywolania: list[list[int]] = []

    def _stub(klient, model, nazwa, kod, pozycje):
        wywolania.append([p[0] for p in pozycje])
        if len(wywolania) == 1:   # oddaje dwie pierwsze + atrapę, jak zmierzony model
            mapa = {i: s for i, _r, s in pozycje[:2]}
            mapa[999] = "placeholder"
            return mapa
        return {i: s for i, _r, s in pozycje}

    with _paczki(_stub):
        ok, log = _tlumacz("is", "tryb_audiobook.yaml")
    assert ok, log
    assert len(wywolania) >= 2 and 999 not in sum(wywolania, [])
    assert set(wywolania[1]) == set(wywolania[0][2:]), wywolania
    assert "asking once more" in log


def test_komentarz_koncowy_na_dwoch_liniach_jest_sklejany():
    def _stub(klient, model, nazwa, kod, pozycje):
        return {i: (s + "\ndruga linia bez krzyżyka" if r == "comment" else s)
                for i, r, s in pozycje}

    with _paczki(_stub) as dicts:
        ok, log = _tlumacz("ru", "tryb_skrypt.yaml")
        assert ok, log
        tekst = (dicts / "ru" / "rezyser" / "tryb_skrypt.yaml").read_text(encoding="utf-8")
    yaml.safe_load(tekst)
    assert "came back on several lines" in log


def test_niewidoczny_znak_to_zarzut_jednostki():
    ok, problemy = bt.waliduj_jednostke("Zwykły tekst.", "Tavallinen­teksti.",
                                        bt.KLASA_ETYKIETA)
    assert not ok and any("SOFT HYPHEN" in p for p in problemy), problemy


def test_proza_na_poczatku_tekstu_nie_jest_cytatem_naglowka():
    zrodlowe = bt.naglowki_struktury("pl")
    assert bt._klucze_cytowanych_naglowkow("Scena nie może dziać się w próżni.",
                                           zrodlowe) == []
    mapa: dict[str, str] = {}
    tekst = bt.zamroz_cytowane_naglowki(
        'Scena trwa. Nagłówki (Prolog/Scena) i "Rozdział 1".', mapa, "is")
    assert tekst.startswith("Scena trwa."), tekst
    assert sorted(mapa.values()) == ["Atriði", "Kafli", "Prolog"], mapa


# Uruchomienie jako skrypt - deleguje do pytesta (kanon v19.2.1, §6.11).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
