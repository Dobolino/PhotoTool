"""P0-Fixes: EXIF-Orientierung, Download-Timeout, Geocode-Cache, CSV-Drift."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import piexif
from PIL import Image

from photobook_curator.geocoding import GeocodeCache
from photobook_curator.models import Photo
from photobook_curator.output import CSV_FIELDS
from photobook_curator.utils import download_model, load_image


def test_csv_fields_match_row():
    p = Photo(path=Path("x.jpg"), filename="x.jpg")
    assert set(p.to_csv_row().keys()) == set(CSV_FIELDS)


def test_load_image_applies_exif_orientation(tmp_path: Path):
    """Orientation 6 (90° CW): gespeichert 40x20 → angezeigt 20x40."""
    path = tmp_path / "rotated.jpg"
    img = Image.new("RGB", (40, 20), (200, 100, 50))
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    exif_dict["0th"][piexif.ImageIFD.Orientation] = 6
    exif_bytes = piexif.dump(exif_dict)
    img.save(path, exif=exif_bytes)

    loaded = load_image(path)
    assert loaded.size == (20, 40)


def test_download_model_rejects_tiny_file(tmp_path: Path):
    dest = tmp_path / "model.tflite"

    def fake_retrieve(url, filename):
        Path(filename).write_bytes(b"tiny")

    with patch("photobook_curator.utils.urlretrieve", side_effect=fake_retrieve):
        assert download_model("http://example.com/m.tflite", dest) is None
    assert not dest.exists()


def test_download_model_keeps_valid_file(tmp_path: Path):
    dest = tmp_path / "model.tflite"

    def fake_retrieve(url, filename):
        Path(filename).write_bytes(b"x" * 2000)

    with patch("photobook_curator.utils.urlretrieve", side_effect=fake_retrieve):
        result = download_model("http://example.com/m.tflite", dest)
    assert result == dest
    assert dest.stat().st_size == 2000


def test_download_model_timeout_cleans_up(tmp_path: Path):
    dest = tmp_path / "model.tflite"

    with patch("photobook_curator.utils.urlretrieve", side_effect=TimeoutError("hang")):
        assert download_model("http://example.com/m.tflite", dest, timeout=1.0) is None
    assert not dest.exists()


def test_geocode_transient_error_not_persisted(tmp_path: Path):
    from geopy.exc import GeocoderTimedOut

    cache = GeocodeCache(tmp_path / "cache.json", enabled=True)
    cache._geocoder = MagicMock()
    cache._geocoder.reverse.side_effect = GeocoderTimedOut("timeout")
    cache.min_interval_s = 0.0

    result = cache.reverse(35.6762, 139.6503)
    assert result["city"] is None
    # Key darf nicht im Cache liegen
    key = cache._key(35.6762, 139.6503)
    assert key not in cache._cache


def test_geocode_none_result_is_cached(tmp_path: Path):
    cache = GeocodeCache(tmp_path / "cache.json", enabled=True)
    cache._geocoder = MagicMock()
    cache._geocoder.reverse.return_value = None
    cache.min_interval_s = 0.0

    result = cache.reverse(1.0, 2.0)
    assert result["city"] is None
    key = cache._key(1.0, 2.0)
    assert key in cache._cache
