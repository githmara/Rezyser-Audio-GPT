"""
test_core_zastepcze.py — litery zastąpione przez generator PDF znakiem ■ (19.19).

Kontrakty, których nie sprawdza żadna bramka danych:
  A. walidacja: model może zmienić WYŁĄCZNIE pozycje ■, każdą na jedną literę
     spoza WinAnsi z alfabetów paczek — każda inna propozycja przepada;
  B. słowa: unikalne, 1–3 ■ i co najmniej jedna litera, od najczęstszych;
     ciąg samych ■ (pasek, maska) nie jest słowem;
  C. wywołanie: do modelu idą tylko słowa z kontekstem i lista liter,
     a odpowiedź spoza listy słów albo po złej walidacji nie trafia do mapy;
  D. podmiana całych słów, nie fragmentów.

Mock modelu, zero wywołań API.

Uruchom:  .venv/Scripts/python -m pytest test_core_zastepcze.py -q
"""
import json
import sys

import pytest

import core_llm as cl
import core_zastepcze as cz

Z = cz.ZASTEPCZY
LITERY_PL = frozenset("aąbcćdeęfghijklłmnńoóprsśtuwyzźżAĄBCĆDEĘFGHIJKLŁMNŃOÓPRSŚTUWYZŹŻ")
KLIENT = cl.KlientLLM(cl.PROVIDER_ANTHROPIC, None)


def test_kandydaci_tylko_spoza_winansi():
    k = cz.kandydaci(LITERY_PL | {"é", "1", " "})
    assert set(k) == set("ąćęłńśźżĄĆĘŁŃŚŹŻ")      # ó, é są w cp1252 — generator ich nie gubi


@pytest.mark.parametrize("slowo, propozycja, ok", [
    ("G" + Z + "ÓWNEJ", "GŁÓWNEJ", True),
    ("audytuj" + Z + "cy", "audytujący", True),
    ("audytuj" + Z + "cy", "audytujacy", False),     # „a” jest w WinAnsi — nie mogło zginąć
    ("audytuj" + Z + "cy", "audytujących", False),   # zmieniona długość
    ("G" + Z + "ÓWNEJ", "GłOWNEJ", False),           # ruszone litery spoza ■
    ("S" + Z + "MU", "S" + Z + "MU", False),         # ■ zostawiony
    # Audyt 19.19: litera musi pasować do słowa — wielkością i pismem.
    ("G" + Z + "ÓWNEJ", "GłÓWNEJ", False),           # mała w słowie wersalikami
    ("zosta" + Z, "zostaŁ", False),                  # wielka w środku słowa małymi
    (Z + "e", "Że", True),                           # wielka na początku słowa: dozwolona
    ("audytuj" + Z + "cy", "audytujЖcy", False),     # cyrylica w słowie łacińskim
])
def test_walidacja_zmienia_tylko_pozycje_zastepcze(slowo, propozycja, ok):
    assert cz.poprawna(slowo, propozycja, cz.kandydaci(LITERY_PL)) is ok


def test_slowa_od_najczestszych_bez_paskow():
    tekst = f"zosta{Z} zosta{Z} audytuj{Z}cy ({Z * 10}) {Z} a{Z}{Z}{Z}{Z}b"
    assert cz.slowa_do_odtworzenia(tekst) == [f"zosta{Z}", f"audytuj{Z}cy"]


def test_jedno_wywolanie_i_walidacja_odpowiedzi(monkeypatch):
    wyslane = []

    def wywolaj(klient, **kw):
        wyslane.append(kw)
        return json.dumps({"words": [
            {"word": f"zosta{Z}", "restored": "został"},
            {"word": f"audytuj{Z}cy", "restored": "audytujacy"},       # zła litera
            {"word": "obce", "restored": "obce"},                       # spoza listy
        ]}), "end_turn"

    monkeypatch.setattr(cl, "wywolaj_llm", wywolaj)
    tekst = f"Raport zosta{Z} przyjęty. Zespół audytuj{Z}cy pracował."
    mapa = cz.odtworz(KLIENT, tekst, LITERY_PL)
    assert mapa == {f"zosta{Z}": "został"}
    tresc = wyslane[0]["messages"][0]["content"]
    assert "Raport zosta" in tresc
    assert "Allowed letters: " + cz.kandydaci(LITERY_PL) in tresc
    assert wyslane[0]["schema_json"] is not None
    # Druga runda: tylko słowo, którego pierwsza nie odtworzyła.
    assert len(wyslane) == cz.PROBY == 2
    assert f'"word": "audytuj{Z}cy"' in wyslane[1]["messages"][0]["content"]
    assert f'"word": "zosta{Z}"' not in wyslane[1]["messages"][0]["content"]


def test_blad_drugiej_rundy_nie_kasuje_pierwszej(monkeypatch):
    odpowiedzi = [(json.dumps({"words": [{"word": f"zosta{Z}", "restored": "został"}]}), "end_turn"),
                  cl.BladTimeoutLLM("timeout")]

    def wywolaj(klient, **kw):
        nastepna = odpowiedzi.pop(0)
        if isinstance(nastepna, Exception):
            raise nastepna
        return nastepna

    monkeypatch.setattr(cl, "wywolaj_llm", wywolaj)
    assert cz.odtworz(KLIENT, f"zosta{Z} i audytuj{Z}cy", LITERY_PL) == {f"zosta{Z}": "został"}
    monkeypatch.setattr(cl, "wywolaj_llm", lambda *a, **k: (_ for _ in ()).throw(cl.BladTimeoutLLM("x")))
    with pytest.raises(cl.BladTimeoutLLM):                  # błąd pierwszej rundy leci do GUI
        cz.odtworz(KLIENT, f"zosta{Z}", LITERY_PL)


def test_dluga_lista_idzie_paczkami_bez_ucinania(monkeypatch):
    # Audyt 19.19: dawny limit 400 słów ucinał resztę po cichu.
    wyslane = []

    def wywolaj(klient, **kw):
        wyslane.append(kw["messages"][0]["content"].count('"word"'))
        return json.dumps({"words": []}), "end_turn"

    monkeypatch.setattr(cl, "wywolaj_llm", wywolaj)
    monkeypatch.setattr(cz, "PACZKA_SLOW", 3)
    slowa = " ".join(f"s{chr(0x61 + i)}{Z}" for i in range(7))
    cz.odtworz(KLIENT, slowa, LITERY_PL)
    assert wyslane == [3, 3, 1] * cz.PROBY          # każde słowo w każdej rundzie, paczkami


def test_bez_slow_bez_wywolania(monkeypatch):
    monkeypatch.setattr(cl, "wywolaj_llm", lambda *a, **k: pytest.fail("niepotrzebne wywołanie"))
    assert cz.odtworz(KLIENT, "Tekst bez znaków zastępczych.", LITERY_PL) == {}


def test_podmiana_calych_slow():
    mapa = {f"zosta{Z}": "został"}
    assert cz.zastosuj(f"zosta{Z} i zosta{Z}o", mapa) == f"został i zosta{Z}o"


def test_koszt_ponizej_centa_dla_typowego_dokumentu():
    assert cz.szacuj_koszt(KLIENT, 150) < 0.1
    assert cz.szacuj_koszt(cl.KlientLLM(cl.PROVIDER_OPENAI_COMPAT, None, model_override="x"), 10) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
