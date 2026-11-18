"""Explain stored facts without claiming to know an unrecorded ranking decision."""

from .i18n import t
from .models import Photo


def selection_reasons(photo: Photo, selected: bool | None = None) -> list[str]:
    selected = photo.is_selected if selected is None else selected
    reasons = [t("reason_selected" if selected else "reason_not_selected")]
    if photo.is_favorite:
        reasons.append(t("reason_favorite"))
    if "manual_add" in photo.flags:
        reasons.append(t("reason_manual_add"))
    if "manual_reject" in photo.flags:
        reasons.append(t("reason_manual_reject"))
    if photo.is_duplicate:
        reasons.append(t("reason_duplicate", name=photo.duplicate_of or "?"))
    if photo.is_burst_reject:
        reasons.append(t("reason_burst"))
    if photo.is_aside:
        reasons.append(t("reason_aside"))
    for attr, key in (("finger_on_lens", "note_finger"), ("eyes_closed", "note_eyes_closed"),
                      ("is_accidental", "note_accidental"), ("is_weak_night", "note_weak_night")):
        if getattr(photo, attr):
            reasons.append(t(key))
    reasons.append(t("reason_scores", technical=photo.technical_score,
                     final=photo.final_score))
    if photo.ai_reviewed:
        reasons.append(t("reason_ai"))
    if photo.quality_issue:
        reasons.append(photo.quality_issue)
    if not selected and not (photo.is_duplicate or photo.is_burst_reject or photo.is_aside
                             or "manual_reject" in photo.flags):
        reasons.append(t("reason_unknown"))
    return reasons
