"""An export underneath originals must not feed back into the next import."""

from pathlib import Path

from PIL import Image

from photobook_curator.scan import find_images, scan_photos


def _image(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (24, 20), "red").save(path)
    return path


def test_nested_output_is_pruned_but_sibling_names_are_kept(tmp_path):
    original = _image(tmp_path / "day1" / "temple.jpg")
    sibling = _image(tmp_path / "output-originals" / "street.jpg")
    _image(tmp_path / "output" / "selected" / "temple.jpg")
    assert find_images(tmp_path, exclude_dirs=[tmp_path / "output"]) == sorted([original, sibling])


def test_explicit_video_still_is_included_once_even_in_excluded_output(tmp_path):
    original = _image(tmp_path / "temple.jpg")
    still = _image(tmp_path / "output" / "video_stills" / "train.jpg")
    _image(tmp_path / "output" / "selected" / "old.jpg")
    photos = scan_photos(tmp_path, exclude_dirs=[tmp_path / "output"], extra_paths=[still, still])
    assert [photo.path for photo in photos] == [original.resolve(), still.resolve()]


def test_excluded_root_is_empty_and_default_scan_is_unchanged(tmp_path):
    original = _image(tmp_path / "temple.jpg")
    assert find_images(tmp_path) == [original]
    assert find_images(tmp_path, exclude_dirs=[tmp_path]) == []
