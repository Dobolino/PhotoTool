"""Explain stored facts without claiming to know an unrecorded ranking decision."""

from .i18n import t
from .models import Photo
from .audit_report import build_photo_audit


def selection_reasons(photo: Photo, selected: bool | None = None) -> list[str]:
    selected = photo.is_selected if selected is None else selected
    reasons = [t("reason_selected" if selected else "reason_not_selected")]
    audit = build_photo_audit([photo], 0, selected)
    if photo.is_favorite:
        reasons.append(t("reason_favorite"))
    decision = getattr(photo, "manual_decision", "auto")
    if decision in ("keep", "reject"):
        reasons.append(t("reason_manual_keep" if decision == "keep" else "reason_manual_exclude"))
        if getattr(photo, "decision_reason", ""):
            reasons.append(t("reason_decision_note", reason=photo.decision_reason))
    if "manual_add" in photo.flags:
        reasons.append(t("reason_manual_add"))
    if "manual_reject" in photo.flags:
        reasons.append(t("reason_manual_reject"))
    # Actual branch evidence comes before quality hints. A stored mark or low
    # score alone cannot explain why a particular automatic run omitted a photo.
    if audit.automatic_reasons:
        reasons.extend(audit.automatic_reasons)
    elif decision == "auto" and not ("manual_add" in photo.flags or "manual_reject" in photo.flags):
        reasons.extend(audit.primary_reasons)
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
    return list(dict.fromkeys(reasons))
