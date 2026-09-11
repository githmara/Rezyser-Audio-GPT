"""Generator „wersji dla czytników ekranu" — warstwa logiki (bez GUI).

v16.1. Tło: silnik akcentów (``core_rezyser.zastosuj_akcenty_uniwersalne``) psuje
ortografię, by zasymulować obcy akcent. Dla ElevenLabs v3 to SZKODLIWE — psuta
ortografia myli detekcję języka modelu — dlatego tryb Skrypt ma
``stosuj_akcenty_fonetyczne: false`` i do v3 idzie czysty tekst (akcent bierze się
z PRÓBKI GŁOSU). Żeby feature psucia ortografii nie przepadł, ten moduł generuje
OSOBNĄ wersję HTML przeznaczoną dla czytników ekranu (NVDA itp.):

  * repliki postaci, które w Księdze Świata mają zdefiniowany akcent, dostają
    PSUTĄ ORTOGRAFIĘ (silnik akcentów) i są owinięte w ``<span lang="<iso>">``,
    co przełącza syntezator NVDA na właściwy język — mocny, akcentowany odczyt;
  * pozostali mówcy i narrator: czysty tekst w języku projektu;
  * audio-tagi ElevenLabs v3 (``[whispers]``, ``[sighs]``…) są USUWANE — czytnik
    ekranu nie ma ich czytać na głos;
  * nagłówki struktury (Prolog/Akt/Scena) → ``<h1>`` / ``<h2>``.

Most ElevenLabs i ten generator to dwa NIEZALEŻNE cele wyjścia tego samego
skryptu: v3 (audio, akcent z głosu) oraz HTML dla NVDA (akcent z ortografii +
``lang``). Wsparcie 9 języków, zgodnie z resztą projektu.

Moduł nie importuje ``wx``. Parser nagłówków/tagów współdzielony z
``core_elevenlabs`` (spójność z mostem); mapa akcentów i korekta ortografii z
``core_rezyser``.
"""

from __future__ import annotations

import html as _html
import re

import core_elevenlabs as ce
import core_rezyser as cr

# v19.1: hardkodowana mapa `_AKCENT_ISO` (10 nazw → ISO) USUNIĘTA. Była
# dublem pola `iso` z `dictionaries/<jezyk>/akcenty/<id>.yaml` — tego samego,
# które o języku głosu decyduje w Poliglocie — i tak samo jak tamten defekt
# nie znała języka projektu. Nazwę rozstrzyga teraz
# `core_rezyser.rozwiaz_nazwe_akcentu` (przyjmuje `id`, formę fleksyjną i
# natywny przymiotnik z `etykieta`), a ISO czytamy z YAML-a wariantu.

_RE_NAWIAS = re.compile(r"\[([^\]]+)\]")


def _usun_audio_tagi(dialog: str) -> str:
    """Usuwa z DIALOGU tokeny ``[audio-tag]`` (z :data:`core_rezyser.AUDIO_TAGS`).

    Działa na treści JUŻ po wycięciu tagu mówcy, więc każdy ``[...]`` to
    kandydat na audio-tag. Tokeny spoza ``AUDIO_TAGS`` zostają (np. gdyby autor
    wpisał coś w nawiasach celowo). Scala powstałe podwójne spacje.
    """
    def repl(m: re.Match) -> str:
        return "" if m.group(1).strip().lower() in cr.AUDIO_TAGS else m.group(0)

    bez = _RE_NAWIAS.sub(repl, dialog)
    return re.sub(r"[ \t]{2,}", " ", bez).strip()


def _iso_dla_mowcy(speaker_lower: str, mapa: dict[str, dict],
                   jezyk_projektu: str) -> str | None:
    """Zwraca kod języka GŁOSU dla akcentu mówcy albo ``None``.

    Dopasowanie mówcy do Księgi jak w silniku akcentów (podciąg w obie strony).
    Nazwę akcentu rozstrzyga `core_rezyser.rozwiaz_nazwe_akcentu`, a kod
    języka pochodzi z pola ``iso`` wariantu — z tego samego miejsca, z którego
    bierze go ścieżka zapisu Poligloty (v19.1). Wcześniej stała tu osobna,
    hardkodowana mapa nazw: dublowała dane, nie znała języka projektu i
    milczała dla nazw natywnych (`Finnish`, `isländisch`).
    """
    dane = next(
        (d for k, d in mapa.items() if k and (k in speaker_lower or speaker_lower in k)),
        None,
    )
    if not dane or not dane.get("nazwa"):
        return None
    id_akcentu = cr.rozwiaz_nazwe_akcentu(dane["nazwa"], jezyk_projektu)
    if not id_akcentu:
        return None
    cfg = cr.wariant_po_id(cr.TRYB_REZYSER, jezyk_projektu, id_akcentu) or {}
    iso = str(cfg.get("iso") or "").strip()
    return iso or None


def _szablon(lang: str, tytul: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{_html.escape(lang, quote=True)}">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{_html.escape(tytul)} — wersja dla czytników ekranu</title>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def generuj_html(
    tekst: str,
    lore_text: str,
    *,
    jezyk_projektu: str = "pl",
    tytul: str = "Skrypt",
) -> str:
    """Buduje HTML dla czytników ekranu ze skryptu ``[Mówca] treść`` + Księgi.

    Args:
        tekst:          Treść pliku skryptu (linie ``[Mówca] treść`` + nagłówki).
        lore_text:      Księga Świata — źródło mapowania postać → akcent.
        jezyk_projektu: Kod paczki/ISO języka skryptu (atrybut ``lang`` całości
                        + wybór ``dictionaries/<jezyk>/akcenty`` przy korekcie).
        tytul:          Nazwa projektu do ``<title>``.

    Returns:
        Kompletny dokument HTML (string). Repliki postaci z akcentem mają psutą
        ortografię + ``<span lang="<iso>">``; audio-tagi usunięte; nagłówki h1/h2.
    """
    mapa = cr.zbuduj_mape_akcentow(lore_text, jezyk_projektu)
    # Korekta ortografii na CAŁOŚCI — `zastosuj_akcenty_uniwersalne` psuje tylko
    # kwestie mówców z akcentem (reszta i nagłówki bez zmian), a audio-tagi
    # pomija (E2). Tagi mówcy zostają nietknięte, więc parsujemy je dalej.
    corrupted = cr.zastosuj_akcenty_uniwersalne(tekst, lore_text, jezyk_projektu)

    body: list[str] = []
    for linia in corrupted.splitlines():
        typ, czysty = ce._klasyfikuj_naglowek(linia)
        if typ == "chapter":
            body.append(f"  <h1>{_html.escape(czysty)}</h1>")
            continue
        if typ == "scene":
            body.append(f"  <h2>{_html.escape(czysty)}</h2>")
            continue
        m = ce._RE_TAG.match(linia)
        if not m:
            if linia.strip():
                body.append(f"  <p>{_html.escape(linia.strip())}</p>")
            continue
        mowca = (ce._wytnij_mowce(m.group(1)) or "").strip()
        dialog = _usun_audio_tagi(m.group(2))
        if not mowca or not dialog:
            continue
        iso = _iso_dla_mowcy(mowca.lower(), mapa, jezyk_projektu)
        dialog_html = _html.escape(dialog)
        if iso:
            dialog_html = f'<span lang="{iso}">{dialog_html}</span>'
        body.append(
            f"  <p><strong>{_html.escape(mowca)}:</strong> {dialog_html}</p>"
        )

    return _szablon(jezyk_projektu, tytul, "\n".join(body))
