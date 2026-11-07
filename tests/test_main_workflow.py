"""Native main-window workflow, including project and page-budget integration."""

from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

import pytest

from photobook_curator.gui import PhotobookApp


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


def test_main_actions_and_responsive_cards_remain_accessible(app):
    assert app._folder_card.grid_info()["column"] == 0
    assert app._settings_card.grid_info()["column"] == 1
    assert not app.advanced_frame.winfo_ismapped()
    assert not app._log_frame.winfo_ismapped()
    assert app.start_btn.winfo_ismapped()
    assert app.review_btn.winfo_ismapped()
    assert app.start_btn.winfo_rooty() + app.start_btn.winfo_height() <= app.winfo_rooty() + app.winfo_height()
    app.geometry("900x720")
    app.update()
    assert app._settings_card.grid_info()["row"] == 1
    app._toggle_advanced()
    app.update()
    assert app.advanced_frame.winfo_ismapped()


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
    assert app.progress.winfo_ismapped()
    assert app.progress.winfo_rooty() + app.progress.winfo_height() < app.start_btn.winfo_rooty()
    saved = load_project(output, remember=False)
    assert saved.settings["target_n"] == 150
    assert saved.settings["book_pages"] == 64
    assert saved.settings["burst_keep"] == 1
    assert saved.settings["food_ratio"] == 0.1
    assert saved.profile_id == "custom"  # page budget customizes the beach preset


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
