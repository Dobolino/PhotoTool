"""The audit UI explains saved evidence without opening source pixels."""
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import pytest

from photobook_curator.models import Photo
from photobook_curator.selection_audit import begin_selection_audit, record_selection_event, finalize_selection_audit
from photobook_curator.review_audit_dialog import AuditReportWindow, open_photo_audit


class ReviewHarness(tk.Toplevel):
    def __init__(self, root, output_dir):
        super().__init__(root)
        self.output_dir = output_dir
        self.photos = [Photo(path=output_dir / f"trip-{n:04d}.jpg", filename=f"trip-{n:04d}.jpg",
            is_selected=n % 2 == 0, is_candidate=True, technical_score=82, final_score=85,
            chapter_folder="01_Coast/hauptteil", datetime_taken=datetime(2026, 7, 1)) for n in range(205)]
        begin_selection_audit(self.photos, {"target": 103})
        order = []
        for index, photo in enumerate(self.photos):
            if photo.is_selected:
                record_selection_event(photo, "diversity_selected", "diversity", method="scene_round_robin", quota=103, score=85)
                order.append((index, photo.chapter_folder, "Hauptteil"))
            else:
                record_selection_event(photo, "cap_day_removed", "caps", cap=103)
        finalize_selection_audit(self.photos, order)
        self.photos[-1].selection_trace = {}  # legacy analyses must stay unknown
        self.photos[0].manual_decision = "reject"
        self.photos[0].decision_reason = "Meine Entscheidung gegen das Bild"
        self.photos[1].manual_decision = "keep"
        self.photos[1].decision_reason = "Wichtige Erinnerung"
        self.kept = {i for i, photo in enumerate(self.photos) if photo.is_selected} - {0} | {1}
        self.previews = []

    def _open_review_pool(self, indices, label):
        self.previews.append((indices, label))


@pytest.fixture
def review(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    root.withdraw()
    # Opening either report must not inspect any original image.
    monkeypatch.setattr("PIL.Image.open", lambda *_a, **_k: pytest.fail("Report opened source pixels"))
    review = ReviewHarness(root, tmp_path)
    review.geometry("1000x700+40+40")
    root.update()
    yield review
    root.destroy()


def test_report_is_paged_and_filterable_without_changing_selection(review):
    before = set(review.kept)
    report = AuditReportWindow(review)
    assert len(report.table.get_children()) == 100
    report._change_page(1)
    assert report.table.get_children()[0] == "100"
    report._change_page(1)
    assert len(report.table.get_children()) == 5
    report.filter_var.set("Ausgelassen")
    report._apply_filters()
    assert all(not audit.selected for audit in report._filtered)
    assert report._page == 0
    report.search_var.set("trip-0000")
    report._apply_filters()
    assert report.table.get_children() == ("0",)
    report.search_var.set("does not exist")
    report._apply_filters()
    assert not report.table.get_children()
    assert str(report.preview_button["state"]) == "disabled"
    assert report.detail.title_var.get() == "Keine passenden Bilder"
    assert report._escape_search() == "break"
    assert report.search_var.get() == ""
    assert report.winfo_exists()
    assert review.kept == before
    report.destroy()


def test_explanation_keeps_automatic_result_and_manual_override_separate(review):
    dialog = open_photo_audit(review, 0)
    body = dialog.detail.text.get("1.0", tk.END)
    assert "Letzte automatische Auswahl: Im Album" in body
    assert "Deine aktuelle Entscheidung" in body
    assert "Dauerhaft ablehnen" in body
    assert "Meine Entscheidung gegen das Bild" in body
    assert dialog.detail.status_var.get().startswith("AUSGELASSEN")
    assert "Kein konkreter Vergleich" in body
    dialog.destroy()
    dialog = open_photo_audit(review, 204)
    assert "Letzte automatische Auswahl: Unbekannt" in dialog.detail.text.get("1.0", tk.END)
    dialog.destroy()


def test_report_freezes_metadata_and_exports_complete_snapshot(review, monkeypatch):
    report = AuditReportWindow(review)
    review.photos[0].decision_reason = "Changed after opening"
    review.kept.add(0)
    report.filter_var.set("Im Album")
    report.search_var.set("trip-0001")
    report._apply_filters()
    for kind in ("html", "csv"):
        path = review.output_dir / ("audit." + kind)
        monkeypatch.setattr("photobook_curator.review_audit_dialog.filedialog.asksaveasfilename", lambda **_kwargs: str(path))
        report._export(kind)
        output = path.read_text(encoding="utf-8-sig")
        assert "trip-0204.jpg" in output  # export contains all pages and filters
        assert "Meine Entscheidung gegen das Bild" in output
        assert "Changed after opening" not in output
    assert not report._by_index[0].selected
    report.destroy()


def test_report_previews_the_selected_photo_via_existing_review_api(review):
    report = AuditReportWindow(review, initial_index=204)
    assert report._page == 2
    assert report.table.selection() == ("204",)
    report._preview()
    assert review.previews[-1][0] == [204]


def test_explanation_uses_only_the_recorded_comparison_peer(review):
    begin_selection_audit(review.photos)
    record_selection_event(review.photos[3], "histogram_rejected", "diversity",
        peer_path=str(review.photos[0].path), similarity=.97, threshold=.92, comparison_available=True)
    finalize_selection_audit(review.photos, [(0, "01_Coast/hauptteil", "Hauptteil")])
    dialog = open_photo_audit(review, 3)
    body = dialog.detail.text.get("1.0", tk.END)
    assert "trip-0000.jpg" in body
    assert "0.970" in body
    assert "trip-0002.jpg" not in body
    dialog.destroy()


def test_report_actions_visible_at_minimum_window_size(review):
    report = AuditReportWindow(review)
    report.geometry("920x580+80+80")
    report.update()

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    for button in descendants(report):
        if isinstance(button, ttk.Button):
            assert button.winfo_height() >= 26
            assert button.winfo_rooty() + button.winfo_height() <= report.winfo_rooty() + report.winfo_height()
            assert button.winfo_rootx() + button.winfo_width() <= report.winfo_rootx() + report.winfo_width()
    assert report.detail.text.winfo_height() >= 120
    report.destroy()


def test_report_toolbar_and_photo_explanation_route_to_readonly_dialogs(monkeypatch):
    from photobook_curator.review_gui import ReviewWindow
    calls = []
    monkeypatch.setattr("photobook_curator.review_audit_dialog.open_audit_report", lambda review: calls.append(("report", review)))
    monkeypatch.setattr("photobook_curator.review_audit_dialog.open_photo_audit", lambda review, index: calls.append(("photo", index)))
    review = object()
    ReviewWindow._open_audit_report(review)
    ReviewWindow._explain(review, 17)
    assert calls == [("report", review), ("photo", 17)]
