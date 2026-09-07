"""
przepisy_rezysera.py – Loader „przepisów twórczych" modułu Reżyser Audio GPT.

Czym jest przepis?
    Zestaw danych opisujący JEDEN tryb pracy AI (Burza Mózgów / Skrypt /
    Audiobook) lub JEDNO narzędzie postprodukcyjne (np. nadawanie tytułów
    rozdziałom). Wszystko jest zapisane w plikach YAML w folderze
    ``dictionaries/<jezyk>/rezyser/``.

Dlaczego osobny plik?
    Historycznie prompty systemowe reżysera były zakute na sztywno w klasie
    ``RezyserPanel`` (``gui_rezyser.py``). Każda modyfikacja wymagała pracy
    programisty i budowania nowego release'u. Po refaktorze z wersji 13.0
    lingwista może:

      * zmienić język odpowiedzi (``jezyk_odpowiedzi: angielsku``),
      * osłabić lub wzmocnić Anti-Closure w trybie Audiobook,
      * podmienić model punktowo (pole ``model:``; domyślnie ``claude-sonnet-5``),
      * dodać zupełnie nowy tryb (np. ``tryb_poezja.yaml``) bez dotykania
        kodu Pythona – wystarczy nowy YAML i restart aplikacji.

Publiczne API (używane przez ``rezyser_ai.py`` i ``gui_rezyser.py``):

    import przepisy_rezysera as pr

    # Lista trybów do wypełnienia RadioBox w GUI:
    tryby = pr.lista_trybow(jezyk="pl")          # [PrzepisRezysera, ...]

    # Pojedynczy przepis po id:
    przepis = pr.zaladuj_przepis("audiobook")     # PrzepisRezysera | None
    postprod = pr.zaladuj_przepis("tytuly", kategoria="postprodukcja")

    # Postprodukcje oferowane w GUI dla bieżącego trybu (filtr `dla_trybow`):
    narzedzia = pr.postprodukcje_dla_trybu(przepis)

    # Zbudowanie końcowego prompt systemowego (podstawia {world_context}
    # i {jezyk_odpowiedzi} w szablonie z YAML-a):
    sys_prompt = pr.buduj_prompt_systemowy(przepis, world_context="...")

    # Zbudowanie sufiksu kontekstowego (np. "alarm" dla Burzy):
    sufiks = pr.buduj_sufiks(przepis, "alarm")

    # Zbudowanie przypomnienia doklejanego do treści użytkownika:
    przypom = pr.buduj_przypomnienie(przepis)

Moduł NIE zależy od wxPython ani od żadnego SDK modelu (OpenAI/Anthropic)
– to czysty loader danych.
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from typing import Any

import yaml

import sciezki


# =============================================================================
# Ścieżki i stałe
# =============================================================================
_ROOT_DIR = sciezki.KATALOG_BAZOWY_STR
DICTIONARIES_DIR = os.path.join(_ROOT_DIR, "dictionaries")

# Podfolder w ``dictionaries/<jezyk>/`` w którym trzymane są przepisy reżysera.
FOLDER_REZYSER = "rezyser"

# Kategorie przepisów. Lingwista może tworzyć własne (np. „scenariusz"),
# ale silnik domyślnie rozumie tylko te dwie.
KATEGORIA_TRYB = "tryb"
KATEGORIA_POSTPROD = "postprodukcja"

# Zakresy przetwarzania postprodukcji (pole ``zakres:`` w YAML, v18.12):
#   per_rozdzial   – iteracja po nagłówkach struktury pliku projektu
#                    (wzorzec tytułów rozdziałów),
#   calosc         – jeden call LLM z całym plikiem projektu (wzorzec raportu),
#   rekoncyliacja  – (v18.13) wejście składane z trzech członów zamiast całego
#                    pliku: dotychczasowe streszczenie + narracja od anchora
#                    z ``_streszczenie_meta.json`` + reszta. Wzorzec Pamięci
#                    Długotrwałej: kolejne streszczenie jest PRZYROSTOWE, a
#                    payload nie rośnie liniowo z długością projektu.
ZAKRES_PER_ROZDZIAL = "per_rozdzial"
ZAKRES_CALOSC = "calosc"
ZAKRES_REKONCYLIACJA = "rekoncyliacja"

# Role postprodukcji (pole ``rola:`` w YAML, v18.13). Pusta = zwykłe narzędzie
# (wynik do dialogu i opcjonalnie do pliku ``<nazwa><sufiks>.txt``).
#   pamiec_dlugotrwala – wynik JEST Pamięcią Długotrwałą projektu: GUI zapisuje
#                        go przez ``ProjektRezysera.zapisz_streszczenie`` (plik +
#                        meta-anchor + stan w RAM + pole „Pamięć" w GUI), a nie
#                        zwykłym zapisem pliku wyniku. Bez tej roli plik powstałby
#                        „obok", a meta-anchor rekoncyliacji rozjechałby się
#                        z treścią — kolejne wczytanie projektu snapowałoby do
#                        nieaktualnego nagłówka.
ROLA_PAMIEC_DLUGOTRWALA = "pamiec_dlugotrwala"

# Sufiks pliku Pamięci Długotrwałej używany, gdy paczka nie ma przepisu z rolą
# :data:`ROLA_PAMIEC_DLUGOTRWALA` (np. user skasował YAML albo paczka jest sprzed
# v18.13). Historyczna wartość — pliki `<nazwa>_streszczenie.txt` istnieją
# u każdego, kto używał Reżysera przed tym wydaniem.
SUFIKS_STRESZCZENIA_DOMYSLNY = "_streszczenie"

# Sufiks paczki `en` (v18.14). Pełni PODWÓJNĄ rolę: jest wartością
# ``sufiks_pliku_wyniku`` w ``en/rezyser/postprod_streszczenie.yaml`` ORAZ stałą
# REGUŁY MIĘDZYNARODOWEGO FALLBACKU. Od v18.14 sufiks JEST lokalizowany (v18.13
# wymagała jeszcze identycznej wartości we wszystkich paczkach — patrz
# :func:`sufiksy_pamieci_dlugotrwalej`), więc aplikacja musi rozpoznać plik
# pamięci także wtedy, gdy paczka, która go wytworzyła, nie jest zainstalowana
# (user ją skasował, przeniósł projekt na inną maszynę, wrócił do innego języka).
# „Na sucho", bez żadnego YAML-a, rozpoznajemy więc dwa sufiksy: neutralny
# angielski ``_overview`` i historyczny ``_streszczenie``.
SUFIKS_PAMIECI_MIEDZYNARODOWY = "_overview"

# Domyślne limity tokenów wyjścia postprodukcji, gdy YAML nie podaje
# ``max_tokens_wyjscia:`` — wartości historyczne obu wzorców (tytuł rozdziału
# to jedna linia; raport całościowy to kilka stron).
MAX_TOKENS_PER_ROZDZIAL_DOMYSLNE = 256
MAX_TOKENS_CALOSC_DOMYSLNE = 8_000

# Znaki zakazane w ``sufiks_pliku_wyniku:`` — sufiks trafia wprost do nazwy
# pliku ``skrypty/<nazwa><sufiks>.txt``, więc separatory ścieżek i znaki
# specjalne Windows odpadają (YAML jest edytowalny przez usera w Managerze).
_ZNAKI_ZAKAZANE_SUFIKSU = '\\/:*?"<>|'

# Domyślny model AI dla przepisów BEZ jawnego pola ``model:`` w YAML-u.
# Od v18.2 cały silnik Reżysera jedzie na Anthropic Claude (``rezyser_ai``
# woła ``messages.create`` z ``model=przepis.model``), więc fallback MUSI być
# identyfikatorem Anthropic. Gdyby został dawny ``"gpt-4o"``, przepis lingwisty
# bez pola ``model:`` przekazałby do API model nieznany Anthropic i wywaliłby
# całe wywołanie (404 model-not-found). Paczki shippowane mają ``model:``
# wypełnione — ta stała chroni ręcznie tworzone / edytowane YAML-e.
MODEL_DOMYSLNY = "claude-sonnet-5"


# -----------------------------------------------------------------------------
# Detekcja odrzucenia przez AI – niezależna od języka odpowiedzi
# -----------------------------------------------------------------------------
# Historia: pierwotnie utrzymywaliśmy listę fraz ("as an ai", "nie mogę...")
# w każdym YAML-u trybu zapisu. Gdy lingwista zmieniał `jezyk_odpowiedzi`
# na np. fiński, te frazy przestawały pasować i odmowa modelu mogła
# przedostać się do pliku historii.
#
# Rozwiązanie (od wersji 13.0): wymuszamy na modelu zwrócenie jednego,
# niezmiennego tagu (``[ODRZUCENIE_AI]``) — nawet gdy cała reszta
# odpowiedzi byłaby w obcym języku. Klauzula systemowa poniżej jest
# celowo po angielsku: model (Claude/GPT) traktuje angielskie "SYSTEM RULE"
# nadal z wyższym priorytetem niż treści w języku użytkownika.
TAG_ODRZUCENIA_AI = "[ODRZUCENIE_AI]"

KLAUZULA_ODRZUCENIA_DOMYSLNA = (
    "\n\n---\n"
    "SYSTEM RULE (do not translate, do not rephrase, do not localize):\n"
    "If you CANNOT or WILL NOT fulfill the request for ANY reason "
    "(safety policy, ethical refusal, content filters, missing information, "
    "ambiguity), respond with EXACTLY this ONE LINE and NOTHING else:\n"
    f"{TAG_ODRZUCENIA_AI}\n"
    "Do not translate the tag. Do not add apologies before or after it. "
    "Do not continue the scene. This tag is an infrastructure marker for "
    "the application – it must appear verbatim, in the Latin alphabet, "
    "regardless of the user's language of choice."
)


# =============================================================================
# Model danych
# =============================================================================
@dataclass
class PrzepisRezysera:
    """Pojedynczy przepis twórczy załadowany z YAML-a.

    Pola wspólne są zawsze wypełnione. Pola specyficzne (np. ``sufiksy``
    albo ``regex_podzial_rozdzialow``) mają sensowne wartości domyślne —
    dzięki temu YAML lingwisty może je po prostu pomijać, jeśli nie są
    mu potrzebne.

    Attributes:
        id:               Unikalny identyfikator (np. ``"audiobook"``).
        etykieta:         Tekst wyświetlany w RadioBox / menu GUI.
        kategoria:        ``"tryb"`` lub ``"postprodukcja"``.
        kolejnosc:        Sortowanie wyświetlania (rosnąco).
        model:            Nazwa modelu AI (np. ``"claude-sonnet-5"``);
                          pominięte w YAML → :data:`MODEL_DOMYSLNY` (Anthropic).
        temperatura:      Parametr ``temperature`` wywołania API.
        jezyk_odpowiedzi: Rzeczownik w miejscowniku (``"polsku"``,
                          ``"angielsku"``) wstawiany jako placeholder
                          ``{jezyk_odpowiedzi}`` w promptach.
        prompt_systemowy: Główny prompt z ``role=system``. Może używać
                          placeholderów ``{world_context}``,
                          ``{jezyk_odpowiedzi}``.
        zapis_do_pliku:   (tylko tryb) True → odpowiedź trafia do
                          ``skrypty/<nazwa>.txt``.
        stosuj_akcenty_fonetyczne:
                          (tylko tryb) True → odpowiedź przechodzi przez
                          silnik akcentów
                          (``core_poliglota.zastosuj_reguly_fonetyczne``).
        przypomnienie_uzytkownika:
                          (tylko tryb) Tekst doklejany do treści
                          ``role=user`` tuż przed wysłaniem.
        sufiksy:          (tylko tryb) Mapa ``nazwa → tekst`` doklejana
                          do ``prompt_systemowy`` w zależności od stanu
                          pamięci / słów w instrukcji użytkownika.
                          Typowe nazwy: ``startowy``, ``kontynuacja``,
                          ``streszczenie``, ``alarm``, ``optymalizacja``.
        slowa_wyzwalajace:
                          (tylko tryb) Mapa ``kategoria → lista słów``.
                          ``streszczenie`` – słowa powodujące doklejenie
                          sufiksu ``streszczenie`` (Burza) lub blokadę
                          wysłania (Skrypt/Audiobook).
                          Detekcja odrzucenia przez AI NIE używa już tej
                          mapy – zastąpiono ją uniwersalnym tagiem
                          ``[ODRZUCENIE_AI]`` (patrz ``wykryto_odrzucenie``),
                          niezależnym od ``jezyk_odpowiedzi``.
        klauzula_odrzucenia:
                          Opcjonalna klauzula systemowa wymuszająca na AI
                          zwrócenie tagu ``[ODRZUCENIE_AI]`` przy odmowie.
                          Pusta wartość (domyślnie) = używaj wbudowanej
                          ``KLAUZULA_ODRZUCENIA_DOMYSLNA``. Pole istnieje
                          głównie po to, by lingwista-eksperymentator mógł
                          przetestować własne sformułowanie (np. bardziej
                          kategoryczne lub po fińsku) bez zmian w kodzie.
        prompt_uzytkownika_szablon:
                          (tylko postprodukcja) Szablon ``role=user``
                          z placeholderami takimi jak ``{naglowek}``,
                          ``{probka}``.
        regex_podzial_rozdzialow:
                          (tylko postprodukcja tytułów) Regex dzielący
                          plik projektu na nagłówki + treści.
        min_dlugosc_fragmentu:
                          (tylko postprodukcja) Fragmenty krótsze → skip.
        max_dlugosc_probki:
                          (tylko postprodukcja) Ile znaków próbki
                          przekazujemy modelowi z każdego rozdziału.
        etykieta_fragment_zbyt_krotki:
                          (tylko postprodukcja) Napis zastępczy gdy
                          rozdział jest za krótki by generować tytuł.
        etykieta_bled_brak_kredytow:
                          (tylko postprodukcja) Napis przy ``RateLimitError``.
        etykieta_odrzucenie:
                          (tylko postprodukcja) Napis gdy model odrzucił tytuł
                          (tag odrzucenia). W języku treści przepisu.
        etykieta_blad_fragment:
                          (tylko postprodukcja) Szablon napisu przy nieoczekiwanym
                          błędzie fragmentu; placeholder ``{blad}`` = treść wyjątku.
        dla_trybow:       (tylko postprodukcja, v18.12) Lista ``id`` trybów,
                          w których GUI oferuje to narzędzie. Pusta lista =
                          narzędzie widoczne we wszystkich trybach
                          z ``zapis_do_pliku`` (postprodukcja operuje na pliku
                          projektu, więc tryb bez zapisu nie ma na czym
                          pracować). YAML sprzed v18.12 bez pola → shim po
                          ``id`` (:data:`_DLA_TRYBOW_LEGACY`).
        zakres:           (tylko postprodukcja, v18.12) Sposób przetwarzania
                          pliku projektu: :data:`ZAKRES_PER_ROZDZIAL` (iteracja
                          po nagłówkach, jak tytuły) lub :data:`ZAKRES_CALOSC`
                          (jeden call z całym plikiem). Nieznana wartość →
                          plik pominięty (literówka nie może po cichu zmienić
                          ścieżki silnika).
        max_tokens_wyjscia:
                          (tylko postprodukcja, v18.12) Limit tokenów wyjścia
                          pojedynczego wywołania LLM. Pominięte/0 → domyślne
                          per zakres (256 / 8000).
        sufiks_pliku_wyniku:
                          (tylko postprodukcja, v18.12) Niepusty → GUI zapisuje
                          wynik do ``skrypty/<nazwa><sufiks>.txt`` (np.
                          ``"_audyt"``). Pusty = wynik tylko w dialogu
                          (zachowanie tytułów).
        prompt_ksiegi_szablon:
                          (tylko postprodukcja ``calosc``, v18.12) Szablon bloku
                          Księgi Świata z placeholderem ``{ksiega}``, doklejany
                          PRZED treścią gdy ``skrypty/<nazwa>.md`` istnieje
                          i jest niepusty. Brak pola = księga ignorowana.
        rola:             (tylko postprodukcja, v18.13) Specjalne znaczenie wyniku
                          dla silnika. Dziś jedna wartość:
                          :data:`ROLA_PAMIEC_DLUGOTRWALA`. Pusta = zwykłe
                          narzędzie. Nieznana wartość jest IGNOROWANA (degraduje
                          się do zwykłego narzędzia) — w odróżnieniu od ``zakres``,
                          gdzie literówka zmieniałaby ścieżkę przetwarzania.
    """

    # --- Wspólne ---
    id: str
    etykieta: str
    kategoria: str
    kolejnosc: int = 0
    model: str = MODEL_DOMYSLNY
    temperatura: float = 0.85
    jezyk_odpowiedzi: str = "polsku"
    # v17.9 (Obszar 3b): kod ISO języka TREŚCI generowanej przez ten przepis
    # (np. "fi"), odrębny od prozaicznego `jezyk_odpowiedzi` ("fińsku"). Steruje
    # JEDNOCZEŚNIE: (a) doborem `dictionaries/<kod>/akcenty/` przy post-processingu
    # fonetycznym, (b) językiem nagłówków struktury (Prolog/Akt/Scena) przez
    # `t(..., jezyk_override=kod)`. Puste = lingwista nie wypełnił → GUI
    # wnioskuje kod mikrorequestem LLM z `jezyk_odpowiedzi` (rezyser_ai.
    # wywnioskuj_kod_jezyka) i wpisuje tu z powrotem; halucynacja → błąd dla
    # reżysera. Paczki shippowane mają to pole wypełnione (= kod pakietu).
    kod_jezyka: str = ""
    prompt_systemowy: str = ""

    # --- Tryb ---
    # Format odpowiedzi modelu, wg którego GUI dobiera ścieżkę przetwarzania
    # (`gui_rezyser._wyslij_worker`). Zastępuje dawny dispatch po `id`
    # (zahardkodowane `if id == "skrypt"/"burza"`), dzięki czemu nowy tryb
    # JSON powstaje przez samą duplikację YAML — bez zmiany w kodzie:
    #   "tekst"       – zwykła proza (generuj_fragment, bez response_format),
    #   "skrypt_json" – {"tury":[{mowca,tekst}]} → renderuj_skrypt (Teatr czytany),
    #   "burza_json"  – 3 opcje fabuły (generuj_burze, BEZ zapisu do pliku).
    # Nowy SCHEMAT JSON (inny niż dwa powyższe) nadal wymaga programisty.
    format_wyjscia: str = "tekst"
    # Sposób segmentacji pliku projektu (.txt) na punkty odniesienia pamięci
    # roboczej — steruje `core_rezyser.wyliczy_markery` ORAZ panelem struktury
    # w GUI (które przyciski Prolog/Akt/Scena/Rozdział pokazać). Zastępuje dawny
    # pozycyjny `tryb_idx == 1/2`, dzięki czemu tryb identyfikuje się stabilnym
    # `id`, a nie pozycją w RadioBox (reorder `kolejnosc` nie przestawia już
    # znaczeń). Parser nagłówków (`_znajdz_naglowki`) jest GENERYCZNY, więc
    # reużycie istniejącej wartości to sam YAML:
    #   "akty_sceny" – Akty z zagnieżdżonymi Scenami (Skrypt: teatr czytany),
    #   "rozdzialy"  – płaska lista Rozdziałów (Audiobook: proza),
    #   "brak"       – tryb bez struktury pliku (np. planowanie / Burza).
    # Nowy TYP nagłówka (inny niż Prolog/Akt/Scena/Rozdział/Epilog) wymaga
    # programisty (rozszerzenie regexa) — ta sama granica co przy `format_wyjscia`.
    struktura: str = "brak"
    zapis_do_pliku: bool = False
    stosuj_akcenty_fonetyczne: bool = False
    przypomnienie_uzytkownika: str = ""
    sufiksy: dict[str, str] = field(default_factory=dict)
    slowa_wyzwalajace: dict[str, list[str]] = field(default_factory=dict)
    klauzula_odrzucenia: str = ""   # "" = użyj KLAUZULA_ODRZUCENIA_DOMYSLNA

    # --- Burza Mózgów (v15.2) ---
    # Lokalizowany blok doklejany przez Python do `cel_sceny` z odpowiedzi
    # JSON LLM-a po kliknięciu opcji w GUI. Zawiera `[Reżyserze: ...]` i
    # `[DYREKTYWA]: ...`. Patrz `rezyser_ai.doklejka_celu_sceny`. Pusty
    # string = brak doklejki (kompatybilność wsteczna z yaml-ami bez klucza).
    doklejka_celu_sceny: str = ""

    # --- Postprodukcja ---
    prompt_uzytkownika_szablon: str = ""
    regex_podzial_rozdzialow: str = ""
    min_dlugosc_fragmentu: int = 0
    max_dlugosc_probki: int = 0
    etykieta_fragment_zbyt_krotki: str = ""
    etykieta_bled_brak_kredytow: str = ""
    etykieta_odrzucenie: str = ""
    etykieta_blad_fragment: str = ""

    # --- Postprodukcja: generalizacja (v18.12) ---
    dla_trybow: list[str] = field(default_factory=list)
    zakres: str = ZAKRES_CALOSC
    max_tokens_wyjscia: int = MAX_TOKENS_CALOSC_DOMYSLNE
    sufiks_pliku_wyniku: str = ""
    prompt_ksiegi_szablon: str = ""

    # --- Postprodukcja: rola wyniku (v18.13) ---
    rola: str = ""

    # --- Postprodukcja: walidacja karty publikacyjnej (v18.14) ---
    # Listy DOZWOLONYCH wartości pól, które platforma publikacyjna przyjmuje
    # tylko z zamkniętego zbioru (gatunki, grupa odbiorców) + limit długości
    # opisu. Trafiają do prompta przez placeholdery (`{gatunki_dozwolone}`,
    # `{odbiorcy_dozwoleni}`, `{limit_znakow_opisu}`) ORAZ do walidatora
    # w Pythonie — model dostaje listę na tacy, a my sprawdzamy, czy jej
    # nie zignorował. Bez tej pary halucynowana kategoria wraca do reżysera
    # jako gotowa do wklejenia, a formularz odrzuca ją dopiero na platformie.
    gatunki_dozwolone: list[str] = field(default_factory=list)
    odbiorcy_dozwoleni: list[str] = field(default_factory=list)
    limit_znakow_opisu: int = 0


# =============================================================================
# Rejestr pominiętych plików (v18.24.2) — diagnostyka dla użytkownika paczki
# =============================================================================
# Do v18.24.1 loader mówił „dlaczego pominąłem twój plik" wyłącznie przez
# ``print(..., file=sys.stderr)``. W buildzie ``--windowed`` ``sys.stderr`` jest
# ``None``, a ``print`` z takim celem sięga po ``sys.stdout`` (też ``None``)
# i MILCZY — kto zepsuł przepis w Managerze Reguł, widział tylko brak opcji
# w RadioBoxie albo brak przycisku postprodukcji. Najgorsza była szósta ścieżka,
# niema także w trybie dev: błąd składni YAML wracał z ``_wczytaj_yaml`` jako
# pusty słownik, więc przepis znikał bez ANI JEDNEJ linii komunikatu.
#
# Rozwiązanie: powody pominięcia zbieramy STRUKTURALNIE (kod powodu + dane
# techniczne), a tekst dla użytkownika składa warstwa GUI przez ``i18n``
# (``gui_diagnostyka``). Ten moduł pozostaje wx-free i i18n-free — kody powodów
# są jego kontraktem, nie zdaniami do przetłumaczenia.
POWOD_PARSE     = "parse"       # pliku nie da się sparsować (składnia YAML)
POWOD_BRAK_POL  = "brak_pol"    # brak wymaganych `id` / `etykieta` / `kategoria`
POWOD_KATEGORIA = "kategoria"   # `kategoria:` poza zbiorem rozumianym przez silnik
POWOD_ZAKRES    = "zakres"      # `zakres:` poza zbiorem (postprodukcja)
POWOD_SUFIKS    = "sufiks"      # niedozwolone znaki w `sufiks_pliku_wyniku`
POWOD_POLE      = "pole"        # zły typ/wartość pola (TypeError/ValueError)
POWOD_DUPLIKAT  = "duplikat"    # dwa pliki o tym samym `id` w jednej kategorii
POWOD_ROLA      = "rola"        # nieznana `rola:` — pole zignorowane, plik działa
POWOD_KLUCZ     = "klucz"       # brak klucza wymaganego przez silnik (Opowieści)
POWOD_WPIS      = "wpis"        # wadliwy wpis WEWNĄTRZ pliku (np. zaczątek)
POWOD_LINGUA    = "lingua"      # `lingua:` w podstawy.yaml: nazwa nieznana detektorowi


@dataclass(frozen=True)
class PominietyPlik:
    """Jeden powód, dla którego silnik pominął plik reguł (albo jego fragment).

    Args:
        sciezka:  Pełna ścieżka pliku — użytkownik musi wiedzieć, co otworzyć
                  w Managerze Reguł.
        powod:    Kod ``POWOD_*`` (klucz i18n składany w ``gui_diagnostyka``).
        szczegol: Dane techniczne dla dewelopera/lingwisty (numer linii, nazwa
                  pola, dozwolone wartości). Celowo NIE tłumaczone — to cytat
                  z pliku albo z wyjątku, jak ``{tresc_bledu}`` w innych
                  komunikatach.
    """

    sciezka: str
    powod: str
    szczegol: str = ""


# Kolejność zgłoszeń zachowana (użytkownik czyta raport plik po pliku), ale bez
# duplikatów: ten sam plik wczytywany dla dwóch języków albo dwa razy w jednej
# sesji nie może rozdmuchać raportu. Lock, bo loadery wołają wątki tła AI
# (`rezyser_ai`, worker Opowieści) równolegle z wątkiem GUI — bez niego wyścig
# na „sprawdź i dopisz" wpuszczałby ten sam powód do raportu dwa razy.
_POMINIETE: list[PominietyPlik] = []
_LOCK_POMINIETE = threading.Lock()


def _dev_log(komunikat: str) -> None:
    """Strażowany ``print`` na konsolę dewelopera (packaged: stdout None → milczy).

    Wzorzec ``core_llm._dev_log`` / ``core_rezyser._dev_log_runtime`` — w paczce
    release aplikacja chodzi bez konsoli, a goły ``print`` mógłby ubić proces.
    Rejestr powyżej jest kanałem dla UŻYTKOWNIKA, ten log — dla dewelopera,
    który uruchamia aplikację ze źródła i chce zobaczyć powód od razu.
    """
    try:
        if sys.stdout is not None:
            print(f"[przepisy_rezysera] {komunikat}", file=sys.stdout)
    except Exception:  # noqa: BLE001 — log nigdy nie może ubić wywołania
        pass


def zglos_pominiecie(sciezka: str, powod: str, szczegol: str = "") -> None:
    """Zapisuje powód pominięcia do rejestru i na konsolę dewelopera.

    Wołane przez loadery danych edytowalnych przez użytkownika — ten moduł oraz
    ``opowiesci_ai`` (import z tego miejsca, żeby oba panele raportowały jednym
    kanałem). Idempotentne: ta sama trójka (ścieżka, powód, szczegół) nie
    dopisuje się dwa razy.
    """
    wpis = PominietyPlik(sciezka=sciezka, powod=powod, szczegol=szczegol)
    with _LOCK_POMINIETE:
        if wpis in _POMINIETE:
            return
        _POMINIETE.append(wpis)
    _dev_log(f"{powod}: {sciezka} ({szczegol})" if szczegol
             else f"{powod}: {sciezka}")


def _zgloszono_blad_parsera(sciezka: str) -> bool:
    """Czy dla tego pliku zgłoszono już błąd składni?

    Plik, którego parser nie zrozumiał, wraca z :func:`_wczytaj_yaml` jako pusty
    słownik — a dalszy filtr „brak wymaganych pól" widziałby wtedy TEN SAM plik
    drugi raz i dopisywał userowi mylący, wtórny powód. Przyczyna jest jedna
    (składnia), więc raport ma o niej mówić jednym wpisem.
    """
    with _LOCK_POMINIETE:
        return any(
            w.sciezka == sciezka and w.powod == POWOD_PARSE for w in _POMINIETE
        )


def pominiete_pliki() -> tuple[PominietyPlik, ...]:
    """Zwraca wszystkie zebrane powody pominięcia (pusta krotka = czysto).

    Rejestr wypełnia się LENIWIE, w miarę wczytywania paczek — panel woła tę
    funkcję po zbudowaniu swojej listy trybów/przepisów, więc widzi powody
    dotyczące dokładnie tych plików, które próbował wczytać.
    """
    with _LOCK_POMINIETE:
        return tuple(_POMINIETE)


def wyczysc_pominiecia() -> None:
    """Zapomina zebrane powody (wołane razem z czyszczeniem cache przepisów)."""
    with _LOCK_POMINIETE:
        _POMINIETE.clear()


# =============================================================================
# Cache wczytanych przepisów
# =============================================================================
# Klucz: język ("pl"). Wartość: lista przepisów w kolejności z dysku.
# yaml.safe_load zwraca świeży dict przy każdym wywołaniu, więc cache jest
# bezpieczny dla wielu wątków (nie modyfikujemy zawartości po wczytaniu).
_CACHE_PRZEPISOW: dict[str, list[PrzepisRezysera]] = {}

# Cache unii sufiksów plików wyniku ze wszystkich paczek (v18.14) — patrz
# :func:`sufiksy_wynikow_wszystkich_paczek`. ``None`` = jeszcze nie liczone
# (pusta krotka jest legalnym wynikiem, więc sentinelem nie może być falsy).
_CACHE_SUFIKSY_GLOBALNE: tuple[str, ...] | None = None


# Mapa wstecznej zgodności id → struktura dla paczek sprzed pola `struktura`
# (dwa tryby strukturalne shippowane od początku). Patrz pole `struktura`
# w :class:`PrzepisRezysera`.
_STRUKTURA_LEGACY: dict[str, str] = {
    "skrypt": "akty_sceny",
    "audiobook": "rozdzialy",
}

# Shimy wstecznej zgodności postprodukcji sprzed v18.12 (pola `dla_trybow`
# i `zakres` nie istniały; jedyną shippowaną postprodukcją były tytuły
# rozdziałów Audiobooka). Kanonicznym źródłem są odtąd pola w YAML —
# paczki shippowane mają je wypełnione, shim chroni YAML-e userów.
_DLA_TRYBOW_LEGACY: dict[str, list[str]] = {
    "tytuly": ["audiobook"],
}
_ZAKRES_LEGACY: dict[str, str] = {
    "tytuly": ZAKRES_PER_ROZDZIAL,
}


# =============================================================================
# Wczytywanie YAML-i
# =============================================================================
def _yaml_to_przepis(data: dict, sciezka: str) -> PrzepisRezysera | None:
    """Konwertuje słownik z YAML na :class:`PrzepisRezysera`.

    Zwraca ``None`` dla YAML-i bez wymaganych pól (``id``, ``etykieta``,
    ``kategoria``) lub dla YAML-i technicznych (``kategoria: oczyszczenie``),
    których nie chcemy pokazywać w liście trybów. Każde odrzucenie zgłasza powód
    do rejestru (:func:`zglos_pominiecie`) — z jednym wyjątkiem: pliku wspólnego
    ``baza.yaml``, który LEGALNIE nie jest przepisem (brak ``id``) i musi
    przechodzić przez ten filtr po cichu, żeby nie straszyć użytkownika
    „pominięciem" pliku, który działa poprawnie.
    """
    if not isinstance(data, dict) or not data:
        # Pusty słownik = plik pusty albo nie do sparsowania. Drugi przypadek
        # zaraportował już `_wczytaj_yaml` (z numerem linii), pierwszy zgłaszamy
        # tutaj — tylko dla plików, które mają być przepisami.
        if not _czy_plik_wspolny(sciezka) and not _zgloszono_blad_parsera(sciezka):
            zglos_pominiecie(sciezka, POWOD_BRAK_POL, "id, etykieta, kategoria")
        return None

    id_ = data.get("id")
    etykieta = data.get("etykieta")
    kategoria = data.get("kategoria")
    if not id_ or not etykieta or not kategoria:
        if not _czy_plik_wspolny(sciezka):
            brakujace = ", ".join(
                nazwa for nazwa, wartosc in (
                    ("id", id_), ("etykieta", etykieta), ("kategoria", kategoria))
                if not wartosc
            )
            zglos_pominiecie(sciezka, POWOD_BRAK_POL, brakujace)
        return None

    # Pomijamy kategorie pomocnicze, które mogłyby wylądować w tym samym
    # folderze przez pomyłkę (np. cudze YAML-e).
    if kategoria not in (KATEGORIA_TRYB, KATEGORIA_POSTPROD):
        zglos_pominiecie(
            sciezka, POWOD_KATEGORIA,
            f"kategoria={kategoria!r} ≠ {KATEGORIA_TRYB!r} / {KATEGORIA_POSTPROD!r}",
        )
        return None

    # Format wyjścia steruje dispatchem w gui_rezyser. Jeśli YAML nie ma pola
    # (paczki sprzed wprowadzenia `format_wyjscia`), wnioskujemy je z `id` dla
    # dwóch trybów JSON istniejących od v15.2/v16.1 — czysto wsteczna zgodność,
    # kanonicznym źródłem jest odtąd samo pole w YAML.
    format_wyjscia = str(data.get("format_wyjscia", "")).strip().lower()
    if not format_wyjscia:
        format_wyjscia = {
            "burza": "burza_json",
            "skrypt": "skrypt_json",
        }.get(str(id_), "tekst")

    # Struktura: analogiczny shim wstecznej zgodności jak `format_wyjscia` —
    # paczki sprzed wprowadzenia pola wnioskują wartość z `id` dla dwóch trybów
    # strukturalnych shippowanych od początku; kanonicznym źródłem jest odtąd
    # samo pole w YAML.
    struktura = str(data.get("struktura", "")).strip().lower()
    if not struktura:
        struktura = _STRUKTURA_LEGACY.get(str(id_), "brak")

    # Pola generalizacji postprodukcji (v18.12). `zakres` wybiera ścieżkę
    # silnika (iteracja vs jeden call z całym plikiem), więc literówka
    # lingwisty nie może po cichu zmienić znaczenia — nieznana wartość pomija
    # plik z ostrzeżeniem, jak błędny typ pola niżej. Idiom `or ""`/`or 0`
    # (audyt 18.12, ŚREDNIA-3): klucz obecny z pustą wartością (YAML null)
    # ma znaczyć „użyj defaultu", nie literalne str(None)="None".
    zakres = str(data.get("zakres") or "").strip().lower()
    if not zakres:
        zakres = _ZAKRES_LEGACY.get(str(id_), ZAKRES_CALOSC)
    if kategoria == KATEGORIA_POSTPROD and zakres not in (
            ZAKRES_PER_ROZDZIAL, ZAKRES_CALOSC, ZAKRES_REKONCYLIACJA):
        zglos_pominiecie(
            sciezka, POWOD_ZAKRES,
            f"zakres={zakres!r} ∉ {{{ZAKRES_PER_ROZDZIAL!r}, "
            f"{ZAKRES_CALOSC!r}, {ZAKRES_REKONCYLIACJA!r}}}",
        )
        return None

    # `dla_trybow`: rozróżniamy BRAK pola (shim legacy po `id`) od jawnie
    # pustej listy (= wszystkie tryby zapisu, patrz `postprodukcje_dla_trybu`).
    # Pojedynczy string (`dla_trybow: audiobook`) przyjmujemy łaskawie jako
    # listę jednoelementową — to naturalny skrót w ręcznie pisanym YAML-u.
    if "dla_trybow" in data:
        surowe = data.get("dla_trybow")
        if not isinstance(surowe, list):
            surowe = [surowe] if surowe is not None else []
        dla_trybow = [str(x).strip().lower() for x in surowe if str(x).strip()]
    else:
        dla_trybow = list(_DLA_TRYBOW_LEGACY.get(str(id_), []))

    # Rola wyniku (v18.13). Nieznana wartość → traktujemy jak brak (zwykłe
    # narzędzie): rola tylko DODAJE zachowanie po sukcesie, więc literówka nie
    # może przekierować przetwarzania w złe miejsce — inaczej niż `zakres`.
    rola = str(data.get("rola") or "").strip().lower()
    if rola and rola != ROLA_PAMIEC_DLUGOTRWALA:
        zglos_pominiecie(
            sciezka, POWOD_ROLA,
            f"rola={rola!r} ≠ {ROLA_PAMIEC_DLUGOTRWALA!r}",
        )
        rola = ""

    # Sufiks trafia wprost do nazwy pliku wyniku — separatory ścieżek i znaki
    # specjalne Windows dyskwalifikują plik (YAML edytowalny w Managerze).
    sufiks_pliku_wyniku = str(data.get("sufiks_pliku_wyniku") or "").strip()
    if rola == ROLA_PAMIEC_DLUGOTRWALA and not sufiks_pliku_wyniku:
        # Pamięć Długotrwała MUSI mieć gdzie wylądować — pusty sufiks oznaczałby
        # nadpisanie samego pliku narracji `<nazwa>.txt`. Spadamy na historyczną
        # wartość zamiast pomijać plik: user dostaje działające narzędzie.
        sufiks_pliku_wyniku = SUFIKS_STRESZCZENIA_DOMYSLNY
    if any(z in sufiks_pliku_wyniku for z in _ZNAKI_ZAKAZANE_SUFIKSU):
        # Szczegół bez ani jednego słowa (wartość pola | lista zakazanych znaków):
        # to samo zdanie ma czytać user w każdym z dziewięciu języków, a co znaczy
        # ten zapis, mówi zlokalizowany `diag.powod.sufiks`.
        zglos_pominiecie(
            sciezka, POWOD_SUFIKS,
            f"sufiks_pliku_wyniku={sufiks_pliku_wyniku!r} | "
            f"{' '.join(_ZNAKI_ZAKAZANE_SUFIKSU)}",
        )
        return None

    # Konwersje pól są celowo objęte guardem (v18.9): `rezyser/*.yaml` to plik
    # EDYTOWALNY przez usera w Managerze Reguł, więc `kolejnosc:` bez wartości
    # (None → TypeError), `kolejnosc: abc` (ValueError) albo `sufiksy:` podane
    # jako lista (AttributeError na `.items()`) to realne wejście, nie teoria.
    # Bez tego wyjątek leciał z konstruktora `RezyserPanel` — po restarcie klik
    # „Reżyser" wywalał aplikację, a narzędzie stawało się trwale niedostępne
    # (poprzedni panel jest już zniszczony). Zachowujemy się jak przy duplikacie
    # `id`: pomijamy plik z ostrzeżeniem na stderr.
    try:
        max_tokens_wyjscia = int(data.get("max_tokens_wyjscia") or 0)
        if max_tokens_wyjscia <= 0:
            max_tokens_wyjscia = (
                MAX_TOKENS_PER_ROZDZIAL_DOMYSLNE
                if zakres == ZAKRES_PER_ROZDZIAL
                else MAX_TOKENS_CALOSC_DOMYSLNE
            )
        return PrzepisRezysera(
            id=str(id_),
            etykieta=str(etykieta),
            kategoria=str(kategoria),
            kolejnosc=int(data.get("kolejnosc", 0)),
            model=str(data.get("model", MODEL_DOMYSLNY)),
            temperatura=float(data.get("temperatura", 0.85)),
            jezyk_odpowiedzi=str(data.get("jezyk_odpowiedzi", "polsku")),
            kod_jezyka=str(data.get("kod_jezyka", "")).strip().lower(),
            prompt_systemowy=str(data.get("prompt_systemowy", "")),
            format_wyjscia=format_wyjscia,
            struktura=struktura,
            zapis_do_pliku=bool(data.get("zapis_do_pliku", False)),
            stosuj_akcenty_fonetyczne=bool(
                data.get("stosuj_akcenty_fonetyczne", False)),
            przypomnienie_uzytkownika=str(data.get("przypomnienie_uzytkownika", "")),
            sufiksy={k: str(v) for k, v in (data.get("sufiksy") or {}).items()},
            slowa_wyzwalajace={
                k: [str(x) for x in (v or [])]
                for k, v in (data.get("slowa_wyzwalajace") or {}).items()
            },
            klauzula_odrzucenia=str(data.get("klauzula_odrzucenia", "")),
            doklejka_celu_sceny=str(data.get("doklejka_celu_sceny", "")),
            prompt_uzytkownika_szablon=str(
                data.get("prompt_uzytkownika_szablon", "")),
            regex_podzial_rozdzialow=str(data.get("regex_podzial_rozdzialow", "")),
            min_dlugosc_fragmentu=int(data.get("min_dlugosc_fragmentu", 0)),
            max_dlugosc_probki=int(data.get("max_dlugosc_probki", 0)),
            etykieta_fragment_zbyt_krotki=str(
                data.get("etykieta_fragment_zbyt_krotki", "")),
            etykieta_bled_brak_kredytow=str(
                data.get("etykieta_bled_brak_kredytow", "")),
            etykieta_odrzucenie=str(data.get("etykieta_odrzucenie", "")),
            etykieta_blad_fragment=str(data.get("etykieta_blad_fragment", "")),
            dla_trybow=dla_trybow,
            zakres=zakres,
            max_tokens_wyjscia=max_tokens_wyjscia,
            sufiks_pliku_wyniku=sufiks_pliku_wyniku,
            prompt_ksiegi_szablon=str(data.get("prompt_ksiegi_szablon", "")),
            rola=rola,
            # v18.14: zamknięte zbiory wartości + limit opisu karty
            # publikacyjnej. `_lista_str` przyjmuje też pojedynczy string
            # (naturalny skrót w ręcznie pisanym YAML-u) i wycina puste wpisy,
            # żeby literówka typu „- " nie weszła na listę dozwolonych gatunków
            # jako pusty ciąg (walidator uznałby wtedy każdy gatunek za legalny).
            gatunki_dozwolone=_lista_str(data.get("gatunki_dozwolone")),
            odbiorcy_dozwoleni=_lista_str(data.get("odbiorcy_dozwoleni")),
            limit_znakow_opisu=max(0, int(data.get("limit_znakow_opisu") or 0)),
        )
    except (TypeError, ValueError, AttributeError) as exc:
        zglos_pominiecie(sciezka, POWOD_POLE, str(exc))
        return None


def _lista_str(surowe: Any) -> list[str]:
    """Normalizuje pole YAML na listę niepustych stringów (v18.14).

    Przyjmuje listę, pojedynczą wartość (skrót w ręcznie pisanym YAML-u) i brak
    pola. Zachowuje ORYGINALNĄ pisownię wpisów — w karcie publikacyjnej gatunki
    trafiają do formularza platformy dosłownie, więc `lower()` byłby szkodliwy
    (walidator porównuje bez uwzględniania wielkości liter osobno).
    """
    if surowe is None:
        return []
    if not isinstance(surowe, list):
        surowe = [surowe]
    return [str(x).strip() for x in surowe if str(x).strip()]


def _czy_plik_wspolny(sciezka: str) -> bool:
    """Czy ścieżka wskazuje plik wspólny ``baza.yaml`` (LEGALNIE nie-przepis)?

    Wydzielone, bo dwa filtry braku pól w :func:`_yaml_to_przepis` muszą go
    przepuszczać bez zgłaszania pominięcia — patrz docstring tamtej funkcji.
    """
    return os.path.splitext(os.path.basename(sciezka))[0].lower() == NAZWA_BAZY


def opis_bledu_yaml(exc: Exception) -> str:
    """Zamienia wyjątek parsera na jednolinijkowy opis z numerem linii.

    Publiczne, bo ten sam format opisu potrzebuje loader Opowieści
    (``opowiesci_ai._zaladuj_przepis``) — raport diagnostyczny jest wspólny dla
    obu narzędzi, więc i opis błędu ma wyglądać identycznie.

    Surowy ``str(yaml.YAMLError)`` to cztery linie z powtórzoną pełną ścieżką
    pliku — w dialogu diagnostycznym liczy się to, CZEGO parser nie zrozumiał
    i GDZIE. Numer linii/kolumny liczymy od 1 (pyyaml indeksuje od 0), bo user
    otworzy plik w edytorze tekstu.

    Pozycję zapisujemy w konwencji kompilatorów (``linia:kolumna:``) — bez słów,
    więc opis jest ten sam we wszystkich dziewięciu językach interfejsu i nie
    wnosi polskiego hard-kodu do komunikatu widzianego przez użytkownika.
    Znaczenie liczb wyjaśnia klucz i18n ``diag.powod.parse``. Sam komunikat
    parsera zostaje w oryginale (cytat z biblioteki, jak ``{tresc_bledu}``).
    """
    problem = getattr(exc, "problem", "") or ""
    marker = getattr(exc, "problem_mark", None)
    if marker is not None:
        pozycja = f"{marker.line + 1}:{marker.column + 1}"
        return f"{pozycja}: {problem}" if problem else pozycja
    return problem or str(exc).replace("\n", " ")


def _wczytaj_yaml(sciezka: str) -> dict:
    """Bezpiecznie wczytuje plik YAML (zwraca pusty dict przy błędzie).

    v18.24.2: błąd SKŁADNI przestał być cichy. Do v18.24.1 ``except Exception``
    zwracał tu ``{}``, a ``_yaml_to_przepis`` odrzucał taki plik w pierwszym
    ``if`` — przepis znikał z GUI bez ani jednej linii komunikatu, nawet na
    konsoli dewelopera (to była najgorsza z sześciu ścieżek pominięcia).
    Teraz powód ląduje w rejestrze razem z numerem linii, a użytkownik dostaje
    go w dialogu diagnostycznym. ``OSError`` (plik zniknął, brak uprawnień)
    raportujemy osobnym szczegółem — objaw jest ten sam, przyczyna inna.
    """
    try:
        with open(sciezka, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        zglos_pominiecie(sciezka, POWOD_PARSE, opis_bledu_yaml(exc))
        return {}
    except OSError as exc:
        zglos_pominiecie(sciezka, POWOD_PARSE, str(exc))
        return {}
    except Exception as exc:  # noqa: BLE001 — np. UnicodeDecodeError
        zglos_pominiecie(sciezka, POWOD_PARSE, str(exc).replace("\n", " "))
        return {}
    return data if isinstance(data, dict) else {}


# =============================================================================
# Plik wspólny ``rezyser/baza.yaml`` — wrappery kontekstu LLM (od v17.10)
# =============================================================================
# Trzyma teksty WSPÓŁDZIELONE między trybami (analogicznie do
# ``opowiesci/baza.yaml``). Dziś: wrappery kontekstu role=assistant
# (``[STRESZCZENIE POPRZEDNICH WYDARZEŃ]:`` / ``[OBECNA FABUŁA]:``) wyniesione
# z hard-kodu ``rezyser_ai.buduj_payload``. NIE jest przepisem (brak ``id``),
# więc ``_yaml_to_przepis`` go pomija — nie zaśmieca listy trybów.
NAZWA_BAZY = "baza"
_CACHE_BAZA: dict[str, dict] = {}


def _zaladuj_baze(jezyk: str) -> dict:
    """Wczytuje ``dictionaries/<jezyk>/rezyser/baza.yaml`` (cache, ``{}`` gdy brak)."""
    if jezyk in _CACHE_BAZA:
        return _CACHE_BAZA[jezyk]
    sciezka = os.path.join(DICTIONARIES_DIR, jezyk, FOLDER_REZYSER, f"{NAZWA_BAZY}.yaml")
    dane = _wczytaj_yaml(sciezka)
    _CACHE_BAZA[jezyk] = dane
    return dane


def tekst_bazy(jezyk: str, klucz: str, default: str) -> str:
    """Zwraca tekstowy klucz z ``rezyser/baza.yaml`` z fallbackiem lang→en→literał.

    Używane przez :func:`rezyser_ai.buduj_payload` do wrapperów kontekstu LLM
    wyniesionych z hard-kodu. Wrappery ``[OBECNA FABUŁA]:`` /
    ``[STRESZCZENIE POPRZEDNICH WYDARZEŃ]:`` to strukturalne TAGI-KOTWICE
    (``tryb_burza.yaml`` referuje ``[OBECNA FABUŁA]`` dosłownie), więc w paczkach
    trzymane są 1:1 we wszystkich językach — fallback do en/literału jest tu
    siatką bezpieczeństwa, nie mechanizmem lokalizacji. Pusty/niełańcuchowy klucz
    (``jezyk`` bez baza.yaml) → en → ``default``.
    """
    val = _zaladuj_baze(jezyk).get(klucz)
    if val is None and jezyk != "en":
        val = _zaladuj_baze("en").get(klucz)
    return val if isinstance(val, str) else default


def _zaladuj_wszystkie(jezyk: str) -> list[PrzepisRezysera]:
    """Skanuje ``dictionaries/<jezyk>/rezyser/*.yaml`` i cache'uje wynik."""
    if jezyk in _CACHE_PRZEPISOW:
        return _CACHE_PRZEPISOW[jezyk]

    folder = os.path.join(DICTIONARIES_DIR, jezyk, FOLDER_REZYSER)
    przepisy: list[PrzepisRezysera] = []

    if os.path.isdir(folder):
        # v18.24.2: mapa (nie set) — raport duplikatu ma powiedzieć, KTÓRY plik
        # zajął identyfikator, inaczej user widzi „pominięto tryb_burza.yaml"
        # i nie wie, że winna jest jego własna kopia sortująca się wcześniej.
        widziane_id: dict[tuple[str, str], str] = {}
        for nazwa_pliku in sorted(os.listdir(folder)):
            if not nazwa_pliku.lower().endswith((".yaml", ".yml")):
                continue
            sciezka = os.path.join(folder, nazwa_pliku)
            data = _wczytaj_yaml(sciezka)
            przepis = _yaml_to_przepis(data, sciezka)
            if przepis is None:
                continue
            # Guard kolizji id: tryb identyfikuje się stabilnym `id` (tożsamość
            # `.mode`, dispatch struktury/paneli). Dwa pliki o tym samym `id`
            # rozbiłyby identyfikację — pomijamy późniejszy i sygnalizujemy na
            # stderr (dev/headless). Unikalność liczona PER KATEGORIA (audyt
            # 18.12, ŚREDNIA-5): globalny guard sprawiał, że postprodukcja
            # o id trybu (`postprod_*` sortuje się przed `tryb_*`) po cichu
            # USUWAŁA tryb z RadioBoxa. Wszystkie lookupy są per kategoria
            # (`zaladuj_przepis(kategoria=...)`, `struktura_dla_id`, listy).
            klucz_id = (przepis.kategoria, przepis.id)
            if klucz_id in widziane_id:
                zglos_pominiecie(
                    sciezka, POWOD_DUPLIKAT,
                    f"id={przepis.id!r}, kategoria={przepis.kategoria!r} "
                    f"← {os.path.basename(widziane_id[klucz_id])}",
                )
                continue
            widziane_id[klucz_id] = sciezka
            przepisy.append(przepis)

    przepisy.sort(key=lambda p: (p.kategoria, p.kolejnosc, p.id))
    _CACHE_PRZEPISOW[jezyk] = przepisy
    return przepisy


# =============================================================================
# Publiczne API
# =============================================================================
def lista_trybow(jezyk: str = "pl") -> list[PrzepisRezysera]:
    """Zwraca listę przepisów kategorii ``tryb`` (do wypełnienia RadioBox).

    Posortowane rosnąco po ``kolejnosc`` (a następnie po ``id`` dla stabilności).
    Gdy folder ``dictionaries/<jezyk>/rezyser/`` nie istnieje – zwraca ``[]``
    (GUI może wtedy pokazać ostrzeżenie „brak zainstalowanych trybów").
    """
    return [p for p in _zaladuj_wszystkie(jezyk) if p.kategoria == KATEGORIA_TRYB]


def struktura_dla_id(id_trybu: str, jezyk: str = "pl") -> str:
    """Zwraca `struktura` trybu o danym `id` (do segmentacji `.txt` przy wczytaniu).

    Używane przez :meth:`core_rezyser.ProjektRezysera.wczytaj`, która z pliku
    `.mode` zna tylko stabilne `id` trybu, a potrzebuje sposobu segmentacji
    (akty/sceny vs rozdziały) do enumeracji punktów odniesienia pamięci. Czyta
    pole `struktura` z przepisu (parytet gwarantuje tę samą wartość we
    wszystkich językach, więc `pl` jako referencja wystarcza). Gdy tryb nie
    istnieje w paczce — fallback na mapę legacy, a w ostateczności ``"brak"``
    (płaska lista — bezpieczny default).
    """
    if not id_trybu:
        return "brak"
    for p in _zaladuj_wszystkie(jezyk):
        # Filtr kategorii (audyt 18.12): od czasu unikalności id per kategoria
        # postprodukcja może legalnie nosić id trybu — segmentacja `.mode`
        # nie może wtedy trafić w jej (pustą) `struktura`.
        if p.id == id_trybu and p.kategoria == KATEGORIA_TRYB:
            return p.struktura
    return _STRUKTURA_LEGACY.get(id_trybu, "brak")


def lista_postprodukcji(jezyk: str = "pl") -> list[PrzepisRezysera]:
    """Zwraca listę WSZYSTKICH przepisów kategorii ``postprodukcja``.

    Od v18.12 GUI nie ładuje już pojedynczego narzędzia po zahardkodowanym
    ``id`` — nowe narzędzie postprodukcyjne to sam YAML z ``kategoria:
    postprodukcja`` (+ pola ``dla_trybow``/``zakres``). Do filtrowania pod
    bieżący tryb służy :func:`postprodukcje_dla_trybu`.
    """
    return [p for p in _zaladuj_wszystkie(jezyk) if p.kategoria == KATEGORIA_POSTPROD]


def filtruj_postprodukcje(
    postprodukcje: list[PrzepisRezysera],
    tryb: PrzepisRezysera | None,
) -> list[PrzepisRezysera]:
    """Filtr postprodukcji pod dany tryb twórczy (semantyka ``dla_trybow``).

    Narzędzie z niepustą listą ``dla_trybow`` pokazuje się wyłącznie
    w wymienionych trybach; narzędzie z pustą listą — we wszystkich trybach
    z ``zapis_do_pliku`` (postprodukcja operuje na pliku projektu
    ``skrypty/<nazwa>.txt``, więc tryb bez zapisu — np. Burza Mózgów — nie ma
    na czym pracować). ``tryb=None`` (RadioBox bez wyboru) → pusta lista.

    Wydzielone z :func:`postprodukcje_dla_trybu`, bo GUI trzyma listę
    postprodukcji załadowaną raz z miękkim fallbackiem języka UI → EN
    (jak tryby) i filtruje ją przy każdym odświeżeniu stanu.
    """
    if tryb is None:
        return []
    wynik: list[PrzepisRezysera] = []
    for p in postprodukcje:
        if p.dla_trybow:
            if tryb.id in p.dla_trybow:
                wynik.append(p)
        elif tryb.zapis_do_pliku:
            wynik.append(p)
    return wynik


def postprodukcje_dla_trybu(
    tryb: PrzepisRezysera | None,
    jezyk: str = "pl",
) -> list[PrzepisRezysera]:
    """Postprodukcje oferowane dla danego trybu twórczego (v18.12).

    Wariant :func:`filtruj_postprodukcje` ładujący listę z paczki ``jezyk``
    (bez fallbacku językowego — ten robi GUI na swojej liście).
    """
    return filtruj_postprodukcje(lista_postprodukcji(jezyk), tryb)


def przepisy_pamieci_dlugotrwalej(
    postprodukcje: list[PrzepisRezysera],
) -> list[PrzepisRezysera]:
    """WSZYSTKIE przepisy z rolą :data:`ROLA_PAMIEC_DLUGOTRWALA` (v18.14).

    Bierze GOTOWĄ listę, a nie kod języka, celowo: GUI ładuje postprodukcje raz,
    z miękkim fallbackiem język-UI → EN, i musi mieć pewność, że sufiks pliku
    pochodzi DOKŁADNIE z tego przepisu, który wygeneruje treść. Wariant liczący
    listę samodzielnie rozjechałby się z GUI przy niekompletnej paczce.

    Kolejność jest deterministyczna: :func:`_zaladuj_wszystkie` sortuje po
    ``(kategoria, kolejnosc, id)``. Do v18.13 zakładaliśmy JEDNO narzędzie z tą
    rolą w paczce; od v18.14 dopuszczamy więcej (reżyser może chcieć osobną
    pamięć „pod siebie" i osobną „pod AI", każdą z własnym sufiksem). Wszystkie
    ich sufiksy są potem KANDYDATAMI przy rozstrzyganiu, który plik na dysku jest
    Pamięcią Długotrwałą projektu — przy więcej niż jednym pyta się usera.

    Uwaga: dwa przepisy o tym samym ``id`` w jednej paczce są nadal niemożliwe
    (guard unikalności ``(kategoria, id)`` w :func:`_zaladuj_wszystkie`) — żeby
    mieć drugą pamięć, trzeba drugiego ``id``.
    """
    return [p for p in postprodukcje if p.rola == ROLA_PAMIEC_DLUGOTRWALA]


def przepis_pamieci_dlugotrwalej(
    postprodukcje: list[PrzepisRezysera],
) -> PrzepisRezysera | None:
    """Pierwszy przepis z rolą :data:`ROLA_PAMIEC_DLUGOTRWALA` (lub ``None``).

    Wariant „głównego" narzędzia pamięci — używany tam, gdzie trzeba wskazać
    JEDEN przepis do uruchomienia bez pytania usera (automat progu alarmowego).
    Do rozpoznawania plików na dysku służy :func:`sufiksy_pamieci_dlugotrwalej`.
    """
    lista = przepisy_pamieci_dlugotrwalej(postprodukcje)
    return lista[0] if lista else None


def sufiksy_pamieci_dlugotrwalej(
    postprodukcje: list[PrzepisRezysera] | None = None,
) -> list[str]:
    """Kandydaci na sufiks pliku Pamięci Długotrwałej — wg PRIORYTETU (v18.14).

    Kolejność: sufiksy przepisów z rolą :data:`ROLA_PAMIEC_DLUGOTRWALA` (wg
    ``kolejnosc``), potem :data:`SUFIKS_PAMIECI_MIEDZYNARODOWY`, na końcu
    historyczny :data:`SUFIKS_STRESZCZENIA_DOMYSLNY`. Pierwszy element jest
    sufiksem GŁÓWNYM (tam trafiają nowe zapisy i tam migruje shim), pozostałe
    służą do ROZPOZNANIA pliku, który już leży na dysku.

    Zmiana wobec v18.13: sufiks jest teraz LOKALIZOWANY (paczka ``de`` może mieć
    ``_zusammenfassung``, ``fi`` — ``_yhteenveto``), bo nazwa pliku należy do
    usera, a nie do silnika. Ceną jest rozpoznawanie po liście kandydatów zamiast
    po jednej stałej — inaczej wystarczyłoby przełączyć język interfejsu, żeby
    aplikacja „zgubiła" pamięć projektu i wczytała całą narrację jako nową.

    ``postprodukcje=None`` → lista z paczki ``pl`` (referencyjna): dla kodu bez
    dostępu do listy GUI (testy, headless). GUI podaje listę z paczki JĘZYKA
    PROJEKTU (``kod_jezyka`` aktywnego przepisu), nie języka interfejsu.
    """
    lista = postprodukcje if postprodukcje is not None else lista_postprodukcji("pl")
    kandydaci: list[str] = []
    for p in przepisy_pamieci_dlugotrwalej(lista):
        if p.sufiks_pliku_wyniku and p.sufiks_pliku_wyniku not in kandydaci:
            kandydaci.append(p.sufiks_pliku_wyniku)
    for zapasowy in (SUFIKS_PAMIECI_MIEDZYNARODOWY, SUFIKS_STRESZCZENIA_DOMYSLNY):
        if zapasowy not in kandydaci:
            kandydaci.append(zapasowy)
    return kandydaci


def sufiks_pamieci_dlugotrwalej(
    postprodukcje: list[PrzepisRezysera] | None = None,
) -> str:
    """Sufiks GŁÓWNY Pamięci Długotrwałej — pierwszy kandydat z listy priorytetów.

    Jedno źródło prawdy dla miejsc, które MUSZĄ się zgadzać co do znaku: ścieżki
    w :class:`core_rezyser.ProjektRezysera`, zapisu wyniku postprodukcji i shimu
    migracyjnego. Rozjazd oznacza „streszczenie zapisane obok, poza
    rekoncyliacją". Do FILTROWANIA listy projektów w GUI ta funkcja NIE
    wystarcza — patrz :func:`sufiksy_wynikow_wszystkich_paczek`.
    """
    return sufiksy_pamieci_dlugotrwalej(postprodukcje)[0]


def sufiksy_wynikow_wszystkich_paczek() -> tuple[str, ...]:
    """Unia ``sufiks_pliku_wyniku`` postprodukcji ze WSZYSTKICH paczek (v18.14).

    Odpowiada na pytanie „czy plik ``skrypty/<coś><sufiks>.txt`` jest wynikiem
    narzędzia, a nie samodzielnym projektem" — i musi je rozstrzygać niezależnie
    od tego, w jakim języku user ma dziś interfejs. Po lokalizacji sufiksów
    (v18.14) filtr oparty na jednej paczce przepuściłby np.
    ``kroniki_zusammenfassung.txt`` na listę projektów PL-owego usera, a po
    wczytaniu takiego „projektu" silnik dopisywałby tury do streszczenia.

    Skanujemy katalogi ``dictionaries/*/`` własnymi siłami (bez importu
    ``core_poliglota`` — zero ryzyka cyklu) i BEZ filtra kompletności paczki:
    plik wytworzony przez paczkę-stuba leży na dysku usera tak samo jak każdy
    inny. Do unii dokładamy oba sufiksy fallbackowe.

    Cache modułowy (czyszczony przez :func:`wyczysc_cache`) — funkcja jest wołana
    przy każdym otwarciu dialogu wyboru projektu, a `_zaladuj_wszystkie` i tak
    trzyma sparsowane paczki.
    """
    global _CACHE_SUFIKSY_GLOBALNE
    if _CACHE_SUFIKSY_GLOBALNE is not None:
        return _CACHE_SUFIKSY_GLOBALNE

    sufiksy: set[str] = {
        SUFIKS_PAMIECI_MIEDZYNARODOWY, SUFIKS_STRESZCZENIA_DOMYSLNY,
    }
    if os.path.isdir(DICTIONARIES_DIR):
        for kod in sorted(os.listdir(DICTIONARIES_DIR)):
            if not os.path.isdir(os.path.join(DICTIONARIES_DIR, kod)):
                continue
            for p in lista_postprodukcji(kod):
                if p.sufiks_pliku_wyniku:
                    sufiksy.add(p.sufiks_pliku_wyniku)
    _CACHE_SUFIKSY_GLOBALNE = tuple(sorted(sufiksy))
    return _CACHE_SUFIKSY_GLOBALNE


def zaladuj_przepis(
    id_: str,
    jezyk: str = "pl",
    kategoria: str | None = None,
) -> PrzepisRezysera | None:
    """Zwraca pojedynczy przepis po ``id`` (lub ``None``, jeśli nie znaleziono).

    Args:
        id_:        Identyfikator (np. ``"audiobook"``, ``"tytuly"``).
        jezyk:      Kod języka (folder w ``dictionaries/``).
        kategoria:  Opcjonalne zawężenie wyszukiwania (``"tryb"``
                    lub ``"postprodukcja"``). Jeśli ``None`` – zwraca
                    pierwszy pasujący.
    """
    for p in _zaladuj_wszystkie(jezyk):
        if p.id != id_:
            continue
        if kategoria is not None and p.kategoria != kategoria:
            continue
        return p
    return None


def wyczysc_cache() -> None:
    """Zapomina wczytane przepisy – użyteczne po edycji YAML-i w runtime.

    Wołane po ręcznej edycji plików ``rezyser/`` / ``akcenty/``, by kolejne
    odczyty wzięły świeżą treść z dysku zamiast przeterminowanego cache.
    """
    global _CACHE_SUFIKSY_GLOBALNE
    _CACHE_PRZEPISOW.clear()
    _CACHE_BAZA.clear()
    # v18.24.2: powody pominięcia są pochodną wczytania — po wyczyszczeniu cache
    # policzą się od nowa ze świeżej treści plików. Bez tego raport pokazywałby
    # błąd, który user właśnie naprawił (albo gubił nowy, o tej samej trójce).
    wyczysc_pominiecia()
    # v18.14: unia sufiksów jest pochodną przepisów — po edycji
    # `sufiks_pliku_wyniku` w Managerze Reguł musi być przeliczona, inaczej filtr
    # listy projektów zostałby przy starej nazwie pliku wyniku.
    _CACHE_SUFIKSY_GLOBALNE = None


# =============================================================================
# Pomocnicze: podstawianie placeholderów
# =============================================================================
def _format_bezpiecznie(szablon: str, **kwargs: Any) -> str:
    """Jak ``str.format`` – ale nie wywala się na nieznanym kluczu.

    Python-owy ``.format`` wymaga, by WSZYSTKIE placeholdery w stringu
    miały odpowiednik w kwargs. Gdyby lingwista napisał w YAML-u
    ``{cos_nowego}`` i zapomniał to obsłużyć w kodzie – aplikacja by
    się wysypała. Tu zamiast tego zostawiamy oryginał ``{cos_nowego}``
    w wyniku, dzięki czemu błąd jest widoczny, ale nie blokujący.
    """
    class _SafeDict(dict):
        def __missing__(self, key: str) -> str:   # type: ignore[override]
            return "{" + key + "}"

    try:
        return szablon.format_map(_SafeDict(**kwargs))
    except (IndexError, ValueError):
        # np. samotne "{" w tekście – oddajemy oryginał, żeby nic nie gubić
        return szablon


def buduj_prompt_systemowy(przepis: PrzepisRezysera, world_context: str = "") -> str:
    """Prompt systemowy: baza + klauzula odrzucenia (bez sufiksu kontekstowego).

    Wariant dla trybów bez sufiksów (np. postprodukcja tytułów) lub gdy GUI
    chce pokazać podgląd. Dla trybów z sufiksami (Burza / Skrypt) silnik
    ``rezyser_ai`` używa :func:`buduj_pelny_prompt_systemowy`, bo tylko tam
    sufiks zostanie doklejony PRZED klauzulą.

    Placeholdery: ``{world_context}``, ``{jezyk_odpowiedzi}``.
    """
    return buduj_pelny_prompt_systemowy(przepis, world_context, sufiks_nazwa=None)


def buduj_pelny_prompt_systemowy(
    przepis: PrzepisRezysera,
    world_context: str = "",
    sufiks_nazwa: str | None = None,
) -> str:
    """Kompletny prompt systemowy z deterministyczną kolejnością sklejania.

    Kolejność (ostatnie wiadomości w systemie mają największy wpływ na
    model, więc klauzula musi być na końcu):

        1. **Baza** z pola ``prompt_systemowy`` (po podstawieniu placeholderów).
        2. **Sufiks kontekstowy** – opcjonalny, np. ``"alarm"`` / ``"startowy"``
           (podstawia placeholdery tak jak baza).
        3. **Klauzula odrzucenia** – z pola ``klauzula_odrzucenia`` lub,
           gdy puste, z :data:`KLAUZULA_ODRZUCENIA_DOMYSLNA`.

    Dzięki temu eksperymentalny sufiks w YAML-u może wpływać na zachowanie
    modelu (np. wymusić wygenerowanie ``<STRESZCZENIE>``) nie kolidując
    z infrastrukturalnym wymuszeniem tagu ``[ODRZUCENIE_AI]``.

    Args:
        przepis:        Załadowany :class:`PrzepisRezysera`.
        world_context:  Treść Księgi Świata (placeholder ``{world_context}``).
        sufiks_nazwa:   Klucz z ``przepis.sufiksy`` lub ``None`` = bez sufiksu.

    Returns:
        String gotowy do wysłania jako ``role=system``.
    """
    bazowy = _format_bezpiecznie(
        przepis.prompt_systemowy,
        world_context=world_context,
        jezyk_odpowiedzi=przepis.jezyk_odpowiedzi,
        # v18.14: zamknięte zbiory wartości karty publikacyjnej wstrzykiwane
        # z pól YAML — jedno źródło prawdy dla prompta i walidatora. Gdyby
        # lingwista wypisał gatunki wprost w treści prompta, każda korekta listy
        # (platforma zmienia kategorie) musiałaby trafić w 9 paczek DWA razy.
        gatunki_dozwolone="; ".join(przepis.gatunki_dozwolone),
        odbiorcy_dozwoleni="; ".join(przepis.odbiorcy_dozwoleni),
        limit_znakow_opisu=przepis.limit_znakow_opisu or "",
    )
    sufiks = ""
    if sufiks_nazwa:
        sufiks = buduj_sufiks(przepis, sufiks_nazwa, world_context=world_context)
    klauzula = przepis.klauzula_odrzucenia or KLAUZULA_ODRZUCENIA_DOMYSLNA
    return bazowy + sufiks + klauzula


def wykryto_odrzucenie(tekst: str) -> bool:
    """Rozpoznaje, czy odpowiedź AI jest odmową wygenerowania treści.

    Działa przez szukanie magicznego tagu :data:`TAG_ODRZUCENIA_AI`, który
    silnik wymusił na modelu w prompt_systemowy. Gdy go znajdzie –
    aplikacja NIE zapisuje odpowiedzi do pliku historii i pokazuje
    stosowny komunikat użytkownikowi.

    Metoda jest niezależna od ``jezyk_odpowiedzi`` (tag jest zawsze
    w alfabecie łacińskim i nie podlega tłumaczeniu).
    """
    return TAG_ODRZUCENIA_AI in (tekst or "")


def buduj_sufiks(przepis: PrzepisRezysera, nazwa: str, **extra: Any) -> str:
    """Zwraca tekst sufiksu ``nazwa`` lub pusty string, jeśli go nie ma.

    Dodatkowe argumenty (``**extra``) są przekazywane do podstawiania
    placeholderów – przydatne, gdy lingwista chce np. wstawić licznik
    rozdziałów w sufiksie kontynuacji.
    """
    szablon = przepis.sufiksy.get(nazwa, "")
    if not szablon:
        return ""
    return _format_bezpiecznie(
        szablon,
        world_context=extra.pop("world_context", ""),
        jezyk_odpowiedzi=przepis.jezyk_odpowiedzi,
        **extra,
    )


def buduj_przypomnienie(przepis: PrzepisRezysera, **extra: Any) -> str:
    """Zwraca przypomnienie doklejane do treści użytkownika (``role=user``)."""
    if not przepis.przypomnienie_uzytkownika:
        return ""
    return _format_bezpiecznie(
        przepis.przypomnienie_uzytkownika,
        jezyk_odpowiedzi=przepis.jezyk_odpowiedzi,
        **extra,
    )


def buduj_prompt_uzytkownika(przepis: PrzepisRezysera, **kwargs: Any) -> str:
    """Szablon z ``prompt_uzytkownika_szablon`` z podstawionymi wartościami.

    Używany przez narzędzia postprodukcyjne (np. tytułowanie rozdziałów),
    gdzie instrukcja ``role=user`` jest powtarzalna dla każdego fragmentu
    i wymaga podstawienia ``{naglowek}`` oraz ``{probka}``.
    """
    if not przepis.prompt_uzytkownika_szablon:
        return ""
    return _format_bezpiecznie(
        przepis.prompt_uzytkownika_szablon,
        jezyk_odpowiedzi=przepis.jezyk_odpowiedzi,
        **kwargs,
    )


def buduj_prompt_ksiegi(przepis: PrzepisRezysera, ksiega: str) -> str:
    """Blok Księgi Świata z ``prompt_ksiegi_szablon`` (placeholder ``{ksiega}``).

    Używany przez postprodukcję ``calosc`` (v18.12): gdy projekt ma Księgę
    Świata (``skrypty/<nazwa>.md``) a przepis szablon bloku — silnik dokleja
    blok PRZED treścią pliku projektu. Pusty szablon LUB pusta księga →
    pusty string (postprodukcja ignoruje księgę).
    """
    if not przepis.prompt_ksiegi_szablon or not (ksiega or "").strip():
        return ""
    return _format_bezpiecznie(
        przepis.prompt_ksiegi_szablon,
        ksiega=ksiega.strip(),
        jezyk_odpowiedzi=przepis.jezyk_odpowiedzi,
    )
