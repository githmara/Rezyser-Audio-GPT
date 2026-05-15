"""
issue_intake_sami.py — etap „Południe" obiegu zgłoszeń.

Reprezentantka: Sami — energiczna, ekspresyjna włoska asystentka-dyspozytorka.
Odbiera GitHub Issue, używa OpenAI do przekucia chaotycznego tekstu użytkownika
w wysoce techniczny, zwięzły prompt inżynieryjny po polsku (gotowy do wklejenia
do agenta AI typu Claude Code), a następnie wysyła ten prompt mailem do Centrum
(maintainer).

Wywołanie z workflow:
    python .github/scripts/issue_intake_sami.py \\
        "$ISSUE_TITLE" "$ISSUE_BODY" "$ISSUE_NUMBER" "$ISSUE_LABELS" "$ISSUE_URL"

Wymagane zmienne środowiskowe:
    OPENAI_API_KEY          klucz OpenAI (sekret GH Actions)
    SMTP_USER               nadawca + odbiorca (gmail dewelopera)
    SMTP_PASS               hasło aplikacji SMTP (Gmail app password)
    MAINTAINER_EMAIL        (opcjonalnie) odbiorca; fallback = SMTP_USER

Fallback: jeśli OpenAI zawiedzie (brak kredytów, 401/429, timeout) — wysyłamy
oryginalną treść zgłoszenia z notatką, że Sami chwilowo nie pomogła w
przeredagowaniu.
"""

from __future__ import annotations

import os
import smtplib
import sys
from email.message import EmailMessage


# Etykiety, które IGNORUJEMY (nie wysyłamy maila do Centrum).
LABELS_IGNORE = {
    "wontfix",
    "duplicate",
    "tiflotecnia-patch",
    "fixed-in-release",
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
    "responsabile dello smistamento delle segnalazioni nel progetto Tiflotecnia "
    "Voices (lettore audio per non vedenti, framework wxPython + NVDA, "
    "9 lingue, motore LLM per modalità interattive). "
    "Il tuo unico compito: leggere una GitHub Issue scritta da un utente "
    "(spesso caotica, in qualunque lingua) e trasformarla in un prompt "
    "tecnico, conciso e azionabile IN POLACCO, pronto da incollare in un "
    "agente AI con accesso al repository (Claude Code, Cursor, Aider).\n\n"
    "REGUŁY OBOWIĄZKOWE DLA WYJŚCIA (po polsku):\n"
    "1. Sekcja „## Cel\" — 1-2 zdania: czego dotyczy zgłoszenie i co ma\n"
    "   się zmienić.\n"
    "2. Sekcja „## Kontekst techniczny\" — punkty: typ zgłoszenia "
    "(bug/enhancement/...), prawdopodobny moduł projektu (gui_*.py / "
    "core_*.py / dictionaries/<kod>/ / runtime/ / docs/ / .github/workflows/), "
    "kroki reprodukcji (gdy bug), oczekiwane zachowanie.\n"
    "3. Sekcja „## Kryteria akceptacji\" — bullet list, co MUSI być spełnione, "
    "żeby uznać zadanie za zrobione (testy, A11y, i18n we wszystkich 9 językach, "
    "regeneracja docs gdy dotyczy).\n"
    "4. Sekcja „## Pułapki do uniknięcia\" — krótka lista znanych z CLAUDE.md "
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


def _wczytaj_argumenty() -> tuple[str, str, str, str, str]:
    if len(sys.argv) < 6:
        sys.stderr.write(
            "Użycie: issue_intake_sami.py "
            "<title> <body> <number> <labels_csv> <url>\n"
        )
        sys.exit(2)
    return (
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
        sys.argv[4],
        sys.argv[5],
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
    title, body, number, labels_csv, url = _wczytaj_argumenty()

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
    temat = f"[Tiflotecnia Voices][{marker}] Issue #{number}: {title[:80]}"

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
        "---\n"
        "Ciao, ciao!\n"
        "Sami"
    )

    ok = _wyslij_maila(temat, pelna_tresc, recipient, smtp_user, smtp_pass)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
