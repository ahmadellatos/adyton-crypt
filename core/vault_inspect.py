"""
core/vault_inspect.py
Inspeksi metadata vault read-only (tanpa credential).
"""

from pathlib import Path

from loguru import logger

from .constants import (
    ARGON2ID_PARAMS_SIZE,
    CHUNK_RECORD_OVERHEAD,
    CORE_HEADER_SIZE,
    MAGIC_BYTES,
    RECOVERY_SLOT_TYPES,
    SALT_SIZE,
    SLOT_TYPE_PASSWORD_KEYFILE,
    VERSION,
    WRAP_NONCE_SIZE,
    WRAPPED_KEY_SIZE,
)
from .vault_stream import _parse_header


def _read_header_from_path(path: Path) -> dict:
    """Buka file dan parse header-nya (tanpa credential). Raise bila format asing."""
    with path.open("rb") as fk:
        if fk.read(4) != MAGIC_BYTES:
            raise ValueError("This file isn't a valid Adyton Crypt vault.")
        version = fk.read(1)
        if version != VERSION:
            raise ValueError("wrong_format")
        return _parse_header(fk)


def _quick_verify_vault(path: Path) -> bool:
    """
    Sanity check kilat: verifikasi magic bytes, version, dan ukuran file minimum.

    os.fsync() di kunci_brankas sudah menjamin data tersimpan ke hardware.
    Setiap record sudah mendapat tag GCM sendiri saat ditulis. Fungsi ini tetap
    hanya sanity check cepat, bukan full read-back.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if f.read(4) != MAGIC_BYTES:
                return False
            version = f.read(1)

        if version == VERSION:
            # Core header + slot_count(1) + minimal 1 slot + metadata & final record.
            min_slot = (
                1 + 1 + 2 + ARGON2ID_PARAMS_SIZE + SALT_SIZE + WRAP_NONCE_SIZE + WRAPPED_KEY_SIZE
            )
            return size >= CORE_HEADER_SIZE + 1 + min_slot + (2 * CHUNK_RECORD_OVERHEAD)
        return False
    except Exception as e:
        logger.error(f"Quick verify gagal: {e}")
        return False


def _format_label(version: bytes | None) -> str:
    return "Adyton Vault" if version == VERSION else "unknown"


def read_vault_hint(vault_path: str) -> str | None:
    """Baca password hint dari header tanpa perlu password. None jika tidak ada."""
    try:
        return _read_header_from_path(Path(vault_path)).get("hint")
    except Exception:
        return None


def vault_info(vault_path: str) -> dict:
    """Ringkas metadata vault untuk UI tanpa membutuhkan password.

    Mengembalikan format, ada/tidaknya hint & recovery key, dan apakah vault
    mendukung ganti password. Tidak pernah melempar exception.
    """
    info = {
        "format": "unknown",
        "supports_change_password": False,  # nosec B105 — nama key, bukan kredensial
        "has_hint": False,
        "hint": None,
        "has_recovery": False,
        "requires_keyfile": False,
        "slot_count": 0,
    }
    path = Path(vault_path)
    try:
        with path.open("rb") as fk:
            if fk.read(4) != MAGIC_BYTES:
                return info
            version = fk.read(1)
        info["format"] = _format_label(version)
        if version != VERSION:
            return info

        hdr = _read_header_from_path(path)
        info.update(
            {
                "supports_change_password": True,  # nosec B105 — nama key, bukan kredensial
                "has_hint": hdr["hint"] is not None,
                "hint": hdr["hint"],
                "has_recovery": any(s["slot_type"] in RECOVERY_SLOT_TYPES for s in hdr["slots"]),
                "requires_keyfile": any(
                    s["slot_type"] == SLOT_TYPE_PASSWORD_KEYFILE for s in hdr["slots"]
                ),
                "slot_count": len(hdr["slots"]),
            }
        )
    except Exception:
        logger.opt(exception=True).debug("vault_info gagal membaca header (non-fatal)")
    return info
