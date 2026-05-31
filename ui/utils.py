"""
Utilitas umum untuk UI Adyton Crypt.
Berisi helper untuk progress bar dan estimasi waktu.
"""

import time


def get_eta_string(start_time: float | None, progress: float) -> str:
    """Hitung estimasi waktu tersisa berdasarkan progress."""
    if start_time is None or progress <= 0.01:
        return "Menghitung..."

    elapsed = time.time() - start_time
    if elapsed < 0.5:
        return "Menghitung..."

    estimated_total = elapsed / progress
    remaining = estimated_total - elapsed

    if remaining < 1:
        return "Hampir selesai"
    elif remaining < 60:
        return f"~{int(remaining)} detik lagi"
    else:
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        return f"~{minutes}m {seconds}s lagi"


def format_progress_label(val: float, mode: str, eta_str: str) -> tuple[str, str]:
    """
    Return (title, subtitle) untuk BigActionBtn.setTextLabels
    berdasarkan progress dan mode ('buka' atau 'kunci').
    """
    if val <= 0.85:
        pct = int(val * 100)
        if mode == "buka":
            title = "MEMBUKA DATA..."
        else:  # kunci
            title = "MENGUNCI DATA..."
        subtitle = f"{pct}%  •  {eta_str}"
    else:
        final_pct = int((val - 0.85) / 0.15 * 100)
        title = "FINALISASI..."
        subtitle = f"{final_pct}%  •  {eta_str}"

    return title, subtitle


def format_file_size(n: int) -> str:
    """Return human-readable file size string (B, KB, MB, GB, TB)."""
    if n <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    val = float(n)
    for u in units:
        if val < 1024 or u == "TB":
            if u == "B":
                return f"{int(val)} {u}"
            if val >= 100:
                return f"{val:.1f} {u}"
            return f"{val:.2f} {u}"
        val /= 1024
    return f"{val:.1f} TB"


def apply_shadow(widget, blur_radius=20, y_offset=6, opacity=60):
    """Apply a drop shadow effect to a widget. Pure utility function."""
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    from PySide6.QtGui import QColor

    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur_radius)
    shadow.setXOffset(0)
    shadow.setYOffset(y_offset)
    shadow.setColor(QColor(0, 0, 0, opacity))
    widget.setGraphicsEffect(shadow)


def apply_cancelling_state(button) -> None:
    """Set tombol aksi ke state 'sedang membatalkan'."""
    button.setTextLabels("MEMBATALKAN...", "Harap tunggu...")
    button.setEnabled(False)


def start_crypto_worker(worker, progress_callback, finished_callback) -> None:
    """
    Menghubungkan signal worker dan menjalankannya.
    Digunakan di TabBuka dan TabKunci.
    """
    worker.progress.connect(progress_callback)
    worker.finished.connect(finished_callback)
    worker.finished.connect(worker.deleteLater)
    worker.start()
