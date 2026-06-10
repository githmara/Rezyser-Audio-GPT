"""
issue_intake_sami.py — etap „Południe" obiegu zgłoszeń.

Reprezentantka: Sami — energiczna, ekspresyjna włoska asystentka-dyspozytorka.
Odbiera GitHub Issue, używa OpenAI do przekucia chaotycznego tekstu użytkownika
w wysoce techniczny, zwięzły prompt inżynieryjny po polsku (gotowy do wklejenia
do agenta AI typu Claude Code), a następnie wysyła ten prompt mailem do Centrum
(maintainer).

Wywołanie z workflow:
    python .github/scripts/issue_intake_sami.py
    (brak argumentów CLI — dane czytamy z os.environ, żeby uniknąć word-
    splittingu basha na cudzysłowach / backtickach w treści issue)

Wymagane zmienne środowiskowe (wstrzykiwane przez sekcję ``env:`` w YAML):
    ISSUE_TITLE             tytuł zgłoszenia
    ISSUE_BODY              treść zgłoszenia
    ISSUE_NUMBER            numer issue
    ISSUE_LABELS            etykiety CSV (przygotowane w kroku poprzednim)
    ISSUE_URL               link do issue na GitHubie
    OPENAI_API_KEY          klucz OpenAI (sekret GH Actions)
    SMTP_USER               nadawca + odbiorca (gmail dewelopera)
    SMTP_PASS               hasło aplikacji SMTP (Gmail app password)
    MAINTAINER_EMAIL        (opcjonalnie) odbiorca; fallback = SMTP_USER
    GH_TOKEN                token gh CLI (auto z secrets.GITHUB_TOKEN) — do
                            dodania komentarza Sami na issue po wysyłce maila
    GITHUB_REPOSITORY       owner/repo (auto z runtime'u GH Actions)

Fallback: jeśli OpenAI zawiedzie (brak kredytów, 401/429, timeout) — wysyłamy
oryginalną treść zgłoszenia z notatką, że Sami chwilowo nie pomogła w
przeredagowaniu.
"""

from __future__ import annotations

import os
import smtplib
import subprocess
import sys
from email.message import EmailMessage

from lingua import Language, LanguageDetectorBuilder


# Lingua singleton zacisnięty do 9 wspieranych języków (te same co
# `send_patch.py` i `issue_closure_north.py`). Cold-init detektora to ~3 sek;
# trzymamy go na poziomie modułu, żeby nie inicjalizować przy każdym wywołaniu.
LANGUAGES = [
    Language.GERMAN, Language.ENGLISH, Language.SPANISH,
    Language.FINNISH, Language.FRENCH, Language.ICELANDIC,
    Language.ITALIAN, Language.POLISH, Language.RUSSIAN,
]
_detector = LanguageDetectorBuilder.from_languages(*LANGUAGES).build()


# Markery zgłoszenia-crash (od v17.0). Globalny handler wyjątków aplikacji
# (`main._zapisz_log_bledu`) zapisuje traceback do `error_log.txt` z nagłówkiem
# `CRASH_MARKER`; zwykły user wkleja/załącza ten plik do Issue. Takie ciało to
# surowy traceback (angielskie nazwy wyjątków, ścieżki Windows, fragmenty kodu)
# — Lingua (detektor n-gramowy) myliłaby się na nim, a i tak chcemy uniwersalnej
# odpowiedzi po angielsku. Wykrywamy crash po DOWOLNYM z markerów. Sygnatura
# `Traceback (most recent call last)` jest gwarantowana w każdym tracebacku
# Pythona (nawet gdy user wklei sam ślad bez nagłówka pliku).
_CRASH_MARKERY = (
    "=== REŻYSER AUDIO GPT — CRASH REPORT ===",
    "Traceback (most recent call last)",
)


def _czy_crash_report(issue_body: str) -> bool:
    """Czy ciało zgłoszenia wygląda na raport o crashu (error_log.txt)?"""
    return any(marker in issue_body for marker in _CRASH_MARKERY)


# Komentarz Sami zostawiany na issue PO pomyślnej wysyłce maila do Centrum.
# Jeden wariant per język (Sami to jedyna persona Południa — bez losowania).
# Styl: włoski temperament, „Ciao!" + „A presto!", bezpośrednio adresuje
# usera i informuje że jego zgłoszenie nie zostało zignorowane — kolejny
# meldunek przyjdzie z Północy (Lumi/Vieno/Katla) po wydaniu fix-a.
COMMENTS: dict[Language, str] = {
    Language.POLISH: (
        "Ciao! 🌞 Sami z Południa zauważyła Twoje zgłoszenie i już "
        "pomknęła z technicznym promptem do Centrum. Za chwilkę "
        "projektant aplikacji się tym zajmie — a kiedy poprawka wjedzie "
        "do najnowszego wydania, odezwie się tutaj jedna z moich "
        "koleżanek z Północy: Lumi, Vieno albo Katla. A presto!\n"
        "— Sami"
    ),
    Language.ENGLISH: (
        "Ciao! 🌞 Sami from the South has spotted your report and zoomed "
        "off with a technical prompt to the Centre. The app's designer "
        "will look into it shortly — and once the fix lands in the "
        "latest release, one of my Northern colleagues will drop by "
        "here: Lumi, Vieno or Katla. A presto!\n"
        "— Sami"
    ),
    Language.GERMAN: (
        "Ciao! 🌞 Sami aus dem Süden hat deine Meldung entdeckt und ist "
        "mit dem technischen Prompt zum Zentrum geflitzt. Der "
        "App-Entwickler kümmert sich gleich darum — und sobald die "
        "Korrektur in der neuesten Veröffentlichung landet, meldet sich "
        "hier eine meiner nordischen Kolleginnen: Lumi, Vieno oder "
        "Katla. A presto!\n"
        "— Sami"
    ),
    Language.SPANISH: (
        "¡Ciao! 🌞 Sami del Sur ha visto tu reporte y ha salido "
        "disparada con el prompt técnico hacia el Centro. El diseñador "
        "de la aplicación se ocupará en breve — y cuando la corrección "
        "llegue a la última versión, aparecerá por aquí una de mis "
        "colegas del Norte: Lumi, Vieno o Katla. ¡A presto!\n"
        "— Sami"
    ),
    Language.FINNISH: (
        "Ciao! 🌞 Etelän Sami huomasi ilmoituksesi ja sujahti teknisen "
        "kehotuksen kanssa Keskukseen. Sovelluksen suunnittelija "
        "paneutuu siihen pian — ja kun korjaus saapuu uusimpaan "
        "julkaisuun, täällä piipahtaa joku Pohjolan kollegoistani: "
        "Lumi, Vieno tai Katla. A presto!\n"
        "— Sami"
    ),
    Language.FRENCH: (
        "Ciao ! 🌞 Sami du Sud a repéré ton signalement et est partie "
        "en trombe avec le prompt technique vers le Centre. Le "
        "concepteur de l'application s'en occupera sous peu — et "
        "lorsque la correction arrivera dans la dernière version, "
        "l'une de mes collègues du Nord passera par ici : Lumi, Vieno "
        "ou Katla. À presto !\n"
        "— Sami"
    ),
    Language.ICELANDIC: (
        "Ciao! 🌞 Sami að sunnan kom auga á tilkynningu þína og þaut "
        "af stað með tæknilegan leiðbeini til Miðstöðvarinnar. "
        "Hönnuður forritsins tekur á henni innan stundar — og þegar "
        "lagfæringin birtist í nýjustu útgáfu, mun ein af norrænu "
        "kollegum mínum kíkja við hér: Lumi, Vieno eða Katla. "
        "A presto!\n"
        "— Sami"
    ),
    Language.ITALIAN: (
        "Ciao! 🌞 Sami dal Sud ha avvistato la tua segnalazione ed è "
        "sfrecciata con il prompt tecnico verso il Centro. Il "
        "progettista dell'app se ne occuperà a breve — e quando la "
        "correzione arriverà nell'ultima versione, qui passerà una "
        "delle mie colleghe del Nord: Lumi, Vieno o Katla. A presto!\n"
        "— Sami"
    ),
    Language.RUSSIAN: (
        "Ciao! 🌞 Сами с Юга заметила твоё обращение и рванула с "
        "техническим запросом в Центр. Разработчик приложения скоро "
        "возьмётся за дело — а когда исправление попадёт в новейший "
        "выпуск, сюда заглянет одна из моих коллег с Севера: Lumi, "
        "Vieno или Katla. A presto!\n"
        "— Sami"
    ),
}


# Etykiety, które IGNORUJEMY (nie wysyłamy maila do Centrum).
LABELS_IGNORE = {
    "wontfix",
    "duplicate",
    "tiflotecnia-patch",
    "fixed-in-release",
    # `answered` USUNIĘTE w v17.1: flow odpowiedzi przeniesiony do lokalnego
    # odpowiedz_lokalnie.py (zamyka issue od razu, bez etykiety-triggera),
    # a sama etykieta skasowana z repo dla czytelności listy Issues.
}

# Etykiety, które AKCEPTUJEMY (przynajmniej jedna musi się pojawić).
LABELS_ACCEPT = {
    "bug",
    "enhancement",
    "documentation",
    "question",
    "invalid",
    "help wanted",
    "good first issue",
}


SAMI_SYSTEM_PROMPT = (
    "Sei Sami — un'energica e espressiva assistente-dispatcher italiana, "
    "responsabile dello smistamento delle segnalazioni nel progetto Regista "
    "Audio AI (studio di registrazione ibrido per radiodrammi, audiolibri e "
    "storie interattive, framework desktop wxPython ottimizzato per lettori "
    "di schermo come NVDA, 9 pacchetti linguistici nativi, motore LLM per "
    "modalità interattive). NOTA: questo NON è il plug-in NVDA „Tiflotecnia "
    "Voices\" (quello è un progetto separato gestito tramite l'etichetta "
    "tiflotecnia-patch dedicata) — le segnalazioni qui possono riguardare "
    "QUALSIASI modulo: Regista, Poliglotta, Convertitore, Architetto degli "
    "Audiolibri, Gestore di Regole, Storie Interattive, workflow GitHub "
    "Actions, documentazione. "
    "Il tuo unico compito: leggere una GitHub Issue scritta da un utente "
    "(spesso caotica, in qualunque lingua) e trasformarla in un prompt "
    "tecnico, conciso e azionabile IN POLACCO, pronto da incollare in un "
    "agente AI con accesso al repository (Claude Code, Cursor, Aider).\n\n"
    "REGUŁA KRYTYCZNA (od v15.2.6): dostosuj FORMAT WYJŚCIA do TYPU "
    "ZGŁOSZENIA. Etykiety GitHub są podane w user message — sprawdź je "
    "i wybierz JEDEN z dwóch trybów poniżej. NIE produkuj 4 sekcji "
    "automatycznie dla każdego zgłoszenia — to było dawne zachowanie (do "
    "v15.2.5) i prowadziło do absurdalnych „Kryteriów akceptacji\" i "
    "„Pułapek do uniknięcia\" dla zwykłych pytań usera.\n\n"
    "TRYB A — pytanie / help wanted (gdy etykiety zawierają TYLKO "
    "`question` i/lub `help wanted`, BEZ `bug`/`enhancement`/`documentation`):\n"
    "  User chce TYLKO odpowiedzi, NIE zmiany kodu. Agent ma przeczytać "
    "konkretne miejsca w kodzie/dokumentacji i odpowiedzieć w komentarzu "
    "na issue (komentarz potem zostanie opakowany w styl persony Północy "
    "Lumi/Vieno/Katla przez bota issue-closure, bez linku do release).\n"
    "  Wygeneruj DOKŁADNIE 2 sekcje po polsku:\n"
    "    1. „## Cel pytania\" — 1-2 zdania: o co dokładnie pyta user.\n"
    "    2. „## Co agent powinien zrobić\" — bullet list konkretnych "
    "miejsc w kodzie/dokumentacji do przejrzenia (np. „docs/manual.<jzk>.txt "
    "sekcja Automatyczne aktualizacje\", „installer.iss linia 64 Excludes\", "
    "„core_updater.py funkcja sprawdz_aktualizacje\") + jedna końcowa "
    "linijka „Odpowiedz w komentarzu na issue w języku oryginalnego "
    "zgłoszenia, tonem technicznym ale przystępnym dla niewidomych userów "
    "NVDA\".\n"
    "  ZAKAZ generowania sekcji „Kryteria akceptacji\", „Pułapki do "
    "uniknięcia\", „Kroki reprodukcji\" — to nie patch, agent tylko czyta "
    "i odpowiada.\n\n"
    "TRYB B — zmiana w kodzie (gdy etykiety zawierają `bug`, `enhancement`, "
    "`documentation` z wymaganiem akcji, lub `invalid` do oceny — nawet w "
    "kombinacji z `question`/`help wanted`):\n"
    "  Wygeneruj DOKŁADNIE 4 sekcje po polsku:\n"
    "    1. „## Cel\" — 1-2 zdania: czego dotyczy zgłoszenie i co ma się "
    "zmienić.\n"
    "    2. „## Kontekst techniczny\" — punkty: typ zgłoszenia "
    "(bug/enhancement/...), prawdopodobny moduł projektu (gui_*.py / "
    "core_*.py / dictionaries/<kod>/ / runtime/ / docs/ / .github/workflows/), "
    "kroki reprodukcji (gdy bug), oczekiwane zachowanie.\n"
    "    3. „## Kryteria akceptacji\" — bullet list, co MUSI być spełnione, "
    "żeby uznać zadanie za zrobione (testy, A11y, i18n we wszystkich 9 "
    "językach, regeneracja docs gdy dotyczy).\n"
    "    4. „## Pułapki do uniknięcia\" — krótka lista znanych z CLAUDE.md "
    "reguł, których agent musi przestrzegać (.venv/Scripts/python, "
    "git --no-pager, ZAKAZ uruchamiania runtime/, bezpieczne testy bez "
    "MainLoop, single source of truth dla VERSION, procedura release "
    "docs->commit).\n\n"
    "STYL: zwięzły, techniczny, bez emoji, bez kurtuazji. Jeśli zgłoszenie "
    "jest po włosku, hiszpańsku, francusku, niemiecku, fińsku, islandzku, "
    "rosyjsku lub angielsku — przetłumacz fakty na polski (NIE zostawiaj "
    "tekstu obcego w prompcie). Jeśli zgłoszenie jest bezsensowne — wprost "
    "napisz w sekcji Cel: „Zgłoszenie wymaga doprecyzowania od użytkownika\"."
)


def _wczytaj_dane_issue() -> tuple[str, str, str, str, str]:
    """Zwraca (title, body, number, labels_csv, url) z os.environ.

    Czytamy z env zamiast z sys.argv, żeby uniknąć word-splittingu basha
    na cudzysłowach i backtickach w treści issue (`"$ISSUE_BODY"` rozsypie
    się, gdy ciało zawiera niesparowany ").
    """
    return (
        os.environ.get("ISSUE_TITLE", ""),
        os.environ.get("ISSUE_BODY", ""),
        os.environ.get("ISSUE_NUMBER", ""),
        os.environ.get("ISSUE_LABELS", ""),
        os.environ.get("ISSUE_URL", ""),
    )


def _przepuszczalne(labels_csv: str) -> tuple[bool, list[str]]:
    """Zwraca (czy_przepuścić, lista_etykiet).

    Logika: filtr ignoruje etykiety z LABELS_IGNORE. Z pozostałych musi być
    co najmniej jedna z LABELS_ACCEPT. Brak etykiet w ogóle = przepuszczamy
    (nowy issue może nie mieć jeszcze przypisanej etykiety; Sami i tak
    spojrzy).
    """
    labels = [
        lbl.strip().lower()
        for lbl in labels_csv.split(",")
        if lbl.strip()
    ]
    if not labels:
        return True, []
    if any(lbl in LABELS_IGNORE for lbl in labels):
        return False, labels
    if any(lbl in LABELS_ACCEPT for lbl in labels):
        return True, labels
    # Nieznana etykieta — domyślnie przepuszczamy (Sami spojrzy raz, dyżurny
    # sam zdecyduje co dalej).
    return True, labels


def _przeredaguj_z_openai(
    title: str, body: str, labels: list[str]
) -> tuple[str, bool]:
    """Zwraca (tekst_promptu, czy_użyto_LLM).

    Fallback: jeśli klucza brak / API zawiedzie — zwracamy oryginalny tekst
    z nagłówkiem i flagą ``False``.
    """
    klucz = os.environ.get("OPENAI_API_KEY", "").strip()
    if not klucz:
        sys.stderr.write(
            "[!] Brak OPENAI_API_KEY — wysyłam oryginalną treść zgłoszenia.\n"
        )
        return _fallback(title, body, labels), False

    try:
        from openai import OpenAI
    except ImportError as exc:
        sys.stderr.write(f"[!] openai SDK nie zainstalowane: {exc}\n")
        return _fallback(title, body, labels), False

    try:
        klient = OpenAI(api_key=klucz)
        odp = klient.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": SAMI_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"# Tytuł zgłoszenia\n{title}\n\n"
                        f"# Etykiety GitHub\n{', '.join(labels) or '(brak)'}\n\n"
                        f"# Treść zgłoszenia użytkownika\n{body}"
                    ),
                },
            ],
        )
        tresc = (odp.choices[0].message.content or "").strip()
        if not tresc:
            sys.stderr.write("[!] OpenAI zwróciło pustą odpowiedź — fallback.\n")
            return _fallback(title, body, labels), False
        return tresc, True
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[!] OpenAI API zawiodło: {exc}\n")
        return _fallback(title, body, labels), False


def _fallback(title: str, body: str, labels: list[str]) -> str:
    return (
        "## Cel\n"
        "(Sami chwilowo nie pomogła z przeredagowaniem — wysyłam oryginalną "
        "treść zgłoszenia. Maintainer doprecyzuje ręcznie.)\n\n"
        f"## Tytuł oryginalny\n{title}\n\n"
        f"## Etykiety\n{', '.join(labels) or '(brak)'}\n\n"
        "## Oryginalna treść\n"
        f"{body}"
    )


def _gh(cmd: list[str]) -> bool:
    """Uruchamia `gh` z przechwyceniem błędów. Zwraca True przy sukcesie.

    Identyczna semantyka co w `issue_closure_north._gh` — duplikat świadomy,
    bo skrypty są niezależnymi entrypointami (workflow je odpala bez
    wspólnego modułu).
    """
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


def _zostaw_komentarz_sami(
    issue_number: str, issue_body: str, czy_llm: bool
) -> None:
    """Zostawia komentarz Sami na issue po pomyślnej wysyłce maila do Centrum.

    Język komentarza wykrywany lingua-language-detector'em na ciele issue
    (te same 9 jzk co reszta obiegu). Brak komentarza dla LABELS_IGNORE
    (skrypt nie dochodzi tu w tym scenariuszu — wcześniejszy return 0).

    `czy_llm` decyduje czy doklejamy sufiks „(tym razem przekazałam
    oryginalną treść — Centrum przejrzy ręcznie)". User powinien wiedzieć,
    że Sami nie pomogła z przeredagowaniem, żeby nie czekał na cudowny
    fix gdy zgłoszenie jest niezrozumiałe.
    """
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        sys.stderr.write(
            "[!] Brak GITHUB_REPOSITORY w env — pomijam komentarz Sami.\n"
        )
        return

    if _czy_crash_report(issue_body):
        # Crash-report → POMIJAMY Lingua (traceback myli detektor) i odpowiadamy
        # po angielsku, uniwersalnie. Patrz `_CRASH_MARKERY`.
        wykryty = Language.ENGLISH
    else:
        wykryty = (
            _detector.detect_language_of(issue_body)
            if issue_body.strip()
            else None
        )
        if wykryty not in COMMENTS:
            wykryty = Language.ENGLISH

    tresc = COMMENTS[wykryty]
    if not czy_llm:
        # Sufiks per język byłby przerostem — pojedyncza krótka angielska
        # adnotacja w nawiasie wystarczy do sygnału „uważaj, fallback".
        # User i tak rzuci okiem na mail jeśli zechce sprawdzić co Centrum
        # dostało.
        tresc += "\n\n*(LLM fallback — original body forwarded raw.)*"

    if _gh(["gh", "issue", "comment", issue_number, "--repo", repo,
            "--body", tresc]):
        print(f"Komentarz Sami dodany do issue #{issue_number} "
              f"(język: {wykryty.name}).")


def _lista_otwartych_issues() -> str:
    """Pełny output `gh issue list --state open` jako trzecia sekcja maila.

    Wprowadzone 2026-05-16: lokalny PATH agentów Centrum nie zawsze ma
    `gh` (potwierdzone empirycznie na Git Bash + PowerShell maintainera),
    co skutkuje powtarzającym się błędem „gh: command not found" przy
    próbie uzyskania kontekstu repo (duplikaty, powiązane bug-raporty,
    co czeka w kolejce). Workflow runner zawsze ma `gh` zainstalowane,
    więc Sami łuska listę tu i wkleja w mailu — Centrum dostaje pełny
    obraz bez konieczności odpalania `gh` lokalnie.

    Bieżące issue nie jest filtrowane — i tak pojawi się na liście (właśnie
    zostało utworzone i ma stan open), ale user wie co zgłosił. Limit 50
    chroni przed wybuchem maila gdy backlog spuchnie.
    """
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return "(brak GITHUB_REPOSITORY w env — listy nie pobrano)"
    try:
        wynik = subprocess.run(
            ["gh", "issue", "list", "--repo", repo,
             "--state", "open", "--limit", "50"],
            check=True, capture_output=True, text=True, timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        return f"(gh issue list zfailowało: {exc.stderr.strip() or exc})"
    except subprocess.TimeoutExpired:
        return "(gh issue list timeout >30s — pomijam)"
    except FileNotFoundError:
        return "(gh CLI nie znalezione w PATH workflow runner'a)"
    return wynik.stdout.strip() or "(brak otwartych issues)"


def _wyslij_maila(
    temat: str, tresc: str, recipient: str, smtp_user: str, smtp_pass: str
) -> bool:
    msg = EmailMessage()
    msg["Subject"] = temat
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg.set_content(tresc)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"Mail wysłany do {recipient}.")
        return True
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[!] Błąd wysyłki maila: {exc}\n")
        return False


def main() -> int:
    title, body, number, labels_csv, url = _wczytaj_dane_issue()
    if not number:
        sys.stderr.write(
            "[!] Brak ISSUE_NUMBER w env — przerywam (workflow musi wstrzyknąć "
            "ISSUE_TITLE/ISSUE_BODY/ISSUE_NUMBER/ISSUE_LABELS/ISSUE_URL).\n"
        )
        return 2

    czy_przepuscic, labels = _przepuszczalne(labels_csv)
    if not czy_przepuscic:
        print(
            f"Issue #{number}: etykiety {labels} odfiltrowane "
            f"(LABELS_IGNORE). Kończę bez maila."
        )
        return 0

    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASS", "").strip()
    if not smtp_user or not smtp_pass:
        sys.stderr.write(
            "[!] Brak SMTP_USER lub SMTP_PASS w env — nie wysyłam.\n"
        )
        return 1
    recipient = os.environ.get("MAINTAINER_EMAIL", "").strip() or smtp_user

    prompt_tresc, czy_llm = _przeredaguj_z_openai(title, body, labels)
    marker = "Sami (LLM)" if czy_llm else "Sami (fallback)"
    temat = f"[Reżyser Audio AI][{marker}] Issue #{number}: {title[:80]}"

    otwarte = _lista_otwartych_issues()

    pelna_tresc = (
        f"Ciao Centrum!\n\n"
        f"Sami z Południa melduje nowe zgłoszenie #{number}.\n"
        f"Link: {url}\n"
        f"Etykiety: {', '.join(labels) or '(brak)'}\n"
        f"Tryb redakcji: {marker}\n\n"
        "=========================================================\n"
        "PROMPT DLA AGENTA AI (Claude Code / Cursor / Aider)\n"
        "=========================================================\n\n"
        f"{prompt_tresc}\n\n"
        "=========================================================\n"
        "ORYGINALNY TEKST ZGŁOSZENIA (do weryfikacji)\n"
        "=========================================================\n\n"
        f"Tytuł: {title}\n\n"
        f"{body}\n\n"
        "=========================================================\n"
        "OTWARTE ISSUES W REPO (snapshot z momentu intake)\n"
        "=========================================================\n\n"
        f"{otwarte}\n\n"
        "---\n"
        "Ciao, ciao!\n"
        "Sami"
    )

    ok = _wyslij_maila(temat, pelna_tresc, recipient, smtp_user, smtp_pass)
    if ok:
        # Komentarz na issue tylko po udanej wysyłce — user nie powinien
        # dostać fałszywej obietnicy „prompt dotarł do Centrum", gdy SMTP
        # zfailowało. Sami głośna i ekspresyjna, ale uczciwa.
        _zostaw_komentarz_sami(number, body, czy_llm)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
