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

KANON ZACHOWAWCZY (2026-09-18) — co robić, gdy przyjęcie nowego wydania
wymagałoby PRZESUNIĘCIA GRANICY na następny minor albo major (a nie zwykłego
kroku patchowego w jej wnętrzu):
  1. wydanie robimy JAK JEST — migracja SDK nie jest treścią tego wydania;
  2. notujemy pozycję w „co nie weszło" (`Planned or deferred`), więc decyzja
     zostaje widoczna zamiast rozpłynąć się w „zrobimy kiedyś";
  3. mrozimy środowisko: `pip freeze > skrypty/zamrozone_<wersja>.txt`
     (gitignored, obok raportu wydania) — to bilet powrotny;
  4. PO wydaniu: przesuwamy granicę, upgradujemy, testujemy i dostrajamy,
     a wynik wydajemy jako OSOBNY patch / minor / major — zależnie od tego, ile
     się realnie ruszyło;
  5. albo przywracamy wersję zamrożoną, zostawiamy stałą granicę i robimy DEV
     PATCH, bo zupgradowany i przywrócony bundle to w praktyce ten sam bundle
     (wykonalne od 2026-09-18 — wcześniej sam zapis granicy blokował skróconą
     procedurę, patrz wyjątek wyżej).
Wariant patchowy WEWNĄTRZ granicy zostaje tani i normalny: upgrade
+ `inspect.signature` wołanej powierzchni (zero zapytań do API) + nota
w `### What's new`.

CZTERY STANY per pakiet (rozróżnienie jest tu całą treścią bramki):

  * ``aktualne``  — zainstalowana wersja == najnowsza na PyPI;
  * ``granica``   — nowsze wydanie ISTNIEJE, ale nasz specyfikator go NIE
                    dopuszcza. To decyzja już podjęta i świadoma, więc NIE jest
                    trafieniem bramki — tylko pozycją do przeglądu, gdy przyjdzie
                    czas na migrację;
  * ``nowsza``    — nowsze wydanie istnieje i nasz manifest je DOPUSZCZA, czyli
                    nikt o nim nie zdecydował, a kontrybutor dostanie je od pip-a.
                    To jest trafienie;
  * ``brak``      — pakiet z manifestu nie jest w ogóle zainstalowany. Środowisko
                    nie odpowiada manifestowi; też trafienie.

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
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional

import dev_konsola

dev_konsola.skonfiguruj_stdout()

ROOT = Path(__file__).resolve().parent
SCIEZKA_MANIFESTU = ROOT / "requirements.txt"
URL_PYPI = "https://pypi.org/pypi/{}/json"
TIMEOUT = 15

#: Nazwa narzędzia w komunikatach fatalnych (standard „zero ciszy").
NARZEDZIE = "audyt_zaleznosci"

# Nazwa dystrybucji + jej specyfikator (surowy, jak w manifeście).
_RE_WPIS = re.compile(r"^(?P<nazwa>[A-Za-z0-9._-]+)\s*(?P<extras>\[[^\]]*\])?\s*(?P<spec>.*)$")


@dataclass
class Wpis:
    """Jedna linia manifestu: nazwa dystrybucji + specyfikator wersji."""
    nazwa: str
    specyfikator: str = ""


@dataclass
class Stan:
    """Wynik dla jednego pakietu."""
    nazwa: str
    specyfikator: str
    zainstalowana: Optional[str]
    najnowsza: Optional[str]
    status: str          # aktualne | granica | nowsza | brak | nieznane
    powod: str = ""      # dlaczego `nieznane` (błąd sieci/parsowania)

    @property
    def trafienie(self) -> bool:
        return self.status in ("nowsza", "brak")


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
        tekst = linia.split("#", 1)[0].strip()
        if not tekst or tekst.startswith("-"):
            continue
        dopasowanie = _RE_WPIS.match(tekst)
        if not dopasowanie:
            raise SystemExit(
                f"❌ {NARZEDZIE}: cannot parse the manifest line {linia!r} in "
                f"{plik.name} — refusing to audit a manifest this tool does not "
                f"understand.")
        wpisy.append(Wpis(nazwa=dopasowanie.group("nazwa"),
                          specyfikator=dopasowanie.group("spec").strip()))
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


# ---------------------------------------------------------------------------
# Bramka
# ---------------------------------------------------------------------------
def bramka(pakiety: list[str] | None = None, *,
           bez_sieci: bool = False) -> WynikBramki:
    """Pełny przebieg. `czysto` = zero pakietów w stanie `nowsza`/`brak`."""
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
    for wpis in wpisy:
        zainst = zainstalowana_wersja(wpis.nazwa)
        if bez_sieci:
            najnowsza, powod = None, "network check disabled (--bez-sieci)"
        else:
            najnowsza, powod = najnowsza_wersja(wpis.nazwa)
        stany.append(rozstrzygnij(wpis, zainst, najnowsza, powod, narzedzia))
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
    "aktualne": "✅ up to date",
    "granica":  "🔒 newer exists, our bound excludes it",
    "nowsza":   "⚠️  NEWER ALLOWED — undecided",
    "brak":     "❌ NOT INSTALLED",
    "nieznane": "ℹ️  not compared",
}


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
    print(f"\n{'package'.ljust(szerokosc)}  {'installed':>12}  {'PyPI':>12}  "
          f"{'bound':<12} status")
    for s in sorted(wynik.stany, key=lambda s: (s.status != "nowsza",
                                                s.status != "brak", s.nazwa)):
        print(f"{s.nazwa.ljust(szerokosc)}  {(s.zainstalowana or '-'):>12}  "
              f"{(s.najnowsza or '-'):>12}  {(s.specyfikator or '-'):<12} "
              f"{ETYKIETY[s.status]}"
              + (f" ({s.powod})" if s.status == "nieznane" and s.powod else ""))

    print("\n========== DEPENDENCY GATE ==========")
    if wynik.degradacja:
        print(f"⚠️  Ran with REDUCED coverage: {wynik.degradacja}.")
    trafienia = [s for s in wynik.stany if s.trafienie]
    if not trafienia:
        print("✅ No dependency has a newer release that our manifest allows.")
    else:
        print(f"⚠️  {len(trafienia)} dependency/dependencies to decide about:")
        for s in trafienia:
            if s.status == "brak":
                print(f"      • {s.nazwa}: declared in the manifest but NOT "
                      f"installed here")
            else:
                print(f"      • {s.nazwa}: {s.zainstalowana} → {s.najnowsza} "
                      f"(manifest allows it)")
        print("Decide per package — and the size of the step decides which way:")
        print("  • PATCH-level step, surface unchanged: upgrade + `inspect."
              "signature` on the API we call (zero API calls, zero cost), then "
              "note it under `### What's new` in RELEASE_NOTES.md. This is the "
              "cheap, normal path.")
        print("  • MINOR or MAJOR step: hold it. The CONSERVATIVE CANON "
              "(2026-09-18) is to ship the release as it stands, note the "
              "pending upgrade under 'what did not make it', freeze the "
              "environment (`pip freeze > skrypty/zamrozone_<version>.txt`) and "
              "set the bound one step below the new release — so the hold is "
              "a RECORDED decision (status `bound excludes it`) and not "
              "silence. AFTER the release: move the bound, upgrade, test, tune, "
              "and ship that as its own patch / minor / major depending on how "
              "much moved — or restore the frozen version, leave a fixed bound "
              "and ship a dev patch, because an upgraded-then-restored bundle "
              "is the same bundle.")
        print("  • A `NOT INSTALLED` line is neither: the environment does not "
              "match the manifest, so fix the environment first.")
        print("A bound change is NOT dev-tools-only, so it escalates a "
              "shortened release to the full procedure.")
    print("=====================================")


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
    args = parser.parse_args()

    wynik = bramka([p for p in args.pakiety.split(",") if p.strip()] or None,
                   bez_sieci=args.bez_sieci)
    raport(wynik)
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
