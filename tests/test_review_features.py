from pathlib import Path
import math

import pytest

from photobook_curator.models import Photo, BookPlan, Region
from photobook_curator.output import write_csv
from photobook_curator.review_export import load_photos_from_csv, rebuild_selection_from_analysis
from photobook_curator.review_history import ReviewHistory
from photobook_curator.selection_draft import save_selection_draft, load_selection_draft, apply_selection_draft
from photobook_curator.selection_draft import restore_favorites
from photobook_curator.print_quality import effective_dpi, print_status, write_print_report
from photobook_curator.selection_reasons import selection_reasons
from photobook_curator.i18n import set_language


def photo(**kwargs):
    return Photo(path=Path("a.jpg"), filename="a.jpg", **kwargs)


def test_favorite_persists_in_csv_and_draft(tmp_path):
    photos = [photo(is_favorite=True, is_selected=True, region="Tokyo")]
    path = tmp_path / "analysis.csv"
    write_csv(photos, path)
    assert load_photos_from_csv(path)[0].is_favorite
    save_selection_draft(tmp_path, photos, {0})
    loaded = [photo()]
    apply_selection_draft(loaded, load_selection_draft(tmp_path))
    assert loaded[0].is_favorite and loaded[0].region == "Tokyo"
    photos[0].is_favorite = False
    save_selection_draft(tmp_path, photos, {0})
    apply_selection_draft(loaded, load_selection_draft(tmp_path))
    assert not loaded[0].is_favorite


def test_old_csv_defaults_to_unprotected(tmp_path):
    path = tmp_path / "old.csv"
    path.write_text("path,filename\na.jpg,a.jpg\n")
    assert not load_photos_from_csv(path)[0].is_favorite


def test_reanalysis_restores_favorites_and_draft_overrides(tmp_path):
    photos = [photo(is_favorite=True, is_selected=True)]
    write_csv(photos, tmp_path / "photos_analysis.csv")
    fresh = [photo()]
    assert restore_favorites(fresh, tmp_path) == 1
    photos[0].is_favorite = False
    save_selection_draft(tmp_path, photos, {0})
    assert restore_favorites(fresh, tmp_path) == 0


def test_reanalysis_uses_unexported_draft_favorites(tmp_path):
    save_selection_draft(tmp_path, [photo(is_favorite=True)], {0})
    fresh = [photo()]
    assert restore_favorites(fresh, tmp_path) == 1


def test_favorites_override_filters_and_survive_zero_quota():
    photos = [photo(is_favorite=True, is_duplicate=True, is_burst_reject=True, region="Tokyo"),
              Photo(path=Path("ticket.jpg"), filename="ticket.jpg", is_aside=True, is_favorite=True)]
    _, order = rebuild_selection_from_analysis(photos, 0)
    assert {i for i, _, _ in order} == {0, 1}
    assert all(p.is_selected for p in photos)
    assert order[1][1] == "99_Optional_Dokumente"


def test_favorites_replace_automatic_selection_within_quota(monkeypatch):
    import photobook_curator.selection as selection
    photos = [photo(region="Tokyo", is_favorite=True), photo(region="Tokyo"), photo(region="Tokyo")]
    monkeypatch.setattr(selection, "ensure_scene_types", lambda *_: None)
    monkeypatch.setattr(selection, "_select_with_coverage", lambda _p, ids, quota, **_: ids[-quota:] if quota else [])
    main, food = selection.select_for_region(photos, [0, 1, 2], 2)
    assert 0 in main
    assert len(main) + len(food) == 2


def test_history_restores_selection_favorite_chapter_and_duplicate_metadata():
    photos = [photo(is_duplicate=True, flags=["duplicate"])]
    history = ReviewHistory(photos)
    photos[0].is_selected = True
    photos[0].is_duplicate = False
    photos[0].flags.clear()
    photos[0].chapter_folder = "01_Tokyo/hauptteil"
    history.record(photos)
    photos[0].is_favorite = True
    history.record(photos)
    assert history.undo(photos) and not photos[0].is_favorite
    assert history.undo(photos) and not photos[0].is_selected
    assert photos[0].is_duplicate and photos[0].flags == ["duplicate"]
    assert photos[0].chapter_folder is None
    assert history.redo(photos) and photos[0].is_selected
    assert photos[0].flags == []
    photos[0].region = "Lyon"
    history.record(photos)
    assert not history.redo(photos)


def test_history_noop_preserves_redo_and_is_bounded():
    photos = [photo()]
    history = ReviewHistory(photos, limit=2)
    for name in ("A", "B", "C"):
        photos[0].region = name
        history.record(photos)
    assert len(history.undo_stack) == 2
    history.undo(photos)
    history.record(photos)
    assert history.redo(photos)
    assert photos[0].region == "C"


def test_print_resolution_accounts_for_crop_and_rotation(tmp_path):
    assert effective_dpi(photo(width=1800, height=1200), 15.24, 10.16) == pytest.approx(300)
    assert effective_dpi(photo(width=1200, height=1800), 15.24, 10.16) == pytest.approx(300)
    assert effective_dpi(photo(width=1800, height=1800), 15.24, 10.16) == pytest.approx(300)
    assert print_status(299, 300) == "print_low"
    assert print_status(300, 300) == "print_ok"
    assert print_status(None) == "print_unknown"
    write_print_report([photo()], {0}, tmp_path / "print.csv", 15, 10, 300)
    assert "print_unknown" in (tmp_path / "print.csv").read_text()


@pytest.mark.parametrize("value", [0, -1, math.inf, math.nan])
def test_print_rejects_invalid_dimensions_and_dpi(value):
    with pytest.raises(ValueError):
        effective_dpi(photo(), value, 10)
    with pytest.raises(ValueError):
        print_status(None, value)


def test_reasons_report_facts_and_unknown_ranking():
    set_language("en")
    try:
        reasons = selection_reasons(photo(is_favorite=True, is_duplicate=True, duplicate_of="best.jpg"))
        assert any("best.jpg" in r for r in reasons)
        assert any("favorite" in r for r in reasons)
        assert any("not recorded" in r for r in selection_reasons(photo()))
    finally:
        set_language("de")
