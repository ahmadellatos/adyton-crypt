"""
core/vault_stream.py
Format envelope (header/keyslot) dan streaming crypto chunked AEAD.
"""

import hashlib
import io
import os
from collections.abc import Callable
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from loguru import logger

from .constants import (
    ARGON2ID_ITERATIONS,
    ARGON2ID_LANES,
    ARGON2ID_MAX_ITERATIONS,
    ARGON2ID_MAX_LANES,
    ARGON2ID_MAX_MEMORY_COST_KIB,
    ARGON2ID_MEMORY_COST_KIB,
    ARGON2ID_PARAMS_SIZE,
    CHUNK_RECORD_HEADER_SIZE,
    CHUNK_SIZE,
    FILE_ID_SIZE,
    FLAG_HINT,
    GENERIC_FAILURE_MESSAGE,
    KDF_ID_ARGON2ID,
    KEYFILE_CREATED_MESSAGE,
    KEYFILE_MAX_SIZE,
    MAGIC_BYTES,
    MASTER_KEY_SIZE,
    MAX_HINT_LENGTH,
    MAX_KEYSLOTS,
    RECORD_TYPE_DATA,
    RECORD_TYPE_FINAL,
    SALT_SIZE,
    SLOT_TYPE_PASSWORD_KEYFILE,
    SLOT_TYPE_RECOVERY_CODE,
    SUPPORTED_FLAGS,
    TAG_SIZE,
    VALID_SLOT_TYPES,
    VERSION,
    WRAP_NONCE_SIZE,
    WRAPPED_KEY_SIZE,
    VaultStatus,
)
from .crypto import (
    combine_kek_with_keyfile,
    derive_key_for_kdf,
    generate_keyfile_bytes,
    normalize_recovery_code,
    safe_cb,
)


def _encode_argon2id_params(
    iterations: int = ARGON2ID_ITERATIONS,
    lanes: int = ARGON2ID_LANES,
    memory_cost: int = ARGON2ID_MEMORY_COST_KIB,
) -> bytes:
    """Encode parameter Argon2id ke format keyslot."""
    for value in (iterations, lanes, memory_cost):
        if value <= 0 or value >= 2**32:
            raise ValueError("Argon2id parameter out of range.")

    return (
        iterations.to_bytes(4, byteorder="big")
        + lanes.to_bytes(4, byteorder="big")
        + memory_cost.to_bytes(4, byteorder="big")
    )


def _decode_argon2id_params(params: bytes) -> dict[str, int]:
    """Decode parameter Argon2id dari keyslot."""
    if len(params) != ARGON2ID_PARAMS_SIZE:
        raise ValueError("Invalid Argon2id parameter size.")

    iterations = int.from_bytes(params[0:4], byteorder="big")
    lanes = int.from_bytes(params[4:8], byteorder="big")
    memory_cost = int.from_bytes(params[8:12], byteorder="big")

    if iterations <= 0 or lanes <= 0 or memory_cost <= 0:
        raise ValueError("Invalid Argon2id parameter.")

    # Reject crafted headers that request absurd cost factors. Without this an
    # attacker-supplied vault could make Argon2id allocate gigabytes/terabytes
    # and OOM the app the moment someone tries to open it.
    if (
        iterations > ARGON2ID_MAX_ITERATIONS
        or lanes > ARGON2ID_MAX_LANES
        or memory_cost > ARGON2ID_MAX_MEMORY_COST_KIB
    ):
        raise ValueError("Argon2id parameters exceed the safe maximum.")

    return {
        "iterations": iterations,
        "lanes": lanes,
        "memory_cost": memory_cost,
    }


def _record_header(record_type: int, record_index: int, plaintext_len: int) -> bytes:
    if not 0 <= record_type <= 255:
        raise ValueError("record_type out of range")
    if record_index < 0 or record_index >= 2**64:
        raise ValueError("record_index out of range")
    if plaintext_len < 0 or plaintext_len >= 2**32:
        raise ValueError("plaintext_len out of range")
    return (
        record_type.to_bytes(1, byteorder="big")
        + record_index.to_bytes(8, byteorder="big")
        + plaintext_len.to_bytes(4, byteorder="big")
    )


def _record_nonce(record_index: int) -> bytes:
    """Nonce AES-GCM 96-bit deterministik per record.

    Aman karena key setiap vault unik dari salt+password, dan setiap record
    dalam vault yang sama memakai indeks unik yang diverifikasi berurutan.
    """
    if record_index < 0 or record_index >= 2**96:
        raise ValueError("record_index out of nonce range")
    return record_index.to_bytes(12, byteorder="big")


def _record_aad(header_context: bytes, record_header: bytes) -> bytes:
    return header_context + record_header


def _write_record(
    file_handle,
    aesgcm: AESGCM,
    header_context: bytes,
    record_type: int,
    record_index: int,
    plaintext: bytes,
) -> None:
    record_header = _record_header(record_type, record_index, len(plaintext))
    ciphertext = aesgcm.encrypt(
        _record_nonce(record_index),
        plaintext,
        _record_aad(header_context, record_header),
    )
    file_handle.write(record_header)
    file_handle.write(ciphertext)


def _read_exact(file_handle, size: int) -> bytes:
    data = file_handle.read(size)
    if len(data) != size:
        raise InvalidTag
    return data


def _read_record_header(file_handle) -> tuple[int, int, int, bytes]:
    raw = _read_exact(file_handle, CHUNK_RECORD_HEADER_SIZE)
    record_type = raw[0]
    record_index = int.from_bytes(raw[1:9], byteorder="big")
    plaintext_len = int.from_bytes(raw[9:13], byteorder="big")
    return record_type, record_index, plaintext_len, raw


class ChunkedAEADEncryptingStream:
    """File-like writer untuk tarfile yang mengenkripsi output sebagai record AEAD.

    Setiap data chunk dienkripsi dengan AES-GCM sendiri. Saat dibuka, setiap
    chunk harus lolos verifikasi tag sebelum plaintext chunk itu boleh ditulis
    ke disk. Ini menghindari two-pass decrypt tanpa kembali ke plaintext
    unauthenticated.
    """

    def __init__(
        self,
        target_file,
        aesgcm: AESGCM,
        header_context: bytes,
        progress_cb,
        total_bytes: int,
        is_cancelled: Callable[[], bool] = None,
        chunk_size: int = CHUNK_SIZE,
    ):
        self.target_file = target_file
        self.aesgcm = aesgcm
        self.header_context = header_context
        self.progress_cb = progress_cb
        self.total_bytes = total_bytes
        self.chunk_size = chunk_size
        self.is_cancelled = is_cancelled
        self.buffer = bytearray()
        self.bytes_written = 0
        self.record_index = 1  # index 0 dipakai metadata
        self._last_pct = 0.0
        self._finished = False

    def write(self, data: bytes):
        if self.is_cancelled and self.is_cancelled():
            raise InterruptedError("Operation cancelled by the user.")

        self.buffer.extend(data)
        self.bytes_written += len(data)

        while len(self.buffer) >= self.chunk_size:
            self._emit_data_record(bytes(self.buffer[: self.chunk_size]))
            del self.buffer[: self.chunk_size]

        if self.total_bytes > 0:
            pct = min(0.85, 0.05 + 0.80 * (self.bytes_written / self.total_bytes))
            if pct - self._last_pct >= 0.005:
                safe_cb(self.progress_cb, pct)
                self._last_pct = pct

        return len(data)

    def _emit_data_record(self, plaintext: bytes) -> None:
        _write_record(
            self.target_file,
            self.aesgcm,
            self.header_context,
            RECORD_TYPE_DATA,
            self.record_index,
            plaintext,
        )
        self.record_index += 1

    def flush(self):
        # Jangan flush buffer parsial di sini; tarfile bisa memanggil flush() untuk
        # sinkronisasi, bukan sebagai akhir stream. Record parsial ditutup di finish().
        return

    def close(self):
        return

    def finish(self) -> None:
        if self._finished:
            return
        if self.buffer:
            self._emit_data_record(bytes(self.buffer))
            self.buffer.clear()
        _write_record(
            self.target_file,
            self.aesgcm,
            self.header_context,
            RECORD_TYPE_FINAL,
            self.record_index,
            b"",
        )
        self._finished = True


class ChunkedAEADDecryptingStream(io.RawIOBase):
    """File-like READER: menarik record AEAD dari vault & meng-yield plaintext.

    Counterpart baca dari ``ChunkedAEADEncryptingStream``. Setiap record diverifikasi
    tag-nya (``aesgcm.decrypt``) SEBELUM plaintext-nya diekspos, jadi konsumen
    (``tarfile`` mode ``r|``) tak pernah melihat plaintext yang belum terautentikasi.
    Membaca record DATA berurutan mulai ``start_index`` sampai ``RECORD_TYPE_FINAL``;
    index tak berurutan / tipe tak dikenal / byte sisa setelah FINAL → ``InvalidTag``.

    Dipakai untuk browse (list isi tanpa menulis ke disk) dan ekstrak selektif: reader
    yang sama mengalirkan payload tar terdekripsi ke tarfile streaming. Pembacaan
    berhenti begitu tarfile mencapai akhir arsip — record FINAL & cek byte-sisa hanya
    tereksekusi bila stream benar-benar dibaca sampai habis (mis. verifikasi penuh),
    dan itu bukan tujuan browse.
    """

    def __init__(
        self,
        fk,
        aesgcm: AESGCM,
        header_context: bytes,
        stored_chunk_size: int,
        total_size: int,
        start_index: int = 1,
        progress_cb=None,
        is_cancelled: Callable[[], bool] | None = None,
    ):
        super().__init__()
        self._fk = fk
        self._aesgcm = aesgcm
        self._header_context = header_context
        self._chunk_size = stored_chunk_size
        self._total_size = total_size
        self._expected_index = start_index
        self._progress_cb = progress_cb
        self._is_cancelled = is_cancelled
        self._buf = bytearray()
        self._eof = False
        self._last_pct = 0.0

    def readable(self) -> bool:
        return True

    def _pull_record(self) -> bool:
        """Baca & dekripsi satu record ke buffer. Return False saat FINAL/EOF."""
        if self._eof:
            return False
        if self._is_cancelled and self._is_cancelled():
            raise InterruptedError("Operation cancelled by the user.")

        record_type, record_index, plaintext_len, record_header = _read_record_header(self._fk)
        if record_index != self._expected_index:
            raise InvalidTag

        if record_type == RECORD_TYPE_DATA:
            if plaintext_len <= 0 or plaintext_len > self._chunk_size:
                raise InvalidTag
            ciphertext = _read_exact(self._fk, plaintext_len + TAG_SIZE)
            plaintext = self._aesgcm.decrypt(
                _record_nonce(record_index),
                ciphertext,
                _record_aad(self._header_context, record_header),
            )
            if len(plaintext) != plaintext_len:
                raise InvalidTag
            self._buf.extend(plaintext)
            self._expected_index += 1

            if self._total_size > 0 and self._progress_cb:
                pct = min(0.98, 0.05 + 0.93 * (self._fk.tell() / self._total_size))
                if pct - self._last_pct >= 0.005:
                    safe_cb(self._progress_cb, pct)
                    self._last_pct = pct
            return True

        if record_type == RECORD_TYPE_FINAL:
            if plaintext_len != 0:
                raise InvalidTag
            ciphertext = _read_exact(self._fk, TAG_SIZE)
            final_plaintext = self._aesgcm.decrypt(
                _record_nonce(record_index),
                ciphertext,
                _record_aad(self._header_context, record_header),
            )
            if final_plaintext != b"":
                raise InvalidTag
            self._expected_index += 1
            self._eof = True
            # Tidak boleh ada byte sisa setelah FINAL.
            if self._fk.tell() != self._total_size:
                raise InvalidTag
            return False

        raise InvalidTag

    def readinto(self, b) -> int:
        # Isi buffer dari SATU record bila kosong; readinto boleh mengembalikan
        # kurang dari len(b) — tarfile/zstd mengulang read() sampai cukup atau EOF.
        while not self._buf and not self._eof:
            self._pull_record()
        if not self._buf:
            return 0
        n = min(len(b), len(self._buf))
        b[:n] = self._buf[:n]
        del self._buf[:n]
        return n


class _CompressProgressWriter:
    """File-like di SISI INPUT tar saat kompresi aktif.

    Saat vault dikompresi, ``ChunkedAEADEncryptingStream`` menerima byte TERKOMPRESI,
    sehingga progress berbasis output-nya tak lagi mencerminkan kemajuan terhadap data
    sumber. Wrapper ini duduk di antara ``tarfile`` dan zstd writer: meneruskan byte tar
    mentah ke zstd, melaporkan progress berdasarkan byte UNCOMPRESSED yang ditulis, dan
    mengecek pembatalan per-write (lebih responsif daripada menunggu blok zstd ter-flush
    ke lapisan enkripsi). Saat kompresi aktif, progress di ``ChunkedAEADEncryptingStream``
    dimatikan (``progress_cb=None``) agar tidak ada laporan ganda.
    """

    def __init__(self, dest, progress_cb, total_bytes: int, is_cancelled: Callable[[], bool]):
        self.dest = dest
        self.progress_cb = progress_cb
        self.total_bytes = total_bytes
        self.is_cancelled = is_cancelled
        self.written = 0
        self._last_pct = 0.0

    def write(self, data: bytes) -> int:
        if self.is_cancelled and self.is_cancelled():
            raise InterruptedError("Operation cancelled by the user.")
        self.dest.write(data)
        self.written += len(data)
        if self.total_bytes > 0:
            pct = min(0.85, 0.05 + 0.80 * (self.written / self.total_bytes))
            if pct - self._last_pct >= 0.005:
                safe_cb(self.progress_cb, pct)
                self._last_pct = pct
        return len(data)

    def flush(self):
        # Jangan paksa zstd menutup blok di tiap flush tarfile (sinkronisasi, bukan
        # akhir stream); frame difinalkan saat zstd writer ditutup oleh pemanggil.
        return


# ── Format Envelope / Keyslot ───────────────────────────────────────────────────
#
# Master Key (MK) acak mengenkripsi seluruh record. MK dibungkus per-credential di
# keyslot. Karena key record adalah MK yang tidak berubah, ganti password / tambah
# recovery cukup menulis ulang region keyslot — record tidak perlu dienkripsi ulang.


def _record_context(file_id: bytes, chunk_size: int, flags: int) -> bytes:
    """AAD setiap record. Sengaja TANPA keyslot/hint agar re-key murah.

    FILE_ID acak mengikat record ke vault ini; chunk_size & flags ditetapkan saat
    pembuatan dan tidak berubah seumur hidup vault.
    """
    return (
        MAGIC_BYTES
        + VERSION
        + file_id
        + chunk_size.to_bytes(4, byteorder="big")
        + flags.to_bytes(4, byteorder="big")
    )


def _slot_meta(
    slot_type: int,
    kdf_id: int,
    kdf_params_raw: bytes,
    salt: bytes,
    wrap_nonce: bytes,
) -> bytes:
    """Bagian keyslot yang dibawa di AAD wrap (semua kecuali wrapped master key)."""
    return (
        bytes([slot_type, kdf_id])
        + len(kdf_params_raw).to_bytes(2, byteorder="big")
        + kdf_params_raw
        + salt
        + wrap_nonce
    )


def _slot_wrap_aad(file_id: bytes, hint_bytes: bytes, meta: bytes) -> bytes:
    """AAD untuk membungkus MK: mengikat ke identitas vault + hint + parameter slot.

    Mencegah slot ditukar antar-vault (file_id), mencegah parameter slot
    (kdf, salt, nonce) diutak-atik diam-diam, dan **mengikat password hint** yang
    disimpan plaintext di header. Tanpa ini hint tidak terautentikasi sama sekali:
    siapa pun yang bisa menulis ke file vault bisa mengganti teks hint (mis. untuk
    menyesatkan korban) tanpa terdeteksi. Dengan hint masuk AAD, tamper apa pun
    pada hint membuat unwrap MK gagal → dilaporkan wrong_password (fail-closed).

    ``hint_bytes`` adalah byte mentah hint persis seperti di header (kosong untuk
    vault tanpa hint). Vault tanpa hint menghasilkan AAD identik dengan format
    sebelum hint diautentikasi, jadi vault lama tanpa hint tetap bisa dibuka.
    """
    return MAGIC_BYTES + VERSION + file_id + hint_bytes + meta


def _derive_slot_kek(
    slot_type: int,
    secret: str,
    salt: bytes,
    kdf_id: int,
    kdf_params: dict[str, int],
    keyfile_material: bytes | None = None,
) -> bytes | None:
    """Turunkan Key Encryption Key untuk satu slot dari credential-nya.

    Untuk slot 2FA (``SLOT_TYPE_PASSWORD_KEYFILE``) KEK = gabung(Argon2id(password),
    keyfile); bila keyfile tak tersedia, kembalikan ``None`` agar pemanggil melewati
    slot ini TANPA menjalankan Argon2id yang mahal (mis. saat user memakai recovery
    key di vault 2FA — keyfile tidak diperlukan untuk slot recovery).
    """
    if slot_type == SLOT_TYPE_PASSWORD_KEYFILE and keyfile_material is None:
        return None
    if slot_type == SLOT_TYPE_RECOVERY_CODE:
        secret = normalize_recovery_code(secret)
    kek = derive_key_for_kdf(secret, salt, kdf_id, kdf_params)
    if slot_type == SLOT_TYPE_PASSWORD_KEYFILE:
        kek = combine_kek_with_keyfile(kek, keyfile_material)
    return kek


def _build_keyslot(
    master_key: bytes,
    file_id: bytes,
    slot_type: int,
    secret: str,
    kdf_params: dict[str, int] | None = None,
    hint_bytes: bytes = b"",
    keyfile_material: bytes | None = None,
) -> bytes:
    """Bangun satu keyslot lengkap (meta + wrapped MK) dari sebuah credential.

    ``kdf_params`` opsional memilih kekuatan Argon2id (level KDF); bila None dipakai
    default vault. Parameter di-encode lalu di-decode lagi agar nilainya tervalidasi
    & dibatasi ceiling sebelum dipakai. ``hint_bytes`` (mentah, byte hint di header)
    diikat ke AAD wrap agar hint terautentikasi — pemanggil WAJIB memakai byte hint
    yang sama persis dengan yang ditulis ``_build_header``. ``keyfile_material`` WAJIB
    untuk slot ``SLOT_TYPE_PASSWORD_KEYFILE`` (2FA) dan diabaikan untuk slot lain.
    """
    salt = os.urandom(SALT_SIZE)
    wrap_nonce = os.urandom(WRAP_NONCE_SIZE)
    if kdf_params:
        kdf_params_raw = _encode_argon2id_params(
            kdf_params["iterations"], kdf_params["lanes"], kdf_params["memory_cost"]
        )
    else:
        kdf_params_raw = _encode_argon2id_params()
    kdf_params = _decode_argon2id_params(kdf_params_raw)
    kek = _derive_slot_kek(slot_type, secret, salt, KDF_ID_ARGON2ID, kdf_params, keyfile_material)
    if kek is None:
        # Hanya terjadi bila slot keyfile dibangun tanpa keyfile — bug pemanggil.
        raise ValueError("A keyfile is required to build this keyslot.")
    meta = _slot_meta(slot_type, KDF_ID_ARGON2ID, kdf_params_raw, salt, wrap_nonce)
    wrapped = AESGCM(kek).encrypt(wrap_nonce, master_key, _slot_wrap_aad(file_id, hint_bytes, meta))
    return meta + wrapped


def _load_keyfile_material(keyfile_path: str) -> bytes:
    """Baca keyfile dari disk (stream, dibatasi ukuran) → material 32-byte.

    Melempar ``ValueError`` dengan pesan path-free yang aman ditampilkan ke user bila
    file kosong, terlalu besar, atau tak terbaca. Hashing streaming agar keyfile besar
    tak dimuat seluruhnya ke memori; di atas ``KEYFILE_MAX_SIZE`` ditolak.
    """
    path = Path(keyfile_path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError("The keyfile could not be read. Check that it still exists.") from exc
    if size == 0:
        raise ValueError("The keyfile is empty. Choose a non-empty file or generate one.")
    if size > KEYFILE_MAX_SIZE:
        raise ValueError("The keyfile is too large. Choose a file under 64 MB.")
    hasher = hashlib.sha256()
    read_total = 0
    try:
        with path.open("rb") as fk:
            for block in iter(lambda: fk.read(1024 * 1024), b""):
                # Cap di dalam loop, jangan hanya andalkan stat() di atas: file bisa
                # tumbuh antara stat dan baca (TOCTOU), atau menunjuk file spesial/
                # virtual yang stat-nya kecil tapi mengalir tanpa henti. Tolak alih-alih
                # mem-hash tanpa batas (mencegah hang / baca raksasa saat membuka vault).
                read_total += len(block)
                if read_total > KEYFILE_MAX_SIZE:
                    raise ValueError("The keyfile is too large. Choose a file under 64 MB.")
                hasher.update(block)
    except OSError as exc:
        raise ValueError("The keyfile could not be read. Check that it still exists.") from exc
    return hasher.digest()


def generate_keyfile(keyfile_path: str) -> tuple[VaultStatus, str]:
    """Tulis keyfile acak entropi tinggi ke ``keyfile_path``.

    Menolak menimpa file yang sudah ada (mencegah merusak keyfile/dokumen lain).
    """
    path = Path(keyfile_path)
    try:
        if path.exists():
            return VaultStatus.ERROR, "A file with that name already exists. Choose another name."
        # x = exclusive create: gagal bila file muncul di antara cek dan tulis (race).
        with path.open("xb") as fk:
            fk.write(generate_keyfile_bytes())
            fk.flush()
            os.fsync(fk.fileno())
        return (VaultStatus.SUCCESS, KEYFILE_CREATED_MESSAGE)
    except FileExistsError:
        return VaultStatus.ERROR, "A file with that name already exists. Choose another name."
    except Exception:
        logger.exception("Gagal membuat keyfile.")
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE


def _slot_bytes(slot: dict) -> bytes:
    """Serialisasi ulang slot hasil parse ke bytes on-disk."""
    return slot["meta"] + slot["wrapped"]


def _build_header(
    file_id: bytes,
    chunk_size: int,
    flags: int,
    hint_bytes: bytes,
    slots: list[bytes],
) -> bytes:
    """Rakit header lengkap (core + hint opsional + daftar keyslot)."""
    if not 1 <= len(slots) <= MAX_KEYSLOTS:
        raise ValueError("keyslot count out of range")
    parts = [
        MAGIC_BYTES,
        VERSION,
        file_id,
        chunk_size.to_bytes(4, byteorder="big"),
        flags.to_bytes(4, byteorder="big"),
    ]
    if flags & FLAG_HINT:
        parts.append(len(hint_bytes).to_bytes(2, byteorder="big") + hint_bytes)
    parts.append(bytes([len(slots)]))
    parts.extend(slots)
    return b"".join(parts)


def _parse_header(fk) -> dict:
    """Parse header dari file yang sudah dibaca MAGIC+VERSION-nya.

    Melempar ``InvalidTag`` bila file terpotong (pemanggil melaporkannya sebagai
    vault korup/tak lengkap) dan ``ValueError`` untuk header yang strukturnya
    tidak valid.
    """
    file_id = _read_exact(fk, FILE_ID_SIZE)
    chunk_size = int.from_bytes(_read_exact(fk, 4), byteorder="big")
    flags = int.from_bytes(_read_exact(fk, 4), byteorder="big")

    if flags & ~SUPPORTED_FLAGS:
        raise ValueError("This vault flag isn't supported by this app version.")

    hint = None
    hint_bytes = b""
    if flags & FLAG_HINT:
        hint_len = int.from_bytes(_read_exact(fk, 2), byteorder="big")
        if hint_len > MAX_HINT_LENGTH:
            raise ValueError("Invalid vault hint length; the file may be corrupted.")
        # Simpan byte mentah: dipakai apa adanya untuk AAD wrap (hint terautentikasi)
        # agar tidak bergantung pada round-trip decode/encode yang bisa lossy.
        hint_bytes = _read_exact(fk, hint_len)
        hint = hint_bytes.decode("utf-8", "replace")

    slot_count = _read_exact(fk, 1)[0]
    if not 1 <= slot_count <= MAX_KEYSLOTS:
        raise ValueError("Invalid keyslot count; the file may be corrupted.")

    slots: list[dict] = []
    for _ in range(slot_count):
        slot_type = _read_exact(fk, 1)[0]
        kdf_id = _read_exact(fk, 1)[0]
        params_len = int.from_bytes(_read_exact(fk, 2), byteorder="big")
        kdf_params_raw = _read_exact(fk, params_len)
        salt = _read_exact(fk, SALT_SIZE)
        wrap_nonce = _read_exact(fk, WRAP_NONCE_SIZE)
        wrapped = _read_exact(fk, WRAPPED_KEY_SIZE)

        if slot_type not in VALID_SLOT_TYPES or kdf_id != KDF_ID_ARGON2ID:
            raise ValueError("This vault keyslot isn't supported by this app version.")

        slots.append(
            {
                "slot_type": slot_type,
                "kdf_id": kdf_id,
                "kdf_params_raw": kdf_params_raw,
                "kdf_params": _decode_argon2id_params(kdf_params_raw),
                "salt": salt,
                "wrap_nonce": wrap_nonce,
                "wrapped": wrapped,
                "meta": _slot_meta(slot_type, kdf_id, kdf_params_raw, salt, wrap_nonce),
            }
        )

    return {
        "file_id": file_id,
        "chunk_size": chunk_size,
        "flags": flags,
        "hint": hint,
        "hint_bytes": hint_bytes,
        "slots": slots,
        "header_end": fk.tell(),
    }


def _recover_master_key(
    secret: str,
    file_id: bytes,
    hint_bytes: bytes,
    slots: list[dict],
    keyfile_material: bytes | None = None,
) -> bytes | None:
    """Coba credential terhadap tiap slot; kembalikan MK pada slot pertama yang cocok.

    Slot dicoba berurutan, jadi password benar di slot 0 hanya butuh satu derivasi
    KDF. Hanya secret yang salah yang membayar derivasi semua slot. ``hint_bytes``
    (byte hint mentah dari header) ikut diautentikasi via AAD wrap.

    ``keyfile_material`` (bila ada) dipakai untuk slot 2FA. Slot keyfile dilewati
    tanpa biaya KDF saat keyfile tak tersedia, sehingga recovery key tetap membuka
    vault 2FA tanpa keyfile (jalur break-glass).
    """
    for slot in slots:
        kek = _derive_slot_kek(
            slot["slot_type"],
            secret,
            slot["salt"],
            slot["kdf_id"],
            slot["kdf_params"],
            keyfile_material,
        )
        if kek is None:
            continue
        try:
            master_key = AESGCM(kek).decrypt(
                slot["wrap_nonce"],
                slot["wrapped"],
                _slot_wrap_aad(file_id, hint_bytes, slot["meta"]),
            )
        except (InvalidTag, ValueError):
            continue
        if len(master_key) == MASTER_KEY_SIZE:
            return master_key
    return None


def _hint_bytes_from_header(hdr: dict) -> bytes:
    """Byte hint mentah persis seperti tersimpan di header.

    Dipakai untuk DUA hal yang harus konsisten byte-per-byte: menulis ulang header
    (``_build_header``) dan mengikat hint ke AAD wrap (``_slot_wrap_aad``). Kalau
    keduanya tidak identik, MK tidak akan bisa di-unwrap setelah header ditulis ulang.
    """
    return hdr.get("hint_bytes", b"")
