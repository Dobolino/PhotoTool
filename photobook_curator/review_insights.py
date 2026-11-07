"""Explainable review suggestions from existing metadata; no invented image semantics."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .models import Photo


def _score(photo: Photo) -> float:
    return float(photo.final_score or photo.technical_score or 0.0)


def _chapter(photo: Photo) -> str:
    return (photo.chapter_folder or photo.region or "Ohne Kapitel").split("/")[0]


def _day(photo: Photo) -> str:
    return photo.datetime_taken.date().isoformat() if photo.datetime_taken else "Ohne Datum"


def story_role(photo: Photo) -> str:
    """A broad role inferred from existing scene labels, not a subject recognizer."""
    scene = photo.scene_type or "sonstiges"
    if photo.face_count > 0 or scene in {"portrait", "gruppe"}:
        return "people"
    if scene in {"landschaft", "sehenswuerdigkeit"}:
        return "overview"
    if scene in {"detail", "essen"}:
        return "detail"
    return "atmosphere"


@dataclass(frozen=True)
class MotifGroup:
    group_id: str
    label: str
    kind: str
    indices: tuple[int, ...]
    recommended_indices: tuple[int, ...]
    reasons: tuple[str, ...]
    selected_count: int


def build_motif_groups(photos: list[Photo]) -> list[MotifGroup]:
    buckets: dict[tuple, list[int]] = defaultdict(list)
    for i, p in enumerate(photos):
        if p.burst_group_id is not None:
            buckets[("burst", p.burst_group_id)].append(i)
        if p.content_cluster_id is not None:
            buckets[("content", p.content_cluster_id)].append(i)
        if p.phash:
            buckets[("phash", p.phash)].append(i)
        if p.landmark:
            buckets[("landmark", _chapter(p), _day(p), p.landmark)].append(i)
    labels = {"burst": "Aufnahmeserie", "content": "Visuell verwandte Motive",
              "phash": "Gleicher Bild-Fingerabdruck", "landmark": "Erkanntes Motiv"}
    reasons = {"burst": "Zeitlich nahe Aufnahmen mit ähnlichem Bildinhalt.",
               "content": "Vorhandene Embedding-Gruppe; Varianten vor dem Aussortieren vergleichen.",
               "phash": "Identischer pHash ist ein Ähnlichkeitshinweis, kein Beweis identischer Dateien.",
               "landmark": "Gleiches vorhandenes Motivlabel am selben Tag und im selben Kapitel."}
    groups = []
    seen_sets: set[frozenset[int]] = set()
    for key, members in buckets.items():
        identity = frozenset(members)
        if len(members) < 2 or identity in seen_sets:
            continue
        seen_sets.add(identity)
        ranked = sorted(members, key=lambda i: (photos[i].is_favorite,
            getattr(photos[i], "manual_decision", "auto") == "keep",
            not photos[i].bad_face, _score(photos[i]), -i), reverse=True)
        eligible = [i for i in ranked if getattr(photos[i], "manual_decision", "auto") != "reject"
                    or photos[i].is_favorite]
        kind = str(key[0])
        label = labels[kind] + (f": {key[-1]}" if kind == "landmark" else "")
        groups.append(MotifGroup(": ".join(map(str, key)), label, kind, tuple(members),
                                tuple(eligible[:2]), (reasons[kind],),
                                sum(photos[i].is_selected for i in members)))
    return sorted(groups, key=lambda g: (-len(g.indices), g.group_id))


@dataclass(frozen=True)
class ReviewItem:
    photo_index: int
    priority: float
    reasons: tuple[str, ...]
    alternatives: tuple[int, ...]
    chapter: str
    day: str


def build_review_queue(photos: list[Photo], limit: int = 100) -> list[ReviewItem]:
    """Prioritize consequential ambiguity; avoid quadratic whole-trip comparisons."""
    alternatives: dict[int, set[int]] = defaultdict(set)
    for group in build_motif_groups(photos):
        ranked = sorted(group.indices, key=lambda i: _score(photos[i]), reverse=True)
        for i in group.indices:
            alternatives[i].update(j for j in ranked[:6] if j != i)
    by_chapter_day: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, p in enumerate(photos):
        by_chapter_day[(_chapter(p), _day(p))].append(i)
    for members in by_chapter_day.values():
        # Nearby score boundary offers useful alternatives without pretending the
        # images show the same object. At most 12 candidates are retained per day.
        ranked = sorted(members, key=lambda i: _score(photos[i]), reverse=True)
        selected = [i for i in ranked if photos[i].is_selected][-6:]
        omitted = [i for i in ranked if not photos[i].is_selected][:6]
        for i in selected:
            alternatives[i].update(omitted)
        for i in omitted:
            alternatives[i].update(selected)
    result = []
    for i, p in enumerate(photos):
        if getattr(p, "manual_decision", "auto") != "auto":
            continue
        reasons: list[str] = []
        priority = 0.0
        if p.is_selected and (p.bad_face or p.eyes_closed or p.quality_issue
                              or p.is_too_dark or p.is_overexposed):
            reasons.append("Ausgewähltes Bild hat einen Qualitäts-/Gesichtshinweis.")
            priority += 65
        if p.is_selected and (p.is_duplicate or p.is_burst_reject or p.is_aside):
            reasons.append("Ausgewähltes Bild widerspricht einem automatischen Filter; bewusste Wahl prüfen.")
            priority += 55
        choices = sorted(alternatives[i], key=lambda j: (
            abs(_score(p) - _score(photos[j])), -_score(photos[j]), j))
        close = [j for j in choices if photos[j].is_selected != p.is_selected
                 and abs(_score(p) - _score(photos[j])) <= 8]
        if close:
            gap = abs(_score(p) - _score(photos[close[0]]))
            reasons.append(f"Auswahl und Alternative liegen nur {gap:.1f} Score-Punkte auseinander.")
            priority += 35 + (8 - gap)
        if p.is_selected and not p.datetime_taken:
            reasons.append("Aufnahmedatum fehlt; Tageszuordnung und Reihenfolge prüfen.")
            priority += 20
        if p.is_favorite:
            priority *= 0.5
        if reasons:
            result.append(ReviewItem(i, round(priority, 2), tuple(reasons), tuple(choices[:5]),
                                     _chapter(p), _day(p)))
    return sorted(result, key=lambda item: (-item.priority, item.chapter, item.day,
                                           item.photo_index))[:max(0, limit)]


@dataclass(frozen=True)
class ChapterStory:
    chapter: str
    counts: dict[str, int]
    missing_roles: tuple[str, ...]
    photo_count: int


def chapter_story_summary(photos: list[Photo], selected_only: bool = True) -> list[ChapterStory]:
    buckets: dict[str, Counter] = defaultdict(Counter)
    for p in photos:
        if not selected_only or p.is_selected:
            buckets[_chapter(p)][story_role(p)] += 1
    roles = ("overview", "people", "detail", "atmosphere")
    return [ChapterStory(chapter, {r: counts[r] for r in roles},
                         tuple(r for r in roles if not counts[r]), sum(counts.values()))
            for chapter, counts in buckets.items()]
