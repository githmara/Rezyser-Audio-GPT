#!/usr/bin/env python
"""cykl_wersji.py — czy bieżąca praca ma zadeklarowany cykl wydania.

Bliźniak `.github/scripts/cykl_wersji.py` w accessible_text_analyst (ta sama
tabela stanów, inna granica „zmiany wydawniczej”). Tylko stdlib: woła go hak
startu sesji maintainera systemowym Pythonem, bez venv projektu.

DLACZEGO (decyzja maintainera 2026-11-14). Wstrzymania zależności wygasają
z następnym minorem, liczonym względem `VERSION`. Gdy `VERSION` zmieniał się
dopiero w commicie wydania (19.11–19.18: zawsze), przez cały cykl stał na
ostatnim WYDANYM numerze — wstrzymania z tego minora świeciły na zielono, a
bramka nie wiedziała, czy powstaje patch, minor czy major. Czerwień
przychodziła dopiero w buildzie zamykającym cykl, czyli tam, gdzie kanon
środowiska („środowisko najpierw”) jest już spóźniony. Cykl otwiera się więc
JAWNIE: pierwszy commit cyklu ustawia `VERSION` na `X.Y.0-WIP` (minor albo
major — stare wstrzymania od razu wygasają) albo `X.Y.Z-WIP` (patch — tylko
ostrzegają). Commit wydania zdejmuje `-WIP`.

STANY:
  wip          `VERSION` ma `-WIP`, a tagu tej wersji jeszcze nie ma — dobrze;
  wydany       `VERSION` = istniejący tag, a od tagu nie zmieniło się nic poza
               dev-tooling — spoczynek po wydaniu (skrócona procedura dozwolona);
  zamykanie    `VERSION` bez `-WIP` i bez tagu — commit wydania w przygotowaniu;
  nieotwarty   `VERSION` = istniejący tag, a od tagu zmieniła się treść
               wydania (granica = `sync_dev_release.klasyfikuj_zmiany`) —
               BŁĄD: zadeklaruj cykl;
  wip_wydanej  `VERSION` = `X.Y.Z-WIP`, a tag `vX.Y.Z` już istnieje — BŁĄD;
  nieznany     brak `VERSION`, gita albo tagów — nie da się orzec.

Zmiany liczone są względem DRZEWA ROBOCZEGO (`git diff <tag>`), nie HEAD:
hak startu ma ostrzec, zanim pierwszy niezadeklarowany commit powstanie.

Uruchom:  python .github/scripts/cykl_wersji.py [--json]   (z roota repo)
Kod wyjścia: 1 dla `nieotwarty` / `wip_wydanej`, inaczej 0.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PLIK_WERSJI = "VERSION"
_WERSJA = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?(-WIP)?$")
STANY_BLEDU = ("nieotwarty", "wip_wydanej")


def _git(*argumenty: str) -> tuple[int, str]:
    try:
        wynik = subprocess.run(["git", *argumenty], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return wynik.returncode, wynik.stdout.strip()


def czytaj_wersje(korzen: Path = Path(".")) -> tuple[tuple[int, int, int], bool] | None:
    """((major, minor, patch), czy_wip) z `VERSION`; brak patcha = 0."""
    try:
        tekst = (korzen / PLIK_WERSJI).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    m = _WERSJA.match(tekst)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)), bool(m.group(4))


def _tag_istnieje(tag: str) -> bool:
    kod, _ = _git("rev-parse", "-q", "--verify", f"refs/tags/{tag}")
    return kod == 0


def _nazwa_tagu(wersja: tuple[int, int, int]) -> str | None:
    """Tag wersji: `vX.Y.Z`, a dla patcha 0 także historyczne `vX.Y`."""
    pelny = "v{}.{}.{}".format(*wersja)
    if _tag_istnieje(pelny):
        return pelny
    if wersja[2] == 0:
        krotki = "v{}.{}".format(*wersja[:2])
        if _tag_istnieje(krotki):
            return krotki
    return None


def winowajcy(tag: str) -> list[str]:
    """Zmiany treści wydania od ``tag`` do drzewa roboczego (granica Reżysera:
    wszystko, co wyklucza skróconą procedurę dev-tools-only)."""
    kod, surowe = _git("diff", "--name-only", tag)
    if kod != 0:
        raise RuntimeError(f"git diff {tag} nie powiódł się")
    # Nowy, jeszcze nieśledzony moduł też otwiera cykl (audyt 19.19:
    # `git diff` go nie widzi, więc hook przed pierwszym commitem milczał).
    kod, nowe = _git("ls-files", "--others", "--exclude-standard")
    if kod == 0:
        surowe += "\n" + nowe
    zmienione = [w for w in surowe.splitlines() if w.strip()]
    if not zmienione:
        return []
    import sync_dev_release as sdr
    # sync_dev_release loguje każdą komendę na stdout — tu to szum.
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            return sdr.klasyfikuj_zmiany(zmienione, tag)
        except SystemExit as exc:
            raise RuntimeError(str(exc)) from exc


def stan_cyklu(korzen: Path = Path(".")) -> dict:
    wersja = czytaj_wersje(korzen)
    if wersja is None:
        return {"stan": "nieznany", "powod": "VERSION missing or not X.Y[.Z][-WIP]"}
    numer, wip = wersja
    tekst = "{}.{}.{}".format(*numer) + ("-WIP" if wip else "")
    kod, _ = _git("rev-parse", "--git-dir")
    if kod != 0:
        return {"stan": "nieznany", "wersja": tekst, "powod": "not a git repository"}
    tag = _nazwa_tagu(numer)
    if wip:
        stan = "wip_wydanej" if tag else "wip"
        return {"stan": stan, "wersja": tekst, "tag": tag,
                "typ": "patch" if numer[2] else "minor/major"}
    if tag is None:
        kod, tagi = _git("tag", "--list", "v*")
        if kod != 0 or not tagi:
            return {"stan": "nieznany", "wersja": tekst,
                    "powod": "no v* tags in this clone (fetch tags?)"}
        return {"stan": "zamykanie", "wersja": tekst}
    try:
        lista = winowajcy(tag)
    except RuntimeError as exc:
        return {"stan": "nieznany", "wersja": tekst, "tag": tag, "powod": str(exc)}
    return {"stan": "nieotwarty" if lista else "wydany", "wersja": tekst,
            "tag": tag, "winowajcy": lista}


def komunikat(stan: dict) -> str:
    """Zdanie dla maintainera — po polsku, jak cały `.github/scripts/` (v19.20.0).

    Narzędzie kontrybutora (`audyt_zaleznosci.ostrzez_cykl`) czyta `--json`
    i składa własne zdanie po angielsku, więc ten tekst do niego nie trafia.
    """
    s = stan["stan"]
    w = stan.get("wersja", "?")
    if s == "nieotwarty":
        pliki = stan.get("winowajcy", [])
        return (f"Cykl wydania nieotwarty: VERSION={w} ma już tag ({stan['tag']}), "
                f"a od niego zmieniło się {len(pliki)} plik(ów) wydania ({', '.join(pliki[:3])}"
                f"{', ...' if len(pliki) > 3 else ''}). Ustaw VERSION na X.Y.0-WIP (minor/major) "
                f"albo X.Y.Z-WIP (patch), żeby wstrzymania zależności wygasły teraz, "
                f"a nie w buildzie zamykającym.")
    if s == "wip_wydanej":
        return (f"VERSION={w} ma -WIP, ale tag {stan['tag']} już istnieje — "
                f"cykl musi nieść NASTĘPNY numer wersji.")
    if s == "wip":
        return f"Cykl otwarty: VERSION={w} ({stan['typ']})."
    if s == "wydany":
        return f"Spoczynek po wydaniu {stan['tag']} (od tamtej pory tylko dev-tooling)."
    if s == "zamykanie":
        return f"Zamykanie cyklu: VERSION={w} nie ma jeszcze tagu."
    return f"Stan cyklu nieznany: {stan.get('powod', '?')}."


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    stan = stan_cyklu()
    if "--json" in argv:
        print(json.dumps(stan, ensure_ascii=False))
    else:
        print(komunikat(stan))
    return 1 if stan["stan"] in STANY_BLEDU else 0


if __name__ == "__main__":
    sys.exit(main())
