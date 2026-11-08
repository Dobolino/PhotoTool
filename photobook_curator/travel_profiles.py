"""Reusable starting points for different trips, independent of destinations.

Profiles suggest values, never lock a project. A project stores a copy so future
profile changes cannot silently change an existing album.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TravelProfile:
    id: str
    name_de: str
    name_en: str
    description_de: str
    description_en: str
    settings: dict[str, Any]

    def label(self, language: str = "de") -> str:
        return self.name_en if language == "en" else self.name_de

    def description(self, language: str = "de") -> str:
        return self.description_en if language == "en" else self.description_de


_PROFILES = {
    "balanced": TravelProfile(
        "balanced", "Ausgewogene Reise", "Balanced trip",
        "Ein flexibler Start für jede Reise: Tage ausgewogen berücksichtigen und ähnliche Serien reduzieren.",
        "A flexible starting point: represent travel days and reduce similar bursts.",
        {"target_n": 180, "coverage_intensity": 0.7, "max_per_day": 20,
         "max_per_chapter": 0, "burst_keep": 2, "burst_max_seconds": 30.0,
         "food_ratio": 0.15, "enable_accidental_filter": False,
         "enable_weak_night_filter": False, "people_balance_intensity": 0.0, "storytelling_intensity": 0.5},
    ),
    "city": TravelProfile(
        "city", "Städtereise", "City break",
        "Architektur, Menschen und Street-Fotos mischen; Nachtaufnahmen zunächst nicht pauschal ausschliessen.",
        "Mix architecture, people and street scenes; review night photographs before excluding them.",
        {"target_n": 180, "coverage_intensity": 0.8, "max_per_day": 18,
         "max_per_chapter": 70, "burst_keep": 2, "burst_max_seconds": 30.0,
         "food_ratio": 0.18, "enable_accidental_filter": False,
         "enable_weak_night_filter": False, "people_balance_intensity": 0.2, "storytelling_intensity": 0.6},
    ),
    "beach": TravelProfile(
        "beach", "Strand & Erholung", "Beach and relaxation",
        "Weniger Bilder je Tag, ausgewogene Tagesabdeckung und wenige ähnliche Serienbilder.",
        "Fewer photographs per day, broad day coverage and fewer similar burst frames.",
        {"target_n": 120, "coverage_intensity": 0.9, "max_per_day": 12,
         "max_per_chapter": 50, "burst_keep": 1, "burst_max_seconds": 45.0,
         "food_ratio": 0.10, "enable_accidental_filter": False,
         "enable_weak_night_filter": False, "people_balance_intensity": 0.2, "storytelling_intensity": 0.5},
    ),
    "roadtrip": TravelProfile(
        "roadtrip", "Rundreise & Roadtrip", "Road trip",
        "Mehr Platz für Etappen und Übergänge, ohne einzelne Tage oder Orte dominieren zu lassen.",
        "Allow travel stages and transitions while preventing a single day or place from dominating.",
        {"target_n": 220, "coverage_intensity": 0.8, "max_per_day": 20,
         "max_per_chapter": 60, "burst_keep": 2, "burst_max_seconds": 30.0,
         "food_ratio": 0.12, "max_transit_quota": 8,
         "enable_accidental_filter": False, "enable_weak_night_filter": False,
         "people_balance_intensity": 0.0, "storytelling_intensity": 0.6},
    ),
    "custom": TravelProfile(
        "custom", "Eigene Einstellungen", "Custom settings",
        "Ohne Reisevorlage starten und die Werte individuell anpassen.",
        "Start without a travel preset and adjust values individually.", {},
    ),
}


def get_profile(profile_id: str) -> TravelProfile:
    """Return a fresh settings copy, so callers cannot mutate shared presets."""
    profile = _PROFILES.get(profile_id)
    if profile is None:
        raise ValueError(f"Unbekanntes Reiseprofil: {profile_id}")
    return TravelProfile(profile.id, profile.name_de, profile.name_en,
                         profile.description_de, profile.description_en,
                         dict(profile.settings))


def profile_choices(language: str = "de") -> list[tuple[str, str]]:
    return [(profile.id, profile.label(language)) for profile in _PROFILES.values()]
