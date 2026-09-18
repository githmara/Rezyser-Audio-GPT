"""
test_bramka_zaleznosci.py - Krok 6b4 builda: blokada domyslna, --no-strict cisza
(v19.4).

Do v19.3.1 bramka zaleznosci TYLKO OSTRZEGALA. Rozumowanie za tym bylo poprawne
(nowe wydanie upstreamu nie mowi nic o poprawnosci NASZEGO kodu), ale wniosek
zly: ostrzezenie jest jedna linia w kilkusetlinijkowym logu buildu, a build trwa
minuty - wiec kolejnosc zdarzen wychodzila odwrotna do zamierzonej. Zmierzone
2026-09-17: maintainer zbudowal instalator, po przejrzeniu logu skasowal go,
a przedmiotem byl `openai` 3.14.1 -> 3.15.0 dopuszczony granica `<4`.

Testy pilnuja piecu wlasnosci, wszystkie mierzone WYKONANIEM na PODSTAWIONYM
wyniku audytu (zero sieci, zero PyPI - inaczej test mierzylby stan swiata,
a nie kontrakt bramki):
  1. JEDNA DEFINICJA SLOWA „STRICT" - `audyt_zaleznosci.strict_przechodzi` jest
     wolane i przez CLI (`--strict`), i przez build. Dwie kopie warunku
     rozjechalyby sie w pierwszej edycji, a wlasnie rozjazd („strict" znaczylo
     w buildzie cos lzejszego) kosztowal ten wyrzucony instalator;
  2. DEGRADACJA JEST NIEPOWODZENIEM - „nie wiem, czy czeka upgrade" to nie to
     samo co „nie czeka", a przedmiotem bramki jest ZAMROZENIE wersji;
  3. BLOKADA MA INNY TON NIZ FATAL - komunikat nie moze nazywac tego usterka
     naszego kodu, bo nia nie jest; musi za to podac furtke `--no-strict`;
  4. `--no-strict` NIE ODPALA AUDYTU W OGOLE - nie „odpala i ignoruje". Test
     podstawia `bramka()`, ktora rzuca przy wywolaniu: jesli bramka ja tknie,
     test padnie. Zostaje jedna linia o pominieciu (standard „zero ciszy");
  5. BRAK MODULU AUDYTU TEZ BLOKUJE - ta galaz do v19.3.1 pisala „SKIPPED"
     i szla dalej, czyli byla dziura o ksztalcie dokladnie tej klasy, ktora
     bramka sciga.

DRUGA CZESC PLIKU to drugi koniec tej samej decyzji: `sync_dev_release.
manifest_tylko_granice`. Kanon zachowawczy ma wariant „przywroc zamrozona
wersje, zostaw stala granice, wydaj DEV PATCH", a ten wariant byl mechanicznie
niewykonalny — `requirements.txt` stoi w `PREFIKSY_NIE_DEV`, wiec sam zapis
decyzji blokowal skrocona procedure. Zawezenie jest waskie i sprawdzalne
z samego gita (runner nie ma naszych zaleznosci): ZBIOR NAZW pakietow musi byc
identyczny, zmieniac sie moga tylko specyfikatory. Testy robia prawdziwe repo
w katalogu tymczasowym, bo przedmiotem jest zachowanie GITA, nie regexa.

Uruchom:  .venv/Scripts/python test_bramka_zaleznosci.py
"""

import argparse
import builtins
import contextlib
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

_KORZEN = Path(__file__).parent
sys.path.insert(0, str(_KORZEN / ".github" / "scripts"))
sys.path.insert(0, str(_KORZEN))

import audyt_zaleznosci as az
import build_release as br
import sync_dev_release as sdr


def _stan(nazwa: str, status: str, zainstalowana="1.0.0", najnowsza="1.1.0",
          spec="<2") -> az.Stan:
    return az.Stan(nazwa=nazwa, specyfikator=spec, zainstalowana=zainstalowana,
                   najnowsza=najnowsza, status=status)


def _uruchom(wynik: az.WynikBramki | None, *, no_strict: bool = False,
             wysadz_audyt: bool = False) -> tuple[str, int | None]:
    """Odpala krok 6b4 na PODSTAWIONYM audycie. Zwraca (log, kod wyjscia)."""
    oryginalna = az.bramka

    def _podstawiona(*_a, **_kw):
        if wysadz_audyt:
            raise AssertionError(
                "--no-strict touched the audit; it must not run it at all")
        return wynik

    az.bramka = _podstawiona
    bufor = io.StringIO()
    kod: int | None = None
    try:
        with contextlib.redirect_stdout(bufor):
            try:
                br._bramka_zaleznosci_lub_przerwij(
                    argparse.Namespace(no_strict=no_strict))
            except SystemExit as exc:
                kod = exc.code if isinstance(exc.code, int) else 1
    finally:
        az.bramka = oryginalna
    return bufor.getvalue(), kod


def test_strict_przechodzi_jest_jedynym_warunkiem():
    """Werdykt STRICT: czysto ORAZ bez degradacji. Zadne dwa z trzech."""
    czysty = az.WynikBramki(czysto=True, stany=[_stan("anthropic", "aktualne")])
    assert az.strict_przechodzi(czysty)
    assert not az.strict_przechodzi(
        az.WynikBramki(czysto=False, stany=[_stan("openai", "nowsza")]))
    assert not az.strict_przechodzi(
        az.WynikBramki(czysto=True, stany=[], degradacja="no network"))


def test_granica_nie_blokuje_buildu():
    """`granica` to DECYZJA, nie trafienie — build musi przejsc.

    Gdyby blokowala, kanon zachowawczy („wydajemy jak jest, granica o stopien
    nizej, migracja po wydaniu") bylby niewykonalny: sam zapis decyzji
    zatrzymywalby build, ktory ta decyzja ma odblokowac.
    """
    log, kod = _uruchom(az.WynikBramki(
        czysto=True,
        stany=[_stan("lingua-language-detector", "granica",
                     zainstalowana="2.2.0", najnowsza="2.3.0", spec="<2.3")]))
    assert kod is None, log
    assert "✅" in log and "bounded on purpose" in log, log


def test_nowsza_dopuszczona_blokuje_ale_nie_tonem_fatal():
    """Blokada + inny ton + wskazanie furtki `--no-strict`."""
    log, kod = _uruchom(az.WynikBramki(
        czysto=False,
        stany=[_stan("openai", "nowsza", zainstalowana="3.14.1",
                     najnowsza="3.15.0", spec="<4")]))
    assert kod == 1, log
    assert "FATAL" not in log, f"ton fatalny w komunikacie nie-naszej winy:\n{log}"
    assert "⛔" in log and "nothing in our code is broken" in log, log
    assert "openai: 3.14.1 → 3.15.0" in log, log
    assert "--no-strict" in log, log


def test_degradacja_blokuje_z_wlasnym_zdaniem():
    """Brak sieci/`packaging` = „nie wiem", a to nie jest „nic nie czeka"."""
    log, kod = _uruchom(az.WynikBramki(
        czysto=True, stany=[_stan("openai", "nieznane")],
        degradacja="1/1 package(s) could not be compared against PyPI"))
    assert kod == 1, log
    assert "could not complete" in log, log


def test_brak_pakietu_blokuje_i_mowi_o_srodowisku():
    """`brak` to rozjazd SRODOWISKA z manifestem — inna rada niz upgrade."""
    log, kod = _uruchom(az.WynikBramki(
        czysto=False,
        stany=[_stan("markdown", "brak", zainstalowana=None, najnowsza=None,
                     spec="")]))
    assert kod == 1, log
    assert "NOT installed here" in log, log


def test_no_strict_nie_tyka_audytu():
    """Pominiecie jest CALKOWITE: zero wywolan, zero tabeli, jedna linia noty."""
    log, kod = _uruchom(None, no_strict=True, wysadz_audyt=True)
    assert kod is None, log
    assert "SKIPPED entirely (--no-strict)" in log, log
    # Zaden stan pakietu nie moze wejsc do logu hotfixa — o tym wlasnie
    # zdecydowano, ze sie nie reaguje.
    for slowo in ("openai", "up to date", "bound", "PyPI..."):
        assert slowo not in log, f"{slowo!r} w logu --no-strict:\n{log}"


def test_brak_modulu_audytu_blokuje():
    """Nieimportowalny audyt = „nie wiem", wiec blokada, nie ciche przejscie."""
    oryginalny_import = builtins.__import__

    def _import(nazwa, *args, **kwargs):
        if nazwa == "audyt_zaleznosci":
            raise ImportError("patched for this test")
        return oryginalny_import(nazwa, *args, **kwargs)

    zapisany = sys.modules.pop("audyt_zaleznosci", None)
    builtins.__import__ = _import
    bufor = io.StringIO()
    kod: int | None = None
    try:
        with contextlib.redirect_stdout(bufor):
            try:
                br._bramka_zaleznosci_lub_przerwij(
                    argparse.Namespace(no_strict=False))
            except SystemExit as exc:
                kod = exc.code if isinstance(exc.code, int) else 1
    finally:
        builtins.__import__ = oryginalny_import
        if zapisany is not None:
            sys.modules["audyt_zaleznosci"] = zapisany
    log = bufor.getvalue()
    assert kod == 1, log
    assert "could not even start" in log and "--no-strict" in log, log


def test_flaga_jest_w_cli_i_domyslnie_wylaczona():
    """`--no-strict` istnieje, a brak flagi znaczy STRICT (nie odwrotnie)."""
    oryginalne_argv = sys.argv
    try:
        sys.argv = ["build_release.py"]
        assert br._parsuj_argumenty().no_strict is False
        sys.argv = ["build_release.py", "--no-strict"]
        assert br._parsuj_argumenty().no_strict is True
    finally:
        sys.argv = oryginalne_argv


# ---------------------------------------------------------------------------
# Wyjatek `requirements.txt` w skroconej procedurze (v19.4.0)
# ---------------------------------------------------------------------------
NL = chr(10)


def _manifest(*linie: str) -> str:
    """Sklada tresc `requirements.txt` z podanych linii (bez escapowania)."""
    return NL.join(linie) + NL


def _sprzataj(katalog: Path) -> None:
    """Usuwa repo tymczasowe — z odblokowaniem read-only obiektow `.git/`.

    Goly `rmtree` z `ignore_errors` NIE wystarcza i to jest zmierzone: po
    dwoch seriach testow w `%TEMP%` zostawalo 5 z 6 repo, bo pliki
    w `.git/objects/` sa na Windows read-only, a tlumienie bledow zjada
    `PermissionError` w milczeniu. `onexc` (nie `onerror` — ten wypadl
    w Pythonie 3.14) zdejmuje flage i ponawia.
    """
    def _odblokuj(func, sciezka, _wyjatek):
        try:
            os.chmod(sciezka, stat.S_IWRITE)
            func(sciezka)
        except OSError:
            pass

    shutil.rmtree(katalog, onexc=_odblokuj)


def _repo_z_manifestem(przed: str, po: str) -> Path:
    """Repo tymczasowe: tag `v1.0` z `przed`, HEAD z `po`."""
    katalog = Path(tempfile.mkdtemp(prefix="test_manifest_"))

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=katalog, check=True,
                       capture_output=True)

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "test")
    (katalog / "requirements.txt").write_text(przed, encoding="utf-8")
    git("add", "requirements.txt")
    git("commit", "-qm", "pierwszy")
    git("tag", "v1.0")
    (katalog / "requirements.txt").write_text(po, encoding="utf-8")
    git("add", "requirements.txt")
    git("commit", "-qm", "drugi")
    return katalog


def _tylko_granice(przed: str, po: str) -> bool:
    """Werdykt `manifest_tylko_granice` na PRAWDZIWYM repo (przedmiotem jest git).

    `sync_dev_release.ROOT` jest relatywne (`Path(".")`), wiec test wchodzi do
    katalogu repo — tak samo jak skrypt na runnerze, ktory chodzi z korzenia
    checkoutu.
    """
    katalog = _repo_z_manifestem(przed, po)
    poprzedni_cwd = os.getcwd()
    try:
        os.chdir(katalog)
        with contextlib.redirect_stdout(io.StringIO()):
            return sdr.manifest_tylko_granice("v1.0")
    finally:
        # Sprzatamy ZAWSZE: bez tego kazdy przebieg pytesta zostawial
        # w %TEMP% repo gitowe (zmierzone 15 katalogow po dwoch seriach).
        os.chdir(poprzedni_cwd)
        _sprzataj(katalog)


def test_parser_manifestu_widzi_nazwe_i_specyfikator():
    """Komentarze, puste linie, `-r` i extras nie moga wejsc do porownania."""
    wynik = sdr.pakiety_manifestu(_manifest(
        "# naglowek", "", "openai<4", "uvicorn[standard]>=1,<2",
        "-r inny.txt", "ruamel.yaml", "WxPython<4.4  # komentarz na koncu"))
    assert wynik == {"openai": "<4", "uvicorn": ">=1,<2",
                     "ruamel.yaml": "", "wxpython": "<4.4"}, wynik


def test_sama_granica_nie_wyklucza_dev_patcha():
    """Wariant 5 kanonu zachowawczego: `openai<4` → `openai<3.15`."""
    assert _tylko_granice(_manifest("openai<4", "pyyaml"),
                          _manifest("openai<3.15", "pyyaml"))


def test_dodanie_pakietu_wyklucza():
    """Nowa nazwa = drzewo zrodlowe wymaga innego srodowiska → pelna procedura."""
    assert not _tylko_granice(_manifest("openai<4"),
                              _manifest("openai<4", "httpx"))


def test_usuniecie_pakietu_wyklucza():
    assert not _tylko_granice(_manifest("openai<4", "httpx"),
                              _manifest("openai<4"))


def test_zmiana_samych_komentarzy_nie_jest_zmiana_granicy():
    """Nie klamiemy, ze „ruszylismy granice", gdy nie ruszylismy niczego.

    Bez tego warunku nota w logu skroconej procedury („wylacznie granice
    istniejacych pakietow") bylaby falszywa diagnostyka przy diffie, ktory
    granic nie tyka.
    """
    assert not _tylko_granice(_manifest("openai<4"),
                              _manifest("# nowy komentarz", "openai<4"))


def test_brak_manifestu_w_tagu_idzie_na_strone_ostrozna():
    """„Nie wiem" = pelna procedura, nie dev patch."""
    katalog = Path(tempfile.mkdtemp(prefix="test_manifest_pusty_"))

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=katalog, check=True,
                       capture_output=True)

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "test")
    (katalog / "inny.txt").write_text("x" + NL, encoding="utf-8")
    git("add", "inny.txt")
    git("commit", "-qm", "bez manifestu")
    git("tag", "v1.0")
    poprzedni_cwd = os.getcwd()
    try:
        os.chdir(katalog)
        with contextlib.redirect_stdout(io.StringIO()):
            assert sdr.manifest_tylko_granice("v1.0") is False
    finally:
        os.chdir(poprzedni_cwd)
        _sprzataj(katalog)


def test_klasyfikacja_uzywa_wyjatku_tylko_dla_manifestu():
    """`pliki_runtime_w_zakresie`: manifest z samymi granicami nie jest winowajca.

    Podstawiamy oba wejscia (diff i domkniecie importow), bo przedmiotem jest
    GALAZ decyzyjna, a nie stan tego repozytorium.
    """
    oryginalne = (sdr.uruchom, sdr.domkniecie_runtime,
                  sdr.manifest_tylko_granice)
    try:
        sdr.uruchom = lambda cmd, **kw: "requirements.txt" + NL + "installer.iss"
        sdr.domkniecie_runtime = lambda: set()
        sdr.manifest_tylko_granice = lambda tag: True
        with contextlib.redirect_stdout(io.StringIO()):
            winowajcy = sdr.pliki_runtime_w_zakresie("v1.0")
        assert winowajcy == [
            "installer.iss (dane albo konfiguracja paczki)"], winowajcy
        # Ten sam diff, ale manifest rusza WIECEJ niz granice → winowajca wraca.
        sdr.manifest_tylko_granice = lambda tag: False
        with contextlib.redirect_stdout(io.StringIO()):
            winowajcy = sdr.pliki_runtime_w_zakresie("v1.0")
        assert len(winowajcy) == 2, winowajcy
        assert winowajcy[0].startswith("requirements.txt"), winowajcy
    finally:
        (sdr.uruchom, sdr.domkniecie_runtime,
         sdr.manifest_tylko_granice) = oryginalne


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
