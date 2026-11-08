"""Old place labels stay editable and warnings never become location evidence."""
from copy import deepcopy
import csv
from datetime import datetime

import pytest

from photobook_curator.models import BookPlan, Photo
from photobook_curator.modern_review_session import ReviewSession
from photobook_curator.output import write_csv
from photobook_curator.review_export import load_photos_from_csv


def test_old_csv_place_description_conflict_warns_without_new_analysis_or_changes(tmp_path):
    original = Photo(tmp_path / "DSCF0518.jpg", "DSCF0518.jpg", region="Hong Kong",
        chapter_folder="02_Hong-Kong/hauptteil", chapter_type="Hauptteil",
        datetime_taken=datetime(2025, 11, 18, 9, 46), landmark="Tōdai-ji, Nandaimon-Tor, Nara",
        ai_reviewed=True, is_selected=True, is_favorite=True, manual_decision="keep",
        decision_reason="Wichtige Erinnerung", book_position=17, technical_score=96)
    output = tmp_path / "project"
    output.mkdir()
    path = output / "photos_analysis.csv"
    write_csv([original], path)
    # A pre-evidence analysis CSV has neither a proof field nor a fresh GPS run.
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = [field for field in reader.fieldnames if field != "location_evidence"]
        rows = [{field: row[field] for field in fields} for row in reader]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    photos = load_photos_from_csv(path)
    session = ReviewSession(photos, BookPlan(), output)
    before, csv_before = deepcopy(photos), path.read_bytes()
    record = session.snapshot()["photos"][0]
    assert record["location_review_required"]
    assert record["location_review_reason"] == "description_conflict"
    assert record["location_source"] is None
    assert record["region"] == "Hong Kong" and record["landmark"].endswith("Nara")
    assert photos == before and path.read_bytes() == csv_before
    assert session.kept == {0} and photos[0].is_favorite
    assert photos[0].manual_decision == "keep" and photos[0].book_position == 17
    assert not (output / "selection_draft.json").exists()


@pytest.mark.parametrize("region,landmark,evidence,expected", [
    ("Hong-Kong", None, {}, "legacy_unverified"),
    ("Hong-Kong", "Straße in Hong Kong", {}, "legacy_unverified"),
    ("Nara", "Tempel in Nara", {"version": 1, "source": "gps_offline"}, None),
    ("Nara", None, {"version": 1, "source": "unknown", "warning": "conflicting_anchors"}, "location_warning"),
    ("Nara", None, {"version": 1, "source": "manual"}, None),
    ("Kyoto", "Zug zwischen Nara und Osaka", {"version": 1, "source": "gps_online"}, None),
    ("Taito", "Tempel in Tokyo", {"version": 1, "source": "gps_online"}, None),
    ("Nara", "Tokyotown display", {"version": 1, "source": "gps_online"}, None),
    ("Album", None, {}, None),
    ("Optional", None, {}, None),
])
def test_review_warning_distinguishes_missing_proof_from_known_conflict(
        tmp_path, region, landmark, evidence, expected):
    photo = Photo(tmp_path / "a.jpg", "a.jpg", region=region,
                  landmark=landmark, location_evidence=evidence)
    session = ReviewSession([photo], BookPlan(), tmp_path / "project")
    record = session.snapshot()["photos"][0]
    assert record["location_review_reason"] == expected
    assert record["location_review_required"] is (expected is not None)
    assert photo.region == region and photo.location_evidence == evidence


@pytest.mark.parametrize("start,end", [("Sumida", "Chiyoda"), ("Nara", "Nishinomiya, Japan")])
def test_transit_reserve_joins_one_automatic_chapter_and_exports_to_same_folder(tmp_path, start, end):
    from photobook_curator.utils import slugify
    from test_modern_session import finish

    region = f"Transit:{start}->{end}"
    root = f"20b_Transit_{slugify(start)}-{slugify(end)}"
    photos = [Photo(tmp_path / f"{i}.jpg", f"{i}.jpg", region=region, country="Japan",
                    chapter_folder=root if i == 0 else None,
                    chapter_type="Transit" if i == 0 else None,
                    is_selected=i == 0, book_position=1 if i == 0 else None)
              for i in range(2)]
    for photo in photos:
        photo.path.write_bytes(b"original bytes")
    output = tmp_path / "project"
    output.mkdir()
    session = ReviewSession(photos, BookPlan(), output)
    state = session.snapshot()
    assert len(state["chapters"]) == 1
    assert {photo["chapter"] for photo in state["photos"]} == {root}
    session.action({"action": "view", "view": {"chapter": root, "filter": "alternatives"}})
    assert session.view["alternative_ids"] == [1]
    session.action({"action": "select", "id": 1, "selected": True})
    assert photos[1].chapter_folder == root and photos[1].chapter_type == "Transit"
    job = session.action({"action": "export", "export_layout": "chapters"})["job"]
    assert finish(session, job)["status"] == "done"
    exported = list((output / "selected").rglob("*.jpg"))
    assert len(exported) == 2 and all(path.parent == output / "selected" / root for path in exported)
    reopened = ReviewSession(load_photos_from_csv(output / "photos_analysis.csv"), BookPlan(), output)
    assert len(reopened.snapshot()["chapters"]) == 1 and reopened.view["chapter"] == root


def test_transit_canonicalization_preserves_manual_ambiguous_and_country_boundaries(tmp_path):
    region = "Transit:Sumida->Chiyoda"
    photos = [
        Photo(tmp_path / "one.jpg", "one.jpg", region=region, country="Japan", chapter_folder="20b_Transit_Sumida-Chiyoda"),
        Photo(tmp_path / "two.jpg", "two.jpg", region=region, country="Japan", chapter_folder="31b_Transit_Sumida-Chiyoda"),
        Photo(tmp_path / "reserve.jpg", "reserve.jpg", region=region, country="Japan"),
        Photo(tmp_path / "manual.jpg", "manual.jpg", region="Transit:Nara->Osaka", country="Japan",
              chapter_folder="42b_Transit_Nara-Osaka", flags=["manual_chapter"]),
        Photo(tmp_path / "unassigned.jpg", "unassigned.jpg", region="Transit:Nara->Osaka", country="Japan"),
        Photo(tmp_path / "foreign.jpg", "foreign.jpg", region=region, country="China"),
        Photo(tmp_path / "reverse.jpg", "reverse.jpg", region="Transit:Chiyoda->Sumida", country="Japan"),
    ]
    state = ReviewSession(photos, BookPlan(), tmp_path / "project").snapshot()
    chapters = [photo["chapter"] for photo in state["photos"]]
    assert chapters[:2] == ["20b_Transit_Sumida-Chiyoda", "31b_Transit_Sumida-Chiyoda"]
    assert chapters[2] not in chapters[:2]
    assert chapters[3] == "42b_Transit_Nara-Osaka" and chapters[4] != chapters[3]
    assert chapters[5] != chapters[2]
    assert chapters[6] not in chapters[:3]


def test_replacement_in_transit_keeps_the_existing_transit_type(tmp_path):
    root = "20b_Transit_Sumida-Chiyoda"
    photos = [Photo(tmp_path / f"{i}.jpg", f"{i}.jpg", region="Transit:Sumida->Chiyoda",
                    chapter_folder=root if i == 0 else None, chapter_type="Transit" if i == 0 else None,
                    is_selected=i == 0, book_position=1 if i == 0 else None) for i in range(2)]
    session = ReviewSession(photos, BookPlan(), tmp_path / "project")
    session.action({"action": "replace", "anchor": 0, "id": 1})
    assert photos[1].chapter_folder == root and photos[1].chapter_type == "Transit"
    assert photos[1].book_position == 1


def test_manual_chapter_with_transit_in_its_name_keeps_its_type_on_replace(tmp_path):
    folder = "Mein-Transit-Urlaub/hauptteil"
    photos = [Photo(tmp_path / f"{i}.jpg", f"{i}.jpg", region="Tokyo",
                    chapter_folder=folder if i == 0 else None, chapter_type="Hauptteil" if i == 0 else None,
                    flags=["manual_chapter"] if i == 0 else [],
                    is_selected=i == 0, book_position=1 if i == 0 else None) for i in range(2)]
    session = ReviewSession(photos, BookPlan(), tmp_path / "project")
    session.action({"action": "replace", "anchor": 0, "id": 1})
    assert photos[1].chapter_folder == folder and photos[1].chapter_type == "Hauptteil"
