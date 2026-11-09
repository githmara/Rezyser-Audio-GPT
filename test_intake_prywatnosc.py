"""
test_intake_prywatnosc.py - adres email z prosby o patch nie wychodzi do OpenAI.

Zgloszone przez maintainera 2026-11-09, potwierdzone w kodzie:
  * zwykly uzytkownik NIE moze nadac etykiety przy otwieraniu issue, wiec
    prosba o patch Tiflotecnii (adres email w tresci) przychodzi do Sami
    zdarzeniem `opened` BEZ `tiflotecnia-patch`; filtr przepuszcza issue bez
    etykiet, wiec tresc z adresem szla do OpenAI, zanim maintainer zdazyl
    nadac etykiete;
  * przy pauzie patch-bota issue ma `tiflotecnia-patch` + `on-hold`; przy
    "zdejmij i naloz `tiflotecnia-patch`" jedyna etykieta przez chwile jest
    `on-hold`, ktorej filtr nie znal.

Kontrakty: adresy zaslaniane przed LLM (na sciezce produkcyjnej `main`),
`on-hold` ignorowane, a lista ignorowanych etykiet w skrypcie i filtr joba
w `issue-intake.yml` sa tym samym zbiorem.

Uruchom:  .venv/Scripts/python -m pytest test_intake_prywatnosc.py -q
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
sys.path.insert(0, str(ROOT))

import issue_intake_sami as sami

ADRESY = ["jan.kowalski@example.com", "user+nvda@mail.example.co.uk",
          "a-b_c@sub-domena.example.org"]


@pytest.mark.parametrize("adres", ADRESY)
def test_adres_zasloniety(adres):
    wynik = sami.bez_adresow_email(f"Prosze o patch: {adres}. Dzieki!")
    assert adres not in wynik and "@" not in wynik, wynik
    assert sami.ZASLONA_EMAIL in wynik


def test_wzmianka_i_tekst_bez_adresu_zostaja():
    tekst = "Dzieki @githmara, wersja 19.17, pip install openai@1.40.0 i plik a.b.txt"
    assert sami.bez_adresow_email(tekst) == tekst


class _Przechwycone(Exception):
    pass


def test_main_nie_wysyla_adresu_do_llm(monkeypatch):
    """Sciezka produkcyjna: issue `opened` bez etykiet, adres w tytule i tresci."""
    adres = ADRESY[1]
    monkeypatch.setenv("ISSUE_TITLE", f"patch dla {adres}")
    monkeypatch.setenv("ISSUE_BODY", f"Prosze o patch tiflotecnia.\n{adres}\n")
    monkeypatch.setenv("ISSUE_NUMBER", "1")
    monkeypatch.setenv("ISSUE_LABELS", "")
    monkeypatch.setenv("ISSUE_URL", "https://github.com/x/y/issues/1")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")
    zlapane = {}

    def _llm(title, body, labels):
        zlapane.update(title=title, body=body)
        raise _Przechwycone

    monkeypatch.setattr(sami, "_przeredaguj_z_openai", _llm)
    with pytest.raises(_Przechwycone):
        sami.main()
    assert adres not in zlapane["title"] and adres not in zlapane["body"], zlapane


@pytest.mark.parametrize("etykiety", ["on-hold", "on-hold,bug", "tiflotecnia-patch,on-hold"])
def test_on_hold_ignorowane(etykiety):
    przepusc, _ = sami._przepuszczalne(etykiety)
    assert not przepusc


def test_filtr_joba_rowna_sie_labels_ignore():
    yml = (ROOT / ".github" / "workflows" / "issue-intake.yml").read_text(encoding="utf-8")
    w_filtrze = set(re.findall(r"github\.event\.label\.name != '([^']+)'", yml))
    assert w_filtrze == sami.LABELS_IGNORE, (
        f"tylko w YAML: {w_filtrze - sami.LABELS_IGNORE}, "
        f"tylko w skrypcie: {sami.LABELS_IGNORE - w_filtrze}")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
