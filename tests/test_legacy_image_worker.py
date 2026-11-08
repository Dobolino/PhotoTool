"""Image decoding must not retain a Tk owner on its background thread."""
from __future__ import annotations

import queue
import threading
import weakref

from PIL import Image

from photobook_curator.models import Photo
from photobook_curator.review_gui import ReviewWindow, THUMB


def test_decoder_outlives_its_window_without_retaining_any_tk_owner(tmp_path):
    source = tmp_path / "original.jpg"
    Image.new("RGB", (320, 200), (10, 120, 210)).save(source)
    photos = [Photo(source, source.name)]
    jobs, thumbs, slides = queue.PriorityQueue(), queue.Queue(), queue.Queue()
    # No native interpreter is needed to verify the worker's ownership boundary.
    window = ReviewWindow.__new__(ReviewWindow)
    owner = weakref.ref(window)
    worker = threading.Thread(target=window._thumb_worker,
                              args=(photos, jobs, thumbs, slides, "#ffffff"), daemon=True)
    del window
    assert owner() is None, "The worker target must not hold a bound Tk window"

    worker.start()
    try:
        jobs.put((0, 0, ("slide", 0)))
        index, slide = slides.get(timeout=3)
        thumb_index, thumb = thumbs.get(timeout=3)
        assert index == thumb_index == 0
        assert isinstance(slide, Image.Image) and slide.size == (320, 200)
        assert isinstance(thumb, Image.Image) and thumb.size == (THUMB, THUMB)
        slide.close()
        thumb.close()
    finally:
        jobs.put((-1, 1, None))
        worker.join(timeout=3)
        assert not worker.is_alive()
