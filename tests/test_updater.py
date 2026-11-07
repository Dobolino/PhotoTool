import hashlib
import io
from urllib.error import HTTPError

import pytest

from photobook_curator import updater


NEXT_VERSION = f"{updater.version_tuple(updater.__version__)[0]}.{updater.version_tuple(updater.__version__)[1] + 1}.0"


def release(version=NEXT_VERSION, **overrides):
    data = {"tag_name": "v" + version, "assets": [{
        "name": f"PhotoTool-Setup-{version}.exe", "size": 4,
        "browser_download_url": f"https://github.com/Dobolino/PhotoTool/releases/download/v{version}/PhotoTool-Setup-{version}.exe",
        "digest": "sha256:" + hashlib.sha256(b"test").hexdigest(),
    }]}
    data.update(overrides)
    return data


def test_only_new_stable_releases_are_offered():
    assert updater.parse_release(release()).version == NEXT_VERSION
    assert updater.parse_release(release(updater.__version__)) is None
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


def test_unavailable_release_is_not_reported_as_up_to_date(monkeypatch):
    def unavailable(*args, **kwargs):
        raise HTTPError(updater.API_URL, 404, "Not Found", {}, None)

    monkeypatch.setattr(updater, "urlopen", unavailable)
    with pytest.raises(RuntimeError, match="No public stable release"):
        updater.check_update()


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


def test_installer_updates_the_running_executable_directory(monkeypatch, tmp_path):
    running_exe = tmp_path / "PhotoTool with spaces" / "Fotobuch.exe"
    installer = tmp_path / "PhotoTool-Setup.exe"
    calls = []
    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "executable", str(running_exe))
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs)))
    updater.launch_installer(installer)
    assert calls == [([str(installer), "/SILENT", "/CLOSEAPPLICATIONS", "/NORESTART",
                      f"/DIR={running_exe.parent.resolve()}"], {"close_fds": True})]


def test_update_stays_open_if_review_autosave_reports_failure(monkeypatch, tmp_path):
    from photobook_curator import update_dialog

    calls = []

    class Review:
        def _autosave_draft(self):
            calls.append("save")
            self._draft_save_error = "Disk full"

    class App:
        def winfo_children(self):
            return [Review()]

        def destroy(self):
            calls.append("close")

    monkeypatch.setattr(update_dialog, "launch_installer", lambda path: calls.append("install"))
    with pytest.raises(OSError, match="Disk full"):
        update_dialog._install_downloaded_update(App(), tmp_path / "setup.exe")
    assert calls == ["save"]


def test_update_saves_all_reviews_before_install_and_close(monkeypatch, tmp_path):
    from photobook_curator import update_dialog

    calls = []

    class Review:
        _draft_save_error = None

        def _autosave_draft(self):
            calls.append("save")

    class App:
        def winfo_children(self):
            return [object(), Review(), Review()]

        def destroy(self):
            calls.append("close")

    monkeypatch.setattr(update_dialog, "launch_installer", lambda path: calls.append("install"))
    update_dialog._install_downloaded_update(App(), tmp_path / "setup.exe")
    assert calls == ["save", "save", "install", "close"]


def test_installer_launch_failure_does_not_close_app(monkeypatch, tmp_path):
    from photobook_curator import update_dialog

    class App:
        closed = False

        def winfo_children(self):
            return []

        def destroy(self):
            self.closed = True

    def fail(path):
        raise OSError("Installer unavailable")

    monkeypatch.setattr(update_dialog, "launch_installer", fail)
    app = App()
    with pytest.raises(OSError, match="Installer unavailable"):
        update_dialog._install_downloaded_update(app, tmp_path / "setup.exe")
    assert not app.closed
