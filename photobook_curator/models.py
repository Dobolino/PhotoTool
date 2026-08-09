"""Datenmodelle für Fotos, Regionen, Transit und Buchstruktur."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ChapterType(str, Enum):
    HAUPTTEIL = "Hauptteil"
    ESSEN = "Essen"
    TRANSIT = "Transit"
    UNBESTIMMT = "Unbestimmt"


SCENE_TYPES = (
    "portrait",
    "gruppe",
    "landschaft",
    "sehenswuerdigkeit",
    "essen",
    "transport",
    "detail",
    "alltag",
    "sonstiges",
)


@dataclass
class Photo:
    path: Path
    filename: str
    datetime_taken: Optional[datetime] = None
    camera_model: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    width: int = 0
    height: int = 0

    # Technische Merkmale
    sharpness: float = 0.0
    exposure_mean: float = 0.0
    is_too_dark: bool = False
    is_overexposed: bool = False
    contrast: float = 0.0
    saturation: float = 0.0
    is_screenshot: bool = False
    is_aside: bool = False  # Screenshot/Dokument – optional, nicht Auto-Kapitel
    aside_type: Optional[str] = None  # screenshot|dokument|karte|ticket
    is_duplicate: bool = False
    is_burst_reject: bool = False
    burst_group_id: Optional[int] = None
    duplicate_of: Optional[str] = None
    face_count: int = 0
    eyes_closed: bool = False
    face_cut_off: bool = False
    face_too_small: bool = False
    bad_face: bool = False
    person_cluster_ids: list[int] = field(default_factory=list)
    technical_score: float = 0.0
    phash: Optional[str] = None

    # Orte / Regionen
    fine_cluster_id: Optional[int] = None
    region: Optional[str] = None
    country: Optional[str] = None
    place_label: Optional[str] = None
    assigned_by_time: bool = False

    # KI
    aesthetic_score: Optional[float] = None
    landmark: Optional[str] = None
    scene_type: Optional[str] = None
    mood: Optional[str] = None
    quality_issue: Optional[str] = None
    keep_recommendation: Optional[bool] = None
    ai_reviewed: bool = False

    # Auswahl
    final_score: float = 0.0
    is_candidate: bool = False
    is_selected: bool = False
    chapter_type: Optional[str] = None
    book_position: Optional[int] = None
    chapter_folder: Optional[str] = None

    flags: list[str] = field(default_factory=list)

    def add_flag(self, flag: str) -> None:
        if flag not in self.flags:
            self.flags.append(flag)

    @property
    def has_gps(self) -> bool:
        return self.gps_lat is not None and self.gps_lon is not None

    def to_csv_row(self) -> dict[str, Any]:
        date_str = self.datetime_taken.strftime("%Y-%m-%d") if self.datetime_taken else ""
        time_str = self.datetime_taken.strftime("%H:%M:%S") if self.datetime_taken else ""
        return {
            "filename": self.filename,
            "path": str(self.path),
            "date": date_str,
            "time": time_str,
            "region": self.region or "",
            "chapter_type": self.chapter_type or "",
            "scene_type": self.scene_type or "",
            "mood": self.mood or "",
            "camera_model": self.camera_model or "",
            "gps_lat": self.gps_lat if self.gps_lat is not None else "",
            "gps_lon": self.gps_lon if self.gps_lon is not None else "",
            "width": self.width,
            "height": self.height,
            "sharpness": round(self.sharpness, 2),
            "exposure_mean": round(self.exposure_mean, 2),
            "contrast": round(self.contrast, 2),
            "saturation": round(self.saturation, 2),
            "face_count": self.face_count,
            "eyes_closed": self.eyes_closed,
            "face_cut_off": self.face_cut_off,
            "face_too_small": self.face_too_small,
            "bad_face": self.bad_face,
            "person_cluster_ids": "|".join(str(x) for x in self.person_cluster_ids),
            "technical_score": round(self.technical_score, 2),
            "aesthetic_score": self.aesthetic_score if self.aesthetic_score is not None else "",
            "landmark": self.landmark or "",
            "quality_issue": self.quality_issue or "",
            "keep_recommendation": (
                self.keep_recommendation if self.keep_recommendation is not None else ""
            ),
            "final_score": round(self.final_score, 2),
            "flags": "|".join(self.flags),
            "is_candidate": self.is_candidate,
            "is_selected": self.is_selected,
            "book_position": self.book_position if self.book_position is not None else "",
            "chapter_folder": self.chapter_folder or "",
            "is_duplicate": self.is_duplicate,
            "is_burst_reject": self.is_burst_reject,
            "burst_group_id": self.burst_group_id if self.burst_group_id is not None else "",
            "is_screenshot": self.is_screenshot,
            "is_aside": self.is_aside,
            "aside_type": self.aside_type or "",
            "assigned_by_time": self.assigned_by_time,
            "fine_cluster_id": (
                self.fine_cluster_id if self.fine_cluster_id is not None else ""
            ),
        }


@dataclass
class FineCluster:
    cluster_id: int
    lat: float
    lon: float
    city: Optional[str] = None
    region_admin: Optional[str] = None
    country: Optional[str] = None
    photo_indices: list[int] = field(default_factory=list)


@dataclass
class Region:
    name: str
    country: Optional[str] = None
    photo_indices: list[int] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    day_count: int = 1
    quota: int = 0
    chapter_index: int = 0


@dataclass
class TransitSection:
    from_region: str
    to_region: str
    photo_indices: list[int] = field(default_factory=list)
    quota: int = 0
    chapter_index: int = 0  # index after which this transit sits (0-based region)

    @property
    def name(self) -> str:
        return f"Von {self.from_region} nach {self.to_region}"


@dataclass
class BookPlan:
    regions: list[Region] = field(default_factory=list)
    transits: list[TransitSection] = field(default_factory=list)
    unassigned_indices: list[int] = field(default_factory=list)
