"""Alle Textdateien des Projekts in gesamter_code.txt zusammenfassen."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

IGNORE_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "build",
    "dist",
    ".pytest_cache",
    "photobook_curator.egg-info",
    "output_ai_fail",
    "output_dry",
    "output_sample",
    "sample_photos",
}
IGNORE_EXTS = {
    ".pyc",
    ".exe",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".gif",
    ".webp",
    ".heic",
    ".mp4",
    ".zip",
}
IGNORE_FILES = {
    "combine.py",
    "gesamter_code.txt",
    "Code zusammenfassen.bat",
}


def main() -> None:
    out_path = ROOT / "gesamter_code.txt"
    with out_path.open("w", encoding="utf-8") as outfile:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [
                d for d in sorted(dirnames) if d not in IGNORE_DIRS and not d.startswith(".")
            ]
            for name in sorted(filenames):
                if name in IGNORE_FILES:
                    continue
                if any(name.lower().endswith(ext) for ext in IGNORE_EXTS):
                    continue
                path = Path(dirpath) / name
                rel = path.relative_to(ROOT)
                outfile.write(f"\n{'=' * 50}\nDATEI: {rel.as_posix()}\n{'=' * 50}\n\n")
                try:
                    outfile.write(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    outfile.write(f"[Fehler beim Lesen: {exc}]\n")

    print(f"Fertig! Gespeichert als:\n  {out_path}")
    print(f"Größe: {out_path.stat().st_size:,} Bytes")


if __name__ == "__main__":
    main()
