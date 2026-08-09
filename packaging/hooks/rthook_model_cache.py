"""PyInstaller Runtime-Hook: Modell-Cache-Pfad im gebündelten Betrieb.

Läuft VOR dem eigentlichen Programm. Zweck:

1. Einen beschreibbaren, benutzerspezifischen Cache-Pfad für die MediaPipe-
   Modelle festlegen (im Bundle ist das Programmverzeichnis oft read-only).
2. Falls im Bundle vorab Modelle mitgeliefert wurden (packaging/models →
   entpackt nach ``photobook_models``), diese einmalig in den User-Cache
   kopieren, damit das Tool auch offline sofort startet.

Der Code ist defensiv: schlägt etwas fehl, bleibt das Standardverhalten
(Lazy-Download nach ~/.cache/photobook_curator) erhalten.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _user_cache_dir() -> Path:
    # Windows: %LOCALAPPDATA%, sonst ~/.cache
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return Path(base) / "photobook_curator"


def _bundled_models_dir() -> Path | None:
    # PyInstaller entpackt datas nach sys._MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    d = Path(meipass) / "photobook_models"
    return d if d.is_dir() else None


def _seed_cache() -> None:
    cache = _user_cache_dir()
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    # Für den restlichen Code auffindbar machen (optional nutzbar).
    os.environ.setdefault("PHOTOBOOK_MODEL_CACHE", str(cache))

    bundled = _bundled_models_dir()
    if not bundled:
        return
    for src in bundled.glob("*"):
        if not src.is_file():
            continue
        dst = cache / src.name
        try:
            if not dst.exists() or dst.stat().st_size < 1000:
                shutil.copy2(src, dst)
        except Exception:
            pass


_seed_cache()
