"""Photo-book capacity and explanatory trip coverage, independent of layout engines."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import BookPlan, Photo


@dataclass(frozen=True)
class BookBudget:
    pages: int
    photos_per_page: float
    reserved_pages: int
    photo_pages: int
    target_count: int


def calculate_book_budget(pages: int, photos_per_page: float = 2.5,
                          reserved_pages: int = 4) -> BookBudget:
    """Reserve title/text pages, then floor average picture capacity.

    This estimates how many source photos to select, not their print placement.
    """
    if isinstance(pages, bool) or not isinstance(pages, int) or pages < 1:
        raise ValueError("Seitenzahl muss eine positive ganze Zahl sein")
    if (isinstance(reserved_pages, bool) or not isinstance(reserved_pages, int)
            or reserved_pages < 0 or reserved_pages >= pages):
        raise ValueError("Reservierte Seiten müssen zwischen 0 und Seitenzahl minus 1 liegen")
    if (isinstance(photos_per_page, bool) or not isinstance(photos_per_page, (int, float))
            or not math.isfinite(photos_per_page) or not 0 < photos_per_page <= 20):
        raise ValueError("Bilder pro Seite müssen grösser 0 und höchstens 20 sein")
    photo_pages = pages - reserved_pages
    target = math.floor(photo_pages * photos_per_page)
    if target < 1:
        raise ValueError("Das Seitenbudget muss mindestens ein Bild erlauben")
    return BookBudget(pages, float(photos_per_page), reserved_pages, photo_pages, target)


@dataclass(frozen=True)
class BudgetAssessment:
    requested: int
    available: int
    capacity_upper_bound: int
    forced_count: int
    feasible: bool
    warnings: tuple[str, ...]


def assess_budget(photos: list[Photo], plan: BookPlan, target: int,
                  max_per_day: int = 0, max_per_chapter: int = 0) -> BudgetAssessment:
    """Conservative capacity estimate; overlapping day/chapter limits may reduce it further."""
    from .selection import _ok_for_selection, _forced
    eligible = {i for i, p in enumerate(photos) if _ok_for_selection(p) or _forced(p)}
    forced = sum(_forced(photos[i]) for i in eligible)
    upper = len(eligible)
    warnings: list[str] = []
    if max_per_day > 0:
        days = Counter(p.datetime_taken.date() if p.datetime_taken else None
                       for i, p in enumerate(photos) if i in eligible)
        forced_days = Counter(p.datetime_taken.date() if p.datetime_taken else None
                             for i, p in enumerate(photos) if i in eligible and _forced(p))
        upper = min(upper, sum(max(min(n, max_per_day), forced_days[d]) for d, n in days.items()))
        if None in days:
            warnings.append("Bilder ohne Aufnahmedatum teilen ein gemeinsames Tageskontingent.")
    if max_per_chapter > 0:
        capacities = []
        assigned: set[int] = set()
        for chapter in [*plan.regions, *plan.transits]:
            indices = set(chapter.photo_indices) & eligible
            assigned.update(indices)
            capacities.append(max(min(len(indices), max_per_chapter),
                                  sum(_forced(photos[i]) for i in indices)))
        # Forced keeps outside regular chapters are still retained.
        upper = min(upper, sum(capacities) + sum(_forced(photos[i]) for i in eligible - assigned))
    if target > upper:
        warnings.append(f"Ziel {target} übersteigt das verfügbare Kontingent (höchstens {upper} Bilder).")
    if forced > target:
        warnings.append(f"{forced} geschützte oder dauerhaft behaltene Bilder haben Vorrang vor Ziel {target}.")
    if max_per_day or max_per_chapter:
        warnings.append("Überlappende Tages-/Kapitelgrenzen können die tatsächliche Auswahl weiter reduzieren.")
    return BudgetAssessment(target, len(eligible), upper, forced, target <= upper and forced <= target,
                            tuple(warnings))
