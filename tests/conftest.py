"""Finalize test-owned Tcl interpreters on the thread that created them."""
from __future__ import annotations

from functools import wraps
import gc
import threading

import pytest


_CREATED_TK_ROOT = pytest.StashKey[bool]()


@pytest.fixture(autouse=True)
def _track_test_tk_roots(request, monkeypatch):
    import tkinter as tk

    original = tk.Tk.__init__

    @wraps(original)
    def initialize(root, *args, **kwargs):
        original(root, *args, **kwargs)
        if threading.current_thread() is threading.main_thread():
            request.node.stash[_CREATED_TK_ROOT] = True

    monkeypatch.setattr(tk.Tk, "__init__", initialize)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    yield
    if item.stash.get(_CREATED_TK_ROOT, False):
        # root.destroy() closes widgets but leaves Python callback/Variable cycles.
        # During fixture teardown, item.funcargs still retains the destroyed root;
        # runtest_protocol releases those references before this hook resumes.
        # Collect now so a later HTTP worker cannot finalize Tcl on its own thread.
        gc.collect()
