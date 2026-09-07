# -*- coding: utf-8 -*-
"""
test_oczyszczanie_tts.py - Bramka uniwersalnosci czyszczenia TTS (18.27).

Czyszczenie tekstu pod syntezator (`core_poliglota.oczysc_tekst_tts`) obsluguje
DOWOLNY plik z dysku: karmi je Poliglota (dwa warianty "Zaden (Czyszczenie...)"
plus 90 plikow akcentow z `czysc_tekst_tts: true`) oraz Szyfrant. Do 18.26.1
mialo zaszyte w Pythonie reguly zalezne od polszczyzny: dwa regexy na fraze
"z wplecionymi wdechami" i liste wykrzyknikow `khh|hh|pff|ahh|ehh`. Zmierzone
skutki: dla `ru` ("Khh", "Pff" cyrylica) i `fi` ("Ohh") byly no-opem, a dla `is`
kasowaly autorskie "Pff," i "Ahh," z dialogu. Rownolegle "uniwersalna" higiena
byla ASCII-only: wielokropek "..." (U+2026) nie byl obslugiwany wcale, a nawias
okragly zjadal dwa akapity naraz i nie widzial nawiasow pelnej szerokosci.

Niezmienniki pilnowane tutaj:
  G1 - w sciezce czyszczenia NIE MA literalu jezyka naturalnego. Kolejne
       "szybkie usuniecie frazy" po polsku nie wejdzie niezauwazone.
  G2 - wynik czyszczenia jest IDENTYCZNY dla kazdego jezyka paczki (i dla kodu
       jezyka, ktorego paczki jeszcze nie ma). Jedyny etap jezykowy to
       normalizacja liczb.
  G3 - regresje zmierzonych defektow: wielokropek Unicode, nawias przez pusta
       linie, nawias pelnej szerokosci, nawias zagniezdzony, niedomkniety
       nawias, nietykalnosc tagow w nawiasach kwadratowych, przetrwanie
       autorskich wykrzyknikow.

Uruchom:  .venv/Scripts/python test_oczyszczanie_tts.py
"""

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import core_poliglota as cp

# Funkcje i stale modulu, ktore RAZEM tworza sciezke czyszczenia. Stale sa tu
# istotne: regex didaskaliow zyje na poziomie modulu, wiec sam
# `inspect.getsource(oczysc_tekst_tts)` by go nie objal.
FUNKCJE_CZYSZCZENIA = ("oczysc_tekst_tts", "_usun_didaskalia",
                       "sklej_pojedyncze_litery", "normalizuj_liczby")
STALE_CZYSZCZENIA = ("_RE_DIDASKALIA", "_WIELOKROPEK")

# Trzy litery z rzedu w literale = slowo jezyka naturalnego. Tokeny regexow
# (\s, \w, \b, [a-z], "...") maja najwyzej jedna litere pod rzad.
RE_SLOWO = re.compile(r"[^\W\d_]{3,}")


def _literaly_sciezki_czyszczenia():
    """Zwraca liste (nazwa, literal) ze wskazanych funkcji i stalych modulu."""
    zrodlo = Path(cp.__file__).read_text(encoding="utf-8")
    drzewo = ast.parse(zrodlo)
    znalezione = []

    def wezel_docstringa(funkcja):
        """Sam WEZEL docstringa - ast.get_docstring zwraca tekst po cleandoc,
        wiec porownanie po wartosci nie trafia w oryginalny literal."""
        pierwsza = funkcja.body[0] if funkcja.body else None
        if (isinstance(pierwsza, ast.Expr)
                and isinstance(pierwsza.value, ast.Constant)
                and isinstance(pierwsza.value.value, str)):
            return pierwsza.value
        return None

    def zbierz(nazwa, wezel, pomijany):
        for pod in ast.walk(wezel):
            if pod is pomijany:
                continue
            if isinstance(pod, ast.Constant) and isinstance(pod.value, str):
                znalezione.append((nazwa, pod.value))

    for wezel in drzewo.body:
        if isinstance(wezel, ast.FunctionDef) and wezel.name in FUNKCJE_CZYSZCZENIA:
            zbierz(wezel.name, wezel, wezel_docstringa(wezel))
        elif isinstance(wezel, ast.Assign):
            for cel in wezel.targets:
                if isinstance(cel, ast.Name) and cel.id in STALE_CZYSZCZENIA:
                    zbierz(cel.id, wezel.value, None)
    return znalezione


# Probki: kazda w innym pismie i z innym artefaktem. Tekstu probek nie
# drukujemy surowo - konsola dev-a bywa na cp1250.
PROBA_WIELOPISMOWA = (
    "## Naglowek\n"
    "*Anna* (szeptem) mowi: to znaczy… tak.\n\n"
    "Кхх... — Пфф, сказал он (шёпотом).\n\n"
    "Öhh, no niin (kuiskaten). Pff, sagdi hann. ¿Qué?... ¡Vaya!\n\n"
    "他说（轻声）然后走了。\n"
)

# Kody, dla ktorych wynik musi byc identyczny: wszystkie paczki + dwa kody
# jeszcze nieistniejace (przyszly jezyk nie moze dostac innego czyszczenia).
def _kody_do_symetrii():
    return sorted(set(cp.dostepne_jezyki_bazowe()) | {"sv", "zh"})


# ---------------------------------------------------------------------------
# G1 - brak literalu jezyka naturalnego w sciezce czyszczenia
# ---------------------------------------------------------------------------
def test_g1_sciezka_czyszczenia_bez_slow_jezyka_naturalnego():
    """Literal ze slowem = regula per jezyk, czyli dlug bez konca."""
    literaly = _literaly_sciezki_czyszczenia()
    assert literaly, "nie znalazlem zadnych literalow - zmienily sie nazwy?"
    winne = [(nazwa, tekst) for nazwa, tekst in literaly
             if RE_SLOWO.search(tekst)]
    assert not winne, [(n, ascii(t)) for n, t in winne]


def test_g1_bramka_widzi_wzorzec_jaki_usunelismy():
    """Kontrola kryterium: stare reguly MUSZA wpadac w RE_SLOWO."""
    for stary in (r"\b(khh|hh|pff|ahh|ehh)\b[\.\s]*",
                  r"(?i)[,\s]*z\s*wplecionymi\s*wdechami",
                  r"(?i)[,\s]*z\s*wdech(em|ami)"):
        assert RE_SLOWO.search(stary), ascii(stary)
    # ...a realne tokeny regexow NIE moga dawac falszywego alarmu.
    for niewinny in (r"[\*=]+", r"^#+\s*", r"^\s*,\s*", r" {2,}",
                     r"(?:\.\s*){4,}", r"\1 ", "...", "…",
                     r"(?i)\b[a-z](?:\s+[a-z]\b)+(?!\w)"):
        assert not RE_SLOWO.search(niewinny), ascii(niewinny)


# ---------------------------------------------------------------------------
# G2 - symetria jezykowa
# ---------------------------------------------------------------------------
def test_g2_wynik_identyczny_dla_wszystkich_kodow():
    """Bez normalizacji liczb czyszczenie nie ma prawa zalezec od jezyka."""
    kody = _kody_do_symetrii()
    assert len(kody) >= 9, kody
    wyniki = {kod: cp.oczysc_tekst_tts(PROBA_WIELOPISMOWA,
                                       z_normalizacja=False, jezyk=kod)
              for kod in kody}
    wzorzec = wyniki[kody[0]]
    rozne = {kod: ascii(w) for kod, w in wyniki.items() if w != wzorzec}
    assert not rozne, rozne


def test_g2_symetria_takze_z_wlaczona_normalizacja_gdy_brak_cyfr():
    """Tekst bez cyfr nie ma zadnego etapu zaleznego od jezyka."""
    bez_cyfr = PROBA_WIELOPISMOWA
    assert not re.search(r"\d", bez_cyfr)
    wyniki = {kod: cp.oczysc_tekst_tts(bez_cyfr, z_normalizacja=True, jezyk=kod)
              for kod in _kody_do_symetrii()}
    assert len(set(wyniki.values())) == 1, {k: ascii(v) for k, v in wyniki.items()}


def test_g2_normalizacja_liczb_pozostaje_jezykowa():
    """Jedyny etap jezykowy musi dalej dzialac - inaczej symetria jest pusta."""
    pl = cp.oczysc_tekst_tts("Mam 123 lata.", z_normalizacja=True, jezyk="pl")
    en = cp.oczysc_tekst_tts("Mam 123 lata.", z_normalizacja=True, jezyk="en")
    assert "sto dwadzie" in pl, ascii(pl)
    assert "one hundred" in en, ascii(en)
    assert pl != en


# ---------------------------------------------------------------------------
# G3 - regresje zmierzonych defektow
# ---------------------------------------------------------------------------
def test_g3_wielokropek_unicode_jest_obslugiwany():
    """"..." (U+2026) bylo niewidzialne, choc ASCII-owy odpowiednik nie."""
    wynik = cp.oczysc_tekst_tts("No wiesz… to znaczy…, tak.",
                                z_normalizacja=False)
    assert "…" not in wynik, ascii(wynik)
    assert "..." in wynik, ascii(wynik)
    # Osierocony przecinek po wielokropku wypada tak samo jak w ASCII.
    assert "..., tak" not in wynik, ascii(wynik)


def test_g3_nawias_nie_przekracza_pustej_linii():
    """Dawniej "akapit (uwaga | pusta linia | drugi)" schodzil do jednego."""
    wejscie = "Pierwszy akapit (uwaga\n\nDrugi akapit) trzeci."
    wynik = cp.oczysc_tekst_tts(wejscie, z_normalizacja=False)
    assert "Pierwszy akapit" in wynik, ascii(wynik)
    assert "Drugi akapit" in wynik, ascii(wynik)
    assert "trzeci" in wynik, ascii(wynik)


def test_g3_nawias_zawijany_twardo_nadal_wypada_caly():
    """Ksiazka zawijana na 72 kolumnach ma didaskalia przez zlamanie wiersza."""
    wejscie = "Mowi (bardzo cicho\ni z namyslem) i wychodzi."
    wynik = cp.oczysc_tekst_tts(wejscie, z_normalizacja=False)
    assert "cicho" not in wynik, ascii(wynik)
    assert "namyslem" not in wynik, ascii(wynik)
    assert "wychodzi" in wynik, ascii(wynik)


def test_g3_nawias_pelnej_szerokosci_tez_jest_didaskalium():
    """Pismo CJK zapisuje didaskalia w U+FF08/U+FF09 - dawniej niewidzialne."""
    wejscie = "他说（轻声）然后走了。"
    wynik = cp.oczysc_tekst_tts(wejscie, z_normalizacja=False)
    assert "（" not in wynik and "）" not in wynik, ascii(wynik)
    assert "轻声" not in wynik, ascii(wynik)
    assert "他说" in wynik, ascii(wynik)


def test_g3_nawias_zagniezdzony_nie_zostawia_slowa_do_przeczytania():
    """Jeden przebieg zostawialby "(mowi )" - syntezator by to przeczytal."""
    wynik = cp.oczysc_tekst_tts("Ona (mowi (cicho)) i wychodzi.",
                                z_normalizacja=False)
    assert "mowi" not in wynik, ascii(wynik)
    assert "cicho" not in wynik, ascii(wynik)
    assert "wychodzi" in wynik, ascii(wynik)


def test_g3_niedomkniety_nawias_nie_pochlania_prozy():
    """Sierocy "(" zostaje jako znak, ale nie zjada zdania do nastepnego ")"."""
    wejscie = "Powiedzial (cicho i wyszedl. Potem wrocila (szeptem) do domu."
    wynik = cp.oczysc_tekst_tts(wejscie, z_normalizacja=False)
    assert "Potem wrocila" in wynik, ascii(wynik)
    assert "szeptem" not in wynik, ascii(wynik)
    assert "do domu" in wynik, ascii(wynik)


def test_g3_tagi_w_nawiasach_kwadratowych_nietykalne():
    """Tam zyja tagi mowcow i audio-tagi ElevenLabs."""
    wynik = cp.oczysc_tekst_tts("[Anna] [whispers] Dobrze, chodzmy.",
                                z_normalizacja=False)
    assert "[Anna]" in wynik, ascii(wynik)
    assert "[whispers]" in wynik, ascii(wynik)


def test_g3_autorskie_wykrzykniki_przetrwaja_w_kazdym_jezyku():
    """Wejscie to dowolny plik z dysku - "Pff," bywa trescia, nie artefaktem."""
    probki = {
        "is": "Uss... — Pff, sagdi hann. Ahh, jaeja.",
        "ru": "Кхх... — Пфф, сказал он.",
        "fi": "Hmph... — Pyh, sanoi hän. Öhh, no niin.",
    }
    for kod, tekst in probki.items():
        wynik = cp.oczysc_tekst_tts(tekst, z_normalizacja=False, jezyk=kod)
        for slowo in tekst.replace("—", " ").replace(",", " ").split():
            rdzen = slowo.strip(".")
            if rdzen:
                assert rdzen in wynik, (kod, ascii(rdzen), ascii(wynik))


def test_g3_dokumentowany_rdzen_czyszczenia_dziala_dalej():
    """Markdown, gwiazdki i didaskalia okragle - to opisuja podreczniki."""
    wejscie = "## Scena\n*Anna* (szeptem) mowi.\n=== podkreslenie ==="
    wynik = cp.oczysc_tekst_tts(wejscie, z_normalizacja=False)
    assert "#" not in wynik and "*" not in wynik and "=" not in wynik, ascii(wynik)
    assert "szeptem" not in wynik, ascii(wynik)
    assert "Anna" in wynik and "Scena" in wynik, ascii(wynik)


if __name__ == "__main__":
    testy = [(nazwa, obiekt) for nazwa, obiekt in sorted(globals().items())
             if nazwa.startswith("test_") and callable(obiekt)]
    bledy = []
    for nazwa, funkcja in testy:
        try:
            funkcja()
            print(f"  OK   {nazwa}")
        except AssertionError as exc:
            bledy.append(nazwa)
            print(f"  FAIL {nazwa}: {exc}")
    print(f"\n{len(testy) - len(bledy)}/{len(testy)} zaliczonych.")
    sys.exit(1 if bledy else 0)
