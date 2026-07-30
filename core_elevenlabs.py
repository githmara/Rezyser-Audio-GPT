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

Warstwa klienta API (natywny SDK ``elevenlabs``): ``saldo``, ``create_project``,
``delete_project`` — patrz dół pliku. Od v17.1 używamy oficjalnego SDK
(``pip install elevenlabs``, ``ElevenLabs.studio.projects.*``) zamiast ręcznie
budowanych żądań ``requests`` — spójność z natywnym klientem OpenAI, koniec
multipart-hacków i ręcznego mapowania kodów HTTP.

Świadomie BEZ ``list_voices``: reżyser wkleja voice ID skopiowane z weba
ElevenLabs. Wybór głosów następuje przez okienko obsady z polem na wklejone ID
(Etap 4), nie przez listowanie API (lista zwróciłaby tylko głosy premade, a
użytkownik może chcieć własnych). Praktyka kopiowania ID (pełna instrukcja
end-userowa → docs ``manual``, sekcja „Krok 1 — Obsada głosowa"):
  - Głos UŻYTY w sztuce MUSI być w „My Voices". Głosy z biblioteki publicznej
    (zakładka „Explore") dodaje się przyciskiem „Add to My Voices".
  - Gdy głos jest już w „My Voices", przycisk „Copy Voice ID" jest dostępny od
    razu — bez rozwijania „More actions".
  - By zminimalizować ewentualne regeneracje, najlepiej brać głosy z kolekcji
    „Best for Eleven v3"; alternatywnie „Voice Design", a dla odważnych IVC/PVC.
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
# Klient API (natywny SDK ``elevenlabs``) — most do ElevenLabs Studio (v17.1)
# =============================================================================
# Od v17.1 oficjalny SDK zamiast ręcznych żądań ``requests``. Receptura
# (potwierdzona spike'iem v16.0/v16.1) bez zmian:
#   - scope'y restricted key: projects_write + voices_read,
#   - tworzenie projektu z ``auto_convert`` POMINIĘTYM (=domyślne) NIE spala
#     kredytów (render robi użytkownik później w webie Studio).
# SDK importowany leniwie wewnątrz ``_klient`` — dzięki temu walidacja klucza
# (System Check, Etap 1) działa nawet bez tej zależności.

#: Strona webowa Studio — raport dispatchera linkuje tu, by user otworzył
#: projekt i wyrenderował mowę (deep-link per-projekt celowo pominięty —
#: format URL bywa zmienny; user odnajduje projekt po nazwie/ID).
STUDIO_URL = "https://elevenlabs.io/app/studio"
#: Model wielojęzyczny. v16.1: eleven_v3 — 70+ języków (pokrywa wszystkie 9
#: paczek) ORAZ honoruje audio-tagi ([whispers], [sighs]…), których tryb Skrypt
#: wplata w treść replik. Spike v16.1 potwierdził, że Studio Projects
#: (from_content_json) przyjmuje ten model_id. Poprzednio: eleven_multilingual_v2
#: (29 języków, ZERO tagów audio).
DEFAULT_MODEL_ID = "eleven_v3"
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


def _klient(klucz: str):
    """Tworzy klienta SDK ElevenLabs. Import leniwy — feature opcjonalny,
    walidacja klucza (System Check) działa nawet bez zainstalowanego SDK."""
    from elevenlabs.client import ElevenLabs
    return ElevenLabs(api_key=klucz)


def _opcje(timeout: int) -> dict:
    """RequestOptions SDK z timeoutem (SDK liczy w sekundach)."""
    return {"timeout_in_seconds": timeout}


def _mapuj_blad(exc) -> BladElevenLabs:
    """Mapuje ``ApiError`` SDK na nasze wyjątki fasadowe.

    Wyróżnia 401 ``missing_permissions`` jako :class:`BrakUprawnien`, by GUI
    mogło pokazać konkretną instrukcję o scope'ach zamiast generycznego błędu.
    Zachowuje kontrakt sprzed migracji SDK — ``gui_rezyser`` łapie te same dwa
    typy (:class:`BrakUprawnien`, :class:`BladElevenLabs`).
    """
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    if status == 401:
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, dict) and detail.get("status") == "missing_permissions":
            return BrakUprawnien(
                "Klucz ElevenLabs nie ma wymaganych uprawnień (scope'ów). "
                "Dodaj projects_write oraz voices_read w panelu ElevenLabs."
            )
        return BladElevenLabs("HTTP 401 — nieautoryzowany (sprawdź klucz ElevenLabs).")
    return BladElevenLabs(f"Błąd ElevenLabs (HTTP {status}): {str(body)[:300]}")


def saldo(klucz: str) -> dict:
    """``user.subscription.get`` — stan konta (0 kredytów).

    Zwraca słownik subskrypcji (``model_dump`` typu SDK); istotne pola to
    ``character_count`` (zużyte znaki) i ``character_limit`` (limit). Pozwala
    dispatcherowi pokazać świadomość kosztu przed renderem.
    """
    from elevenlabs.core import ApiError
    try:
        sub = _klient(klucz).user.subscription.get(
            request_options=_opcje(_TIMEOUT_ODCZYT)
        )
    except ApiError as exc:
        raise _mapuj_blad(exc) from exc
    return sub.model_dump()


def create_project(
    klucz: str,
    name: str,
    narrator_voice_id: str,
    chapters: list,
    *,
    model_id: str = DEFAULT_MODEL_ID,
    language: str | None = None,
    volume_normalization: bool = True,
) -> str:
    """Tworzy wielogłosowy projekt Studio. ``auto_convert`` POMINIĘTY → 0 kredytów.

    ``studio.projects.create`` (SDK). Render mowy to osobny krok po stronie
    użytkownika w webie Studio — tutaj powstaje tylko edytowalny projekt.

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
        model_id:          Domyślnie ``eleven_v3`` (:data:`DEFAULT_MODEL_ID`).
        language:          Kod ISO 639-1 języka projektu (np. ``"pl"``, ``"de"``).
                           Ustawia domyślny język Studio — bez niego v3 bywa
                           niespójny na liniach nagłówkowych (Prolog/Akt/Scena).
                           ``None`` → pole pomijane (Studio decyduje samo).
                           UWAGA: dla głosu z celowo obcym akcentem (np. fiński
                           akcent na polskim tekście) ustawienie języka może
                           osłabić ten efekt — to świadomy tradeoff renderu.
        volume_normalization: Włącza „Volume normalization" Studio („Normalize
                           volume to meet audiobook standards"). Domyślnie ``True``
                           — wyrównuje głośność do standardu audiobooka i, co
                           ważne, ustawia to przez API, więc reżyser nie musi
                           otwierać ustawień projektu w webie (gdzie v3-alpha
                           wyświetla nagabywania o zmianę modelu na Flash/v2).

    Returns:
        ``project_id`` utworzonego projektu.

    Raises:
        BrakUprawnien:  401 missing_permissions (brak scope'ów).
        BladElevenLabs: inny błąd HTTP lub nieoczekiwana struktura odpowiedzi.
    """
    import json
    from elevenlabs.core import ApiError

    # ``auto_convert`` POMINIĘTY (nie przekazujemy) → projekt powstaje bez
    # renderu = 0 kredytów. ``language`` przekazujemy tylko gdy ustawiony —
    # inaczej Studio wybiera samo (SDK pomija nieprzekazane pola).
    kwargs = dict(
        name=name,
        default_title_voice_id=narrator_voice_id,
        default_paragraph_voice_id=narrator_voice_id,
        default_model_id=model_id,
        from_content_json=json.dumps(chapters, ensure_ascii=False),
        volume_normalization=volume_normalization,
        request_options=_opcje(_TIMEOUT_PROJEKT),
    )
    if language:
        kwargs["language"] = language
    try:
        resp = _klient(klucz).studio.projects.create(**kwargs)
    except ApiError as exc:
        raise _mapuj_blad(exc) from exc

    projekt = getattr(resp, "project", None)
    project_id = getattr(projekt, "project_id", None)
    if not project_id:
        raise BladElevenLabs(
            f"Nieoczekiwana struktura odpowiedzi przy tworzeniu projektu: {str(resp)[:300]}"
        )
    return project_id


def delete_project(klucz: str, project_id: str) -> None:
    """``studio.projects.delete`` — sprzątanie (np. projektu testowego)."""
    from elevenlabs.core import ApiError
    try:
        _klient(klucz).studio.projects.delete(
            project_id, request_options=_opcje(_TIMEOUT_ODCZYT)
        )
    except ApiError as exc:
        raise _mapuj_blad(exc) from exc


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


#: Maks. długość linii, którą wolno uznać za nagłówek. Publiczna, bo tego
#: samego strażnika używa Architekt Audiobooków (`gui_konwerter`) — oba
#: parsery muszą tak samo odróżniać nagłówek od prozy narratora.
MAX_DLUGOSC_NAGLOWKA = 60


def czysty_naglowek(linia: str) -> str:
    """Obcina dekoracje ``= - spacja`` z obu stron linii nagłówka."""
    return re.sub(r"^[=\-\s]+|[=\-\s]+$", "", linia).strip()


def czy_moze_byc_naglowkiem(czysty: str) -> bool:
    """Czy oczyszczona linia w ogóle kwalifikuje się na nagłówek?

    Strażnik przeciw fałszywym trafieniom w erze narratora: linia opisowa
    narratora może zaczynać się od słowa „Scena"/„Akt". Nagłówkiem jest tylko
    linia KRÓTKA (≤ ``MAX_DLUGOSC_NAGLOWKA``) i BEZ interpunkcji zdaniowej
    ``.!?`` — zdania narratora („Scena była pusta.") przepadają przez filtr.
    """
    return bool(czysty) and len(czysty) <= MAX_DLUGOSC_NAGLOWKA \
        and not re.search(r"[.!?]", czysty)


# Aliasy wstecznej zgodności dla dotychczasowych, prywatnych nazw w tym module.
_czysty_naglowek = czysty_naglowek


def _klasyfikuj_naglowek(linia: str):
    """Zwraca ``("chapter"|"scene"|None, czysty_tekst)`` dla linii."""
    czysty = czysty_naglowek(linia)
    if not czy_moze_byc_naglowkiem(czysty):
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


def wykryj_sieroty(tekst: str) -> list:
    """Wykrywa linie-sieroty, które ``buduj_chapters`` po cichu pomija (v17.2).

    Format ``.txt`` pozwala wpisać dowolny nietagowany tekst w dowolnym miejscu,
    ale most Studio wymaga, by KAŻDA linia była albo wypowiedzią ze znacznikiem
    mówcy (``[Imię: …]``/`[Narrator: …]`), albo nagłówkiem struktury
    (Prolog/Akt/Scena/Rozdział…). Linia nietagowana i niebędąca nagłówkiem,
    która pojawia się, gdy żaden mówca nie jest aktywny (przed pierwszym tagiem
    albo zaraz po nagłówku, który zeruje bieżącego mówcę), nie trafia do żadnego
    ``tts_node`` — renderowany projekt rozjeżdża się z intencją reżysera. Ten
    strażnik pozwala GUI ostrzec PRZED budową (Zasada Montażysty, sekcja mostu).

    Stan ``mowca_aktywny`` jest wierną repliką stanu ``stan["mowca"]`` z
    :func:`buduj_chapters` — dzięki temu zwrócony zbiór to dokładnie linie, które
    parser dziś milcząco gubi. Linie kontynuujące bieżącego mówcę (po jego tagu,
    także przez puste linie) NIE są sierotami.

    Edge: tag o niesparsowalnej nazwie mówcy (np. ``[: x]`` — ``_wytnij_mowce``
    zwraca None) nie aktywuje mówcy, więc tekst po nim również wpada w sieroty
    (zgodnie z zachowaniem ``buduj_chapters``); sama taka linia-tag nie jest
    flagowana, bo to skrajny przypadek formatu, nie nietagowana proza.

    Returns:
        Lista ``(numer_linii_1based, tekst_linii_strip)`` w kolejności wystąpienia.
    """
    sieroty: list = []
    mowca_aktywny = False
    for nr, linia in enumerate(tekst.splitlines(), start=1):
        typ, _ = _klasyfikuj_naglowek(linia)
        if typ is not None:
            mowca_aktywny = False
            continue
        m = _RE_TAG.match(linia)
        if m:
            mowca_aktywny = bool(_wytnij_mowce(m.group(1)))
            continue
        if linia.strip() and not mowca_aktywny:
            sieroty.append((nr, linia.strip()))
    return sieroty


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
