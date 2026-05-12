"""
core/vault.py
Logika utama: kunci folder/file (enkripsi) dan buka brankas (dekripsi).
Dioptimasi dengan Single-Pass I/O Streaming menggunakan Tarfile + Memory Buffering.
Multi-file support: Menggabungkan banyak file/folder menjadi satu brankas.
"""
import os
import shutil
import uuid
import tempfile
import tarfile

from .crypto import CHUNK_SIZE, derive_key, make_encryptor, make_decryptor, safe_cb

# ── File Operations ───────────────────────────────────────────────────────────

def secure_delete(path: str):
    """
    Menimpa file dengan nol sebelum dihapus.
    PERHATIAN: Tidak menjamin penghapusan aman di SSD/NVMe karena wear leveling.
    """
    if not os.path.exists(path):
        return
    if os.path.isfile(path):
        try:
            size = os.path.getsize(path)
            with open(path, "r+b") as f:
                written = 0
                while written < size:
                    chunk = min(CHUNK_SIZE, size - written)
                    f.write(b'\x00' * chunk)
                    written += chunk
            os.remove(path)
        except Exception:
            pass
    elif os.path.isdir(path):
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                secure_delete(os.path.join(root, name))
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
        try:
            os.rmdir(path)
        except OSError:
            shutil.rmtree(path, ignore_errors=True)


# ── Custom Stream Classes ─────────────────────────────────────────────────────

class EncryptingStream:
    """Pipa memori ajaib yang dilengkapi Buffer (Waduk)."""
    def __init__(self, target_file, encryptor, progress_cb, total_bytes):
        self.target_file  = target_file
        self.encryptor    = encryptor
        self.progress_cb  = progress_cb
        self.total_bytes  = total_bytes
        self.bytes_written = 0
        self.buffer       = bytearray()
        self._last_pct    = 0.0
        # FIX: flag idempoten agar flush() aman dipanggil berkali-kali.
        # tarfile memanggil close() → flush() saat context manager selesai,
        # dan kunci_brankas() juga memanggil flush() eksplisit setelahnya.
        # Tanpa flag ini, encryptor.update(b"") dipanggil dua kali.
        self._flushed     = False

    def write(self, data: bytes):
        self.buffer.extend(data)
        self.bytes_written += len(data)

        if self.total_bytes > 0:
            pct = min(0.89, 0.05 + 0.85 * (self.bytes_written / self.total_bytes))
            if pct - self._last_pct >= 0.005:
                safe_cb(self.progress_cb, pct)
                self._last_pct = pct

        # FIX: gunakan CHUNK_SIZE langsung, bukan self.chunk_size yang
        # hanya menduplikasi konstanta modul tanpa nilai tambah.
        if len(self.buffer) >= CHUNK_SIZE:
            encrypted = self.encryptor.update(bytes(self.buffer))
            if encrypted:
                self.target_file.write(encrypted)
            self.buffer.clear()

        return len(data)

    def flush(self):
        # Guard idempoten: abaikan panggilan kedua dan seterusnya.
        if self._flushed:
            return
        self._flushed = True
        if self.buffer:
            encrypted = self.encryptor.update(bytes(self.buffer))
            if encrypted:
                self.target_file.write(encrypted)
            self.buffer.clear()

    def close(self):
        self.flush()


# ── Logic Pembantu ────────────────────────────────────────────────────────────

def _hitung_total_size(paths: list[str]) -> int:
    """Menghitung total ukuran byte dari kumpulan file/folder."""
    total = 0
    for p in paths:
        if os.path.isfile(p):
            total += os.path.getsize(p)
        elif os.path.isdir(p):
            total += sum(
                os.path.getsize(os.path.join(r, f))
                for r, _, files in os.walk(p)
                for f in files if not os.path.islink(os.path.join(r, f))
            )
    return total or 1

# ── Public API ────────────────────────────────────────────────────────────────

def kunci_brankas(paths: list[str], path_simpan: str, password: str,
                  hapus_asli: bool = False,
                  progress_cb=None) -> tuple[bool, str]:
    """
    Mengunci satu atau banyak file/folder ke dalam satu file .locked.

    FIX: jika path_simpan sudah ada, file lama di-backup dulu ke .bak.
    Kalau enkripsi gagal, file lama di-restore. Kalau berhasil, .bak dihapus.
    Ini mencegah kehilangan data jika user menimpa .locked yang sudah ada.
    """
    path_backup = path_simpan + ".bak"
    backup_dibuat = False

    try:
        # Backup file lama jika ada sebelum mulai menulis
        if os.path.exists(path_simpan):
            os.rename(path_simpan, path_backup)
            backup_dibuat = True

        salt  = os.urandom(16)
        nonce = os.urandom(12)

        key = derive_key(password, salt)
        safe_cb(progress_cb, 0.05)

        total_size = _hitung_total_size(paths)
        encryptor  = make_encryptor(key, nonce)

        # Tentukan nama root di dalam arsip
        is_single_file = len(paths) == 1 and os.path.isfile(paths[0])
        is_single_dir  = len(paths) == 1 and os.path.isdir(paths[0])

        if is_single_file:
            nama_virtual = os.path.basename(paths[0])
            target_dir   = ""
        elif is_single_dir:
            nama_virtual = os.path.basename(os.path.abspath(paths[0]))
            target_dir   = ""
        else:
            nama_file    = os.path.basename(path_simpan)
            target_dir   = os.path.splitext(nama_file)[0] or "Brankas_Rahasia"
            nama_virtual = target_dir

        nama_bytes   = nama_virtual.encode('utf-8')
        panjang_nama = len(nama_bytes).to_bytes(2, byteorder='big')

        with open(path_simpan, "wb") as fk:
            fk.write(salt)
            fk.write(nonce)
            fk.write(encryptor.update(panjang_nama + nama_bytes))

            out_stream = EncryptingStream(fk, encryptor, progress_cb, total_size)

            with tarfile.open(fileobj=out_stream, mode='w|') as tar:
                for p in paths:
                    if not os.path.exists(p):
                        continue
                    nama_item = os.path.basename(os.path.abspath(p))
                    arcname   = os.path.join(target_dir, nama_item) if target_dir else nama_item
                    tar.add(p, arcname=arcname)

            # flush() eksplisit ini aman karena EncryptingStream._flushed
            # sudah di-set True oleh tarfile saat close() dipanggil.
            # Baris ini tidak melakukan apa-apa selain menjadi dokumentasi intent.
            out_stream.flush()

            fk.write(encryptor.finalize())
            fk.write(encryptor.tag)

        safe_cb(progress_cb, 0.90)

        # Enkripsi berhasil — hapus backup
        if backup_dibuat and os.path.exists(path_backup):
            os.remove(path_backup)

        if hapus_asli:
            safe_cb(progress_cb, 0.95)
            for p in paths:
                secure_delete(p)

        size_mb = os.path.getsize(path_simpan) / (1024 * 1024)
        safe_cb(progress_cb, 1.0)
        return True, f"Brankas berhasil dikunci!\nUkuran: {size_mb:.1f} MB"

    except Exception as exc:
        # Gagal — hapus file korup dan restore backup jika ada
        if os.path.exists(path_simpan):
            os.remove(path_simpan)
        if backup_dibuat and os.path.exists(path_backup):
            os.rename(path_backup, path_simpan)
        return False, str(exc)


def buka_brankas(locked_path: str, password: str,
                 force: bool = False,
                 progress_cb=None) -> tuple[str, str | None]:
    temp_archive = None
    try:
        total_size = os.path.getsize(locked_path)
        if total_size < 44:
            return "ERROR", "File terlalu kecil/rusak."

        cipher_len = total_size - 44

        with open(locked_path, "rb") as fk:
            salt  = fk.read(16)
            nonce = fk.read(12)
            fk.seek(-16, os.SEEK_END)
            tag   = fk.read(16)
            fk.seek(28)

            key       = derive_key(password, salt)
            decryptor = make_decryptor(key, nonce, tag)

            first_sz        = min(1024, cipher_len)
            first_chunk     = fk.read(first_sz)
            bytes_remaining = cipher_len - first_sz

            decrypted_first = decryptor.update(first_chunk)

            try:
                panjang_nama = int.from_bytes(decrypted_first[:2], byteorder='big')
                if panjang_nama > 512:
                    return "WRONG_PW", None
                if len(decrypted_first) < 2 + panjang_nama:
                    return "ERROR", "File brankas rusak atau terpotong."
                nama_folder = decrypted_first[2:2 + panjang_nama].decode('utf-8')
            except Exception:
                return "WRONG_PW", None

            base_dir    = os.path.dirname(locked_path)
            path_tujuan = os.path.join(base_dir, nama_folder)

            if os.path.exists(path_tujuan):
                if not force:
                    return "OVERWRITE", nama_folder
                else:
                    if os.path.isfile(path_tujuan):
                        secure_delete(path_tujuan)

            id_temp      = uuid.uuid4().hex[:8]
            temp_archive = os.path.join(tempfile.gettempdir(), f"dec_temp_{id_temp}.tmp")
            bytes_dec    = first_sz
            last_pct     = 0.0

            with open(temp_archive, "wb") as ft:
                ft.write(decrypted_first[2 + panjang_nama:])
                safe_cb(progress_cb, 0.80 * bytes_dec / (cipher_len or 1))

                while bytes_remaining > 0:
                    chunk            = fk.read(min(CHUNK_SIZE, bytes_remaining))
                    bytes_remaining -= len(chunk)
                    ft.write(decryptor.update(chunk))
                    bytes_dec += len(chunk)

                    pct = 0.80 * bytes_dec / (cipher_len or 1)
                    if pct - last_pct >= 0.005:
                        safe_cb(progress_cb, pct)
                        last_pct = pct

            try:
                decryptor.finalize()
            except Exception:
                secure_delete(temp_archive)
                return "WRONG_PW", None

        safe_cb(progress_cb, 0.85)

        try:
            with tarfile.open(temp_archive, 'r') as tar:
                tar.extractall(path=base_dir)
        except tarfile.ReadError:
            secure_delete(temp_archive)
            return "ERROR", "Format arsip di dalam brankas rusak atau tidak dikenali."

        secure_delete(temp_archive)
        safe_cb(progress_cb, 1.0)
        return "SUCCESS", nama_folder

    except Exception as exc:
        if temp_archive and os.path.exists(temp_archive):
            secure_delete(temp_archive)
        return "ERROR", str(exc)