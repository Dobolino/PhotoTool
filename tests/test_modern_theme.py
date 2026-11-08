"""Readable modern palettes, durable preferences and usable project controls."""
import tkinter as tk

import pytest

from photobook_curator.settings import AppSettings, load_settings, save_settings, theme_colors


def contrast(first, second):
    def luminance(colour):
        channels = [int(colour[i:i+2], 16)/255 for i in (1, 3, 5)]
        linear = [x/12.92 if x <= .04045 else ((x+.055)/1.055)**2.4 for x in channels]
        return sum(value*weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    low, high = sorted((luminance(first), luminance(second)))
    return (high+.05)/(low+.05)


@pytest.mark.parametrize('theme', ['night', 'modern'])
def test_modern_text_remains_readable_on_action_and_selection_surfaces(theme):
    colours = theme_colors(theme)
    # Covers the actual failure-prone pairings: cyan action surfaces need dark
    # text; orange primary actions must not inherit white legacy button text.
    for foreground, background in [('ink', 'surface'), ('muted', 'surface'),
            ('ink', 'accent_soft'), ('on_accent', 'accent'), ('on_accent', 'accent_hover'),
            ('cta_ink', 'cta'), ('cta_ink', 'cta_hover'), ('phase_run_fg', 'phase_run_bg'),
            ('phase_run_bg', 'surface'), ('phase_done_fg', 'phase_done_bg')]:
        assert contrast(colours[foreground], colours[background]) >= 4.5, (theme, foreground, background)


@pytest.mark.parametrize('theme', ['night', 'modern', 'forest', 'slate', 'ink'])
def test_appearance_choice_roundtrip_preserves_other_preferences(tmp_path, monkeypatch, theme):
    monkeypatch.setattr('photobook_curator.settings.settings_path', lambda: tmp_path/'settings.json')
    save_settings(AppSettings(theme=theme, language='en', slideshow_auto_advance=True,
        slideshow_show_alternative=False, max_per_day=18, max_per_chapter=60))
    loaded = load_settings()
    assert loaded.theme == theme
    assert (loaded.language, loaded.slideshow_auto_advance, loaded.slideshow_show_alternative,
            loaded.max_per_day, loaded.max_per_chapter) == ('en', True, False, 18, 60)


@pytest.mark.parametrize('choice,expected', [('light', 'modern'), ('hell', 'modern'), ('dark', 'night')])
def test_web_theme_names_persist_as_native_appearance_choices(tmp_path, monkeypatch, choice, expected):
    monkeypatch.setattr('photobook_curator.settings.settings_path', lambda: tmp_path/'settings.json')
    save_settings(AppSettings(theme=choice))
    assert load_settings().theme == expected
    assert theme_colors(choice) == theme_colors(expected)


def test_project_actions_remain_accessible_in_a_small_work_area(monkeypatch):
    from photobook_curator.project_dialog import show_project_manager
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('Native Tk display unavailable')
    window = None
    try:
        root.geometry('1000x700+20+20')
        root.update()
        monkeypatch.setattr(root, 'winfo_screenwidth', lambda: 860)
        monkeypatch.setattr(root, 'winfo_screenheight', lambda: 680)
        monkeypatch.setattr('photobook_curator.project_dialog.recent_projects', lambda: [])
        colours = theme_colors('night')
        window = show_project_manager(root, colours, lambda _: None)
        window.update()

        def descendants(parent):
            for child in parent.winfo_children():
                yield child
                yield from descendants(child)

        buttons = [child for child in descendants(window) if isinstance(child, tk.Button)]
        create = next(button for button in buttons if button.cget('text') == 'Projekt anlegen')
        assert create.winfo_height() == create.winfo_reqheight()
        assert create.cget('bg') == colours['cta']
        assert contrast(create.cget('fg'), create.cget('bg')) >= 4.5
        canvas = window._project_canvas
        assert canvas.yview()[1] < 1  # Stacked cards can be reached by scrolling.
        canvas.yview_moveto(1)
        window.update()
        open_file = next(button for button in buttons if button.cget('text') == 'Projektdatei öffnen...')
        assert open_file.winfo_height() == open_file.winfo_reqheight()
        assert open_file.winfo_rooty() >= window.winfo_rooty()
        assert open_file.winfo_rooty()+open_file.winfo_height() <= window.winfo_rooty()+window.winfo_height()
    finally:
        if window is not None:
            window.destroy()
        root.destroy()
