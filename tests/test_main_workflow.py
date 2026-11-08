"""Native main-window workflow, including project and page-budget integration."""

from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
import threading
import time

import pytest

from photobook_curator.gui import PhotobookApp

_REAL_WARMUP = PhotobookApp._warmup_backend


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr("photobook_curator.settings.settings_path", lambda: tmp_path / "preferences.json")
    monkeypatch.setattr(PhotobookApp, "_warmup_backend", lambda self: None)
    monkeypatch.setattr(PhotobookApp, "_update_found_count", lambda self, path: None)
    try:
        window = PhotobookApp()
    except tk.TclError:
        pytest.skip("Native Tk display unavailable")
    assert window._init_ok
    window.geometry("1120x760")
    window.update()
    yield window
    window.destroy()


def test_planning_stays_compact_and_extra_settings_open_in_grouped_sheet(app):
    assert app._setup_view.winfo_ismapped()
    assert not app._analysis_view.winfo_ismapped()
    assert app.start_btn.winfo_ismapped()
    assert app.review_btn.winfo_ismapped()
    assert app.start_btn.winfo_rooty() + app.start_btn.winfo_height() <= app.winfo_rooty() + app.winfo_height()
    setup_height = app._setup_view.winfo_height()
    app.advanced_toggle.invoke()
    app.update()
    assert app._settings_sheet.winfo_ismapped()
    assert app._setup_view.winfo_height() == setup_height
    tabs = [app._settings_notebook.tab(tab, "text") for tab in app._settings_notebook.tabs()]
    assert tabs == ["Bildqualität", "Abwechslung", "KI"]
    app._close_selection_settings()
    app.update()
    assert not app._settings_sheet.winfo_ismapped()


def test_maximized_workspace_has_bounded_centered_content(app):
    from photobook_curator.main_workspace import WORKSPACE_MAX_WIDTH
    app.geometry(f"{app.winfo_screenwidth() - 60}x{app.winfo_screenheight() - 100}+20+20")
    app.update()
    scale = float(app.tk.call("tk", "scaling")) / (96 / 72)
    assert app._content_frame.winfo_width() <= round(WORKSPACE_MAX_WIDTH * scale) + 2
    # Use the available desktop until the readability cap is reached, rather
    # than retaining the old 1,100px central island on a maximized display.
    useful_width = min(round(1250 * scale), app._body_canvas.winfo_width() - round(96 * scale))
    assert app._content_frame.winfo_width() >= useful_width
    available = app._body_canvas.winfo_width()
    left = app._content_frame.winfo_rootx() - app._body_canvas.winfo_rootx()
    right = available - left - app._content_frame.winfo_width()
    assert abs(left - right) <= 4


def test_saved_ai_estimate_mode_is_prominent_before_start(app):
    app.ai_provider_var.set("anthropic")
    app.dry_run_var.set(True)
    assert "Kostenschätzung" in app._mode_title_var.get()
    assert "keine fertige Auswahl" in app._mode_title_var.get()
    assert "Anthropic Claude" in app._mode_description_var.get()
    assert app.start_btn.cget("text") == "Kosten schätzen"
    app._open_selection_settings("ai")
    app.update()
    assert app._settings_notebook.select() == str(app._settings_tabs["ai"])
    assert app.dry_run_var.get() is True
    app._close_selection_settings()


@pytest.mark.parametrize("scale_factor", [1.0, 1.5])
def test_primary_actions_and_settings_fit_narrow_window_at_display_scaling(app, scale_factor):
    original_scaling = float(app.tk.call("tk", "scaling"))
    try:
        app.tk.call("tk", "scaling", (96 / 72) * scale_factor)
        app._setup_style()
        app.geometry("1024x768+10+10")
        app.ai_provider_var.set("anthropic")
        app.dry_run_var.set(True)
        app.update()
        for action in (app.start_btn, app.review_btn):
            assert action.winfo_ismapped()
            assert action.winfo_rootx() >= app.winfo_rootx()
            assert action.winfo_rootx() + action.winfo_width() <= app.winfo_rootx() + app.winfo_width()
        assert app._footer_hint.winfo_ismapped()
        assert "Kostenschätzung" in app._footer_hint.cget("text")
        app._open_selection_settings("ai")
        app.update()
        sheet = app._settings_sheet
        assert sheet.winfo_width() <= sheet.winfo_screenwidth()
        assert sheet.winfo_height() <= sheet.winfo_screenheight()
        assert sheet.winfo_rooty() >= 0
        app._close_selection_settings()
    finally:
        app.tk.call("tk", "scaling", original_scaling)
        app._setup_style()


def test_backend_warmup_updates_status_through_main_queue_without_worker_tk_calls(app, monkeypatch):
    main_thread = threading.get_ident()
    original_after = app.after

    def main_thread_after(*args, **kwargs):
        assert threading.get_ident() == main_thread, "Worker called Tk.after"
        return original_after(*args, **kwargs)

    monkeypatch.setattr(app, "after", main_thread_after)
    _REAL_WARMUP(app)
    app._warmup_worker.join(timeout=15)
    assert not app._warmup_worker.is_alive()
    assert app._pipeline_ready
    assert app._pipeline_error is None
    assert app.status_var.get() != "Bereit"
    app._drain_queues()
    assert app.status_var.get() == "Bereit"


def test_profiles_and_book_pages_update_real_selection_values(app):
    beach = next(n for n, (profile_id, _) in enumerate(app._profile_choices) if profile_id == "beach")
    app._profile_combo.current(beach)
    app._apply_selected_profile()
    assert app.target_var.get() == 120
    assert app.max_per_day_var.get() == "12"
    assert app._loaded_config_settings["burst_keep"] == 1
    app.book_pages_var.set("64")
    assert app.target_var.get() == 150
    assert app.profile_var.get() == "custom"
    app.photos_per_page_var.set("2")
    app.reserved_pages_var.set("8")
    assert app.target_var.get() == 112
    assert "disabled" in app._target_spin.state()
    app.book_pages_var.set("0")
    assert "disabled" not in app._target_spin.state()


def test_loading_project_resets_previous_trip_settings(app, tmp_path):
    from photobook_curator.projects import create_project
    source = tmp_path / "originals"
    source.mkdir()
    project = create_project("Beach", source, tmp_path / "album", profile_id="beach")
    app.ai_provider_var.set("anthropic")
    app.book_pages_var.set("64")
    app.video_var.set(True)
    app._load_project_into_form(project)
    assert app.ai_provider_var.get() == "none"
    assert app.book_pages_var.get() == "0"
    assert app.video_var.get() is False
    assert app.target_var.get() == 120
    assert app._loaded_config_settings["burst_keep"] == 1
    assert app._current_project is project


def test_start_saves_full_profile_and_page_budget_before_analysis(app, tmp_path, monkeypatch):
    from photobook_curator.pipeline import PipelineConfig, PipelineCancelled
    from photobook_curator.projects import load_project
    source = tmp_path / "originals"
    source.mkdir()
    output = tmp_path / "album"
    app.input_var.set(str(source))
    app.output_var.set(str(output))
    app._profile_combo.current(next(n for n, (pid, _) in enumerate(app._profile_choices) if pid == "beach"))
    app._apply_selected_profile()
    app.book_pages_var.set("64")
    monkeypatch.setattr(app, "_ensure_pipeline", lambda: (PipelineCancelled, PipelineConfig, None))

    class NoopWorker:
        def __init__(self, **kwargs):
            self.cfg = kwargs["args"][0]
        def start(self):
            pass
        def is_alive(self):
            return False

    monkeypatch.setattr("photobook_curator.gui.threading.Thread", NoopWorker)
    app._start()
    app.update()
    assert app._analysis_view.winfo_ismapped()
    assert not app._setup_view.winfo_ismapped()
    assert app.progress.winfo_ismapped()
    assert app.cancel_btn.winfo_ismapped()
    assert not app.start_btn.winfo_ismapped()
    assert not app._log_frame.winfo_ismapped()
    app._set_progress("Lokale Analyse", 0.42, "quality")
    assert app._percent_var.get() == "42 %"
    app._finish_analysis_view()
    app.update()
    assert app._setup_view.winfo_ismapped()
    assert not app._analysis_view.winfo_ismapped()
    saved = load_project(output, remember=False)
    assert saved.settings["target_n"] == 150
    assert saved.settings["book_pages"] == 64
    assert saved.settings["burst_keep"] == 1
    assert saved.settings["food_ratio"] == 0.1
    assert saved.profile_id == "custom"  # page budget customizes the beach preset


def test_real_local_run_returns_to_review_ready_planning(app, tmp_path, monkeypatch):
    from PIL import Image, ImageDraw
    source = tmp_path / "photos"
    source.mkdir()
    for n, color in enumerate(("red", "blue")):
        image = Image.new("RGB", (160, 120), color)
        ImageDraw.Draw(image).rectangle((n * 30, 20, 90, 80), fill="yellow")
        image.save(source / f"photo-{n}.jpg")
    app.input_var.set(str(source))
    app.output_var.set(str(tmp_path / "album"))
    app._apply_config_settings({
        "target_n": 2, "geocode": False, "enable_faces": False,
        "enable_content_clusters": False, "enable_document_aside": False,
        "enable_local_aesthetic": False, "enable_accidental_filter": False,
        "enable_weak_night_filter": False, "max_per_day": 0,
    })
    errors = []
    monkeypatch.setattr(app, "report_callback_exception", lambda _kind, exc, _tb: errors.append(exc))
    monkeypatch.setattr("photobook_curator.gui.messagebox.showerror", lambda *args, **kwargs: errors.append(args))
    app._start()
    assert app._view_mode == "analysis"
    deadline = time.monotonic() + 15
    while app._view_mode == "analysis" and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    assert errors == []
    assert app._view_mode == "setup"
    assert app._setup_view.winfo_ismapped()
    assert "Fotos sind bereit" in app._result_note_var.get()
    assert "disabled" not in app.review_btn.state()
    assert (tmp_path / "album" / "selected").is_dir()


def test_failed_review_autosave_blocks_project_switching():
    review = SimpleNamespace(_autosave_draft=lambda: None, _draft_save_error="disk full")
    app = SimpleNamespace(winfo_children=lambda: [review])
    with pytest.raises(OSError, match="disk full"):
        PhotobookApp._save_open_reviews(app)


def test_open_existing_album_loads_its_own_project_before_review(app, tmp_path, monkeypatch):
    from photobook_curator.projects import create_project
    source_a = tmp_path / "source-a"
    source_b = tmp_path / "source-b"
    source_a.mkdir()
    source_b.mkdir()
    project_a = create_project("Trip A", source_a, tmp_path / "album-a", profile_id="city")
    project_b = create_project("Trip B", source_b, tmp_path / "album-b", profile_id="beach")
    app._load_project_into_form(project_a)
    (project_b.output_dir / "photos_analysis.csv").touch()
    monkeypatch.setattr("photobook_curator.gui.filedialog.askdirectory", lambda **kwargs: str(project_b.output_dir))
    opened = []
    monkeypatch.setattr(app, "_open_review", lambda: opened.append(app.input_var.get()))
    app._open_existing_review()
    assert app._current_project.name == "Trip B"
    assert Path(app.input_var.get()) == source_b
    assert app.target_var.get() == 120
    assert app._loaded_config_settings["burst_keep"] == 1
    assert opened == [str(source_b)]
    assert app.review_btn.cget("style") == "Start.TButton"
    assert app.start_btn.cget("style") == "Browse.TButton"


def test_legacy_album_requires_new_source_instead_of_reusing_previous_trip(app, tmp_path, monkeypatch):
    legacy = tmp_path / "legacy-album"
    legacy.mkdir()
    (legacy / "photos_analysis.csv").touch()
    app.input_var.set(str(tmp_path / "previous-trip"))
    app.ai_provider_var.set("anthropic")
    monkeypatch.setattr("photobook_curator.gui.filedialog.askdirectory", lambda **kwargs: str(legacy))
    monkeypatch.setattr(app, "_open_review", lambda: None)
    app._open_existing_review()
    assert app.input_var.get() == ""
    assert app._current_project is None
    assert app.ai_provider_var.get() == "none"
    assert Path(app.output_var.get()) == legacy
