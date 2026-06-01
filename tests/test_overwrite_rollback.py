"""Regression tests for staged force-overwrite rollback."""

import os
import shutil
from pathlib import Path

from core import vault as vault_mod
from core.vault import VaultStatus, buka_brankas, kunci_brankas

PASSWORD = "P@ssw0rd!Kuat123"


def test_force_overwrite_restores_existing_folder_when_final_move_fails(sample_folder, tmp_dir, monkeypatch):
    vault_path = os.path.join(tmp_dir, "rollback.adtn")
    status, msg = kunci_brankas([sample_folder], vault_path, PASSWORD)
    assert status == VaultStatus.SUCCESS, msg

    marker = os.path.join(sample_folder, "dokumen.txt")
    with open(marker, "w", encoding="utf-8") as f:
        f.write("DATA LAMA YANG HARUS TETAP ADA")

    real_move = shutil.move

    def failing_move(src, dst, *args, **kwargs):
        if os.fspath(dst) == os.fspath(sample_folder):
            raise OSError("simulated final placement failure")
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr(vault_mod.shutil, "move", failing_move)

    status, msg = buka_brankas(vault_path, PASSWORD, force=True)

    assert status == VaultStatus.ERROR
    assert os.path.isdir(sample_folder)
    with open(marker, encoding="utf-8") as f:
        assert f.read() == "DATA LAMA YANG HARUS TETAP ADA"
    assert not list(Path(tmp_dir).glob("._dec_*"))
