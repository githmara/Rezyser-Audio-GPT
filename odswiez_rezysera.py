"""
odswiez_rezysera.py – Generator wrapperów akcentów dla trybu Reżysera.

Moduł używany w DWÓCH miejscach:

1. Z GUI: przycisk „🔄 Odśwież akcenty Reżysera z YAML" w ``HomePanel``
   (``main.py``) woła :func:`uruchom` i wyświetla zebrany log w dialogu.

2. Z CLI (dla developerów i automatyzacji):
       .venv/Scripts/python.exe odswiez_rezysera.py

Co robi: skanuje ``dictionaries/<jezyk>/akcenty/*.yaml`` (kategoria ``akcent``)
i regeneruje DWA fragmenty kodu:

* W ``core_poliglota.py`` – definicje ``akcent_<id>(tekst)`` między markerami
  ``# <GENEROWANE_AKCENTY_REZYSERA_START>`` / ``...END``.
* W ``core_rezyser.py`` – blok importów + słownik ``_AKCENT_FUNCS`` między
  własnymi markerami.

Historia: do refaktoru 13.0/Etap 5 drugi cel generatora był w ``gui_rezyser.py``
(silnik fonetyczny żył tam jako metoda klasy). Po wydzieleniu silnika do
``core_rezyser.zastosuj_akcenty_uniwersalne`` (funkcja wolnostojąca) markery
wędrują do ``core_rezyser.py`` – z inną głębokością wcięcia dispatchera
(4 spacje zamiast 8).

Dzięki temu lingwista dodaje YAML, klika jeden przycisk – reszta jest
automatyczna. Tryb Poligloty NIE wymaga tego kroku (odczytuje YAML-e
dynamicznie przez ``core_poliglota.lista_wariantow(...)``), ale tryb
Reżysera aplikuje akcenty punktowo po nazwie i potrzebuje tych wrapperów.


Bezpieczeństwo:
  * Skrypt jest IDEMPOTENTNY – ponowne wywołanie bez zmian YAML drukuje
    „bez zmian" i nie dotyka plików.
  * Modyfikuje WYŁĄCZNIE obszary między markerami.
  * Wymaga ``pyyaml`` (z requirements.txt).
"""

from __future__ import annotations

import os
import re
import sys
from typing import Callable, Iterable

import yaml

# Windows: wymuś UTF-8 na stdout/stderr, bo domyślnie cp1250 wybucha
# na znakach typu "ę", "ł", a w runtime/ na czystej cp852 wawet
# na myślniku "–". reconfigure() pojawiło się w Pythonie 3.7.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


# Typ publicznego callbacka używanego do raportowania postępu.
LogCallback = Callable[[str], None]


# =============================================================================
# Konfiguracja: ścieżki, markery, obsługiwane języki
# =============================================================================
ROOT = os.path.dirname(os.path.abspath(__file__))

# 13.3: dynamiczny skan zamiast hardkodowanej krotki. Generator skanuje
# wszystkie foldery ``dictionaries/<kod>/akcenty/`` i zbiera unię id-ów
# akcentów. Dzięki temu dodanie ``dictionaries/en/akcenty/`` (albo dowolnego
# kolejnego języka) nie wymaga edycji kodu Pythona — spójnie z duchem
# projektu „nowy język = nowy folder".
DICTIONARIES_DIR = os.path.join(ROOT, "dictionaries")


def odkryj_obslugiwane_jezyki() -> tuple[str, ...]:
    """Skanuje ``dictionaries/`` i zwraca kody języków z folderem ``akcenty/``.

    Zwracamy tylko te języki, które mają NIEPUSTE ``akcenty/`` (przynajmniej
    jeden plik ``.yaml``/``.yml``). Foldery bez akcentów pomijamy — dodanie
    pustego stuba językowego nie ma być warunkiem regeneracji.

    Wynik posortowany alfabetycznie po kodzie języka, dla deterministycznego
    porządku w generowanych blokach.
    """
    if not os.path.isdir(DICTIONARIES_DIR):
        return ()
    znalezione: list[str] = []
    for kod in sorted(os.listdir(DICTIONARIES_DIR)):
        kat_akcenty = os.path.join(DICTIONARIES_DIR, kod, "akcenty")
        if not os.path.isdir(kat_akcenty):
            continue
        if any(p.lower().endswith((".yaml", ".yml"))
               for p in os.listdir(kat_akcenty)):
            znalezione.append(kod)
    return tuple(znalezione)

CORE_POLIGLOTA_PATH = os.path.join(ROOT, "core_poliglota.py")
CORE_REZYSER_PATH   = os.path.join(ROOT, "core_rezyser.py")

# Markery w core_poliglota.py (aliasy akcent_*)
CORE_POLI_MARK_START = "# <GENEROWANE_AKCENTY_REZYSERA_START>"
CORE_POLI_MARK_END   = "# <GENEROWANE_AKCENTY_REZYSERA_END>"

# Markery w core_rezyser.py – blok importu (na poziomie modułu, bez wcięcia)
REZ_IMP_START = "# <GENEROWANE_IMPORTY_AKCENTOW_START>"
REZ_IMP_END   = "# <GENEROWANE_IMPORTY_AKCENTOW_END>"

# Markery w core_rezyser.py – słownik dispatchera.
# W ``core_rezyser.zastosuj_akcenty_uniwersalne`` (funkcja wolnostojąca, nie
# metoda klasy) ciało ma wcięcie 4 spacji – dlatego dispatcher dostaje również
# 4 spacje (wcześniej, gdy silnik był metodą w ``gui_rezyser``, było to 8).
REZ_DISP_START = "# <GENEROWANY_SLOWNIK_AKCENTOW_START>"
REZ_DISP_END   = "# <GENEROWANY_SLOWNIK_AKCENTOW_END>"



# =============================================================================
# Skanowanie YAML-i
# =============================================================================

def _wczytaj_yaml(sciezka: str, log: LogCallback = print) -> dict:
    """Bezpiecznie wczytuje plik YAML (zwraca pusty dict przy błędzie)."""
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:  # noqa: BLE001
        log(f"  [OSTRZEŻENIE] nie udało się wczytać {sciezka}: {exc}")
        return {}
    return data if isinstance(data, dict) else {}


def zbierz_akcenty(jezyk: str, log: LogCallback = print) -> list[dict]:
    """Zwraca posortowaną listę akcentów (kategoria=='akcent') dla danego języka.

    Pomija oczyszczenia (``kategoria: oczyszczenie``) i naprawiacz tagów
    (``kategoria: naprawiacz``) – nie są one prawdziwymi akcentami fonetycznymi
    i nie potrzebują wrapperów w trybie Reżysera.

    Args:
        jezyk: Kod ISO 639-1 języka bazowego (np. ``"pl"``).

    Returns:
        Lista słowników ``{id, etykieta, iso, kolejnosc, plik}`` posortowanych
        po polu ``kolejnosc`` (rosnąco), a w ramach równej wartości – po
        nazwie pliku (alfabetycznie, deterministycznie).
    """
    katalog = os.path.join(ROOT, "dictionaries", jezyk, "akcenty")
    if not os.path.isdir(katalog):
        return []

    wyniki: list[dict] = []
    for nazwa_pliku in sorted(os.listdir(katalog)):
        if not nazwa_pliku.lower().endswith((".yaml", ".yml")):
            continue
        cfg = _wczytaj_yaml(os.path.join(katalog, nazwa_pliku), log)
        if cfg.get("kategoria") != "akcent":
            continue
        id_         = cfg.get("id")        or os.path.splitext(nazwa_pliku)[0]
        etykieta    = cfg.get("etykieta",   id_)
        iso_code    = cfg.get("iso",        "")
        kolejnosc   = int(cfg.get("kolejnosc", 999))
        wyniki.append({
            "id":        id_,
            "etykieta":  etykieta,
            "iso":       iso_code,
            "kolejnosc": kolejnosc,
            "plik":      nazwa_pliku,
        })

    wyniki.sort(key=lambda a: (a["kolejnosc"], a["plik"]))
    return wyniki


# =============================================================================
# Generatory bloków kodu
# =============================================================================

def _generuj_aliasy_core(akcenty: list[dict]) -> str:
    """Zwraca treść między markerami w ``core_poliglota.py``.

    13.3: wrapper przyjmuje opcjonalny argument ``jezyk`` (default ``"pl"``
    dla backward-compat). Reguły fonetyczne tego samego id mogą żyć
    w wielu folderach (np. ``pl/akcenty/islandzki.yaml`` to akcent islandzki
    *po polsku*, ``en/akcenty/islandzki.yaml`` — *po angielsku*) — wrapper
    deleguje wybór do silnika ``zastosuj_reguly_fonetyczne``.
    """
    bloki: list[str] = [
        "# UWAGA: Blok poniżej jest generowany automatycznie przez skrypt",
        "# ``odswiez_rezysera.py``. NIE edytuj go ręcznie — edycje zostaną",
        "# nadpisane przy najbliższym uruchomieniu skryptu (po dodaniu",
        "# nowego pliku YAML w dictionaries/<język>/akcenty/).",
        "",
        "",
    ]
    for idx, akc in enumerate(akcenty):
        id_ = akc["id"]
        jezyki = akc.get("jezyki", ["pl"])
        zrodla = ", ".join(
            f"``dictionaries/{j}/akcenty/{akc['plik']}``" for j in jezyki
        )
        bloki.append(f'def akcent_{id_}(tekst: str, jezyk: str = "pl") -> str:')
        bloki.append(
            f'    """Alias: reguły fonetyczne akcentu ``{id_}`` '
            f'(źródła: {zrodla})."""'
        )
        bloki.append(
            f'    return zastosuj_reguly_fonetyczne(tekst, "{id_}", jezyk)'
        )
        if idx < len(akcenty) - 1:
            bloki.append("")   # pusta linia między funkcjami
            bloki.append("")
    bloki.append("")   # końcowy newline przed markerem END
    return "\n".join(bloki) + "\n"


def _generuj_imports_rezyser(akcenty: list[dict]) -> str:
    """Zwraca treść między markerami imports w ``core_rezyser.py``.

    Zachowuje oryginalną kolejność akcentów (z ``kolejnosc``), co ma znaczenie
    jedynie kosmetyczne – Python akceptuje dowolny porządek wewnątrz krotki.
    Importy są na poziomie modułu, więc nie mają wcięcia.
    """
    if not akcenty:
        return "# (brak akcentów – żaden folder dictionaries/*/akcenty/ nie zawiera reguł)\n"
    linie = ["from core_poliglota import ("]
    for akc in akcenty:
        linie.append(f"    akcent_{akc['id']},")
    linie.append(")")
    return "\n".join(linie) + "\n"


def _generuj_dispatcher_rezyser(akcenty: list[dict]) -> str:
    """Zwraca treść między markerami dispatchera w ``core_rezyser.py``.

    Blok ma wcięcie **4 spacji** – dispatcher jest lokalną zmienną w ciele
    funkcji wolnostojącej ``zastosuj_akcenty_uniwersalne``. Wyrównujemy klucze
    kolonami dla czytelności – identycznie jak w dawnej wersji dla
    ``gui_rezyser.py`` (tam było 8 spacji, bo był to kod w metodzie klasy).
    """
    if not akcenty:
        return "    _AKCENT_FUNCS: dict[str, object] = {}   # brak akcentów\n"

    szerokosc = max(len(akc["id"]) for akc in akcenty)
    linie = ["    _AKCENT_FUNCS = {"]
    for akc in akcenty:
        klucz  = f'"{akc["id"]}":'
        spacje = " " * (szerokosc + 3 - len(klucz))   # 3 = cudzysłowy + dwukropek
        linie.append(f'        {klucz}{spacje}akcent_{akc["id"]},')
    linie.append("    }")
    return "\n".join(linie) + "\n"



# =============================================================================
# Podmiana tekstu między markerami (idempotentna)
# =============================================================================

def _podmien_blok(tresc: str, start: str, end: str, nowa_zawartosc: str) -> str:
    """Zwraca ``tresc`` z zawartością między markerami zastąpioną.

    Jeśli markery nie zostaną znalezione – rzuca ``RuntimeError`` z czytelnym
    komunikatem. Podmienia TYLKO pierwsze wystąpienie pary marker-start/end.
    """
    if start not in tresc or end not in tresc:
        raise RuntimeError(
            f"Nie znaleziono markerów w pliku.\n"
            f"  start: {start}\n  end:   {end}\n"
            f"Czy plik nie został ręcznie nadpisany bez zachowania markerów?"
        )

    wzor = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    return wzor.sub(start + "\n" + nowa_zawartosc + end, tresc, count=1)


def _zaktualizuj_plik(
    sciezka: str,
    podmiany: Iterable[tuple[str, str, str]],
    log: LogCallback = print,
) -> bool:
    """Aplikuje listę ``(start, end, content)`` do pliku. Zwraca True gdy zmieniono."""
    with open(sciezka, "r", encoding="utf-8") as fh:
        oryginal = fh.read()

    tresc = oryginal
    for start, end, content in podmiany:
        tresc = _podmien_blok(tresc, start, end, content)

    if tresc == oryginal:
        log(f"  [{os.path.basename(sciezka)}] bez zmian")
        return False

    with open(sciezka, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(tresc)
    log(f"  [{os.path.basename(sciezka)}] zaktualizowano [OK]")
    return True


# =============================================================================
# Publiczne API: uruchom()
# =============================================================================

def uruchom(on_log: LogCallback = print) -> dict:
    """Publiczne API generatora – używane z CLI i z GUI (HomePanel).

    Skanuje foldery ``dictionaries/<jezyk>/akcenty/`` i regeneruje bloki
    wrapperów między markerami w ``core_poliglota.py`` i ``core_rezyser.py``.

    Args:
        on_log: Callback wywoływany na każdej linii raportu. Domyślnie
                ``print`` (wygodne dla CLI). GUI podstawia własną listę.

    Returns:
        Słownik-raport z kluczami:
            ``akcenty``         – lista ``id`` wykrytych akcentów,
            ``core_changed``    – czy zmieniono ``core_poliglota.py``,
            ``rezyser_changed`` – czy zmieniono ``core_rezyser.py``,
            ``errors``          – lista błędów (pusta lista = sukces).
    """
    raport = {
        "akcenty":         [],
        "core_changed":    False,
        "rezyser_changed": False,
        "errors":          [],
    }

    on_log("=" * 60)
    on_log("Odświeżacz Reżysera – generator akcent_* z plików YAML")
    on_log("=" * 60)

    # 13.3: zamiast hardkodowanej krotki — dynamiczny skan ``dictionaries/``.
    obslugiwane = odkryj_obslugiwane_jezyki()
    on_log(f"\nWykryte folder(y) z akcentami: {', '.join(obslugiwane) or '(brak)'}")

    # Agregacja: dla każdego ``id`` pamiętamy listę języków, w których plik
    # istnieje. Dzięki temu wrapper ``akcent_<id>(tekst, jezyk)`` w docstringu
    # pokazuje pełną listę dostępnych folderów (a nie tylko jeden).
    zlepione: dict[str, dict] = {}
    for jezyk in obslugiwane:
        akcenty = zbierz_akcenty(jezyk, on_log)
        on_log(f"\nJezyk '{jezyk}': wykryto {len(akcenty)} akcentow")
        for akc in akcenty:
            on_log(
                f"  - {akc['id']:<25} (iso={akc['iso'] or '?':<4})"
                f" [{akc['plik']}]"
            )
            akc_id = akc["id"]
            if akc_id not in zlepione:
                zlepione[akc_id] = {**akc, "jezyki": [jezyk]}
            else:
                zlepione[akc_id]["jezyki"].append(jezyk)

    if not zlepione:
        msg = ("Nie wykryto zadnego akcentu (kategoria: akcent). "
               "Sprawdz katalog dictionaries/*/akcenty/.")
        on_log("\n[BLAD] " + msg)
        raport["errors"].append(msg)
        return raport

    # Deterministyczny porządek: kolejność z YAML-a, fallback po pliku.
    unikalne: list[dict] = sorted(
        zlepione.values(), key=lambda a: (a["kolejnosc"], a["plik"])
    )

    raport["akcenty"] = [akc["id"] for akc in unikalne]
    on_log(f"\nGenerowanie wrapperów dla {len(unikalne)} unikalnych akcentów…")

    on_log("\n1) Aktualizacja core_poliglota.py")
    try:
        raport["core_changed"] = _zaktualizuj_plik(
            CORE_POLIGLOTA_PATH,
            [(
                CORE_POLI_MARK_START,
                CORE_POLI_MARK_END,
                _generuj_aliasy_core(unikalne),
            )],
            on_log,
        )
    except RuntimeError as exc:
        on_log(f"  [BLAD] {exc}")
        raport["errors"].append(f"core_poliglota.py: {exc}")
        return raport

    on_log("\n2) Aktualizacja core_rezyser.py")
    try:
        raport["rezyser_changed"] = _zaktualizuj_plik(
            CORE_REZYSER_PATH,
            [
                (REZ_IMP_START,  REZ_IMP_END,
                 _generuj_imports_rezyser(unikalne)),
                (REZ_DISP_START, REZ_DISP_END,
                 _generuj_dispatcher_rezyser(unikalne)),
            ],
            on_log,
        )
    except RuntimeError as exc:
        on_log(f"  [BLAD] {exc}")
        raport["errors"].append(f"core_rezyser.py: {exc}")
        return raport

    on_log("\n" + "=" * 60)
    on_log("Gotowe. Uruchom aplikacje ponownie, by zobaczyc nowe akcenty.")
    on_log("=" * 60)
    return raport



def main() -> int:
    """Wejście CLI. Zwraca kod exit (0 = sukces, >0 = błąd)."""
    raport = uruchom()
    return 1 if raport["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
