# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec für den Photobook Curator (GUI, Windows-first).

Baut ein --onedir-Bundle inkl. der nativen ML-Abhängigkeiten (MediaPipe,
OpenCV, pillow-heif, scikit-learn). Aufruf:

    pyinstaller packaging/photobook.spec

oder komfortabel über packaging/build_windows.bat / packaging/build.py.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# Projektwurzel (eine Ebene über packaging/)
ROOT = Path(SPECPATH).resolve().parent

datas = []
binaries = []
hiddenimports = []

# Native/Datengetriebene Pakete vollständig einsammeln.
# MediaPipe liefert .binarypb/.tflite-Ressourcen, die sonst fehlen.
for pkg in ("mediapipe", "pillow_heif", "cv2", "sklearn"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # pragma: no cover - Build-Zeit-Diagnose
        print(f"[photobook.spec] Warnung: collect_all({pkg}) fehlgeschlagen: {exc}")

# Optional vorab gebündelte MediaPipe-Modelle (falls vorhanden),
# damit das Tool offline startet (siehe packaging/README.md, Abschnitt 7.3).
models_dir = ROOT / "packaging" / "models"
if models_dir.is_dir():
    for model_file in models_dir.glob("*"):
        if model_file.is_file():
            datas.append((str(model_file), "photobook_models"))

hiddenimports += [
    "PIL._tkinter_finder",
    "sklearn.utils._typedefs",
    "sklearn.neighbors._partition_nodes",
]


a = Analysis(
    [str(ROOT / "packaging" / "entry_gui.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "packaging" / "hooks")],
    runtime_hooks=[str(ROOT / "packaging" / "hooks" / "rthook_model_cache.py")],
    excludes=["tkinter.test", "test", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Fotobuch",
    debug=False,
    strip=False,
    upx=False,           # UPX bei ML-DLLs vermeiden (Fehlalarme/Instabilität)
    console=False,       # GUI-Anwendung, kein Konsolenfenster
    icon=str(ROOT / "packaging" / "icon.ico") if (ROOT / "packaging" / "icon.ico").is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Fotobuch",
)
