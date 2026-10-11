"""Bounded undo history storing only changed review metadata, never image pixels."""

from __future__ import annotations

from .models import Photo

FIELDS = (
    "is_selected", "is_favorite", "chapter_folder", "chapter_type", "region",
    "is_aside", "is_duplicate", "is_burst_reject", "duplicate_of",
    "book_position", "flags",
)


def _state(photo: Photo) -> tuple:
    return tuple(tuple(photo.flags) if key == "flags" else getattr(photo, key)
                 for key in FIELDS)


class ReviewHistory:
    def __init__(self, photos: list[Photo], limit: int = 100):
        self.current = [_state(p) for p in photos]
        self.limit = max(1, limit)
        self.undo_stack: list[list[tuple[int, tuple, tuple]]] = []
        self.redo_stack: list[list[tuple[int, tuple, tuple]]] = []

    def record(self, photos: list[Photo]) -> None:
        states = [_state(p) for p in photos]
        changes = [(i, old, new) for i, (old, new) in enumerate(zip(self.current, states))
                   if old != new]
        if changes:
            self.undo_stack.append(changes)
            del self.undo_stack[:-self.limit]
            self.redo_stack.clear()
            self.current = states

    def _apply(self, photos: list[Photo], source: list, target: list, forward: bool) -> bool:
        if not source:
            return False
        changes = source.pop()
        for idx, before, after in changes:
            state = after if forward else before
            for key, value in zip(FIELDS, state):
                setattr(photos[idx], key, list(value) if key == "flags" else value)
            self.current[idx] = state
        target.append(changes)
        return True

    def undo(self, photos: list[Photo]) -> bool:
        return self._apply(photos, self.undo_stack, self.redo_stack, False)

    def redo(self, photos: list[Photo]) -> bool:
        return self._apply(photos, self.redo_stack, self.undo_stack, True)
