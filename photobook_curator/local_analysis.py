"""Lokale Analyse in einem Decode-Durchlauf (Qualität, Dokumente, pHash, Faces, …)."""

from __future__ import annotations

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


@dataclass
class LocalAnalysisResult:
    cache_hits: int = 0
    decoded: int = 0
    aside_count: int = 0
    face_backend: str = "skipped"
    face_quality_backend: str = "skipped"
    finger_backend: str = "skipped"
    embed_backend: str = "skipped"
    closed_eyes: int = 0
    bad_faces: int = 0
    finger_hits: int = 0
    accidental_hits: int = 0
    weak_night_hits: int = 0
    smiling_hits: int = 0
    looking_hits: int = 0
    embeddings: dict[int, np.ndarray] = field(default_factory=dict)
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
    Pro Foto höchstens ein BGR-Decode für Qualität + Dokumente + pHash + Faces + Finger
    + Embedding + lokale Ästhetik.
    People-Clustering bleibt separat (braucht globale Vergleiche).
    """
    from .analysis_cache import apply_quality_payload, quality_payload

    result = LocalAnalysisResult()
    face_counter: FaceCounter | None = None
    face_quality: FaceQualityAnalyzer | None = None
    finger: FingerObstructionAnalyzer | None = None
    embedder = None

    if options.enable_faces:
        face_counter = FaceCounter()
        face_quality = FaceQualityAnalyzer()
        result.face_backend = face_counter.backend
        result.face_quality_backend = face_quality.backend
    if options.enable_finger:
        finger = FingerObstructionAnalyzer()
        result.finger_backend = finger.backend
    if options.enable_embeddings:
        from .embeddings import ImageEmbedder

        embedder = ImageEmbedder()
        result.embed_backend = embedder.backend

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
            # Neuere Caches enthalten smiling-Key (auch None) → Faces nicht erneut
            faces_hit = bool(quality_hit and cached is not None and "smiling" in cached)
            composition_hit = bool(
                quality_hit and cached is not None and "is_accidental" in cached
            )
            aesthetic_hit = bool(
                quality_hit
                and cached is not None
                and cached.get("aesthetic_score") is not None
            )
            if quality_hit:
                apply_quality_payload(photo, cached)  # type: ignore[arg-type]
                result.cache_hits += 1
                if photo.smiling is True:
                    result.smiling_hits += 1
                if photo.looking_at_camera is True:
                    result.looking_hits += 1
                if photo.is_accidental:
                    result.accidental_hits += 1
                if photo.is_weak_night:
                    result.weak_night_hits += 1

            need_docs_pixels = options.enable_documents and _docs_need_pixels(photo)
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
            need_embed = False
            cached_emb = None
            if options.enable_embeddings and cache is not None:
                cached_emb = cache.get_embedding(photo.path)
                if cached_emb is not None:
                    result.embeddings[i] = cached_emb
                else:
                    need_embed = True
            elif options.enable_embeddings:
                need_embed = True

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
                            if photo.smiling is True:
                                result.smiling_hits += 1
                            if photo.looking_at_camera is True:
                                result.looking_hits += 1
                    except Exception:
                        photo.add_flag("face_quality_failed")
                elif photo.face_count == 0:
                    # smiling-Key im Cache setzen (via payload) – keine Gesichter
                    photo.smiling = None
                    photo.looking_at_camera = None

            # Komposition vor finalem Score (nutzt quality + face_count)
            if need_composition and bgr is not None and not getattr(photo, "is_aside", False):
                try:
                    # Cache-Treffer nicht doppelt zählen
                    was_acc = bool(getattr(photo, "is_accidental", False))
                    was_night = bool(getattr(photo, "is_weak_night", False))
                    comp = analyze_composition_bgr(
                        photo,
                        bgr,
                        enable_accidental=options.enable_accidental,
                        enable_weak_night=options.enable_weak_night,
                    )
                    if comp.is_accidental and not was_acc:
                        result.accidental_hits += 1
                    if comp.is_weak_night and not was_night:
                        result.weak_night_hits += 1
                except Exception:
                    pass

            if need_aesthetic and not getattr(photo, "is_aside", False):
                try:
                    from .local_aesthetic import apply_local_aesthetic

                    apply_local_aesthetic(photo, bgr)
                except Exception:
                    pass

            if need_embed and embedder is not None and bgr is not None:
                try:
                    vec = embedder.embed_bgr(bgr)
                    result.embeddings[i] = vec
                except Exception:
                    pass

            if not scored:
                compute_technical_score(photo)
            elif getattr(photo, "is_accidental", False) or getattr(photo, "is_weak_night", False):
                # Face-Qualität hat schon gescored – Abzüge nachziehen
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
                emb = result.embeddings.get(i)
                cache.put(photo.path, quality_payload(photo), embedding=emb)
    finally:
        if face_counter is not None:
            face_counter.close()
        if face_quality is not None:
            face_quality.close()
        if finger is not None:
            finger.close()
        if embedder is not None:
            embedder.close()

    if result.cache_hits:
        result.notes.append(
            f"Analyse-Cache: {result.cache_hits}/{len(photos)} Treffer"
        )
    if options.enable_embeddings:
        result.notes.append(
            f"Embeddings: {result.embed_backend} ({len(result.embeddings)} Vektoren)"
        )
    if options.enable_local_aesthetic:
        n_aes = sum(1 for p in photos if p.aesthetic_score is not None and not p.ai_reviewed)
        result.notes.append(f"Lokale Ästhetik: {n_aes} bewertet")
    return result
