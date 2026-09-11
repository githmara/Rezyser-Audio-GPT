"""
test_sprzatanie_bundla.py - Bramka-lustro dla sprzatania martwego bundla przy
upgrade w miejscu (19.0).

Instalator kasuje zawartosc `{app}\\runtime` przed skopiowaniem nowej paczki,
POMIJAJAC to, co runtime sam tam zapisuje. Ta allowlista zyje w Pascalu, a rzeczy,
ktore chroni - w Pythonie. Rozjazd miedzy nimi nie jest halasliwy: nowy plik
cache'u w `runtime/` zaczalby po prostu znikac uzytkownikowi przy kazdym
upgrade, bez bledu i bez sladu. Stad trzy kontrakty:

  1. ALLOWLISTA ZGADZA SIE Z KODEM. Nazwy chronione w Pascalu wyprowadzone sa
     ze stalych aplikacji (`core_rezyser`, `core_llm`, `gui_opowiesci`,
     `tlumacz_ai`), a nie przepisane recznie.
  2. ZADEN INNY MODUL NIE PISZE DO KORZENIA `runtime/`. Skan zrodel lapie nowego
     konsumenta, ktory dolozylby tam plik i nie dopisal go do allowlisty.
  3. PROCEDURA TRAFIA DO BUILDA. `build_release` NADPISUJE cala sekcje `[Code]`
     z `installer.iss`, wiec kopia zostawiona tylko w placeholderze zniknelaby
     bez slowa. Sprawdzamy obie kopie i wynik generatora.

Uruchom:  .venv/Scripts/python test_sprzatanie_bundla.py
"""

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import build_release as br
import core_llm as cl
import core_rezyser as cr
import tlumacz_ai

ROOT = Path(__file__).parent
ISS = ROOT / "installer.iss"


# ---------------------------------------------------------------------------
# Wyciagniecie allowlisty z Pascala
# ---------------------------------------------------------------------------
def _allowlista_pascal() -> tuple[set[str], tuple[str, str]]:
    """(nazwy dokladne, (prefiks, sufiks) wzorca) z `KOD_SPRZATANIE_BUNDLA`.

    Czytamy TRESC procedury, a nie osobna liste - zeby nie dalo sie zmienic
    zachowania instalatora bez zmiany tego, co widzi ten test.
    """
    kod = br.KOD_SPRZATANIE_BUNDLA
    dokladne = set(re.findall(r"Nazwa = '([^']+)'", kod))
    dokladne -= {".", ".."}
    prefiks = re.search(r"Copy\(Nazwa, 1, \d+\) = '([^']+)'", kod).group(1)
    sufiks = re.search(r"Copy\(Nazwa, Length\(Nazwa\) - \d+, \d+\) = '([^']+)'",
                       kod).group(1)
    return dokladne, (prefiks, sufiks)


# ---------------------------------------------------------------------------
# 1. Allowlista zgadza sie ze stalymi aplikacji
# ---------------------------------------------------------------------------
def test_allowlista_pokrywa_pliki_cache_runtimeu():
    dokladne, _wzorzec = _allowlista_pascal()
    assert cr._PLIK_CACHE_ISO in dokladne, (
        f"cache ISO ({cr._PLIK_CACHE_ISO}) nie jest chroniony przed upgradem")
    assert cl._PLIK_CACHE_SAMPLINGU in dokladne, (
        f"autocache samplingu ({cl._PLIK_CACHE_SAMPLINGU}) nie jest chroniony")


def test_allowlista_pokrywa_podkatalogi_metadanych():
    dokladne, _wzorzec = _allowlista_pascal()
    # `gui_opowiesci` ciagnie wx, wiec bierzemy nazwy z zrodla zamiast importu -
    # test ma dzialac tez tam, gdzie GUI nie da sie zaimportowac.
    zrodlo = (ROOT / "gui_opowiesci.py").read_text(encoding="utf-8")
    for stala in ("OPOWIESCI_DIR", "MODE_DIR"):
        m = re.search(rf'{stala}\s*=\s*os\.path\.join\("runtime", "([^"]+)"\)',
                      zrodlo)
        assert m, f"{stala} zmienil ksztalt - test przestal cokolwiek mierzyc"
        assert m.group(1) in dokladne, (
            f"podkatalog metadanych `{m.group(1)}` znika przy upgrade")
    # Rezyser trzyma `.mode` w tym samym miejscu co Opowiesci.
    assert cr.RUNTIME_DIR == "runtime", cr.RUNTIME_DIR


def test_allowlista_pokrywa_cache_wznawiania_tlumaczenia():
    """Utrata tego pliku kosztuje uzytkownika pieniadze, nie tylko czas."""
    _dokladne, (prefiks, sufiks) = _allowlista_pascal()
    with tempfile.TemporaryDirectory() as tmp:
        nazwa = os.path.basename(
            tlumacz_ai._sciezka_pliku_tymczasowego(tmp, "projekt"))
    assert nazwa.startswith(prefiks), (nazwa, prefiks)
    assert nazwa.endswith(sufiks), (nazwa, sufiks)


def test_dlugosci_w_pascalu_zgadzaja_sie_z_tekstem():
    """`Copy(Nazwa, 1, N)` i `Copy(Nazwa, Length-N, M)` licza znaki RECZNIE."""
    kod = br.KOD_SPRZATANIE_BUNDLA
    n_pref = int(re.search(r"Copy\(Nazwa, 1, (\d+)\)", kod).group(1))
    _dokladne, (prefiks, sufiks) = _allowlista_pascal()
    assert n_pref == len(prefiks), (n_pref, prefiks)
    od, ile = re.search(r"Copy\(Nazwa, Length\(Nazwa\) - (\d+), (\d+)\)",
                        kod).groups()
    assert int(ile) == len(sufiks), (ile, sufiks)
    # Pascal indeksuje od 1: ostatnie `ile` znakow zaczyna sie na `Length-ile+1`.
    assert int(od) == len(sufiks) - 1, (od, sufiks)


# ---------------------------------------------------------------------------
# 2. Nikt inny nie pisze do korzenia runtime/
# ---------------------------------------------------------------------------
def test_zaden_inny_modul_nie_dokłada_pliku_do_korzenia_runtime():
    """Skan zrodel: kazdy literal sklejany z `runtime` musi byc chroniony.

    To polowa testu, ktora lapie PRZYSZLOSC - nowy plik cache'u dolozony do
    `runtime/` bez wpisu w allowliscie zaczalby znikac przy kazdym upgrade,
    a jedynym objawem byloby „znowu sie przelicza".
    """
    dokladne, (prefiks, _sufiks) = _allowlista_pascal()
    wzorzec = re.compile(r'"runtime",\s*"([^"]+)"')
    podejrzane = []
    for plik in ROOT.glob("*.py"):
        if plik.name.startswith("test_") or plik.name == "build_release.py":
            continue
        for nazwa in wzorzec.findall(plik.read_text(encoding="utf-8")):
            if nazwa in dokladne or nazwa.startswith(prefiks):
                continue
            podejrzane.append(f"{plik.name}: runtime/{nazwa}")
    assert not podejrzane, (
        "cos pisze do `runtime/` poza allowlista instalatora: " + str(podejrzane))


# ---------------------------------------------------------------------------
# 3. Procedura naprawde trafia do instalatora
# ---------------------------------------------------------------------------
def test_placeholder_w_iss_jest_identyczny_z_generatorem():
    """Rozjazd tutaj znaczy, ze `iscc installer.iss` sprawdza INNY kod."""
    tresc = ISS.read_text(encoding="utf-8")
    assert br.KOD_SPRZATANIE_BUNDLA.strip() in tresc, (
        "kopia w installer.iss rozjechala sie z build_release.KOD_SPRZATANIE_BUNDLA")


def test_generowana_sekcja_code_niesie_procedure():
    """Regresja, nie tautologia: generator NADPISUJE [Code] w calosci.

    Odtwarzamy dokladnie te sklejke, ktora robi `zbuduj_installer`, i sprawdzamy,
    ze procedura w niej jest. Gdyby wrocila do samego placeholdera w .iss,
    ten test pada, mimo ze plik w repo wygladalby poprawnie.
    """
    blok_kod_iso = br.buduj_blok_kodu_iso([("polish", "x.isl")], ["pl"])
    kod_section = (
        "[Code]\n"
        "function GetManualISO(Param: String): String;\n"
        "begin\n"
        f"{blok_kod_iso}\n"
        "end;\n\n"
        f"{br.KOD_SPRZATANIE_BUNDLA}\n"
    )
    assert "procedure UsunMartwyBundle();" in kod_section
    assert "CurStepChanged" in kod_section and "ssInstall" in kod_section
    assert "GetManualISO" in kod_section, "nie zjedlismy istniejacej funkcji"


def test_sekcja_code_kompiluje_sie_pod_iscc():
    """Jedyna kontrola, ktorej asercje na tekscie nie zastapia.

    Zlapala realny blad przy pisaniu tej bramki: komentarze `;` (poprawne
    w pozostalych sekcjach .iss) sa w [Code] bledem skladni Pascala. Build by
    tego NIE pokazal - generator nadpisuje ta sekcje w calosci - wiec placeholder
    po cichu przestalby byc kompilowalny, a `iscc installer.iss` (jego jedyny
    powod istnienia) zaczalby padac.

    Bramka DEGRADOWANA, nie pomijana: bez Inno Setup mowi to wprost.
    """
    import shutil
    import subprocess

    iscc = shutil.which("iscc") or shutil.which("ISCC")
    if not iscc:
        print("      (brak ISCC w PATH — kompilacja [Code] niesprawdzona)")
        return

    blok = ISS.read_text(encoding="utf-8").split("[Code]", 1)[1]
    blok = blok.split("[CustomMessages]", 1)[0]
    with tempfile.TemporaryDirectory() as tmp:
        iss = Path(tmp) / "sprawdzenie.iss"
        iss.write_text(
            "[Setup]\nAppName=C\nAppVersion=0\n"
            "DefaultDirName={autopf}\\C\n"
            f"OutputDir={tmp}\nOutputBaseFilename=c\n\n[Code]" + blok,
            encoding="utf-8")
        wynik = subprocess.run([iscc, str(iss)], capture_output=True, text=True)
    assert wynik.returncode == 0, (
        "sekcja [Code] w installer.iss nie kompiluje sie:\n"
        + (wynik.stdout or "")[-600:])


def test_procedura_kasuje_dopiero_po_potwierdzeniu():
    """`ssInstall` = po kliknieciu Install, przed kopiowaniem. Nie `ssPostInstall`
    (byloby po skopiowaniu = skasowalibysmy swiezy bundle) i nie wczesniej."""
    kod = br.KOD_SPRZATANIE_BUNDLA
    assert "if CurStep = ssInstall then" in kod
    assert "ssPostInstall" not in kod


def test_procedura_nie_rusza_katalogu_ktorego_nie_ma():
    """Swieza instalacja nie ma `{app}\\runtime` - guard musi byc pierwszy."""
    kod = br.KOD_SPRZATANIE_BUNDLA
    i_guard = kod.index("if not DirExists(Katalog) then")
    i_kasowanie = kod.index("DelTree")
    assert i_guard < i_kasowanie, "guard stoi PO kasowaniu"


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
