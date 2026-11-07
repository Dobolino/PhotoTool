"""Thumbnail-Review: Auswahl prüfen, Bilder rausnehmen oder Alternativen hinzufügen."""

from __future__ import annotations

import itertools
import queue
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

from .i18n import sync_language_from_settings, t
from .models import BookPlan, Photo
from .review_export import (
    all_duplicate_indices,
    alternatives_for_index,
    apply_manual_selection,
    best_swap_candidate,
    candidate_alternatives,
    chapter_sections,
    duplicate_kind,
    related_duplicates,
)
from .review_warnings import collect_review_warnings
from .review_history import ReviewHistory
from .review_compare import RELATION_LABELS, candidate_relation, comparison_candidates, ordered_album_indices
from .print_quality import effective_dpi, print_status, write_print_report
from .selection_draft import (
    apply_selection_draft,
    load_selection_draft,
    save_selection_draft,
)
from .settings import load_settings, save_settings, theme_colors
from .utils import load_image_scaled, load_thumb_cached

FONT_UI = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
COLORS = theme_colors()

THUMB = 160
LABEL_H = 28  # Beschriftungsband unter dem Bild (vertikal zentrierter Text)
CELL_W = THUMB + 28
CELL_H = 4 + THUMB + 4 + LABEL_H + 8  # Rand, Bild, Band, Abstand
HEADER_H = 44
ALT_BTN_H = 40
GRID_PAD = 14
STRIP = 64
STRIP_WINDOW = 9  # ungerade: aktuelle Bildmitte + Nachbarn
# PhotoImage-Updates pro Tick (UI bleibt flüssig, Ordner füllt sich schneller)
_THUMBS_PER_TICK = 12
_THUMB_PENDING_MAX = 64
_SLIDE_MAX = 1600  # max. Kantenlänge in der Diashow (kleiner = schneller)
_LOADER_THREADS = 3
_ALT_LIMIT = 6  # Varianten pro Kapitel (weniger Widgets = flüssiger)
_SLIDE_CACHE_MAX = 24

# Kameranummer / kurzer Stem aus Dateiname (DSCF0491, IMG_0260, …)
_IMAGE_NUM_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])((?:DSCF?|IMG_?|P|DSC)\d{3,}|\d{4,})(?:$|[^A-Za-z0-9])",
    re.IGNORECASE,
)


def short_tile_label(filename: str, max_len: int = 12) -> str:
    """Kurze Kachel-Beschriftung: Bildnummer oder gekürzter Dateiname."""
    stem = Path(filename or "").stem
    if not stem:
        return "?"
    match = _IMAGE_NUM_RE.search(stem)
    if match:
        label = match.group(1)
    else:
        # oft reicht der vordere Teil (ohne lange Hash-/Export-Suffixe)
        suffix = re.search(r"(?:_|-)(\d{2,})$", stem)
        label = suffix.group(1) if suffix else (stem.split("_")[0] if "_" in stem else stem)
    if len(label) > max_len:
        return label[: max_len - 1] + "…"
    return label


class ReviewWindow(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        photos: list[Photo],
        plan: BookPlan,
        output_dir: Path,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master)
        sync_language_from_settings()
        self.settings = load_settings()
        global COLORS
        COLORS = theme_colors(self.settings.theme)
        self.title(t("review_title"))
        self.resizable(True, True)
        self.configure(bg=COLORS["bg"])
        self._open_large()
        # Nach Style/Build erneut – manche Windows-Setups setzen zoomed erst dann um
        self._open_large_job = self.after(80, self._open_large)

        self.photos = photos
        self.plan = plan
        self.output_dir = Path(output_dir)
        self.on_saved = on_saved
        self._filter_mode = "all"  # all | kept | removed | candidates | duplicates
        self._search_text = ""
        self._search_job = None
        self._chapter_filter = ""  # Diashow: "" = alle
        self._grid_folder = ""  # Raster: genau ein Ordner
        self._folder_labels: list[tuple[str, str]] = []  # (folder, title)
        self._known_folders: list[str] = []  # Session: auch leere Ordner nach Verschieben
        self._auto_advance = bool(self.settings.slideshow_auto_advance)
        self._show_alt_panel = bool(self.settings.slideshow_show_alternative)
        self._alt_idx: int | None = None
        self._alt_img_ref: ImageTk.PhotoImage | None = None
        self._chapters: list[str] = []

        # Startzustand: Auswahl aus CSV, ggf. Entwurf überschreibt/ergänzt
        self.kept: set[int] = {i for i, p in enumerate(photos) if p.is_selected}
        initial_selection = set(self.kept)
        self._draft_note = ""
        draft = load_selection_draft(self.output_dir)
        if draft and isinstance(draft.get("kept"), list):
            applied = apply_selection_draft(photos, draft)
            if applied or not draft["kept"]:
                self.kept = set(applied)
                self._draft_note = (
                    f"Entwurf geladen ({len(self.kept)} Bilder) – "
                    f"zuletzt {str(draft.get('updated_at') or '')[:19]}"
                )
        self.baseline: set[int] = initial_selection | self.kept
        self._history = ReviewHistory(photos)
        self._photo_images: list[ImageTk.PhotoImage] = []  # Referenzen halten
        self._thumb_cache: dict[int, ImageTk.PhotoImage] = {}
        self._slide_cache: dict[int, ImageTk.PhotoImage] = {}
        self._slide_pil: dict[int, Image.Image] = {}
        self._pending_thumbs: set[int] = set()
        # Indizes die noch geladen werden sollen (nicht verwerfen bei Warteschlangen-Limit)
        self._wanted_thumbs: dict[int, int] = {}  # idx → beste (niedrigste) Priorität
        self._thumb_failed: set[int] = set()
        # PriorityQueue: (prio, seq, job) — job = ("thumb"|"slide", idx) oder None=Stop
        self._load_queue: queue.PriorityQueue = queue.PriorityQueue()
        self._load_seq = itertools.count()
        self._ready_queue: queue.Queue[tuple[int, Image.Image | None]] = queue.Queue()
        self._slide_queue: queue.Queue[tuple[int, Image.Image | None]] = queue.Queue()
        self._pending_slides: set[int] = set()
        self._wheel_bound = False
        self._grid_cols = 6
        self._session_added: set[int] = {i for i, p in enumerate(photos) if p.review_added}
        self._preview_pool: list[int] | None = None
        self._preview_kind = "album"
        self._album_return: dict | None = None
        self._comparison_anchor_idx: int | None = None
        self._comparison_side = "candidate"
        self._anchor_img_ref = None
        self._comparison_evidence: dict[int, tuple[str, str]] = {}
        self._album_slot_contexts: list[dict] = []
        self._resume_state = (draft or {}).get("review_state", {})
        if not isinstance(self._resume_state, dict):
            self._resume_state = {}
        self._expanded_alts: set[str] = set()
        self._canvas_img_ids: dict[int, int] = {}  # photo idx → canvas image id
        self._canvas_border_ids: dict[tuple, int] = {}  # (mode, idx[, folder]) → rect
        self._hit_tiles: list[dict] = []
        self._status_flash_job: str | None = None
        self._view_save_job = None
        self._slideshow = False
        self._thumb_request_budget = 0
        self._slide_indices: list[int] = []
        self._slide_pos = 0
        self._slide_img_ref: ImageTk.PhotoImage | None = None
        self._slide_showing_idx: int | None = None
        self._strip_frames: dict[int, tk.Frame] = {}
        self._strip_thumb_labels: dict[int, tk.Label] = {}
        self._placeholder_img: ImageTk.PhotoImage | None = None
        self._loaders = [
            threading.Thread(target=self._thumb_worker, daemon=True)
            for _ in range(_LOADER_THREADS)
        ]
        for loader in self._loaders:
            loader.start()

        self._setup_style()
        self._build()
        self._restore_review_view()
        self._render()
        self._autosave_draft()
        self._thumb_after = self.after(50, self._drain_thumbs)
        self._slide_after = self.after(60, self._drain_slides)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Left>", self._slide_key_prev)
        self.bind("<Right>", self._slide_key_next)
        self.bind("<space>", self._slide_key_toggle)
        self.bind("<Return>", self._slide_key_toggle)
        self.bind("<Escape>", self._slide_key_escape)
        self.bind("<Delete>", self._slide_key_remove)
        self.bind("<BackSpace>", self._slide_key_remove)
        self.bind("<a>", self._slide_key_take_alt)
        self.bind("<A>", self._slide_key_take_alt)
        self.bind("<Prior>", self._slide_key_chapter_prev)  # PageUp
        self.bind("<Next>", self._slide_key_chapter_next)  # PageDown
        self.bind("<Control-z>", self._undo)
        self.bind("<Control-y>", self._redo)
        self.bind("<Control-Shift-Z>", self._redo)
        self.bind("<Control-s>", lambda _e: self._save_shortcut())
        self.bind("<Control-f>", lambda _e: self._focus_search())
        self.bind("<k>", lambda e: self._decision_shortcut("keep", e))
        self.bind("<x>", lambda e: self._decision_shortcut("reject", e))
        self.bind("<u>", lambda e: self._decision_shortcut("auto", e))

    def _open_large(self) -> None:
        """Groß öffnen (möglichst maximiert), frei skalierbar."""
        from .window_layout import place_window

        scale = float(self.tk.call("tk", "scaling")) / (96 / 72)
        min_width = min(round(1000 * scale), max(600, self.winfo_screenwidth() - 40))
        min_height = min(round(700 * scale), max(440, self.winfo_screenheight() - 80))
        self.minsize(min_width, min_height)

        try:
            self.update_idletasks()
        except tk.TclError:
            pass
        try:
            # Windows: maximiert
            self.state("zoomed")
            return
        except tk.TclError:
            pass
        place_window(
            self,
            frac_w=0.94,
            frac_h=0.90,
            min_width=min_width,
            min_height=min_height,
            width=1280,
            height=860,
        )

    def _refresh_workspace_tabs(self) -> None:
        if not hasattr(self, "_workspace_tabs"):
            return
        counts = {"all": len(self.baseline | self.kept), "kept": len(self.kept),
                  "removed": len(self.baseline - self.kept),
                  "candidates": sum(p.is_candidate and i not in self.kept for i, p in enumerate(self.photos)),
                  "duplicates": len(all_duplicate_indices(self.photos))}
        for mode, (button, label) in self._workspace_tabs.items():
            active = self._filter_mode == mode
            button.configure(text=f"{label}  {counts.get(mode, 0)}",
                             bg=COLORS["accent_soft"] if active else COLORS["bg"],
                             fg=COLORS["accent"] if active else COLORS["muted"],
                             activebackground=COLORS["accent_soft"], activeforeground=COLORS["accent"])

    def _set_workspace_filter(self, mode: str) -> None:
        self._workspace_page = 0
        self._filter_mode = mode
        if hasattr(self, "_filter_var"):
            self._filter_var.set(mode)
        if self._slideshow:
            self._exit_slideshow()
        self._refresh_folder_nav()
        self._render()
        self.canvas.yview_moveto(0)
        self._schedule_view_save()

    def _schedule_search(self) -> None:
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(180, self._apply_search)

    def _apply_search(self) -> None:
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except tk.TclError:
                pass
        self._search_job = None
        self._search_text = self._search_var.get().strip().casefold()
        self._workspace_page = 0
        if not self._slideshow:
            self._render()
            self.canvas.yview_moveto(0)

    def _focus_search(self) -> str:
        if self._slideshow:
            self._exit_slideshow()
        self._search_entry.focus_set()
        self._search_entry.select_range(0, tk.END)
        return "break"

    def _save_shortcut(self) -> str:
        self._autosave_draft()
        if not getattr(self, "_draft_save_error", None):
            self._flash_status("Zwischenstand gespeichert. Das Album exportierst du separat.")
        return "break"

    def _show_shortcuts(self) -> None:
        messagebox.showinfo("Schneller prüfen",
            "Bild anklicken: grosse Vorschau\n← / →: vorheriges / nächstes Bild\n"
            "Leertaste: zur Auswahl hinzufügen / entfernen\nK: dauerhaft behalten\n"
            "X: dauerhaft ablehnen\nU: dauerhafte Entscheidung aufheben\n"
            "A: Varianten öffnen / aktuelle Alternative zusätzlich aufnehmen\n"
            "Strg+Z / Strg+Y: rückgängig / wiederholen\nStrg+S: Zwischenstand speichern\n"
            "Strg+F: Suche\nEsc: zurück zum Raster\n\n"
            "Dauerhafte Entscheidungen gelten auch bei einer Neuberechnung. "
            "Geschützte Favoriten haben Vorrang.", parent=self)

    def _open_insights(self) -> None:
        from .review_workspace import open_review_assistant
        open_review_assistant(self)

    def _open_audit_report(self) -> None:
        from .review_audit_dialog import open_audit_report
        open_audit_report(self)

    def _open_location_repair(self) -> None:
        from .review_location_dialog import open_location_repair
        open_location_repair(self)

    def _open_review_pool(self, indices: list[int], label: str = "Prüfliste") -> None:
        indices = list(dict.fromkeys(i for i in indices if 0 <= i < len(self.photos)))
        if not indices:
            self._flash_status("In dieser Prüfliste gibt es keine Bilder.")
            return
        self._preview_pool = indices
        self._preview_kind = "variants"
        self._album_return = None
        self._comparison_anchor_idx = None
        self._comparison_evidence = {}
        self._enter_slideshow()
        self._slide_pos = 0
        self._show_current_slide()
        self._flash_status(label)

    def _relink_sources(self) -> None:
        from .source_relink_dialog import open_source_relink
        self._autosave_draft()
        if getattr(self, "_draft_save_error", None):
            return
        open_source_relink(self, self.photos, self.output_dir, on_saved=self._sources_relinked)

    def _sources_relinked(self) -> None:
        self._thumb_cache.clear()
        self._thumb_failed.clear()
        self._slide_cache.clear()
        self._slide_pil.clear()
        self._wanted_thumbs.clear()
        self._pending_thumbs.clear()
        self._pending_slides.clear()
        for result_queue in (self._ready_queue, self._slide_queue):
            while True:
                try:
                    result_queue.get_nowait()
                except queue.Empty:
                    break
        self._refresh_review_edit()
        self._flash_status("Originalordner aktualisiert. Die Auswahl bleibt erhalten.")

    def _text_input_active(self) -> bool:
        try:
            return isinstance(self.focus_get(), (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox))
        except (tk.TclError, AttributeError):
            return False

    def _decision_shortcut(self, decision: str, event=None) -> str | None:
        if event is not None:
            try:
                if isinstance(self.focus_get(), (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox)):
                    return None
            except (tk.TclError, AttributeError):
                pass
        if self._slideshow and self._slide_indices:
            self._set_decision(self._preview_action_index(), decision)
            return "break"
        return None

    def _set_decision(self, idx: int, decision: str, reason: str | None = None) -> None:
        from .models import set_manual_decision
        photo = self.photos[idx]
        if decision == "reject" and photo.is_favorite:
            self._flash_status("Zuerst den Favoritenschutz aufheben, um dieses Bild abzulehnen.")
            return
        set_manual_decision(photo, decision,
                            getattr(photo, "decision_reason", "") if reason is None else reason)
        if decision == "keep":
            self.kept.add(idx)
            self.baseline.add(idx)
            if not photo.chapter_folder:
                self._place_in_chapter(idx, self._grid_folder)
        elif decision == "reject":
            self.baseline.add(idx)
            self.kept.discard(idx)
        photo.is_selected = idx in self.kept
        self._autosave_draft()
        self._refresh_review_edit()
        labels = {"keep": "Dauerhaft behalten", "reject": "Dauerhaft abgelehnt",
                  "auto": "Dauerhafte Entscheidung aufgehoben"}
        self._flash_status(labels.get(decision, decision))

    def _apply_motif_recommendation(self, group) -> None:
        from .models import set_manual_decision
        recommended = set(group.recommended_indices)
        for idx in group.indices:
            photo = self.photos[idx]
            if photo.is_favorite or getattr(photo, "manual_decision", "auto") == "keep":
                continue
            if idx in recommended:
                set_manual_decision(photo, "keep", "Motivgruppe: empfohlene Variante übernommen")
                self.kept.add(idx)
                self.baseline.add(idx)
                if not photo.chapter_folder:
                    self._place_in_chapter(idx, self._grid_folder)
            else:
                set_manual_decision(photo, "reject", "Motivgruppe: andere Variante gewählt")
                self.baseline.add(idx)
                self.kept.discard(idx)
            photo.is_selected = idx in self.kept
        self._autosave_draft()
        self._refresh_review_edit()

    def _edit_decision_reason(self, idx: int) -> None:
        photo = self.photos[idx]
        reason = simpledialog.askstring("Entscheidung begründen", photo.filename,
            initialvalue=getattr(photo, "decision_reason", ""), parent=self)
        if reason is not None:
            self._set_decision(idx, getattr(photo, "manual_decision", "auto"), reason)

    def _matches_search(self, idx: int) -> bool:
        query = getattr(self, "_search_text", "")
        if not query:
            return True
        photo = self.photos[idx]
        return query in " ".join(str(value or "") for value in (
            photo.filename, photo.region, photo.scene_type, photo.landmark,
            getattr(photo, "decision_reason", ""))).casefold()

    def _render_workspace_view(self, folder: str, y: int, width: int, cols: int) -> bool:
        mode = self._filter_mode
        if mode == "all" and not getattr(self, "_search_text", ""):
            if hasattr(self, "_page_label"):
                self._page_label.configure(text="")
                self._page_prev.configure(state=tk.DISABLED)
                self._page_next.configure(state=tk.DISABLED)
            return False
        if mode == "duplicates":
            indices = all_duplicate_indices(self.photos)
            draw_mode, label = "dup", "Serien und Duplikate · alle Kapitel"
            tile_folder = "__dups__"
        elif mode == "candidates":
            indices = candidate_alternatives(self.photos, folder, limit=len(self.photos), exclude=self.kept)
            draw_mode, label, tile_folder = "add", "Weitere Bilder für dieses Kapitel", folder
        else:
            base = self.kept if mode == "kept" else (self.baseline - self.kept if mode == "removed" else self.baseline | self.kept)
            indices = [i for i in sorted(base) if not folder or self.photos[i].chapter_folder == folder]
            draw_mode, label, tile_folder = "keep", {"kept": "Im Album", "removed": "Entfernt"}.get(mode, "Suchergebnisse"), folder
        indices = [i for i in indices if self._matches_search(i)]
        page_size = 120
        pages = max(1, (len(indices) + page_size - 1) // page_size)
        page = max(0, min(getattr(self, "_workspace_page", 0), pages - 1))
        self._workspace_page = page
        if hasattr(self, "_page_label"):
            self._page_label.configure(text=f"{len(indices)} Bilder · {page + 1}/{pages}")
            self._page_prev.configure(state=tk.NORMAL if page > 0 else tk.DISABLED)
            self._page_next.configure(state=tk.NORMAL if page + 1 < pages else tk.DISABLED)
        self.canvas.create_text(GRID_PAD, y + 8, anchor=tk.NW,
            text=f"{label} · {len(indices)}", fill=COLORS["ink"],
            font=(FONT_UI, 13), tags=("grid",))
        y += HEADER_H
        if indices:
            y = self._draw_photo_rows(indices[page * page_size:(page + 1) * page_size], tile_folder, draw_mode, y, cols)
        else:
            message = "Keine passenden Bilder. Suche leeren oder eine andere Ansicht wählen."
            if mode == "removed" and not getattr(self, "_search_text", ""):
                message = "Noch keine Bilder entfernt. Deine Auswahl bleibt unverändert."
            self.canvas.create_text(GRID_PAD, y + 16, anchor=tk.NW, text=message,
                fill=COLORS["muted"], font=(FONT_UI, 11), width=max(280, width - GRID_PAD * 2), tags=("grid",))
            y += 80
        self.canvas.configure(scrollregion=(0, 0, width, max(100, y + GRID_PAD)))
        self._flush_thumb_requests()
        return True

    def _workspace_page_change(self, delta: int) -> None:
        self._workspace_page = max(0, getattr(self, "_workspace_page", 0) + delta)
        self._render()
        self.canvas.yview_moveto(0)

    def _setup_style(self) -> None:
        from tkinter import font as tkfont
        global FONT_UI
        families = {family.casefold(): family for family in tkfont.families(self)}
        for candidate in ("Segoe UI", "DejaVu Sans", "Nimbus Sans L", "Helvetica"):
            if candidate.casefold() in families:
                FONT_UI = families[candidate.casefold()]
                break
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Rev.TEntry", fieldbackground=COLORS["surface"], foreground=COLORS["ink"],
                        insertcolor=COLORS["ink"], bordercolor=COLORS["line"], padding=5)
        style.configure("Rev.TMenubutton", background=COLORS["chip_bg"], foreground=COLORS["ink"],
                        arrowcolor=COLORS["muted"], borderwidth=0, font=(FONT_UI, 10), padding=(12, 8))
        style.map("Rev.TMenubutton", background=[("active", COLORS["line"])])
        style.configure("Rev.TCombobox", fieldbackground=COLORS["surface"],
            background=COLORS["surface"], foreground=COLORS["ink"],
            arrowcolor=COLORS["muted"], borderwidth=0, padding=6)
        style.map("Rev.TCombobox", fieldbackground=[("readonly", COLORS["surface"])],
            foreground=[("readonly", COLORS["ink"])], selectbackground=[("readonly", COLORS["surface"])],
            selectforeground=[("readonly", COLORS["ink"])])
        style.configure("Rev.TFrame", background=COLORS["bg"])
        style.configure("RevCard.TFrame", background=COLORS["surface"])
        style.configure(
            "RevHead.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["ink"],
            font=(FONT_UI, 12),
        )
        style.configure(
            "RevCardHead.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["ink"],
            font=(FONT_UI, 11),
        )
        style.configure(
            "RevMuted.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["muted"],
            font=(FONT_UI, 9),
        )
        style.configure(
            "RevCardMuted.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=(FONT_UI, 9),
        )
        style.configure(
            "RevSave.TButton",
            font=(FONT_UI, 10),
            padding=(16, 10),
            background=COLORS["accent"],
            foreground=COLORS.get("hero_fg", "#FFFFFF"),
        )
        style.map(
            "RevSave.TButton",
            background=[("active", COLORS["accent_hover"])],
        )
        style.configure(
            "Rev.TButton",
            font=(FONT_UI, 10),
            padding=(14, 9),
            borderwidth=0, relief="flat",
            background=COLORS.get("chip_bg", COLORS["surface"]),
            foreground=COLORS["ink"],
        )
        style.map(
            "Rev.TButton",
            background=[("active", COLORS["line"])],
        )
        style.configure(
            "Rev.TRadiobutton",
            background=COLORS["bg"],
            foreground=COLORS["ink"],
            font=(FONT_UI, 10),
            focuscolor=COLORS["bg"],
        )
        style.map("Rev.TRadiobutton", background=[("active", COLORS["bg"])])
        for name, background in (("Compare.TButton", COLORS["chip_bg"]),
                                 ("ComparePrimary.TButton", COLORS["accent"])):
            style.configure(name, font=(FONT_UI, 12), padding=(12, 9), borderwidth=0,
                            relief="flat", background=background, foreground=COLORS["ink"])
            style.map(name, background=[("active", COLORS["accent_hover"]), ("disabled", COLORS["surface"])],
                      foreground=[("disabled", COLORS["muted"])])
        style.configure("Compare.TMenubutton", font=(FONT_UI, 12), padding=(12, 9),
                        borderwidth=0, background=COLORS["chip_bg"], foreground=COLORS["ink"])

    def _build(self) -> None:
        from .ui_widgets import PaddedButton

        tk.Frame(self, bg=COLORS["accent"], height=3).pack(fill=tk.X)
        header = tk.Frame(self, bg=COLORS["bg"], padx=24, pady=16)
        header.pack(fill=tk.X)
        actions = tk.Frame(header, bg=COLORS["bg"])
        actions.pack(side=tk.RIGHT)
        PaddedButton(actions, "Album exportieren", COLORS, command=self._save,
                     primary=True, padx=18, pady=11).pack(side=tk.RIGHT)
        PaddedButton(actions, "Pause & speichern", COLORS, command=self._close,
                     padx=14, pady=11).pack(side=tk.RIGHT, padx=(0, 10))
        titles = tk.Frame(header, bg=COLORS["bg"])
        titles.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(titles, text="FOTOBUCH  /  AUSWAHL PRÜFEN", bg=COLORS["bg"],
                 fg=COLORS["accent"], font=(FONT_UI, 9)).pack(anchor=tk.W)
        tk.Label(titles, text=self.output_dir.name or t("review_title"),
                 bg=COLORS["bg"], fg=COLORS["ink"], font=(FONT_UI, 23)
                 ).pack(anchor=tk.W, pady=(4, 0))
        self._hero_hint = tk.Label(titles,
            text="Erinnerungen auswählen. Varianten vergleichen. Dein Album fertigstellen.",
            bg=COLORS["bg"], fg=COLORS["muted"], font=(FONT_UI, 10),
            anchor=tk.W, justify=tk.LEFT)
        self._hero_hint.pack(anchor=tk.W, pady=(4, 0))

        bar = tk.Frame(self, bg=COLORS["surface"], padx=18, pady=10,
                       highlightbackground=COLORS["line"], highlightthickness=1)
        bar.pack(fill=tk.X, padx=24, pady=(0, 12))
        self.count_var = tk.StringVar()
        tk.Label(bar, textvariable=self.count_var, bg=COLORS["surface"],
                 fg=COLORS["ink"], font=(FONT_UI, 11)).pack(side=tk.LEFT)
        self.mode_btn = ttk.Button(bar, text="Grosse Vorschau", command=self._toggle_slideshow)
        self.mode_btn.pack(side=tk.LEFT, padx=(18, 8))
        self._undo_btn = ttk.Button(bar, text="Rückg.", width=6, command=self._undo)
        self._undo_btn.pack(side=tk.LEFT)
        self._redo_btn = ttk.Button(bar, text="Wiederh.", width=7, command=self._redo)
        self._redo_btn.pack(side=tk.LEFT, padx=(4, 12))
        ttk.Button(bar, text="Prüf-Assistent", command=self._open_insights).pack(side=tk.RIGHT)
        self._audit_report_button = ttk.Button(bar, text="Prüfbericht", command=self._open_audit_report)
        self._audit_report_button.pack(side=tk.RIGHT, padx=(0, 8))
        more = ttk.Menubutton(bar, text="Werkzeuge", style="Rev.TMenubutton")
        menu = tk.Menu(more, tearoff=0, bg=COLORS["surface"], fg=COLORS["ink"])
        menu.add_command(label="Druckqualität prüfen", command=self._print_check)
        menu.add_command(label="Originalordner neu verknüpfen...", command=self._relink_sources)
        menu.add_command(label="Orte neu prüfen...", command=self._open_location_repair)
        menu.add_separator()
        menu.add_command(label="Tastenkürzel", command=self._show_shortcuts)
        more.configure(menu=menu)
        more.pack(side=tk.RIGHT, padx=(0, 8))

        tabs = tk.Frame(self, bg=COLORS["bg"], padx=24)
        tabs.pack(fill=tk.X, pady=(0, 12))
        self._workspace_tabs = {}
        for mode, label in (("all", "Übersicht"), ("kept", "Im Album"),
                            ("candidates", "Weitere Bilder"), ("removed", "Entfernt"),
                            ("duplicates", "Serien & Duplikate")):
            btn = tk.Button(tabs, text=label, relief=tk.FLAT, borderwidth=0,
                            font=(FONT_UI, 9), padx=12, pady=9,
                            cursor="hand2", takefocus=True,
                            command=lambda value=mode: self._set_workspace_filter(value))
            btn.pack(side=tk.LEFT, padx=(0, 5))
            self._workspace_tabs[mode] = (btn, label)
        self._search_var = tk.StringVar(value="")
        search = ttk.Entry(tabs, textvariable=self._search_var, width=23, style="Rev.TEntry")
        search.pack(side=tk.RIGHT, ipady=5, padx=(8, 0))
        self._search_entry = search
        self._search_var.trace_add("write", lambda *_: self._schedule_search())
        search.bind("<Escape>", lambda _e: self._search_var.set(""))
        tk.Label(tabs, text="Suchen", bg=COLORS["bg"], fg=COLORS["muted"],
                 font=(FONT_UI, 9)).pack(side=tk.RIGHT)

        # Warn-Leiste (Tageslücken, Personen, Auflösung)
        self._warn_host = tk.Frame(self, bg=COLORS["bg"], padx=20)
        self._warn_host.pack(fill=tk.X, pady=(0, 8))
        self._warn_var = tk.StringVar(value="")
        self._warn_lbl = tk.Label(
            self._warn_host,
            textvariable=self._warn_var,
            bg=COLORS.get("chip_bg", COLORS["surface"]),
            fg=COLORS["muted"],
            font=(FONT_UI, 9),
            anchor=tk.W,
            justify=tk.LEFT,
            padx=10,
            pady=6,
            wraplength=900,
        )

        # Ordner-Navigation (ein Kapitel/Ordner nach dem anderen)
        nav = tk.Frame(self, bg=COLORS["bg"], padx=20)
        nav.pack(fill=tk.X, pady=(0, 8))
        self._folder_meta = tk.StringVar(value="")
        PaddedButton(
            nav,
            "< Voriges Kapitel",
            COLORS,
            command=self._grid_folder_prev,
            padx=12,
            pady=8,
        ).pack(side=tk.LEFT)
        self._grid_folder_var = tk.StringVar(value="")
        self._grid_folder_combo = ttk.Combobox(
            nav,
            textvariable=self._grid_folder_var,
            state="readonly",
            width=32, style="Rev.TCombobox",
        )
        self._grid_folder_combo.pack(side=tk.LEFT, padx=10, ipady=4)
        self._grid_folder_combo.bind("<<ComboboxSelected>>", self._on_grid_folder_chosen)
        PaddedButton(
            nav,
            "Nächstes Kapitel >",
            COLORS,
            command=self._grid_folder_next,
            padx=12,
            pady=8,
        ).pack(side=tk.LEFT)
        tk.Label(
            nav,
            textvariable=self._folder_meta,
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=(FONT_UI, 9),
        ).pack(side=tk.LEFT, padx=(14, 0))

        # Kein Banner mehr – Hinweis steht kurz in der Zählerzeile / Hilfe
        if self._draft_note:
            self._draft_note_job = self.after(100, lambda: self._flash_status(self._draft_note))

        self._body = tk.Frame(self, bg=COLORS["bg"])
        footer = tk.Frame(self, bg=COLORS["bg"], padx=24, pady=8)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        self._page_next = ttk.Button(footer, text="Weiter >", command=lambda: self._workspace_page_change(1))
        self._page_next.pack(side=tk.RIGHT)
        self._page_prev = ttk.Button(footer, text="< Zurück", command=lambda: self._workspace_page_change(-1))
        self._page_prev.pack(side=tk.RIGHT, padx=6)
        self._page_label = tk.Label(footer, text="", bg=COLORS["bg"], fg=COLORS["muted"], font=(FONT_UI, 9))
        self._page_label.pack(side=tk.RIGHT, padx=8)
        tk.Label(footer, text="Klick: Vorschau  ·  Rechtsklick: Entscheidungen  ·  Strg+S: speichern",
                 bg=COLORS["bg"], fg=COLORS["muted"], font=(FONT_UI, 9)
                 ).pack(side=tk.LEFT)
        self._body.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 4))

        self._grid_host = tk.Frame(self._body, bg=COLORS["bg"])
        self._grid_host.pack(fill=tk.BOTH, expand=True)

        # Reines Canvas-Raster (keine eingebetteten Frames) → kein Windows-Ghosting
        self.canvas = tk.Canvas(
            self._grid_host,
            bg=COLORS["bg"],
            highlightthickness=0,
            bd=0,
            yscrollincrement=40,
        )
        self._vscroll = tk.Scrollbar(
            self._grid_host,
            orient=tk.VERTICAL,
            command=self.canvas.yview,
            bg=COLORS.get("chip_bg", COLORS["surface"]),
            troughcolor=COLORS["bg"],
            activebackground=COLORS["accent"],
            width=14,
        )
        self.canvas.configure(yscrollcommand=self._vscroll.set)
        self._vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Button-1>", self._on_grid_click)
        self.canvas.bind("<Button-3>", self._on_grid_right_click)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda _e: self._scroll_units(-3))
        self.canvas.bind("<Button-5>", lambda _e: self._scroll_units(3))
        self._install_wheel()

        self._slide_host = tk.Frame(self._body, bg=COLORS["bg"])
        self._build_slideshow_ui()
        self._style_review_buttons(self)
        self._ensure_placeholder()
        self._refresh_folder_nav(select_first=True)
        self._grid_chrome = [(widget, widget.pack_info()) for widget in
                             (header, bar, tabs, self._warn_host, nav, footer)]
        self._body_grid_pack = self._body.pack_info()

    def _style_review_buttons(self, widget) -> None:
        for child in widget.winfo_children():
            if isinstance(child, ttk.Button) and not child.cget("style"):
                child.configure(style="Rev.TButton")
            self._style_review_buttons(child)

    def _schedule_view_save(self) -> None:
        if self._view_save_job is not None:
            self.after_cancel(self._view_save_job)
        def save():
            self._view_save_job = None
            self._autosave_draft()
        self._view_save_job = self.after(700, save)

    def _review_view_state(self) -> dict:
        current = (str(self.photos[self._slide_indices[self._slide_pos]].path)
                   if self._slideshow and self._slide_indices else "")
        return dict(folder=self._grid_folder, slideshow=self._slideshow, preview_kind=self._preview_kind,
            album_return=self._album_return,
            album_slot_contexts=self._album_slot_contexts[-100:],
            comparison_evidence=[dict(path=str(self.photos[i].path), code=relation[0])
                                 for i, relation in self._comparison_evidence.items()],
            comparison_side=self._comparison_side,
            current_photo=current, filter=self._filter_mode,
            expanded=list(self._expanded_alts), baseline=[str(self.photos[i].path)
                for i in sorted(self.baseline)],
            preview=[str(self.photos[i].path) for i in self._preview_pool]
                if self._preview_pool is not None else None,
            search=getattr(self, "_search_text", ""), page=getattr(self, "_workspace_page", 0),
            scroll=self.canvas.yview()[0])

    def _restore_review_view(self) -> None:
        state = self._resume_state
        self._album_return = state.get("album_return") if isinstance(state.get("album_return"), dict) else None
        self._comparison_anchor_idx = None
        self._comparison_evidence = {}
        self._comparison_side = "anchor" if state.get("comparison_side") == "anchor" else "candidate"
        self._album_slot_contexts = [entry for entry in state.get("album_slot_contexts", []) if isinstance(entry, dict)][-100:]
        by_path = {str(p.path): i for i, p in enumerate(self.photos)}
        for entry in state.get("comparison_evidence", []):
            if isinstance(entry, dict) and entry.get("path") in by_path and entry.get("code") in RELATION_LABELS:
                code = entry["code"]
                self._comparison_evidence[by_path[entry["path"]]] = (code, RELATION_LABELS[code])
        self.baseline.update(by_path[p] for p in state.get("baseline", []) if p in by_path)
        self._expanded_alts = {p for p in state.get("expanded", []) if isinstance(p, str)}
        folder = state.get("folder")
        if folder in {f for f, _ in self._folder_labels}:
            self._grid_folder = folder
            self._refresh_folder_nav()
        mode = state.get("filter", "all")
        if mode in ("all", "kept", "removed", "duplicates", "candidates"):
            self._filter_mode = mode
            self._filter_var.set(mode)
        search = state.get("search", "")
        if isinstance(search, str):
            self._search_text = search[:300].casefold()
            self._search_var.set(self._search_text)
        page = state.get("page", 0)
        self._workspace_page = page if isinstance(page, int) and page >= 0 else 0
        if state.get("slideshow"):
            pool = state.get("preview")
            if isinstance(pool, list):
                self._preview_pool = [by_path[p] for p in pool if isinstance(p, str) and p in by_path]
                self._preview_kind = "variants" if state.get("preview_kind") == "variants" else "album"
            self._enter_slideshow()
            idx = by_path.get(state.get("current_photo"))
            if idx in self._slide_indices:
                self._slide_pos = self._slide_indices.index(idx)
                self._show_current_slide()
        else:
            scroll = state.get("scroll", 0)
            if isinstance(scroll, (int, float)):
                self.after_idle(lambda: self.canvas.yview_moveto(max(0, min(1, scroll))))

    def _open_photo_preview(self, idx: int, folder: str = "") -> None:
        self._album_return = None
        self._comparison_anchor_idx = None
        self._comparison_evidence = {}
        self._preview_kind = "album" if idx in self.baseline else "variants"
        if idx in self.kept:
            pool = ordered_album_indices(self.photos, self.kept)
        else:
            pool = list(dict.fromkeys(hit["idx"] for hit in self._hit_tiles
                        if hit["kind"] == "photo" and hit.get("folder", "") == folder
                        and (hit["mode"] in ("add", "dup")) == (idx not in self.baseline)))
        if idx not in pool:
            pool = [idx]
        self._preview_pool = pool
        if folder:
            self._grid_folder = folder
        self._enter_slideshow()
        self._slide_pos = self._slide_indices.index(idx)
        self._show_current_slide()

    def _ensure_placeholder(self) -> None:
        if self._placeholder_img is not None:
            return
        img = Image.new("RGB", (THUMB, THUMB), COLORS.get("thumb_pad", COLORS["line"]))
        self._placeholder_img = ImageTk.PhotoImage(img)
        self._photo_images.append(self._placeholder_img)

    def _on_canvas_configure(self, event) -> None:
        if self._slideshow or event.width < 80:
            return
        cols = max(1, (int(event.width) - GRID_PAD * 2) // CELL_W)
        if cols == self._grid_cols:
            return
        self._grid_cols = cols
        try:
            top = self.canvas.yview()[0]
        except tk.TclError:
            top = 0.0
        self._render()
        try:
            self.canvas.yview_moveto(top)
        except tk.TclError:
            pass

    def _install_wheel(self) -> None:
        if self._wheel_bound:
            return
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_linux_scroll_up)
        self.bind_all("<Button-5>", self._on_linux_scroll_down)
        self._wheel_bound = True

    def _unbind_wheel(self, _event=None) -> None:
        if not self._wheel_bound:
            return
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.unbind_all(seq)
            except Exception:
                pass
        self._wheel_bound = False

    def _pointer_in_grid(self) -> bool:
        try:
            if not self.winfo_exists() or self._slideshow:
                return False
            x, y = self.winfo_pointerxy()
            widget = self.winfo_containing(x, y)
            w = widget
            while w is not None:
                if w in (self.canvas, self._vscroll, self._grid_host):
                    return True
                w = getattr(w, "master", None)
            return False
        except tk.TclError:
            return False

    def _scroll_units(self, units: int) -> None:
        if self.winfo_exists() and not self._slideshow:
            self.canvas.yview_scroll(units, "units")

    def _on_linux_scroll_up(self, _event=None) -> None:
        if self._pointer_in_grid():
            self._scroll_units(-3)

    def _on_linux_scroll_down(self, _event=None) -> None:
        if self._pointer_in_grid():
            self._scroll_units(3)

    def _on_mousewheel(self, event) -> str | None:
        if not self._pointer_in_grid():
            return None
        delta = int(getattr(event, "delta", 0) or 0)
        if delta == 0:
            return None
        steps = -1 if delta > 0 else 1
        if abs(delta) >= 120:
            steps = int(-1 * (delta / 120))
        self._scroll_units(max(-8, min(8, steps * 3)))
        return "break"

    def _build_slideshow_ui(self) -> None:
        from .review_compare_view import build_preview
        build_preview(self, COLORS, FONT_UI)

    def _set_preview_chrome(self, preview: bool) -> None:
        if preview:
            for widget, _options in self._grid_chrome:
                widget.pack_forget()
            self._body.pack_configure(padx=16, pady=12)
        else:
            for widget, options in self._grid_chrome:
                widget.pack(before=self._body, **options)
            self._body.pack_configure(**self._body_grid_pack)

    def _comparison_anchor(self) -> int | None:
        anchor = self._comparison_anchor_idx
        if anchor is None and self._album_return:
            path = self._album_return.get("anchor", self._album_return.get("photo"))
            anchor = next((i for i, p in enumerate(self.photos) if str(p.path) == path), None)
            self._comparison_anchor_idx = anchor
        return anchor

    def _comparison_slot(self) -> int | None:
        anchor = self._comparison_anchor()
        if anchor is not None and anchor in self.kept:
            return anchor
        paths = (self._album_return or {}).get("replacements", [])
        if not paths and (self._album_return or {}).get("replacement"):
            paths = [self._album_return["replacement"]]
        by_path = {str(photo.path): i for i, photo in enumerate(self.photos)}
        return next((by_path[path] for path in reversed(paths) if path in by_path and by_path[path] in self.kept), None)

    def _set_comparison_side(self, side: str) -> None:
        self._comparison_side = side
        self._fit_comparison_panels()
        self._refresh_slide_meta()

    def _preview_action_index(self) -> int | None:
        if not self._slide_indices:
            return None
        if (self._preview_kind == "variants" and getattr(self, "_comparison_compact", False)
                and self._comparison_side == "anchor" and self._comparison_anchor() is not None):
            return self._comparison_anchor()
        return self._slide_indices[self._slide_pos]

    def _fit_comparison_panels(self) -> None:
        if not self._slideshow:
            return
        pair = self._preview_kind == "variants" and self._comparison_anchor() is not None
        self._anchor_panel.grid_forget()
        self._current_panel.grid_forget()
        self._comparison_switcher.pack_forget()
        scale = float(self.tk.call("tk", "scaling")) / (96 / 72)
        wide = self._comparison_stage_row.winfo_width() >= round(1000 * scale)
        compact = pair and not wide
        changed = getattr(self, "_comparison_compact", False) != compact
        self._comparison_compact = compact
        if pair and wide:
            self._anchor_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
            self._current_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        elif pair:
            self._comparison_switcher.pack(fill=tk.X, pady=(0, 8), before=self._comparison_stage_row)
            panel = self._anchor_panel if self._comparison_side == "anchor" else self._current_panel
            panel.grid(row=0, column=0, columnspan=2, sticky="nsew")
        else:
            self._current_panel.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self._anchor_view_btn.configure(style="ComparePrimary.TButton" if self._comparison_side == "anchor" else "Compare.TButton")
        self._candidate_view_btn.configure(style="ComparePrimary.TButton" if self._comparison_side == "candidate" else "Compare.TButton")
        self._show_anchor_image()
        if changed:
            self._refresh_slide_meta()

    def _show_anchor_image(self) -> None:
        anchor = self._comparison_anchor()
        if anchor is None or self._preview_kind != "variants" or not self._slideshow:
            return
        pil = self._slide_pil.get(anchor)
        if pil is not None:
            fitted = pil.copy()
            fitted.thumbnail((max(160, self._anchor_stage.winfo_width() - 16),
                              max(160, self._anchor_stage.winfo_height() - 16)), Image.Resampling.LANCZOS)
            image = ImageTk.PhotoImage(fitted)
        else:
            image = self._thumb_cache.get(anchor)
            self._request_slide(anchor, priority=0)
        self._anchor_img_ref = image
        self._anchor_image_lbl.configure(image=image or "", text="" if image else "Albumfoto wird geladen...")

    def _explain_anchor(self) -> None:
        anchor = self._comparison_anchor()
        if anchor is not None:
            self._explain(anchor)

    def _on_slide_stage_configure(self, event=None) -> None:
        if not self._slideshow or self._slide_showing_idx is None:
            return
        w = int(getattr(event, "width", 0) or 0)
        h = int(getattr(event, "height", 0) or 0)
        prev = getattr(self, "_slide_stage_size", (0, 0))
        if abs(prev[0] - w) < 12 and abs(prev[1] - h) < 12:
            return
        self._slide_stage_size = (w, h)
        idx = self._slide_showing_idx
        if idx in self._slide_pil:
            self.after_idle(lambda i=idx: self._show_slide_image(i) if self._slideshow else None)

    def _enqueue_job(self, kind: str, idx: int, priority: int) -> None:
        self._load_queue.put((priority, next(self._load_seq), (kind, idx)))

    def _thumb_worker(self) -> None:
        while True:
            _prio, _seq, job = self._load_queue.get()
            if job is None:
                break
            kind, real = job
            if real < 0 or real >= len(self.photos):
                continue
            photo = self.photos[real]
            source_path = photo.path
            try:
                if kind == "slide":
                    # Ein Decode für großes Bild; Thumb gleich mit erzeugen
                    img = load_image_scaled(source_path, _SLIDE_MAX)
                    if photo.path != source_path:
                        continue
                    self._slide_queue.put((real, img.copy()))
                    if real not in self._thumb_cache:
                        thumb = img.copy()
                        thumb.thumbnail((THUMB, THUMB), Image.Resampling.BILINEAR)
                        pad = COLORS.get("thumb_pad", "#F5F1E9")
                        canvas_img = Image.new("RGB", (THUMB, THUMB), pad)
                        x = (THUMB - thumb.width) // 2
                        y = (THUMB - thumb.height) // 2
                        canvas_img.paste(thumb, (x, y))
                        self._ready_queue.put((real, canvas_img))
                else:
                    img = load_thumb_cached(source_path, THUMB)
                    if photo.path != source_path:
                        continue
                    pad = COLORS.get("thumb_pad", "#F5F1E9")
                    canvas_img = Image.new("RGB", (THUMB, THUMB), pad)
                    x = (THUMB - img.width) // 2
                    y = (THUMB - img.height) // 2
                    canvas_img.paste(img, (x, y))
                    self._ready_queue.put((real, canvas_img))
            except Exception:
                if photo.path != source_path:
                    continue
                if kind == "slide":
                    self._slide_queue.put((real, None))
                else:
                    self._ready_queue.put((real, None))

    def _request_thumb(self, idx: int, priority: int = 40) -> None:
        """Thumb anfordern – nie still verwerfen; Limit nur drosselt die parallele Queue."""
        if idx in self._thumb_cache or idx in self._thumb_failed:
            return
        if idx in self._pending_thumbs:
            return
        prev = self._wanted_thumbs.get(idx)
        if prev is None or priority < prev:
            self._wanted_thumbs[idx] = priority
        self._flush_thumb_requests()

    def _flush_thumb_requests(self) -> None:
        """Füllt die Lade-Queue aus _wanted_thumbs nach, sobald Platz ist."""
        while self._wanted_thumbs and len(self._pending_thumbs) < _THUMB_PENDING_MAX:
            idx = min(self._wanted_thumbs, key=self._wanted_thumbs.get)
            prio = self._wanted_thumbs.pop(idx)
            if idx in self._thumb_cache or idx in self._thumb_failed or idx in self._pending_thumbs:
                continue
            self._pending_thumbs.add(idx)
            self._enqueue_job("thumb", idx, prio)

    def _request_slide(self, idx: int, priority: int = 10) -> None:
        if idx in self._slide_pil or idx in self._pending_slides:
            return
        if len(self._pending_slides) > 12 and priority > 2:
            return
        self._pending_slides.add(idx)
        self._enqueue_job("slide", idx, priority)
        self._request_thumb(idx, priority=priority + 5)

    def _trim_slide_cache(self) -> None:
        """Alte Diashow-Bilder verwerfen, damit RAM/Tk nicht anschwellen."""
        if len(self._slide_pil) <= _SLIDE_CACHE_MAX:
            return
        keep: set[int] = set()
        if self._slide_indices and 0 <= self._slide_pos < len(self._slide_indices):
            for off in range(-2, 5):
                n = self._slide_pos + off
                if 0 <= n < len(self._slide_indices):
                    keep.add(self._slide_indices[n])
        if self._alt_idx is not None:
            keep.add(self._alt_idx)
        if self._comparison_anchor() is not None:
            keep.add(self._comparison_anchor())
        for idx in list(self._slide_pil.keys()):
            if idx not in keep and len(self._slide_pil) > _SLIDE_CACHE_MAX // 2:
                self._slide_pil.pop(idx, None)
                self._slide_cache.pop(idx, None)

    def _drain_thumbs(self) -> None:
        updated = 0
        try:
            while updated < _THUMBS_PER_TICK:
                idx, canvas_img = self._ready_queue.get_nowait()
                self._pending_thumbs.discard(idx)
                if canvas_img is None:
                    self._thumb_failed.add(idx)
                    continue
                tk_img = ImageTk.PhotoImage(canvas_img)
                self._thumb_cache[idx] = tk_img
                img_id = self._canvas_img_ids.get(idx)
                if img_id is not None:
                    try:
                        self.canvas.itemconfigure(img_id, image=tk_img)
                    except tk.TclError:
                        pass
                if self._slideshow:
                    if (
                        self._slide_showing_idx == idx
                        and idx not in self._slide_cache
                    ):
                        self._show_slide_placeholder(idx)
                    if idx in self._strip_frames:
                        self._apply_strip_thumb(idx)
                updated += 1
        except queue.Empty:
            pass
        # Nach abgeschlossenen Jobs die zurückgestellten Ordner-Bilder nachschieben
        self._flush_thumb_requests()
        if self.winfo_exists():
            delay = 25 if (updated or self._wanted_thumbs or self._pending_thumbs) else 100
            self._thumb_after = self.after(delay, self._drain_thumbs)

    def _drain_slides(self) -> None:
        try:
            while True:
                idx, img = self._slide_queue.get_nowait()
                self._pending_slides.discard(idx)
                if img is None:
                    continue
                self._slide_pil[idx] = img
                # Grobes Preview für Cache/Alt; Anzeige skaliert zusätzlich auf Stage
                preview = img.copy()
                preview.thumbnail((_SLIDE_MAX, _SLIDE_MAX), Image.Resampling.BILINEAR)
                tk_img = ImageTk.PhotoImage(preview)
                self._slide_cache[idx] = tk_img
                if self._slideshow and self._slide_showing_idx == idx:
                    self._show_slide_image(idx)
                if self._slideshow and self._alt_idx == idx:
                    self._refresh_alt_panel()
                if self._slideshow and self._comparison_anchor() == idx:
                    self._show_anchor_image()
                self._trim_slide_cache()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self._slide_after = self.after(50, self._drain_slides)

    def _update_count(self) -> None:
        error = getattr(self, "_draft_save_error", None)
        self.count_var.set(f"Zwischenstand nicht gespeichert: {error}" if error
                           else t("selected_count", n=len(self.kept)))
        self._refresh_warnings()
        self._refresh_workspace_tabs()
        if self._slideshow:
            self._refresh_slide_meta()

    def _refresh_warnings(self) -> None:
        """Aktualisiert die Warn-Leiste unter der Zählerzeile."""
        try:
            warns = collect_review_warnings(
                self.photos,
                self.kept,
                folder=self._grid_folder or None,
            )
        except Exception:
            warns = []
        if not warns:
            self._warn_var.set("")
            try:
                self._warn_lbl.pack_forget()
            except tk.TclError:
                pass
            return
        # Max. 3 Hinweise, mit Trenner
        parts: list[str] = []
        for w in warns[:3]:
            try:
                parts.append(t(w.key, **w.params).replace("⚠ ", "Hinweis: "))
            except Exception:
                parts.append(w.key)
        self._warn_var.set("  ·  ".join(parts))
        try:
            if not self._warn_lbl.winfo_ismapped():
                self._warn_lbl.pack(fill=tk.X)
        except tk.TclError:
            pass

    def _display_indices(self) -> list[int]:
        """Review-Menge: Baseline ∪ Kept, bei Filter „Duplikate“ die aussortierten."""
        if self._filter_mode == "duplicates":
            return all_duplicate_indices(self.photos)
        if self._filter_mode == "candidates":
            return candidate_alternatives(self.photos, self._grid_folder, limit=len(self.photos), exclude=self.kept)
        return sorted(self.baseline | self.kept)

    def _chapter_list(self) -> list[str]:
        return [folder for folder, _title in self._folder_entries()]

    def _folder_title(self, folder: str) -> str:
        return folder.replace("/", " · ").replace("\\", " · ").replace("_", " ")

    def _folder_entries(self) -> list[tuple[str, str]]:
        """[(folder, title), ...] in Buch-Reihenfolge; leere Session-Ordner bleiben navigierbar."""
        display = sorted(self.baseline | self.kept)
        sections = chapter_sections(self.photos, display)
        by_folder = {folder: title for title, folder, _idx in sections}
        from .documents import ASIDE_FOLDER, aside_indices

        aside = [
            i
            for i in aside_indices(self.photos)
            if i not in self.kept and not self.photos[i].is_duplicate
        ]
        if aside:
            by_folder.setdefault(ASIDE_FOLDER, self._folder_title(ASIDE_FOLDER))

        for folder in by_folder:
            if folder not in self._known_folders:
                self._known_folders.append(folder)
        if self._grid_folder and self._grid_folder not in self._known_folders:
            self._known_folders.append(self._grid_folder)

        return [
            (folder, by_folder.get(folder) or self._folder_title(folder))
            for folder in self._known_folders
        ]

    def _refresh_folder_nav(self, select_first: bool = False) -> None:
        self._folder_labels = self._folder_entries()
        titles = [title for _f, title in self._folder_labels]
        try:
            self._grid_folder_combo.configure(values=titles)
        except tk.TclError:
            return
        if not self._folder_labels:
            self._grid_folder = ""
            self._grid_folder_var.set("")
            self._folder_meta.set("")
            return
        folders = [f for f, _t in self._folder_labels]
        if select_first or self._grid_folder not in folders:
            self._grid_folder = folders[0]
        title = dict(self._folder_labels).get(self._grid_folder, self._folder_title(self._grid_folder))
        self._grid_folder_var.set(title)
        self._update_folder_meta()

    def _update_folder_meta(self) -> None:
        folders = [f for f, _t in self._folder_labels]
        if not folders or not self._grid_folder:
            self._folder_meta.set("")
            return
        try:
            i = folders.index(self._grid_folder) + 1
        except ValueError:
            i = 1
        n_in = sum(
            1
            for idx in self._display_indices()
            if (self.photos[idx].chapter_folder or "") == self._grid_folder
        )
        # Aside-Pool zählen
        from .documents import ASIDE_FOLDER, aside_indices

        if self._grid_folder == ASIDE_FOLDER:
            n_in = max(
                n_in,
                len(
                    [
                        j
                        for j in aside_indices(self.photos)
                        if j not in self.kept and not self.photos[j].is_duplicate
                    ]
                ),
            )
        self._folder_meta.set(
            f"{t('folder_of', i=i, n=len(folders))}  ·  {t('folder_count', n=n_in)}"
        )
        self._refresh_warnings()

    def _on_grid_folder_chosen(self, _event=None) -> None:
        title = self._grid_folder_var.get()
        for folder, label in self._folder_labels:
            if label == title:
                self._grid_folder = folder
                break
        self._apply_folder_change(reset_slide=True)

    def _grid_folder_prev(self) -> None:
        folders = [f for f, _t in self._folder_labels]
        if not folders:
            return
        try:
            i = folders.index(self._grid_folder)
        except ValueError:
            i = 0
        self._grid_folder = folders[(i - 1) % len(folders)]
        self._apply_folder_change(reset_slide=True)

    def _grid_folder_next(self) -> None:
        folders = [f for f, _t in self._folder_labels]
        if not folders:
            return
        try:
            i = folders.index(self._grid_folder)
        except ValueError:
            i = 0
        self._grid_folder = folders[(i + 1) % len(folders)]
        self._apply_folder_change(reset_slide=True)

    def _apply_folder_change(self, *, reset_slide: bool = False) -> None:
        self._schedule_view_save()
        """Ordnerwechsel: Raster neu zeichnen oder Diashow auf diesen Ordner setzen."""
        self._preview_pool = None
        self._refresh_folder_nav()
        if self._slideshow:
            self._sync_slide_chapter_to_grid_folder()
            self._reapply_slide_filter(keep_photo=not reset_slide)
            return
        self._render()
        try:
            self.canvas.yview_moveto(0)
        except tk.TclError:
            pass

    def _sync_slide_chapter_to_grid_folder(self) -> None:
        """Diashow-Kapitel-Filter = aktueller Ordner aus der oberen Navigation."""
        folder = self._grid_folder or ""
        self._chapter_filter = folder
        try:
            self._chapters = self._chapter_list()
            values = [t("chapter_all")] + [
                c for c in self._chapters if c != folder
            ]
            if folder:
                values = [t("chapter_all"), folder] + [
                    c for c in self._chapters if c != folder
                ]
            self._chapter_combo.configure(values=values)
            self._chapter_var.set(folder if folder else t("chapter_all"))
        except tk.TclError:
            pass

    def _move_photo_to_folder(self, idx: int, target_folder: str) -> None:
        """Bild in einen anderen Kapitelordner legen; Entwurf speichert chapter_folder."""
        if idx < 0 or idx >= len(self.photos) or not target_folder:
            return
        if not self._can_add_photo(idx):
            return
        photo = self.photos[idx]
        current = photo.chapter_folder or ""
        if current == target_folder and not (
            photo.is_aside and not target_folder.startswith("99_")
        ):
            return
        self._assign_chapter(idx, target_folder)
        self.kept.add(idx)
        self.baseline.add(idx)
        photo.is_selected = True
        self._autosave_draft()
        self._flash_status(t("moved_to", folder=self._folder_title(target_folder)))
        self._refresh_folder_nav()
        # Im aktuellen Ordner bleiben – Bild ist dort weg; Ziel per ←/→ oder Combobox
        self._render()

    def _filtered_slide_indices(self) -> list[int]:
        if self._preview_pool is not None:
            return list(self._preview_pool)
        indices = self._display_indices()
        if self._filter_mode in ("duplicates", "candidates"):
            return indices
        if self._chapter_filter:
            indices = [
                i
                for i in indices
                if (self.photos[i].chapter_folder or self.photos[i].region or "")
                == self._chapter_filter
            ]
        if self._filter_mode == "kept":
            indices = [i for i in indices if i in self.kept]
        elif self._filter_mode == "removed":
            indices = [i for i in indices if i not in self.kept]
        return indices

    def _refresh_chapter_combo(self) -> None:
        self._chapters = self._chapter_list()
        values = [t("chapter_all")] + self._chapters
        try:
            self._chapter_combo.configure(values=values)
            if self._chapter_filter and self._chapter_filter in self._chapters:
                self._chapter_var.set(self._chapter_filter)
            else:
                self._chapter_filter = ""
                self._chapter_var.set(t("chapter_all"))
        except tk.TclError:
            pass

    def _on_filter_changed(self) -> None:
        self._filter_mode = self._filter_var.get() or "all"
        self._workspace_page = 0
        if self._slideshow:
            self._reapply_slide_filter(keep_photo=True)
        else:
            self._refresh_folder_nav()
            self._render()

    def _on_chapter_changed(self, _event=None) -> None:
        val = self._chapter_var.get()
        if val == t("chapter_all") or not val:
            self._chapter_filter = ""
        else:
            self._chapter_filter = val
            # Obere Ordner-Navigation mitziehen
            if val in {f for f, _t in self._folder_labels}:
                self._grid_folder = val
                self._refresh_folder_nav()
        self._reapply_slide_filter(keep_photo=True)

    def _toggle_auto_advance(self) -> None:
        self._auto_advance = not self._auto_advance
        try:
            self._auto_btn.configure(
                text=t("auto_on") if self._auto_advance else t("auto_off")
            )
        except tk.TclError:
            pass
        try:
            self.settings.slideshow_auto_advance = self._auto_advance
            save_settings(self.settings)
        except Exception:
            pass

    def _reapply_slide_filter(self, keep_photo: bool = True) -> None:
        current = None
        if keep_photo and self._slide_indices and 0 <= self._slide_pos < len(self._slide_indices):
            current = self._slide_indices[self._slide_pos]
        indices = self._filtered_slide_indices()
        self._slide_indices = indices
        if current is not None and current in indices:
            self._slide_pos = indices.index(current)
        else:
            self._slide_pos = 0
        if self._slideshow:
            if not indices:
                try:
                    self._slide_image_lbl.configure(
                        image="", text=t("no_slide_photos")
                    )
                except tk.TclError:
                    pass
                self._slide_status.set(t("no_slide_photos"))
                self._clear_alt_panel()
                return
            self._show_current_slide()

    def _toggle_slideshow(self) -> None:
        if self._slideshow:
            self._exit_slideshow()
        else:
            self._enter_slideshow()

    def _enter_slideshow(self) -> None:
        if not (self._preview_pool if self._preview_pool is not None else self._display_indices()):
            messagebox.showinfo(
                t("review_title"),
                t("no_slide_photos"),
            )
            return
        self._slideshow = True
        self._set_preview_chrome(True)
        # Gleicher Ordner wie im Raster
        self._sync_slide_chapter_to_grid_folder()
        indices = self._filtered_slide_indices()
        # Fallback: wenn Ordner leer (Filter), alle Bilder zeigen
        if not indices and self._chapter_filter:
            self._chapter_filter = ""
            try:
                self._chapter_var.set(t("chapter_all"))
            except tk.TclError:
                pass
            indices = self._filtered_slide_indices()
        self._slide_indices = indices
        self._slide_pos = 0
        try:
            self._grid_host.pack_forget()
        except tk.TclError:
            pass
        self._slide_host.pack(fill=tk.BOTH, expand=True)
        self.mode_btn.configure(text=t("grid_view"))
        self._hero_hint.configure(text=t("review_hint_slide"))
        self._unbind_wheel()
        self._show_current_slide()
        try:
            self.focus_set()
        except tk.TclError:
            pass

    def _exit_slideshow(self) -> None:
        self._preview_pool = None
        self._preview_kind = "album"
        self._album_return = None
        self._comparison_anchor_idx = None
        self._comparison_evidence = {}
        if not self._slideshow:
            return
        self._slideshow = False
        self._set_preview_chrome(False)
        try:
            self._slide_host.pack_forget()
        except tk.TclError:
            pass
        self._grid_host.pack(fill=tk.BOTH, expand=True)
        self.mode_btn.configure(text=t("slideshow"))
        self._hero_hint.configure(text=t("review_hint_grid"))
        self._render()

    def _show_current_slide(self) -> None:
        self._schedule_view_save()
        if not self._slide_indices:
            return
        self._slide_pos = max(0, min(self._slide_pos, len(self._slide_indices) - 1))
        idx = self._slide_indices[self._slide_pos]
        self._slide_showing_idx = idx
        self._refresh_slide_meta()
        self._rebuild_filmstrip()
        self._refresh_alt_panel()
        self._fit_comparison_panels()
        if idx in self._slide_pil or idx in self._slide_cache:
            self._show_slide_image(idx)
        else:
            if not self._show_slide_placeholder(idx):
                try:
                    self._slide_image_lbl.configure(
                        image="",
                        text=t("loading_image"),
                        fg=COLORS.get("slide_fg", "#E8E2D8"),
                    )
                except tk.TclError:
                    pass
                self._slide_img_ref = None
            self._request_slide(idx, priority=0)
        # Nur nahe Nachbarn vorladen (weniger OneDrive-Last)
        for dist in (1, 2):
            for n in (self._slide_pos + dist, self._slide_pos - dist):
                if 0 <= n < len(self._slide_indices):
                    self._request_slide(self._slide_indices[n], priority=dist)

    def _show_slide_placeholder(self, idx: int) -> bool:
        tk_img = self._thumb_cache.get(idx)
        if tk_img is None:
            self._request_thumb(idx, priority=1)
            return False
        self._slide_img_ref = tk_img
        try:
            self._slide_image_lbl.configure(image=tk_img, text="")
        except tk.TclError:
            return False
        return True

    def _show_slide_image(self, idx: int) -> None:
        pil = self._slide_pil.get(idx)
        if pil is None:
            cached = self._slide_cache.get(idx)
            if cached is None:
                return
            self._slide_img_ref = cached
            try:
                self._slide_image_lbl.configure(image=cached, text="")
            except tk.TclError:
                pass
            return
        try:
            max_w = max(160, int(self._slide_stage.winfo_width()) - 20)
            max_h = max(160, int(self._slide_stage.winfo_height()) - 20)
        except (tk.TclError, AttributeError, ValueError):
            max_w = max_h = _SLIDE_MAX
        fitted = pil.copy()
        fitted.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        tk_img = ImageTk.PhotoImage(fitted)
        self._slide_img_ref = tk_img
        try:
            self._slide_image_lbl.configure(image=tk_img, text="")
        except tk.TclError:
            pass

    def _photo_quality_notes(self, photo) -> list[str]:
        """Kurzinfos wie Augen zu, Finger, KI-Hinweise für die Diashow."""
        notes: list[str] = []
        flags = set(photo.flags or [])
        if getattr(photo, "eyes_closed", False) or "eyes_closed" in flags:
            notes.append(t("note_eyes_closed"))
        elif getattr(photo, "bad_face", False) or "bad_face" in flags:
            notes.append(t("note_bad_face"))
        if getattr(photo, "looking_at_camera", None) is False or "looking_away" in flags:
            notes.append(t("note_looking_away"))
        if getattr(photo, "smiling", None) is True:
            notes.append(t("note_smiling"))
        if getattr(photo, "finger_on_lens", False) or "finger_on_lens" in flags:
            notes.append(t("note_finger"))
        if getattr(photo, "is_accidental", False) or "accidental" in flags:
            notes.append(t("note_accidental"))
        if getattr(photo, "is_weak_night", False) or "weak_night" in flags:
            notes.append(t("note_weak_night"))
        if getattr(photo, "is_blurry", False) or "blurry" in flags:
            notes.append(t("note_blurry"))
        if getattr(photo, "is_too_dark", False) or "too_dark" in flags:
            notes.append(t("note_dark"))
        if getattr(photo, "is_overexposed", False) or "overexposed" in flags:
            notes.append(t("note_bright"))
        qi = getattr(photo, "quality_issue", None)
        if qi:
            notes.append(str(qi))
        mood = getattr(photo, "mood", None)
        if mood:
            notes.append(f"{t('note_mood')}: {mood}")
        landmark = getattr(photo, "landmark", None)
        if landmark:
            notes.append(str(landmark))
        if getattr(photo, "keep_recommendation", None) is False:
            notes.append(t("note_ai_reject"))
        seen: set[str] = set()
        out: list[str] = []
        for n in notes:
            if n and n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def _filmstrip_range(self) -> list[int]:
        if not self._slide_indices:
            return []
        half = STRIP_WINDOW // 2
        start = max(0, self._slide_pos - half)
        end = min(len(self._slide_indices), start + STRIP_WINDOW)
        start = max(0, end - STRIP_WINDOW)
        return list(range(start, end))

    def _rebuild_filmstrip(self) -> None:
        if hasattr(self, "_comparison_stage_row"):
            return
        try:
            for child in self._strip_bar.winfo_children():
                child.destroy()
        except tk.TclError:
            return
        self._strip_frames.clear()
        self._strip_thumb_labels.clear()
        positions = self._filmstrip_range()
        stage_bg = COLORS.get("slide_stage", COLORS["ink"])
        try:
            self._strip_bar.configure(bg=stage_bg)
        except tk.TclError:
            pass
        for pos in positions:
            idx = self._slide_indices[pos]
            kept = idx in self.kept
            is_current = pos == self._slide_pos
            size = STRIP + 12 if is_current else STRIP
            accent = COLORS["accent"]
            border = accent if is_current else (
                COLORS["keep_border"] if kept else COLORS["reject_border"]
            )
            # Äußerer Ring markiert die aktuelle Position klar
            ring_pad = 3 if is_current else 0
            ring = tk.Frame(
                self._strip_bar,
                bg=accent if is_current else stage_bg,
                padx=ring_pad,
                pady=ring_pad,
                cursor="hand2",
            )
            ring.pack(side=tk.LEFT, padx=5 if is_current else 3, pady=2)
            pad = 3 if is_current else 1
            outer = tk.Frame(ring, bg=border, padx=pad, pady=pad, cursor="hand2")
            outer.pack()
            inner = tk.Frame(outer, bg=COLORS["surface"], width=size, height=size)
            inner.pack()
            inner.pack_propagate(False)
            tk_img = self._thumb_cache.get(idx)
            if tk_img is not None:
                lbl = tk.Label(inner, image=tk_img, bg=COLORS["surface"], cursor="hand2")
            else:
                lbl = tk.Label(
                    inner,
                    text="…",
                    bg=COLORS["line"],
                    fg=COLORS["muted"],
                    font=(FONT_UI, 9),
                    cursor="hand2",
                )
                self._request_thumb(idx, priority=8)
            lbl.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            if is_current:
                # Kleiner Indikator oben am aktuellen Bild
                here = tk.Label(
                    inner,
                    text="●",
                    bg=COLORS["surface"],
                    fg=accent,
                    font=(FONT_UI, 8),
                    cursor="hand2",
                )
                here.place(relx=0.5, rely=0.0, anchor=tk.N)
                here.bind("<Button-1>", lambda e, p=pos: self._jump_slide(p))
            if not kept:
                mark = tk.Label(
                    inner,
                    text="×",
                    bg=COLORS["reject"],
                    fg="white",
                    font=(FONT_UI, 8),
                    cursor="hand2",
                )
                mark.place(relx=1.0, rely=0.0, anchor=tk.NE)
                mark.bind("<Button-1>", lambda e, p=pos: self._jump_slide(p))

            def jump(_event=None, p=pos):
                self._jump_slide(p)

            for w in (ring, outer, inner, lbl):
                w.bind("<Button-1>", jump)
            self._strip_frames[idx] = outer
            self._strip_thumb_labels[idx] = lbl

    def _jump_slide(self, pos: int) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        if 0 <= pos < len(self._slide_indices):
            self._slide_pos = pos
            self._show_current_slide()

    def _apply_strip_thumb(self, idx: int) -> None:
        lbl = self._strip_thumb_labels.get(idx)
        tk_img = self._thumb_cache.get(idx)
        if lbl is None or tk_img is None:
            return
        try:
            if lbl.winfo_exists():
                lbl.configure(image=tk_img, text="", bg=COLORS["surface"])
        except tk.TclError:
            pass

    def _refresh_strip_borders(self) -> None:
        """Nach Keep/Remove Filmstrip neu aufbauen (aktuelles Bild bleibt markiert)."""
        if not self._slideshow:
            return
        self._rebuild_filmstrip()

    def _refresh_slide_meta(self) -> None:
        if not self._slide_indices:
            self._slide_status.set("Keine Bilder in dieser Ansicht")
            return
        self._slide_pos = max(0, min(self._slide_pos, len(self._slide_indices) - 1))
        idx = self._slide_indices[self._slide_pos]
        photo = self.photos[idx]
        variants = self._preview_kind == "variants"
        anchor = self._comparison_anchor() if variants else None
        folder = (self.photos[anchor].chapter_folder if anchor is not None else photo.chapter_folder) or self._grid_folder
        chapter = self._folder_title(folder) if folder else photo.region or "Ohne Kapitel"
        self._preview_breadcrumb.set(f"Album / {chapter}" + (" / Vergleich" if anchor is not None else ""))
        self._preview_prev_btn.configure(text="Vorige Alternative" if variants else "Voriges Albumfoto",
                                         state=tk.NORMAL if self._slide_pos > 0 else tk.DISABLED)
        self._preview_next_btn.configure(text="Nächste Alternative" if variants else "Nächstes Albumfoto",
                                         state=tk.NORMAL if self._slide_pos + 1 < len(self._slide_indices) else tk.DISABLED)
        if anchor is not None:
            context = self._album_return or {}
            album_paths = context.get("indices", [])
            anchor_path = str(self.photos[anchor].path)
            position = album_paths.index(anchor_path) + 1 if anchor_path in album_paths else 1
            self._slide_status.set(f"Albumfoto {position} von {len(album_paths)}  ·  Alternative {self._slide_pos + 1} von {len(self._slide_indices)}")
            self._anchor_title.configure(text="Albumfoto" + (" · geschützt" if self.photos[anchor].is_favorite or self.photos[anchor].manual_decision == "keep" else ""))
            state = "im Album" if anchor in self.kept else "nicht mehr im Album"
            self._anchor_caption.set(f"{self.photos[anchor].filename} · {state}")
        elif variants:
            self._slide_status.set(f"Weitere Aufnahme {self._slide_pos + 1} von {len(self._slide_indices)}  ·  {len(self.kept)} Fotos im Album")
        else:
            self._slide_status.set(f"Albumprüfung {self._slide_pos + 1} von {len(self._slide_indices)}  ·  {len(self.kept)} Fotos im Album")
        if variants:
            relation = self._comparison_evidence.get(idx)
            if relation is None:
                relation = candidate_relation(self.photos, anchor, idx) if anchor is not None else ("other", "Weitere Aufnahmen")
                self._comparison_evidence[idx] = relation
            self._current_title.configure(text=f"Alternative · {relation[1]}" if anchor is not None else "Weitere Aufnahme")
            detail = "Keine direkte Ähnlichkeit belegt." if relation[0] == "other" else "Zugehörigkeit laut gespeicherter Bildanalyse."
            self._current_caption.set(f"{photo.filename} · {'im Album' if idx in self.kept else 'nicht im Album'}\n{detail}")
        else:
            self._current_title.configure(text="Albumfoto" if idx in self.kept else "Entferntes Albumfoto")
            notes = self._photo_quality_notes(photo)
            self._current_caption.set(photo.filename + (" · " + "; ".join(notes[:2]) if notes else ""))
        self._slide_caption.set(photo.filename)
        self._slide_notes.set(" · ".join(self._photo_quality_notes(photo)))
        for widget in (self._slide_toggle_btn, self._compare_btn, self._album_back_btn,
                       self._compare_add_btn, self._compare_replace_btn):
            widget.pack_forget()
        if variants:
            self._album_back_btn.configure(text="Zurück zum Albumfoto" if anchor is not None else "Zur Albumübersicht")
            self._album_back_btn.pack(side=tk.LEFT)
            self._compare_add_btn.pack(side=tk.LEFT, padx=(10, 0))
            self._compare_replace_btn.pack(side=tk.LEFT, padx=(10, 0))
            blocked = photo.manual_decision == "reject" and not photo.is_favorite
            viewing_candidate = not (getattr(self, "_comparison_compact", False) and self._comparison_side == "anchor")
            self._compare_add_btn.configure(state=tk.NORMAL if viewing_candidate and idx not in self.kept and not blocked else tk.DISABLED)
            self._compare_add_btn.configure(style="Compare.TButton" if anchor is not None else "ComparePrimary.TButton")
            slot = self._comparison_slot()
            replaceable = slot is not None and not (self.photos[slot].is_favorite or self.photos[slot].manual_decision == "keep")
            self._compare_replace_btn.configure(state=tk.NORMAL if viewing_candidate and replaceable and slot != idx and not blocked else tk.DISABLED)
            self._preview_why_btn.configure(text=("Warum Albumfoto?" if not viewing_candidate else "Warum Alternative?") if anchor is not None else "Warum dieses Bild?")
        else:
            self._slide_toggle_btn.configure(text="Aus Album entfernen" if idx in self.kept else "Wieder aufnehmen")
            self._slide_toggle_btn.pack(side=tk.LEFT)
            self._compare_btn.pack(side=tk.LEFT, padx=(10, 0))
            self._preview_why_btn.configure(text="Warum dieses Bild?")
        self._preview_undo_btn.configure(state=tk.NORMAL if self._history.undo_stack else tk.DISABLED)
        menu = self._preview_menu
        menu.delete(0, tk.END)
        action_idx = self._preview_action_index()
        action_photo = self.photos[action_idx] if action_idx is not None else photo
        menu.add_command(label="Favoritenschutz aufheben" if action_photo.is_favorite else "Als Favorit schützen", command=self._favorite_current)
        menu.add_separator()
        for decision, label in (("keep", "Dauerhaft behalten [K]"), ("reject", "Dauerhaft ablehnen [X]"), ("auto", "Dauerhafte Entscheidung aufheben [U]")):
            menu.add_command(label=label, command=lambda d=decision: self._decision_shortcut(d))
        menu.add_command(label="Notiz zur Entscheidung", command=lambda: self._edit_decision_reason(action_idx))
        menu.add_separator()
        menu.add_command(label="Orte neu prüfen...", command=self._open_location_repair)
        self._fit_preview_actions()

    def _clear_alt_panel(self) -> None:
        self._alt_idx = None
        self._alt_caption.set("")
        self._compare_btn.configure(state=tk.DISABLED, text="Keine weiteren Aufnahmen")

    def _refresh_alt_panel(self) -> None:
        if not self._slide_indices or self._preview_kind == "variants":
            return
        idx = self._slide_indices[self._slide_pos]
        candidates = comparison_candidates(self.photos, idx, self.kept)
        self._alt_idx = candidates[0] if candidates else None
        self._compare_btn.configure(text=f"Varianten vergleichen ({len(candidates)})" if candidates else "Keine weiteren Aufnahmen",
                                    state=tk.NORMAL if candidates else tk.DISABLED)

    def _preview_alternatives(self, _event=None) -> None:
        if not self._slide_indices or self._preview_kind == "variants":
            return
        anchor = self._slide_indices[self._slide_pos]
        candidates = comparison_candidates(self.photos, anchor, self.kept)
        if not candidates:
            return
        self._album_return = dict(photo=str(self.photos[anchor].path), anchor=str(self.photos[anchor].path),
            indices=[str(self.photos[i].path) for i in self._slide_indices], folder=self._grid_folder, filter=self._filter_mode)
        self._comparison_anchor_idx = anchor
        self._comparison_evidence = {}
        self._comparison_side = "candidate"
        self._preview_kind = "variants"
        self._preview_pool = list(candidates)
        self._slide_indices = list(candidates)
        self._slide_pos = 0
        self._preview_feedback_var.set("")
        self._show_current_slide()

    def _return_to_album_slideshow(self) -> None:
        if self._preview_kind != "variants":
            return
        context = self._album_return or {}
        if not context:
            self._exit_slideshow()
            return
        by_path = {str(p.path): i for i, p in enumerate(self.photos)}
        pool = [by_path[p] for p in context.get("indices", []) if p in by_path]
        current = self._comparison_slot()
        original = by_path.get(context.get("photo", ""))
        if current is None:
            current = original
        if current is not None and original in pool and current != original:
            pool[pool.index(original)] = current
        if not pool:
            self._exit_slideshow()
            return
        self._grid_folder = (self.photos[current].chapter_folder if current is not None else None) or context.get("folder", self._grid_folder)
        self._preview_kind = "album"
        self._preview_pool = pool
        self._album_slot_contexts.append(dict(context))
        del self._album_slot_contexts[:-100]
        self._album_return = None
        self._comparison_anchor_idx = None
        self._comparison_evidence = {}
        self._filter_mode = context.get("filter", "all")
        self._filter_var.set(self._filter_mode)
        self._slide_indices = pool
        self._slide_pos = pool.index(current) if current in pool else 0
        self._show_current_slide()

    def _slide_take_alternative(self, _event=None) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        if (self._preview_kind == "variants" and getattr(self, "_comparison_compact", False)
                and self._comparison_side == "anchor"):
            self._flash_status("Zuerst die Alternative anzeigen, um sie als Ersatz zu wählen.")
            return
        if self._preview_kind == "variants":
            anchor = self._comparison_anchor()
            slot = self._comparison_slot()
            candidate = self._slide_indices[self._slide_pos]
        else:
            anchor = self._slide_indices[self._slide_pos]
            slot = anchor
            candidate = self._alt_idx
        if anchor is None or slot is None or candidate is None or slot == candidate:
            return
        if self._protected(slot) or not self._can_add_photo(candidate):
            return
        folder = self.photos[anchor].chapter_folder or self._grid_folder
        position = self.photos[slot].book_position
        self.kept.remove(slot)
        self.photos[slot].is_selected = False
        self.photos[slot].book_position = None
        self._adopt_comparison_photo(candidate, folder)
        self.photos[candidate].book_position = position
        if self._album_return:
            self._album_return["replacement"] = str(self.photos[candidate].path)
            self._album_return.setdefault("replacements", []).append(str(self.photos[candidate].path))
        else:
            self._slide_indices[self._slide_pos] = candidate
            self._preview_pool = list(self._slide_indices)
        self._autosave_draft()
        self._update_count()
        self._show_current_slide()
        self._flash_status("Alternative als Ersatz übernommen. Rückgängig stellt beide Bilder wieder her.")

    def _adopt_comparison_photo(self, idx: int, folder: str) -> None:
        self.kept.add(idx)
        self.baseline.add(idx)
        self._session_added.add(idx)
        photo = self.photos[idx]
        photo.review_added = True
        self._assign_chapter(idx, folder)
        photo.is_duplicate = False
        photo.is_burst_reject = False
        photo.duplicate_of = None
        photo.flags = [flag for flag in photo.flags if flag not in ("duplicate", "content_duplicate", "burst_reject")]

    def _comparison_add_current(self) -> None:
        if not self._slideshow or self._preview_kind != "variants" or not self._slide_indices:
            return
        if getattr(self, "_comparison_compact", False) and self._comparison_side == "anchor":
            self._flash_status("Zuerst die Alternative anzeigen, um sie zusätzlich aufzunehmen.")
            return
        idx = self._slide_indices[self._slide_pos]
        if idx in self.kept or not self._can_add_photo(idx):
            return
        anchor = self._comparison_anchor()
        folder = self.photos[anchor].chapter_folder if anchor is not None else self._grid_folder
        self._adopt_comparison_photo(idx, folder or self._grid_folder)
        self._autosave_draft()
        self._update_count()
        self._show_current_slide()
        self._flash_status("Zusätzlich aufgenommen. Dein Albumfoto bleibt erhalten.")

    def _slide_chapter_of(self, idx: int) -> str:
        return self.photos[idx].chapter_folder or self.photos[idx].region or ""

    def _slide_chapter_prev(self) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        cur_ch = self._slide_chapter_of(self._slide_indices[self._slide_pos])
        for pos in range(self._slide_pos - 1, -1, -1):
            if self._slide_chapter_of(self._slide_indices[pos]) != cur_ch:
                # Anfang dieses Kapitels
                ch = self._slide_chapter_of(self._slide_indices[pos])
                start = pos
                while start > 0 and self._slide_chapter_of(self._slide_indices[start - 1]) == ch:
                    start -= 1
                self._slide_pos = start
                self._show_current_slide()
                return

    def _slide_chapter_next(self) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        cur_ch = self._slide_chapter_of(self._slide_indices[self._slide_pos])
        for pos in range(self._slide_pos + 1, len(self._slide_indices)):
            if self._slide_chapter_of(self._slide_indices[pos]) != cur_ch:
                self._slide_pos = pos
                self._show_current_slide()
                return

    def _slide_prev(self) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        if self._slide_pos > 0:
            self._comparison_side = "candidate"
            self._slide_pos -= 1
            self._show_current_slide()

    def _slide_next(self) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        if self._slide_pos < len(self._slide_indices) - 1:
            self._comparison_side = "candidate"
            self._slide_pos += 1
            self._show_current_slide()

    def _slide_toggle_current(self, _event=None) -> None:
        if not self._slideshow or not self._slide_indices:
            return
        idx = self._preview_action_index()
        removed = False
        if idx in self.kept:
            if self._protected(idx):
                return
            self.kept.remove(idx)
            removed = True
        else:
            if not self._can_add_photo(idx):
                return
            was_variant = idx not in self.baseline
            self.kept.add(idx)
            self.baseline.add(idx)
            if was_variant:
                self.photos[idx].review_added = True
                self._session_added.add(idx)
                self._assign_chapter(idx, self._grid_folder)
                self.photos[idx].is_duplicate = False
                self.photos[idx].is_burst_reject = False
                self.photos[idx].duplicate_of = None
                self.photos[idx].flags = [f for f in self.photos[idx].flags
                    if f not in ("duplicate", "content_duplicate", "burst_reject")]
        self._update_count()
        self._autosave_draft()
        self._paint_tile_state(idx, "keep", self.photos[idx].chapter_folder or "")
        self._refresh_slide_meta()
        self._refresh_strip_borders()
        self._refresh_alt_panel()
        if removed and self._auto_advance:
            # Bei Filter „Dabei“ fällt das Bild raus → Liste neu, sonst weiter
            if self._filter_mode == "kept":
                self._reapply_slide_filter(keep_photo=False)
            else:
                self._slide_next()

    def _slide_mousewheel(self, event) -> None:
        if not self._slideshow:
            return
        delta = int(getattr(event, "delta", 0) or 0)
        if delta > 0:
            self._slide_prev()
        elif delta < 0:
            self._slide_next()
        return "break"

    def _slide_key_prev(self, _event=None) -> None:
        if self._text_input_active():
            return None
        if self._slideshow:
            self._slide_prev()

    def _slide_key_next(self, _event=None) -> None:
        if self._text_input_active():
            return None
        if self._slideshow:
            self._slide_next()

    def _slide_key_toggle(self, _event=None) -> None:
        if self._text_input_active():
            return None
        if self._slideshow:
            self._slide_toggle_current()
            return "break"

    def _slide_key_remove(self, _event=None) -> None:
        if self._text_input_active():
            return None
        if not self._slideshow or not self._slide_indices:
            return
        idx = self._preview_action_index()
        if idx in self.kept:
            if self._protected(idx):
                return "break"
            self.kept.remove(idx)
            self._update_count()
            self._autosave_draft()
            self._paint_tile_state(idx, "keep", self.photos[idx].chapter_folder or "")
            self._refresh_slide_meta()
            self._refresh_strip_borders()
            self._refresh_alt_panel()
            if self._auto_advance:
                if self._filter_mode == "kept":
                    self._reapply_slide_filter(keep_photo=False)
                else:
                    self._slide_next()
        return "break"

    def _slide_key_take_alt(self, _event=None) -> None:
        if self._text_input_active():
            return None
        if self._slideshow:
            if self._preview_kind == "variants":
                self._comparison_add_current()
            else:
                self._preview_alternatives()
            return "break"

    def _slide_key_chapter_prev(self, _event=None) -> None:
        if self._text_input_active():
            return None
        if self._slideshow:
            # PageUp = vorheriger Ordner (wie oben)
            self._grid_folder_prev()
            return "break"

    def _slide_key_chapter_next(self, _event=None) -> None:
        if self._text_input_active():
            return None
        if self._slideshow:
            # PageDown = nächster Ordner (wie oben)
            self._grid_folder_next()
            return "break"

    def _slide_key_escape(self, _event=None) -> None:
        if self._slideshow:
            if self._preview_kind == "variants":
                self._return_to_album_slideshow()
            else:
                self._exit_slideshow()
            return "break"

    def _protected(self, idx: int) -> bool:
        if self.photos[idx].is_favorite or getattr(self.photos[idx], "manual_decision", "auto") == "keep":
            self._flash_status("Dieses Bild ist geschützt. Zuerst den Schutz oder die dauerhafte Entscheidung aufheben.")
            return True
        return False

    def _can_add_photo(self, idx: int) -> bool:
        photo = self.photos[idx]
        if getattr(photo, "manual_decision", "auto") == "reject" and not photo.is_favorite:
            self._flash_status("Dauerhaft abgelehnt. Zuerst die Entscheidung über Rechtsklick oder [U] aufheben.")
            return False
        return True

    def _favorite_current(self) -> None:
        if self._slide_indices:
            self._toggle_favorite(self._preview_action_index())

    def _toggle_favorite(self, idx: int) -> None:
        photo = self.photos[idx]
        photo.is_favorite = not photo.is_favorite
        if photo.is_favorite:
            self.kept.add(idx)
            self.baseline.add(idx)
        self._autosave_draft()
        self._refresh_review_edit()

    def _explain_current(self) -> None:
        if self._slide_indices:
            self._explain(self._preview_action_index())

    def _explain(self, idx: int) -> None:
        from .review_audit_dialog import open_photo_audit
        open_photo_audit(self, idx)

    def _refresh_review_edit(self) -> None:
        if self._preview_kind == "album" and self._preview_pool is not None:
            by_path = {str(photo.path): i for i, photo in enumerate(self.photos)}
            for context in self._album_slot_contexts:
                original = by_path.get(context.get("photo", ""))
                source = context.get("indices", [])
                replacements = [by_path[path] for path in context.get("replacements", []) if path in by_path]
                if original is None or str(self.photos[original].path) not in source:
                    continue
                pos = source.index(str(self.photos[original].path))
                if len(source) != len(self._preview_pool) or pos >= len(self._preview_pool):
                    continue
                active = original if original in self.kept else next((i for i in reversed(replacements) if i in self.kept), None)
                if active is not None and self._preview_pool[pos] in {original, *replacements}:
                    self._preview_pool[pos] = active
        self._update_count()
        self._refresh_folder_nav()
        self._render()
        if self._slideshow:
            self._reapply_slide_filter(keep_photo=True)

    def _undo(self, _event=None) -> str:
        if self._history.undo(self.photos):
            self.kept = {i for i, p in enumerate(self.photos) if p.is_selected}
            self._session_added = {i for i, p in enumerate(self.photos) if p.review_added}
            self._autosave_draft()
            self._refresh_review_edit()
        return "break"

    def _redo(self, _event=None) -> str:
        if self._history.redo(self.photos):
            self.kept = {i for i, p in enumerate(self.photos) if p.is_selected}
            self.baseline.update(self.kept)
            self._session_added = {i for i, p in enumerate(self.photos) if p.review_added}
            self._autosave_draft()
            self._refresh_review_edit()
        return "break"

    def _print_check(self) -> None:
        win = tk.Toplevel(self)
        win.title(t("print_check"))
        win.geometry("760x500")
        win.transient(self)
        width = tk.StringVar(value="15")
        height = tk.StringVar(value="10")
        target = tk.StringVar(value="300")
        options = ttk.Frame(win, padding=12)
        options.pack(fill=tk.X)
        ttk.Label(options, text=t("print_size")).pack(side=tk.LEFT)
        for var in (width, height):
            ttk.Entry(options, textvariable=var, width=7).pack(side=tk.LEFT, padx=4)
        ttk.Label(options, text=t("print_target")).pack(side=tk.LEFT, padx=8)
        ttk.Entry(options, textvariable=target, width=7).pack(side=tk.LEFT)
        ttk.Label(win, text=t("print_hint"), wraplength=720).pack(fill=tk.X, padx=12)
        summary = tk.StringVar()
        ttk.Label(win, textvariable=summary).pack(fill=tk.X, padx=12, pady=8)
        table = ttk.Treeview(win, columns=("name", "dpi", "status"), show="headings")
        for col, label in (("name", "Foto"), ("dpi", "DPI"), ("status", t("print_check"))):
            table.heading(col, text=label)
        scroll = ttk.Scrollbar(win, orient=tk.VERTICAL, command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        table.pack(fill=tk.BOTH, expand=True, padx=12)

        def check(save: bool = False) -> None:
            try:
                w, h, dpi_target = (float(v.get().replace(",", ".")) for v in (width, height, target))
                effective_dpi(Photo(path=Path(), filename=""), w, h)
                print_status(None, dpi_target)
            except ValueError:
                messagebox.showerror(t("print_check"), t("print_invalid"), parent=win)
                return
            table.delete(*table.get_children())
            low = unknown = 0
            for i in sorted(self.kept):
                dpi = effective_dpi(self.photos[i], w, h)
                status = print_status(dpi, dpi_target)
                low += status == "print_low"
                unknown += dpi is None
                table.insert("", tk.END, values=(self.photos[i].filename,
                             f"{dpi:.0f}" if dpi is not None else "?", t(status)))
            summary.set(t("print_summary", n=len(self.kept), low=low, unknown=unknown))
            if save:
                from tkinter import filedialog
                filename = filedialog.asksaveasfilename(parent=win, defaultextension=".csv",
                            initialfile="print_quality.csv", filetypes=[("CSV", "*.csv")])
                if filename:
                    try:
                        write_print_report(self.photos, self.kept, Path(filename), w, h, dpi_target)
                    except OSError as exc:
                        messagebox.showerror(t("print_check"), str(exc), parent=win)

        buttons = ttk.Frame(win, padding=12)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text=t("print_run"), command=check).pack(side=tk.LEFT)
        ttk.Button(buttons, text=t("print_report"), command=lambda: check(True)).pack(side=tk.LEFT, padx=8)
        check()

    def _autosave_draft(self) -> None:
        for i, photo in enumerate(self.photos):
            was_selected = self._history.current[i][0]
            if was_selected != (i in self.kept):
                if i in self.kept:
                    photo.flags = [f for f in photo.flags if f != "manual_reject"]
                    photo.add_flag("manual_add")
                else:
                    photo.add_flag("manual_reject")
            photo.is_selected = i in self.kept
        self._history.record(self.photos)
        if hasattr(self, "_undo_btn"):
            self._undo_btn.configure(state=tk.NORMAL if self._history.undo_stack else tk.DISABLED)
            self._redo_btn.configure(state=tk.NORMAL if self._history.redo_stack else tk.DISABLED)
        try:
            save_selection_draft(self.output_dir, self.photos, self.kept,
                                 review_state=self._review_view_state())
            self._draft_save_error = None
        except Exception as exc:
            self._draft_save_error = str(exc)
            self._flash_status(f"Zwischenstand nicht gespeichert: {exc}")

    def _flash_status(self, text: str) -> None:
        """Kurz Feedback in der Zählerzeile, dann wieder normale Anzahl."""
        try:
            self.count_var.set(text)
            if self._slideshow and hasattr(self, "_preview_feedback_var"):
                self._preview_feedback_var.set(text)
        except tk.TclError:
            return
        if self._status_flash_job is not None:
            try:
                self.after_cancel(self._status_flash_job)
            except Exception:
                pass
        def clear_feedback():
            self._status_flash_job = None
            self._update_count()
            self._preview_feedback_var.set("")
        self._status_flash_job = self.after(3200, clear_feedback)

    def _assign_chapter(self, idx: int, folder_name: str) -> None:
        """Kapitelordner setzen – Entwurf + Speichern schreiben chapter_folder mit."""
        if not folder_name:
            return
        from .documents import ASIDE_FOLDER

        self.photos[idx].add_flag("manual_chapter")
        self.photos[idx].chapter_folder = folder_name
        if folder_name == ASIDE_FOLDER or folder_name.startswith("99_"):
            self.photos[idx].is_aside = True
            self.photos[idx].chapter_type = "Optional"
            self.photos[idx].region = self.photos[idx].region or "Optional"
        else:
            # Wichtig: sonst schreibt Speichern wieder 99_Optional_Dokumente
            self.photos[idx].is_aside = False
            self.photos[idx].chapter_type = (
                "Transit"
                if "Transit" in folder_name
                else "Essen"
                if folder_name.replace("\\", "/").endswith("/essen")
                or folder_name.replace("\\", "/").endswith("essen")
                else "Hauptteil"
            )
        self.photos[idx].is_selected = True

    def _place_in_chapter(self, idx: int, folder_name: str) -> None:
        """Variante ins Kapitel legen und Raster neu zeichnen."""
        folder = folder_name or self.photos[idx].chapter_folder or "Unbestimmt"
        self._assign_chapter(idx, folder)
        self._session_added.add(idx)
        self.photos[idx].review_added = True
        self._flash_status(t("added_to_chapter", folder=folder))
        self._autosave_draft()
        self._refresh_folder_nav()
        self._render()

    def _hit_at(self, event) -> dict | None:
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        for hit in reversed(self._hit_tiles):
            x1, y1, x2, y2 = hit["box"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return hit
        return None

    def _on_grid_click(self, event) -> None:
        if self._slideshow:
            return
        hit = self._hit_at(event)
        if not hit:
            return
        kind = hit["kind"]
        if kind == "photo":
            self._open_photo_preview(hit["idx"], hit.get("folder") or "")
        elif kind == "selection":
            self._toggle_photo(hit["idx"], hit["mode"], hit.get("folder") or "")
        elif kind == "swap":
            self._grid_swap_alternative(hit["idx"], hit.get("folder") or "")
        elif kind == "alt_toggle":
            key = hit["key"]
            if key in self._expanded_alts:
                self._expanded_alts.discard(key)
            else:
                self._expanded_alts.add(key)
            try:
                top = self.canvas.yview()[0]
            except tk.TclError:
                top = 0.0
            self._render()
            try:
                self.canvas.yview_moveto(top)
            except tk.TclError:
                pass

    def _grid_swap_alternative(self, idx: int, folder: str) -> None:
        """1-Klick: behaltenes Bild gegen beste Burst-/Kapitel-Alternative tauschen."""
        if idx not in self.kept:
            return
        if self._protected(idx):
            return
        alt = best_swap_candidate(self.photos, idx, self.kept)
        if alt is None:
            self._flash_status(t("alt_none"))
            return
        if not self._can_add_photo(alt):
            return
        target_folder = folder or self.photos[idx].chapter_folder or self._grid_folder or ""
        self.kept.remove(idx)
        self.photos[idx].is_selected = False
        # Alternative ggf. aus Duplikat-Status holen
        photo = self.photos[alt]
        photo.is_duplicate = False
        photo.is_burst_reject = False
        photo.duplicate_of = None
        photo.flags = [
            f
            for f in photo.flags
            if f not in ("duplicate", "content_duplicate", "burst_reject")
        ]
        self.kept.add(alt)
        self.baseline.add(alt)
        self._session_added.add(alt)
        self.photos[alt].review_added = True
        self._assign_chapter(alt, target_folder)
        self._flash_status(t("alt_swapped", name=photo.filename))
        self._autosave_draft()
        self._update_count()
        self._refresh_folder_nav()
        self._render()

    def _on_grid_right_click(self, event) -> None:
        """Rechtsklick: Bild in anderen Ordner verschieben."""
        if self._slideshow:
            return
        hit = self._hit_at(event)
        if not hit or hit.get("kind") != "photo":
            return
        idx = int(hit["idx"])
        mode = hit.get("mode") or "keep"
        # Nur behaltene / hinzufügbare Bilder verschieben
        if mode == "add" and idx not in self.kept:
            # Erst ins Buch legen, dann verschieben-Menü – oder direkt mit Zielordner
            pass
        folders = [f for f, _t in self._folder_labels if f != (hit.get("folder") or self._grid_folder)]
        # Alle bekannten Ordner inkl. aktueller Liste
        if not folders:
            folders = [f for f, _t in self._folder_entries() if f != self._grid_folder]
        menu = tk.Menu(self, tearoff=0, bg=COLORS["surface"], fg=COLORS["ink"])
        menu.add_command(label=t("unfavorite" if self.photos[idx].is_favorite else "favorite"),
                         command=lambda: self._toggle_favorite(idx))
        menu.add_command(label="Warum dieses Bild?", command=lambda: self._explain(idx))
        menu.add_separator()
        for decision, label in (("keep", "Dauerhaft behalten"),
                                ("reject", "Dauerhaft ablehnen"),
                                ("auto", "Dauerhafte Entscheidung aufheben")):
            menu.add_command(label=label, command=lambda d=decision: self._set_decision(idx, d))
        menu.add_command(label="Entscheidung begründen...", command=lambda: self._edit_decision_reason(idx))
        menu.add_separator()
        menu.add_command(label=t("move_to"), state=tk.DISABLED)
        for folder in folders:
            label = self._folder_title(folder)
            menu.add_command(
                label=label,
                command=lambda f=folder, i=idx: self._move_photo_to_folder(i, f),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _toggle_photo(self, idx: int, mode: str, folder: str) -> None:
        if idx not in self.kept and not self._can_add_photo(idx):
            return
        if mode in ("add", "dup"):
            if idx in self.kept:
                return
            photo = self.photos[idx]
            if mode == "dup":
                photo.is_duplicate = False
                photo.is_burst_reject = False
                photo.duplicate_of = None
                photo.flags = [
                    f
                    for f in photo.flags
                    if f
                    not in (
                        "duplicate",
                        "content_duplicate",
                        "burst_reject",
                    )
                ]
            self.kept.add(idx)
            self.baseline.add(idx)
            target_folder = folder
            if mode == "dup" and (not target_folder or target_folder.endswith("__dups") or target_folder == "__dups__"):
                # In aktuellen Raster-Ordner legen
                target_folder = self._grid_folder or folder
            self._place_in_chapter(idx, target_folder)
            self._update_count()
            self._autosave_draft()
            self._render()
            return
        if idx in self.kept:
            if self._protected(idx):
                return
            self.kept.remove(idx)
            self.photos[idx].is_selected = False
        else:
            self.kept.add(idx)
            self.photos[idx].is_selected = True
        self._update_count()
        self._autosave_draft()
        top = self.canvas.yview()[0]
        self._render()
        self.canvas.yview_moveto(top)

    def _paint_tile_state(self, idx: int, mode: str, folder: str) -> None:
        key = (mode, idx, folder)
        border_id = self._canvas_border_ids.get(key) or self._canvas_border_ids.get(("keep", idx, folder))
        if border_id is None:
            # Fallback: neu zeichnen
            try:
                top = self.canvas.yview()[0]
            except tk.TclError:
                top = 0.0
            self._render()
            try:
                self.canvas.yview_moveto(top)
            except tk.TclError:
                pass
            return
        kept = idx in self.kept
        border = COLORS["keep_border"] if kept else COLORS["reject_border"]
        try:
            self.canvas.itemconfigure(border_id, outline=border)
            # Overlay-Text aktualisieren
            tag = f"ov_{mode}_{idx}_{folder}"
            self.canvas.delete(tag)
            coords = self.canvas.coords(border_id)
            if len(coords) >= 4:
                cx = (coords[0] + coords[2]) / 2
                cy = (coords[1] + coords[3]) / 2
                if mode == "keep" and not kept:
                    self.canvas.create_text(
                        cx,
                        cy,
                        text=t("removed_state"),
                        fill=COLORS.get("hero_fg", "#FFFFFF"),
                        font=(FONT_UI, 9),
                        anchor=tk.CENTER,
                        tags=("grid", tag),
                    )
                elif mode == "add" and idx not in self.kept:
                    self.canvas.create_text(
                        cx,
                        cy,
                        text="+",
                        fill=COLORS.get("hero_fg", "#FFFFFF"),
                        font=(FONT_UI, 14),
                        anchor=tk.CENTER,
                        tags=("grid", tag),
                    )
        except tk.TclError:
            pass

    def _render(self) -> None:
        """Zeichnet nur den aktuellen Ordner – scrollt ohne Geisterbilder."""
        self._ensure_placeholder()
        self.canvas.delete("grid")
        self._canvas_img_ids.clear()
        self._canvas_border_ids.clear()
        self._hit_tiles.clear()
        self._update_count()
        self._update_folder_meta()

        width = max(self.canvas.winfo_width(), CELL_W + GRID_PAD * 2)
        cols = max(1, (width - GRID_PAD * 2) // CELL_W)
        self._grid_cols = cols
        y = GRID_PAD

        from .documents import ASIDE_FOLDER, aside_indices

        display = sorted(self.baseline | self.kept)
        sections = chapter_sections(self.photos, display)
        current = self._grid_folder
        if not current and self._folder_labels:
            current = self._folder_labels[0][0]
            self._grid_folder = current

        if self._render_workspace_view(current, y, width, cols):
            return

        # Filter „Duplikate“: eigene Rasteransicht aller aussortierten
        if self._filter_mode == "duplicates":
            dups = all_duplicate_indices(self.photos)
            self.canvas.create_text(
                GRID_PAD,
                y + 8,
                anchor=tk.NW,
                text=t("dup_section_title", n=len(dups)),
                fill=COLORS["ink"],
                font=(FONT_UI, 12),
                tags=("grid",),
            )
            y += HEADER_H
            if dups:
                y = self._draw_photo_rows(dups[:80], "__dups__", "dup", y, cols)
            else:
                self.canvas.create_text(
                    GRID_PAD,
                    y + 8,
                    anchor=tk.NW,
                    text=t("dup_none"),
                    fill=COLORS["muted"],
                    font=(FONT_UI, 10),
                    tags=("grid",),
                )
                y += 40
            self.canvas.configure(scrollregion=(0, 0, width, y + GRID_PAD))
            return

        active = [(title, folder, indices) for title, folder, indices in sections if folder == current]
        drew_photos = False

        if active:
            for title, folder, indices in active:
                original = [i for i in indices if i in self.kept and i not in self._session_added]
                added = [i for i in indices if i in self.kept and i in self._session_added]
                removed = [i for i in indices if i not in self.kept]
                for label, group in (("Album-Auswahl", original), ("Hinzugefügt", added),
                                     ("Entfernt", removed)):
                    if group:
                        y = self._draw_section(f"{label} · {len(group)}", folder, group,
                                               y, cols, show_alts=False)
                if not folder.startswith("99_"):
                    alts = candidate_alternatives(self.photos, folder,
                        limit=len(self.photos), exclude=self.baseline | self.kept)
                    if alts:
                        y = self._draw_alt_section("Varianten", folder, alts, y, cols,
                            collapsed=folder not in self._expanded_alts)
                # Verwandte Duplikate/Serien unter dem Kapitel
                related: list[int] = []
                seen: set[int] = set()
                for idx in indices:
                    for d in related_duplicates(self.photos, idx, limit=8):
                        if d not in seen and d not in self.kept:
                            seen.add(d)
                            related.append(d)
                if related:
                    y = self._draw_alt_section(
                        t("dup_related_title"),
                        f"{folder}__dups",
                        related[:24],
                        y,
                        cols,
                        collapsed=f"{folder}__dups" not in self._expanded_alts,
                        mode="dup",
                    )
                drew_photos = True
        elif current and current != ASIDE_FOLDER:
            # Leerer Ordner (z. B. alles verschoben) – Varianten trotzdem anbieten
            title = self._folder_title(current)
            self.canvas.create_text(
                GRID_PAD,
                y + 8,
                anchor=tk.NW,
                text=title,
                fill=COLORS["ink"],
                font=(FONT_UI, 12),
                tags=("grid",),
            )
            self.canvas.create_text(
                GRID_PAD,
                y + 32,
                anchor=tk.NW,
                text=t("empty_folder"),
                fill=COLORS["muted"],
                font=(FONT_UI, 10),
                tags=("grid",),
            )
            y += HEADER_H + 16
            if not current.startswith("99_"):
                alts = candidate_alternatives(
                    self.photos,
                    current,
                    limit=_ALT_LIMIT,
                    exclude=self.kept,
                )
                if alts:
                    y = self._draw_alt_section(
                        title,
                        current,
                        alts,
                        y,
                        cols,
                        collapsed=current not in self._expanded_alts,
                    )
                    drew_photos = True

        if current == ASIDE_FOLDER:
            aside = [
                i
                for i in aside_indices(self.photos)
                if i not in self.kept and not self.photos[i].is_duplicate
            ]
            if aside:
                aside.sort(
                    key=lambda i: (
                        self.photos[i].aside_type or "",
                        self.photos[i].filename,
                    )
                )
                # Im Optional-Ordner Varianten direkt aufklappen
                self._expanded_alts.add(ASIDE_FOLDER)
                y = self._draw_alt_section(
                    "Optional: Dokumente & Screenshots",
                    ASIDE_FOLDER,
                    aside[:40],
                    y,
                    cols,
                    collapsed=False,
                )
                drew_photos = True
            elif not active:
                self.canvas.create_text(
                    GRID_PAD,
                    y + 8,
                    anchor=tk.NW,
                    text=t("empty_folder"),
                    fill=COLORS["muted"],
                    font=(FONT_UI, 10),
                    tags=("grid",),
                )
                y += 40

        if not current and not sections:
            self.canvas.create_text(
                GRID_PAD,
                y + 8,
                anchor=tk.NW,
                text="Keine Bilder in der Auswahl. Füge Alternativen hinzu oder brich ab.",
                fill=COLORS["muted"],
                font=(FONT_UI, 10),
                tags=("grid",),
            )
            y += 40
            alts = [
                i
                for i, p in enumerate(self.photos)
                if p.is_candidate
                and not p.is_duplicate
                and not getattr(p, "is_aside", False)
                and i not in self.kept
            ]
            alts.sort(
                key=lambda i: self.photos[i].final_score or self.photos[i].technical_score,
                reverse=True,
            )
            if alts:
                y = self._draw_alt_section(
                    "Vorschläge",
                    "__suggestions__",
                    alts[:_ALT_LIMIT],
                    y,
                    cols,
                    collapsed="__suggestions__" not in self._expanded_alts,
                )
                drew_photos = True

        if not drew_photos and current and current != ASIDE_FOLDER and not active:
            pass  # empty_folder-Text steht schon

        y += GRID_PAD
        self.canvas.configure(scrollregion=(0, 0, width, max(y, 100)))
        # Nach dem Zeichnen ausstehende Thumbs anstoßen (falls Queue vorher voll war)
        self._flush_thumb_requests()

    def _draw_section(
        self,
        title: str,
        folder: str,
        indices: list[int],
        y: int,
        cols: int,
        *,
        show_alts: bool,
    ) -> int:
        self.canvas.create_text(
            GRID_PAD,
            y,
            anchor=tk.NW,
            text=title,
            fill=COLORS["ink"],
            font=(FONT_UI, 12),
            tags=("grid",),
        )
        self.canvas.create_text(
            GRID_PAD,
            y + 20,
            anchor=tk.NW,
            text="",
            fill=COLORS["muted"],
            font=(FONT_UI, 9),
            tags=("grid",),
        )
        y += HEADER_H
        y = self._draw_photo_rows(indices, folder, "keep", y, cols)

        if show_alts:
            alts = candidate_alternatives(
                self.photos,
                folder,
                limit=_ALT_LIMIT,
                exclude=self.kept,
            )
            if alts:
                y = self._draw_alt_section(
                    title,
                    folder,
                    alts,
                    y,
                    cols,
                    collapsed=folder not in self._expanded_alts,
                )
        y += 10
        return y

    def _draw_alt_section(
        self,
        title: str,
        key: str,
        indices: list[int],
        y: int,
        cols: int,
        *,
        collapsed: bool,
        mode: str = "add",
    ) -> int:
        indices = [i for i in indices if i not in self.kept]
        if not indices:
            return y
        if mode == "dup":
            action = (
                t("show_duplicates", n=len(indices))
                if collapsed
                else t("hide_duplicates")
            )
        else:
            action = (
                t("show_variants", n=len(indices))
                if collapsed
                else t("hide_variants")
            )
        # Volle Breite der Rasterzeile, Text mittig
        row_w = max(CELL_W * max(cols, 1), self.canvas.winfo_width() - GRID_PAD * 2 - 18)
        btn_w = max(280, row_w)
        btn_h = ALT_BTN_H
        x1, y1 = GRID_PAD, y
        x2, y2 = x1 + btn_w, y1 + btn_h
        self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            fill=COLORS.get("chip_bg", COLORS["surface"]),
            outline=COLORS["line"],
            tags=("grid",),
        )
        short = (title or "").strip()
        if len(short) > 36:
            short = short[:34] + "…"
        text = f"{action}   ·   {short}" if short else action
        self.canvas.create_text(
            (x1 + x2) / 2,
            (y1 + y2) / 2,
            text=text,
            fill=COLORS["ink"],
            font=(FONT_UI, 10),
            anchor=tk.CENTER,
            tags=("grid",),
        )
        self._hit_tiles.append(
            {"kind": "alt_toggle", "key": key, "box": (x1, y1, x2, y2)}
        )
        y += btn_h + 10
        if not collapsed:
            tile_mode = mode if mode in ("add", "dup", "keep") else "add"
            folder_key = "" if key in ("__suggestions__", "__dups__") else key.replace("__dups", "")
            if key.endswith("__dups"):
                folder_key = key[: -len("__dups")]
            y = self._draw_photo_rows(
                indices,
                folder_key,
                tile_mode,
                y,
                cols,
            )
        return y

    def _draw_photo_rows(
        self,
        indices: list[int],
        folder: str,
        mode: str,
        y: int,
        cols: int,
    ) -> int:
        for n, idx in enumerate(indices):
            col = n % cols
            if col == 0 and n:
                y += CELL_H
            x = GRID_PAD + col * CELL_W
            self._draw_tile(x, y, idx, mode, folder)
        if indices:
            y += CELL_H
        return y

    def _draw_tile(self, x: int, y: int, idx: int, mode: str, folder: str) -> None:
        kept = idx in self.kept
        border = COLORS["line"]
        if mode in ("add", "dup"):
            border = COLORS["line"]
        tile_w = THUMB + 12
        tile_h = CELL_H - 8
        img_x1, img_y1 = x + 4, y + 4
        img_x2, img_y2 = x + 8 + THUMB, y + 8 + THUMB
        label_y1 = img_y2 + 2
        label_y2 = y + tile_h - 2
        label_cx = x + tile_w / 2
        label_cy = (label_y1 + label_y2) / 2

        # Kachel-Hintergrund
        self.canvas.create_rectangle(
            x,
            y,
            x + tile_w,
            y + tile_h,
            fill=COLORS["surface"],
            outline="",
            tags=("grid",),
        )
        border_id = self.canvas.create_rectangle(
            img_x1,
            img_y1,
            img_x2,
            img_y2,
            outline=border,
            width=2,
            tags=("grid",),
        )
        key = (mode, idx, folder)
        self._canvas_border_ids[key] = border_id

        tk_img = self._thumb_cache.get(idx) or self._placeholder_img
        img_id = self.canvas.create_image(
            (img_x1 + img_x2) / 2,
            (img_y1 + img_y2) / 2,
            image=tk_img,
            tags=("grid",),
        )
        self._canvas_img_ids[idx] = img_id
        if idx not in self._thumb_cache:
            # Obere Zeilen zuerst; Varianten etwas später
            row_boost = max(0, int(y) // max(CELL_H, 1))
            base = 20 if mode == "keep" else 40
            self._request_thumb(idx, priority=base + min(row_boost, 30))

        photo = self.photos[idx]
        caption = short_tile_label(photo.filename)
        if photo.is_favorite:
            caption = "* " + caption
        elif getattr(photo, "manual_decision", "auto") == "keep":
            caption = "+ " + caption
        elif getattr(photo, "manual_decision", "auto") == "reject":
            caption = "x " + caption
        fg = COLORS["muted"] if (mode == "keep" and not kept) else COLORS["ink"]
        # Beschriftungsband: Text horizontal + vertikal mittig
        self.canvas.create_rectangle(
            img_x1,
            label_y1,
            img_x2,
            label_y2,
            fill=COLORS.get("chip_bg", COLORS["bg"]),
            outline="",
            tags=("grid",),
        )
        self.canvas.create_text(
            label_cx,
            label_cy,
            text=caption,
            fill=fg,
            font=(FONT_UI, 9),
            anchor=tk.CENTER,
            tags=("grid",),
        )

        # Badges / Overlays
        warn = None
        kind = duplicate_kind(photo)
        if kind == "burst":
            warn = t("dup_badge_burst")
        elif kind == "content":
            warn = t("dup_badge_content")
        elif kind == "phash" or mode == "dup":
            warn = t("dup_badge_phash")
        elif getattr(photo, "finger_on_lens", False) or "finger_on_lens" in photo.flags:
            warn = "Finger"
        elif getattr(photo, "is_accidental", False) or "accidental" in photo.flags:
            warn = "Fehlausl."
        elif getattr(photo, "is_weak_night", False) or "weak_night" in photo.flags:
            warn = "Nacht?"
        elif getattr(photo, "bad_face", False) or "eyes_closed" in photo.flags:
            warn = (
                "Augen zu"
                if getattr(photo, "eyes_closed", False) or "eyes_closed" in photo.flags
                else "Gesicht?"
            )
        elif "looking_away" in photo.flags or getattr(photo, "looking_at_camera", None) is False:
            warn = "Blick weg"
        if warn:
            self.canvas.create_rectangle(
                x + 8,
                y + 8,
                x + 70,
                y + 24,
                fill=COLORS.get("phase_run_bg", "#C47A3A"),
                outline="",
                tags=("grid",),
            )
            self.canvas.create_text(
                x + 12,
                y + 16,
                anchor=tk.W,
                text=warn,
                fill=COLORS.get("phase_run_fg", "#FFF8F0"),
                font=(FONT_UI, 7),
                tags=("grid",),
            )
        elif mode == "keep" and idx in self._session_added:
            self.canvas.create_rectangle(
                x + 8,
                y + 8,
                x + 72,
                y + 24,
                fill=COLORS["accent"],
                outline="",
                tags=("grid",),
            )
            self.canvas.create_text(
                x + 12,
                y + 16,
                anchor=tk.W,
                text=t("new_badge"),
                fill=COLORS.get("hero_fg", "#FFFFFF"),
                font=(FONT_UI, 7),
                tags=("grid",),
            )

        tag = f"ov_{mode}_{idx}_{folder}"
        img_cx = (img_x1 + img_x2) / 2
        img_cy = (img_y1 + img_y2) / 2
        if mode == "keep" and not kept:
            self.canvas.create_text(
                img_cx,
                img_cy,
                text=t("removed_state"),
                fill=COLORS.get("hero_fg", "#FFFFFF"),
                font=(FONT_UI, 9),
                anchor=tk.CENTER,
                tags=("grid", tag),
            )
        elif mode in ("add", "dup") and idx not in self.kept:
            self.canvas.create_text(
                img_cx,
                img_cy,
                text="+",
                fill=COLORS.get("hero_fg", "#FFFFFF"),
                font=(FONT_UI, 16),
                anchor=tk.CENTER,
                tags=("grid", tag),
            )

        self._hit_tiles.append(
            {
                "kind": "photo",
                "idx": idx,
                "mode": mode,
                "folder": folder,
                "box": (x, y, x + tile_w, y + tile_h),
            }
        )

        # A separate action keeps opening a photo from changing the selection.
        action = "Entfernen" if kept else "+ Hinzufügen"
        bx1, by1, bx2, by2 = img_x1, img_y2 - 26, img_x2, img_y2
        self.canvas.create_rectangle(bx1, by1, bx2, by2,
            fill=COLORS["surface"], outline="", tags=("grid",))
        self.canvas.create_text((bx1 + bx2) / 2, (by1 + by2) / 2,
            text=action, fill=COLORS["accent"] if kept else COLORS["ink"],
            font=(FONT_UI, 9), tags=("grid",))
        self._hit_tiles.append(dict(kind="selection", idx=idx, mode=mode,
            folder=folder, box=(bx1, by1, bx2, by2)))

    def _save(self) -> None:
        if not self.kept:
            if not messagebox.askyesno(
                "Keine Bilder",
                "Es ist kein Bild mehr ausgewählt. Trotzdem speichern (leere Auswahl)?",
            ):
                return
        report_warnings = []
        try:
            order = apply_manual_selection(
                self.photos,
                self.plan,
                sorted(self.kept),
                self.output_dir,
                report_warning=report_warnings.append,
            )
        except Exception as exc:
            messagebox.showerror("Fehler beim Speichern", str(exc))
            return
        messagebox.showinfo(
            "Gespeichert",
            f"{len(order)} Bilder geschrieben nach:\n{self.output_dir / 'selected'}"
            + ("\n\nDer Bildexport ist fertig. Hinweis zum Prüfbericht:\n" + "\n".join(report_warnings) if report_warnings else ""),
        )
        if self.on_saved:
            self.on_saved()
        try:
            # Finaler Export ersetzt den Entwurf
            from .selection_draft import draft_path

            dp = draft_path(self.output_dir)
            if dp.is_file():
                dp.unlink()
        except Exception:
            pass
        self._close()

    def _close(self) -> None:
        self._autosave_draft()
        if self._draft_save_error:
            messagebox.showerror("Zwischenstand nicht gespeichert",
                "Das Fenster bleibt offen. Bitte Speicherort/Berechtigungen prüfen.\n\n"
                + self._draft_save_error, parent=self)
            return
        self._unbind_wheel()
        for attr in ("_thumb_after", "_slide_after", "_open_large_job", "_draft_note_job"):
            job = getattr(self, attr, None)
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, attr, None)
        if self._search_job is not None:
            self.after_cancel(self._search_job)
            self._search_job = None
        if self._view_save_job is not None:
            self.after_cancel(self._view_save_job)
            self._view_save_job = None
        if self._status_flash_job is not None:
            try:
                self.after_cancel(self._status_flash_job)
            except Exception:
                pass
            self._status_flash_job = None
        for _ in self._loaders:
            self._load_queue.put((0, next(self._load_seq), None))
        self.destroy()


def open_review(
    master: tk.Misc,
    photos: list[Photo],
    plan: BookPlan,
    output_dir: Path,
    on_saved: Optional[Callable[[], None]] = None,
) -> ReviewWindow:
    win = ReviewWindow(master, photos, plan, output_dir, on_saved=on_saved)
    # transient macht das Fenster manchmal „klein gebunden“ an den Parent –
    # für Review lieber eigenständig groß und maximierbar.
    try:
        win.lift()
        win.focus_force()
    except tk.TclError:
        pass
    return win
