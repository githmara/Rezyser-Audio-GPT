#!/usr/bin/env python
"""
sync_dev_release.py — skrócona procedura wydawnicza (dev-tools-only).

Wołany przez workflow `sync-dev-release.yml`. Realizuje to, co maintainer robił
dotąd ręcznie po dopisaniu dev-toolingu do JUŻ OPUBLIKOWANEGO wydania (wzorzec
od v18.6, użyty m.in. w v18.22.0 i v18.24.0):

  1. czyta `VERSION` i sprawdza, że tag `v<wersja>` istnieje na origin,
  2. sprawdza, że wydanie dla tego tagu jest OPUBLIKOWANE (nie draft),
  3. **bramka dev-tools-only** — patrz :func:`pliki_runtime_w_zakresie`,
  4. wycina sekcję `## <wersja>` z `RELEASE_NOTES.md` (wspólny
     `release_notes_sekcja`, ten sam co przy tworzeniu draftu),
  5. przesuwa tag na HEAD (force-push, jedyny dozwolony wyjątek od zakazu
     force-pusha — tag-only, nigdy gałąź),
  6. synchronizuje body wydania z wyciętą sekcją,
  7. weryfikuje U ŹRÓDŁA oba twierdzenia, na których stoi cała procedura: tag
     na origin wskazuje HEAD, a opis wydania zgadza się z sekcją.

Skrypt jest IDEMPOTENTNY — ponowne uruchomienie na zsynchronizowanym stanie
nie robi nic poza weryfikacją. To celowe: gdyby padł między przesunięciem tagu
a synchronizacją opisu (albo odwrotnie), właściwą reakcją jest po prostu
uruchomić go jeszcze raz.

DLACZEGO force-push tagu jest tu poprawny: od v17.11 aktualizacja ze źródła
dostarcza użytkownikowi także dev-tooling, więc dopisany dev-tool bez przesunięcia
tagu byłby niedostępny dla nikogo poza maintainerem. Rangę tego wyjątku podniesiono
świadomie — patrz reguły git-workflow.

DLACZEGO to NIE JEST droga dla zmian w runtime: asset instalatora w wydaniu
zostaje z POPRZEDNIEGO builda. Przesunięcie tagu po zmianie w kodzie aplikacji
dałoby opublikowane wydanie, którego `.exe` nie zawiera kodu z jego własnego tagu
— rozjazd nieodwracalny bez ponownego wydania. Dlatego bramka z punktu 3 blokuje
i NIE MA obejścia: właściwą drogą jest nowy patch tag i pełna procedura.

Wszystkie dane wejściowe idą przez `os.environ` (nigdy argv) — user-input
z Web UI Actions nie może trafić do shellu, bo bash robi word-splitting na
cudzysłowach i backtickach (ta sama pułapka, którą omija `issue_intake_sami`).
"""
from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from release_notes_sekcja import BladSekcji, wytnij_sekcje  # noqa: E402

ROOT = pathlib.Path(".")
# Wycięta sekcja idzie do katalogu tymczasowego, nie do roota repo (wzorzec
# `draft-release.yml`: `/tmp/release_notes.md`) — inaczej lokalne uruchomienie
# diagnostyczne zostawiałoby w drzewie nietrackowany plik, a `git status` przed
# commitem jest tu procedurą, nie zwyczajem.
PLIK_BODY = pathlib.Path(tempfile.gettempdir()) / "sync_release_body.md"

# Punkt wejścia aplikacji — korzeń domknięcia importów (patrz niżej).
PUNKT_WEJSCIA = "main.py"

# Ścieżki, których zmiana wymaga PEŁNEJ procedury, choć nie są modułem `.py`
# osiągalnym z `main.py`. `VERSION` bo jest w bundlu (`datas` w spec) i decyduje
# o numerze w GUI; `requirements.txt`, `*.spec` i `installer.iss` bo zmieniają
# zawartość paczki; `dictionaries/` i `docs/` bo instalator shipuje je OBOK exe.
PREFIKSY_NIE_DEV = (
    "VERSION",
    "requirements.txt",
    "installer.iss",
    "dictionaries/",
    "docs/",
)
SUFIKSY_NIE_DEV = (".spec",)


def uruchom(cmd: list[str], *, check: bool = True) -> str:
    """Uruchamia komendę, zwraca stdout. Przy błędzie pokazuje stderr w logu.

    `capture_output` bez tego pochłaniałby diagnostykę gita i `gh` — czyli
    dokładnie to, co jest potrzebne, gdy workflow padnie na uprawnieniach do
    tagu albo na regule ochrony gałęzi.
    """
    print(f"-> {' '.join(cmd)}", flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        if check:
            sys.stderr.write(res.stdout)
            sys.stderr.write(res.stderr)
            sys.exit(
                f"::error::Komenda `{' '.join(cmd)}` zakończyła się kodem "
                f"{res.returncode}. Diagnostyka wyżej."
            )
        return ""
    return res.stdout.strip()


def sha_z_ls_remote(surowe: str) -> str:
    """Wyciąga SHA COMMITU z wyjścia `git ls-remote` dla jednego refa.

    Tag anotowany daje DWA wiersze: obiekt tagu i — z sufiksem `^{}` — commit,
    na który wskazuje. Nasze tagi są lightweight (`git tag <nazwa>` w
    `draft-release.yml`), więc drugiego wiersza zwykle nie ma, ale jeśli kiedyś
    powstanie tag anotowany, porównanie z `HEAD` musi dotyczyć COMMITU, nie
    obiektu tagu — inaczej skrypt uznałby zgodny tag za rozjechany i przesuwał go
    przy każdym uruchomieniu.
    """
    commit, obiekt = "", ""
    for wiersz in surowe.split("\n"):
        czesci = wiersz.split()
        if len(czesci) < 2:
            continue
        if czesci[1].endswith("^{}"):
            commit = czesci[0]
        else:
            obiekt = czesci[0]
    return commit or obiekt


def moduly_lokalne() -> set[str]:
    """Nazwy modułów `.py` z roota repo (bez rozszerzenia)."""
    return {p.stem for p in ROOT.glob("*.py")}


def domkniecie_runtime(punkt_wejscia: str = PUNKT_WEJSCIA) -> set[str]:
    """Moduły `.py` osiągalne z punktu wejścia aplikacji (BFS po importach).

    Ta sama semantyka, którą ma PyInstaller: analiza jest STATYCZNA i wchodzi
    także w importy z CIAŁA funkcji, bo `ast.walk` nie zna pojęcia „leniwy
    import". To nie niedokładność, a właśnie zgodność — lekcja z v18.24, gdy
    okazało się, że `openai` JEST w bundlu (2098 wpisów w `PYZ-00.toc`) mimo
    wyłącznie leniwych importów.

    Rezultat jest z definicji NADMIAROWY względem prawdy o bundlu (nie zna
    warunków `if`), a to jest właściwy kierunek dla bramki: fałszywy alarm
    kosztuje pełną procedurę, przeoczenie kosztuje rozjechane wydanie.
    """
    lokalne = moduly_lokalne()
    do_odwiedzenia, widziane = [punkt_wejscia], set()
    while do_odwiedzenia:
        nazwa = do_odwiedzenia.pop()
        if nazwa in widziane:
            continue
        widziane.add(nazwa)
        plik = ROOT / nazwa
        if not plik.is_file():
            continue
        try:
            drzewo = ast.parse(plik.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as exc:
            sys.exit(f"::error::Nie mogę sparsować {nazwa}: {exc}")
        for wezel in ast.walk(drzewo):
            if isinstance(wezel, ast.Import):
                kandydaci = [a.name.split(".")[0] for a in wezel.names]
            elif isinstance(wezel, ast.ImportFrom):
                # `level > 0` = import relatywny (pakiet) — w płaskim roocie
                # nie występuje; `module is None` przy `from . import x`.
                kandydaci = (
                    [wezel.module.split(".")[0]]
                    if wezel.module and wezel.level == 0
                    else []
                )
            else:
                continue
            for kandydat in kandydaci:
                if kandydat in lokalne:
                    do_odwiedzenia.append(f"{kandydat}.py")
    return widziane


def pliki_runtime_w_zakresie(tag: str) -> list[str]:
    """Pliki zmienione między tagiem a HEAD, które NIE są dev-tools-only.

    Zwraca listę „winowajców" (pusta = można iść skróconą procedurą).
    """
    surowe = uruchom(["git", "diff", "--name-only", f"{tag}..HEAD"])
    zmienione = [w for w in surowe.split("\n") if w.strip()]
    if not zmienione:
        return []
    runtime = domkniecie_runtime()
    winowajcy: list[str] = []
    for sciezka in zmienione:
        normalna = sciezka.replace("\\", "/")
        if normalna in runtime:
            winowajcy.append(f"{normalna} (moduł osiągalny z {PUNKT_WEJSCIA})")
        elif normalna.startswith(PREFIKSY_NIE_DEV):
            winowajcy.append(f"{normalna} (dane albo konfiguracja paczki)")
        elif normalna.endswith(SUFIKSY_NIE_DEV):
            winowajcy.append(f"{normalna} (spec PyInstallera)")
    print(
        f"[*] Zakres {tag}..HEAD: {len(zmienione)} plik(ów), "
        f"domknięcie runtime: {len(runtime)} modułów, "
        f"naruszeń dev-tools-only: {len(winowajcy)}"
    )
    for w in winowajcy:
        print(f"      * {w}")
    return winowajcy


def main() -> int:
    if os.environ.get("POTWIERDZENIE", "").strip() != "tak":
        print("[*] Input `potwierdz` nie jest równy 'tak' — no-op, nic nie zmieniam.")
        return 0

    # 1. VERSION → oczekiwany tag.
    plik_wersji = ROOT / "VERSION"
    if not plik_wersji.is_file():
        sys.exit("::error::Brak pliku VERSION w roocie repo.")
    wersja = plik_wersji.read_text(encoding="utf-8").strip()
    if not wersja:
        sys.exit("::error::Plik VERSION jest pusty.")
    tag = f"v{wersja}"
    print(f"[*] Wersja z pliku VERSION: {wersja} (tag: {tag})")

    if wersja.endswith("-WIP"):
        sys.exit(
            f"::error::VERSION={wersja} jest oznaczony jako WIP. Skrócona "
            f"procedura synchronizuje OPUBLIKOWANE wydanie — najpierw domknij "
            f"wersję albo użyj `draft-release.yml` dla nowego wydania."
        )

    # 2. HEAD musi być czubkiem `main` na origin. Sprawdzamy SHA, nie nazwę
    #    gałęzi: `actions/checkout` bywa w stanie detached (zależnie od tego,
    #    czym workflow został wyzwolony), a bramka na `--abbrev-ref HEAD`
    #    odmawiałaby wtedy pracy bez powodu. Zgodność SHA z `refs/heads/main`
    #    na origin niesie CAŁY potrzebny warunek: tag nie może wskazać commita,
    #    którego nie ma w gałęzi domyślnej — ani lokalnego, ani z innej gałęzi.
    head = uruchom(["git", "rev-parse", "HEAD"])
    zdalny = uruchom(["git", "ls-remote", "origin", "refs/heads/main"])
    origin_main = zdalny.split()[0] if zdalny else ""
    if not origin_main:
        sys.exit("::error::Nie mogę odczytać `refs/heads/main` z origin.")
    if origin_main != head:
        sys.exit(
            f"::error::HEAD ({head[:8]}) nie jest czubkiem origin/main "
            f"({origin_main[:8]}). Albo commit nie został wypchnięty, albo "
            f"workflow uruchomiono z innej gałęzi — w Web UI Actions wybierz "
            f"`main` (Run workflow → Branch) i wypchnij zmiany przed synchronizacją."
        )

    # 3. Tag MUSI istnieć na origin — skrócona procedura aktualizuje wydanie,
    #    nie tworzy go (do tworzenia jest `draft-release.yml`). SHA bierzemy
    #    ZE ZDALNEGO refa, nie z lokalnego tagu: to zdalny stan decyduje, czy
    #    push jest potrzebny, a lokalna kopia po `fetch` bywa nieaktualna
    #    dokładnie w tym scenariuszu, który to narzędzie obsługuje.
    surowy_ref = uruchom(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"])
    if not surowy_ref:
        sys.exit(
            f"::error::Tag {tag} nie istnieje na origin. Skrócona procedura "
            f"wymaga opublikowanego wydania — dla nowego użyj `draft-release.yml`."
        )
    stary_commit = sha_z_ls_remote(surowy_ref)

    # 4. Wydanie musi być opublikowane. Draft ma inną drogę (upload + Publish),
    #    a `gh release edit --notes-file` po cichu przepisałby treść draftu,
    #    zostawiając maintainera z wrażeniem, że wydanie jest gotowe.
    stan = uruchom(
        ["gh", "release", "view", tag, "--json", "isDraft,tagName", "--jq",
         '(.isDraft|tostring) + " " + .tagName'],
        check=False,
    )
    if not stan:
        sys.exit(
            f"::error::Nie znalazłem wydania dla tagu {tag} (albo `gh` nie ma "
            f"do niego dostępu). Skrócona procedura synchronizuje ISTNIEJĄCE "
            f"wydanie."
        )
    if stan.split()[0] == "true":
        sys.exit(
            f"::error::Wydanie {tag} jest DRAFTEM. Skrócona procedura dotyczy "
            f"wydań OPUBLIKOWANYCH — dokończ publikację (upload instalatora "
            f"+ Publish) albo popraw treść draftu ręcznie."
        )

    # 5. BRAMKA dev-tools-only — bez obejścia (patrz nagłówek modułu).
    winowajcy = pliki_runtime_w_zakresie(tag)
    if winowajcy:
        # Zakres niebędący dev-tools-only bywa duży (bump VERSION ciągnie 27
        # plików `docs/`), a komunikat ma być czytelny — pełna lista jest
        # w logu kroku, w adnotacji zostaje próbka.
        widoczne = winowajcy[:8]
        if len(winowajcy) > len(widoczne):
            widoczne.append(f"... (+{len(winowajcy) - len(widoczne)} więcej)")
        lista = "%0A".join(f"      * {w}" for w in widoczne)
        # `%0A` zamiast `\n`: adnotacja `::error::` konczy sie na pierwszym
        # znaku nowej linii, wiec surowy `\n` uciąłby liste winowajców
        # dokładnie tam, gdzie zaczyna się to, co maintainer ma przeczytać.
        sys.exit(
            "::error::Odmowa: zakres tej synchronizacji NIE jest dev-tools-only.%0A"
            f"{lista}%0A"
            "      Asset instalatora w wydaniu zostaje z POPRZEDNIEGO builda, więc "
            "przesunięcie tagu dałoby opublikowane wydanie, którego `.exe` nie "
            "zawiera kodu z jego własnego tagu. Właściwa droga: bump VERSION, "
            "pełna procedura wydawnicza i nowy tag (`draft-release.yml`)."
        )

    # 6. Sekcja RELEASE_NOTES — ten sam ekstraktor, co przy tworzeniu draftu.
    plik_notes = ROOT / "RELEASE_NOTES.md"
    if not plik_notes.is_file():
        sys.exit("::error::Brak pliku RELEASE_NOTES.md w roocie repo.")
    try:
        body = wytnij_sekcje(plik_notes.read_text(encoding="utf-8"), wersja)
    except BladSekcji as exc:
        sys.exit(f"::error::{exc}")
    PLIK_BODY.write_text(body, encoding="utf-8")
    print(f"[*] Sekcja ## {wersja}: {len(body)} znaków → {PLIK_BODY}")

    # 7. Przesunięcie tagu (force-push TAG-ONLY, nigdy gałąź).
    uruchom(["git", "config", "user.name", "github-actions[bot]"])
    uruchom(
        ["git", "config", "user.email",
         "41898282+github-actions[bot]@users.noreply.github.com"]
    )
    if stary_commit == head:
        print(f"[*] Tag {tag} już wskazuje HEAD ({head[:8]}) — pomijam przesunięcie.")
    else:
        uruchom(["git", "tag", "-d", tag], check=False)
        uruchom(["git", "tag", tag, "HEAD"])
        uruchom(["git", "push", "origin", f"refs/tags/{tag}", "--force"])
        print(
            f"[*] Tag {tag} przesunięty: {stary_commit[:8] or '(brak)'} → {head[:8]}"
        )

    # 8. Synchronizacja treści wydania.
    uruchom(["gh", "release", "edit", tag, "--notes-file", str(PLIK_BODY)])
    print(f"[*] Body wydania {tag} zsynchronizowane z RELEASE_NOTES.md.")

    # 9. Weryfikacja PO FAKCIE — cała ta procedura opiera się na dwóch
    #    twierdzeniach („tag wskazuje HEAD", „opis zgadza się z RELEASE_NOTES"),
    #    więc oba sprawdzamy u źródła, zamiast wnioskować z kodów wyjścia.
    #    Tak samo weryfikowane jest ręczne wydanie: tag, body znak w znak.
    po_pushu = sha_z_ls_remote(
        uruchom(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"])
    )
    if po_pushu != head:
        sys.exit(
            f"::error::Po pushu tag {tag} na origin wskazuje {po_pushu[:8]}, "
            f"a nie HEAD ({head[:8]}). Sprawdź reguły ochrony tagów w "
            f"ustawieniach repozytorium."
        )
    print(f"[*] Weryfikacja: tag {tag} na origin = HEAD ({head[:8]}).")

    zdalne_body = uruchom(
        ["gh", "release", "view", tag, "--json", "body", "--jq", ".body"],
        check=False,
    )
    # GitHub normalizuje końce linii (CRLF) i przycina końcowy znak nowej linii,
    # więc porównujemy treść bez białych znaków na brzegach — reszta musi się
    # zgadzać znak w znak.
    if zdalne_body.replace("\r\n", "\n").strip() != body.strip():
        sys.exit(
            f"::error::Opis wydania {tag} po synchronizacji NIE zgadza się "
            f"z sekcją ## {wersja} (zdalnie {len(zdalne_body)} znaków, lokalnie "
            f"{len(body)}). Sprawdź opis w Web UI przed ogłoszeniem gotowości."
        )
    print(f"[*] Weryfikacja: opis wydania zgodny z sekcją ## {wersja} "
          f"({len(body.strip())} znaków).")

    print(
        "[*] Gotowe. Asset instalatora NIE został ruszony — to zamierzone "
        "w skróconej procedurze (zmiana nie wchodzi do paczki)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
