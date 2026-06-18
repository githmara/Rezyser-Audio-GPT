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
import re
import smtplib
import subprocess
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage

import bot_i18n


# Nagłówek crash-loga generowanego przez globalny handler wyjątków aplikacji
# (`main._zapisz_log_bledu` → stała `main.CRASH_MARKER`). Trzymamy własną kopię
# literału, bo ten skrypt to samodzielny entrypoint workflowa GH Actions i nie
# importuje `main`. Użyte przez `_oczysc_tekst_dla_lingua` (przez `re.escape`,
# żeby em-dash „—" nie wymagał ręcznego przepisania w regexie).
_CRASH_HEADER = "=== REŻYSER AUDIO GPT — CRASH REPORT ==="


def _oczysc_tekst_dla_lingua(issue_body: str) -> str:
    """Wycina techniczne bloki (crash-log, traceback, bloki kodu) oraz linki,
    zostawiając naturalny tekst użytkownika do detekcji języka przez Lingua.

    Powód: detektor n-gramowy myli się na surowym tracebacku (angielskie nazwy
    wyjątków, ścieżki Windows, fragmenty kodu) oraz na markdownowych linkach.

    KRYTYCZNE dla scenariusza ZAŁĄCZONEGO pliku: GitHub NIE wkleja treści
    załącznika do `body` — wstawia tylko link
    `[error_log.txt](https://.../files/.../error_log.txt)`. Dlatego crash
    zgłoszony przez załączenie pliku nie ma w `body` markerów tracebacku, a samo
    body to (link + opcjonalny opis usera). Po wycięciu linków:
      * gołe załączenie bez opisu → pusty string → caller spada na angielski;
      * załączenie + natywny opis usera → zostaje opis → Lingua wykryje jego
        prawdziwy język (komentarz Sami będzie w języku usera, nie sztywno EN).
    """
    if not issue_body:
        return ""
    tekst = issue_body
    # 1. Markdownowe bloki kodu ``` ... ``` (typowa wklejka logu/tracebacku).
    tekst = re.sub(r"```.*?```", " ", tekst, flags=re.DOTALL)
    # 2. Pełny blok CRASH REPORT: od nagłówka do stopki „====" (60×'=' z
    #    `_zapisz_log_bledu`) LUB do końca tekstu, gdy user wkleił sam fragment
    #    bez stopki (`\Z` ratuje przed regresją „nic nie wycięte").
    tekst = re.sub(
        re.escape(_CRASH_HEADER) + r".*?(?:={10,}|\Z)",
        " ", tekst, flags=re.DOTALL,
    )
    # 3. Surowy traceback Pythona (nawet wklejony bez nagłówka pliku): od
    #    sygnatury do pustej linii albo końca tekstu.
    tekst = re.sub(
        r"Traceback \(most recent call last\):.*?(?=\n\s*\n|\Z)",
        " ", tekst, flags=re.DOTALL,
    )
    # 4. Linki markdown (w tym do załączonych plików-logów) i gołe URL-e —
    #    w całości, żeby host „github.com" ani nazwa pliku nie zaśmiecały Lingui.
    tekst = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", tekst)
    tekst = re.sub(r"https?://\S+", " ", tekst)
    return tekst.strip()


# Komentarz Sami: klucz bot.sami_comment w ui.yaml, renderowany przez
# bot_i18n.t_bot — patrz docstring modułu.


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


# --- Pobieranie treści ZAŁĄCZONYCH plików (od v17.11.2) --------------------
# GitHub NIE wkleja treści załącznika do `body` issue — wstawia tylko link
# markdown `[error_log.txt](https://github.com/user-attachments/files/…)`. Bez
# pobrania tej treści LLM (gpt-4o-mini) dostaje sam URL, którego NIE odwiedzi,
# więc crash zgłoszony przez ZAŁĄCZENIE pliku (a dialog crashu w aplikacji
# wprost do tego zachęca: „ZAŁĄCZ ten plik") dawałby pusty prompt do Centrum
# („Zgłoszenie wymaga doprecyzowania") + wesoły komentarz Sami = rozczarowany
# user. Dlatego runner Actions (pełny internet + GITHUB_TOKEN) pobiera tekstowe
# załączniki i inline'uje je do promptu LLM ORAZ do maila. Repo PUBLICZNE →
# zwykły GET wystarcza; token dokładamy jako nagłówek-fallback (nieszkodliwy
# przy publicznym, ratuje gdyby asset kiedyś wymagał auth). Patrz [[reguly_github_bot]].

# Rozszerzenia, których treść umiemy sensownie inline'ować (tekstowe).
_ZALACZNIK_TEKST_EXT = (
    ".txt", ".log", ".md", ".json", ".yaml", ".yml", ".csv", ".ini",
    ".cfg", ".py", ".traceback", ".out", ".err",
)
# Wzorzec URL-a załącznika GitHub (odróżnia od zwykłego linku w prozie usera).
_ZALACZNIK_URL = re.compile(
    r"https?://("
    r"github\.com/user-attachments/[^\s)]+"          # nowy format (files/ i assets/)
    r"|github\.com/[^\s)]+/files/[^\s)]+"             # legacy [owner]/[repo]/files/id/nazwa
    r"|[a-z0-9.-]*githubusercontent\.com/[^\s)]+"     # CDN (user-images, objects)
    r")",
    re.IGNORECASE,
)
_ZALACZNIK_MAX_BAJTY = 60_000        # cap na pojedynczy plik (ochrona maila + LLM)
_ZALACZNIK_LIMIT_PLIKOW = 5          # max liczba pobieranych załączników


def _wykryj_linki_zalacznikow(issue_body: str) -> list[tuple[str, str]]:
    """Zwraca [(nazwa, url)] dla linków wskazujących na załączniki GitHub.

    Skanuje linki markdown `[label](url)` / `![label](url)` ORAZ gołe URL-e.
    `nazwa` = etykieta markdown albo ostatni segment ścieżki URL. Dedup po URL.
    """
    if not issue_body:
        return []
    znalezione: list[tuple[str, str]] = []
    widziane: set[str] = set()

    def _dodaj(nazwa: str, url: str) -> None:
        url = url.rstrip(").,;")
        if url in widziane or not _ZALACZNIK_URL.match(url):
            return
        widziane.add(url)
        nazwa = (nazwa or url.rsplit("/", 1)[-1]).strip()
        znalezione.append((nazwa, url))

    for m in re.finditer(r"!?\[([^\]]*)\]\((https?://[^)\s]+)\)", issue_body):
        _dodaj(m.group(1), m.group(2))
    for m in _ZALACZNIK_URL.finditer(issue_body):
        _dodaj("", m.group(0))
    return znalezione


def _czy_tekstowy(nazwa: str, url: str) -> bool:
    """Czy załącznik ma rozszerzenie tekstowe (po nazwie markdown albo URL-u)?"""
    cel = (nazwa or url).lower().rsplit("/", 1)[-1].split("?")[0]
    return cel.endswith(_ZALACZNIK_TEKST_EXT)


def _pobierz_zalacznik(url: str) -> tuple[str | None, str | None]:
    """GET treści załącznika. Zwraca (tekst, błąd) — dokładnie jedno jest None.

    Cap na `_ZALACZNIK_MAX_BAJTY` (czytamy +1 bajt, żeby wykryć obcięcie).
    Token GH dokładamy jako nagłówek-fallback (repo publiczne → i tak zbędny).
    """
    naglowki = {"User-Agent": "RezyserAudio-Sami-intake"}
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        naglowki["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=naglowki)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            surowe = resp.read(_ZALACZNIK_MAX_BAJTY + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"pobranie nie powiodło się ({exc})"
    obciete = len(surowe) > _ZALACZNIK_MAX_BAJTY
    tekst = surowe[:_ZALACZNIK_MAX_BAJTY].decode("utf-8", errors="replace").strip()
    if obciete:
        tekst += "\n…[treść obcięta przez Sami do limitu]"
    return (tekst or "(plik pusty)"), None


def _zbierz_tresc_zalacznikow(issue_body: str) -> str:
    """Blok z treścią pobranych załączników (lub notatkami). '' gdy brak linków.

    Tekstowe pobiera i inline'uje; nietekstowe (obrazy/zip) tylko WYMIENIA, żeby
    Centrum wiedziało, że trzeba je obejrzeć ręcznie. Nigdy nie rzuca — błąd
    pobrania ląduje jako notatka przy linku (graceful degradation).
    """
    linki = _wykryj_linki_zalacznikow(issue_body)
    if not linki:
        return ""
    sekcje: list[str] = []
    pobrane = 0
    for nazwa, url in linki:
        if not _czy_tekstowy(nazwa, url):
            sekcje.append(f"### {nazwa} (nietekstowy — nie pobrano, obejrzyj ręcznie)\n{url}")
            continue
        if pobrane >= _ZALACZNIK_LIMIT_PLIKOW:
            sekcje.append(
                f"### {nazwa} (pominięto — limit {_ZALACZNIK_LIMIT_PLIKOW} plików)\n{url}"
            )
            continue
        pobrane += 1
        tekst, blad = _pobierz_zalacznik(url)
        if blad:
            sekcje.append(f"### {nazwa} ({blad})\n{url}")
        else:
            sekcje.append(f"### {nazwa}\n{url}\n---\n{tekst}")
    return "\n\n".join(sekcje)


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

    Język komentarza wykrywany Lingua-language-detector'em na ciele issue PO
    wycięciu bloków technicznych i linków (`_oczysc_tekst_dla_lingua`) — te same
    9 jzk co reszta obiegu. Crash-report bez opisu / gołe załączenie pliku-loga
    zwijają się po czyszczeniu do pustego stringa → uniwersalny angielski; crash
    z natywnym opisem usera zachowuje język opisu. Brak komentarza dla
    LABELS_IGNORE (skrypt nie dochodzi tu — wcześniejszy return 0).

    `czy_llm` decyduje czy doklejamy sufiks o fallbacku LLM. User powinien
    wiedzieć, że Sami nie pomogła z przeredagowaniem, żeby nie czekał na cudowny
    fix gdy zgłoszenie jest niezrozumiałe.
    """
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        sys.stderr.write(
            "[!] Brak GITHUB_REPOSITORY w env — pomijam komentarz Sami.\n"
        )
        return

    czysty = _oczysc_tekst_dla_lingua(issue_body)
    # Po wycięciu logów/linków za mało tekstu (czysty traceback bez opisu, samo
    # „fix", gołe załączenie pliku) → None → t_bot na uniwersalny EN. Inaczej
    # wykrywamy język realnego opisu usera (detektor dynamiczny z podstawy.yaml).
    wykryty = bot_i18n.wykryj(czysty) if len(czysty) >= 5 else None

    tresc = bot_i18n.t_bot("bot.sami_comment", wykryty)
    if not czy_llm:
        # Sufiks per język byłby przerostem — pojedyncza krótka angielska
        # adnotacja w nawiasie wystarczy do sygnału „uważaj, fallback".
        # User i tak rzuci okiem na mail jeśli zechce sprawdzić co Centrum
        # dostało.
        tresc += "\n\n*(LLM fallback — original body forwarded raw.)*"

    if _gh(["gh", "issue", "comment", issue_number, "--repo", repo,
            "--body", tresc]):
        print(f"Komentarz Sami dodany do issue #{issue_number} "
              f"(język: {bot_i18n.kod_iso(wykryty)}).")


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

    # Pobierz treść załączonych plików (GitHub trzyma w body tylko link) —
    # inline'ujemy do promptu LLM, żeby gpt-4o-mini miał na czym pracować, oraz
    # do maila, żeby Centrum widziało log bez ręcznego klikania w URL.
    zalaczniki_tresc = _zbierz_tresc_zalacznikow(body)
    if zalaczniki_tresc:
        print(f"Sami pobrała załączniki issue #{number} ({len(zalaczniki_tresc)} znaków).")
        body_dla_llm = (
            f"{body}\n\n"
            "# Treść załączonych plików (pobrana przez Sami — NIE była w body issue)\n"
            f"{zalaczniki_tresc}"
        )
    else:
        body_dla_llm = body

    prompt_tresc, czy_llm = _przeredaguj_z_openai(title, body_dla_llm, labels)
    marker = "Sami (LLM)" if czy_llm else "Sami (fallback)"
    temat = f"[Reżyser Audio AI][{marker}] Issue #{number}: {title[:80]}"

    otwarte = _lista_otwartych_issues()

    blok_zalacznikow = (
        "\n--- Treść załączników pobrana przez Sami "
        "(NIE jest częścią body issue) ---\n"
        f"{zalaczniki_tresc}\n"
    ) if zalaczniki_tresc else ""

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
        f"{body}\n"
        f"{blok_zalacznikow}\n"
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
