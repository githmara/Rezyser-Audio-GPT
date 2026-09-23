"""
test_uciety_skrypt.py - Skrypt ucięty na max_tokens zapisuje odzyskane tury (19.8).

Do v19.7 `generuj_skrypt` przy `stop_reason == "max_tokens"` rzucał wyjątek
i cała OPŁACONA generacja przepadała. Decyzja maintainera: kompletne tury
bierzemy, ostatnią domykamy mikro-callem (`_domknij_urwane_zdanie`, jak
audiobook), a gdy ucięcie padło w nazwie mówcy albo domknięcie zawiedzie -
turę wycinamy. Ostrzeżenie w obu przypadkach. Zmierzone WYKONANIEM na stubie
`core_llm.wywolaj_llm` (zero sieci), przez pełne `generuj_skrypt`.

Uruchom:  .venv/Scripts/python -m pytest test_uciety_skrypt.py -q
Albo jako skrypt (deleguje do pytesta): .venv/Scripts/python test_uciety_skrypt.py
"""

import contextlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import core_llm as cl
import core_rezyser as cr
import i18n
import przepisy_rezysera as pr
import rezyser_ai as rai

PELNE = [{"mowca": "Narrator", "tekst": "Peron jest pusty."},
         {"mowca": "Hans", "tekst": "[whispers] Jestem tutaj."}]
POCZATEK = json.dumps({"tury": PELNE}, ensure_ascii=False)[:-2]   # bez `]}`


def _uciety(ogon: str) -> str:
    return POCZATEK + ", " + ogon


@contextlib.contextmanager
def _stub(odpowiedz_glowna: str, domkniecie: tuple[str, str] = ("Johanna odchodzi.", "end_turn")):
    wywolania: list[str] = []

    def _llm(klient, *, model, system, messages, max_tokens, **_kw):
        if "cut off mid-sentence" in system:
            wywolania.append("domkniecie")
            return domkniecie
        wywolania.append("glowne")
        return odpowiedz_glowna, "max_tokens"

    stary_llm, stary_jezyk = cl.wywolaj_llm, rai._wykryty_inny_jezyk
    cl.wywolaj_llm = _llm
    rai._wykryty_inny_jezyk = lambda *_a, **_k: None
    try:
        yield wywolania
    finally:
        cl.wywolaj_llm, rai._wykryty_inny_jezyk = stary_llm, stary_jezyk


def _generuj():
    przepis = pr.zaladuj_przepis("skrypt", "pl")
    snapshot = cr.SnapshotProjektu(**{
        f: "" for f in cr.SnapshotProjektu.__dataclass_fields__})
    return rai.generuj_skrypt(None, przepis, snapshot, "Scena na peronie.")


@pytest.mark.parametrize("surowy,tury,ucieta,urwano", [
    (_uciety('{"mowca": "Johanna", "tekst": "Idę do'), 2,
     {"mowca": "Johanna", "tekst": "Idę do"}, True),
    (_uciety('{"mowca": "Joha'), 2, None, True),              # ucięty mówca
    (_uciety('{"mowca": "Johanna", "tekst": "'), 2, None, True),   # tekst się nie zaczął
    (_uciety('{"mowca": "Johanna", "tekst": "Znak \\u00'), 2,
     {"mowca": "Johanna", "tekst": "Znak "}, True),            # ucięta sekwencja \u
    (POCZATEK, 2, None, False),                               # cięcie MIĘDZY turami
    ('{"typ": "tura", "tury": [', 0, None, False),
    ("", 0, None, False),
    # openai_compat: dosłowny znak nowej linii w pełnej turze nie może zabrać
    # kolejnych (F5 audytu 19.8).
    ('{"tury":[{"mowca":"N","tekst":"a\nb"},{"mowca":"B","tekst":"xyz."}, '
     '{"mowca":"C","tekst":"cut', 2, {"mowca": "C", "tekst": "cut"}, True),
])
def test_odzysk_przyrostowy(surowy, tury, ucieta, urwano):
    wynik_tury, wynik_ucieta, wynik_urwano = rai.odzyskaj_tury_ucietego_skryptu(surowy)
    assert len(wynik_tury) == tury
    assert wynik_ucieta == ucieta
    assert wynik_urwano is urwano


def test_ucieta_kwestia_domknieta():
    with _stub(_uciety('{"mowca": "Johanna", "tekst": "Idę do pracy, Hans. Ktoś tu mu')) as w:
        wynik = _generuj()
    assert w == ["glowne", "domkniecie"], w
    assert len(wynik.tury) == 3
    assert wynik.tury[-1].tekst == "Idę do pracy, Hans. Johanna odchodzi."
    assert wynik.ostrzezenie == i18n.t("rezyser.ostrzezenie_skrypt_domknieto")
    assert wynik.tekst_odpowiedzi.splitlines()[-1].startswith("[Johanna] ")


def test_uciety_mowca_wycina_ture_bez_mikrocallu():
    with _stub(_uciety('{"mowca": "Joha')) as w:
        wynik = _generuj()
    assert w == ["glowne"], "bez kwestii nie ma czego domykać"
    assert [t.mowca for t in wynik.tury] == ["Narrator", "Hans"]
    assert wynik.ostrzezenie == i18n.t("rezyser.ostrzezenie_skrypt_wycieto")


def test_nieudane_domkniecie_wycina_ture():
    with _stub(_uciety('{"mowca": "Johanna", "tekst": "Idę do'),
               domkniecie=("", "max_tokens")):
        wynik = _generuj()
    assert len(wynik.tury) == 2
    assert wynik.ostrzezenie == i18n.t("rezyser.ostrzezenie_skrypt_wycieto")


def test_urwany_audio_tag_zdjety_przed_domknieciem():
    ogony: list[str] = []

    def _llm(klient, *, model, system, messages, **_kw):
        if "cut off mid-sentence" in system:
            ogony.append(messages[0]["content"])
            return "Stój.", "end_turn"
        return _uciety('{"mowca": "Hans", "tekst": "Stój. [whisp'), "max_tokens"

    stary_llm, stary_jezyk = cl.wywolaj_llm, rai._wykryty_inny_jezyk
    cl.wywolaj_llm, rai._wykryty_inny_jezyk = _llm, (lambda *_a, **_k: None)
    try:
        wynik = _generuj()
    finally:
        cl.wywolaj_llm, rai._wykryty_inny_jezyk = stary_llm, stary_jezyk
    assert wynik.tekst_odpowiedzi.splitlines()[-1] == "[Hans] Stój."
    assert ogony == [], "kwestia kończy się pełnym zdaniem — nie ma czego domykać"


def test_niepoprawna_tura_nie_spala_retry_struktury():
    """F1 audytu: pusta kwestia (API nie niesie minLength) = odrzut tury, nie 3 pełne calle."""
    with _stub('{"typ":"tura","tury":[{"mowca":"N","tekst":""},'
               '{"mowca":"A","tekst":"Pełna."},{"mowca":"B","tekst":"cut') as w:
        wynik = _generuj()
    assert w.count("glowne") == 1, w
    assert [t.mowca for t in wynik.tury] == ["A", "B"]
    assert wynik.ostrzezenie == i18n.t("rezyser.ostrzezenie_skrypt_wycieto")


def test_pelny_tag_w_ogonie_nie_idzie_do_mikrocallu():
    """F2 audytu: `[whispers]` po ostatniej granicy zdania zostaje w kwestii."""
    ogony: list[str] = []

    def _llm(klient, *, model, system, messages, **_kw):
        if "cut off mid-sentence" in system:
            ogony.append(messages[0]["content"])
            return "Idę do domu.", "end_turn"
        return _uciety('{"mowca": "A", "tekst": "Dobrze. [whispers] Idę do'), "max_tokens"

    stary_llm, stary_jezyk = cl.wywolaj_llm, rai._wykryty_inny_jezyk
    cl.wywolaj_llm, rai._wykryty_inny_jezyk = _llm, (lambda *_a, **_k: None)
    try:
        wynik = _generuj()
    finally:
        cl.wywolaj_llm, rai._wykryty_inny_jezyk = stary_llm, stary_jezyk
    assert ogony == ["Idę do"], ogony
    assert wynik.tekst_odpowiedzi.splitlines()[-1] == "[A] Dobrze. [whispers] Idę do domu."


def test_ciecie_miedzy_turami_nie_twierdzi_ze_cos_przepadlo():
    """F3 audytu: nic nie wycięto -> neutralny komunikat, nie „pominięta kwestia"."""
    with _stub(POCZATEK) as w:
        wynik = _generuj()
    assert w == ["glowne"]
    assert len(wynik.tury) == 2
    assert wynik.ostrzezenie == i18n.t("rezyser.ostrzezenie_skrypt_limit")


def test_bez_zadnej_tury_zostaje_dawny_blad():
    with _stub('{"typ": "tura", "tury": [{"mowca": "Na'):
        with pytest.raises(rai.BladDlugosciOdpowiedzi):
            _generuj()


def test_klucze_ostrzezen_w_kazdej_paczce():
    """Komunikat pokazuje GUI w języku interfejsu — każda paczka musi go mieć."""
    # Plik paczki czytany WPROST: `i18n.t` spada na paczkę zapasową, więc
    # przeszedłby także wtedy, gdy klucza w paczce brak (zmierzone przy pisaniu).
    import yaml
    import core_poliglota as cp
    for kod in cp.dostepne_jezyki_bazowe():
        plik = Path(__file__).parent / "dictionaries" / kod / "gui" / "ui.yaml"
        sekcja = yaml.safe_load(plik.read_text(encoding="utf-8"))["rezyser"]
        for klucz in ("ostrzezenie_skrypt_domknieto", "ostrzezenie_skrypt_wycieto",
                      "ostrzezenie_skrypt_limit"):
            assert str(sekcja.get(klucz, "")).strip(), (kod, klucz)


# Uruchomienie jako skrypt - deleguje do pytesta (kanon v19.2.1, §6.11).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
