"""
test_json_structured.py - Regresja structured outputs i degradacji payloadu (18.23).

Punkt wyjscia to realne zgloszenie z 2026-08-29 (projekt `helsinki_story`, tryb
Burzy): model zwrocil JSON z PRZECINKIEM WISZACYM, `json.loads` rzucil
„Expecting property name enclosed in double quotes", a self-correction odeslal
modelowi ten komunikat - czyli kazal mu naprawiac CUDZYSLOWY, ktore byly
bezbledne. Trzy proby, trzy razy ten sam blad, `BladStrukturyJSON` u usera.

Testy pilnuja czterech rzeczy, ktorych nie pilnuje zadna bramka danych:
  1. schemat wysylany do API miesci sie w podzbiorze structured outputs,
     a schemat KANONICZNY (do `jsonschema`) zostaje nietkniety;
  2. klauzula odrzucenia ma legalna droge wyjscia mimo wymuszonego schematu;
  3. degradacja payloadu jest CELOWANA - 400 o `temperature` NIE MOZE zdejmowac
     `output_config` (inaczej structured outputs nie dzialaja ani razu, bo
     domyslny `claude-sonnet-5` nie honoruje temperatury z przepisow);
  4. tresc `BladStrukturyJSON` nadaje sie do PUBLICZNEGO zgloszenia - niesie
     request_id kazdej proby i zero prozy uzytkownika.

Piata rzecz doszla w 18.24 (sekcja 3b): kontrakt samplingu `core_llm` jest teraz
DZIELONY z rodzina autotlumaczy, ktora ma wlasnych klientow Anthropic. Testy
pilnuja, ze rodzina nie placi jalowym round-tripem 400 na modelu z baseline'u
i ze nauke o nieznanym modelu zapamietuje RAZ, a nie co chunk.

Mock SDK, zero wywolan API.

Uruchom:  .venv/Scripts/python test_json_structured.py
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))

import core_llm as cl
import core_rezyser as cr
import opowiesci_ai as oa
import przepisy_rezysera as pr
import rezyser_ai as ra
from bledy_ai import BladStrukturyJSON

# IZOLACJA: autocache samplingu jest TRWALY (`runtime/`), a test wymusza 400
# o temperaturze - bez tego przekierowania zapisalby stan do prawdziwej
# instalacji maintainera. Kierujemy go w katalog tymczasowy i zerujemy pamiec.
import tempfile

_TYMCZASOWY_CACHE = str(
    Path(tempfile.gettempdir()) / "test_json_structured_sampling.json")
cl._sciezka_cache_samplingu = lambda: _TYMCZASOWY_CACHE
cl._NAUCZONE_BEZ_TEMPERATURY = set()


# ---------------------------------------------------------------------------
# Mock SDK: oddaje przygotowane odpowiedzi, notuje wyslane kwargs
# ---------------------------------------------------------------------------
class _Blad400(Exception):
    """Imituje `BadRequestError` SDK (rozpoznawany przez `_czy_zla_struktura`)."""

    status_code = 400

    def __init__(self, komunikat):
        super().__init__(komunikat)


BLAD_TEMPERATURY = "`temperature` is deprecated for this model."
BLAD_SCHEMATU = (
    "output_config.format.schema: For 'array' type, property 'maxItems' "
    "is not supported"
)


class _MockSDK:
    """`odpowiedzi` to lista (tekst, stop_reason) albo wyjatkow do rzucenia."""

    def __init__(self, odpowiedzi, wyslane):
        self._odpowiedzi = list(odpowiedzi)
        self._wyslane = wyslane
        self.messages = self

    def with_options(self, **_kwargs):
        return self

    def create(self, **kwargs):
        self._wyslane.append(kwargs)
        pozycja = self._odpowiedzi.pop(0)
        if isinstance(pozycja, Exception):
            raise pozycja
        tekst, stop = pozycja
        resp = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=tekst)] if tekst else [],
            stop_reason=stop,
            usage=SimpleNamespace(input_tokens=1234, output_tokens=567),
        )
        resp._request_id = f"req_TEST{len(self._wyslane)}"
        return resp


def klient_z(odpowiedzi):
    wyslane = []
    sdk = _MockSDK(odpowiedzi, wyslane)
    return cl.KlientLLM(provider=cl.PROVIDER_ANTHROPIC, sdk=sdk), wyslane


# Paczka `en`, bo fixture i komunikaty sa angielskie — inaczej bramka
# jezykowa (`_wykryty_inny_jezyk`) slusznie wykrywa rozjazd i dokłada
# jeden strzal korekty, co psuje liczniki prob w testach.
PRZEPIS_BURZA = pr.zaladuj_przepis("burza", "en")
SNAP = cr.SnapshotProjektu(
    nazwa="helsinki_story",
    full_story="PROLOGUE: Aino steps off the night train in Helsinki.",
    summary_text="",
    world_lore="Helsinki, February, frost.",
)
TRZY_OPCJE = [
    {"tytul": f"Option {i}", "opis": f"Description {i}", "cel_sceny": f"Goal {i}"}
    for i in (1, 2, 3)
]

# Ksztalt DOKLADNIE z logu usera: indent 2, przecinek po ostatnim polu opcji,
# dlugie `cel_sceny`. Bez naprawy: 3 proby -> BladStrukturyJSON.
JSON_Z_LOGU = (
    '{\n  "opcje": [\n    {\n'
    '      "tytul": "Night chase",\n'
    '      "opis": "Aino follows the shadow.",\n'
    '      "cel_sceny": "' + "x" * 1100 + '",\n'
    "    }\n  ]\n}"
)


# ---------------------------------------------------------------------------
# 1. Schemat wysylany do API vs schemat kanoniczny
# ---------------------------------------------------------------------------
def test_fixture_odtwarza_komunikat_z_logu():
    try:
        json.loads(JSON_Z_LOGU)
    except json.JSONDecodeError as exc:
        assert exc.msg == "Expecting property name enclosed in double quotes", exc.msg
        return
    raise AssertionError("fixture parses, but it must not")


def test_schemat_api_bez_niewspieranych_slow_kluczowych():
    for schemat in (ra.SCHEMA_BURZA_API, ra.SCHEMA_SKRYPT_API, oa.SCHEMA_TURA_API):
        tekst = json.dumps(schemat)
        for klucz in cl._KLUCZE_NIEWSPIERANE:
            assert f'"{klucz}"' not in tekst, f"{klucz} leaked into the API schema"


def test_schemat_kanoniczny_zostaje_nietkniety():
    # `jsonschema` musi dalej pilnowac kardynalnosci, ktorej API nie przyjmuje.
    assert "maxItems" in json.dumps(ra.SCHEMA_BURZA)
    assert oa.SCHEMA_TURA["properties"]["stan"]["additionalProperties"] is True


def test_additional_properties_domkniete_w_kopii_api():
    assert oa.SCHEMA_TURA_API["anyOf"][0]["properties"]["stan"][
        "additionalProperties"] is False


def test_galaz_tury_dziedziczy_required_kanoniczne():
    # Bez tego model POMIJA pola (zmierzone zywo: tura Opowiesci bez `wybory`),
    # bo API ich nie wymaga, a `jsonschema` wymaga -> jalowe retry.
    tura = oa.SCHEMA_TURA_API["anyOf"][0]
    assert set(oa.SCHEMA_TURA["required"]) <= set(tura["required"])
    assert tura["properties"]["typ"]["const"] == cl.TYP_TURA


def test_galaz_odmowy_ma_nietrywialny_sentinel():
    odmowa = ra.SCHEMA_BURZA_API["anyOf"][1]
    assert set(odmowa["required"]) == {"typ", "odrzucenie"}
    assert pr.TAG_ODRZUCENIA_AI in odmowa["properties"]["odrzucenie"]["description"]


def test_schemat_api_jest_deterministyczny():
    # Kompilacja schematu po stronie API jest cache'owana bajtowo (24 h).
    pierwszy = json.dumps(cl.schemat_z_dyskryminatorem(
        ra.SCHEMA_BURZA, pr.TAG_ODRZUCENIA_AI))
    drugi = json.dumps(cl.schemat_z_dyskryminatorem(
        ra.SCHEMA_BURZA, pr.TAG_ODRZUCENIA_AI))
    assert pierwszy == drugi


# ---------------------------------------------------------------------------
# 2. Normalizacja dyskryminatora i tolerancyjne parsowanie
# ---------------------------------------------------------------------------
def test_rozpakuj_zdejmuje_dyskryminator():
    odmowa, dane, powod = cl.rozpakuj_dyskryminator(
        {"typ": "tura", "opcje": TRZY_OPCJE})
    assert not odmowa and set(dane) == {"opcje"} and powod == ""


def test_rozpakuj_rozpoznaje_odmowe():
    odmowa, _dane, powod = cl.rozpakuj_dyskryminator(
        {"typ": "odrzucenie", "odrzucenie": pr.TAG_ODRZUCENIA_AI, "powod": "safety"})
    assert odmowa and powod == "safety"


def _przechwyc_dev_log(funkcja) -> str:
    """Zwraca to, co `funkcja` wypisala przez `core_llm._dev_log`."""
    import io

    bufor, stary = io.StringIO(), sys.stdout
    sys.stdout = bufor
    try:
        funkcja()
    finally:
        sys.stdout = stary
    return bufor.getvalue()


def test_powod_odmowy_trafia_do_logu_dewelopera():
    # 18.24.1: `powod` byl porzucany we wszystkich trzech wolaniach
    # (`odmowa, dane, _powod = ...`), mimo obietnicy w docstringu schematu.
    wynik = _przechwyc_dev_log(lambda: cl.zaloguj_odmowe("safety", "burza"))
    assert "burza" in wynik and "safety" in wynik


def test_log_odmowy_nie_wpuszcza_dowolnego_stringu_od_modelu():
    # Log jest z zalozenia NIETRESCIOWY (idzie do publicznego zgloszenia), a
    # `powod` wypelnia model - wiec wartosc spoza `enum` degraduje do "?".
    # Wartosc testowa po ANGIELSKU celowo: polska proza w zrodle `.py` podnosi
    # bramke `--bramka-py` (POSSIBLE|lingua:PL), a test niczego nie traci -
    # sprawdza filtrowanie, nie jezyk.
    wynik = _przechwyc_dev_log(
        lambda: cl.zaloguj_odmowe("the elevator scene felt wrong to me", "tura"))
    assert "powod=?" in wynik and "elevator" not in wynik


def test_rozpakuj_przepuszcza_odpowiedz_bez_typu():
    # Galaz `openai_compat` nie ma structured outputs - stare zachowanie zostaje.
    odmowa, dane, _ = cl.rozpakuj_dyskryminator({"opcje": []})
    assert not odmowa and dane == {"opcje": []}


def test_naprawa_zdejmuje_przecinek_wiszacy():
    assert json.loads(cl.napraw_luzny_json(JSON_Z_LOGU))["opcje"][0][
        "tytul"] == "Night chase"


def test_naprawa_zdejmuje_fence():
    assert json.loads(cl.napraw_luzny_json('```json\n{"a": 1}\n```')) == {"a": 1}
    assert json.loads(cl.napraw_luzny_json('```\n{"a": 1}\n```')) == {"a": 1}


def test_naprawa_nie_rusza_prozy_uzytkownika():
    # Naiwny regex `,(\s*[}\]])` zjadlby przecinek WEWNATRZ wartosci.
    proza = '{"opis": "They left, and then ] and , } remained.", "x": [1, 2]}'
    assert json.loads(cl.napraw_luzny_json(proza))["opis"] == (
        "They left, and then ] and , } remained.")
    esc = '{"opis": "She said \\"yes\\", then left,"}'
    assert json.loads(cl.napraw_luzny_json(esc))["opis"] == (
        'She said "yes", then left,')


def test_naprawa_nie_zmienia_poprawnego_json():
    assert cl.napraw_luzny_json('{"a": [1, 2]}') == '{"a": [1, 2]}'


# ---------------------------------------------------------------------------
# 3. Sampling: baseline, autocache, degradacja CELOWANA
# ---------------------------------------------------------------------------
def test_baseline_modeli_bez_temperatury():
    assert not cl.honoruje_temperature("claude-sonnet-5", 0.85)
    assert not cl.honoruje_temperature("claude-opus-5", 0.85)
    assert cl.honoruje_temperature("claude-sonnet-4-6", 0.85)
    assert cl.honoruje_temperature("claude-haiku-4-5", 0.85)
    # Nieznany endpoint compat dostaje szanse (nauczy sie po pierwszym 400).
    assert cl.honoruje_temperature("jakis-lokalny-model", 0.85)


def test_temperatura_domyslna_przechodzi_wszedzie():
    # 1.0 jest no-opem samplingu - API przyjmuje ja nawet od Sonneta 5.
    assert cl.honoruje_temperature("claude-sonnet-5", cl._TEMPERATURA_DOMYSLNA)


def test_rozpoznanie_winowajcy_400():
    assert cl._co_odrzucono(_Blad400(BLAD_TEMPERATURY)) == "temperature"
    assert cl._co_odrzucono(_Blad400(BLAD_SCHEMATU)) == "output_config"
    assert cl._co_odrzucono(_Blad400("something else entirely")) is None


def test_blad_temperatury_NIE_zdejmuje_schematu():
    """Sedno kontroli: gdyby degradacja byla kolejnosciowa, structured outputs
    nie zadzialalyby ani razu (domyslny model nie honoruje temperatury)."""
    klient, wyslane = klient_z([
        _Blad400(BLAD_TEMPERATURY),
        (json.dumps({"typ": "tura", "opcje": TRZY_OPCJE}), "end_turn"),
    ])
    wynik = ra.generuj_burze(klient, PRZEPIS_BURZA, SNAP, "Advance the plot.")
    assert len(wynik.opcje) == 3
    assert len(wyslane) == 2, f"prob={len(wyslane)}"
    assert "temperature" not in wyslane[1], "temperature was not dropped"
    assert "output_config" in wyslane[1], "the SCHEMA was dropped for no reason"


def test_blad_schematu_zdejmuje_tylko_schemat():
    klient, wyslane = klient_z([
        _Blad400(BLAD_SCHEMATU),
        (json.dumps({"opcje": TRZY_OPCJE}), "end_turn"),
    ])
    wynik = ra.generuj_burze(klient, PRZEPIS_BURZA, SNAP, "Advance the plot.")
    assert len(wynik.opcje) == 3
    assert "output_config" not in wyslane[1]


def test_nierozpoznany_400_konczy_sie_najprostszym_payloadem():
    klient, wyslane = klient_z([
        _Blad400("mysterious upstream complaint"),
        (json.dumps({"opcje": TRZY_OPCJE}), "end_turn"),
    ])
    ra.generuj_burze(klient, PRZEPIS_BURZA, SNAP, "Advance the plot.")
    assert "output_config" not in wyslane[1] and "temperature" not in wyslane[1]


def test_autocache_uczy_sie_nieznanego_modelu():
    """Reżyser z cudzym endpointem nie musi czekac na mikropatch baseline'u."""
    cl._NAUCZONE_BEZ_TEMPERATURY.discard("egzotyczny-model-7")
    assert cl.honoruje_temperature("egzotyczny-model-7", 0.85)
    cl.zapamietaj_odrzucenie_temperatury("egzotyczny-model-7")
    assert not cl.honoruje_temperature("egzotyczny-model-7", 0.85)


def test_autocache_nie_dubluje_baseline():
    # Plik ma trzymac tylko to, czego baseline NIE wie.
    cl._NAUCZONE_BEZ_TEMPERATURY.discard("claude-sonnet-5")
    cl.zapamietaj_odrzucenie_temperatury("claude-sonnet-5")
    assert "claude-sonnet-5" not in cl._NAUCZONE_BEZ_TEMPERATURY


def test_powtarzajacy_sie_ten_sam_400_nie_petli():
    klient, _wyslane = klient_z([_Blad400(BLAD_SCHEMATU)] * 4)
    try:
        ra.generuj_burze(klient, PRZEPIS_BURZA, SNAP, "Advance the plot.")
    except _Blad400:
        return
    raise AssertionError("the error must propagate instead of looping the degradation ladder")


# ---------------------------------------------------------------------------
# 3b. Kontrakt samplingu dzielony z RODZINA AUTOTLUMACZY (v18.24)
# ---------------------------------------------------------------------------
# `tlumacz_rdzen` (czterej bracia) i `buduj_wielojezyczne_ui` maja WLASNYCH
# klientow Anthropic, poza `cl.wywolaj_llm`, ale od v18.24 pytaja `core_llm`,
# czy w ogole wysylac `temperature`. Bez tego kazdy chunk kazdego jezyka placil
# jalowym round-tripem 400 - wszystkie szesc narzedzi jedzie domyslnie na
# `claude-sonnet-5`, a tlumaczenie wysyla NIEDOMYSLNE `temperature=0.0`.
ODP_TLUMACZENIA = (json.dumps({"translations": [{"id": 1, "target": "Talo"}]}), "end_turn")
POZYCJE_FI = [(1, "pole", "Dom")]


class _Blad429(Exception):
    """Limit zapytan, ktorego tresc PRZYPADKIEM wspomina o temperaturze."""

    status_code = 429


def _wywolaj_rdzen(model, odpowiedzi):
    """Jeden chunk przez `tlumacz_rdzen`; zwraca (mapa, wyslane_kwargs)."""
    import tlumacz_rdzen as tr

    wyslane = []
    sdk = _MockSDK(odpowiedzi, wyslane)
    mapa = tr.wywolaj_llm(
        sdk, model=model, system="Translate.", nazwa_celu="Suomi", kod="fi",
        pozycje=POZYCJE_FI, max_tokens=1000,
    )
    return mapa, wyslane


def test_czy_odrzucono_temperature_rozdziela_przypadki():
    assert cl.czy_odrzucono_temperature(_Blad400(BLAD_TEMPERATURY))
    # Blad schematu to TEN SAM kod 400 - pomylenie ich kosztowaloby structured outputs.
    assert not cl.czy_odrzucono_temperature(_Blad400(BLAD_SCHEMATU))
    # Sam komunikat nie wystarcza: 429 nie jest bledem struktury payloadu.
    assert not cl.czy_odrzucono_temperature(_Blad429(BLAD_TEMPERATURY))


def test_rodzina_nie_placi_jalowym_round_tripem_na_domyslnym_modelu():
    mapa, wyslane = _wywolaj_rdzen("claude-sonnet-5", [ODP_TLUMACZENIA])
    assert mapa == {1: "Talo"}
    assert len(wyslane) == 1, f"idle 400 round-trip was paid anyway: {len(wyslane)} calls"
    assert "temperature" not in wyslane[0]


def test_rodzina_nadal_wysyla_temperature_do_modelu_ktory_ja_honoruje():
    _mapa, wyslane = _wywolaj_rdzen("claude-sonnet-4-6", [ODP_TLUMACZENIA])
    import tlumacz_rdzen as tr

    assert wyslane[0]["temperature"] == tr.TEMPERATURA_TLUMACZENIA


def test_rodzina_uczy_sie_nieznanego_modelu_raz_a_nie_co_chunk():
    cl._NAUCZONE_BEZ_TEMPERATURY.discard("egzotyczny-endpoint-9")
    _mapa, pierwsze = _wywolaj_rdzen(
        "egzotyczny-endpoint-9", [_Blad400(BLAD_TEMPERATURY), ODP_TLUMACZENIA])
    assert len(pierwsze) == 2, "the reactive safety net did not retry"
    assert "temperature" in pierwsze[0] and "temperature" not in pierwsze[1]
    # Drugi chunk tego samego przebiegu juz NIE probuje - nauka jest trwala.
    _mapa2, drugie = _wywolaj_rdzen("egzotyczny-endpoint-9", [ODP_TLUMACZENIA])
    assert len(drugie) == 1, "the model rejection was not remembered"
    assert "temperature" not in drugie[0]


def test_blad_ktory_nie_dotyczy_temperatury_leci_wyzej_z_rodziny():
    try:
        _wywolaj_rdzen("claude-sonnet-4-6", [_Blad400(BLAD_SCHEMATU), ODP_TLUMACZENIA])
    except _Blad400:
        return
    raise AssertionError("a schema error must not be swallowed by the temperature retry")


def test_builder_ui_dostal_ten_sam_kontrakt_co_rdzen():
    import buduj_wielojezyczne_ui as bu

    wyslane = []
    sdk = _MockSDK([ODP_TLUMACZENIA], wyslane)
    mapa = bu.wywolaj_llm(sdk, "claude-sonnet-5", "Suomi", "fi", [(1, "Dom")])
    assert mapa == {1: "Talo"}
    assert len(wyslane) == 1 and "temperature" not in wyslane[0]


# ---------------------------------------------------------------------------
# 4. Sciezki odmowy i tresc bledu dla publicznego zgloszenia
# ---------------------------------------------------------------------------
def test_przypadek_z_logu_przechodzi_w_jednej_probie():
    klient, wyslane = klient_z([(JSON_Z_LOGU, "end_turn")])
    wynik = ra.generuj_burze(klient, PRZEPIS_BURZA, SNAP, "Advance the plot.")
    assert wynik.opcje[0].tytul == "Night chase"
    assert not wynik.odrzucone
    assert len(wyslane) == 1, f"prob={len(wyslane)}"


def test_stop_reason_refusal_to_odrzucenie_nie_blad_struktury():
    klient, wyslane = klient_z([("", cl.STOP_ODRZUCENIE)])
    wynik = ra.generuj_burze(klient, PRZEPIS_BURZA, SNAP, "Advance the plot.")
    assert wynik.odrzucone and len(wyslane) == 1


def test_galaz_odrzucenia_rozpoznana():
    odm = json.dumps({"typ": "odrzucenie", "odrzucenie": pr.TAG_ODRZUCENIA_AI,
                      "powod": "inne"})
    klient, _wyslane = klient_z([(odm, "end_turn")])
    assert ra.generuj_burze(klient, PRZEPIS_BURZA, SNAP, "Advance the plot.").odrzucone


def test_tresc_bledu_nadaje_sie_do_publicznego_zgloszenia():
    klient, wyslane = klient_z([("this is not json", "end_turn")] * 3)
    try:
        ra.generuj_burze(klient, PRZEPIS_BURZA, SNAP, "Advance the plot.")
    except BladStrukturyJSON as exc:
        tresc = str(exc)
        assert all(f"req_TEST{i}" in tresc for i in (1, 2, 3)), tresc
        assert "tokens_in=1234" in tresc
        assert "no content" in tresc
        for poufne in ("Aino", "Helsinki", "helsinki_story"):
            assert poufne not in tresc, f"user prose leaked into the log: {poufne}"
        # Wskazowka retry NIE moze cytowac parsera - to ona zapetlila zgloszenie.
        for kwargs in wyslane[1:]:
            wskazowka = kwargs["messages"][-1]["content"]
            assert "Expecting property name" not in wskazowka
            assert "JSONDecodeError" not in wskazowka
            assert "trailing comma" in wskazowka
        return
    raise AssertionError("BladStrukturyJSON was not raised")


def test_opcja_z_bialych_znakow_przechodzi_walidacje():
    """Dokumentuje LUKE, ktora musi zamknac GUI (`gui_rezyser`).

    `minLength: 1` liczy znaki PRZED `strip()`, wiec opcja z samych spacji jest
    dla schematu poprawna. Warstwa AI ja przepuszcza - i tak ma byc, bo to nie
    ona decyduje o prezentacji. Gdyby ten test zaczal FAILOWAC (schema odrzuca),
    filtr w `_on_wyslij_done_burza_json` mozna uproscic.
    """
    puste = [{"tytul": "   ", "opis": "   ", "cel_sceny": "   "}]
    klient, _wyslane = klient_z([
        (json.dumps({"typ": "tura", "opcje": puste}), "end_turn")])
    wynik = ra.generuj_burze(klient, PRZEPIS_BURZA, SNAP, "Advance the plot.")
    assert not wynik.odrzucone
    assert len(wynik.opcje) == 1
    assert not wynik.opcje[0].tytul.strip()


def test_notka_o_kardynalnosci_trafia_do_description():
    # `minItems`/`maxItems` sa zdejmowane ze schematu API, wiec model
    # dowiaduje sie o nich juz tylko z `description`.
    opis = ra.SCHEMA_BURZA_API["anyOf"][0]["properties"]["opcje"]["description"]
    assert "between 1 and 5" in opis, opis
    tytul = (ra.SCHEMA_BURZA_API["anyOf"][0]["properties"]["opcje"]
             ["items"]["properties"]["tytul"]["description"])
    assert "200 characters" in tytul and "Must not be empty" in tytul


def test_slad_niesie_model_i_odcisk_schematu():
    klient, _wyslane = klient_z([("this is not json", "end_turn")] * 3)
    try:
        ra.generuj_burze(klient, PRZEPIS_BURZA, SNAP, "Advance the plot.")
    except BladStrukturyJSON as exc:
        tresc = str(exc)
        assert "model=claude-sonnet-5" in tresc, tresc
        # Odcisk schematu: 10 znakow hex, identyczny w kazdej probie.
        odciski = {w.split("schema=")[1].split()[0]
                   for w in tresc.splitlines() if "schema=" in w}
        assert len(odciski) == 1, odciski
        assert odciski.pop() not in ("no", "unserializable")
        return
    raise AssertionError("BladStrukturyJSON was not raised")


def test_opis_srodowiska_jest_nietresciowy():
    opis = cl.opisz_srodowisko()
    assert "Python:" in opis
    assert "provider:" in opis
    # Zadnych sciezek ani nazw projektow.
    assert "helsinki" not in opis.lower() and "\\" not in opis


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
