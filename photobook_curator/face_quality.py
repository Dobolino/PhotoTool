"""Lokale Gesichtsqualitäts-Analyse: geschlossene Augen, Anschnitt, zu klein."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlretrieve

import cv2
import numpy as np
from tqdm import tqdm

from .models import Photo
from .quality import compute_technical_score
from .utils import load_image, to_cv_bgr

_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)

# MediaPipe Face Mesh Indizes für Eye Aspect Ratio
_LEFT_EYE = (33, 160, 158, 133, 153, 144)
_RIGHT_EYE = (362, 385, 387, 263, 373, 380)

EAR_CLOSED_THRESHOLD = 0.19
BLINK_SCORE_THRESHOLD = 0.45
FACE_MIN_AREA_RATIO = 0.012  # unter ~1.2% der Bildfläche = sehr klein
EDGE_MARGIN_RATIO = 0.02  # 2% Rand = angeschnitten


@dataclass
class FaceQualityResult:
    face_count: int = 0
    eyes_closed: bool = False
    face_cut_off: bool = False
    face_too_small: bool = False
    issues: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.issues is None:
            self.issues = []

    @property
    def bad_face(self) -> bool:
        return self.eyes_closed or self.face_cut_off or self.face_too_small


def _ensure_landmarker_model(cache_dir: Path) -> Path | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_path = cache_dir / "face_landmarker.task"
    # Alte/fehlerhafte .tflite-Caches entfernen
    legacy = cache_dir / "face_landmarker.tflite"
    if legacy.exists():
        legacy.unlink(missing_ok=True)
    if model_path.exists() and model_path.stat().st_size > 1000:
        return model_path
    try:
        urlretrieve(_LANDMARKER_URL, model_path)
        if model_path.stat().st_size < 1000:
            model_path.unlink(missing_ok=True)
            return None
        return model_path
    except Exception:
        if model_path.exists():
            model_path.unlink(missing_ok=True)
        return None


def eye_aspect_ratio(points: np.ndarray) -> float:
    """EAR aus 6 Punkten: [outer, upper1, upper2, inner, lower2, lower1]."""
    if points.shape != (6, 2):
        raise ValueError("EAR erwartet 6 Punkte")
    p1, p2, p3, p4, p5, p6 = points
    vertical = np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)
    horizontal = np.linalg.norm(p1 - p4)
    if horizontal < 1e-6:
        return 0.0
    return float(vertical / (2.0 * horizontal))


def _landmarks_to_xy(landmarks, width: int, height: int) -> np.ndarray:
    return np.array([[lm.x * width, lm.y * height] for lm in landmarks], dtype=np.float64)


def _bbox_from_points(pts: np.ndarray) -> tuple[float, float, float, float]:
    xs, ys = pts[:, 0], pts[:, 1]
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def _analyze_landmarks(
    landmarks,
    width: int,
    height: int,
    blendshapes=None,
) -> tuple[bool, bool, bool, list[str]]:
    pts = _landmarks_to_xy(landmarks, width, height)
    issues: list[str] = []

    # Geschlossene Augen: Blendshapes bevorzugt, sonst EAR
    eyes_closed = False
    if blendshapes is not None:
        # MediaPipe liefert entweder Classifications oder eine Liste von Category
        cats = getattr(blendshapes, "categories", None) or blendshapes
        scores = {b.category_name: b.score for b in cats}
        left = scores.get("eyeBlinkLeft", 0.0)
        right = scores.get("eyeBlinkRight", 0.0)
        if left >= BLINK_SCORE_THRESHOLD and right >= BLINK_SCORE_THRESHOLD:
            eyes_closed = True
        elif max(left, right) >= 0.7 and min(left, right) >= 0.35:
            # ein Auge fest zu, anderes fast
            eyes_closed = True
    if not eyes_closed:
        try:
            left_ear = eye_aspect_ratio(pts[list(_LEFT_EYE)])
            right_ear = eye_aspect_ratio(pts[list(_RIGHT_EYE)])
            if left_ear < EAR_CLOSED_THRESHOLD and right_ear < EAR_CLOSED_THRESHOLD:
                eyes_closed = True
        except Exception:
            pass
    if eyes_closed:
        issues.append("Augen geschlossen")

    x0, y0, x1, y1 = _bbox_from_points(pts)
    bw, bh = max(1.0, x1 - x0), max(1.0, y1 - y0)
    area_ratio = (bw * bh) / max(1.0, width * height)
    face_too_small = area_ratio < FACE_MIN_AREA_RATIO
    if face_too_small:
        issues.append("Gesicht zu klein")

    margin_x = width * EDGE_MARGIN_RATIO
    margin_y = height * EDGE_MARGIN_RATIO
    face_cut_off = (
        x0 <= margin_x
        or y0 <= margin_y
        or x1 >= width - margin_x
        or y1 >= height - margin_y
    )
    if face_cut_off:
        issues.append("Gesicht angeschnitten")

    return eyes_closed, face_cut_off, face_too_small, issues


class FaceQualityAnalyzer:
    def __init__(self, model_cache_dir: Path | None = None) -> None:
        self._mode = "none"
        self._landmarker = None
        self._haar_face = None
        self._haar_eye = None
        self._init(model_cache_dir or Path.home() / ".cache" / "photobook_curator")

    def _init(self, cache_dir: Path) -> None:
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            model_path = _ensure_landmarker_model(cache_dir)
            if model_path is not None:
                options = vision.FaceLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
                    output_face_blendshapes=True,
                    num_faces=5,
                    min_face_detection_confidence=0.4,
                    min_face_presence_confidence=0.4,
                    min_tracking_confidence=0.4,
                )
                self._landmarker = vision.FaceLandmarker.create_from_options(options)
                self._mode = "mediapipe_landmarker"
                return
        except Exception:
            pass

        try:
            self._haar_face = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            self._haar_eye = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_eye.xml"
            )
            if not self._haar_face.empty():
                self._mode = "haar"
        except Exception:
            self._mode = "none"

    @property
    def backend(self) -> str:
        return self._mode

    def analyze_bgr(self, bgr: np.ndarray) -> FaceQualityResult:
        h, w = bgr.shape[:2]
        if self._mode == "mediapipe_landmarker" and self._landmarker is not None:
            return self._analyze_mp(bgr, w, h)
        if self._mode == "haar" and self._haar_face is not None:
            return self._analyze_haar(bgr, w, h)
        return FaceQualityResult()

    def _analyze_mp(self, bgr: np.ndarray, w: int, h: int) -> FaceQualityResult:
        import mediapipe as mp

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(mp_image)
        if not result.face_landmarks:
            return FaceQualityResult(face_count=0)

        any_closed = False
        any_cut = False
        any_small = False
        issues: list[str] = []
        for i, lms in enumerate(result.face_landmarks):
            blends = None
            if result.face_blendshapes and i < len(result.face_blendshapes):
                blends = result.face_blendshapes[i]
            closed, cut, small, face_issues = _analyze_landmarks(lms, w, h, blends)
            any_closed = any_closed or closed
            any_cut = any_cut or cut
            any_small = any_small or small
            for issue in face_issues:
                if issue not in issues:
                    issues.append(issue)

        return FaceQualityResult(
            face_count=len(result.face_landmarks),
            eyes_closed=any_closed,
            face_cut_off=any_cut,
            face_too_small=any_small,
            issues=issues,
        )

    def _analyze_haar(self, bgr: np.ndarray, w: int, h: int) -> FaceQualityResult:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        faces = self._haar_face.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
        if len(faces) == 0:
            return FaceQualityResult(face_count=0)

        any_closed = False
        any_cut = False
        any_small = False
        issues: list[str] = []
        margin_x = w * EDGE_MARGIN_RATIO
        margin_y = h * EDGE_MARGIN_RATIO

        for x, y, fw, fh in faces:
            area_ratio = (fw * fh) / max(1.0, w * h)
            if area_ratio < FACE_MIN_AREA_RATIO:
                any_small = True
            if x <= margin_x or y <= margin_y or x + fw >= w - margin_x or y + fh >= h - margin_y:
                any_cut = True

            if self._haar_eye is not None and not self._haar_eye.empty():
                roi = gray[y : y + fh, x : x + fw]
                eyes = self._haar_eye.detectMultiScale(roi, 1.1, 8, minSize=(12, 12))
                # Bei klar erkennbarem Gesicht ohne Augen: verdächtig geschlossen
                if len(eyes) == 0 and fh > 80:
                    any_closed = True

        if any_closed:
            issues.append("Augen geschlossen")
        if any_cut:
            issues.append("Gesicht angeschnitten")
        if any_small:
            issues.append("Gesicht zu klein")

        return FaceQualityResult(
            face_count=len(faces),
            eyes_closed=any_closed,
            face_cut_off=any_cut,
            face_too_small=any_small,
            issues=issues,
        )

    def close(self) -> None:
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception:
                pass


def apply_face_quality(photo: Photo, result: FaceQualityResult) -> None:
    """Schreibt Ergebnis in Photo-Flags/Felder und aktualisiert Scores."""
    if result.face_count > 0 and photo.face_count == 0:
        photo.face_count = result.face_count

    photo.eyes_closed = result.eyes_closed
    photo.face_cut_off = result.face_cut_off
    photo.face_too_small = result.face_too_small
    photo.bad_face = result.bad_face

    for issue in result.issues:
        flag = {
            "Augen geschlossen": "eyes_closed",
            "Gesicht angeschnitten": "face_cut_off",
            "Gesicht zu klein": "face_too_small",
        }.get(issue)
        if flag:
            photo.add_flag(flag)

    if result.bad_face:
        photo.add_flag("bad_face")
        # quality_issue nur setzen, wenn KI nichts gesetzt hat
        if not photo.quality_issue:
            photo.quality_issue = "; ".join(result.issues)

    compute_technical_score(photo)


def analyze_face_quality(photos: list[Photo]) -> str:
    analyzer = FaceQualityAnalyzer()
    backend = analyzer.backend
    for photo in tqdm(photos, desc=f"Gesichtsqualität ({backend})", unit="img"):
        # Nur Bilder mit Gesichtern oder Portrait-Kandidaten prüfen — trotzdem alle scannen,
        # da face_count vorher schon gesetzt sein kann; bei 0 trotzdem kurz prüfen.
        try:
            img = load_image(photo.path)
            bgr = to_cv_bgr(img)
            result = analyzer.analyze_bgr(bgr)
            # Wenn vorher face_count > 0 aber Landmarker 0 findet: Flags nicht erzwingen
            if result.face_count == 0 and photo.face_count == 0:
                continue
            if result.face_count == 0 and photo.face_count > 0:
                # Fallback: keine Qualitätsinfo
                continue
            apply_face_quality(photo, result)
        except Exception:
            photo.add_flag("face_quality_failed")
    analyzer.close()
    return backend
