"""Einstiegspunkt für das gebündelte Assistent-Executable (PyInstaller).

Startet die geführte Schritt-für-Schritt-Oberfläche (gui_wizard) und fängt
Startfehler ab – im --windowed-Bundle gäbe es sonst keinerlei Rückmeldung.
"""

from __future__ import annotations

import sys
import traceback


def main() -> int:
    try:
        from photobook_curator.gui_wizard import main as wizard_main

        return wizard_main()
    except Exception:  # pragma: no cover - Startdiagnose im Bundle
        err = traceback.format_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Fotobuch-Assistent – Startfehler",
                "Der Assistent konnte nicht gestartet werden:\n\n" + err,
            )
        except Exception:
            sys.stderr.write(err)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
