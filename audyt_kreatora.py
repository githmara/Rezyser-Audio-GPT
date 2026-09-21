#!/usr/bin/env python
"""audyt_kreatora.py — bramka SYNCHRONIZACJI tekstów Managera Reguł z kodem.

Manager Reguł wystawia dla każdego z dziewięciu typów reguły dwa teksty:
SZABLON (plik YAML, który użytkownik dostaje na dysk) i PROMPT (instrukcję
dla agenta AI, który ten plik wypełni). Oba OPISUJĄ silnik — nazywają jego
pola, wartości, moduły, funkcje i pliki wzorcowe. Żaden z nich nie jest
wykonywany, więc zmiana w silniku nie łamie ich w żaden widoczny sposób:
opis po prostu zaczyna kłamać i kłamie do następnego przeczytania przez
człowieka.

DLACZEGO TO JEST BRAMKA, A NIE POZYCJA W CHECKLIŚCIE. Adresatem tych tekstów
jest ktoś, kto NIE MA jak sprawdzić, czy mówią prawdę: użytkownik zainstalowanej
paczki nie widzi źródeł, a agent AI, któremu wkleja prompt, uwierzy w każde
zdanie i wykona je dosłownie. Fałszywe zdanie w prompcie zamienia się w gotowy
plik, a nie w pytanie. Mierzone w v19.7: prompt postprodukcji wyliczał paczki
jako „(PL/DE/IT/RU/FI/IS/EN)", czyli siedem z dziewięciu, więc autor
postprodukcji dla `es` albo `fr` nie widział wzorca własnej paczki; komentarz
o `format_wyjscia` opisywał ścieżkę Anthropic sprzed v18.23; a szablon trybu
przez pewien czas nie renderował się WCALE (niepodwojone klamry w f-stringu).

Bramka NIE MA BASELINE'U, z tego samego powodu co `audyt_podstaw`: trafienie
znaczy „tekst dla użytkownika opisuje coś, czego nie ma", a taki stan nie ma
dopuszczalnej postaci. Naprawą jest zdanie w szablonie albo interpolacja
z kodu, nie negocjacja.

OSIEM KLAS:

  * ``render-blad``          — `zbuduj_wynik(typ)` rzuca wyjątkiem. Klasa
    pierwsza, bo unieruchamia cały typ w GUI: najczęstsza przyczyna to
    niepodwojona klamra w f-stringu szablonu (ta sama pułapka, przed którą
    szablon trybu Reżysera ostrzega w swoim własnym tekście).
  * ``modul-nieznany``       — cytowany `*.py` nie istnieje w repozytorium.
  * ``symbol-nieznany``      — cytowany `modul.symbol` nie istnieje w module.
  * ``plik-paczki-nieznany`` — cytowany `*.yaml` nie istnieje w paczce
    referencyjnej (`dictionaries/pl`). Prompty odsyłają do plików WZORCOWYCH;
    wzorzec, którego nie ma, to ślepa instrukcja „open before writing".
  * ``pole-nieznane``        — klucz wyrenderowanego szablonu nie jest polem,
    które silnik dla tej kategorii czyta. Szablon zapisuje PLIK, więc pole
    spoza modelu jest martwą literą w danych użytkownika.
  * ``pole-poza-promptem``   — klucz szablonu, o którym prompt nie mówi ani
    słowa. To jest rdzeń synchronizacji: prompt i szablon opisują JEDEN plik,
    a agent dostaje oba i uzupełnia ten drugi wg pierwszego.
  * ``wartosc-nielegalna``   — wartość pola enumeratywnego (`kategoria`,
    `zakres`, `format_wyjscia`, `struktura`, `rola`, `algorytm`) spoza zbioru,
    który silnik zna.
  * ``sciezka-nieznana``     — konkretna ścieżka `dictionaries/...` (bez
    placeholderów i bez pliku, który dopiero ma powstać) nie istnieje.

SONDA. Teksty są f-stringami parametryzowanymi przez id, etykietę, ISO i kod
paczki bazowej, więc bramka renderuje je dla ustalonej sondy: id `zzsonda`,
ISO `zz`, paczka bazowa `pl`. Wartości sondy są celowo takie, żeby nie dało
się ich pomylić z niczym realnym — ścieżka zawierająca `zzsonda` albo `/zz/`
to zawsze plik, który użytkownik ma dopiero utworzyć, i bramka ją pomija.

Łagodna degradacja jak w rodzinie: brak paczki referencyjnej na dysku wyłącza
klasy, które ją czytają (i mówi o tym na głos), zamiast wywracać bramkę.

Użycie:
  python audyt_kreatora.py            # raport (zero API, zero sieci)
  python audyt_kreatora.py --bramka   # GATE: exit 1 na jakimkolwiek trafieniu
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib
import re
import sys
from pathlib import Path

import yaml

import audyt_leakow as al
import dev_konsola
import manager_regul_szablony as mrs
import przepisy_rezysera as pr

dev_konsola.skonfiguruj_stdout()

NARZEDZIE = "audyt_kreatora"
ROOT = Path(__file__).resolve().parent

# Sonda: wartości, których nie sposób pomylić z realną regułą ani realną paczką.
SONDA_ID = "zzsonda"
SONDA_ISO = "zz"
SONDA_PACZKA = "pl"

_NOTY_DEGRADACJI: list[str] = []

# Rozszerzenia, które w zapisie `foo.bar` są NAZWĄ PLIKU, nie atrybutem modułu.
# Bez tego `core_poliglota.py` w prozie promptu czyta się jako „atrybut `py`
# modułu `core_poliglota`" i produkuje trafienie na każdym zdaniu o silniku.
_ROZSZERZENIA = {"py", "yaml", "yml", "md", "txt", "json", "iss", "exe", "html"}

_RE_MODUL = re.compile(r"`([a-z_0-9]+\.py)")
_RE_SYMBOL = re.compile(r"`([a-z_][a-z_0-9]*)\.([A-Za-z_][A-Za-z_0-9]*)")
_RE_PLIK_YAML = re.compile(r"`(?:[A-Za-z_0-9<>{}*/.-]*/)?([a-z_0-9]+\.yaml)")
_RE_SCIEZKA_DICT = re.compile(r"`(dictionaries/[A-Za-z_0-9<>{}*/.-]+)")

# Pola enumeratywne → zbiór wartości, które silnik REALNIE rozpoznaje. Puste
# `""` w `rola` znaczy „zwykłe narzędzie" i jest legalne. Źródłem są stałe
# `przepisy_rezysera`, nie kopia listy — inaczej bramka pilnowałaby własnej
# pamięci zamiast kodu.
def _wartosci_enumeratywne() -> dict[str, set[str]]:
    import core_poliglota as cp                                # noqa: PLC0415
    return {
        "kategoria":      {"akcent", "oczyszczenie", "naprawiacz", "szyfr",
                           pr.KATEGORIA_TRYB, pr.KATEGORIA_POSTPROD, "podstawy"},
        "zakres":         set(pr.ZAKRESY_DOZWOLONE),
        "format_wyjscia": set(pr.FORMATY_WYJSCIA),
        "struktura":      set(pr.STRUKTURY),
        "rola":           {"", pr.ROLA_PAMIEC_DLUGOTRWALA},
        "algorytm":       set(cp._ALGORYTMY_SZYFROW),
    }


@dataclasses.dataclass
class Znalezisko:
    """Jedno trafienie: gdzie (typ.pole), jaka klasa, co dokładnie."""

    zakres: str
    klasa: str
    szczegol: str


def _pakiet(typ: str) -> dict:
    """Renderuje pakiet kreatora dla sondy. Wyjątek zostawia wołającemu."""
    id_pliku = SONDA_ISO if typ == mrs.TYP_JEZYK_BAZOWY else SONDA_ID
    return mrs.zbuduj_wynik(typ, id_pliku=id_pliku, etykieta="Zzsonda",
                            iso=SONDA_ISO, jezyk_bazowy=SONDA_PACZKA,
                            opis_efektu="sonda")


def _czy_sonda(tekst: str) -> bool:
    """Czy ścieżka/nazwa dotyczy pliku, który użytkownik dopiero utworzy?"""
    return (SONDA_ID in tekst or SONDA_ISO + "/" in tekst
            or tekst.startswith(SONDA_ISO) or f"/{SONDA_ISO}/" in tekst)


def _pliki_paczki_referencyjnej() -> set[str]:
    """Nazwy plików YAML paczki `pl` — orakuł klasy `plik-paczki-nieznany`."""
    folder = ROOT / "dictionaries" / SONDA_PACZKA
    if not folder.is_dir():
        nota = (f"reference pack `{SONDA_PACZKA}` not on disk — the gate did "
                f"NOT check the YAML files the prompts point at")
        if nota not in _NOTY_DEGRADACJI:
            _NOTY_DEGRADACJI.append(nota)
        return set()
    return {p.name for p in folder.rglob("*.yaml")}


def _pola_modelu(docelowy: str) -> set[str]:
    """Pola, które silnik czyta w pliku o tej ścieżce docelowej.

    Dwa źródła i oba są potrzebne. `buduj_wielojezyczne_akcenty.KLASY_POL`
    plus pola przepisu Reżysera mówią, co silnik czyta Z KODU; klucze REALNYCH
    plików paczki referencyjnej dokładają to, co kod czyta bez deklaracji
    (`podstawy.yaml` nie ma dataclassy, a jego kształt jest umową paczek pl/en).
    Sama paczka referencyjna nie wystarczy: żaden wdrożony szyfr nie ma jeszcze
    listy `zamiany`, choć silnik ją czyta od v19.6 — model oparty wyłącznie na
    dysku uznałby własny szablon Managera za błąd.
    """
    import buduj_wielojezyczne_akcenty as bwa                  # noqa: PLC0415
    pola = set(bwa.KLASY_POL) | {"algorytm", "rozwiniecia", "alfabet"}
    czesci = docelowy.split("/")
    podfolder = czesci[1] if len(czesci) > 2 else ""
    if podfolder == "rezyser":
        pola |= {f.name for f in dataclasses.fields(pr.PrzepisRezysera)}
    wzor = (f"dictionaries/{SONDA_PACZKA}/{podfolder}/*.yaml" if podfolder
            else f"dictionaries/{SONDA_PACZKA}/podstawy.yaml")
    znalezione = False
    for plik in ROOT.glob(wzor):
        znalezione = True
        # `mrs._wczytaj_yaml` melduje awarię do wspólnego rejestru pominięć
        # i zwraca `{}` — ten sam loader, którego używa moduł szablonów, więc
        # bramka nie ma własnej, cichszej ścieżki czytania tych samych plików.
        pola |= set(mrs._wczytaj_yaml(plik))
    if not znalezione:
        nota = (f"no reference file matched `{wzor}` — the field model for "
                f"that folder came from code only")
        if nota not in _NOTY_DEGRADACJI:
            _NOTY_DEGRADACJI.append(nota)
    return pola


def _sprawdz_cytaty(typ: str, pole: str, tekst: str, pliki_paczki: set[str],
                    zglos) -> None:
    """Klasy `modul-nieznany`, `symbol-nieznany`, `plik-paczki-nieznany`,
    `sciezka-nieznana` — wszystko, co tekst nazywa po imieniu."""
    for m in _RE_MODUL.finditer(tekst):
        if not (ROOT / m.group(1)).exists():
            zglos("modul-nieznany",
                  f"{pole} cites `{m.group(1)}`, which is not in the repository")
    for m in _RE_SYMBOL.finditer(tekst):
        modul, atrybut = m.group(1), m.group(2)
        if atrybut in _ROZSZERZENIA or not (ROOT / f"{modul}.py").exists():
            continue
        try:
            obiekt = importlib.import_module(modul)
        except ImportError as exc:
            nota = f"`{modul}` not importable ({exc}) — its symbols unchecked"
            if nota not in _NOTY_DEGRADACJI:
                _NOTY_DEGRADACJI.append(nota)
            continue
        if not hasattr(obiekt, atrybut):
            zglos("symbol-nieznany",
                  f"{pole} cites `{modul}.{atrybut}`, which the module does "
                  f"not define")
    if pliki_paczki:
        for m in _RE_PLIK_YAML.finditer(tekst):
            nazwa = m.group(1)
            if _czy_sonda(nazwa) or nazwa in pliki_paczki:
                continue
            zglos("plik-paczki-nieznany",
                  f"{pole} points at `{nazwa}` as a model to open, but no such "
                  f"file exists in the reference pack `{SONDA_PACZKA}`")
    for m in _RE_SCIEZKA_DICT.finditer(tekst):
        sciezka = m.group(1).rstrip(".,;:").split("::")[0]
        if any(znak in sciezka for znak in "<>{}*") or _czy_sonda(sciezka):
            continue
        if not (ROOT / sciezka).exists():
            zglos("sciezka-nieznana",
                  f"{pole} cites the path `{sciezka}`, which does not exist")


def _sprawdz_szablon(typ: str, pakiet: dict, zglos) -> None:
    """Klasy `pole-nieznane`, `pole-poza-promptem`, `wartosc-nielegalna`.

    Wzmianka w prompcie jest liczona LIBERALNIE — wystarczy nazwa pola jako
    osobne słowo, w dowolnej formie zapisu. Prompty piszą o polach na kilka
    sposobów naraz (`` `pole:` ``, „Fields: `id`, `etykieta`", „the `rola:`
    value"), więc wymaganie jednego kształtu produkowałoby trafienia na
    tekstach, które swoje zadanie wykonują. Bramka pyta „czy prompt w ogóle
    o tym polu mówi", bo to jest pytanie, na które źle odpowiedzieć da się
    tylko przez przeoczenie.
    """
    surowy = pakiet.get("yaml") or ""
    if not surowy:
        return                       # typ PROMPT-only: nie ma szablonu do badania
    try:
        cfg = yaml.safe_load(surowy)
    except yaml.YAMLError as exc:
        zglos("render-blad",
              f"the rendered template is not valid YAML: "
              f"{str(exc).splitlines()[0] if str(exc) else type(exc).__name__}")
        return
    if not isinstance(cfg, dict):
        zglos("render-blad",
              f"the rendered template parses to {type(cfg).__name__}, not to "
              f"a mapping")
        return

    model = _pola_modelu(pakiet["docelowy"])
    for klucz in sorted(set(cfg) - model):
        zglos("pole-nieznane",
              f"the template writes `{klucz}:`, which the engine does not read "
              f"for `{pakiet['docelowy']}` — the user gets a dead line in their "
              f"own file")

    prompt = pakiet.get("prompt") or ""
    if prompt:
        for klucz in sorted(cfg):
            if not re.search(rf"\b{re.escape(klucz)}\b", prompt):
                zglos("pole-poza-promptem",
                      f"the template writes `{klucz}:` and the prompt never "
                      f"mentions it — the agent filling the file has no "
                      f"instruction for that line")

    legalne = _wartosci_enumeratywne()
    for klucz, dozwolone in legalne.items():
        if klucz not in cfg:
            continue
        wartosc = cfg[klucz]
        if not isinstance(wartosc, str):
            continue
        if wartosc.strip() not in dozwolone:
            zglos("wartosc-nielegalna",
                  f"the template sets `{klucz}: {wartosc}`, which is not one of "
                  f"{sorted(dozwolone)} — the engine would fall back to its "
                  f"default or skip the file")


def zbierz() -> dict[str, list[str]]:
    """Trafienia jako `{"<typ>": ["<klasa>|<szczegol>", …]}` — kanon raportu."""
    _NOTY_DEGRADACJI.clear()
    znaleziska: list[Znalezisko] = []
    pliki_paczki = _pliki_paczki_referencyjnej()

    for typ in mrs.LISTA_TYPOW:
        def zglos(klasa: str, szczegol: str, _typ: str = typ) -> None:
            znaleziska.append(Znalezisko(_typ, klasa, szczegol))

        try:
            pakiet = _pakiet(typ)
        except Exception as exc:                               # noqa: BLE001
            # KAŻDY wyjątek, bo chodzi o to, że typ nie da się w ogóle wystawić
            # użytkownikowi — a najczęstsza przyczyna (`ValueError` z
            # `str.format`) niczym się nie wyróżnia spośród innych.
            zglos("render-blad",
                  f"`zbuduj_wynik({typ!r})` raised {type(exc).__name__}: {exc} "
                  f"— this type cannot be produced in the GUI at all")
            continue
        for pole in ("yaml", "prompt"):
            tekst = pakiet.get(pole) or ""
            if tekst:
                _sprawdz_cytaty(typ, pole, tekst, pliki_paczki, zglos)
        _sprawdz_szablon(typ, pakiet, zglos)

    wynik: dict[str, list[str]] = {}
    for z in znaleziska:
        wynik.setdefault(z.zakres, []).append(f"{z.klasa}|{z.szczegol}")
    return {k: sorted(v) for k, v in wynik.items()}


def bramka() -> al.WynikBramki:
    """Bramka kreatora. BEZ baseline'u — każde trafienie blokuje."""
    aktualne = zbierz()
    return al.WynikBramki(not aktualne, aktualne,
                          degradacja="; ".join(_NOTY_DEGRADACJI))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate over the Manager Reguł creator texts: every template "
                    "and prompt must describe the engine that actually exists. "
                    "Checks that each of the nine rule types renders at all, "
                    "that the modules, symbols, pack files and paths they cite "
                    "exist, that the template writes only fields the engine "
                    "reads, that the prompt mentions every field the template "
                    "writes, and that enumerated values are ones the engine "
                    "knows. No baseline: a lying description has no acceptable "
                    "form.")
    parser.add_argument("--bramka", action="store_true",
                        help="GATE mode: exit 1 on any finding.")
    args = parser.parse_args()

    wynik = bramka()
    print("\n===== CREATOR-TEXT SYNC GATE (Manager Reguł) =====")
    if wynik.degradacja:
        print(f"⚠️  Ran with REDUCED coverage: {wynik.degradacja}.")
    if wynik.czysto:
        print(f"✅ All {len(mrs.LISTA_TYPOW)} creator type(s) render, and every "
              f"module, symbol, pack file, path, field and enumerated value "
              f"they cite exists in the engine.")
    else:
        ile = sum(len(v) for v in wynik.nowe.values())
        print(f"❌ {ile} finding(s) in {len(wynik.nowe)} creator type(s):")
        for typ, powody in sorted(wynik.nowe.items()):
            print(f"  • {typ}")
            for powod in powody:
                klasa, _, szczegol = powod.partition("|")
                print(f"      - [{klasa}] {szczegol}")
        print("Fix: change the TEXT, or interpolate the value from code the way "
              "`_sklad_rezysera` / `_regexy_rozdzialow` / `_algorytmy_szyfrow` "
              "already do in `manager_regul_szablony`. A creator text is read by "
              "someone who cannot verify it.")
    print("=" * 50)
    return 1 if (args.bramka and not wynik.czysto) else 0


if __name__ == "__main__":
    sys.exit(main())
