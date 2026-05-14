import os
import random
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

PERSONAS = ["Lumi", "Vieno", "Katla"]

FOOTERS = {
    Language.POLISH: (
        "Otrzymujesz tę wiadomość, bo Twój adres email został podany "
        "w GitHub Issue #{issue_number}. Jeśli to nie Ty zgłaszałeś — zignoruj."
    ),
    Language.ENGLISH: (
        "You are receiving this because your email was provided "
        "in GitHub Issue #{issue_number}. If you didn't request this, please ignore."
    ),
    Language.GERMAN: (
        "Du erhältst diese Nachricht, weil deine E-Mail-Adresse "
        "in GitHub Issue #{issue_number} angegeben wurde. "
        "Falls du diese Anfrage nicht gestellt hast, ignoriere sie bitte."
    ),
    Language.SPANISH: (
        "Recibes este mensaje porque tu dirección de correo se proporcionó "
        "en el GitHub Issue #{issue_number}. "
        "Si no fuiste tú quien lo solicitó, por favor ignóralo."
    ),
    Language.FINNISH: (
        "Saat tämän viestin, koska sähköpostiosoitteesi annettiin "
        "GitHub Issuessa #{issue_number}. "
        "Jos et tehnyt tätä pyyntöä, voit jättää viestin huomiotta."
    ),
    Language.FRENCH: (
        "Vous recevez ce message car votre adresse e-mail a été indiquée "
        "dans le GitHub Issue #{issue_number}. "
        "Si vous n'êtes pas à l'origine de cette demande, veuillez l'ignorer."
    ),
    Language.ICELANDIC: (
        "Þú færð þessi skilaboð vegna þess að netfangið þitt var gefið upp "
        "í GitHub Issue #{issue_number}. "
        "Ef þetta varst ekki þú, vinsamlegast hunsaðu skilaboðin."
    ),
    Language.ITALIAN: (
        "Ricevi questo messaggio perché il tuo indirizzo email è stato fornito "
        "nella GitHub Issue #{issue_number}. "
        "Se non sei stato tu a fare la richiesta, ignora pure il messaggio."
    ),
    Language.RUSSIAN: (
        "Вы получили это сообщение, потому что ваш email был указан "
        "в GitHub Issue #{issue_number}. "
        "Если это были не вы, просто проигнорируйте письмо."
    ),
}

TEMPLATES = {
    Language.POLISH: {
        "Lumi": {
            "subject": "Tiflotecnia Voices patch — zimowa przesyłka #{issue_number}",
            "body": (
                "Cześć!\n\n"
                "Przedarłam się przez zaspy, żeby to dostarczyć! Twój patch jest gotowy, "
                "a zgłoszenie zamknęłam, żeby nie wiało chłodem.\n"
                "{link}\n\n"
                "Jeśli śnieżyca ukryła wiadomość w skrzynce, sprawdź folder Spam "
                "lub Wiadomości-śmieci.\n\n"
                "Niech mróz będzie z Tobą,\n"
                "Lumi"
            ),
        },
        "Vieno": {
            "subject": "Tiflotecnia Voices patch — wizja dla zgłoszenia #{issue_number}",
            "body": (
                "Witaj.\n\n"
                "Duchy Północy przyniosły wieści o Twoim zgłoszeniu. Rytuał dobiegł końca, "
                "a patch zmaterializował się tutaj:\n"
                "{link}\n\n"
                "Jeśli wizja nie dotarła do Twojej skrzynki, przeszukaj mgłę "
                "w folderze Spam.\n\n"
                "Słuchaj wiatru,\n"
                "Vieno"
            ),
        },
        "Katla": {
            "subject": "Tiflotecnia Voices patch — gorące zgłoszenie #{issue_number}",
            "body": (
                "Hej!\n\n"
                "Wykute w wulkanicznym ogniu i wciąż gorące! Przesyłam patcha "
                "i zamykam zgłoszenie.\n"
                "{link}\n\n"
                "Jeśli dym zasłonił Ci widok na skrzynkę, sprawdź koniecznie folder Spam.\n\n"
                "Z wulkanicznym pozdrowieniem,\n"
                "Katla"
            ),
        },
    },
    Language.ENGLISH: {
        "Lumi": {
            "subject": "Tiflotecnia Voices patch — winter delivery #{issue_number}",
            "body": (
                "Hi!\n\n"
                "I waded through the snowdrifts to deliver this! Your patch is ready, "
                "and I closed the issue to keep the cold out.\n"
                "{link}\n\n"
                "If a blizzard hid this message, please check your Spam or Junk folder.\n\n"
                "Stay frosty,\n"
                "Lumi"
            ),
        },
        "Vieno": {
            "subject": "Tiflotecnia Voices patch — a vision for request #{issue_number}",
            "body": (
                "Greetings.\n\n"
                "The Northern Spirits have brought word of your request. The ritual is "
                "complete, and the patch has manifested here:\n"
                "{link}\n\n"
                "If the vision did not reach your inbox, search the mist in your "
                "Spam folder.\n\n"
                "Listen to the wind,\n"
                "Vieno"
            ),
        },
        "Katla": {
            "subject": "Tiflotecnia Voices patch — hot off the forge #{issue_number}",
            "body": (
                "Hey!\n\n"
                "Forged in volcanic fire and still glowing! Sending you the patch "
                "and closing the issue.\n"
                "{link}\n\n"
                "If smoke obscured your view of the inbox, be sure to check your "
                "Spam folder.\n\n"
                "With volcanic greetings,\n"
                "Katla"
            ),
        },
    },
    Language.GERMAN: {
        "Lumi": {
            "subject": "Tiflotecnia Voices Patch — Winter-Lieferung #{issue_number}",
            "body": (
                "Hallo!\n\n"
                "Ich habe mich durch die Schneewehen gekämpft, um das zu liefern! "
                "Dein Patch ist bereit und ich habe das Anliegen geschlossen, "
                "damit es nicht kalt hereinzieht.\n"
                "{link}\n\n"
                "Falls ein Schneesturm die Nachricht versteckt hat, prüfe bitte "
                "deinen Spam- oder Junk-Ordner.\n\n"
                "Bleib frostig,\n"
                "Lumi"
            ),
        },
        "Vieno": {
            "subject": "Tiflotecnia Voices Patch — eine Vision für Anfrage #{issue_number}",
            "body": (
                "Sei gegrüßt.\n\n"
                "Die Geister des Nordens haben Kunde von deinem Anliegen gebracht. "
                "Das Ritual ist vollendet und der Patch hat sich hier manifestiert:\n"
                "{link}\n\n"
                "Wenn die Vision deinen Posteingang nicht erreicht hat, durchsuche "
                "den Nebel im Spam-Ordner.\n\n"
                "Lausche dem Wind,\n"
                "Vieno"
            ),
        },
        "Katla": {
            "subject": "Tiflotecnia Voices Patch — heiß aus der Schmiede #{issue_number}",
            "body": (
                "Hey!\n\n"
                "Im vulkanischen Feuer geschmiedet und noch glühend! Ich schicke dir "
                "den Patch und schließe das Anliegen.\n"
                "{link}\n\n"
                "Falls Rauch deinen Blick auf den Posteingang versperrt hat, prüfe "
                "unbedingt den Spam-Ordner.\n\n"
                "Mit vulkanischen Grüßen,\n"
                "Katla"
            ),
        },
    },
    Language.SPANISH: {
        "Lumi": {
            "subject": "Parche Tiflotecnia Voices — entrega invernal #{issue_number}",
            "body": (
                "¡Hola!\n\n"
                "¡He atravesado los ventisqueros para entregártelo! Tu parche está listo "
                "y he cerrado la incidencia para que no entre el frío.\n"
                "{link}\n\n"
                "Si una ventisca ha escondido el mensaje en tu bandeja, revisa la "
                "carpeta de Spam o Correo no deseado.\n\n"
                "Que la escarcha te acompañe,\n"
                "Lumi"
            ),
        },
        "Vieno": {
            "subject": "Parche Tiflotecnia Voices — una visión para la solicitud #{issue_number}",
            "body": (
                "Saludos.\n\n"
                "Los Espíritus del Norte han traído noticias de tu solicitud. "
                "El ritual ha concluido y el parche se ha manifestado aquí:\n"
                "{link}\n\n"
                "Si la visión no llegó a tu bandeja, busca entre la niebla en la "
                "carpeta de Spam.\n\n"
                "Escucha al viento,\n"
                "Vieno"
            ),
        },
        "Katla": {
            "subject": "Parche Tiflotecnia Voices — recién salido de la fragua #{issue_number}",
            "body": (
                "¡Hey!\n\n"
                "¡Forjado en fuego volcánico y todavía al rojo vivo! Te envío el parche "
                "y cierro la incidencia.\n"
                "{link}\n\n"
                "Si el humo te ha tapado la bandeja, asegúrate de revisar la carpeta "
                "de Spam.\n\n"
                "Saludos volcánicos,\n"
                "Katla"
            ),
        },
    },
    Language.FINNISH: {
        "Lumi": {
            "subject": "Tiflotecnia Voices -korjaustiedosto — talvitoimitus #{issue_number}",
            "body": (
                "Hei!\n\n"
                "Tallasin tieni nietosten läpi tuodakseni tämän! Korjaustiedostosi "
                "on valmis ja suljin ilmoituksen, jottei kylmä pääse sisään.\n"
                "{link}\n\n"
                "Jos lumimyrsky kätki viestin postilaatikkoosi, tarkista roskaposti- "
                "tai mainoskansio.\n\n"
                "Pysy kylmänä,\n"
                "Lumi"
            ),
        },
        "Vieno": {
            "subject": "Tiflotecnia Voices -korjaustiedosto — näky pyyntöön #{issue_number}",
            "body": (
                "Tervehdys.\n\n"
                "Pohjolan henget toivat sanan pyynnöstäsi. Riitti on päättynyt ja "
                "korjaustiedosto on ilmestynyt tänne:\n"
                "{link}\n\n"
                "Jos näky ei saavuttanut postilaatikkoasi, etsi sumusta "
                "roskapostikansiosta.\n\n"
                "Kuuntele tuulta,\n"
                "Vieno"
            ),
        },
        "Katla": {
            "subject": "Tiflotecnia Voices -korjaustiedosto — pajasta kuumana #{issue_number}",
            "body": (
                "Hei!\n\n"
                "Taottu tulivuoren tulessa ja yhä hehkuva! Lähetän korjaustiedoston "
                "ja suljen ilmoituksen.\n"
                "{link}\n\n"
                "Jos savu peitti näkymäsi postilaatikkoon, tarkista ehdottomasti "
                "roskapostikansio.\n\n"
                "Tulivuorimaisin terveisin,\n"
                "Katla"
            ),
        },
    },
    Language.FRENCH: {
        "Lumi": {
            "subject": "Patch Tiflotecnia Voices — livraison hivernale #{issue_number}",
            "body": (
                "Bonjour !\n\n"
                "Je me suis frayée un chemin à travers les congères pour vous livrer "
                "ceci ! Votre patch est prêt et j'ai clôturé le ticket pour que le "
                "froid ne s'engouffre pas.\n"
                "{link}\n\n"
                "Si une tempête de neige a caché le message dans votre boîte, vérifiez "
                "le dossier Spam ou Courrier indésirable.\n\n"
                "Glaciales salutations,\n"
                "Lumi"
            ),
        },
        "Vieno": {
            "subject": "Patch Tiflotecnia Voices — une vision pour la demande #{issue_number}",
            "body": (
                "Salutations.\n\n"
                "Les Esprits du Nord ont apporté des nouvelles de votre demande. "
                "Le rituel s'est achevé et le patch s'est matérialisé ici :\n"
                "{link}\n\n"
                "Si la vision n'a pas atteint votre boîte, fouillez la brume dans "
                "le dossier Spam.\n\n"
                "Écoute le vent,\n"
                "Vieno"
            ),
        },
        "Katla": {
            "subject": "Patch Tiflotecnia Voices — sorti tout chaud de la forge #{issue_number}",
            "body": (
                "Hé !\n\n"
                "Forgé dans le feu volcanique et encore brûlant ! Je vous envoie le patch "
                "et je clôture le ticket.\n"
                "{link}\n\n"
                "Si la fumée vous a masqué la vue de votre boîte, pensez à vérifier "
                "le dossier Spam.\n\n"
                "Salutations volcaniques,\n"
                "Katla"
            ),
        },
    },
    Language.ICELANDIC: {
        "Lumi": {
            "subject": "Tiflotecnia Voices-bót — vetrarsending #{issue_number}",
            "body": (
                "Halló!\n\n"
                "Ég braust í gegnum snjóskaflana til að færa þér þetta! Bóturinn þinn "
                "er tilbúinn og ég lokaði málinu svo kuldinn læddist ekki inn.\n"
                "{link}\n\n"
                "Ef snjóstormur faldi skilaboðin í pósthólfinu þínu, skoðaðu þá "
                "ruslpóstsmöppuna.\n\n"
                "Frostkveðjur,\n"
                "Lumi"
            ),
        },
        "Vieno": {
            "subject": "Tiflotecnia Voices-bót — sýn vegna beiðni #{issue_number}",
            "body": (
                "Heilsa.\n\n"
                "Andar Norðursins hafa fært tíðindi af beiðni þinni. Athöfninni er lokið "
                "og bóturinn hefur birst hér:\n"
                "{link}\n\n"
                "Ef sýnin barst ekki í pósthólfið þitt, leitaðu í þokunni í "
                "ruslpóstsmöppunni.\n\n"
                "Hlustaðu á vindinn,\n"
                "Vieno"
            ),
        },
        "Katla": {
            "subject": "Tiflotecnia Voices-bót — beint úr smiðjunni #{issue_number}",
            "body": (
                "Hæ!\n\n"
                "Smíðaður í eldfjallaeldi og enn glóandi! Ég sendi þér bótinn og "
                "loka málinu.\n"
                "{link}\n\n"
                "Ef reykur skyggði á yfirsýn þína yfir pósthólfið, mundu að gá í "
                "ruslpóstsmöppuna.\n\n"
                "Eldfjallakveðjur,\n"
                "Katla"
            ),
        },
    },
    Language.ITALIAN: {
        "Lumi": {
            "subject": "Patch Tiflotecnia Voices — consegna invernale #{issue_number}",
            "body": (
                "Ciao!\n\n"
                "Mi sono fatta strada tra i cumuli di neve per consegnartela! "
                "La tua patch è pronta e ho chiuso la segnalazione perché non entri "
                "il freddo.\n"
                "{link}\n\n"
                "Se una bufera ha nascosto il messaggio nella posta in arrivo, "
                "controlla la cartella Spam o Posta indesiderata.\n\n"
                "Saluti gelidi,\n"
                "Lumi"
            ),
        },
        "Vieno": {
            "subject": "Patch Tiflotecnia Voices — una visione per la richiesta #{issue_number}",
            "body": (
                "Salve.\n\n"
                "Gli Spiriti del Nord hanno portato notizia della tua richiesta. "
                "Il rito si è concluso e la patch si è manifestata qui:\n"
                "{link}\n\n"
                "Se la visione non è arrivata nella tua posta in arrivo, cerca nella "
                "nebbia della cartella Spam.\n\n"
                "Ascolta il vento,\n"
                "Vieno"
            ),
        },
        "Katla": {
            "subject": "Patch Tiflotecnia Voices — appena uscita dalla fucina #{issue_number}",
            "body": (
                "Ehi!\n\n"
                "Forgiata nel fuoco vulcanico e ancora rovente! Ti mando la patch "
                "e chiudo la segnalazione.\n"
                "{link}\n\n"
                "Se il fumo ti ha coperto la vista della posta in arrivo, controlla "
                "assolutamente la cartella Spam.\n\n"
                "Saluti vulcanici,\n"
                "Katla"
            ),
        },
    },
    Language.RUSSIAN: {
        "Lumi": {
            "subject": "Патч Tiflotecnia Voices — зимняя доставка #{issue_number}",
            "body": (
                "Привет!\n\n"
                "Я пробралась сквозь сугробы, чтобы доставить это! Твой патч готов, "
                "а обращение я закрыла, чтобы не задувало холодом.\n"
                "{link}\n\n"
                "Если метель спрятала письмо в почтовом ящике, загляни в папку "
                "«Спам» или «Нежелательные».\n\n"
                "Морозного привета,\n"
                "Lumi"
            ),
        },
        "Vieno": {
            "subject": "Патч Tiflotecnia Voices — видение по запросу #{issue_number}",
            "body": (
                "Приветствую.\n\n"
                "Духи Севера принесли весть о твоём обращении. Обряд завершён, "
                "и патч проявился здесь:\n"
                "{link}\n\n"
                "Если видение не достигло твоего ящика, поищи в тумане папки «Спам».\n\n"
                "Слушай ветер,\n"
                "Vieno"
            ),
        },
        "Katla": {
            "subject": "Патч Tiflotecnia Voices — прямо из кузницы #{issue_number}",
            "body": (
                "Привет!\n\n"
                "Выкован в вулканическом огне и всё ещё раскалён! Отправляю патч "
                "и закрываю обращение.\n"
                "{link}\n\n"
                "Если дым заслонил тебе вид на ящик, обязательно загляни в папку «Спам».\n\n"
                "С вулканическим приветом,\n"
                "Katla"
            ),
        },
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
        dodaj_komentarz_do_issue(issue_number, KOMENTARZ_BRAK_EMAILA)
        return 1

    recipient_email = email_match.group(0)
    tekst_do_analizy = issue_body.replace(recipient_email, "").strip()
    wykryty_jezyk = detector.detect_language_of(tekst_do_analizy)

    if wykryty_jezyk not in TEMPLATES:
        wykryty_jezyk = Language.ENGLISH

    wylosowana_postac = random.choice(PERSONAS)
    print(
        f"Wykryto język: {wykryty_jezyk.name}. "
        f"Dzisiaj obsługuje: {wylosowana_postac}."
    )

    szablon = TEMPLATES[wykryty_jezyk][wylosowana_postac]
    stopka = FOOTERS[wykryty_jezyk]

    temat = szablon["subject"].format(issue_number=issue_number)
    tresc_glowna = szablon["body"].format(link=PATCH_LINK)
    stopka_sformatowana = stopka.format(issue_number=issue_number)
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
        return 0
    except Exception as exc:
        sys.stderr.write(f"[!] Błąd wysyłki maila: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
