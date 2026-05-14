import os
import re
import smtplib
import subprocess
import sys
from email.message import EmailMessage
from lingua import Language, LanguageDetectorBuilder

EMAIL_REGEX = re.compile(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}\b")

PATCH_LINK = (
    "https://1drv.ms/u/c/717e0c193b743dcf/"
    "IQDbzNF_k71lR7r54Qtpfc_jASfUF0BwreedEUqqltWDbaU?e=KDJb38"
)

KOMENTARZ_BRAK_EMAILA = (
    "PL: Nie znalazłem adresu email w treści — uzupełnij proszę.\n"
    "EN: I couldn't find an email address in the body — please provide one."
)

LANGUAGES = [
    Language.GERMAN, Language.ENGLISH, Language.SPANISH,
    Language.FINNISH, Language.FRENCH, Language.ICELANDIC,
    Language.ITALIAN, Language.POLISH, Language.RUSSIAN,
]
detector = LanguageDetectorBuilder.from_languages(*LANGUAGES).build()

TEMPLATES = {
    Language.POLISH: {
        "subject": "Tiflotecnia Voices patch — potwierdzenie zgłoszenia #{issue_number}",
        "body": (
            "Cześć!\n\n"
            "Przesyłam patcha — zgłoszenie zostało zamknięte.\n"
            "{link}\n\n"
            "Jeśli nie widzisz wiadomości w skrzynce odbiorczej, sprawdź folder Spam lub Wiadomości-śmieci.\n\n"
            "Pozdrawiam\n"
            "Marek Uram\n\n"
            "---\n"
            "Otrzymujesz tę wiadomość, bo Twój adres email został podany w GitHub Issue #{issue_number}. "
            "Jeśli to nie Ty zgłaszałeś — zignoruj."
        ),
    },
    Language.ENGLISH: {
        "subject": "Tiflotecnia Voices patch — request confirmation #{issue_number}",
        "body": (
            "Hi!\n\n"
            "Here is your patch — the issue has been closed.\n"
            "{link}\n\n"
            "If you don't see the message in your inbox, please check your Spam or Junk folder.\n\n"
            "Best regards,\n"
            "Marek Uram\n\n"
            "---\n"
            "You are receiving this because your email was provided in GitHub Issue #{issue_number}. "
            "If you didn't request this, please ignore."
        ),
    },
    Language.GERMAN: {
        "subject": "Tiflotecnia Voices Patch — Bestätigung der Anfrage #{issue_number}",
        "body": (
            "Hallo!\n\n"
            "Hier ist dein Patch — das Anliegen wurde geschlossen.\n"
            "{link}\n\n"
            "Falls du die Nachricht nicht im Posteingang siehst, prüfe bitte deinen Spam- oder Junk-Ordner.\n\n"
            "Mit freundlichen Grüßen,\n"
            "Marek Uram\n\n"
            "---\n"
            "Du erhältst diese Nachricht, weil deine E-Mail-Adresse in GitHub Issue #{issue_number} angegeben wurde. "
            "Falls du diese Anfrage nicht gestellt hast, ignoriere sie bitte."
        ),
    },
    Language.SPANISH: {
        "subject": "Parche para Tiflotecnia Voices — confirmación de la solicitud #{issue_number}",
        "body": (
            "¡Hola!\n\n"
            "Aquí tienes tu parche — la incidencia ha sido cerrada.\n"
            "{link}\n\n"
            "Si no ves el mensaje en tu bandeja de entrada, revisa la carpeta de Spam o Correo no deseado.\n\n"
            "Un saludo,\n"
            "Marek Uram\n\n"
            "---\n"
            "Recibes este mensaje porque tu dirección de correo se proporcionó en el GitHub Issue #{issue_number}. "
            "Si no fuiste tú quien lo solicitó, por favor ignóralo."
        ),
    },
    Language.FINNISH: {
        "subject": "Tiflotecnia Voices -korjaustiedosto — pyynnön vahvistus #{issue_number}",
        "body": (
            "Hei!\n\n"
            "Tässä on korjaustiedostosi — ilmoitus on suljettu.\n"
            "{link}\n\n"
            "Jos et näe viestiä saapuneissa, tarkista roskaposti- tai mainoskansio.\n\n"
            "Ystävällisin terveisin,\n"
            "Marek Uram\n\n"
            "---\n"
            "Saat tämän viestin, koska sähköpostiosoitteesi annettiin GitHub Issuessa #{issue_number}. "
            "Jos et tehnyt tätä pyyntöä, voit jättää viestin huomiotta."
        ),
    },
    Language.FRENCH: {
        "subject": "Patch Tiflotecnia Voices — confirmation de la demande #{issue_number}",
        "body": (
            "Bonjour !\n\n"
            "Voici votre patch — le ticket a été clôturé.\n"
            "{link}\n\n"
            "Si vous ne voyez pas le message dans votre boîte de réception, vérifiez votre dossier Spam ou Courrier indésirable.\n\n"
            "Cordialement,\n"
            "Marek Uram\n\n"
            "---\n"
            "Vous recevez ce message car votre adresse e-mail a été indiquée dans le GitHub Issue #{issue_number}. "
            "Si vous n'êtes pas à l'origine de cette demande, veuillez l'ignorer."
        ),
    },
    Language.ICELANDIC: {
        "subject": "Tiflotecnia Voices-bót — staðfesting á beiðni #{issue_number}",
        "body": (
            "Halló!\n\n"
            "Hér er bóturinn þinn — málinu hefur verið lokað.\n"
            "{link}\n\n"
            "Ef þú sérð ekki skilaboðin í pósthólfinu þínu, skoðaðu þá ruslpóstsmöppuna.\n\n"
            "Með kveðju,\n"
            "Marek Uram\n\n"
            "---\n"
            "Þú færð þessi skilaboð vegna þess að netfangið þitt var gefið upp í GitHub Issue #{issue_number}. "
            "Ef þetta varst ekki þú, vinsamlegast hunsaðu skilaboðin."
        ),
    },
    Language.ITALIAN: {
        "subject": "Patch Tiflotecnia Voices — conferma della richiesta #{issue_number}",
        "body": (
            "Ciao!\n\n"
            "Ecco la tua patch — la segnalazione è stata chiusa.\n"
            "{link}\n\n"
            "Se non vedi il messaggio nella posta in arrivo, controlla la cartella Spam o Posta indesiderata.\n\n"
            "Cordiali saluti,\n"
            "Marek Uram\n\n"
            "---\n"
            "Ricevi questo messaggio perché il tuo indirizzo email è stato fornito nella GitHub Issue #{issue_number}. "
            "Se non sei stato tu a fare la richiesta, ignora pure il messaggio."
        ),
    },
    Language.RUSSIAN: {
        "subject": "Патч Tiflotecnia Voices — подтверждение запроса #{issue_number}",
        "body": (
            "Здравствуйте!\n\n"
            "Вот ваш патч — обращение закрыто.\n"
            "{link}\n\n"
            "Если вы не видите письмо во входящих, проверьте папку «Спам» или «Нежелательные».\n\n"
            "С уважением,\n"
            "Marek Uram\n\n"
            "---\n"
            "Вы получили это сообщение, потому что ваш email был указан в GitHub Issue #{issue_number}. "
            "Если это были не вы, просто проигнорируйте письмо."
        ),
    },
}

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

def main() -> int:
    if len(sys.argv) < 3:
        sys.stderr.write("Użycie: send_patch.py <issue_body> <issue_number>\n")
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

    tekst_do_analizy = issue_body.replace(recipient_email, "").strip()
    wykryty_jezyk = detector.detect_language_of(tekst_do_analizy)

    if wykryty_jezyk not in TEMPLATES:
        sys.stderr.write(
            f"[!] Język niewykryty lub poza listą wspieranych ({wykryty_jezyk}) "
            "— fallback na ENGLISH.\n"
        )
        wykryty_jezyk = Language.ENGLISH

    print(f"Wykryto język zgłoszenia: {wykryty_jezyk.name}.")

    szablon = TEMPLATES[wykryty_jezyk]
    temat = szablon["subject"].format(issue_number=issue_number)
    tresc = szablon["body"].format(link=PATCH_LINK, issue_number=issue_number)

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
    msg.set_content(tresc)

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
