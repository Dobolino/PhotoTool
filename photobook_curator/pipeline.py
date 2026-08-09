"""Orchestriert alle Phasen der Fotobuch-Kuratierung."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .ai_review import ensure_scene_types, run_ai_review
from .bursts import mark_bursts
from .documents import mark_aside_documents
from .duplicates import mark_duplicates
from .face_quality import analyze_face_quality
from .faces import count_faces
from .geocoding import GeocodeCache
from .models import BookPlan, Photo
from .output import copy_aside_pool, copy_selected, write_csv, write_markdown_overview
from .people_balance import analyze_people_clusters
from .quality import analyze_all
from .regions import build_location_plan
from .scan import scan_photos
from .selection import build_book_order, mark_candidates
from .transit import detect_transits


@dataclass
class PipelineConfig:
    input_dir: Path
    output_dir: Path
    target_n: int = 80
    candidate_factor: float = 4.0
    geocode: bool = True
    ai_review: bool = False
    dry_run: bool = False
    food_ratio: float = 0.15
    max_landmarks: int = 3
    min_transit_photos: int = 3
    max_transit_quota: int = 5
    similarity_threshold: float = 0.92
    gps_time_hours: float = 6.0
    cluster_eps_meters: float = 400.0
    ai_concurrency: int = 5
    enable_faces: bool = True
    enable_bursts: bool = True
    enable_document_aside: bool = True
    coverage_intensity: float = 0.0  # 0=aus, 1=starke Tages-Abdeckung
    people_balance_intensity: float = 0.0  # 0=aus, 1=starke Personen-Balance
    burst_max_seconds: float = 30.0
    burst_keep: int = 2
    burst_min_size: int = 3

    @property
    def skip_faces(self) -> bool:
        return not self.enable_faces


def run_pipeline(cfg: PipelineConfig) -> dict[str, Any]:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cfg.output_dir / "geocode_cache.json"

    print("=== Phase 1: Einlesen & technische Vorfilterung ===")
    photos = scan_photos(cfg.input_dir)
    print(f"  {len(photos)} Bilder gefunden")
    analyze_all(photos)
    if cfg.enable_document_aside:
        aside_count = mark_aside_documents(photos)
        print(f"  {aside_count} Screenshots/Dokumente → Optional-Pool (nicht Auto-Kapitel)")
    else:
        print("  Dokumente/Screenshots-Trennung übersprungen")
    dup_count, burst_from_dup = mark_duplicates(
        photos,
        burst_seconds=cfg.burst_max_seconds if cfg.enable_bursts else 0.0,
        keep_per_burst=cfg.burst_keep if cfg.enable_bursts else 1,
        min_burst_size=cfg.burst_min_size if cfg.enable_bursts else 10**9,
    )
    print(f"  {dup_count} Duplikate markiert")
    if cfg.enable_faces:
        backend = count_faces(photos)
        print(f"  Gesichtserkennung: {backend}")
        fq_backend = analyze_face_quality(photos)
        bad = sum(1 for p in photos if p.bad_face)
        closed = sum(1 for p in photos if p.eyes_closed)
        print(f"  Gesichtsqualität: {fq_backend} ({closed} Augen zu, {bad} problematisch)")
    else:
        print("  Gesichtserkennung übersprungen")
    if cfg.people_balance_intensity > 0:
        pb_backend = analyze_people_clusters(photos)
        n_clustered = sum(1 for p in photos if p.person_cluster_ids)
        n_people = len({pid for p in photos for pid in p.person_cluster_ids})
        print(
            f"  Personen-Balance: {pb_backend} "
            f"({n_people} Personen-Cluster in {n_clustered} Fotos, "
            f"Stärke {cfg.people_balance_intensity:.0%})"
        )
    if cfg.enable_bursts:
        burst_extra = mark_bursts(
            photos,
            max_seconds=cfg.burst_max_seconds,
            keep_per_burst=cfg.burst_keep,
            min_burst_size=cfg.burst_min_size,
        )
        burst_rejected = burst_from_dup + burst_extra
        burst_groups = len({p.burst_group_id for p in photos if p.burst_group_id})
        print(
            f"  {burst_groups} Serien erkannt, {burst_rejected} Burst-Bilder aussortiert "
            f"(je max. {cfg.burst_keep} behalten)"
        )
    else:
        print("  Serien/Burst-Erkennung übersprungen")

    print("=== Phase 2: Orte & Regionen ===")
    cache = GeocodeCache(cache_path, enabled=cfg.geocode)
    plan = build_location_plan(
        photos,
        cache,
        eps_meters=cfg.cluster_eps_meters,
        gps_time_hours=cfg.gps_time_hours,
    )
    print(f"  {len(plan.regions)} Regionen: {[r.name for r in plan.regions]}")
    print(f"  {len(plan.unassigned_indices)} unbestimmt")

    print("=== Phase 3: Transit ===")
    detect_transits(
        photos,
        plan,
        min_photos=cfg.min_transit_photos,
        max_transit_quota=cfg.max_transit_quota,
    )
    print(f"  {len(plan.transits)} Transit-Abschnitte")
    for t in plan.transits:
        print(f"    - {t.name} ({len(t.photo_indices)} Fotos, Quota {t.quota})")

    print("=== Kandidatenauswahl ===")
    candidates = mark_candidates(
        photos,
        plan,
        target_n=cfg.target_n,
        candidate_factor=cfg.candidate_factor,
        max_transit_quota=cfg.max_transit_quota,
    )
    print(f"  {len(candidates)} Kandidaten (Faktor {cfg.candidate_factor})")

    ai_stats: dict[str, Any] = {}
    if cfg.ai_review:
        print("=== Phase 4: AI-Review ===")
        ai_stats = run_ai_review(
            photos,
            candidates,
            dry_run=cfg.dry_run,
            concurrency=cfg.ai_concurrency,
        )
    else:
        print("=== Phase 4: AI-Review übersprungen ===")
        ensure_scene_types(photos, candidates)

    if cfg.dry_run and cfg.ai_review:
        # Im Dry-Run nach Kostenschätzung stoppen, trotzdem CSV der bisherigen Analyse schreiben
        write_csv(photos, cfg.output_dir / "photos_analysis.csv")
        return {
            "photos": len(photos),
            "regions": [r.name for r in plan.regions],
            "transits": [t.name for t in plan.transits],
            "candidates": len(candidates),
            "ai": ai_stats,
            "dry_run": True,
        }

    print("=== Phase 5: Auswahl & Buchstruktur ===")
    if cfg.coverage_intensity > 0:
        print(f"  Tages-Abdeckung aktiv (Stärke {cfg.coverage_intensity:.0%})")
    if cfg.people_balance_intensity > 0:
        print(f"  Personen-Balance aktiv (Stärke {cfg.people_balance_intensity:.0%})")
    order = build_book_order(
        photos,
        plan,
        food_ratio=cfg.food_ratio,
        max_landmarks=cfg.max_landmarks,
        similarity_threshold=cfg.similarity_threshold,
        coverage_intensity=cfg.coverage_intensity,
        people_balance_intensity=cfg.people_balance_intensity,
    )
    print(f"  {len(order)} Bilder ausgewählt")

    print("=== Ausgabe ===")
    write_csv(photos, cfg.output_dir / "photos_analysis.csv")
    copy_selected(photos, order, cfg.output_dir)
    aside_copied = copy_aside_pool(photos, cfg.output_dir)
    write_markdown_overview(photos, plan, order, cfg.output_dir / "inhaltsverzeichnis.md")
    print(f"  CSV: {cfg.output_dir / 'photos_analysis.csv'}")
    print(f"  Auswahl: {cfg.output_dir / 'selected'}")
    if aside_copied:
        print(f"  Optional-Pool: {cfg.output_dir / 'optional_dokumente'} ({aside_copied} Dateien)")
    print(f"  Übersicht: {cfg.output_dir / 'inhaltsverzeichnis.md'}")

    return {
        "photos": len(photos),
        "regions": [r.name for r in plan.regions],
        "transits": [t.name for t in plan.transits],
        "selected": len(order),
        "candidates": len(candidates),
        "ai": ai_stats,
        "dry_run": False,
        "photo_objects": photos,
        "plan": plan,
        "order": order,
        "output_dir": cfg.output_dir,
    }
