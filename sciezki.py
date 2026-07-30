"""sciezki.py — centralne rozwiązywanie katalogu bazowego aplikacji.

Pojedyncze źródło prawdy dla pytania „gdzie leżą zasoby i dane?" — niezależnie
od tego, czy aplikacja chodzi ze źródła (``python main.py``), czy jako paczka
PyInstaller (onedir, ``--windowed``).

Tło migracji na PyInstaller (od v17.0): wcześniej deployment opierał się o
przenośny ``runtime/python.exe`` + ``run.bat`` i wszystkie moduły liczyły ścieżki
względem ``Path(__file__).parent`` (katalog z plikami ``.py``). Po zamrożeniu
PyInstallerem ``__file__`` wskazuje WEWNĄTRZ bundla (folder z biblioteką, u nas
nazwany ``runtime/`` przez ``--contents-directory``), a NIE obok pliku
wykonywalnego. Zasoby end-userowe (``dictionaries/``, ``docs/``,
``golden_key.env``) oraz ukryta metadata (``runtime/skrypty/*.mode`` itd.) leżą
obok ``.exe``. Dlatego baza musi przeskoczyć na katalog pliku wykonywalnego, gdy
``sys.frozen`` jest ustawione.

Reguła:
  * **frozen** (PyInstaller): baza = katalog ``sys.executable`` (tam, gdzie leży
    ``Rezyser Audio GPT.exe``; obok niego ``dictionaries/``, ``docs/`` i folder
    bundla ``runtime/`` z interpreterem oraz metadanymi projektów).
  * **źródło**: baza = katalog tego pliku (root repo, gdzie leżą wszystkie
    moduły ``.py`` i ``dictionaries/``).

Współdzielony ``runtime/`` (metadata) NIE koliduje z folderem bundla: przy
zamrożeniu ``--contents-directory runtime`` sprawia, że biblioteki PyInstallera
i metadane projektów żyją w tym samym, „onieśmielającym" katalogu ``runtime/``
obok exe — dokładnie tam, gdzie wcześniej (obok interpretera), więc ciekawski
użytkownik nadal traktuje go jak folder systemowy.

NARZĘDZIA DEWELOPERSKIE (``build_release.py``, ``generuj_dokumentacje.py``,
``buduj_wielojezyczne_*.py``, ``tlumacz_ai.py``) celowo NIE importują tego
modułu — uruchamiają się wyłącznie ze źródła, nigdy w paczce frozen, więc
``Path(__file__).parent`` jest tam zawsze poprawne i prostsze.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


def _wyznacz_baze() -> Path:
    """Zwraca katalog bazowy zależnie od trybu uruchomienia (frozen vs źródło)."""
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: exe leży w katalogu instalacji; zasoby (dictionaries,
        # docs, golden_key.env) oraz folder bundla `runtime/` są obok niego.
        return Path(sys.executable).resolve().parent
    # Uruchomienie ze źródła: katalog z plikami .py (root repozytorium).
    return Path(__file__).resolve().parent


# Wyznaczane raz przy imporcie — ani `sys.frozen`, ani `sys.executable` nie
# zmieniają się w trakcie życia procesu, więc cache na poziomie modułu jest
# bezpieczny i tani.
KATALOG_BAZOWY: Path = _wyznacz_baze()

# Wariant string dla kodu operującego na `os.path.join(...)` zamiast `pathlib`.
KATALOG_BAZOWY_STR: str = str(KATALOG_BAZOWY)

# Czy aplikacja działa jako zamrożona paczka (PyInstaller), czy ze źródła.
# Wyznaczane raz przy imporcie (jak wyżej — `sys.frozen` jest niezmienne).
# Używane m.in. do różnicowania komunikatów dev vs end-user (np. bramka
# komend technicznych w trybie Opowieści — patrz gui_opowiesci).
JEST_FROZEN: bool = getattr(sys, "frozen", False)


def _wyznacz_zasoby() -> Path:
    """Zwraca katalog z zasobami SPAKOWANYMI do bundla (nie edytowalnymi przez usera).

    W odróżnieniu od `KATALOG_BAZOWY` (= dir(exe) gdy frozen — tam żyją EDYTOWALNE
    seed-data `dictionaries/`/`docs/` i user-data obok exe), ten katalog wskazuje
    WNĘTRZE bundla PyInstallera (`sys._MEIPASS`, u nas folder `runtime/` przez
    `--contents-directory`). Tu trafiają pliki dołączone przez `datas` w
    `rezyser_audio.spec` — np. `VERSION`, który jest pojedynczym źródłem prawdy
    numeru wersji i NIE jest danymi użytkownika (nie powinien leżeć luzem obok exe,
    gdzie kusi do edycji i — bez rozszerzenia — odpala systemowy file-picker).

    frozen: `sys._MEIPASS` (= `<install>/runtime/`, gdzie COLLECT składa datas).
    źródło: root repo (== `KATALOG_BAZOWY`) — `_MEIPASS` nie istnieje, VERSION
            leży w roocie obok plików `.py`.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


# Katalog zasobów spakowanych do bundla (VERSION itd.). Patrz docstring wyżej.
KATALOG_ZASOBOW: Path = _wyznacz_zasoby()


# ---------------------------------------------------------------------------
# Otwieranie plików/folderów domyślną aplikacją systemową (cross-platform)
# ---------------------------------------------------------------------------
def otworz_w_systemie(sciezka) -> None:
    """Otwiera plik lub folder domyślną aplikacją systemową (cross-platform).

    HTML (``.html``/``.htm``) → domyślna PRZEGLĄDARKA przez ``webbrowser``
    (wszystkie systemy); Windows → folder otwiera ``os.startfile``
    (Eksplorator), a pozostałe PLIKI trafiają bezwarunkowo do Notatnika
    (``notepad.exe``); macOS → ``open``; pozostałe (Linux/BSD + Orca itd.)
    → ``xdg-open``.

    **Dlaczego HTML osobną gałęzią (od v18.8):** dokumentacja z menu Pomoc to
    ``docs/<rdzen>.<iso>.html`` — reguła „plik = Notatnik" (niżej) rzucałaby
    userowi w twarz kodem źródłowym zamiast wyrenderowanego dokumentu
    (złapane na realnym UI przed wydaniem 18.8.0). ``webbrowser.open`` na
    ``file://`` URI gwarantuje przeglądarkę niezależnie od skojarzeń systemowych.

    **Dlaczego Notatnik, a nie ``os.startfile`` na pliku (od v18.4):** pliki, które
    ta aplikacja otwiera najczęściej (``golden_key.env``, ``*.yaml`` Managera Reguł),
    poza środowiskiem programistycznym NIE mają skojarzenia rozszerzenia — wtedy
    ``os.startfile`` pokazuje systemowy picker „Jak chcesz otworzyć ten plik?"
    zamiast edytora (zgłoszone na ``.env``). Notatnik jest zawsze obecny, dostępny
    dla NVDA i radzi sobie z każdym plikiem tekstowym (env/yaml/md/txt) — a innych
    niż tekst, HTML i foldery przez ten helper nie otwieramy. Folder MUSI iść przez
    ``os.startfile`` (Notatnik nie otworzy katalogu — np. ``dictionaries/``).

    POJEDYNCZE źródło prawdy dla „otwórz w systemie" — wcześniej ten 3-gałęziowy
    wzorzec `platform.system()` był skopiowany w `main.py` (×3), `gui_opowiesci`,
    `gui_manager_regul` i `gui_rezyser`, a w jednym miejscu (otwarcie docs)
    BŁĘDNIE zahardkodowany na samo ``os.startfile`` — co wywalało się na nie-
    Windowsowym devie (`setup_dev.sh`/`run.sh`). Zamrożony release jest Windows,
    ale ŹRÓDŁO chodzi też na Linux/macOS, więc helper musi być cross-platform.

    Rzuca wyjątek (OSError / AttributeError / FileNotFoundError) przy błędzie —
    wołający łapie go i pokazuje komunikat dostępny dla NVDA. Nie blokuje:
    ``subprocess.Popen`` wraca natychmiast, ``os.startfile`` jest również async.
    """
    cel = str(sciezka)

    # HTML → zawsze domyślna przeglądarka (as_uri obsługuje spacje/diakrytykę
    # w ścieżce; wymaga ścieżki absolutnej, stąd resolve()).
    if os.path.isfile(cel) and cel.lower().endswith((".html", ".htm")):
        import webbrowser
        from pathlib import Path
        webbrowser.open(Path(cel).resolve().as_uri())
        return

    system = platform.system()
    if system == "Windows":
        if os.path.isdir(cel):
            os.startfile(cel)                   # noqa: S606 — Eksplorator dla folderu
        else:
            subprocess.Popen(["notepad.exe", cel])  # noqa: S603,S607 — pewny edytor tekstu
    elif system == "Darwin":
        subprocess.Popen(["open", cel])         # noqa: S603,S607
    else:
        subprocess.Popen(["xdg-open", cel])     # noqa: S603,S607
