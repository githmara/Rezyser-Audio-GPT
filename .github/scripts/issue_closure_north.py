"""
issue_closure_north.py — etap „Północ" obiegu „Z Południa na Północ".

Po nadaniu etykiety ``fixed-in-release`` przez maintainera, pałeczkę przejmują
bohaterki z Północy:

  * Lumi  — śnieżnie, mroźnie, z humorem,
  * Vieno — szamańsko, mgliście, w półszeptach,
  * Katla — wulkanicznie, gorąco, z hukiem.

Skrypt:
  1. odczytuje tytuł + treść issue z argumentów,
  2. wykrywa język oryginalnej treści (lingua-language-detector; fallback EN),
  3. losuje jedną z trzech bohaterek,
  4. formatuje komentarz w wykrytym języku,
  5. dodaje komentarz przez ``gh issue comment`` i zamyka przez ``gh issue close``.

Wywołanie:
    python .github/scripts/issue_closure_north.py "$ISSUE_BODY" "$ISSUE_NUMBER"

Env: GH_TOKEN (gh CLI), GITHUB_REPOSITORY, GITHUB_SERVER_URL (do linku Releases).
"""

from __future__ import annotations

import os
import random
import subprocess
import sys

from lingua import Language, LanguageDetectorBuilder


LANGUAGES = [
    Language.GERMAN, Language.ENGLISH, Language.SPANISH,
    Language.FINNISH, Language.FRENCH, Language.ICELANDIC,
    Language.ITALIAN, Language.POLISH, Language.RUSSIAN,
]
detector = LanguageDetectorBuilder.from_languages(*LANGUAGES).build()

PERSONAS = ["Lumi", "Vieno", "Katla"]


# Komentarze per (język, persona). `{link}` -> link do najnowszego release'u.
# Diakrytyki KRYTYCZNE: czytniki ekranu (NVDA) potrzebują poprawnej ortografii,
# żeby fonetyka brzmiała naturalnie. Wzór zaczerpnięty z send_patch.py.
TEMPLATES: dict[Language, dict[str, str]] = {
    Language.POLISH: {
        "Lumi": (
            "Cześć!\n\n"
            "Śnieg już osiadł, a poprawka dotarła! Wszystko, o co prosiłaś/eś, "
            "właśnie wylądowało w najnowszym wydaniu Tiflotecnia Voices.\n\n"
            "Pobierz aktualizację tutaj: {link}\n\n"
            "Zamykam zgłoszenie, żeby nie wiało chłodem. Mroźnych pozdrowień!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Witaj.\n\n"
            "Wiatry Północy przyniosły wieść, że Twoja prośba znalazła swoje "
            "miejsce w nowym wydaniu. Wizja się zmaterializowała.\n\n"
            "Najnowsze wydanie czeka tutaj: {link}\n\n"
            "Zamykam ten krąg — sprawa znalazła swój kres.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hej!\n\n"
            "Wykute w wulkanicznym ogniu, jeszcze parzy! Twoja sprawa została "
            "rozwiązana w najnowszym wydaniu Tiflotecnia Voices.\n\n"
            "Łapiesz tutaj: {link}\n\n"
            "Zamykam zgłoszenie — z wulkanicznym pozdrowieniem!\n"
            "— Katla"
        ),
    },
    Language.ENGLISH: {
        "Lumi": (
            "Hi!\n\n"
            "The snow has settled and the fix has arrived! Everything you asked "
            "for just landed in the latest Tiflotecnia Voices release.\n\n"
            "Grab the update here: {link}\n\n"
            "Closing the issue to keep the cold out. Stay frosty!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Greetings.\n\n"
            "The Northern winds carried word that your request has found its "
            "place in the new release. The vision has manifested.\n\n"
            "The latest release awaits here: {link}\n\n"
            "Closing this circle — the matter has reached its end.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hey!\n\n"
            "Forged in volcanic fire and still glowing! Your request has been "
            "resolved in the latest Tiflotecnia Voices release.\n\n"
            "Catch it here: {link}\n\n"
            "Closing the issue — volcanic greetings!\n"
            "— Katla"
        ),
    },
    Language.GERMAN: {
        "Lumi": (
            "Hallo!\n\n"
            "Der Schnee hat sich gelegt und der Fix ist da! Alles, worum du "
            "gebeten hast, ist gerade in der neuesten Tiflotecnia-Voices-"
            "Veröffentlichung gelandet.\n\n"
            "Hol dir das Update hier: {link}\n\n"
            "Ich schließe das Anliegen, damit es nicht kalt hereinzieht. "
            "Bleib frostig!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Sei gegrüßt.\n\n"
            "Die Winde des Nordens haben Kunde gebracht, dass dein Anliegen "
            "seinen Platz in der neuen Veröffentlichung gefunden hat. Die "
            "Vision ist manifest geworden.\n\n"
            "Die neueste Veröffentlichung erwartet dich hier: {link}\n\n"
            "Ich schließe diesen Kreis — die Angelegenheit hat ihr Ende erreicht.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hey!\n\n"
            "Im vulkanischen Feuer geschmiedet und noch glühend! Dein Anliegen "
            "wurde in der neuesten Tiflotecnia-Voices-Veröffentlichung gelöst.\n\n"
            "Greif zu hier: {link}\n\n"
            "Ich schließe das Anliegen — vulkanische Grüße!\n"
            "— Katla"
        ),
    },
    Language.SPANISH: {
        "Lumi": (
            "¡Hola!\n\n"
            "¡La nieve se ha asentado y la corrección ha llegado! Todo lo que "
            "pediste acaba de aterrizar en la última publicación de "
            "Tiflotecnia Voices.\n\n"
            "Consigue la actualización aquí: {link}\n\n"
            "Cierro la incidencia para que no entre el frío. ¡Que la escarcha "
            "te acompañe!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Saludos.\n\n"
            "Los vientos del Norte han traído noticia de que tu solicitud ha "
            "encontrado su lugar en la nueva versión. La visión se ha "
            "manifestado.\n\n"
            "La última versión te espera aquí: {link}\n\n"
            "Cierro este círculo — el asunto ha llegado a su fin.\n"
            "— Vieno"
        ),
        "Katla": (
            "¡Hey!\n\n"
            "¡Forjada en fuego volcánico y todavía al rojo vivo! Tu solicitud "
            "ha sido resuelta en la última versión de Tiflotecnia Voices.\n\n"
            "Recógela aquí: {link}\n\n"
            "Cierro la incidencia — ¡saludos volcánicos!\n"
            "— Katla"
        ),
    },
    Language.FINNISH: {
        "Lumi": (
            "Hei!\n\n"
            "Lumi on laskeutunut ja korjaus on saapunut! Kaikki mitä pyysit "
            "löytyy nyt uusimmasta Tiflotecnia Voices -julkaisusta.\n\n"
            "Nappaa päivitys täältä: {link}\n\n"
            "Suljen ilmoituksen, jottei kylmä pääse sisään. Pysy kylmänä!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Tervehdys.\n\n"
            "Pohjolan tuulet ovat tuoneet sanan, että pyyntösi on löytänyt "
            "paikkansa uudessa julkaisussa. Näky on toteutunut.\n\n"
            "Uusin julkaisu odottaa täällä: {link}\n\n"
            "Suljen tämän piirin — asia on saapunut päätökseen.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hei!\n\n"
            "Taottu tulivuoren tulessa ja yhä hehkuva! Pyyntösi on "
            "ratkaistu uusimmassa Tiflotecnia Voices -julkaisussa.\n\n"
            "Tartu siihen täällä: {link}\n\n"
            "Suljen ilmoituksen — tulivuoriterveisin!\n"
            "— Katla"
        ),
    },
    Language.FRENCH: {
        "Lumi": (
            "Bonjour !\n\n"
            "La neige s'est posée et le correctif est arrivé ! Tout ce que vous "
            "avez demandé vient d'atterrir dans la dernière version de "
            "Tiflotecnia Voices.\n\n"
            "Récupérez la mise à jour ici : {link}\n\n"
            "Je clôture le ticket pour que le froid ne s'engouffre pas. "
            "Glaciales salutations !\n"
            "— Lumi"
        ),
        "Vieno": (
            "Salutations.\n\n"
            "Les vents du Nord ont porté la nouvelle : votre demande a trouvé "
            "sa place dans la nouvelle version. La vision s'est manifestée.\n\n"
            "La dernière version vous attend ici : {link}\n\n"
            "Je referme ce cercle — l'affaire a atteint sa fin.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hé !\n\n"
            "Forgée dans le feu volcanique et encore brûlante ! Votre demande "
            "a été résolue dans la dernière version de Tiflotecnia Voices.\n\n"
            "Attrapez-la ici : {link}\n\n"
            "Je clôture le ticket — salutations volcaniques !\n"
            "— Katla"
        ),
    },
    Language.ICELANDIC: {
        "Lumi": (
            "Halló!\n\n"
            "Snjórinn hefur sest og lagfæringin er komin! Allt sem þú baðst "
            "um er nú komið í nýjustu útgáfu Tiflotecnia Voices.\n\n"
            "Næðu uppfærslunni hér: {link}\n\n"
            "Ég loka málinu svo kuldinn læddist ekki inn. Frostkveðjur!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Heilsa.\n\n"
            "Vindar Norðursins hafa borið þau tíðindi að beiðni þín hafi "
            "fundið sinn stað í nýju útgáfunni. Sýnin hefur birst.\n\n"
            "Nýjasta útgáfan bíður hér: {link}\n\n"
            "Ég loka þessum hring — málið hefur náð sínum enda.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hæ!\n\n"
            "Smíðað í eldfjallaeldi og enn glóandi! Beiðni þín hefur verið "
            "leyst í nýjustu útgáfu Tiflotecnia Voices.\n\n"
            "Gríptu hana hér: {link}\n\n"
            "Ég loka málinu — eldfjallakveðjur!\n"
            "— Katla"
        ),
    },
    Language.ITALIAN: {
        "Lumi": (
            "Ciao!\n\n"
            "La neve si è posata e la correzione è arrivata! Tutto ciò che hai "
            "chiesto è appena atterrato nell'ultima versione di Tiflotecnia "
            "Voices.\n\n"
            "Prendi l'aggiornamento qui: {link}\n\n"
            "Chiudo la segnalazione perché non entri il freddo. Saluti gelidi!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Salve.\n\n"
            "I venti del Nord hanno portato notizia che la tua richiesta ha "
            "trovato il suo posto nella nuova versione. La visione si è "
            "manifestata.\n\n"
            "L'ultima versione ti aspetta qui: {link}\n\n"
            "Chiudo questo cerchio — la questione ha raggiunto la sua fine.\n"
            "— Vieno"
        ),
        "Katla": (
            "Ehi!\n\n"
            "Forgiata nel fuoco vulcanico e ancora rovente! La tua richiesta "
            "è stata risolta nell'ultima versione di Tiflotecnia Voices.\n\n"
            "Acchiappala qui: {link}\n\n"
            "Chiudo la segnalazione — saluti vulcanici!\n"
            "— Katla"
        ),
    },
    Language.RUSSIAN: {
        "Lumi": (
            "Привет!\n\n"
            "Снег улёгся, и исправление прибыло! Всё, о чём ты просил(а), "
            "только что появилось в новейшем выпуске Tiflotecnia Voices.\n\n"
            "Забирай обновление здесь: {link}\n\n"
            "Закрываю обращение, чтобы не задувало холодом. Морозного "
            "привета!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Приветствую.\n\n"
            "Ветра Севера принесли весть, что твоя просьба нашла своё место "
            "в новом выпуске. Видение проявилось.\n\n"
            "Новейший выпуск ждёт тебя здесь: {link}\n\n"
            "Закрываю этот круг — дело дошло до своего конца.\n"
            "— Vieno"
        ),
        "Katla": (
            "Привет!\n\n"
            "Выкована в вулканическом огне и всё ещё раскалена! Твоя "
            "просьба решена в новейшем выпуске Tiflotecnia Voices.\n\n"
            "Лови здесь: {link}\n\n"
            "Закрываю обращение — с вулканическим приветом!\n"
            "— Katla"
        ),
    },
}


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
            f"[!] gh zfailowało ({' '.join(cmd[:3])}): "
            f"{exc.stderr.strip() or exc}\n"
        )
        return False
    except FileNotFoundError:
        sys.stderr.write("[!] `gh` CLI nie znalezione w PATH.\n")
        return False


def main() -> int:
    if len(sys.argv) < 3:
        sys.stderr.write(
            "Użycie: issue_closure_north.py <issue_body> <issue_number>\n"
        )
        return 2

    issue_body = sys.argv[1]
    issue_number = sys.argv[2]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        sys.stderr.write("[!] Brak GITHUB_REPOSITORY w env.\n")
        return 1

    wykryty = detector.detect_language_of(issue_body) if issue_body.strip() else None
    if wykryty not in TEMPLATES:
        wykryty = Language.ENGLISH

    persona = random.choice(PERSONAS)
    print(f"Wykryto język: {wykryty.name}. Dyżur: {persona}.")

    szablon = TEMPLATES[wykryty][persona]
    link = _zbuduj_link_release()
    tresc = szablon.format(link=link)

    if not _gh(["gh", "issue", "comment", issue_number, "--repo", repo,
                "--body", tresc]):
        return 1
    if not _gh(["gh", "issue", "close", issue_number, "--repo", repo]):
        return 1

    print(f"Issue #{issue_number} skomentowane i zamknięte przez {persona}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
