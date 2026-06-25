"""
Modul: i18n.py
Deskripsi: Lapisan terjemahan ringan (runtime) untuk UI.

Sengaja tidak memakai .ts/.qm Qt Linguist agar bisa ganti bahasa LIVE tanpa
toolchain. ``tr(key, default)`` mengembalikan teks bahasa aktif; default selalu
teks Inggris. Memancarkan ``language_changed`` agar widget bisa retranslate.

Pola retranslate app-wide:
- Saat membangun UI, daftarkan widget yang teksnya statis lewat ``register(w,
  key, default[, setter])`` — ini menyetel teks sekarang DAN menandai widget agar
  ``retranslate(root)`` bisa menyetel ulang saat bahasa berganti.
- Teks dinamis (status, error, progres) cukup dibungkus ``tr(...)`` di titik
  pembuatannya: ia memakai bahasa aktif saat itu dan ikut berganti pada aksi
  berikutnya.

Catatan keamanan-perubahan: untuk bahasa Inggris, ``tr(key, default)`` selalu
mengembalikan ``default`` apa adanya; key yang belum ada di kamus ID juga jatuh
ke ``default``. Jadi membungkus literal dengan ``tr("key", "<literal>")`` tidak
mengubah tampilan Inggris sama sekali — hanya menambah jalur Indonesia.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

# Hanya entri non-Inggris yang perlu didefinisikan; "en" memakai default di situs panggil.
_TRANSLATIONS: dict[str, dict[str, str]] = {
    "id": {
        # ── Settings (permukaan dwibahasa pertama) ──────────────────────────
        "settings.title": "Pengaturan",
        "settings.security": "Keamanan",
        "settings.security.cap": "Bagaimana vault kamu dilindungi",
        "settings.kdf.label": "Kekuatan enkripsi",
        "settings.kdf.desc": "Derivasi kunci Argon2id — makin kuat makin lambat dibuka.",
        "settings.kdf.interactive": "Interaktif",
        "settings.kdf.interactive.desc": "Buka tercepat. Pemakaian harian.",
        "settings.kdf.moderate": "Sedang",
        "settings.kdf.moderate.desc": "Seimbang antara keamanan & kecepatan.",
        "settings.kdf.paranoid": "Paranoid",
        "settings.kdf.paranoid.desc": "Kekerasan maksimum. Lebih lambat.",
        "settings.defaults": "Default",
        "settings.defaults.cap": "Opsi bawaan untuk tab Kunci",
        "settings.delete_original": "Hapus asli setelah dikunci",
        "settings.delete_original.desc": "Menghapus sumber setelah vault terverifikasi.",
        "settings.destructive": "Merusak.",
        "settings.secure_wipe": "Hapus aman (timpa data)",
        "settings.secure_wipe.desc": "Timpa data sebelum dihapus (lebih lambat).",
        "settings.privacy": "Privasi",
        "settings.privacy.cap": "Kurangi jejak yang tertinggal",
        "settings.clipboard": "Bersihkan clipboard otomatis",
        "settings.clipboard.desc": "Hapus rahasia yang disalin setelah jeda.",
        "settings.off": "Mati",
        "settings.auto_lock": "Kunci otomatis saat idle",
        "settings.auto_lock.desc": "Bersihkan kolom sensitif setelah tidak aktif.",
        "settings.recent": "Ingat vault terakhir",
        "settings.recent.desc": "Tampilkan vault yang baru dikunci atau dibuka untuk akses cepat.",
        "settings.recent.clear": "Bersihkan",
        "settings.notifications": "Notifikasi",
        "settings.notifications.cap": "Pemberitahuan dari aplikasi",
        "settings.tray_notif": "Beri tahu saat diminimize ke tray",
        "settings.tray_notif.desc": "Tampilkan notifikasi saat jendela disembunyikan ke system tray.",
        "settings.appearance": "Tampilan",
        "settings.appearance.cap": "Tampilan & bahasa",
        "settings.theme": "Tema",
        "settings.theme.desc": "Mode gelap disarankan.",
        "settings.theme.dark": "Gelap",
        "settings.theme.system": "Sistem",
        "settings.language": "Bahasa",
        "settings.language.desc": "Bahasa antarmuka.",
        "settings.about": "Tentang",
        "settings.about.cap": "Enkripsi lokal AES-256-GCM + Argon2id",
        "settings.about.build": "Versi pra-rilis.",
        "settings.reset": "Setel ulang ke default",
        "settings.done": "Selesai",
        "settings.seconds": "{n} detik",
        "settings.minutes": "{n} mnt",
        # ── Umum ────────────────────────────────────────────────────────────
        "common.cancel": "Batal",
        "common.continue": "Lanjut",
        "common.remove": "Hapus",
        "common.close": "Tutup",
        "common.gotit": "Mengerti",
        "common.yes": "ya",
        "common.no": "tidak",
        # ── Sidebar navigasi ────────────────────────────────────────────────
        "nav.lock": "Kunci",
        "nav.open": "Buka",
        "nav.text": "Teks",
        "nav.manage": "Kelola",
        "nav.settings": "Pengaturan",
        "nav.lock.tip": "Tab Kunci Folder",
        "nav.open.tip": "Tab Buka Vault",
        "nav.text.tip": "Tab Enkripsi Teks",
        "nav.manage.tip": "Tab Kelola Vault",
        # ── Header halaman + topbar + footer ────────────────────────────────
        "header.lock.title": "Kunci Folder",
        "header.lock.sub": "Pilih file atau folder, atur password, lalu kunci.",
        "header.open.title": "Buka Vault",
        "header.open.sub": "Pilih file vault terenkripsi dan masukkan password untuk membukanya.",
        "header.text.title": "Teks",
        "header.text.sub": "Enkripsi atau dekripsi teks dengan password.",
        "header.manage.title": "Kelola Vault",
        "header.manage.sub": "Ganti password atau recovery key vault yang sudah ada.",
        "status.aes": "AES-256 • GCM",
        "status.local": "Enkripsi lokal aktif",
        "footer.safe": "Password kamu tidak pernah dikirim ke mana pun",
        "footer.version": "Versi {v}",
        # ── Tray menu ───────────────────────────────────────────────────────
        "tray.open": "Buka Adyton Crypt",
        "tray.replay": "Putar Ulang Pengenalan",
        "tray.quit": "Keluar Sepenuhnya",
        # ── Lock antar-operasi / quit / close ───────────────────────────────
        "locks.switch_msg": "Kamu bisa berpindah tab, tapi operasi baru ditunda sampai yang berjalan selesai.",
        "quit.title": "Operasi Sedang Berjalan",
        "quit.msg": "Adyton sedang mengenkripsi atau mendekripsi file.\n\nKeluar sekarang bisa merusak file atau menyebabkan kehilangan data. Tunggu sampai selesai, atau batalkan operasinya dulu.",
        "close.title": "{app} masih berjalan",
        "close.msg": "Adyton ada di System Tray. Operasi yang sedang berjalan akan dilanjutkan di latar belakang.",
        # ── Status bersama antar-operasi ────────────────────────────────────
        "busy.other.title": "Operasi lain sedang berjalan",
        "busy.other.sub": "Tunggu sampai selesai, atau batalkan dulu",
        "busy.other.warn": "Operasi lain sedang berjalan. Tunggu sampai selesai atau batalkan proses yang berjalan.",
        "notif.cancelled": "Operasi dibatalkan.",
        # ── Kartu password bersama ──────────────────────────────────────────
        "card.setpw.title": "Atur Password",
        "card.setpw.sub.lock": "Password kuat menjaga data kamu tetap aman",
        "card.setpw.sub.text": "Password kuat menjaga teks kamu tetap aman",
        "card.enterpw.title": "Masukkan Password",
        "card.enterpw.sub.text": "Masukkan password yang kamu pakai saat mengenkripsi",
        "generator": " Generator",
        # ── Form pembuatan password ─────────────────────────────────────────
        "pw.label": "Password",
        "pw.confirm": "Konfirmasi Password",
        "pw.placeholder": "Masukkan password yang kuat…",
        "pw.confirm_placeholder": "Ulangi password kamu…",
        "pw.match": "Password cocok",
        "pw.nomatch": "Password tidak cocok",
        "pw.strength": "Kekuatan",
        "pw.strength.val": "Kekuatan: {label}",
        "pw.strength.none": "Kekuatan: -",
        "pw.weak": "Lemah",
        "pw.fair": "Cukup",
        "pw.strong": "Kuat",
        "pw.verystrong": "Sangat Kuat",
        "pw.chk.len": "Minimal 8 karakter",
        "pw.chk.upper": "Huruf besar (A-Z)",
        "pw.chk.lower": "Huruf kecil (a-z)",
        "pw.chk.num": "Angka (0-9)",
        "pw.chk.sym": "Simbol (!@#$%^&*)",
        # ── Tab Kunci ───────────────────────────────────────────────────────
        "lock.action.title": "Kunci Sekarang",
        "lock.action.sub": "Klik untuk mulai mengenkripsi file kamu",
        "lock.action.delete.title": "Enkripsi & Hapus Asli",
        "lock.action.delete.sub": "File asli akan dihapus setelah dikunci",
        "lock.busy.title": "Mengunci vault",
        "lock.busy.sub": "Menyiapkan data • Klik untuk membatalkan",
        "lock.status.ready": "Siap dikunci",
        "lock.status.ready.sub": "Target & password siap",
        "lock.status.complete_pw": "Lengkapi password",
        "lock.status.complete_pw.sub": "Buat password yang kuat",
        "lock.status.locking": "Mengunci vault",
        "lock.status.locking.sub": "Biarkan aplikasi tetap terbuka",
        "lock.status.locked": "Terkunci",
        "lock.status.locked.sub": "Vault berhasil dibuat",
        "lock.status.cancelled": "Dibatalkan",
        "lock.status.cancelled.sub": "Proses penguncian dibatalkan",
        "lock.status.failed": "Gagal mengunci",
        "lock.status.failed.sub": "Periksa file, izin, atau ruang disk yang tersedia",
        "lock.notif.locked": "Vault terkunci dengan aman.",
        "lock.recovery.empty": "Masukkan recovery passphrase, atau matikan recovery key.",
        "lock.dialog.delete.title": "Konfirmasi Hapus",
        "lock.dialog.delete.msg": "File atau folder asli akan dihapus permanen setelah vault dibuat dan diverifikasi.\n\nPastikan kamu punya cadangan untuk hal-hal penting sebelum melanjutkan.",
        "lock.save_vault": "Simpan Vault",
        "lock.save_filter": "File Terkunci (*.adtn)",
        # ── Tab Buka ────────────────────────────────────────────────────────
        "open.action.title": "Buka Vault",
        "open.action.sub": "Masukkan password untuk membuka",
        "open.action.sub2": "Masukkan password untuk membuka kunci",
        "open.busy.title": "Membuka vault",
        "open.busy.sub": "Menyiapkan vault • Klik untuk membatalkan",
        "open.status.ready": "Vault siap dibuka",
        "open.status.ready.sub": "Format valid • Belum diverifikasi",
        "open.status.notverified": "Belum diverifikasi",
        "open.status.invalid": "File tidak valid",
        "open.status.verifying": "Memverifikasi vault",
        "open.status.verifying.sub": "Biarkan aplikasi tetap terbuka",
        "open.status.verified": "Terverifikasi",
        "open.status.verified.sub": "Data berhasil dibuka",
        "open.status.cancelled": "Dibatalkan",
        "open.status.cancelled.sub": "File sementara dibersihkan",
        "open.status.failed": "Verifikasi gagal",
        "open.status.failed.sub": "Password salah atau file rusak",
        "open.status.failopen": "Gagal membuka",
        "open.status.failopen.sub": "Periksa file, izin, atau ruang disk yang tersedia",
        "open.restored": "'{name}' berhasil dipulihkan.",
        "open.notif.opened": "Vault dibuka — '{name}' siap.",
        "open.overwrite.title": "File Sudah Ada",
        "open.overwrite.msg": "File atau folder bernama '{name}' sudah ada di lokasi ini.\n\nAdyton akan mengekstrak ke folder sementara dulu, dan baru menggantikan data yang ada setelah vault berhasil dibuka.\n\nGanti data yang ada?",
        "open.overwrite.replace": "Ganti Data",
        # ── Panel password Tab Buka ─────────────────────────────────────────
        "open.pw.title": "Masukkan Password",
        "open.pw.sub": "Masukkan password yang kamu pakai saat mengunci vault ini.",
        "open.pw.opening.title": "Membuka Vault",
        "open.pw.opening.sub": "Vault sedang diverifikasi dan diekstrak.",
        "open.pw.failed.title": "Gagal Membuka Vault",
        "open.pw.failed.sub": "Password salah, file rusak, atau format tak didukung.",
        "open.pw.placeholder": "Ketik password kamu di sini…",
        "open.pw.placeholder.recovery": "Password atau recovery key…",
        "open.pw.hint": "Petunjuk: {hint}",
        "open.pw.status.intro": "Vault kamu sedang diverifikasi dan diekstrak. Biarkan aplikasi terbuka dan drive tetap terhubung sampai selesai.",
        "open.pw.status.file": "File",
        "open.pw.status.size": "Ukuran",
        "open.pw.status.stage": "Tahap",
        "open.pw.status.preparing": "Menyiapkan vault",
        "open.pw.error": "Password salah atau file vault rusak.",
        "open.pw.retry": "Coba Lagi",
        "open.pw.pickfile": "Pilih File Lain",
        "open.tip.1": "Password kamu tidak bisa dipulihkan. Simpan di tempat aman.",
        "open.tip.2": "Pakai password yang sama persis seperti saat mengunci vault ini.",
        "open.tip.3": "Hanya file .adtn buatan Adyton Crypt yang bisa dibuka.",
        # ── Tab Teks ────────────────────────────────────────────────────────
        "text.action.enc.title": "Enkripsi Teks",
        "text.action.enc.sub": "Masukkan teks dan buat password untuk mulai",
        "text.action.dec.title": "Dekripsi Teks",
        "text.action.dec.sub": "Masukkan teks terenkripsi dan password untuk membuka",
        "text.processing.title": "Memproses…",
        "text.processing.enc": "Mengenkripsi teks…",
        "text.processing.dec": "Mendekripsi teks…",
        "text.status.ready": "Siap diproses",
        "text.status.ready.enc": "Teks & password siap dienkripsi",
        "text.status.ready.dec": "Teks & password siap didekripsi",
        "text.status.processing": "Memproses teks",
        "text.status.processing.sub": "Sebentar lagi",
        "text.status.success": "Berhasil",
        "text.status.success.sub": "Hasil disalin ke clipboard",
        "text.status.failed": "Gagal",
        "text.status.failed.sub": "Periksa password atau format teksmu",
        "text.empty": "Teks tidak boleh kosong.",
        "text.pw_empty": "Password tidak boleh kosong.",
        "text.limit": "Teks mencapai maksimum {n} karakter.",
        "text.notif.enc.title": "Teks berhasil dienkripsi",
        "text.notif.dec.title": "Teks berhasil didekripsi",
        "text.notif.body": "Disalin ke clipboard — terhapus otomatis dalam {s}d.",
        "text.notif.enc.ok": "✓ Teks berhasil dienkripsi — disalin (terhapus otomatis dalam {s}d).",
        "text.notif.dec.ok": "✓ Teks berhasil didekripsi — disalin (terhapus otomatis dalam {s}d).",
        "text.err.wrong": "Password salah, atau teks terenkripsi sudah diubah atau rusak.",
        "text.err.format": "Format tidak valid. Pastikan teks terenkripsi diawali 'ADTN_TEXT:1:'.",
        "text.err.enc": "Enkripsi gagal. {detail}",
        "text.err.dec": "Dekripsi gagal. {detail}",
        # input card
        "text.input.title": "Input teks",
        "text.input.sub": "Ketik atau tempel teks yang ingin dienkripsi/didekripsi",
        "text.input.paste": " Tempel",
        "text.input.clear": "Bersihkan",
        "text.input.placeholder": "Ketik atau tempel teks di sini…\n\nTip: Tempel teks terenkripsi (ADTN_TEXT:1:…) untuk mendekripsinya.",
        "text.input.count": "{n} karakter",
        "text.input.count_max": "{n} / {max} karakter (maks)",
        "text.input.clipboard_empty": "Clipboard kosong atau tidak berisi teks.",
        "text.mode.enc": " Enkripsi",
        "text.mode.dec": " Dekripsi",
        "text.decrypt_placeholder": "Ketik password kamu di sini…",
        "text.tip.1": "Password kamu tidak bisa dipulihkan. Simpan di tempat aman.",
        "text.tip.2": "Hasil terenkripsi bisa disimpan di mana saja — email, catatan, chat.",
        "text.tip.3": "Untuk mendekripsi, pakai password yang sama persis dengan yang kamu atur di sini.",
        # result card
        "text.result.enc.title": "Hasil Enkripsi",
        "text.result.enc.sub": "Salin dan simpan teks terenkripsi di bawah",
        "text.result.enc.sub2": "Salin dan simpan teks terenkripsi ini — hanya bisa didekripsi dengan password yang sama",
        "text.result.dec.title": "Hasil Dekripsi",
        "text.result.dec.sub": "Teks asli kamu sudah dipulihkan",
        "text.result.copy": " Salin ke Clipboard",
        "text.result.qr": " QR",
        "text.result.copied": "✓ Disalin — terhapus otomatis dalam {s}d",
        # ── Tab Kelola ──────────────────────────────────────────────────────
        "manage.title": "Kelola Vault",
        "manage.sub": "Ganti password atau recovery key vault yang sudah ada",
        "manage.select": "Pilih file vault untuk dikelola.",
        "manage.current_label": "Password atau recovery key saat ini",
        "manage.current_placeholder": "Masukkan password atau recovery key saat ini…",
        "manage.seg.pw": " Ganti password",
        "manage.seg.rec": " Recovery key",
        "manage.btn.change": "Ganti Password",
        "manage.btn.add": "Tambah Recovery Key",
        "manage.btn.remove": "Hapus Recovery Key",
        "manage.unsupported": "Vault ini dibuat oleh versi Adyton Crypt yang berbeda ({fmt}) dan tidak bisa dikelola di sini. Mohon perbarui aplikasi.",
        "manage.info": "Format {fmt} · Recovery key: {rec} · Petunjuk: {hint}",
        "manage.has_recovery": "Vault ini punya recovery key.",
        "manage.method_label": "Metode recovery",
        "manage.passphrase_placeholder": "Passphrase pemulihan…",
        "manage.guard.select": "Pilih file vault untuk dikelola dulu.",
        "manage.guard.current": "Masukkan password atau recovery key saat ini.",
        "manage.invalid_pw": "Pilih password baru yang memenuhi semua syarat.",
        "manage.passphrase_empty": "Masukkan recovery passphrase.",
        "manage.remove.title": "Hapus Recovery Key",
        "manage.remove.msg": "Recovery key untuk vault ini akan dihapus. Setelah itu, hanya password yang bisa membukanya.\n\nHapus recovery key?",
        "manage.ready": "Siap dikelola",
        "manage.ready.sub": "Masukkan password saat ini",
        "manage.different_version": "Versi berbeda ({fmt}) — tidak bisa dikelola di sini",
        "manage.status.idle.title": "Kelola vault",
        "manage.status.idle.sub": "Pilih vault untuk dikelola",
        "manage.status.unsupported.title": "Format tak didukung",
        "manage.status.unsupported.sub": "Perbarui aplikasi untuk mengelola",
        "manage.status.working.title": "Bekerja",
        "manage.status.working.sub": "Memperbarui vault",
        "manage.status.done.title": "Selesai",
        "manage.status.done.sub": "Vault berhasil diperbarui",
        "manage.status.wrong.title": "Kredensial salah",
        "manage.status.wrong.sub": "Coba lagi",
        "manage.status.failed.title": "Gagal",
        "manage.status.failed.sub": "Tidak bisa memperbarui vault",
        "manage.done": "Vault berhasil diperbarui.",
        "manage.wrong": "Password atau recovery key saat ini salah.",
        "manage.fail": "Tidak bisa memperbarui vault.",
        "manage.notif.updated": "Kredensial vault diperbarui.",
        # ── Recovery + hint (Tab Kunci) ─────────────────────────────────────
        "recovery.add.title": "Tambah recovery key",
        "recovery.add.desc": "Cara kedua masuk jika kamu lupa password.",
        "recovery.method": "Metode recovery",
        "recovery.card.code.title": "Buat kode",
        "recovery.card.code.desc": "Buat kode recovery sekali pakai, ditampilkan sekali.",
        "recovery.card.pass.title": "Pakai passphrase",
        "recovery.card.pass.desc": "Atur frasa recovery pilihanmu sendiri.",
        "recovery.passphrase_placeholder": "Passphrase pemulihan…",
        "recovery.infobox": "Simpan recovery key di tempat yang aman — kamu akan membutuhkannya untuk masuk kembali.",
        "hint.title": "Petunjuk password (opsional)",
        "hint.placeholder": "mis. perjalanan pertama kita bersama",
        "hint.warn": "Disimpan tanpa enkripsi di vault — jangan pernah menaruh password asli kamu di sini.",
        # ── Opsi (Tab Kunci) ────────────────────────────────────────────────
        "options.delete.title": "Hapus asli setelah dikunci",
        "options.delete.desc": "Penghapusan standar — cepat & aman untuk SSD.",
        "options.secure.title": "Lanjutan: Hapus Aman (timpa data)",
        "options.secure.desc": "Lebih lambat — untuk HDD atau data sangat sensitif.",
        "options.secure.dialog.title": "Perhatian: Kompatibilitas Hardware",
        "options.secure.dialog.msg": "Hapus Aman menimpa data asli dengan byte acak sebelum menghapus, sehingga pemulihan jauh lebih sulit.\n\nPenting:\n• Hindari ini di SSD — penimpaan berulang mempercepat keausan drive.\n• Pakai hanya untuk hard disk tradisional (HDD).\n\nAktifkan Hapus Aman?",
        # ── Drop zone (Buka / Kelola) ───────────────────────────────────────
        "dz.empty.main": "Seret & lepas file .adtn di sini",
        "dz.empty.sub": "atau klik tombol di bawah untuk memilih file",
        "dz.empty.browse": " Pilih File Vault",
        "dz.empty.footer": "Hanya file vault .adtn yang bisa dibuka di sini",
        "dz.filled.title": "File Vault (.adtn)",
        "dz.filled.sub": "Pilih file vault yang ingin dibuka.",
        "dz.ready": "Siap dibuka",
        "dz.change": "  Ganti File Vault",
        "dz.meta.size": "Ukuran File",
        "dz.meta.created": "Dibuat",
        "dz.meta.enc": "Enkripsi",
        "dz.meta.status": "Status",
        "dz.meta.waiting": "Menunggu password",
        "dz.sec.title": "Detail Keamanan",
        "dz.sec.enc": "Enkripsi",
        "dz.sec.kdf": "KDF",
        "dz.sec.format": "Format",
        "dz.sec.integrity": "Integritas",
        "dz.sec.notverified": "Belum diverifikasi",
        "dz.choose_dialog": "Pilih File Vault",
        "dz.choose_filter": "File Adyton Crypt (*.adtn)",
        "dz.status.valid": "Format valid",
        "dz.status.verifying": "Memverifikasi",
        "dz.status.verified": "Terverifikasi",
        "dz.status.verifying_pw": "Memverifikasi password",
        "dz.status.integrity_verified": "Integritas terverifikasi",
        "dz.status.wrong": "Password salah atau file rusak",
        "dz.status.verification_failed": "Verifikasi gagal",
        "dz.status.unsupported": "Format tak didukung",
        "dz.status.unsupported_here": "Tak didukung di sini",
        "dz.recent.clear": "Bersihkan",
        "dz.recent.remove": "Hapus dari daftar",
        "dz.recent.missing": "hilang",
        "recentbar.title": "Vault Terakhir",
        "recentbar.sub": "Akses cepat ke vault yang pernah kamu pakai",
        # ── Onboarding ──────────────────────────────────────────────────────
        "onboard.brand_sub": "Enkripsi file lokal, dengan tenang",
        "onboard.loading": "Memuat modul aman…",
        "onboard.step1.eyebrow": "SELAMAT DATANG DI ADYTON CRYPT",
        "onboard.step1.title": "Enkripsi apa saja. Simpan di perangkatmu.",
        "onboard.step1.body": "Adyton Crypt mengunci file, folder, dan catatanmu di balik enkripsi kuat — langsung di komputermu. Tanpa akun, tanpa cloud, tanpa server.",
        "onboard.step2.eyebrow": "PRIVAT SEJAK DESAIN",
        "onboard.step2.title": "Datamu tidak pernah meninggalkan mesin ini.",
        "onboard.step2.body": "Setiap kunci dan buka terjadi offline. Password dan filemu diproses sepenuhnya di perangkatmu, dan tidak pernah diunggah, disinkronkan, atau dikirim ke mana pun.",
        "onboard.step3.eyebrow": "TIGA ALAT, SATU VAULT",
        "onboard.step3.title": "Kunci folder, buka vault, enkripsi teks.",
        "onboard.step3.body": "Tiga alat fokus berbagi alur kerja yang sama tenangnya — jadi melindungi sesuatu selalu terasa sama.",
        "onboard.step4.eyebrow": "SEMUA SIAP",
        "onboard.step4.title": "Satu hal yang perlu diingat.",
        "onboard.step4.body": "Passwordmu adalah satu-satunya kunci. Adyton tidak bisa mereset atau memulihkannya — jika hilang, datanya hilang selamanya. Simpan di tempat aman.",
        "onboard.s1.focal": "Enkripsi lokal, dengan tenang",
        "onboard.s1.chip1": "Tanpa daftar",
        "onboard.s1.chip2": "Bekerja sepenuhnya offline",
        "onboard.s1.chip3": "Format .adtn terbuka",
        "onboard.s2.pill": "100% offline · tanpa jaringan",
        "onboard.s2.row1.title": "AES-256-GCM",
        "onboard.s2.row1.sub": "Enkripsi terotentikasi untuk setiap byte",
        "onboard.s2.row2.title": "Proteksi kunci Argon2id",
        "onboard.s2.row2.sub": "Pertahanan lambat & memory-hard melawan tebakan",
        "onboard.s2.row3.title": "Tanpa akses jaringan",
        "onboard.s2.row3.sub": "Adyton tidak pernah membuka koneksi",
        "onboard.s3.pill": "Tiga alat fokus, satu alur kerja",
        "onboard.s3.row1.title": "Kunci Folder",
        "onboard.s3.row1.sub": "Bungkus seluruh folder jadi satu vault .adtn",
        "onboard.s3.row2.title": "Buka Vault",
        "onboard.s3.row2.sub": "Buka kembali dan ekstrak vault yang kamu kunci sebelumnya",
        "onboard.s3.row3.title": "Enkripsi Teks",
        "onboard.s3.row3.sub": "Ubah catatan privat jadi sandi yang bisa dibagikan",
        "onboard.s4.pill": "Kuncimu, tanggung jawabmu",
        "onboard.s4.notice1.title": "Enkripsi kuat, siap pakai",
        "onboard.s4.notice1.sub": "AES-256-GCM dan Argon2id, sepenuhnya di perangkat ini.",
        "onboard.s4.notice2.title": "Passwordmu tidak bisa dipulihkan",
        "onboard.s4.notice2.sub": "Jika kamu kehilangannya, datanya hilang selamanya — simpan dengan aman.",
        "onboard.back": "Kembali",
        "onboard.skip": "Lewati tur",
        "onboard.continue": "Lanjut",
        "onboard.getstarted": "Mulai",
        "onboard.done.title": "Semua siap",
        "onboard.done.body": "Adyton Crypt sudah siap. Dari sini aplikasi membuka ke alat-alatmu — kunci folder pertamamu kapan pun kamu siap.",
        "onboard.done.replay": "Putar ulang pengenalan",
        "onboard.done.open": "Buka Adyton Crypt",
        # ── Tambahan (dialog recovery, toggle mata, status drop zone, dll) ──
        "pw.show": "Tampilkan password",
        "pw.hide": "Sembunyikan password",
        "open.awaiting": "Terverifikasi, menunggu konfirmasi",
        "open.failopen.dz": "Gagal membuka file",
        "open.pw.status.processing": "Memproses",
        "recovery.dialog.title": "Simpan recovery key kamu",
        "recovery.dialog.msg": "Ini satu-satunya cara kembali ke vault jika kamu lupa password. Kode ini tidak bisa ditampilkan lagi atau dipulihkan untukmu — simpan di tempat aman.",
        "recovery.dialog.copy": " Salin recovery key",
        "recovery.dialog.gate": "Saya sudah menyimpan recovery key",
        "recovery.dialog.copied": "✓ Disalin — clipboard terhapus otomatis dalam {s}d",
        "text.result.qr.tip": "Tampilkan hasil enkripsi sebagai kode QR untuk dipindai dengan kamera ponsel",
        # ── Drop zone Tab Kunci ─────────────────────────────────────────────
        "dzl.menu.file": "File",
        "dzl.menu.folder": "Folder",
        "dzl.empty.main": "Seret & lepas file atau folder di sini",
        "dzl.empty.sub": "atau klik tombol di bawah untuk memilih manual",
        "dzl.empty.browse": " Pilih Target",
        "dzl.empty.footer": "Mendukung semua format file dan folder tanpa batas",
        "dzl.list.title": "Daftar target",
        "dzl.list.sub": "Pilih file atau folder yang ingin dikunci",
        "dzl.file": "file",
        "dzl.files": "file",
        "dzl.summary": "{n} {noun} · {total} total",
        "dzl.choose_folder": "Pilih Folder",
        "dzl.choose_files": "Pilih File",
        "dzl.already_vault": "⚠ '{name}' sudah berupa file vault!",
        "dzl.clear.title": "Bersihkan Daftar Target",
        "dzl.clear.msg": "Yakin ingin menghapus semua {n} target dari daftar?",
        "dzl.clear.btn": "Bersihkan",
        # ── Dialog QR ───────────────────────────────────────────────────────
        "qr.title": "Bagikan via Kode QR",
        "qr.info": "Pindai dengan kamera ponsel untuk mentransfer teks terenkripsi.\nQR ini aman dilihat siapa pun — isinya tetap terkunci tanpa password.",
        "qr.save": " Simpan PNG",
        "qr.saved": " Tersimpan ✓",
        "qr.save_dialog": "Simpan Kode QR",
        "qr.png_filter": "Gambar PNG (*.png)",
        # ── Nama aksesibilitas (screen reader) ──────────────────────────────
        "a11y.gen_password": "Buat password kuat",
        "a11y.toggle_password": "Tampilkan atau sembunyikan password",
        "a11y.btn.encrypt_text": "Tombol Enkripsi Teks",
        "a11y.btn.lock_vault": "Tombol Kunci Vault",
        "a11y.btn.open_vault": "Tombol Buka Vault",
        "a11y.btn.add_target": "Tambah Target",
        "a11y.btn.clear_targets": "Bersihkan Semua Target",
        "a11y.btn.paste": "Tempel teks dari clipboard",
        "a11y.btn.clear_input": "Bersihkan teks input",
        "a11y.btn.copy_result": "Salin hasil ke clipboard",
        "a11y.btn.show_qr": "Tampilkan kode QR hasil enkripsi",
        "a11y.list.targets": "Daftar Target",
        "a11y.list.targets_desc": "Daftar file dan folder untuk dikunci. Gunakan tombol hapus atau tombol Delete di keyboard.",
        "a11y.pw.new": "Password baru",
        "a11y.pw.confirm": "Konfirmasi password baru",
        "a11y.pw.open_vault": "Password untuk membuka vault",
        "a11y.pw.text_decrypt": "Password dekripsi teks",
        "a11y.pw.recovery_passphrase": "Passphrase recovery",
        "a11y.pw.hint": "Petunjuk password",
        "a11y.manage.current": "Password atau recovery key saat ini",
        "a11y.manage.new_rec": "Passphrase recovery baru",
        "a11y.switch.saved_recovery": "Saya sudah menyimpan recovery key",
        "a11y.switch.add_recovery": "Tambah recovery key",
        "a11y.switch.delete_original": "Hapus file asli setelah dikunci",
        "a11y.switch.secure_wipe": "Hapus Aman — timpa data asli",
    }
}


class _I18n(QObject):
    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lang = "en"

    def language(self) -> str:
        return self._lang

    def set_language(self, lang: str) -> None:
        lang = lang if lang in ({"en"} | set(_TRANSLATIONS)) else "en"
        if lang != self._lang:
            self._lang = lang
            self.language_changed.emit(lang)

    def tr(self, key: str, default: str) -> str:
        if self._lang == "en":
            return default
        return _TRANSLATIONS.get(self._lang, {}).get(key, default)


_i18n = _I18n()


def i18n() -> _I18n:
    return _i18n


def tr(key: str, default: str) -> str:
    return _i18n.tr(key, default)


# ── Retranslate app-wide (tag + tree-walk) ──────────────────────────────────
def register(widget, key: str, default: str, setter: str = "setText"):
    """Setel teks widget SEKARANG dan tandai agar ``retranslate(root)`` bisa
    menyetel ulang saat bahasa berganti.

    ``setter`` = nama method satu-argumen (``setText``, ``setPlaceholderText``,
    ``setToolTip``, ``setAccessibleName``, ``setWindowTitle``). Boleh dipanggil
    beberapa kali untuk satu widget (mis. teks + tooltip), tiap pendaftaran
    disimpan dan diterapkan ulang.
    """
    metas = getattr(widget, "_i18n_metas", None)
    if metas is None:
        metas = []
        try:
            widget._i18n_metas = metas
        except (AttributeError, TypeError):
            # Widget tak menerima atribut dinamis — setel sekali tanpa retranslate.
            fn = getattr(widget, setter, None)
            if callable(fn):
                fn(tr(key, default))
            return widget
    metas.append((key, default, setter))
    fn = getattr(widget, setter, None)
    if callable(fn):
        fn(tr(key, default))
    return widget


def retranslate(root) -> None:
    """Terapkan ulang semua teks terdaftar di bawah ``root`` (termasuk root)."""
    for w in (root, *root.findChildren(QWidget)):
        metas = getattr(w, "_i18n_metas", None)
        if not metas:
            continue
        for key, default, setter in metas:
            fn = getattr(w, setter, None)
            if callable(fn):
                fn(tr(key, default))
