"""
Guard: pemetaan pesan core → i18n (ui/core_messages.py) tetap sinkron dengan core.

Menangkap drift lebih awal:
- setiap pesan user-facing yang dikembalikan ``core.vault`` harus punya entri di peta
  (atau ada di allowlist pesan internal/ter-interpolasi yang ditangani terpisah);
- setiap kunci ``tr()`` di peta (plus pesan ruang-disk) harus punya terjemahan Indonesia;
- ``localize_core_message`` menerjemahkan di mode ID dan meneruskan pesan asing apa adanya.
"""

from __future__ import annotations

import ast
import pathlib

from ui.core_messages import _MAP, localize_core_message
from ui.i18n import _TRANSLATIONS, i18n

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Pesan yang SENGAJA tak dipetakan: sentinel internal (bug pemanggil, ditangkap
# handler generik → GENERIC_FAILURE_MESSAGE) & pesan sukses lock ter-interpolasi
# (UI membuat teksnya sendiri, tak menampilkan pesan core mentah).
_ALLOWLIST = {
    "A keyfile is required to build this keyslot.",
    "Argon2id parameter out of range.",
}


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    """NAMA → nilai untuk assignment string level-modul (dipakai resolusi Name)."""
    constmap: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            constmap[node.targets[0].id] = node.value.value
    return constmap


def _extract_core_messages() -> set[str]:
    """String English user-facing yang dikembalikan core (return tuple / ValueError).

    Memindai SEMUA modul vault (vault.py + hasil split vault_*.py). Konstanta pesan
    kini hidup di core/constants.py, jadi constmap-nya dibangun dari sana lebih dulu
    agar ``return VaultStatus.X, NAMA_KONSTANTA`` tetap teresolusi.
    """
    constmap = _module_string_constants(
        ast.parse((ROOT / "core" / "constants.py").read_text(encoding="utf-8"))
    )

    msgs: set[str] = set()
    for src_path in sorted((ROOT / "core").glob("vault*.py")):
        tree = ast.parse(src_path.read_text(encoding="utf-8"))
        local_constmap = {**constmap, **_module_string_constants(tree)}

        for n in ast.walk(tree):
            # return (VaultStatus.X, "msg"[, ...])
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple) and n.value.elts:
                head = n.value.elts[0]
                if (
                    isinstance(head, ast.Attribute)
                    and isinstance(head.value, ast.Name)
                    and head.value.id == "VaultStatus"
                ):
                    for el in n.value.elts[1:]:
                        if isinstance(el, ast.Constant) and isinstance(el.value, str):
                            s = el.value
                            if len(s) > 5 and s[0].isupper() and "{" not in s:
                                msgs.add(s)
                        elif isinstance(el, ast.Name) and el.id in local_constmap:
                            msgs.add(local_constmap[el.id])
            # raise ValueError("Msg ...")
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "ValueError"
                and n.args
                and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)
            ):
                s = n.args[0].value
                if s and s[0].isupper() and " " in s and "{" not in s:
                    msgs.add(s)
    return msgs


def test_every_core_message_is_mapped_or_allowlisted():
    unmapped = sorted(m for m in _extract_core_messages() if m not in _MAP and m not in _ALLOWLIST)
    assert not unmapped, "Pesan core belum dipetakan di ui/core_messages._MAP:\n" + "\n".join(
        repr(m) for m in unmapped
    )


def test_every_mapped_key_has_indonesian_translation():
    id_dict = _TRANSLATIONS["id"]
    keys = set(_MAP.values()) | {"core.disk_space"}
    missing = sorted(k for k in keys if k not in id_dict)
    assert not missing, f"Kunci tr() tanpa terjemahan ID: {missing}"


def test_localize_translates_in_id_and_passes_through_unknown():
    original = i18n().language()
    try:
        i18n().set_language("id")
        # pesan yang dipetakan → berubah (diterjemahkan)
        sample = "This file isn't a valid Adyton Crypt vault."
        assert localize_core_message(sample) != sample
        # pesan asing → apa adanya; None → None
        assert localize_core_message("totally unknown message xyz") == "totally unknown message xyz"
        assert localize_core_message(None) is None
        # ruang-disk (ber-angka) → template ID terisi angka
        disk = "Not enough storage space.\nDisk free: 12.3 MB. At least 45.6 MB is required."
        out = localize_core_message(disk)
        assert out != disk and "12.3" in out and "45.6" in out
    finally:
        i18n().set_language(original)
