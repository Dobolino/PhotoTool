"""Kommandozeilen-Interface für das Fotobuch-Kuratierungs-Tool."""

from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import PipelineConfig, run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="photobook-curator",
        description=(
            "Lokales Tool zur Kuratierung eines Urlaubs-Fotobuchs aus einer "
            "iPhone/iCloud-Fotosammlung."
        ),
    )
    p.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        help="Eingabeordner mit Fotos (rekursiv)",
    )
    p.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="Ausgabeordner für CSV, Auswahl und Übersicht",
    )
    p.add_argument(
        "-n",
        "--target-count",
        type=int,
        default=80,
        help="Zielanzahl N ausgewählter Bilder (Standard: 80)",
    )
    p.add_argument(
        "-k",
        "--candidate-factor",
        type=float,
        default=4.0,
        help="Kandidatenfaktor K (Standard: 4)",
    )
    p.add_argument(
        "--geocode",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reverse Geocoding via Nominatim (Standard: an)",
    )
    p.add_argument(
        "--ai-review",
        action="store_true",
        help="KI-gestützte Inhaltsbewertung via Anthropic API aktivieren",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Mit --ai-review: nur Kostenschätzung, kein API-Aufruf",
    )
    p.add_argument(
        "--food-ratio",
        type=float,
        default=0.15,
        help="Maximaler Essens-Anteil pro Region (Standard: 0.15)",
    )
    p.add_argument(
        "--max-landmarks",
        type=int,
        default=3,
        help="Maximale Landmark-Bilder pro Region (Standard: 3)",
    )
    p.add_argument(
        "--min-transit-photos",
        type=int,
        default=3,
        help="Mindestanzahl Bilder für eigenen Transit-Abschnitt (Standard: 3)",
    )
    p.add_argument(
        "--max-transit-quota",
        type=int,
        default=5,
        help="Maximale Bilder pro Transit-Abschnitt (Standard: 5)",
    )
    p.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.92,
        help="Ähnlichkeits-Schwellenwert 0–1 für Diversitätsfilter (Standard: 0.92)",
    )
    p.add_argument(
        "--gps-time-hours",
        type=float,
        default=6.0,
        help="Max. Stunden Abstand für GPS-lose Zuordnung (Standard: 6)",
    )
    p.add_argument(
        "--cluster-eps-meters",
        type=float,
        default=400.0,
        help="DBSCAN-Radius in Metern für feine Cluster (Standard: 400)",
    )
    p.add_argument(
        "--ai-concurrency",
        type=int,
        default=5,
        help="Gleichzeitige AI-Anfragen (Standard: 5)",
    )
    p.add_argument(
        "--faces",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Gesichtserkennung & Gesichtsqualität (Standard: an)",
    )
    p.add_argument(
        "--skip-faces",
        action="store_true",
        help=argparse.SUPPRESS,  # Alias für --no-faces
    )
    p.add_argument(
        "--bursts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Serien/Burst-Erkennung (Standard: an)",
    )
    p.add_argument(
        "--aside-documents",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Screenshots/Dokumente in Optional-Pool (Standard: an)",
    )
    p.add_argument(
        "--finger-filter",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Finger vor der Linse erkennen und aussortieren (Standard: aus)",
    )
    p.add_argument(
        "--accidental-filter",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fehlaufnahmen/Komposition aussortieren (Standard: an)",
    )
    p.add_argument(
        "--weak-night-filter",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Schwache/schwummerige Nachtaufnahmen aussortieren (Standard: an)",
    )
    p.add_argument(
        "--coverage-intensity",
        type=float,
        default=0.0,
        help="Tages-Abdeckung 0.0–1.0 (0=aus, 1=stark gleichmäßig; Standard: 0)",
    )
    p.add_argument(
        "--people-balance-intensity",
        type=float,
        default=0.0,
        help="Personen-Balance 0.0–1.0 (0=aus, 1=stark ausgewogen; Standard: 0)",
    )
    p.add_argument(
        "--map-preview",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Kapitel-Karte (kapitel_karte.html) schreiben (Standard: aus)",
    )
    p.add_argument(
        "--analysis-cache",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="SQLite Feature-Cache zwischen Läufen (Standard: an)",
    )
    p.add_argument(
        "--content-clusters",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Inhalts-ähnliche Motive per Embedding clustern (Standard: an)",
    )
    p.add_argument(
        "--local-aesthetic",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Lokale Ästhetik ohne API (Standard: an; bei --ai-review aus)",
    )
    p.add_argument(
        "--video-frames",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Best-Frame aus Videos/Live Photos extrahieren (Standard: aus)",
    )
    p.add_argument(
        "--timezone-offset-hours",
        type=float,
        default=0.0,
        help="Stunden-Korrektur für EXIF-Zeiten (z. B. 9 bei Kamera auf Heimatzeit)",
    )
    p.add_argument(
        "--burst-seconds",
        type=float,
        default=30.0,
        help="Max. Sekunden Abstand für Serien/Bursts (Standard: 30)",
    )
    p.add_argument(
        "--burst-keep",
        type=int,
        default=2,
        help="Beste Bilder pro Serie behalten (Standard: 2)",
    )
    p.add_argument(
        "--gui",
        action="store_true",
        help="Einfache Fenster-Oberfläche starten",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # GUI braucht keine Pflicht-Args -i/-o
    if argv is None:
        import sys

        raw = sys.argv[1:]
    else:
        raw = list(argv)
    if "--gui" in raw or (len(raw) == 1 and raw[0] == "gui"):
        from .gui import main as gui_main

        return gui_main()

    args = parser.parse_args(argv)

    if not args.input.is_dir():
        parser.error(f"Eingabeordner nicht gefunden: {args.input}")

    cfg = PipelineConfig(
        input_dir=args.input.resolve(),
        output_dir=args.output.resolve(),
        target_n=args.target_count,
        candidate_factor=args.candidate_factor,
        geocode=args.geocode,
        ai_review=args.ai_review,
        dry_run=args.dry_run,
        food_ratio=args.food_ratio,
        max_landmarks=args.max_landmarks,
        min_transit_photos=args.min_transit_photos,
        max_transit_quota=args.max_transit_quota,
        similarity_threshold=args.similarity_threshold,
        gps_time_hours=args.gps_time_hours,
        cluster_eps_meters=args.cluster_eps_meters,
        ai_concurrency=args.ai_concurrency,
        enable_faces=bool(args.faces) and not bool(args.skip_faces),
        enable_bursts=bool(args.bursts),
        enable_document_aside=bool(args.aside_documents),
        enable_finger_filter=bool(args.finger_filter),
        enable_accidental_filter=bool(args.accidental_filter),
        enable_weak_night_filter=bool(args.weak_night_filter),
        coverage_intensity=max(0.0, min(1.0, float(args.coverage_intensity))),
        people_balance_intensity=max(
            0.0, min(1.0, float(args.people_balance_intensity))
        ),
        enable_map_preview=bool(args.map_preview),
        enable_analysis_cache=bool(args.analysis_cache),
        enable_content_clusters=bool(args.content_clusters),
        enable_local_aesthetic=bool(args.local_aesthetic),
        enable_video_frames=bool(args.video_frames),
        timezone_offset_hours=float(args.timezone_offset_hours),
        burst_max_seconds=args.burst_seconds,
        burst_keep=args.burst_keep,
    )
    try:
        result = run_pipeline(cfg)
    except RuntimeError as exc:
        print(f"Fehler: {exc}")
        return 1
    summary = {k: v for k, v in result.items() if k not in ("photo_objects", "plan", "order")}
    print("Fertig:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
