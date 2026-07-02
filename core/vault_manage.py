"""
core/vault_manage.py
Manajemen credential vault: ganti password, tambah/hapus recovery key, tambah/hapus keyfile (2FA).
"""

import contextlib
import os
import shutil
import time
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from loguru import logger

from .constants import (
    CHUNK_SIZE,
    DISK_OVERHEAD_BYTES,
    GENERIC_FAILURE_MESSAGE,
    MASTER_KEY_SIZE,
    MAX_KEYSLOTS,
    OLD_TEMP_MAX_AGE_SECONDS,
    PASSWORD_SLOT_TYPES,
    RECOVERY_SLOT_TYPES,
    SLOT_TYPE_PASSWORD,
    SLOT_TYPE_PASSWORD_KEYFILE,
    SLOT_TYPE_RECOVERY_CODE,
    SLOT_TYPE_RECOVERY_PASSPHRASE,
    VaultStatus,
)
from .vault_extract import _make_unique_replace_backup_path
from .vault_inspect import _read_header_from_path
from .vault_stream import (
    _build_header,
    _build_keyslot,
    _derive_slot_kek,
    _hint_bytes_from_header,
    _load_keyfile_material,
    _recover_master_key,
    _slot_bytes,
    _slot_wrap_aad,
)


def _load_for_management(
    path: Path,
    secret: str,
    keyfile_material: bytes | None = None,
) -> tuple[VaultStatus, str | None, dict | None, bytes | None]:
    """Buka header + recover Master Key untuk operasi manajemen credential.

    Return ``(status, message_or_None, header_or_None, master_key_or_None)``.
    Status SUCCESS berarti ``header`` dan ``master_key`` terisi. ``keyfile_material``
    dipakai untuk membuka slot 2FA (lihat ``_recover_master_key``).
    """
    try:
        hdr = _read_header_from_path(path)
    except ValueError as exc:
        if str(exc) == "wrong_format":
            return (
                VaultStatus.ERROR,
                "This vault was made by a different version of Adyton Crypt and "
                "can't be managed here. Please update the app.",
                None,
                None,
            )
        return VaultStatus.ERROR, str(exc), None, None
    except FileNotFoundError:
        return VaultStatus.ERROR, "The vault file could not be found.", None, None
    except Exception:
        logger.exception("Gagal membaca header untuk manajemen.")
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE, None, None

    master_key = _recover_master_key(
        secret, hdr["file_id"], _hint_bytes_from_header(hdr), hdr["slots"], keyfile_material
    )
    if master_key is None:
        return VaultStatus.WRONG_PASSWORD, None, None, None

    return VaultStatus.SUCCESS, None, hdr, master_key


def _load_keyfile_material_optional(keyfile_path: str | None) -> tuple[bytes | None, str | None]:
    """Load keyfile bila path diberikan. Return ``(material, error_message)``.

    ``material`` None bila tak ada keyfile; ``error_message`` non-None bila path
    diberikan tapi gagal dibaca (pesan path-free aman ditampilkan).
    """
    if not keyfile_path:
        return None, None
    try:
        return _load_keyfile_material(keyfile_path), None
    except ValueError as exc:
        return None, str(exc)


def _read_header_for_management(path: Path) -> tuple[VaultStatus, str | None, dict | None]:
    """Baca header vault untuk operasi manajemen TANPA membukanya (tanpa credential).

    Memetakan error baca header ke pesan path-free yang aman ditampilkan. Dipakai
    operasi yang perlu inspeksi slot sebelum unlock (mis. tambah/hapus keyfile yang
    membuka slot password secara spesifik, bukan slot apa pun).
    """
    try:
        return VaultStatus.SUCCESS, None, _read_header_from_path(path)
    except ValueError as exc:
        if str(exc) == "wrong_format":
            return (
                VaultStatus.ERROR,
                "This vault was made by a different version of Adyton Crypt and "
                "can't be managed here. Please update the app.",
                None,
            )
        return VaultStatus.ERROR, str(exc), None
    except FileNotFoundError:
        return VaultStatus.ERROR, "The vault file could not be found.", None
    except Exception:
        logger.exception("Gagal membaca header untuk manajemen.")
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE, None


def _rewrite_header_full(
    path: Path, old_header_end: int, new_header: bytes
) -> tuple[VaultStatus, str]:
    """Tulis ulang header yang panjangnya berubah, lewat temp file + atomic replace.

    Dipakai saat menambah/menghapus keyslot (header bertambah/berkurang). Record
    di belakang header disalin apa adanya — O(ukuran vault), tapi aman karena
    file asli baru diganti setelah temp lengkap & ter-fsync.
    """
    tmp: Path | None = None
    try:
        # Sapu temp .replace-* yatim dari rewrite sebelumnya yang crash. Isinya
        # salinan vault ini (yang asli tetap utuh karena os.replace tak sempat
        # terjadi), jadi aman dihapus setelah melewati umur minimum. HANYA file
        # yang cocok pola nama vault ini — backup folder overwrite (dibuat
        # _extract_and_place_vault untuk path lain) tidak tersentuh.
        for stale in path.parent.glob(f"{path.name}.replace-*"):
            with contextlib.suppress(OSError):
                if (
                    stale.is_file()
                    and time.time() - stale.stat().st_mtime > OLD_TEMP_MAX_AGE_SECONDS
                ):
                    stale.unlink()

        free = shutil.disk_usage(path.parent).free
        if free < path.stat().st_size + DISK_OVERHEAD_BYTES:
            return VaultStatus.ERROR, "Not enough storage space to update the vault."

        tmp = _make_unique_replace_backup_path(path)
        with path.open("rb") as src, tmp.open("wb") as dst:
            dst.write(new_header)
            src.seek(old_header_end)
            while True:
                chunk = src.read(CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())

        os.replace(tmp, path)
        tmp = None
        return VaultStatus.SUCCESS, "Vault updated successfully."
    except Exception:
        logger.exception("Gagal menulis ulang header (full rewrite).")
        if tmp is not None:
            with contextlib.suppress(Exception):
                tmp.unlink(missing_ok=True)
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE


def _unlock_password_slot(
    hdr: dict, password: str, keyfile_material: bytes | None = None
) -> bytes | None:
    """Unwrap MK lewat slot PASSWORD vault secara spesifik (bukan slot recovery).

    Dipakai operasi yang mengubah faktor password (tambah/hapus keyfile) sehingga
    yakin secret yang diberikan benar-benar password — bukan recovery key yang
    kebetulan membuka slot lain — sebelum slot password ditulis ulang.
    """
    pw_slot = next((s for s in hdr["slots"] if s["slot_type"] in PASSWORD_SLOT_TYPES), None)
    if pw_slot is None:
        return None
    kek = _derive_slot_kek(
        pw_slot["slot_type"],
        password,
        pw_slot["salt"],
        pw_slot["kdf_id"],
        pw_slot["kdf_params"],
        keyfile_material,
    )
    if kek is None:
        return None
    try:
        master_key = AESGCM(kek).decrypt(
            pw_slot["wrap_nonce"],
            pw_slot["wrapped"],
            _slot_wrap_aad(hdr["file_id"], _hint_bytes_from_header(hdr), pw_slot["meta"]),
        )
    except (InvalidTag, ValueError):
        return None
    return master_key if len(master_key) == MASTER_KEY_SIZE else None


def change_password(
    vault_path: str,
    old_password: str,
    new_password: str,
    keyfile_path: str | None = None,
) -> tuple[VaultStatus, str | None]:
    """Ganti password vault tanpa mengenkripsi ulang data.

    Hanya keyslot password yang ditulis ulang (panjang identik), jadi operasi ini
    O(ukuran header), bukan O(ukuran vault). ``old_password`` boleh berupa password
    lama ATAU recovery key — apa pun yang berhasil membuka salah satu slot.

    Untuk vault 2FA (slot password dilindungi keyfile), ``keyfile_path`` WAJIB
    diberikan: slot password baru tetap dilindungi keyfile yang sama, jadi 2FA tidak
    diam-diam dilepas. (Melepas keyfile adalah aksi terpisah ``remove_keyfile``.)
    """
    if not new_password or not new_password.strip():
        return VaultStatus.ERROR, "New password cannot be empty."

    keyfile_material, kf_error = _load_keyfile_material_optional(keyfile_path)
    if kf_error:
        return VaultStatus.ERROR, kf_error

    path = Path(vault_path)
    status, message, hdr = _read_header_for_management(path)
    if status != VaultStatus.SUCCESS:
        return status, message

    pw_index = next(
        (i for i, s in enumerate(hdr["slots"]) if s["slot_type"] in PASSWORD_SLOT_TYPES),
        None,
    )
    if pw_index is None:
        return VaultStatus.ERROR, "This vault has no password slot to change."

    pw_slot_type = hdr["slots"][pw_index]["slot_type"]
    # Cek kebutuhan keyfile SEBELUM unlock agar pesan membantu (bukan WRONG_PASSWORD):
    # slot password baru tetap dilindungi keyfile, jadi keyfile wajib untuk membangunnya.
    if pw_slot_type == SLOT_TYPE_PASSWORD_KEYFILE and keyfile_material is None:
        return (
            VaultStatus.ERROR,
            "This vault uses a keyfile. Select the keyfile to change its password.",
        )

    master_key = _recover_master_key(
        old_password, hdr["file_id"], _hint_bytes_from_header(hdr), hdr["slots"], keyfile_material
    )
    if master_key is None:
        return VaultStatus.WRONG_PASSWORD, None

    # Pertahankan level KDF slot lama agar header tetap sepanjang semula (invariant
    # re-key in-place) dan kekuatan yang dipilih user tidak diam-diam diturunkan.
    slot_bytes = [_slot_bytes(s) for s in hdr["slots"]]
    slot_bytes[pw_index] = _build_keyslot(
        master_key,
        hdr["file_id"],
        pw_slot_type,
        new_password,
        kdf_params=hdr["slots"][pw_index]["kdf_params"],
        hint_bytes=_hint_bytes_from_header(hdr),
        keyfile_material=keyfile_material,
    )
    new_header = _build_header(
        hdr["file_id"], hdr["chunk_size"], hdr["flags"], _hint_bytes_from_header(hdr), slot_bytes
    )

    # Re-key tidak boleh mengubah panjang header (slot password fixed-size). Kalau
    # berubah, batalkan tanpa menulis apa pun demi keamanan.
    if len(new_header) != hdr["header_end"]:
        return VaultStatus.ERROR, "Internal error: header length changed during re-key."

    # Tulis lewat temp file + atomic os.replace, BUKAN overwrite in-place. Region
    # keyslot bisa melebihi satu sektor disk (hint + beberapa slot), jadi tulis
    # in-place rentan torn-write saat power-loss di tengah tulis → vault rusak dan
    # tak bisa dibuka oleh password lama MAUPUN baru. Konsisten dengan
    # add_recovery_key / remove_recovery_key.
    status, message = _rewrite_header_full(path, hdr["header_end"], new_header)
    if status == VaultStatus.SUCCESS:
        return VaultStatus.SUCCESS, "Password changed successfully."
    return status, message


def add_recovery_key(
    vault_path: str,
    password: str,
    recovery_secret: str,
    recovery_type: str = "code",
    keyfile_path: str | None = None,
) -> tuple[VaultStatus, str | None]:
    """Tambahkan keyslot recovery ke vault yang sudah ada.

    Header bertambah panjang, jadi vault ditulis ulang (temp + atomic replace).
    Menolak bila sudah ada recovery key. Untuk vault 2FA, ``keyfile_path`` dipakai
    bersama ``password`` untuk membukanya.
    """
    if not recovery_secret or not recovery_secret.strip():
        return VaultStatus.ERROR, "Recovery secret cannot be empty."

    keyfile_material, kf_error = _load_keyfile_material_optional(keyfile_path)
    if kf_error:
        return VaultStatus.ERROR, kf_error

    path = Path(vault_path)
    status, message, hdr, master_key = _load_for_management(path, password, keyfile_material)
    if status != VaultStatus.SUCCESS:
        return status, message

    if any(s["slot_type"] in RECOVERY_SLOT_TYPES for s in hdr["slots"]):
        return (
            VaultStatus.ERROR,
            "This vault already has a recovery key. Remove it first to set a new one.",
        )
    if len(hdr["slots"]) >= MAX_KEYSLOTS:
        return VaultStatus.ERROR, "This vault already has the maximum number of keyslots."

    # Samakan level KDF recovery dengan slot password vault agar konsisten.
    pw_slot = next((s for s in hdr["slots"] if s["slot_type"] in PASSWORD_SLOT_TYPES), None)
    level_params = pw_slot["kdf_params"] if pw_slot else None
    rtype = SLOT_TYPE_RECOVERY_CODE if recovery_type == "code" else SLOT_TYPE_RECOVERY_PASSPHRASE
    new_slot = _build_keyslot(
        master_key,
        hdr["file_id"],
        rtype,
        recovery_secret,
        kdf_params=level_params,
        hint_bytes=_hint_bytes_from_header(hdr),
    )
    slot_bytes = [_slot_bytes(s) for s in hdr["slots"]] + [new_slot]
    new_header = _build_header(
        hdr["file_id"], hdr["chunk_size"], hdr["flags"], _hint_bytes_from_header(hdr), slot_bytes
    )
    return _rewrite_header_full(path, hdr["header_end"], new_header)


def remove_recovery_key(
    vault_path: str,
    password: str,
    keyfile_path: str | None = None,
) -> tuple[VaultStatus, str | None]:
    """Hapus keyslot recovery dari vault. ``password`` harus membuka slot mana pun.

    Untuk vault 2FA, ``keyfile_path`` dipakai bersama ``password`` untuk membukanya.
    """
    keyfile_material, kf_error = _load_keyfile_material_optional(keyfile_path)
    if kf_error:
        return VaultStatus.ERROR, kf_error

    path = Path(vault_path)
    status, message, hdr, master_key = _load_for_management(path, password, keyfile_material)
    if status != VaultStatus.SUCCESS:
        return status, message

    kept = [s for s in hdr["slots"] if s["slot_type"] not in RECOVERY_SLOT_TYPES]
    if len(kept) == len(hdr["slots"]):
        return VaultStatus.ERROR, "This vault has no recovery key to remove."
    if not kept:
        return VaultStatus.ERROR, "Cannot remove the last keyslot from the vault."

    slot_bytes = [_slot_bytes(s) for s in kept]
    new_header = _build_header(
        hdr["file_id"], hdr["chunk_size"], hdr["flags"], _hint_bytes_from_header(hdr), slot_bytes
    )
    return _rewrite_header_full(path, hdr["header_end"], new_header)


def add_keyfile(
    vault_path: str,
    password: str,
    keyfile_path: str,
) -> tuple[VaultStatus, str | None]:
    """Aktifkan 2FA pada vault yang sudah ada: lindungi slot password dengan keyfile.

    Yang BERUBAH hanya region keyslot (panjang header identik — slot password & slot
    keyfile berukuran sama), tapi penulisannya tetap lewat ``_rewrite_header_full``
    (temp + atomic replace) yang **menyalin seluruh isi vault**, jadi secara I/O ini
    **O(ukuran vault)** dan butuh ruang disk kosong ≈ sebesar vault (bisa memunculkan
    "Not enough storage space to update the vault" untuk vault besar). ``password``
    HARUS membuka slot password (bukan recovery key), karena slot itu dibangun ulang
    menjadi slot keyfile dari password yang sama.
    """
    keyfile_material, kf_error = _load_keyfile_material_optional(keyfile_path)
    if kf_error:
        return VaultStatus.ERROR, kf_error
    if keyfile_material is None:
        return VaultStatus.ERROR, "Select a keyfile to protect this vault."

    path = Path(vault_path)
    status, message, hdr = _read_header_for_management(path)
    if status != VaultStatus.SUCCESS:
        return status, message

    pw_index = next(
        (i for i, s in enumerate(hdr["slots"]) if s["slot_type"] in PASSWORD_SLOT_TYPES),
        None,
    )
    if pw_index is None:
        return VaultStatus.ERROR, "This vault has no password slot."
    if hdr["slots"][pw_index]["slot_type"] == SLOT_TYPE_PASSWORD_KEYFILE:
        return VaultStatus.ERROR, "This vault is already protected by a keyfile."

    # Buktikan secret adalah password (membuka slot password), lalu bangun ulang slot
    # itu sebagai slot keyfile dari password yang sama.
    master_key = _unlock_password_slot(hdr, password)
    if master_key is None:
        return VaultStatus.WRONG_PASSWORD, None

    slot_bytes = [_slot_bytes(s) for s in hdr["slots"]]
    slot_bytes[pw_index] = _build_keyslot(
        master_key,
        hdr["file_id"],
        SLOT_TYPE_PASSWORD_KEYFILE,
        password,
        kdf_params=hdr["slots"][pw_index]["kdf_params"],
        hint_bytes=_hint_bytes_from_header(hdr),
        keyfile_material=keyfile_material,
    )
    new_header = _build_header(
        hdr["file_id"], hdr["chunk_size"], hdr["flags"], _hint_bytes_from_header(hdr), slot_bytes
    )
    if len(new_header) != hdr["header_end"]:
        return VaultStatus.ERROR, "Internal error: header length changed while adding keyfile."

    status, message = _rewrite_header_full(path, hdr["header_end"], new_header)
    if status == VaultStatus.SUCCESS:
        return (
            VaultStatus.SUCCESS,
            "Keyfile added. You'll now need it plus your password to open this vault.",
        )
    return status, message


def remove_keyfile(
    vault_path: str,
    password: str,
    keyfile_path: str,
) -> tuple[VaultStatus, str | None]:
    """Matikan 2FA: lepas perlindungan keyfile dari slot password.

    Membutuhkan ``password`` DAN ``keyfile_path`` (keduanya membuka slot password),
    lalu membangun ulang slot itu sebagai slot password biasa. Panjang header tetap,
    tetapi seperti ``add_keyfile`` penulisannya lewat ``_rewrite_header_full`` yang
    menyalin seluruh isi vault → secara I/O **O(ukuran vault)** + butuh ruang disk
    kosong ≈ sebesar vault.
    """
    keyfile_material, kf_error = _load_keyfile_material_optional(keyfile_path)
    if kf_error:
        return VaultStatus.ERROR, kf_error
    if keyfile_material is None:
        return VaultStatus.ERROR, "Select the keyfile to remove keyfile protection."

    path = Path(vault_path)
    status, message, hdr = _read_header_for_management(path)
    if status != VaultStatus.SUCCESS:
        return status, message

    pw_index = next(
        (i for i, s in enumerate(hdr["slots"]) if s["slot_type"] in PASSWORD_SLOT_TYPES),
        None,
    )
    if pw_index is None:
        return VaultStatus.ERROR, "This vault has no password slot."
    if hdr["slots"][pw_index]["slot_type"] != SLOT_TYPE_PASSWORD_KEYFILE:
        return VaultStatus.ERROR, "This vault isn't protected by a keyfile."

    master_key = _unlock_password_slot(hdr, password, keyfile_material)
    if master_key is None:
        return VaultStatus.WRONG_PASSWORD, None

    slot_bytes = [_slot_bytes(s) for s in hdr["slots"]]
    slot_bytes[pw_index] = _build_keyslot(
        master_key,
        hdr["file_id"],
        SLOT_TYPE_PASSWORD,
        password,
        kdf_params=hdr["slots"][pw_index]["kdf_params"],
        hint_bytes=_hint_bytes_from_header(hdr),
    )
    new_header = _build_header(
        hdr["file_id"], hdr["chunk_size"], hdr["flags"], _hint_bytes_from_header(hdr), slot_bytes
    )
    if len(new_header) != hdr["header_end"]:
        return VaultStatus.ERROR, "Internal error: header length changed while removing keyfile."

    status, message = _rewrite_header_full(path, hdr["header_end"], new_header)
    if status == VaultStatus.SUCCESS:
        return VaultStatus.SUCCESS, "Keyfile removed. Your password alone now opens this vault."
    return status, message
