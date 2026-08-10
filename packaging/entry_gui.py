"""Einstiegspunkt für das gebündelte GUI-Executable (PyInstaller).

Bewusst schlank gehalten: nur der GUI-Start, damit PyInstaller einen klaren
Entry-Point hat. Fängt Startfehler ab und zeigt sie – im gebündelten
--windowed-Modus gäbe es sonst keinerlei Rückmeldung.
"""

from __future__ import annotations

import sys
import traceback


def main() -> int:
    try:
        from photobook_curator.gui import main as gui_main

        return gui_main()
    except Exception:  # pragma: no cover - Startdiagnose im Bundle
        err = traceback.format_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Fotobuch – Startfehler",
                "Das Programm konnte nicht gestartet werden:\n\n" + err,
            )
        except Exception:
            sys.stderr.write(err)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
