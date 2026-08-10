"""Wiederverwendbare UI-Bausteine mit ausreichend Padding (kein gequetschter Text)."""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional


def section_header(parent: tk.Misc, text: str, colors: dict[str, str]) -> tk.Label:
    lbl = tk.Label(
        parent,
        text=text.upper(),
        bg=colors["bg"],
        fg=colors["muted"],
        font=("Segoe UI Semibold", 9),
        anchor=tk.W,
    )
    lbl.pack(anchor=tk.W, pady=(0, 8))
    return lbl


def card(parent: tk.Misc, colors: dict[str, str], padx: int = 20, pady: int = 18) -> tk.Frame:
    """Karte mit 1px Rahmen – Innenfläche über ``._inner`` nutzen."""
    outer = tk.Frame(parent, bg=colors["line"], padx=1, pady=1)
    inner = tk.Frame(outer, bg=colors["surface"], padx=padx, pady=pady)
    inner.pack(fill=tk.BOTH, expand=True)
    outer._inner = inner  # type: ignore[attr-defined]
    return outer


def soft_banner(parent: tk.Misc, text: str, colors: dict[str, str]) -> tk.Frame:
    """Dezenter Hinweisstreifen (kein Modal, kein Badge-Chaos)."""
    wrap = tk.Frame(parent, bg=colors.get("accent_soft", colors["surface"]), padx=14, pady=10)
    tk.Label(
        wrap,
        text=text,
        bg=colors.get("accent_soft", colors["surface"]),
        fg=colors.get("hero_muted", colors["ink"]),
        font=("Segoe UI", 9),
        anchor=tk.W,
        justify=tk.LEFT,
        wraplength=720,
    ).pack(fill=tk.X)
    return wrap


class PaddedButton(tk.Frame):
    """Button als Label-Frame – zuverlässiges Padding (ttk quetscht Text oft)."""

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        colors: dict[str, str],
        command: Optional[Callable[[], None]] = None,
        *,
        primary: bool = False,
        font=("Segoe UI Semibold", 10),
        padx: int = 16,
        pady: int = 10,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.colors = colors
        self._command = command
        self._primary = primary
        self._label = tk.Label(
            self,
            text=text,
            font=font,
            padx=padx,
            pady=pady,
            cursor="hand2",
        )
        self._label.pack()
        self._label.bind("<Button-1>", self._click)
        self.bind("<Button-1>", self._click)
        self._label.bind("<Enter>", lambda _e: self._hover(True))
        self._label.bind("<Leave>", lambda _e: self._hover(False))
        self._paint(False)

    def configure(self, cnf=None, **kw):  # type: ignore[override]
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
        text = kw.pop("text", None)
        if text is not None:
            self._label.configure(text=text)
        if kw:
            return super().configure(**kw)
        return None

    def _click(self, _event=None) -> None:
        if self._command:
            self._command()

    def _hover(self, on: bool) -> None:
        self._paint(on)

    def _paint(self, hover: bool) -> None:
        c = self.colors
        if self._primary:
            bg = c["accent_hover"] if hover else c["accent"]
            fg = c.get("hero_fg", "#FFFFFF")
            border = bg
        else:
            bg = c["line"] if hover else c.get("chip_bg", c["surface"])
            fg = c["ink"]
            border = c["line"]
        self.configure(bg=border, highlightbackground=border, highlightthickness=1)
        self._label.configure(bg=bg, fg=fg)


class AnAusToggle(tk.Frame):
    """Zweier-Toggle An/Aus mit großzügigem Padding – kein zusammengedrückter Text."""

    def __init__(
        self,
        parent: tk.Misc,
        variable: tk.BooleanVar,
        colors: dict[str, str],
        command: Optional[Callable[[], None]] = None,
        *,
        on_text: str = "An",
        off_text: str = "Aus",
        **kwargs,
    ) -> None:
        super().__init__(parent, bg=colors["surface"], **kwargs)
        self.variable = variable
        self.colors = colors
        self._command = command
        self._on = tk.Label(
            self,
            text=f"  {on_text}  ",
            font=("Segoe UI Semibold", 10),
            padx=10,
            pady=7,
            cursor="hand2",
        )
        self._off = tk.Label(
            self,
            text=f"  {off_text}  ",
            font=("Segoe UI Semibold", 10),
            padx=10,
            pady=7,
            cursor="hand2",
        )
        self._on.pack(side=tk.LEFT)
        self._off.pack(side=tk.LEFT, padx=(3, 0))
        self._on.bind("<Button-1>", lambda _e: self._set(True))
        self._off.bind("<Button-1>", lambda _e: self._set(False))
        try:
            self.variable.trace_add("write", lambda *_: self._paint())
        except Exception:
            pass
        self._paint()

    def set_labels(self, on_text: str, off_text: str) -> None:
        self._on.configure(text=f"  {on_text}  ")
        self._off.configure(text=f"  {off_text}  ")

    def _set(self, value: bool) -> None:
        self.variable.set(value)
        self._paint()
        if self._command:
            self._command()

    def _paint(self) -> None:
        on = bool(self.variable.get())
        c = self.colors
        chip = c.get("chip_bg", c["line"])
        if on:
            self._on.configure(bg=c["accent"], fg=c.get("hero_fg", "#FFFFFF"))
            self._off.configure(bg=chip, fg=c["muted"])
        else:
            self._on.configure(bg=chip, fg=c["muted"])
            self._off.configure(bg=c["accent"], fg=c.get("hero_fg", "#FFFFFF"))


class StepChip(tk.Frame):
    """Workflow-Schritt mit genug Innenabstand – kein Umbruch/Clipping."""

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        colors: dict[str, str],
        active: bool = False,
    ) -> None:
        super().__init__(
            parent,
            bg=colors["bg"],
            highlightthickness=1,
            highlightbackground=colors["line"],
        )
        self.colors = colors
        self._label = tk.Label(
            self,
            text=text,
            font=("Segoe UI Semibold", 10),
            padx=16,
            pady=9,
        )
        self._label.pack()
        self.set_active(active)

    def set_text(self, text: str) -> None:
        self._label.configure(text=text)

    def set_active(self, active: bool) -> None:
        c = self.colors
        if active:
            self._label.configure(
                bg=c["accent"],
                fg=c.get("hero_fg", "#FFFFFF"),
            )
            self.configure(bg=c["accent"], highlightbackground=c["accent"])
        else:
            chip = c.get("chip_bg", c["surface"])
            self._label.configure(bg=chip, fg=c["ink"])
            self.configure(bg=chip, highlightbackground=c["line"])


def pill_badge(parent: tk.Misc, text: str, colors: dict[str, str]) -> tk.Label:
    return tk.Label(
        parent,
        text=f"  {text}  ",
        bg=colors["accent"],
        fg=colors.get("hero_fg", "#FFFFFF"),
        font=("Segoe UI Semibold", 9),
        padx=10,
        pady=6,
    )


class HelpTip(tk.Label):
    """Kleines „?“ neben einer Option – Klick öffnet Erklärung (folgt der Sprache)."""

    _open_tip: Optional["HelpTip"] = None

    def __init__(
        self,
        parent: tk.Misc,
        help_key: str,
        colors: dict[str, str],
        *,
        get_text: Optional[Callable[[str], str]] = None,
        **kwargs,
    ) -> None:
        self.help_key = help_key
        self.colors = colors
        self._get_text = get_text
        self._popup: tk.Toplevel | None = None
        super().__init__(
            parent,
            text=" ?",
            bg=colors.get("surface", colors.get("bg", "#111")),
            fg=colors.get("muted", "#888"),
            font=("Segoe UI Semibold", 10),
            cursor="question_arrow",
            padx=4,
            pady=0,
            **kwargs,
        )
        self.bind("<Button-1>", self._toggle)
        self.bind("<Enter>", lambda _e: self.configure(fg=colors.get("accent", "#7B6CFF")))
        self.bind("<Leave>", lambda _e: self.configure(fg=colors.get("muted", "#888")))

    def set_help_key(self, help_key: str) -> None:
        self.help_key = help_key

    def _resolve_text(self) -> str:
        if self._get_text is not None:
            return self._get_text(self.help_key)
        return self.help_key

    def _toggle(self, _event=None) -> None:
        if self._popup is not None and self._popup.winfo_exists():
            self._close()
            return
        if HelpTip._open_tip is not None and HelpTip._open_tip is not self:
            try:
                HelpTip._open_tip._close()
            except Exception:
                pass
        self._show()

    def _show(self) -> None:
        text = (self._resolve_text() or "").strip()
        if not text:
            return
        tip = tk.Toplevel(self)
        tip.wm_overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        c = self.colors
        wrap = tk.Frame(tip, bg=c.get("line", "#333"), padx=1, pady=1)
        wrap.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(wrap, bg=c.get("surface", "#1a1a22"), padx=12, pady=10)
        inner.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            inner,
            text=text,
            bg=c.get("surface", "#1a1a22"),
            fg=c.get("ink", "#eee"),
            font=("Segoe UI", 9),
            justify=tk.LEFT,
            wraplength=400,
            anchor=tk.W,
        ).pack(fill=tk.X)
        tip.update_idletasks()
        try:
            x = self.winfo_rootx() + 18
            y = self.winfo_rooty() + self.winfo_height() + 4
            sw = tip.winfo_screenwidth()
            sh = tip.winfo_screenheight()
            tw = tip.winfo_reqwidth()
            th = tip.winfo_reqheight()
            if x + tw > sw - 8:
                x = max(8, sw - tw - 8)
            if y + th > sh - 8:
                y = max(8, self.winfo_rooty() - th - 4)
            tip.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        tip.bind("<Escape>", lambda _e: self._close())
        # Autoclose nach ein paar Sekunden; erneuter Klick auf ? schließt sofort
        tip.after(8000, self._close)
        self._popup = tip
        HelpTip._open_tip = self

    def _close(self) -> None:
        tip = self._popup
        self._popup = None
        if HelpTip._open_tip is self:
            HelpTip._open_tip = None
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass


def step_connector(parent: tk.Misc, colors: dict[str, str]) -> tk.Frame:
    """Kurze Verbindungslinie zwischen Workflow-Chips."""
    wrap = tk.Frame(parent, bg=colors["bg"])
    tk.Frame(wrap, bg=colors["line"], height=2, width=16).pack(pady=16)
    return wrap
