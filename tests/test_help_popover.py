"""Context help stays readable, compact and out of the normal workflow's way."""
import tkinter as tk

import pytest

from photobook_curator.settings import theme_colors
from photobook_curator.ui_widgets import HelpTip


@pytest.fixture
def ui():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('Native Tk display unavailable')
    root.geometry('800x600+20+20')
    root.update()
    yield root
    if HelpTip._open_tip is not None:
        HelpTip._open_tip._close()
    root.destroy()


def descendants(widget):
    return [child for item in widget.winfo_children() for child in [item, *descendants(item)]]


def hint(root, text):
    lookup = {'help': text, 'help_tip_title': 'Gut zu wissen', 'help_tip_close': 'Schliessen'}
    tip = HelpTip(root, 'help', theme_colors('night'), get_text=lookup.get)
    tip.place(x=700, y=520)
    root.update()
    return tip


def test_short_help_uses_its_content_height_without_scroll_area(ui):
    tip = hint(ui, 'Ähnliche Serien werden verglichen. Die besten zwei Bilder bleiben in der Auswahl.')
    tip._show()
    ui.update()
    popup = tip._popup
    assert popup.winfo_width() <= 450
    assert popup.winfo_height() < 220
    assert not any(isinstance(child, (tk.Text, tk.Scrollbar)) for child in descendants(popup))
    assert popup.winfo_rootx() + popup.winfo_width() <= ui.winfo_screenwidth()
    assert popup.winfo_rooty() + popup.winfo_height() <= ui.winfo_screenheight()
    assert popup.winfo_rooty() >= 12


def test_outside_click_closes_hint_without_removing_existing_handler(ui):
    clicks = []
    ui.bind('<ButtonPress-1>', lambda _event: clicks.append('existing'))
    outside = tk.Button(ui, text='Weiter')
    outside.pack()
    tip = hint(ui, 'Kurze Erklärung.')
    tip._show()
    ui.update()
    outside.event_generate('<ButtonPress-1>')
    ui.update()
    assert tip._popup is None
    outside.event_generate('<ButtonPress-1>')
    ui.update()
    assert clicks == ['existing', 'existing']


def test_escape_closes_and_returns_keyboard_focus_to_help_control(ui):
    tip = hint(ui, 'Kurze Erklärung.')
    tip._toggle()
    ui.update()
    tip._popup.event_generate('<Escape>')
    ui.update()
    assert tip._popup is None and HelpTip._open_tip is None
    assert ui.focus_get() is tip


def test_long_help_only_adds_scrolling_when_required(ui):
    tip = hint(ui, ('Eine längere Dokumentation bleibt vollständig lesbar. ' * 150))
    tip._show()
    ui.update()
    assert tip._popup.winfo_height() <= 470
    assert any(isinstance(child, tk.Text) for child in descendants(tip._popup))
    assert any(isinstance(child, tk.Scrollbar) for child in descendants(tip._popup))


def test_opening_another_hint_closes_previous_popup(ui):
    first = hint(ui, 'Erste Erklärung.')
    second = hint(ui, 'Zweite Erklärung.')
    first._toggle()
    ui.update()
    second._toggle()
    ui.update()
    assert first._popup is None
    assert second._popup is not None
    assert HelpTip._open_tip is second


def test_help_at_high_dpi_stays_within_screen_and_close_action_visible(ui):
    ui.tk.call('tk', 'scaling', 2.0)  # 144 DPI, a common 150% Windows scale.
    tip = hint(ui, 'Die besten zwei Bilder einer Aufnahmeserie bleiben in der Auswahl. Du kannst später weitere Varianten hinzufügen.')
    tip._show()
    ui.update()
    popup = tip._popup
    close = tip._close_button
    assert popup.winfo_width() <= 450
    assert popup.winfo_height() < 320
    assert close.winfo_ismapped()
    assert close.winfo_rooty() + close.winfo_height() <= popup.winfo_rooty() + popup.winfo_height()
    assert popup.winfo_rootx() >= 0 and popup.winfo_rooty() >= 0
    assert popup.winfo_rootx() + popup.winfo_width() <= ui.winfo_screenwidth()
    assert popup.winfo_rooty() + popup.winfo_height() <= ui.winfo_screenheight()
