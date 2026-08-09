"""Stabile Analyse-Schritte für Fortschritts-Anzeige in der GUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class PhaseStep:
    id: str
    label: str
    """Wenn gesetzt: Schritt nur anzeigen/ausführen, wenn Config dieses Flag wahr ist."""
    require_attr: Optional[str] = None
    """Wenn gesetzt: Schritt nur wenn float-Attribut > 0."""
    require_positive: Optional[str] = None


# Reihenfolge = Ablauf in run_pipeline
PHASE_STEPS: tuple[PhaseStep, ...] = (
    PhaseStep("scan", "Einlesen"),
    PhaseStep("quality", "Technik"),
    PhaseStep("documents", "Dokumente", require_attr="enable_document_aside"),
    PhaseStep("phash", "pHash"),
    PhaseStep("duplicates", "Duplikate"),
    PhaseStep("faces", "Gesichter", require_attr="enable_faces"),
    PhaseStep("finger", "Finger", require_attr="enable_finger_filter"),
    PhaseStep("people", "Personen", require_positive="people_balance_intensity"),
    PhaseStep("bursts", "Serien", require_attr="enable_bursts"),
    PhaseStep("regions", "Orte"),
    PhaseStep("transit", "Transit"),
    PhaseStep("candidates", "Kandidaten"),
    PhaseStep("scenes", "Szenen/KI"),
    PhaseStep("selection", "Auswahl"),
    PhaseStep("map", "Karte", require_attr="enable_map_preview"),
    PhaseStep("export", "Ausgabe"),
)

PHASE_BY_ID = {s.id: s for s in PHASE_STEPS}


def step_enabled(step: PhaseStep, cfg: Any) -> bool:
    if step.require_attr is not None:
        return bool(getattr(cfg, step.require_attr, False))
    if step.require_positive is not None:
        try:
            return float(getattr(cfg, step.require_positive, 0) or 0) > 0
        except (TypeError, ValueError):
            return False
    return True


def steps_for_config(cfg: Any) -> list[PhaseStep]:
    """Schritte in Lauf-Reihenfolge inkl. optionaler (GUI blendet Skip sichtbar)."""
    return list(PHASE_STEPS)


def initial_phase_status(cfg: Any) -> dict[str, str]:
    """pending | skipped für alle bekannten Schritte."""
    status: dict[str, str] = {}
    for step in PHASE_STEPS:
        status[step.id] = "pending" if step_enabled(step, cfg) else "skipped"
    return status


def match_step_id(label: str) -> Optional[str]:
    """Fallback: Label → step_id, falls Callback kein step_id liefert."""
    low = (label or "").lower()
    mapping = (
        ("einlesen", "scan"),
        ("technische", "quality"),
        ("dokument", "documents"),
        ("phash", "phash"),
        ("duplikat", "duplicates"),
        ("gesicht", "faces"),
        ("finger", "finger"),
        ("personen", "people"),
        ("serie", "bursts"),
        ("burst", "bursts"),
        ("ort", "regions"),
        ("region", "regions"),
        ("transit", "transit"),
        ("kandidat", "candidates"),
        ("szene", "scenes"),
        ("ki", "scenes"),
        ("auswahl", "selection"),
        ("buchstruktur", "selection"),
        ("karte", "map"),
        ("ausgabe", "export"),
        ("fertig", "done"),
    )
    for needle, sid in mapping:
        if needle in low:
            return sid
    return None
