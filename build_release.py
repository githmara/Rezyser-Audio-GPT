import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import dev_konsola
import generuj_dokumentacje


# =============================================================================
# STDOUT UTF-8 (fix dla Windowsa, gdzie domyślne cp1250 łamie się na emoji 🔍)
# =============================================================================
# Jeśli uruchomisz ten skrypt w CMD albo PowerShellu z polską lokalizacją,
# Python domyślnie używa kodowania cp1250 dla stdout — a to NIE umie znaków
# z płaszczyzny astralnej Unicode (emoji U+1F5xx). print("🔍 ...") wywala
# wtedy UnicodeEncodeError zanim w ogóle zdążymy wypisać cokolwiek innego.
# Od v18.25 jedna implementacja dla wszystkich dev-tooli → `dev_konsola`.
dev_konsola.skonfiguruj_stdout()


# =============================================================================
# WYKRYWANIE WERSJI (od 13.4 — single source of truth: plik VERSION w roocie)
# =============================================================================
# Historia:
#   * do 12.x: numer wersji podawany ręcznie przez input() — literówki, desynchronizacja.
#   * 13.0:    cross-check main.py::MainFrame.VERSION ↔ pierwsza linia instrukcja.txt
#              — działało, ale wymagało edycji DWÓCH miejsc przy każdym bumpie.
#   * 13.1:    wersja migruje w całości do dictionaries/pl/gui/ui.yaml::app.wersja,
#              czytana przez t("app.wersja"). Bumpa robisz w jednym pliku — ALE
#              po dodaniu kolejnych języków (en/fi/is/it/ru w 13.3) pojawiła się
#              regresja: app.wersja jest powielony w każdej paczce, co przy
#              bumpie skaluje się liniowo z liczbą języków (fi/is/it/ru tkwiło
#              przez dwa wydania na "13.1" — nikt nie pamiętał).
#   * 13.4:    numer wersji wyjeżdża do plain-text pliku VERSION w roocie.
#              W ui.yaml::app.wersja zostaje tylko placeholder typu
#              "{numer_wersji} – Wersja Wydawnicza". i18n.py auto-wstrzykuje
#              numer_wersji do każdego format() w t(), więc main.py i szablony
#              docs/manual.*.txt nadal działają bez zmian. Bumpa robisz wyłącznie
#              w pliku VERSION — niezależnie od liczby paczek językowych.

SCIEZKA_VERSION = os.path.join(os.path.dirname(__file__), "VERSION")
SCIEZKA_REQUIREMENTS = os.path.join(os.path.dirname(__file__), "requirements.txt")

# Mapowanie kodów ISO języków na wpisy Inno Setupa (nazwa + plik .isl).
#
# UWAGA: Ta mapa to lustro listy języków OFICJALNIE shippowanych z Inno Setup 6
# (29 paczek w `compiler:Languages\\` + angielski w `compiler:Default.isl`),
# nie listy języków naszego projektu. Pliki .isl należą do instalacji Inno
# Setupa, więc ich nazwy są stałe niezależnie od tego, które języki ma
# `dictionaries/`. Wniosek praktyczny: dodanie nowego języka bazowego do
# `dictionaries/<kod>/` NIE wymaga edycji tej mapy, dopóki ten język ma
# oficjalną paczkę Inno Setupa. Mapa jest pre-populowana, więc fr/es/de/ja/ko/...
# działają out-of-the-box.
#
# Świadomie pomijamy paczki NIEOFICJALNE z https://jrsoftware.org/files/istrans/
# (np. Icelandic, Esperanto, Estonian, SerbianCyrillic, SerbianLatin). Mają różny
# poziom utrzymania (Icelandic ostatni update 2020), więc deweloperzy musieliby
# je doinstalowywać ręcznie — a to przeczy idei "działa po świeżej instalacji
# Inno Setupa". Jeśli kiedyś potrzebny będzie nieoficjalny język, dopisać go tu
# z komentarzem "[unofficial]" i zadbać o instrukcję pobrania w docs.
#
# Fallback "skip with warning" obsługuje dwa scenariusze:
#   1. Język spoza puli Inno Setupa (np. esperanto bez ręcznej paczki) — kod
#      nieobecny w mapie.
#   2. Plik .isl jest w mapie, ale nie istnieje w instalacji u dewelopera
#      (bardzo stara wersja Inno Setupa albo własnoręcznie usunięta paczka).
#      Sprawdzane runtime przez `buduj_wpisy_inno` przed przekazaniem do iscc,
#      żeby nie dostać kryptycznego błędu Windows "nie można odnaleźć
#      określonego pliku" z głębi kompilatora.
INNO_LANG_MAP: dict[str, tuple[str, str]] = {
    "en":    ("english",             "compiler:Default.isl"),
    "ar":    ("arabic",              "compiler:Languages\\Arabic.isl"),
    "bg":    ("bulgarian",           "compiler:Languages\\Bulgarian.isl"),
    "ca":    ("catalan",             "compiler:Languages\\Catalan.isl"),
    "co":    ("corsican",            "compiler:Languages\\Corsican.isl"),
    "cs":    ("czech",               "compiler:Languages\\Czech.isl"),
    "da":    ("danish",              "compiler:Languages\\Danish.isl"),
    "de":    ("german",              "compiler:Languages\\German.isl"),
    "es":    ("spanish",             "compiler:Languages\\Spanish.isl"),
    "fi":    ("finnish",             "compiler:Languages\\Finnish.isl"),
    "fr":    ("french",              "compiler:Languages\\French.isl"),
    "he":    ("hebrew",              "compiler:Languages\\Hebrew.isl"),
    "hu":    ("hungarian",           "compiler:Languages\\Hungarian.isl"),
    "hy":    ("armenian",            "compiler:Languages\\Armenian.isl"),
    "it":    ("italian",             "compiler:Languages\\Italian.isl"),
    "ja":    ("japanese",            "compiler:Languages\\Japanese.isl"),
    "ko":    ("korean",              "compiler:Languages\\Korean.isl"),
    "nb":    ("norwegian",           "compiler:Languages\\Norwegian.isl"),
    "nl":    ("dutch",               "compiler:Languages\\Dutch.isl"),
    "pl":    ("polish",              "compiler:Languages\\Polish.isl"),
    "pt":    ("portuguese",          "compiler:Languages\\Portuguese.isl"),
    "pt-br": ("brazilianportuguese", "compiler:Languages\\BrazilianPortuguese.isl"),
    "ru":    ("russian",             "compiler:Languages\\Russian.isl"),
    "sk":    ("slovak",              "compiler:Languages\\Slovak.isl"),
    "sl":    ("slovenian",           "compiler:Languages\\Slovenian.isl"),
    "sv":    ("swedish",             "compiler:Languages\\Swedish.isl"),
    "ta":    ("tamil",               "compiler:Languages\\Tamil.isl"),
    "th":    ("thai",                "compiler:Languages\\Thai.isl"),
    "tr":    ("turkish",             "compiler:Languages\\Turkish.isl"),
    "uk":    ("ukrainian",           "compiler:Languages\\Ukrainian.isl"),
}


def zbierz_jezyki_bazowe() -> list[str]:
    """Zwraca kody języków bazowych z folderu dictionaries/.

    Kryterium: podfolder dictionaries/<kod>/ zawiera plik podstawy.yaml.
    Wynik posortowany alfabetycznie dla determinizmu outputu.
    """
    katalog = Path(__file__).parent / "dictionaries"
    kody = sorted(
        p.parent.name
        for p in katalog.glob("*/podstawy.yaml")
        if p.parent.is_dir()
    )
    return kody


def zbierz_jezyki_z_manualem(kody: list[str]) -> list[str]:
    """Filtr `kody` zostawiając tylko te, dla których istnieje docs/manual.<iso>.html.

    Sens: język bazowy `dictionaries/<kod>/podstawy.yaml` to konieczność, ale
    sam fakt jego obecności nie wystarcza, żeby instalator otwarł manual po
    instalacji — `docs/manual.<iso>.html` (od v18.8 HTML zamiast .txt) musi
    faktycznie istnieć w paczce.
    Dlaczego dwa odrębne kryteria: ktoś może dorzucić paczkę `podstawy.yaml`
    do `dictionaries/cs/` (np. czeski) zanim dotłumaczy `gui/dokumentacja/
    manual.yaml` przez `buduj_wielojezyczne_docs.py`. Wtedy `zbierz_jezyki_bazowe`
    zwróci `cs`, generator wyrzuci warning „pusty manual" ale i tak wytworzy
    plik, a Inno installer próbujący otworzyć `manual.cs.html` po instalacji
    pokaże user-friendly tekst typu "brak danych w sekcji X" — średnio
    elegancko. Lepiej: jeśli plik manual nie istnieje fizycznie, pomiń ten
    język w mapie Inno (instalator wystartuje w fallbacku en).

    Wywoływane PO `generuj_dokumentacje.generuj()` (krok 6 w main),
    żeby sprawdzenie istnienia odbywało się na świeżo wygenerowanych
    plikach, nie na potencjalnie nieaktualnych z poprzedniego buildu.
    """
    docs_dir = Path(__file__).parent / "docs"
    z_manualem: list[str] = []
    for kod in kody:
        manual_path = docs_dir / f"manual.{kod}.html"
        if manual_path.is_file():
            z_manualem.append(kod)
        else:
            print(f"   ⚠ Skipping language '{kod}' from Inno installer: "
                  f"'{manual_path.name}' missing in docs/ "
                  "(install `dictionaries/<kod>/gui/dokumentacja/manual.yaml` "
                  "and rerun generation).")
    return z_manualem


# =============================================================================
# Mapa etykiet CustomMessages dla WSZYSTKICH 30 jzk obecnych w `INNO_LANG_MAP`
# (1:1 z oficjalnymi paczkami Inno Setup 6 — english + 29 z Languages/).
# Pre-populated dla spójności:
# dodanie nowej paczki `dictionaries/<iso>/` przy istniejącym wpisie tu daje
# natywne etykiety od razu, bez modyfikacji build_release.py.
#
# Każdy wpis to:
#   inno_nazwa_jezyka → dict z 3 etykietami:
#     * AdditionalActionsGroup — nagłówek sekcji „Additional Tasks" obok
#       desktopicon (konwencja Inno: z dwukropkiem na końcu).
#     * OpenManualTaskDesc — etykieta CHECKBOX'a na stronie „Select
#       Additional Tasks", domyślnie zaznaczona (Tasks: openmanual).
#     * OpenManualRunDesc — etykieta CHECKBOX'a na stronie „Finish"
#       (Flags: postinstall), ten sam task ale krótszy wariant.
#
# Inno Setup w czasie buildu używa wpisu odpowiadającego językowi instalatora
# wybranemu przez użytkownika; jeśli wpisu zabraknie — fallback do english.*.
# Po rozszerzeniu na pełne 30 jzk, fallback (teoretycznie) nigdy nie powinien
# wystrzelić — chyba że ktoś doda nowy język do `INNO_LANG_MAP` zapominając
# tu dorzucić etykiet.
#
# Smart-filter w `buduj_blok_custom_messages`: iterujemy po `wpisy` (czyli
# tylko jzk wybrane przez `buduj_wpisy_inno` jako Inno-supported i obecne
# w `dictionaries/<kod>/`). Mapa nadmiarowa dla 22 jzk bez paczki (cs/sk/sv
# itd. — z 30 w mapie minus aktualne 8 obsługiwanych: en/pl/de/es/fi/fr/it/ru)
# ŻYJE TU CICHO — nigdy nie generuje wpisu w [CustomMessages] tmp
# installer'a, bo `buduj_blok_custom_messages` go po prostu nie odwiedza.
# Żaden warning nie leci, bo brak folderu `dictionaries/<iso>/` jest stanem
# domyślnym, nie problemem.
#
# Tłumaczenia idiomatyczne robione zachowawczo (proste słowa, nie próby
# literackie). Native speakerzy mogą zgłaszać szlif przez GitHub issue;
# fallback do english zawsze dostępny.
INNO_MANUAL_MESSAGES_MAP: dict[str, dict[str, str]] = {
    "english": {
        "AdditionalActionsGroup": "Additional actions:",
        "OpenManualTaskDesc":     "Open the user manual after installation",
        "OpenManualRunDesc":      "Open user manual",
    },
    "arabic": {
        "AdditionalActionsGroup": "إجراءات إضافية:",
        "OpenManualTaskDesc":     "افتح دليل المستخدم بعد التثبيت",
        "OpenManualRunDesc":      "افتح دليل المستخدم",
    },
    "armenian": {
        "AdditionalActionsGroup": "Լրացուցիչ գործողություններ․",
        "OpenManualTaskDesc":     "Բացել օգտատիրոջ ուղեցույցը տեղադրումից հետո",
        "OpenManualRunDesc":      "Բացել օգտատիրոջ ուղեցույցը",
    },
    "brazilianportuguese": {
        "AdditionalActionsGroup": "Ações adicionais:",
        "OpenManualTaskDesc":     "Abrir o manual do usuário após a instalação",
        "OpenManualRunDesc":      "Abrir o manual do usuário",
    },
    "bulgarian": {
        "AdditionalActionsGroup": "Допълнителни действия:",
        "OpenManualTaskDesc":     "Отвори ръководството за потребителя след инсталацията",
        "OpenManualRunDesc":      "Отвори ръководството за потребителя",
    },
    "catalan": {
        "AdditionalActionsGroup": "Accions addicionals:",
        "OpenManualTaskDesc":     "Obre el manual d'usuari després de la instal·lació",
        "OpenManualRunDesc":      "Obre el manual d'usuari",
    },
    "corsican": {
        "AdditionalActionsGroup": "Azzioni supplementari:",
        "OpenManualTaskDesc":     "Apri u manuale di l'utilizatore dopu l'installazione",
        "OpenManualRunDesc":      "Apri u manuale di l'utilizatore",
    },
    "czech": {
        "AdditionalActionsGroup": "Další akce:",
        "OpenManualTaskDesc":     "Otevřít uživatelskou příručku po instalaci",
        "OpenManualRunDesc":      "Otevřít uživatelskou příručku",
    },
    "danish": {
        "AdditionalActionsGroup": "Yderligere handlinger:",
        "OpenManualTaskDesc":     "Åbn brugervejledningen efter installation",
        "OpenManualRunDesc":      "Åbn brugervejledningen",
    },
    "dutch": {
        "AdditionalActionsGroup": "Aanvullende acties:",
        "OpenManualTaskDesc":     "Open de gebruikershandleiding na de installatie",
        "OpenManualRunDesc":      "Open de gebruikershandleiding",
    },
    "finnish": {
        "AdditionalActionsGroup": "Lisätoiminnot:",
        "OpenManualTaskDesc":     "Avaa käyttöohje asennuksen jälkeen",
        "OpenManualRunDesc":      "Avaa käyttöohje",
    },
    "french": {
        "AdditionalActionsGroup": "Actions supplémentaires :",
        "OpenManualTaskDesc":     "Ouvrir le manuel d'utilisation après l'installation",
        "OpenManualRunDesc":      "Ouvrir le manuel d'utilisation",
    },
    "german": {
        "AdditionalActionsGroup": "Zusätzliche Aktionen:",
        "OpenManualTaskDesc":     "Benutzerhandbuch nach der Installation öffnen",
        "OpenManualRunDesc":      "Benutzerhandbuch öffnen",
    },
    "hebrew": {
        "AdditionalActionsGroup": "פעולות נוספות:",
        "OpenManualTaskDesc":     "פתח את מדריך המשתמש לאחר ההתקנה",
        "OpenManualRunDesc":      "פתח את מדריך המשתמש",
    },
    "hungarian": {
        "AdditionalActionsGroup": "További műveletek:",
        "OpenManualTaskDesc":     "Felhasználói kézikönyv megnyitása a telepítés után",
        "OpenManualRunDesc":      "Felhasználói kézikönyv megnyitása",
    },
    "italian": {
        "AdditionalActionsGroup": "Azioni aggiuntive:",
        "OpenManualTaskDesc":     "Apri il manuale utente dopo l'installazione",
        "OpenManualRunDesc":      "Apri il manuale utente",
    },
    "japanese": {
        "AdditionalActionsGroup": "追加のアクション:",
        "OpenManualTaskDesc":     "インストール後にユーザーマニュアルを開く",
        "OpenManualRunDesc":      "ユーザーマニュアルを開く",
    },
    "korean": {
        "AdditionalActionsGroup": "추가 작업:",
        "OpenManualTaskDesc":     "설치 후 사용자 설명서 열기",
        "OpenManualRunDesc":      "사용자 설명서 열기",
    },
    "norwegian": {
        "AdditionalActionsGroup": "Tilleggshandlinger:",
        "OpenManualTaskDesc":     "Åpne brukerveiledningen etter installasjon",
        "OpenManualRunDesc":      "Åpne brukerveiledningen",
    },
    "polish": {
        "AdditionalActionsGroup": "Dodatkowe akcje:",
        "OpenManualTaskDesc":     "Otwórz instrukcję obsługi po instalacji",
        "OpenManualRunDesc":      "Otwórz instrukcję obsługi",
    },
    "portuguese": {
        "AdditionalActionsGroup": "Ações adicionais:",
        "OpenManualTaskDesc":     "Abrir o manual do utilizador após a instalação",
        "OpenManualRunDesc":      "Abrir o manual do utilizador",
    },
    "russian": {
        "AdditionalActionsGroup": "Дополнительные действия:",
        "OpenManualTaskDesc":     "Открыть руководство пользователя после установки",
        "OpenManualRunDesc":      "Открыть руководство пользователя",
    },
    "slovak": {
        "AdditionalActionsGroup": "Ďalšie akcie:",
        "OpenManualTaskDesc":     "Otvoriť používateľskú príručku po inštalácii",
        "OpenManualRunDesc":      "Otvoriť používateľskú príručku",
    },
    "slovenian": {
        "AdditionalActionsGroup": "Dodatna dejanja:",
        "OpenManualTaskDesc":     "Odpri uporabniški priročnik po namestitvi",
        "OpenManualRunDesc":      "Odpri uporabniški priročnik",
    },
    "spanish": {
        "AdditionalActionsGroup": "Acciones adicionales:",
        "OpenManualTaskDesc":     "Abrir el manual de usuario después de la instalación",
        "OpenManualRunDesc":      "Abrir el manual de usuario",
    },
    "swedish": {
        "AdditionalActionsGroup": "Ytterligare åtgärder:",
        "OpenManualTaskDesc":     "Öppna användarmanualen efter installationen",
        "OpenManualRunDesc":      "Öppna användarmanualen",
    },
    "tamil": {
        "AdditionalActionsGroup": "கூடுதல் செயல்கள்:",
        "OpenManualTaskDesc":     "நிறுவலுக்குப் பிறகு பயனர் கையேட்டைத் திற",
        "OpenManualRunDesc":      "பயனர் கையேட்டைத் திற",
    },
    "thai": {
        "AdditionalActionsGroup": "การกระทำเพิ่มเติม:",
        "OpenManualTaskDesc":     "เปิดคู่มือผู้ใช้หลังการติดตั้ง",
        "OpenManualRunDesc":      "เปิดคู่มือผู้ใช้",
    },
    "turkish": {
        "AdditionalActionsGroup": "Ek eylemler:",
        "OpenManualTaskDesc":     "Kurulum sonrası kullanıcı kılavuzunu aç",
        "OpenManualRunDesc":      "Kullanıcı kılavuzunu aç",
    },
    "ukrainian": {
        "AdditionalActionsGroup": "Додаткові дії:",
        "OpenManualTaskDesc":     "Відкрити посібник користувача після встановлення",
        "OpenManualRunDesc":      "Відкрити посібник користувача",
    },
}


def buduj_blok_kodu_iso(wpisy: list[tuple[str, str]], kody_z_manualem: list[str]) -> str:
    """Generuje pascal-case dla `GetManualISO()` z mapowania Inno → ISO.

    Args:
        wpisy:           Lista par `(inno_nazwa, plik_isl)` z `buduj_wpisy_inno()`.
        kody_z_manualem: Lista kodów ISO, dla których `docs/manual.<iso>.html`
                         faktycznie istnieje (z `zbierz_jezyki_z_manualem()`).

    Zwraca string typu:
        case ActiveLanguage() of
          'polish':  Result := 'pl';
          'german':  Result := 'de';
          ...
        else
          Result := 'en';
        end;
    """
    # Odwróć INNO_LANG_MAP: ('polish', '...isl') → 'pl'.
    nazwa_do_iso = {nazwa: iso for iso, (nazwa, _) in INNO_LANG_MAP.items()}

    linie_case = []
    for nazwa, _plik in wpisy:
        iso = nazwa_do_iso.get(nazwa)
        # Pomijamy en w case'ach — leci do `else Result := 'en'`.
        if iso == "en" or iso is None:
            continue
        # Pomijamy języki bez manuala (instalator wystartuje, ale w fallback'u).
        if iso not in kody_z_manualem:
            continue
        linie_case.append(f"    '{nazwa}': Result := '{iso}';")

    if not linie_case:
        # Pusta lista → tylko fallback do 'en'. Inno Pascal nie pozwala na
        # case bez żadnego selektora, więc tu degenerujemy do `Result := 'en'`.
        return "  Result := 'en';"

    case_body = "\n".join(linie_case)
    return (
        "  case ActiveLanguage() of\n"
        f"{case_body}\n"
        "  else\n"
        "    Result := 'en';\n"
        "  end;"
    )


def buduj_blok_custom_messages(wpisy: list[tuple[str, str]]) -> str:
    """Generuje sekcję `[CustomMessages]` dla 3 kluczy menu Pomoc per jzk Inno.

    Iteruje po `wpisy` (Inno-supported languages), dla każdego patrzy w
    `INNO_MANUAL_MESSAGES_MAP`. Jeśli język ma wpis — wstawia 3 linie:
    `<nazwa>.AdditionalActionsGroup=...`, `<nazwa>.OpenManualTaskDesc=...`,
    `<nazwa>.OpenManualRunDesc=...`. Jeśli brak wpisu (np. czeski/japoński
    bez tłumaczeń) — Inno użyje english.* fallback (nie generujemy nic dla
    tego języka, ale english zawsze jest pierwszy w pętli i pierwszy w
    Inno-language list → fallback działa).
    """
    linie: list[str] = []
    for nazwa, _plik in wpisy:
        slownik = INNO_MANUAL_MESSAGES_MAP.get(nazwa)
        if slownik is None:
            # Brak natywnych etykiet — fallback Inno do english.*.
            # Brak własnego wpisu w [CustomMessages] dla tego języka jest OK
            # (Inno nie potrzebuje placeholdera, sam wybiera english.*).
            continue
        for klucz, wartosc in slownik.items():
            linie.append(f"{nazwa}.{klucz}={wartosc}")
    return "\n".join(linie)


def odczytaj_wersje() -> str:
    """Wczytuje numer wersji z pliku ``VERSION`` w roocie projektu.

    Raises:
        RuntimeError: gdy plik nie istnieje albo jest pusty/białoznakowy.

    Returns:
        Numer wersji bez końcowego whitespace'a, np. ``"13.4-WIP"`` lub ``"13.4"``.
    """
    if not os.path.exists(SCIEZKA_VERSION):
        raise RuntimeError(
            f"VERSION file not found at {SCIEZKA_VERSION}. "
            "Since 13.4 it's the single source of truth for the version number — "
            "make sure the file exists in the repo root."
        )
    try:
        with open(SCIEZKA_VERSION, "r", encoding="utf-8") as fh:
            wartosc = fh.read().strip()
    except OSError as exc:
        raise RuntimeError(f"Failed to read {SCIEZKA_VERSION}: {exc}") from exc

    if not wartosc:
        raise RuntimeError(
            f"{SCIEZKA_VERSION} is empty. Write the version number into it "
            "(e.g. 13.4 or 13.4-WIP)."
        )
    return wartosc


def wczytaj_wymagane_pakiety() -> list[str]:
    """Czyta ``requirements.txt`` i zwraca listę nazw dystrybucji PyPI.

    Specyfikatory wersji (``==``, ``>=``), extras (``[fast]``) i markers
    (``; python_version >= "3.10"``) zostają obcięte — interesuje nas wyłącznie
    nazwa, którą poda się do ``importlib.metadata.version()``. Komentarze
    (``# ...``) i linie zaczynające się od ``-`` (np. ``-e ./mylib``,
    ``-r other.txt``) są pomijane — to konstrukcje pip-a, nie pakiety, więc
    nie ma sensu pytać o ich wersję.
    """
    if not os.path.exists(SCIEZKA_REQUIREMENTS):
        raise RuntimeError(
            f"requirements.txt not found at {SCIEZKA_REQUIREMENTS}. "
            "Cannot verify the runtime environment without the dependency manifest."
        )
    pakiety: list[str] = []
    with open(SCIEZKA_REQUIREMENTS, "r", encoding="utf-8") as fh:
        for linia in fh:
            tekst = linia.strip()
            if not tekst or tekst.startswith("#") or tekst.startswith("-"):
                continue
            nazwa = re.split(r"[<>=!~;\s\[]", tekst, 1)[0].strip()
            if nazwa:
                pakiety.append(nazwa)
    if not pakiety:
        raise RuntimeError(
            f"{SCIEZKA_REQUIREMENTS} contains no installable packages — "
            "release verification needs at least one entry to be meaningful."
        )
    return pakiety


def weryfikuj_runtime(sciezka_python: str) -> None:
    """Sprawdza, czy ``runtime/python.exe`` to faktyczny interpreter Pythona
    z kompletem zależności wydawniczych z ``requirements.txt``.

    Zamiast minimalnego ``print('OK')`` (które potwierdzało tylko, że proces się
    uruchamia, ale milczało o tym, czy wxpython/openai/lingua faktycznie są
    zainstalowane), odpalamy w runtime jednorazowy skrypt: dla każdego pakietu
    z manifestu pyta ``importlib.metadata.version()`` o numer wersji, a brak
    rzuca ``PackageNotFoundError``. Logika dystynkcji błędów na końcu rozróżnia
    dwa scenariusze:

    * **brak pakietów** (subprocess wraca z ``__MISSING__:...`` na stderr) →
      runtime istnieje, ale jest niegotowy do wydania; fix to
      ``runtime/python.exe -m pip install -r requirements.txt``;
    * **runtime/python.exe nie jest Pythonem** (timeout, non-zero exit bez
      sygnału ``__MISSING__``) → trzeba podmienić cały folder ``runtime/``.

    Używamy ``importlib.metadata.version`` zamiast ``importlib.import_module``,
    bo czyta tylko metadata pip-a — nie ładuje natywnych bibliotek wxpython
    (które bywają cięższe i potencjalnie psują output stderr). To wystarczy,
    żeby stwierdzić „pip uważa, że jest zainstalowane" — a to dokładnie to
    pytanie, na które chcemy odpowiedzi przed pakowaniem release'u.
    """
    try:
        pakiety = wczytaj_wymagane_pakiety()
    except RuntimeError as exc:
        print(f"❌ FATAL: {exc}")
        sys.exit(1)

    skrypt_check = (
        "import sys\n"
        "from importlib.metadata import version, PackageNotFoundError\n"
        f"pakiety = {pakiety!r}\n"
        "brakujace = []\n"
        "for nazwa in pakiety:\n"
        "    try:\n"
        "        print(f'   {nazwa} == {version(nazwa)}')\n"
        "    except PackageNotFoundError:\n"
        "        brakujace.append(nazwa)\n"
        "        print(f'   {nazwa} == [MISSING]')\n"
        "if brakujace:\n"
        "    sys.stderr.write('__MISSING__:' + ','.join(brakujace) + '\\n')\n"
        "    sys.exit(1)\n"
    )

    try:
        wynik = subprocess.run(
            [sciezka_python, "-c", skrypt_check],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        print("❌ FATAL: 'runtime/python.exe' stopped responding (timeout). It is probably not Python.")
        sys.exit(1)
    except Exception as exc:
        print(f"❌ FATAL: Cannot launch 'runtime/python.exe'. Details: {exc}")
        sys.exit(1)

    if wynik.stdout:
        print(wynik.stdout, end="")

    if wynik.returncode != 0:
        if wynik.stderr and "__MISSING__:" in wynik.stderr:
            brakujace = wynik.stderr.split("__MISSING__:", 1)[1].strip().rstrip(",")
            print()
            print(f"❌ FATAL: 'runtime/' is missing release dependencies: {brakujace}")
            print("The runtime exists, but it isn't release-ready yet. Install the manifest:")
            print(f"   {sciezka_python} -m pip install -r requirements.txt")
            sys.exit(1)
        print("❌ FATAL: 'runtime/python.exe' exists but does not behave like Python!")
        if wynik.stderr:
            print("Subprocess stderr:")
            print(wynik.stderr)
        print("Make sure you put a proper Portable Python build there, not an installer or some other program.")
        sys.exit(1)


_RE_INSTALLER_NAME = re.compile(r"^Rezyser_Audio_v(.+)_Installer\.exe$")
_RE_SHA256_NAME = re.compile(r"^Rezyser_Audio_v(.+)_Installer\.exe\.sha256$")


def sprzataj_opublikowane_instalatory(wersja_chroniona: str | None = None) -> None:
    """Usuwa lokalne `Rezyser_Audio_v*_Installer.exe` (oraz ich sidecary
    `.exe.sha256`, od v18.11), których odpowiednik jest już opublikowany jako
    asset GitHub Release (non-draft).

    Tło: każdy installer waży ~145 MB. Bez automatycznego sprzątania eksplorator
    szybko zarasta starymi binariami z podobnymi nazwami — utrudniona nawigacja,
    ryzyko uploadu nie tej wersji. GitHub trzyma całą historię release'ów z
    assetami pod tagiem, więc lokalna kopia po publikacji jest redundantna.
    Od v18.10 obok instalatora powstaje drugi asset — plik sumy kontrolnej
    `.exe.sha256` — sprzątany według tej samej zasady: leci tylko wtedy, gdy
    DOKŁADNIE ten plik jest już assetem opublikowanego Release (sidecar bez
    uploadu zostaje na dysku, bo lokalna kopia byłaby jedyną).

    Sprzątamy PRZED buildem: jeśli build się wywali, nic nie tracimy — usunięte
    zostały tylko pliki które i tak są w chmurze.

    `wersja_chroniona` (od mikropatcha bezpieczeństwa): instalator TEJ wersji NIE
    jest kasowany, nawet jeśli jest już opublikowany. Pre-build cleanup dostaje tu
    bieżącą wersję, żeby NIE wycinać pliku, którego pilnuje
    `sprawdz_czy_installer_juz_istnieje`. Wcześniej cleanup kasował go także gdy był
    opublikowany → guard refuse-overwrite przechodził → build BEZ bumpa cicho
    przebudowywał JUŻ OPUBLIKOWANĄ wersję, dając niereprodukowalny binarny artefakt
    rozjeżdżający się z assetem na GitHubie. `--cleanup-only` woła bez tego argumentu
    (świadome zwolnienie miejsca po publikacji — wtedy bieżący też leci).

    Wymaga `gh` CLI w PATH + autoryzacji. Brak `gh`, brak autoryzacji, brak
    sieci, malformed JSON, timeout → WARN i kontynuuj (cleanup jest wygodą, nie
    krytyczną częścią builda — fail open, nie blokujemy release flow).
    """
    if shutil.which("gh") is None:
        print("⚠ gh CLI not in PATH — skipping cleanup of published installers.")
        return

    # Kandydaci grupowani per WERSJA, nie per plik: exe i sidecar `.sha256`
    # tej samej wersji obsługuje JEDNO zapytanie gh, a osierocony sidecar
    # (exe sprzątnięte przez starszy cleanup sprzed v18.11) też jest łapany,
    # bo wersję wyprowadzamy niezależnie z obu wzorców nazw.
    kandydaci: dict[str, list[Path]] = {}
    for plik in Path(".").glob("Rezyser_Audio_v*_Installer.exe"):
        match = _RE_INSTALLER_NAME.match(plik.name)
        if match:
            kandydaci.setdefault(match.group(1), []).append(plik)
    for plik in Path(".").glob("Rezyser_Audio_v*_Installer.exe.sha256"):
        match = _RE_SHA256_NAME.match(plik.name)
        if match:
            kandydaci.setdefault(match.group(1), []).append(plik)

    if not kandydaci:
        return

    print("🧹 Cleaning up locally published installers...")
    for wersja in sorted(kandydaci):
        pliki = sorted(kandydaci[wersja], key=lambda p: p.name)
        nazwy = ", ".join(p.name for p in pliki)
        tag = f"v{wersja}"
        if wersja_chroniona is not None and wersja == wersja_chroniona:
            print(f"   • {nazwy}: current build version — protected by "
                  "overwrite guard, keeping.")
            continue
        try:
            wynik = subprocess.run(
                ["gh", "release", "view", tag, "--json", "isDraft,assets"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"   ⚠ Skipped {nazwy}: gh call failed ({exc}).")
            continue
        if wynik.returncode != 0:
            print(f"   • {nazwy}: no Release {tag} on GitHub — keeping.")
            continue
        try:
            dane = json.loads(wynik.stdout)
        except json.JSONDecodeError:
            print(f"   ⚠ Skipped {nazwy}: gh returned malformed JSON.")
            continue
        if dane.get("isDraft"):
            print(f"   • {nazwy}: Release {tag} still in DRAFT — keeping.")
            continue
        nazwy_assetow = {a.get("name") for a in (dane.get("assets") or [])}
        for plik in pliki:
            if plik.name not in nazwy_assetow:
                print(f"   • {plik.name}: Release {tag} published but this "
                      "asset not uploaded — keeping.")
                continue
            rozmiar_mb = plik.stat().st_size / (1024 * 1024)
            rozmiar_opis = f" ({rozmiar_mb:.0f} MB)" if rozmiar_mb >= 1 else ""
            try:
                plik.unlink()
            except OSError as exc:
                print(f"   ⚠ Failed to remove {plik.name}: {exc}.")
                continue
            print(f"   ✓ Removed {plik.name}{rozmiar_opis} — already on GitHub: {tag}.")
    print()


def sprawdz_czy_installer_juz_istnieje(nazwa_installer: str) -> None:
    """Przerywa budowanie, jeśli installer tej wersji już leży na dysku.

    Celowo NIE nadpisujemy automatycznie — dzięki temu najnowszy release
    zostaje na dysku do czasu, gdy deweloper świadomie go usunie lub
    przenumeruje wersję. Chroni przed sytuacją „zbudowałem w złej kolejności
    i nadpisałem wcześniejszy wariant, którego już nigdy nie odtworzę".

    Komunikaty po angielsku — od 13.1 cała infrastruktura buildowa mówi do
    dewelopera po angielsku, żeby ewentualni zagraniczni kontrybutorzy mieli
    zerowy próg wejścia. Polski interfejs aplikacji dla end-userów
    (dictionaries/pl/gui/ui.yaml) zostaje bez zmian.
    """
    if os.path.exists(nazwa_installer):
        print(f"❌ FATAL: Installer {nazwa_installer} already exists in this directory.")
        print()
        print("Pick one of three:")
        print(f"  (a) Bump the version in {SCIEZKA_VERSION}.")
        print(f"  (b) Move the existing {nazwa_installer} somewhere else "
              "(archive of previous releases).")
        print(f"  (c) Delete {nazwa_installer} on purpose if you want to rebuild it "
              "from the current state of the repo.")
        sys.exit(1)


def buduj_wpisy_inno(kody: list[str], katalog_inno: Path) -> list[tuple[str, str]]:
    """Mapuje kody języków bazowych na wpisy bloku ``[Languages]`` Inno Setupa.

    Pomija języki nieobecne w INNO_LANG_MAP (Inno Setup nie ma oficjalnej
    paczki — np. islandzki, esperanto, estoński; mapa świadomie ich nie
    zawiera, patrz komentarz przy INNO_LANG_MAP) oraz te, których plik ``.isl``
    nie istnieje w lokalnej instalacji (bardzo stara wersja Inno Setupa albo
    własnoręcznie usunięta paczka). Sprawdzanie runtime, żeby zamiast
    kryptycznego błędu Windows o nieznalezionym pliku dostać czytelny
    ``⚠ Skipping language``. Angielski leci pierwszy, żeby Inno Setup wybrał
    go jako fallback default.
    """
    wpisy: list[tuple[str, str]] = []
    kolejnosc = (["en"] if "en" in kody else []) + [k for k in kody if k != "en"]
    for kod in kolejnosc:
        if kod not in INNO_LANG_MAP:
            print(f"   ⚠ Skipping language '{kod}': not supported by Inno Setup.")
            continue
        nazwa, plik = INNO_LANG_MAP[kod]
        relatywna = plik.removeprefix("compiler:").replace("\\", "/")
        if not (katalog_inno / relatywna).exists():
            nazwa_pliku = relatywna.rsplit("/", 1)[-1]
            print(f"   ⚠ Skipping language '{kod}': '{nazwa_pliku}' missing in "
                  f"Inno Setup install ({katalog_inno}).")
            print("     → Update Inno Setup or grab the .isl from "
                  "https://jrsoftware.org/files/istrans/")
            continue
        wpisy.append((nazwa, plik))
    return wpisy



# =============================================================================
# GŁÓWNY FLOW BUDOWANIA WYDANIA (wywoływany tylko przez __main__)
# =============================================================================
# Owinięcie całego flow w funkcję main() + wywołanie pod __main__ daje dwie
# korzyści:
#   1. Funkcje walidacji wersji (odczytaj_wersje itp.) można
#      importować i testować w izolacji, bez wyzwalania guardu runtime/ ani
#      interaktywnego input().
#   2. Skrypt staje się zgodny z normalną konwencją Python (import-safe).


# Nazwa folderu/EXE produkowanego przez rezyser_audio.spec (COLLECT/EXE name).
# Single source of truth współdzielone z installer.iss (placeholder
# {#MyAppDistDir} podstawiany dynamicznie, patrz niżej).
NAZWA_DIST = "Rezyser Audio GPT"
SPEC_PLIK = "rezyser_audio.spec"


def buduj_pyinstaller() -> Path:
    """Buduje paczkę onedir PyInstallerem z ``rezyser_audio.spec``.

    Uruchamia ``python -m PyInstaller --noconfirm --clean rezyser_audio.spec``
    bieżącym interpreterem (zwykle ``.venv`` — to jego środowisko zostaje
    zamrożone, więc to ono musi mieć komplet zależności z requirements.txt).
    ``--clean`` czyści cache PyInstallera, ``--noconfirm`` nadpisuje ``dist/``
    bez interaktywnego pytania (build bywa odpalany przez agenta / CI).
    ``--log-level=WARN`` wycisza domyślny zalew linii INFO z milisekundowymi
    timestampami (każdy analizowany moduł = osobna linia) — w terminalu zostają
    tylko realne WARNING/ERROR.

    Świadomie NIE próbujemy automatycznie walidować z logu (ani z
    ``build/<spec>/warn-<spec>.txt``), czy zamrożony exe wystartuje: ten plik to
    setki fałszywych alarmów z bibliotek trzecich (samo ``numpy._core`` generuje
    ~180 „missing module", wszystkie nieszkodliwe), a NASZE moduły (``main``,
    ``gui_*``, ``core_*``) nie produkują tam ŻADNEGO wpisu — czyli sygnał tonie w
    szumie. Jedyny wiarygodny test (uruchomienie exe) łamie A11y (ciągłe GUI),
    więc sygnałem „apka w ogóle powstała" pozostaje obecność ``.exe`` (sprawdzana
    niżej). ``warn-<spec>.txt`` i tak powstaje — do ręcznego wglądu, gdyby kiedyś
    był potrzebny.

    Zwraca ścieżkę do ``dist/<NAZWA_DIST>/``. Przerywa build (exit 1), gdy spec
    nie istnieje, PyInstaller zwróci błąd albo brak oczekiwanego ``.exe``.
    """
    spec = Path(__file__).parent / SPEC_PLIK
    if not spec.exists():
        print(f"❌ FATAL: '{SPEC_PLIK}' not found at {spec}.")
        print("It defines the PyInstaller onedir/windowed build. Restore it from the repo.")
        sys.exit(1)

    print("🔨 Freezing the app with PyInstaller (onedir, windowed)...")
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--log-level=WARN", str(spec)],
            check=True,
        )
    except subprocess.CalledProcessError:
        print("❌ FATAL: PyInstaller returned a non-zero exit code. Build aborted.")
        print("Tip: run it manually for the full log:")
        print(f"   {sys.executable} -m PyInstaller --noconfirm --clean {SPEC_PLIK}")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ FATAL: PyInstaller is not installed in the current environment.")
        print(f"   {sys.executable} -m pip install -r requirements.txt")
        sys.exit(1)

    dist_dir = Path(__file__).parent / "dist" / NAZWA_DIST
    exe = dist_dir / f"{NAZWA_DIST}.exe"
    if not exe.is_file():
        print(f"❌ FATAL: PyInstaller finished but '{exe.name}' is missing in {dist_dir}.")
        print("Check the spec's EXE/COLLECT `name` matches NAZWA_DIST in build_release.py.")
        sys.exit(1)
    print(f"✅ PyInstaller build complete: {dist_dir}\n")
    return dist_dir


def skompletuj_dist(dist_dir: Path) -> None:
    """Kopiuje ``dictionaries/`` (bez ``gui/dokumentacja/``) + ``docs/`` do
    ``dist_dir``, czyniąc paczkę samowystarczalną (Opcja A: zasoby OBOK exe).

    Bez tego surowy ``dist/<app>/`` ma tylko exe + folder bundla ``runtime/`` —
    aplikacja STARTUJE, ale i18n nie znajduje słowników i pokazuje placeholdery
    ``[klucz]`` (a Reżyser/Opowieści nic nie tworzą). Po skompletowaniu: (a)
    ``installer.iss`` pakuje po prostu cały ``dist\\<app>\\*`` jednym wpisem,
    (b) ``dist/`` jest gotowy do ręcznego smoke-testu bez budowania instalatora.

    Kopia jest ŚWIEŻA przy każdym buildzie. Edytowalność seed-data (Manager
    Reguł) dotyczy ZAINSTALOWANEJ kopii obok exe, nie tej w ``dist/`` — rebuild
    nadpisuje tylko `dist/`, nie ruszając instalacji użytkownika.
    """
    root = Path(__file__).parent

    # Czyścimy katalogi docelowe PRZED kopią — deterministyczny wynik niezależnie
    # od pozostałości (np. po ręcznym smoke-teście dewelopera albo gdyby
    # PyInstaller nie wymiótł starych podfolderów). Bez tego stare/usunięte pliki
    # słownika mogłyby przetrwać w paczce.
    for podfolder in ("dictionaries", "docs"):
        cel = dist_dir / podfolder
        if cel.is_dir():
            shutil.rmtree(cel)

    src_docs = root / "docs"
    if src_docs.is_dir():
        # `.gitkeep` (znacznik utrzymania pustego folderu w gicie) i runtime'owy
        # `changelog.md` (zapisywany przy aktualizacji obok exe) to pliki dev /
        # user-data — nie pakujemy ich do paczki end-usera.
        shutil.copytree(
            src_docs, dist_dir / "docs",
            ignore=shutil.ignore_patterns(".gitkeep", "changelog.md"),
        )

    def _pomin_dokumentacje(katalog: str, nazwy: list[str]) -> list[str]:
        # Surowe szablony dev (dictionaries/<kod>/gui/dokumentacja/*.yaml) nie
        # wchodzą do paczki end-usera — analogicznie do dawnego Excludes w iss.
        if os.path.basename(katalog) == "gui" and "dokumentacja" in nazwy:
            return ["dokumentacja"]
        return []

    src_dict = root / "dictionaries"
    if src_dict.is_dir():
        shutil.copytree(
            src_dict, dist_dir / "dictionaries", ignore=_pomin_dokumentacje,
        )

    # VERSION NIE jest tu kopiowany: od v18.x to KOD/seed pakowany przez `datas`
    # w rezyser_audio.spec PROSTO DO bundla (`runtime/`), czytany z
    # `sciezki.KATALOG_ZASOBOW` (= sys._MEIPASS gdy frozen). Do v17.11 lądował
    # luzem obok exe (KATALOG_BAZOWY) — porzucone, bo nie jest danymi usera.
    print("   ✓ Completed dist payload: dictionaries/ + docs/ next to the exe (VERSION lives inside the bundle).\n")


def _parsuj_argumenty() -> argparse.Namespace:
    """Parsuje argumenty CLI build_release.py.

    Pojedyncza flaga ``-y/--yes`` — pomija interaktywny prompt potwierdzający
    przed kompilacją Inno Setupa. Reszta gardów (runtime/ check, VERSION
    czytany z pliku, sprawdzenie ISCC w PATH, refuse-overwrite istniejącego
    EXE o tej samej wersji) zostaje aktywna — `-y` pomija TYLKO ostatni
    human-in-the-loop, nie wyłącza walidacji.

    Use case: skrypt wywoływany przez CI/CD albo przez agenta automatyzacji
    (np. nowy workflow w GitHub Actions po draft-release, albo lokalny
    one-liner `python build_release.py -y` w batch'u). Default zachowanie
    (interaktywny prompt) trzymane dla developera odpalającego ręcznie.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Build the release Installer EXE for Reżyser Audio GPT. "
            "Reads VERSION (single source of truth), regenerates docs/*.html, "
            "and runs ISCC to compile installer.iss. Output: "
            "`Rezyser_Audio_v<VERSION>_Installer.exe` in the repo root."
        ),
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip the interactive 'Build X? (y/n):' prompt and proceed "
             "directly to compilation. A deliberate choice — every other "
             "validation (runtime/, VERSION, ISCC on PATH, refuse-overwrite) "
             "stays active; only the last human-in-the-loop step is skipped. "
             "Use case: CI/CD or automation by an agent.",
    )
    grupa_cleanup = parser.add_mutually_exclusive_group()
    grupa_cleanup.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Skip the pre-build cleanup of locally published installers. "
             "Default: cleanup runs before build, removing any "
             "`Rezyser_Audio_v*_Installer.exe` (and its `.exe.sha256` "
             "checksum sidecar) already published as a non-draft GitHub "
             "Release asset. Use this flag for diagnostic builds where you "
             "want to keep older EXEs on disk.",
    )
    grupa_cleanup.add_argument(
        "--cleanup-only",
        action="store_true",
        help="Run ONLY the cleanup step (delete locally cached installers "
             "and their .sha256 checksum files already published on GitHub) "
             "and exit. Skips runtime/ check, doc regeneration, ISCC "
             "compilation. Use case: free up disk space after a release "
             "without rebuilding.",
    )
    return parser.parse_args()


# =============================================================================
# STRAŻNIK FLAG DEBUG (od 18.3 — siatka bezpieczeństwa przed wyciekiem do paczki)
# =============================================================================
# Niektóre funkcje techniczne są ukryte za stałą boolean zaszytą w źródle
# (NIE env-var, NIE user-facing), domyślnie False. Deweloper przełącza ją na
# True, by poeksperymentować lokalnie (np. ręczna edycja `.game.json`), i łatwo
# zapomnieć cofnąć przed buildem — wtedy ryzykowna funkcja trafiłaby do paczki
# end-usera. Ten strażnik twardo odmawia buildu, gdy którakolwiek flaga = True.
# Druga warstwa (hook pre-commit w `hooks/pre-commit`) pilnuje commitów; tutaj
# pilnujemy samego buildu — niezależnie, czy hook był aktywny.
#
# Lista rozszerzalna: (plik, regex wykrywający stan "niebezpieczny", etykieta).
_FLAGI_DEBUG: list[tuple[str, str, str]] = [
    (
        "gui_opowiesci.py",
        r"^EDYCJA_STANU_GRY_WIDOCZNA\s*=\s*True",
        "EDYCJA_STANU_GRY_WIDOCZNA",
    ),
]


def _weryfikuj_flagi_debug() -> None:
    """Aborts the build if any debug flag is left enabled in the source.

    Mirrors the doc-validation gate above: a standalone concern in dev, but a
    FATAL at build time so the installer never ships a debug feature exposed.
    """
    print("🔍 Verifying debug flags are disabled...")
    znalezione: list[str] = []
    for nazwa_pliku, wzorzec, etykieta in _FLAGI_DEBUG:
        sciezka = Path(__file__).resolve().parent / nazwa_pliku
        try:
            tekst = sciezka.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"❌ FATAL: cannot read {nazwa_pliku} to verify debug flags: {exc}")
            sys.exit(1)
        if re.search(wzorzec, tekst, flags=re.MULTILINE):
            znalezione.append(f"   • {etykieta} = True  ({nazwa_pliku})")

    if znalezione:
        print("❌ FATAL: a debug flag is still enabled — refusing to build.")
        print("These flags expose technical/experimental features to the end user")
        print("and must be False in a release build. Set them back, then rebuild")
        print("(the pre-commit hook in hooks/ auto-resets them on commit).")
        for linia in znalezione:
            print(linia)
        sys.exit(1)

    print("✅ Debug flags verified (all disabled).\n")


def _policz_sha256(sciezka: Path) -> str:
    """SHA256 pliku, czytany blokami (instalator ma dziesiątki MB)."""
    skrot = hashlib.sha256()
    with open(sciezka, "rb") as fh:
        for blok in iter(lambda: fh.read(1024 * 1024), b""):
            skrot.update(blok)
    return skrot.hexdigest()


def _regeneruj_dokumentacje_lub_przerwij() -> None:
    """Regeneruje docs/<id>.<kod>.html z szablonów YAML albo przerywa build.

    We call the generator in-process (same Python process, no subprocess) —
    the module has its own UTF-8 fix and does not need a fresh session.
    This guarantees the installer ships fresh docs/ even when the developer
    forgot to run the generator manually after editing a template.
    The generator is a Polish-language developer tool (its warnings read
    "⚠️  …brakujące placeholdery…"), whereas this build log is English by design
    (since 13.1 — zero entry bar for foreign contributors). A bare call would
    leak Polish lines into the English build output and, worse, would happily
    build on top of broken docs if the developer skipped the standalone
    `--waliduj` step.

    So we (a) run with cicho=True to mute the routine ✅/ℹ️ chatter, (b) capture
    whatever the generator still prints (the deep warnings about malformed
    YAML / wrong-typed sections aren't gated by cicho), (c) collect unresolved
    placeholders structurally via `zbieraj_brakujace`, and (d) ESCALATE any of
    those signals — captured warning text, collected placeholders, or an empty
    result set — to a FATAL that aborts the build. In a standalone run these
    are warnings; in a release build they are fatal, so an installer never
    ships docs/*.html that didn't validate. The Polish detail only ever appears
    indented under the English FATAL header (diagnostics for the dev), never in
    the normal flow.
    """
    print("🔍 Regenerating documentation (YAML templates → docs/*.html)...")
    brakujace_docs: dict[str, list[str]] = {}
    drafty_docs: dict[str, str] = {}
    bufor_generatora = io.StringIO()
    with contextlib.redirect_stdout(bufor_generatora):
        wyniki_docs = generuj_dokumentacje.generuj(
            cicho=True, zbieraj_brakujace=brakujace_docs, zbieraj_drafty=drafty_docs,
        )
    szum_generatora = bufor_generatora.getvalue().strip()

    # RAW-HTML gate (od v18.10): do v18.9 bramka żyła tylko w `--waliduj`,
    # a build wołał gołe generuj() — instalator mógł wypuścić .html z tagiem
    # spoza whitelisty renderera (surowy `<fragment>` z szablonu, który
    # przeglądarka POŁYKA razem z treścią). Ten sam skan co w waliduj().
    obce_tagi_docs: dict[str, list[str]] = {}
    for sciezka_html in wyniki_docs:
        if sciezka_html.suffix != ".html":
            continue
        obce = generuj_dokumentacje._obce_tagi_w_html(
            sciezka_html.read_text(encoding="utf-8"))
        if obce:
            obce_tagi_docs[sciezka_html.name] = obce

    # Draftowe / niekanoniczne nagłówki = bezwarunkowy FATAL (guard od v18.6).
    # generuj() w cicho=True pomija takie pliki MILCZĄCO (sygnał wyłącznie
    # strukturalny przez `drafty_docs`), więc nie liczymy na `szum_generatora` —
    # warunek bije wprost po zebranym słowniku. Chroni przed wpuszczeniem do
    # paczki maszynowego draftu, którego maintainer zapomniał sfinalizować.
    if brakujace_docs or drafty_docs or szum_generatora or obce_tagi_docs \
            or not wyniki_docs:
        print("❌ FATAL: documentation regeneration is not clean — refusing to build.")
        print("In a standalone run these are warnings; in a release build they are")
        print("fatal, so the installer never ships docs/*.html that didn't validate.")
        print("Fix the source, then re-run `python generuj_dokumentacje.py --waliduj`.")
        if not wyniki_docs:
            print("   • No documentation files were generated at all "
                  "(missing dictionaries/<kod>/gui/dokumentacja/?).")
        if drafty_docs:
            print("   Draft / non-canonical headers (run the matching builder "
                  "with --finalizuj after reviewing):")
            for nazwa, powod in sorted(drafty_docs.items()):
                print(f"      • {nazwa}: {powod}")
        if brakujace_docs:
            print("   Unresolved placeholders:")
            for nazwa, klucze in sorted(brakujace_docs.items()):
                wypis = ", ".join("{" + k + "}" for k in klucze)
                print(f"      • {nazwa}: {wypis}")
        if obce_tagi_docs:
            print("   Raw HTML tags beyond the renderer's whitelist "
                  "(wrap the `<fragment>` in backticks in the template):")
            for nazwa, tagi in sorted(obce_tagi_docs.items()):
                print(f"      • {nazwa}: {tagi}")
        if szum_generatora:
            print("   Generator warnings:")
            for linia in szum_generatora.splitlines():
                print(f"      {linia}")
        sys.exit(1)

    print(f"✅ Documentation regenerated ({len(wyniki_docs)} files, clean).\n")


def main(args: argparse.Namespace | None = None) -> None:
    # Allow main() to be called from CLI (with parser) or programmatically
    # (with `args=argparse.Namespace(yes=False, no_cleanup=False,
    # cleanup_only=False)` lub None → default).
    if args is None:
        args = argparse.Namespace(yes=False, no_cleanup=False, cleanup_only=False)

    # --- CLEANUP-ONLY MODE (no build, no runtime/ guard) ---
    # Skrót po publikacji żeby zwolnić miejsce bez ponownego uruchamiania
    # weryfikacji runtime/ i kompilacji Inno. Bezpieczny niezależnie od tego
    # czy runtime/ leży na dysku.
    if getattr(args, "cleanup_only", False):
        sprzataj_opublikowane_instalatory()
        return

    # --- (v17.0) PyInstaller zastąpił portable runtime/python.exe ---
    # Dawniej tu stał guard sprawdzający `runtime/python.exe` + `weryfikuj_runtime()`
    # (czy portable Python istnieje i ma komplet zależności z requirements.txt).
    # Po migracji na PyInstaller paczka jest budowana ze środowiska, w którym
    # uruchamiamy ten skrypt (zwykle `.venv`), a interpreter + zależności wchodzą
    # do bundla. Walidacja środowiska sprowadza się więc do tego, czy bieżący
    # Python ma PyInstaller — sprawdzane w `buduj_pyinstaller()` niżej.

    # 1. Read the release version (single source of truth: VERSION in repo root).
    print(f"🔍 Detecting release version ({SCIEZKA_VERSION})...")
    try:
        wersja = odczytaj_wersje()
    except RuntimeError as exc:
        print(f"❌ FATAL (version read): {exc}")
        sys.exit(1)
    print(f"✅ Version loaded: {wersja}\n")

    nazwa_installer = f"Rezyser_Audio_v{wersja}_Installer.exe"

    # 4a. Pre-build cleanup of locally cached installers already on GitHub
    # (od v18.11 razem z sidecarami `.exe.sha256` — inaczej po każdym wydaniu
    # zostawał osierocony plik sumy kontrolnej sprzątniętego exe).
    # Każdy installer waży ~145 MB; bez tego eksplorator zarasta podobnymi
    # nazwami po kilku patchach. Cleanup leci PRZED `sprawdz_czy_installer_juz_istnieje`
    # (krok 4b niżej), ale dostaje `wersja_chroniona=wersja` — instalator BIEŻĄCEJ
    # wersji NIE jest kasowany, więc guard refuse-overwrite zawsze ma co bronić.
    # (Wcześniej cleanup kasował go także gdy był opublikowany → guard przechodził
    # → build bez bumpa cicho przebudowywał OPUBLIKOWANĄ wersję, dając binarny
    # artefakt rozjeżdżający się z assetem na GitHubie.) Stare opublikowane wersje
    # dalej lecą. Flaga `--no-cleanup` pomija ten krok dla buildów diagnostycznych.
    if not getattr(args, "no_cleanup", False):
        sprzataj_opublikowane_instalatory(wersja_chroniona=wersja)

    # 4b. Refuse to overwrite a previous installer of the same version.
    # Od v15.2.5: ZIP Portable został wycięty z release flow (single deployment
    # path — patrz RELEASE_NOTES.md::15.2.5). Pozostaje tylko Installer EXE,
    # który i tak instaluje do per-user %LocalAppData%\Programs (PrivilegesRequired=
    # lowest w installer.iss), więc nie wymaga praw administratora i jest de facto
    # equivalent funkcjonalny dawnego ZIP-a, bez ryzyka autoupdate'u nadpisującego
    # nieznaną lokalizację.
    sprawdz_czy_installer_juz_istnieje(nazwa_installer)

    # 5. Last-chance developer confirmation before we actually compile.
    # Flaga -y/--yes pomija ten prompt całkowicie (CI/CD lub automatyzacja
    # agentowa) — pierwszym widocznym sygnałem startu buildu jest komunikat
    # „Regenerating documentation…" z kroku 6. Bez -y developer manualny musi
    # potwierdzić y/n/t (tak/nie habit pl).
    if not args.yes:
        odp = input(f"Build {nazwa_installer}? (y/n): ").strip().lower()
        if odp not in ("y", "t"):   # `t` kept as alias — historical tak/nie habit
            print("Build aborted.")
            sys.exit(0)

    # 6a. Leak gate (od v18.5.3): scan the docs templates for untranslated Polish
    # text against the accepted baseline. The finalization-header guard — now run
    # LATER (step 6d, right before the freeze) — only proves a file was *finalized*,
    # not that its content is leak-free, so this closes
    # that gap (a "finalized" pack could still ship Polish; see RELEASE_NOTES v18.5.2
    # "Co nie weszło"). A new or shifted leak beyond audyt_leakow_baseline.json is a
    # FATAL. Lazy import with graceful degradation: a contributor building without
    # the `lingua` dev dependency gets a loud warning, not a blocked build (the
    # maintainer's canonical release always has lingua, so they get the real gate).
    print("🔍 Leak gate: scanning docs templates for Polish-text leaks...")
    try:
        import audyt_leakow
    except ImportError:
        print("⚠️  audyt_leakow/lingua not available — leak gate SKIPPED. "
              "Install `lingua` for the full release gate.\n")
    else:
        wynik_leak = audyt_leakow.bramka_docs()
        # Paczka poza `lingua` (język, którego detektor nie zna) jest skanowana
        # z węższym zestawem klas. Wydanie NIE jest blokowane — ale przemilczenie
        # tego przy zielonej bramce byłoby obietnicą pokrycia, którego nie ma.
        for kod, powod in sorted(wynik_leak.pokrycie_obnizone.items()):
            print(f"⚠️  Leak gate, reduced coverage for `{kod}`: {powod}. "
                  f"Class A (whole-line drift) is NOT checked for this pack.")
        if wynik_leak.pominieto:
            print(f"⚠️  Leak gate skipped: {wynik_leak.powod_pominiecia}. "
                  "Install `lingua` for the full release gate.\n")
        elif not wynik_leak.czysto:
            ile = sum(len(v) for v in wynik_leak.nowe.values())
            print(f"❌ FATAL: {ile} Polish-text leak(s) ABOVE the baseline in "
                  f"{len(wynik_leak.nowe)} section(s) — refusing to build.")
            print("A 'finalized' header does not prove leak-free content. Fix the "
                  "leaked fragment(s) in the template, or — if this is a deliberate,")
            print("legitimate content change — regenerate the baseline with "
                  "`python audyt_leakow.py --zapisz-baseline` and commit the diff.")
            for nazwa, powody in sorted(wynik_leak.nowe.items()):
                print(f"      • {nazwa}: {', '.join(powody)}")
            sys.exit(1)
        else:
            print(f"✅ No leaks beyond the baseline ({audyt_leakow.BASELINE_PATH.name}).\n")

        # 6b. Source `.py` hard-code gate (od v18.5.4): scan application modules for
        # user/LLM-facing Polish string literals that bypass i18n/recipe YAML, against
        # a separate accepted baseline (audyt_leakow_py_baseline.json). Same baseline
        # pattern as the docs gate: a new hard-code beyond the baseline (especially any
        # LIKELY — a string reaching a wx Set*/MessageBox sink or an LLM payload) is a
        # FATAL. `audyt_leakow` already imported above; reuse it (still lazy/graceful).
        print("🔍 Source gate: scanning *.py for user/LLM-facing Polish hard-codes...")
        wynik_py = audyt_leakow.bramka_py()
        if wynik_py.pominieto:
            print(f"⚠️  Source gate skipped: {wynik_py.powod_pominiecia}. "
                  "Install `lingua` for the full release gate.\n")
        elif not wynik_py.czysto:
            ile = sum(len(v) for v in wynik_py.nowe.values())
            print(f"❌ FATAL: {ile} Polish hard-code(s) ABOVE the baseline in "
                  f"{len(wynik_py.nowe)} file(s) — refusing to build.")
            print("Move the string into i18n (`t()`) / a recipe YAML, or — if it is a "
                  "deliberate, by-design hard-code — regenerate the baseline with "
                  "`python audyt_leakow.py --zapisz-baseline-py` and commit the diff.")
            for nazwa, powody in sorted(wynik_py.nowe.items()):
                for p in powody:
                    print(f"      • {nazwa}: {p}")
            sys.exit(1)
        else:
            print(f"✅ No hard-codes beyond the baseline ({audyt_leakow.BASELINE_PY_PATH.name}).\n")

        # 6b'. CONTRIBUTING language contract in the dev tools (v18.24) — argparse
        # texts and ❌/⚠️ lines that a non-Polish contributor has to read. This one
        # is deliberately NON-FATAL: it guards the barrier to entry, not the
        # correctness of the package, and a Polish help text ships nothing broken
        # to the end user (dev tools are not in the bundle at all). Printed as a
        # reminder so the regression is noticed at release time rather than by a
        # contributor months later — which is exactly how the 60 helps accumulated.
        print("🔍 Contract gate: scanning dev tools for Polish CLI text, ❌/⚠️ lines "
              "and abort messages...")
        wynik_kontrakt = audyt_leakow.bramka_kontraktu()
        if wynik_kontrakt.pominieto:
            print(f"⚠️  Contract gate skipped: {wynik_kontrakt.powod_pominiecia}.\n")
        elif not wynik_kontrakt.czysto:
            ile = sum(len(v) for v in wynik_kontrakt.nowe.values())
            print(f"⚠️  {ile} contract violation(s) ABOVE the baseline in "
                  f"{len(wynik_kontrakt.nowe)} file(s) — NOT blocking the build.")
            print("   Run `python audyt_leakow.py --bramka-kontrakt` for the list.\n")
        else:
            print(f"✅ Dev-tool contract clean "
                  f"({audyt_leakow.BASELINE_KONTRAKT_PATH.name}).\n")

    # 6c. Verify no debug flag leaked into the build (e.g. EDYCJA_STANU_GRY_WIDOCZNA).
    _weryfikuj_flagi_debug()

    # 6d. Regenerate end-user documentation (docs/<id>.<kod>.html) — DELIBERATELY the
    # LAST gate before the freeze (reordered v18.x). Doc regeneration MUTATES
    # docs/*.html and bakes in the (possibly bumped) VERSION, so running it only AFTER
    # the cheap, read-only gates above (leak/py/debug) means a failing gate aborts the
    # build WITHOUT leaving a regenerated-but-unbuilt docs/ diff behind. All those gates
    # scan YAML/`.py` source (independent of regenerated docs); the only consumer of
    # fresh docs/manual.<iso>.html is the Inno step (8 below), still after us.
    _regeneruj_dokumentacje_lub_przerwij()

    # 7. Freeze the app with PyInstaller (onedir, windowed) → dist/<app>/,
    # następnie skompletuj paczkę (dictionaries/ + docs/ OBOK exe), żeby dist/
    # był samowystarczalny. installer.iss pakuje potem cały dist/<app>/* jednym
    # wpisem, więc PyInstaller + skompletowanie MUSZĄ zakończyć się przed ISCC.
    dist_dir = buduj_pyinstaller()
    skompletuj_dist(dist_dir)

    # 8. Build the Installer EXE.
    iscc_exe = shutil.which("iscc")
    if iscc_exe is None:
        print("❌ FATAL: 'iscc' not found in PATH.")
        print("Install Inno Setup (https://jrsoftware.org/isinfo.php) and make sure")
        print("its folder (e.g. C:\\Program Files (x86)\\Inno Setup 6) is in your PATH.")
        sys.exit(1)

    # Collect base language codes and map them to Inno Setup .isl entries.
    # `katalog_inno` derives from iscc_exe (it sits in the Inno Setup install
    # root) — we use it to verify each .isl file is actually present before
    # handing the path to the compiler.
    katalog_inno = Path(iscc_exe).parent
    kody = zbierz_jezyki_bazowe()
    # Krzyżowa walidacja: język musi mieć NIE TYLKO `dictionaries/<kod>/
    # podstawy.yaml`, ale też `docs/manual.<iso>.html` w paczce (regenerowany
    # w kroku 6d wyżej). Bez manuala instalator nie ma czego otworzyć po
    # kliknięciu Finish — pomiń ten język z mapy Inno.
    kody_z_manualem = zbierz_jezyki_z_manualem(kody)
    wpisy = buduj_wpisy_inno(kody_z_manualem, katalog_inno)

    # Trzy dynamiczne sekcje wstrzykiwane do tmp installer.iss:
    #   [Languages]      — lista jzk Inno z .isl-em w lokalnej instalacji
    #   [Code]           — funkcja GetManualISO z case'ami ActiveLanguage()
    #                      mapującymi inno_nazwa → kod_iso pliku manual.<iso>.html
    #   [CustomMessages] — etykiety menu Pomoc (AdditionalActionsGroup +
    #                      OpenManualTaskDesc + OpenManualRunDesc) per jzk
    # Wszystkie 3 odbudowane z `wpisy` jako pojedynczego źródła prawdy — żeby
    # dodanie języka wymagało tylko (a) wpisu w INNO_LANG_MAP, (b) wpisu w
    # INNO_MANUAL_MESSAGES_MAP, (c) szablonu dokumentacji.
    blok_languages = "\n".join(
        f'Name: "{nazwa}";  MessagesFile: "{plik}"'
        for nazwa, plik in wpisy
    )
    blok_kod_iso = buduj_blok_kodu_iso(wpisy, kody_z_manualem)
    blok_custom_messages = buduj_blok_custom_messages(wpisy)

    # Read installer.iss and replace 3 sekcje dynamicznie. installer.iss
    # to placeholder w repo (dla syntax check przez `iscc` bezpośrednio +
    # czytelnego stanu w diff'ach) — to co tu wstrzykujemy NADPISUJE jego
    # bloki [Languages], [Code] i [CustomMessages].
    sciezka_iss = Path(__file__).parent / "installer.iss"
    sciezka_tmp = Path(__file__).parent / "_installer_tmp.iss"
    iss_tresc = sciezka_iss.read_text(encoding="utf-8")

    # Sekcja [Languages] — split around [Languages] … [Setup].
    przed, reszta = iss_tresc.split("[Languages]", 1)
    _, po_setup = reszta.split("[Setup]", 1)
    iss_etap_1 = f"{przed}[Languages]\n{blok_languages}\n\n[Setup]{po_setup}"

    # Sekcja [Code] — split around [Code] … [CustomMessages] (lub do EOF
    # jeśli to ostatnia sekcja). installer.iss MA [Code] przed [CustomMessages]
    # w stałej kolejności.
    if "[Code]" in iss_etap_1 and "[CustomMessages]" in iss_etap_1:
        przed_kodu, reszta_kodu = iss_etap_1.split("[Code]", 1)
        _, po_messages = reszta_kodu.split("[CustomMessages]", 1)
        kod_section = (
            "[Code]\n"
            "function GetManualISO(Param: String): String;\n"
            "begin\n"
            f"{blok_kod_iso}\n"
            "end;\n\n"
        )
        iss_etap_2 = (
            f"{przed_kodu}{kod_section}"
            f"[CustomMessages]\n{blok_custom_messages}\n{po_messages}"
        )
    else:
        # Defensywnie: jeśli installer.iss zostanie kiedyś zrefactorowany
        # i straci [Code] lub [CustomMessages] — leci bez nadpisywania.
        # Niespójność wykryta w wizualnej weryfikacji (Otwórz instrukcję
        # otworzy zły plik), nie cichy bug.
        print("⚠ Skipping [Code]/[CustomMessages] dynamic injection: "
              "installer.iss missing one of those sections.")
        iss_etap_2 = iss_etap_1

    nowy_iss = iss_etap_2

    print("\nCreating the installer...")
    tmp_created = False
    try:
        sciezka_tmp.write_text(nowy_iss, encoding="utf-8")
        tmp_created = True
        subprocess.run(
            [iscc_exe, "/Q", str(sciezka_tmp), f"/DMyAppVersion={wersja}"],
            check=True,
        )
        print(f"✅ Installer created: Rezyser_Audio_v{wersja}_Installer.exe")
        # v18.10: suma kontrolna instalatora. Plik `.sha256` (format sha256sum:
        # "<hash> *<nazwa>") idzie jako DRUGI asset Release — `core_updater`
        # weryfikuje nim pobrany plik przed uruchomieniem (graceful skip dla
        # starych wydań bez assetu).
        sciezka_exe = Path(__file__).parent / f"Rezyser_Audio_v{wersja}_Installer.exe"
        if sciezka_exe.exists():
            suma = _policz_sha256(sciezka_exe)
            sciezka_sha = sciezka_exe.with_name(sciezka_exe.name + ".sha256")
            sciezka_sha.write_text(f"{suma} *{sciezka_exe.name}\n", encoding="ascii")
            print(f"   SHA256: {suma}")
            print(f"   Checksum file: {sciezka_sha.name} "
                  "(upload it as the SECOND release asset, next to the .exe)")
        else:
            # ISCC zwrócił 0, ale pliku nie ma — nie maskujemy tego sukcesem.
            print(f"❌ FATAL: ISCC exited 0 but {sciezka_exe.name} was not found.")
            sys.exit(1)
    except subprocess.CalledProcessError:
        print("❌ Compilation error. Inno Setup returned a non-zero exit code.")
        # v18.9: bez tego build kończył się kodem 0 mimo braku instalatora —
        # w trybie automatycznym (`-y`) wyglądało to na sukces, a w `dist/`
        # zostawał co najwyżej installer POPRZEDNIEJ wersji.
        sys.exit(1)
    finally:
        if tmp_created and sciezka_tmp.exists():
            sciezka_tmp.unlink()



if __name__ == "__main__":
    main(_parsuj_argumenty())
