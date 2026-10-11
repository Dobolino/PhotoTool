import hashlib
import io

import pytest

from photobook_curator import updater


def release(version="0.4.0", **overrides):
    data = {"tag_name": "v" + version, "assets": [{
        "name": f"PhotoTool-Setup-{version}.exe", "size": 4,
        "browser_download_url": f"https://github.com/Dobolino/PhotoTool/releases/download/v{version}/PhotoTool-Setup-{version}.exe",
        "digest": "sha256:" + hashlib.sha256(b"test").hexdigest(),
    }]}
    data.update(overrides)
    return data


def test_only_new_stable_releases_are_offered():
    assert updater.parse_release(release()).version == "0.4.0"
    assert updater.parse_release(release("0.3.0")) is None
    assert updater.parse_release(release("0.1.0")) is None
    assert updater.parse_release(release(prerelease=True)) is None
    assert updater.parse_release(release(draft=True)) is None
    assert updater.version_tuple("v0.10.0") > updater.version_tuple("0.9.0")


@pytest.mark.parametrize("field,value", [("digest", None), ("digest", "sha256:bad"),
    ("browser_download_url", "https://example.com/setup.exe"), ("size", 0), ("size", updater.MAX_DOWNLOAD + 1)])
def test_bad_update_assets_are_rejected(field, value):
    data = release()
    data["assets"][0][field] = value
    with pytest.raises(ValueError):
        updater.parse_release(data)


def test_missing_installer_is_distinct_from_current_version():
    with pytest.raises(ValueError):
        updater.parse_release(release(assets=[]))


def test_download_verifies_hash_and_size(monkeypatch, tmp_path):
    update = updater.parse_release(release())
    monkeypatch.setattr(updater, "urlopen", lambda *a, **kw: io.BytesIO(b"test"))
    result = updater.download_update(update, tmp_path)
    assert result.read_bytes() == b"test"


@pytest.mark.parametrize("payload", [b"fake", b"short", b"no"])
def test_corrupt_or_truncated_download_is_deleted(monkeypatch, tmp_path, payload):
    update = updater.parse_release(release())
    monkeypatch.setattr(updater, "urlopen", lambda *a, **kw: io.BytesIO(payload))
    with pytest.raises(ValueError):
        updater.download_update(update, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_source_runs_cannot_launch_installers(tmp_path):
    with pytest.raises(RuntimeError):
        updater.launch_installer(tmp_path / "setup.exe")
