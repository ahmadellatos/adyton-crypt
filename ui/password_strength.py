"""
Modul: password_strength.py
Deskripsi: Sumber kebenaran tunggal untuk logika kekuatan password yang dipakai
           bersama oleh Tab Kunci dan Tab Teks — skor zxcvbn (di-remap), warna &
           label meter, aturan checklist, gate "cukup kuat", dan generator.

           Murni Python (tanpa Qt) supaya mudah di-unit-test.
"""

import secrets
import string

from zxcvbn import zxcvbn

from .styles import CLR_DANGER, CLR_SUCCESS, CLR_WARN, CLR_YELLOW

# Indeks 0-3 sejajar dengan hasil pw_strength().
STRENGTH_COLORS = [CLR_DANGER, CLR_WARN, CLR_YELLOW, CLR_SUCCESS]
STRENGTH_LABELS = ["Weak", "Fair", "Strong", "Very Strong"]

# Label + urutan checklist; dipakai bersama agar kedua tab selalu sinkron.
CHECKLIST_ITEMS = [
    "At least 8 characters",
    "Uppercase letter (A-Z)",
    "Lowercase letter (a-z)",
    "Number (0-9)",
    "Symbol (!@#$%^&*)",
]

# Alfabet generator — superset dari versi lama Tab Kunci (mencakup simbol Teks).
_GEN_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
_GEN_LENGTH = 20


def pw_strength(pw: str) -> int:
    """Skor 0-3 (indeks ke STRENGTH_COLORS/LABELS). -1 bila password kosong.

    zxcvbn mengembalikan 0-4; kita remap agar dua tier terendah menyatu menjadi
    "Weak" sehingga meter terasa lebih jujur untuk password lemah.
    """
    if not pw:
        return -1
    score = zxcvbn(pw)["score"]
    return 0 if score <= 1 else score - 1


def password_rules(pw: str) -> list[bool]:
    """Status lima kriteria, sejajar dengan CHECKLIST_ITEMS.

    Urutan: panjang >= 8, huruf besar, huruf kecil, angka, simbol.
    """
    return [
        len(pw) >= 8,
        any(c.isupper() for c in pw),
        any(c.islower() for c in pw),
        any(c.isdigit() for c in pw),
        any(not c.isalnum() and not c.isspace() for c in pw),
    ]


def is_strong(pw: str) -> bool:
    """Gate yang dipakai saat enkripsi (Tab Kunci & Tab Teks mode enkripsi):
    seluruh checklist terpenuhi DAN skor zxcvbn cukup (>= 1 setelah remap)."""
    return all(password_rules(pw)) and pw_strength(pw) >= 1


def generate_password(length: int = _GEN_LENGTH) -> str:
    """Password acak yang dijamin lolos seluruh kriteria checklist."""
    while True:
        pw = "".join(secrets.choice(_GEN_ALPHABET) for _ in range(length))
        if all(password_rules(pw)):
            return pw
