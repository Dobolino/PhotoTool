"""Lokale Analyse in einem Decode-Durchlauf (Qualität, Dokumente, pHash, Faces, …)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from tqdm import tqdm

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

ProgressFrac = Callable[[float], None]


@dataclass
class LocalAnalysisOptions:
    enable_documents: bool = True
    enable_faces: bool = True
    enable_finger: bool = False


@dataclass
class LocalAnalysisResult:
    cache_hits: int = 0
    decoded: int = 0
    aside_count: int = 0
    face_backend: str = "skipped"
    face_quality_backend: str = "skipped"
    finger_backend: str = "skipped"
    closed_eyes: int = 0
    bad_faces: int = 0
    finger_hits: int = 0
    notes: list[str] = field(default_factory=list)


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


def run_local_analysis(
    photos: list[Photo],
    options: LocalAnalysisOptions,
    cache: Optional["AnalysisCache"] = None,
    progress: ProgressFrac | None = None,
) -> LocalAnalysisResult:
    """
    Pro Foto höchstens ein BGR-Decode für Qualität + Dokumente + pHash + Faces + Finger.
    People-Clustering bleibt separat (braucht globale Vergleiche).
    """
    from .analysis_cache import apply_quality_payload, quality_payload

    result = LocalAnalysisResult()
    face_counter: FaceCounter | None = None
    face_quality: FaceQualityAnalyzer | None = None
    finger: FingerObstructionAnalyzer | None = None

    if options.enable_faces:
        face_counter = FaceCounter()
        face_quality = FaceQualityAnalyzer()
        result.face_backend = face_counter.backend
        result.face_quality_backend = face_quality.backend
    if options.enable_finger:
        finger = FingerObstructionAnalyzer()
        result.finger_backend = finger.backend

    n = max(1, len(photos))
    try:
        for i, photo in enumerate(tqdm(photos, desc="Lokale Analyse", unit="img")):
            if progress is not None and (i % 25 == 0 or i + 1 == len(photos)):
                try:
                    progress(i / n)
                except Exception:
                    pass

            cached = cache.get(photo.path) if cache is not None else None
            quality_hit = bool(cached and "sharpness" in cached)
            if quality_hit:
                apply_quality_payload(photo, cached)  # type: ignore[arg-type]
                result.cache_hits += 1

            need_docs_pixels = options.enable_documents and _docs_need_pixels(photo)
            need_phash = not photo.phash
            need_faces = options.enable_faces
            need_finger = options.enable_finger and not getattr(photo, "is_aside", False)
            need_quality = not quality_hit
            need_bgr = (
                need_quality
                or need_phash
                or need_docs_pixels
                or need_faces
                or need_finger
            )

            scored = False
            bgr = None
            if need_bgr:
                try:
                    bgr = load_bgr_cached(photo.path)
                    result.decoded += 1
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
                    continue

            if need_quality and bgr is not None:
                analyze_image_quality_from_bgr(photo, bgr)

            if options.enable_documents:
                is_aside, aside_type = classify_document_image(photo, bgr)
                if is_aside:
                    _apply_aside(photo, aside_type)
                    result.aside_count += 1
                    need_finger = False  # Aside: kein Finger-Check

            if need_phash and bgr is not None and not photo.phash:
                value = phash_hex_from_bgr(bgr)
                if value is None:
                    photo.phash = None
                    photo.add_flag("phash_failed")
                else:
                    photo.phash = value

            if need_faces and face_counter is not None and bgr is not None:
                try:
                    photo.face_count = face_counter.count(bgr)
                except Exception:
                    photo.face_count = 0
                    photo.add_flag("face_failed")

                if (
                    face_quality is not None
                    and photo.face_count > 0
                    and "unreadable" not in photo.flags
                ):
                    try:
                        fq = face_quality.analyze_bgr(bgr)
                        if fq.face_count > 0:
                            apply_face_quality(photo, fq)
                            scored = True
                            if photo.eyes_closed:
                                result.closed_eyes += 1
                            if photo.bad_face:
                                result.bad_faces += 1
                    except Exception:
                        photo.add_flag("face_quality_failed")

            if not scored:
                compute_technical_score(photo)

            if (
                need_finger
                and finger is not None
                and bgr is not None
                and not getattr(photo, "is_aside", False)
                and "unreadable" not in photo.flags
            ):
                try:
                    detected, ratio = finger.analyze_bgr(bgr)
                    apply_finger_obstruction(photo, detected, ratio)
                    if detected:
                        result.finger_hits += 1
                    else:
                        photo.finger_on_lens = False
                except Exception:
                    photo.finger_on_lens = False

            if cache is not None and "unreadable" not in photo.flags:
                cache.put(photo.path, quality_payload(photo))
    finally:
        if face_counter is not None:
            face_counter.close()
        if face_quality is not None:
            face_quality.close()
        if finger is not None:
            finger.close()

    if result.cache_hits:
        result.notes.append(
            f"Analyse-Cache: {result.cache_hits}/{len(photos)} Treffer"
        )
    return result
