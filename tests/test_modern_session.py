"""Non-UI boundaries for the live metadata session and native callbacks."""
from datetime import datetime, timedelta
from pathlib import Path
import threading
import time

import pytest

from photobook_curator.models import BookPlan, Photo
from photobook_curator.modern_review_session import ReviewSession, SessionError
from photobook_curator.selection_draft import load_selection_draft


def make_session(tmp_path, on_native=None):
    source = tmp_path / "originals"
    source.mkdir(exist_ok=True)
    photos = [Photo(source / f"{i}.jpg", f"{i}.jpg", region="Hong Kong",
                    chapter_folder="01_Hong-Kong/hauptteil", chapter_type="Hauptteil",
                    datetime_taken=datetime(2025, 11, 1) + timedelta(hours=i),
                    is_selected=i < 2, book_position=i + 1 if i < 2 else None)
              for i in range(4)]
    return ReviewSession(photos, BookPlan(), tmp_path / "project", on_native=on_native)


def finish(session, job):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = session.action({"action": "job", "job_id": job["id"]})
        if result["job"]["status"] != "running":
            assert not result["state"]["busy"]
            return result["job"]
        time.sleep(.005)
    raise AssertionError("Background operation did not complete")


@pytest.mark.parametrize("action", [
    {"action": "view", "view": {"layout": []}},
    {"action": "view", "view": {"chapter": {}}},
    {"action": "decision", "id": 0, "decision": []},
    {"action": "export", "export_layout": {}},
    {"action": "toggle", "id": True},
    {"action": "toggle", "id": 0, "selected": "false"},
    {"action": "job", "job_id": []},
    {"action": "location_apply", "preview_id": {}},
])
def test_invalid_json_values_are_client_errors_not_partial_mutations(tmp_path, action):
    session = make_session(tmp_path)
    before = session.snapshot()
    with pytest.raises(SessionError):
        session.action(action)
    assert session.snapshot() == before


@pytest.mark.parametrize("action", ["source_choose", "open_folder"])
def test_native_callback_never_holds_session_lock(tmp_path, action):
    completed = threading.Event()
    def callback(name, payload):
        reader = threading.Thread(target=lambda: (session.snapshot(), completed.set()), daemon=True)
        reader.start()
        assert completed.wait(1), "Native callback held the session lock"
        return str(tmp_path / "new-originals") if name == "choose_source" else None
    session = make_session(tmp_path, callback)
    session.action({"action": action})
    assert completed.is_set()


def test_advanced_tools_save_before_native_handoff_without_holding_lock(tmp_path):
    completed = threading.Event()
    def callback(name, payload):
        assert name == "advanced_tools" and payload == {"tool": "print"}
        assert load_selection_draft(session.output_dir) is not None
        reader = threading.Thread(target=lambda: (session.snapshot(), completed.set()), daemon=True)
        reader.start()
        assert completed.wait(1)
    session = make_session(tmp_path, callback)
    assert session.action({"action": "advanced", "tool": "print"}) == {"switching": True}


def test_native_choice_rechecks_revision_after_modal_returns(tmp_path):
    def callback(name, payload):
        session.action({"action": "toggle", "id": 3})
        return str(tmp_path / "new-originals")
    session = make_session(tmp_path, callback)
    with pytest.raises(SessionError) as exc:
        session.action({"action": "source_choose"})
    assert exc.value.status == 409
    assert 3 in session.kept
    with pytest.raises(SessionError):
        session.action({"action": "source_preview"})


def test_existing_manual_reason_survives_view_changes_and_reopen(tmp_path):
    session = make_session(tmp_path)
    session.action({"action": "decision", "id": 0, "decision": "keep", "reason": "Unsere erste gemeinsame Reise"})
    session.action({"action": "view", "view": {"layout": "C", "theme": "light"}})
    assert session.snapshot()["photos"][0]["decision_reason"] == "Unsere erste gemeinsame Reise"
    loaded = make_session(tmp_path)
    assert loaded.snapshot()["photos"][0]["decision_reason"] == "Unsere erste gemeinsame Reise"
    assert loaded.view["layout"] == "C"


def test_location_cancel_leaves_current_project_untouched(tmp_path, monkeypatch):
    from photobook_curator.geocoding import GeocodeCache
    session = make_session(tmp_path)
    session.photos[0].gps_lat, session.photos[0].gps_lon = 34.6851, 135.8048
    entered, release = threading.Event(), threading.Event()
    def slow_reverse(self, lat, lon):
        entered.set()
        assert release.wait(2)
        return {"city": "Nara", "country": "Japan", "source": "gps_offline"}
    monkeypatch.setattr(GeocodeCache, "reverse", slow_reverse)
    job = session.action({"action": "location_preview"})["job"]
    assert entered.wait(1)
    session.action({"action": "location_cancel"})
    release.set()
    assert finish(session, job)["status"] == "cancelled"
    assert session.photos[0].region == "Hong Kong"
    assert session.kept == {0, 1}
    assert session._location_previews == {}


def test_close_saves_view_and_requests_native_close(tmp_path):
    session = make_session(tmp_path)
    session.action({"action": "view", "view": {"focus": 3, "layout": "B"}})
    assert session.action({"action": "close"})["close_requested"]
    draft = load_selection_draft(session.output_dir)
    assert draft["review_state"]["modern_review"]["focus_path"] == str(session.photos[3].path)
    session.close()
    session.close()  # Native close and controller shutdown can race harmlessly.
    with pytest.raises(SessionError):
        session.action({"action": "toggle", "id": 3})


def test_export_does_not_silently_change_inconsistent_legacy_selection(tmp_path):
    session = make_session(tmp_path)
    session.photos[3].is_favorite = True  # Corrupt/legacy state that the report flags.
    with pytest.raises(SessionError, match="widerspricht"):
        session.action({"action": "export", "export_layout": "flat"})
    assert session.kept == {0, 1}
    assert not (session.output_dir / "selected").exists()


def test_source_relink_uses_native_choice_and_preserves_view_positions(tmp_path):
    new_root = tmp_path / "moved-originals"
    new_root.mkdir()
    for index in range(4):
        (new_root / f"{index}.jpg").write_bytes(f"original-{index}".encode())
    session = make_session(tmp_path, lambda name, payload: {"new_root": str(new_root)})
    session.action({"action": "replace", "anchor": 0, "id": 3})
    with pytest.raises(SessionError):
        session.action({"action": "source_preview", "new_root": str(new_root)})
    session.action({"action": "source_choose"})
    preview = session.action({"action": "source_preview"})
    assert preview["can_apply"] and preview["changed_count"] == 4
    applied = session.action({"action": "source_apply", "preview_id": preview["preview_id"]})
    assert applied["kept"] == [3, 1]
    assert session.image_photo(3).path == new_root / "3.jpg"
    assert applied["image_revision"] == 1
    draft = load_selection_draft(session.output_dir)
    modern = draft["review_state"]["modern_review"]
    assert modern["focus_path"] == str(new_root / "3.jpg")
    assert {entry["path"] for entry in modern["book_positions"]} == {
        str(new_root / "3.jpg"), str(new_root / "1.jpg")}
    assert str(new_root / "0.jpg") not in {entry["path"] for entry in draft["kept"]}


def test_reserves_share_automatic_chapter_scope_and_export_folder(tmp_path):
    photos = [Photo(tmp_path / f"{i}.jpg", f"{i}.jpg", region="Tokyo", country="Japan",
                    is_selected=i == 0, book_position=1 if i == 0 else None,
                    chapter_folder="01_Tokyo/hauptteil" if i == 0 else None,
                    scene_type="essen" if i == 2 else "landschaft") for i in range(3)]
    for photo in photos:
        photo.path.write_bytes(b"source bytes preserved")
    session = ReviewSession(photos, BookPlan(), tmp_path / "project")
    snapshot = session.snapshot()
    assert snapshot["chapters"] == [{"id": "01_Tokyo", "name": "Tokyo", "total": 3, "selected": 1}]
    assert {photo["chapter"] for photo in snapshot["photos"]} == {"01_Tokyo"}
    view = session.action({"action": "view", "view": {"chapter": "01_Tokyo", "filter": "alternatives"}})
    assert view["view"]["alternative_ids"] == [1, 2]
    session.action({"action": "toggle", "id": 1})
    session.action({"action": "toggle", "id": 2})
    assert photos[1].chapter_folder == "01_Tokyo/hauptteil"
    assert photos[2].chapter_folder == "01_Tokyo/essen"
    assert session.view["alternative_ids"] == [1, 2]  # Color changes, collection stays.
    job = session.action({"action": "export", "export_layout": "chapters"})["job"]
    assert finish(session, job)["status"] == "done"
    assert len(list((session.output_dir / "selected" / "01_Tokyo").rglob("*.jpg"))) == 3
    assert not (session.output_dir / "selected" / "Tokyo").exists()
    reopened = ReviewSession([replace_photo(photo) for photo in photos], BookPlan(), session.output_dir)
    assert reopened.view["chapter"] == "01_Tokyo"


def replace_photo(photo):
    from dataclasses import replace
    return replace(photo, flags=list(photo.flags))


def test_canonical_chapters_do_not_merge_manual_or_ambiguous_visits(tmp_path):
    photos = [
        Photo(tmp_path / "one.jpg", "one.jpg", region="Tokyo", country="Japan", chapter_folder="01_Tokyo/hauptteil"),
        Photo(tmp_path / "two.jpg", "two.jpg", region="Tokyo", country="Japan", chapter_folder="03_Tokyo/hauptteil"),
        Photo(tmp_path / "reserve.jpg", "reserve.jpg", region="Tokyo", country="Japan"),
        Photo(tmp_path / "manual.jpg", "manual.jpg", region="Tokyo", country="Japan", chapter_folder="Mein-Kapitel/hauptteil", flags=["manual_chapter"]),
        Photo(tmp_path / "abroad.jpg", "abroad.jpg", region="Tokyo", country="Canada"),
    ]
    state = ReviewSession(photos, BookPlan(), tmp_path / "project").snapshot()
    assert [photo["chapter"] for photo in state["photos"]] == [
        "01_Tokyo", "03_Tokyo", "Tokyo · Japan", "Mein-Kapitel", "Tokyo · Canada"]
    assert len({chapter["name"] for chapter in state["chapters"]}) == len(state["chapters"])


def test_location_origin_is_metadata_in_snapshot(tmp_path):
    session = make_session(tmp_path)
    session.photos[0].location_evidence = {"version": 1, "source": "unknown", "warning": "conflicting_anchors"}
    photo = session.snapshot()["photos"][0]
    assert photo["location_source"] == "unknown" and photo["location_warning"] == "conflicting_anchors"


def test_removed_album_photo_remains_available_in_alternative_strip(tmp_path):
    session = make_session(tmp_path)
    assert session.view["alternative_ids"] == [2, 3]
    session.action({"action": "toggle", "id": 0})
    assert session.view["alternative_ids"] == [2, 3, 0]
    session.action({"action": "undo"})
    assert 0 in session.kept and session.view["alternative_ids"] == [2, 3, 0]


def test_exported_positions_become_baseline_for_next_selection_undo(tmp_path):
    session = make_session(tmp_path)
    for photo in session.photos:
        photo.path.write_bytes(b"source bytes")
    session.photos[0].book_position, session.photos[1].book_position = 10, 20
    # A project loaded from CSV has those original positions in its history.
    from photobook_curator.review_history import ReviewHistory
    session._history = ReviewHistory(session.photos)
    job = session.action({"action": "export", "export_layout": "flat"})["job"]
    assert finish(session, job)["status"] == "done"
    assert [session.photos[i].book_position for i in (0, 1)] == [1, 2]
    session.action({"action": "toggle", "id": 2})
    session.action({"action": "undo"})
    assert session.kept == {0, 1}
    assert [session.photos[i].book_position for i in (0, 1)] == [1, 2]
