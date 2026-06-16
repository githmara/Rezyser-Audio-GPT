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

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import jsonschema

import core_rezyser as cr
import przepisy_rezysera as pr
from bledy_ai import BladDlugosciOdpowiedzi, BladStrukturyJSON

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
        # v15.1: pamięć liczymy w tokenach przez `core_tokeny` (był len-w-znakach).
        tokeny  = cr.policz_tokeny_payloadu_snapshot(snapshot)
        udzial  = tokeny / cr.OKNO_KONTEKSTU_MAX
        if udzial >= cr.PROG_OSTRZEZENIE:
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

    # Wrappery kontekstu (tagi-kotwice) wyniesione z hard-kodu do `rezyser/baza.yaml`
    # (v17.10). 1:1 we wszystkich językach — `tryb_burza.yaml` referuje [OBECNA FABUŁA]
    # dosłownie, więc lokalizacja by je rozjechała; baza daje pojedyncze źródło + fallback.
    if snapshot.summary_text.strip():
        prefiks_streszczenia = pr.tekst_bazy(
            przepis.kod_jezyka, "wrapper_streszczenie",
            "[STRESZCZENIE POPRZEDNICH WYDARZEŃ]:",
        )
        messages.append({
            "role": "assistant",
            "content": f"{prefiks_streszczenia}\n{snapshot.summary_text}",
        })

    if snapshot.full_story.strip():
        prefiks_fabuly = pr.tekst_bazy(
            przepis.kod_jezyka, "wrapper_fabula", "[OBECNA FABUŁA]:",
        )
        messages.append({
            "role": "assistant",
            "content": f"{prefiks_fabuly}\n{snapshot.full_story}",
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
    on_postep: PostepCallback | None = None,
    timeout:   float = 120.0,
    max_retry: int = 2,
) -> WynikBurzy:
    """Wysyła Burzę z ``response_format=json_object`` i waliduje JSON-schemę.

    Wzorzec self-correction via error feedback — z ``opowiesci_ai.generuj_ture``.
    Przy halucynacji struktury (brak klucza, zły typ) appendujemy poprzedni
    błąd jako system message i wołamy ponownie; max ``max_retry`` powtórzeń
    (default 2 → łącznie 3 wywołania).

    Args:
        klient:    Klient OpenAI.
        przepis:   ``PrzepisRezysera`` z ``id="burza"``.
        snapshot:  Niezmienny snapshot stanu projektu.
        user_text: Instrukcja użytkownika.
        on_postep: Callback postępu.
        timeout:   Limit czasu pojedynczego wywołania (sekundy).
        max_retry: Maks. liczba RETRY (default 2; łącznie max 3 wywołania).

    Returns:
        :class:`WynikBurzy` z 1-5 opcjami + opcjonalnym streszczeniem.

    Raises:
        RuntimeError: wyczerpane retry (halucynacja struktury) ALBO model
                      zwrócił finish_reason="length" (max_tokens hit).
        Wyjątki OpenAI (RateLimitError, APITimeoutError, ...) — propagowane.
    """
    if on_postep:
        on_postep("Budowanie payloadu Burzy…", 10)

    messages, sufiks_nazwa = buduj_payload(przepis, snapshot, user_text)

    if on_postep:
        on_postep(f"Wysyłanie do {przepis.model} (JSON mode)…", 30)

    ostatni_blad: str | None = None
    surowy_text: str = ""

    for proba in range(max_retry + 1):
        # Self-correction: przy retry dodajemy info o poprzednim błędzie
        # walidacji jako system message — model próbuje skorygować strukturę.
        if ostatni_blad is not None:
            messages.append({
                "role": "system",
                "content": (
                    f"YOUR PREVIOUS OUTPUT FAILED VALIDATION. Error: {ostatni_blad}. "
                    "Regenerate the response STRICTLY conforming to the JSON schema "
                    "defined in the system prompt. Every required field MUST be present "
                    "and MUST have the correct type. Return ONLY a single valid JSON "
                    "object — no prose, no markdown code fences, no commentary."
                ),
            })

        response = klient.chat.completions.create(
            model=przepis.model,
            messages=messages,
            temperature=przepis.temperatura,
            timeout=timeout,
            response_format={"type": "json_object"},
        )

        finish = getattr(response.choices[0], "finish_reason", None)
        if finish == "length":
            raise BladDlugosciOdpowiedzi(
                "The model hit its max_tokens limit — the Brainstorm response was "
                "cut off before the JSON could be closed. Shorten the context or "
                "raise max_tokens."
            )

        surowy_text = response.choices[0].message.content or ""

        # Detekcja odrzucenia PRZED walidacją JSON — bo klauzula odrzucenia
        # wymusza ZWROT samego tagu, NIE JSON-a. JSONDecodeError w tej linii
        # to legalny case „LLM odmówił, zwrócił tag, nie JSON".
        if pr.wykryto_odrzucenie(surowy_text):
            if on_postep:
                on_postep("AI odrzuciło prompt (tag wykryty).", 100)
            return WynikBurzy(
                odrzucone=True,
                uzyty_sufiks=sufiks_nazwa,
                surowy_json=surowy_text,
            )

        try:
            dane = json.loads(surowy_text)
            jsonschema.validate(instance=dane, schema=SCHEMA_BURZA)
        except json.JSONDecodeError as exc:
            ostatni_blad = f"JSONDecodeError: {exc.msg}"
            continue
        except jsonschema.ValidationError as exc:
            ostatni_blad = (
                f"ValidationError: {exc.message} (path: {list(exc.absolute_path)})"
            )
            continue

        # Sukces — żaden błąd schemy. Mapujemy do dataclassy.
        opcje = [
            OpcjaBurzy(
                tytul=o["tytul"],
                opis=o["opis"],
                cel_sceny=o["cel_sceny"],
            )
            for o in dane["opcje"]
        ]
        streszczenie = (dane.get("streszczenie") or "").strip()

        if on_postep:
            on_postep("Gotowe.", 100)

        return WynikBurzy(
            opcje=opcje,
            streszczenie=streszczenie,
            odrzucone=False,
            uzyty_sufiks=sufiks_nazwa,
            surowy_json=surowy_text,
        )

    raise BladStrukturyJSON(
        f"The AI returned a malformed JSON structure {max_retry + 1} times in a row "
        f"for Brainstorm mode. Last error: {ostatni_blad}"
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
    on_postep: PostepCallback | None = None,
    timeout:   float = 120.0,
    max_retry: int = 2,
) -> WynikSkryptu:
    """Generuje turę trybu Skrypt jako JSON (lista tur) + waliduje + renderuje.

    Wzorzec self-correction via error feedback — identyczny jak
    :func:`generuj_burze`. Przy halucynacji struktury (brak klucza / zły typ)
    dopinamy poprzedni błąd jako system message i wołamy ponownie; max
    ``max_retry`` powtórzeń (default 2 → łącznie 3 wywołania).

    WYMÓG: ``przepis.prompt_systemowy`` MUSI instruować model, by zwracał JSON
    zgodny ze :data:`SCHEMA_SKRYPT`, i zawierać słowo „json" (warunek konieczny
    ``response_format={"type": "json_object"}`` w OpenAI). To zadanie przepisu
    YAML (Etap E3), nie tego modułu.

    Args:
        klient:    Klient OpenAI.
        przepis:   ``PrzepisRezysera`` z ``id="skrypt"`` (``zapis_do_pliku=True``).
        snapshot:  Niezmienny snapshot stanu projektu.
        user_text: Instrukcja użytkownika.
        on_postep: Callback postępu.
        timeout:   Limit czasu pojedynczego wywołania (sekundy).
        max_retry: Maks. liczba RETRY (default 2; łącznie max 3 wywołania).

    Returns:
        :class:`WynikSkryptu` z wyrenderowanym ``tekst_odpowiedzi`` (po akcentach,
        gdy ``przepis.stosuj_akcenty_fonetyczne``) i surową listą ``tury``.

    Raises:
        RuntimeError: wyczerpane retry (halucynacja struktury) ALBO
                      finish_reason="length" (ucięty JSON).
        Wyjątki OpenAI (RateLimitError, APITimeoutError, ...) — propagowane.
    """
    if on_postep:
        on_postep("Budowanie payloadu Skryptu…", 10)

    messages, sufiks_nazwa = buduj_payload(przepis, snapshot, user_text)

    if on_postep:
        on_postep(f"Wysyłanie do {przepis.model} (JSON mode)…", 30)

    ostatni_blad: str | None = None
    surowy_text: str = ""

    for proba in range(max_retry + 1):
        if ostatni_blad is not None:
            messages.append({
                "role": "system",
                "content": (
                    f"YOUR PREVIOUS OUTPUT FAILED VALIDATION. Error: {ostatni_blad}. "
                    "Regenerate the response STRICTLY conforming to the JSON schema "
                    "defined in the system prompt. Every required field MUST be present "
                    "and MUST have the correct type. Return ONLY a single valid JSON "
                    "object — no prose, no markdown code fences, no commentary."
                ),
            })

        response = klient.chat.completions.create(
            model=przepis.model,
            messages=messages,
            temperature=przepis.temperatura,
            timeout=timeout,
            response_format={"type": "json_object"},
        )

        finish = getattr(response.choices[0], "finish_reason", None)
        if finish == "length":
            raise BladDlugosciOdpowiedzi(
                "The model hit its max_tokens limit — the Script response was cut "
                "off before the JSON could be closed. Shorten the context or raise "
                "max_tokens."
            )

        surowy_text = response.choices[0].message.content or ""

        # Detekcja odrzucenia PRZED walidacją JSON — klauzula odrzucenia wymusza
        # ZWROT samego tagu, NIE JSON-a (JSONDecodeError byłby tu legalnym
        # skutkiem „LLM odmówił, zwrócił tag").
        if pr.wykryto_odrzucenie(surowy_text):
            if on_postep:
                on_postep("AI odrzuciło prompt (tag wykryty).", 100)
            return WynikSkryptu(
                odrzucone=True,
                uzyty_sufiks=sufiks_nazwa,
                surowy_json=surowy_text,
                liczba_prob=proba + 1,
            )

        try:
            dane = json.loads(surowy_text)
            jsonschema.validate(instance=dane, schema=SCHEMA_SKRYPT)
        except json.JSONDecodeError as exc:
            ostatni_blad = f"JSONDecodeError: {exc.msg}"
            continue
        except jsonschema.ValidationError as exc:
            ostatni_blad = (
                f"ValidationError: {exc.message} (path: {list(exc.absolute_path)})"
            )
            continue

        # Sukces — mapujemy do dataclass, renderujemy, nakładamy akcenty.
        tury = [TuraSkryptu(mowca=o["mowca"], tekst=o["tekst"]) for o in dane["tury"]]
        tekst = renderuj_skrypt(tury)

        # v17.9 (Obszar 3a): akcenty w języku treści przepisu (`kod_jezyka`),
        # bez pl-fallbacku — brak kodu → tekst nietknięty (patrz generuj_fragment).
        if przepis.stosuj_akcenty_fonetyczne and przepis.kod_jezyka:
            tekst = cr.zastosuj_akcenty_uniwersalne(
                tekst, snapshot.world_lore, jezyk_projektu=przepis.kod_jezyka,
            )

        if on_postep:
            on_postep("Gotowe.", 100)

        return WynikSkryptu(
            tekst_odpowiedzi=tekst,
            tury=tury,
            odrzucone=False,
            uzyty_sufiks=sufiks_nazwa,
            surowy_json=surowy_text,
            liczba_prob=proba + 1,
        )

    raise BladStrukturyJSON(
        f"The AI returned a malformed JSON structure {max_retry + 1} times in a row "
        f"for Script mode. Last error: {ostatni_blad}"
    )


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
    # v17.9 (Obszar 3a): aplikujemy w JĘZYKU TREŚCI przepisu (`kod_jezyka`),
    # nie w domyślnym „pl". Brak `kod_jezyka` → NIE aplikujemy akcentów (żaden
    # fallback — lepiej zostawić tekst nietknięty niż psuć obcą ortografię
    # polskimi/angielskimi regułami; dług z dawnego komentarza tu domknięty).
    if przepis.stosuj_akcenty_fonetyczne and przepis.kod_jezyka:
        tekst = cr.zastosuj_akcenty_uniwersalne(
            tekst, snapshot.world_lore, jezyk_projektu=przepis.kod_jezyka,
        )

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
        resp = klient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": jezyk_odpowiedzi},
            ],
            temperature=0,
            max_tokens=5,
            timeout=timeout,
        )
    except Exception:  # noqa: BLE001 — każdy błąd API/SDK = brak kodu, nie crash
        return None

    raw = (resp.choices[0].message.content or "").strip().lower()
    m = re.search(r"[a-z]{2}", raw)
    kod = m.group(0) if m else ""
    return kod if kod in dozwolone_set else None
