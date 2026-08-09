"""Phase 4: KI-gestützte Inhaltsbewertung via Anthropic Vision API."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from tqdm import tqdm

from .models import Photo
from .utils import load_image, resize_max_edge

SYSTEM_PROMPT = (
    "Du bewertest ein Urlaubsfoto für ein gedrucktes Fotobuch. "
    "Antworte ausschliesslich mit einem JSON-Objekt, keine Erklärung davor oder danach. Felder:\n"
    "- aesthetic_score: Zahl von 0 bis 100, wie gut das Foto als Erinnerungsstück und für den Druck wirkt, "
    "Bildaufbau, Licht, Emotion, Moment\n"
    "- landmark: entweder null oder ein kurzer String mit dem Namen einer erkannten Sehenswürdigkeit\n"
    "- scene_type: einer von 'portrait', 'gruppe', 'landschaft', 'sehenswuerdigkeit', 'essen', "
    "'transport', 'detail', 'alltag', 'sonstiges'\n"
    "- mood: kurzer String zur Stimmung, z.B. 'ausgelassen', 'ruhig', 'spontan'\n"
    "- quality_issue: entweder null oder kurzer Grund, warum das Bild ungeeignet ist, "
    "z.B. 'Augen geschlossen', 'unvorteilhafter Ausdruck'\n"
    "- keep_recommendation: true oder false"
)

DEFAULT_MODEL = "claude-sonnet-4-6"
# Grobe Kostenschätzung USD pro Bild (Input+Output Vision klein)
ESTIMATED_COST_PER_IMAGE_USD = 0.01


def image_to_jpeg_b64(photo: Photo, max_edge: int = 1024, quality: int = 85) -> Optional[str]:
    try:
        img = load_image(photo.path)
        img = resize_max_edge(img, max_edge=max_edge)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
        return base64.standard_b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def parse_ai_response(text: str) -> Optional[dict[str, Any]]:
    text = text.strip()
    # JSON ggf. aus Markdown-Fence extrahieren
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def apply_ai_result(photo: Photo, data: dict[str, Any]) -> None:
    try:
        photo.aesthetic_score = float(data.get("aesthetic_score"))
    except (TypeError, ValueError):
        photo.aesthetic_score = None
    landmark = data.get("landmark")
    photo.landmark = None if landmark in (None, "null") else str(landmark)
    scene = data.get("scene_type")
    photo.scene_type = str(scene) if scene else "sonstiges"
    mood = data.get("mood")
    photo.mood = str(mood) if mood else None
    qi = data.get("quality_issue")
    photo.quality_issue = None if qi in (None, "null") else str(qi)
    keep = data.get("keep_recommendation")
    if isinstance(keep, bool):
        photo.keep_recommendation = keep
    elif isinstance(keep, str):
        photo.keep_recommendation = keep.lower() in ("true", "1", "yes", "ja")
    else:
        photo.keep_recommendation = None
    photo.ai_reviewed = True
    if photo.quality_issue:
        photo.add_flag("quality_issue")
    if photo.keep_recommendation is False:
        photo.add_flag("ai_reject")


def estimate_cost(num_candidates: int) -> dict[str, float]:
    total = num_candidates * ESTIMATED_COST_PER_IMAGE_USD
    return {
        "candidates": float(num_candidates),
        "usd_per_image": ESTIMATED_COST_PER_IMAGE_USD,
        "usd_total_estimate": round(total, 4),
    }


def _review_one(client, model: str, photo: Photo) -> tuple[Photo, Optional[dict], Optional[str]]:
    b64 = image_to_jpeg_b64(photo)
    if b64 is None:
        return photo, None, "encode_failed"
    try:
        message = client.messages.create(
            model=model,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Bewerte dieses Urlaubsfoto für das Fotobuch.",
                        },
                    ],
                }
            ],
        )
        text_parts = []
        for block in message.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        raw = "\n".join(text_parts)
        data = parse_ai_response(raw)
        if data is None:
            return photo, None, "parse_failed"
        return photo, data, None
    except Exception as exc:
        return photo, None, f"api_error:{type(exc).__name__}"


def run_ai_review(
    photos: list[Photo],
    candidate_indices: list[int],
    *,
    dry_run: bool = False,
    concurrency: int = 5,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Bewertet Kandidatenbilder. Bei dry_run nur Kostenschätzung."""
    cost = estimate_cost(len(candidate_indices))
    if dry_run:
        print(
            f"[dry-run] AI-Review: {int(cost['candidates'])} Kandidaten, "
            f"geschätzte Kosten ~ ${cost['usd_total_estimate']:.2f} "
            f"(${cost['usd_per_image']:.3f}/Bild)"
        )
        return {"dry_run": True, **cost}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY ist nicht gesetzt. Bitte Umgebungsvariable setzen oder --dry-run nutzen."
        )

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    ok = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {
            pool.submit(_review_one, client, model, photos[i]): i for i in candidate_indices
        }
        for fut in tqdm(as_completed(futures), total=len(futures), desc="AI-Review", unit="img"):
            photo, data, err = fut.result()
            if data is not None:
                apply_ai_result(photo, data)
                ok += 1
            else:
                failed += 1
                photo.add_flag(err or "ai_failed")
                # technischer Score bleibt, Lauf geht weiter

    return {"dry_run": False, "ok": ok, "failed": failed, **cost}


def heuristic_scene_type(photo: Photo) -> str:
    """Fallback ohne AI: grobe Heuristik für scene_type."""
    name = photo.filename.lower()
    for key in (
        "essen",
        "food",
        "meal",
        "transport",
        "transit",
        "zug",
        "train",
        "flug",
        "portrait",
        "gruppe",
        "landschaft",
        "sehenswuerdigkeit",
        "landmark",
        "detail",
        "alltag",
    ):
        if key in name:
            if key in ("food", "meal"):
                return "essen"
            if key in ("transit", "zug", "train", "flug"):
                return "transport"
            if key == "landmark":
                return "sehenswuerdigkeit"
            return key

    if "transit" in photo.flags:
        return "transport"
    if photo.face_count >= 3:
        return "gruppe"
    if photo.face_count >= 1:
        return "portrait"
    if photo.sharpness > 200 and photo.contrast > 40:
        return "landschaft"
    return "alltag"


def ensure_scene_types(photos: list[Photo], indices: Optional[list[int]] = None) -> None:
    """Setzt scene_type falls fehlend (ohne AI oder nach AI-Fehler)."""
    targets = indices if indices is not None else list(range(len(photos)))
    for i in targets:
        if not photos[i].scene_type:
            photos[i].scene_type = heuristic_scene_type(photos[i])
