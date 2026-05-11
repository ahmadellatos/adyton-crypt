"""
ui/dnd.py
Helper drag-and-drop berbasis tkinterdnd2.
Mendukung multi-file drop.
"""
import os
import re

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except ImportError:
    TkinterDnD = None
    DND_FILES   = None
    DND_AVAILABLE = False


def parse_drop_paths(raw: str) -> list[str]:
    """
    Parse path mentah dari event drop Windows Explorer.
    Sekarang mengembalikan LIST dari semua file/folder yang diseret.
    """
    raw = raw.strip()
    matches = re.findall(r'\{([^}]+)\}|(\S+)', raw)
    paths = []
    for braced, plain in matches:
        p = braced or plain
        if p:
            paths.append(os.path.normpath(p))
    return paths


def _bind_hover(widget, on_enter, on_leave):
    hovering = [False]

    def _enter(event):
        if not hovering[0]:
            hovering[0] = True
            if on_enter: on_enter()

    def _position(event):
        if not hovering[0]:
            hovering[0] = True
            if on_enter: on_enter()
        return event.action

    def _leave(event):
        if hovering[0]:
            hovering[0] = False
            if on_leave: on_leave()

    widget.dnd_bind('<<DropEnter>>', _enter)
    widget.dnd_bind('<<DropPosition>>', _position)
    widget.dnd_bind('<<DropLeave>>', _leave)


def register_drop_multiple(widget, on_drop, on_enter=None, on_leave=None):
    """Untuk Tab Kunci: Menerima banyak file/folder sekaligus."""
    if not DND_AVAILABLE: return
    widget.drop_target_register(DND_FILES)

    def _on_drop(event):
        if on_leave: on_leave()
        paths = parse_drop_paths(event.data)
        if paths:
            # Filter hanya path yang benar-benar ada di OS
            valid_paths = [p for p in paths if os.path.exists(p)]
            if valid_paths:
                on_drop(valid_paths)

    widget.dnd_bind('<<Drop>>', _on_drop)
    _bind_hover(widget, on_enter, on_leave)


def register_drop_file(widget, on_drop, extension: str = ".locked", on_enter=None, on_leave=None):
    """Untuk Tab Buka: Hanya menerima 1 file .locked."""
    if not DND_AVAILABLE: return
    widget.drop_target_register(DND_FILES)

    def _on_drop(event):
        if on_leave: on_leave()
        paths = parse_drop_paths(event.data)
        if paths:
            p = paths[0] # Ambil yang pertama aja
            if os.path.isfile(p) and p.lower().endswith(extension):
                on_drop(p)

    widget.dnd_bind('<<Drop>>', _on_drop)
    _bind_hover(widget, on_enter, on_leave)