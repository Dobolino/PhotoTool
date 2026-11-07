"""Reproducible synthetic benchmark; does not read or analyse real photographs.

Run from a development checkout:
    python scripts/benchmark_selection_scale.py --photos 2000

The fixture models 14 travel days, groups of four similar shots and 1024-value
embeddings. Each algorithm receives a fresh photo list. Time excludes fixture
generation and imports. Peak RSS is for the whole process (including fixtures
and imports), not incremental memory attributable to a single stage.
No models, API calls, image decoding, face detection or export are exercised.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

import numpy as np

try:
    import resource
except ImportError:  # Windows: timings still work, RSS is unavailable.
    resource = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photobook_curator.bursts import mark_bursts
from photobook_curator.content_clusters import mark_content_clusters
from photobook_curator.duplicates import mark_duplicates
from photobook_curator.models import Photo


def fixture(count: int, dimensions: int, seed: int, undated: bool = False):
    rng = np.random.default_rng(seed)
    hashes = random.Random(seed)
    base = datetime(2026, 4, 1, 8)
    scene_count = (count + 3) // 4
    scene_hashes = [f"{hashes.getrandbits(64):016x}" for _ in range(scene_count)]
    scene_vectors = rng.normal(size=(scene_count, dimensions)).astype(np.float32)
    scene_vectors /= np.linalg.norm(scene_vectors, axis=1, keepdims=True)
    vectors = {}
    for i in range(count):
        vector = scene_vectors[i // 4] + rng.normal(0, 0.001, dimensions)
        vector = vector.astype(np.float32)
        vectors[i] = vector / np.linalg.norm(vector)

    def photos():
        result = []
        for i in range(count):
            scene = i // 4
            day = min(13, scene * 14 // max(1, scene_count))
            within_day = scene - (day * scene_count + 13) // 14
            result.append(Photo(
                path=Path(f"synthetic/day_{day + 1:02d}/photo_{i:05d}.jpg"),
                filename=f"photo_{i:05d}.jpg",
                datetime_taken=(None if undated else base + timedelta(
                    days=day, minutes=within_day * 8, seconds=(i % 4) * 8)),
                gps_lat=35.68 + day * 0.005,
                gps_lon=139.69 + day * 0.005,
                width=6000,
                height=4000,
                sharpness=300.0 + (i % 4) * 10,
                exposure_mean=120,
                contrast=50,
                saturation=60,
                technical_score=70.0 + i % 4,
                phash=scene_hashes[scene],
            ))
        return result

    return photos, vectors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", type=int, default=2000)
    parser.add_argument("--embedding-dim", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--undated", action="store_true", help="Stress case without capture times")
    args = parser.parse_args()
    if args.photos < 1 or args.embedding_dim < 1:
        parser.error("--photos and --embedding-dim must be positive")
    make_photos, embeddings = fixture(args.photos, args.embedding_dim, args.seed, args.undated)
    results = {}
    for name, operation in (
        ("phash_duplicates_and_bursts", lambda p: mark_duplicates(p, compute_hashes=False)),
        ("bursts", lambda p: mark_bursts(p)),
        ("content_clusters", lambda p: mark_content_clusters(p, embeddings)),
    ):
        photos = make_photos()
        started = perf_counter()
        marked = operation(photos)
        results[name] = {"seconds": round(perf_counter() - started, 4), "marked": marked}
    # Linux reports KiB; macOS reports bytes.
    rss_mib = None
    if resource is not None:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mib = round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
    print(json.dumps({
        "kind": "synthetic_metadata_and_vectors_only",
        "photos": args.photos,
        "embedding_dimensions": args.embedding_dim,
        "seed": args.seed,
        "undated": args.undated,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "algorithms": results,
        "process_peak_rss_mib": rss_mib,
        "excludes": ["image_decode", "quality_scoring", "faces", "model_inference", "export"],
    }, indent=2))


if __name__ == "__main__":
    main()
