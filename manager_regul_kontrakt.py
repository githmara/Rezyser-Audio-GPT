"""
manager_regul_kontrakt.py — co w ``dictionaries/`` wolno NAZWAĆ jak (v19.4).

Moduł odpowiada na jedno pytanie i nic więcej: **czy silnik czyta tę nazwę
pliku?** Jeśli tak, nazwa nie jest własnością użytkownika — jest
IDENTYFIKATOREM, a wpisanie w to miejsce czegokolwiek daje plik, który albo
nic nie robi, albo robi coś pod cudzą nazwą. Jeśli nie, nazwa jest wolna
i moduł milczy.

DLACZEGO TO NIE ŁAMIE ZASADY „PACZKI SĄ DANYMI UŻYTKOWNIKA". Bo argument
user-data chroni wolność edycji TREŚCI, a nie wolność wymyślania nazw, których
silnik nie czyta. Blokada nazwy nie odbiera użytkownikowi niczego (każdy plik
w ``dictionaries/`` może otworzyć w edytorze tekstu — Manager Reguł sam mu go
otwiera); dopuszczenie nazwy odbiera mu plik, o którym myśli, że działa.

TRZY KLASY, KTÓRE Z TEGO WYCHODZĄ:

* **A — nazwa z ZAMKNIĘTEGO zbioru**: ``podstawy.yaml``, ``gui/ui.yaml``,
  narzędzia z :data:`core_poliglota._NARZEDZIA_AKCENTOW`, przepisy
  z :data:`opowiesci_ai.NAZWY_PRZEPISOW`. Wolny ID jest tu defektem
  z definicji — silnik szuka tych plików po nazwie i tylko po nazwie.
* **B — nazwa WYLICZALNA z danych**: ``akcenty/<polska nazwa języka>.yaml``.
  Kanon (:mod:`jezyki_lingua`) rozstrzyga ją z pola ``iso``, więc nie ma
  o co pytać użytkownika.
* **C — nazwa WOLNA**: ``szyfry/*.yaml``, ``rezyser/tryb_*.yaml``,
  ``rezyser/postprod_*.yaml``. Dispatch idzie z POLA (``kategoria``,
  ``format_wyjscia``, ``struktura``, ``zakres``, ``rola``), a obiekt przepisu
  jest przekazywany, nie wyszukiwany po ``id`` — więc nazwa może być dowolna
  i tak ma być.

GRADACJA: blokuj tylko to, co dowodliwie martwe albo dowodliwie kłamie;
ostrzegaj o tym, co działa, ale łamie konwencję; na resztę nie reaguj wcale.

Moduł jest WX-FREE i zwraca KLUCZE i18n, nie teksty (napisy żyją
w ``dictionaries/<kod>/gui/ui.yaml`` pod ``manager.kontrakt.*``) — dzięki temu
da się go objąć testem jednostkowym bez ``wx.App`` i bez paczki językowej.

Geneza (2026-09-17, testy bojowe 1–4 w zainstalowanej paczce): Manager przyjął
``ucraine.yaml`` przy ``iso: uk`` (kanon: ``ukrainski``), ``bulgarian.yaml``
przy ``iso: bg`` (kanon: ``bulgarski``), zapisał naprawiacz tagów pod nazwą
``bulgarski.yaml`` — czyli DZIAŁAJĄCE narzędzie zajmujące nazwę przyszłego
akcentu — i pozwolił zduplikować ``zaczatki.yaml`` w tym samym folderze, gdzie
kopia jest nieczytana przez silnik. Żadna bramka w repozytorium tego nie
widziała (zmierzone: ``audyt_podstaw --bramka`` ZIELONA z trzema takimi plikami
w ``pl/``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import core_poliglota as cp
import jezyki_lingua as jl
import opowiesci_ai as oai


# =============================================================================
# Werdykty
# =============================================================================
# `BLOKADA` = operacja nie ma wykonalnego sensu (plik byłby martwy albo kłamał
# nazwą). `OSTRZEZENIE` = plik zadziała, ale łamie konwencję paczki i użytkownik
# ma o tym usłyszeć PRZED zapisem, nie po wydaniu.
BLOKADA     = "blokada"
OSTRZEZENIE = "ostrzezenie"


@dataclass(frozen=True)
class Zastrzezenie:
    """Jedno zastrzeżenie do nazwy pliku: werdykt + klucz i18n + parametry.

    ``klucz`` jest SUFIKSEM pod ``manager.kontrakt.`` — wołający składa pełny
    klucz i podaje ``**parametry`` do :func:`i18n.t`. Trzymanie tekstu poza tym
    modułem to ta sama reguła, co w całym GUI (zakaz hardkodowania etykiet),
    tylko tu ma dodatkowy skutek: moduł jest testowalny bez paczki językowej.
    """

    werdykt: str
    klucz: str
    parametry: dict[str, str] = field(default_factory=dict)

    @property
    def blokuje(self) -> bool:
        return self.werdykt == BLOKADA


# =============================================================================
# Zamknięte zbiory nazw — WYŁĄCZNIE z modułów, które je definiują
# =============================================================================
# Żadnej własnej tabeli nazw plików: lustro pola/zbioru z innego modułu jest
# długiem nawet wtedy, gdy dziś się zgadza (lekcja `core_screen_reader._AKCENT_ISO`,
# v19.1). Stąd `_NARZEDZIA_AKCENTOW` z silnika Poligloty i `NAZWY_PRZEPISOW`
# z silnika Opowieści, a nie ich kopie.
def _narzedzia_akcentow() -> set[str]:
    """Nazwy (bez rozszerzenia) trzech narzędzi Poligloty z ``akcenty/``."""
    return {os.path.splitext(n)[0] for n in cp._NARZEDZIA_AKCENTOW}


def narzedzia_dla_typu(prefiks: str) -> list[str]:
    """Kanoniczne nazwy narzędzi o danym prefiksie, alfabetycznie.

    Podział po PREFIKSIE nazwy (``oczyszczenie`` / ``naprawiacz``) jest tym
    samym rozstrzygnięciem, którego używa
    ``gui_manager_regul._zgadnij_typ_z_zaznaczenia`` — jedna heurystyka
    w dwóch miejscach zamiast dwóch list do synchronizacji.
    """
    return sorted(n for n in _narzedzia_akcentow() if n.startswith(prefiks))


def narzedzia_brakujace(kod_jezyka: str, prefiks: str) -> list[str]:
    """Kanoniczne nazwy narzędzi, których paczka ``kod_jezyka`` jeszcze NIE ma.

    To jest cała lista, z której kreator ma dać wybrać — pusta znaczy
    „paczka ma komplet", a nie „wpisz cokolwiek".
    """
    folder = os.path.join(cp.DICTIONARIES_DIR, kod_jezyka, "akcenty")
    istniejace = set()
    if os.path.isdir(folder):
        istniejace = {
            os.path.splitext(n)[0] for n in os.listdir(folder)
            if n.lower().endswith((".yaml", ".yml"))
        }
    return [n for n in narzedzia_dla_typu(prefiks) if n not in istniejace]


def paczka_istnieje(kod: str) -> bool:
    """Czy ``dictionaries/<kod>/`` jest na dysku (choćby jako stub)."""
    if not kod:
        return False
    return os.path.isdir(os.path.join(cp.DICTIONARIES_DIR, kod))


# =============================================================================
# Ocena celu
# =============================================================================
def ocen_cel(sciezka_rel: str, cfg: dict) -> tuple[Zastrzezenie, ...]:
    """Ocenia nazwę pliku, który ma powstać, wobec konfiguracji, która w nim będzie.

    Args:
        sciezka_rel: ścieżka WZGLĘDNA wobec ``dictionaries/``, posixowa albo
                     windowsowa (``"pl/akcenty/bulgarski.yaml"``).
        cfg:         zawartość YAML-a, która pod tą nazwą wyląduje — dla
                     kreatora sparsowany szablon, dla duplikatu wczytane
                     źródło. Pusty dict = „nie wiem, co będzie w środku",
                     wtedy oceniamy wyłącznie samą nazwę.

    Returns:
        Krotka zastrzeżeń, BLOKADY na początku. Pusta = nazwa jest w porządku.
    """
    czesci = str(sciezka_rel).replace("\\", "/").strip("/").split("/")
    if len(czesci) != 3:
        return ()                      # `<kod>/podstawy.yaml` i inne — nazwa stała
    _kod, podfolder, plik = czesci
    nazwa = os.path.splitext(plik)[0]

    if podfolder == "akcenty":
        zastrzezenia = _ocen_akcent(nazwa, cfg)
    elif podfolder == "opowiesci":
        zastrzezenia = _ocen_opowiesc(nazwa)
    elif podfolder == "szyfry":
        zastrzezenia = _ocen_szyfr(cfg)
    else:
        zastrzezenia = []              # `rezyser/`, `gui/` — klasa C / nazwa stała

    return tuple(sorted(zastrzezenia, key=lambda z: 0 if z.blokuje else 1))


def _ocen_akcent(nazwa: str, cfg: dict) -> list[Zastrzezenie]:
    """Reguły dla ``akcenty/``: nazwa języka ↔ ``kategoria`` ↔ ``iso``.

    Trzy niezmienniki sprawdzone WYKONANIEM na wszystkich dziewięciu paczkach
    (2026-09-17, 0 naruszeń), więc ich egzekwowanie nie odrzuca żadnego
    istniejącego pliku:

      1. nazwa należąca do kanonu ⇒ ``kategoria: akcent`` ORAZ ``iso`` tego
         właśnie języka,
      2. ``kategoria: akcent`` ⇒ nazwa z kanonu (chyba że język jest POZA
         kanonem — wtedy kanon nie ma czym rozstrzygnąć i nazwa jest wolna),
      3. narzędzia (``oczyszczenie*``, ``naprawiacz*``) nigdy nie noszą nazwy
         języka.
    """
    zastrzezenia: list[Zastrzezenie] = []
    iso_nazwy = jl.iso_dla_pliku_akcentu(nazwa)
    kategoria = str(cfg.get("kategoria") or "").strip().lower()
    iso_pola  = str(cfg.get("iso") or "").strip().lower()

    if iso_nazwy and kategoria and kategoria != "akcent":
        # Test 2: `bulgarski.yaml` z `kategoria: naprawiacz` DZIAŁA (dispatch
        # idzie po `kategoria`), więc to nie martwy plik, a działające
        # narzędzie pod nazwą zarezerwowaną dla akcentu tego języka.
        zastrzezenia.append(Zastrzezenie(
            BLOKADA, "nazwa_jezyka_nie_akcent",
            {"nazwa": nazwa,
             "jezyk": jl.nazwa_polska(iso_nazwy) or iso_nazwy,
             "kategoria": kategoria,
             "propozycja": ", ".join(narzedzia_dla_typu(kategoria))
                           or ", ".join(sorted(_narzedzia_akcentow()))},
        ))
        return zastrzezenia

    if kategoria and kategoria != "akcent":
        if iso_nazwy is None and nazwa not in _narzedzia_akcentow():
            # Czwarty wariant czyszczący pod własną nazwą jest LEGALNY (silnik
            # czyta `kategoria`, a crosscheck pl↔en obejmuje tylko trójkę),
            # ale autor paczki ma wiedzieć, że wypadł z kanonicznej trójki.
            zastrzezenia.append(Zastrzezenie(
                OSTRZEZENIE, "narzedzie_poza_kanonem",
                {"nazwa": nazwa,
                 "kanon": ", ".join(sorted(_narzedzia_akcentow()))},
            ))
        return zastrzezenia

    # Dalej: plik JEST (albo ma być) akcentem fonetycznym.
    if iso_nazwy and iso_pola and iso_pola != iso_nazwy:
        zastrzezenia.append(Zastrzezenie(
            BLOKADA, "akcent_iso_rozjazd",
            {"nazwa": nazwa,
             "jezyk_nazwy": jl.nazwa_polska(iso_nazwy) or iso_nazwy,
             "iso_nazwy": iso_nazwy,
             "iso_pola": iso_pola,
             "propozycja": jl.plik_akcentu(iso_pola) or ""},
        ))
    elif not iso_nazwy:
        kanoniczna = jl.plik_akcentu(iso_pola)
        if kanoniczna:
            # Test 1 i 3: `ucraine` przy `iso: uk`, `bulgarian` przy `iso: bg`.
            zastrzezenia.append(Zastrzezenie(
                BLOKADA, "akcent_zla_nazwa",
                {"nazwa": nazwa, "iso": iso_pola, "propozycja": kanoniczna},
            ))
        elif iso_pola:
            # Język POZA kanonem Lingui (faroeski, maltański, luksemburski…):
            # kanon nie zna jego polskiej nazwy, więc nie ma czym rozstrzygnąć
            # — i to jest stan POPRAWNY, dokładnie jak zakomentowane `lingua:`.
            zastrzezenia.append(Zastrzezenie(
                OSTRZEZENIE, "akcent_iso_poza_kanonem",
                {"nazwa": nazwa, "iso": iso_pola},
            ))

    if iso_pola and not paczka_istnieje(iso_pola):
        # Lustro noty G1 z `buduj_wielojezyczne_akcenty --audyt`: reguła
        # natywności mówi, że akcent celuje w język, który paczka ma na dysku.
        zastrzezenia.append(Zastrzezenie(
            OSTRZEZENIE, "akcent_brak_paczki_celu", {"iso": iso_pola},
        ))
    return zastrzezenia


def _ocen_opowiesc(nazwa: str) -> list[Zastrzezenie]:
    """Reguły dla ``opowiesci/``: silnik czyta WYŁĄCZNIE nazwy kanoniczne."""
    if nazwa in oai.NAZWY_PRZEPISOW:
        return []
    if nazwa.startswith("tryb_"):
        # Nowy tryb Opowieści wymaga okablowania w Pythonie (stała int + dwie
        # mapy + RadioBox), czego plik YAML nie zapewni — inaczej niż w Reżyserze,
        # gdzie dispatch idzie z pól. Zgoda użytkownika tego nie zmienia.
        return [Zastrzezenie(
            BLOKADA, "opowiesci_tryb_bez_okablowania",
            {"nazwa": nazwa, "kanon": ", ".join(sorted(oai.NAZWY_PRZEPISOW))},
        )]
    return [Zastrzezenie(
        OSTRZEZENIE, "opowiesci_nazwa_nieczytana",
        {"nazwa": nazwa, "kanon": ", ".join(sorted(oai.NAZWY_PRZEPISOW))},
    )]


def _ocen_szyfr(cfg: dict) -> list[Zastrzezenie]:
    """Reguły dla ``szyfry/``: nazwa pliku wolna, ale ``algorytm:`` z rejestru."""
    algorytm = str(cfg.get("algorytm") or "").strip()
    if algorytm and algorytm not in cp._ALGORYTMY_SZYFROW:
        return [Zastrzezenie(
            OSTRZEZENIE, "szyfr_algorytm_nieznany",
            {"algorytm": algorytm,
             "dostepne": ", ".join(sorted(cp._ALGORYTMY_SZYFROW))},
        )]
    return []
