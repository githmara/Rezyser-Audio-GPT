"""bot_i18n.py — most do warstwy i18n + dynamiczne wykrywanie języków dla botów.

Boty (`issue_closure_north.py`, `send_patch.py`, `issue_intake_sami.py`) oraz
lokalny `odpowiedz_lokalnie.py` renderują teksty person z
`dictionaries/<kod>/gui/ui.yaml` (sekcja ``bot:``) zamiast hardkodowanych
dictów `dict[Language, ...]`. Dzięki temu dodanie 10. języka NIE wymaga już
edycji Pythona — wystarczy paczka `dictionaries/<kod>/` + autotłumacz
`buduj_wielojezyczne_ui.py`, który tłumaczy sekcję ``bot:`` razem z resztą UI.

Most jest możliwy, bo `i18n.py` + `sciezki.py` NIE zależą od wxPython (ciągną
tylko `PyYAML` + stdlib), więc `import i18n` jest bezpieczny zarówno w runnerze
GitHub Actions (pełny checkout repo), jak i na lokalnej maszynie maintainera.
`sciezki.KATALOG_BAZOWY` liczy się względem `sciezki.__file__` (root repo, bo
moduł leży w roocie), więc `dictionaries/` jest znajdowane identycznie w obu
kontekstach — bez `sys.frozen` boty nigdy nie chodzą zamrożone.

DYNAMICZNE WYKRYWANIE JĘZYKÓW (krytyczne — żeby nowy język NIE wymagał Pythona):
lista języków detektora lingua ORAZ mapa `Language ↔ ISO` są budowane na żywo ze
`dictionaries/<kod>/podstawy.yaml` — nazwa folderu = kod ISO, pole `lingua:` =
nazwa enuma `lingua.Language` (np. ``POLISH``). To ten sam mechanizm, który
silnik ma w `core_poliglota._zbuduj_mapowanie_lingua`, odtworzony tu LEKKO:
`core_poliglota` importuje globalnie `docx`/`num2words`, których runner Actions
nie instaluje, więc nie można go zaimportować w bocie — kopiujemy więc samą
logikę (zależną tylko od `yaml` + `lingua`). Skutek: dodanie 10. języka =
nowy folder `dictionaries/<kod>/` (podstawy.yaml z polem `lingua` + ui.yaml z
kluczami `bot.*`); ZERO zahardkodowanej mapy/listy języków w botach.

Workflowy MUSZĄ instalować `pyyaml` (patrz `.github/workflows/*.yml`), bo i18n
parsuje YAML — to jedyna nowa zależność obiegu botów.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from lingua import Language, LanguageDetectorBuilder

# Root repo = dwa poziomy w górę od `.github/scripts/bot_i18n.py`.
# (`scripts` → `.github` → root). Wstrzykujemy go do sys.path, żeby `import i18n`
# znalazł moduł z roota niezależnie od katalogu, z którego workflow odpala skrypt.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import i18n  # noqa: E402  (po manipulacji sys.path)

# Katalog słowników — single source z i18n (liczony przez sciezki.KATALOG_BAZOWY).
_DICT_DIR: Path = i18n._DICTIONARIES_DIR


# ---------------------------------------------------------------------------
# Dynamiczne mapowanie ISO ↔ lingua.Language ze `dictionaries/<kod>/podstawy.yaml`
# ---------------------------------------------------------------------------
# Lekka kopia `core_poliglota._zbuduj_mapowanie_lingua` (tam nie do zaimportowania
# w runnerze — ciągnie docx/num2words). Pole `lingua:` jest OBOWIĄZKOWE w każdym
# podstawy.yaml języka bazowego, więc to wystarczające i jedyne źródło prawdy.
def _jezyki_z_podstawami() -> list[str]:
    """Kody ISO folderów `dictionaries/<kod>/` mających `podstawy.yaml`."""
    if not _DICT_DIR.is_dir():
        return []
    return sorted(
        p.name for p in _DICT_DIR.iterdir()
        if p.is_dir() and (p / "podstawy.yaml").is_file()
    )


def _pole_lingua(kod: str) -> str | None:
    """Wartość pola `lingua:` z `<kod>/podstawy.yaml` (UPPER) lub None."""
    sciezka = _DICT_DIR / kod / "podstawy.yaml"
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            dane = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(dane, dict):
        return None
    wartosc = dane.get("lingua")
    if isinstance(wartosc, str) and wartosc.strip():
        return wartosc.strip().upper()
    return None


_MAPA_ISO_LINGUA: dict[str, Language] | None = None


def mapa_iso_na_lingua() -> dict[str, Language]:
    """Mapa ISO → ``Language`` zbudowana ze słowników (cache).

    Pomija języki bez pola `lingua` albo z nazwą nieznaną aktualnej wersji
    `lingua-language-detector` (`getattr` zamiast `Language[...]`, by literówka
    nie wywaliła całego bota). Wzorzec 1:1 z `core_poliglota`.
    """
    global _MAPA_ISO_LINGUA
    if _MAPA_ISO_LINGUA is not None:
        return _MAPA_ISO_LINGUA
    mapa: dict[str, Language] = {}
    for kod in _jezyki_z_podstawami():
        nazwa = _pole_lingua(kod)
        if not nazwa:
            continue
        kandydat = getattr(Language, nazwa, None)
        if kandydat is None:
            sys.stderr.write(
                f"[bot_i18n] lingua: '{nazwa}' w dictionaries/{kod}/podstawy.yaml "
                f"nie jest znaną nazwą lingua.Language — pomijam w detektorze.\n"
            )
            continue
        mapa[kod] = kandydat
    _MAPA_ISO_LINGUA = mapa
    return mapa


def mapa_lingua_na_iso() -> dict[str, str]:
    """Odwrócone mapowanie ``Language.name`` → ISO (na bazie tej samej mapy)."""
    return {lang.name: iso for iso, lang in mapa_iso_na_lingua().items()}


_DETEKTOR: Any = None
_DETEKTOR_FAILED = False


def zbuduj_detektor() -> Any:
    """Lazy singleton ``LanguageDetector`` z języków obecnych w `dictionaries/`.

    Zwraca None, gdy w słownikach jest < 2 języków z poprawnym polem `lingua`
    (lingua wymaga ≥ 2). Wołający spada wtedy na fallback (EN).
    """
    global _DETEKTOR, _DETEKTOR_FAILED
    if _DETEKTOR is not None:
        return _DETEKTOR
    if _DETEKTOR_FAILED:
        return None
    mapa = mapa_iso_na_lingua()
    if len(mapa) < 2:
        _DETEKTOR_FAILED = True
        return None
    _DETEKTOR = LanguageDetectorBuilder.from_languages(*mapa.values()).build()
    return _DETEKTOR


def wykryj(tekst: str | None) -> Language | None:
    """Wykrywa język lingua tekstu; None gdy pusto / detektor < 2 jzk / niepewność.

    Centralny detektor obiegu botów — zastępuje zahardkodowane `LANGUAGES = [...]`
    w każdym bocie. Pusty/biały tekst → None (wołający użyje fallbacku EN).
    """
    if not tekst or not tekst.strip():
        return None
    det = zbuduj_detektor()
    if det is None:
        return None
    return det.detect_language_of(tekst)


def kod_iso(jezyk: Language | None) -> str:
    """Mapuje enum lingua na kod ISO katalogu (dynamicznie); fallback na EN."""
    if jezyk is None:
        return i18n.JEZYK_FALLBACK
    return mapa_lingua_na_iso().get(jezyk.name, i18n.JEZYK_FALLBACK)


def t_bot(klucz: str, jezyk: Language | None, **kwargs: object) -> str:
    """Renderuje klucz ``bot.*`` w języku zgłoszenia.

    Cienki wrapper na `i18n.t` z `jezyk_override` wyliczonym z enuma lingua.
    Dziedziczy z `i18n.t` całą semantykę: fallback na EN przy braku klucza w
    języku bazowym, `str.format(**kwargs)` z połykaniem brakujących/nadmiarowych
    placeholderów (nie wywala się na `{link}` vs `{maintainer_answer}`),
    auto-wstrzyknięcie `numer_wersji`. Brak klucza wszędzie → `[klucz]`
    (widoczny sygnał „dopisz do ui.yaml", nie cichy pusty string).
    """
    return i18n.t(klucz, jezyk_override=kod_iso(jezyk), **kwargs)
