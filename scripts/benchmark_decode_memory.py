"""Compare full JPEG decode and JPEG draft on a synthetic high-resolution image.

Each strategy runs in a fresh subprocess and retains the same number of scaled
BGR arrays. Peak RSS includes imports and retained arrays. This is a decoder
microbenchmark, not a full analysis of real photos or a HEIC benchmark.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def worker(args) -> None:
    from photobook_curator.utils import load_image, load_image_scaled, resize_max_edge, to_cv_bgr

    arrays = []
    started = perf_counter()
    for _ in range(args.images):
        if args.mode == "full_decode_then_resize":
            image = resize_max_edge(load_image(Path(args.fixture)), args.edge)
        else:
            image = load_image_scaled(Path(args.fixture), args.edge)
        try:
            arrays.append(to_cv_bgr(image))
        finally:
            image.close()
    rss_mib = None
    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mib = round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
    except ImportError:
        pass
    print(json.dumps({
        "seconds": round(perf_counter() - started, 4),
        "process_peak_rss_mib": rss_mib,
        "retained_arrays_mib": round(sum(a.nbytes for a in arrays) / 1024 ** 2, 1),
        "output_shape": list(arrays[0].shape),
    }))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=6000)
    parser.add_argument("--height", type=int, default=4000)
    parser.add_argument("--images", type=int, default=8)
    parser.add_argument("--edge", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--mode", choices=("full_decode_then_resize", "jpeg_draft_then_resize"),
                        help=argparse.SUPPRESS)
    parser.add_argument("--fixture", help=argparse.SUPPRESS)
    parser.add_argument("--make-fixture", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.width, args.height, args.images, args.edge) < 1:
        parser.error("dimensions, images and edge must be positive")
    if args.mode:
        worker(args)
        return
    if args.make_fixture:
        from PIL import Image
        import numpy as np

        # Small random texture enlarged to a large JPEG; no real photographs.
        pixels = np.random.default_rng(args.seed).normal(128, 70, (500, 750))
        image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8)).convert("RGB")
        image = image.resize((args.width, args.height), Image.Resampling.BILINEAR)
        exif = Image.Exif()
        exif[274] = 6  # portrait display; exercise EXIF transpose in both strategies
        image.save(args.fixture, quality=90, exif=exif)
        image.close()
        return

    with tempfile.TemporaryDirectory(prefix="phototool-decode-benchmark-") as temp:
        path = Path(temp) / "synthetic_24mp.jpg"
        # Generate in another process: fixture allocation must not inflate the
        # inherited peak RSS of the measurement subprocesses on POSIX systems.
        subprocess.run([
            sys.executable, str(Path(__file__).resolve()), "--make-fixture",
            "--fixture", str(path), "--width", str(args.width), "--height", str(args.height),
            "--seed", str(args.seed),
        ], check=True)
        results = {}
        for mode in ("full_decode_then_resize", "jpeg_draft_then_resize"):
            result = subprocess.run([
                sys.executable, str(Path(__file__).resolve()), "--mode", mode,
                "--fixture", str(path), "--images", str(args.images), "--edge", str(args.edge),
            ], check=True, capture_output=True, text=True)
            results[mode] = json.loads(result.stdout)
        print(json.dumps({
            "kind": "synthetic_jpeg_decode_only",
            "source_pixels": [args.width, args.height],
            "repeated_decodes_per_strategy": args.images,
            "edge": args.edge,
            "seed": args.seed,
            "strategies": results,
            "excludes": ["HEIC", "analysis", "model_inference", "export"],
        }, indent=2))


if __name__ == "__main__":
    main()
