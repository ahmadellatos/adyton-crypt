"""
Utilitas umum untuk UI Adyton Crypt.
Berisi helper untuk progress bar dan estimasi waktu.
"""

import time


def _format_eta_seconds(remaining: float) -> str:
    """Format ETA dengan pembulatan stabil dan bahasa yang mudah dipahami."""
    if remaining < 1:
        return "Hampir selesai"
    if remaining < 60:
        return f"sekitar {int(round(remaining))} detik lagi"

    minutes = int(remaining // 60)
    seconds = int(remaining % 60)
    if minutes < 60:
        return f"sekitar {minutes}m {seconds:02d}s lagi"

    hours = minutes // 60
    minutes = minutes % 60
    return f"sekitar {hours}j {minutes:02d}m lagi"


def get_eta_string(start_time: float | None, progress: float) -> str:
    """Hitung estimasi waktu tersisa sederhana.

    Dipertahankan untuk kompatibilitas lama. Untuk UI live gunakan
    ``ProgressETA`` karena estimator itu menahan progress mundur dan memakai
    smoothed transfer rate agar ETA tidak meloncat-loncat.
    """
    if start_time is None or progress <= 0.01:
        return "Menghitung..."

    elapsed = time.monotonic() - start_time
    if elapsed < 0.75:
        return "Menghitung..."

    remaining = max((elapsed / max(progress, 1e-6)) - elapsed, 0.0)
    return _format_eta_seconds(remaining)


class ProgressETA:
    """Estimator ETA stateful untuk progress UI.

    Callback crypto bisa datang dengan jarak tidak rata dan beberapa fase punya
    bobot berbeda. Estimator ini menjaga progress tetap monotonik, menghaluskan
    rate memakai exponential moving average, dan menahan display ETA agar tidak
    berubah terlalu sering.
    """

    def __init__(self, smoothing: float = 0.25, min_update_interval: float = 0.75):
        self.smoothing = max(0.01, min(1.0, smoothing))
        self.min_update_interval = max(0.1, min_update_interval)
        self.reset()

    def reset(self) -> None:
        self.start_time: float | None = None
        self.last_time: float | None = None
        self.last_display_time: float | None = None
        self.last_progress = 0.0
        self.smoothed_rate: float | None = None
        self.last_eta = "Menghitung..."

    def update(self, progress: float) -> str:
        now = time.monotonic()
        progress = max(0.0, min(0.999, float(progress)))

        if self.start_time is None:
            self.start_time = now
            self.last_time = now
            self.last_progress = progress
            return self.last_eta

        # Jangan biarkan callback fase sebelumnya membuat progress mundur di UI.
        if progress < self.last_progress:
            progress = self.last_progress

        elapsed = now - self.start_time
        if progress <= 0.015 or elapsed < 1.0:
            self.last_progress = progress
            self.last_time = now
            return self.last_eta

        if self.last_time is not None:
            dt = max(now - self.last_time, 1e-6)
            dp = max(progress - self.last_progress, 0.0)
            if dp > 0:
                instant_rate = dp / dt
                if self.smoothed_rate is None:
                    self.smoothed_rate = instant_rate
                else:
                    self.smoothed_rate = (
                        self.smoothing * instant_rate + (1.0 - self.smoothing) * self.smoothed_rate
                    )

        self.last_progress = progress
        self.last_time = now

        if not self.smoothed_rate or self.smoothed_rate <= 1e-9:
            return self.last_eta

        if (
            self.last_display_time is not None
            and now - self.last_display_time < self.min_update_interval
            and progress < 0.985
        ):
            return self.last_eta

        remaining = max((1.0 - progress) / self.smoothed_rate, 0.0)
        self.last_eta = _format_eta_seconds(remaining)
        self.last_display_time = now
        return self.last_eta


def progress_stage_label(val: float, mode: str) -> str:
    """Label tahap proses yang mudah dipahami user.

    Nilai progress dari core merepresentasikan beberapa fase internal. UI tidak
    perlu memaparkan detail teknis; cukup beri konteks supaya proses besar
    terasa transparan dan tidak seperti macet.
    """
    val = max(0.0, min(1.0, float(val)))

    if mode == "buka":
        if val < 0.08:
            return "Memverifikasi password"
        if val < 0.88:
            return "Mengekstrak data"
        if val < 0.97:
            return "Memindahkan hasil"
        return "Membersihkan file sementara"

    if val < 0.08:
        return "Menyiapkan data"
    if val < 0.88:
        return "Mengenkripsi data"
    if val < 0.97:
        return "Menulis brankas"
    return "Finalisasi"


def format_progress_label(val: float, mode: str, eta_str: str) -> tuple[str, str]:
    """
    Return (title, subtitle) untuk BigActionBtn.setTextLabels
    berdasarkan progress dan mode ('buka' atau 'kunci').
    """
    val = max(0.0, min(1.0, float(val)))
    pct = int(val * 100)
    stage = progress_stage_label(val, mode)

    if mode == "buka":
        title = "Membuka brankas"
        subtitle = f"{pct}% • {eta_str} • {stage} • Klik untuk membatalkan"
    else:
        title = "Mengunci brankas"
        subtitle = f"{pct}% • {eta_str} • {stage} • Klik untuk membatalkan"

    return title, subtitle


def format_user_error(status, message: str | None, mode: str) -> str:
    """Ubah status core menjadi pesan UI yang lebih ramah dan actionable."""
    status_name = getattr(status, "name", str(status)).lower()
    raw = (message or "").strip()

    if "wrong_password" in status_name:
        return (
            "Password tidak cocok, file bukan brankas Adyton yang valid, "
            "atau isi brankas sudah rusak. Periksa password dan coba lagi."
        )

    if "cancelled" in status_name:
        return "Proses dibatalkan. File tujuan belum diganti."

    prefix = "Tidak bisa membuka brankas" if mode == "buka" else "Tidak bisa mengunci brankas"
    if not raw:
        return f"{prefix}. Coba ulangi proses atau periksa ruang disk."

    # Hindari label teknis seperti “Error:” di UI utama, tapi tetap tampilkan detail
    # yang memang sudah dibuat aman oleh core.
    raw = raw.removeprefix("Error:").strip()
    return f"{prefix}. {raw}"


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
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur_radius)
    shadow.setXOffset(0)
    shadow.setYOffset(y_offset)
    shadow.setColor(QColor(0, 0, 0, opacity))
    widget.setGraphicsEffect(shadow)


def apply_cancelling_state(button) -> None:
    """Set tombol aksi ke state 'sedang membatalkan'."""
    button.setTextLabels("Membatalkan proses", "Membersihkan file sementara...")
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
