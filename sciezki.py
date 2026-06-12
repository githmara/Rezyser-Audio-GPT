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
