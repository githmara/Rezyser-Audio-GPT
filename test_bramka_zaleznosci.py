"""
test_bramka_zaleznosci.py - Krok 3h builda (do 19.15: 6b4): blokada domyslna,
--no-strict cisza (v19.4).

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

Uruchom:  .venv/Scripts/python -m pytest test_bramka_zaleznosci.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_bramka_zaleznosci.py
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

import pytest

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
    """Odpala krok 3h na PODSTAWIONYM audycie. Zwraca (log, kod wyjscia)."""
    oryginalna = az.bramka

    def _podstawiona(*_a, **_kw):
        if wysadz_audyt:
            raise AssertionError(
                "--no-strict touched the audit; it must not run it at all")
        return wynik

    az.bramka = _podstawiona
    # Build zapisuje znacznik budzika - w tescie NIE do prawdziwego `skrypty/`.
    znacznik = az.ZNACZNIK_BUDZIKA
    az.ZNACZNIK_BUDZIKA = Path(tempfile.mkdtemp()) / "znacznik.json"
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
        az.ZNACZNIK_BUDZIKA = znacznik
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
    assert "✅" in log and "held on purpose" in log, log


# ---------------------------------------------------------------------------
# Kanon srodowiska (2026-11-12): datowane wstrzymania, grupy ryzyka, zamrozenia
# ---------------------------------------------------------------------------
def _granica(nazwa="anthropic", hold=None, projekt=(19, 18, 0)) -> az.Stan:
    """`granica` z PRAWDZIWEGO `rozstrzygnij` + `ocen_wstrzymanie` (bez sieci)."""
    wpis = az.Wpis(nazwa=nazwa, specyfikator="<1.8", wstrzymanie=hold)
    stan = az.rozstrzygnij(wpis, "1.7.0", "2.8.0", "", az._packaging())
    assert stan.status == "granica", stan
    return az.ocen_wstrzymanie(stan, wpis, projekt)


def test_hold_z_biezacego_minora_jest_decyzja():
    """Data z tego samego albo pozniejszego minora = wazne wstrzymanie."""
    for hold in ("19.18.0", "19.18.2", "19.19.0"):
        stan = _granica(hold=hold)
        assert stan.status == "granica" and not stan.trafienie, (hold, stan)


def test_hold_bez_daty_jest_trafieniem():
    """Granica wykluczajaca istniejace wydanie bez `# hold:` = nikt nie wie, od kiedy."""
    stan = _granica(hold=None)
    assert stan.status == "niedatowana" and stan.trafienie, stan


def test_przeterminowany_hold_blokuje_tylko_otwarcie_cyklu():
    """To jest serce kanonu: 🔒 przestaje byc zielone na zawsze.

    Zmierzone 2026-11-12: `anthropic<1.8` stal od 19.8.0, a PyPI doszedl do 2.8.0.
    Build X.Y.0 ma odmowic, build patcha ostrzec i przepuscic.
    """
    otwarcie = _granica(hold="19.8.0", projekt=(19, 18, 0))
    assert otwarcie.status == "przeterminowana" and otwarcie.trafienie
    patch = _granica(hold="19.8.0", projekt=(19, 18, 1))
    assert patch.status == "przeterminowana" and not patch.trafienie


def test_build_patcha_przepuszcza_przeterminowany_hold_glosno():
    stan = _granica(hold="19.8.0", projekt=(19, 18, 1))
    log, kod = _uruchom(az.WynikBramki(czysto=True, stany=[stan]))
    assert kod is None, log
    assert "⏰" in log and "held since 19.8.0" in log, log


def test_build_otwarcia_cyklu_odmawia_przy_przeterminowanym_holdzie():
    stan = _granica(hold="19.8.0", projekt=(19, 18, 0))
    log, kod = _uruchom(az.WynikBramki(czysto=False, stany=[stan]))
    assert kod == 1, log
    assert "held since 19.8.0" in log and "FATAL" not in log, log


def test_drugi_zegar_hold_wygasa_po_wieku_bez_zmiany_minora():
    """Budzik: projekt nie wydaje, `VERSION` stoi - hold i tak wygasa po czasie.

    Bez tego hold z biezacego minora bylby wazny na zawsze, a wstrzymany pakiet
    swiecilby 🔒 - ta sama klasa, ktora kanon srodowiska mial zamknac.
    """
    wpis = az.Wpis(nazwa="anthropic", specyfikator="<1.8", wstrzymanie="19.18.0")

    def _ocen(wiek, projekt=(19, 18, 1)):
        stan = az.rozstrzygnij(wpis, "1.7.0", "2.8.0", "", az._packaging())
        return az.ocen_wstrzymanie(stan, wpis, projekt, wiek)

    assert _ocen(az.WIEK_HOLDU_DNI).status == "granica"
    assert _ocen(None).status == "granica"          # bez gita: wiek nieznany
    stary = _ocen(az.WIEK_HOLDU_DNI + 1)
    assert stary.status == "przeterminowana" and not stary.trafienie, stary
    assert "days old" in az.opis_trafienia(stary)
    assert _ocen(az.WIEK_HOLDU_DNI + 1, (19, 19, 0)).trafienie
    # Aktualny pakiet ze stara linia nie ma czego testowac.
    swiezy = az.rozstrzygnij(wpis, "1.7.0", "1.7.0", "", az._packaging())
    assert az.ocen_wstrzymanie(swiezy, wpis, (19, 18, 1), 999).status == "aktualne"


def test_wiek_linii_manifestu_z_git_blame():
    from datetime import date, timedelta
    wieki = az.wiek_linii_manifestu()
    if not wieki:
        pytest.skip("git blame unavailable here")
    assert "anthropic" in wieki and wieki["anthropic"] >= 0
    pozniej = az.wiek_linii_manifestu(dzis=date.today() + timedelta(days=100))
    assert pozniej["anthropic"] == wieki["anthropic"] + 100


def test_hold_bez_znanego_wieku_degraduje_glosno():
    """Audyt 19.18: bez gita (paczka „Source code”) drugi zegar stal po cichu,
    hold wygladal zielono, a budzik i tak sie cofal."""
    wynik = az.bramka(["anthropic"], bez_sieci=True, projekt=(19, 18, 0), wieki={})
    assert "unknown" in wynik.degradacja and "anthropic" in wynik.degradacja
    z_wiekiem = az.bramka(["anthropic"], bez_sieci=True, projekt=(19, 18, 0),
                          wieki={"anthropic": 1})
    assert "unknown" not in (z_wiekiem.degradacja or "")


def test_wiek_tylko_z_linii_hold(tmp_path):
    """Komentarz proza zaczynajacy sie od nazwy pakietu nie podaje wieku
    (blizniak ATA bral wiek komentarza naglowka zamiast linii z granica)."""
    import subprocess
    repo = tmp_path / "r"
    repo.mkdir()
    plik = repo / "requirements.txt"

    def git(*a, data):
        env = {"GIT_AUTHOR_DATE": data, "GIT_COMMITTER_DATE": data,
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        import os
        subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True,
                       env={**os.environ, **env})

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    plik.write_text("# markdown 3.10: stary komentarz naglowka\n", encoding="utf-8")
    git("add", ".", data="2020-01-01T12:00:00")
    git("commit", "-qm", "a", data="2020-01-01T12:00:00")
    plik.write_text("# markdown 3.10: stary komentarz naglowka\n"
                    "markdown<3.12  # hold: 19.18.0\n", encoding="utf-8")
    git("add", ".", data="2026-01-01T12:00:00")
    git("commit", "-qm", "b", data="2026-01-01T12:00:00")
    from datetime import date
    wieki = az.wiek_linii_manifestu(plik, dzis=date(2026, 1, 11))
    assert wieki == {"markdown": 10}


def test_wiek_nie_z_prozy_ani_z_plytkiego_klonu(tmp_path):
    """Audyt 2026-11-13: (a) swiezy komentarz prozą z `hold:` NAD wpisem dawal
    wiek komentarza (10 dni zamiast 130); (b) klon `--depth 1` przypisywal
    kazda linie commitowi granicznemu — hold zielony, zadnej degradacji."""
    import os
    import subprocess
    from datetime import date
    repo = tmp_path / "r"
    repo.mkdir()
    plik = repo / "requirements.txt"
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def commit(tresc, data):
        plik.write_text(tresc, encoding="utf-8")
        e = {**env, "GIT_AUTHOR_DATE": data, "GIT_COMMITTER_DATE": data}
        subprocess.run(["git", "add", "."], cwd=repo, check=True, env=e)
        subprocess.run(["git", "commit", "-qm", "x"], cwd=repo, check=True, env=e)

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    commit("openai<4  # hold: 19.18.0\n", "2026-01-01T12:00:00")
    commit("# openai: hold: 19.18.0 przedluzony po pomiarze\nopenai<4  # hold: 19.18.0\n",
           "2026-05-01T12:00:00")
    assert az.wiek_linii_manifestu(plik, dzis=date(2026, 5, 11)) == {"openai": 130}
    klon = tmp_path / "klon"
    subprocess.run(["git", "clone", "-q", "--depth", "1", repo.as_uri(), str(klon)],
                   check=True, capture_output=True)
    assert az._klon_plytki(klon)
    assert az.wiek_linii_manifestu(klon / "requirements.txt", dzis=date(2026, 5, 11)) == {}


def test_znacznik_budzika_tylko_po_pelnym_audycie(tmp_path):
    from datetime import date
    import json
    stan = _granica(hold="19.8.0", projekt=(19, 18, 1))   # ⏰ nieblokujace
    plik = tmp_path / "znacznik.json"
    zdegradowany = az.WynikBramki(czysto=True, stany=[stan], degradacja="no network")
    assert not az.zapisz_znacznik(zdegradowany, "test", plik)
    assert not plik.exists(), "an offline run must not silence the alarm clock"
    pelny = az.WynikBramki(czysto=True, stany=[stan])
    assert az.zapisz_znacznik(pelny, "test", plik, dzis=date(2026, 11, 12))
    dane = json.loads(plik.read_text(encoding="utf-8"))
    assert dane["format"] == 1 and dane["data"] == "2026-11-12"
    assert len(dane["do_decyzji"]) == 1 and "anthropic" in dane["do_decyzji"][0]


def test_pakiet_bez_grupy_jest_trafieniem():
    wpis = az.Wpis(nazwa="nowa-zaleznosc", specyfikator="")
    stan = az.rozstrzygnij(wpis, "1.0", "1.0", "", az._packaging())
    stan = az.ocen_wstrzymanie(stan, wpis, (19, 18, 0))
    assert stan.status == "bez_grupy" and stan.trafienie, stan


def test_kazdy_pakiet_manifestu_ma_grupe_i_parsuje_hold():
    """Offline: manifest x GRUPY_RYZYKA oraz daty `# hold:` z prawdziwego pliku."""
    wpisy = az.wczytaj_manifest()
    bez = [w.nazwa for w in wpisy if w.nazwa.lower() not in az.GRUPY_RYZYKA]
    assert not bez, f"pakiety bez grupy ryzyka: {bez}"
    assert set(az.GRUPY_RYZYKA.values()) <= set(az.OPIS_GRUP)
    daty = {w.nazwa: w.wstrzymanie for w in wpisy if w.wstrzymanie}
    assert daty and all(az._RE_VERSION.match(d) for d in daty.values()), daty
    # Kazda granica (`<`) nosi date - inaczej po cichu stalaby na zawsze.
    assert all(w.wstrzymanie for w in wpisy if "<" in w.specyfikator), daty


def _instalacje_w_workflow(tekst: str) -> list[tuple[str, str]]:
    """[(nazwa kanoniczna, specyfikator)] dla KAZDEGO pakietu z `pip install`
    (tez `pip3`, `python -m pip`, kontynuacje linii, apostrofy, extras,
    markery) — lista, nie dict: dwa joby w jednym pliku nie nadpisuja sie.
    Audyt 2026-11-13: poprzedni parser dzielil tylko po cudzyslowie `"`
    i szukal dokladnie „pip install", wiec kilka zwyklych zapisow przechodzilo
    po cichu jako „zgodne"."""
    import shlex
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name

    wynik = []
    for linia in tekst.replace(chr(92) + chr(10), " ").splitlines():
        if linia.strip().startswith("#"):
            continue
        try:
            tokeny = shlex.split(linia)
        except ValueError:
            continue
        for i, tok in enumerate(tokeny):
            if tok != "install" or i == 0 or tokeny[i - 1] not in ("pip", "pip3"):
                continue
            pomin = False
            for arg in tokeny[i + 1:]:
                if arg in ("&&", "||", ";", "|"):
                    break
                if pomin:
                    pomin = False
                    continue
                if arg.startswith("-"):
                    # `-r plik`, `-c plik`, `-e sciezka`... biora argument.
                    pomin = arg in ("-r", "--requirement", "-c", "--constraint", "-e",
                                    "--editable", "-i", "--index-url", "--extra-index-url")
                    continue
                try:
                    req = Requirement(arg)
                except InvalidRequirement:
                    continue
                wynik.append((canonicalize_name(req.name), str(req.specifier)))
    return wynik


def _gorna_granica(spec: str):
    """(Version, czy_wlacznie) — najciasniejsza gorna granica zbioru wersji
    albo None. Pin `==` i `~=` tez ja wyznaczaja (pin jest granica)."""
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    granice = []
    for s in SpecifierSet(spec):
        v = s.version
        if s.operator == "<":
            granice.append((Version(v), False))
        elif s.operator == "<=" or (s.operator in ("==", "===") and "*" not in v):
            granice.append((Version(v), True))
        elif s.operator == "==":       # X.Y.* -> < X.(Y+1)
            czesci = [int(c) for c in v[:-2].split(".")]
            czesci[-1] += 1
            granice.append((Version(".".join(map(str, czesci))), False))
        elif s.operator == "~=":       # ~=X.Y -> < (X+1); ~=X.Y.Z -> < X.(Y+1)
            czesci = list(Version(v).release[:-1])
            czesci[-1] += 1
            granice.append((Version(".".join(map(str, czesci))), False))
    return min(granice) if granice else None


def _rozjazdy_granic(workflowy: dict[str, str], manifest: dict[str, str]):
    """(rozjazdy, widziane[nazwa -> zbior plikow]). Rozjazd = pakiet z
    manifestu, ktorego gorna granica w workflowie jest INNA (semantycznie:
    `<4.0` == `<4`) — wezsza zamrozilaby bota na starej wersji, szersza albo
    brak granicy wpuscilyby nieprzetestowana."""
    from packaging.utils import canonicalize_name

    manifest = {canonicalize_name(n): s for n, s in manifest.items()}
    rozjazdy, widziane = [], {}
    for plik, tekst in sorted(workflowy.items()):
        for nazwa, spec in _instalacje_w_workflow(tekst):
            if nazwa not in manifest:
                continue
            widziane.setdefault(nazwa, set()).add(plik)
            if _gorna_granica(spec) != _gorna_granica(manifest[nazwa]):
                rozjazdy.append(f"{plik}: {nazwa}{spec or ' (bez granicy)'}, "
                                f"requirements.txt: {nazwa}{manifest[nazwa]}")
    return rozjazdy, widziane


def test_gorne_granice_workflowow_zgodne_z_manifestem():
    """Bliźniak ATA (audyt 2026-11-13): tam release.yml instalował fonttools<4.68
    po podbiciu manifestu do <4.69. Boty Reżysera instalują `openai` i `lingua`
    osobno — po podbiciu manifestu workflow nie może zostać przy starej granicy."""
    katalog = _KORZEN / ".github" / "workflows"
    workflowy = {wf.name: wf.read_text(encoding="utf-8")
                 for wf in sorted(katalog.glob("*.yml")) + sorted(katalog.glob("*.yaml"))}
    manifest = {w.nazwa: w.specyfikator for w in az.wczytaj_manifest()}
    rozjazdy, widziane = _rozjazdy_granic(workflowy, manifest)
    # Kazdy plik instalujacy pakiet sprawdzany OSOBNO (do 2026-11-13 zbior byl
    # wspolny, wiec pin w jednym z trzech workflowow lingua przechodzil).
    assert len(widziane.get("lingua-language-detector", ())) == 3, widziane
    assert widziane.get("openai") == {"issue-intake.yml"}, widziane
    assert not rozjazdy, rozjazdy


_Q = chr(34)


@pytest.mark.parametrize("instalacja, rozjazd", [
    (f"pip install {_Q}openai<4{_Q}", False),
    (f"pip install {_Q}openai<4.0{_Q}", False),
    ("pip install 'openai >= 1.40, < 4'", False),
    (f"pip install --upgrade {_Q}openai>=1.40,<4{_Q} pyyaml", False),
    (f"pip install {_Q}openai~=3.0{_Q}", False),       # ~=3.0 = <4
    ("pip install -r requirements.txt", False),
    (f"pip install {_Q}openai<3{_Q}", True),
    ("pip install 'openai<3'", True),
    (f"pip install {_Q}openai~=3.49.0{_Q}", True),     # = <3.50
    (f"pip install {_Q}openai==3.49.0{_Q}", True),
    (f"pip install {_Q}openai[realtime]<3{_Q}", True),
    (f"pip3 install {_Q}openai<3{_Q}", True),
    (f"python -m pip install {_Q}openai<3{_Q}", True),
    (f"pip install {chr(92)}{chr(10)}  {_Q}openai<3{_Q}", True),
    (f"pip install {_Q}openai>=4{_Q}", True),
    ("pip install openai", True),
])
def test_bramka_granic_workflow_lapie_rozjazd(instalacja, rozjazd):
    """Porownanie z manifestem widziane na czerwono — kazda forma z audytu."""
    wynik, _ = _rozjazdy_granic({"x.yml": "run: " + instalacja}, {"openai": ">=1.40,<4"})
    assert bool(wynik) is rozjazd, wynik


def test_bramka_granic_dwa_joby_w_pliku_nie_nadpisuja_sie():
    tekst = f"run: pip install {_Q}openai<4{_Q}{chr(10)}run: pip install {_Q}openai<3{_Q}"
    wynik, _ = _rozjazdy_granic({"x.yml": tekst}, {"openai": "<4"})
    assert len(wynik) == 1 and "<3" in wynik[0], wynik


def test_bramka_granic_nazwa_z_podkreslnikami():
    tekst = f"run: pip install {_Q}lingua_language_detector<2.2{_Q}"
    wynik, widziane = _rozjazdy_granic({"x.yml": tekst}, {"lingua-language-detector": "<2.3"})
    assert wynik and "lingua-language-detector" in widziane


def test_wersja_projektu_czyta_wip_jako_otwarcie(tmp_path):
    plik = tmp_path / "VERSION"
    plik.write_text("19.18-WIP\n", encoding="utf-8")
    assert az.wersja_projektu(plik) == (19, 18, 0)
    plik.write_text("19.17.3", encoding="utf-8")
    assert az.wersja_projektu(plik) == (19, 17, 3)
    plik.write_text("nonsens", encoding="utf-8")
    assert az.wersja_projektu(plik) is None


def test_zamrozenie_nie_duplikuje_identycznego(tmp_path):
    """Trzy identyczne pliki 19.5.0 / 19.8.0 / 19.8.1 — tego ma juz nie byc."""
    srodowisko = "anthropic==1.7.0\nopenai==3.16.2\n"
    plik, zapisano = az.zamroz("19.17.0", tmp_path, freeze=srodowisko)
    assert zapisano and plik.name == "zamrozone_19.17.0.txt"
    plik, zapisano = az.zamroz("19.17.1", tmp_path, freeze=srodowisko)
    assert not zapisano and plik.name == "zamrozone_19.17.0.txt"
    # Porownanie idzie z NAJNOWSZYM wg PEP 440, nie alfabetycznie (19.17 > 19.8).
    (tmp_path / "zamrozone_19.8.1.txt").write_text("stare==1\n", encoding="utf-8")
    plik, zapisano = az.zamroz("19.18.0", tmp_path, freeze=srodowisko)
    assert not zapisano and plik.name == "zamrozone_19.17.0.txt"
    plik, zapisano = az.zamroz("19.18.0", tmp_path,
                               freeze=srodowisko + "pytest==9.2.0\n")
    assert zapisano and plik.name == "zamrozone_19.18.0.txt"


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


# Uruchomienie jako skrypt — deleguje do pytesta: jeden mechanizm, jedno
# raportowanie (kanon v19.2.1). Własny harness łapał wyłącznie `AssertionError`,
# więc `pytest.skip` wywracał mu cały przebieg, a fixture i `parametrize` były
# dla niego niewidzialne.

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
