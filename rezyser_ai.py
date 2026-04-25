"""
rezyser_ai.py – Warstwa OpenAI dla modułu Reżyser Audio GPT.

Wydzielone z ``gui_rezyser.py`` w refaktorze wersji 13.0 — analogicznie
do ``tlumacz_ai.py`` dla Poligloty. Moduł NIE zależy od wxPython; GUI woła
go z wątku tła (``threading.Thread``) i dostaje wyniki przez callbacki
lub zwracane ``@dataclass``-y. Dzięki temu:

* Można testować logikę bez mockowania wx (użyj mock-klienta OpenAI).
* Można podmienić warstwę GUI na cokolwiek innego (web, CLI, REST API)
  bez dotykania promptów i logiki przetwarzania.

Zakres odpowiedzialności:

    * Budowa payloadu ``chat.completions`` (system prompt + sufiks kontekstowy
      + klauzula odrzucenia + wiadomości assistant z pamięci + user).
    * Wybór sufiksu kontekstowego (``startowy``/``kontynuacja``/
      ``optymalizacja``/``alarm``/``streszczenie``) na podstawie stanu
      pamięci i słów kluczowych w instrukcji użytkownika.
    * Wywołanie OpenAI z timeoutem (domyślnie 120 s dla generowania,
      60 s dla tytułów).
    * Detekcja odrzucenia modelu przez uniwersalny tag
      :data:`przepisy_rezysera.TAG_ODRZUCENIA_AI`.
    * Ekstrakcja ``<STRESZCZENIE>...</STRESZCZENIE>`` w trybie Burzy.
    * Post-processing fonetyczny (:func:`core_rezyser.zastosuj_akcenty_uniwersalne`)
      dla trybów z ``stosuj_akcenty_fonetyczne: true``.
    * Postprodukcja: iteracja po rozdziałach i nadawanie tytułów.

Publiczne API:

    import rezyser_ai as rai

    # Generowanie kolejnego fragmentu historii:
    wynik = rai.generuj_fragment(
        klient=openai_client,
        przepis=przepis_rezysera,       # PrzepisRezysera
        snapshot=proj.snapshot(),        # SnapshotProjektu
        user_text="Napisz scenę w tawernie.",
        on_postep=lambda msg, pct: print(msg, pct),
        timeout=120.0,
    )
    if wynik.odrzucone:
        # AI odmówiło – nie zapisujemy do pliku historii
        pokaz_blad("AI odrzuciło prompt.")
    elif wynik.nowe_streszczenie:
        # Burza Mózgów wygenerowała streszczenie – aktualizujemy Pamięć Długotrwałą
        proj.summary_text = wynik.nowe_streszczenie

    # Nadawanie tytułów rozdziałom:
    wynik_tyt = rai.nadaj_tytuly_rozdzialom(
        klient=openai_client,
        przepis_tytuly=przepis_postprod_tytuly,
        pelny_tekst=open("skrypty/projekt.txt").read(),
        on_postep=cb_postep,
    )
    if wynik_tyt.przerwano_bledem:
        ...

Komunikacja z GUI z wątku tła: GUI przekazuje callbacki zawinięte w
``wx.CallAfter``. Przykład:

    def _cb_postep(msg, pct):
        wx.CallAfter(self._update_postep, msg, pct)

Moduł ``openai`` importujemy leniwie – to samo podejście co w
``tlumacz_ai.py``: pozwala uruchamiać testy jednostkowe bez instalowania
SDK, gdy test używa mock-klienta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

import core_rezyser as cr
import przepisy_rezysera as pr

# ``openai`` potrzebne tylko do łapania ``RateLimitError``. Import leniwy
# wewnątrz funkcji – by testy jednostkowe mogły działać bez SDK, a samo
# wykrycie "brak SDK" zwrócić jako zwykły wyjątek do GUI.


# =============================================================================
# Typy wynikowe
# =============================================================================

PostepCallback = Callable[[str, int], None]   # (komunikat, procent 0-100)


@dataclass
class WynikGeneracji:
    """Zbiorczy rezultat :func:`generuj_fragment`.

    Attributes:
        tekst_odpowiedzi:  Surowy tekst z modelu PO post-processingu:
                           ekstrakcja ``<STRESZCZENIE>`` (w Burzy trafia
                           do ``nowe_streszczenie``), aplikacja akcentów
                           fonetycznych (w Skrypcie). Gdy ``odrzucone``
                           jest ``True`` — zawiera surową odpowiedź
                           modelu (głównie sam tag, ewentualnie z
                           fragmentami, jeśli model go nie posłuchał).
        odrzucone:         True, jeśli model zwrócił
                           :data:`przepisy_rezysera.TAG_ODRZUCENIA_AI`.
                           W tym wypadku GUI NIE powinno zapisywać tekstu
                           do pliku historii.
        nowe_streszczenie: Jeśli w trybie Burza Mózgów AI zwróciło
                           ``<STRESZCZENIE>...</STRESZCZENIE>``, tutaj
                           jest zawartość wewnątrz tagu (bez samych tagów).
                           W pozostałych trybach zawsze ``""``.
        uzyty_sufiks:      Diagnostyczne – nazwa sufiksu, który został
                           doklejony do prompt_systemowy (``"alarm"``,
                           ``"startowy"`` itd.), lub ``None`` gdy żaden.
    """

    tekst_odpowiedzi: str
    odrzucone: bool = False
    nowe_streszczenie: str = ""
    uzyty_sufiks: str | None = None


@dataclass
class WynikTytulowania:
    """Zbiorczy rezultat :func:`nadaj_tytuly_rozdzialom`.

    Attributes:
        tytuly:           Lista stringów w formacie ``"Rozdział N: Tytuł"``.
                          Zawiera częściowe wyniki nawet gdy iteracja
                          została przerwana błędem.
        przerwano_bledem: True, jeśli iteracja nie dobiegła końca
                          (RateLimitError, timeout, inny wyjątek).
        blad:             Ludzka wersja błędu do pokazania użytkownikowi.
    """

    tytuly: list[str] = field(default_factory=list)
    przerwano_bledem: bool = False
    blad: str = ""


# =============================================================================
# Wybór sufiksu kontekstowego (reguły sterujące z YAML-a)
# =============================================================================

def wybierz_sufiks(
    przepis: pr.PrzepisRezysera,
    snapshot: cr.SnapshotProjektu,
    user_text: str,
) -> str | None:
    """Zwraca nazwę sufiksu do doklejenia, lub ``None`` gdy żaden.

    Reguły (odziedziczone po logice ``_wyslij_worker`` z gui_rezyser.py,
    ale teraz opartej o flagi z YAML-a):

        * **Tryb planowania** (``zapis_do_pliku: false``, np. Burza Mózgów):
            - użytkownik wpisał słowo ze ``slowa_wyzwalajace.streszczenie``
              → doklejamy sufiks ``"streszczenie"`` (wymusza wygenerowanie
              ``<STRESZCZENIE>...</STRESZCZENIE>``);
            - pamięć ``>= PROG_OSTRZEZENIE`` → doklejamy ``"alarm"``
              (sam z siebie wymusza streszczenie, zanim zabraknie tokenów);
            - w przeciwnym razie (pamięć jest pojemna) → ``"optymalizacja"``
              (informuje AI, że NIE musi generować streszczenia).

        * **Tryby zapisu** (``zapis_do_pliku: true``, np. Skrypt):
            - gdy przepis ma zdefiniowane OBA sufiksy ``startowy``
              i ``kontynuacja``:
                * historia pusta LUB bez tagów ``[...]`` → ``"startowy"``,
                * w przeciwnym razie → ``"kontynuacja"``.
            - gdy przepis ma tylko jeden albo żaden → ``None`` (audiobook).

    Sufiks jest brany tylko gdy RZECZYWIŚCIE istnieje w ``przepis.sufiksy``
    – lingwista może w YAML-u usunąć dany sufiks, co skutecznie wyłączy
    odpowiednie zachowanie silnika (np. wyłączyć alarm dla Burzy = zawsze
    optymalizacja).
    """
    slowa_s = przepis.slowa_wyzwalajace.get("streszczenie", [])
    user_lower = (user_text or "").lower()
    zada_streszczenia = any(slowo in user_lower for slowo in slowa_s)

    # --- Tryb planowania (Burza) ---
    if not przepis.zapis_do_pliku:
        if zada_streszczenia and "streszczenie" in przepis.sufiksy:
            return "streszczenie"
        if len(snapshot.full_story) >= cr.PROG_OSTRZEZENIE:
            if "alarm" in przepis.sufiksy:
                return "alarm"
        elif "optymalizacja" in przepis.sufiksy:
            return "optymalizacja"
        return None

    # --- Tryby zapisu (Skrypt / Audiobook) ---
    if "startowy" in przepis.sufiksy and "kontynuacja" in przepis.sufiksy:
        # Uznajemy historię za "pustą" jeśli pusta LUB bez żadnych tagów
        # [Postać:] – bo sam Prolog bez dialogu nie ustawia jeszcze
        # kontekstu dla audio-ekspozycji w Skrypcie.
        if (not snapshot.full_story.strip()) or ("[" not in snapshot.full_story):
            return "startowy"
        return "kontynuacja"

    return None


# =============================================================================
# Budowa payloadu OpenAI
# =============================================================================

def buduj_payload(
    przepis: pr.PrzepisRezysera,
    snapshot: cr.SnapshotProjektu,
    user_text: str,
) -> tuple[list[dict], str | None]:
    """Buduje listę wiadomości ``chat.completions`` + zwraca użyty sufiks.

    Kolejność wiadomości (istotna dla modelu):

        1. ``role=system``  – pełny prompt systemowy
           (baza + sufiks + klauzula odrzucenia).
        2. ``role=assistant`` – streszczenie (gdy niepuste).
        3. ``role=assistant`` – obecna fabuła (gdy niepusta).
        4. ``role=user``    – instrukcja użytkownika + przypomnienie z YAML-a.

    Returns:
        Krotka ``(messages, nazwa_sufiksu)``. Druga wartość jest
        diagnostyczna i trafia do :class:`WynikGeneracji.uzyty_sufiks`.
    """
    sufiks_nazwa = wybierz_sufiks(przepis, snapshot, user_text)

    system_prompt = pr.buduj_pelny_prompt_systemowy(
        przepis,
        world_context=snapshot.world_lore,
        sufiks_nazwa=sufiks_nazwa,
    )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    if snapshot.summary_text.strip():
        messages.append({
            "role": "assistant",
            "content": f"[STRESZCZENIE POPRZEDNICH WYDARZEŃ]:\n{snapshot.summary_text}",
        })

    if snapshot.full_story.strip():
        messages.append({
            "role": "assistant",
            "content": f"[OBECNA FABUŁA]:\n{snapshot.full_story}",
        })

    przypom = pr.buduj_przypomnienie(przepis)
    messages.append({"role": "user", "content": user_text + przypom})

    return messages, sufiks_nazwa


# =============================================================================
# Ekstrakcja <STRESZCZENIE> (tylko Burza Mózgów)
# =============================================================================

_RE_STRESZCZENIE = re.compile(
    r"<STRESZCZENIE>(.*?)</STRESZCZENIE>",
    re.DOTALL | re.IGNORECASE,
)


def wyciagnij_streszczenie(tekst: str) -> tuple[str, str]:
    """Usuwa ``<STRESZCZENIE>...</STRESZCZENIE>`` z tekstu i zwraca oba.

    Returns:
        Krotka ``(tekst_bez_streszczenia, sama_tresc_streszczenia)``.
        Jeśli tagu nie ma – zwraca ``(tekst, "")``.
    """
    m = _RE_STRESZCZENIE.search(tekst)
    if not m:
        return tekst, ""
    streszczenie = m.group(1).strip()
    tekst_bez = _RE_STRESZCZENIE.sub("", tekst).strip()
    return tekst_bez, streszczenie


# =============================================================================
# Główna funkcja: generowanie fragmentu historii
# =============================================================================

def generuj_fragment(
    klient: Any,
    przepis: pr.PrzepisRezysera,
    snapshot: cr.SnapshotProjektu,
    user_text: str,
    on_postep: PostepCallback | None = None,
    timeout: float = 120.0,
) -> WynikGeneracji:
    """Wysyła zapytanie do OpenAI i zwraca przetworzoną odpowiedź.

    Args:
        klient:     Klient OpenAI (``OpenAI(api_key=...)``).
        przepis:    Tryb pracy (Burza / Skrypt / Audiobook).
        snapshot:   Niezmienny snapshot stanu projektu.
        user_text:  Instrukcja użytkownika z pola „Instrukcje".
        on_postep:  Opcjonalny callback postępu (msg, procent).
        timeout:    Limit czasu na wywołanie OpenAI w sekundach.
                    Uwaga: obejmuje **cały** czas od wysłania do
                    otrzymania pełnej odpowiedzi. Dla długich generacji
                    audiobookowych można podnieść.

    Returns:
        :class:`WynikGeneracji` – GUI sprawdza ``.odrzucone`` i
        ``.nowe_streszczenie`` decydując, co zrobić z odpowiedzią.

    Raises:
        Wyjątki OpenAI (``RateLimitError``, ``APITimeoutError``,
        ``APIError``) są propagowane – GUI pokazuje je w dialogu błędu.
    """
    if on_postep:
        on_postep("Budowanie payloadu do AI…", 10)

    messages, sufiks_nazwa = buduj_payload(przepis, snapshot, user_text)

    if on_postep:
        on_postep(f"Wysyłanie do {przepis.model}…", 30)

    response = klient.chat.completions.create(
        model=przepis.model,
        messages=messages,
        temperature=przepis.temperatura,
        timeout=timeout,
    )
    tekst: str = response.choices[0].message.content or ""

    if on_postep:
        on_postep("Przetwarzanie odpowiedzi…", 80)

    # 1) Detekcja odrzucenia — przed wszystkim innym. Tag infrastruktury
    # jest wymuszany przez KLAUZULA_ODRZUCENIA_DOMYSLNA niezależnie od
    # jezyk_odpowiedzi, więc działa tak samo dla fińskiego i japońskiego.
    if pr.wykryto_odrzucenie(tekst):
        if on_postep:
            on_postep("AI odrzuciło prompt (tag wykryty).", 100)
        return WynikGeneracji(
            tekst_odpowiedzi=tekst,
            odrzucone=True,
            uzyty_sufiks=sufiks_nazwa,
        )

    # 2) Ekstrakcja <STRESZCZENIE> — tylko w trybach planowania (Burza).
    # Tryby zapisu nie powinny nigdy zwracać tego tagu, bo klauzula
    # w prompt_systemowy tego nie wymusza; ale jeśli model je doda, to
    # zostają w tekście. To mniej istotne niż brak streszczenia w Burzy.
    nowe_streszczenie = ""
    if not przepis.zapis_do_pliku:
        tekst, nowe_streszczenie = wyciagnij_streszczenie(tekst)

    # 3) Akcenty fonetyczne — tylko gdy przepis tego wymaga (Skrypt).
    # 13.3: ``zastosuj_akcenty_uniwersalne`` przyjmuje teraz ``jezyk_projektu``
    # (default "pl"). Tu zostawiamy default — gdy pojawi się odrębne pole
    # „język projektu" w stanie reżysera (kandydat na 13.x), przekazujemy
    # ``jezyk_projektu=snapshot.jezyk`` lub równoważne.
    if przepis.stosuj_akcenty_fonetyczne:
        tekst = cr.zastosuj_akcenty_uniwersalne(tekst, snapshot.world_lore)

    if on_postep:
        on_postep("Gotowe.", 100)

    return WynikGeneracji(
        tekst_odpowiedzi=tekst,
        odrzucone=False,
        nowe_streszczenie=nowe_streszczenie,
        uzyty_sufiks=sufiks_nazwa,
    )


# =============================================================================
# Postprodukcja: nadawanie tytułów rozdziałom
# =============================================================================

def nadaj_tytuly_rozdzialom(
    klient: Any,
    przepis_tytuly: pr.PrzepisRezysera,
    pelny_tekst: str,
    on_postep: PostepCallback | None = None,
    timeout: float = 60.0,
) -> WynikTytulowania:
    """Iteruje po rozdziałach pliku projektu i generuje tytuł dla każdego.

    Algorytm:
        1. Dzielimy ``pelny_tekst`` regexem ``regex_podzial_rozdzialow``
           z YAML-a (domyślnie: Prolog / Rozdział N / Epilog).
        2. Dla każdego fragmentu:
           - jeśli za krótki (< ``min_dlugosc_fragmentu``) → dopisujemy
             etykietę "Fragment zbyt krótki" bez wywołania AI;
           - w przeciwnym razie wysyłamy ``prompt_uzytkownika_szablon``
             z placeholderami ``{naglowek}`` i ``{probka}`` (pierwsze
             ``max_dlugosc_probki`` znaków rozdziału).
        3. Jeśli AI odpowie tagiem odrzucenia – dopisujemy "(Odrzucenie AI)".
        4. RateLimitError → wracamy wcześniej z częściowymi tytułami
           i flagą ``przerwano_bledem=True``.

    Używane tylko w trybie Audiobook (postprodukcja tekstu, bez wpływu
    na plik historii). Wynik prezentowany w dialogu, by użytkownik mógł
    skopiować tytuły do Księgi Świata / spisu treści.
    """
    # Import leniwy – tylko tu potrzebujemy wyjątków OpenAI
    import openai  # noqa: PLC0415

    wzorzec = przepis_tytuly.regex_podzial_rozdzialow
    fragmenty = re.split(wzorzec, pelny_tekst)

    if len(fragmenty) <= 1:
        return WynikTytulowania(
            tytuly=[],
            przerwano_bledem=True,
            blad=(
                "Nie znaleziono tagów struktury (Prolog / Rozdział N / Epilog) "
                "w pliku. Wstaw cięcia rozdziałów przed nadaniem tytułów."
            ),
        )

    tytuly: list[str] = []
    iter_idx = list(range(1, len(fragmenty), 2))
    total = len(iter_idx)

    system_prompt = pr.buduj_prompt_systemowy(przepis_tytuly)

    for step, i in enumerate(iter_idx, start=1):
        naglowek = fragmenty[i].strip()
        tresc = fragmenty[i + 1].strip() if i + 1 < len(fragmenty) else ""
        percent = int(step / total * 100)

        if on_postep:
            on_postep(f"Tytułowanie: {naglowek} ({step}/{total})…", percent)

        # Fragmenty krótsze niż próg – pomijamy, nie marnujemy kredytów
        if len(tresc) < przepis_tytuly.min_dlugosc_fragmentu:
            tytuly.append(
                f"{naglowek}: {przepis_tytuly.etykieta_fragment_zbyt_krotki}"
            )
            continue

        probka = tresc[:przepis_tytuly.max_dlugosc_probki]
        user_prompt = pr.buduj_prompt_uzytkownika(
            przepis_tytuly, naglowek=naglowek, probka=probka,
        )

        try:
            resp = klient.chat.completions.create(
                model=przepis_tytuly.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=przepis_tytuly.temperatura,
                timeout=timeout,
            )
            tytul_raw = (resp.choices[0].message.content or "").strip()

            # Nawet model tytułujący może odrzucić prompt (szczególnie przy
            # brutalnych treściach w treści rozdziału). Honorujemy tag.
            if pr.wykryto_odrzucenie(tytul_raw):
                tytuly.append(f"{naglowek}: (Odrzucenie AI)")
            else:
                tytuly.append(f"{naglowek}: {tytul_raw}")

        except openai.RateLimitError:
            tytuly.append(
                f"{naglowek}: {przepis_tytuly.etykieta_bled_brak_kredytow}"
            )
            return WynikTytulowania(
                tytuly=tytuly,
                przerwano_bledem=True,
                blad="Brak kredytów OpenAI! Doładuj konto i spróbuj ponownie.",
            )
        except Exception as exc:  # noqa: BLE001
            tytuly.append(f"{naglowek}: (Błąd – {exc})")
            return WynikTytulowania(
                tytuly=tytuly,
                przerwano_bledem=True,
                blad=str(exc),
            )

    return WynikTytulowania(tytuly=tytuly, przerwano_bledem=False, blad="")
