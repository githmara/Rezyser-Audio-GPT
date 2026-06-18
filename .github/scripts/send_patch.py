import os
import random
import re
import smtplib
import subprocess
import sys
from email.message import EmailMessage

import bot_i18n

EMAIL_REGEX = re.compile(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}\b")

# Link patcha NIE jest już zahardkodowany — czytamy go z sekretu
# TIFLO_PATCH_LINK (env). Aktualizacja = `gh secret set TIFLO_PATCH_LINK`:
# atomowo i natychmiast dla następnego runu, BEZ commita/pusha → znika okno
# wyścigu „stary link w trakcie aktualizacji". Bonus: link nie leży jawnie
# w repo. Patrz reguly_github_bot „wyścig nieaktualnego linku Tiflotecnia".

# Komunikaty pauza / brak_emaila: klucze bot.patch.pauza / bot.patch.brak_emaila
# w ui.yaml (per-język), renderowane przez bot_i18n.t_bot.
ETYKIETA_ON_HOLD = "on-hold"

PERSONAS = ["Lumi", "Vieno", "Katla"]

# Teksty maila patcha (subject / body / footer): klucze bot.patch.* w ui.yaml,
# renderowane przez bot_i18n.t_bot — patrz docstring modułu.


def dodaj_komentarz_do_issue(numer_issue: str, tresc: str) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        sys.stderr.write("[!] Brak GITHUB_REPOSITORY w env — nie dodaję komentarza.\n")
        return
    try:
        subprocess.run(
            [
                "gh", "issue", "comment", numer_issue,
                "--repo", repo,
                "--body", tresc,
            ],
            check=True, capture_output=True, text=True,
        )
        print(f"Komentarz dodany do issue #{numer_issue}.")
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"[!] gh issue comment zfailowało: {exc.stderr.strip() or exc}\n"
        )
    except FileNotFoundError:
        sys.stderr.write("[!] `gh` CLI nie znalezione w PATH.\n")


def oznacz_etykieta(numer_issue: str, etykieta: str) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        sys.stderr.write("[!] Brak GITHUB_REPOSITORY w env — nie nadaję etykiety.\n")
        return
    try:
        subprocess.run(
            [
                "gh", "issue", "edit", numer_issue,
                "--repo", repo,
                "--add-label", etykieta,
            ],
            check=True, capture_output=True, text=True,
        )
        print(f"Nadano etykietę '{etykieta}' issue #{numer_issue}.")
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"[!] gh issue edit --add-label zfailowało: {exc.stderr.strip() or exc}\n"
        )
    except FileNotFoundError:
        sys.stderr.write("[!] `gh` CLI nie znalezione w PATH.\n")


def ustaw_status(status: str) -> None:
    """Zapisuje `status=<...>` do $GITHUB_OUTPUT — workflow YAML odpala kroki
    redact/close/lock TYLKO gdy status == 'sent' (patrz patch-bot.yml)."""
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    try:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"status={status}\n")
    except OSError as exc:
        sys.stderr.write(f"[!] Nie udało się zapisać status={status}: {exc}\n")


def czy_pauza() -> bool:
    """TIFLO_PATCH_PAUSED == 'tak' → maintainer aktualizuje link, wstrzymujemy."""
    return os.environ.get("TIFLO_PATCH_PAUSED", "").strip().lower() == "tak"


def main() -> int:
    # Dane issue czytamy z env (ISSUE_BODY/ISSUE_NUMBER w sekcji `env:`
    # workflowu), a nie z sys.argv — bash przy przekazywaniu argumentów
    # robi word-splitting na cudzysłowach i backtickach w ciele zgłoszenia,
    # co rozsypuje argv przy treściach typu `Błąd w "Managerze"` albo
    # snippetcie kodu z `gh issue list`.
    issue_body = os.environ.get("ISSUE_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "").strip()
    if not issue_number:
        sys.stderr.write(
            "[!] Brak ISSUE_NUMBER w env — workflow musi wstrzyknąć "
            "ISSUE_BODY i ISSUE_NUMBER w sekcji env:.\n"
        )
        return 1

    # Język komentarzy pre-email (pauza / brak emaila) wykrywamy z treści
    # zgłoszenia. None → t_bot spadnie na EN. Detektor budowany dynamicznie ze
    # `dictionaries/*/podstawy.yaml` (bot_i18n) — nowy język bez edycji Pythona.
    jezyk_zgloszenia = bot_i18n.wykryj(issue_body)

    # --- PAUZA: maintainer właśnie aktualizuje link patcha ---
    # Wstrzymujemy CAŁY flow: komentarz „trwa aktualizacja", etykieta on-hold,
    # issue zostaje OTWARTE. Nie wysyłamy, nie zamykamy, nie lockujemy.
    if czy_pauza():
        dodaj_komentarz_do_issue(issue_number,
                                 bot_i18n.t_bot("bot.patch.pauza", jezyk_zgloszenia))
        oznacz_etykieta(issue_number, ETYKIETA_ON_HOLD)
        ustaw_status("paused")
        print("Tryb PAUZY (TIFLO_PATCH_PAUSED=tak) — issue otwarte, link NIE wysłany.")
        return 0

    email_match = EMAIL_REGEX.search(issue_body)
    if not email_match:
        dodaj_komentarz_do_issue(issue_number,
                                 bot_i18n.t_bot("bot.patch.brak_emaila", jezyk_zgloszenia))
        ustaw_status("no_email")
        return 1

    # Link czytany z sekretu (env). Brak sekretu = traktujemy jak pauzę:
    # NIGDY nie wysyłaj pustego linku ani nie zamykaj issue (fail-safe).
    patch_link = os.environ.get("TIFLO_PATCH_LINK", "").strip()
    if not patch_link:
        sys.stderr.write(
            "[!] Brak TIFLO_PATCH_LINK w env — sekret nieustawiony. "
            "Wstrzymuję (on-hold), nie wysyłam.\n"
        )
        dodaj_komentarz_do_issue(issue_number,
                                 bot_i18n.t_bot("bot.patch.pauza", jezyk_zgloszenia))
        oznacz_etykieta(issue_number, ETYKIETA_ON_HOLD)
        ustaw_status("paused")
        return 0

    recipient_email = email_match.group(0)
    # Język maila wykrywamy z treści BEZ adresu email (mniej szumu dla lingua).
    tekst_do_analizy = issue_body.replace(recipient_email, "").strip()
    wykryty_jezyk = bot_i18n.wykryj(tekst_do_analizy)

    wylosowana_postac = random.choice(PERSONAS)
    print(
        f"Wykryto język: {bot_i18n.kod_iso(wykryty_jezyk)}. "
        f"Dzisiaj obsługuje: {wylosowana_postac}."
    )

    # Źródło prawdy = klucze `bot.patch.*` w ui.yaml (t_bot ma fallback EN).
    # subject używa {issue_number}, body {link} — format ignoruje nieużyte kwargi.
    temat = bot_i18n.t_bot(f"bot.patch.{wylosowana_postac}.subject",
                           wykryty_jezyk, issue_number=issue_number)
    tresc_glowna = bot_i18n.t_bot(f"bot.patch.{wylosowana_postac}.body",
                                  wykryty_jezyk, link=patch_link)
    stopka_sformatowana = bot_i18n.t_bot("bot.patch.footer",
                                         wykryty_jezyk, issue_number=issue_number)
    pelna_tresc = f"{tresc_glowna}\n\n---\n{stopka_sformatowana}"

    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    if not smtp_user or not smtp_pass:
        sys.stderr.write(
            "[!] Brak SMTP_USER lub SMTP_PASS w env — nie da się wysłać.\n"
        )
        return 1

    msg = EmailMessage()
    msg["Subject"] = temat
    msg["From"] = smtp_user
    msg["To"] = recipient_email
    msg.set_content(pelna_tresc)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"Wiadomość wysłana pomyślnie na {recipient_email}.")
        ustaw_status("sent")
        return 0
    except Exception as exc:
        sys.stderr.write(f"[!] Błąd wysyłki maila: {exc}\n")
        ustaw_status("error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
