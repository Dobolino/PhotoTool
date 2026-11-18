"""Phase 3: Transit-Abschnitte zwischen aufeinanderfolgenden Regionen."""

from __future__ import annotations

from datetime import datetime

from .models import BookPlan, Photo, TransitSection


def detect_transits(
    photos: list[Photo],
    plan: BookPlan,
    min_photos: int = 3,
    max_transit_quota: int = 5,
) -> list[TransitSection]:
    """Erkennt Transit-Bilder zwischen Regionen; zu wenige werden der nächsten Region zugeordnet."""
    regions = plan.regions
    transits: list[TransitSection] = []
    if len(regions) < 2:
        plan.transits = transits
        return transits

    assigned_to_region = set()
    for region in regions:
        assigned_to_region.update(region.photo_indices)

    for i in range(len(regions) - 1):
        a = regions[i]
        b = regions[i + 1]
        if a.end_time is None or b.start_time is None:
            continue
        if a.end_time >= b.start_time:
            # Überlappende Aufenthalte: kein Transit-Fenster
            continue

        candidates: list[int] = []
        for idx, photo in enumerate(photos):
            if photo.datetime_taken is None:
                continue
            if not (a.end_time < photo.datetime_taken < b.start_time):
                continue
            # Nicht bereits einer der beiden Regionen zugeordnet
            if idx in a.photo_indices or idx in b.photo_indices:
                continue
            candidates.append(idx)

        candidates.sort(key=lambda j: photos[j].datetime_taken or datetime.min)

        if len(candidates) >= min_photos:
            for idx in candidates:
                photos[idx].region = f"Transit:{a.name}->{b.name}"
                photos[idx].chapter_type = "Transit"
                photos[idx].add_flag("transit")
                # aus Unbestimmt entfernen
                if idx in plan.unassigned_indices:
                    plan.unassigned_indices.remove(idx)
            transit = TransitSection(
                from_region=a.name,
                to_region=b.name,
                photo_indices=candidates,
                quota=min(max_transit_quota, len(candidates)),
                chapter_index=i,
            )
            transits.append(transit)
        else:
            # Wenige Bilder: als Auftakt der nächsten Region einsortieren
            for idx in candidates:
                photos[idx].region = b.name
                photos[idx].assigned_by_time = True
                photos[idx].add_flag("preamble_next_region")
                if "unbestimmt" in photos[idx].flags:
                    photos[idx].flags = [f for f in photos[idx].flags if f != "unbestimmt"]
                if idx in plan.unassigned_indices:
                    plan.unassigned_indices.remove(idx)
                if idx not in b.photo_indices:
                    b.photo_indices.append(idx)
            b.photo_indices = sorted(
                set(b.photo_indices),
                key=lambda j: photos[j].datetime_taken or datetime.min,
            )
            times = [
                photos[j].datetime_taken for j in b.photo_indices if photos[j].datetime_taken
            ]
            if times:
                b.start_time = min(times)
                b.end_time = max(times)

    plan.transits = transits
    return transits
