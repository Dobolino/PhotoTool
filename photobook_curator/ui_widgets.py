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
    """Kleines „?“ neben einer Option – öffnet ein echtes Hilfefenster mit Schließen (X)."""

    _open_tip: Optional["HelpTip"] = None

    def __init__(
        self,
        parent: tk.Misc,
        help_key: str,
        colors: dict[str, str],
        *,
        get_text: Optional[Callable[[str], str]] = None,
        title_key: str = "help_tip_title",
        **kwargs,
    ) -> None:
        self.help_key = help_key
        self.title_key = title_key
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

    def _resolve_title(self) -> str:
        if self._get_text is not None:
            return self._get_text(self.title_key)
        return "Hilfe"

    def _root_window(self) -> tk.Misc:
        w: tk.Misc = self
        while True:
            master = getattr(w, "master", None)
            if master is None:
                return w
            w = master

    def _toggle(self, _event=None) -> None:
        if self._popup is not None and self._popup.winfo_exists():
            try:
                self._popup.lift()
                self._popup.focus_force()
            except tk.TclError:
                self._close()
                self._show()
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
        c = self.colors
        tip = tk.Toplevel(self._root_window())
        tip.title(self._resolve_title())
        tip.configure(bg=c.get("bg", "#111"))
        try:
            tip.transient(self._root_window())
        except tk.TclError:
            pass
        tip.resizable(True, True)

        outer = tk.Frame(tip, bg=c.get("bg", "#111"), padx=16, pady=14)
        outer.pack(fill=tk.BOTH, expand=True)

        body = tk.Frame(outer, bg=c.get("surface", "#1a1a22"), padx=14, pady=12)
        body.pack(fill=tk.BOTH, expand=True)

        text_wrap = tk.Frame(body, bg=c.get("surface", "#1a1a22"))
        text_wrap.pack(fill=tk.BOTH, expand=True)
        scroll = tk.Scrollbar(text_wrap)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        txt = tk.Text(
            text_wrap,
            wrap=tk.WORD,
            height=14,
            width=52,
            bg=c.get("surface", "#1a1a22"),
            fg=c.get("ink", "#eee"),
            relief=tk.FLAT,
            font=("Segoe UI", 10),
            padx=4,
            pady=4,
            yscrollcommand=scroll.set,
            highlightthickness=0,
        )
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.configure(command=txt.yview)
        txt.insert("1.0", text)
        txt.configure(state=tk.DISABLED)

        btn_row = tk.Frame(outer, bg=c.get("bg", "#111"))
        btn_row.pack(fill=tk.X, pady=(12, 0))
        close_lbl = "Schließen"
        if self._get_text is not None:
            close_lbl = self._get_text("help_tip_close")
        close_btn = tk.Button(
            btn_row,
            text=f"✕  {close_lbl}",
            command=self._close,
            bg=c.get("chip_bg", c.get("surface", "#222")),
            fg=c.get("ink", "#eee"),
            activebackground=c.get("line", "#333"),
            activeforeground=c.get("ink", "#eee"),
            relief=tk.FLAT,
            font=("Segoe UI Semibold", 10),
            padx=14,
            pady=8,
            cursor="hand2",
        )
        close_btn.pack(side=tk.RIGHT)

        tip.bind("<Escape>", lambda _e: self._close())
        tip.protocol("WM_DELETE_WINDOW", self._close)

        tip.update_idletasks()
        try:
            tw = max(420, tip.winfo_reqwidth())
            th = max(320, tip.winfo_reqheight())
            root = self._root_window()
            rx = int(root.winfo_rootx())
            ry = int(root.winfo_rooty())
            rw = int(root.winfo_width())
            rh = int(root.winfo_height())
            x = rx + max(24, (rw - tw) // 2)
            y = ry + max(24, (rh - th) // 3)
            tip.geometry(f"{tw}x{th}+{x}+{y}")
            tip.minsize(360, 260)
        except tk.TclError:
            tip.geometry("480x360")

        self._popup = tip
        HelpTip._open_tip = self
        try:
            tip.focus_force()
        except tk.TclError:
            pass

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
