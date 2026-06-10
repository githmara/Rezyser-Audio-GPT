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

Templatki personalne ZOSTAJĄ w tym module jako single source:
  * ``TEMPLATES``           — bug-fix flow (z linkiem do Release), używane tutaj,
  * ``TEMPLATES_ANSWERED``  — answer flow, importowane przez ``odpowiedz_lokalnie.py``,
  * ``PERSONAL_NOTE_INTRO`` — dolepek osobistej notki, też dla skryptu lokalnego.

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
            "właśnie wylądowało w najnowszym wydaniu Reżysera Audio AI.\n\n"
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
            "rozwiązana w najnowszym wydaniu Reżysera Audio AI.\n\n"
            "Łapiesz tutaj: {link}\n\n"
            "Zamykam zgłoszenie — z wulkanicznym pozdrowieniem!\n"
            "— Katla"
        ),
    },
    Language.ENGLISH: {
        "Lumi": (
            "Hi!\n\n"
            "The snow has settled and the fix has arrived! Everything you asked "
            "for just landed in the latest Audio AI Director release.\n\n"
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
            "resolved in the latest Audio AI Director release.\n\n"
            "Catch it here: {link}\n\n"
            "Closing the issue — volcanic greetings!\n"
            "— Katla"
        ),
    },
    Language.GERMAN: {
        "Lumi": (
            "Hallo!\n\n"
            "Der Schnee hat sich gelegt und der Fix ist da! Alles, worum du "
            "gebeten hast, ist gerade in der neuesten Audio-AI-Regisseur-"
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
            "wurde in der neuesten Audio-AI-Regisseur-Veröffentlichung gelöst.\n\n"
            "Greif zu hier: {link}\n\n"
            "Ich schließe das Anliegen — vulkanische Grüße!\n"
            "— Katla"
        ),
    },
    Language.SPANISH: {
        "Lumi": (
            "¡Hola!\n\n"
            "¡La nieve se ha asentado y la corrección ha llegado! Todo lo que "
            "pediste acaba de aterrizar en la última publicación del "
            "Director de Audio AI.\n\n"
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
            "ha sido resuelta en la última versión del Director de Audio AI.\n\n"
            "Recógela aquí: {link}\n\n"
            "Cierro la incidencia — ¡saludos volcánicos!\n"
            "— Katla"
        ),
    },
    Language.FINNISH: {
        "Lumi": (
            "Hei!\n\n"
            "Lumi on laskeutunut ja korjaus on saapunut! Kaikki mitä pyysit "
            "löytyy nyt uusimmasta Audio AI -ohjaajan julkaisusta.\n\n"
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
            "ratkaistu uusimmassa Audio AI -ohjaajan julkaisussa.\n\n"
            "Tartu siihen täällä: {link}\n\n"
            "Suljen ilmoituksen — tulivuoriterveisin!\n"
            "— Katla"
        ),
    },
    Language.FRENCH: {
        "Lumi": (
            "Bonjour !\n\n"
            "La neige s'est posée et le correctif est arrivé ! Tout ce que vous "
            "avez demandé vient d'atterrir dans la dernière version du "
            "Réalisateur Audio AI.\n\n"
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
            "a été résolue dans la dernière version du Réalisateur Audio AI.\n\n"
            "Attrapez-la ici : {link}\n\n"
            "Je clôture le ticket — salutations volcaniques !\n"
            "— Katla"
        ),
    },
    Language.ICELANDIC: {
        "Lumi": (
            "Halló!\n\n"
            "Snjórinn hefur sest og lagfæringin er komin! Allt sem þú baðst "
            "um er nú komið í nýjustu útgáfu Audio AI leikstjórans.\n\n"
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
            "leyst í nýjustu útgáfu Audio AI leikstjórans.\n\n"
            "Gríptu hana hér: {link}\n\n"
            "Ég loka málinu — eldfjallakveðjur!\n"
            "— Katla"
        ),
    },
    Language.ITALIAN: {
        "Lumi": (
            "Ciao!\n\n"
            "La neve si è posata e la correzione è arrivata! Tutto ciò che hai "
            "chiesto è appena atterrato nell'ultima versione del Regista "
            "Audio AI.\n\n"
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
            "è stata risolta nell'ultima versione del Regista Audio AI.\n\n"
            "Acchiappala qui: {link}\n\n"
            "Chiudo la segnalazione — saluti vulcanici!\n"
            "— Katla"
        ),
    },
    Language.RUSSIAN: {
        "Lumi": (
            "Привет!\n\n"
            "Снег улёгся, и исправление прибыло! Всё, о чём ты просил(а), "
            "только что появилось в новейшем выпуске Audio AI Director.\n\n"
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
            "просьба решена в новейшем выпуске Audio AI Director.\n\n"
            "Лови здесь: {link}\n\n"
            "Закрываю обращение — с вулканическим приветом!\n"
            "— Katla"
        ),
    },
}


# Od v15.2.6: szablony dla flow `answered` (pytanie/help wanted dostało odpowiedź
# od Centrum, NIE poprzez patch w release'ie). Bez `{link}` do release — w tym
# kontekście link byłby szumem informacyjnym (user nie potrzebuje aktualizować
# aplikacji, tylko chce dostać odpowiedź na pytanie). Zamiast tego placeholder
# `{maintainer_answer}` jest wypełniany treścią ostatniego komentarza na issue
# (konwencja workflow: maintainer komentuje, potem nadaje etykietę `answered`,
# bot wyciąga ostatni komentarz przez `gh issue view --json comments`).
#
# Styl personalności taki sam jak w TEMPLATES wyżej (Lumi mroźno, Vieno
# szamańsko, Katla wulkanicznie) — żeby user-facing głos Northern operations
# pozostał spójny niezależnie od typu zgłoszenia (bug-fix vs answer-passing).
TEMPLATES_ANSWERED: dict[Language, dict[str, str]] = {
    Language.POLISH: {
        "Lumi": (
            "Cześć!\n\n"
            "Z Centrum dotarła do Północy wieść z odpowiedzią dla Ciebie. "
            "Podaję ją dalej dokładnie tak, jak została wystosowana:\n\n"
            "{maintainer_answer}\n\n"
            "Zamykam zgłoszenie — śnieg już osiadł na tej sprawie. "
            "Mroźnych pozdrowień!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Witaj.\n\n"
            "Wiatry Północy przyniosły z Centrum słowa odpowiedzi. "
            "Przekazuję je w nienaruszonej formie:\n\n"
            "{maintainer_answer}\n\n"
            "Zamykam ten krąg — pytanie znalazło swój kres.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hej!\n\n"
            "Gorące słowo z Centrum przybyło na Północ — przekazuję Ci wprost:\n\n"
            "{maintainer_answer}\n\n"
            "Zamykam zgłoszenie — z wulkanicznym pozdrowieniem!\n"
            "— Katla"
        ),
    },
    Language.ENGLISH: {
        "Lumi": (
            "Hi!\n\n"
            "Word from the Centre has reached the North with an answer for you. "
            "Passing it along exactly as it was given:\n\n"
            "{maintainer_answer}\n\n"
            "Closing the issue — the snow has settled on this matter. "
            "Stay frosty!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Greetings.\n\n"
            "The Northern winds carried words of answer from the Centre. "
            "I relay them intact:\n\n"
            "{maintainer_answer}\n\n"
            "Closing this circle — the question has reached its end.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hey!\n\n"
            "A hot word from the Centre arrived at the North — passing it "
            "on to you directly:\n\n"
            "{maintainer_answer}\n\n"
            "Closing the issue — volcanic greetings!\n"
            "— Katla"
        ),
    },
    Language.GERMAN: {
        "Lumi": (
            "Hallo!\n\n"
            "Vom Zentrum ist eine Nachricht in den Norden gelangt — eine "
            "Antwort für dich. Ich gebe sie genau so weiter, wie sie "
            "formuliert wurde:\n\n"
            "{maintainer_answer}\n\n"
            "Ich schließe das Anliegen — der Schnee hat sich auf diese "
            "Sache gelegt. Bleib frostig!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Sei gegrüßt.\n\n"
            "Die Winde des Nordens haben Worte der Antwort vom Zentrum "
            "gebracht. Ich überbringe sie unverändert:\n\n"
            "{maintainer_answer}\n\n"
            "Ich schließe diesen Kreis — die Frage hat ihr Ende erreicht.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hey!\n\n"
            "Ein heißes Wort vom Zentrum ist im Norden eingetroffen — "
            "ich gebe es dir direkt weiter:\n\n"
            "{maintainer_answer}\n\n"
            "Ich schließe das Anliegen — vulkanische Grüße!\n"
            "— Katla"
        ),
    },
    Language.SPANISH: {
        "Lumi": (
            "¡Hola!\n\n"
            "Una noticia desde el Centro ha llegado al Norte — una "
            "respuesta para ti. La transmito exactamente tal como fue "
            "formulada:\n\n"
            "{maintainer_answer}\n\n"
            "Cierro la incidencia — la nieve se ha asentado sobre este "
            "asunto. ¡Que la escarcha te acompañe!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Saludos.\n\n"
            "Los vientos del Norte han traído palabras de respuesta desde "
            "el Centro. Las relevo intactas:\n\n"
            "{maintainer_answer}\n\n"
            "Cierro este círculo — la pregunta ha llegado a su fin.\n"
            "— Vieno"
        ),
        "Katla": (
            "¡Hey!\n\n"
            "Una palabra ardiente del Centro llegó al Norte — te la paso "
            "directamente:\n\n"
            "{maintainer_answer}\n\n"
            "Cierro la incidencia — ¡saludos volcánicos!\n"
            "— Katla"
        ),
    },
    Language.FINNISH: {
        "Lumi": (
            "Hei!\n\n"
            "Keskuksesta on saapunut Pohjolaan sana — vastaus sinulle. "
            "Välitän sen täsmälleen siinä muodossa kuin se annettiin:\n\n"
            "{maintainer_answer}\n\n"
            "Suljen ilmoituksen — lumi on laskeutunut tämän asian päälle. "
            "Pysy kylmänä!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Tervehdys.\n\n"
            "Pohjolan tuulet ovat tuoneet vastauksen sanat Keskuksesta. "
            "Välitän ne ehjinä:\n\n"
            "{maintainer_answer}\n\n"
            "Suljen tämän piirin — kysymys on saapunut päätökseen.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hei!\n\n"
            "Kuuma sana Keskuksesta saapui Pohjolaan — annan sen sinulle "
            "suoraan:\n\n"
            "{maintainer_answer}\n\n"
            "Suljen ilmoituksen — tulivuoriterveisin!\n"
            "— Katla"
        ),
    },
    Language.FRENCH: {
        "Lumi": (
            "Bonjour !\n\n"
            "Un message du Centre est parvenu au Nord — une réponse pour "
            "vous. Je vous la transmets exactement comme elle a été "
            "formulée :\n\n"
            "{maintainer_answer}\n\n"
            "Je clôture le ticket — la neige s'est posée sur cette affaire. "
            "Glaciales salutations !\n"
            "— Lumi"
        ),
        "Vieno": (
            "Salutations.\n\n"
            "Les vents du Nord ont porté les mots de réponse du Centre. "
            "Je vous les relaye intacts :\n\n"
            "{maintainer_answer}\n\n"
            "Je referme ce cercle — la question a atteint sa fin.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hé !\n\n"
            "Un mot brûlant du Centre est arrivé au Nord — je vous le "
            "transmets directement :\n\n"
            "{maintainer_answer}\n\n"
            "Je clôture le ticket — salutations volcaniques !\n"
            "— Katla"
        ),
    },
    Language.ICELANDIC: {
        "Lumi": (
            "Halló!\n\n"
            "Skilaboð frá Miðstöðinni hafa borist Norðrinu — svar fyrir "
            "þig. Ég flyt þau nákvæmlega eins og þau voru sett fram:\n\n"
            "{maintainer_answer}\n\n"
            "Ég loka málinu — snjórinn hefur sest yfir þetta mál. "
            "Frostkveðjur!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Heilsa.\n\n"
            "Vindar Norðursins hafa borið svarorð frá Miðstöðinni. "
            "Ég kem þeim óbreyttum til skila:\n\n"
            "{maintainer_answer}\n\n"
            "Ég loka þessum hring — spurningin hefur náð sínum enda.\n"
            "— Vieno"
        ),
        "Katla": (
            "Hæ!\n\n"
            "Heit orð frá Miðstöðinni komu til Norðursins — ég sendi þér "
            "þau beint:\n\n"
            "{maintainer_answer}\n\n"
            "Ég loka málinu — eldfjallakveðjur!\n"
            "— Katla"
        ),
    },
    Language.ITALIAN: {
        "Lumi": (
            "Ciao!\n\n"
            "Una notizia dal Centro è giunta al Nord — una risposta per "
            "te. Te la trasmetto esattamente come è stata formulata:\n\n"
            "{maintainer_answer}\n\n"
            "Chiudo la segnalazione — la neve si è posata su questa "
            "faccenda. Saluti gelidi!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Salve.\n\n"
            "I venti del Nord hanno portato parole di risposta dal Centro. "
            "Te le riferisco intatte:\n\n"
            "{maintainer_answer}\n\n"
            "Chiudo questo cerchio — la domanda ha raggiunto la sua fine.\n"
            "— Vieno"
        ),
        "Katla": (
            "Ehi!\n\n"
            "Una parola rovente dal Centro è arrivata al Nord — te la "
            "passo direttamente:\n\n"
            "{maintainer_answer}\n\n"
            "Chiudo la segnalazione — saluti vulcanici!\n"
            "— Katla"
        ),
    },
    Language.RUSSIAN: {
        "Lumi": (
            "Привет!\n\n"
            "Из Центра в Север пришла весть — ответ для тебя. "
            "Передаю его ровно в той форме, в какой он был сформулирован:\n\n"
            "{maintainer_answer}\n\n"
            "Закрываю обращение — снег уже улёгся на этом деле. "
            "Морозного привета!\n"
            "— Lumi"
        ),
        "Vieno": (
            "Приветствую.\n\n"
            "Ветра Севера принесли слова ответа из Центра. "
            "Передаю их в неизменённой форме:\n\n"
            "{maintainer_answer}\n\n"
            "Закрываю этот круг — вопрос дошёл до своего конца.\n"
            "— Vieno"
        ),
        "Katla": (
            "Привет!\n\n"
            "Горячее слово из Центра прибыло на Север — передаю тебе "
            "напрямую:\n\n"
            "{maintainer_answer}\n\n"
            "Закрываю обращение — с вулканическим приветом!\n"
            "— Katla"
        ),
    },
}


# Intro dolepka „dodatkowa wiadomość od maintainera" w flow `fixed-in-release`
# z opcjonalnym trybem FILE (od v15.2.8). Bug-flow domyślnie publikuje sam
# generyczny TEMPLATES bez customizacji; jeśli maintainer chce dorzucić
# osobistą wiadomość (przeprosiny za incydent, tip o recovery, etc.) — zapisuje
# ją jako `pending_answer.md` w roocie repo PRZED nadaniem `fixed-in-release`,
# a bot dolepia ją pod TEMPLATES separatorem `---` z poniższym intro.
# W odróżnieniu od trybu FILE dla `answered`: brak pliku NIE jest błędem ani
# fallbackiem na tryb COMMENT — po prostu używamy standardowego TEMPLATES bez
# dolepka (bug-fix sam w sobie nie wymaga osobistej wiadomości — link do
# Release wystarcza).
PERSONAL_NOTE_INTRO: dict[Language, str] = {
    Language.POLISH: "Dodatkowa wiadomość od maintainera dla Ciebie:",
    Language.ENGLISH: "An additional message from the maintainer for you:",
    Language.GERMAN: "Eine zusätzliche Nachricht vom Maintainer für dich:",
    Language.SPANISH: "Un mensaje adicional del maintainer para ti:",
    Language.FINNISH: "Lisäviesti ylläpitäjältä sinulle:",
    Language.FRENCH: "Un message supplémentaire du mainteneur pour vous :",
    Language.ICELANDIC: "Viðbótarskilaboð frá viðhaldsaðila til þín:",
    Language.ITALIAN: "Un messaggio aggiuntivo dal maintainer per te:",
    Language.RUSSIAN: "Дополнительное сообщение от мейнтейнера для вас:",
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
    # Templatki TEMPLATES_ANSWERED + PERSONAL_NOTE_INTRO ZOSTAJĄ w tym module
    # jako single source — importuje je `odpowiedz_lokalnie.py`.
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

    wykryty = detector.detect_language_of(issue_body) if issue_body.strip() else None
    if wykryty not in TEMPLATES:
        wykryty = Language.ENGLISH

    persona = random.choice(PERSONAS)
    print(f"Wykryto język: {wykryty.name}. Dyżur: {persona}. "
          f"Etykieta wyzwalająca: {label_name or '(nieznana)'}.")

    tresc = TEMPLATES[wykryty][persona].format(link=_zbuduj_link_release())

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
