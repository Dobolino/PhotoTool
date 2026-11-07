"""Cap input and preference persistence without a display server."""

from types import SimpleNamespace

import pytest

from photobook_curator.gui import PhotobookApp
from photobook_curator.settings import AppSettings, load_settings, save_settings


def _variable(value):
    return SimpleNamespace(get=lambda: value)


def test_caps_accept_unlimited_and_positive_integers():
    app = SimpleNamespace(max_per_day_var=_variable("0"), max_per_chapter_var=_variable(" 60 "))
    assert PhotobookApp._selection_caps(app) == (0, 60)


@pytest.mark.parametrize("invalid", ["", "-1", "1.5", "twenty", "nan"])
def test_caps_reject_invalid_typed_input(invalid):
    app = SimpleNamespace(max_per_day_var=_variable(invalid), max_per_chapter_var=_variable("60"))
    with pytest.raises(ValueError):
        PhotobookApp._selection_caps(app)


def test_caps_persist_without_losing_appearance_preferences(tmp_path, monkeypatch):
    monkeypatch.setattr("photobook_curator.settings.settings_path", lambda: tmp_path / "settings.json")
    save_settings(AppSettings(language="en", theme="slate", slideshow_auto_advance=True))
    app = SimpleNamespace()
    PhotobookApp._save_selection_caps(app, 20, 60)
    loaded = load_settings()
    assert (loaded.max_per_day, loaded.max_per_chapter) == (20, 60)
    assert loaded.language == "en"
    assert loaded.theme == "slate"
    assert loaded.slideshow_auto_advance is True


def test_invalid_saved_caps_fall_back_to_unlimited(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr("photobook_curator.settings.settings_path", lambda: path)
    path.write_text('{"max_per_day": "oops", "max_per_chapter": -5}', encoding="utf-8")
    loaded = load_settings()
    assert (loaded.max_per_day, loaded.max_per_chapter) == (0, 0)


def test_failed_settings_replacement_preserves_previous_preferences(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr("photobook_curator.settings.settings_path", lambda: path)
    save_settings(AppSettings(max_per_day=20))

    def fail_replace(*_args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("photobook_curator.settings.os.replace", fail_replace)
    with pytest.raises(OSError):
        save_settings(AppSettings(max_per_day=10))
    assert load_settings().max_per_day == 20
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("input_path, output_path", [("", "/tmp/output"), ("/tmp/photos", " ")])
def test_empty_directory_fields_do_not_start_analysis(input_path, output_path, monkeypatch):
    errors = []
    monkeypatch.setattr("photobook_curator.gui.messagebox.showerror", lambda *args, **kwargs: errors.append(args))
    app = SimpleNamespace(
        _worker=None,
        _selection_caps=lambda: (0, 0),
        input_var=_variable(input_path),
        output_var=_variable(output_path),
    )
    PhotobookApp._start(app)
    assert len(errors) == 1
    assert "ordner fehlt" in errors[0][0]


def test_identical_directories_do_not_start_analysis(tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr("photobook_curator.gui.messagebox.showerror", lambda *args, **kwargs: errors.append(args))
    app = SimpleNamespace(
        _worker=None,
        _selection_caps=lambda: (0, 0),
        input_var=_variable(str(tmp_path)),
        output_var=_variable(str(tmp_path / ".")),
    )
    PhotobookApp._start(app)
    assert errors[0][0] == "Ausgabeordner wählen"
