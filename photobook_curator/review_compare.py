"""Evidence-aware review candidates and stable album ordering.

Chapter and region membership provide browsing context, not visual evidence.
These helpers read existing metadata only: they do not analyze images, mutate
selection state, or call an AI provider.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from math import isfinite
from typing import Sequence

from .models import Photo


RELATION_LABELS = {
    "series": "Serie",
    "visual": "Visuelle Gruppe",
    "duplicate": "Duplikatbezug",
    "other": "Weitere Aufnahmen",
}


def _path_identity(value) -> str:
    # CSV files can move between Windows and POSIX. No filesystem access is
    # needed, and an ambiguous case-insensitive identity is rejected below.
    return str(value or "").replace("\\", "/").casefold()


def _identity_counts(photos: Sequence[Photo]) -> tuple[Counter, Counter]:
    return (
        Counter(str(photo.filename).casefold() for photo in photos),
        Counter(_path_identity(photo.path) for photo in photos),
    )


def _points_to(source: Photo, target: Photo, names: Counter, paths: Counter) -> bool:
    reference = str(source.duplicate_of or "").strip()
    if not reference:
        return False
    normalized = _path_identity(reference)
    target_path = _path_identity(target.path)
    if normalized == target_path and paths[target_path] == 1:
        return True
    # A basename cannot distinguish IMG_0001.JPG from different folders/cameras.
    # Do not advertise a duplicate relationship unless its target is unique.
    target_name = str(target.filename).casefold()
    return (
        "/" not in normalized
        and normalized == target_name
        and names[target_name] == 1
    )


def _relation(
    anchor: Photo, candidate: Photo, names: Counter, paths: Counter
) -> str:
    if anchor.burst_group_id is not None and candidate.burst_group_id == anchor.burst_group_id:
        return "series"
    if anchor.content_cluster_id is not None and candidate.content_cluster_id == anchor.content_cluster_id:
        return "visual"
    if _points_to(anchor, candidate, names, paths) or _points_to(candidate, anchor, names, paths):
        return "duplicate"
    return "other"


def candidate_relation(
    photos: Sequence[Photo], anchor_idx: int, candidate_idx: int
) -> tuple[str, str]:
    """Return an existing relationship's code and its honest display label.

    A shared chapter/region alone always returns ``other``. Filename-only
    duplicate links must resolve uniquely across this collection.
    """
    if (
        not 0 <= anchor_idx < len(photos)
        or not 0 <= candidate_idx < len(photos)
        or anchor_idx == candidate_idx
    ):
        return "other", RELATION_LABELS["other"]
    names, paths = _identity_counts(photos)
    relation = _relation(photos[anchor_idx], photos[candidate_idx], names, paths)
    return relation, RELATION_LABELS[relation]


def _score(photo: Photo) -> float:
    for value in (photo.final_score, photo.technical_score):
        try:
            score = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if isfinite(score) and score != 0:
            return score
    return 0.0


def _chapter(photo: Photo) -> str:
    folder = (photo.chapter_folder or "").replace("\\", "/")
    return folder.split("/", 1)[0]


def comparison_candidates(
    photos: Sequence[Photo],
    anchor_idx: int,
    kept: set[int],
    limit: int | None = None,
) -> list[int]:
    """Return a deterministic pool, with evidenced relatives before fallbacks.

    Related burst/duplicate photos remain inspectable even if automatic filters
    excluded them. Other photos must be candidates from the same chapter or a
    known matching region. Durable rejections remain visible for comparison;
    the action layer is responsible for its existing protection rules.

    The caller can freeze the returned list while comparing or editing. Selection
    changes do not mutate a previously returned pool.
    """
    if not 0 <= anchor_idx < len(photos) or (limit is not None and limit <= 0):
        return []
    anchor = photos[anchor_idx]
    names, paths = _identity_counts(photos)
    anchor_chapter = _chapter(anchor)
    ranked = []
    for idx, photo in enumerate(photos):
        if idx == anchor_idx or idx in kept or "unreadable" in (photo.flags or []):
            continue
        relation = _relation(anchor, photo, names, paths)
        same_chapter = bool(anchor_chapter and _chapter(photo) == anchor_chapter)
        same_region = bool(anchor.region and photo.region == anchor.region)
        if relation == "other" and not (photo.is_candidate and (same_chapter or same_region)):
            continue
        ranked.append((relation == "other", -_score(photo), idx))
    ranked.sort()
    indices = [idx for _fallback, _score_value, idx in ranked]
    return indices if limit is None else indices[:limit]


def _capture_time(photo: Photo) -> datetime:
    taken = photo.datetime_taken
    if taken is None:
        return datetime.max
    if taken.tzinfo is not None:
        return taken.astimezone(timezone.utc).replace(tzinfo=None)
    return taken


def ordered_album_indices(photos: Sequence[Photo], kept: set[int]) -> list[int]:
    """Order selected photos by saved book position, then capture time/path.

    Photos without a saved book position follow the ordered album. Unknown
    capture times sort last. Exact ties use collection index for stable results.
    """
    def key(idx: int):
        photo = photos[idx]
        position = photo.book_position
        positioned = isinstance(position, int) and not isinstance(position, bool) and position > 0
        return (
            0 if positioned else 1,
            position if positioned else 0,
            _capture_time(photo),
            _path_identity(photo.path),
            str(photo.path),
            idx,
        )

    return sorted((idx for idx in kept if 0 <= idx < len(photos)), key=key)
