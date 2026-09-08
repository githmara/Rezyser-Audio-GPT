#!/usr/bin/env python
"""audyt_podstaw.py — bramka na PODSTAWY paczki językowej: kanon Lingui + `podstawy.yaml`.

Dwie części, jedna bramka, bo jedna jest ORAKUŁEM drugiej: kanon
(`jezyki_lingua.py`) rozstrzyga, jaką wartość ma mieć pole `lingua:` w danym
folderze, więc rozdzielenie dałoby dwa moduły czytające te same dane i dwa
wpisy w `build_release`.

CZĘŚĆ 1 — kanon jest lustrem zainstalowanej biblioteki 1:1 (sześć klas niżej).
CZĘŚĆ 2 — treść `dictionaries/<kod>/podstawy.yaml` w każdej paczce na dysku:
pole `lingua` skonfrontowane z kanonem i kodem ISO FOLDERA, `alfabet` (wejście
szyfru Cezara), `polskie_znaki` (pre-pass KAŻDEGO akcentu paczki),
`slowo_akcent` przeliczone REALNYM parserem Księgi Świata i endonim
w `etykieta`. Szesnaście klas, każda z konsekwencją w działaniu — komentarz
nad sekcją „CZĘŚĆ 2" tłumaczy, dlaczego to KONTROLA, a nie siódmy generator
rodziny `buduj_wielojezyczne_*` (decyzja maintainera 2026-09-08).

Geneza (v18.29.0, etap 2 standardu „zero ciszy"). `jezyki_lingua.KANON` jest
LUSTREM enuma `lingua.Language`, a nie źródłem — i lustro bez kontroli po
cichu się starzeje: `pip install -U lingua-language-detector` może dodać język,
a wtedy kanon zaczyna KŁAMAĆ. Kłamie w najgorszy możliwy sposób, bo
`czy_w_lingua()` odpowiada „nie" o języku, który detektor obsługuje — i paczka
bez pola `lingua:` przestaje być usterką, choć nią jest.

Bramka nie ma BASELINE'U i to jest świadome odstępstwo od rodziny
`audyt_leakow`/`audyt_ciszy`. Tam baseline istnieje, bo trafienia są sądem
o TREŚCI (zastany dług bywa legalny). Tu trafienie znaczy „kanon nie jest
lustrem", a taki stan nie ma dopuszczalnej postaci: albo się zgadza 1:1, albo
jest zepsuty. Naprawa to jedna linia w `jezyki_lingua.py`, nie negocjacja.

Kanon kontrolują sześć klas:

  * ``brak-w-kanonie``   — biblioteka zna język, którego kanon nie ma (typowo:
    aktualizacja `lingui`). Skutek: `czy_w_lingua()` mówi „nie" o obsługiwanym
    języku, a szablon Managera Reguł każe zakomentować pole, które POWINNO być
    wypełnione.
  * ``nadwyzka-kanonu`` — kanon zna kod, którego biblioteka nie zna (literówka
    albo język WYCOFANY z `lingui`). Skutek: prefill w szablonie podaje nazwę,
    której detektor odrzuci.
  * ``rozjazd-enuma``   — ten sam kod ISO, inna nazwa enuma. Najgroźniejsza
    klasa, bo wszystko wygląda poprawnie: to dokładnie te cztery pułapki
    nazewnicze, których kanon ma nas pozbawić (`NORWEGIAN` → `BOKMAL`/
    `NYNORSK`, `SLOVENIAN` → `SLOVENE`, `FLEMISH` → `DUTCH`, `FILIPINO` →
    `TAGALOG`).
  * ``duplikat-enuma``  — dwa kody ISO wskazują jedną nazwę enuma, więc mapa
    odwrotna (`iso_dla_enuma`) po cichu gubi jeden z nich.
  * ``kolizja-nazwy``   — dwie polskie nazwy foldują się do jednej nazwy pliku
    akcentu (`norweski` dla `nb` i `nn`). Dwa języki o jednym pliku to nie
    kosmetyka: `dictionaries/<paczka>/akcenty/<nazwa>.yaml` jest
    IDENTYFIKATOREM i drugi język nadpisałby pierwszy.
  * ``zla-forma-nazwy`` — polska nazwa foldem nie schodzi do samych ASCII-liter
    (spacja, nawias, cyfra), więc nie nadaje się na nazwę pliku.

Fold liczy `buduj_wielojezyczne_akcenty.nazwa_pliku_akcentu` — TA SAMA funkcja,
którą ścieżka generująca nazywa nowe pary, sprawdzona na 72 istniejących.
Bramka nie ma prawa mieć własnej kopii folda; kopia mogłaby przepuścić nazwę,
na której realny generator się wywróci.

Łagodna degradacja jak w całej rodzinie: bez `lingui` w środowisku bramka NIE
BLOKUJE (kontrybutor bez pełnego dev-env), tylko melduje, że się nie wykonała.
Maintainer robiący kanoniczny release `lingui` MA, więc dostaje pełną kontrolę.

Użycie:
  python audyt_podstaw.py                # raport obu części (zero API, zero sieci)
  python audyt_podstaw.py --tylko-kanon  # tylko część 1 (lustro kanonu)
  python audyt_podstaw.py --bramka       # GATE: exit 1 na jakimkolwiek trafieniu
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import audyt_leakow as al
import buduj_wielojezyczne_akcenty as bwa
import dev_konsola
import dev_yaml
import jezyki_lingua
import refresh_languages as rl

dev_konsola.skonfiguruj_stdout()

NARZEDZIE = "audyt_podstaw"
ROOT = Path(__file__).resolve().parent

# Degradacje, które trafiły się w OSTATNIM przebiegu: część bramki, której nie
# dało się wykonać, i dlaczego (po angielsku). Wypełniane przez `zbierz`,
# meldowane przez bramkę i CLI — milczenie o niewykonanej połowie kontroli
# byłoby tą samą fałszywą czystością, przed którą stoi cały standard „zero
# ciszy" (v18.28.0).
_NOTY_DEGRADACJI: list[str] = []

# Klucz raportu i baseline-podobnej mapy `WynikBramki.nowe`. Kanon jest JEDNYM
# bytem (nie plikiem per język), więc wszystkie jego trafienia lądują pod jedną
# etykietą — czytelną w wyjściu `build_release`.
ZAKRES_KANON = "jezyki_lingua.KANON"


@dataclass
class Znalezisko:
    """Jedno trafienie bramki podstaw."""
    zakres: str      # `jezyki_lingua.KANON` (etap 2) albo kod paczki
    klasa: str       # brak-w-kanonie | nadwyzka-kanonu | rozjazd-enuma | …
    szczegol: str    # opis po angielsku (contributor-facing)

    def __str__(self) -> str:
        return f"{self.klasa}: {self.szczegol}"


def _kanon_biblioteki() -> dict[str, str]:
    """{ISO 639-1: NAZWA_ENUMA} wprost z zainstalowanej `lingui`.

    Import jest LENIWY i nieopakowany: `ImportError` ma wyjść na wołającego
    (`bramka`), który dopiero decyduje o łagodnej degradacji. Enuma nie da się
    iterować przez `list(Language)` (`TypeError: 'type' object is not
    iterable`) — jedyne wejście to `Language.all()` (zmierzone na 2.1.1).
    """
    from lingua import Language

    return {jezyk.iso_code_639_1.name.lower(): jezyk.name
            for jezyk in Language.all()}


def sprawdz_kanon() -> list[Znalezisko]:
    """Porównuje `jezyki_lingua.KANON` z zainstalowaną biblioteką (sześć klas).

    Rzuca `ImportError`, gdy `lingui` nie ma w środowisku — patrz `bramka`.
    """
    biblioteka = _kanon_biblioteki()
    kanon = jezyki_lingua.KANON
    znaleziska: list[Znalezisko] = []

    def dodaj(klasa: str, szczegol: str) -> None:
        znaleziska.append(Znalezisko(ZAKRES_KANON, klasa, szczegol))

    for iso in sorted(set(biblioteka) - set(kanon)):
        dodaj("brak-w-kanonie",
              f"`{iso}` ({biblioteka[iso]}) is known to the installed lingua but "
              f"missing from KANON — add the entry (ISO, enum name, traditional "
              f"Polish name of the language)")
    for iso in sorted(set(kanon) - set(biblioteka)):
        dodaj("nadwyzka-kanonu",
              f"`{iso}` ({kanon[iso][0]}) is in KANON but unknown to the installed "
              f"lingua — a typo, or the language was dropped from the library")
    for iso in sorted(set(kanon) & set(biblioteka)):
        if kanon[iso][0] != biblioteka[iso]:
            dodaj("rozjazd-enuma",
                  f"`{iso}`: KANON says `{kanon[iso][0]}`, the library says "
                  f"`{biblioteka[iso]}`")

    po_enumie: dict[str, list[str]] = {}
    po_pliku: dict[str, list[str]] = {}
    for iso, (nazwa_enuma, nazwa_pl) in sorted(kanon.items()):
        po_enumie.setdefault(nazwa_enuma, []).append(iso)
        forma = bwa.nazwa_pliku_akcentu(nazwa_pl)
        po_pliku.setdefault(forma, []).append(iso)
        if not forma or not forma.isascii() or not forma.isalpha():
            dodaj("zla-forma-nazwy",
                  f"`{iso}`: the Polish name „{nazwa_pl}” folds to „{forma}”, which "
                  f"is not a plain ASCII-letter accent file name")
    for nazwa_enuma, kody in sorted(po_enumie.items()):
        if len(kody) > 1:
            dodaj("duplikat-enuma",
                  f"`{nazwa_enuma}` is claimed by {', '.join(kody)} — "
                  f"`iso_dla_enuma` can only return one of them")
    for forma, kody in sorted(po_pliku.items()):
        if len(kody) > 1:
            nazwy = ", ".join(f"{k} („{kanon[k][1]}”)" for k in kody)
            dodaj("kolizja-nazwy",
                  f"{nazwy} all fold to the accent file name „{forma}” — give them "
                  f"distinct Polish names (cf. `nb` norweski / `nn` nynorski)")
    return znaleziska


# ---------------------------------------------------------------------------
# CZĘŚĆ 2: treść `dictionaries/<kod>/podstawy.yaml`
# ---------------------------------------------------------------------------
# Dlaczego kontrola, a nie generator (decyzja maintainera 2026-09-08): każdy
# z sześciu braci rodziny `buduj_wielojezyczne_*` ma ORAKUŁ — strukturę źródła,
# konsensus 72 par, tabele precedensowe. Dla `alfabet` i `polskie_znaki` NOWEGO
# języka orakuł w repozytorium nie istnieje, a błąd w tych dwóch polach psuje
# szyfr Cezara i pre-pass WSZYSTKICH akcentów paczki (lekcja G9/v18.22). Przy
# N=1 pliku na język korzyść skali generatora nie występuje — realną dziurą
# jest brak KONTROLI, nie brak generowania.
#
# Kontrole są ERRORAMI, nie uwagami: stan legalny nie jest tu w ogóle
# raportowany (paczka poza `lingua` bez pola `lingua:` przechodzi w milczeniu,
# a `ß` bez pary wielkoliterowej jest poprawny, bo `ß`.upper() = „SS").
# Zmierzone 2026-09-08 na dziewięciu wydanych paczkach: zero trafień.

# Dla polskiego endonim JEST polską nazwą języka („Polski"), więc kontrola
# „endonim to nie polska nazwa" musi ten jeden kod pominąć.
KOD_POLSKI = "pl"

# Kształt szykowany dla sondy wyzwalacza akcentu — dokładnie taki zapis
# pokazują podręczniki Księgi Świata.
_SZYK_SONDY = ("[Speaker 1: Test] - ma {slowo} {akcent}",
               "[Speaker 1: Test] - ma {akcent} {slowo}")


def paczki() -> list[str]:
    """Kody paczek językowych na dysku (folder z `podstawy.yaml`)."""
    if not (bwa.DICT_DIR).is_dir():
        return []
    return sorted(p.name for p in bwa.DICT_DIR.iterdir()
                  if p.is_dir() and (p / "podstawy.yaml").is_file())


def wczytaj_podstawy(kod: str) -> dict:
    """`dictionaries/<kod>/podstawy.yaml` — zepsuty plik = FATAL TEGO narzędzia.

    Wspólny loader `dev_yaml` (standard „zero ciszy"), ale wołany z WŁASNĄ nazwą
    narzędzia: `paczki()` wybrało ten kod właśnie po obecności pliku, więc plik
    nieczytelny albo niebędący mapą to zepsuta paczka, a nie „paczka bez uwag".
    Do audytu 2026-09-08 (N5) bramka używała loadera z
    `buduj_wielojezyczne_akcenty`, więc fatal podpisywał się cudzą nazwą.
    """
    return dev_yaml.wczytaj_lub_padnij(
        bwa.DICT_DIR / kod / "podstawy.yaml", narzedzie=NARZEDZIE)


def _sprawdz_lingua(kod: str, dane: dict, dodaj) -> None:
    """Pole `lingua:` skonfrontowane z kanonem i kodem ISO FOLDERA."""
    wartosc = dane.get("lingua")
    oczekiwana = jezyki_lingua.nazwa_enuma(kod)
    if not isinstance(wartosc, str) or not wartosc.strip():
        if oczekiwana:
            dodaj("lingua-brak",
                  f"no `lingua:` field, but the detector DOES support this "
                  f"language — declare `lingua: {oczekiwana}` (without it the pack "
                  f"never takes part in automatic language detection)")
        return   # język poza kanonem: brak pola to poprawny stan paczki
    nazwa = wartosc.strip().upper()
    if oczekiwana and nazwa != oczekiwana:
        gdzie = jezyki_lingua.iso_dla_enuma(nazwa)
        dodaj("lingua-rozjazd",
              f"`lingua: {nazwa}` does not belong to ISO `{kod}` — the canonical "
              f"name is `{oczekiwana}`"
              + (f" and `{nazwa}` is the language of folder `{gdzie}`" if gdzie
                 else " and `{}` is not a detector name at all".format(nazwa)))
    elif not oczekiwana and jezyki_lingua.iso_dla_enuma(nazwa) is None:
        dodaj("lingua-nieznana",
              f"`lingua: {nazwa}` is not a name the detector knows, and ISO "
              f"`{kod}` is outside the canon too — comment the field out instead "
              f"(a name the detector does not know has the same effect as no "
              f"field, only quieter)")
    elif not oczekiwana:
        dodaj("lingua-rozjazd",
              f"`lingua: {nazwa}` is a valid detector name, but it belongs to "
              f"ISO `{jezyki_lingua.iso_dla_enuma(nazwa)}`, not to this folder "
              f"(`{kod}`) — the detector would map detected text to the wrong pack")


def _sprawdz_alfabet(kod: str, dane: dict, dodaj) -> None:
    """`alfabet`: wersaliki, litery, unikalność, brak liter puchnących pod `.upper()`.

    Ten łańcuch jest wejściem szyfru Cezara (`core_poliglota`), więc każda
    z czterech własności ma konsekwencję w działaniu: mała litera i znak
    niebędący literą wypadają z szyfrowania, duplikat przesuwa alfabet o inną
    liczbę pozycji dla dwóch takich samych liter, a litera puchnąca pod
    `.upper()` (`ß` → `SS`) rozjeżdża długość alfabetu z długością tekstu.
    """
    alfabet = dane.get("alfabet")
    if not isinstance(alfabet, str) or not alfabet.strip():
        dodaj("alfabet-brak",
              "no `alfabet` (the Caesar cipher has nothing to shift along)")
        return
    male = sorted({z for z in alfabet if z != z.upper()})
    if male:
        dodaj("alfabet-male",
              f"`alfabet` contains lowercase letter(s) {male} — the field must be "
              f"UPPERCASE (the cipher upper-cases the text before shifting)")
    nie_litery = sorted({z for z in alfabet if not z.isalpha()})
    if nie_litery:
        dodaj("alfabet-nie-litera",
              f"`alfabet` contains {nie_litery} — only letters belong there "
              f"(whitespace, digits and punctuation pass through the cipher)")
    duplikaty = sorted({z for z in alfabet if alfabet.count(z) > 1})
    if duplikaty:
        dodaj("alfabet-duplikat",
              f"`alfabet` repeats {duplikaty} — a repeated letter shifts by a "
              f"different number of positions depending on which copy is found")
    puchnace = sorted({z for z in alfabet if len(z.upper()) > 1})
    if puchnace:
        dodaj("alfabet-puchnie",
              f"`alfabet` contains {puchnace}, whose `.upper()` is longer than one "
              f"character (e.g. ß → SS) — such letters NEVER enter the alphabet; "
              f"put them in `polskie_znaki` instead")


def _sprawdz_znaki(kod: str, dane: dict, dodaj) -> None:
    """`polskie_znaki`: kształt par, cel w ASCII, warianty lower+upper.

    Ta lista jest PRE-PASSEM każdego akcentu z `usun_polskie_znaki: true`, więc
    jej dziura zostawia diakrytyk w tekście podanym syntezatorowi — i to
    w każdej parze akcentowej paczki naraz.
    """
    znaki = dane.get("polskie_znaki")
    if not isinstance(znaki, list) or not znaki:
        dodaj("znaki-ksztalt",
              "no `polskie_znaki` list (accents with `usun_polskie_znaki: true` "
              "would have nothing to strip)")
        return
    wzory: list[str] = []
    for poz, wpis in enumerate(znaki, start=1):
        if not isinstance(wpis, dict) or "wzor" not in wpis or "zamiana" not in wpis:
            dodaj("znaki-ksztalt",
                  f"`polskie_znaki` entry #{poz} is not a "
                  f"{{ wzor, zamiana }} mapping: {wpis!r}")
            continue
        wzor, zamiana = str(wpis["wzor"]), str(wpis["zamiana"])
        if not wzor:
            dodaj("znaki-ksztalt", f"`polskie_znaki` entry #{poz} has an empty `wzor`")
            continue
        wzory.append(wzor)
        if not zamiana.isascii():
            dodaj("znaki-cel-nieascii",
                  f"`{wzor}` → `{zamiana}`: the replacement is not ASCII, so the "
                  f"pre-pass leaves a diacritic in the text handed to the "
                  f"synthesizer")
        if wzor == zamiana:
            dodaj("znaki-tozsamosc",
                  f"`{wzor}` → `{zamiana}`: a rule that replaces a character with "
                  f"itself is dead weight")
    for wzor in sorted(set(wzory)):
        if len(wzor) != 1 or wzor.lower() == wzor.upper():
            continue
        # Litera, której druga wielkość jest DŁUŻSZA niż jeden znak, nie ma
        # jednoznakowego bliźniaka i mieć nie może: `ß`.upper() = „SS",
        # a tureckie `İ`.lower() = „i̇" (i + U+0307). Oba kierunki, bo audyt
        # 2026-09-08 (S2) złapał fałszywy alarm dokładnie na tym lustrzanym
        # przypadku — a `tr` i `az` są w kanonie, więc to najbliższy realny
        # kandydat na dziesiątą paczkę, nie hipoteza.
        if len(wzor.upper()) > 1 or len(wzor.lower()) > 1:
            continue
        blizniak = wzor.upper() if wzor == wzor.lower() else wzor.lower()
        # Bliźniak, który JEST czystym ASCII, nie potrzebuje reguły pre-passu —
        # transliterować nie ma czego. Turecka bezkropkowa `ı` transliteruje się
        # do `i`, ale jej wielka forma to zwykłe `I`, więc żądanie wpisu `I → I`
        # produkowałoby regułę tożsamościową, na którą ta sama bramka słusznie
        # krzyczy klasą `znaki-tozsamosc` (audyt 2026-09-08, S2).
        if blizniak.isascii():
            continue
        if blizniak not in wzory:
            dodaj("znaki-bez-pary",
                  f"`{wzor}` has no `{blizniak}` counterpart — the pre-pass is "
                  f"a literal `str.replace`, so the missing case survives into "
                  f"the synthesizer's input")


def _sprawdz_slowo_akcent(kod: str, dane: dict, pary: dict, dodaj) -> None:
    """`slowo_akcent` przeliczone REALNYM parserem Księgi Świata (v18.25).

    Deklaracja „to słowo wyzwala akcent" jest sprawdzalna tylko przez
    uruchomienie: `core_rezyser.zbuduj_mape_akcentow` buduje z tej listy regex
    łapiący „<słowo> X" i „X <słowo>", a lekcja v18.25 mówi, dlaczego trzeba
    zmierzyć OBA szyki — do v18.24.2 wygrywało najlewsze dopasowanie i zapis
    „ma akcent francuski" dawał nazwę mówcy `ma`, więc akcent NIE był nakładany.
    Sonda używa akcentu, który ta paczka realnie ma na dysku.
    """
    slowa = dane.get("slowo_akcent")
    if not isinstance(slowa, list) or not slowa:
        dodaj("slowo-akcent-brak",
              "no `slowo_akcent` list — Director mode cannot recognize any accent "
              "declared in the World Book for this pack")
        return
    akcenty = sorted(a for (p, a) in pary if p == kod)
    if not akcenty:
        return   # paczka bez par akcentowych: nie ma czym sondować, to nie usterka
    try:
        import core_rezyser as cr
    except ImportError as exc:
        # Silnik ciągnie `python-docx`/`num2words`, więc w okrojonym środowisku
        # kontrybutora sonda może się nie dać uruchomić. Reszta klas działa
        # dalej, ale bramka MUSI powiedzieć, czego nie sprawdziła.
        nota = (f"accent trigger words not re-run through the engine "
                f"(core_rezyser unavailable: {exc})")
        if nota not in _NOTY_DEGRADACJI:
            _NOTY_DEGRADACJI.append(nota)
        return

    bwa.ustaw_silnik()
    # Sondujemy akcentem, który SILNIK uznaje za akcent — inaczej zielona sonda
    # mówiłaby o pliku, a nie o wyzwalaczu. Gdy nie uznaje żadnego, deklaracja
    # akcentu w Księdze Świata nie zadziała w tej paczce w ogóle i to jest
    # osobne, mocniejsze znalezisko (samą `kategoria` pilnuje G1 w
    # `buduj_wielojezyczne_akcenty` — tu nie duplikujemy tamtej bramki).
    akcent = next((a for a in akcenty if cr.czy_znany_akcent(a, kod)), "")
    if not akcent:
        dodaj("akcent-nierozpoznany",
              f"the pack has {len(akcenty)} accent file(s) ({', '.join(akcenty)}) "
              f"but the engine recognizes NONE of them as an accent, so no World "
              f"Book accent declaration can work here — run "
              f"`python buduj_wielojezyczne_akcenty.py --audyt` (gate G1) for the "
              f"reason")
        return
    for slowo in slowa:
        if not isinstance(slowo, str) or not slowo.strip():
            dodaj("slowo-akcent-brak",
                  f"`slowo_akcent` contains an empty entry ({slowo!r})")
            continue
        martwe = []
        for szyk in _SZYK_SONDY:
            tekst = szyk.format(slowo=slowo.strip(), akcent=akcent)
            mapa = cr.zbuduj_mape_akcentow(tekst, kod)
            rozpoznane = {(w or {}).get("nazwa") for w in mapa.values()}
            if akcent not in rozpoznane:
                martwe.append(tekst)
        if martwe:
            dodaj("slowo-akcent-nieaktywny",
                  f"a World Book accent declaration does NOT work for this pack: "
                  f"the real parser did not recognize the `{akcent}` accent in "
                  + "; ".join(f"„{t}”" for t in martwe)
                  + f". Check both ends — the trigger word „{slowo}” and the "
                    f"`kategoria: akcent` of `akcenty/{akcent}.yaml`")


def _sprawdz_etykieta(kod: str, dane: dict, dodaj) -> None:
    """`etykieta`: separator endonimu + endonim, który NIE jest nazwą polską.

    Etykieta jest jedynym miejscem, z którego narzędzia biorą natywną nazwę
    języka (`refresh_languages.natywna_nazwa`, rdzeń rodziny autotłumaczy →
    nazwa celu dla modelu). Bez separatora ` – ` cała etykieta udaje endonim,
    a polska nazwa w tym polu („Szwedzki – …" zamiast „Svenska – …") wysyła
    modelowi błędny cel i psuje nagłówek paczki dla jej własnych użytkowników.
    """
    etykieta = dane.get("etykieta")
    if not isinstance(etykieta, str) or not etykieta.strip():
        dodaj("etykieta-brak",
              "no `etykieta` (the pack has no name to show, and the tools have "
              "no native language name to hand the model)")
        return
    # Endonim rozcina TA SAMA reguła, której używa `refresh_languages` (jedno
    # źródło separatora), ale na JUŻ WCZYTANYCH danych — inaczej fatal o zepsutym
    # pliku podpisywałby się nazwą tamtego narzędzia (audyt 2026-09-08, N5).
    endonim = rl.endonim_z_etykiety(etykieta)
    if endonim == etykieta.strip():
        dodaj("etykieta-separator",
              f"`etykieta` has no ` – ` separator, so the whole string „"
              f"{etykieta.strip()}” is taken as the native language name")
        return
    nazwa_pl = jezyki_lingua.nazwa_polska(kod)
    if kod != KOD_POLSKI and nazwa_pl and endonim.lower() == nazwa_pl.lower():
        dodaj("etykieta-polska-nazwa",
              f"the native name in `etykieta` is „{endonim}”, which is the POLISH "
              f"name of this language — the field must open with the endonym "
              f"(what its own speakers call it)")


def sprawdz_paczki() -> list[Znalezisko]:
    """Kontrola treści `podstawy.yaml` w każdej paczce na dysku."""
    pary = bwa.pary_akcentowe()
    znaleziska: list[Znalezisko] = []
    for kod in paczki():
        dane = wczytaj_podstawy(kod)

        def dodaj(klasa: str, szczegol: str, _kod: str = kod) -> None:
            znaleziska.append(Znalezisko(f"dictionaries/{_kod}/podstawy.yaml",
                                         klasa, szczegol))

        if str(dane.get("id", "")).strip() != "podstawy":
            dodaj("id-rozjazd",
                  f"`id: {dane.get('id')!r}` — the engine looks this file up by "
                  f"`id: podstawy`")
        if str(dane.get("jezyk", "")).strip() != kod:
            dodaj("jezyk-rozjazd",
                  f"`jezyk: {dane.get('jezyk')!r}` does not match the folder name "
                  f"`{kod}`, and the folder name is what the engine trusts")
        _sprawdz_lingua(kod, dane, dodaj)
        _sprawdz_alfabet(kod, dane, dodaj)
        _sprawdz_znaki(kod, dane, dodaj)
        _sprawdz_slowo_akcent(kod, dane, pary, dodaj)
        _sprawdz_etykieta(kod, dane, dodaj)
    return znaleziska


def zbierz(*, tylko_kanon: bool = False) -> dict[str, list[str]]:
    """Trafienia jako `{"<zakres>": ["<klasa>|<szczegol>", …]}` — kanon raportu.

    Degradacja jest ROZDZIELONA na dwie części i to jest poprawka po audycie
    2026-09-08 (S1). Brak `lingui` w środowisku unieruchamia WYŁĄCZNIE część 1
    (lustro kanonu wobec biblioteki); część 2 nie tyka biblioteki — jej orakułem
    jest czysto pythonowy `jezyki_lingua.KANON` — więc jedzie dalej. Do
    poprawki jedno `except ImportError` wyciszało całą bramkę, czyli
    kontrybutor bez pełnego dev-env nie dostawał ŻADNEJ kontroli podstaw.
    """
    _NOTY_DEGRADACJI.clear()
    znaleziska: list[Znalezisko] = []
    try:
        znaleziska += sprawdz_kanon()
    except ImportError as exc:
        _NOTY_DEGRADACJI.append(
            f"canon mirror NOT checked against the library (lingua not "
            f"available: {exc})")
    if not tylko_kanon:
        znaleziska += sprawdz_paczki()
    wynik: dict[str, list[str]] = {}
    for z in znaleziska:
        wynik.setdefault(z.zakres, []).append(f"{z.klasa}|{z.szczegol}")
    return {k: sorted(v) for k, v in wynik.items()}


def bramka(*, tylko_kanon: bool = False) -> al.WynikBramki:
    """Bramka podstaw. BEZ baseline'u — każde trafienie blokuje.

    Zwraca ten sam typ, co pozostałe bramki rodziny (`al.WynikBramki`), więc
    `build_release` konsumuje ją tym samym wzorcem — z jedną różnicą, którą
    wołający musi znać: `pominieto` zostaje ``False``, bo część 2 wykonuje się
    ZAWSZE, a `powod_pominiecia` niesie wtedy listę tego, czego mimo to nie
    sprawdzono (brak `lingui`, brak silnika dla sondy wyzwalaczy). Niepusty
    powód przy `czysto=True` znaczy „czysto, ale nie wszędzie tak samo
    dokładnie" i wołający MUSI to powiedzieć na głos — wzorzec
    `WynikBramki.pokrycie_obnizone` z bramki leaków.
    """
    aktualne = zbierz(tylko_kanon=tylko_kanon)
    return al.WynikBramki(not aktualne, aktualne, False,
                          "; ".join(_NOTY_DEGRADACJI))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate over the language-pack foundations. Part 1: verify that "
                    "`jezyki_lingua.KANON` is a 1:1 mirror of the installed "
                    "lingua-language-detector (same ISO codes, same enum names, no "
                    "surplus, no gaps, unique accent file names). Part 2: check the "
                    "content of every `dictionaries/<code>/podstawy.yaml` — the "
                    "`lingua:` field against the canon and the folder ISO, the "
                    "`alfabet` the Caesar cipher shifts along, the `polskie_znaki` "
                    "pre-pass of every accent, the `slowo_akcent` trigger words "
                    "re-run through the real World Book parser, and the endonym in "
                    "`etykieta`.",
    )
    parser.add_argument("--bramka", action="store_true",
                        help="CI/build GATE: exit 1 on any hit (this gate has no "
                             "baseline — the canon either mirrors the library or it "
                             "is broken, and a broken `podstawy.yaml` breaks the "
                             "cipher and every accent of the pack).")
    parser.add_argument("--tylko-kanon", dest="tylko_kanon", action="store_true",
                        help="Run part 1 only (the canon mirror), skipping the "
                             "per-pack content checks.")
    args = parser.parse_args()

    if args.bramka:
        wynik = bramka(tylko_kanon=args.tylko_kanon)
        print("========== FOUNDATIONS GATE (lingua canon + podstawy.yaml) ==========")
        # Niepusty powód przy zielonej bramce = „czysto, ale czegoś nie
        # sprawdziliśmy". Mówimy to ZAWSZE, nie tylko przy trafieniach.
        if wynik.powod_pominiecia:
            print(f"⚠️  Reduced coverage: {wynik.powod_pominiecia}.")
        if wynik.czysto:
            if "canon mirror NOT checked" in wynik.powod_pominiecia:
                czesc_1 = "canon mirror not verified"
            else:
                czesc_1 = (f"KANON mirrors the installed lingua 1:1 "
                           f"({len(jezyki_lingua.KANON)} languages)")
            czesc_2 = ("part 2 skipped (--tylko-kanon)" if args.tylko_kanon
                       else f"all {len(paczki())} pack foundation file(s) are clean")
            print(f"✅ {czesc_1}; {czesc_2}.")
            print("=====================================================================")
            return 0
        ile = sum(len(v) for v in wynik.nowe.values())
        print(f"❌ {ile} defect(s) in the language-pack foundations:")
        for zakres, powody in sorted(wynik.nowe.items()):
            for p in powody:
                klasa, _, szczegol = p.partition("|")
                print(f"  • {zakres} [{klasa}]: {szczegol}")
        # Rada naprawcza tylko dla tych zakresów, które REALNIE dostały
        # trafienie — inaczej bramka mówi o kanonie także przy usterce paczki
        # (audyt 2026-09-08, N5).
        if ZAKRES_KANON in wynik.nowe:
            print("Fix (canon): `jezyki_lingua.KANON` is a MIRROR of the library "
                  "enum, so the library always wins — edit the canon, not the "
                  "expectation.")
        if any(z != ZAKRES_KANON for z in wynik.nowe):
            print("Fix (pack): the `alfabet` feeds the Caesar cipher and "
                  "`polskie_znaki` is the pre-pass of EVERY accent in the pack, so "
                  "a defect there fails quietly and everywhere at once.")
        print("=====================================================================")
        return 1

    znaleziska: list[Znalezisko] = []
    print(f"🔎 Kanon Lingui: {len(jezyki_lingua.KANON)} wpisów w "
          f"`jezyki_lingua.KANON`.")
    try:
        znaleziska = sprawdz_kanon()
    except ImportError as exc:
        # Brak biblioteki unieruchamia TYLKO część 1 — część 2 leci dalej
        # (audyt 2026-09-08, S1). Dawniej `return 0` w tym miejscu zabierał
        # kontrybutorowi bez pełnego dev-env całą kontrolę podstaw paczki.
        print(f"⚠️  `lingua` not available ({exc}) — the canon has nothing to be "
              f"compared against (install `lingua-language-detector`). The "
              f"per-pack checks below do NOT need it and run anyway.")
    else:
        if not znaleziska:
            print("✅ Kanon jest lustrem zainstalowanej biblioteki 1:1 "
                  "(kody, nazwy enumów, unikalne nazwy plików akcentów).")
    if not args.tylko_kanon:
        kody = paczki()
        poza = [k for k in kody if not jezyki_lingua.czy_w_lingua(k)]
        print(f"🔎 Podstawy paczek: {len(kody)} plików ({', '.join(kody)}).")
        if poza:
            print(f"ℹ️  Poza kanonem Lingui (brak pola `lingua:` jest tam stanem "
                  f"poprawnym): {', '.join(poza)}.")
        _NOTY_DEGRADACJI.clear()
        z_paczek = sprawdz_paczki()
        for nota in _NOTY_DEGRADACJI:
            print(f"⚠️  Reduced coverage: {nota}.")
        if not z_paczek:
            print("✅ Podstawy wszystkich paczek bez uwag (pole `lingua`, alfabet, "
                  "pre-pass, wyzwalacze akcentu przeliczone parserem, endonim).")
        znaleziska = znaleziska + z_paczek
    if not znaleziska:
        return 0
    licznik: dict[str, int] = {}
    for z in znaleziska:
        licznik[z.klasa] = licznik.get(z.klasa, 0) + 1
    print(f"\n❌ {len(znaleziska)} defect(s):\n")
    for z in znaleziska:
        print(f"   · [{z.zakres}] {z}")
    print("\n========== TOTAL: "
          + ", ".join(f"{k} {v}" for k, v in sorted(licznik.items()))
          + " ==========")
    return 1


if __name__ == "__main__":
    sys.exit(main())
