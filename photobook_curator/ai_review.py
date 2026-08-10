"""Phase 4: KI-gestützte Inhaltsbewertung via Anthropic Vision oder lokale Ollama."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from tqdm import tqdm

from .models import Photo
from .utils import load_image, resize_max_edge

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OLLAMA = "ollama"
AI_PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_OLLAMA)

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
DEFAULT_OLLAMA_MODEL = "llava"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
# Grobe Kostenschätzung USD pro Bild (Input+Output Vision klein) – nur Anthropic
ESTIMATED_COST_PER_IMAGE_USD = 0.01


def normalize_ai_provider(provider: str | None) -> str:
    raw = str(provider or PROVIDER_ANTHROPIC).strip().lower()
    if raw in ("gratis", "free", "local", "ollama"):
        return PROVIDER_OLLAMA
    if raw in ("claude", "anthropic", "api"):
        return PROVIDER_ANTHROPIC
    return PROVIDER_ANTHROPIC if raw not in AI_PROVIDERS else raw


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


def estimate_cost(
    num_candidates: int,
    *,
    provider: str = PROVIDER_ANTHROPIC,
) -> dict[str, float]:
    prov = normalize_ai_provider(provider)
    per = 0.0 if prov == PROVIDER_OLLAMA else ESTIMATED_COST_PER_IMAGE_USD
    total = num_candidates * per
    return {
        "candidates": float(num_candidates),
        "usd_per_image": per,
        "usd_total_estimate": round(total, 4),
        "provider": prov,
    }


def check_ollama_available(host: str | None = None) -> tuple[bool, str]:
    """Prüft, ob der lokale Ollama-Server erreichbar ist."""
    base = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).rstrip("/")
    url = f"{base}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw) if raw else {}
        models = data.get("models") or []
        names = [str(m.get("name", "")) for m in models if isinstance(m, dict)]
        if not names:
            return (
                True,
                f"Ollama läuft unter {base}, aber noch kein Modell geladen "
                f"(z. B. ollama pull {DEFAULT_OLLAMA_MODEL}).",
            )
        return True, f"Ollama OK ({base}): {', '.join(names[:5])}"
    except Exception as exc:  # noqa: BLE001
        return False, (
            f"Ollama nicht erreichbar unter {base}: {exc}\n"
            f"Bitte Ollama installieren/starten und z. B. "
            f"„ollama pull {DEFAULT_OLLAMA_MODEL}“ ausführen."
        )


def estimate_candidate_count(
    target_n: int,
    found: int = 0,
    candidate_factor: float = 4.0,
) -> int:
    """Grobe Obergrenze der KI-Kandidaten vor dem Lauf (Ziel × Faktor, max. Fotos)."""
    target = max(0, int(target_n))
    factor = max(0.1, float(candidate_factor))
    n = max(1, int(round(target * factor))) if target else 0
    if found and found > 0:
        n = min(n, int(found))
    return max(0, n)


def _review_one_anthropic(
    client, model: str, photo: Photo
) -> tuple[Photo, Optional[dict], Optional[str]]:
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


# Rückwärtskompatibler Alias
_review_one = _review_one_anthropic


def _review_one_ollama(
    host: str, model: str, photo: Photo
) -> tuple[Photo, Optional[dict], Optional[str]]:
    b64 = image_to_jpeg_b64(photo)
    if b64 is None:
        return photo, None, "encode_failed"
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": "Bewerte dieses Urlaubsfoto für das Fotobuch.",
                "images": [b64],
            },
        ],
    }
    url = f"{host.rstrip('/')}/api/chat"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return photo, None, f"ollama_http_{exc.code}:{detail}"
    except Exception as exc:  # noqa: BLE001
        return photo, None, f"ollama_error:{type(exc).__name__}"

    try:
        data_wrap = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return photo, None, "parse_failed"
    msg = data_wrap.get("message") or {}
    raw = str(msg.get("content") or data_wrap.get("response") or "")
    data = parse_ai_response(raw)
    if data is None:
        return photo, None, "parse_failed"
    return photo, data, None


def run_ai_review(
    photos: list[Photo],
    candidate_indices: list[int],
    *,
    dry_run: bool = False,
    concurrency: int = 5,
    model: str | None = None,
    provider: str = PROVIDER_ANTHROPIC,
    api_key: str | None = None,
    ollama_host: str | None = None,
) -> dict[str, Any]:
    """Bewertet Kandidatenbilder (Anthropic oder lokale Ollama). Bei dry_run nur Kostenschätzung."""
    prov = normalize_ai_provider(provider)
    cost = estimate_cost(len(candidate_indices), provider=prov)
    if dry_run:
        if prov == PROVIDER_OLLAMA:
            print(
                f"[dry-run] AI-Review (Ollama/gratis): {int(cost['candidates'])} Kandidaten, "
                f"geschätzte Kosten $0.00 (lokal)"
            )
        else:
            print(
                f"[dry-run] AI-Review (Anthropic): {int(cost['candidates'])} Kandidaten, "
                f"geschätzte Kosten ~ ${cost['usd_total_estimate']:.2f} "
                f"(${cost['usd_per_image']:.3f}/Bild)"
            )
        return {"dry_run": True, **cost}

    if prov == PROVIDER_OLLAMA:
        host = (ollama_host or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).rstrip("/")
        use_model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
        ok_host, msg = check_ollama_available(host)
        if not ok_host:
            raise RuntimeError(msg)
        print(f"  {msg}")
        print(f"  Ollama-Modell: {use_model}")
        # Lokal meist ein Modell → wenig Parallelität
        workers = max(1, min(int(concurrency or 1), 2))
        review_fn = _review_one_ollama
        review_args = (host, use_model)
    else:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY ist nicht gesetzt. "
                "Bitte Umgebungsvariable setzen, API-Key in der GUI eintragen "
                "oder Gratis-KI (Ollama) wählen."
            )
        import anthropic

        use_model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
        client = anthropic.Anthropic(api_key=key)
        workers = max(1, int(concurrency or 5))
        review_fn = _review_one_anthropic
        review_args = (client, use_model)

    ok = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(review_fn, *review_args, photos[i]): i for i in candidate_indices
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


def _visual_scene_hint(photo: Photo) -> Optional[str]:
    """
    Bildbasierte Heuristik ohne KI.
    - essen: warme, gesättigte Farben, wenig/keine Gesichter
    - landschaft: Himmel/Grün-Anteil oben/gesamt, keine Gesichter
    """
    try:
        import cv2
        import numpy as np

        from .utils import load_bgr_cached

        bgr = load_bgr_cached(photo.path, max_edge=256)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h = hsv[:, :, 0]
        s = hsv[:, :, 1]
        v = hsv[:, :, 2]
        sat_mean = float(s.mean())
        # warme Töne (Rot/Orange/Gelb), kräftig
        warm = (((h <= 25) | (h >= 160)) & (s > 70) & (v > 50)).mean()
        # Himmel im oberen Drittel
        upper = hsv[: max(1, hsv.shape[0] // 3)]
        sky = (
            (upper[:, :, 0] > 85)
            & (upper[:, :, 0] < 140)
            & (upper[:, :, 1] < 120)
            & (upper[:, :, 2] > 130)
        ).mean()
        green = ((h > 35) & (h < 90) & (s > 40) & (v > 40)).mean()

        if photo.face_count == 0 and warm > 0.16 and sat_mean > 65:
            # Nah-/Food-typisch oft etwas weicher als Landschaft
            if photo.sharpness < 420 or warm > 0.28:
                return "essen"
        if photo.face_count == 0 and (sky > 0.22 or green > 0.28) and photo.sharpness > 60:
            return "landschaft"
    except Exception:
        return None
    return None


def heuristic_scene_type(photo: Photo) -> str:
    """Fallback ohne AI: Dateiname + Gesichter + einfache Bildheuristik."""
    name = photo.filename.lower()
    for key in (
        "essen",
        "food",
        "meal",
        "restaurant",
        "dinner",
        "lunch",
        "transport",
        "transit",
        "zug",
        "train",
        "flug",
        "flight",
        "airport",
        "portrait",
        "gruppe",
        "landschaft",
        "sehenswuerdigkeit",
        "landmark",
        "detail",
        "alltag",
    ):
        if key in name:
            if key in ("food", "meal", "restaurant", "dinner", "lunch"):
                return "essen"
            if key in ("transit", "zug", "train", "flug", "flight", "airport"):
                return "transport"
            if key == "landmark":
                return "sehenswuerdigkeit"
            return key

    if "transit" in photo.flags or (
        photo.region and str(photo.region).startswith("Transit:")
    ):
        return "transport"
    if photo.face_count >= 3:
        return "gruppe"
    if photo.face_count >= 1:
        return "portrait"

    visual = _visual_scene_hint(photo)
    if visual:
        return visual

    if photo.sharpness > 200 and photo.contrast > 40 and photo.face_count == 0:
        return "landschaft"
    return "alltag"


def ensure_scene_types(photos: list[Photo], indices: Optional[list[int]] = None) -> None:
    """Setzt scene_type falls fehlend (ohne AI oder nach AI-Fehler)."""
    targets = indices if indices is not None else list(range(len(photos)))
    for i in targets:
        if not photos[i].scene_type:
            photos[i].scene_type = heuristic_scene_type(photos[i])
