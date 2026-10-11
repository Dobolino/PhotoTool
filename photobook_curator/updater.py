"""Opt-in updates from stable GitHub Releases, verified against GitHub's SHA256."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from . import __version__

REPO = "Dobolino/PhotoTool"
RELEASES_URL = f"https://github.com/{REPO}/releases"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
MAX_DOWNLOAD = 2 * 1024 ** 3


@dataclass(frozen=True)
class Update:
    version: str
    url: str
    sha256: str
    size: int


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError(f"Unsupported stable version: {value}")
    return tuple(int(v) for v in match.groups())


def parse_release(data: dict, current: str = __version__) -> Update | None:
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name", "")
    if version_tuple(tag) <= version_tuple(current):
        return None
    version = tag.removeprefix("v")
    name = f"PhotoTool-Setup-{version}.exe"
    for asset in data.get("assets", []):
        if asset.get("name") != name:
            continue
        url = asset.get("browser_download_url", "")
        expected = f"https://github.com/{REPO}/releases/download/{tag}/{name}"
        digest = asset.get("digest") or ""
        size = asset.get("size", 0)
        if (url != expected or not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest)
                or not isinstance(size, int) or not 0 < size <= MAX_DOWNLOAD):
            raise ValueError("Invalid update asset or missing SHA256 digest")
        return Update(version, url, digest[7:].lower(), size)
    raise ValueError("The latest release has no matching Windows installer")


def check_update() -> Update | None:
    request = Request(API_URL, headers={"Accept": "application/vnd.github+json",
                      "User-Agent": f"PhotoTool/{__version__}"})
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(2 * 1024 ** 2 + 1)
    except HTTPError as exc:
        if exc.code == 404:  # No published stable release yet.
            return None
        raise
    if len(raw) > 2 * 1024 ** 2:
        raise ValueError("Release metadata too large")
    return parse_release(json.loads(raw))


def download_update(update: Update, directory: Path | None = None) -> Path:
    # Revalidate even if called independently of check_update.
    version_tuple(update.version)
    expected = f"https://github.com/{REPO}/releases/download/v{update.version}/PhotoTool-Setup-{update.version}.exe"
    without_v = expected.replace(f"/v{update.version}/", f"/{update.version}/")
    if (update.url not in (expected, without_v) or
            not re.fullmatch(r"[a-f0-9]{64}", update.sha256) or
            not 0 < update.size <= MAX_DOWNLOAD):
        raise ValueError("Invalid update")
    root = Path(tempfile.mkdtemp(prefix="PhotoTool-update-", dir=directory))
    path = root / f"PhotoTool-Setup-{update.version}.exe"
    digest = hashlib.sha256()
    received = 0
    try:
        request = Request(update.url, headers={"User-Agent": f"PhotoTool/{__version__}"})
        with urlopen(request, timeout=30) as response, path.open("xb") as out:
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                if received > update.size:
                    raise ValueError("Update download exceeds expected size")
                out.write(chunk)
                digest.update(chunk)
        if received != update.size or digest.hexdigest() != update.sha256:
            raise ValueError("Update integrity check failed")
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        root.rmdir()
        raise


def launch_installer(path: Path) -> None:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        raise RuntimeError("In-app installation is available in the Windows executable")
    # Installer handles locked files and restarts the application after setup.
    subprocess.Popen([str(path), "/SILENT", "/CLOSEAPPLICATIONS", "/NORESTART",
                      f"/DIR={Path(sys.executable).resolve().parent}"],
                     close_fds=True)
