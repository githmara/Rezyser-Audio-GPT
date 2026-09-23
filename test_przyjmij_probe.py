"""
test_przyjmij_probe.py - Odrzuty bramki rozdmuchania i reczna akceptacja proby (19.8).

Obieg zmierzony WYKONANIEM (stub modelu z `test_cache_powtorki`, ktory zawsze
rozdmuchuje sekcje; `runtime/` i `skrypty/` w katalogu tymczasowym):

  1. Sekcja ubita po powtorce zostawia DWA artefakty `odrzut_*.md` z metadanymi
     i przekladem z przywroconymi `{placeholderami}`.
  2. `przyjmij_probe` na poprawionym artefakcie: twarde bramki od nowa, wpis
     w magazynie sekcji przyjetych, wiersz w rejestrze ilorazow, artefakty
     skasowane.
  3. Nastepny zwykly przebieg bierze sekcje z magazynu - ZERO wywolan modelu.
  4. Odmowy: artefakt po zmianie polskiego zrodla, artefakt ze zgubionym
     placeholderem, zepsuty wpis magazynu (sekcja staje zamiast placic).
  5. Sygnal progu: dwie przyjete sekcje ponad prog jezyka => sugestia wpisu
     `prog_rozdmuchania` do `jezyki_docelowe.yaml`.

Uruchom:  .venv/Scripts/python -m pytest test_przyjmij_probe.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_przyjmij_probe.py
"""

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import buduj_wielojezyczne_docs as bd
import test_cache_powtorki as tcp

KLUCZ = bd.KLUCZ_LEGACY


@contextlib.contextmanager
def _srodowisko():
    """Stub + `RUNTIME_DIR` z `test_cache_powtorki`, plus `skrypty/` obok."""
    with tcp._srodowisko() as katalog:
        stary = bd.KATALOG_ODRZUTOW
        bd.KATALOG_ODRZUTOW = katalog / "skrypty"
        try:
            yield katalog
        finally:
            bd.KATALOG_ODRZUTOW = stary


def _cicho(funkcja, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        wynik = funkcja(*args, **kwargs)
    return wynik, buf.getvalue()


def _przyjmij(proba: int, tresc: str = tcp.TRESC_PL):
    return _cicho(bd.przyjmij_probe, tcp.KOD, "test.yaml", tcp.RDZEN, KLUCZ,
                  tresc, proba)


def _artefakt(proba: int) -> Path:
    return bd.sciezka_odrzutu(tcp.KOD, tcp.RDZEN, KLUCZ, proba)


def _popraw(proba: int) -> None:
    """Czlowiek usuwa dosypke z proby — zostaje przeklad bez rozdmuchania."""
    sciezka = _artefakt(proba)
    tresc = sciezka.read_text(encoding="utf-8").replace(tcp.DOSYPKA.strip(), "")
    sciezka.write_text(tresc, encoding="utf-8")


def test_ubita_sekcja_zostawia_dwa_artefakty():
    with _srodowisko():
        (ok, log), = [tcp._przebieg()]
        assert not ok
        for proba in (1, 2):
            meta, tekst = bd.wczytaj_odrzut(_artefakt(proba))
            assert meta["proba"] == proba and meta["zarzuty"], meta
            assert meta["iloraz"] > bd.PROG_ROZDMUCHANIA, meta
            assert "{nazwa_projektu}" in tekst, "placeholdery maja wrocic"
        assert "--przyjmij-probe" in log, log


def test_pelny_obieg_przyjecia():
    with _srodowisko() as katalog:
        tcp._przebieg()
        _popraw(2)
        ok, log = _przyjmij(2)
        assert ok, log
        assert not _artefakt(1).exists() and not _artefakt(2).exists()
        wpis = json.loads(bd.sciezka_przyjetej(
            bd._cache_key_sekcji(tcp.RDZEN, KLUCZ, tcp.KOD)).read_text(encoding="utf-8"))
        assert wpis["proba"] == 2 and wpis["iloraz"] <= bd.PROG_ROZDMUCHANIA
        rejestr = (katalog / "ilorazy_przyjete.jsonl").read_text(encoding="utf-8")
        assert len(rejestr.splitlines()) == 1

        tcp._licznik["blok"] = 0
        ok, log = tcp._przebieg()
        assert ok, log
        assert tcp._licznik["blok"] == 0, "przyjeta sekcja nie ma prawa placic za API"
        assert "accepted sections" in log, log


def test_artefakt_po_zmianie_zrodla_jest_odrzucany():
    with _srodowisko():
        tcp._przebieg()
        _popraw(1)
        ok, log = _przyjmij(1, tresc=tcp.TRESC_PL + "Nowe zdanie.\n")
        assert not ok and "changed" in log, log


def test_zgubiony_placeholder_blokuje_przyjecie():
    with _srodowisko():
        tcp._przebieg()
        _popraw(1)
        sciezka = _artefakt(1)
        sciezka.write_text(sciezka.read_text(encoding="utf-8")
                           .replace("{liczba_znakow}", "wiele"), encoding="utf-8")
        ok, log = _przyjmij(1)
        assert not ok and "placeholders" in log, log
        assert sciezka.exists(), "artefakt zostaje do poprawki"


def test_zepsuty_wpis_magazynu_zatrzymuje_sekcje():
    with _srodowisko():
        tcp._przebieg()
        _popraw(1)
        _przyjmij(1)
        plik = bd.sciezka_przyjetej(bd._cache_key_sekcji(tcp.RDZEN, KLUCZ, tcp.KOD))
        wpis = json.loads(plik.read_text(encoding="utf-8"))
        wpis["tekst"] = wpis["tekst"].replace("{nazwa_projektu}", "")
        plik.write_text(json.dumps(wpis), encoding="utf-8")
        tcp._licznik["blok"] = 0
        ok, log = tcp._przebieg()
        assert not ok and "hard gates" in log, log
        assert tcp._licznik["blok"] == 0


def test_powtorka_na_twardej_bramce_nie_zabiera_proby_1():
    """Proba 1 rozdmuchana, powtorka gubi marker ⟦i⟧ -> proba 1 zostaje w `skrypty/`."""
    def _stub(klient, *, model, system, messages, **_kw):
        tresc = messages[0]["content"]
        if tcp.NAGLOWEK_NACISKU in system:
            return bd.TOKEN_REGEX.sub("", tresc), "end_turn"   # zlamana parzystosc
        return tresc + tcp.DOSYPKA, "end_turn"

    with _srodowisko():
        stary = tcp.cl.wywolaj_llm
        tcp.cl.wywolaj_llm = _stub
        try:
            ok, log = tcp._przebieg()
        finally:
            tcp.cl.wywolaj_llm = stary
        assert not ok and "BROKEN parity" in log, log
        assert _artefakt(1).exists(), log
        assert not _artefakt(2).exists(), "proba 2 nie doszla do etapu zarzutow"
        assert "--przyjmij-probe <1>" in log, log


def _z_stubem(stub):
    """Podmienia model na czas bloku (poza stubem z `test_cache_powtorki`)."""
    @contextlib.contextmanager
    def _cm():
        stary = tcp.cl.wywolaj_llm
        tcp.cl.wywolaj_llm = stub
        try:
            yield
        finally:
            tcp.cl.wywolaj_llm = stary
    return _cm()


def _echo(klient, *, messages, **_kw):
    return messages[0]["content"], "end_turn"


def test_wpis_dla_starszego_zrodla_jest_ignorowany():
    """Luka audytu: bez kontroli odcisku stary przekład szedłby po cichu do pliku."""
    with _srodowisko():
        tcp._przebieg()
        _popraw(1)
        _przyjmij(1)
        tcp._licznik["blok"] = 0
        ok, log = _cicho(
            bd._tlumacz_pojedyncza_sekcje, tcp.KOD, tcp.NAZWA_PL, None, "test.yaml",
            tcp.RDZEN, KLUCZ, tcp.TRESC_PL + "Nowe zdanie źródła.\n",
            dry_run=False, model="stub", prompt_dodatkowy="")
        assert "OLDER" in log, log
        assert tcp._licznik["blok"] > 0, "nieaktualny wpis nie ma prawa zastąpić API"


@pytest.mark.parametrize("zmiana,fraza", [
    (lambda t: "[PONIŻEJ PRZEKŁAD SEKCJI DLA CZYTELNIKA]\n" + t, "marker"),
    (lambda t: t + "\n## Nagłówek, którego źródło nie ma\n", ""),
])
def test_bramki_przyjetego_tekstu_widza_preambule_i_strukture(zmiana, fraza):
    problemy = bd.bramki_przyjetego_tekstu(tcp.TRESC_PL, zmiana(tcp.TRESC_PL))
    assert problemy, "bramka przepuściła zepsuty tekst"
    assert fraza in " ".join(problemy)


def test_blad_api_w_powtorce_nie_zabiera_proby_1():
    def _stub(klient, *, system, messages, **_kw):
        if tcp.NAGLOWEK_NACISKU in system:
            raise RuntimeError("simulated API error")
        return messages[0]["content"] + tcp.DOSYPKA, "end_turn"

    with _srodowisko(), _z_stubem(_stub):
        ok, log = tcp._przebieg()
        assert not ok and _artefakt(1).exists(), log
        assert not _artefakt(2).exists()


def test_bramka_struktury_w_powtorce_nie_zabiera_proby_1():
    def _stub(klient, *, system, messages, **_kw):
        tresc = messages[0]["content"]
        if tcp.NAGLOWEK_NACISKU in system:
            return tresc + "\n## Nagłówek, którego źródło nie ma\n", "end_turn"
        return tresc + tcp.DOSYPKA, "end_turn"

    with _srodowisko(), _z_stubem(_stub):
        ok, log = tcp._przebieg()
        assert not ok and "structural fingerprint" in log, log
        assert _artefakt(1).exists()


def test_sukces_kasuje_odrzuty_z_wczesniejszego_przebiegu():
    """F4 audytu: stary odrzut po sukcesie dałby się przyjąć i nadpisać dobry przekład."""
    with _srodowisko():
        tcp._przebieg()
        assert _artefakt(1).exists() and _artefakt(2).exists()
        with _z_stubem(_echo):
            ok, log = tcp._przebieg()
        assert ok, log
        assert not _artefakt(1).exists() and not _artefakt(2).exists()


def test_zapis_pliku_konsumuje_wpis_magazynu(tmp_path):
    """Luka audytu: wpis przyjęty zostaje skonsumowany razem z cache'em sekcji."""
    with _srodowisko():
        tcp._przebieg()
        _popraw(1)
        _przyjmij(1)
        plik = bd.sciezka_przyjetej(bd._cache_key_sekcji(tcp.RDZEN, KLUCZ, tcp.KOD))
        assert plik.exists()
        stary, stary_root = bd.DICT_DIR, bd.ROOT
        bd.DICT_DIR, bd.ROOT = tmp_path, tmp_path   # log liczy ścieżkę względem ROOT
        try:
            ok, log = _cicho(bd.tlumacz_szablon, tcp.KOD, tcp.NAZWA_PL, "Suomi", None,
                             f"{tcp.RDZEN}.yaml", "test", {KLUCZ: tcp.TRESC_PL},
                             skip_existing=False, dry_run=False, model="stub")
        finally:
            bd.DICT_DIR, bd.ROOT = stary, stary_root
        assert ok, log
        assert not plik.exists(), "wpis magazynu przeżył zapis pliku"


def test_sygnal_progu_po_dwoch_przyjeciach_ponad_prog():
    with _srodowisko():
        for _ in range(2):
            bd.sciezka_przyjetej(
                bd._cache_key_sekcji(tcp.RDZEN, KLUCZ, tcp.KOD)).unlink(missing_ok=True)
            tcp._przebieg()
            ok, log = _przyjmij(2)   # BEZ poprawki: rozdmuchana, ale przyjeta
            assert ok and "ABOVE" in log, log
        assert "prog_rozdmuchania:" in log, log


# Uruchomienie jako skrypt - deleguje do pytesta (kanon v19.2.1, §6.11).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
