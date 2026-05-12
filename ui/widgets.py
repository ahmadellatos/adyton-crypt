"""
ui/widgets.py
Komponen UI yang dipakai bersama oleh kedua tab.
"""
import re
import customtkinter as ctk

from .theme import (
    CLR_CARD, CLR_MUTED, CLR_NOTIF_OK, CLR_NOTIF_ERR, CLR_NOTIF_WARN,
    STRENGTH_COLORS, STRENGTH_LABELS, FONT_BODY, FONT_SMALL,
)


def pw_strength(pw: str) -> int:
    """
    Nilai kekuatan password: -1 (kosong), 0 (lemah) hingga 3 (sangat kuat).
    """
    if not pw:
        return -1
    score = 0
    if len(pw) >= 8:
        score += 1
    if re.search(r"[A-Z]", pw) and re.search(r"[a-z]", pw):
        score += 1
    if re.search(r"\d", pw):
        score += 1
    if re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>/?\\|`~]", pw):
        score += 1
    return min(score, 3)


def make_card(parent, padx: int = 20, pady: tuple = (0, 12)) -> ctk.CTkFrame:
    """Card frame dengan background CLR_CARD."""
    f = ctk.CTkFrame(parent, fg_color=CLR_CARD, corner_radius=10)
    f.pack(fill="x", padx=padx, pady=pady)
    return f


class NotifBar(ctk.CTkFrame):
    """
    Strip notifikasi yang selalu ada di layout.
    Tidak menyebabkan elemen lain bergeser saat muncul/hilang.
    Dilengkapi fitur Auto-Hide yang aman dari Race Condition.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, height=40, corner_radius=8,
                         fg_color="transparent", **kwargs)
        self.pack_propagate(False)
        self.lbl = ctk.CTkLabel(
            self, text="", font=FONT_BODY,
            wraplength=380, anchor="center",
        )
        self.lbl.place(relx=0.5, rely=0.5, anchor="center")

        self._timer_id = None

    def show(self, kind: str, msg: str, auto_hide_ms: int = 0):
        if self._timer_id is not None:
            self.after_cancel(self._timer_id)
            self._timer_id = None

        bg, fg = {
            "ok":   CLR_NOTIF_OK,
            "err":  CLR_NOTIF_ERR,
            "warn": CLR_NOTIF_WARN,
        }.get(kind, ("transparent", CLR_MUTED))
        self.configure(fg_color=bg)
        self.lbl.configure(text=msg, text_color=fg)

        if auto_hide_ms > 0:
            self._timer_id = self.after(auto_hide_ms, self.clear)

    def clear(self):
        if self._timer_id is not None:
            self.after_cancel(self._timer_id)
            self._timer_id = None

        self.configure(fg_color="transparent")
        self.lbl.configure(text="")


class ProgressRow(ctk.CTkFrame):
    """
    Progress bar + label persentase dalam satu baris.
    """

    def __init__(self, parent, accent_color: str, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.bar = ctk.CTkProgressBar(self, height=8, corner_radius=4,
                                      progress_color=accent_color)
        self.bar.set(0)
        self.bar.pack(side="left", expand=True, fill="x", padx=(0, 10))

        self.lbl = ctk.CTkLabel(self, text="0%", width=38,
                                font=FONT_SMALL, text_color=CLR_MUTED, anchor="e")
        self.lbl.pack(side="right")

    def update(self, val: float):
        self.bar.set(val)
        self.lbl.configure(text=f"{int(val * 100)}%")

    def reset(self):
        self.bar.set(0)
        self.lbl.configure(text="0%")

    def make_callback(self, root_widget) -> callable:
        """Buat progress callback yang thread-safe via after()."""
        def cb(val: float):
            root_widget.after(0, lambda: self.update(val))
        return cb