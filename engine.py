import os
import shutil
import uuid
import tempfile
import zipfile
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

# 4 MB — sweet spot antara performa dan memory usage (was 16 MB)
CHUNK_SIZE = 4 * 1024 * 1024


def secure_delete(path):
    """
    Menimpa file dengan nol sebelum dihapus.
    PERHATIAN: Tidak menjamin penghapusan aman di SSD/NVMe karena wear leveling.
    Hanya efektif untuk HDD konvensional.
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


def buat_kunci_dari_password(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
        backend=default_backend()
    )
    return kdf.derive(password.encode())


def _cb(progress_cb, val: float):
    """Panggil callback dengan aman — tidak crash jika None atau error."""
    if progress_cb:
        try:
            progress_cb(max(0.0, min(1.0, val)))
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
def kunci_brankas_logic(nama_folder, password_kamu, hapus_asli=False, progress_cb=None):
    """
    Mengompresi folder ke ZIP lalu mengenkripsi dengan AES-256-GCM.

    Progress:
        0.00 – 0.40  : fase ZIP
        0.40 – 1.00  : fase enkripsi
    """
    id_temp     = uuid.uuid4().hex[:8]
    file_zip    = os.path.join(tempfile.gettempdir(), f"brankas_temp_{id_temp}.zip")
    path_simpan = None

    try:
        salt  = os.urandom(16)
        kunci = buat_kunci_dari_password(password_kamu, salt)
        nonce = os.urandom(12)

        # Tentukan nama file output yang unik
        while True:
            nama_file_kunci = f"brankas_{uuid.uuid4().hex[:8]}.locked"
            path_simpan = os.path.join(os.path.dirname(nama_folder), nama_file_kunci)
            if not os.path.exists(path_simpan):
                break

        abs_path   = os.path.abspath(nama_folder)
        parent_dir = os.path.dirname(abs_path)
        target_dir = os.path.basename(abs_path)

        # ── Phase 1: ZIP (0% → 40%) ──────────────────────────────────────────
        total_bytes = sum(
            os.path.getsize(os.path.join(r, f))
            for r, _, files in os.walk(nama_folder)
            for f in files
        ) or 1

        bytes_zipped = 0
        with zipfile.ZipFile(file_zip, 'w', zipfile.ZIP_STORED) as zipf:
            for root, _, files in os.walk(nama_folder):
                for file in files:
                    fp      = os.path.join(root, file)
                    arcname = os.path.relpath(fp, start=parent_dir)
                    zipf.write(fp, arcname)
                    bytes_zipped += os.path.getsize(fp)
                    _cb(progress_cb, 0.40 * bytes_zipped / total_bytes)

        # ── Phase 2: Enkripsi (40% → 100%) ───────────────────────────────────
        zip_size  = os.path.getsize(file_zip) or 1
        bytes_enc = 0

        encryptor = Cipher(
            algorithms.AES(kunci),
            modes.GCM(nonce),
            backend=default_backend()
        ).encryptor()

        with open(path_simpan, "wb") as fk:
            fk.write(salt)
            fk.write(nonce)

            nama_bytes   = target_dir.encode('utf-8')
            panjang_nama = len(nama_bytes).to_bytes(2, byteorder='big')
            fk.write(encryptor.update(panjang_nama + nama_bytes))

            with open(file_zip, "rb") as fz:
                while True:
                    chunk = fz.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    fk.write(encryptor.update(chunk))
                    bytes_enc += len(chunk)
                    _cb(progress_cb, 0.40 + 0.60 * bytes_enc / zip_size)

            encryptor.finalize()
            fk.write(encryptor.tag)

        _cb(progress_cb, 1.0)
        secure_delete(file_zip)

        if hapus_asli:
            secure_delete(nama_folder)

        size_mb = os.path.getsize(path_simpan) / (1024 * 1024)
        return True, f"Berhasil!\n\nNama Brankas: {nama_file_kunci}\nUkuran: {size_mb:.1f} MB"

    except Exception as e:
        if os.path.exists(file_zip):
            secure_delete(file_zip)
        if path_simpan and os.path.exists(path_simpan):
            os.remove(path_simpan)
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
def buka_brankas_logic(path_file_kunci, password_kamu, force=False, progress_cb=None):
    """
    Mendekripsi file .locked dan mengekstrak folder di dalamnya.

    Progress:
        0.00 – 0.80  : fase dekripsi
        0.80 – 1.00  : fase ekstrak ZIP
    """
    file_zip_sementara = None
    try:
        ukuran_total   = os.path.getsize(path_file_kunci)
        # Struktur: [16 salt][12 nonce][ciphertext][16 GCM tag]
        panjang_cipher = ukuran_total - 44

        with open(path_file_kunci, "rb") as fk:
            salt  = fk.read(16)
            nonce = fk.read(12)

            fk.seek(-16, os.SEEK_END)
            tag = fk.read(16)
            fk.seek(28)

            kunci     = buat_kunci_dari_password(password_kamu, salt)
            decryptor = Cipher(
                algorithms.AES(kunci),
                modes.GCM(nonce, tag),
                backend=default_backend()
            ).decryptor()

            bytes_left     = panjang_cipher
            first_chunk_sz = min(1024, bytes_left)
            first_chunk    = fk.read(first_chunk_sz)
            bytes_left    -= first_chunk_sz

            decrypted_first = decryptor.update(first_chunk)

            # FIX: GCM update() tidak throw untuk wrong password — garbage output
            # yang kemudian gagal di-parse. Wrap parse agar return WRONG_PW bukan ERROR.
            try:
                panjang_nama = int.from_bytes(decrypted_first[:2], byteorder='big')
                if panjang_nama > 512:
                    # Nama folder tidak mungkin > 512 karakter — pasti garbage
                    return "WRONG_PW", None
                nama_folder_tujuan = decrypted_first[2:2 + panjang_nama].decode('utf-8')
            except Exception:
                return "WRONG_PW", None

            base_dir         = os.path.dirname(path_file_kunci)
            path_tujuan_full = os.path.join(base_dir, nama_folder_tujuan)

            if os.path.exists(path_tujuan_full) and not force:
                return "OVERWRITE", nama_folder_tujuan

            id_temp            = uuid.uuid4().hex[:8]
            file_zip_sementara = os.path.join(tempfile.gettempdir(), f"dec_temp_{id_temp}.zip")
            bytes_decrypted    = first_chunk_sz

            # ── Phase 1: Dekripsi (0% → 80%) ─────────────────────────────────
            with open(file_zip_sementara, "wb") as fz:
                fz.write(decrypted_first[2 + panjang_nama:])
                _cb(progress_cb, 0.80 * bytes_decrypted / (panjang_cipher or 1))

                while bytes_left > 0:
                    chunk       = fk.read(min(CHUNK_SIZE, bytes_left))
                    bytes_left -= len(chunk)
                    fz.write(decryptor.update(chunk))
                    bytes_decrypted += len(chunk)
                    _cb(progress_cb, 0.80 * bytes_decrypted / (panjang_cipher or 1))

            # finalize() di sinilah GCM memverifikasi tag — ini deteksi wrong password yang benar
            try:
                decryptor.finalize()
            except Exception:
                secure_delete(file_zip_sementara)
                return "WRONG_PW", None

        # ── Phase 2: Ekstrak (80% → 100%) ────────────────────────────────────
        _cb(progress_cb, 0.85)
        with zipfile.ZipFile(file_zip_sementara, 'r') as zip_ref:
            zip_ref.extractall(base_dir)

        secure_delete(file_zip_sementara)
        _cb(progress_cb, 1.0)
        return "SUCCESS", nama_folder_tujuan

    except Exception as e:
        if file_zip_sementara and os.path.exists(file_zip_sementara):
            secure_delete(file_zip_sementara)
        return "ERROR", str(e)