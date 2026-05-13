"""
send_patch.py — wysyła patcha Tiflotecnia Voices na adres email z body issue.

Logika:
  1. Wyciągnij adres email z `argv[1]` (treść issue) używając rygorystycznego
     regex-u `[\\w\\.-]+@[\\w\\.-]+\\.[a-zA-Z]{2,}\\b`.
  2. Jeśli BRAK adresu — dodaj komentarz do issue „Nie znalazłem adresu email
     w treści — uzupełnij proszę", po czym EXIT 1. Workflow GitHub Actions
     wykrywa exit-code, nie kontynuuje kroków redact / close / lock — issue
     zostaje OPEN dla retry przez użytkownika.
  3. Jeśli email znaleziony — buduj wiadomość z linkiem do patcha + stopką
     antyspamową zawierającą numer issue. Wyślij przez Gmail SMTP_SSL,
     EXIT 0 — workflow kontynuuje redact + close + lock.

Wymagane env-vars (ustawiane w `.github/workflows/patch-bot.yml`):
  * SMTP_USER, SMTP_PASS — Gmail App Password (NIE hasło konta).
  * GH_TOKEN — domyślny `secrets.GITHUB_TOKEN` (dla `gh issue comment` przy
    braku emaila — wystarczy `issues: write`, mamy w permissions workflow).
  * GITHUB_REPOSITORY — auto-wstrzykiwany przez Actions w formacie `owner/repo`.

CLI: `python send_patch.py "<issue_body>" "<issue_number>"`.
"""
import os
import re
import smtplib
import subprocess
import sys
from email.message import EmailMessage


# Mocniejszy regex: TLD min 2 znaki literowe (nie pasuje już `foo@bar.c`).
# Granica słowa `\b` na końcu zapobiega łapaniu trailing kropki / przecinka.
EMAIL_REGEX = re.compile(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}\b")

# Hardkodowany link OneDrive z patchem — autor utrzymuje paczkę poza repo,
# bo Tiflotecnia Voices for NVDA jest oprogramowaniem komercyjnym i licencja
# dodatku nie zezwala na publiczną redystrybucję plików .py.
PATCH_LINK = (
    "https://1drv.ms/u/c/717e0c193b743dcf/"
    "IQDbzNF_k71lR7r54Qtpfc_jASfUF0BwreedEUqqltWDbaU?e=KDJb38"
)

KOMENTARZ_BRAK_EMAILA = (
    "Nie znalazłem adresu email w treści — uzupełnij proszę."
)


def dodaj_komentarz_do_issue(numer_issue: str, tresc: str) -> None:
    """Dodaje komentarz przez `gh issue comment` (env GH_TOKEN + GITHUB_REPOSITORY).

    Nie rzuca wyjątkiem przy błędzie — logujemy do stderr i kontynuujemy.
    Powód: skrypt jest wywoływany tuż przed exit 1 dla brakującego emaila,
    więc nawet jeśli komentarz się nie doda, workflow ma się zakończyć
    z błędem (issue zostaje OPEN). Wyjątek z komentarza tylko zaciemniłby
    główną przyczynę (brak emaila).
    """
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


def zbuduj_tresc_maila(numer_issue: str) -> str:
    """Składa treść wiadomości email z linkiem do patcha + stopką antyspamową.

    Stopka jest WAŻNA z powodu spam-wektora: jeśli ktoś otworzy issue
    z adresem ofiary (third-party), bot wyśle link do tej ofiary. Stopka
    daje odbiorcy kontekst i pozwala go zignorować bez paniki.
    """
    return (
        "Cześć!\n\n"
        "Przesyłam patcha — zgłoszenie zostało zamknięte.\n"
        f"{PATCH_LINK}\n\n"
        "Pozdrawiam\n"
        "Marek Uram\n\n"
        "---\n"
        f"Otrzymujesz tę wiadomość, bo Twój adres email został podany "
        f"w GitHub Issue #{numer_issue} w repozytorium. "
        "Jeśli to nie Ty zgłaszałeś — zignoruj."
    )


def main() -> int:
    if len(sys.argv) < 3:
        sys.stderr.write(
            "Użycie: send_patch.py <issue_body> <issue_number>\n"
        )
        return 1

    issue_body = sys.argv[1]
    issue_number = sys.argv[2]

    email_match = EMAIL_REGEX.search(issue_body)
    if not email_match:
        print(
            "Nie znaleziono adresu email w treści issue. "
            "Dodaję komentarz informacyjny, zostawiam issue OPEN."
        )
        dodaj_komentarz_do_issue(issue_number, KOMENTARZ_BRAK_EMAILA)
        return 1

    recipient_email = email_match.group(0)
    print(f"Znaleziono email: {recipient_email}. Przygotowuję wysyłkę...")

    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    if not smtp_user or not smtp_pass:
        sys.stderr.write(
            "[!] Brak SMTP_USER lub SMTP_PASS w env — nie da się wysłać.\n"
        )
        return 1

    msg = EmailMessage()
    msg["Subject"] = "Tiflotecnia Voices patch — potwierdzenie zgłoszenia"
    msg["From"] = smtp_user
    msg["To"] = recipient_email
    msg.set_content(zbuduj_tresc_maila(issue_number))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"Wiadomość wysłana pomyślnie na {recipient_email}.")
        return 0
    except Exception as exc:
        sys.stderr.write(f"[!] Błąd wysyłki maila: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
