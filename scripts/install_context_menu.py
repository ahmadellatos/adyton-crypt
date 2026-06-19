"""
scripts/install_context_menu.py
Daftarkan/lepas menu klik-kanan Windows untuk Adyton Crypt.

Semua entri ditulis di HKEY_CURRENT_USER (tidak butuh admin). Struktur:

    *\\shell\\AdytonCrypt           → cascade "Adyton Crypt" (file apa pun)
    Directory\\shell\\AdytonCrypt   → cascade "Adyton Crypt" (folder)
        └─ ExtendedSubCommandsKey → AdytonCrypt.PathCommands\\shell
               ├─ 01_encrypt  → "Lock to Vault…"      (--encrypt "%1")
               └─ 02_shred    → "Securely Delete…"    (--shred   "%1")
    .adtn\\shell\\AdytonOpen        → "Open Vault…"    (--decrypt "%1")

Perintah otomatis menyesuaikan mode:
  • Dev    : "<venv>\\pythonw.exe" "<proj>\\main.py" --<aksi> "%1"
  • Build  : "<adyton.exe>" --<aksi> "%1"   (saat dijalankan dari exe frozen,
             atau lewat --target <path-exe>)

Pakai:
    python scripts/install_context_menu.py            # pasang (install)
    python scripts/install_context_menu.py --uninstall
    python scripts/install_context_menu.py --status
    python scripts/install_context_menu.py --target "C:\\...\\adyton.exe"

Catatan: verb registry dengan "%1" dipanggil sekali per file. Memilih banyak
file lalu klik aksi akan memunculkan satu dialog per file (cukup untuk v1).
"""

import argparse
import ctypes
import sys
from pathlib import Path

if sys.platform != "win32":
    print("Skrip ini hanya untuk Windows.")
    sys.exit(1)

# Konsol Windows default (cp1252) tidak bisa mencetak ✓/…/→; paksa UTF-8 agar
# output tidak crash. Nilai registry sendiri ditulis Unicode lewat winreg.
for _stream in (sys.stdout, sys.stderr):
    with __import__("contextlib").suppress(Exception):
        _stream.reconfigure(encoding="utf-8")

import winreg  # noqa: E402  (import setelah guard platform)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ICON_PATH = PROJECT_ROOT / "assets" / "icon_adyton.ico"

HKCU = winreg.HKEY_CURRENT_USER
CLASSES = r"Software\Classes"

MENU_LABEL = "Adyton Crypt"
PARENT_KEY = "AdytonCrypt"  # subkey di bawah *\shell dan Directory\shell
STORE_KEY = "AdytonCrypt.PathCommands"  # ExtendedSubCommandsKey bersama
OPEN_KEY = "AdytonOpen"  # subkey di bawah .adtn\shell

SHCNE_ASSOCCHANGED = 0x08000000


# =========================================================================
# COMMAND BUILDER
# =========================================================================


def _quote(s: str) -> str:
    return f'"{s}"' if " " in s else s


def _launcher(target: str | None) -> list[str]:
    """Bagian awal command (tanpa flag/%1), menyesuaikan dev/build/target."""
    if target:
        return [target]
    if getattr(sys, "frozen", False):
        return [sys.executable]
    # Dev: pythonw (tanpa konsol) + main.py
    pyw = Path(sys.executable).with_name("pythonw.exe")
    launcher = str(pyw) if pyw.exists() else sys.executable
    return [launcher, str(PROJECT_ROOT / "main.py")]


def build_command(flag: str, target: str | None) -> str:
    head = " ".join(_quote(p) for p in _launcher(target))
    return f'{head} {flag} "%1"'


# =========================================================================
# REGISTRY HELPERS
# =========================================================================


def _set(path: str, name: str, value: str) -> None:
    with winreg.CreateKey(HKCU, path) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _exists(path: str) -> bool:
    try:
        with winreg.OpenKey(HKCU, path):
            return True
    except FileNotFoundError:
        return False


def _get(path: str, name: str = "") -> str | None:
    try:
        with winreg.OpenKey(HKCU, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except FileNotFoundError:
        return None


def _delete_tree(path: str) -> None:
    """Hapus key beserta seluruh subkey-nya (winreg.DeleteKey hanya hapus kosong)."""
    try:
        with winreg.OpenKey(HKCU, path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    sub = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(path + "\\" + sub)
        winreg.DeleteKey(HKCU, path)
    except FileNotFoundError:
        pass


def _refresh_shell() -> None:
    ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, 0, None, None)


# =========================================================================
# REGISTER / UNREGISTER
# =========================================================================


def register(target: str | None = None) -> None:
    icon = str(ICON_PATH) if ICON_PATH.exists() else None
    cmd_enc = build_command("--encrypt", target)
    cmd_shred = build_command("--shred", target)
    cmd_dec = build_command("--decrypt", target)

    # 1) Cascade parent di file (*) dan folder (Directory) → store bersama
    for ctx in (r"*\shell", r"Directory\shell"):
        base = rf"{CLASSES}\{ctx}\{PARENT_KEY}"
        _set(base, "MUIVerb", MENU_LABEL)
        _set(base, "ExtendedSubCommandsKey", STORE_KEY)
        if icon:
            _set(base, "Icon", icon)
        # Pada file .adtn, sembunyikan cascade "Adyton Crypt" (yang memuat "Lock")
        # agar vault tak bisa dikunci ulang; .adtn cukup menampilkan "Open Vault…".
        if ctx == r"*\shell":
            _set(base, "AppliesTo", "NOT System.FileExtension:=.adtn")

    # 2) Isi cascade (urut via prefix 01_/02_)
    enc = rf"{CLASSES}\{STORE_KEY}\shell\01_encrypt"
    _set(enc, "MUIVerb", "Lock to Vault…")
    _set(enc + r"\command", "", cmd_enc)
    if icon:
        _set(enc, "Icon", icon)

    shred = rf"{CLASSES}\{STORE_KEY}\shell\02_shred"
    _set(shred, "MUIVerb", "Securely Delete…")
    _set(shred + r"\command", "", cmd_shred)
    if icon:
        _set(shred, "Icon", icon)

    # 3) Aksi langsung "Open Vault…" khusus file .adtn (tanpa mengubah ProgID)
    op = rf"{CLASSES}\.adtn\shell\{OPEN_KEY}"
    _set(op, "", "Open Vault…")  # default value = label
    _set(op + r"\command", "", cmd_dec)
    if icon:
        _set(op, "Icon", icon)

    _refresh_shell()

    print(f"✓ Menu '{MENU_LABEL}' terpasang (HKCU, tanpa admin).")
    if not icon:
        print(f"  ! Ikon tidak ditemukan di {ICON_PATH} — entri dibuat tanpa ikon.")
    print("\n  Perintah terdaftar:")
    print(f"    Lock to Vault…   {cmd_enc}")
    print(f"    Securely Delete… {cmd_shred}")
    print(f"    Open Vault…      {cmd_dec}")
    print("\n  Klik kanan file/folder → 'Adyton Crypt'; file .adtn → 'Open Vault…'.")
    print("  Di Windows 11 mungkin ada di 'Show more options' (menu klasik).")


def unregister() -> None:
    _delete_tree(rf"{CLASSES}\*\shell\{PARENT_KEY}")
    _delete_tree(rf"{CLASSES}\Directory\shell\{PARENT_KEY}")
    _delete_tree(rf"{CLASSES}\{STORE_KEY}")
    _delete_tree(rf"{CLASSES}\.adtn\shell\{OPEN_KEY}")
    _refresh_shell()
    print(f"✓ Menu '{MENU_LABEL}' dilepas dari context menu.")


def status() -> None:
    checks = {
        "File cascade  (*)": rf"{CLASSES}\*\shell\{PARENT_KEY}",
        "Folder cascade": rf"{CLASSES}\Directory\shell\{PARENT_KEY}",
        "Sub-commands store": rf"{CLASSES}\{STORE_KEY}\shell\01_encrypt",
        ".adtn Open Vault": rf"{CLASSES}\.adtn\shell\{OPEN_KEY}",
    }
    print("Status context menu Adyton Crypt:\n")
    all_ok = True
    for label, path in checks.items():
        ok = _exists(path)
        all_ok = all_ok and ok
        print(f"  [{'x' if ok else ' '}] {label}")
    if all_ok:
        cmd = _get(rf"{CLASSES}\{STORE_KEY}\shell\01_encrypt\command")
        print(f"\n  Encrypt command: {cmd}")
    else:
        print("\n  Belum terpasang sepenuhnya. Jalankan tanpa argumen untuk install.")


# =========================================================================
# MAIN
# =========================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="Kelola context menu Adyton Crypt (HKCU).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--uninstall", action="store_true", help="Lepas menu dari Explorer.")
    group.add_argument("--status", action="store_true", help="Cek apakah menu terpasang.")
    parser.add_argument(
        "--target",
        metavar="EXE",
        help="Path ke adyton.exe hasil build (override deteksi dev otomatis).",
    )
    args = parser.parse_args()

    if args.status:
        status()
    elif args.uninstall:
        unregister()
    else:
        register(args.target)


if __name__ == "__main__":
    main()
