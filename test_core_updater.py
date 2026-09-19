"""
test_core_updater.py - Testy bez GUI dla modulu core_updater.

Uruchom:  .venv/Scripts/python -m pytest test_core_updater.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_core_updater.py
Opcjonalnie z tokenem: GITHUB_TOKEN=ghp_... (repo jest publiczne, wiec token
jest tylko podniesieniem limitu 60 zapytan/h).

HISTORIA TEGO PLIKU, bo to lekcja, nie ciekawostka (v19.2.1): do tej wersji
wszystkie cztery funkcje ZWRACALY bool zamiast asertowac — wzorzec z czasow, gdy
plik byl skryptem z wlasnym `__main__`-harnessem sumujacym wyniki. Pod pytestem
wartosc zwracana jest IGNOROWANA, wiec kazdy z tych testow przechodzil ZAWSZE,
takze gdy sprawdzana rzecz byla zepsuta. Pytest 9 zglasza to jako
`PytestReturnNotNoneWarning`. Wniosek do powtarzania: test, ktory nie ma jak
zawiesc, jest gorszy od braku testu — brak testu widac w spisie, a zielony pusty
przebieg uczy, ze obszar jest pokryty.

Testy sieciowe SKIPUJA sie przy braku laczności, zamiast przechodzic na zielono.
Skip jest widoczny w podsumowaniu pytesta, "pass" nie da sie odroznic od realnej
weryfikacji.
"""

import os
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_updater as cu

# Odczyt tokenu ze srodowiska — None jesli nie ustawiony (repo publiczne)
TOKEN = os.environ.get("GITHUB_TOKEN") or None

# Bledy, ktore znacza "nie ma sieci / API nie odpowiada", a nie "nasz kod jest zly".
BLEDY_SIECI = (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError)


# ---------------------------------------------------------------------------
# 1. Testy jednostkowe _normalizuj_wersje (czysto lokalne, bez sieci)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("wejscie, oczekiwane", [
    ("13.4",     (13, 4, 0)),
    ("v13.4.1",  (13, 4, 1)),
    ("13.5-WIP", (13, 5, 0)),
    ("v2.0",     (2,  0, 0)),
    ("1.2.3",    (1,  2, 3)),
])
def test_normalizuj(wejscie, oczekiwane):
    assert cu._normalizuj_wersje(wejscie) == oczekiwane


# ---------------------------------------------------------------------------
# 2. Odczyt pliku VERSION
# ---------------------------------------------------------------------------

def test_odczyt_version():
    """VERSION musi dac sie odczytac i znormalizowac.

    Dawna wersja lapala `Exception` i zwracala False — czyli brak pliku VERSION
    konczyl sie zielonym testem. Tutaj wyjatek MA wyleciec: to jedyny plik,
    z ktorego bierze sie numer wersji w calym projekcie.
    """
    wersja = cu._odczytaj_wersje_lokalna()
    assert isinstance(wersja, str) and wersja.strip(), f"VERSION puste: {wersja!r}"
    numer = cu._normalizuj_wersje(wersja)
    assert len(numer) == 3 and all(isinstance(c, int) for c in numer), numer
    assert numer != (0, 0, 0), f"VERSION {wersja!r} znormalizowalo sie do zera"


# ---------------------------------------------------------------------------
# 3. Zapytanie do GitHub API (wymaga internetu — przy braku SKIP, nie pass)
# ---------------------------------------------------------------------------

def test_github_api():
    try:
        dane = cu._pobierz_json_api(cu._API_URL, token=TOKEN)
    except BLEDY_SIECI as exc:
        pytest.skip(f"GitHub API nieosiagalne ({type(exc).__name__}: {exc})")

    # Od v19.5 odpytujemy LISTE wydan, nie `releases/latest`: changelog ma
    # obejmowac takze wydania pominiete przez uzytkownika.
    assert isinstance(dane, list), type(dane)
    assert dane, "API zwrocilo pusta liste wydan"

    wydania = cu._wydania_publiczne(dane)
    assert wydania, "po odsianiu szkicow i pre-release'ow nie zostalo nic"

    # Sortowanie MALEJACE po numerze wersji — na tym stoi wybor celu.
    numery = [cu._normalizuj_wersje(str(w["tag_name"])) for w in wydania]
    assert numery == sorted(numery, reverse=True), numery

    najnowsze = wydania[0]
    tag = najnowsze.get("tag_name")
    assert tag, f"wydanie bez `tag_name`: {sorted(najnowsze)[:10]}"
    assert cu._normalizuj_wersje(tag) != (0, 0, 0), f"tag nie parsuje sie: {tag!r}"

    # Wydanie MUSI miec instalator i jego sume — updater weryfikuje nia pobranie
    # (od v18.10), a bez sumy weryfikacja SHA256 jest po cichu pomijana.
    nazwy = [a.get("name", "") for a in najnowsze.get("assets", [])]
    assert any(n.endswith(".exe") for n in nazwy), f"brak assetu .exe: {nazwy}"
    assert any(n.endswith(".exe.sha256") for n in nazwy), f"brak sumy .sha256: {nazwy}"


# ---------------------------------------------------------------------------
# 3b. Agregacja changelogu — wydanie POMINIETE tez musi sie policzyc (v19.5)
# ---------------------------------------------------------------------------
# Te testy sa OFFLINE i syntetyczne: karmimy helpery ksztaltem odpowiedzi API,
# bo mierzona wlasnosc jest regula sklejania, a nie stanem repozytorium.

def _wydanie(tag, body, *, draft=False, prerelease=False, exe=True):
    assets = []
    if exe:
        assets = [
            {"name": f"Rezyser_Audio_{tag.lstrip('v')}_Installer.exe",
             "browser_download_url": f"https://example.invalid/{tag}.exe",
             "size": 123},
            {"name": f"Rezyser_Audio_{tag.lstrip('v')}_Installer.exe.sha256",
             "browser_download_url": f"https://example.invalid/{tag}.exe.sha256",
             "size": 103},
        ]
    return {"tag_name": tag, "body": body, "draft": draft,
            "prerelease": prerelease, "assets": assets,
            "html_url": f"https://example.invalid/tag/{tag}",
            "zipball_url": f"https://example.invalid/zip/{tag}"}


def test_changelog_obejmuje_wydanie_pominiete():
    """Uzytkownik 19.4.0 widzi TAKZE sekcje 19.4.1, nie tylko 19.4.2.

    To jest cala usterka zamknieta w v19.5: `releases/latest` zwracal jedno
    wydanie, wiec o poprawkach wydania posredniego nikt sie nie dowiadywal.
    """
    wydania = cu._wydania_publiczne([
        _wydanie("v19.4.1", "## 19.4.1 — patch\nDruga rzecz."),
        _wydanie("v19.4.2", "## 19.4.2 — patch\nPierwsza rzecz."),
        _wydanie("v19.4.0", "## 19.4.0 — minor\nJUZ ZAINSTALOWANE."),
    ])
    sklejony = cu._sklej_changelog(wydania, "19.4.0")

    assert "## 19.4.2" in sklejony, sklejony
    assert "## 19.4.1" in sklejony, sklejony
    assert "JUZ ZAINSTALOWANE" not in sklejony, "wlasna wersja nie nalezy do changelogu"
    # Kolejnosc: najnowsze na gorze.
    assert sklejony.index("## 19.4.2") < sklejony.index("## 19.4.1")
    assert "---" in sklejony, "brak separatora miedzy sekcjami"


def test_changelog_pusty_gdy_nie_ma_nic_nowszego():
    wydania = cu._wydania_publiczne([_wydanie("v19.4.2", "## 19.4.2 — patch\nX.")])
    assert cu._sklej_changelog(wydania, "19.4.2") == ""
    assert cu._sklej_changelog(wydania, "19.5.0") == ""


def test_szkice_i_prerelease_nie_wchodza_do_wyboru_celu():
    """Draft i pre-release nie sa wydaniem dla end-usera — ani celem, ani trescia."""
    wydania = cu._wydania_publiczne([
        _wydanie("v20.0.0", "## 20.0.0 — draft", draft=True),
        _wydanie("v19.9.9", "## 19.9.9 — rc", prerelease=True),
        _wydanie("v19.4.2", "## 19.4.2 — patch\nRealne."),
        _wydanie("nie-wersja", "## cos\nTag spoza workflow."),
    ])
    assert [w["tag_name"] for w in wydania] == ["v19.4.2"]
    sklejony = cu._sklej_changelog(wydania, "19.4.0")
    assert "20.0.0" not in sklejony and "19.9.9" not in sklejony, sklejony


def test_cel_to_najwyzszy_numer_a_nie_najswiezsza_data():
    """Hotfix wydany pozniej, a numerowany nizej, nie moze wygrac z nowszym.

    `releases/latest` GitHuba wybiera po `created_at`, wiec taki uklad kazalby
    updaterowi zaproponowac COFNIECIE wersji. My sortujemy po numerze.
    """
    wydania = cu._wydania_publiczne([
        _wydanie("v18.9.1", "## 18.9.1 — hotfix starej linii"),
        _wydanie("v19.4.2", "## 19.4.2 — patch"),
    ])
    assert wydania[0]["tag_name"] == "v19.4.2"


# ---------------------------------------------------------------------------
# 4. Pelny przeplyw: sprawdz_aktualizacje()
# ---------------------------------------------------------------------------

def test_sprawdz_aktualizacje():
    """Kontrakt: albo None (brak nowszego wydania), albo KOMPLETNY UpdateInfo.

    Dawna wersja konczyla sie `return True` w OBU galeziach, wiec nie sprawdzala
    niczego poza tym, ze funkcja nie rzuca. Tu wariant "jest aktualizacja" musi
    dowiezc wszystkie pola, ktorych dialog updatera faktycznie uzywa — pusty
    `url_instalatora` albo zerowy rozmiar to defekt, a nie "brak aktualizacji".
    """
    try:
        wynik = cu.sprawdz_aktualizacje(token=TOKEN)
    except BLEDY_SIECI as exc:
        pytest.skip(f"GitHub API nieosiagalne ({type(exc).__name__}: {exc})")

    if wynik is None:
        # Brak nowszego wydania jest poprawnym wynikiem — ale wtedy lokalna
        # wersja musi byc odczytywalna, inaczej None znaczylo by co innego.
        assert cu._odczytaj_wersje_lokalna().strip()
        return

    assert wynik.tag and wynik.wersja, (wynik.tag, wynik.wersja)
    assert wynik.nazwa_pliku.endswith(".exe"), wynik.nazwa_pliku
    assert wynik.url_instalatora.startswith("https://"), wynik.url_instalatora
    assert wynik.rozmiar_bajtow > 0, wynik.rozmiar_bajtow
    # Nowsza niz lokalna — inaczej `sprawdz_aktualizacje` nie powinno jej zwrocic.
    assert (cu._normalizuj_wersje(wynik.wersja)
            > cu._normalizuj_wersje(cu._odczytaj_wersje_lokalna()))


# ---------------------------------------------------------------------------
# 5. Kontrakt TRESCI: noty o jezyku changelogu i strony wydania
# ---------------------------------------------------------------------------
# Klasa dlugu domknieta w v19.4.1 (otwarta v19.4.0): dwa stringi runtime'u
# opisywaly zachowanie, ktore przestalo istniec. `updater.changelog_uwaga`
# mowil „Jest po angielsku i polsku", a `updater.co_nowego_online_pl` — „strona
# wydania jest dostepna po polsku". Obie obietnice przestaly byc prawdziwe
# w chwili, gdy sekcja `RELEASE_NOTES.md` stracila polska diagnostyke, bo
# in-app „Co nowego" od v17.11 pokazuje ZYWE body Release. Zaden przeglad
# tlumaczen tego nie lapal: stringi byly poprawnie przetlumaczone we wszystkich
# dziewieciu paczkach — falszywe bylo ZDANIE, a jego prawdziwosc mieszka POZA
# paczka, w kanonie `RELEASE_NOTES.md`. Dlatego bramka stoi po obu stronach:
# sprawdza noty w paczkach ORAZ kanon, ktory je uprawdziwia.

_DICT_UI = Path(__file__).parent / "dictionaries"

# Mapy kuratorskie: slowo „polski" i slowo „angielski" w jezyku KAZDEJ paczki.
# Dziesiaty jezyk projektu dopisze tu dwa slowa — i o tym, ze musi, dowie sie
# z tego testu, nie od uzytkownika (wzorzec z `test_manager_kontrakt.py`).
_SLOWO_POLSKI = {
    "pl": "polsk", "en": "polish", "de": "polnisch", "es": "polac",
    "fi": "puola", "fr": "polon", "is": "pólsk", "it": "polacc",
    "ru": "польск",
}
_SLOWO_ANGIELSKI = {
    "pl": "angielsk", "en": "english", "de": "englisch", "es": "ingl",
    "fi": "englan", "fr": "anglais", "is": "ensku", "it": "ingles",
    "ru": "английск",
}

# Naglowki porzuconej polskiej diagnostyki. Obecnosc ktoregokolwiek w sekcji
# BIEZACEJ wersji znaczy, ze body Release znow nie jest samo angielskie — a wtedy
# klamia noty, nie plik.
_NAGLOWKI_PL = ("### TL;DR", "### Co nowego", "### Pod maska", "### Pod maską",
                "### Co nie weszlo", "### Co nie weszło", "### Walidacja")

_KLUCZE_NOT = ("updater.changelog_uwaga", "updater.co_nowego_online_uwaga")


def _kody_paczek():
    return sorted(k.name for k in _DICT_UI.iterdir()
                  if (k / "gui" / "ui.yaml").is_file())


def test_noty_o_jezyku_maja_klucze_pod_NOWA_nazwa():
    """`co_nowego_online_uwaga` w kazdej paczce, `..._pl` w zadnej.

    Przemianowanie w v19.4.1: sufiks `_pl` opisywal JEZYK TRESCI, a nie rzecz,
    ktora klucz nazywa, wiec starzal sie razem z kanonem. Polowiczne
    przemianowanie degraduje CICHO — kod pyta o nowy klucz, paczka ma stary,
    `i18n.t` oddaje „[updater.co_nowego_online_uwaga]" i tyle widzi user.
    """
    import i18n
    braki = []
    for kod in _kody_paczek():
        i18n.ustaw_jezyk(kod)
        for klucz in _KLUCZE_NOT:
            if i18n.t(klucz).startswith("["):
                braki.append(f"{kod}: brak klucza {klucz}")
        if not i18n.t("updater.co_nowego_online_pl").startswith("["):
            braki.append(f"{kod}: zostal PRZEDAWNIONY klucz "
                         f"updater.co_nowego_online_pl (przemianowany w v19.4.1)")
    i18n.ustaw_jezyk("pl")
    assert not braki, "\n".join(braki)


def test_noty_o_jezyku_nie_obiecuja_polskiego():
    """Obie noty nazywaja angielski i ZADNA nie nazywa polskiego.

    Mechanicznie sprawdzalne jest tu dokladnie jedno: czy zdanie nazywa jezyk,
    ktorego w tresci nie ma. Obietnica pozytywna jest w tej samej petli, bo
    nota bez zadnej nazwy jezyka jest rownie bezuzyteczna dla nie-EN usera —
    po to te dwa stringi istnieja.
    """
    import i18n
    braki = []
    for kod in _kody_paczek():
        assert kod in _SLOWO_POLSKI and kod in _SLOWO_ANGIELSKI, (
            f"{kod}: dopisz slowa „polski\" i „angielski\" w tym jezyku "
            f"do map tego testu")
        i18n.ustaw_jezyk(kod)
        for klucz in _KLUCZE_NOT:
            tekst = i18n.t(klucz).lower()
            if _SLOWO_POLSKI[kod] in tekst:
                braki.append(f"{kod}/{klucz}: nota nadal obiecuje polski "
                             f"(znaleziono „{_SLOWO_POLSKI[kod]}\")")
            if _SLOWO_ANGIELSKI[kod] not in tekst:
                braki.append(f"{kod}/{klucz}: nota nie nazywa angielskiego "
                             f"(szukano „{_SLOWO_ANGIELSKI[kod]}\")")
    i18n.ustaw_jezyk("pl")
    assert not braki, "\n".join(braki)


def test_sekcja_biezacego_wydania_jest_bez_polskiej_diagnostyki():
    """Kanon, ktory uprawdziwia noty wyzej: body Release = samo angielskie.

    Body Release to CALA sekcja `## <wersja>` z RELEASE_NOTES.md (wycinana tym
    samym ekstraktorem, ktorego uzywa `draft-release.yml`), zapisywana przez
    dialog do `docs/changelog.md`. Powrot polskiej diagnostyki do sekcji
    biezacej wersji nie jest wiec kosmetyka: uniewaznia dwa stringi w dziewieciu
    paczkach, ktorych ta sekcja nawet nie widzi.
    """
    sys.path.insert(0, str(Path(__file__).parent / ".github" / "scripts"))
    import release_notes_sekcja as rns

    wersja = cu._odczytaj_wersje_lokalna().strip().lstrip("v")
    tresc = (Path(__file__).parent / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    try:
        sekcja = rns.wytnij_sekcje(tresc, wersja)
    except rns.BladSekcji as exc:
        pytest.skip(f"RELEASE_NOTES.md nie ma jeszcze sekcji {wersja} ({exc})")

    trafienia = [n for n in _NAGLOWKI_PL if n in sekcja]
    assert not trafienia, (
        f"sekcja {wersja} ma naglowki porzuconej polskiej diagnostyki "
        f"{trafienia} — body Release nie jest samo angielskie, wiec "
        f"`updater.changelog_uwaga` i `updater.co_nowego_online_uwaga` "
        f"w 9 paczkach klamia (patrz v19.4.0 i v19.4.1)")


# ---------------------------------------------------------------------------
# Uruchomienie jako skrypt — deleguje do pytesta.
# ---------------------------------------------------------------------------
# Wlasny harness sumujacy bool-e byl dokladnie tym, co zepsulo te testy pod
# pytestem (dwa sposoby raportowania wyniku, z czego jeden cichy). Jeden
# mechanizm, jedno raportowanie.

if __name__ == "__main__":
    if TOKEN:
        print(f"GITHUB_TOKEN ustawiony (pierwsze 8 znakow: {TOKEN[:8]}...)")
    else:
        print("GITHUB_TOKEN nie ustawiony — zakladam repo publiczne.")
    sys.exit(pytest.main([__file__, "-v"]))
