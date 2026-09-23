"""
test_jezyk_odpowiedzi.py - Regresja: dwie usterki przepisow Rezysera znalezione w 19.8.

  1. SLOWA-WYZWALACZE streszczenia porownywane OBUSTRONNIE malymi literami.
     GUI obnizalo tylko tekst uzytkownika, wiec slowo z paczki zapisane wielka
     litera (de `Zusammenfassung`, `Uberblick`) nie trafialo nigdy.
  2. `{jezyk_odpowiedzi}` PO RENDERZE nie dubluje przyimka. Wartosc pola jest
     w wielu paczkach juz okolicznikiem (`a islensku`, `na russkom`), a szablon
     dopisywal przed nia ten sam przyimek: model czytal „a a islensku",
     „na na russkom". Bramka lapie wylacznie DUBEL - pokrewnej klasy
     („kielella suomeksi", „w polsku") nie da sie sprawdzic bez gramatyki
     jezyka, dlatego stoi w checkliscie `przeglad_tlumaczen._CHECKLIST_TRYBY`.

Uruchom:  .venv/Scripts/python -m pytest test_jezyk_odpowiedzi.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_jezyk_odpowiedzi.py
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_poliglota as cp
import przepisy_rezysera as pr


def _wszystkie_przepisy():
    for kod in cp.dostepne_jezyki_bazowe():
        for przepis in pr.lista_trybow(kod) + pr.lista_postprodukcji(kod):
            yield kod, przepis


def test_zakres_nie_jest_pusty():
    assert len(list(_wszystkie_przepisy())) >= 9 * 5


@pytest.mark.parametrize("tekst", [
    "Gib mir eine Zusammenfassung", "ZUSAMMENFASSUNG bitte", "fasse zusammen",
])
def test_wyzwalacz_z_wielkiej_litery_trafia(tekst):
    przepis = pr.zaladuj_przepis("skrypt", "de")
    assert pr.prosi_o_streszczenie(przepis, tekst), tekst


@pytest.mark.parametrize("tekst", [
    "Väinö betritt das Lager.",
    # Audyt 19.8: `Überblick` to zwykły rzeczownik — po poprawce wielkości liter
    # zaczął blokować zwykłe instrukcje sceny, więc wypadł z list paczki de.
    "Der Kommissar verschafft sich einen Überblick über den Tatort.",
])
def test_zwykla_instrukcja_nie_jest_prosba_o_streszczenie(tekst):
    przepis = pr.zaladuj_przepis("skrypt", "de")
    assert not pr.prosi_o_streszczenie(przepis, tekst)


@pytest.mark.parametrize("tryb", ["skrypt", "audiobook"])
def test_fi_kertaa_nie_blokuje_zwyklej_instrukcji(tryb):
    """Decyzja maintainera 19.8: `kertaa` to też partytyw od *kerta* („kaksi
    kertaa" = dwa razy), więc jako podciąg blokował zwykłe instrukcje sceny."""
    przepis = pr.zaladuj_przepis(tryb, "fi")
    assert not pr.prosi_o_streszczenie(przepis, "Hän koputtaa oveen kaksi kertaa.")


def test_kazdy_wyzwalacz_kazdej_paczki_trafia_w_samego_siebie():
    """Slowo z paczki wpisane dokladnie tak, jak stoi w pliku, MUSI blokowac."""
    for kod, przepis in _wszystkie_przepisy():
        for slowo in przepis.slowa_wyzwalajace.get("streszczenie", []):
            assert pr.prosi_o_streszczenie(przepis, slowo), (kod, przepis.id, slowo)


def test_jezyk_odpowiedzi_nie_dubluje_przyimka():
    usterki = []
    for kod, przepis in _wszystkie_przepisy():
        wartosc = przepis.jezyk_odpowiedzi.strip()
        pierwsze = wartosc.split()[0] if wartosc else ""
        if not pierwsze:
            continue
        tekst = "\n".join([
            pr.buduj_prompt_systemowy(przepis, ""),
            pr.buduj_przypomnienie(przepis),
        ])
        for m in re.finditer(rf"(\S+)\s+{re.escape(wartosc)}", tekst):
            if m.group(1).lower() == pierwsze.lower():
                usterki.append(f"{kod}/{przepis.id}: …{m.group(0)}…")
    assert not usterki, "\n".join(usterki)


# Uruchomienie jako skrypt - deleguje do pytesta (kanon v19.2.1, §6.11).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
