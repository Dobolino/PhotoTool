"""Phase 5: Kontingentverteilung, Essens-Trennung, Vielfalt, finale Buchreihenfolge."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

from .ai_review import ensure_scene_types
from .models import BookPlan, ChapterType, Photo
from .utils import load_image, to_cv_bgr


def mark_candidates(
    photos: list[Photo],
    plan: BookPlan,
    target_n: int,
    candidate_factor: float = 4.0,
    max_transit_quota: int = 5,
) -> list[int]:
    """Markiert technisch beste Kandidaten pro Region/Transit (K * Zielanzahl)."""
    distribute_quotas(photos, plan, target_n, max_transit_quota=max_transit_quota)
    candidate_indices: list[int] = []

    def pick_for(indices: list[int], quota: int) -> list[int]:
        eligible = [
            i
            for i in indices
            if not photos[i].is_duplicate
            and not getattr(photos[i], "is_burst_reject", False)
            and "unreadable" not in photos[i].flags
        ]
        eligible.sort(key=lambda i: photos[i].technical_score, reverse=True)
        k = max(quota, int(np.ceil(quota * candidate_factor)))
        chosen = eligible[:k]
        for i in chosen:
            photos[i].is_candidate = True
        return chosen

    for region in plan.regions:
        candidate_indices.extend(pick_for(region.photo_indices, region.quota))
    for transit in plan.transits:
        candidate_indices.extend(pick_for(transit.photo_indices, transit.quota))

    return sorted(set(candidate_indices))


def distribute_quotas(
    photos: list[Photo],
    plan: BookPlan,
    target_n: int,
    max_transit_quota: int = 5,
) -> None:
    transit_total = sum(min(max_transit_quota, max(1, t.quota or max_transit_quota)) for t in plan.transits)
    # Transit-Kontingente festsetzen
    for t in plan.transits:
        t.quota = min(max_transit_quota, max(1, len(t.photo_indices)))
    transit_total = sum(t.quota for t in plan.transits)

    region_budget = max(0, target_n - transit_total)
    if not plan.regions:
        return

    weights = []
    for region in plan.regions:
        n_photos = max(1, len(region.photo_indices))
        days = max(1, region.day_count)
        weights.append(n_photos * days)
    weight_sum = float(sum(weights)) or 1.0

    raw = [region_budget * (w / weight_sum) for w in weights]
    quotas = [max(1, int(round(x))) for x in raw] if region_budget > 0 else [0] * len(plan.regions)

    # Anpassen falls Rundung über/unter Budget
    diff = region_budget - sum(quotas)
    order = sorted(range(len(quotas)), key=lambda i: raw[i] - quotas[i], reverse=diff > 0)
    idx = 0
    while diff != 0 and order:
        i = order[idx % len(order)]
        if diff > 0:
            quotas[i] += 1
            diff -= 1
        elif quotas[i] > 1:
            quotas[i] -= 1
            diff += 1
        else:
            idx += 1
            if idx > len(order) * 3:
                break
            continue
        idx += 1

    for region, q in zip(plan.regions, quotas):
        region.quota = q


def color_histogram(photo: Photo, bins: int = 16) -> Optional[np.ndarray]:
    try:
        img = load_image(photo.path)
        bgr = to_cv_bgr(img)
        hist = cv2.calcHist([bgr], [0, 1, 2], None, [bins, bins, bins], [0, 256, 0, 256, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        return hist
    except Exception:
        return None


def hist_similarity(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
    if a is None or b is None:
        return 0.0
    return float(cv2.compareHist(a.astype(np.float32), b.astype(np.float32), cv2.HISTCMP_CORREL))


def compute_final_score(photo: Photo) -> float:
    tech = photo.technical_score
    if photo.aesthetic_score is not None:
        score = 0.45 * tech + 0.55 * float(photo.aesthetic_score)
    else:
        score = tech
    if photo.keep_recommendation is False:
        score *= 0.4
    if photo.quality_issue:
        score *= 0.7
    if getattr(photo, "bad_face", False):
        score *= 0.45
    if photo.landmark and not getattr(photo, "bad_face", False):
        score += 5.0
    photo.final_score = float(max(0.0, min(100.0, score)))
    return photo.final_score


def _select_diverse(
    photos: list[Photo],
    indices: list[int],
    quota: int,
    similarity_threshold: float,
    prefer_landmarks: bool = False,
    max_landmarks: int = 3,
) -> list[int]:
    if quota <= 0 or not indices:
        return []

    hist_cache: dict[int, Optional[np.ndarray]] = {
        i: color_histogram(photos[i]) for i in indices
    }

    # Nach Score sortieren; schlechte Gesichter stark nach hinten
    def sort_key(i: int) -> tuple:
        bad = 1 if getattr(photos[i], "bad_face", False) else 0
        landmark_boost = 1 if (prefer_landmarks and photos[i].landmark and not bad) else 0
        return (-bad, landmark_boost, photos[i].final_score)

    ranked = sorted(indices, key=sort_key, reverse=True)
    selected: list[int] = []
    landmark_count = 0

    # Szene-Typen rotieren
    scene_buckets: dict[str, list[int]] = defaultdict(list)
    for i in ranked:
        scene_buckets[photos[i].scene_type or "sonstiges"].append(i)
    scene_order = [
        "sehenswuerdigkeit",
        "landschaft",
        "portrait",
        "gruppe",
        "detail",
        "alltag",
        "transport",
        "sonstiges",
        "essen",
    ]
    # Round-robin über Szenen
    pointers = {s: 0 for s in scene_buckets}
    mixed: list[int] = []
    while len(mixed) < len(ranked):
        progressed = False
        for scene in scene_order:
            bucket = scene_buckets.get(scene) or []
            p = pointers.get(scene, 0)
            if p < len(bucket):
                mixed.append(bucket[p])
                pointers[scene] = p + 1
                progressed = True
        if not progressed:
            break
    # Rest anhängen
    remaining = [i for i in ranked if i not in mixed]
    mixed.extend(remaining)

    for i in mixed:
        if len(selected) >= quota:
            break
        is_landmark = bool(photos[i].landmark)
        if prefer_landmarks and is_landmark and landmark_count >= max_landmarks:
            # Landmark-Deckel: überspringen wenn schon genug
            # aber nur wenn noch Alternativen existieren
            continue
        too_similar = False
        for j in selected:
            if hist_similarity(hist_cache[i], hist_cache[j]) >= similarity_threshold:
                too_similar = True
                break
        if too_similar:
            continue
        selected.append(i)
        if is_landmark:
            landmark_count += 1

    # Falls durch Filter zu wenig: mit nächstbesten auffüllen (Similarity lockern)
    if len(selected) < quota:
        for i in ranked:
            if i in selected:
                continue
            if len(selected) >= quota:
                break
            selected.append(i)

    return selected[:quota]


def select_for_region(
    photos: list[Photo],
    indices: list[int],
    quota: int,
    food_ratio: float = 0.15,
    max_landmarks: int = 3,
    similarity_threshold: float = 0.92,
) -> tuple[list[int], list[int]]:
    """Gibt (hauptteil_indices, essen_indices) zurück, chronologisch sortiert."""
    # Nur Kandidaten bevorzugen, Fallback auf alle nicht-Duplikate
    def _ok(i: int) -> bool:
        return not photos[i].is_duplicate and not getattr(photos[i], "is_burst_reject", False)

    cand = [i for i in indices if photos[i].is_candidate and _ok(i)]
    if not cand:
        cand = [i for i in indices if _ok(i)]

    ensure_scene_types(photos, cand)
    for i in cand:
        compute_final_score(photos[i])

    food = [i for i in cand if photos[i].scene_type == "essen"]
    main = [i for i in cand if photos[i].scene_type != "essen"]

    food_quota = 0
    if food and quota > 0:
        food_quota = max(1, int(round(quota * food_ratio)))
        food_quota = min(food_quota, len(food), quota)
    main_quota = max(0, quota - food_quota)

    selected_main = _select_diverse(
        photos,
        main,
        main_quota,
        similarity_threshold=similarity_threshold,
        prefer_landmarks=True,
        max_landmarks=max_landmarks,
    )
    selected_food = _select_diverse(
        photos,
        food,
        food_quota,
        similarity_threshold=similarity_threshold,
        prefer_landmarks=False,
    )

    selected_main.sort(key=lambda i: photos[i].datetime_taken or datetime.min)
    selected_food.sort(key=lambda i: photos[i].datetime_taken or datetime.min)
    return selected_main, selected_food


def select_for_transit(
    photos: list[Photo],
    indices: list[int],
    quota: int,
    similarity_threshold: float = 0.92,
) -> list[int]:
    def _ok(i: int) -> bool:
        return not photos[i].is_duplicate and not getattr(photos[i], "is_burst_reject", False)

    cand = [i for i in indices if photos[i].is_candidate and _ok(i)]
    if not cand:
        cand = [i for i in indices if _ok(i)]
    ensure_scene_types(photos, cand)
    for i in cand:
        compute_final_score(photos[i])
    selected = _select_diverse(
        photos, cand, quota, similarity_threshold=similarity_threshold, prefer_landmarks=False
    )
    selected.sort(key=lambda i: photos[i].datetime_taken or datetime.min)
    return selected


def build_book_order(
    photos: list[Photo],
    plan: BookPlan,
    food_ratio: float = 0.15,
    max_landmarks: int = 3,
    similarity_threshold: float = 0.92,
) -> list[tuple[int, str, str]]:
    """
    Finale Buchreihenfolge.
    Returns list of (photo_index, chapter_folder, chapter_type).
    """
    from .utils import slugify

    order: list[tuple[int, str, str]] = []
    transit_by_after = {t.chapter_index: t for t in plan.transits}

    for r_idx, region in enumerate(plan.regions):
        folder = f"{r_idx + 1:02d}_{slugify(region.name)}"
        main_sel, food_sel = select_for_region(
            photos,
            region.photo_indices,
            region.quota,
            food_ratio=food_ratio,
            max_landmarks=max_landmarks,
            similarity_threshold=similarity_threshold,
        )
        for i in main_sel:
            photos[i].is_selected = True
            photos[i].chapter_type = ChapterType.HAUPTTEIL.value
            photos[i].chapter_folder = f"{folder}/hauptteil"
            order.append((i, f"{folder}/hauptteil", ChapterType.HAUPTTEIL.value))
        for i in food_sel:
            photos[i].is_selected = True
            photos[i].chapter_type = ChapterType.ESSEN.value
            photos[i].chapter_folder = f"{folder}/essen"
            order.append((i, f"{folder}/essen", ChapterType.ESSEN.value))

        if r_idx in transit_by_after:
            t = transit_by_after[r_idx]
            t_folder = (
                f"{r_idx + 1:02d}b_Transit_{slugify(t.from_region)}-{slugify(t.to_region)}"
            )
            t_sel = select_for_transit(
                photos,
                t.photo_indices,
                t.quota,
                similarity_threshold=similarity_threshold,
            )
            for i in t_sel:
                photos[i].is_selected = True
                photos[i].chapter_type = ChapterType.TRANSIT.value
                photos[i].chapter_folder = t_folder
                order.append((i, t_folder, ChapterType.TRANSIT.value))

    for pos, (idx, folder, ctype) in enumerate(order, start=1):
        photos[idx].book_position = pos
        photos[idx].chapter_folder = folder
        photos[idx].chapter_type = ctype

    return order
