"""Review assistant: explainable worklist, motif comparison and narrative mix."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .review_insights import build_motif_groups, build_review_queue, chapter_story_summary

ROLES = {"overview": "Übersicht", "people": "Menschen", "detail": "Details", "atmosphere": "Atmosphäre"}


def open_review_assistant(review):
    """Build suggestions on demand, keeping every photo decision in ReviewWindow."""
    from .review_gui import COLORS, FONT_UI

    win = tk.Toplevel(review)
    win.title("Prüf-Assistent · Motive und Auswahl")
    win.geometry("1000x660")
    win.minsize(760, 500)
    win.configure(bg=COLORS["bg"])
    win.transient(review)
    style = ttk.Style(win)
    style.configure("Assist.TFrame", background=COLORS["bg"])
    style.configure("Assist.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=(FONT_UI, 10))
    style.configure("Assist.TNotebook", background=COLORS["bg"], borderwidth=0, bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.configure("Assist.TNotebook.Tab", padding=(16, 12), font=(FONT_UI, 10),
                    background=COLORS["surface"], foreground=COLORS["muted"], bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.map("Assist.TNotebook.Tab", background=[("selected", COLORS["accent_soft"])],
              foreground=[("selected", COLORS["accent"])])
    style.configure("Assist.TButton", background=COLORS["chip_bg"], foreground=COLORS["ink"],
                    font=(FONT_UI, 10), padding=(14, 9), borderwidth=0)
    style.map("Assist.TButton", background=[("active", COLORS["line"])])
    style.configure("Assist.Vertical.TScrollbar", background=COLORS["chip_bg"],
                    troughcolor=COLORS["surface"], arrowcolor=COLORS["muted"], bordercolor=COLORS["line"])
    style.configure("Assist.Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"],
                    foreground=COLORS["ink"], borderwidth=0, rowheight=34, font=(FONT_UI, 10), bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.configure("Assist.Treeview.Heading", background=COLORS["chip_bg"], foreground=COLORS["ink"],
                    font=(FONT_UI, 10), padding=(8, 10), bordercolor=COLORS["line"], lightcolor=COLORS["line"], darkcolor=COLORS["line"])
    style.map("Assist.Treeview", background=[("selected", COLORS["accent_soft"])],
              foreground=[("selected", COLORS["ink"])])
    head = tk.Frame(win, bg=COLORS["bg"], padx=24, pady=20)
    head.pack(fill=tk.X)
    tk.Label(head, text="Weniger durchsuchen. Bewusster auswählen.", bg=COLORS["bg"],
             fg=COLORS["ink"], font=(FONT_UI, 20, "bold")).pack(anchor=tk.W)
    tk.Label(head, text="Hinweise aus vorhandenen Scores, Serien und Szenenlabels – deine Erinnerungen entscheiden.",
             bg=COLORS["bg"], fg=COLORS["muted"], font=(FONT_UI, 10)).pack(anchor=tk.W, pady=(6, 0))
    notebook = ttk.Notebook(win, style="Assist.TNotebook")
    notebook.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 20))

    queue = build_review_queue(review.photos)
    groups = build_motif_groups(review.photos)
    stories = chapter_story_summary(review.photos)

    def page(label, columns, widths):
        host = ttk.Frame(notebook, padding=14, style="Assist.TFrame")
        notebook.add(host, text=label)
        table_host = ttk.Frame(host, style="Assist.TFrame")
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1, minsize=80)
        table_host.grid(row=0, column=0, sticky="nsew")
        table = ttk.Treeview(table_host, columns=tuple(c[0] for c in columns), show="headings", selectmode="browse", style="Assist.Treeview")
        for (key, title), width in zip(columns, widths):
            table.heading(key, text=title)
            table.column(key, width=width, minwidth=60, stretch=True)
        scrollbar = ttk.Scrollbar(table_host, orient=tk.VERTICAL, command=table.yview, style="Assist.Vertical.TScrollbar")
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail = tk.StringVar(value="Eintrag wählen, um Hinweise und Alternativen zu sehen.")
        detail_label = ttk.Label(host, textvariable=detail, wraplength=860,
                                 justify=tk.LEFT, style="Assist.TLabel")
        detail_label.grid(row=1, column=0, sticky="ew", pady=12)
        host.bind("<Configure>", lambda event, label=detail_label:
                  label.configure(wraplength=max(280, event.width - 28)))
        buttons = ttk.Frame(host, style="Assist.TFrame")
        buttons.grid(row=2, column=0, sticky="ew")
        return host, table, detail, buttons

    _, queue_table, queue_detail, queue_buttons = page(
        f"Zuerst prüfen  {len(queue)}", (("photo", "Bild"), ("chapter", "Kapitel"),
        ("day", "Tag"), ("why", "Warum prüfen?")), (160, 170, 110, 390))
    for n, item in enumerate(queue):
        queue_table.insert("", tk.END, iid=str(n), values=(review.photos[item.photo_index].filename,
            item.chapter, item.day, item.reasons[0] if item.reasons else ""))

    def queue_selected(_event=None):
        selected = queue_table.selection()
        if selected:
            item = queue[int(selected[0])]
            names = ", ".join(review.photos[i].filename for i in item.alternatives)
            queue_detail.set("\n".join(item.reasons) + (f"\nAlternativen: {names}" if names else ""))

    def preview_queue(all_items=False):
        selected = queue_table.selection()
        if all_items:
            indices = [item.photo_index for item in queue]
        elif selected:
            item = queue[int(selected[0])]
            indices = [item.photo_index, *item.alternatives]
        else:
            return
        win.destroy()
        review._open_review_pool(indices, "Prüfliste: unsichere Entscheidungen")

    queue_table.bind("<<TreeviewSelect>>", queue_selected)
    queue_table.bind("<Double-1>", lambda _e: preview_queue())
    ttk.Button(queue_buttons, style="Assist.TButton", text="Bild und Alternativen ansehen", command=preview_queue).pack(side=tk.LEFT)
    ttk.Button(queue_buttons, style="Assist.TButton", text="Gesamte Prüfliste öffnen", command=lambda: preview_queue(True)).pack(side=tk.LEFT, padx=8)
    if queue:
        queue_table.selection_set("0")
        queue_selected()
    else:
        queue_detail.set("Keine auffälligen Auswahlkonflikte gefunden. Das ersetzt keine persönliche Nachkontrolle.")

    _, motif_table, motif_detail, motif_buttons = page(
        f"Motivgruppen  {len(groups)}", (("group", "Gruppe"), ("count", "Bilder"),
        ("selected", "Im Album"), ("best", "Vorschlag: beste 1–2")), (280, 80, 90, 370))
    for n, group in enumerate(groups):
        motif_table.insert("", tk.END, iid=str(n), values=(group.label, len(group.indices),
            group.selected_count, ", ".join(review.photos[i].filename for i in group.recommended_indices)))

    def motif_selected(_event=None):
        selected = motif_table.selection()
        if selected:
            group = groups[int(selected[0])]
            motif_detail.set("\n".join(group.reasons) + "\nEine Gruppe ist ein Vergleichsvorschlag. "
                "Beim Übernehmen bleiben geschützte Favoriten und dauerhaft behaltene Bilder erhalten.")

    def preview_group():
        selected = motif_table.selection()
        if selected:
            group = groups[int(selected[0])]
            win.destroy()
            review._open_review_pool(list(group.indices), group.label)

    def apply_group():
        selected = motif_table.selection()
        if selected:
            group = groups[int(selected[0])]
            review._apply_motif_recommendation(group)
            motif_table.set(selected[0], "selected", sum(i in review.kept for i in group.indices))
            motif_detail.set("Gruppenvorschlag übernommen und als dauerhafte Entscheidungen gespeichert. "
                             "Mit Strg+Z im Hauptfenster rückgängig machen.")

    motif_table.bind("<<TreeviewSelect>>", motif_selected)
    motif_table.bind("<Double-1>", lambda _e: preview_group())
    ttk.Button(motif_buttons, style="Assist.TButton", text="Alle Varianten vergleichen", command=preview_group).pack(side=tk.LEFT)
    ttk.Button(motif_buttons, style="Assist.TButton", text="Beste 1–2 übernehmen", command=apply_group).pack(side=tk.LEFT, padx=8)
    if groups:
        motif_table.selection_set("0")
        motif_selected()
    else:
        motif_detail.set("Keine vergleichbaren Gruppen in den vorhandenen Metadaten gefunden.")

    _, story_table, story_detail, story_buttons = page(
        "Erzählmix", (("chapter", "Kapitel"), ("total", "Bilder"), ("overview", "Übersicht"),
        ("people", "Menschen"), ("detail", "Details"), ("atmosphere", "Atmosphäre")),
        (260, 70, 100, 100, 100, 100))
    for n, story in enumerate(stories):
        story_table.insert("", tk.END, iid=str(n), values=(story.chapter, story.photo_count,
            *(story.counts[r] for r in ROLES)))

    def story_selected(_event=None):
        selected = story_table.selection()
        if selected:
            story = stories[int(selected[0])]
            missing = ", ".join(ROLES[r] for r in story.missing_roles)
            story_detail.set((f"Bisher nicht vertreten: {missing}. " if missing else "Alle vier Bildrollen sind vertreten. ") +
                "Die Rollen werden aus vorhandenen Szenenlabels und Gesichtszahlen abgeleitet. "
                "Ein ruhiger Strandurlaub braucht keinen erzwungenen Menschen-Anteil.")

    def preview_story():
        selected = story_table.selection()
        if selected:
            story = stories[int(selected[0])]
            indices = [i for i in sorted(review.kept) if
                (review.photos[i].chapter_folder or review.photos[i].region or "Ohne Kapitel").split("/")[0] == story.chapter]
            win.destroy()
            review._open_review_pool(indices, f"Erzählmix: {story.chapter}")

    story_table.bind("<<TreeviewSelect>>", story_selected)
    ttk.Button(story_buttons, style="Assist.TButton", text="Kapitel in Vorschau prüfen", command=preview_story).pack(side=tk.LEFT)
    if stories:
        story_table.selection_set("0")
        story_selected()
    else:
        story_detail.set("Noch keine Bilder ausgewählt. Füge Bilder hinzu, um den Erzählmix zu sehen.")
    win.bind("<Escape>", lambda _e: win.destroy())
    return win
