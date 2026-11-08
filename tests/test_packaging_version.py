"""Reject release builds whose three public versions disagree."""

import runpy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
validate = runpy.run_path(str(ROOT / "packaging" / "build.py"))["validate_release_version"]


def test_current_release_metadata_agrees():
    from photobook_curator import __version__

    assert validate(ROOT) == __version__


@pytest.mark.parametrize("metadata,installer", [("0.2.0", "0.3.0"), ("0.3.0", "0.2.0")])
def test_mismatched_metadata_blocks_build(tmp_path, metadata, installer):
    (tmp_path / "photobook_curator").mkdir()
    (tmp_path / "packaging").mkdir()
    (tmp_path / "photobook_curator" / "__init__.py").write_text('__version__ = "0.3.0"\n')
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{metadata}"\n')
    (tmp_path / "packaging" / "installer.iss").write_text(f'#define AppVersion "{installer}"\n')
    with pytest.raises(ValueError, match="Versionen"):
        validate(tmp_path)
