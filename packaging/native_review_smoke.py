"""Run the real packaged WebView2 review over generated, private-data-free photos."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile


def create_fixture(directory: Path, *, stress: bool = False):
    """Only local drawings and explicit metadata; no model or service is called."""
    from PIL import Image, ImageDraw
    from photobook_curator.models import Photo
    from photobook_curator.output import write_csv
    from photobook_curator.review_export import plan_from_photos
    from photobook_curator.selection_audit import (
        begin_selection_audit, finalize_selection_audit, record_selection_event,
    )

    original_dir = directory / "generated-originals"
    output_dir = directory / "PhotoTool native review test"
    original_dir.mkdir(parents=True)
    output_dir.mkdir()
    photos = []
    for i in range(8):
        name = f"DEMO_{'Kyoto' if i < 4 else 'Tokyo'}_{i + 1:02d}.jpg"
        image = Image.new("RGB", (1200, 800), "#ccdedd")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 480, 1200, 800), fill="#648773")
        draw.ellipse((900, 75, 1035, 210), fill="#f7db8a")
        shift = (i % 4) * 35
        draw.rectangle((350 + shift, 350, 730 + shift, 650), fill="#b5553f")
        draw.polygon(((230 + shift, 370), (540 + shift, 180), (850 + shift, 370)), fill="#25483f")
        draw.rectangle((500 + shift, 480, 580 + shift, 650), fill="#23493e")
        draw.rectangle((0, 0, 1200, 55), fill="#193f3d")
        draw.text((18, 20), "SYNTHETIC NATIVE WINDOW TEST / " + name, fill="white")
        source = original_dir / name
        if stress and i % 4 == 1:
            image = image.transpose(Image.Transpose.ROTATE_90)
        width, height = image.size
        image.save(source, quality=90)
        image.close()
        selected = i in {0, 3, 4}
        photo = Photo(source, name, width=width, height=height,
            datetime_taken=datetime(2026, 7, 1 + i // 4, 10) + timedelta(seconds=i * 3),
            region="Kyoto" if i < 4 else "Tokyo", country="Japan", is_candidate=True,
            is_selected=selected, book_position={0: 1, 3: 2, 4: 3}.get(i),
            chapter_folder=("01_Kyoto" if i < 4 else "02_Tokyo") + "/hauptteil",
            chapter_type="Hauptteil", technical_score=93 - i, final_score=93 - i,
            burst_group_id=1 if i < 3 else None, scene_type="sehenswuerdigkeit")
        photos.append(photo)
    if stress:
        # The real 0.5.0 failure needed a long chapter list; two short cities
        # cannot reproduce it. Keep the small fixture for focused unit tests,
        # but exercise 44 chapters and mixed image shapes in every native gate.
        import shutil
        from photobook_curator.utils import slugify
        for chapter in range(42):
            region = (f"Transit Hatsukaichi–Fujikawaguchiko über Nishinomiya · Abschnitt {chapter + 1:02d}"
                      if chapter % 2 else f"Kyoto · Stadtbezirk mit langer Kapitelbezeichnung {chapter + 1:02d}")
            for variant in range(2):
                template = photos[variant]
                name = f"TEST_Kapitel_{chapter + 3:02d}_{variant + 1}.jpg"
                source = original_dir / name
                shutil.copyfile(template.path, source)
                photos.append(Photo(source, name, width=template.width, height=template.height,
                    datetime_taken=datetime(2026, 7, 3, 10) + timedelta(minutes=chapter * 2 + variant),
                    region=region, country="Japan", is_candidate=True,
                    chapter_folder=f"{chapter + 3:02d}_{slugify(region)}/hauptteil",
                    chapter_type="Hauptteil", technical_score=90, final_score=90,
                    scene_type="transport"))
    begin_selection_audit(photos, {"synthetic_native_window_test": True, "target_count": 3})
    for i, photo in enumerate(photos):
        record_selection_event(photo, "diversity_selected" if photo.is_selected else "diversity_quota_exhausted",
                               "diversity", quota=3, score=photo.final_score)
    finalize_selection_audit(photos, [(i, p.chapter_folder, p.chapter_type)
                                     for i, p in enumerate(photos) if p.is_selected])
    write_csv(photos, output_dir / "photos_analysis.csv")
    return photos, plan_from_photos(photos), output_dir


def run(result_path: Path, capture_dir: Path | None = None) -> int:
    from photobook_curator.modern_review import ReviewServer, run_native_window
    from photobook_curator.modern_review_session import ReviewSession

    result_path = Path(result_path).resolve()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    if capture_dir is not None:
        capture_dir = Path(capture_dir).resolve()
        capture_dir.mkdir(parents=True, exist_ok=True)
    # An old success file must never make a failed new process look healthy.
    result_path.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="PhotoTool-native-review-") as temporary:
        photos, plan, output_dir = create_fixture(Path(temporary), stress=True)
        session = ReviewSession(photos, plan, output_dir)
        server = ReviewServer(session)
        original_mode = None
        display = None
        try:
            if capture_dir is not None and sys.platform == "win32":
                from capture_ui import prepare_display
                display, original_mode = prepare_display()
            url = server.start()
            run_native_window(url, title="PhotoTool · Native Review Test",
                              smoke_result=result_path, capture_dir=capture_dir)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if display is not None:
                result["capture_display"] = display
                result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            if not result.get("success"):
                raise RuntimeError("The native review did not report a successful render: "
                                   + str(result.get("error", "no render diagnostics")))
            return 0
        finally:
            try:
                session.action({"action": "save"})
            finally:
                server.close()
                if original_mode is not None:
                    import ctypes
                    restored = ctypes.windll.user32.ChangeDisplaySettingsExW(
                        None, ctypes.byref(original_mode), None, 0, None)
                    if result_path.is_file():
                        result = json.loads(result_path.read_text(encoding="utf-8"))
                        result.setdefault("capture_display", {})["restore_result"] = restored
                        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
