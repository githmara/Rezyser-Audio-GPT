#!/usr/bin/env python
"""
odpowiedz_lokalnie.py — lokalne domknięcie issue głosem Północy (od v17.1).

Zastępuje dawny obieg ``pending_answer.md`` + commit + bot + atomic-reset dla
flow ``answered``. Maintainer ma lokalny ``gh`` CLI, więc odpowiedź na pytanie
(albo domknięcie buga z osobistą notką) publikujemy WPROST z maszyny — bez
commitów, pushy, force-pushy i bez zanieczyszczania historii repo. Draft
odpowiedzi leży w pliku GITIGNOROWANYM (domyślnie ``skrypty/pending_answer.md``)
i nigdy nie trafia do gita.

Skrypt opakowuje treść w styl jednej z bohaterek Północy (Lumi/Vieno/Katla),
wykrywa język oryginalnego zgłoszenia (lingua) i robi przez ``gh``:
``issue comment`` → ``issue close`` → ``issue lock --reason resolved``.

Teksty person renderuje ``bot_i18n.t_bot`` z ``dictionaries/<kod>/gui/ui.yaml``
(sekcja ``bot:``) — to samo źródło prawdy, którego używa bot Actions. Wykrywanie
języka robi ``bot_i18n.wykryj`` (detektor budowany dynamicznie ze
``dictionaries/*/podstawy.yaml``). Listę person (PERSONAS) importujemy z bota
Północy ``.github/scripts/issue_closure_north.py`` (single source).

Dwa tryby:
  * ``answered`` (domyślny) — odpowiedź na pytanie/help wanted. Draft jest
    OBOWIĄZKOWY (to treść odpowiedzi), opakowywany w klucz ``bot.answered.*``
    bez linku do Release.
  * ``fixed-in-release`` — domknięcie buga z linkiem do najnowszego Release
    (``bot.closure.*``). Draft jest OPCJONALNY: jeśli istnieje, dolepiamy go jako
    osobistą notkę pod separatorem ``---`` (dawny „release-with-answer").
    Bez draftu publikujemy sam ``bot.closure.*`` z linkiem. Uwaga: zwykłe bugi i tak
    domyka bot przez web-label `fixed-in-release` — ten tryb jest dla sytuacji,
    gdy chcesz dorzucić osobistą wiadomość lub zamknąć ręcznie z lokala.

Użycie:
    python odpowiedz_lokalnie.py <numer_issue> [--tryb answered|fixed-in-release]
        [--plik skrypty/pending_answer.md] [--persona Lumi|Vieno|Katla]
        [--etykieta] [--dry-run]

    --dry-run    pokazuje wygenerowaną treść i NIE publikuje (podgląd przed wysyłką).
    --etykieta   dodatkowo nadaje etykietę (answered/fixed-in-release) dla rekordu
                 (domyślnie nie — zamknięcie robi sam skrypt, etykieta zbędna).
    --persona    wymusza konkretną bohaterkę (domyślnie losowa).

Wymaga: zalogowanego lokalnie ``gh`` CLI oraz ``lingua-language-detector``
w środowisku (to samo, którego używa reszta projektu).
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys

# Detektor języka + lista person żyją w bocie Północy; teksty person renderuje
# `bot_i18n.t_bot` z `dictionaries/<kod>/gui/ui.yaml` (sekcja `bot:`) — to samo
# źródło prawdy, którego używa bot Actions (koniec hardkodowanych dictów).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".github", "scripts"))
import bot_i18n  # noqa: E402
from lingua import Language  # noqa: E402
from issue_closure_north import PERSONAS  # noqa: E402

DOMYSLNY_PLIK = os.path.join("skrypty", "pending_answer.md")


def _gh_tekst(cmd: list[str]) -> str | None:
    """Uruchamia ``gh`` i zwraca stdout (str) lub None przy błędzie."""
    try:
        wynik = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return wynik.stdout
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"[!] {' '.join(cmd[:3])} zfailowało: {exc.stderr.strip() or exc}\n"
        )
        return None
    except FileNotFoundError:
        sys.stderr.write("[!] `gh` CLI nie znalezione w PATH.\n")
        return None


def _gh_akcja(cmd: list[str]) -> bool:
    """Uruchamia ``gh`` dla efektu ubocznego (comment/close/lock). True = sukces."""
    return _gh_tekst(cmd) is not None


def _repo_namewithowner() -> str | None:
    out = _gh_tekst(["gh", "repo", "view", "--json", "nameWithOwner",
                     "-q", ".nameWithOwner"])
    return out.strip() if out else None


def _tresc_issue(numer: str) -> str:
    """Pobiera body issue przez gh (do detekcji języka). Pusty string przy błędzie."""
    out = _gh_tekst(["gh", "issue", "view", numer, "--json", "body", "-q", ".body"])
    return (out or "").strip()


def _wczytaj_draft(sciezka: str) -> str:
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except FileNotFoundError:
        return ""
    except OSError as exc:
        sys.stderr.write(f"[!] Nie udało się otworzyć {sciezka}: {exc}\n")
        return ""


def _wykryj_jezyk(tekst: str) -> Language:
    # Detektor budowany dynamicznie ze `dictionaries/*/podstawy.yaml`
    # (bot_i18n.wykryj) — wynik to jeden z obecnych języków albo None (pusty
    # tekst / niepewność) → wtedy angielski. t_bot i tak ma własny fallback EN,
    # ale Language jest potrzebny do logu (.name).
    return bot_i18n.wykryj(tekst) or Language.ENGLISH


def _buduj_tresc(tryb: str, jezyk: Language, persona: str, draft: str,
                 link: str | None) -> str:
    if tryb == "answered":
        return bot_i18n.t_bot(f"bot.answered.{persona}", jezyk,
                              maintainer_answer=draft)
    # fixed-in-release: closure z linkiem + opcjonalny dolepek osobistej notki.
    tresc = bot_i18n.t_bot(f"bot.closure.{persona}", jezyk, link=link)
    if draft:
        intro = bot_i18n.t_bot("bot.personal_note_intro", jezyk)
        tresc = f"{tresc}\n\n---\n\n*{intro}*\n\n{draft}"
    return tresc


def main() -> int:
    p = argparse.ArgumentParser(description="Lokalne domknięcie issue głosem Północy.")
    p.add_argument("numer", help="numer issue do domknięcia")
    p.add_argument("--tryb", choices=["answered", "fixed-in-release"],
                   default="answered", help="rodzaj domknięcia (domyślnie answered)")
    p.add_argument("--plik", default=DOMYSLNY_PLIK,
                   help=f"plik z draftem (domyślnie {DOMYSLNY_PLIK})")
    p.add_argument("--persona", choices=PERSONAS, default=None,
                   help="wymuś bohaterkę (domyślnie losowa)")
    p.add_argument("--etykieta", action="store_true",
                   help="dodatkowo nadaj etykietę trybu (domyślnie nie)")
    p.add_argument("--dry-run", action="store_true",
                   help="pokaż treść i NIE publikuj")
    args = p.parse_args()

    numer = args.numer.strip().lstrip("#")
    draft = _wczytaj_draft(args.plik)

    if args.tryb == "answered" and not draft:
        sys.stderr.write(
            f"[!] Tryb `answered` wymaga treści odpowiedzi w pliku {args.plik}. "
            "Zapisz tam draft (markdown OK, bez podpisu — wrapper dopisze swój) "
            "i uruchom ponownie.\n"
        )
        return 1

    body = _tresc_issue(numer)
    if not body:
        sys.stderr.write(
            f"[!] Nie udało się pobrać treści issue #{numer} (gh). Sprawdź numer "
            "i czy `gh` jest zalogowany. Język spadnie na angielski.\n"
        )

    jezyk = _wykryj_jezyk(body)
    persona = args.persona or random.choice(PERSONAS)

    link = None
    if args.tryb == "fixed-in-release":
        repo = _repo_namewithowner()
        link = (f"https://github.com/{repo}/releases/latest" if repo
                else "https://github.com/releases/latest")

    tresc = _buduj_tresc(args.tryb, jezyk, persona, draft, link)

    print(f"Issue #{numer} | tryb: {args.tryb} | język: {jezyk.name} | "
          f"persona: {persona}"
          + (f" | notka: {len(draft)} zn." if args.tryb == 'fixed-in-release' and draft else "")
          + (f" | odpowiedź: {len(draft)} zn." if args.tryb == 'answered' else ""))

    if args.dry_run:
        print("\n--- DRY-RUN: treść do opublikowania (nic nie wysłano) ---\n")
        print(tresc)
        return 0

    if not _gh_akcja(["gh", "issue", "comment", numer, "--body", tresc]):
        return 1
    if args.etykieta:
        # Nadanie etykiety dla rekordu — niekrytyczne (zamknięcie i tak robimy).
        _gh_akcja(["gh", "issue", "edit", numer, "--add-label", args.tryb])
    if not _gh_akcja(["gh", "issue", "close", numer]):
        return 1
    if not _gh_akcja(["gh", "issue", "lock", numer, "--reason", "resolved"]):
        sys.stderr.write(
            f"[!] Lock issue #{numer} nie powiódł się — komentarz i close OK, "
            "ale wątek pozostaje odblokowany.\n"
        )

    print(f"Issue #{numer} skomentowane, zamknięte i zablokowane przez {persona}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
