"""Sonda PRODUKCYJNEJ ścieżki Sami: sekret Actions `OPENAI_API_KEY` + `MODEL_SAMI`.

Uruchamia ją wyłącznie workflow `sonda-sami.yml` (workflow_dispatch). Po co
osobno (2026-11-17): żywe wywołanie z lokalnego `golden_key.env` sprawdza klucz
na dysku maintainera, a Sami w produkcji czyta SEKRET repozytorium. Po rotacji
kluczy lokalna zieleń przy nieprzestawionym sekrecie to fałszywa zieleń —
a produkcyjna Sami połyka błąd API w fallback, więc nikt by go nie zobaczył
aż do pierwszego zgłoszenia. Lokalny klucz może też w ogóle nie być kluczem
OpenAI (tryb `openai_compat` Reżysera wskazuje nim inny endpoint).

Kontrakt: jedno wywołanie przez `issue_intake_sami.zapytaj_model` — tę samą
funkcję, której używa bot — i kod wyjścia 1 przy KAŻDYM błędzie. Repo jest
publiczne, więc log jest publiczny: drukujemy klasę wyjątku i status HTTP,
nigdy treść błędu (OpenAI cytuje w niej końcówkę klucza).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import issue_intake_sami as sami  # noqa: E402

PYTANIE = "Capital of Finland?"
OCZEKIWANE = "helsinki"


def main() -> int:
    klucz = os.environ.get("OPENAI_API_KEY", "").strip()
    if not klucz:
        print("FAIL: secret OPENAI_API_KEY is empty or not set for this workflow")
        return 1
    try:
        odp = sami.zapytaj_model(klucz, [
            {"role": "system", "content": "Answer with one word."},
            {"role": "user", "content": PYTANIE},
        ])
    except Exception as exc:  # noqa: BLE001 — każdy błąd = czerwień, bez treści
        status = getattr(exc, "status_code", None)
        print(f"FAIL: {type(exc).__name__} (HTTP {status}) model={sami.MODEL_SAMI}")
        return 1
    tekst = (odp.choices[0].message.content or "").strip()
    ok = OCZEKIWANE in tekst.lower()
    print(f"{'OK' if ok else 'FAIL'}: model={sami.MODEL_SAMI} "
          f"finish={odp.choices[0].finish_reason} reply={tekst[:40]!r}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
