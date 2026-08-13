"""
rezyser_ai.py – Warstwa Anthropic Claude dla modułu Reżyser Audio GPT.

Wydzielone z ``gui_rezyser.py`` w refaktorze wersji 13.0 — analogicznie
do ``tlumacz_ai.py`` dla Poligloty. Moduł NIE zależy od wxPython; GUI woła
go z wątku tła (``threading.Thread``) i dostaje wyniki przez callbacki
lub zwracane ``@dataclass``-y. Dzięki temu:

* Można testować logikę bez mockowania wx (użyj mock-klienta Anthropic).
* Można podmienić warstwę GUI na cokolwiek innego (web, CLI, REST API)
  bez dotykania promptów i logiki przetwarzania.

Zakres odpowiedzialności:

    * Budowa payloadu Messages API (prompt systemowy w parametrze ``system=``
      + sufiks kontekstowy + klauzula odrzucenia + kontekst pamięci złożony
      w wiadomość ``user`` — Anthropic wymaga pierwszej wiadomości ``user``).
    * Wybór sufiksu kontekstowego (``startowy``/``kontynuacja``/
      ``optymalizacja``/``alarm``/``streszczenie``) na podstawie stanu
      pamięci i słów kluczowych w instrukcji użytkownika.
    * Wywołanie Claude (Messages API) z timeoutem (domyślnie 120 s dla
      generowania, 60 s dla tytułów) — przez ``klient.with_options(timeout=...)``.
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
        klient=anthropic_client,
        przepis=przepis_rezysera,       # PrzepisRezysera
        snapshot=proj.snapshot(),        # SnapshotProjektu
        user_text="Napisz scenę w tawernie.",
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
        klient=anthropic_client,
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

Moduł ``anthropic`` importujemy leniwie – to samo podejście co w
``tlumacz_ai.py``: pozwala uruchamiać testy jednostkowe bez instalowania
SDK, gdy test używa mock-klienta.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

import jsonschema

import core_llm as cl
import core_poliglota as cp
import core_rezyser as cr
import i18n
import przepisy_rezysera as pr
from bledy_ai import BladDlugosciOdpowiedzi, BladStrukturyJSON


def _dev_log(msg: str) -> None:
    """Strażowany print diagnostyczny (jak `core_rezyser._dev_log_runtime`) —
    w paczce release `sys.stdout` bywa None, goły print mógłby ubić apkę."""
    try:
        if sys.stdout is not None:
            print(f"[rezyser_ai] {msg}")
    except Exception:  # noqa: BLE001 — log dev nigdy nie ubija apki
        pass

# Warstwę API LLM (budowa klienta + wywołanie + normalizacja błędów) trzyma
# `core_llm` — moduł SDK-agnostyczny (Anthropic albo OpenAI-compat). Tutaj
# wołamy wyłącznie `cl.wywolaj_llm(...)` i łapiemy `cl.BladLimituLLM`; SDK
# konkretnego providera nie jest tu importowane.


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
        ostrzezenie:       Niepusty tekst miękkiego ostrzeżenia dla reżysera,
                           gdy odpowiedź urwała się na ``max_tokens`` i NIE
                           udało się jej domknąć mikro-callem (sprawa #1).
                           GUI pokazuje go po zapisie — zapis i tak przechodzi
                           (tekst jest zachowany w obecnej postaci). Pusty =
                           wszystko OK (brak ucięcia albo domknięte czysto).
    """

    tekst_odpowiedzi: str
    odrzucone: bool = False
    nowe_streszczenie: str = ""
    uzyty_sufiks: str | None = None
    ostrzezenie: str = ""


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
# Burza Mózgów (v15.2): strukturyzowane JSON wyjście + przyciski opcji
# =============================================================================
# Do v15.1 tryb Burza zwracał plain text w formacie „OPCJA 1: ... [Krótki tytuł]
# / opis / blok kodu z [CEL SCENY], [Reżyserze: ...], [DYREKTYWA]: ..." — całość
# wpisaną przez LLM. Skutki uboczne:
# - LLM regularnie ignorował zakaz „nie wymyślaj instrukcji o uwagach od
#   reżysera" i halucynował własne zwroty ([Reżyserze, rozważ kątem...]),
#   przez co kontrakt na wpinanie się tych linijek do GUI był zawodny.
# - Parsowanie tego pseudo-formatu w GUI wymagałoby regexa nad treścią
#   LLM-a (kruche), więc nie było zrobione i gracz musiał przeklejać.
#
# v15.2: LLM zwraca STRUKTURYZOWANY JSON z 3 opcjami; każda zawiera
# `cel_sceny` (treść celowa, którą LLM wymyślił). Linijki `[Reżyserze: ...]` i
# `[DYREKTYWA]: ...` doklejane są W PYTHONIE z lokalizowanej stałej w
# `dictionaries/<jezyk>/rezyser/tryb_burza.yaml::doklejka_celu_sceny` — Python
# kontroluje treść tych instrukcji deterministycznie, LLM nie ma jak ich zepsuć.
# GUI po wynikach generacji buduje przyciski 1/2/3; klik wstawia pełny szkic
# prompta do pola Instrukcji (gracz dopisuje swoje uwagi reżyserskie).
# -----------------------------------------------------------------------------

SCHEMA_BURZA: dict[str, Any] = {
    "type": "object",
    "required": ["opcje"],
    "additionalProperties": False,
    "properties": {
        # Streszczenie pojawia się TYLKO gdy sufiks "streszczenie"/"alarm" był
        # aktywny. W normalnej turze klucz jest pusty stringiem albo nieobecny
        # — GUI traktuje brak/"" tak samo. Sentinel pozwala odróżnić „LLM celowo
        # nie wygenerował" (pusty string) od „pamięć była pełna i streszczenie
        # jest" (niepusty string).
        "streszczenie": {"type": "string"},
        "opcje": {
            "type": "array",
            "minItems": 1,   # liberalnie — yaml mówi 3, ale halucynacja 2 nie powinna blokować GUI
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": ["tytul", "opis", "cel_sceny"],
                "additionalProperties": False,
                "properties": {
                    # Krótki tytuł opcji (max ~80 znaków). Wyświetlany na
                    # przycisku w GUI: „1. {tytul}".
                    "tytul":     {"type": "string", "minLength": 1, "maxLength": 200},
                    # Logiczny opis tego co się stanie w opcji (1-3 zdania).
                    # Trafia jako podpowiedź / tooltip + nad polem instrukcji
                    # gdy gracz wybierze opcję.
                    "opis":      {"type": "string", "minLength": 1},
                    # Konkretna treść do wpisania jako [CEL SCENY]: w polu
                    # Instrukcji. Powinna być GŁĘBSZA niż `opis` — szczegół
                    # akcji/dialogu, który LLM proponuje. To jest jedyna treść
                    # twórcza od LLM trafiająca do pola gracza.
                    "cel_sceny": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}


@dataclass
class OpcjaBurzy:
    """Pojedyncza opcja wygenerowana przez Burzę.

    Attributes:
        tytul:     Krótki tytuł (do przycisku „1. {tytul}" w GUI).
        opis:      Logiczny opis co się stanie (do tooltipa / nagłówka).
        cel_sceny: Konkretny szkic celu sceny — to jedyna treść LLM-a
                   trafiająca do pola Instrukcji po kliknięciu opcji.
    """
    tytul:     str
    opis:      str
    cel_sceny: str


@dataclass
class WynikBurzy:
    """Wynik :func:`generuj_burze` — strukturyzowana odpowiedź Burzy.

    Attributes:
        opcje:             Lista 1-5 :class:`OpcjaBurzy` (yaml wymaga 3,
                           ale schemę zostawiamy liberalną — halucynacja
                           2 nie powinna blokować GUI).
        streszczenie:      Niepusty string gdy sufiks streszczenie/alarm
                           był aktywny; pusty gdy LLM celowo nie generował.
        odrzucone:         True jeśli LLM zwrócił sam tag ``[ODRZUCENIE_AI]``
                           zamiast JSON-a (klauzula odmowy zadziałała).
        uzyty_sufiks:      Diagnostyczne — nazwa sufiksu doklejonego do
                           prompt_systemowy (``"alarm"``/``"streszczenie"``/
                           ``"optymalizacja"``/``None``).
        surowy_json:       Sucha odpowiedź modelu (do logu / debugowania).
    """
    opcje:        list[OpcjaBurzy] = field(default_factory=list)
    streszczenie: str = ""
    odrzucone:    bool = False
    uzyty_sufiks: str | None = None
    surowy_json:  str = ""


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
            - w przeciwnym razie (pamięć jest pojemna) → ``None``
              (brak sufiksu; dawny „optymalizacja" zniesiony — był szumem,
              instruował AI o czymś, czego i tak domyślnie nie robi).

        * **Tryby zapisu** (``zapis_do_pliku: true``, np. Skrypt):
            - gdy przepis ma zdefiniowane OBA sufiksy ``startowy``
              i ``kontynuacja``:
                * historia pusta LUB bez tagów ``[...]`` → ``"startowy"``,
                * w przeciwnym razie → ``"kontynuacja"``.
            - gdy przepis ma tylko jeden albo żaden → ``None`` (audiobook).

    Sufiks jest brany tylko gdy RZECZYWIŚCIE istnieje w ``przepis.sufiksy``
    – lingwista może w YAML-u usunąć dany sufiks, co skutecznie wyłączy
    odpowiednie zachowanie silnika (np. wyłączyć alarm dla Burzy = zawsze
    bez sufiksu).
    """
    slowa_s = przepis.slowa_wyzwalajace.get("streszczenie", [])
    user_lower = (user_text or "").lower()
    zada_streszczenia = any(slowo in user_lower for slowo in slowa_s)

    # --- Tryb planowania (Burza) ---
    if not przepis.zapis_do_pliku:
        if zada_streszczenia and "streszczenie" in przepis.sufiksy:
            return "streszczenie"
        # v15.1: pamięć liczymy w tokenach przez `core_tokeny` (był len-w-znakach).
        tokeny  = cr.policz_tokeny_payloadu_snapshot(snapshot)
        udzial  = tokeny / cr.OKNO_KONTEKSTU_MAX
        if udzial >= cr.PROG_OSTRZEZENIE:
            if "alarm" in przepis.sufiksy:
                return "alarm"
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
# Budowa payloadu Anthropic (Claude) + wywołanie Messages API
# =============================================================================

# Maks. tokenów wyjścia trybów narracyjnych Claude (audiobook/skrypt/burza).
# Ceiling, nie target — pod progiem non-streaming SDK (brak ryzyka HTTP-timeoutu).
MAX_TOKENS_NARRACJA = 16000

# Maks. tokenów wyjścia postprodukcji tytułów (konsolidacja v18.x na Anthropic):
# tytuł to jedna krótka linia, więc 256 z dużym zapasem. Anthropic wymaga jawnego
# `max_tokens` (w OpenAI był domyślny). Mikro-call ISO ma własny, jeszcze mniejszy.
MAX_TOKENS_TYTUL = 256

# Maks. tokenów mikro-callu domykającego urwane zdanie (sprawa #1). Jedno zdanie
# to kilkadziesiąt–kilkaset znaków; 300 z zapasem. Osobny, mały ceiling — domknięcie
# nie ma prawa znów spuchnąć do rozmiarów narracji (inaczej samo by się ucięło).
MAX_TOKENS_DOMKNIECIE = 300

# Granica długości urwanego ogona zdania, powyżej której rezygnujemy z
# automatycznego domknięcia (detekcja granicy zdania najpewniej zawiodła —
# „zdanie" na 2000+ znaków to artefakt). Lepiej miękko ostrzec reżysera niż
# przepisywać mikro-callem wielką partię tekstu (ryzyko parafrazy/utraty treści).
MAX_ZNAKOW_URWANEGO_ZDANIA = 2000


def _wywolaj_claude(
    klient:   Any,
    przepis:  pr.PrzepisRezysera,
    system:   str,
    messages: list[dict],
    timeout:  float,
    segmenty: list[dict] | None = None,
    wymusz_json: bool = False,
) -> tuple[str, str | None]:
    """Wywołuje warstwę LLM (proza, BEZ reasoningu) → (tekst, stop_reason).

    ``thinking=disabled`` — tryby narracyjne to czysta proza/JSON, reasoning tylko
    dodawałby latencję i koszt. ``temperature`` z przepisu (Sonnet 4.6 ją honoruje
    jako jedyny parametr próbkowania — bez ``top_p``). Timeout per-wywołanie przez
    ``with_options`` (SDK Anthropic nie przyjmuje ``timeout=`` na ``messages.create``).

    ``segmenty`` (role pre-v18 dla ``openai_compat``) przekazujemy bez zmian — na
    Anthropic są ignorowane, więc nazwa „Claude" w sygnaturze jest historyczna.
    """
    return cl.wywolaj_llm(
        klient,
        model=przepis.model,
        system=system,
        messages=messages,
        max_tokens=MAX_TOKENS_NARRACJA,
        temperature=przepis.temperatura,
        timeout=timeout,
        segmenty=segmenty,
        wymusz_json=wymusz_json,
    )


def buduj_payload(
    przepis: pr.PrzepisRezysera,
    snapshot: cr.SnapshotProjektu,
    user_text: str,
) -> tuple[str, list[dict], list[dict], str | None]:
    """Buduje ``(system_prompt, messages, segmenty, sufiks)`` dla warstwy LLM.

    Anthropic rozdziela prompt systemowy (parametr ``system=``) od ``messages``
    i wymaga, by PIERWSZA wiadomość miała ``role=user``. Kontekst poprzednich
    wydarzeń (streszczenie + dotychczasowa fabuła) składamy w JEDNĄ wiadomość
    ``user`` razem z instrukcją (``messages``) — to jest payload Anthropic, filar
    jakości, bez zmian. Kotwice (``[STRESZCZENIE...]``, ``[OBECNA FABUŁA]:``)
    zostają w treści dosłownie, więc referencje z ``tryb_burza.yaml`` działają.

    RÓWNOLEGLE budujemy ``segmenty`` z PRAWDZIWYMI rolami (streszczenie + fabuła →
    ``assistant``, instrukcja → ``user``) — czyta je wyłącznie gałąź ``openai_compat``
    w :func:`core_llm.wywolaj_llm`, przywracając rozdział ról sprzed v18 (kontekst
    jako wypowiedź modelu) na cudzych endpointach. Anthropic ``segmenty`` ignoruje.

    Returns:
        Krotka ``(system_prompt, messages, segmenty, nazwa_sufiksu)``. Czwarta
        wartość jest diagnostyczna i trafia do :class:`WynikGeneracji.uzyty_sufiks`.
    """
    sufiks_nazwa = wybierz_sufiks(przepis, snapshot, user_text)

    system_prompt = pr.buduj_pelny_prompt_systemowy(
        przepis,
        world_context=snapshot.world_lore,
        sufiks_nazwa=sufiks_nazwa,
    )

    # Wrappery kontekstu (tagi-kotwice) z `rezyser/baza.yaml` (v17.10). 1:1 we
    # wszystkich językach — `tryb_burza.yaml` referuje [OBECNA FABUŁA] dosłownie,
    # więc kotwice muszą zostać w treści. `czesci` → zwinięty `user` (Anthropic),
    # `segmenty` → te same bloki z rolą `assistant` (kontekst) / `user` (instrukcja)
    # dla compat.
    czesci: list[str] = []
    segmenty: list[dict] = []
    if snapshot.summary_text.strip():
        prefiks_streszczenia = pr.tekst_bazy(
            przepis.kod_jezyka, "wrapper_streszczenie",
            "[STRESZCZENIE POPRZEDNICH WYDARZEŃ]:",
        )
        blok_streszczenia = f"{prefiks_streszczenia}\n{snapshot.summary_text}"
        czesci.append(blok_streszczenia)
        segmenty.append({"rola": "assistant", "content": blok_streszczenia})

    if snapshot.full_story.strip():
        prefiks_fabuly = pr.tekst_bazy(
            przepis.kod_jezyka, "wrapper_fabula", "[OBECNA FABUŁA]:",
        )
        blok_fabuly = f"{prefiks_fabuly}\n{snapshot.full_story}"
        czesci.append(blok_fabuly)
        segmenty.append({"rola": "assistant", "content": blok_fabuly})

    przypom = pr.buduj_przypomnienie(przepis)
    blok_instrukcji = user_text + przypom
    czesci.append(blok_instrukcji)
    segmenty.append({"rola": "user", "content": blok_instrukcji})

    messages: list[dict] = [{"role": "user", "content": "\n\n".join(czesci)}]

    return system_prompt, messages, segmenty, sufiks_nazwa


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
# Pobranie doklejki [Reżyserze: ...] / [DYREKTYWA]: ... z YAML-a Burzy
# =============================================================================

def doklejka_celu_sceny(przepis: pr.PrzepisRezysera) -> str:
    """Zwraca lokalizowany blok doklejany do `cel_sceny` z YAML-a Burzy.

    Tekst pochodzi z klucza ``doklejka_celu_sceny`` w
    ``dictionaries/<jezyk>/rezyser/tryb_burza.yaml``. Po stronie GUI
    klik przycisku opcji wstawia do pola Instrukcji:

        [CEL SCENY]: <cel_sceny od LLM>

        <doklejka_celu_sceny — z YAML, lokalizowana>

    Gdzie doklejka zawiera linijki `[Reżyserze: ...]` (instrukcja do
    własnego dopisania uwag) i `[DYREKTYWA]: ...` (przypomnienie dla
    następnego tryba o domknięciu sceny). Python kontroluje treść tych
    linii deterministycznie — LLM nie ma jak ich zepsuć ani naruszyć
    zakazu wymyślania własnych „[Reżyserze, rozważ ...]" zwrotów.

    Fallback: jeśli yaml nie ma klucza ``doklejka_celu_sceny``, zwracamy
    pusty string. GUI wtedy pokaże tylko ``[CEL SCENY]: ...`` bez doklejki.
    Migracja na v15.2 wymaga dodania tego klucza do 9 yaml-ów.
    """
    # PrzepisRezysera nie ma tego pola jako dataclass attribute (kompatybilność
    # wsteczna z v15.1) — bierzemy z surowego dictu yaml. Dla DRY: ładujemy
    # raz przez `przepisy_rezysera`, ale tam dict jest filtrowany do dataclassy.
    # Najmniej inwazyjnie: dodać pole `doklejka_celu_sceny` jako attribute w
    # `PrzepisRezysera` z defaultem "" — robimy to w fazie B (yaml).
    return getattr(przepis, "doklejka_celu_sceny", "") or ""


# =============================================================================
# Burza Mózgów (v15.2): wywołanie LLM z JSON schema i walidacją
# =============================================================================

def generuj_burze(
    klient:    Any,
    przepis:   pr.PrzepisRezysera,
    snapshot:  cr.SnapshotProjektu,
    user_text: str,
    timeout:   float = 120.0,
    max_retry: int = 2,
) -> WynikBurzy:
    """Wysyła Burzę z ``response_format=json_object`` i waliduje JSON-schemę.

    Wzorzec self-correction via error feedback — z ``opowiesci_ai.generuj_ture``.
    Przy halucynacji struktury (brak klucza, zły typ) appendujemy poprzedni
    błąd jako system message i wołamy ponownie; max ``max_retry`` powtórzeń
    (default 2 → łącznie 3 wywołania).

    Args:
        klient:    Klient Anthropic (Claude).
        przepis:   ``PrzepisRezysera`` z ``id="burza"``.
        snapshot:  Niezmienny snapshot stanu projektu.
        user_text: Instrukcja użytkownika.
        timeout:   Limit czasu pojedynczego wywołania (sekundy).
        max_retry: Maks. liczba RETRY (default 2; łącznie max 3 wywołania).

    Returns:
        :class:`WynikBurzy` z 1-5 opcjami + opcjonalnym streszczeniem.

    Raises:
        RuntimeError: wyczerpane retry (halucynacja struktury) ALBO model
                      zwrócił stop_reason="max_tokens" (ucięty JSON).
        Wyjątki Anthropic (RateLimitError, APITimeoutError, ...) — propagowane.
    """
    system, messages, segmenty, sufiks_nazwa = buduj_payload(przepis, snapshot, user_text)

    ostatni_blad: str | None = None
    surowy_text: str = ""
    # v17.11.1: osobne budżety prób struktury i języka (patrz generuj_skrypt).
    proby_struktury = 0
    jezyk_skorygowano = False

    while True:
        # Self-correction: przy retry dodajemy info o poprzednim błędzie
        # walidacji jako system message — model próbuje skorygować strukturę.
        if ostatni_blad is not None:
            komunikat = {
                "role": "user",
                "content": (
                    f"YOUR PREVIOUS OUTPUT FAILED VALIDATION. Error: {ostatni_blad}. "
                    "Regenerate the response STRICTLY conforming to the JSON schema "
                    "defined in the system prompt. Every required field MUST be present "
                    "and MUST have the correct type. Return ONLY a single valid JSON "
                    "object — no prose, no markdown code fences, no commentary."
                ),
            }
            messages.append(komunikat)
            segmenty.append(_segment_systemowy(komunikat))

        surowy_text, stop_reason = _wywolaj_claude(
            klient, przepis, system, messages, timeout, segmenty, wymusz_json=True,
        )
        ostatni_blad = None   # zużyty — wiadomość już doklejona (jeśli była)

        if stop_reason == "max_tokens":
            raise BladDlugosciOdpowiedzi(
                "The model hit its max_tokens limit — the Brainstorm response was "
                "cut off before the JSON could be closed. Shorten the context or "
                "raise max_tokens."
            )

        # Detekcja odrzucenia PRZED walidacją JSON — bo klauzula odrzucenia
        # wymusza ZWROT samego tagu, NIE JSON-a. JSONDecodeError w tej linii
        # to legalny case „LLM odmówił, zwrócił tag, nie JSON".
        if pr.wykryto_odrzucenie(surowy_text):
            return WynikBurzy(
                odrzucone=True,
                uzyty_sufiks=sufiks_nazwa,
                surowy_json=surowy_text,
            )

        try:
            dane = json.loads(surowy_text)
            jsonschema.validate(instance=dane, schema=SCHEMA_BURZA)
        except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
            proby_struktury += 1
            if proby_struktury > max_retry:
                raise BladStrukturyJSON(
                    f"The AI returned a malformed JSON structure {max_retry + 1} "
                    f"times in a row for Brainstorm mode. Last error: {exc}"
                ) from exc
            ostatni_blad = (
                f"JSONDecodeError: {exc.msg}"
                if isinstance(exc, json.JSONDecodeError)
                else f"ValidationError: {exc.message} (path: {list(exc.absolute_path)})"
            )
            continue

        # Struktura OK — mapujemy do dataclassy.
        opcje = [
            OpcjaBurzy(
                tytul=o["tytul"],
                opis=o["opis"],
                cel_sceny=o["cel_sceny"],
            )
            for o in dane["opcje"]
        ]
        streszczenie = (dane.get("streszczenie") or "").strip()

        # v17.11.1 BRAMKA JĘZYKOWA — sklejka WSZYSTKICH wartości narracyjnych
        # (tytuł + opis + cel sceny + streszczenie) daje Lingui dość tekstu mimo
        # że pojedyncza opcja bywa krótka. Pewny rozjazd → jeden dodatkowy strzał.
        wartosci = " ".join(
            [o.tytul + " " + o.opis + " " + o.cel_sceny for o in opcje] + [streszczenie]
        )
        wykryty = _wykryty_inny_jezyk(wartosci, przepis.kod_jezyka)
        if wykryty and not jezyk_skorygowano:
            jezyk_skorygowano = True
            komunikat = _komunikat_korekty_jezyka(przepis.jezyk_odpowiedzi, wykryty)
            messages.append(komunikat)
            segmenty.append(_segment_systemowy(komunikat))
            continue
        if wykryty and jezyk_skorygowano:
            _dev_log(
                f"Burza: render nadal w '{wykryty}' (oczekiwano "
                f"'{przepis.kod_jezyka}') po korekcie językowej — przepuszczam."
            )

        return WynikBurzy(
            opcje=opcje,
            streszczenie=streszczenie,
            odrzucone=False,
            uzyty_sufiks=sufiks_nazwa,
            surowy_json=surowy_text,
        )


# =============================================================================
# Tryb Skrypt (v16.1): strukturyzowane JSON wyjście (lista tur) + audio-tagi v3
# =============================================================================
# Do v16.0 Skrypt zwracał plain text `[Narrator: ton]` / `[Postać: emocja]` +
# kwestia. Problem: most ElevenLabs i tak WYRZUCAŁ emocję z tagu (``_wytnij_mowce``
# bierze nazwę do pierwszego ``:``), więc słownie wyrażone emocje NIGDY nie
# docierały do TTS — a multilingual_v2 i tak ich nie czytał.
#
# v16.1: LLM zwraca STRUKTURYZOWANY JSON ``{"tury":[{"mowca","tekst"}]}``:
#   - ``mowca``  — CZYSTA nazwa (bez nawiasów). Python owija ją w ``[...]``.
#   - ``tekst``  — kwestia JUŻ sformatowana pod TTS: z audio-tagami ElevenLabs
#                  v3 (``[whispers]``, ``[sighs]``, ``[excited]``…) wplecionymi
#                  w treść. W przeciwieństwie do dawnej emocji-w-tagu, te tagi
#                  trafiają do ``tts_node.text`` i realnie sterują renderem v3.
# Nagłówków (Prolog/Akt/Scena/Epilog) LLM NIE generuje — wstawia je reżyser
# z panelu struktury (``gui_rezyser._on_wstaw_*``). Stąd schema to płaska lista
# tur, bez pola ``typ``. Wzorzec self-correction (retry+walidacja) jak w
# ``generuj_burze`` / ``opowiesci_ai.generuj_ture``.
# -----------------------------------------------------------------------------

SCHEMA_SKRYPT: dict[str, Any] = {
    "type": "object",
    "required": ["tury"],
    "additionalProperties": False,
    "properties": {
        "tury": {
            "type": "array",
            # Liberalnie ≥1 — pojedyncza tura (np. samo wejście narratora) jest
            # legalna; GUI nie powinno blokować się na „za mało" tur.
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["mowca", "tekst"],
                "additionalProperties": False,
                "properties": {
                    # Czysta nazwa mówcy / narratora — bez nawiasów, bez emocji.
                    # Python owija w [...] przy renderowaniu (``renderuj_skrypt``).
                    "mowca": {"type": "string", "minLength": 1, "maxLength": 100},
                    # Kwestia sformatowana pod TTS (może zawierać audio-tagi v3).
                    "tekst": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}


@dataclass
class TuraSkryptu:
    """Pojedyncza tura skryptu: kto mówi + co (już sformatowane pod TTS).

    Attributes:
        mowca: Czysta nazwa mówcy / narratora (bez nawiasów). Renderer owija
               ją w ``[...]``; most ElevenLabs mapuje na voice_id z obsady.
        tekst: Treść kwestii, opcjonalnie z audio-tagami v3 (``[whispers]`` itd.)
               wplecionymi przez LLM. Renderer normalizuje ją do JEDNEJ linii.
    """
    mowca: str
    tekst: str


@dataclass
class WynikSkryptu:
    """Wynik :func:`generuj_skrypt`.

    Attributes:
        tekst_odpowiedzi: Wyrenderowany skrypt w formacie pliku — linie
                          ``[Mówca] treść`` (po nałożeniu akcentów fonetycznych,
                          jeśli przepis tego wymaga). To jest to, co GUI dopisuje
                          do ``skrypty/<nazwa>.txt`` i co czyta most ElevenLabs.
        tury:             Surowa lista :class:`TuraSkryptu` (diagnostyka / testy).
        odrzucone:        True, gdy LLM zwrócił sam tag ``[ODRZUCENIE_AI]``.
        uzyty_sufiks:     Diagnostyczne — nazwa doklejonego sufiksu
                          (``"startowy"`` / ``"kontynuacja"`` / ``None``).
        surowy_json:      Sucha odpowiedź modelu (log / debug).
        liczba_prob:      Ile wywołań LLM zużyto (1 = bez retry). Sygnał do
                          diagnostyki „struktura sypie się przy N% kontekstu".
    """
    tekst_odpowiedzi: str = ""
    tury:             list[TuraSkryptu] = field(default_factory=list)
    odrzucone:        bool = False
    uzyty_sufiks:     str | None = None
    surowy_json:      str = ""
    liczba_prob:      int = 0


def renderuj_skrypt(tury: list[TuraSkryptu]) -> str:
    """Renderuje listę tur do formatu pliku skryptu: ``[Mówca] treść`` / tura.

    KAŻDA tura to dokładnie JEDNA linia. Treść jest normalizowana do jednej
    linii (wewnętrzne ``\\n`` → spacja, scalone białe znaki), bo most
    (``buduj_chapters`` / ``wykryj_postacie``) i silnik akcentów rozpoznają
    nową turę po linii zaczynającej się od ``[``. Gdyby kwestia łamała się na
    kolejne linie, a któraś zaczynała się od audio-tagu (np. ``[sighs] …``),
    parser liniowy wziąłby ją za nowego mówcę „sighs". Trzymanie jednej linii
    na turę usuwa to ryzyko po stronie mostu u źródła (audio-tag zostaje wtedy
    w treści węzła TTS, nie jako tag mówcy).

    Tury z pustym mówcą lub pustą treścią są pomijane (defensywnie — schema
    i tak wymusza ``minLength: 1``, ale po ``strip()`` mogą zostać puste).
    """
    linie: list[str] = []
    for tura in tury:
        mowca = (tura.mowca or "").strip()
        tekst = re.sub(r"\s+", " ", (tura.tekst or "").replace("\n", " ")).strip()
        if not mowca or not tekst:
            continue
        linie.append(f"[{mowca}] {tekst}")
    return "\n".join(linie)


def generuj_skrypt(
    klient:    Any,
    przepis:   pr.PrzepisRezysera,
    snapshot:  cr.SnapshotProjektu,
    user_text: str,
    timeout:   float = 120.0,
    max_retry: int = 2,
) -> WynikSkryptu:
    """Generuje turę trybu Skrypt jako JSON (lista tur) + waliduje + renderuje.

    Wzorzec self-correction via error feedback — identyczny jak
    :func:`generuj_burze`. Przy halucynacji struktury (brak klucza / zły typ)
    dopinamy poprzedni błąd jako system message i wołamy ponownie; max
    ``max_retry`` powtórzeń (default 2 → łącznie 3 wywołania).

    WYMÓG: ``przepis.prompt_systemowy`` MUSI instruować model, by zwracał JSON
    zgodny ze :data:`SCHEMA_SKRYPT`. Na Claude egzekwujemy to przez prompt +
    walidację ``jsonschema`` + retry (nie ma odpowiednika OpenAI
    ``response_format={"type": "json_object"}``). To zadanie przepisu YAML
    (Etap E3), nie tego modułu.

    Args:
        klient:    Klient Anthropic (Claude).
        przepis:   ``PrzepisRezysera`` z ``id="skrypt"`` (``zapis_do_pliku=True``).
        snapshot:  Niezmienny snapshot stanu projektu.
        user_text: Instrukcja użytkownika.
        timeout:   Limit czasu pojedynczego wywołania (sekundy).
        max_retry: Maks. liczba RETRY (default 2; łącznie max 3 wywołania).

    Returns:
        :class:`WynikSkryptu` z wyrenderowanym ``tekst_odpowiedzi`` (po akcentach,
        gdy ``przepis.stosuj_akcenty_fonetyczne``) i surową listą ``tury``.

    Raises:
        RuntimeError: wyczerpane retry (halucynacja struktury) ALBO
                      stop_reason="max_tokens" (ucięty JSON).
        Wyjątki Anthropic (RateLimitError, APITimeoutError, ...) — propagowane.
    """
    system, messages, segmenty, sufiks_nazwa = buduj_payload(przepis, snapshot, user_text)

    ostatni_blad: str | None = None
    surowy_text: str = ""
    # v17.11.1: dwa NIEZALEŻNE budżety prób — struktury (JSON) i języka (Lingua).
    # Bramka językowa „resetuje licznik retry" (życzenie usera): rozjazd języka
    # daje JEDEN dodatkowy strzał, nie zżerając budżetu retry struktury.
    proby_struktury = 0
    jezyk_skorygowano = False
    wywolan = 0

    while True:
        if ostatni_blad is not None:
            komunikat = {
                "role": "user",
                "content": (
                    f"YOUR PREVIOUS OUTPUT FAILED VALIDATION. Error: {ostatni_blad}. "
                    "Regenerate the response STRICTLY conforming to the JSON schema "
                    "defined in the system prompt. Every required field MUST be present "
                    "and MUST have the correct type. Return ONLY a single valid JSON "
                    "object — no prose, no markdown code fences, no commentary."
                ),
            }
            messages.append(komunikat)
            segmenty.append(_segment_systemowy(komunikat))

        surowy_text, stop_reason = _wywolaj_claude(
            klient, przepis, system, messages, timeout, segmenty, wymusz_json=True,
        )
        wywolan += 1
        ostatni_blad = None   # zużyty — wiadomość już doklejona (jeśli była)

        if stop_reason == "max_tokens":
            raise BladDlugosciOdpowiedzi(
                "The model hit its max_tokens limit — the Script response was cut "
                "off before the JSON could be closed. Shorten the context or raise "
                "max_tokens."
            )

        # Detekcja odrzucenia PRZED walidacją JSON — klauzula odrzucenia wymusza
        # ZWROT samego tagu, NIE JSON-a (JSONDecodeError byłby tu legalnym
        # skutkiem „LLM odmówił, zwrócił tag").
        if pr.wykryto_odrzucenie(surowy_text):
            return WynikSkryptu(
                odrzucone=True,
                uzyty_sufiks=sufiks_nazwa,
                surowy_json=surowy_text,
                liczba_prob=wywolan,
            )

        try:
            dane = json.loads(surowy_text)
            jsonschema.validate(instance=dane, schema=SCHEMA_SKRYPT)
        except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
            proby_struktury += 1
            if proby_struktury > max_retry:
                raise BladStrukturyJSON(
                    f"The AI returned a malformed JSON structure {max_retry + 1} "
                    f"times in a row for Script mode. Last error: {exc}"
                ) from exc
            ostatni_blad = (
                f"JSONDecodeError: {exc.msg}"
                if isinstance(exc, json.JSONDecodeError)
                else f"ValidationError: {exc.message} (path: {list(exc.absolute_path)})"
            )
            continue

        # Struktura OK — mapujemy do dataclass.
        tury = [TuraSkryptu(mowca=o["mowca"], tekst=o["tekst"]) for o in dane["tury"]]

        # v17.11.1 BRAMKA JĘZYKOWA — na surowych kwestiach, PRZED akcentami
        # (akcenty psują ortografię → myliłyby Linguę). Pewny rozjazd → jeden
        # dodatkowy strzał z jawną instrukcją tłumaczenia wartości; po nim
        # przepuszczamy z dev-logiem (NIE blokujemy reżysera w kółko — D2).
        wykryty = _wykryty_inny_jezyk(
            " ".join(t.tekst for t in tury), przepis.kod_jezyka,
        )
        if wykryty and not jezyk_skorygowano:
            jezyk_skorygowano = True
            komunikat = _komunikat_korekty_jezyka(przepis.jezyk_odpowiedzi, wykryty)
            messages.append(komunikat)
            segmenty.append(_segment_systemowy(komunikat))
            continue
        if wykryty and jezyk_skorygowano:
            _dev_log(
                f"Skrypt: render nadal w '{wykryty}' (oczekiwano "
                f"'{przepis.kod_jezyka}') po korekcie językowej — przepuszczam."
            )

        tekst = renderuj_skrypt(tury)

        # v17.9 (Obszar 3a): akcenty w języku treści przepisu (`kod_jezyka`),
        # bez pl-fallbacku — brak kodu → tekst nietknięty (patrz generuj_fragment).
        if przepis.stosuj_akcenty_fonetyczne and przepis.kod_jezyka:
            tekst = cr.zastosuj_akcenty_uniwersalne(
                tekst, snapshot.world_lore, jezyk_projektu=przepis.kod_jezyka,
            )

        return WynikSkryptu(
            tekst_odpowiedzi=tekst,
            tury=tury,
            odrzucone=False,
            uzyty_sufiks=sufiks_nazwa,
            surowy_json=surowy_text,
            liczba_prob=wywolan,
        )


# =============================================================================
# Guard urwanej prozy (sprawa #1): domknięcie zdania uciętego na max_tokens
# =============================================================================
# Tryby JSON (Skrypt/Burza) łapią `stop_reason=="max_tokens"` i rzucają
# `BladDlugosciOdpowiedzi`. Tryb prozy (audiobook, `generuj_fragment`) dotąd
# IGNOROWAŁ stop_reason — odpowiedź ucięta w pół zdania szła po cichu do pliku
# z doklejonym `\n\n`. Przyczyna: anti-closure w promptach Reżysera (model nie
# domyka scen) plus ceiling `MAX_TOKENS_NARRACJA`. Decyzja (2026-06-18): zapisu
# NIE blokujemy — przy `max_tokens` domykamy ostatnie zdanie jednym mikro-callem
# z minimalnym kontekstem (sam urwany ogon). Gdy się nie uda → miękkie
# ostrzeżenie dla reżysera, a tekst zapisuje się w obecnej postaci.

# Zakończenie zdania: jeden+ znak `.!?…` (+ ewentualny domykający cudzysłów /
# nawias). Po nim musi nastąpić biały znak lub koniec tekstu — dzięki temu
# „3.14" czy skrót „np." w środku zdania nie są brane za koniec (po kropce nie
# ma spacji). Heurystyka, nie pełny tokenizer — w razie pomyłki na skrócie
# domkniemy nieco dłuższy ogon, co jest nieszkodliwe.
_RE_GRANICA_ZDANIA = re.compile(r"[.!?…]+[\"'»”’\)\]]*")


def _ostatnia_granica_zdania(tekst: str) -> int:
    """Indeks tuż PO ostatnim pełnym zakończeniu zdania w ``tekst`` (0 = brak)."""
    best = 0
    for m in _RE_GRANICA_ZDANIA.finditer(tekst):
        koniec = m.end()
        if koniec >= len(tekst) or tekst[koniec] in " \n\t\r":
            best = koniec
    return best


def _domknij_urwane_zdanie(
    klient:  Any,
    przepis: pr.PrzepisRezysera,
    tekst:   str,
    timeout: float,
) -> tuple[str, bool]:
    """Domyka zdanie urwane przez ``max_tokens`` jednym mikro-callem LLM.

    Bierze ogon od ostatniej granicy zdania i prosi model o przepisanie go jako
    JEDNEGO domkniętego, naturalnego zdania w języku treści
    (``przepis.jezyk_odpowiedzi``), zachowując dotychczasowe słowa. Zwrócone
    zdanie podmienia urwany ogon (prefiks sprzed granicy + oryginalny separator
    biały zostają nietknięte). Przepisanie CAŁEGO ogona (a nie doklejanie
    „reszty") usuwa ryzyko sklejki w pół słowa — ucięcie na ``max_tokens`` pada
    na granicy tokenu, często w środku wyrazu.

    Returns:
        Krotka ``(tekst, doszyto)``:
          * ``doszyto=True``  — domknięte (albo nie było czego domykać, bo
            ucięcie wypadło dokładnie na końcu zdania);
          * ``doszyto=False`` — nie ruszamy tekstu (ogon zbyt długi, błąd API,
            mikro-call też się uciął / odmówił / nic nie zwrócił). Wołający
            ustawia wtedy miękkie ostrzeżenie, ale zapis przechodzi.
    """
    granica = _ostatnia_granica_zdania(tekst)
    reszta = tekst[granica:]
    ogon = reszta.strip()
    if not ogon:
        return tekst, True   # ucięcie dokładnie na końcu zdania — nic do roboty
    if len(ogon) > MAX_ZNAKOW_URWANEGO_ZDANIA:
        return tekst, False

    sep = reszta[: len(reszta) - len(reszta.lstrip())]
    system = (
        "A passage of prose was cut off mid-sentence. You are given only the "
        "final, incomplete sentence. Rewrite it as exactly ONE complete, natural "
        f"sentence written in {przepis.jezyk_odpowiedzi}, keeping the existing "
        "words and wording and merely continuing them to a natural end. Output "
        "ONLY that single finished sentence — no quotes, no commentary, no extra "
        "sentences, no leading or trailing whitespace."
    )
    try:
        domkniete_raw, stop_reason = cl.wywolaj_llm(
            klient,
            model=przepis.model,
            system=system,
            messages=[{"role": "user", "content": ogon}],
            max_tokens=MAX_TOKENS_DOMKNIECIE,
            temperature=przepis.temperatura,
            timeout=timeout,
        )
    except Exception:  # noqa: BLE001 — błąd domknięcia = ostrzeżenie, nie crash
        return tekst, False

    domkniete = domkniete_raw.strip()
    # Mikro-call też się uciął / odmówił / milczy → nie ryzykujemy sklejki
    # połówek; oddajemy oryginał i sygnalizujemy ostrzeżenie.
    if (
        not domkniete
        or stop_reason == "max_tokens"
        or pr.wykryto_odrzucenie(domkniete)
    ):
        return tekst, False

    return tekst[:granica] + sep + domkniete, True


# =============================================================================
# Główna funkcja: generowanie fragmentu historii
# =============================================================================

def generuj_fragment(
    klient: Any,
    przepis: pr.PrzepisRezysera,
    snapshot: cr.SnapshotProjektu,
    user_text: str,
    timeout: float = 120.0,
) -> WynikGeneracji:
    """Wysyła zapytanie do Claude (Anthropic) i zwraca przetworzoną odpowiedź.

    Args:
        klient:     Klient Anthropic (``anthropic.Anthropic(api_key=...)``).
        przepis:    Tryb pracy (Burza / Skrypt / Audiobook).
        snapshot:   Niezmienny snapshot stanu projektu.
        user_text:  Instrukcja użytkownika z pola „Instrukcje".
        timeout:    Limit czasu na wywołanie Claude w sekundach.
                    Uwaga: obejmuje **cały** czas od wysłania do
                    otrzymania pełnej odpowiedzi. Dla długich generacji
                    audiobookowych można podnieść.

    Returns:
        :class:`WynikGeneracji` – GUI sprawdza ``.odrzucone`` i
        ``.nowe_streszczenie`` decydując, co zrobić z odpowiedzią.

    Raises:
        Wyjątki Anthropic (``RateLimitError``, ``APITimeoutError``,
        ``APIError``) są propagowane – GUI pokazuje je w dialogu błędu.
    """
    system, messages, segmenty, sufiks_nazwa = buduj_payload(przepis, snapshot, user_text)

    # v17.11.1: pojedyncze wywołanie owinięte w pętlę, żeby bramka językowa
    # mogła dać JEDEN dodatkowy strzał z instrukcją tłumaczenia (D2). Struktury
    # tu nie walidujemy (proza), więc jedyny powód powtórki to rozjazd języka.
    jezyk_skorygowano = False
    while True:
        tekst, stop_reason = _wywolaj_claude(
            klient, przepis, system, messages, timeout, segmenty,
        )

        # 1) Detekcja odrzucenia — przed wszystkim innym. Tag infrastruktury
        # jest wymuszany przez KLAUZULA_ODRZUCENIA_DOMYSLNA niezależnie od
        # jezyk_odpowiedzi, więc działa tak samo dla fińskiego i japońskiego.
        if pr.wykryto_odrzucenie(tekst):
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

        # 2b) BRAMKA JĘZYKOWA — na narracji PO ekstrakcji streszczenia, PRZED
        # akcentami (akcenty psują ortografię → myliłyby Linguę). Pewny rozjazd
        # → jeden dodatkowy strzał z instrukcją tłumaczenia; po nim przepuszczamy
        # z dev-logiem (nie blokujemy reżysera w kółko — D2).
        wykryty = _wykryty_inny_jezyk(tekst, przepis.kod_jezyka)
        if wykryty and not jezyk_skorygowano:
            jezyk_skorygowano = True
            komunikat = _komunikat_korekty_jezyka(przepis.jezyk_odpowiedzi, wykryty)
            messages.append(komunikat)
            segmenty.append(_segment_systemowy(komunikat))
            continue
        if wykryty and jezyk_skorygowano:
            _dev_log(
                f"Fragment: render nadal w '{wykryty}' (oczekiwano "
                f"'{przepis.kod_jezyka}') po korekcie językowej — przepuszczam."
            )

        # 2c) GUARD URWANEJ PROZY (sprawa #1) — PO bramce językowej (żeby nie
        # domykać zdania, które i tak zostałoby zregenerowane przy rozjeździe
        # języka) i PRZED akcentami (akcenty psują ortografię → utrudniłyby
        # mikro-callowi pracę). Tylko `max_tokens` = realne ucięcie; inne
        # stop_reason (`end_turn` itp.) oznaczają, że model skończył sam.
        ostrzezenie = ""
        if stop_reason == "max_tokens":
            tekst, doszyto = _domknij_urwane_zdanie(klient, przepis, tekst, timeout)
            if not doszyto:
                ostrzezenie = i18n.t("rezyser.ostrzezenie_urwane_tresc")

        # 3) Akcenty fonetyczne — tylko gdy przepis tego wymaga (Skrypt).
        # v17.9 (Obszar 3a): aplikujemy w JĘZYKU TREŚCI przepisu (`kod_jezyka`),
        # nie w domyślnym „pl". Brak `kod_jezyka` → NIE aplikujemy akcentów (żaden
        # fallback — lepiej zostawić tekst nietknięty niż psuć obcą ortografię
        # polskimi/angielskimi regułami; dług z dawnego komentarza tu domknięty).
        if przepis.stosuj_akcenty_fonetyczne and przepis.kod_jezyka:
            tekst = cr.zastosuj_akcenty_uniwersalne(
                tekst, snapshot.world_lore, jezyk_projektu=przepis.kod_jezyka,
            )

        return WynikGeneracji(
            tekst_odpowiedzi=tekst,
            odrzucone=False,
            nowe_streszczenie=nowe_streszczenie,
            uzyty_sufiks=sufiks_nazwa,
            ostrzezenie=ostrzezenie,
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
    wzorzec = przepis_tytuly.regex_podzial_rozdzialow
    fragmenty = re.split(wzorzec, pelny_tekst)

    if len(fragmenty) <= 1:
        return WynikTytulowania(
            tytuly=[],
            przerwano_bledem=True,
            blad=i18n.t("rezyser.tytuly_blad_brak_struktury"),
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
            on_postep(
                i18n.t("rezyser.tytuly_postep",
                       naglowek=naglowek, step=step, total=total),
                percent,
            )

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
            tytul_raw, _stop = cl.wywolaj_llm(
                klient,
                model=przepis_tytuly.model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=MAX_TOKENS_TYTUL,
                temperature=przepis_tytuly.temperatura,
                timeout=timeout,
            )
            tytul_raw = tytul_raw.strip()

            # Nawet model tytułujący może odrzucić prompt (szczególnie przy
            # brutalnych treściach w treści rozdziału). Honorujemy tag.
            if pr.wykryto_odrzucenie(tytul_raw):
                tytuly.append(
                    f"{naglowek}: "
                    f"{przepis_tytuly.etykieta_odrzucenie or '(Odrzucenie AI)'}"
                )
            else:
                tytuly.append(f"{naglowek}: {tytul_raw}")

        except cl.BladLimituLLM:
            tytuly.append(
                f"{naglowek}: {przepis_tytuly.etykieta_bled_brak_kredytow}"
            )
            return WynikTytulowania(
                tytuly=tytuly,
                przerwano_bledem=True,
                blad=i18n.t("rezyser.err_rate_limit"),
            )
        except Exception as exc:  # noqa: BLE001
            # v18.10 (audyt): timeout dostaje natywny komunikat i18n — bez tej
            # gałęzi user widział surowe EN z SDK, choć rate-limit obok był
            # zlokalizowany od dawna.
            komunikat = (i18n.t("rezyser.err_timeout")
                         if isinstance(exc, cl.BladTimeoutLLM) else str(exc))
            etykieta_bledu = przepis_tytuly.etykieta_blad_fragment or "(Błąd – {blad})"
            tytuly.append(f"{naglowek}: {etykieta_bledu.replace('{blad}', komunikat)}")
            return WynikTytulowania(
                tytuly=tytuly,
                przerwano_bledem=True,
                blad=komunikat,
            )

    return WynikTytulowania(tytuly=tytuly, przerwano_bledem=False, blad="")


# =============================================================================
# Wnioskowanie kodu ISO języka treści (v17.9, Obszar 3b)
# =============================================================================

def wywnioskuj_kod_jezyka(
    klient:           Any,
    jezyk_odpowiedzi: str,
    dozwolone:        "set[str] | list[str]",
    timeout:          float = 30.0,
) -> str | None:
    """Wnioskuje kod ISO 639-1 języka treści z prozaicznego ``jezyk_odpowiedzi``.

    Używane, gdy lingwista zostawił ``kod_jezyka`` puste w przepisie (paczki
    shippowane mają je wypełnione, więc to ścieżka awaryjna). Mikrorequest LLM
    w stylu :mod:`tlumacz_ai`: krótki prompt, ``temperature=0``, zwraca GOŁY
    dwuliterowy kod.

    Walidacja (decyzja 2a): wynik MUSI należeć do ``dozwolone`` — zwykle
    zainstalowane pakiety UI (``i18n.dostepne_jezyki_ui()``), bo tylko dla nich
    nagłówki struktury wyrenderują się natywnie. Cokolwiek innego (halucynacja,
    kod nieobsługiwanego języka, pusta odpowiedź) → ``None``; wołający (GUI)
    pokazuje wtedy błąd reżyserowi i NIE wstawia nagłówka.

    Nigdy nie rzuca — błąd sieci/SDK także daje ``None`` (degradacja do błędu
    dla reżysera, nie crash wątku tła).
    """
    dozwolone_set = {str(k).strip().lower() for k in dozwolone}
    system = (
        "You map a natural-language description of a language (often given in a "
        "locative or otherwise inflected form, in any language) to its ISO 639-1 "
        "two-letter code. Respond with ONLY the two-letter lowercase code and "
        "nothing else. Examples: 'polsku' -> pl, 'angielsku' -> en, "
        "'fińsku' -> fi, 'suomeksi' -> fi, 'auf Deutsch' -> de, "
        "'по-русски' -> ru."
    )
    try:
        raw_txt, _stop = cl.wywolaj_llm(
            klient,
            model="claude-sonnet-5",
            system=system,
            messages=[{"role": "user", "content": jezyk_odpowiedzi}],
            temperature=0,
            max_tokens=16,
            timeout=timeout,
        )
    except Exception:  # noqa: BLE001 — każdy błąd API/SDK = brak kodu, nie crash
        return None

    raw = raw_txt.strip().lower()
    m = re.search(r"[a-z]{2}", raw)
    kod = m.group(0) if m else ""
    return kod if kod in dozwolone_set else None


# =============================================================================
# v17.11.1: samowystarczalny resolver ISO (cache + retry) + bramka językowa
# =============================================================================
# Problem: lingwista/reżyser wpisywał `jezyk_odpowiedzi: fińsku`, ale `kod_jezyka`
# zostawiał „pl" (lub puste) — silnik brał wpisany kod PO CICHU, dając rozjazd
# „treść fińska / nagłówki polskie". Decyzja D1 (Wariant A): kod ISO ustalamy
# ZAWSZE z `jezyk_odpowiedzi` (przez cache, więc bez spamu API), a wpisany
# `kod_jezyka` traktujemy tylko jako fallback offline; rozjazd → jawne
# ostrzeżenie dla reżysera (uciszamy każdego, kto sądził, że sam
# `jezyk_odpowiedzi` wystarcza).


@dataclass
class RozwiazanieKodu:
    """Wynik :func:`rozwiaz_kod_jezyka` — kod ISO + skąd pochodzi + flaga rozjazdu.

    Attributes:
        kod:            Rozwiązany 2-literowy ISO 639-1, albo ``None`` gdy nie
                        udało się ustalić (brak API + brak sensownego fallbacku).
        zrodlo:         ``"cache"`` | ``"llm"`` | ``"fallback_yaml"`` | ``"brak"``
                        — diagnostyka / decyzja GUI (warn vs dialog edukacyjny).
        rozjazd_z_yaml: ``True`` gdy PEWNY kod (cache/llm) ≠ niepuste, inne
                        `kod_jezyka` wpisane w YAML → GUI pokazuje ostrzeżenie.
        yaml_kod:       Oryginalny wpisany `kod_jezyka` (do treści komunikatu).
    """

    kod: str | None
    zrodlo: str
    rozjazd_z_yaml: bool
    yaml_kod: str


def rozwiaz_kod_jezyka(
    klient:           Any,
    jezyk_odpowiedzi: str,
    kod_jezyka_yaml:  str,
    dozwolone:        "set[str] | list[str]",
    *,
    retry:            int = 2,
    timeout:          float = 30.0,
) -> RozwiazanieKodu:
    """Ustala kod ISO treści z `jezyk_odpowiedzi` — cache → LLM (2 retry) → fallback.

    Kolejność (samowystarczalność, D1 Wariant A):
      1. **Cache** ``runtime/jezyki_iso.json`` (klucz = znormalizowany
         `jezyk_odpowiedzi`) — trafienie zwraca kod bez API.
      2. **Mikrorequest LLM** (`wywnioskuj_kod_jezyka`) z maks. ``retry``
         powtórkami (domyślnie 2 → łącznie 3 próby; chroni przed transient
         network error). Sukces → zapis do cache.
      3. **Fallback offline** do wpisanego `kod_jezyka_yaml`, jeśli jest w
         ``dozwolone`` (brak API / wyczerpane próby). Inaczej ``kod=None``
         (GUI pokaże dialog edukacyjny).

    `rozjazd_z_yaml` ustawiamy tylko dla PEWNEGO kodu (cache/llm) — fallback do
    YAML z definicji się z nim zgadza, więc nie ostrzega o sobie samym.
    """
    dozwolone_set = {str(k).strip().lower() for k in dozwolone}
    yaml_kod = (kod_jezyka_yaml or "").strip().lower()
    klucz = (jezyk_odpowiedzi or "").strip().lower()

    cache = cr.wczytaj_cache_iso()
    z_cache = cache.get(klucz)
    if z_cache and z_cache in dozwolone_set:
        return RozwiazanieKodu(
            z_cache, "cache", bool(yaml_kod) and z_cache != yaml_kod, yaml_kod,
        )

    if klient is not None and klucz:
        for _ in range(max(0, retry) + 1):
            kod = wywnioskuj_kod_jezyka(klient, jezyk_odpowiedzi, dozwolone, timeout)
            if kod:
                cache[klucz] = kod
                cr.zapisz_cache_iso(cache)
                return RozwiazanieKodu(
                    kod, "llm", bool(yaml_kod) and kod != yaml_kod, yaml_kod,
                )

    if yaml_kod in dozwolone_set:
        return RozwiazanieKodu(yaml_kod, "fallback_yaml", False, yaml_kod)
    return RozwiazanieKodu(None, "brak", False, yaml_kod)


def _wykryty_inny_jezyk(tekst: str, oczekiwany_kod: str) -> str | None:
    """Bramka językowa (#1B): zwraca PEWNIE wykryty inny kod ISO albo ``None``.

    Korzysta z `core_poliglota.wykryj_jezyk_zrodlowy`, które przy niepewności
    (tekst za krótki, brak sygnału, brak Lingua) zwraca ``fallback``. Podajemy
    `fallback=oczekiwany_kod`, więc niepewna detekcja daje ``wykryty ==
    oczekiwany`` → ``None`` (D2: przy niepewności UFAMY renderowi, nie korygujemy).
    Tylko PEWNY, inny wynik → zwracamy go (sygnał do jednej korekty)."""
    if not oczekiwany_kod or not tekst or not tekst.strip():
        return None
    wykryty = cp.wykryj_jezyk_zrodlowy(tekst, fallback=oczekiwany_kod)
    return wykryty if wykryty != oczekiwany_kod else None


def _komunikat_korekty_jezyka(jezyk_odpowiedzi: str, wykryty: str) -> dict[str, str]:
    """User-message wymuszający przetłumaczenie WARTOŚCI na język treści
    (po angielsku, spójnie z resztą self-correction w tym module — D2/„po en").

    Rola ``user`` (nie ``system``): Anthropic nie przyjmuje dowolnych wiadomości
    ``system`` w ``messages`` — kolejne ``user`` API skleja w jedną turę."""
    return {
        "role": "user",
        "content": (
            f"YOUR PREVIOUS OUTPUT WAS WRITTEN IN THE WRONG LANGUAGE "
            f"(detected ISO: '{wykryty}'). The target content language is "
            f"'{jezyk_odpowiedzi}'. Regenerate the SAME content, but translate "
            f"ALL human-readable VALUES into '{jezyk_odpowiedzi}'. Keep the JSON "
            f"structure, field names, audio tags and speaker names UNCHANGED — "
            f"translate only the narrative/prose values."
        ),
    }


def _segment_systemowy(komunikat: dict) -> dict:
    """Z meta-wiadomości ``messages`` (rola ``user`` — Anthropic) robi segment
    ``system`` dla ``openai_compat``.

    Retry-walidacja i korekta języka to instrukcje meta (nie wkład użytkownika) —
    w payloadzie z rolami należą do ``system``. Anthropic dostaje je dalej jako
    kolejny ``user`` (kolejne ``user`` API i tak skleja), więc filar bez zmian."""
    return {"rola": "system", "content": komunikat["content"]}
