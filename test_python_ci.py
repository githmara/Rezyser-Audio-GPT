"""Every workflow installs EXACTLY the Python the project was tested on.

`setup-python` with `python-version: '3.14'` takes the newest patch (2026-10-21:
the accessible_text_analyst runner got CPython 3.14.8 while the local interpreter
is 3.14.3). A green CI would then say nothing about the interpreter a contributor
runs, and the build freezes the LOCAL interpreter into the bundle. Single source
of truth: `audyt_zaleznosci.PYTHON_PRZETESTOWANY` (read with `ast`, no import);
bumping the interpreter means changing that constant and every workflow in one
commit. Twin of `.github/scripts/test_python_ci.py` in accessible_text_analyst.
"""
import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
QUOTES = chr(39) + chr(34)


def _tested_python(path: Path) -> str:
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "PYTHON_PRZETESTOWANY" for t in node.targets):
            return ast.literal_eval(node.value)
    raise LookupError(f"PYTHON_PRZETESTOWANY not found in {path}")


def _workflow_versions(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("python-version:"):
            found.append(s.split(":", 1)[1].split("#", 1)[0].strip().strip(QUOTES))
    return found


def test_tested_python_is_an_exact_patch():
    parts = _tested_python(ROOT / "audyt_zaleznosci.py").split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), parts


def test_every_workflow_matches_tested_python():
    expected = _tested_python(ROOT / "audyt_zaleznosci.py")
    seen = 0
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for v in _workflow_versions(wf.read_text(encoding="utf-8")):
            seen += 1
            assert v == expected, f"{wf.name}: python-version {v!r}, expected {expected!r}"
    assert seen > 0, "no python-version found — the parser no longer matches the workflows"


def test_parser_sees_a_bare_minor_and_ignores_comments():
    q = chr(39)
    assert _workflow_versions(f"  python-version: {q}3.14{q}") == ["3.14"]
    assert _workflow_versions(f"python-version: {q}3.14.3{q}  # pinned") == ["3.14.3"]


# Uruchomienie jako skrypt — deleguje do pytesta (kanon v19.2.1).
if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
