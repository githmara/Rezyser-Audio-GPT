"""
test_cache_powtorki.py - Regresja: cache wznawiania NIGDY nie udaje pracy,
ktorej nie bylo (18.30.1).

Cztery kontrakty, wszystkie zmierzone przez WYKONANIE (stub `core_llm.wywolaj_llm`,
zero sieci, `runtime/` w katalogu tymczasowym):

  1. POWTORKA sekcji docs (`buduj_wielojezyczne_docs`) musi realnie dojechac do
     modelu. Sekcje ida z `zachowaj_cache=True`, wiec dopoki cache odrzuconej
     proby jest UZYWALNY, silnik odzyskuje z niego wszystkie bloki, doklejka
     nacisku nie trafia do modelu, a „powtorka" oddaje bajt w bajt te sama,
     zakwestionowana tresc. Uniewaznienie cache'u jest wiec WARUNKIEM powtorki,
     nie sprzataniem - a jego porazka nie ma prawa skonczyc sie logiem
     „still rejected after the retry".
  2. `uniewaznij_cache_tlumaczenia` uniewaznia po TRESCI, nie po istnieniu pliku:
     gdy `os.remove` pada (Windows: dowolny otwarty uchwyt = ERROR_SHARING_
     VIOLATION), plik zostaje obciety do zera bajtow i tym samym przestaje byc
     cache'em. Napis z powodem wraca tylko wtedy, gdy nie udalo sie NIC.
  3. Silnik (`tlumacz_ai`) po odrzuceniu niezgodnego cache'u zapisuje nowa
     metryke ZAWSZE - nadpisaniem w miejscu. Dawna para „skasuj + utworz, jesli
     brak" przy nieudanym kasowaniu zostawiala stara metryke i dopisywala bloki
     pod nia: cache stawal sie trwale nieuzywalny, a user placil za te bloki
     przy kazdym wznowieniu, bez slowa w logu.
  4. ODCISK ZRODLA w metryce (18.31): cache o zgodnym podziale, ale z INNEJ
     tresci zrodla, jest odrzucany - inaczej edycja pliku miedzy przebiegami
     oddawala POPRZEDNI przeklad, o ile nie zmienila liczby blokow. Druga
     polowa tego kontraktu jest rownie wazna: metryka BEZ pola `zrodlo` (plik
     sprzed 18.31) musi byc TOLEROWANA, bo inaczej aktualizacja aplikacji
     uniewaznia cache komus w polowie platnego tlumaczenia.

Uruchom:  .venv/Scripts/python test_cache_powtorki.py
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import yaml

import core_llm as cl
import tlumacz_ai
import buduj_wielojezyczne_docs as bd

KOD = "fi"
NAZWA_PL = "finski"
RDZEN = "test_cache_powtorki"
NAGLOWEK_NACISKU = "RETRY — YOUR PREVIOUS TRANSLATION"
DICT_DIR = Path(__file__).parent / "dictionaries"

# Zrodlo MUSI miec >= 200 znakow (`tlumacz_bramki.stosunek_dlugosci` ponizej
# progu nie liczy ilorazu) i co najmniej jeden placeholder - wtedy sekcja idzie
# z prefiks-instrukcja, dokladnie jak w realnym przebiegu.
TRESC_PL = (
    "Projekt {nazwa_projektu} liczy {liczba_znakow} znakow.\n"
    "To zdanie zrodla istnieje, zeby sekcja miala ponad dwiescie znakow, bo\n"
    "ponizej tego progu bramka stosunku dlugosci celowo nie liczy ilorazu.\n"
    "Trzecie zdanie dosypuje jeszcze kilkadziesiat znakow zwyklej prozy.\n"
)
DOSYPKA = " Lisaa tekstia ilman markkereita." * 12   # -> iloraz > PROG_ROZDMUCHANIA

_licznik = {"blok": 0, "iso": 0}
_prompty: list[str] = []


def _stub_llm(klient, *, model, system, messages, max_tokens, temperature,
              timeout, segmenty=None, wymusz_json=False, thinking_budget=0,
              schema_json=None, slad=None):
    """Model, ktory zawsze rozdmuchuje sekcje (parzystosc markerow zachowana)."""
    tresc_user = messages[0]["content"]
    if "BCP-47" in tresc_user:
        _licznik["iso"] += 1
        return "fi", "end_turn"
    _licznik["blok"] += 1
    _prompty.append(system)
    return tresc_user + DOSYPKA, "end_turn"


@contextlib.contextmanager
def _srodowisko():
    """Stub LLM + `RUNTIME_DIR` w katalogu tymczasowym (zero sieci, zero smieci)."""
    katalog = tempfile.mkdtemp()
    stary_runtime, stary_llm = bd.RUNTIME_DIR, cl.wywolaj_llm
    bd.RUNTIME_DIR = Path(katalog)
    cl.wywolaj_llm = _stub_llm
    _licznik["blok"] = _licznik["iso"] = 0
    _prompty.clear()
    try:
        yield Path(katalog)
    finally:
        bd.RUNTIME_DIR, cl.wywolaj_llm = stary_runtime, stary_llm
        shutil.rmtree(katalog, ignore_errors=True)


def _sciezka_cache() -> str:
    return bd.sciezka_cache_tlumaczenia(
        str(bd.RUNTIME_DIR), bd._cache_key_sekcji(RDZEN, bd.KLUCZ_LEGACY, KOD),
        NAZWA_PL)


def _blok_zrodla() -> str:
    """Jedyny blok, na jaki dzieli sie sekcja testowa (sanity: naprawde jeden)."""
    tresc_tok, _mapa = bd.tokenizuj(TRESC_PL)
    bloki = tlumacz_ai._podziel_na_bloki(
        bd.PREFIX_INSTRUKCJA + tresc_tok, max_tokenow=2_500,
        model=tlumacz_ai._MODEL_TOKENIZER)
    assert len(bloki) == 1, f"oczekiwano jednego bloku, jest {len(bloki)}"
    return bloki[0]


def _payload_sekcji() -> str:
    """Tresc, jaka builder REALNIE podaje silnikowi (prefiks + stokenizowana)."""
    tresc_tok, _mapa = bd.tokenizuj(TRESC_PL)
    return bd.PREFIX_INSTRUKCJA + tresc_tok


def _odcisk_sekcji() -> str:
    return tlumacz_ai._odcisk_zrodla(_payload_sekcji())


def _zasiej_cache(*, bloki_w_metryce: int = 1) -> str:
    """Cache jak po nieudanym poprzednim przebiegu: jeden blok, tresc odrzucona."""
    sciezka = _sciezka_cache()
    with open(sciezka, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"meta": tlumacz_ai._WERSJA_CHUNKOWANIA,
                             "bloki": bloki_w_metryce}) + "\n")
        fh.write(json.dumps({"id": 0, "text": _blok_zrodla() + DOSYPKA},
                            ensure_ascii=False) + "\n")
    return sciezka


def _wiersze_cache(sciezka: str) -> list[dict]:
    with open(sciezka, "r", encoding="utf-8") as fh:
        return [json.loads(linia) for linia in fh if linia.strip()]


def _przebieg() -> tuple[bool, str]:
    """Jedna sekcja przez pelny `_tlumacz_pojedyncza_sekcje`. Zwraca (ok, log)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        ok, _tresc = bd._tlumacz_pojedyncza_sekcje(
            KOD, NAZWA_PL, None, "test.yaml", RDZEN, bd.KLUCZ_LEGACY, TRESC_PL,
            dry_run=False, model="stub", prompt_dodatkowy="")
    return ok, buf.getvalue()


def _z_naciskiem() -> int:
    return sum(1 for p in _prompty if NAGLOWEK_NACISKU in p)


def _czy_kasowanie_pada(sciezka: str) -> bool:
    """Czy ten system blokuje `os.remove` na otwartym pliku (Windows: tak)."""
    try:
        os.remove(sciezka)
        return False
    except OSError:
        return True


# ---------------------------------------------------------------------------
# 1. Powtorka realnie dociera do modelu
# ---------------------------------------------------------------------------
def test_powtorka_dostaje_nacisk():
    """Bez cache'u na wejsciu: dwie realne proby, druga z blokiem nacisku."""
    with _srodowisko():
        ok, log = _przebieg()
        assert ok is False, "rozdmuchana sekcja musi zostac odrzucona"
        assert _licznik["blok"] == 2, _licznik
        assert _z_naciskiem() == 1, _prompty
        assert "still rejected after the retry" in log, log


def test_zasiany_cache_nie_zabiera_powtorki():
    """Cache z poprzedniego (nieudanego) przebiegu jest uniewazniany."""
    with _srodowisko():
        _zasiej_cache()
        ok, log = _przebieg()
        assert ok is False, log
        # Proba 1 = darmowe wznowienie odrzuconej tresci (0 callow), powtorka
        # = jedno realne wywolanie, z naciskiem.
        assert _licznik["blok"] == 1, _licznik
        assert _z_naciskiem() == 1, _prompty


def test_zajety_cache_nie_zabiera_powtorki():
    """`os.remove` pada (otwarty uchwyt), a powtorka i tak jest REALNA.

    Obciecie pliku przechodzi tam, gdzie kasowanie pada, wiec Windowsowy
    ERROR_SHARING_VIOLATION (antywirus, edytor) przestal kosztowac powtorke.
    """
    with _srodowisko():
        sciezka = _zasiej_cache()
        with open(sciezka, "r", encoding="utf-8") as uchwyt:
            if not _czy_kasowanie_pada(sciezka):
                print("   (pominieto: ten system pozwala usunac otwarty plik)")
                return
            assert uchwyt.readable()
            ok, log = _przebieg()
            assert ok is False, log
            assert _licznik["blok"] == 1, _licznik
            assert _z_naciskiem() == 1, _prompty
            assert "the retry CANNOT run" not in log, log
            # Silnik zapisal nowa metryke NADPISANIEM w miejscu, wiec cache
            # powtorki jest uzywalny dla nastepnego przebiegu.
            wiersze = _wiersze_cache(sciezka)
            assert wiersze[0] == {"meta": tlumacz_ai._WERSJA_CHUNKOWANIA,
                                  "bloki": 1,
                                  "zrodlo": _odcisk_sekcji()}, wiersze[0]
            assert [w["id"] for w in wiersze[1:]] == [0], wiersze


def test_nieuniewazniony_cache_zatrzymuje_powtorke():
    """Gdy nie da sie NIC: powtorka nie startuje i log tego nie ukrywa."""
    with _srodowisko():
        _zasiej_cache()
        stary = bd.uniewaznij_cache_tlumaczenia
        bd.uniewaznij_cache_tlumaczenia = (
            lambda _s: "remove: PermissionError: symulacja")
        try:
            ok, log = _przebieg()
        finally:
            bd.uniewaznij_cache_tlumaczenia = stary
        assert ok is False, log
        assert "the retry CANNOT run" in log, log
        # Kluczowe: NIE wolno zameldowac powtorki, ktorej nie bylo.
        assert "still rejected after the retry" not in log, log
        assert _z_naciskiem() == 0, _prompty
        assert "symulacja" in log, log


# ---------------------------------------------------------------------------
# 2. Sam uniewazniacz: po tresci, nie po istnieniu pliku
# ---------------------------------------------------------------------------
def test_uniewaznianie_zajetego_pliku_obcina():
    """Kasowanie pada -> plik obciety do zera, wynik `None` (cisza uzasadniona)."""
    katalog = tempfile.mkdtemp()
    try:
        sciezka = os.path.join(katalog, "temp_zajety.jsonl")
        with open(sciezka, "w", encoding="utf-8") as fh:
            fh.write('{"meta": 2, "bloki": 1}\n{"id": 0, "text": "stare"}\n')
        with open(sciezka, "r", encoding="utf-8") as uchwyt:
            if not _czy_kasowanie_pada(sciezka):
                print("   (pominieto: ten system pozwala usunac otwarty plik)")
                return
            assert uchwyt.readable()
            assert tlumacz_ai.uniewaznij_cache_tlumaczenia(sciezka) is None
            assert os.path.getsize(sciezka) == 0, "plik mial zostac obciety"
    finally:
        shutil.rmtree(katalog, ignore_errors=True)


def test_uniewaznianie_braku_pliku_milczy():
    """Brak pliku to normalny stan (proba 1 padla przed zapisem bloku)."""
    katalog = tempfile.mkdtemp()
    try:
        brak = os.path.join(katalog, "temp_nie_ma.jsonl")
        assert tlumacz_ai.uniewaznij_cache_tlumaczenia(brak) is None
    finally:
        shutil.rmtree(katalog, ignore_errors=True)


def test_uniewaznianie_niemozliwe_zwraca_powod():
    """Ani skasowac, ani obciac -> napis nazywajacy OBIE porazki.

    Katalog pod sciezka cache'u jest tu wehikulem dla klasy „system nie oddaje
    tego pliku" (ACL bez prawa DELETE, nosnik read-only): `os.remove` i
    `open(..., "w")` padaja oba, tak jak w tych przypadkach.
    """
    katalog = tempfile.mkdtemp()
    try:
        przeszkoda = os.path.join(katalog, "temp_katalog.jsonl")
        os.makedirs(przeszkoda)
        powod = tlumacz_ai.uniewaznij_cache_tlumaczenia(przeszkoda)
        assert isinstance(powod, str) and powod, powod
        assert "remove:" in powod and "truncate:" in powod, powod
    finally:
        shutil.rmtree(katalog, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. Silnik: metryka zapisywana ZAWSZE, gdy nie wznawiamy
# ---------------------------------------------------------------------------
def test_niezgodna_metryka_nadpisuje_naglowek_w_miejscu():
    """Niezgodny cache + zajety plik -> nowa metryka i tak wchodzi do pliku.

    Bez tego cache zostawal ze stara metryka i bloki dopisywaly sie pod nia:
    kazde kolejne wznowienie odrzucalo plik i user placil za bloki ponownie.
    """
    with _srodowisko():
        sciezka = _zasiej_cache(bloki_w_metryce=99)     # metryka niezgodna
        with open(sciezka, "r", encoding="utf-8") as uchwyt:
            if not _czy_kasowanie_pada(sciezka):
                print("   (pominieto: ten system pozwala usunac otwarty plik)")
                return
            assert uchwyt.readable()
            wynik = tlumacz_ai.tlumacz_dlugi_tekst(
                tresc=TRESC_PL, jezyk_docelowy=NAZWA_PL, klient=None,
                runtime_dir=str(bd.RUNTIME_DIR),
                oryginalna_nazwa=bd._cache_key_sekcji(RDZEN, bd.KLUCZ_LEGACY, KOD),
                model_tlumacz="stub", zachowaj_cache=True)
        assert wynik is not None, "tlumaczenie nie moze padnac"
        wiersze = _wiersze_cache(sciezka)
        # Tu silnik wolany jest BEZPOSREDNIO, wiec zrodlem jest samo `TRESC_PL`
        # (bez prefiks-instrukcji, ktora doklada builder) — odcisk musi to znac.
        assert wiersze[0] == {"meta": tlumacz_ai._WERSJA_CHUNKOWANIA,
                              "bloki": 1,
                              "zrodlo": tlumacz_ai._odcisk_zrodla(TRESC_PL)},             wiersze[0]
        assert [w["id"] for w in wiersze[1:]] == [0], wiersze


def test_ostrzezenie_o_niezabranym_cache():
    """`zachowaj_cache=False` + nieudane uniewaznienie -> miekkie ostrzezenie."""
    with _srodowisko():
        miekkie: list = []
        stary = tlumacz_ai.uniewaznij_cache_tlumaczenia
        tlumacz_ai.uniewaznij_cache_tlumaczenia = (
            lambda _s: "remove: PermissionError: symulacja")
        try:
            wynik = tlumacz_ai.tlumacz_dlugi_tekst(
                tresc=TRESC_PL, jezyk_docelowy=NAZWA_PL, klient=None,
                runtime_dir=str(bd.RUNTIME_DIR), oryginalna_nazwa="ostrzezenie",
                model_tlumacz="stub", on_blad_miekki=miekkie.append)
        finally:
            tlumacz_ai.uniewaznij_cache_tlumaczenia = stary
        assert wynik is not None
        klucze = [i.klucz_i18n for i in miekkie]
        assert "ai_ostrzezenie_cache" in klucze, klucze
        info = next(i for i in miekkie if i.klucz_i18n == "ai_ostrzezenie_cache")
        assert info.klucz_tytul == "ai_ostrzezenie_cache_tytul", info
        assert set(info.kwargs) == {"plik", "szczegoly"}, info.kwargs
        # Techniczny slad musi zostac w wyniku (log / dialog szczegolow).
        assert any("resume-cache" in o for o in wynik.ostrzezenia), wynik.ostrzezenia


def test_klucze_ostrzezenia_w_kazdej_paczce():
    """Nowe klucze `poliglota.*` sa w KAZDEJ paczce (inaczej user widzi `[klucz]`)."""
    braki = {}
    for paczka in sorted(p for p in DICT_DIR.iterdir() if p.is_dir()):
        plik = paczka / "gui" / "ui.yaml"
        if not plik.is_file():
            continue
        # Bez `or {}` — pusty/zepsuty `ui.yaml` ma tu PADNAC, nie zniknac po
        # cichu (standard „zero ciszy", bramka `audyt_ciszy` klasa or-domyslny).
        dane = yaml.safe_load(plik.read_text(encoding="utf-8"))
        assert isinstance(dane, dict), f"{paczka.name}: ui.yaml nie jest mapa"
        poliglota = dane.get("poliglota")
        assert isinstance(poliglota, dict), f"{paczka.name}: brak sekcji poliglota"
        nieobecne = [k for k in ("ai_ostrzezenie_cache",
                                 "ai_ostrzezenie_cache_tytul")
                     if not str(poliglota.get(k, "")).strip()]
        if nieobecne:
            braki[paczka.name] = nieobecne
    assert not braki, braki


# ---------------------------------------------------------------------------
# 4. Odcisk zrodla w metryce (18.31)
# ---------------------------------------------------------------------------
# Cache'e w tym silniku przezywaja Z ZALOZENIA (przerwany przebieg zostawia
# oplacone bloki, `zachowaj_cache=True` trzyma je miedzy sekcjami), wiec te
# testy jada wlasnie tak: pierwszy przebieg ZOSTAWIA cache, drugi go zastaje.

TRESC_EDYTOWANA = TRESC_PL.replace("Trzecie zdanie", "Trzecie zdanko")


def _przebieg_silnika(katalog: str, tresc: str, nazwa: str = "odcisk"):
    """Jedno wywolanie silnika, cache zostawiony na dysku (jak w builderze)."""
    return tlumacz_ai.tlumacz_dlugi_tekst(
        tresc=tresc, jezyk_docelowy=NAZWA_PL, klient=None,
        runtime_dir=katalog, oryginalna_nazwa=nazwa,
        model_tlumacz="stub", zachowaj_cache=True)


def _sciezka_odcisku(katalog: str, nazwa: str = "odcisk") -> str:
    return tlumacz_ai.sciezka_cache_tlumaczenia(katalog, nazwa, NAZWA_PL)


def test_edytowane_zrodlo_nie_oddaje_starego_przekladu():
    """Edycja zrodla miedzy przebiegami MUSI trafic do modelu.

    Obie wersje daja te sama liczbe blokow (poprawka prozatorska), wiec do 18.31
    metryka „wersja + bloki" pasowala idealnie i drugi przebieg oddawal przeklad
    PIERWSZEJ wersji, nie placac za nic i nie mowiac nic.
    """
    with _srodowisko() as katalog:
        assert len(tlumacz_ai._podziel_na_bloki(TRESC_EDYTOWANA)) ==             len(tlumacz_ai._podziel_na_bloki(TRESC_PL)) == 1,             "test ma sens tylko wtedy, gdy edycja NIE zmienia liczby blokow"
        _przebieg_silnika(str(katalog), TRESC_PL)
        assert _licznik["blok"] == 1, _licznik
        wynik = _przebieg_silnika(str(katalog), TRESC_EDYTOWANA)
        assert _licznik["blok"] == 2, "cache z innej tresci zabral przebieg"
        assert "zdanko" in wynik.tekst, wynik.tekst
        assert "Trzecie zdanie" not in wynik.tekst, wynik.tekst
        metryka = _wiersze_cache(_sciezka_odcisku(str(katalog)))[0]
        assert metryka["zrodlo"] == tlumacz_ai._odcisk_zrodla(TRESC_EDYTOWANA),             metryka


def test_to_samo_zrodlo_wznawia_za_darmo():
    """Kontrola przeciwna: bez edycji cache dalej dziala (zero nowych callow)."""
    with _srodowisko() as katalog:
        _przebieg_silnika(str(katalog), TRESC_PL)
        assert _licznik["blok"] == 1, _licznik
        wynik = _przebieg_silnika(str(katalog), TRESC_PL)
        assert _licznik["blok"] == 1, "odcisk uniewaznil cache bez powodu"
        assert wynik.tekst.strip(), wynik


def test_metryka_bez_odcisku_jest_tolerowana():
    """Plik sprzed 18.31 (metryka bez `zrodlo`) NADAL wznawia.

    Druga polowa kontraktu: gdyby brak pola dyskwalifikowal cache, sama
    aktualizacja aplikacji kasowalaby oplacony postep komus w polowie PLATNEGO
    tlumaczenia. Tego samego bledu, tylko brutalniejszego, dotyczylby bump
    `_WERSJA_CHUNKOWANIA`.
    """
    with _srodowisko() as katalog:
        sciezka = _sciezka_odcisku(str(katalog))
        with open(sciezka, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"meta": tlumacz_ai._WERSJA_CHUNKOWANIA,
                                 "bloki": 1}) + "\n")
            fh.write(json.dumps({"id": 0, "text": "PRZEKLAD SPRZED 18.31"}) + "\n")
        wynik = _przebieg_silnika(str(katalog), TRESC_PL)
        assert _licznik["blok"] == 0, "stary cache mial zostac uzyty"
        assert wynik.tekst == "PRZEKLAD SPRZED 18.31", wynik.tekst


def test_niezgodny_odcisk_odrzuca_caly_cache():
    """Odcisk z innej tresci -> caly cache leci, metryka nadpisana biezaca."""
    with _srodowisko() as katalog:
        sciezka = _sciezka_odcisku(str(katalog))
        with open(sciezka, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"meta": tlumacz_ai._WERSJA_CHUNKOWANIA,
                                 "bloki": 1, "zrodlo": "0123456789abcdef"}) + "\n")
            fh.write(json.dumps({"id": 0, "text": "PRZEKLAD OBCEGO ZRODLA"}) + "\n")
        wynik = _przebieg_silnika(str(katalog), TRESC_PL)
        assert _licznik["blok"] == 1, _licznik
        assert "PRZEKLAD OBCEGO ZRODLA" not in wynik.tekst, wynik.tekst
        wiersze = _wiersze_cache(sciezka)
        assert wiersze[0] == {"meta": tlumacz_ai._WERSJA_CHUNKOWANIA, "bloki": 1,
                              "zrodlo": tlumacz_ai._odcisk_zrodla(TRESC_PL)},             wiersze[0]
        assert [w["id"] for w in wiersze[1:]] == [0], wiersze


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
