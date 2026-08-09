"""Phase 5: Kontingentverteilung, Essens-Trennung, Vielfalt, finale Buchreihenfolge."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

from .ai_review import ensure_scene_types
from .models import BookPlan, ChapterType, Photo
from .people_balance import people_balance_penalty
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
            and not getattr(photos[i], "is_aside", False)
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


def _photo_day(photo: Photo):
    return photo.datetime_taken.date() if photo.datetime_taken else None


def allocate_day_quotas(
    day_sizes: dict,
    quota: int,
    intensity: float,
) -> dict:
    """
    Mischt anteilige und gleichmäßige Tageskontingente.
    intensity 0 = rein proportional zur Fotoanzahl,
    intensity 1 = möglichst gleichmäßig über Tage, mit Deckel pro Tag.
    """
    if quota <= 0 or not day_sizes:
        return {d: 0 for d in day_sizes}
    intensity = float(max(0.0, min(1.0, intensity)))
    days = list(day_sizes.keys())
    total = sum(day_sizes.values()) or 1
    n = len(days)
    prop = {d: quota * (day_sizes[d] / total) for d in days}
    even = {d: quota / n for d in days}
    raw = {d: (1.0 - intensity) * prop[d] + intensity * even[d] for d in days}

    # Bei starker Intensität: kein Tag > ~60% des Kontingents
    max_share = 1.0 - 0.4 * intensity
    max_per_day = max(1, int(np.ceil(quota * max_share)))
    for d in days:
        raw[d] = min(raw[d], float(max_per_day), float(day_sizes[d]))

    # Largest-remainder-Rundung
    floors = {d: int(np.floor(raw[d])) for d in days}
    # mindestens 1 pro Tag mit Fotos, wenn Intensität hoch und Quota es hergibt
    if intensity >= 0.35 and quota >= n:
        for d in days:
            if day_sizes[d] > 0 and floors[d] == 0:
                floors[d] = 1
    assigned = sum(floors.values())
    # Deckel erneut einhalten
    for d in days:
        floors[d] = min(floors[d], day_sizes[d], max_per_day)
    assigned = sum(floors.values())
    remainders = sorted(days, key=lambda d: raw[d] - int(np.floor(raw[d])), reverse=True)
    idx = 0
    while assigned < quota and idx < len(remainders) * 3:
        d = remainders[idx % len(remainders)]
        if floors[d] < min(day_sizes[d], max_per_day):
            floors[d] += 1
            assigned += 1
        idx += 1
    # falls über Quota (durch Mindest-1): wieder kürzen bei größten Tagen
    while assigned > quota:
        d = max(days, key=lambda x: floors[x])
        if floors[d] <= 0:
            break
        floors[d] -= 1
        assigned -= 1
    return floors


def _select_with_coverage(
    photos: list[Photo],
    indices: list[int],
    quota: int,
    similarity_threshold: float,
    coverage_intensity: float,
    prefer_landmarks: bool = False,
    max_landmarks: int = 3,
    people_balance_intensity: float = 0.0,
    person_counts: Optional[dict[int, int]] = None,
) -> list[int]:
    """Auswahl mit optionaler Tages-Abdeckung."""
    counts = person_counts if person_counts is not None else defaultdict(int)
    if coverage_intensity <= 0 or quota <= 0 or not indices:
        return _select_diverse(
            photos,
            indices,
            quota,
            similarity_threshold,
            prefer_landmarks=prefer_landmarks,
            max_landmarks=max_landmarks,
            people_balance_intensity=people_balance_intensity,
            person_counts=counts,
        )

    by_day: dict = defaultdict(list)
    for i in indices:
        by_day[_photo_day(photos[i])].append(i)
    # Tage ohne Datum: eigener Bucket
    day_sizes = {d: len(v) for d, v in by_day.items()}
    if len(day_sizes) <= 1:
        return _select_diverse(
            photos,
            indices,
            quota,
            similarity_threshold,
            prefer_landmarks=prefer_landmarks,
            max_landmarks=max_landmarks,
            people_balance_intensity=people_balance_intensity,
            person_counts=counts,
        )

    quotas = allocate_day_quotas(day_sizes, quota, coverage_intensity)
    selected: list[int] = []
    landmark_budget = max_landmarks
    for day, q in sorted(quotas.items(), key=lambda kv: (kv[0] is None, kv[0])):
        if q <= 0:
            continue
        picked = _select_diverse(
            photos,
            by_day[day],
            q,
            similarity_threshold,
            prefer_landmarks=prefer_landmarks,
            max_landmarks=landmark_budget,
            people_balance_intensity=people_balance_intensity,
            person_counts=counts,
        )
        selected.extend(picked)
        landmark_budget = max(0, landmark_budget - sum(1 for i in picked if photos[i].landmark))

    # Restkontingent auffüllen (falls Tage nicht genug hergaben)
    if len(selected) < quota:
        leftover = [i for i in indices if i not in selected]
        extra = _select_diverse(
            photos,
            leftover,
            quota - len(selected),
            similarity_threshold,
            prefer_landmarks=prefer_landmarks,
            max_landmarks=landmark_budget,
            people_balance_intensity=people_balance_intensity,
            person_counts=counts,
        )
        selected.extend(extra)
    return selected[:quota]


def _bump_person_counts(photo: Photo, person_counts: dict[int, int]) -> None:
    for pid in photo.person_cluster_ids or []:
        person_counts[pid] = person_counts.get(pid, 0) + 1


def _select_diverse(
    photos: list[Photo],
    indices: list[int],
    quota: int,
    similarity_threshold: float,
    prefer_landmarks: bool = False,
    max_landmarks: int = 3,
    people_balance_intensity: float = 0.0,
    person_counts: Optional[dict[int, int]] = None,
) -> list[int]:
    if quota <= 0 or not indices:
        return []

    hist_cache: dict[int, Optional[np.ndarray]] = {
        i: color_histogram(photos[i]) for i in indices
    }
    counts = person_counts if person_counts is not None else defaultdict(int)
    balance_on = float(people_balance_intensity or 0.0) > 0

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
    remaining_rank = [i for i in ranked if i not in mixed]
    mixed.extend(remaining_rank)

    if not balance_on:
        for i in mixed:
            if len(selected) >= quota:
                break
            is_landmark = bool(photos[i].landmark)
            if prefer_landmarks and is_landmark and landmark_count >= max_landmarks:
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
    else:
        # Greedy: Score minus Personen-Überrepräsentation, Reihenfolge in mixed als Tiebreaker
        left = list(mixed)
        while len(selected) < quota and left:
            best_pos: Optional[int] = None
            best_key: Optional[tuple] = None
            for pos, i in enumerate(left):
                is_landmark = bool(photos[i].landmark)
                if prefer_landmarks and is_landmark and landmark_count >= max_landmarks:
                    continue
                too_similar = False
                for j in selected:
                    if hist_similarity(hist_cache[i], hist_cache[j]) >= similarity_threshold:
                        too_similar = True
                        break
                if too_similar:
                    continue
                penalty = people_balance_penalty(
                    photos[i], counts, float(people_balance_intensity)
                )
                key = (photos[i].final_score - penalty, -pos)
                if best_key is None or key > best_key:
                    best_key = key
                    best_pos = pos
            if best_pos is None:
                break
            i = left.pop(best_pos)
            selected.append(i)
            _bump_person_counts(photos[i], counts)
            if photos[i].landmark:
                landmark_count += 1

    # Falls durch Filter zu wenig: mit nächstbesten auffüllen (Similarity lockern)
    if len(selected) < quota:
        pool = ranked if not balance_on else sorted(
            ranked,
            key=lambda i: (
                photos[i].final_score
                - people_balance_penalty(photos[i], counts, float(people_balance_intensity))
            ),
            reverse=True,
        )
        for i in pool:
            if i in selected:
                continue
            if len(selected) >= quota:
                break
            selected.append(i)
            if balance_on:
                _bump_person_counts(photos[i], counts)

    return selected[:quota]


def select_for_region(
    photos: list[Photo],
    indices: list[int],
    quota: int,
    food_ratio: float = 0.15,
    max_landmarks: int = 3,
    similarity_threshold: float = 0.92,
    coverage_intensity: float = 0.0,
    people_balance_intensity: float = 0.0,
) -> tuple[list[int], list[int]]:
    """Gibt (hauptteil_indices, essen_indices) zurück, chronologisch sortiert."""
    # Nur Kandidaten bevorzugen, Fallback auf alle nicht-Duplikate
    def _ok(i: int) -> bool:
        return (
            not photos[i].is_duplicate
            and not getattr(photos[i], "is_burst_reject", False)
            and not getattr(photos[i], "is_aside", False)
        )

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

    # Personen-Balance über Hauptteil + Essen einer Region teilen
    person_counts: dict[int, int] = defaultdict(int)
    selected_main = _select_with_coverage(
        photos,
        main,
        main_quota,
        similarity_threshold=similarity_threshold,
        coverage_intensity=coverage_intensity,
        prefer_landmarks=True,
        max_landmarks=max_landmarks,
        people_balance_intensity=people_balance_intensity,
        person_counts=person_counts,
    )
    selected_food = _select_with_coverage(
        photos,
        food,
        food_quota,
        similarity_threshold=similarity_threshold,
        coverage_intensity=coverage_intensity,
        prefer_landmarks=False,
        people_balance_intensity=people_balance_intensity,
        person_counts=person_counts,
    )

    selected_main.sort(key=lambda i: photos[i].datetime_taken or datetime.min)
    selected_food.sort(key=lambda i: photos[i].datetime_taken or datetime.min)
    return selected_main, selected_food


def select_for_transit(
    photos: list[Photo],
    indices: list[int],
    quota: int,
    similarity_threshold: float = 0.92,
    coverage_intensity: float = 0.0,
    people_balance_intensity: float = 0.0,
) -> list[int]:
    def _ok(i: int) -> bool:
        return (
            not photos[i].is_duplicate
            and not getattr(photos[i], "is_burst_reject", False)
            and not getattr(photos[i], "is_aside", False)
        )

    cand = [i for i in indices if photos[i].is_candidate and _ok(i)]
    if not cand:
        cand = [i for i in indices if _ok(i)]
    ensure_scene_types(photos, cand)
    for i in cand:
        compute_final_score(photos[i])
    selected = _select_with_coverage(
        photos,
        cand,
        quota,
        similarity_threshold=similarity_threshold,
        coverage_intensity=coverage_intensity,
        prefer_landmarks=False,
        people_balance_intensity=people_balance_intensity,
    )
    selected.sort(key=lambda i: photos[i].datetime_taken or datetime.min)
    return selected


def build_book_order(
    photos: list[Photo],
    plan: BookPlan,
    food_ratio: float = 0.15,
    max_landmarks: int = 3,
    similarity_threshold: float = 0.92,
    coverage_intensity: float = 0.0,
    people_balance_intensity: float = 0.0,
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
            coverage_intensity=coverage_intensity,
            people_balance_intensity=people_balance_intensity,
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
                coverage_intensity=coverage_intensity,
                people_balance_intensity=people_balance_intensity,
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
