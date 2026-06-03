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

Warstwa klienta HTTP (``requests``: ``list_voices``, ``create_project``,
``delete_project``) dochodzi w Etapie 2 — patrz dół pliku.
"""

from __future__ import annotations

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
# Klient HTTP (requests) — DOCHODZI W ETAPIE 2
# =============================================================================
# Planowane API (receptura ze spike'u v16.0):
#   - list_voices(klucz) -> list[dict]                     GET  /v1/voices
#   - saldo(klucz) -> int                                  GET  /v1/user/subscription
#   - create_project(klucz, name, narrator_voice, chapters) POST /v1/studio/projects
#     (multipart from_content_json, auto_convert pominięty = 0 kredytów)
#   - delete_project(klucz, project_id) -> None            DELETE /v1/studio/projects/{id}
# Auth: header ``xi-api-key``. Scope'y: projects_write + voices_read.
# Brak scope → HTTP 401 detail.status == "missing_permissions".
