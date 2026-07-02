"""
Modul: core_messages.py
Deskripsi: Terjemahan pesan hasil/error yang berasal dari lapisan ``core`` (vault /
           text_vault). ``core`` sengaja TIDAK bergantung pada i18n UI (agar tetap
           bisa diuji mandiri & tidak memuat Qt), jadi ia mengembalikan teks English
           sebagai sumber kebenaran. Pemetaan English → kunci ``tr()`` dilakukan di
           SINI, di batas UI, lewat ``localize_core_message()``.

Kontrak:
- Kunci peta = string English PERSIS seperti dikembalikan ``core`` (untuk yang
  panjang/multibaris dipakai konstanta ``core.vault`` agar tak rawan salah ketik).
- Nilai peta = kunci ``tr()``; default ``tr()`` = pesan English itu sendiri, sehingga
  mode English mengembalikannya apa adanya dan hanya mode ID yang diterjemahkan.
- Pesan yang tak dikenal dikembalikan apa adanya (fail-safe: tetil tampil, English).
- Pesan ruang-disk mengandung angka ter-interpolasi → ditangani via regex terpisah.

``tests/test_core_i18n.py`` menjaga peta ini tetap sinkron dengan ``core``:
setiap pesan user-facing yang dikembalikan ``core`` harus ada di peta / allowlist,
dan tiap kunci ``tr()`` di sini harus punya terjemahan Indonesia.
"""

from __future__ import annotations

import re

from core.constants import (
    CORRUPT_VAULT_MESSAGE,
    DELETE_ORIGINAL_FAILED_MESSAGE,
    GENERIC_FAILURE_MESSAGE,
    KEYFILE_CREATED_MESSAGE,
    KEYFILE_INSIDE_SOURCE_MESSAGE,
    SAVE_INSIDE_SOURCE_MESSAGE,
    VERIFY_DISK_FAIL_MESSAGE,
)

from .i18n import tr

# ── Pesan ruang-disk (ber-angka) ────────────────────────────────────────────────
# core: "Not enough storage space.\nDisk free: {free_mb:.1f} MB. At least {req_mb:.1f} MB is required."
_DISK_RE = re.compile(
    r"^Not enough storage space\.\nDisk free: ([0-9.]+) MB\. "
    r"At least ([0-9.]+) MB is required\.$"
)
_DISK_KEY = "core.disk_space"
_DISK_DEFAULT = (
    "Not enough storage space.\nDisk free: {free} MB. At least {required} MB is required."
)

# ── Peta pesan English core → kunci tr() ─────────────────────────────────────────
# Kunci = teks English PERSIS dari core. Konstanta dipakai untuk pesan panjang.
_MAP: dict[str, str] = {
    # File / format vault
    "This file isn't a valid Adyton Crypt vault.": "core.not_vault",
    "This vault was made by a different version of Adyton Crypt. "
    "Please update the app.": "core.version_mismatch",
    "This vault was made by a different version of Adyton Crypt and can't be managed "
    "here. Please update the app.": "core.version_mismatch_manage",
    "The vault file is too small or incomplete.": "core.too_small",
    "The vault file could not be found.": "core.not_found",
    "The vault's chunk parameters are invalid, or the file is corrupted.": "core.chunk_invalid",
    "Invalid keyslot count; the file may be corrupted.": "core.keyslot_count",
    "Invalid vault hint length; the file may be corrupted.": "core.hint_len",
    "This vault flag isn't supported by this app version.": "core.flag_unsupported",
    "This vault keyslot isn't supported by this app version.": "core.keyslot_unsupported",
    "Invalid Argon2id parameter size.": "core.argon_size",
    "Invalid Argon2id parameter.": "core.argon_invalid",
    "Argon2id parameters exceed the safe maximum.": "core.argon_max",
    CORRUPT_VAULT_MESSAGE: "core.corrupt",
    "Vault contents don't match the expected format.": "core.contents_mismatch",
    GENERIC_FAILURE_MESSAGE: "core.generic",
    # Kunci (lock)
    "No valid file/folder to lock.": "core.no_valid",
    "Vault locked successfully!": "core.locked_ok",
    "Password cannot be empty.": "core.pw_empty",
    SAVE_INSIDE_SOURCE_MESSAGE: "core.save_inside_source",
    KEYFILE_INSIDE_SOURCE_MESSAGE: "core.keyfile_inside_source",
    VERIFY_DISK_FAIL_MESSAGE: "core.verify_disk_fail",
    DELETE_ORIGINAL_FAILED_MESSAGE: "core.delete_original_failed",
    "Not enough storage space to update the vault.": "core.disk_update",
    "Operation cancelled. No existing data was changed.": "core.cancelled_nochange",
    # Verify
    "Vault verified — your credential is correct and all data is intact.": "core.verified",
    "Verification cancelled.": "core.verify_cancelled",
    # Browse / extract
    "No items were selected to extract.": "core.no_items",
    "The destination folder doesn't exist.": "core.dest_missing",
    "None of the selected items were found in the vault.": "core.none_found",
    "Extraction cancelled. No files were placed.": "core.extract_cancelled",
    "Browse cancelled.": "core.browse_cancelled",
    # Keyfile
    "The keyfile could not be read. Check that it still exists.": "core.keyfile_read_fail",
    "The keyfile is empty. Choose a non-empty file or generate one.": "core.keyfile_empty",
    "The keyfile is too large. Choose a file under 64 MB.": "core.keyfile_too_large",
    "A file with that name already exists. Choose another name.": "core.file_exists",
    KEYFILE_CREATED_MESSAGE: "core.keyfile_created",
    "Select a keyfile to protect this vault.": "core.keyfile_select_protect",
    "Select the keyfile to remove keyfile protection.": "core.keyfile_select_remove",
    "This vault is already protected by a keyfile.": "core.keyfile_already",
    "This vault isn't protected by a keyfile.": "core.keyfile_not_protected",
    "This vault uses a keyfile. Select the keyfile to change its "
    "password.": "core.keyfile_needed_changepw",
    "Keyfile added. You'll now need it plus your password to open this "
    "vault.": "core.keyfile_added",
    "Keyfile removed. Your password alone now opens this vault.": "core.keyfile_removed",
    # Manage: password / recovery / keyslot
    "New password cannot be empty.": "core.newpw_empty",
    "Password changed successfully.": "core.pw_changed",
    "Recovery secret cannot be empty.": "core.recovery_empty",
    "This vault already has a recovery key. Remove it first to set a new "
    "one.": "core.recovery_exists",
    "This vault already has the maximum number of keyslots.": "core.max_slots",
    "This vault has no password slot to change.": "core.no_pw_slot_change",
    "This vault has no password slot.": "core.no_pw_slot",
    "This vault has no recovery key to remove.": "core.no_recovery",
    "Cannot remove the last keyslot from the vault.": "core.last_slot",
    "Vault updated successfully.": "core.updated",
    "Internal error: header length changed during re-key.": "core.err_rekey_len",
    "Internal error: header length changed while adding keyfile.": "core.err_addkf_len",
    "Internal error: header length changed while removing keyfile.": "core.err_rmkf_len",
}


def localize_core_message(msg: str | None) -> str | None:
    """Terjemahkan pesan English dari ``core`` ke bahasa aktif.

    ``None`` → ``None``. Pesan tak dikenal dikembalikan apa adanya (fail-safe).
    Pesan ruang-disk (ber-angka) direkonstruksi dari template terjemahan.
    """
    if not msg:
        return msg
    m = _DISK_RE.match(msg)
    if m:
        return tr(_DISK_KEY, _DISK_DEFAULT).format(free=m.group(1), required=m.group(2))
    key = _MAP.get(msg)
    if key is not None:
        # default = pesan English itu sendiri → mode EN tak berubah.
        return tr(key, msg)
    return msg
