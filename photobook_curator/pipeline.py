"""Orchestriert alle Phasen der Fotobuch-Kuratierung."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .ai_review import ensure_scene_types, run_ai_review
from .analysis_cache import AnalysisCache
from .bursts import mark_bursts
from .content_clusters import mark_content_clusters
from .duplicates import mark_duplicates
from .geocoding import GeocodeCache
from .local_analysis import LocalAnalysisOptions, run_local_analysis
from .map_preview import write_chapter_map
from .models import BookPlan, Photo
from .output import copy_aside_pool, copy_selected, write_csv, write_markdown_overview
from .people_balance import analyze_people_clusters
from .regions import build_location_plan, promote_unassigned_to_region
from .scan import scan_photos
from .selection import build_book_order, mark_candidates
from .transit import detect_transits
from .utils import clear_bgr_cache
from .video_frames import extract_video_stills

# progress(label, fraction) oder progress(label, fraction, step_id)
ProgressCallback = Callable[..., None]
# Rückgabe True => Abbruch gewünscht
CancelCheck = Callable[[], bool]


class PipelineCancelled(Exception):
    """Wird ausgelöst, wenn der Lauf über cancel_check abgebrochen wurde."""


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
    enable_finger_filter: bool = False  # Finger vor der Linse aussortieren
    enable_accidental_filter: bool = True  # Fehlauslösungen / schlechte Komposition
    enable_weak_night_filter: bool = True  # schwummerige Nachtaufnahmen
    enable_content_clusters: bool = True  # Embedding-Ähnlichkeit (Inhalts-Duplikate)
    content_cluster_similarity: float = 0.92
    enable_local_aesthetic: bool = True  # lokale Ästhetik ohne API
    enable_video_frames: bool = False  # Best-Frame aus Videos / Live Photos
    timezone_offset_hours: float = 0.0  # manuelle Zeitkorrektur (Urlaub)
    apply_exif_offset: bool = False  # EXIF OffsetTime → UTC (selten)
    coverage_intensity: float = 0.0  # 0=aus, 1=starke Tages-Abdeckung
    people_balance_intensity: float = 0.0  # 0=aus, 1=starke Personen-Balance
    enable_map_preview: bool = False
    skip_export: bool = False  # GUI: Export nach Kapitel-Vorschau
    enable_analysis_cache: bool = True  # SQLite Feature-Cache zwischen Läufen
    burst_max_seconds: float = 30.0
    burst_keep: int = 2
    burst_min_size: int = 3

    @property
    def skip_faces(self) -> bool:
        return not self.enable_faces


def export_book_outputs(
    photos: list[Photo],
    plan: BookPlan,
    order: list[tuple[int, str, str]],
    output_dir: Path,
    *,
    write_map: bool = False,
) -> dict[str, Any]:
    """Schreibt CSV, selected/, Optional-Pool, Markdown und optional die Karte."""
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(photos, output_dir / "photos_analysis.csv")
    copy_selected(photos, order, output_dir)
    aside_copied = copy_aside_pool(photos, output_dir)
    write_markdown_overview(photos, plan, order, output_dir / "inhaltsverzeichnis.md")
    map_path = None
    if write_map:
        map_path = write_chapter_map(photos, plan, output_dir, order)
    print(f"  CSV: {output_dir / 'photos_analysis.csv'}")
    print(f"  Auswahl: {output_dir / 'selected'}")
    if aside_copied:
        print(f"  Optional-Pool: {output_dir / 'optional_dokumente'} ({aside_copied} Dateien)")
    print(f"  Übersicht: {output_dir / 'inhaltsverzeichnis.md'}")
    if map_path:
        print(f"  Karte: {map_path}")
    return {"aside_copied": aside_copied, "map_path": map_path}


def run_pipeline(
    cfg: PipelineConfig,
    progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    """
    Führt die Kuratierung aus.
    Optional: progress(phase_label, fraction) mit fraction in [0, 1].
    Optional: cancel_check() -> bool; liefert es True, wird an der nächsten
    Phasengrenze mit PipelineCancelled abgebrochen (kein Export).
    """

    def report(label: str, frac: float, step_id: str | None = None) -> None:
        # Abbruch an jeder Phasengrenze prüfen (vor dem nächsten Schritt).
        if cancel_check is not None:
            try:
                cancelled = bool(cancel_check())
            except Exception:
                cancelled = False
            if cancelled:
                raise PipelineCancelled(label)
        if progress is None:
            return
        frac_n = float(max(0.0, min(1.0, frac)))
        try:
            progress(label, frac_n, step_id)
        except TypeError:
            try:
                progress(label, frac_n)
            except Exception:
                pass
        except Exception:
            pass

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cfg.output_dir / "geocode_cache.json"
    analysis_cache = None
    if cfg.enable_analysis_cache:
        analysis_cache = AnalysisCache(cfg.output_dir / "analysis_cache.json")
    clear_bgr_cache()

    report("Einlesen…", 0.02, "scan")
    print("=== Phase 1: Einlesen & technische Vorfilterung ===")
    extra_stills: list[Path] = []
    if cfg.enable_video_frames:
        report("Video-Standbilder…", 0.03, "video")
        stills_dir = cfg.output_dir / "video_stills"
        extra_stills = extract_video_stills(
            cfg.input_dir, stills_dir, enabled=True
        )
        print(f"  Video-/Live-Photo-Standbilder: {len(extra_stills)}")
    photos = scan_photos(
        cfg.input_dir,
        timezone_offset_hours=cfg.timezone_offset_hours,
        apply_exif_offset=cfg.apply_exif_offset,
        extra_paths=extra_stills,
    )
    print(f"  {len(photos)} Bilder gefunden")
    if cfg.timezone_offset_hours:
        print(f"  Zeitzone: +{cfg.timezone_offset_hours:g} h Korrektur")

    # Ein Decode pro Foto für Qualität + Dokumente + pHash + Faces + Finger + …
    report("Lokale Analyse…", 0.08, "quality")
    local = run_local_analysis(
        photos,
        LocalAnalysisOptions(
            enable_documents=cfg.enable_document_aside,
            enable_faces=cfg.enable_faces,
            enable_finger=cfg.enable_finger_filter,
            enable_accidental=cfg.enable_accidental_filter,
            enable_weak_night=cfg.enable_weak_night_filter,
            enable_embeddings=cfg.enable_content_clusters,
            enable_local_aesthetic=cfg.enable_local_aesthetic and not cfg.ai_review,
        ),
        cache=analysis_cache,
        progress=lambda f: report(
            "Lokale Analyse…",
            0.08 + 0.45 * float(max(0.0, min(1.0, f))),
            "quality",
        ),
    )
    for note in local.notes:
        print(f"  {note}")
    print(f"  Decode-Durchläufe: {local.decoded}/{len(photos)} (fusioniert)")

    if cfg.enable_document_aside:
        report("Dokumente…", 0.54, "documents")
        print(f"  {local.aside_count} Screenshots/Dokumente → Optional-Pool (nicht Auto-Kapitel)")
    else:
        print("  Dokumente/Screenshots-Trennung übersprungen")

    report("pHash…", 0.56, "phash")
    report("Duplikate…", 0.58, "duplicates")
    dup_count, burst_from_dup = mark_duplicates(
        photos,
        burst_seconds=cfg.burst_max_seconds if cfg.enable_bursts else 0.0,
        keep_per_burst=cfg.burst_keep if cfg.enable_bursts else 1,
        min_burst_size=cfg.burst_min_size if cfg.enable_bursts else 10**9,
        cache=analysis_cache,
        compute_hashes=False,
    )
    print(f"  {dup_count} Duplikate markiert")

    content_dup = 0
    if cfg.enable_content_clusters and local.embeddings:
        report("Inhalts-Cluster…", 0.60, "content")
        content_dup = mark_content_clusters(
            photos,
            local.embeddings,
            similarity=cfg.content_cluster_similarity,
        )
        print(f"  Inhalts-ähnliche Motive: {content_dup} zusätzlich aussortiert")

    if analysis_cache is not None:
        analysis_cache.save()
        print(f"  Analyse-Cache: {analysis_cache.cache_path}")

    if cfg.enable_faces:
        report("Gesichter…", 0.62, "faces")
        print(f"  Gesichtserkennung: {local.face_backend}")
        print(
            f"  Gesichtsqualität: {local.face_quality_backend} "
            f"({local.closed_eyes} Augen zu, {local.bad_faces} problematisch, "
            f"{local.smiling_hits} Lächeln, {local.looking_hits} Blick zur Kamera)"
        )
    else:
        print("  Gesichtserkennung übersprungen")

    if cfg.enable_finger_filter:
        report("Finger-Check…", 0.64, "finger")
        print(
            f"  Finger vor Linse: {local.finger_backend} "
            f"({local.finger_hits} aussortiert)"
        )
    if cfg.enable_accidental_filter or cfg.enable_weak_night_filter:
        print(
            f"  Fehlaufnahmen: {local.accidental_hits} · "
            f"schwache Nacht: {local.weak_night_hits}"
        )

    if cfg.people_balance_intensity > 0:
        report("Personen-Balance…", 0.66, "people")
        pb_backend = analyze_people_clusters(photos)
        n_clustered = sum(1 for p in photos if p.person_cluster_ids)
        n_people = len({pid for p in photos for pid in p.person_cluster_ids})
        print(
            f"  Personen-Balance: {pb_backend} "
            f"({n_people} Personen-Cluster in {n_clustered} Fotos, "
            f"Stärke {cfg.people_balance_intensity:.0%})"
        )
    if cfg.enable_bursts:
        report("Serien…", 0.68, "bursts")
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
    clear_bgr_cache()  # Analyse-Bilder freigeben vor Geocode/Auswahl

    report("Orte & Regionen…", 0.72, "regions")
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

    report("Transit…", 0.78, "transit")
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

    # Ohne GPS (oder nach Transit übrig): sonst 0 Auswahl trotz analysierter Fotos
    promoted = promote_unassigned_to_region(photos, plan)
    if promoted is not None:
        print(
            f"  {len(promoted.photo_indices)} Fotos ohne Ortszuordnung → "
            f"Kapitel „{promoted.name}“ (Auswahl ohne GPS/KI möglich)"
        )

    report("Kandidaten…", 0.82, "candidates")
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
    report("Szenen / KI…", 0.86, "scenes")
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

    # Checkpoint: Analyse/KI sichern, bevor Auswahl/Export – Absturz kostet dann keine KI erneut
    write_csv(photos, cfg.output_dir / "photos_analysis.csv")
    print(
        f"  Zwischenstand gespeichert: {cfg.output_dir / 'photos_analysis.csv'} "
        "(Analyse/KI – später ohne neuen KI-Lauf fortsetzbar)"
    )

    if cfg.dry_run and cfg.ai_review:
        report("Fertig (Dry-Run)", 1.0, "done")
        return {
            "photos": len(photos),
            "regions": [r.name for r in plan.regions],
            "transits": [t.name for t in plan.transits],
            "candidates": len(candidates),
            "ai": ai_stats,
            "dry_run": True,
        }

    report("Auswahl & Buchstruktur…", 0.90, "selection")
    print("=== Phase 5: Auswahl & Buchstruktur ===")
    print(
        "  Hinweis: Jetzt werden Ähnlichkeiten verglichen. "
        "Bei vielen Fotos / OneDrive kann das mehrere Minuten dauern – "
        "das Programm hängt nicht, auch wenn die GUI kurz stockt."
    )
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
    write_csv(photos, cfg.output_dir / "photos_analysis.csv")
    print("  Auswahl-Zwischenstand in photos_analysis.csv geschrieben")

    map_path = None
    if cfg.enable_map_preview:
        report("Karte…", 0.94, "map")
        map_path = write_chapter_map(photos, plan, cfg.output_dir, order)
        print(f"  Kapitel-Karte: {map_path}")

    exported = False
    report("Ausgabe…", 0.96, "export")
    if cfg.skip_export:
        print("=== Ausgabe zurückgestellt (Kapitel-Vorschau) ===")
        write_csv(photos, cfg.output_dir / "photos_analysis.csv")
        print(f"  CSV: {cfg.output_dir / 'photos_analysis.csv'}")
    else:
        print("=== Ausgabe ===")
        export_book_outputs(
            photos,
            plan,
            order,
            cfg.output_dir,
            write_map=False,  # Karte ggf. schon oben geschrieben
        )
        exported = True

    report("Fertig", 1.0, "done")
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
        "map_path": map_path,
        "exported": exported,
        "enable_map_preview": cfg.enable_map_preview,
    }
