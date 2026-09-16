"""
test_tytul_screen_readera.py - <title> wersji dla czytnikow ekranu pochodzi
Z PACZKI jezyka TRESCI, nie z kodu (19.3.1).

Do v19.3.0 `core_screen_reader._szablon` sklejal tytul dokumentu z zaszytego
polskiego sufiksu („wersja dla czytnikow ekranu"), a `audyt_leakow --bramka-py`
mial ten literal W BASELINE jako przeciek zaakceptowany. Tryb porazki byl wiec
cichy i dotyczyl artefaktu UZYTKOWNIKA: finski projekt dostawal dokument,
ktory w jednej linijce deklarowal `<html lang="fi">`, a w nastepnej mowil po
polsku - czytnik ekranu czytal ten tytul finskim glosem.

Niezmiennik pilnowany tutaj jest wezszy niz „nie ma polskich znakow" (na to
bramka baseline'owa juz raz powiedziala „czysto"): tytul MUSI byc identyczny
z wartoscia `rezyser.sr_html_tytul` z paczki jezyka tresci, a polski sufiks
NIE MOZE pojawic sie w dokumencie zadnego innego jezyka.

Uruchom:  .venv/Scripts/python test_tytul_screen_readera.py
"""

import html as _html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import core_screen_reader as csr
import i18n

KLUCZ = "rezyser.sr_html_tytul"
SKRYPT = "[Olaf] Dialogue line."
PROJEKT = "Hamlet"

_RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S)


def _tytul(kod: str, tytul: str = PROJEKT) -> str:
    """Zwraca zawartosc <title> dokumentu wygenerowanego dla paczki `kod`."""
    html = csr.generuj_html(SKRYPT, "", jezyk_projektu=kod, tytul=tytul)
    trafienia = _RE_TITLE.findall(html)
    assert len(trafienia) == 1, f"{kod}: oczekiwano jednego <title>, jest {len(trafienia)}"
    return trafienia[0]


def test_kazda_paczka_ma_klucz():
    """Zaden zainstalowany jezyk nie oddaje placeholdera `[klucz]` w <title>."""
    paczki = i18n.dostepne_jezyki_ui()
    assert paczki, "brak jakiejkolwiek paczki ui.yaml - test nie ma przedmiotu"
    for kod in paczki:
        tytul = _tytul(kod)
        assert f"[{KLUCZ}]" not in tytul, (
            f"{kod}: brak klucza {KLUCZ} w paczce - <title> to placeholder"
        )
        assert PROJEKT in tytul, f"{kod}: nazwa projektu wypadla z <title> ({tytul!r})"


def test_tytul_jest_wartoscia_z_paczki():
    """Tytul = `sr_html_tytul` tej paczki, przepuszczony przez `html.escape`.

    Porownanie idzie do wartosci ESCAPOWANEJ, a nie do surowej, bo pinuje dwie
    rzeczy naraz: zrodlo napisu (paczka, nie kod) oraz to, ze napis wchodzi do
    dokumentu przez `html.escape`. Nie jest to teoria - paczka `fr` ma w tym
    kluczu apostrof („lecteurs d'ecran"), wiec w dokumencie stoi `&#x27;`.
    Gdyby escapowanie wypadlo, nazwa projektu z `<` albo `&` psulaby HTML.
    """
    for kod in i18n.dostepne_jezyki_ui():
        oczekiwany = i18n.t(KLUCZ, jezyk_override=kod, nazwa_projektu=PROJEKT)
        assert _tytul(kod) == _html.escape(oczekiwany), (
            f"{kod}: <title> rozjechany z paczka - kod cos dokleja albo nie escapuje"
        )


def test_nazwa_projektu_jest_escapowana():
    """Nazwa projektu z metaznakiem HTML nie wychodzi do dokumentu surowa."""
    tytul = _tytul("pl", tytul='Akt <b>I</b> & "final"')
    assert "<b>" not in tytul, f"surowy tag w <title>: {tytul!r}"
    assert "&lt;b&gt;" in tytul and "&amp;" in tytul, f"brak escapowania: {tytul!r}"


def test_polski_sufiks_nie_wchodzi_do_obcych_paczek():
    """Sufiks PL nie pojawia sie w dokumencie zadnego innego jezyka.

    Sufiks czytamy Z PACZKI pl (pusta nazwa projektu), zeby ten plik nie
    musial go powtarzac jako wlasnego literalu - powtorka rozjechalaby sie
    z paczka przy pierwszej redakcji tekstu.
    """
    sufiks_pl = i18n.t(KLUCZ, jezyk_override="pl", nazwa_projektu="").strip()
    assert len(sufiks_pl) > 10, f"sufiks PL podejrzanie krotki: {sufiks_pl!r}"
    for kod in i18n.dostepne_jezyki_ui():
        if kod == "pl":
            continue
        tytul = _tytul(kod)
        assert sufiks_pl not in tytul, (
            f"{kod}: polski sufiks w dokumencie o lang={kod} ({tytul!r})"
        )


def test_dziesiaty_jezyk_bez_dotykania_pythona():
    """Paczka-atrapa `sv` rzadzi tytulem; w kodzie nie ma zadnego sufiksu.

    Szwedzkiego w repo NIE MA - wlasnie o to chodzi. Gdyby ktos kiedykolwiek
    wrocil do sklejania tytulu w Pythonie, ten test zlapie to natychmiast,
    bo napis atrapy nie moze powstac inaczej niz przez odczyt z paczki.
    """
    stare_t = i18n.t
    stare_jezyki = i18n.dostepne_jezyki_ui
    NAPIS = "{nazwa_projektu} - version for skarmlasare"
    try:
        i18n.dostepne_jezyki_ui = lambda: ["sv"]
        i18n.t = lambda klucz, *, jezyk_override=None, **kw: (
            NAPIS.format(**kw) if (klucz == KLUCZ and jezyk_override == "sv")
            else f"[{klucz}]"
        )
        assert _tytul("sv") == NAPIS.format(nazwa_projektu=PROJEKT)
    finally:
        i18n.t = stare_t
        i18n.dostepne_jezyki_ui = stare_jezyki
        i18n.wyczysc_cache()


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
