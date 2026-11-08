"""Preview geography changes without running selection or modifying originals."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .geocoding import GeocodeCache
from .location_schema import normalize_location_evidence
from .models import Photo
from .regions import build_location_plan
from .utils import slugify

GEOGRAPHIC_FIELDS = ("region", "country", "place_label", "assigned_by_time",
                     "location_evidence", "fine_cluster_id", "chapter_folder", "chapter_type")
MANUAL_CHAPTER_FLAGS = {"manual_chapter", "manual_chapter_override"}


def geographic_flag(flag: str) -> bool:
    return flag in {"assigned_by_time", "unbestimmt", "transit", "preamble_next_region"} or flag.startswith(
        ("location_", "gps_"))


@dataclass(frozen=True)
class LocationChange:
    index: int
    filename: str
    old_region: str | None
    new_region: str | None
    old_folder: str | None
    new_folder: str | None
    source: str
    warning: str | None


@dataclass(frozen=True)
class LocationRepairPreview:
    photos: list[Photo]
    changes: tuple[LocationChange, ...]
    unresolved_count: int

    @property
    def changed_count(self) -> int:
        return len(self.changes)


def preview_location_repair(
    photos: list[Photo], cache: GeocodeCache, max_hours: float = 6.0,
) -> LocationRepairPreview:
    """Fresh GPS/city/time evidence; explicit chapters and manual locations survive.

    The cache performs online lookups only when explicitly enabled by the caller.
    Scores, last automatic selection traces and all current decisions are copied
    unchanged. No files containing photos or project decisions are written.
    """
    corrected = deepcopy(photos)
    for photo in corrected:
        photo.region = photo.country = photo.place_label = None
        photo.location_evidence = {}
        photo.fine_cluster_id = None
        photo.assigned_by_time = False
        # Retain a scanner's invalid-GPS finding even if its malformed EXIF was
        # safely converted to None. Other previous inference flags are stale.
        photo.flags = [flag for flag in photo.flags if not geographic_flag(flag) or flag == "gps_invalid"]
    plan = build_location_plan(corrected, cache, gps_time_hours=max_hours)
    folders = {region.name: f"{i + 1:02d}_{slugify(region.name)}"
               for i, region in enumerate(plan.regions)}
    if any(photo.region == "Unbestimmt" for photo in corrected):
        folders["Unbestimmt"] = f"{len(folders) + 1:02d}_Unbestimmt"
    changes: list[LocationChange] = []
    for i, (old, new) in enumerate(zip(photos, corrected)):
        prior = normalize_location_evidence(old.location_evidence)
        if prior.get("source") == "manual":
            for field in GEOGRAPHIC_FIELDS[:6]:
                setattr(new, field, deepcopy(getattr(old, field)))
            new.flags = [flag for flag in old.flags]
        if (old.is_aside or MANUAL_CHAPTER_FLAGS.intersection(old.flags)
                or prior.get("source") == "manual"):
            new.chapter_folder, new.chapter_type = old.chapter_folder, old.chapter_type
        elif old.chapter_folder or old.is_selected:
            food = old.chapter_type == "Essen" or old.scene_type == "essen"
            new.chapter_type = "Essen" if food else "Hauptteil"
            folder = folders.get(new.region, slugify(new.region or "Unbestimmt"))
            new.chapter_folder = f"{folder}/{'essen' if food else 'hauptteil'}"
        evidence = normalize_location_evidence(new.location_evidence)
        warning = evidence.get("warning")
        prior_proof = {key: value for key, value in prior.items() if key != "assigned_at"}
        current_proof = {key: value for key, value in evidence.items() if key != "assigned_at"}
        if ((old.region, old.country, old.chapter_folder) != (new.region, new.country, new.chapter_folder)
                or prior_proof != current_proof or warning):
            changes.append(LocationChange(i, new.filename, old.region, new.region,
                old.chapter_folder, new.chapter_folder, evidence.get("source", "unknown"), warning))
    return LocationRepairPreview(corrected, tuple(changes), sum(
        not photo.is_aside and photo.region in (None, "Unbestimmt", "Album") for photo in corrected))


def apply_location_repair(photos: list[Photo], preview: LocationRepairPreview) -> None:
    """Apply only geography, after the caller has durably saved the preview."""
    if len(photos) != len(preview.photos) or any(
            old.path != new.path for old, new in zip(photos, preview.photos)):
        raise ValueError("Die Fotoliste hat sich seit der Ortsprüfung geändert.")
    for old, new in zip(photos, preview.photos):
        for field in GEOGRAPHIC_FIELDS:
            setattr(old, field, deepcopy(getattr(new, field)))
        old.flags = ([flag for flag in old.flags if not geographic_flag(flag)]
                     + [flag for flag in new.flags if geographic_flag(flag)])
