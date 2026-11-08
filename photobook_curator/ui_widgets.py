"""Wiederverwendbare UI-Bausteine mit ausreichend Padding (kein gequetschter Text)."""

from __future__ import annotations

import tkinter as tk
import sys
from typing import Callable, Optional


FONT_UI = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
BODY_FONT_SIZE = 12


def section_header(parent: tk.Misc, text: str, colors: dict[str, str]) -> tk.Label:
    lbl = tk.Label(
        parent,
        text=text.upper(),
        bg=colors["bg"],
        fg=colors["muted"],
        font=(FONT_UI, 9, "bold"),
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
        font=(FONT_UI, 9),
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
        font=None,
        padx: int = 16,
        pady: int = 10,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.configure(takefocus=True)
        self.colors = colors
        self._command = command
        self._primary = primary
        self._enabled = True
        self._label = tk.Label(
            self,
            text=text,
            font=font or (FONT_UI, 10, "bold"),
            padx=padx,
            pady=pady,
            cursor="hand2",
        )
        self._label.pack()
        self._label.bind("<Button-1>", self._click)
        self.bind("<Button-1>", self._click)
        self._label.bind("<Enter>", lambda _e: self._hover(True))
        self._label.bind("<Leave>", lambda _e: self._hover(False))
        self.bind("<Return>", self._click)
        self.bind("<space>", self._click)
        self.bind("<FocusIn>", lambda _e: self._paint(False))
        self.bind("<FocusOut>", lambda _e: self._paint(False))
        self._paint(False)

    def configure(self, cnf=None, **kw):  # type: ignore[override]
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
        text = kw.pop("text", None)
        state = kw.pop("state", None)
        if state is not None:
            self._enabled = state != tk.DISABLED
        if text is not None:
            self._label.configure(text=text)
        if kw:
            return super().configure(**kw)
        return None

    def _click(self, _event=None) -> None:
        if self._enabled and self._command:
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
        if self.focus_get() is self:
            border = c["accent"]
        self.configure(bg=border, highlightbackground=border, highlightthickness=2)
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
        self.configure(takefocus=True, highlightthickness=1, highlightbackground=colors["surface"])
        self.variable = variable
        self.colors = colors
        self._command = command
        self._on = tk.Label(
            self,
            text=f"  {on_text}  ",
            font=(FONT_UI, 10, "bold"),
            padx=10,
            pady=7,
            cursor="hand2",
        )
        self._off = tk.Label(
            self,
            text=f"  {off_text}  ",
            font=(FONT_UI, 10, "bold"),
            padx=10,
            pady=7,
            cursor="hand2",
        )
        self._on.pack(side=tk.LEFT)
        self._off.pack(side=tk.LEFT, padx=(3, 0))
        self._on.bind("<Button-1>", lambda _e: self._set(True))
        self._off.bind("<Button-1>", lambda _e: self._set(False))
        self.bind("<space>", lambda _e: self._set(not bool(self.variable.get())))
        self.bind("<Right>", lambda _e: self._set(True))
        self.bind("<Left>", lambda _e: self._set(False))
        self.bind("<FocusIn>", lambda _e: self.configure(highlightbackground=colors["accent"]))
        self.bind("<FocusOut>", lambda _e: self.configure(highlightbackground=colors["surface"]))
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
            font=(FONT_UI, 10, "bold"),
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
        font=(FONT_UI, 9, "bold"),
        padx=10,
        pady=6,
    )


class HelpTip(tk.Label):
    """Compact contextual help, anchored to its control rather than a modal window."""

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
        self._outside_bindings: list[tuple[tk.Misc, str]] = []
        self._focus_out_job: str | None = None
        super().__init__(
            parent,
            text=" ? ",
            bg=colors.get("surface", colors.get("bg", "#111")),
            fg=colors.get("muted", "#888"),
            font=(FONT_UI, BODY_FONT_SIZE, "bold"),
            cursor="question_arrow",
            padx=3,
            pady=2,
            **kwargs,
        )
        self.configure(takefocus=True, highlightthickness=1,
                       highlightbackground=colors.get("surface", colors.get("bg", "#111")),
                       highlightcolor=colors.get("accent", "#7B6CFF"))
        self.bind("<Button-1>", self._toggle)
        self.bind("<Return>", self._toggle)
        self.bind("<space>", self._toggle)
        self.bind("<Escape>", lambda _e: self._close(restore_focus=True))
        self.bind("<Enter>", lambda _e: self.configure(fg=colors.get("accent", "#7B6CFF")))
        self.bind("<Leave>", lambda _e: self.configure(fg=colors.get("muted", "#888")))
        self.bind("<Destroy>", self._owner_destroyed)

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
        while getattr(w, "master", None) is not None:
            w = w.master
        return w

    def _toggle(self, _event=None) -> str:
        if self._popup is not None and self._popup.winfo_exists():
            self._close(restore_focus=True)
            return "break"
        if HelpTip._open_tip is not None and HelpTip._open_tip is not self:
            HelpTip._open_tip._close()
        self._show()
        return "break"

    @staticmethod
    def _inside(widget, parent: tk.Misc) -> bool:
        return widget is parent or str(widget).startswith(str(parent) + ".")

    def _outside_click(self, event) -> None:
        popup = self._popup
        if popup is not None and event.widget is not self and not self._inside(event.widget, popup):
            self._close()

    def _focus_left(self, _event=None) -> None:
        popup = self._popup
        if popup is None:
            return
        if self._focus_out_job is not None:
            try:
                self.after_cancel(self._focus_out_job)
            except tk.TclError:
                pass
        self._focus_out_job = self.after(80, self._check_focus)

    def _check_focus(self) -> None:
        self._focus_out_job = None
        popup = self._popup
        if popup is not None:
            try:
                focus = self.focus_get()
                if focus is None or not self._inside(focus, popup):
                    self._close()
            except tk.TclError:
                self._close()

    def _show(self) -> None:
        text = (self._resolve_text() or "").strip()
        if not text:
            return
        c = self.colors
        host = self.winfo_toplevel()
        tip = tk.Toplevel(host)
        tip.withdraw()
        tip.title(self._resolve_title())
        tip.transient(host)
        tip.overrideredirect(True)
        tip.configure(bg=c.get("line", "#374151"), padx=1, pady=1)
        tip.resizable(False, False)
        surface = c.get("surface", "#1a1a22")
        outer = tk.Frame(tip, bg=surface, padx=18, pady=14)
        outer.pack(fill=tk.BOTH, expand=True)
        header = tk.Frame(outer, bg=surface)
        header.pack(fill=tk.X, pady=(0, 9))
        tk.Label(header, text=self._resolve_title(), bg=surface,
                 fg=c.get("ink", "#eee"), font=(FONT_UI, BODY_FONT_SIZE, "bold"),
                 anchor=tk.W).pack(side=tk.LEFT)
        close_text = self._get_text("help_tip_close") if self._get_text else "Schliessen"
        self._close_button = tk.Button(
            header, text=close_text, command=lambda: self._close(restore_focus=True),
            bg=c.get("chip_bg", surface), fg=c.get("muted", "#aaa"),
            activebackground=c.get("accent_soft", surface), activeforeground=c.get("ink", "#eee"),
            relief=tk.FLAT, bd=0, padx=8, pady=4, cursor="hand2", takefocus=True,
            font=(FONT_UI, 10),
        )
        self._close_button.pack(side=tk.RIGHT, padx=(14, 0))
        # A short explanation determines its own height. Only genuinely long help
        # gets a bounded, scrollable text area, rather than a large empty modal.
        wrap_width = min(380, max(220, self.winfo_screenwidth() - 64))
        label = tk.Label(outer, text=text, wraplength=wrap_width, justify=tk.LEFT,
                         anchor=tk.NW, bg=surface, fg=c.get("ink", "#eee"),
                         font=(FONT_UI, BODY_FONT_SIZE))
        label.pack(fill=tk.X)
        tip.update_idletasks()
        max_body_height = max(100, min(340, int(self.winfo_screenheight() * 0.4)))
        if label.winfo_reqheight() > max_body_height:
            label.destroy()
            body = tk.Frame(outer, bg=surface)
            body.pack(fill=tk.BOTH, expand=True)
            import tkinter.font as tkfont
            line_height = tkfont.Font(tip, font=(FONT_UI, BODY_FONT_SIZE)).metrics("linespace")
            txt = tk.Text(body, wrap=tk.WORD, height=max(3, max_body_height // max(1, line_height)),
                          width=max(24, int(wrap_width / max(1, tkfont.Font(tip, font=(FONT_UI, BODY_FONT_SIZE)).measure("n")))),
                          bg=surface, fg=c.get("ink", "#eee"), relief=tk.FLAT,
                          font=(FONT_UI, BODY_FONT_SIZE), padx=0, pady=0, highlightthickness=0)
            scroll = tk.Scrollbar(body, command=txt.yview)
            txt.configure(yscrollcommand=scroll.set)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)
            txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            txt.insert("1.0", text)
            txt.configure(state=tk.DISABLED)
        tip.update_idletasks()
        width, height = tip.winfo_reqwidth(), tip.winfo_reqheight()
        # Keep the hint next to the setting, and above it if the bottom edge is near.
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 8
        if y + height > self.winfo_screenheight() - 12:
            y = self.winfo_rooty() - height - 8
        x = max(12, min(x, self.winfo_screenwidth() - width - 12))
        y = max(12, min(y, self.winfo_screenheight() - height - 12))
        tip.geometry(f"{width}x{height}+{x}+{y}")
        tip.bind("<Escape>", lambda _e: self._close(restore_focus=True))
        tip.bind("<FocusOut>", self._focus_left)
        tip.protocol("WM_DELETE_WINDOW", self._close)
        self._popup = tip
        HelpTip._open_tip = self
        # Toplevel bindtags catch clicks elsewhere in the settings dialog without
        # replacing the app's existing handlers. Unbind just our own callback.
        for parent in dict.fromkeys((host, self._root_window())):
            binding = parent.bind("<ButtonPress-1>", self._outside_click, add="+")
            self._outside_bindings.append((parent, binding))
        tip.deiconify()
        tip.lift()
        self._close_button.focus_force()

    def _owner_destroyed(self, event) -> None:
        if event.widget is self:
            self._close()

    def _close(self, *, restore_focus: bool = False) -> None:
        tip, self._popup = self._popup, None
        if self._focus_out_job is not None:
            try:
                self.after_cancel(self._focus_out_job)
            except tk.TclError:
                pass
            self._focus_out_job = None
        for parent, binding in self._outside_bindings:
            try:
                parent.unbind("<ButtonPress-1>", binding)
            except tk.TclError:
                pass
        self._outside_bindings.clear()
        if HelpTip._open_tip is self:
            HelpTip._open_tip = None
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass
        if restore_focus:
            try:
                self.focus_force()
            except tk.TclError:
                pass


def step_connector(parent: tk.Misc, colors: dict[str, str]) -> tk.Frame:
    """Kurze Verbindungslinie zwischen Workflow-Chips."""
    wrap = tk.Frame(parent, bg=colors["bg"])
    tk.Frame(wrap, bg=colors["line"], height=2, width=16).pack(pady=16)
    return wrap
