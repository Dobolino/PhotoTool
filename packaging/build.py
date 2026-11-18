"""Plattformneutraler Build-Treiber für das Standalone-Bundle.

Aufruf (im aktivierten venv mit installierten Build-Deps):

    python packaging/build.py

Baut über die Spec ``packaging/photobook.spec`` nach ``dist/Fotobuch/``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "photobook.spec"


def main() -> int:
    if shutil.which("pyinstaller") is None and not _pyinstaller_importable():
        print(
            "PyInstaller ist nicht installiert. Bitte zuerst:\n"
            "  pip install -r packaging/requirements-build.txt"
        )
        return 1

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC),
    ]
    print("Baue Bundle:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode == 0:
        print("\nFertig. Ergebnis: dist/Fotobuch/Fotobuch"
              + (".exe" if sys.platform.startswith("win") else ""))
    return result.returncode


def _pyinstaller_importable() -> bool:
    try:
        import PyInstaller  # noqa: F401

        return True
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
