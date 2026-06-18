"""
issue_closure_north.py — etap „Północ" obiegu „Z Południa na Północ".

Od v17.1 ten bot obsługuje WYŁĄCZNIE etykietę ``fixed-in-release`` (bug-fix
flow). Po jej nadaniu przez maintainera jedna z bohaterek Północy:

  * Lumi  — śnieżnie, mroźnie, z humorem,
  * Vieno — szamańsko, mgliście, w półszeptach,
  * Katla — wulkanicznie, gorąco, z hukiem,

komentuje issue z linkiem do najnowszego Release, zamyka je i lockuje — w
języku oryginalnego zgłoszenia (lingua-language-detector; fallback EN).

Flow ``answered`` (odpowiedzi na pytania) został w v17.1 PRZENIESIONY do
lokalnego skryptu ``odpowiedz_lokalnie.py``. Maintainer ma od dawna lokalny
``gh`` CLI, więc nie potrzeba już obiegu przez zacommitowany plik: zniknęła
cała maszyneria ``pending_answer.md`` + commit + atomic-reset / cleanup-commit
/ force-push + tryb COMMENT (draft odpowiedzi nigdy nie dotyka historii repo).
Historia tamtego rozwiązania (v15.2.6 → v15.2.8) → ``claude_archive.md``.

Źródłem prawdy tekstów person jest ``dictionaries/<kod>/gui/ui.yaml`` (klucze
``bot.closure.*`` / ``bot.answered.*`` / ``bot.personal_note_intro``),
renderowane przez ``bot_i18n.t_bot(...)`` — autotłumaczalne razem z resztą UI,
więc dodanie 10. języka nie wymaga już edycji Pythona (sprawa 2 / cykl 18.X).
Dawne dict-y ``TEMPLATES`` / ``TEMPLATES_ANSWERED`` / ``PERSONAL_NOTE_INTRO``
zostały usunięte po akceptacji autotłumaczeń (przeniesione 1:1 do ui.yaml).

Wywołanie (z workflow ``issue-closure.yml``):
    python .github/scripts/issue_closure_north.py
    (dane czytane z os.environ — bez argv, by uniknąć word-splittingu basha
    na cudzysłowach / backtickach w treści issue)

Wymagane zmienne środowiskowe (sekcja ``env:`` w YAML):
    ISSUE_BODY         oryginalna treść issue (detekcja języka)
    ISSUE_NUMBER       numer issue
    LABEL_NAME         etykieta wyzwalająca (``fixed-in-release``)
    GH_TOKEN           token gh CLI (auto z secrets.GITHUB_TOKEN)
    GITHUB_REPOSITORY  owner/repo (auto z runtime'u GH Actions)
    GITHUB_SERVER_URL  https://github.com (auto; do linku Releases)
"""

from __future__ import annotations

import os
import random
import subprocess
import sys

import bot_i18n


PERSONAS = ["Lumi", "Vieno", "Katla"]


# Teksty person (closure / answered / personal_note_intro) żyją w
# dictionaries/<kod>/gui/ui.yaml (sekcja bot.*) i są renderowane przez
# bot_i18n.t_bot — patrz docstring modułu (ui.yaml = źródło prawdy).


def _zbuduj_link_release() -> str:
    """Konstruuje link do najnowszego release'u na podstawie env GitHub."""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return f"{server}/releases/latest"
    return f"{server}/{repo}/releases/latest"


def _gh(cmd: list[str]) -> bool:
    """Uruchamia `gh` z przechwyceniem błędów. Zwraca True przy sukcesie."""
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"[!] {cmd[0]} zfailowało ({' '.join(cmd[:3])}): "
            f"{exc.stderr.strip() or exc}\n"
        )
        return False
    except FileNotFoundError:
        sys.stderr.write(f"[!] `{cmd[0]}` CLI nie znalezione w PATH.\n")
        return False


def main() -> int:
    # Od v17.1 ten bot obsługuje WYŁĄCZNIE etykietę `fixed-in-release`
    # (bug-fix flow): jedna z bohaterek Północy komentuje z linkiem do
    # najnowszego Release i zamyka issue w języku oryginalnego zgłoszenia.
    #
    # Flow `answered` (odpowiedzi na pytania) został w v17.1 PRZENIESIONY do
    # lokalnego skryptu `odpowiedz_lokalnie.py` — maintainer ma lokalny gh CLI,
    # więc nie potrzeba już obiegu przez zacommitowany plik. Zniknęła cała
    # maszyneria pending_answer.md + commit + atomic-reset / cleanup-commit /
    # force-push + tryb COMMENT: draft odpowiedzi nigdy nie dotyka historii repo.
    # Teksty answer-flow to teraz klucze `bot.answered.*` w ui.yaml (renderowane
    # przez bot_i18n.t_bot), używane przez `odpowiedz_lokalnie.py`.
    #
    # Dane issue czytamy z env (nie z argv), żeby uniknąć word-splittingu basha
    # na cudzysłowach / backtickach w treści zgłoszenia.
    issue_body = os.environ.get("ISSUE_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "").strip()
    label_name = os.environ.get("LABEL_NAME", "").strip()
    if not issue_number:
        sys.stderr.write(
            "[!] Brak ISSUE_NUMBER w env — przerywam (workflow musi "
            "wstrzyknąć ISSUE_BODY i ISSUE_NUMBER w sekcji env:).\n"
        )
        return 2

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        sys.stderr.write("[!] Brak GITHUB_REPOSITORY w env.\n")
        return 1

    # Bezpiecznik: workflow filtruje już po `fixed-in-release`, ale gdyby event
    # przyszedł z inną etykietą (np. ktoś rozszerzy trigger), nie zamykamy issue.
    if label_name and label_name != "fixed-in-release":
        print(
            f"Etykieta {label_name!r} nie jest obsługiwana przez tego bota "
            "(tylko `fixed-in-release`). Kończę bez zmian."
        )
        return 0

    wykryty = bot_i18n.wykryj(issue_body)

    persona = random.choice(PERSONAS)
    kod = bot_i18n.kod_iso(wykryty)
    print(f"Wykryto język: {kod}. Dyżur: {persona}. "
          f"Etykieta wyzwalająca: {label_name or '(nieznana)'}.")

    # Źródło prawdy = `bot.closure.<persona>` w ui.yaml (t_bot ma fallback EN).
    tresc = bot_i18n.t_bot(f"bot.closure.{persona}", wykryty,
                           link=_zbuduj_link_release())

    if not _gh(["gh", "issue", "comment", issue_number, "--repo", repo,
                "--body", tresc]):
        return 1
    if not _gh(["gh", "issue", "close", issue_number, "--repo", repo]):
        return 1
    # Lock po zamknięciu (reason `resolved`). Niekrytyczny — przy fail logujemy
    # ostrzeżenie, ale komentarz + close już poszły.
    if not _gh(["gh", "issue", "lock", issue_number, "--repo", repo,
                "--reason", "resolved"]):
        sys.stderr.write(
            f"[!] Lock issue #{issue_number} nie powiódł się — "
            "komentarz i close OK, ale wątek pozostaje odblokowany.\n"
        )

    print(f"Issue #{issue_number} skomentowane, zamknięte i zablokowane przez {persona}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
