"""Most do ElevenLabs Studio — warstwa logiki (bez GUI).

v16.0: opcjonalny tryb postprodukcji. Surowy skrypt teatru czytanego
(tryb Skrypt Reżysera: ``[Narrator: …]`` + ``[Postać: …]``) zostaje zbudowany
w wielogłosowy projekt ElevenLabs Studio, renderowany natywnie po stronie
użytkownika (narrator = głos domyślny projektu).

Feature jest **opcjonalny**: aktywuje się dopiero, gdy w ``golden_key.env``
pojawi się prawidłowy ``ELEVENLABS_API_KEY`` (klucz typu ``sk_`` —
z PODKREŚLNIKIEM, inaczej niż klucz OpenAI ``sk-``). Bez klucza reszta
aplikacji działa bez zmian, a UI postprodukcji pozostaje ukryte.

Ten moduł celowo nie importuje ``wx`` — może być używany zarówno przez
``HomePanel`` (System Check), jak i przez dispatcher w panelu Reżysera,
bez ryzyka cyklicznych importów.

Warstwa klienta HTTP (``requests``): ``saldo``, ``create_project``,
``delete_project`` — patrz dół pliku. Świadomie BEZ ``list_voices``:
reżyser wkleja voice ID skopiowane z weba ElevenLabs (zakładka Voices →
odnajdź głos → odtwórz próbkę dla pewności → More actions → Copy Voice ID),
bo lista API zwróciłaby tylko głosy premade, a użytkownik może chcieć
własnych (Voice Design) albo dowolnych innych. Wybór głosów następuje więc
przez okienko obsady z polem na wklejone ID (Etap 4), nie przez listowanie.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Stałe konfiguracyjne klucza ---------------------------------------------
NAZWA_ZMIENNEJ = "ELEVENLABS_API_KEY"
#: Klucze ElevenLabs zaczynają się od ``sk_`` (PODKREŚLNIK) — nie mylić
#: z OpenAI ``sk-`` (myślnik). To główny dyskryminator formatu.
PREFIX_KLUCZA = "sk_"
MINIMUM_ZNAKOW_KLUCZA = 40

# --- Kody statusu diagnozy (używane też jako sufiks klucza i18n home.el_<kod>)
STATUS_BRAK = "brak"               # zmiennej nie ma / pusta → feature wyłączony (NIE błąd)
STATUS_PLACEHOLDER = "placeholder"  # nadal tekst zastępczy
STATUS_CUDZYSLOWY = "cudzyslowy"    # klucz w cudzysłowach
STATUS_SPACJE = "spacje"            # białe znaki wokół klucza
STATUS_FORMAT = "format"            # zły prefiks (nie sk_)
STATUS_ZBYT_KROTKI = "zbyt_krotki"  # za mało znaków
STATUS_OK = "ok"                    # klucz wykryty i poprawny


@dataclass
class DiagnozaKlucza:
    """Wynik walidacji klucza ElevenLabs z treści ``golden_key.env``.

    Attributes:
        status:        Jeden z ``STATUS_*``. ``STATUS_BRAK`` oznacza, że
                       feature jest po prostu nieskonfigurowany (opcjonalny),
                       a nie że wystąpił błąd.
        klucz:         Prawidłowy klucz, gdy ``status == STATUS_OK`` (inaczej None).
        liczba_znakow: Długość znalezionego klucza (dla komunikatu „zbyt krótki").
    """

    status: str
    klucz: str | None = None
    liczba_znakow: int = 0


def _wytnij_wartosc(zawartosc: str) -> str | None:
    """Zwraca surową wartość po ``ELEVENLABS_API_KEY=`` lub None, gdy brak.

    Parsuje linijka po linijce (nie substringiem jak walidator OpenAI),
    pomijając linie zakomentowane ``#`` — dzięki temu wygenerowana przez
    aplikację podpowiedź ``# ELEVENLABS_API_KEY=`` nie jest traktowana jako
    aktywny, pusty klucz. Wartość zwracana BEZ ``strip()``, aby walidacja
    mogła wykryć przypadkowe spacje wokół klucza.
    """
    for linia in zawartosc.splitlines():
        bez_wciecia = linia.lstrip()
        if bez_wciecia.startswith("#"):
            continue
        if bez_wciecia.startswith(NAZWA_ZMIENNEJ + "="):
            return bez_wciecia.split("=", 1)[1]
    return None


def diagnoza_klucza(zawartosc: str) -> DiagnozaKlucza:
    """Waliduje klucz ElevenLabs zawarty w treści ``golden_key.env``.

    Kolejność testów odwzorowuje walidator OpenAI w ``main.HomePanel``,
    ale ``STATUS_BRAK`` i pusta wartość NIE są błędami — to po prostu
    nieaktywny, opcjonalny feature.
    """
    wartosc_raw = _wytnij_wartosc(zawartosc)
    if wartosc_raw is None:
        return DiagnozaKlucza(STATUS_BRAK)

    klucz = wartosc_raw.strip()

    # Pusty (`ELEVENLABS_API_KEY=` bez wartości) → traktuj jak nieskonfigurowany.
    if not klucz:
        return DiagnozaKlucza(STATUS_BRAK)

    # Nadal tekst zastępczy.
    if "TUTAJ_WKLEJ" in klucz:
        return DiagnozaKlucza(STATUS_PLACEHOLDER)

    # Zbędne cudzysłowy wokół klucza.
    if (klucz.startswith('"') and klucz.endswith('"')) or \
       (klucz.startswith("'") and klucz.endswith("'")):
        return DiagnozaKlucza(STATUS_CUDZYSLOWY)

    # Spacje / znaki niedrukowalne wokół klucza.
    if wartosc_raw != klucz:
        return DiagnozaKlucza(STATUS_SPACJE)

    # Zły prefiks (OpenAI sk- zamiast ElevenLabs sk_, albo coś zupełnie innego).
    if not klucz.startswith(PREFIX_KLUCZA):
        return DiagnozaKlucza(STATUS_FORMAT)

    # Zbyt krótki — prawdopodobnie ucięty.
    if len(klucz) < MINIMUM_ZNAKOW_KLUCZA:
        return DiagnozaKlucza(STATUS_ZBYT_KROTKI, liczba_znakow=len(klucz))

    return DiagnozaKlucza(STATUS_OK, klucz=klucz, liczba_znakow=len(klucz))


def wczytaj_klucz(env_path: str) -> str | None:
    """Czyta ``golden_key.env`` i zwraca prawidłowy klucz ElevenLabs lub None.

    Wygodny skrót dla dispatchera: zwraca klucz wyłącznie, gdy diagnoza jest
    ``STATUS_OK``. Każdy problem (brak, zły format, plik nieczytelny) → None,
    bo feature jest opcjonalny i nigdy nie wywraca aplikacji.
    """
    try:
        with open(env_path, "r", encoding="utf-8-sig") as fh:
            zawartosc = fh.read()
    except OSError:
        return None
    diag = diagnoza_klucza(zawartosc)
    return diag.klucz if diag.status == STATUS_OK else None


# =============================================================================
# Klient HTTP (requests) — most do ElevenLabs Studio (v16.0, Etap 2)
# =============================================================================
# Receptura potwierdzona empirycznie spike'iem v16.0:
#   - auth: header ``xi-api-key``
#   - scope'y restricted key: projects_write + voices_read
#   - tworzenie projektu z ``auto_convert`` pominiętym (=false) NIE spala
#     kredytów (render robi użytkownik później w webie Studio)
# ``requests`` importowane leniwie wewnątrz funkcji — dzięki temu walidacja
# klucza (System Check, Etap 1) działa nawet bez tej zależności.

API_BASE = "https://api.elevenlabs.io"
#: Strona webowa Studio — raport dispatchera linkuje tu, by user otworzył
#: projekt i wyrenderował mowę (deep-link per-projekt celowo pominięty —
#: format URL bywa zmienny; user odnajduje projekt po nazwie/ID).
STUDIO_URL = "https://elevenlabs.io/app/studio"
#: Model wielojęzyczny — pokrywa wszystkie 9 języków paczek (w tym PL).
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
_TIMEOUT_ODCZYT = 30
_TIMEOUT_PROJEKT = 120


class BladElevenLabs(Exception):
    """Ogólny błąd komunikacji z API ElevenLabs (HTTP nie-2xx lub zła struktura)."""


class BrakUprawnien(BladElevenLabs):
    """HTTP 401 z ``detail.status == "missing_permissions"``.

    Klucz jest poprawny, ale restricted key nie ma wymaganych scope'ów
    (``projects_write`` + ``voices_read``). Użytkownik musi je dodać w panelu
    ElevenLabs (Profile → API key → edit → scopes). 401 niczego nie spala.
    """


def _naglowki(klucz: str) -> dict:
    return {"xi-api-key": klucz}


def _sprawdz_odpowiedz(r) -> None:
    """Mapuje odpowiedź HTTP na wyjątki; przy 2xx nie robi nic.

    Wyróżnia 401 ``missing_permissions`` jako :class:`BrakUprawnien`, by GUI
    mogło pokazać konkretną instrukcję o scope'ach zamiast generycznego błędu.
    """
    if r.status_code == 401:
        detail = None
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = None
        if isinstance(detail, dict) and detail.get("status") == "missing_permissions":
            raise BrakUprawnien(
                "Klucz ElevenLabs nie ma wymaganych uprawnień (scope'ów). "
                "Dodaj projects_write oraz voices_read w panelu ElevenLabs."
            )
        raise BladElevenLabs("HTTP 401 — nieautoryzowany (sprawdź klucz ElevenLabs).")
    if not r.ok:
        raise BladElevenLabs(f"HTTP {r.status_code} z ElevenLabs: {r.text[:300]}")


def saldo(klucz: str) -> dict:
    """``GET /v1/user/subscription`` — stan konta (0 kredytów).

    Zwraca surowy słownik subskrypcji; istotne pola to ``character_count``
    (zużyte znaki) i ``character_limit`` (limit). Pozwala dispatcherowi
    pokazać świadomość kosztu przed renderem.
    """
    import requests
    r = requests.get(
        f"{API_BASE}/v1/user/subscription",
        headers=_naglowki(klucz),
        timeout=_TIMEOUT_ODCZYT,
    )
    _sprawdz_odpowiedz(r)
    return r.json()


def create_project(
    klucz: str,
    name: str,
    narrator_voice_id: str,
    chapters: list,
    *,
    model_id: str = DEFAULT_MODEL_ID,
) -> str:
    """Tworzy wielogłosowy projekt Studio. ``auto_convert`` POMINIĘTY → 0 kredytów.

    ``POST /v1/studio/projects`` jako multipart (``requests`` wymaga formy
    ``files={'pole': (None, wartość)}`` dla pól tekstowych). Render mowy to
    osobny krok po stronie użytkownika w webie Studio — tutaj powstaje tylko
    edytowalny projekt.

    Args:
        name:              Nazwa projektu (wymagana przez API).
        narrator_voice_id: Głos domyślny — tytuły rozdziałów i akapity
                           narratora (``default_title_voice_id`` +
                           ``default_paragraph_voice_id``).
        chapters:          Lista rozdziałów w formacie ``from_content_json``
                           (budowana w Etapie 3): każdy rozdział to
                           ``{"name": str, "blocks": [...]}``, blok to
                           ``{"sub_type": "h1"|"p", "nodes": [tts_node, ...]}``,
                           a tts_node to ``{"voice_id", "text", "type": "tts_node"}``.
        model_id:          Domyślnie ``eleven_multilingual_v2``.

    Returns:
        ``project_id`` utworzonego projektu.

    Raises:
        BrakUprawnien:  401 missing_permissions (brak scope'ów).
        BladElevenLabs: inny błąd HTTP lub nieoczekiwana struktura odpowiedzi.
    """
    import json
    import requests

    from_content = json.dumps(chapters, ensure_ascii=False)
    files = {
        "name": (None, name),
        "default_title_voice_id": (None, narrator_voice_id),
        "default_paragraph_voice_id": (None, narrator_voice_id),
        "default_model_id": (None, model_id),
        "from_content_json": (None, from_content),
    }
    r = requests.post(
        f"{API_BASE}/v1/studio/projects",
        headers=_naglowki(klucz),
        files=files,
        timeout=_TIMEOUT_PROJEKT,
    )
    _sprawdz_odpowiedz(r)

    dane = r.json()
    projekt = dane.get("project", dane) if isinstance(dane, dict) else {}
    project_id = (projekt.get("project_id") if isinstance(projekt, dict) else None) \
        or (dane.get("project_id") if isinstance(dane, dict) else None)
    if not project_id:
        raise BladElevenLabs(
            f"Nieoczekiwana struktura odpowiedzi przy tworzeniu projektu: {str(dane)[:300]}"
        )
    return project_id


def delete_project(klucz: str, project_id: str) -> None:
    """``DELETE /v1/studio/projects/{id}`` — sprzątanie (np. projektu testowego)."""
    import requests
    r = requests.delete(
        f"{API_BASE}/v1/studio/projects/{project_id}",
        headers=_naglowki(klucz),
        timeout=_TIMEOUT_ODCZYT,
    )
    _sprawdz_odpowiedz(r)


# =============================================================================
# Parser skryptu teatru czytanego → from_content_json (v16.0, Etap 3)
# =============================================================================
# Wejście: surowy skrypt trybu Skrypt (``[Narrator: …]`` / ``[Postać: …]`` +
# nagłówki Prolog/Akt/Scena). Wyjście: lista rozdziałów ``from_content_json``
# dla ``create_project``.

#: Klucz głosu narratora w mapie obsady (zob. ``buduj_chapters``).
NARRATOR_KEY = "__narrator__"

#: Słowa-wyzwalacze tagu narratora — zlokalizowane per język (małe litery).
#: Tag narratora jest tłumaczony w promptach (``[Narrator:]``/`[Erzähler:]`/…),
#: więc detekcja idzie po unii wszystkich 9 wariantów (są dostatecznie
#: rozróżnialne, by zbiór mógł być wspólny niezależnie od języka projektu).
NARRATOR_WORDS = {
    "narrator",     # pl, en
    "erzähler",     # de
    "narrador",     # es
    "kertoja",      # fi
    "narrateur",    # fr
    "sögumaður",    # is
    "narratore",    # it
    "рассказчик",   # ru
}

# Markery rozdziałów (→ nowy rozdział, tytuł = h1 narratorem) i scen
# (→ h1 wewnątrz bieżącego rozdziału). Wzorce zsynchronizowane z
# ``gui_konwerter.py`` (9 języków: pl/en/de/es/fi/fr/is/it/ru).
_RE_CHAPTER = re.compile(
    r"^[=\-\s]*("
    r"Czołówka"
    r"|Rozdzia[łl]|Chapter|Kapitel|Luku|Kafli|Capitolo|Chapitre|Cap[íi]tulo|Глава"
    r"|Prolog(?:ue|i|o)?|Formáli|Пролог"
    r"|Epilog(?:ue|i|o)?|Eftirorð|Эпилог"
    r"|Akt|Act|Acte|Acto|Atto|Акт|Näytös|Þáttur"
    r")",
    re.IGNORECASE,
)
_RE_SCENE = re.compile(
    r"^[=\-\s]*(Scena|Scene|Szene|Kohtaus|Atriði|Сцена)",
    re.IGNORECASE,
)


def _czysty_naglowek(linia: str) -> str:
    """Obcina dekoracje ``= - spacja`` z obu stron linii nagłówka."""
    return re.sub(r"^[=\-\s]+|[=\-\s]+$", "", linia).strip()


def _klasyfikuj_naglowek(linia: str):
    """Zwraca ``("chapter"|"scene"|None, czysty_tekst)`` dla linii.

    Strażnik przeciw fałszywym trafieniom w erze narratora: linia opisowa
    narratora może zaczynać się od słowa „Scena"/„Akt". Nagłówkiem jest tylko
    linia KRÓTKA (≤ 60 znaków) i BEZ interpunkcji zdaniowej ``.!?`` — zdania
    narratora („Scena była pusta.") przepadają przez filtr i trafiają do
    bufora mówcy jako zwykły tekst.
    """
    czysty = _czysty_naglowek(linia)
    if not czysty or len(czysty) > 60 or re.search(r"[.!?]", czysty):
        return (None, czysty)
    if _RE_CHAPTER.match(linia):
        return ("chapter", czysty)
    if _RE_SCENE.match(linia):
        return ("scene", czysty)
    return (None, czysty)


def _wytnij_mowce(tag: str) -> str | None:
    """Wyłuskuje nazwę mówcy z tagu ``[Imię: emocja]`` → ``"imię"`` (bez emocji).

    Mirror ``core_rezyser`` (``^\\[([^:\\]\\-]+)``): nazwa = tekst do pierwszego
    ``:``, ``]`` lub ``-``.
    """
    m = re.match(r"^\[([^:\]\-]+)", tag)
    return m.group(1).strip() if m else None


_RE_TAG = re.compile(r"\s*(\[[^\]]+\])(.*)")


def wykryj_postacie(tekst: str):
    """Skanuje skrypt → ``(lista_postaci_z_kwestiami, czy_uzyto_narratora)``.

    Postacie w kolejności pierwszego wystąpienia, w oryginalnej pisowni tagu
    (narrator wykluczony z listy — ma osobny, zawsze obecny slot w obsadzie).
    Liczą się tylko mówcy z NIEPUSTĄ kwestią. Feed dla okienka obsady (Etap 4).
    """
    postacie: list[str] = []
    widziane: set[str] = set()
    czy_narrator = False
    mowca = None          # nazwa małymi literami
    mowca_oryg = None     # oryginalna pisownia
    ma_tekst = False

    def _flush():
        nonlocal mowca, mowca_oryg, ma_tekst, czy_narrator
        if mowca is not None and ma_tekst:
            if mowca in NARRATOR_WORDS:
                czy_narrator = True
            elif mowca not in widziane:
                widziane.add(mowca)
                postacie.append(mowca_oryg)
        mowca = None
        mowca_oryg = None
        ma_tekst = False

    for linia in tekst.splitlines():
        typ, _ = _klasyfikuj_naglowek(linia)
        if typ is not None:
            _flush()
            continue
        m = _RE_TAG.match(linia)
        if m:
            _flush()
            sp = _wytnij_mowce(m.group(1))
            mowca_oryg = sp.strip() if sp else None
            mowca = mowca_oryg.lower() if mowca_oryg else None
            ma_tekst = bool(m.group(2).strip())
            continue
        if linia.strip() and mowca is not None:
            ma_tekst = True
    _flush()
    return postacie, czy_narrator


def liczba_rozdzialow(tekst: str) -> int:
    """Liczy markery rozdziałów (Prolog/Akt/Rozdział/…) — do walidacji „≥1 akt"."""
    return sum(
        1 for linia in tekst.splitlines()
        if _klasyfikuj_naglowek(linia)[0] == "chapter"
    )


def _tts_node(voice_id, text: str) -> dict:
    return {"voice_id": voice_id, "text": text, "type": "tts_node"}


def buduj_chapters(tekst: str, obsada: dict, *, domyslny_tytul: str = "1") -> list:
    """Buduje listę rozdziałów ``from_content_json`` ze skryptu + mapy obsady.

    Args:
        obsada: mapa ``{nazwa_postaci_lower: voice_id, NARRATOR_KEY: voice_id}``.
                Narrator (``NARRATOR_KEY``) jest głosem domyślnym — tytuły
                rozdziałów/scen (h1) i kwestie narratora.
        domyslny_tytul: nazwa rozdziału, gdy treść pojawia się PRZED pierwszym
                markerem (np. nazwa projektu); zwykle nieużywana, bo skrypt
                zaczyna się od „Prolog"/„Akt".

    Każda tura mówcy (tag + jego tekst do następnego tagu/nagłówka) → jeden
    blok ``p`` z jednym ``tts_node`` głosem mówcy. Nagłówek rozdziału → nowy
    rozdział + h1 narratorem; nagłówek sceny → h1 narratorem w bieżącym
    rozdziale. Tekst nieotagowanego mówcy (sierota) jest pomijany — nowy
    format wymaga tagu przy każdej linii.
    """
    narrator_voice = obsada.get(NARRATOR_KEY)
    chapters: list = []
    stan = {"biezacy": None, "mowca": None, "bufor": []}

    def _voice_dla(speaker_lower: str):
        if speaker_lower in NARRATOR_WORDS:
            return narrator_voice
        if speaker_lower in obsada:
            return obsada[speaker_lower]
        # Dopasowanie rozmyte (jak silnik akcentów): podciąg w obie strony.
        for k, v in obsada.items():
            if k == NARRATOR_KEY:
                continue
            if k and (k in speaker_lower or speaker_lower in k):
                return v
        return None

    def _zapewnij_chapter():
        if stan["biezacy"] is None:
            stan["biezacy"] = {"name": domyslny_tytul, "blocks": []}
            chapters.append(stan["biezacy"])

    def _h1(text: str):
        _zapewnij_chapter()
        stan["biezacy"]["blocks"].append(
            {"sub_type": "h1", "nodes": [_tts_node(narrator_voice, text)]}
        )

    def _flush():
        mowca = stan["mowca"]
        bufor = stan["bufor"]
        if mowca is not None:
            text = " ".join(s.strip() for s in bufor if s.strip()).strip()
            if text:
                _zapewnij_chapter()
                stan["biezacy"]["blocks"].append(
                    {"sub_type": "p", "nodes": [_tts_node(_voice_dla(mowca), text)]}
                )
        stan["mowca"] = None
        stan["bufor"] = []

    for linia in tekst.splitlines():
        typ, czysty = _klasyfikuj_naglowek(linia)
        if typ == "chapter":
            _flush()
            stan["biezacy"] = {"name": czysty, "blocks": []}
            chapters.append(stan["biezacy"])
            _h1(czysty)
            continue
        if typ == "scene":
            _flush()
            _h1(czysty)
            continue
        m = _RE_TAG.match(linia)
        if m:
            _flush()
            sp = _wytnij_mowce(m.group(1))
            stan["mowca"] = sp.lower().strip() if sp else None
            reszta = m.group(2).strip()
            stan["bufor"] = [reszta] if reszta else []
            continue
        if linia.strip() and stan["mowca"] is not None:
            stan["bufor"].append(linia)
    _flush()
    return chapters
