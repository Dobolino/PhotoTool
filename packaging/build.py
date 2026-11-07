"""Plattformneutraler Build-Treiber für das Standalone-Bundle.

Aufruf (im aktivierten venv mit installierten Build-Deps):

    python packaging/build.py

Baut über die Spec ``packaging/photobook.spec`` nach ``dist/Fotobuch/``.
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "photobook.spec"


def validate_release_version(root: Path = ROOT) -> str:
    """Fail before a build if installed metadata and updater versions disagree."""
    namespace = ast.parse((root / "photobook_curator" / "__init__.py").read_text(encoding="utf-8"))
    version = next(
        ast.literal_eval(node.value)
        for node in namespace.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)
    )
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    installer = (root / "packaging" / "installer.iss").read_text(encoding="utf-8")
    match = re.search(r'^\s*#define AppVersion "([^"]+)"', installer, re.MULTILINE)
    if (not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version)
            or metadata["project"]["version"] != version
            or match is None or match.group(1) != version):
        raise ValueError("Versionen in __init__.py, pyproject.toml und installer.iss müssen übereinstimmen")
    return version


def main() -> int:
    try:
        version = validate_release_version()
    except (ValueError, KeyError, StopIteration, OSError) as exc:
        print(f"Release-Prüfung fehlgeschlagen: {exc}")
        return 1
    if "--check" in sys.argv:
        print(f"Release-Version {version}: Metadaten stimmen überein")
        return 0
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
