"""Bild-Embeddings für Inhalts-Ähnlichkeit (ohne Torch)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .utils import download_model

_EMBEDDER_URL = (
    "https://storage.googleapis.com/mediapipe-models/image_embedder/"
    "mobilenet_v3_small/float32/1/mobilenet_v3_small.tflite"
)


def _fallback_embedding(bgr: np.ndarray) -> np.ndarray:
    """Kompaktes Offline-Embedding: Thumbnail + Farb-/Kantenhistogramm."""
    small = cv2.resize(bgr, (64, 64), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    thumb = gray.flatten()
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist_h = cv2.calcHist([hsv], [0], None, [16], [0, 180]).flatten()
    hist_s = cv2.calcHist([hsv], [1], None, [8], [0, 256]).flatten()
    hist_v = cv2.calcHist([hsv], [2], None, [8], [0, 256]).flatten()
    edges = cv2.Canny((gray * 255).astype(np.uint8), 60, 140)
    edge_hist = cv2.calcHist([edges], [0], None, [8], [0, 256]).flatten()
    vec = np.concatenate(
        [
            thumb,
            hist_h / (hist_h.sum() + 1e-6),
            hist_s / (hist_s.sum() + 1e-6),
            hist_v / (hist_v.sum() + 1e-6),
            edge_hist / (edge_hist.sum() + 1e-6),
        ]
    ).astype(np.float32)
    n = float(np.linalg.norm(vec)) + 1e-8
    return vec / n


class ImageEmbedder:
    """MediaPipe ImageEmbedder wenn verfügbar, sonst Offline-Fallback."""

    def __init__(self, model_cache_dir: Path | None = None) -> None:
        self._mode = "fallback"
        self._embedder = None
        cache = model_cache_dir or Path.home() / ".cache" / "photobook_curator"
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            model = download_model(_EMBEDDER_URL, cache / "mobilenet_v3_small.tflite")
            if model is not None:
                options = vision.ImageEmbedderOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=str(model)),
                    l2_normalize=True,
                    quantize=False,
                )
                self._embedder = vision.ImageEmbedder.create_from_options(options)
                self._mode = "mediapipe"
        except Exception:
            self._embedder = None
            self._mode = "fallback"

    @property
    def backend(self) -> str:
        return self._mode

    def embed_bgr(self, bgr: np.ndarray) -> np.ndarray:
        if self._embedder is not None:
            try:
                import mediapipe as mp

                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                # Embedder erwartet typisch 224px
                side = 224
                h, w = rgb.shape[:2]
                scale = side / max(h, w)
                resized = cv2.resize(
                    rgb,
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    interpolation=cv2.INTER_AREA,
                )
                canvas = np.zeros((side, side, 3), dtype=np.uint8)
                y0 = (side - resized.shape[0]) // 2
                x0 = (side - resized.shape[1]) // 2
                canvas[y0 : y0 + resized.shape[0], x0 : x0 + resized.shape[1]] = resized
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=canvas)
                result = self._embedder.embed(mp_image)
                if result.embeddings:
                    emb = result.embeddings[0]
                    vec = np.asarray(emb.embedding, dtype=np.float32)
                    n = float(np.linalg.norm(vec)) + 1e-8
                    return vec / n
            except Exception:
                pass
        return _fallback_embedding(bgr)

    def close(self) -> None:
        if self._embedder is not None:
            try:
                self._embedder.close()
            except Exception:
                pass


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None or a.size == 0 or b.size == 0:
        return 0.0
    if a.shape != b.shape:
        n = min(a.size, b.size)
        a = a[:n]
        b = b[:n]
    return float(np.dot(a, b))
