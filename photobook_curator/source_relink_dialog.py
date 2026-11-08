"""Preview-first source relocation dialog; never runs image/AI analysis."""
from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .models import Photo
from .settings import load_settings, theme_colors
from .source_relink import (
    SourceRelinkPreview, apply_source_relink, missing_source_indices, preview_source_relink,
)
from .window_layout import fit_dialog
from .ui_widgets import FONT_UI


class SourceRelinkDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, photos: list[Photo], output_dir: Path,
                 on_saved: Callable[[], None] | None = None):
        super().__init__(parent)
        self.photos, self.output_dir, self.on_saved = photos, Path(output_dir), on_saved
        self.preview: SourceRelinkPreview | None = None
        settings = load_settings()
        self._en = settings.language == 'en'
        colors = theme_colors(settings.theme)
        self.title(self._text('Originale neu verknüpfen', 'Relink originals'))
        self.configure(bg=colors['bg'])
        self.transient(parent)
        self.grab_set()
        outer = tk.Frame(self, bg=colors['bg'], padx=22, pady=20)
        outer.pack(fill=tk.BOTH, expand=True)
        tk.Label(outer, text=self._text('Deine Fotos wiederfinden', 'Reconnect your photos'),
                 bg=colors['bg'], fg=colors['ink'], font=(FONT_UI, 18, 'bold')).pack(anchor='w')
        missing = missing_source_indices(photos)
        tk.Label(outer, text=self._text(
            f'{len(missing)} von {len(photos)} Originalen fehlen. Die relative Ordnerstruktur bleibt erhalten.',
            f'{len(missing)} of {len(photos)} originals are missing. Relative folders are preserved.'),
            bg=colors['bg'], fg=colors['muted'], font=(FONT_UI, 10)).pack(anchor='w', pady=(6, 16))
        initial = ''
        try:
            paths = [str(photos[i].path.parent) for i in (missing or range(len(photos)))]
            initial = os.path.commonpath(paths) if paths else ''
        except ValueError:
            pass
        self.old_var = tk.StringVar(value=initial)
        self.new_var = tk.StringVar()
        self.missing_only = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value=self._text(
            'Wähle die bisherigen und neuen Stammordner und prüfe die Vorschau.',
            'Enter the old and new root folders, then review the preview.'))
        form = ttk.Frame(outer, padding=14)
        form.pack(fill=tk.X)
        form.columnconfigure(1, weight=1)
        for row, (label, variable) in enumerate([
                (self._text('Bisheriger Ordner', 'Old root folder'), self.old_var),
                (self._text('Neuer Ordner', 'New root folder'), self.new_var)]):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=6)
            ttk.Entry(form, textvariable=variable, width=60).grid(row=row, column=1, sticky='ew', pady=6)
            ttk.Button(form, text=self._text('Auswählen...', 'Choose...'),
                       command=lambda v=variable: self._choose(v)).grid(row=row, column=2, padx=(10, 0))
        ttk.Checkbutton(form, text=self._text('Nur fehlende Originale verknüpfen', 'Relink missing originals only'),
                        variable=self.missing_only).grid(row=2, column=1, sticky='w', pady=(8, 0))
        table_frame = ttk.Frame(outer)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=16)
        self.tree = ttk.Treeview(table_frame, columns=('status', 'old', 'new'), show='headings', height=12)
        for column, label, width in [('status', self._text('Status', 'Status'), 150),
                                     ('old', self._text('Bisherige Datei', 'Old file'), 280),
                                     ('new', self._text('Neue Datei', 'New file'), 280)]:
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, minwidth=70)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(table_frame, orient='horizontal', command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        self.tree.bind('<<TreeviewSelect>>', self._show_entry)
        ttk.Label(outer, textvariable=self.status_var, wraplength=730).pack(anchor='w')
        actions = ttk.Frame(outer)
        actions.pack(fill=tk.X, pady=(16, 0))
        ttk.Button(actions, text=self._text('Vorschau prüfen', 'Check preview'),
                   command=self._preview).pack(side=tk.LEFT)
        self.apply_btn = ttk.Button(actions, text=self._text('Verknüpfungen speichern', 'Save links'),
                                    command=self._apply, state=tk.DISABLED)
        self.apply_btn.pack(side=tk.RIGHT)
        ttk.Button(actions, text=self._text('Schliessen', 'Close'), command=self.destroy).pack(side=tk.RIGHT, padx=10)
        for variable in (self.old_var, self.new_var, self.missing_only):
            variable.trace_add('write', lambda *_: self._invalidate())
        self.update_idletasks()
        fit_dialog(self, min_width=620, min_height=460, max_frac_w=0.9)

    def _text(self, german: str, english: str) -> str:
        return english if self._en else german

    def _choose(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(parent=self)
        if selected:
            variable.set(selected)

    def _invalidate(self) -> None:
        self.preview = None
        self.apply_btn.configure(state=tk.DISABLED)

    def _preview(self) -> None:
        self._invalidate()
        self.tree.delete(*self.tree.get_children())
        try:
            preview = preview_source_relink(self.photos, self.old_var.get(), self.new_var.get(),
                                            missing_only=self.missing_only.get(), output_dir=self.output_dir)
        except (OSError, ValueError) as exc:
            self.status_var.set(str(exc))
            return
        labels = {
            'ready': self._text('Bereit', 'Ready'),
            'missing': self._text('Zieldatei fehlt', 'Target missing'),
            'ambiguous': self._text('Mehrdeutig', 'Ambiguous'),
            'outside_root': self._text('Anderer Stammordner', 'Other root'),
            'unchanged': self._text('Unverändert', 'Unchanged'),
            'invalid': self._text('Ungültiges Ziel', 'Invalid target'),
        }
        for entry in preview.entries:
            self.tree.insert('', tk.END, iid=str(entry.index), values=(labels[entry.status], str(entry.old_path),
                                                str(entry.new_path or '')))
        self.preview = preview
        self.apply_btn.configure(state=tk.NORMAL if preview.can_apply else tk.DISABLED)
        expanded = len(preview.expanded_indices)
        scope = self._text(
            f' Davon {expanded} bereits vorhandene Originale, damit die neue Projektquelle alle Entscheidungen behält.',
            f' Includes {expanded} available originals so the new project root retains all decisions.') if expanded else ''
        self.status_var.set(self._text(
            f'{len(preview.changes)} Verknüpfungen bereit. Fehlende oder mehrdeutige Ziele müssen zuerst korrigiert werden.',
            f'{len(preview.changes)} links ready. Fix missing or ambiguous targets before saving.') + scope)

    def _show_entry(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected or self.preview is None:
            return
        entry = next((entry for entry in self.preview.entries if str(entry.index) == selected[0]), None)
        if entry is not None:
            self.status_var.set(f"{entry.old_path}  ->  {entry.new_path or '?'}"
                                + (f"\n{entry.message}" if entry.message else ''))

    def _apply(self) -> None:
        if self.preview is None:
            return
        try:
            count = apply_source_relink(self.photos, self.preview, self.output_dir)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            self._invalidate()
            return
        self.status_var.set(self._text(f'{count} Originale neu verknüpft.', f'{count} originals relinked.'))
        self._invalidate()
        if self.on_saved:
            self.on_saved()
        self.destroy()


def open_source_relink(parent: tk.Misc, photos: list[Photo], output_dir: Path,
                       on_saved: Callable[[], None] | None = None) -> SourceRelinkDialog:
    return SourceRelinkDialog(parent, photos, output_dir, on_saved)
