"""
test_patch_dev.py - Regresja: skrocona procedura wydawnicza przestaje byc
niewidzialna dla kogos pracujacego ZE ZRODLA (18.32).

Trzy kontrakty, wszystkie mierzone przez WYKONANIE (stub `urlopen`, zero sieci,
pliki w katalogu tymczasowym):

  1. SLEPOTA I JEJ NAPRAWA W JEDNYM TESCIE. Gdy tag przesunie sie BEZ bumpa
     numeru, `sprawdz_aktualizacje` z definicji milczy (porownuje wersje, a te
     sa rowne) — i to jest udokumentowane asercja, nie zalozeniem. Sygnal ma dac
     `sprawdz_patch_dev`, porownujac licznik z `patch_dev.json` w drzewie
     z tym przy tagu.
  2. CISZA JEST ZAKAZANA, ALE TYLKO ZE ZRODLA. Brak pliku, plik niepoprawny albo
     opisujacy INNA wersje niz VERSION = glosno na stderr i pominiecie kroku.
     W aplikacji ZAMROZONEJ krok nie odpala sie wcale i nie wykonuje ZADNEGO
     zapytania — pliku nie ma w bundlu, a end-user nie ma z dev-toolingu nic.
  3. DWIE BRAMKI-LUSTRA. Pelne wydanie wymaga licznika wyzerowanego dla swojej
     wersji (`build_release`), a klasyfikacja zaleznosci rozdziela decyzje
     (nowsze wydanie wykluczone granica) od zaniedbania (nowsze dopuszczone).

Uruchom:  .venv/Scripts/python test_patch_dev.py
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import audyt_zaleznosci as az
import build_release as br
import core_updater as cu

WERSJA = "18.31.0"


class _OdpowiedzStub:
    """Minimalny odpowiednik obiektu z `urlopen` (context manager + `read`)."""

    def __init__(self, tresc: str):
        self._tresc = tresc.encode("utf-8")

    def read(self, ile: int | None = None) -> bytes:
        return self._tresc if ile is None else self._tresc[:ile]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@contextlib.contextmanager
def _srodowisko(*, licznik_lokalny=0, wersja_pliku=WERSJA, licznik_zdalny=None,
                tresc_lokalna=None, bez_pliku=False, zdalny_status=None,
                wersja_apki=WERSJA):
    """Podstawia `patch_dev.json`, VERSION i `urlopen`. Zwraca licznik wywolan sieci."""
    katalog = Path(tempfile.mkdtemp())
    licznik_wywolan = {"sieć": 0}

    plik = katalog / "patch_dev.json"
    if not bez_pliku:
        plik.write_text(
            tresc_lokalna if tresc_lokalna is not None
            else json.dumps({"wersja": wersja_pliku, "patch_dev": licznik_lokalny}),
            encoding="utf-8")
    plik_wersji = katalog / "VERSION"
    plik_wersji.write_text(wersja_apki, encoding="utf-8")

    def _stub(req, timeout=None):
        licznik_wywolan["sieć"] += 1
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if zdalny_status is not None:
            from urllib.error import HTTPError
            raise HTTPError(url, zdalny_status, "stub", {}, None)
        if url.endswith("patch_dev.json"):
            return _OdpowiedzStub(json.dumps(
                {"wersja": WERSJA, "patch_dev": licznik_zdalny}))
        # `releases/latest` — wydanie o TEJ SAMEJ wersji, czyli dokladnie
        # sytuacja skroconej procedury: tag sie przesunal, numer nie.
        return _OdpowiedzStub(json.dumps({
            "tag_name": f"v{WERSJA}",
            "html_url": "https://example.invalid/release",
            "zipball_url": "https://example.invalid/zip",
            "body": "-",
            "assets": [{"name": "rezyser_audio_installer.exe",
                        "browser_download_url": "https://example.invalid/exe",
                        "size": 1}],
        }))

    stare = (cu._SCIEZKA_PATCH_DEV, cu._SCIEZKA_VERSION, cu.urllib.request.urlopen)
    cu._SCIEZKA_PATCH_DEV = plik
    cu._SCIEZKA_VERSION = plik_wersji
    cu.urllib.request.urlopen = _stub
    try:
        yield licznik_wywolan
    finally:
        (cu._SCIEZKA_PATCH_DEV, cu._SCIEZKA_VERSION,
         cu.urllib.request.urlopen) = stare
        shutil.rmtree(katalog, ignore_errors=True)


def _przebieg(funkcja):
    """(wynik, tekst stderr) — kanałem tego sprawdzenia jest wyłącznie stderr."""
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        wynik = funkcja()
    return wynik, buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Slepota porownania wersji i sygnal z licznika
# ---------------------------------------------------------------------------
def test_porownanie_wersji_milczy_o_przesunietym_tagu():
    """Kontrakt-dokumentacja: `sprawdz_aktualizacje` z definicji tego nie widzi."""
    with _srodowisko(licznik_lokalny=0, licznik_zdalny=1):
        assert cu.sprawdz_aktualizacje() is None, (
            "wydanie o TEJ SAMEJ wersji nie moze byc zgloszone jako nowa wersja")


def test_licznik_wykrywa_nowszy_dev_patch():
    """Licznik zdalny wyzszy = info plus jedna linia na stderr z instrukcja."""
    with _srodowisko(licznik_lokalny=0, licznik_zdalny=2):
        info, log = _przebieg(cu.sprawdz_patch_dev)
        assert info is not None, log
        assert (info.lokalny, info.zdalny) == (0, 2), info
        assert "NEWER DEV TOOLING" in log, log
        assert "git fetch" in log and "Source code" in log, log
        assert f"releases/tag/v{WERSJA}" in info.url_tagu, info.url_tagu


def test_rowny_licznik_nie_halasuje():
    """Ten sam licznik = brak wyniku i ZERO wyjscia (to jest stan normalny)."""
    with _srodowisko(licznik_lokalny=3, licznik_zdalny=3):
        info, log = _przebieg(cu.sprawdz_patch_dev)
        assert info is None
        assert log == "", f"stan normalny ma milczec, a wypisal: {log!r}"


def test_starszy_licznik_zdalny_nie_halasuje():
    """Drzewo przed origin (praca w toku) — nie jest to nic do zgloszenia."""
    with _srodowisko(licznik_lokalny=5, licznik_zdalny=4):
        info, log = _przebieg(cu.sprawdz_patch_dev)
        assert info is None and log == "", log


# ---------------------------------------------------------------------------
# 2. Cisza zakazana ze zrodla, calkowita w aplikacji zamrozonej
# ---------------------------------------------------------------------------
def test_frozen_nie_sprawdza_i_nie_pyta_sieci():
    with _srodowisko(licznik_lokalny=0, licznik_zdalny=9) as licznik:
        sys.frozen = True                      # type: ignore[attr-defined]
        try:
            info, log = _przebieg(cu.sprawdz_patch_dev)
        finally:
            del sys.frozen                     # type: ignore[attr-defined]
        assert info is None and log == "", log
        assert licznik["sieć"] == 0, "aplikacja zamrozona nie ma prawa pytac sieci"


def test_brak_pliku_mowi_glosno():
    with _srodowisko(bez_pliku=True, licznik_zdalny=1) as licznik:
        info, log = _przebieg(cu.sprawdz_patch_dev)
        assert info is None
        assert "patch_dev.json is missing" in log, log
        assert licznik["sieć"] == 0, "bez licznika lokalnego nie ma co porownywac"


def test_zepsuty_plik_mowi_glosno():
    with _srodowisko(tresc_lokalna="{to nie json", licznik_zdalny=1):
        info, log = _przebieg(cu.sprawdz_patch_dev)
        assert info is None
        assert "unreadable" in log, log


def test_licznik_z_innej_wersji_mowi_glosno():
    """VERSION podbity, licznik niewyzerowany — ta sama niespojnosc, co w bramce."""
    with _srodowisko(wersja_pliku="18.30.0", licznik_lokalny=2, licznik_zdalny=3):
        info, log = _przebieg(cu.sprawdz_patch_dev)
        assert info is None
        assert "describes version" in log and "18.30.0" in log, log


def test_tag_bez_pliku_mowi_i_nie_zglasza():
    """Wydanie sprzed licznika (HTTP 404 na raw) — nota, nie alarm."""
    with _srodowisko(licznik_lokalny=0, zdalny_status=404):
        info, log = _przebieg(cu.sprawdz_patch_dev)
        assert info is None
        assert "carries no patch_dev.json" in log, log


def test_wersja_wip_nie_pyta_sieci():
    """VERSION z sufiksem nie ma tagu na origin — jedna nota, ZERO zapytan.

    Licznik jest przy tym uznany za zgodny (18.32.0 kontra 18.32.0-WIP), bo
    nalezy do NUMERU, nie do etapu pracy: inaczej caly cykl WIP maintainera
    konczylby sie ostrzezeniem o niezgodnosci przy kazdym starcie aplikacji.
    """
    with _srodowisko(wersja_apki="18.32.0-WIP", wersja_pliku="18.32.0",
                     licznik_lokalny=0, licznik_zdalny=7) as licznik:
        info, log = _przebieg(cu.sprawdz_patch_dev)
        assert info is None
        assert "carries a suffix" in log, log
        assert "describes version" not in log, f"licznik mial byc uznany za zgodny: {log}"
        assert licznik["sieć"] == 0, "wersja WIP nie ma prawa pytac sieci"


# ---------------------------------------------------------------------------
# 3. Bramki-lustra: zerowanie przy pelnym wydaniu, klasyfikacja zaleznosci
# ---------------------------------------------------------------------------
def _z_plikiem_patch_dev(tresc: str, wersja: str):
    katalog = Path(tempfile.mkdtemp())
    plik = katalog / "patch_dev.json"
    plik.write_text(tresc, encoding="utf-8")
    stara = br.PLIK_PATCH_DEV
    br.PLIK_PATCH_DEV = plik
    try:
        return br.sprawdz_licznik_patch_dev(wersja)
    finally:
        br.PLIK_PATCH_DEV = stara
        shutil.rmtree(katalog, ignore_errors=True)


def test_pelne_wydanie_wymaga_zerowego_licznika():
    zgodny = json.dumps({"wersja": "18.32.0", "patch_dev": 0})
    assert _z_plikiem_patch_dev(zgodny, "18.32.0") is None

    powod = _z_plikiem_patch_dev(json.dumps({"wersja": "18.32.0", "patch_dev": 2}),
                                 "18.32.0")
    assert powod and "reset" in powod, powod

    powod = _z_plikiem_patch_dev(zgodny, "18.33.0")
    assert powod and "describes version" in powod, powod


def test_klasyfikacja_zaleznosci_rozdziela_decyzje_od_zaniedbania():
    """Granica = decyzja podjeta (nie trafienie), brak granicy = zaniedbanie."""
    narzedzia = az._packaging()
    assert narzedzia is not None, "test wymaga `packaging` (jest w requirements)"

    aktualne = az.rozstrzygnij(az.Wpis("x", ""), "1.2.3", "1.2.3", "", narzedzia)
    assert (aktualne.status, aktualne.trafienie) == ("aktualne", False)

    granica = az.rozstrzygnij(az.Wpis("anthropic", "<1"), "0.109.2", "1.5.0", "",
                              narzedzia)
    assert (granica.status, granica.trafienie) == ("granica", False), granica

    nowsza = az.rozstrzygnij(az.Wpis("tiktoken", ""), "0.12.0", "0.14.0", "",
                             narzedzia)
    assert (nowsza.status, nowsza.trafienie) == ("nowsza", True), nowsza

    # Granica, ktora nowszego wydania NIE wyklucza (minor pod majorem), musi
    # zostac trafieniem — inaczej `elevenlabs<3` uciszalby 15 zaleglych minorow.
    luzna = az.rozstrzygnij(az.Wpis("elevenlabs", "<3"), "2.52.0", "2.67.0", "",
                            narzedzia)
    assert (luzna.status, luzna.trafienie) == ("nowsza", True), luzna

    brak = az.rozstrzygnij(az.Wpis("y", ""), None, "1.0.0", "", narzedzia)
    assert (brak.status, brak.trafienie) == ("brak", True), brak

    nieznane = az.rozstrzygnij(az.Wpis("z", ""), "1.0.0", None, "DNS down",
                               narzedzia)
    assert (nieznane.status, nieznane.trafienie) == ("nieznane", False), nieznane


def test_manifest_ma_granice_na_pieciu_pakietach():
    """Granice sa czescia kontraktu, nie ozdoba — trzymamy je pod asercja."""
    oczekiwane = {"wxpython": "<4.3", "anthropic": "<1", "openai": "<3",
                  "elevenlabs": "<3", "lingua-language-detector": "<2.2"}
    manifest = {w.nazwa: w.specyfikator for w in az.wczytaj_manifest()}
    for nazwa, granica in oczekiwane.items():
        assert manifest.get(nazwa) == granica, (
            f"{nazwa}: oczekiwana granica {granica}, jest {manifest.get(nazwa)!r}")


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
