"""Phase 4: KI-Bewertung via Anthropic, Google Gemini oder lokale Ollama."""

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

PROVIDER_NONE = "none"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_GEMINI = "gemini"
PROVIDER_OLLAMA = "ollama"
AI_PROVIDERS = (PROVIDER_NONE, PROVIDER_GEMINI, PROVIDER_ANTHROPIC, PROVIDER_OLLAMA)
CLOUD_AI_PROVIDERS = (PROVIDER_GEMINI, PROVIDER_ANTHROPIC, PROVIDER_OLLAMA)

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

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_MODEL = DEFAULT_ANTHROPIC_MODEL  # Rückwärtskompatibilität
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
DEFAULT_OLLAMA_MODEL = "llava"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
ANTHROPIC_KEY_URL = "https://console.anthropic.com/"
GEMINI_KEY_URL = "https://aistudio.google.com/apikey"
# Grobe Kostenschätzung USD pro Bild – nur Anthropic (Pay-per-Use)
ESTIMATED_COST_PER_IMAGE_USD = 0.01


def normalize_ai_provider(provider: str | None) -> str:
    raw = str(provider or PROVIDER_NONE).strip().lower()
    if raw in ("", "none", "off", "local-only", "heuristik", "heuristic", "no", "false", "0"):
        return PROVIDER_NONE
    if raw in ("gemini", "google", "flash", "gemini-flash", "gratis", "free"):
        return PROVIDER_GEMINI
    if raw in ("claude", "anthropic", "api", "sonnet"):
        return PROVIDER_ANTHROPIC
    if raw in ("ollama", "llava", "local"):
        return PROVIDER_OLLAMA
    return raw if raw in AI_PROVIDERS else PROVIDER_NONE


def is_ai_provider_enabled(provider: str | None) -> bool:
    return normalize_ai_provider(provider) in CLOUD_AI_PROVIDERS


def image_to_jpeg_b64(photo: Photo, max_edge: int = 1024, quality: int = 85) -> Optional[str]:
    raw = image_to_jpeg_bytes(photo, max_edge=max_edge, quality=quality)
    if raw is None:
        return None
    return base64.standard_b64encode(raw).decode("ascii")


def image_to_jpeg_bytes(photo: Photo, max_edge: int = 1024, quality: int = 85) -> Optional[bytes]:
    try:
        img = load_image(photo.path)
        img = resize_max_edge(img, max_edge=max_edge)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
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
) -> dict[str, float | str]:
    prov = normalize_ai_provider(provider)
    per = ESTIMATED_COST_PER_IMAGE_USD if prov == PROVIDER_ANTHROPIC else 0.0
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


def _review_one_gemini(
    model: Any, photo: Photo
) -> tuple[Photo, Optional[dict], Optional[str]]:
    raw = image_to_jpeg_bytes(photo)
    if raw is None:
        return photo, None, "encode_failed"
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        response = model.generate_content(
            [img, "Bewerte dieses Urlaubsfoto für das Fotobuch."]
        )
        text = getattr(response, "text", None) or ""
        if not text and getattr(response, "candidates", None):
            # Fallback bei blockierten/leeren Antworten
            parts = []
            for cand in response.candidates:
                content = getattr(cand, "content", None)
                for part in getattr(content, "parts", []) or []:
                    if getattr(part, "text", None):
                        parts.append(part.text)
            text = "\n".join(parts)
        data = parse_ai_response(text)
        if data is None:
            return photo, None, "parse_failed"
        return photo, data, None
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        msg = str(exc).lower()
        if "quota" in msg or "429" in msg or "resource exhausted" in msg:
            return photo, None, f"gemini_quota:{name}"
        if "api key" in msg or "permission" in msg or "401" in msg or "403" in msg:
            return photo, None, f"gemini_auth:{name}"
        return photo, None, f"gemini_error:{name}"


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
    """Bewertet Kandidaten (Gemini / Anthropic / Ollama). Bei dry_run nur Schätzung."""
    prov = normalize_ai_provider(provider)
    if prov == PROVIDER_NONE:
        ensure_scene_types(photos, candidate_indices)
        return {
            "dry_run": False,
            "ok": 0,
            "failed": 0,
            "skipped_cached": 0,
            "provider": prov,
            "candidates": float(len(candidate_indices)),
            "usd_per_image": 0.0,
            "usd_total_estimate": 0.0,
        }

    # Bereits bewertete Fotos (CSV/Cache) nicht erneut an die API schicken
    todo: list[int] = []
    skipped_cached = 0
    for i in candidate_indices:
        if i < 0 or i >= len(photos):
            continue
        if photos[i].ai_reviewed:
            skipped_cached += 1
            continue
        todo.append(i)

    cost = estimate_cost(len(todo), provider=prov)
    if dry_run:
        label = {
            PROVIDER_GEMINI: "Gemini Free Tier",
            PROVIDER_OLLAMA: "Ollama/lokal",
            PROVIDER_ANTHROPIC: "Anthropic",
        }.get(prov, prov)
        print(
            f"[dry-run] AI-Review ({label}): {int(cost['candidates'])} Kandidaten"
            + (
                f", geschätzt ~ ${cost['usd_total_estimate']:.2f}"
                if prov == PROVIDER_ANTHROPIC
                else ", geschätzt $0.00"
            )
            + (f" · {skipped_cached} bereits im Cache" if skipped_cached else "")
        )
        return {"dry_run": True, "skipped_cached": skipped_cached, **cost}

    if not todo:
        print(f"  AI-Review: alle {skipped_cached} Kandidaten bereits bewertet (Cache) – übersprungen")
        ensure_scene_types(photos, candidate_indices)
        return {
            "dry_run": False,
            "ok": 0,
            "failed": 0,
            "skipped_cached": skipped_cached,
            **cost,
        }

    if prov == PROVIDER_OLLAMA:
        host = (ollama_host or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).rstrip("/")
        use_model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
        ok_host, msg = check_ollama_available(host)
        if not ok_host:
            raise RuntimeError(msg)
        print(f"  {msg}")
        print(f"  Ollama-Modell: {use_model}")
        workers = max(1, min(int(concurrency or 1), 2))
        review_fn = _review_one_ollama
        review_args: tuple[Any, ...] = (host, use_model)
    elif prov == PROVIDER_GEMINI:
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY fehlt. Key unter "
                f"{GEMINI_KEY_URL} erstellen und in der GUI eintragen."
            )
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "google-generativeai ist nicht installiert. "
                "Bitte: pip install google-generativeai"
            ) from exc
        use_model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        genai.configure(api_key=key)
        gemini_model = genai.GenerativeModel(
            model_name=use_model,
            system_instruction=SYSTEM_PROMPT,
            generation_config={
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        )
        print(f"  Gemini-Modell: {use_model} (Free Tier – Rate-Limits beachten)")
        workers = max(1, min(int(concurrency or 3), 3))
        review_fn = _review_one_gemini
        review_args = (gemini_model,)
    else:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY ist nicht gesetzt. "
                "Bitte Umgebungsvariable setzen, API-Key in der GUI eintragen "
                "oder Gemini / Ollama wählen."
            )
        import anthropic

        use_model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
        client = anthropic.Anthropic(api_key=key)
        workers = max(1, int(concurrency or 5))
        review_fn = _review_one_anthropic
        review_args = (client, use_model)

    ok = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(review_fn, *review_args, photos[i]): i for i in todo}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="AI-Review", unit="img"):
            photo, data, err = fut.result()
            if data is not None:
                apply_ai_result(photo, data)
                ok += 1
            else:
                failed += 1
                photo.add_flag(err or "ai_failed")
                # Stabil: lokale Heuristik statt leerem scene_type
                if not photo.scene_type:
                    photo.scene_type = heuristic_scene_type(photo)

    ensure_scene_types(photos, candidate_indices)
    return {
        "dry_run": False,
        "ok": ok,
        "failed": failed,
        "skipped_cached": skipped_cached,
        **cost,
    }


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
