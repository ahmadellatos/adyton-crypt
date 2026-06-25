"""
Utilitas umum untuk UI Adyton Crypt.
Berisi helper untuk progress bar dan estimasi waktu.
"""

import os
import sys
import time


def _format_eta_seconds(remaining: float) -> str:
    """Format ETA dengan pembulatan stabil dan bahasa yang mudah dipahami."""
    if remaining < 1:
        return "Almost done"
    if remaining < 60:
        return f"about {int(round(remaining))} sec left"

    minutes = int(remaining // 60)
    seconds = int(remaining % 60)
    if minutes < 60:
        return f"about {minutes}m {seconds:02d}s left"

    hours = minutes // 60
    minutes = minutes % 60
    return f"about {hours}h {minutes:02d}m left"


def get_eta_string(start_time: float | None, progress: float) -> str:
    """Hitung estimasi waktu tersisa sederhana.

    Dipertahankan untuk kompatibilitas lama. Untuk UI live gunakan
    ``ProgressETA`` karena estimator itu menahan progress mundur dan memakai
    smoothed transfer rate agar ETA tidak meloncat-loncat.
    """
    if start_time is None or progress <= 0.01:
        return "Calculating…"

    elapsed = time.monotonic() - start_time
    if elapsed < 0.75:
        return "Calculating…"

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
        self.last_eta = "Calculating…"

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
            return "Verifying password"
        if val < 0.88:
            return "Extracting data"
        if val < 0.97:
            return "Moving result"
        return "Cleaning up temp files"

    if val < 0.08:
        return "Preparing data"
    if val < 0.88:
        return "Encrypting data"
    if val < 0.97:
        return "Writing vault"
    return "Finalizing"


def format_progress_label(val: float, mode: str, eta_str: str) -> tuple[str, str]:
    """
    Return (title, subtitle) untuk BigActionBtn.setTextLabels
    berdasarkan progress dan mode ('buka' atau 'kunci').
    """
    val = max(0.0, min(1.0, float(val)))
    pct = int(val * 100)
    stage = progress_stage_label(val, mode)

    if mode == "buka":
        title = "Opening vault"
        subtitle = f"{pct}% • {eta_str} • {stage} • Click to cancel"
    else:
        title = "Locking vault"
        subtitle = f"{pct}% • {eta_str} • {stage} • Click to cancel"

    return title, subtitle


def format_user_error(status, message: str | None, mode: str) -> str:
    """Ubah status core menjadi pesan UI yang lebih ramah dan actionable."""
    status_name = getattr(status, "name", str(status)).lower()
    raw = (message or "").strip()

    if "wrong_password" in status_name:
        return (
            "Wrong password, or the vault file is invalid or corrupted. "
            "Double-check your password and try again."
        )

    if "cancelled" in status_name:
        return "Operation cancelled. No changes were made to your files."

    prefix = "Couldn't open the vault" if mode == "buka" else "Couldn't lock the vault"
    if not raw:
        return f"{prefix}. Try again or check your disk space."

    # Hindari label teknis seperti “Error:” di UI utama, tapi tetap tampilkan detail
    # yang memang sudah dibuat aman oleh core.
    raw = raw.removeprefix("Error:").strip()
    return f"{prefix}. {raw}"


def path_size(path: str) -> int:
    """Ukuran total sebuah path dalam byte.

    File → ukuran file. Folder → jumlah rekursif ukuran semua file di dalamnya
    (ini yang akan dikunci ke vault), bukan ukuran entri direktori (yang 0 di
    Windows). Symlink dilewati agar tak menghitung ganda / loop. File yang tak
    terbaca diabaikan; mengembalikan 0 bila path tak ada / tak terbaca.
    """
    try:
        if os.path.isfile(path):
            return os.path.getsize(path)
        if os.path.isdir(path):
            total = 0
            # followlinks=False (default) → os.walk tak menuruni folder symlink.
            for root, _dirs, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        if not os.path.islink(fp):
                            total += os.path.getsize(fp)
                    except OSError:
                        pass
            return total
    except OSError:
        pass
    return 0


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
    button.setTextLabels("Cancelling", "Cleaning up temp files…")
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


# ── Clipboard auto-clear ────────────────────────────────────────────────────────

# Jendela waktu default sebelum clipboard dibersihkan otomatis. Cukup lama untuk
# pindah aplikasi lalu paste, cukup pendek untuk membatasi paparan teks sensitif
# (mis. plaintext hasil dekripsi Tab Teks) di clipboard sistem yang dibaca app lain.
CLIPBOARD_AUTO_CLEAR_MS = 30_000


def _set_clipboard_sensitive(clipboard, text: str) -> None:
    """Taruh ``text`` ke clipboard, dan di Windows tandai sebagai sensitif.

    Auto-clear hanya membersihkan isi clipboard *aktif*; ia tidak bisa menghapus
    salinan yang sudah terlanjur masuk Clipboard History (Win+V) atau ter-sinkron
    ke Cloud Clipboard antar-perangkat. Untuk teks sensitif (plaintext hasil
    dekripsi, recovery code) kita pasang format clipboard khusus Windows yang
    memberi tahu OS agar TIDAK menyimpannya ke history maupun cloud.

    Di platform lain (atau bila QMimeData tak tersedia) jatuh ke ``setText`` biasa.
    """
    if sys.platform != "win32":
        clipboard.setText(text)
        return
    try:
        from PySide6.QtCore import QByteArray, QMimeData

        mime = QMimeData()
        mime.setText(text)
        # Nama format clipboard terdaftar resmi Windows. Kehadiran
        # ExcludeClipboardContentFromMonitorProcessing saja sudah cukup; dua
        # lainnya eksplisit menolak history (Win+V) & sinkronisasi cloud.
        zero = QByteArray(b"\x00\x00\x00\x00")  # DWORD 0
        mime.setData("ExcludeClipboardContentFromMonitorProcessing", zero)
        mime.setData("CanIncludeInClipboardHistory", zero)
        mime.setData("CanUploadToCloudClipboard", zero)
        clipboard.setMimeData(mime)
    except Exception:
        # Jangan sampai gagal menyalin hanya karena penanda privasi bermasalah.
        clipboard.setText(text)


class _ClipboardAutoClear:
    """Salin teks ke clipboard, lalu hapus otomatis setelah timeout.

    Hanya menghapus bila isi clipboard MASIH persis sama dengan yang kita taruh,
    supaya tidak menimpa sesuatu yang user salin setelahnya. Memakai satu QTimer
    singleton: tiap salin baru me-reset jadwal clear yang sebelumnya.
    """

    def __init__(self):
        self._timer = None
        self._pending: str | None = None

    @staticmethod
    def _clipboard():
        # Import lazy mengikuti pola apply_shadow di modul ini — agar ui.utils
        # tidak hard-depend ke PySide6 hanya untuk diimpor.
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        return app.clipboard() if app is not None else None

    def copy(self, text: str, timeout_ms: int = CLIPBOARD_AUTO_CLEAR_MS) -> None:
        clipboard = self._clipboard()
        if clipboard is None:
            return
        _set_clipboard_sensitive(clipboard, text)
        self._pending = text

        if timeout_ms <= 0:
            # Auto-clear timer dimatikan (setting "Off"), tapi _pending TETAP dilacak
            # agar auto-lock idle masih bisa panic-clear salinan sensitif milik kita
            # tanpa menyentuh clipboard aplikasi lain.
            if self._timer is not None:
                self._timer.stop()
            return

        if self._timer is None:
            from PySide6.QtCore import QTimer

            self._timer = QTimer()
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._clear_if_unchanged)

        self._timer.stop()
        self._timer.start(max(0, int(timeout_ms)))

    def _clear_if_unchanged(self) -> None:
        clipboard = self._clipboard()
        if clipboard is not None and self._pending is not None:
            if clipboard.text() == self._pending:
                clipboard.clear()
        self._pending = None

    def clear_if_ours(self) -> bool:
        """Bersihkan clipboard HANYA bila isinya masih sama dengan salinan sensitif
        terakhir milik kita. Kembalikan True bila benar-benar dibersihkan.

        Dipakai auto-lock idle agar panic-clear tidak menghapus clipboard yang user
        salin dari aplikasi lain.
        """
        clipboard = self._clipboard()
        if clipboard is None or self._pending is None:
            return False
        if clipboard.text() == self._pending:
            clipboard.clear()
            self._pending = None
            return True
        return False


_clipboard_auto_clear = _ClipboardAutoClear()

# Sentinel: bila timeout tidak diberikan eksplisit, ambil dari Settings (detik).
_USE_SETTING = -1


def copy_to_clipboard_auto_clear(text: str, timeout_ms: int = _USE_SETTING) -> None:
    """Salin ``text`` ke clipboard sistem lalu jadwalkan auto-clear.

    Tanpa ``timeout_ms`` eksplisit, durasinya diambil dari Settings (0 = matikan
    auto-clear). Tiap panggilan me-reset timer clear sebelumnya, jadi hanya salinan
    terakhir yang dijadwalkan.
    """
    if timeout_ms == _USE_SETTING:
        try:
            from ui.settings_store import get_settings

            timeout_ms = get_settings().clipboard_seconds() * 1000
        except Exception:
            timeout_ms = CLIPBOARD_AUTO_CLEAR_MS
    _clipboard_auto_clear.copy(text, timeout_ms)


def clear_clipboard_if_ours() -> bool:
    """Panic-clear clipboard untuk auto-lock idle: hanya hapus bila isinya masih
    salinan sensitif terakhir dari Adyton (plaintext dekripsi / recovery code).
    Tidak pernah menghapus konten yang user salin dari aplikasi lain.
    """
    return _clipboard_auto_clear.clear_if_ours()
