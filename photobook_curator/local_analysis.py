"""Lokale Analyse in einem Decode-Durchlauf (Qualität, Dokumente, pHash, Faces, …)."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

import numpy as np
from tqdm import tqdm

from .composition import analyze_composition_bgr
from .documents import (
    _filename_hint,
    _looks_like_phone_ui,
    classify_document_image,
)
from .duplicates import phash_hex_from_bgr
from .face_quality import FaceQualityAnalyzer, apply_face_quality
from .faces import FaceCounter
from .finger_obstruction import FingerObstructionAnalyzer, apply_finger_obstruction
from .models import Photo
from .quality import (
    analyze_image_quality_from_bgr,
    compute_technical_score,
)
from .utils import load_bgr_cached

if TYPE_CHECKING:
    from .analysis_cache import AnalysisCache

# Ändern, wenn Decoder/Metriken oder Modelle inkompatibel geändert werden.
_QUALITY_RECIPE = "scaled-jpeg-v1"
_FACE_FLAGS = {
    "eyes_closed", "face_cut_off", "face_too_small", "bad_face", "no_smile", "looking_away"
}
ProgressFrac = Callable[[float], None]


@dataclass
class LocalAnalysisOptions:
    enable_documents: bool = True
    enable_faces: bool = True
    enable_finger: bool = False
    enable_accidental: bool = True
    enable_weak_night: bool = True
    enable_embeddings: bool = False
    enable_local_aesthetic: bool = False
    workers: int | None = None  # None = auto (1–4)


@dataclass
class LocalAnalysisResult:
    cache_hits: int = 0
    decoded: int = 0
    aside_count: int = 0
    face_backend: str = "skipped"
    face_quality_backend: str = "skipped"
    finger_backend: str = "skipped"
    embed_backend: str = "skipped"
    workers: int = 1
    closed_eyes: int = 0
    bad_faces: int = 0
    finger_hits: int = 0
    accidental_hits: int = 0
    weak_night_hits: int = 0
    smiling_hits: int = 0
    looking_hits: int = 0
    embeddings: dict[int, np.ndarray] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class _PhotoStats:
    cache_hit: bool = False
    decoded: bool = False
    aside: bool = False
    closed_eyes: bool = False
    bad_face: bool = False
    finger: bool = False
    accidental: bool = False
    weak_night: bool = False
    smiling: bool = False
    looking: bool = False
    embedding: np.ndarray | None = None


def _docs_need_pixels(photo: Photo) -> bool:
    return not (
        photo.is_screenshot
        or _filename_hint(photo)
        or _looks_like_phone_ui(photo.width, photo.height, photo.camera_model)
    )


def _apply_aside(photo: Photo, aside_type: str | None) -> None:
    photo.is_aside = True
    photo.aside_type = aside_type or "dokument"
    photo.add_flag("aside")
    photo.add_flag(f"aside_{photo.aside_type}")
    photo.region = "Optional"
    if photo.is_screenshot and "screenshot" not in photo.flags:
        photo.add_flag("screenshot")


def _resolve_workers(options: LocalAnalysisOptions, n_photos: int) -> int:
    if options.workers is not None:
        return max(1, int(options.workers))
    if n_photos < 8:
        return 1
    cpu = os.cpu_count() or 2
    return max(1, min(4, cpu // 2 if cpu > 2 else 2))


class _AnalyzerBundle:
    """Pro Worker-Thread eigene Analyzer (MediaPipe oft nicht thread-safe)."""

    def __init__(self, options: LocalAnalysisOptions) -> None:
        self.face_counter: FaceCounter | None = None
        self.face_quality: FaceQualityAnalyzer | None = None
        self.finger: FingerObstructionAnalyzer | None = None
        self.embedder = None
        self.face_backend = "skipped"
        self.face_quality_backend = "skipped"
        self.finger_backend = "skipped"
        self.embed_backend = "skipped"
        if options.enable_faces:
            self.face_counter = FaceCounter()
            self.face_quality = FaceQualityAnalyzer()
            self.face_backend = self.face_counter.backend
            self.face_quality_backend = self.face_quality.backend
        if options.enable_finger:
            self.finger = FingerObstructionAnalyzer()
            self.finger_backend = self.finger.backend
        if options.enable_embeddings:
            from .embeddings import ImageEmbedder

            self.embedder = ImageEmbedder()
            self.embed_backend = self.embedder.backend

    def close(self) -> None:
        for obj in (self.face_counter, self.face_quality, self.finger, self.embedder):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass


_thread_local = threading.local()


def _analyze_one(
    index: int,
    photo: Photo,
    options: LocalAnalysisOptions,
    cache: Optional["AnalysisCache"],
    bundle: _AnalyzerBundle,
) -> _PhotoStats:
    from .analysis_cache import apply_quality_payload, quality_payload

    stats = _PhotoStats()
    cached = cache.get(photo.path) if cache is not None else None
    quality_hit = bool(cached and cached.get("_quality_recipe") == _QUALITY_RECIPE)
    face_recipe = [bundle.face_backend, bundle.face_quality_backend]
    composition_recipe = [
        options.enable_accidental,
        options.enable_weak_night,
        face_recipe if options.enable_faces else None,
    ]
    faces_hit = bool(
        quality_hit and options.enable_faces and cached.get("_faces_recipe") == face_recipe
    )
    composition_hit = bool(
        quality_hit and cached.get("_composition_recipe") == composition_recipe
    )
    aesthetic_hit = bool(
        quality_hit and cached.get("_local_aesthetic") and cached.get("aesthetic_score") is not None
    )
    if quality_hit:
        # Defaults in einem Payload bedeuten nicht, dass ein optionaler Analyzer
        # bereits lief. Nur Ergebnisse derselben aktivierten Stufe übernehmen.
        apply_quality_payload(photo, cached)
        stats.cache_hit = True
    if not faces_hit:
        photo.face_count = 0
        photo.eyes_closed = photo.face_cut_off = photo.face_too_small = photo.bad_face = False
        photo.smiling = photo.looking_at_camera = None
        photo.flags = [f for f in photo.flags if f not in _FACE_FLAGS]
    if not composition_hit or not options.enable_accidental:
        photo.is_accidental = False
        photo.flags = [f for f in photo.flags if f not in {"accidental", "accidental_shot"}]
    if not composition_hit or not options.enable_weak_night:
        photo.is_weak_night = False
        photo.flags = [f for f in photo.flags if f != "weak_night"]
    if not options.enable_local_aesthetic and not photo.ai_reviewed:
        photo.aesthetic_score = None
    stats.smiling = photo.smiling is True
    stats.looking = photo.looking_at_camera is True
    stats.accidental = bool(photo.is_accidental)
    stats.weak_night = bool(photo.is_weak_night)
    stats.closed_eyes = bool(photo.eyes_closed)
    stats.bad_face = bool(photo.bad_face)
    faces_done = faces_hit
    composition_done = composition_hit

    docs_hit = bool(quality_hit and cached and "_document_result" in cached)
    if options.enable_documents and docs_hit and cached["_document_result"][0]:
        _apply_aside(photo, cached["_document_result"][1])
        stats.aside = True
    need_docs_pixels = options.enable_documents and not docs_hit and _docs_need_pixels(photo)
    need_phash = not photo.phash
    need_faces = options.enable_faces and not faces_hit
    need_finger = options.enable_finger and not getattr(photo, "is_aside", False)
    need_composition = (
        (options.enable_accidental or options.enable_weak_night)
        and not composition_hit
        and not getattr(photo, "is_aside", False)
    )
    need_quality = not quality_hit
    need_aesthetic = options.enable_local_aesthetic and not aesthetic_hit
    need_embed = options.enable_embeddings and bundle.embed_backend == "mediapipe" and not photo.is_aside
    if need_embed and cache is not None and cached and cached.get("_embedding_recipe") == "mediapipe-v1":
        cached_emb = cache.get_embedding(photo.path)
        if cached_emb is not None:
            stats.embedding = cached_emb
            need_embed = False

    need_bgr = (
        need_quality
        or need_phash
        or need_docs_pixels
        or need_faces
        or need_finger
        or need_composition
        or need_aesthetic
        or need_embed
    )

    scored = False
    bgr = None
    if need_bgr:
        try:
            bgr = load_bgr_cached(photo.path)
            stats.decoded = True
        except Exception:
            if need_quality:
                photo.add_flag("unreadable")
                photo.technical_score = 0.0
            if need_phash:
                photo.phash = None
                photo.add_flag("phash_failed")
            if need_faces:
                photo.face_count = 0
                photo.add_flag("face_failed")
            compute_technical_score(photo)
            return stats

    if need_quality and bgr is not None:
        analyze_image_quality_from_bgr(photo, bgr)

    if options.enable_documents and not docs_hit:
        is_aside, aside_type = classify_document_image(photo, bgr)
        if is_aside:
            _apply_aside(photo, aside_type)
            stats.aside = True
            need_finger = False
            need_composition = False
            need_embed = False

    if need_phash and bgr is not None and not photo.phash:
        value = phash_hex_from_bgr(bgr)
        if value is None:
            photo.phash = None
            photo.add_flag("phash_failed")
        else:
            photo.phash = value

    if need_faces and bundle.face_counter is not None and bgr is not None:
        try:
            photo.face_count = bundle.face_counter.count(bgr)
            faces_done = True
        except Exception:
            photo.face_count = 0
            photo.add_flag("face_failed")

        if (
            bundle.face_quality is not None
            and photo.face_count > 0
            and "unreadable" not in photo.flags
        ):
            try:
                fq = bundle.face_quality.analyze_bgr(bgr)
                if fq.face_count > 0:
                    apply_face_quality(photo, fq)
                    scored = True
                    stats.closed_eyes = bool(photo.eyes_closed)
                    stats.bad_face = bool(photo.bad_face)
                    stats.smiling = photo.smiling is True
                    stats.looking = photo.looking_at_camera is True
            except Exception:
                photo.add_flag("face_quality_failed")
                faces_done = False
        elif photo.face_count == 0:
            photo.smiling = None
            photo.looking_at_camera = None

    if need_composition and bgr is not None and not getattr(photo, "is_aside", False):
        try:
            was_acc = bool(getattr(photo, "is_accidental", False))
            was_night = bool(getattr(photo, "is_weak_night", False))
            comp = analyze_composition_bgr(
                photo,
                bgr,
                enable_accidental=options.enable_accidental,
                enable_weak_night=options.enable_weak_night,
            )
            composition_done = True
            if comp.is_accidental and not was_acc:
                stats.accidental = True
            if comp.is_weak_night and not was_night:
                stats.weak_night = True
        except Exception:
            pass

    if need_aesthetic and not getattr(photo, "is_aside", False):
        try:
            from .local_aesthetic import apply_local_aesthetic

            apply_local_aesthetic(photo, bgr)
        except Exception:
            pass

    if need_embed and bundle.embedder is not None and bgr is not None:
        try:
            stats.embedding = bundle.embedder.embed_bgr(bgr, allow_fallback=False)
        except Exception:
            pass

    if not scored:
        compute_technical_score(photo)
    elif getattr(photo, "is_accidental", False) or getattr(photo, "is_weak_night", False):
        compute_technical_score(photo)

    if (
        need_finger
        and bundle.finger is not None
        and bgr is not None
        and not getattr(photo, "is_aside", False)
        and "unreadable" not in photo.flags
    ):
        try:
            detected, ratio = bundle.finger.analyze_bgr(bgr)
            apply_finger_obstruction(photo, detected, ratio)
            stats.finger = bool(detected)
            if not detected:
                photo.finger_on_lens = False
        except Exception:
            photo.finger_on_lens = False

    if cache is not None and "unreadable" not in photo.flags:
        payload = quality_payload(photo)
        payload["_quality_recipe"] = _QUALITY_RECIPE
        if options.enable_documents:
            payload["_document_result"] = [photo.is_aside, photo.aside_type]
        if faces_done and options.enable_faces:
            payload["_faces_recipe"] = face_recipe
        if composition_done and (not options.enable_faces or faces_done):
            payload["_composition_recipe"] = composition_recipe
        payload["_local_aesthetic"] = bool(options.enable_local_aesthetic and photo.aesthetic_score is not None)
        if stats.embedding is not None:
            payload["_embedding_recipe"] = "mediapipe-v1"
        cache.put(photo.path, payload, embedding=stats.embedding)

    return stats


def _merge_stats(result: LocalAnalysisResult, index: int, stats: _PhotoStats) -> None:
    if stats.cache_hit:
        result.cache_hits += 1
    if stats.decoded:
        result.decoded += 1
    if stats.aside:
        result.aside_count += 1
    if stats.closed_eyes:
        result.closed_eyes += 1
    if stats.bad_face:
        result.bad_faces += 1
    if stats.finger:
        result.finger_hits += 1
    if stats.accidental:
        result.accidental_hits += 1
    if stats.weak_night:
        result.weak_night_hits += 1
    if stats.smiling:
        result.smiling_hits += 1
    if stats.looking:
        result.looking_hits += 1
    if stats.embedding is not None:
        result.embeddings[index] = stats.embedding


def run_local_analysis(
    photos: list[Photo],
    options: LocalAnalysisOptions,
    cache: Optional["AnalysisCache"] = None,
    progress: ProgressFrac | None = None,
) -> LocalAnalysisResult:
    """
    Pro Foto höchstens ein BGR-Decode für Qualität + Dokumente + pHash + Faces + Finger
    + Embedding + lokale Ästhetik.
    Bei mehreren Workern: ThreadPool + Analyzer pro Thread.
    """
    result = LocalAnalysisResult()
    n = max(1, len(photos))
    workers = _resolve_workers(options, len(photos))
    result.workers = workers

    # Probe-Backend für Log (ein Bundle im Hauptthread)
    probe = _AnalyzerBundle(options)
    result.face_backend = probe.face_backend
    result.face_quality_backend = probe.face_quality_backend
    result.finger_backend = probe.finger_backend
    result.embed_backend = probe.embed_backend

    bundles_created: list[_AnalyzerBundle] = []
    done = 0
    done_lock = threading.Lock()

    def _report() -> None:
        if cache is not None:
            cache.save()
        if progress is None:
            return
        # Der Pipeline-Callback prüft hier auch den Benutzer-Abbruch. Diesen
        # nicht verschlucken; der finally-Block sichert Cache und Analyzer.
        progress(done / n)

    try:
        if workers <= 1:
            for i, photo in enumerate(tqdm(photos, desc="Lokale Analyse", unit="img")):
                stats = _analyze_one(i, photo, options, cache, probe)
                _merge_stats(result, i, stats)
                done = i + 1
                if i % 25 == 0 or i + 1 == len(photos):
                    _report()
        else:
            # Probe bleibt Worker-0-ähnlich; weitere Threads bauen eigene Bundles
            probe.close()
            probe = None  # type: ignore[assignment]
            bundles_lock = threading.Lock()

            def _worker(item: tuple[int, Photo]) -> tuple[int, _PhotoStats]:
                idx, photo = item
                bundle = getattr(_thread_local, "bundle", None)
                if bundle is None:
                    bundle = _AnalyzerBundle(options)
                    _thread_local.bundle = bundle
                    with bundles_lock:
                        bundles_created.append(bundle)
                return idx, _analyze_one(idx, photo, options, cache, bundle)

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_worker, (i, photo)) for i, photo in enumerate(photos)
                ]
                try:
                    with tqdm(total=len(photos), desc="Lokale Analyse", unit="img") as bar:
                        for fut in as_completed(futures):
                            idx, stats = fut.result()
                            _merge_stats(result, idx, stats)
                            with done_lock:
                                done += 1
                                cur = done
                            bar.update(1)
                            if cur % 25 == 0 or cur == len(photos):
                                _report()
                except BaseException:
                    # Executor.__exit__ wartet sonst auf die gesamte Warteschlange.
                    # Nur die höchstens `workers` laufenden Bilder fertigstellen.
                    for fut in futures:
                        fut.cancel()
                    raise

            # Backends vom ersten Bundle übernehmen
            if bundles_created:
                b0 = bundles_created[0]
                result.face_backend = b0.face_backend
                result.face_quality_backend = b0.face_quality_backend
                result.finger_backend = b0.finger_backend
                result.embed_backend = b0.embed_backend
    finally:
        for b in bundles_created:
            b.close()
        if probe is not None:
            probe.close()
        if cache is not None:
            cache.save()
        # Thread-Locals gehören den beendeten Executor-Threads.

    if result.cache_hits:
        result.notes.append(
            f"Analyse-Cache: {result.cache_hits}/{len(photos)} Treffer"
        )
    if workers > 1:
        result.notes.append(f"Parallel: {workers} Worker")
    if options.enable_embeddings:
        result.notes.append(
            f"Embeddings: {result.embed_backend} ({len(result.embeddings)} Vektoren)"
        )
    if options.enable_embeddings and result.embed_backend != "mediapipe":
        result.notes.append("Inhalts-Cluster übersprungen: kein semantisches Modell verfügbar; pHash/Serien bleiben aktiv")
    if options.enable_local_aesthetic:
        n_aes = sum(
            1 for p in photos if p.aesthetic_score is not None and not p.ai_reviewed
        )
        result.notes.append(f"Lokale Ästhetik: {n_aes} bewertet")
    return result
