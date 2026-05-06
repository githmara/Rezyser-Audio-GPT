"""
gui_manager_regul.py – panel Managera Reguł (eksplorator słowników).

Czwarte narzędzie głównego okna (obok Reżysera, Poligloty, Konwertera).
Pozwala użytkownikowi BEZ Pythona:

  * przeglądać wszystkie YAML-e w ``dictionaries/`` w natywnym drzewie
    (wx.TreeCtrl – w pełni obsługiwane przez NVDA),
  * otwierać pliki w domyślnym edytorze tekstu (ta sama logika, co
    ``HomePanel._on_action_btn`` dla ``golden_key.env``),
  * tworzyć nowe reguły: szablony (akcent/szyfr/tryb/postprodukcja) oraz
    prompty dla chatbotów AI dla trudniejszych przypadków (nowy język,
    szyfr algorytmiczny) – teksty pochodzą z ``manager_regul_szablony``,
  * duplikować istniejące pliki (szybki start dla wariantu),
  * usuwać pliki z potwierdzeniem.

Bezpieczeństwo: drzewo ma zakotwiczony root w ``DICTIONARIES_DIR``,
kreator nie udostępnia wyboru dowolnej ścieżki, a każda operacja
na pliku przechodzi przez :func:`_bezpieczna_sciezka` – użytkownik nie
ma jak wyjść poza ``dictionaries/``.

Wersja 13.1: dodana czwarta kategoria ``gui/`` (tłumaczenia UI), cały
tekst widoczny dla użytkownika przechodzi przez :mod:`i18n` (klucze
``manager.*`` w ``dictionaries/<kod>/gui/ui.yaml``).
"""

from __future__ import annotations

import os
import platform
import re
import subprocess

import wx

import manager_regul_szablony as mrs
from i18n import aktualny_jezyk, t


# 13.2: sentinel oznaczający widok bez filtra (dla autorów paczek językowych).
# Wartość nie odpowiada żadnemu kodowi języka, więc nie zderzy się z folderami
# w ``dictionaries/``. Etykieta wyświetlana w dropdownie pochodzi z i18n.
_OPCJA_WSZYSTKIE = "__all__"


# =============================================================================
# Stałe i helpery
# =============================================================================
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DICTIONARIES_DIR = os.path.join(_ROOT_DIR, "dictionaries")

# Nazwy podfolderów rozpoznawane przez silnik
FOLDER_AKCENTY = "akcenty"
FOLDER_SZYFRY  = "szyfry"
FOLDER_REZYSER = "rezyser"
FOLDER_GUI     = "gui"   # tłumaczenia UI – dodane w 13.1


# Walidacja id pliku – ASCII snake_case (żeby działało wszędzie, także
# pod Windows z UAC i w nazwach z generatora wrapperów akcent_*).
_RE_ID_PLIKU        = re.compile(r"^[a-z][a-z0-9_]*$")
_RE_KOD_JEZYKA      = re.compile(r"^[a-z]{2,3}$")
_RE_KOD_ISO         = re.compile(r"^[a-z]{2,3}$")


def _etykieta_kategorii(kat: str) -> str:
    """Zwraca przyjazną etykietę kategorii drzewa (z ``manager.kategorie.*``).

    Wersja 13.1: etykiety przeniesione do i18n zamiast stałej globalnej,
    dzięki czemu przyzwyczajenie do języka polskiego można zmienić
    wyłącznie przez edycję ``dictionaries/<kod>/gui/ui.yaml`` – kod
    Pythona nie wymaga zmian.
    """
    return t(f"manager.kategorie.{kat}")


def _otworz_w_edytorze_tekstu(parent: wx.Window, sciezka: str) -> None:
    """Otwiera plik w domyślnym edytorze tekstu systemu.

    Identyczna logika jak :meth:`main.HomePanel._on_action_btn` dla
    ``golden_key.env`` – ``os.startfile`` na Windows, ``open`` na macOS,
    ``xdg-open`` na Linuksie. Przy błędzie pokazuje ``wx.MessageBox`` ze
    ścieżką, żeby użytkownik mógł otworzyć plik ręcznie.
    """
    try:
        if platform.system() == "Windows":
            os.startfile(sciezka)                              # noqa: S606
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", sciezka])                # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", sciezka])            # noqa: S603,S607
    except Exception as exc:                                    # noqa: BLE001
        wx.MessageBox(
            t(
                "manager.blad_otwarcia_tresc",
                sciezka_pliku=sciezka,
                tresc_bledu=str(exc),
            ),
            t("manager.blad_otwarcia_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            parent,
        )


def _bezpieczna_sciezka(sciezka: str) -> bool:
    """Sprawdza, czy ``sciezka`` leży wewnątrz ``DICTIONARIES_DIR``.

    Obrona przed nadpisaniem plików projektu (np. gdyby użytkownik
    spróbował podmienić drzewo przez manipulację path). W praktyce GUI
    nie udostępnia pola tekstowego ze ścieżką, ale ta funkcja działa
    jak drugi zawór bezpieczeństwa.
    """
    abs_path = os.path.abspath(sciezka)
    abs_root = os.path.abspath(DICTIONARIES_DIR)
    # os.path.commonpath rzuca wyjątek, gdy ścieżki są na różnych dyskach.
    try:
        return os.path.commonpath([abs_path, abs_root]) == abs_root
    except ValueError:
        return False


# =============================================================================
# Panel główny
# =============================================================================
class ManagerRegulPanel(wx.Panel):
    """
    Czwarte narzędzie głównego okna – eksplorator ``dictionaries/``.

    Struktura panelu (od góry):
        - krótki opis A11y (wx.TextCtrl TE_READONLY bez obramowania),
        - dwukolumnowy obszar roboczy:
            * lewo: wx.TreeCtrl z hierarchią języków i plików YAML,
            * prawo: kolumna przycisków akcji.
    """

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetName(t("manager.panel_name"))

        self._build_ui()
        self._bind_events()
        self._zaladuj_drzewo()

    # ------------------------------------------------------------------
    # Budowa UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Opis górny (A11y) ---
        desc = wx.TextCtrl(
            self,
            value=t("manager.desc"),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            name=t("manager.desc_name"),
        )
        desc.SetBackgroundColour(self.GetBackgroundColour())
        main_sizer.Add(desc, flag=wx.ALL | wx.EXPAND, border=12)

        # --- 13.2: filtr języka (A11y) ---
        # Domyślny widok = język UI (czysta lista, bez mieszanki w czytniku
        # ekranu). Ostatnia opcja "Wszystkie języki" jest przeznaczona dla
        # autorów paczek językowych, którzy chcą porównywać foldery obok
        # siebie. Choice trzyma kody języków równolegle do widocznych etykiet
        # (lista ``self._kody_jezykow``), żeby selekcja mogła wprost
        # przenieść kod do filtra drzewa.
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lbl_filter = wx.StaticText(self, label=t("manager.dropdown_jezyk_label"))
        self._kody_jezykow: list[str] = self._dostepne_kody_jezykow()
        etykiety_jezykow = [
            t("manager.tree_jezyk", kod_jezyka=k, nazwa_jezyka=_opis_jezyka(k))
            for k in self._kody_jezykow
        ]
        etykiety_jezykow.append(t("manager.opcja_wszystkie_jezyki"))
        self._kody_jezykow.append(_OPCJA_WSZYSTKIE)

        self._choice_jezyk = wx.Choice(
            self,
            choices=etykiety_jezykow,
            name=t("manager.dropdown_jezyk_label"),
        )
        self._choice_jezyk.SetToolTip(t("manager.dropdown_jezyk_tooltip"))

        domyslny = aktualny_jezyk()
        if domyslny in self._kody_jezykow:
            self._choice_jezyk.SetSelection(self._kody_jezykow.index(domyslny))
        else:
            # Język UI nie ma własnego folderu w dictionaries/ — pokaż wszystko.
            self._choice_jezyk.SetSelection(len(self._kody_jezykow) - 1)

        filter_sizer.Add(lbl_filter, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        filter_sizer.Add(self._choice_jezyk, proportion=1, flag=wx.EXPAND)
        main_sizer.Add(filter_sizer, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, border=12)

        # --- Obszar roboczy (drzewo + przyciski) ---
        work_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Lewa kolumna: drzewo
        self._tree = wx.TreeCtrl(
            self,
            style=wx.TR_DEFAULT_STYLE
                  | wx.TR_HAS_BUTTONS
                  | wx.TR_HIDE_ROOT
                  | wx.TR_SINGLE
                  | wx.TR_FULL_ROW_HIGHLIGHT,
            name=t("manager.tree_name"),
        )
        self._tree.SetToolTip(t("manager.tree_tooltip"))
        work_sizer.Add(self._tree, proportion=3, flag=wx.EXPAND | wx.ALL, border=6)

        # Prawa kolumna: pionowy stos przycisków
        btn_sizer = wx.BoxSizer(wx.VERTICAL)

        self._btn_otworz = wx.Button(
            self, label=t("manager.btn_otworz_label"),
            name=t("manager.btn_otworz_name"),
        )
        self._btn_otworz.SetToolTip(t("manager.btn_otworz_tooltip"))

        self._btn_nowy = wx.Button(
            self, label=t("manager.btn_nowy_label"),
            name=t("manager.btn_nowy_name"),
        )
        self._btn_nowy.SetToolTip(t("manager.btn_nowy_tooltip"))

        self._btn_duplikuj = wx.Button(
            self, label=t("manager.btn_duplikuj_label"),
            name=t("manager.btn_duplikuj_name"),
        )
        self._btn_duplikuj.SetToolTip(t("manager.btn_duplikuj_tooltip"))

        self._btn_usun = wx.Button(
            self, label=t("manager.btn_usun_label"),
            name=t("manager.btn_usun_name"),
        )
        self._btn_usun.SetToolTip(t("manager.btn_usun_tooltip"))

        self._btn_odswiez = wx.Button(
            self, label=t("manager.btn_odswiez_label"),
            name=t("manager.btn_odswiez_name"),
        )
        self._btn_odswiez.SetToolTip(t("manager.btn_odswiez_tooltip"))

        for btn in (
            self._btn_otworz,
            self._btn_nowy,
            self._btn_duplikuj,
            self._btn_usun,
            self._btn_odswiez,
        ):
            btn_sizer.Add(btn, flag=wx.EXPAND | wx.BOTTOM, border=6)

        # Uwaga dla użytkownika na samym dole kolumny przycisków
        info = wx.StaticText(self, label=t("manager.info_stopka"))
        info.Wrap(260)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(info, flag=wx.TOP, border=12)

        work_sizer.Add(btn_sizer, proportion=1,
                       flag=wx.EXPAND | wx.ALL, border=6)

        main_sizer.Add(work_sizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

        self.SetSizer(main_sizer)

    # ------------------------------------------------------------------
    # Podpięcie zdarzeń
    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_sel_changed, self._tree)
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_item_activated, self._tree)
        self.Bind(wx.EVT_BUTTON, self._on_otworz,   self._btn_otworz)
        self.Bind(wx.EVT_BUTTON, self._on_nowy,     self._btn_nowy)
        self.Bind(wx.EVT_BUTTON, self._on_duplikuj, self._btn_duplikuj)
        self.Bind(wx.EVT_BUTTON, self._on_usun,     self._btn_usun)
        self.Bind(wx.EVT_BUTTON, self._on_odswiez,  self._btn_odswiez)
        self.Bind(wx.EVT_CHOICE, self._on_zmiana_filtra_jezyka, self._choice_jezyk)

    # ------------------------------------------------------------------
    # 13.2: filtr języka
    # ------------------------------------------------------------------
    @staticmethod
    def _dostepne_kody_jezykow() -> list[str]:
        """Zwraca posortowaną listę kodów języków (folderów w ``dictionaries/``).

        Zwracamy WSZYSTKIE foldery, nie tylko kompletne (``_jezyk_kompletny``),
        bo manager służy też do tworzenia paczek od zera — autor może edytować
        język, który jeszcze nie ma akcentów ani szyfrów.
        """
        if not os.path.isdir(DICTIONARIES_DIR):
            return []
        return sorted(
            nazwa for nazwa in os.listdir(DICTIONARIES_DIR)
            if os.path.isdir(os.path.join(DICTIONARIES_DIR, nazwa))
        )

    def _aktywny_filtr_jezyka(self) -> str:
        """Zwraca kod języka z dropdownu lub ``_OPCJA_WSZYSTKIE``."""
        idx = self._choice_jezyk.GetSelection()
        if 0 <= idx < len(self._kody_jezykow):
            return self._kody_jezykow[idx]
        return _OPCJA_WSZYSTKIE

    def _on_zmiana_filtra_jezyka(self, _event: wx.CommandEvent) -> None:
        self._zaladuj_drzewo()

    # ------------------------------------------------------------------
    # Ładowanie drzewa
    # ------------------------------------------------------------------
    def _zaladuj_drzewo(self, zaznacz_sciezke: str | None = None) -> None:
        """Przebudowuje wx.TreeCtrl na podstawie aktualnej zawartości dysku.

        Wersja 13.1: oprócz ``akcenty/``, ``szyfry/`` i ``rezyser/``
        skanujemy też nowy katalog ``gui/`` (tłumaczenia UI) – dzięki temu
        lingwista pracujący nad nowym językiem widzi wszystkie warstwy
        w jednym drzewie.

        Args:
            zaznacz_sciezke: jeśli podane, po przebudowie drzewo próbuje
                             zaznaczyć element o tej ścieżce (użyteczne
                             po utworzeniu lub zmianie nazwy pliku).
        """
        self._tree.DeleteAllItems()
        root = self._tree.AddRoot(t("manager.tree_root"))

        if not os.path.isdir(DICTIONARIES_DIR):
            # Brak katalogu – ostrzeż i zakończ
            wezel = self._tree.AppendItem(root, t("manager.tree_brak_folderu"))
            self._tree.SetItemData(wezel, {"typ": "info"})
            return

        do_zaznaczenia: wx.TreeItemId | None = None

        # 13.2: filtr języka z dropdownu — domyślnie pokazujemy tylko język UI
        # (czysty widok, bez mieszanki kodów dla NVDA), opcja „Wszystkie"
        # pokazuje cały folder dla autorów paczek.
        filtr = self._aktywny_filtr_jezyka()

        # Sortujemy języki alfabetycznie; docelowe ścieżki to foldery w
        # dictionaries/ (pomijamy ukryte i pliki na tym poziomie, np. README).
        for jezyk in sorted(os.listdir(DICTIONARIES_DIR)):
            sciezka_jezyka = os.path.join(DICTIONARIES_DIR, jezyk)
            if not os.path.isdir(sciezka_jezyka):
                continue
            if filtr != _OPCJA_WSZYSTKIE and jezyk != filtr:
                continue

            wezel_jezyka = self._tree.AppendItem(
                root,
                t("manager.tree_jezyk", kod_jezyka=jezyk, nazwa_jezyka=_opis_jezyka(jezyk)),
            )
            self._tree.SetItemData(wezel_jezyka, {
                "typ": "jezyk",
                "jezyk": jezyk,
                "sciezka": sciezka_jezyka,
            })

            # 1) podstawy.yaml
            podstawy = os.path.join(sciezka_jezyka, "podstawy.yaml")
            if os.path.isfile(podstawy):
                wezel = self._tree.AppendItem(wezel_jezyka, t("manager.tree_podstawy"))
                self._tree.SetItemData(wezel, {
                    "typ": "plik",
                    "sciezka": podstawy,
                    "kategoria": "podstawy",
                    "jezyk": jezyk,
                })
                if zaznacz_sciezke and _ta_sama_sciezka(podstawy, zaznacz_sciezke):
                    do_zaznaczenia = wezel

            # 2) kategorie (akcenty/ / szyfry/ / rezyser/ / gui/)
            # Wersja 13.1: FOLDER_GUI dołożony jako czwarta kategoria.
            for kat in (FOLDER_AKCENTY, FOLDER_SZYFRY, FOLDER_REZYSER, FOLDER_GUI):
                sciezka_kat = os.path.join(sciezka_jezyka, kat)
                if not os.path.isdir(sciezka_kat):
                    continue

                pliki = sorted(
                    p for p in os.listdir(sciezka_kat)
                    if p.endswith(".yaml") and os.path.isfile(
                        os.path.join(sciezka_kat, p),
                    )
                )
                wezel_kat = self._tree.AppendItem(
                    wezel_jezyka,
                    t(
                        "manager.tree_kategoria",
                        etykieta=_etykieta_kategorii(kat),
                        liczba_plikow=len(pliki),
                    ),
                )
                self._tree.SetItemData(wezel_kat, {
                    "typ": "kategoria",
                    "jezyk": jezyk,
                    "kategoria": kat,
                    "sciezka": sciezka_kat,
                })
                for plik in pliki:
                    pelna = os.path.join(sciezka_kat, plik)
                    wezel = self._tree.AppendItem(
                        wezel_kat,
                        t("manager.tree_plik", nazwa_pliku=plik),
                    )
                    self._tree.SetItemData(wezel, {
                        "typ": "plik",
                        "sciezka": pelna,
                        "kategoria": kat,
                        "jezyk": jezyk,
                    })
                    if zaznacz_sciezke and _ta_sama_sciezka(pelna, zaznacz_sciezke):
                        do_zaznaczenia = wezel

            # Domyślnie rozwijamy gałąź języka (UX – użytkownik od razu widzi zawartość)
            self._tree.Expand(wezel_jezyka)

        # Zaznacz wskazany plik lub (domyślnie) pierwsze dziecko pod rootem
        if do_zaznaczenia is not None:
            self._tree.SelectItem(do_zaznaczenia)
            self._tree.EnsureVisible(do_zaznaczenia)
        else:
            first_child, cookie = self._tree.GetFirstChild(root)
            if first_child.IsOk():
                self._tree.SelectItem(first_child)

        self._odswiez_stan_przyciskow()

    # ------------------------------------------------------------------
    # Handlery drzewa
    # ------------------------------------------------------------------
    def _on_sel_changed(self, _event: wx.TreeEvent) -> None:
        self._odswiez_stan_przyciskow()

    def _on_item_activated(self, _event: wx.TreeEvent) -> None:
        """Enter / dwuklik na elemencie drzewa = Otwórz (jeśli plik)."""
        meta = self._aktualny_wybor()
        if meta and meta["typ"] == "plik":
            self._otworz_plik(meta["sciezka"])

    def _odswiez_stan_przyciskow(self) -> None:
        """Włącza / wyłącza przyciski akcji w zależności od typu zaznaczenia."""
        meta = self._aktualny_wybor()
        czy_plik = bool(meta and meta["typ"] == "plik")
        self._btn_otworz.Enable(czy_plik)
        self._btn_duplikuj.Enable(czy_plik)
        self._btn_usun.Enable(czy_plik)
        # Nowy i Odśwież są zawsze dostępne.

    def _aktualny_wybor(self) -> dict | None:
        """Zwraca metadane zaznaczonego węzła lub None, jeśli brak."""
        item = self._tree.GetSelection()
        if not item.IsOk():
            return None
        data = self._tree.GetItemData(item)
        return data if isinstance(data, dict) else None

    # ------------------------------------------------------------------
    # Handlery przycisków – operacje na plikach
    # ------------------------------------------------------------------
    def _on_otworz(self, _event: wx.Event) -> None:
        meta = self._aktualny_wybor()
        if meta and meta["typ"] == "plik":
            self._otworz_plik(meta["sciezka"])

    def _otworz_plik(self, sciezka: str) -> None:
        """Opakowanie bezpieczeństwa wokół ``_otworz_w_edytorze_tekstu``."""
        if not _bezpieczna_sciezka(sciezka) or not os.path.isfile(sciezka):
            wx.MessageBox(
                t("manager.plik_wne_tresc"),
                t("manager.plik_wne_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        _otworz_w_edytorze_tekstu(self, sciezka)

    def _on_odswiez(self, _event: wx.Event) -> None:
        self._zaladuj_drzewo()

    # ------------------------------------------------------------------
    # Duplikowanie pliku
    # ------------------------------------------------------------------
    def _on_duplikuj(self, _event: wx.Event) -> None:
        meta = self._aktualny_wybor()
        if not meta or meta["typ"] != "plik":
            return

        stary = meta["sciezka"]
        folder = os.path.dirname(stary)
        stara_nazwa = os.path.basename(stary)

        dlg = wx.TextEntryDialog(
            self,
            t("manager.dup_dlg_label", nazwa_pliku=stara_nazwa),
            t("manager.dup_dlg_tytul"),
            value=_zaproponuj_nowa_nazwe(stara_nazwa),
        )
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            nowa_id = dlg.GetValue().strip().lower()
        finally:
            dlg.Destroy()

        if not _RE_ID_PLIKU.match(nowa_id):
            wx.MessageBox(
                t("manager.dup_nazwa_blad_tresc"),
                t("manager.dup_nazwa_blad_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        nowa_sciezka = os.path.join(folder, f"{nowa_id}.yaml")
        if not _bezpieczna_sciezka(nowa_sciezka):
            wx.MessageBox(
                t("manager.dup_poza_dict_tresc"),
                t("manager.dup_poza_dict_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        if os.path.exists(nowa_sciezka):
            wx.MessageBox(
                t("manager.dup_istnieje_tresc", nazwa_pliku=nowa_id),
                t("manager.dup_istnieje_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return

        try:
            with open(stary, "r", encoding="utf-8") as fh:
                zawartosc = fh.read()
            # Zamień `id: <stare>` na `id: <nowe>` w pierwszej linii, która pasuje.
            zawartosc_nowa = re.sub(
                r"^(\s*id:\s*).+$",
                rf"\1{nowa_id}",
                zawartosc,
                count=1,
                flags=re.MULTILINE,
            )
            # Dopisz jednorazowy komentarz na górze, żeby lingwista wiedział,
            # skąd pochodzi plik i co zmienić dalej.
            naglowek = t("manager.dup_komentarz_naglowek", nazwa_pliku=stara_nazwa) + "\n"
            with open(nowa_sciezka, "w", encoding="utf-8") as fh:
                fh.write(naglowek + zawartosc_nowa)
        except Exception as exc:                                # noqa: BLE001
            wx.MessageBox(
                t("manager.dup_blad", tresc_bledu=str(exc)),
                t("common.blad_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        wx.MessageBox(
            t("manager.dup_ok_tresc", nazwa_pliku=os.path.basename(nowa_sciezka)),
            t("manager.dup_ok_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        _otworz_w_edytorze_tekstu(self, nowa_sciezka)
        self._zaladuj_drzewo(zaznacz_sciezke=nowa_sciezka)

    # ------------------------------------------------------------------
    # Usuwanie pliku
    # ------------------------------------------------------------------
    def _on_usun(self, _event: wx.Event) -> None:
        meta = self._aktualny_wybor()
        if not meta or meta["typ"] != "plik":
            return

        sciezka = meta["sciezka"]
        if not _bezpieczna_sciezka(sciezka):
            return  # defensive

        odp = wx.MessageBox(
            t(
                "manager.usun_pytanie_tresc",
                nazwa_pliku=os.path.basename(sciezka),
                katalog_wzgledny=os.path.relpath(os.path.dirname(sciezka), _ROOT_DIR),
            ),
            t("manager.usun_pytanie_tytul"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            self,
        )
        if odp != wx.YES:
            return

        try:
            os.remove(sciezka)
        except Exception as exc:                                # noqa: BLE001
            wx.MessageBox(
                t("manager.usun_blad", tresc_bledu=str(exc)),
                t("common.blad_tytul"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        wx.MessageBox(
            t("manager.usun_ok_tresc"),
            t("manager.usun_ok_tytul"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )
        self._zaladuj_drzewo()

    # ------------------------------------------------------------------
    # Kreator „Nowy plik reguł…"
    # ------------------------------------------------------------------
    def _on_nowy(self, _event: wx.Event) -> None:
        meta = self._aktualny_wybor()

        # Kontekst podpowiada domyślny typ + język bazowy dla kreatora.
        domyslny_jezyk = (meta or {}).get("jezyk", "pl") or "pl"
        domyslny_typ   = _zgadnij_typ_z_zaznaczenia(meta)

        dlg = KreatorNowejRegulyDialog(
            self,
            dostepne_jezyki=self._lista_jezykow_bazowych(),
            domyslny_typ=domyslny_typ,
            domyslny_jezyk=domyslny_jezyk,
        )
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            wybor = dlg.wynik
        finally:
            dlg.Destroy()

        self._obsluz_wynik_kreatora(wybor)

    def _lista_jezykow_bazowych(self) -> list[str]:
        """Zwraca posortowaną listę istniejących kodów języka w dictionaries/."""
        if not os.path.isdir(DICTIONARIES_DIR):
            return ["pl"]
        return sorted(
            nazwa for nazwa in os.listdir(DICTIONARIES_DIR)
            if os.path.isdir(os.path.join(DICTIONARIES_DIR, nazwa))
        ) or ["pl"]

    def _obsluz_wynik_kreatora(self, wybor: dict) -> None:
        """Przyjmuje wybor z KreatorNowejRegulyDialog i uruchamia akcję."""
        typ          = wybor["typ"]
        id_pliku     = wybor["id"]
        etykieta     = wybor["etykieta"]
        iso          = wybor.get("iso", "")
        jezyk_bazowy = wybor.get("jezyk_bazowy", "pl")
        opis_efektu  = wybor.get("opis_efektu", "")

        pakiet = mrs.zbuduj_wynik(
            typ,
            id_pliku=id_pliku,
            etykieta=etykieta,
            iso=iso,
            jezyk_bazowy=jezyk_bazowy,
            opis_efektu=opis_efektu,
        )

        docelowy_rel = pakiet["docelowy"]                        # np. pl/akcenty/x.yaml
        docelowy_abs = os.path.join(DICTIONARIES_DIR, docelowy_rel)

        # KOLEJNOŚĆ MA ZNACZENIE:
        # Najpierw zapisujemy plik podstawy.yaml (gdy tworzymy nowy język),
        # DOPIERO POTEM tworzymy podfoldery akcenty/, szyfry/ i gui/. Odwrotna
        # kolejność tworzyła „półpusty" folder języka (tylko puste
        # podfoldery, bez podstawy.yaml) zawsze, gdy użytkownik anulował
        # pytanie o nadpisanie – a silnik Poligloty wywraca się na takim
        # katalogu podczas skanowania.
        if pakiet["yaml"]:
            if not _bezpieczna_sciezka(docelowy_abs):
                wx.MessageBox(
                    t("manager.blad_bezpieczenstwa_tresc"),
                    t("manager.blad_bezpieczenstwa_tytul"),
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
                return
            if os.path.exists(docelowy_abs):
                odp = wx.MessageBox(
                    t(
                        "manager.plik_istnieje_tresc",
                        nazwa_pliku=os.path.basename(docelowy_abs),
                    ),
                    t("manager.plik_istnieje_tytul"),
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
                    self,
                )
                if odp != wx.YES:
                    return

            try:
                os.makedirs(os.path.dirname(docelowy_abs), exist_ok=True)
                with open(docelowy_abs, "w", encoding="utf-8") as fh:
                    fh.write(pakiet["yaml"])
            except Exception as exc:                            # noqa: BLE001
                wx.MessageBox(
                    t("manager.blad_tworzenia", tresc_bledu=str(exc)),
                    t("common.blad_tytul"),
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
                return

        # Dopiero po udanym zapisie podstawy.yaml dokładamy strukturę
        # podfolderów dla nowego języka (silnik ich oczekuje).
        # Wersja 13.1: tworzymy też podfolder gui/ – żeby tłumacz UI nowego
        # języka miał gotowe miejsce na ui.yaml bez grzebania w konsoli.
        if typ == mrs.TYP_JEZYK_BAZOWY:
            folder_jezyka = os.path.join(DICTIONARIES_DIR, id_pliku)
            try:
                os.makedirs(os.path.join(folder_jezyka, FOLDER_AKCENTY),
                            exist_ok=True)
                os.makedirs(os.path.join(folder_jezyka, FOLDER_SZYFRY),
                            exist_ok=True)
                os.makedirs(os.path.join(folder_jezyka, FOLDER_GUI),
                            exist_ok=True)
            except Exception as exc:                            # noqa: BLE001
                wx.MessageBox(
                    t("manager.niepelna_struktura_tresc", tresc_bledu=str(exc)),
                    t("manager.niepelna_struktura_tytul"),
                    wx.OK | wx.ICON_WARNING,
                    self,
                )

        # Pokaż dialog wyniku (uwagi + ewentualny prompt do skopiowania).
        dlg = WynikKreatoraDialog(
            self,
            pakiet=pakiet,
            docelowy_abs=docelowy_abs,
            szablon_zapisany=bool(pakiet["yaml"]),
        )
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()

        # Odśwież drzewo; jeśli plik powstał, zaznacz go automatycznie.
        self._zaladuj_drzewo(
            zaznacz_sciezke=docelowy_abs if pakiet["yaml"] else None,
        )


# =============================================================================
# Pomocnicze: etykiety, walidacje, zgadywanie kontekstu
# =============================================================================
# Uwaga: mapowanie ``kod_jezyka → nazwa_jezyka`` zostaje intencjonalnie
# twardo w kodzie, bo to dane referencyjne (jak kody ISO) – nie etykiety UI.
# Gdy ktoś zmieni język aplikacji na angielski, i tak dalej ma sens
# pokazywać „ru (rosyjski)", bo to tylko pomaga rozróżnić folder
# w drzewie. Pełne tłumaczenie tej tabeli może przyjść w 14.0, jeśli
# będzie na nie konkretne zapotrzebowanie.
_NAZWY_JEZYKOW = {
    "pl": "polski",
    "en": "angielski",
    "de": "niemiecki",
    "fr": "francuski",
    "es": "hiszpański",
    "it": "włoski",
    "fi": "fiński",
    "is": "islandzki",
    "sv": "szwedzki",
    "da": "duński",
    "no": "norweski",
    "ru": "rosyjski",
    "cs": "czeski",
    "sk": "słowacki",
    "hu": "węgierski",
    "nl": "niderlandzki",
    "pt": "portugalski",
    "uk": "ukraiński",
    "ja": "japoński",
    "zh": "chiński",
}


def _opis_jezyka(kod: str) -> str:
    """Zwraca przyjazną nazwę języka dla kodu ISO (fallback: kod)."""
    return _NAZWY_JEZYKOW.get(kod.lower(), kod)


def _zaproponuj_nowa_nazwe(stara_nazwa: str) -> str:
    """Proponuje nazwę duplikatu typu ``cezar_kopia``."""
    baza = os.path.splitext(stara_nazwa)[0]
    return f"{baza}_kopia"


def _ta_sama_sciezka(a: str, b: str) -> bool:
    """Porównanie ścieżek, tolerancyjne dla Windows (case-insensitive)."""
    try:
        return os.path.samefile(a, b)
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(a)) == \
               os.path.normcase(os.path.abspath(b))


# Łata na starszy Python-y bez samefile_or_eq – os.path go nie ma, używamy
# naszej funkcji _ta_sama_sciezka w głównym kodzie. Tu zostawiamy pustą
# referencję dla zachowania wstecznej kompatybilności, ale finalnie
# w _zaladuj_drzewo() używamy _ta_sama_sciezka().
if not hasattr(os.path, "samefile_or_eq"):
    os.path.samefile_or_eq = _ta_sama_sciezka  # type: ignore[attr-defined]


def _zgadnij_typ_z_zaznaczenia(meta: dict | None) -> str:
    """Zgaduje typ reguły na podstawie zaznaczonego węzła w drzewie."""
    if not meta:
        return mrs.TYP_AKCENT
    kat = meta.get("kategoria", "")
    if kat == FOLDER_AKCENTY:
        return mrs.TYP_AKCENT
    if kat == FOLDER_SZYFRY:
        return mrs.TYP_SZYFR_ZAMIANY
    if kat == FOLDER_REZYSER:
        return mrs.TYP_TRYB_REZYSERA
    # FOLDER_GUI nie ma jeszcze dedykowanego typu w kreatorze (13.1) –
    # trafia do domyślnego (akcent), bo kreator tłumaczeń UI byłby
    # dużym osobnym skryptem (patrz TODO_wielojezycznosc.md).
    return mrs.TYP_AKCENT


# =============================================================================
# Dialog: Kreator „Nowy plik reguł…"
# =============================================================================
class KreatorNowejRegulyDialog(wx.Dialog):
    """
    Dialog wyboru typu + parametrów dla nowej reguły.

    Po zatwierdzeniu wynik jest dostępny jako ``self.wynik`` (słownik
    przekazywany do ``ManagerRegulPanel._obsluz_wynik_kreatora``).
    """

    def __init__(
        self,
        parent: wx.Window,
        *,
        dostepne_jezyki: list[str],
        domyslny_typ: str,
        domyslny_jezyk: str,
    ) -> None:
        super().__init__(
            parent,
            title=t("manager.kreator_tytul"),
            size=(640, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._dostepne_jezyki = dostepne_jezyki
        self._domyslny_jezyk  = domyslny_jezyk
        self.wynik: dict | None = None

        self._build_ui(domyslny_typ)
        self._bind_events()
        self._aktualizuj_widoczne_pola()

    # ------------------------------------------------------------------
    # Budowa UI kreatora
    # ------------------------------------------------------------------
    def _build_ui(self, domyslny_typ: str) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Wybór typu reguły ---
        sizer.Add(
            wx.StaticText(self, label=t("manager.kreator_co_utworzyc")),
            flag=wx.LEFT | wx.RIGHT | wx.TOP, border=12,
        )

        # Reprezentacja w ComboBox: etykieta widoczna ↔ id typu
        self._etykiety_typow: list[str] = []
        self._id_typow: list[str] = []
        for tid, lbl, _ in mrs.LISTA_TYPOW:
            self._etykiety_typow.append(lbl)
            self._id_typow.append(tid)

        self._cb_typ = wx.ComboBox(
            self,
            choices=self._etykiety_typow,
            style=wx.CB_READONLY,
            name=t("manager.kreator_cb_name"),
        )
        domyslny_idx = self._id_typow.index(domyslny_typ) \
                       if domyslny_typ in self._id_typow else 0
        self._cb_typ.SetSelection(domyslny_idx)
        sizer.Add(self._cb_typ, flag=wx.EXPAND | wx.ALL, border=12)

        # --- Opis wybranego typu (auto-aktualizacja) ---
        self._lbl_opis_typu = wx.TextCtrl(
            self,
            value="",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            size=(-1, 60),
            name=t("manager.kreator_opis_name"),
        )
        self._lbl_opis_typu.SetBackgroundColour(self.GetBackgroundColour())
        sizer.Add(self._lbl_opis_typu, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=12)

        # --- Pola formularza ---
        form = wx.FlexGridSizer(rows=0, cols=2, vgap=8, hgap=8)
        form.AddGrowableCol(1)

        self._txt_id = wx.TextCtrl(self, name=t("manager.kreator_id_name"))
        self._txt_id.SetHint(t("manager.kreator_id_hint"))
        form.Add(wx.StaticText(self, label=t("manager.kreator_lbl_id")),
                 flag=wx.ALIGN_CENTER_VERTICAL)
        form.Add(self._txt_id, flag=wx.EXPAND)

        self._txt_etykieta = wx.TextCtrl(self, name=t("manager.kreator_etykieta_name"))
        self._txt_etykieta.SetHint(t("manager.kreator_etykieta_hint"))
        self._lbl_etykieta = wx.StaticText(self, label=t("manager.kreator_lbl_etykieta"))
        form.Add(self._lbl_etykieta, flag=wx.ALIGN_CENTER_VERTICAL)
        form.Add(self._txt_etykieta, flag=wx.EXPAND)

        self._txt_iso = wx.TextCtrl(self, name=t("manager.kreator_iso_name"))
        self._txt_iso.SetHint(t("manager.kreator_iso_hint"))
        self._lbl_iso = wx.StaticText(self, label=t("manager.kreator_lbl_iso"))
        form.Add(self._lbl_iso, flag=wx.ALIGN_CENTER_VERTICAL)
        form.Add(self._txt_iso, flag=wx.EXPAND)

        self._cb_jezyk = wx.ComboBox(
            self,
            choices=self._dostepne_jezyki,
            style=wx.CB_READONLY,
            name=t("manager.kreator_jezyk_name"),
        )
        if self._domyslny_jezyk in self._dostepne_jezyki:
            self._cb_jezyk.SetStringSelection(self._domyslny_jezyk)
        else:
            self._cb_jezyk.SetSelection(0)
        self._lbl_jezyk = wx.StaticText(self, label=t("manager.kreator_lbl_jezyk"))
        form.Add(self._lbl_jezyk, flag=wx.ALIGN_CENTER_VERTICAL)
        form.Add(self._cb_jezyk, flag=wx.EXPAND)

        self._txt_opis_efektu = wx.TextCtrl(
            self, style=wx.TE_MULTILINE,
            name=t("manager.kreator_opis_efektu_name"),
        )
        self._txt_opis_efektu.SetHint(t("manager.kreator_opis_efektu_hint"))
        self._lbl_opis_efektu = wx.StaticText(self, label=t("manager.kreator_lbl_opis"))
        form.Add(self._lbl_opis_efektu, flag=wx.ALIGN_CENTER_VERTICAL | wx.TOP, border=4)
        form.Add(self._txt_opis_efektu, flag=wx.EXPAND)

        sizer.Add(form, proportion=1, flag=wx.EXPAND | wx.ALL, border=12)

        # --- Przyciski OK / Anuluj ---
        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        self.FindWindowById(wx.ID_OK, self).SetLabel(t("manager.kreator_btn_utworz"))
        self.FindWindowById(wx.ID_CANCEL, self).SetLabel(t("common.btn_anuluj"))
        sizer.Add(btn_sizer, flag=wx.ALL | wx.ALIGN_RIGHT, border=12)

        self.SetSizer(sizer)

        # Porządek fokusu – NVDA
        self._cb_typ.SetFocus()

    # ------------------------------------------------------------------
    # Zdarzenia
    # ------------------------------------------------------------------
    def _bind_events(self) -> None:
        self.Bind(wx.EVT_COMBOBOX, self._on_typ_change, self._cb_typ)
        self.Bind(wx.EVT_BUTTON,   self._on_ok,          id=wx.ID_OK)

    def _on_typ_change(self, _event: wx.CommandEvent) -> None:
        self._aktualizuj_widoczne_pola()

    def _aktualizuj_widoczne_pola(self) -> None:
        """Pokazuje/chowa pola zależne od wybranego typu."""
        idx = self._cb_typ.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        typ = self._id_typow[idx]

        # Opis typu pod ComboBoxem
        _, _, opis = mrs.LISTA_TYPOW[idx]
        self._lbl_opis_typu.SetValue(opis)
        self._lbl_opis_typu.SetName(opis)   # NVDA odczyta po sfocusowaniu

        # Reguły pokazywania pól:
        #   - ISO: tylko dla akcentu (nie dla nowego języka — tam jest zbędne).
        #   - Opis efektu: tylko dla szyfru algorytmicznego.
        #   - Język bazowy (ComboBox): dla WSZYSTKICH poza nowym językiem.
        pokaz_iso        = typ == mrs.TYP_AKCENT
        pokaz_opis_efekt = typ == mrs.TYP_SZYFR_ALGORYTM
        pokaz_jezyk      = typ != mrs.TYP_JEZYK_BAZOWY

        self._lbl_iso.Show(pokaz_iso)
        self._txt_iso.Show(pokaz_iso)
        self._lbl_opis_efektu.Show(pokaz_opis_efekt)
        self._txt_opis_efektu.Show(pokaz_opis_efekt)
        self._lbl_jezyk.Show(pokaz_jezyk)
        self._cb_jezyk.Show(pokaz_jezyk)

        # Zmiana etykiet + podpowiedzi pod dany typ
        if typ == mrs.TYP_JEZYK_BAZOWY:
            self._txt_id.SetHint(t("manager.kreator_jezyk_bazowy_id_hint"))
            self._lbl_etykieta.SetLabel(t("manager.kreator_jezyk_bazowy_etykieta_label"))
            self._txt_etykieta.SetHint(t("manager.kreator_jezyk_bazowy_etykieta_hint"))
        else:
            self._txt_id.SetHint(t("manager.kreator_id_hint"))
            self._lbl_etykieta.SetLabel(t("manager.kreator_lbl_etykieta"))
            self._txt_etykieta.SetHint(t("manager.kreator_etykieta_hint"))
            self._lbl_iso.SetLabel(t("manager.kreator_lbl_iso"))
            self._txt_iso.SetHint(t("manager.kreator_iso_hint"))

        self.Layout()

    # ------------------------------------------------------------------
    # OK – walidacja i zwrot wyniku
    # ------------------------------------------------------------------
    def _on_ok(self, event: wx.CommandEvent) -> None:
        idx = self._cb_typ.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        typ = self._id_typow[idx]

        id_pliku     = self._txt_id.GetValue().strip().lower()
        etykieta     = self._txt_etykieta.GetValue().strip()
        iso_lub_nazwa = self._txt_iso.GetValue().strip()
        jezyk_bazowy = self._cb_jezyk.GetStringSelection() if self._cb_jezyk.IsShown() else "pl"
        opis_efektu  = self._txt_opis_efektu.GetValue().strip()

        # --- Walidacja pól obowiązkowych zależna od typu ---
        if typ == mrs.TYP_JEZYK_BAZOWY:
            # Tu „id” = kod języka (en, de, fr)
            if not _RE_KOD_JEZYKA.match(id_pliku):
                self._alert(t("manager.kreator_blad_kod_jezyka"))
                return
            if not etykieta:
                self._alert(t("manager.kreator_blad_nazwa_jezyka"))
                return
            iso = iso_lub_nazwa or etykieta   # w prompcie użyjemy nazwy
        else:
            if not _RE_ID_PLIKU.match(id_pliku):
                self._alert(t("manager.kreator_blad_id"))
                return
            if not etykieta:
                self._alert(t("manager.kreator_blad_etykieta"))
                return
            iso = iso_lub_nazwa.lower()
            if typ == mrs.TYP_AKCENT:
                if not _RE_KOD_ISO.match(iso):
                    self._alert(t("manager.kreator_blad_iso"))
                    return
            else:
                iso = iso or "pl"    # domyślny dla szyfrów i trybów

        if typ == mrs.TYP_SZYFR_ALGORYTM and not opis_efektu:
            self._alert(t("manager.kreator_blad_opis_efektu"))
            return

        self.wynik = {
            "typ": typ,
            "id": id_pliku,
            "etykieta": etykieta,
            "iso": iso,
            "jezyk_bazowy": jezyk_bazowy,
            "opis_efektu": opis_efektu,
        }
        event.Skip()   # domyślnie zamyka dialog z wx.ID_OK

    def _alert(self, wiadomosc: str) -> None:
        wx.MessageBox(
            wiadomosc,
            t("manager.kreator_alert_tytul"),
            wx.OK | wx.ICON_WARNING,
            self,
        )


# =============================================================================
# Dialog: wynik kreatora (uwagi + prompt do skopiowania)
# =============================================================================
class WynikKreatoraDialog(wx.Dialog):
    """
    Pokazuje wynik akcji „Nowy plik reguł…":

      * status (plik utworzony / pominięto),
      * uwagi dla użytkownika,
      * tekst promptu dla AI (jeśli dostępny) w polu TextCtrl READONLY –
        z przyciskiem „Skopiuj do schowka".

    Wzorzec A11y: pojedynczy dialog z polami TextCtrl (TE_READONLY), bez
    aktualizacji etykiet w locie. NVDA odczyta zawartość po wejściu
    strzałkami, Ctrl+A/Ctrl+C kopiuje ręcznie.
    """

    def __init__(
        self,
        parent: wx.Window,
        *,
        pakiet: dict,
        docelowy_abs: str,
        szablon_zapisany: bool,
    ) -> None:
        super().__init__(
            parent, title=t("manager.wynik_tytul"), size=(700, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._pakiet = pakiet
        self._docelowy_abs = docelowy_abs

        self._build_ui(szablon_zapisany)

    def _build_ui(self, szablon_zapisany: bool) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Nagłówek statusu ---
        if szablon_zapisany:
            naglowek_txt = t(
                "manager.wynik_sukces_naglowek",
                sciezka_pliku=os.path.relpath(self._docelowy_abs, _ROOT_DIR),
            )
        else:
            naglowek_txt = t("manager.wynik_brak_pliku_naglowek")
        naglowek = wx.TextCtrl(
            self, value=naglowek_txt,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER,
            size=(-1, 60),
        )
        naglowek.SetBackgroundColour(self.GetBackgroundColour())
        sizer.Add(naglowek, flag=wx.ALL | wx.EXPAND, border=12)

        # --- Uwagi z pakietu ---
        uwagi_lbl = wx.StaticText(self, label=t("manager.wynik_lbl_uwagi"))
        font = uwagi_lbl.GetFont()
        font.MakeBold()
        uwagi_lbl.SetFont(font)
        sizer.Add(uwagi_lbl, flag=wx.LEFT | wx.RIGHT, border=12)

        uwagi_txt = wx.TextCtrl(
            self, value=self._pakiet["uwagi"],
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            size=(-1, 110),
            name=t("manager.wynik_uwagi_name"),
        )
        sizer.Add(uwagi_txt, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=12)

        # --- Prompt dla AI (jeśli jest) ---
        if self._pakiet["prompt"]:
            prompt_lbl = wx.StaticText(self, label=t("manager.wynik_lbl_prompt"))
            f2 = prompt_lbl.GetFont()
            f2.MakeBold()
            prompt_lbl.SetFont(f2)
            sizer.Add(prompt_lbl, flag=wx.TOP | wx.LEFT | wx.RIGHT, border=12)

            self._txt_prompt = wx.TextCtrl(
                self, value=self._pakiet["prompt"],
                style=wx.TE_MULTILINE | wx.TE_READONLY,
                name=t("manager.wynik_prompt_name"),
            )
            sizer.Add(self._txt_prompt, proportion=1,
                      flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=12)

            btn_kopiuj = wx.Button(
                self, label=t("manager.wynik_btn_kopiuj"),
                name=t("manager.wynik_btn_kopiuj_name"),
            )
            self.Bind(wx.EVT_BUTTON, self._on_kopiuj, btn_kopiuj)
            sizer.Add(btn_kopiuj, flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=12)
        else:
            self._txt_prompt = None

        # --- Przycisk Zamknij ---
        btn_close = wx.Button(self, wx.ID_CLOSE, label=t("common.btn_zamknij"))
        self.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE), btn_close)
        self.SetEscapeId(wx.ID_CLOSE)
        sizer.Add(btn_close, flag=wx.ALL | wx.ALIGN_RIGHT, border=12)

        self.SetSizer(sizer)

        # Focus: najważniejsze pole – prompt (jeśli jest) lub uwagi.
        if self._txt_prompt is not None:
            self._txt_prompt.SetFocus()
        else:
            uwagi_txt.SetFocus()

    # ------------------------------------------------------------------
    # Handler: kopiowanie promptu do schowka
    # ------------------------------------------------------------------
    def _on_kopiuj(self, _event: wx.Event) -> None:
        if self._txt_prompt is None:
            return
        dane = wx.TextDataObject(self._txt_prompt.GetValue())
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(dane)
                wx.TheClipboard.Flush()
                wx.MessageBox(
                    t("manager.wynik_skopiowano_tresc"),
                    t("manager.wynik_skopiowano_tytul"),
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
            finally:
                wx.TheClipboard.Close()
        else:
            wx.MessageBox(
                t("manager.wynik_schowek_nieudany_tresc"),
                t("manager.wynik_schowek_nieudany_tytul"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
