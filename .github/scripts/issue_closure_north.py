"""
issue_closure_north.py — etap „Północ" obiegu „Z Południa na Północ".

Po nadaniu etykiety ``fixed-in-release`` (bug-fix flow) lub ``answered``
(question flow, od v15.2.6) przez maintainera, pałeczkę przejmują bohaterki
z Północy:

  * Lumi  — śnieżnie, mroźnie, z humorem,
  * Vieno — szamańsko, mgliście, w półszeptach,
  * Katla — wulkanicznie, gorąco, z hukiem.

Skrypt (bug-fix flow, etykieta ``fixed-in-release``):
  1. odczytuje treść issue z env,
  2. wykrywa język oryginalnej treści (lingua-language-detector; fallback EN),
  3. losuje jedną z trzech bohaterek,
  4. formatuje komentarz w wykrytym języku z linkiem do najnowszego Release,
  5. dodaje komentarz przez ``gh issue comment``, zamyka przez ``gh issue close``
     i lockuje przez ``gh issue lock --reason resolved``.

Skrypt (question flow, etykieta ``answered``, od v15.2.6):

  Tryb FILE (od v15.2.7, priorytetowy gdy ``pending_answer.md`` istnieje
  w roocie repo — eliminuje race condition obecny w trybie COMMENT
  i obchodzi A11y blokadę kopiowania z terminala VS Code):
    1. odczytuje treść draftu z ``pending_answer.md`` (working dir
       po ``actions/checkout@v4`` = root repo),
    2. opakowuje treść w styl persony (TEMPLATES_ANSWERED),
    3. dodaje wrap'owany komentarz, zamyka issue i lockuje,
    4. wymazuje draft z historii main — dwie ścieżki, zależnie od stanu
       HEAD na origin/main:
         (a) atomic-reset (preferowana, od v15.2.8): jeśli HEAD = atomowy
             commit dodający TYLKO pending_answer.md, bot robi
             ``git reset --hard HEAD~1`` + ``git push --force-with-lease``,
             wymazując commit jakby nigdy nie istniał. Tag v<wersja>
             pozostaje stabilny, archive Release UI od razu czysty.
         (b) cleanup commit boota (fallback): jeśli HEAD zawiera dodatkowe
             pliki (np. fix-up CLAUDE.md zcommitowany razem z draftem),
             bot dokłada commit ``git rm pending_answer.md`` z autorem
             ``github-actions[bot]``. Wtedy tag wymaga force-push
             post-publish per heurystyka v15.2.7 (CLAUDE.md).
       Obie ścieżki wymagają ``contents: write`` w workflow permissions;
       atomic-reset dodatkowo wymaga ``fetch-depth: 2`` na
       ``actions/checkout`` (default shallow @v4 = depth 1, HEAD~1 nie
       istnieje lokalnie).

  Tryb COMMENT (fallback gdy ``pending_answer.md`` nie istnieje):
    1. odczytuje treść issue + wciąga OSTATNI komentarz maintainera (treść,
       URL, autor) przez ``_pobierz_ostatni_komentarz_z_meta``,
    2. safety check: jeśli ostatni komentarz pochodzi od bota (intake Sami),
       przerywa workflow z komunikatem o złej kolejności (maintainer nadał
       ``answered`` zanim odpowiedział),
    3. opakowuje komentarz maintainera w styl persony (TEMPLATES_ANSWERED),
    4. USUWA oryginalny komentarz maintainera przez REST DELETE
       ``/repos/{repo}/issues/comments/{id}`` (wycięty z URL'a), żeby
       user-facing wątek nie zawierał duplikatu treści (bez delete'u maintainer
       comment + wrap'owany komentarz Lumi/Vieno/Katla wyświetlałyby się obok
       siebie identycznie, a NVDA czytałby tę samą odpowiedź dwukrotnie),
    5. dodaje wrap'owany komentarz, zamyka issue i lockuje analogicznie jak
       w bug-fix flow.

  Motywacja trybu FILE (v15.2.7): maintainer NVDA-user nie może wygodnie
  wkleić długiej odpowiedzi przez web GitHub UI (kopiowanie z terminala VS
  Code zawodzi w accessibility buffer — powtarzanie ciągów znaków). Plus
  tryb COMMENT ma race condition: gdyby ktoś trzeci skomentował między
  komentarzem maintainera a nadaniem etykiety, ``_pobierz_ostatni_komentarz``
  wciągnąłby JEGO komentarz. File mode jest niezależny od stanu komentarzy
  i deterministyczny.

Wywołanie:
    python .github/scripts/issue_closure_north.py
    (brak argumentów CLI — dane czytamy z os.environ, żeby uniknąć word-
    splittingu basha na cudzysłowach / backtickach w treści issue)

Wymagane zmienne środowiskowe (wstrzykiwane przez sekcję ``env:`` w YAML):
    ISSUE_BODY              oryginalna treść issue (do detekcji języka)
    ISSUE_NUMBER            numer issue
    LABEL_NAME              etykieta wyzwalająca (``fixed-in-release``
                            lub ``answered``); od v15.2.6
    GH_TOKEN                token gh CLI (auto z secrets.GITHUB_TOKEN)
    GITHUB_REPOSITORY       owner/repo (auto z runtime'u GH Actions)
    GITHUB_SERVER_URL       https://github.com (auto z runtime'u; do linku
                            Releases)
"""

from __future__ import annotations

import json
import os
import random
import re
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


def _zbuduj_link_release() -> str:
    """Konstruuje link do najnowszego release'u na podstawie env GitHub."""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return f"{server}/releases/latest"
    return f"{server}/{repo}/releases/latest"


def _pobierz_ostatni_komentarz_z_meta(
    issue_number: str, repo: str,
) -> tuple[str, str, str]:
    """Wyciąga ostatni komentarz na issue + metadane (url, autor).

    Zwraca tuple ``(body, url, author_login)``. Pusty tuple ``("", "", "")``
    przy błędzie — wówczas wywołujący zdecyduje czy przerwać workflow.

    Konwencja workflow (od v15.2.6, flow `answered`): maintainer komentuje
    z odpowiedzią → nadaje etykietę `answered` → ten skrypt wciąga komentarz
    i opakowuje go w styl persony Północy (TEMPLATES_ANSWERED), a następnie
    usuwa oryginalny komentarz przez ``_usun_komentarz_po_url`` (po to żeby
    user-facing wątek nie miał duplikatu treści — bez delete'u maintainer
    comment i wrap'owany komentarz Lumi/Vieno/Katla wyświetlałyby się obok
    siebie z identyczną treścią, a NVDA odczytywałoby ją dwukrotnie).

    URL i autor potrzebne są dlatego, że:
      * ``url`` (format ``https://github.com/<repo>/issues/N#issuecomment-XXX``)
        pozwala wyciągnąć databaseId komentarza do REST DELETE — gh JSON nie
        eksponuje go bezpośrednio (pole ``id`` zwraca GraphQL Node ID, nie
        databaseId którego oczekuje REST endpoint
        ``/repos/{repo}/issues/comments/{id}``),
      * ``author.login`` służy safety checkowi: jeśli ostatni komentarz jest
        od bota (np. intake Sami z ``issue-intake.yml``), oznacza że
        maintainer nadał etykietę PRZED napisaniem odpowiedzi — wrap'owanie
        komentarza Sami byłoby błędem semantycznym. ``main()`` w takiej
        sytuacji przerywa workflow z komunikatem korygującym kolejność.
    """
    try:
        wynik = subprocess.run(
            ["gh", "issue", "view", issue_number, "--repo", repo,
             "--json", "comments"],
            check=True, capture_output=True, text=True,
        )
        data = json.loads(wynik.stdout)
        comments = data.get("comments", [])
        if not comments:
            return "", "", ""
        last = comments[-1]
        return (
            last.get("body", "") or "",
            last.get("url", "") or "",
            (last.get("author") or {}).get("login", "") or "",
        )
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"[!] Nie udało się pobrać ostatniego komentarza issue "
            f"#{issue_number}: {exc.stderr.strip() or exc}\n"
        )
        return "", "", ""
    except json.JSONDecodeError as exc:
        sys.stderr.write(
            f"[!] gh zwrócił nie-JSON output dla issue #{issue_number}: {exc}\n"
        )
        return "", "", ""
    except FileNotFoundError:
        sys.stderr.write("[!] `gh` CLI nie znalezione w PATH.\n")
        return "", "", ""


_RE_COMMENT_ID = re.compile(r"#issuecomment-(\d+)\s*$")


# File mode (v15.2.7+): draft odpowiedzi maintainera leży jako plain markdown
# w roocie repo. Nazwa flat (jak `release.txt` w workflow direct-to-main) —
# jeden plik per zgłoszenie pending, drugi musi poczekać aż pierwszy się
# zamknie. Konwencja: maintainer pushuje plik → nadaje etykietę `answered` →
# bot czyta, opakowuje, publikuje, usuwa plik commitem własnego autora.
PENDING_ANSWER_FILE = "pending_answer.md"

# Standardowy noreply-email użytkownika github-actions[bot] (numer 41898282
# to public ID użytkownika; wzorzec używany w setupach gdzie workflow
# commituje z powrotem do repo).
BOT_GIT_NAME = "github-actions[bot]"
BOT_GIT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def _usun_komentarz_po_url(repo: str, url: str) -> bool:
    """Usuwa komentarz na issue przez REST DELETE.

    URL ma format ``.../issues/<N>#issuecomment-<databaseId>`` — wyciągamy
    ``databaseId`` regex'em i wołamy ``gh api -X DELETE
    /repos/{repo}/issues/comments/{databaseId}``. ``gh`` używa swojego
    tokena (``GH_TOKEN``/``GITHUB_TOKEN`` z env), workflow ma
    ``permissions: issues: write`` co wystarcza.

    Zwraca True przy sukcesie, False przy błędzie (delete jest non-fatal
    z perspektywy wywołującego — jeśli się nie uda, wątek dostanie duplikat
    treści ale komentarz wrap'owany Lumi/Vieno/Katla i tak zostanie dodany,
    issue zamknięty i zalockowany).
    """
    if not url:
        return False
    m = _RE_COMMENT_ID.search(url)
    if not m:
        sys.stderr.write(
            f"[!] Nie udało się sparsować comment ID z URL: {url!r}\n"
        )
        return False
    comment_id = m.group(1)
    return _gh(["gh", "api", "-X", "DELETE",
                f"/repos/{repo}/issues/comments/{comment_id}"])


def _gh(cmd: list[str]) -> bool:
    """Uruchamia `gh` (lub `git`) z przechwyceniem błędów. Zwraca True przy sukcesie."""
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


def _wczytaj_pending_answer_z_pliku() -> str:
    """Wczytuje draft odpowiedzi z `pending_answer.md` w roocie repo.

    Zwraca treść (po ``strip()``) albo pusty string, jeśli plik nie istnieje
    lub jest pusty/whitespace-only. Pusty string sygnalizuje wywołującemu,
    że trzeba spaść do trybu COMMENT (wciąganie ostatniego komentarza).

    Po ``actions/checkout@v4`` working directory workflowu = root repo,
    więc ścieżka relatywna ``pending_answer.md`` trafia w roota.
    """
    try:
        with open(PENDING_ANSWER_FILE, "r", encoding="utf-8") as fh:
            tresc = fh.read().strip()
        if not tresc:
            sys.stderr.write(
                f"[!] {PENDING_ANSWER_FILE} istnieje, ale jest pusty — "
                "fallback do trybu wciągania ostatniego komentarza.\n"
            )
            return ""
        return tresc
    except FileNotFoundError:
        return ""
    except OSError as exc:
        sys.stderr.write(
            f"[!] Nie udało się otworzyć {PENDING_ANSWER_FILE}: {exc}\n"
        )
        return ""


def _czy_head_to_atomowy_pending_commit() -> bool:
    """Sprawdza, czy HEAD commit zawiera DOKŁADNIE jeden plik: pending_answer.md.

    ``git show --name-only --format= HEAD`` zwraca listę plików zmienionych
    w HEAD commit. Jeśli to dokładnie ``[PENDING_ANSWER_FILE]`` — wybieramy
    ścieżkę preferowaną (reset --hard HEAD~1 + force-push), która wymazuje
    commit z historii bez śladu i pozostawia tag v<wersja> stabilny. W każdym
    innym przypadku (commit modyfikuje też inne pliki, albo HEAD nie jest
    commit'em dodającym pending) — fallback do klasycznego cleanup commit'a
    przez ``_usun_pending_answer_z_git``.

    Wzorzec workflow „release-then-answer" (od v15.2.8): release commit
    pushowany jest NA CZYSTO (bez pending_answer.md), tag tworzony przez web
    Release UI atomowo z release commit'em, dopiero POTEM osobny atomowy
    commit z samym ``pending_answer.md``. Tak zorganizowana historia main
    pozwala bot'owi wymazać draft commit'em zerojedynkowym, a tag pozostaje
    na release commit'cie bez potrzeby force-push tag'a.
    """
    try:
        wynik = subprocess.run(
            ["git", "show", "--name-only", "--format=", "HEAD"],
            check=True, capture_output=True, text=True,
        )
        pliki = [linia.strip() for linia in wynik.stdout.splitlines() if linia.strip()]
        return pliki == [PENDING_ANSWER_FILE]
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"[!] git show HEAD nie zwrócił listy plików: "
            f"{exc.stderr.strip() or exc}\n"
        )
        return False
    except FileNotFoundError:
        sys.stderr.write("[!] `git` CLI nie znalezione w PATH.\n")
        return False


def _wymaz_pending_commit_force_push() -> bool:
    """Wymazuje atomowy pending_answer commit przez reset --hard + force-push.

    Działa TYLKO gdy HEAD == atomowy commit dodający TYLKO pending_answer.md
    — wywołujący MUSI najpierw sprawdzić to przez
    ``_czy_head_to_atomowy_pending_commit``. Sekwencja:

      1. ``git config user.{name,email}`` z BOT_GIT_* (commit autora nie tworzymy,
         ale ``git reset`` w niektórych konfiguracjach też wymaga ustawionej
         tożsamości — ustawiamy preventively),
      2. ``git reset --hard HEAD~1`` — przesuwamy lokalny ref jeden commit
         w tył, plik znika z worktree i indeksu,
      3. ``git push --force-with-lease origin HEAD:main`` — force-push z
         leasingiem: push przejdzie tylko jeśli zdalny ref jest dokładnie
         tam, gdzie był przy ostatnim fetch'u (chroni przed nadpisaniem
         cudzych commit'ów, gdyby — w niemożliwym solo-dev edge case — ktoś
         pushnął na main między checkoutem boota a jego pushem).

    Wymaga ``contents: write`` w workflow permissions (default token z tym
    scope'm pozwala na force-push do main — workflow direct-to-main repo
    nie ma branch protection na main). Wymaga też ``fetch-depth: 2`` na
    ``actions/checkout`` w workflow YAML — bez tego HEAD~1 nie istnieje
    lokalnie (default shallow clone @v4 = depth 1).

    Po sukcesie historia main wygląda tak, jakby pending_answer.md nigdy
    nie istniał: tag v<wersja> nadal wskazuje na release commit, HEAD też,
    archive Release UI nie zawiera draftu, nie ma cleanup commit'a do
    sprzątania.
    """
    if not _gh(["git", "config", "user.name", BOT_GIT_NAME]):
        return False
    if not _gh(["git", "config", "user.email", BOT_GIT_EMAIL]):
        return False
    if not _gh(["git", "reset", "--hard", "HEAD~1"]):
        return False
    if not _gh(["git", "push", "--force-with-lease", "origin", "HEAD:main"]):
        return False
    return True


def _usun_pending_answer_z_git(issue_number: str) -> bool:
    """Fallback: usuwa pending_answer.md cleanup commit-em boota.

    Stosowany gdy HEAD NIE jest atomowym commit'em pending_answer.md
    (np. maintainer zcommitował razem fix-up CLAUDE.md z lessons learned).
    Wtedy nie możemy wymazać HEAD'a — zniszczyłoby to inne zmiany — więc
    dodajemy commit boota usuwający tylko sam plik.

    Sekwencja: ``git config user.{name,email}`` (z BOT_GIT_*) → ``git rm`` →
    ``git commit`` → ``git push origin HEAD:main``. Każdy krok przez ``_gh``
    z przechwytem błędu — przy fail zwraca False i pozostawia plik w repo
    (wywołujący zaloguje warning, ale workflow zamknięcia issue już zrobił
    swoje: komentarz + close + lock).

    UWAGA: po tej ścieżce tag v<wersja> wskazuje na release commit
    zawierający pending_answer.md, a HEAD jest commit boota bez pliku.
    Należy zastosować heurystykę „cleanup commit boota = force-push tag"
    z v15.2.7 (CLAUDE.md), żeby Release archive UI był czysty. W praktyce
    wzorzec „release-then-answer" eliminuje większość przypadków
    sprowadzających się do tego fallbacku.
    """
    if not _gh(["git", "config", "user.name", BOT_GIT_NAME]):
        return False
    if not _gh(["git", "config", "user.email", BOT_GIT_EMAIL]):
        return False
    if not _gh(["git", "rm", PENDING_ANSWER_FILE]):
        return False
    msg = (
        f"chore(answer-bot): cleanup {PENDING_ANSWER_FILE} po odpowiedzi "
        f"na #{issue_number}"
    )
    if not _gh(["git", "commit", "-m", msg]):
        return False
    if not _gh(["git", "push", "origin", "HEAD:main"]):
        return False
    return True


def main() -> int:
    # Dane issue czytamy z env, żeby uniknąć word-splittingu basha na
    # cudzysłowach / backtickach w ciele zgłoszenia (czyli przy każdym
    # wklejonym snippetcie kodu pełnym ` i ").
    issue_body = os.environ.get("ISSUE_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "").strip()
    label_name = os.environ.get("LABEL_NAME", "").strip()  # od v15.2.6
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

    wykryty = detector.detect_language_of(issue_body) if issue_body.strip() else None
    if wykryty not in TEMPLATES:
        wykryty = Language.ENGLISH

    persona = random.choice(PERSONAS)
    print(f"Wykryto język: {wykryty.name}. Dyżur: {persona}. "
          f"Etykieta wyzwalająca: {label_name or '(nieznana)'}.")

    # Branching per etykieta (od v15.2.6):
    #   `fixed-in-release` → klasyczny bug-fix flow: TEMPLATES z {link}
    #                        do najnowszego Release na GitHubie.
    #   `answered` → flow odpowiedzi na pytanie/help wanted: wciągnij
    #                ostatni komentarz maintainera, opakuj w TEMPLATES_ANSWERED
    #                bez linku do release (w tym kontekście link byłby
    #                szumem informacyjnym — user nie potrzebuje aktualizować
    #                aplikacji).
    #   Fallback (nieznana lub pusta etykieta) → klasyczny flow, jak
    #                pre-v15.2.6 — backward compat dla starszych webhook
    #                eventów które nie wstrzyknęły jeszcze LABEL_NAME.
    # Flaga ustawiana tylko w trybie FILE: po publikacji wrapped komentarza
    # + close + lock, bot usunie pending_answer.md commit-em własnego autora.
    # W trybie COMMENT pozostaje False (nie ma czego sprzątać — komentarz
    # maintainera został już usunięty REST DELETE w obrębie tej samej gałęzi).
    cleanup_pending_file = False

    if label_name == "answered":
        # FILE mode priorytetowy (v15.2.7+): jeśli `pending_answer.md` istnieje
        # w roocie repo, używamy jego treści bez wciągania ostatniego
        # komentarza. Eliminuje race condition obecny w COMMENT mode (gdyby
        # ktoś trzeci skomentował między napisaniem odpowiedzi a nadaniem
        # etykiety, COMMENT mode wciągnąłby JEGO komentarz). Plus omija
        # A11y blokadę kopiowania długich odpowiedzi przez web GitHub UI
        # u maintainera-NVDA-usera.
        draft_z_pliku = _wczytaj_pending_answer_z_pliku()
        if draft_z_pliku:
            print(
                f"Tryb FILE: wciągnięto draft z {PENDING_ANSWER_FILE} "
                f"({len(draft_z_pliku)} znaków)."
            )
            maintainer_answer = draft_z_pliku
            cleanup_pending_file = True
        else:
            # COMMENT mode (fallback): obecny mechanizm pre-15.2.7.
            print("Tryb COMMENT: brak pending_answer.md — wciągam ostatni komentarz.")
            maintainer_answer, comment_url, comment_author = (
                _pobierz_ostatni_komentarz_z_meta(issue_number, repo)
            )
            if not maintainer_answer:
                sys.stderr.write(
                    "[!] Brak draftu w pending_answer.md ANI komentarza "
                    "maintainera do opakowania. Konwencje (od v15.2.7):\n"
                    "  (A) FILE mode: zapisz draft w pending_answer.md "
                    "i pushnij PRZED nadaniem etykiety `answered`,\n"
                    "  (B) COMMENT mode: skomentuj na issue PRZED "
                    "nadaniem etykiety `answered`.\n"
                )
                return 1
            # Safety check: ostatni komentarz musi być od człowieka, nie
            # od bota. Jeśli ostatnim komentarzem jest intake Sami
            # (`github-actions[bot]`), oznacza że maintainer pomylił
            # kolejność (nadał `answered` zanim odpowiedział).
            if (comment_author.endswith("[bot]")
                    or comment_author == "github-actions"):
                sys.stderr.write(
                    f"[!] Ostatni komentarz na issue #{issue_number} pochodzi "
                    f"od bota ({comment_author!r}). Maintainer musi napisać "
                    "odpowiedź ZANIM doda etykietę `answered` (lub użyć "
                    "trybu FILE — pending_answer.md). Workflow przerywany — "
                    "popraw kolejność.\n"
                )
                return 1
            # Usuń oryginalny komentarz maintainera ZANIM dodamy wrapped
            # wersję. Bez delete'u user widzi tę samą odpowiedź dwukrotnie
            # (raz jako sam komentarz, raz wewnątrz wrap'a Lumi/Vieno/Katla).
            # Delete jest non-fatal: jeśli się nie uda (np. brak permissions,
            # GitHub rate limit), wciąż wolimy zamknąć issue z duplikatem
            # niż w ogóle nie odpowiedzieć i nie zamknąć.
            if not _usun_komentarz_po_url(repo, comment_url):
                sys.stderr.write(
                    f"[!] Usunięcie oryginalnego komentarza maintainera nie "
                    f"powiodło się — wątek issue #{issue_number} będzie "
                    "zawierał duplikat treści (komentarz maintainera + "
                    "wrap'owana wersja Lumi/Vieno/Katla).\n"
                )
        szablon = TEMPLATES_ANSWERED[wykryty][persona]
        tresc = szablon.format(maintainer_answer=maintainer_answer)
    else:
        szablon = TEMPLATES[wykryty][persona]
        link = _zbuduj_link_release()
        tresc = szablon.format(link=link)

    if not _gh(["gh", "issue", "comment", issue_number, "--repo", repo,
                "--body", tresc]):
        return 1
    if not _gh(["gh", "issue", "close", issue_number, "--repo", repo]):
        return 1
    # Lock po zamknięciu — analogicznie do patch-bot.yml. Reason `resolved`
    # czytelnie sygnalizuje czytnikom ekranu i bot-watcherom, że dyskusja
    # zakończyła się rozwiązaniem (a nie spam/duplikat/wontfix). Bez locka
    # użytkownik mógłby dopisywać komentarze po Lumi/Vieno/Katla — wątek
    # rozjeżdża się i robot przy następnej etykiecie zbędnie domyka go
    # ponownie.
    if not _gh(["gh", "issue", "lock", issue_number, "--repo", repo,
                "--reason", "resolved"]):
        # Lock nie jest krytyczny dla samego zamknięcia (komentarz + close
        # już poszły) — logujemy ostrzeżenie, ale nie kładziemy całego
        # workflowu. Typowy powód błędu: brak uprawnień `issues: write`
        # w sekcji `permissions:` (unlikely w naszym setup, ale przewidywalny
        # gdy ktoś kiedyś skopiuje workflow do innego repo z bardziej
        # restrykcyjnymi permissions).
        sys.stderr.write(
            f"[!] Lock issue #{issue_number} nie powiódł się — "
            "komentarz i close OK, ale wątek pozostaje odblokowany.\n"
        )

    # Cleanup file mode (od v15.2.8): dwie ścieżki, dwa stopnie czystości
    # historii.
    #
    # Preferowana (atomic-reset): jeśli HEAD jest atomowym commit'em
    # dodającym TYLKO pending_answer.md (wzorzec workflow „release-then-
    # answer": release commit + tag PRZED commitem pending_answer.md),
    # wymazujemy commit przez `git reset --hard HEAD~1` + force-push-with-
    # lease. Historia main wygląda tak, jakby draft nigdy nie istniał — tag
    # v<wersja> stabilny, archive Release UI czysty, brak cleanup commit'a.
    #
    # Fallback (cleanup commit boota, pre-v15.2.8 default): jeśli HEAD
    # zawiera dodatkowe pliki (np. fix-up CLAUDE.md razem z draftem), nie
    # możemy wymazać commit'a — dodajemy commit boota usuwający sam plik.
    # Tag v<wersja> wymaga wtedy force-push post-publish per heurystyka
    # v15.2.7 (CLAUDE.md sekcja „cleanup commit boota = force-push tag").
    #
    # Non-fatal jak w v15.2.7: jeśli obie ścieżki failują, plik zostaje
    # w repo i maintainer usuwa go ręcznie. Komentarz + close + lock już
    # przeszły, więc user-facing flow jest kompletny niezależnie od cleanup.
    if cleanup_pending_file:
        if _czy_head_to_atomowy_pending_commit():
            print(
                f"HEAD = atomowy commit {PENDING_ANSWER_FILE} — ścieżka "
                "preferowana (reset+force-push, wymazanie z historii)."
            )
            if _wymaz_pending_commit_force_push():
                print(
                    f"Wymazano atomowy commit {PENDING_ANSWER_FILE} "
                    "przez reset+force-push. Historia main czysta, tag "
                    "v<wersja> stabilny."
                )
            else:
                # Reset/force-push fail. Lokalny stan boota może być rozjechany
                # (reset zadziałał, push nie), ale następny workflow run dostanie
                # świeży checkout, więc to bez znaczenia. Plik wciąż jest na
                # origin/main — maintainer usuwa ręcznie.
                sys.stderr.write(
                    f"[!] Atomic-reset {PENDING_ANSWER_FILE} nie powiódł "
                    "się — komentarz, close i lock OK, ale plik wisi na "
                    "origin/main. Usuń ręcznie: `git rm "
                    f"{PENDING_ANSWER_FILE} && git commit -m \"cleanup\" "
                    "&& git push`.\n"
                )
        else:
            print(
                f"HEAD zawiera dodatkowe pliki poza {PENDING_ANSWER_FILE} "
                "— fallback do cleanup commit'a boota. Tag v<wersja> może "
                "wymagać force-push post-publish (heurystyka v15.2.7)."
            )
            if _usun_pending_answer_z_git(issue_number):
                print(
                    f"Cleanup {PENDING_ANSWER_FILE} OK (commit boota "
                    "pushnięty na main)."
                )
            else:
                sys.stderr.write(
                    f"[!] Cleanup {PENDING_ANSWER_FILE} nie powiódł się — "
                    "komentarz, close i lock OK, ale plik wisi w repo. "
                    "Usuń ręcznie: `git rm pending_answer.md && git commit "
                    "-m \"cleanup\" && git push`.\n"
                )

    print(f"Issue #{issue_number} skomentowane, zamknięte i zablokowane przez {persona}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
