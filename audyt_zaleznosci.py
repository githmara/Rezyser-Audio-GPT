#!/usr/bin/env python
"""
audyt_zaleznosci.py — bramka: czy któraś zależność ma nowsze wydanie, o którym
NIE PODJĘLIŚMY DECYZJI.

Powstała, bo `requirements.txt` nie miał ANI JEDNEJ granicy wersji, a pomiar
(2026-09-10) pokazał, że to nie jest ryzyko teoretyczne: 10 z 15 pakietów było
w rozjeździe wobec PyPI, w tym DWIE zmiany majora — `anthropic` 0.109.2 → 1.5.0
i `openai` 2.31.0 → 3.12.0. Konsekwencja jest po stronie kontrybutora, nie
naszej: kto dziś zrobi `pip install -r requirements.txt`, dostanie inne majory
niż te, na których pracujemy, i jego pierwsze uruchomienie może wywalić się na
przemianowanym API — a przyczyną będzie nasz manifest bez granic.

ODRUCH, którego ta bramka jest narzędziem (kanon maintainera 2026-09-10):
próbę upgrade'u zależności robimy przed KAŻDYM zamrożeniem aplikacji, także
przy zmianach dev-tools-only — bo upgrade biblioteki potrafi podnieść planowane
skrócone wydanie do pełnej procedury (`requirements.txt` jest na liście
`PREFIKSY_NIE_DEV` w `sync_dev_release.py`, więc jego zmiana wyklucza skróconą
drogę — z JEDNYM wąskim wyjątkiem od 2026-09-18: diff ruszający wyłącznie
SPECYFIKATORY istniejących pakietów, przy identycznym zbiorze nazw, skróconej
drogi nie wyklucza, bo manifest nie wchodzi do bundla, a dev patch nic nie
rebuilduje; patrz `sync_dev_release.manifest_tylko_granice`). Gdy po upgradzie coś się zmieni: smoke test funkcji zależnych od tej
biblioteki albo co najmniej inspekcja sygnatury (kandydat pierwszy: SDK
`elevenlabs`, gdzie wołamy `client.studio.projects.create/delete`
i `client.user.subscription.get` — powierzchnia, którą ten SDK przemianowuje
między minorami). Działa dalej albo wymagało drobnych poprawek → nota
w `### What's new` sekcji wydania w `RELEASE_NOTES.md`. Wymaga refaktoru →
rozważamy za i przeciw i albo go robimy, albo ustalamy granicę
w `requirements.txt`.

RUBRYKA ZMIENIŁA SIĘ W v19.4.0, A TEN PLIK MÓWIŁ O NIEISTNIEJĄCEJ DO v19.4.1:
nota szła dawniej do polskiej sekcji „Pod maską", a polska diagnostyka
(`TL;DR → Co nowego → Pod maską → Co nie weszło → Walidacja`) została z nowych
sekcji `RELEASE_NOTES.md` porzucona. Adres jest dziś jeden — angielskie
`### What's new` — a diagnostykę, która nie jest treścią wydania, przyjmuje
raport wydania (`skrypty/raport_wydania_<wersja>.md`).

OD v19.4.0 ODRUCH NIE JEST JUŻ SAMĄ DYSCYPLINĄ: `build_release.py` stosuje
werdykt STRICT (`strict_przechodzi`) DOMYŚLNIE i ODMAWIA buildu, dopóki jakaś
zależność ma nowsze wydanie dopuszczone naszym manifestem. Do v19.3.1 bramka
w buildzie tylko ostrzegała — i to wystarczyło, żeby pominięcie kosztowało
zbudowany, a potem skasowany instalator (2026-09-17, `openai` 3.14.1 → 3.15.0
w granicy `<4`): ostrzeżenie jest jedną linią w kilkusetlinijkowym logu,
a lektura logu następuje PO buildzie. Komunikat blokady świadomie NIE ma tonu
„FATAL" — nic naszego nie jest zepsute, upstream po prostu coś wydał. Furtką
jest `build_release.py --no-strict`, która audytu NIE ODPALA w ogóle (krytyczny
hotfix wydawany bez sprawdzania zależności).

KANON ŚRODOWISKA (2026-11-12, zastąpił kanon zachowawczy z 2026-09-18):
  * ŚRODOWISKO NAJPIERW, jak w NVDA: pierwszy commit cyklu minorowego to
    `WIP vX.Y: środowisko` — zdjęcie wstrzymań, upgrade, testy tego, co już
    istnieje — i dopiero potem nowy kod. Funkcje cyklu są wtedy testowane na
    wersjach, które pójdą do bundla, a zmiany środowiska trafiają do sekcji
    wydania jako „Environment” (to, co widzi użytkownik, i to, co deweloper);
  * GRUPY RYZYKA (:data:`GRUPY_RYZYKA`) mówią, KIEDY wolno podbić i CZYM to
    udowodnić: A (okno, wyświetlanie, treść) tylko w commicie środowiska,
    z dowodem właściwym dla pakietu; B (providerzy) w dowolnym momencie cyklu,
    `inspect.signature` + jedno żywe wywołanie; C (dev-only) zawsze, a dowodem
    jest przejście `pytest`;
  * WSTRZYMANIE JEST DATOWANE: granica, która wyklucza istniejące wydanie, musi
    mieć w swojej linii `# hold: <wersja wydania, które ją postawiło>`.
    Wstrzymanie WYGASA z następnym minorem: build `X.Y.0` odmawia, dopóki stoi
    wstrzymanie z wcześniejszego minora, a build patcha tylko ostrzega;
  * DRUGI ZEGAR + BUDZIK: wstrzymanie wygasa też po :data:`WIEK_HOLDU_DNI`
    dniach od commitu, który ostatnio zmienił jego linię (`git blame`) — zegar
    wersji staje, gdy nic nie wychodzi. Pełny audyt zapisuje
    :data:`ZNACZNIK_BUDZIKA` (data + sprawy do decyzji), który czyta hak startu
    sesji maintainera: przypomnienie przychodzi także wtedy, gdy przez miesiące
    nie powstaje żaden build.

Zastąpiony kanon zachowawczy miał krok „PO wydaniu migrujemy” bez żadnego
wyzwalacza, a bramka liczyła zapisaną granicę jako zielone na zawsze. Zmierzone
2026-11-12: siedem wstrzymań, `anthropic` trzymany granicą `<1.8` od v19.8.0
przespał cały major (PyPI 2.8.0), `openai` był 33 minory w tyle, a trzy pliki
`zamrozone_*.txt` (19.5.0, 19.8.0, 19.8.1) były identyczne co do bajtu.

STANY per pakiet (rozróżnienie jest tu całą treścią bramki):

  * ``aktualne``        — zainstalowana wersja == najnowsza na PyPI;
  * ``granica``         — nowsze wydanie ISTNIEJE, nasz specyfikator go NIE
                          dopuszcza, a linia ma ważne `# hold:`. Decyzja, nie
                          trafienie;
  * ``przeterminowana`` — jak wyżej, ale `hold:` pochodzi z wcześniejszego
                          minora niż `VERSION`. Trafienie w buildzie `X.Y.0`
                          (otwarcie cyklu przegapiło commit środowiska),
                          ostrzeżenie w buildzie patcha;
  * ``niedatowana``     — granica wyklucza istniejące wydanie, a linia nie ma
                          `# hold:`. Nikt nie zapisał, KIEDY zdecydował, więc
                          nic nie przypomni o terminie. Trafienie;
  * ``nowsza``          — nowsze wydanie istnieje i nasz manifest je DOPUSZCZA,
                          czyli nikt o nim nie zdecydował, a kontrybutor dostanie
                          je od pip-a. Trafienie;
  * ``brak``            — pakiet z manifestu nie jest w ogóle zainstalowany.
                          Środowisko nie odpowiada manifestowi; też trafienie;
  * ``bez_grupy``       — pakiet nie ma grupy ryzyka w :data:`GRUPY_RYZYKA`.
                          Nowa zależność musi dostać grupę razem z wpisem.

CZEGO TA BRAMKA NIE UMIE, i mówi to wprost: stanu PyPI nie da się sprawdzić
offline, więc runner `sync-dev-release.yml` (gdzie nasze zależności nie są
zainstalowane) NIE MOŻE wymusić tego kroku. Mechanicznie egzekwowalna jest
tutaj, lokalnie, przed wydaniem — i tak jest wpięta w `build_release.py`.
Bez sieci albo bez `packaging` bramka DEGRADUJE się głośno, nigdy się nie pomija
(kanon v18.30.0).

Użycie:
  python audyt_zaleznosci.py                    # raport + werdykt
  python audyt_zaleznosci.py --strict           # exit 1 przy trafieniach
  python build_release.py                       # ten sam werdykt, blokuje build
  python build_release.py --no-strict           # hotfix: audytu nie odpala
  python audyt_zaleznosci.py --bez-sieci        # tylko manifest kontra zainstalowane
  python audyt_zaleznosci.py --pakiety anthropic,openai
  python audyt_zaleznosci.py --zamroz 19.18.0   # pip freeze, ale bez duplikatów
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional

import subprocess

import dev_konsola

dev_konsola.skonfiguruj_stdout()

ROOT = Path(__file__).resolve().parent
SCIEZKA_MANIFESTU = ROOT / "requirements.txt"
SCIEZKA_VERSION = ROOT / "VERSION"
KATALOG_ZAMROZEN = ROOT / "skrypty"
URL_PYPI = "https://pypi.org/pypi/{}/json"
TIMEOUT = 15

#: Drugi zegar wstrzymania: hold starszy niż tyle dni (od commitu, który
#: ostatnio zmienił jego linię) wygasa nawet bez zmiany minora.
WIEK_HOLDU_DNI = 60

#: Znacznik BUDZIKA: wynik ostatniego pełnego audytu (z siecią, cały manifest).
#: Czyta go hak startu sesji maintainera — budzik ma działać także wtedy, gdy
#: przez miesiące nie powstaje żaden build. `skrypty/` jest poza gitem.
ZNACZNIK_BUDZIKA = KATALOG_ZAMROZEN / "audyt_zaleznosci_ostatni.json"

#: Python, na którym zestaw z manifestu był ostatnio przetestowany — jedno miejsce,
#: lustro `PYTHON_PRZETESTOWANY` z ATA (klasa bliźniaków `zaleznosci`). Workflowy
#: muszą instalować DOKŁADNIE tę wersję (`test_python_ci.py`): gołe '3.14' daje
#: najnowszy patch (2026-10-21: runner ATA 3.14.8 przy lokalnym 3.14.3). Build
#: zamraża LOKALNY interpreter, więc rozjazd tutaj = bundel na niesprawdzonym Pythonie.
PYTHON_PRZETESTOWANY = "3.14.3"

#: Nazwa narzędzia w komunikatach fatalnych (standard „zero ciszy").
NARZEDZIE = "audyt_zaleznosci"

# Nazwa dystrybucji + jej specyfikator (surowy, jak w manifeście).
_RE_WPIS = re.compile(r"^(?P<nazwa>[A-Za-z0-9._-]+)\s*(?P<extras>\[[^\]]*\])?\s*(?P<spec>.*)$")
# Data wstrzymania w komentarzu tej samej linii: `anthropic<1.8  # hold: 19.8.0`.
# pip traktuje ` #` jako początek komentarza, więc manifest instaluje się bez zmian.
_RE_HOLD = re.compile(r"\bhold:\s*(?P<wersja>\d+\.\d+(?:\.\d+)?)")
_RE_VERSION = re.compile(r"^\s*(\d+)\.(\d+)(?:\.(\d+))?")

#: Grupa ryzyka KAŻDEJ zależności z manifestu. Grupa mówi, kiedy wolno podbić
#: wersję i czym to udowodnić — patrz :data:`OPIS_GRUP`. Pakiet spoza tej mapy
#: to trafienie bramki (`bez_grupy`): nowa zależność dostaje grupę w tym samym
#: commicie, w którym trafia do `requirements.txt`.
GRUPY_RYZYKA: dict[str, str] = {
    # A — okno, wyświetlanie i treść, którą użytkownik czyta albo słyszy.
    "wxpython": "A",                  # całe GUI, przejście z czytnikiem ekranu
    "lingua-language-detector": "A",  # lustro enuma w `jezyki_lingua.KANON`
    "markdown": "A",                  # renderuje wszystkie `docs/*.html`
    "fonttools": "A",                 # naprawa warstwy tekstu PDF (`core_pdf`)
    "pypdfium2": "A",                 # warstwa tekstu PDF (`core_pdf`)
    "pyinstaller": "A",               # kształt bundla, wychodzi dopiero w buildzie
    "num2words": "A",                 # liczby zamieniane na słowa w Poliglocie
    "python-docx": "A",               # wczytywanie i zapis .docx
    "beautifulsoup4": "A",            # wczytywanie HTML w Poliglocie
    "pyyaml": "A",                    # wczytywanie słowników i receptur
    "ruamel.yaml": "A",               # zapis YAML z zachowaniem komentarzy
    # B — providerzy i warstwa wokół wywołań modelu.
    "anthropic": "B",
    "openai": "B",
    "elevenlabs": "B",
    "tiktoken": "B",                  # liczenie tokenów (`core_tokeny`)
    "jsonschema": "B",                # schematy structured outputs
    "python-dotenv": "B",             # klucze providerów z `golden_key.env`
    # C — tylko narzędzia deweloperskie, poza bundlem.
    "pytest": "C",
    "packaging": "C",
}

OPIS_GRUP: dict[str, str] = {
    "A": "window, display, content: upgrade ONLY in the cycle's environment "
         "commit, with the package's own proof (screen-reader pass for "
         "wxpython, `docs/` regeneration + diff for markdown, `audyt_podstaw` "
         "for lingua, PDF tests for pypdfium2/fonttools, a trial build for "
         "pyinstaller)",
    "B": "providers: upgrade any time in the cycle; bound on the MAJOR line; "
         "proof = `inspect.signature` on the surface we call + one live call",
    "C": "dev-only, outside the bundle: upgrade any time; proof = `pytest` "
         "passes",
}


@dataclass
class Wpis:
    """Jedna linia manifestu: nazwa dystrybucji + specyfikator wersji."""
    nazwa: str
    specyfikator: str = ""
    wstrzymanie: Optional[str] = None   # wersja z `# hold:` albo None


@dataclass
class Stan:
    """Wynik dla jednego pakietu."""
    nazwa: str
    specyfikator: str
    zainstalowana: Optional[str]
    najnowsza: Optional[str]
    status: str          # aktualne | granica | przeterminowana | niedatowana
                         # | nowsza | brak | bez_grupy | nieznane
    powod: str = ""      # dlaczego `nieznane` (błąd sieci/parsowania)
    grupa: str = ""
    wstrzymanie: Optional[str] = None
    #: Czy audyt dotyczy buildu otwierającego cykl (`VERSION` = X.Y.0). Tylko
    #: wtedy przeterminowane wstrzymanie blokuje; w patchu ostrzega.
    otwarcie_cyklu: bool = False
    #: Dni od commitu, który ostatnio zmienił linię manifestu (`git blame`);
    #: None = nie wiadomo (brak gita, plik spoza repo).
    wiek_holdu: Optional[int] = None

    @property
    def trafienie(self) -> bool:
        if self.status == "przeterminowana":
            return self.otwarcie_cyklu
        return self.status in ("nowsza", "brak", "niedatowana", "bez_grupy")


@dataclass
class WynikBramki:
    """Kontrakt zgodny z pozostałymi bramkami wołanymi z `build_release`."""
    czysto: bool
    stany: list[Stan] = field(default_factory=list)
    degradacja: str = ""


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def wczytaj_manifest(sciezka: Path | None = None) -> list[Wpis]:
    """Czyta `requirements.txt` — nazwa PLUS specyfikator.

    Specyfikator jest POŁOWĄ odpowiedzi: to on odróżnia decyzję („granica")
    od zaniedbania („nowsza"), więc obcięcie go — jak robił usunięty
    `build_release.wczytaj_wymagane_pakiety`, który pytał tylko „czy
    zainstalowane" — zostawiałoby narzędzie bez jego jedynej treści.
    """
    plik = sciezka or SCIEZKA_MANIFESTU
    if not plik.is_file():
        raise SystemExit(
            f"❌ {NARZEDZIE}: cannot read {plik} — without the dependency "
            f"manifest there is nothing to audit.")
    wpisy: list[Wpis] = []
    for linia in plik.read_text(encoding="utf-8").splitlines():
        tekst, _, komentarz = linia.partition("#")
        tekst = tekst.strip()
        if not tekst or tekst.startswith("-"):
            continue
        dopasowanie = _RE_WPIS.match(tekst)
        if not dopasowanie:
            raise SystemExit(
                f"❌ {NARZEDZIE}: cannot parse the manifest line {linia!r} in "
                f"{plik.name} — refusing to audit a manifest this tool does not "
                f"understand.")
        hold = _RE_HOLD.search(komentarz)
        wpisy.append(Wpis(nazwa=dopasowanie.group("nazwa"),
                          specyfikator=dopasowanie.group("spec").strip(),
                          wstrzymanie=hold.group("wersja") if hold else None))
    if not wpisy:
        raise SystemExit(
            f"❌ {NARZEDZIE}: {plik.name} declares no packages — an audit of an "
            f"empty manifest would report 'clean' about nothing.")
    return wpisy


# ---------------------------------------------------------------------------
# Wersje: zainstalowana, najnowsza, porównanie
# ---------------------------------------------------------------------------
def zainstalowana_wersja(nazwa: str) -> Optional[str]:
    try:
        return version(nazwa)
    except PackageNotFoundError:
        return None


def najnowsza_wersja(nazwa: str) -> tuple[Optional[str], str]:
    """(wersja, powód) — powód niepusty tylko przy porażce."""
    try:
        with urllib.request.urlopen(
                URL_PYPI.format(nazwa), timeout=TIMEOUT) as resp:
            dane = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — sieć/DNS/JSON: jedna kategoria „nie wiem"
        return None, f"{type(exc).__name__}: {exc}"
    wersja = (dane.get("info") or {}).get("version")
    if not isinstance(wersja, str) or not wersja:
        return None, "PyPI response has no `info.version`"
    return wersja, ""


def _packaging():
    """Moduły `packaging` albo ``None`` (bramka wtedy degraduje, nie zgaduje)."""
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import InvalidVersion, Version
    except ImportError:
        return None
    return SpecifierSet, Version, InvalidVersion


def rozstrzygnij(wpis: Wpis, zainstalowana: Optional[str],
                 najnowsza: Optional[str], powod: str, narzedzia) -> Stan:
    """Składa :class:`Stan` dla jednego pakietu (bez sieci i bez I/O)."""
    wspolne = dict(nazwa=wpis.nazwa, specyfikator=wpis.specyfikator,
                   zainstalowana=zainstalowana, najnowsza=najnowsza)
    if zainstalowana is None:
        return Stan(**wspolne, status="brak",
                    powod="not installed in this environment")
    if najnowsza is None:
        return Stan(**wspolne, status="nieznane", powod=powod)
    if najnowsza == zainstalowana:
        return Stan(**wspolne, status="aktualne")
    if narzedzia is None:
        return Stan(**wspolne, status="nieznane",
                    powod="`packaging` is not importable, so PEP 440 comparison "
                          "is unavailable")
    SpecifierSet, Version, InvalidVersion = narzedzia
    try:
        v_zainst, v_naj = Version(zainstalowana), Version(najnowsza)
    except InvalidVersion as exc:
        return Stan(**wspolne, status="nieznane", powod=f"InvalidVersion: {exc}")
    if v_naj < v_zainst:
        # Lokalnie stoi coś nowszego niż „latest" na PyPI (yanked release, build
        # z gita, pre-release). Nie jest to nasz dług — ale i nie „aktualne".
        return Stan(**wspolne, status="nieznane",
                    powod="the installed version is NEWER than PyPI's latest "
                          "(yanked release? local build?)")
    if wpis.specyfikator:
        try:
            dopuszcza = SpecifierSet(wpis.specyfikator).contains(
                najnowsza, prereleases=False)
        except Exception as exc:  # noqa: BLE001 — nieznana składnia specyfikatora
            return Stan(**wspolne, status="nieznane",
                        powod=f"cannot evaluate specifier "
                              f"{wpis.specyfikator!r}: {exc}")
        if not dopuszcza:
            return Stan(**wspolne, status="granica")
    return Stan(**wspolne, status="nowsza")


def wersja_projektu(sciezka: Path | None = None) -> Optional[tuple[int, int, int]]:
    """`VERSION` jako (major, minor, patch); brak patcha (`19.18-WIP`) = 0.

    ``None``, gdy pliku nie ma albo nie zaczyna się od liczby — wtedy terminu
    wstrzymań nie da się policzyć i bramka degraduje się głośno.
    """
    plik = sciezka or SCIEZKA_VERSION
    try:
        tekst = plik.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _RE_VERSION.match(tekst)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def wiek_linii_manifestu(sciezka: Path | None = None,
                         dzis: date | None = None) -> dict[str, int]:
    """{nazwa pakietu (lower): dni od commitu, który ostatnio zmienił jego linię}.

    Z `git blame --line-porcelain` — jedno wywołanie na cały plik. Linia
    zmieniona w drzewie roboczym ma wiek 0 (git oddaje ją jako „Not Committed
    Yet” z bieżącym czasem). Bez gita albo poza repo: pusty słownik, a bramka
    ocenia wtedy same wersje (wiek nie jest wtedy znany, nie zerowy).
    """
    plik = sciezka or SCIEZKA_MANIFESTU
    dzis = dzis or date.today()
    try:
        wynik = subprocess.run(
            ["git", "blame", "--line-porcelain", "--", plik.name],
            cwd=plik.parent, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return {}
    if wynik.returncode != 0:
        return {}
    wieki: dict[str, int] = {}
    czas: Optional[int] = None
    for linia in wynik.stdout.splitlines():
        if linia.startswith("committer-time "):
            czas = int(linia.split()[1])
        elif linia.startswith("\t") and czas is not None:
            tekst = linia[1:].partition("#")[0].strip()
            m = _RE_WPIS.match(tekst) if tekst and not tekst.startswith("-") else None
            if m:
                dni = (dzis - datetime.fromtimestamp(czas).date()).days
                wieki.setdefault(m.group("nazwa").lower(), max(dni, 0))
            czas = None
    return wieki


def ocen_wstrzymanie(stan: Stan, wpis: Wpis,
                     projekt: Optional[tuple[int, int, int]],
                     wiek_dni: Optional[int] = None) -> Stan:
    """Nakłada na stan `granica` datę z `# hold:` i grupę ryzyka.

    Czysta funkcja (bez I/O), żeby testy mogły podać dowolną wersję projektu.
    Granica bez daty to `niedatowana`; data z minora wcześniejszego niż
    `VERSION` to `przeterminowana`. Data z TEGO SAMEGO albo późniejszego minora
    jest ważna — dopisuje się ją przecież w cyklu, którego wydanie dopiero
    wyjdzie, więc może wyprzedzać `VERSION` sprzed bumpu.

    DRUGI ZEGAR (budzik, 2026-11-12): hold wygasa też po :data:`WIEK_HOLDU_DNI`
    dniach od commitu, który ostatnio zmienił jego linię (``wiek_dni``). Sam
    zegar wersji staje, gdy projekt nie wydaje: `VERSION` stoi, hold z tego
    samego minora jest „ważny” na zawsze, a wstrzymany pakiet świeci 🔒 —
    dokładnie klasa, którą kanon środowiska miał zamknąć.
    """
    stan.grupa = GRUPY_RYZYKA.get(wpis.nazwa.lower(), "")
    stan.wstrzymanie = wpis.wstrzymanie
    stan.wiek_holdu = wiek_dni
    if projekt is not None:
        stan.otwarcie_cyklu = projekt[2] == 0
    if not stan.grupa and stan.status not in ("brak", "nieznane"):
        stan.status = "bez_grupy"
        return stan
    if stan.status != "granica":
        return stan
    if not wpis.wstrzymanie:
        stan.status = "niedatowana"
        return stan
    if projekt is None:
        stan.status = "nieznane"
        stan.powod = "VERSION is unreadable, so the hold's age cannot be judged"
        return stan
    m = _RE_VERSION.match(wpis.wstrzymanie)
    if m and (int(m.group(1)), int(m.group(2))) < projekt[:2]:
        stan.status = "przeterminowana"
    elif wiek_dni is not None and wiek_dni > WIEK_HOLDU_DNI:
        stan.status = "przeterminowana"
        stan.powod = f"held for {wiek_dni} days (limit {WIEK_HOLDU_DNI})"
    return stan


# ---------------------------------------------------------------------------
# Bramka
# ---------------------------------------------------------------------------
def bramka(pakiety: list[str] | None = None, *,
           bez_sieci: bool = False,
           projekt: Optional[tuple[int, int, int]] | str = "VERSION",
           wieki: dict[str, int] | None = None,
           ) -> WynikBramki:
    """Pełny przebieg. `czysto` = żaden :attr:`Stan.trafienie`.

    ``projekt`` domyślnie czyta `VERSION`, ``wieki`` — `git blame` manifestu;
    testy podają jedno i drugie wprost.
    """
    if projekt == "VERSION":
        projekt = wersja_projektu()
    wpisy = wczytaj_manifest()
    if pakiety:
        chciane = {p.strip().lower() for p in pakiety if p.strip()}
        wpisy = [w for w in wpisy if w.nazwa.lower() in chciane]
        if not wpisy:
            raise SystemExit(
                f"❌ {NARZEDZIE}: none of {sorted(chciane)} is in "
                f"{SCIEZKA_MANIFESTU.name}.")
    narzedzia = _packaging()
    degradacje: list[str] = []
    if narzedzia is None:
        degradacje.append("`packaging` is not importable — version comparison "
                          "is unavailable, so nothing can be classified")
    stany: list[Stan] = []
    wieki = wiek_linii_manifestu() if wieki is None else wieki
    for wpis in wpisy:
        zainst = zainstalowana_wersja(wpis.nazwa)
        if bez_sieci:
            najnowsza, powod = None, "network check disabled (--bez-sieci)"
        else:
            najnowsza, powod = najnowsza_wersja(wpis.nazwa)
        stany.append(ocen_wstrzymanie(
            rozstrzygnij(wpis, zainst, najnowsza, powod, narzedzia),
            wpis, projekt, wieki.get(wpis.nazwa.lower())))
    if projekt is None:
        degradacje.append("VERSION is unreadable — hold expiry cannot be judged")
    nieznane = [s for s in stany if s.status == "nieznane"]
    if nieznane:
        degradacje.append(
            f"{len(nieznane)}/{len(stany)} package(s) could not be compared "
            f"against PyPI")
    return WynikBramki(
        czysto=not any(s.trafienie for s in stany),
        stany=stany,
        degradacja="; ".join(degradacje),
    )


ETYKIETY = {
    "aktualne":        "✅ up to date",
    "granica":         "🔒 held on purpose",
    "przeterminowana": "⏰ HOLD EXPIRED",
    "niedatowana":     "⚠️  HOLD WITHOUT A DATE",
    "nowsza":          "⚠️  NEWER ALLOWED — undecided",
    "brak":            "❌ NOT INSTALLED",
    "bez_grupy":       "⚠️  NO RISK GROUP",
    "nieznane":        "ℹ️  not compared",
}

# Kolejność w tabeli: najpierw to, co wymaga decyzji.
_PORZADEK = ("nowsza", "brak", "bez_grupy", "niedatowana", "przeterminowana",
             "nieznane", "granica", "aktualne")


def opis_trafienia(s: Stan) -> str:
    """Jedna linia o pakiecie wymagającym decyzji — wspólna dla CLI i builda."""
    if s.status == "brak":
        return (f"{s.nazwa}: declared in the manifest but NOT installed here — "
                f"the environment does not match the manifest")
    if s.status == "bez_grupy":
        return (f"{s.nazwa}: has no risk group — add it to "
                f"`audyt_zaleznosci.GRUPY_RYZYKA` (A, B or C)")
    if s.status == "niedatowana":
        return (f"{s.nazwa}: {s.zainstalowana} → {s.najnowsza} is excluded by "
                f"`{s.specyfikator}`, but the line has no `# hold: <version>` — "
                f"date the hold or lift it")
    if s.status == "przeterminowana":
        dlaczego = (f"the hold is {s.wiek_holdu} days old (limit "
                    f"{WIEK_HOLDU_DNI})" if s.powod.startswith("held for")
                    else "the hold expired with the next minor")
        return (f"{s.nazwa}: held since {s.wstrzymanie} ({s.zainstalowana}, "
                f"PyPI {s.najnowsza}) — {dlaczego}; lift it in the environment "
                f"commit or re-date it on purpose")
    return (f"{s.nazwa}: {s.zainstalowana} → {s.najnowsza} (our bound "
            f"`{s.specyfikator or 'none'}` allows it, so a contributor gets it "
            f"from pip)")


ZASADA_DECYZJI = (
    "Decide by the package's risk group (column `grp`):\n"
    + "".join(f"  • {g}: {opis}\n" for g, opis in OPIS_GRUP.items())
    + "  • Not now? Set the bound one step below the new release and DATE it in "
      "the same line: `pkg<X.Y  # hold: <version you are releasing>`. A hold "
      "expires with the next minor, so the cycle-opening build (X.Y.0) refuses "
      "until the environment commit lifts it. Freeze the environment with "
      "`python audyt_zaleznosci.py --zamroz <version>` (it skips a freeze "
      "identical to the previous one).\n"
    + "  • An upgrade that ships goes to the release section as 'Environment' "
      "(what users see; what developers see).")


def strict_przechodzi(wynik: WynikBramki) -> bool:
    """Czy wynik przechodzi w trybie STRICT (`--strict`, domyślny build).

    JEDNA definicja słowa „strict" dla obu konsumentów: CLI tego narzędzia
    i `build_release.py` (od v19.4.0 bramka blokuje build domyślnie). Zanim ta
    funkcja powstała, build miał własny, luźniejszy warunek — ostrzegał i szedł
    dalej — więc „strict" znaczyło dwie różne rzeczy w zależności od tego, kto
    pyta, i pominięcie bramki kosztowało zbudowany, a potem wyrzucony instalator
    (zmierzone 2026-09-17: `openai` 3.14.1 → 3.15.0 dopuszczone granicą `<4`).

    DEGRADACJA JEST NIEPOWODZENIEM, nie neutralnym stanem: „nie wiem, czy czeka
    upgrade" to nie to samo co „nie czeka". Bez sieci i bez `packaging` bramka
    nie ma czym odpowiedzieć na pytanie, w którym cel jest zamrożenie wersji.
    """
    return wynik.czysto and not wynik.degradacja


def raport(wynik: WynikBramki) -> None:
    """Tabela + werdykt na stdout."""
    szerokosc = max((len(s.nazwa) for s in wynik.stany), default=10)
    print(f"\n{'package'.ljust(szerokosc)}  grp  {'installed':>12}  {'PyPI':>12}  "
          f"{'bound':<12} {'hold':<8} status")
    for s in sorted(wynik.stany, key=lambda s: (
            _PORZADEK.index(s.status) if s.status in _PORZADEK else 0, s.nazwa)):
        print(f"{s.nazwa.ljust(szerokosc)}  {(s.grupa or '?'):^3}  "
              f"{(s.zainstalowana or '-'):>12}  "
              f"{(s.najnowsza or '-'):>12}  {(s.specyfikator or '-'):<12} "
              f"{(s.wstrzymanie or '-'):<8} {ETYKIETY[s.status]}"
              + (f" ({s.powod})" if s.status == "nieznane" and s.powod else ""))

    print("\n========== DEPENDENCY GATE ==========")
    teraz = platform.python_version()
    if teraz != PYTHON_PRZETESTOWANY:
        print(f"⚠️  Running on Python {teraz}, the manifest was last tested on "
              f"{PYTHON_PRZETESTOWANY} (PYTHON_PRZETESTOWANY). A build freezes THIS "
              "interpreter into the bundle — test on it, then update the constant "
              "and every workflow's python-version in one commit.")
    if wynik.degradacja:
        print(f"⚠️  Ran with REDUCED coverage: {wynik.degradacja}.")
    trafienia = [s for s in wynik.stany if s.trafienie]
    # Przeterminowane w buildzie patcha nie blokują, ale nie mogą być ciche:
    # to dokładnie ta klasa, która do 2026-11-12 znikała pod zielonym 🔒.
    ostrzezenia = [s for s in wynik.stany
                   if s.status == "przeterminowana" and not s.trafienie]
    if not trafienia:
        print("✅ No dependency waits for a decision.")
    else:
        print(f"⚠️  {len(trafienia)} dependency/dependencies to decide about:")
        for s in trafienia:
            print(f"      • {opis_trafienia(s)}")
    if ostrzezenia:
        print(f"⏰ {len(ostrzezenia)} expired hold(s) — a patch build allows "
              f"them, the next X.Y.0 build will not:")
        for s in ostrzezenia:
            print(f"      • {opis_trafienia(s)}")
    if trafienia or ostrzezenia:
        print(ZASADA_DECYZJI)
        print("Moving a bound of an existing package keeps a shortened "
              "release possible; ADDING or REMOVING a package escalates it to "
              "the full procedure.")
    print("=====================================")


def do_decyzji(wynik: WynikBramki) -> list[str]:
    """Wszystko, co czeka na człowieka: trafienia ORAZ ⏰ nieblokujące w patchu."""
    return [opis_trafienia(s) for s in wynik.stany
            if s.trafienie or s.status == "przeterminowana"]


def zapisz_znacznik(wynik: WynikBramki, zrodlo: str,
                    sciezka: Path | None = None, dzis: date | None = None) -> bool:
    """Zapisuje znacznik BUDZIKA po PEŁNYM audycie; zwraca, czy zapisał.

    Pełny = cały manifest i bez degradacji (sieć, `packaging`, `VERSION`):
    audyt, który nie wie, czy upgrade czeka, nie może cofnąć budzika — inaczej
    jeden przebieg offline uciszałby go na kolejny miesiąc. Wołający odpowiada
    za to, że ``wynik`` dotyczy całego manifestu. Format czyta hak startu sesji
    maintainera (stdlib, bez importu tego modułu), więc zmiana kluczy = zmiana
    po obu stronach. Błąd zapisu jest cichy: budzik to przypomnienie, nie bramka.
    """
    if wynik.degradacja:
        return False
    cel = sciezka or ZNACZNIK_BUDZIKA
    dane = {
        "format": 1,
        "data": (dzis or date.today()).isoformat(),
        "zrodlo": zrodlo,
        "wersja_projektu": (SCIEZKA_VERSION.read_text(encoding="utf-8").strip()
                            if SCIEZKA_VERSION.is_file() else ""),
        "do_decyzji": do_decyzji(wynik),
    }
    try:
        cel.parent.mkdir(parents=True, exist_ok=True)
        tmp = cel.with_suffix(".tmp")
        tmp.write_text(json.dumps(dane, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(cel)
    except OSError:
        return False
    return True


def zamroz(wersja: str, katalog: Path | None = None,
           freeze: str | None = None) -> tuple[Path, bool]:
    """`pip freeze` do `skrypty/zamrozone_<wersja>.txt` — chyba że nic się nie zmieniło.

    Zwraca (plik, czy_zapisano). Gdy treść jest identyczna z NAJNOWSZYM
    istniejącym zamrożeniem, nic nie zapisujemy i oddajemy tamten plik: on już
    jest biletem powrotnym do tego środowiska. Do 2026-11-12 `pip freeze` szło
    bezwarunkowo i trzy wydania (19.5.0, 19.8.0, 19.8.1) zostawiły trzy
    identyczne pliki. ``freeze`` podają testy; normalnie pyta interpreter.
    """
    katalog = katalog or KATALOG_ZAMROZEN
    if freeze is None:
        freeze = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"], check=True,
            capture_output=True, text=True, encoding="utf-8").stdout
    narzedzia = _packaging()

    def _klucz(p: Path):
        surowa = p.stem.removeprefix("zamrozone_")
        if narzedzia is not None:
            try:
                return (1, narzedzia[1](surowa), "")
            except narzedzia[2]:
                pass
        return (0, None, surowa)

    istniejace = sorted(katalog.glob("zamrozone_*.txt"), key=_klucz)
    istniejace = [p for p in istniejace if _klucz(p)[0] == 1] or istniejace
    if istniejace:
        ostatni = istniejace[-1]
        if ostatni.read_text(encoding="utf-8").splitlines() == freeze.splitlines():
            return ostatni, False
    cel = katalog / f"zamrozone_{wersja}.txt"
    cel.write_text(freeze, encoding="utf-8")
    return cel, True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audits requirements.txt against the installed environment "
                    "and PyPI: which dependency has a newer release that our "
                    "manifest still allows (i.e. nobody decided about it).")
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit 1 when any package is in the `newer allowed` or `not "
             "installed` state, or when the audit could not be completed. Use "
             "it before deciding on the shortened (dev-tools-only) release "
             "procedure: a pending upgrade escalates it to the full one. Since "
             "v19.4.0 `build_release.py` applies this same verdict by DEFAULT "
             "and refuses to build; `build_release.py --no-strict` is the "
             "hotfix escape hatch.")
    parser.add_argument(
        "--bez-sieci", dest="bez_sieci", action="store_true",
        help="Skip PyPI entirely: only checks that every manifest package is "
             "installed. Everything else reports as `not compared`.")
    parser.add_argument(
        "--pakiety", type=str, default="", metavar="NAME[,NAME...]",
        help="Audit only these distributions (names as in requirements.txt).")
    parser.add_argument(
        "--zamroz", type=str, default="", metavar="VERSION",
        help="Write `pip freeze` to skrypty/zamrozone_<VERSION>.txt — unless "
             "it is identical to the newest existing freeze, which then stays "
             "the return ticket. Runs no audit.")
    args = parser.parse_args()

    if args.zamroz:
        plik, zapisano = zamroz(args.zamroz.strip())
        if zapisano:
            print(f"🧊 Environment frozen to {plik}.")
        else:
            print(f"🧊 Nothing to freeze: the environment is identical to "
                  f"{plik.name}, which stays the return ticket.")
        return 0

    pakiety = [p for p in args.pakiety.split(",") if p.strip()] or None
    wynik = bramka(pakiety, bez_sieci=args.bez_sieci)
    raport(wynik)
    if pakiety is None and zapisz_znacznik(wynik, "audyt_zaleznosci"):
        print(f"⏱️  Alarm clock reset: {ZNACZNIK_BUDZIKA.relative_to(ROOT)} "
              f"(read by the maintainer's session-start hook).")
    if args.strict and not strict_przechodzi(wynik):
        # Świadomie surowo: `--strict` służy decyzji „czy wolno pójść skróconą
        # procedurą", a ta jest OPTYMALIZACJĄ. Kiedy nie wiemy, czy upgrade
        # czeka, właściwą odpowiedzią jest pełna procedura, nie domysł. Warunek
        # stoi w `strict_przechodzi`, bo od v19.4.0 ma DRUGIEGO konsumenta
        # (`build_release`) i dwie kopie rozjechałyby się w pierwszej edycji.
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
