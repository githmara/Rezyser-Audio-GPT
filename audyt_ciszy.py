#!/usr/bin/env python
"""audyt_ciszy.py — bramka na CICHE pominięcie pliku YAML (runtime i dev-toole).

Geneza (v18.28.0). Wzorcem jest `audyt_leakow._wczytaj_yaml_lub_padnij`: plik,
którego nie umiemy przeczytać ALBO który parsuje się do czegoś innego niż
oczekiwany kształt (goły skalar, lista, `null` po wykasowaniu treści), jest
błędem FATALNYM, a nie powodem do zwrócenia pustego słownika. Powód jest
niezmienny od v18.9: bramka nie ma prawa zameldować „czysto" o pliku, którego
nie przeczytała — a `return {}` w handlerze wygląda z zewnątrz DOKŁADNIE tak
samo jak plik bez uwag.

Ta bramka mierzy, czy reszta drzewa trzyma ten sam standard. Skanuje AST i
zgłasza TRZY klasy:

  * ``except-cichy``  — `try` z wczytaniem YAML-a, którego handler nie robi NIC
    poza `return` / `continue` / `pass`: ani `raise`, ani zgłoszenia do rejestru,
    ani nawet linii na konsolę.
  * ``ksztalt-cichy`` — kontrola kształtu korzenia (`isinstance(dane, dict)`)
    zwracająca wartość domyślną bez ani jednego słowa. To druga połowa reguły
    z v18.9 i bez niej łata jest niepełna: plik, który PARSUJE SIĘ poprawnie,
    ale nie do mapy, wracał jako „czysto" (v18.26.1).
  * ``or-domyslny``   — `yaml.safe_load(fh) or {}`, czyli zamiecenie pustego
    (albo skalarnego!) korzenia pod dywan w jednym wyrażeniu.

Czego bramka NIE zgłasza (świadomie):
  * braku pliku (`if not plik.is_file(): return {}`) — nie każda paczka ma każdy
    szablon, więc pusty wynik jest tam legalny i tylko WOŁAJĄCY wie, co znaczy
    brak jego pliku;
  * handlera, który cokolwiek MÓWI — `raise`, `zglos_pominiecie`, `_zglos_awarie`,
    `print`, `_dev_log`. Wymóg mocniejszy („dane edytowalne przez użytkownika
    raportuj do rejestru, bo w buildzie `--windowed` konsoli nie ma") jest
    sprawą przeglądu, nie tej bramki. Ta pilnuje wyłącznie CISZY.

Wzorzec bramki jak w rodzinie `audyt_leakow`: LEJEK over-raportujący + BASELINE
(`audyt_ciszy_baseline.json`), więc blokuje wyłącznie trafienia NOWE. Baseline
wchodzi do repo pusty — po v18.28.0 nie ma w drzewie ani jednego cichego
pominięcia, a każdy nowy wpis to regres, nie „zastany dług".

Użycie:
  python audyt_ciszy.py                    # raport per plik (zero API)
  python audyt_ciszy.py --bramka           # GATE: exit 1 na trafieniach ponad baseline
  python audyt_ciszy.py --zapisz-baseline  # regeneracja baseline'u (przeczytaj diff!)
"""
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

import audyt_leakow as al
import dev_konsola

dev_konsola.skonfiguruj_stdout()

ROOT = Path(__file__).resolve().parent
BASELINE_PATH = ROOT / "audyt_ciszy_baseline.json"

# Zasięg skanu: korzeń repo + skrypty botów. `skrypty/` NIE wchodzi — to
# jednorazowe walidatory z konkretnych wydań (`walidacja_1812.py`), których nikt
# nie utrzymuje i które nie chodzą ani w buildzie, ani u kontrybutora.
# `runtime/` też nie: tam leży portable Python (8073 pliki).
KATALOGI_SKANU: tuple[tuple[str, str], ...] = (
    (".", "*.py"),
    (".github/scripts", "*.py"),
)

# Nazwy metod wczytujących YAML. `safe_load` bierzemy bez pytania o odbiornik
# (`yaml`, `_pyyaml`, alias — zawsze to samo), a gołe `load` tylko wtedy, gdy
# odbiornik wygląda na parser YAML-a: `YAML(typ="safe").load`, `yaml_io.load`,
# `_yaml_safe().load`. Bez tego zawężenia łapalibyśmy `json.load` i `dotenv`.
METODY_YAML = {"safe_load", "unsafe_load", "full_load"}
METODA_NIEJEDNOZNACZNA = "load"
_TOKENY_YAML = ("yaml", "YAML")

# Wywołania, które łamią ciszę. `print`/`_dev_log` są tu ŚWIADOMIE, mimo że
# w paczce `--windowed` stdout jest `None`: mocniejszy wymóg (rejestr powodów
# dla danych, które user edytuje) pilnuje przegląd, nie ta bramka.
WOLANIA_GLOSNE = {
    "zglos_pominiecie", "_zglos_awarie", "_zglos_awarie_ui",
    "padnij_na_pliku", "_padnij_na_pliku", "padnij",
    "wczytaj_lub_padnij", "wczytaj_yaml_lub_padnij", "_wczytaj_yaml_lub_padnij",
    "ostrzez", "_ostrzez", "zglos", "print",
    "_dev_log", "_dev_log_runtime", "warning", "error", "exception",
    # Kanały wxPython: Konstytucja wskazuje `wx.MessageBox` jako właściwe
    # miejsce krótkiego powiadomienia, a dialog `ShowModal` — długiego. Handler,
    # który je woła, MÓWI użytkownikowi; pierwsza wersja bramki raportowała go
    # jako cichego (fałszywy alarm złapany audytem v18.28.0).
    "MessageBox", "ShowModal", "LogError", "LogWarning",
}

# Menedżery kontekstu, które POŁYKAJĄ wyjątek bez `except` — `ast.Try` nie
# istnieje, więc klasa `except-cichy` nie miałaby czego oglądać.
TLUMIKI_KONTEKSTOWE = {"suppress"}

# Typy kształtu korzenia, których szukamy w `isinstance(...)`.
TYPY_KSZTALTU = {"dict", "list", "str", "tuple", "set"}


@dataclass
class Znalezisko:
    """Jedno ciche pominięcie pliku YAML."""
    plik: str
    linia: int
    zakres: str      # nazwa funkcji (albo „<modul>")
    klasa: str       # except-cichy | ksztalt-cichy | or-domyslny
    szczegol: str    # np. „except OSError, YAMLError → return"

    def __str__(self) -> str:
        return f"L{self.linia} [{self.zakres}] {self.klasa}: {self.szczegol}"


# ---------------------------------------------------------------------------
# Rozpoznanie wywołania wczytującego YAML
# ---------------------------------------------------------------------------
def _czy_wczytanie_yaml(wezel: ast.AST) -> bool:
    """Czy ten węzeł jest wywołaniem parsera YAML-a?

    Odbiornik oceniamy po ŹRÓDLE (`ast.unparse`), nie po typie: w tym drzewie
    parser bywa aliasem (`_pyyaml`), wynikiem fabryki (`_yaml_safe()`) i obiektem
    round-tripowym (`yaml_io`), a wszystkie trzy prowadzą do tego samego pliku
    na dysku.
    """
    if not isinstance(wezel, ast.Call) or not isinstance(wezel.func, ast.Attribute):
        return False
    if wezel.func.attr in METODY_YAML:
        return True
    if wezel.func.attr != METODA_NIEJEDNOZNACZNA:
        return False
    zrodlo = ast.unparse(wezel.func.value)
    return any(token in zrodlo for token in _TOKENY_YAML)


def _zawiera_wczytanie_yaml(wezel: ast.AST) -> bool:
    """Czy w poddrzewie jest wczytanie YAML-a?"""
    return any(_czy_wczytanie_yaml(w) for w in ast.walk(wezel))


def _glosny(wezel: ast.AST) -> bool:
    """Czy poddrzewo cokolwiek MÓWI (raise / zgłoszenie / log / zapis na stderr)?"""
    for w in ast.walk(wezel):
        if isinstance(w, ast.Raise):
            return True
        if not isinstance(w, ast.Call):
            continue
        nazwa = (w.func.attr if isinstance(w.func, ast.Attribute)
                 else getattr(w.func, "id", ""))
        if nazwa in WOLANIA_GLOSNE:
            return True
        # `sys.stderr.write(...)` — kanał bota GitHub Actions (`bot_i18n`),
        # który świadomie degraduje głośno zamiast padać: zgłoszenie
        # użytkownika bez odpowiedzi byłoby gorsze niż gorsza detekcja języka.
        if (nazwa == "write" and isinstance(w.func, ast.Attribute)
                and any(strumien in ast.unparse(w.func.value)
                        for strumien in ("stderr", "stdout"))):
            return True
    return False


def _opis_handlera(handler: ast.ExceptHandler) -> str:
    """„except OSError, YAMLError" — do czytelnego szczegółu w raporcie."""
    if handler.type is None:
        return "except:"
    return "except " + ast.unparse(handler.type)


def _wyjscie_handlera(handler: ast.ExceptHandler) -> str:
    """Jak handler kończy pracę: return / continue / break / pass."""
    for w in ast.walk(handler):
        if isinstance(w, ast.Return):
            return "return " + (ast.unparse(w.value) if w.value else "None")
        if isinstance(w, ast.Continue):
            return "continue"
        if isinstance(w, ast.Break):
            return "break"
    return "pass"


# ---------------------------------------------------------------------------
# Kontrola kształtu korzenia
# ---------------------------------------------------------------------------
def _zmienne_korzenia(zakres: ast.AST) -> set[str]:
    """Nazwy, pod którymi w tym zakresie siedzi KORZEŃ wczytanego pliku.

    Zawężenie zmierzone (pomiar 1 → 2): bez niego bramka zgłaszała kontrole
    POJEDYNCZYCH PÓL (`isinstance(etykieta, str)`, `isinstance(sekcja, dict)`),
    których cisza nie ma nic wspólnego z pominięciem PLIKU — brak pola to
    normalny stan świeżej paczki, a wołający zwykle degraduje o tym głośno.
    Bramka pyta o jedno: czy plik został przeczytany. Więc pyta o jego korzeń.
    """
    nazwy: set[str] = set()
    for w in ast.walk(zakres):
        if isinstance(w, (ast.Assign, ast.AnnAssign)) and w.value is not None:
            if not _zawiera_wczytanie_yaml(w.value):
                continue
            cele = w.targets if isinstance(w, ast.Assign) else [w.target]
            for cel in cele:
                if isinstance(cel, ast.Name):
                    nazwy.add(cel.id)
    return nazwy


def _test_ksztaltu(test: ast.AST, korzenie: set[str]) -> tuple[str, bool]:
    """`isinstance(<korzeń>, <typ>)` w teście → (typ, czy_zaprzeczony).

    `czy_zaprzeczony` mówi, KTÓRA gałąź jest ścieżką porażki: przy `not
    isinstance(...)` jest nią `body`, przy gołym `isinstance(...)` — `orelse`.
    Liczymy to po przodkach konkretnego węzła, a nie po kształcie całego testu,
    bo `if isinstance(x, str) and x.strip():` to `BoolOp` BEZ zaprzeczenia
    (pierwsza wersja bramki brała tam `body` i produkowała FP).
    """
    for w in ast.walk(test):
        if not (isinstance(w, ast.Call) and isinstance(w.func, ast.Name)
                and w.func.id == "isinstance" and len(w.args) == 2):
            continue
        if not (isinstance(w.args[0], ast.Name) and w.args[0].id in korzenie):
            continue
        nazwy = [n.id for n in ast.walk(w.args[1]) if isinstance(n, ast.Name)]
        trafione = [n for n in nazwy if n in TYPY_KSZTALTU]
        if not trafione:
            continue
        zaprzeczony = any(
            isinstance(rodzic, ast.UnaryOp) and isinstance(rodzic.op, ast.Not)
            and any(dziecko is w for dziecko in ast.walk(rodzic.operand))
            for rodzic in ast.walk(test)
        )
        return trafione[0], zaprzeczony
    return "", False


def _bloki(zakres: ast.AST):
    """Wszystkie listy instrukcji w zakresie (`body`/`orelse`/`finalbody`).

    Bramka musi widzieć SĄSIADÓW instrukcji `if`, nie tylko ją samą — patrz
    :func:`_znajdz_ksztalt_cichy`, gałąź „fall-through".
    """
    for w in ast.walk(zakres):
        for pole in ("body", "orelse", "finalbody"):
            ciało = getattr(w, pole, None)
            if isinstance(ciało, list) and ciało and isinstance(ciało[0], ast.stmt):
                yield ciało


def _konczy_przeplyw(instrukcje: list[ast.stmt]) -> bool:
    """Czy blok kończy przepływ (`return`/`continue`/`break`/`raise`)?"""
    return bool(instrukcje) and isinstance(
        instrukcje[-1], (ast.Return, ast.Continue, ast.Break, ast.Raise))


def _znajdz_ksztalt_cichy(zakres: ast.AST, nazwa_zakresu: str,
                          plik: str) -> list[Znalezisko]:
    """Kontrole kształtu KORZENIA, które NIC nie mówią."""
    korzenie = _zmienne_korzenia(zakres)
    if not korzenie:
        return []
    wyniki: list[Znalezisko] = []

    # (1) `dane if isinstance(dane, dict) else {}` — w wyrażeniu nie ma nawet
    #     miejsca na komunikat, więc zawsze jest ciche.
    for w in ast.walk(zakres):
        if not isinstance(w, ast.IfExp):
            continue
        typ, zaprzeczony = _test_ksztaltu(w.test, korzenie)
        if typ:
            galaz = w.body if zaprzeczony else w.orelse
            wyniki.append(Znalezisko(
                plik, getattr(w, "lineno", 0), nazwa_zakresu, "ksztalt-cichy",
                f"isinstance(korzeń, {typ}) w wyrażeniu warunkowym → "
                f"{ast.unparse(galaz)}"))

    # (2) `if not isinstance(dane, dict): return {}` — gałąź porażki bez słowa.
    #     Idziemy po BLOKACH, nie po pojedynczych węzłach, bo trzecia forma tej
    #     samej semantyki nie ma własnej gałęzi (audyt v18.28.0):
    #         if isinstance(dane, dict):
    #             return dane
    #         return {}            # ← ścieżka porażki leży PO instrukcji `if`
    #     Pierwsza wersja bramki brała tu `orelse`, czyli pustą listę, i
    #     przepuszczała dokładnie ten sam defekt, który łapała w zapisie
    #     wyrażeniem warunkowym. „Po instrukcji" liczy się jako gałąź porażki
    #     WYŁĄCZNIE wtedy, gdy gałąź pozytywna kończy przepływ — inaczej dalszy
    #     kod jest wspólny dla obu ścieżek i nic nie orzeka o pominięciu.
    for blok in _bloki(zakres):
        for i, instrukcja in enumerate(blok):
            if not isinstance(instrukcja, ast.If):
                continue
            typ, zaprzeczony = _test_ksztaltu(instrukcja.test, korzenie)
            if not typ:
                continue
            if zaprzeczony:
                galaz: list[ast.stmt] = list(instrukcja.body)
            elif instrukcja.orelse:
                galaz = list(instrukcja.orelse)
            elif _konczy_przeplyw(instrukcja.body):
                galaz = list(blok[i + 1:])
            else:
                galaz = []
            if not galaz:
                continue
            if _glosny(ast.Module(body=list(galaz), type_ignores=[])):
                continue
            wyjscie = _wyjscie_handlera(
                ast.ExceptHandler(type=None, name=None, body=list(galaz)))
            wyniki.append(Znalezisko(
                plik, getattr(instrukcja, "lineno", 0), nazwa_zakresu,
                "ksztalt-cichy", f"isinstance(korzeń, {typ}) → {wyjscie}"))
    return wyniki


def _znajdz_or_domyslny(zakres: ast.AST, nazwa_zakresu: str,
                        plik: str) -> list[Znalezisko]:
    """`yaml.safe_load(fh) or {}` i `dane or {}` — korzeń zamieciony wyrażeniem.

    Druga forma dopisana po pomiarze 2, bo pierwsza wersja przegapiła NAJGORSZY
    przypadek w drzewie: `opowiesci_ai._zaladuj_przepis` kończyło się `return
    dane or {}`, gdzie `dane` to świeży korzeń pliku. Dla gołego skalara (plik
    zredukowany do jednego napisu) wyrażenie jest PRAWDZIWE, więc funkcja
    oddawała stringa tam, gdzie wołający robi `.get(...)` — czyli nie cisza,
    a wywrócony panel. Wzorzec `(dane or {}).get(...)` z tej samej rodziny.
    """
    korzenie = _zmienne_korzenia(zakres)
    wyniki: list[Znalezisko] = []
    for w in ast.walk(zakres):
        if not (isinstance(w, ast.BoolOp) and isinstance(w.op, ast.Or)):
            continue
        if not w.values:
            continue
        pierwszy = w.values[0]
        czy_korzen = (
            _czy_wczytanie_yaml(pierwszy)
            or (isinstance(pierwszy, ast.Name) and pierwszy.id in korzenie)
        )
        if not czy_korzen:
            continue
        wyniki.append(Znalezisko(
            plik, getattr(w, "lineno", 0), nazwa_zakresu, "or-domyslny",
            f"{ast.unparse(w)[:80]}"))
    return wyniki


# ---------------------------------------------------------------------------
# Skan pliku
# ---------------------------------------------------------------------------
def _zakresy(drzewo: ast.Module) -> list[tuple[str, ast.AST]]:
    """Funkcje pliku + sam moduł (bez ciał funkcji) jako osobne zakresy.

    Zakres per FUNKCJA, bo cisza jest własnością jednej ścieżki wczytania:
    plik ma zwykle jeden loader poprawny i jeden zapomniany, a zasięg pliku
    zrównałby je ze sobą.
    """
    wynik: list[tuple[str, ast.AST]] = []
    for w in ast.walk(drzewo):
        if isinstance(w, (ast.FunctionDef, ast.AsyncFunctionDef)):
            wynik.append((w.name, w))
    poziom_modulu = [
        s for s in drzewo.body
        if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    if poziom_modulu:
        wynik.append(("<modul>", ast.Module(body=poziom_modulu, type_ignores=[])))
    return wynik


def skanuj_plik(sciezka: Path) -> list[Znalezisko]:
    """Wszystkie ciche pominięcia YAML-a w jednym pliku `.py`."""
    try:
        drzewo = ast.parse(sciezka.read_text(encoding="utf-8"), filename=str(sciezka))
    except (OSError, SyntaxError) as exc:
        raise SystemExit(
            f"❌ audyt_ciszy: cannot parse {sciezka} ({exc}) — a scan of this file "
            f"would be falsely \"clean\"."
        ) from exc

    nazwa = sciezka.name
    wyniki: list[Znalezisko] = []
    for nazwa_zakresu, zakres in _zakresy(drzewo):
        if not _zawiera_wczytanie_yaml(zakres):
            continue
        # (a) handlery `try`, w których wczytujemy YAML
        for w in ast.walk(zakres):
            if not isinstance(w, ast.Try):
                continue
            if not any(_zawiera_wczytanie_yaml(s) for s in w.body):
                continue
            for handler in w.handlers:
                if _glosny(handler):
                    continue
                wyniki.append(Znalezisko(
                    nazwa, handler.lineno, nazwa_zakresu, "except-cichy",
                    f"{_opis_handlera(handler)} → {_wyjscie_handlera(handler)}"))
        # (a') `with contextlib.suppress(...)` — połknięcie wyjątku BEZ `except`,
        # więc niewidoczne dla pętli wyżej (audyt v18.28.0). Dziś w drzewie nie
        # występuje i o to chodzi: bramka ma trzymać ten wzorzec z daleka.
        for w in ast.walk(zakres):
            if not isinstance(w, (ast.With, ast.AsyncWith)):
                continue
            tlumiki = [
                ast.unparse(poz.context_expr)
                for poz in w.items
                if isinstance(poz.context_expr, ast.Call)
                and (getattr(poz.context_expr.func, "attr", "")
                     in TLUMIKI_KONTEKSTOWE
                     or getattr(poz.context_expr.func, "id", "")
                     in TLUMIKI_KONTEKSTOWE)
            ]
            if not tlumiki or not _zawiera_wczytanie_yaml(w):
                continue
            wyniki.append(Znalezisko(
                nazwa, w.lineno, nazwa_zakresu, "except-cichy",
                f"with {tlumiki[0]} wokół wczytania YAML-a"))
        # (b) kontrola kształtu i (c) `or {}`
        wyniki.extend(_znajdz_ksztalt_cichy(zakres, nazwa_zakresu, nazwa))
        wyniki.extend(_znajdz_or_domyslny(zakres, nazwa_zakresu, nazwa))
    return wyniki


def pliki_skanu(root: Path = ROOT) -> list[Path]:
    """Lista plików `.py` w zasięgu bramki (deterministycznie posortowana)."""
    pliki: list[Path] = []
    for podkatalog, wzorzec in KATALOGI_SKANU:
        katalog = root / podkatalog
        if not katalog.is_dir():
            continue
        pliki.extend(sorted(katalog.glob(wzorzec)))
    return pliki


def skanuj(root: Path = ROOT) -> list[Znalezisko]:
    """Skan całego zasięgu."""
    wyniki: list[Znalezisko] = []
    for sciezka in pliki_skanu(root):
        wyniki.extend(skanuj_plik(sciezka))
    return wyniki


def zbierz(root: Path = ROOT) -> dict[str, list[str]]:
    """Skan jako `{"<plik>": ["<zakres>|<klasa>|<szczegol>", …]}` — kanon baseline'u.

    Klucz bez numeru linii (odporny na przesunięcia), wartość to multiset —
    dokładnie ten sam kanon co pozostałe baseline'y rodziny.
    """
    wynik: dict[str, list[str]] = {}
    for z in skanuj(root):
        wynik.setdefault(z.plik, []).append(f"{z.zakres}|{z.klasa}|{z.szczegol}")
    return {k: sorted(v) for k, v in wynik.items()}


def bramka() -> al.WynikBramki:
    """Bramka ciszy względem `audyt_ciszy_baseline.json` (bez zależności od lingui)."""
    aktualne = zbierz()
    nowe = al.roznica_wzgledem_baseline(aktualne, al.wczytaj_baseline(BASELINE_PATH))
    return al.WynikBramki(not nowe, nowe, False, "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate against SILENTLY skipping a YAML file (runtime and dev "
                    "tools): a swallowed parse error, an unreported root-shape "
                    "mismatch (bare scalar / list / null) or `... or {}` on the "
                    "load result.",
    )
    grupa = parser.add_mutually_exclusive_group()
    grupa.add_argument("--bramka", action="store_true",
                       help="CI/build GATE: exit 1 on hits above the baseline "
                            f"({BASELINE_PATH.name}).")
    grupa.add_argument("--zapisz-baseline", dest="zapisz_baseline", action="store_true",
                       help="Regenerate the baseline from the current scan. Overwrites "
                            f"{BASELINE_PATH.name} — review the diff before committing.")
    args = parser.parse_args()

    if args.zapisz_baseline:
        aktualne = zbierz()
        al.zapisz_baseline(aktualne, BASELINE_PATH)
        ile = sum(len(v) for v in aktualne.values())
        print(f"✅ Saved the silence baseline: {ile} hit(s) in {len(aktualne)} file(s) → "
              f"{BASELINE_PATH.name}. Review the diff before committing.")
        return 0

    if args.bramka:
        wynik = bramka()
        print("========== YAML SILENCE GATE (vs baseline) ==========")
        if wynik.czysto:
            print(f"✅ No silently skipped YAML file above the baseline "
                  f"({BASELINE_PATH.name}).")
            print("====================================================")
            return 0
        ile = sum(len(v) for v in wynik.nowe.values())
        print(f"❌ {ile} silent skip(s) ABOVE the baseline in {len(wynik.nowe)} file(s):")
        for klucz, powody in sorted(wynik.nowe.items()):
            for p in powody:
                print(f"  • {klucz}: {p}")
        print("Fix: in a dev tool make it FATAL (`dev_yaml.wczytaj_lub_padnij`); in the "
              "runtime report the reason to the registry (`przepisy_rezysera."
              "zglos_pominiecie` / `i18n._zglos_awarie`). If the empty result is "
              "genuinely legitimate — regenerate the baseline: "
              f"`python {Path(__file__).name} --zapisz-baseline` and commit the diff.")
        print("====================================================")
        return 1

    znaleziska = skanuj()
    if not znaleziska:
        print("✅ Skan ciszy: żaden plik YAML nie jest pomijany bez słowa.")
        return 0
    per_plik: dict[str, list[Znalezisko]] = {}
    for z in znaleziska:
        per_plik.setdefault(z.plik, []).append(z)
    print(f"🔎 Skan ciszy: {len(znaleziska)} trafień w {len(per_plik)} plik(ach) "
          f"({len(pliki_skanu())} przeskanowanych).\n")
    for plik in sorted(per_plik):
        print(f"📄 {plik}: {len(per_plik[plik])}")
        for z in sorted(per_plik[plik], key=lambda z: z.linia):
            print(f"   · {z}")
        print()
    licznik: dict[str, int] = {}
    for z in znaleziska:
        licznik[z.klasa] = licznik.get(z.klasa, 0) + 1
    print("========== TOTAL: "
          + ", ".join(f"{k} {v}" for k, v in sorted(licznik.items()))
          + " ==========")
    return 1


if __name__ == "__main__":
    sys.exit(main())
