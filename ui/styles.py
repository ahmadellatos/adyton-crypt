"""
Modul: styles.py
Deskripsi: Token warna + stylesheet (QSS) utama aplikasi, mengikuti
           "Adyton Crypt — Design System" (dark-teal, tenang & minimal).

           Prinsip: satu keluarga font (Plus Jakarta Sans untuk UI, JetBrains
           Mono untuk payload), aksen teal kalem (#4FBFC9) yang hemat, sudut
           lembut berskala (input 15 → kartu 22), elevasi hanya dari bayangan
           gelap halus — tanpa glow/halo neon.
"""

# =============================================================================
# TOKEN WARNA (COLOR PALETTE) — sesuai Design System §2
# =============================================================================

# --- PERMUKAAN & GARIS ---
CLR_CANVAS = "#0E1B21"  # Latar paling bawah
CLR_WINDOW = "#16282E"  # Badan jendela / area konten
CLR_CARD = "#1B2F36"  # Kartu konten
CLR_INSET = "#13242A"  # Titlebar, input, inset, bar
CLR_BORDER_WINDOW = "#243A41"  # Border jendela
CLR_BORDER = "#253D44"  # Border kartu
CLR_LINE = "#1E343A"  # Pembatas tipis

# Alias kompatibilitas dengan kode lama (nama token tetap, nilai diremap):
CLR_BG = CLR_WINDOW  # dulu latar paling bawah; kini = badan jendela
CLR_INNER = CLR_INSET  # dulu permukaan inner; kini = inset/bar
CLR_BORDER_SUBTLE = "rgba(30, 52, 58, 0.5)"  # pembatas halus (mis. footer)

# --- AKSEN & SEMANTIK ---
CLR_ACCENT = "#4FBFC9"  # Aksi utama, fokus, aktif
CLR_ACCENT_HOVER = "#62CDD6"  # Hover aksi utama
CLR_ACCENT_DK = "#3CA9B2"  # Aktif/tekan aksi utama
CLR_ACCENT_DK_HOVER = "#3CA9B2"  # (alias) hover-tekan
CLR_ACCENT_DISABLED = "rgba(19, 36, 42, 0.85)"
CLR_ACCENT_TEXT = "#7FD6DF"  # Teal heading/ikon di atas latar gelap (eyebrow, ikon onboarding)

# --- STATUS & ALERT ---
CLR_DANGER = "#E89089"  # Error / hapus
CLR_DANGER_HOVER = "#EFA39D"
CLR_DANGER_BG = "#33181A"  # Notification bar — err

CLR_WARN = "#E8A855"  # Warning / notif
CLR_WARN_DK = "#D9963F"  # Secure wipe checkbox (warning gelap)
CLR_WARN_BG = "#332815"  # Notification bar — warn
CLR_WARN_TEXT = "#E8C79A"  # Teks warning lebih terang (pill bertint warning)

CLR_SUCCESS = "#86CBA3"  # Valid / berhasil / match
CLR_SUCCESS_BG = "#16322A"  # Notification bar — ok

# --- TEKS ---
CLR_TEXT_MAIN = "#EAF4F5"  # Judul & nilai penting
CLR_TEXT_MUTED = "#A7C0C4"  # Label / teks sekunder
CLR_TEXT_DIM = "#88A2A7"  # Deskripsi & bantuan
CLR_TEXT_FAINT = "#5E787E"  # Placeholder & meta
CLR_MONO_META = "#6E888D"  # Nilai mono / kode

# --- INTERAKSI / STATE (turunan) ---
CLR_HOVER_BG = "#19303A"  # hover tombol sekunder
CLR_HOVER_BORDER = "#33545D"  # border hover / border tombol sekunder
CLR_BTN_BORDER = "#33545D"  # border tombol sekunder default
CLR_INPUT_BORDER = "#2A444C"  # border input default
CLR_LIST_HOVER = "rgba(79, 191, 201, 0.06)"  # baris daftar hover (tint aksen 6%)
CLR_LIST_SELECTED = "rgba(79, 191, 201, 0.10)"  # baris daftar terpilih (tint 10%)
CLR_BTN_TRANSPARENT = "rgba(19, 36, 42, 0.6)"
CLR_PRESSED_BG = "#0F2026"  # tekan tombol sekunder

# --- SCROLLBAR ---
CLR_SCROLL_HANDLE = "#2C474E"
CLR_SCROLL_HOVER = "#365861"
CLR_SCROLL_PRESSED = "#3F656F"

# --- LAIN-LAIN ---
CLR_TIPS_BG = CLR_INSET
CLR_TIPS_BORDER = CLR_LINE

# --- KOMPONEN TEKS GELAP DI ATAS AKSEN ---
CLR_ON_ACCENT = "#072025"  # teks/ikon di atas latar aksen terang

# Fragmen RGB untuk tint aksen/semantik (dipakai inline di komponen)
ACCENT_RGB = "79, 191, 201"
SUCCESS_RGB = "134, 203, 163"
WARN_RGB = "232, 168, 85"
DANGER_RGB = "232, 144, 137"

# Keluarga font
FONT_UI = "'Plus Jakarta Sans', 'Segoe UI', sans-serif"
FONT_MONO = "'JetBrains Mono', 'Cascadia Mono', monospace"


# =============================================================================
# QSS STYLESHEET LOADER
# =============================================================================


def load_stylesheet() -> str:
    return f"""

    /* --- GLOBAL --- */
    QMainWindow {{ background-color: transparent; }}
    QWidget#CentralWidget {{ background-color: {CLR_WINDOW}; }}
    QWidget {{ color: {CLR_TEXT_MAIN}; font-family: {FONT_UI}; font-size: 10.5pt; letter-spacing: 0.1px; }}

    QLabel#Icon {{ font-family: 'Segoe MDL2 Assets', 'Segoe Fluent Icons', sans-serif; background: transparent; }}

    /* --- CARDS & CONTAINERS (sudut lembut, datar) --- */
    QFrame#Card {{
        background-color: {CLR_CARD};
        border-radius: 22px;
        border: 1px solid {CLR_BORDER};
    }}

    #Inner {{
        background-color: {CLR_INSET};
        border-radius: 14px;
        border: 1px solid {CLR_LINE};
    }}

    QFrame#ListItem {{
        background-color: transparent;
        border: none;
        border-bottom: 1px solid {CLR_LINE};
        border-radius: 0px;
    }}
    QFrame#ListItem:hover {{
        background-color: {CLR_LIST_HOVER};
    }}

    QFrame#TipsBox {{
        background-color: {CLR_TIPS_BG};
        border: 1px solid {CLR_TIPS_BORDER};
        border-radius: 14px;
    }}

    /* --- HEADER --- */
    QFrame#HeaderWrapper {{
        background-color: transparent;
    }}

    /* --- STATUS PILL (badge status keamanan kanan atas) --- */
    QFrame#StatusPill {{
        border-radius: 15px;
        background-color: rgba({ACCENT_RGB}, 0.10);
        border: 1px solid rgba({ACCENT_RGB}, 0.30);
    }}
    QFrame#StatusPill[state="busy"], QFrame#StatusPill[state="warn"] {{
        background-color: rgba({WARN_RGB}, 0.10);
        border: 1px solid rgba({WARN_RGB}, 0.30);
    }}
    QFrame#StatusPill[state="success"] {{
        background-color: rgba({SUCCESS_RGB}, 0.10);
        border: 1px solid rgba({SUCCESS_RGB}, 0.30);
    }}
    QFrame#StatusPill[state="error"] {{
        background-color: rgba({DANGER_RGB}, 0.10);
        border: 1px solid rgba({DANGER_RGB}, 0.30);
    }}
    QLabel#StatusPillText {{ background: transparent; }}

    /* --- SIDEBAR / RAIL IKON --- */
    QFrame#Sidebar {{
        background-color: {CLR_INSET};
        border-right: 1px solid {CLR_LINE};
    }}
    QLabel#SidebarSection {{
        color: {CLR_TEXT_DIM};
        font-size: 7.5pt;
        font-weight: 700;
        letter-spacing: 1.5px;
    }}
    QToolButton#NavBtn {{
        background-color: transparent;
        color: {CLR_TEXT_DIM};
        border: 2px solid transparent;
        border-radius: 13px;
        font-weight: 700;
        font-size: 7.5pt;
        padding-top: 6px;
        padding-bottom: 4px;
    }}
    QToolButton#NavBtn:checked {{
        background-color: rgba({ACCENT_RGB}, 0.16);
        color: {CLR_ACCENT};
        font-weight: 700;
    }}
    QToolButton#NavBtn:hover:!checked {{
        background-color: rgba({ACCENT_RGB}, 0.08);
        color: {CLR_TEXT_MAIN};
    }}
    /* Ring fokus hanya untuk tab non-aktif (mis. navigasi keyboard); tab aktif
       sudah ditandai background terisi, jadi ring tidak perlu & tak menyangkut. */
    QToolButton#NavBtn:focus:!checked {{
        border: 2px solid {CLR_ACCENT};
    }}

    /* --- SEGMENTED CONTROL (mis. toggle Enkripsi/Dekripsi) --- */
    QFrame#TabContainer {{
        background-color: {CLR_INSET};
        border-radius: 14px;
        border: 1px solid {CLR_LINE};
    }}

    QPushButton#TabBtn {{
        background-color: transparent;
        color: {CLR_TEXT_MUTED};
        border: none;
        border-radius: 10px;
        font-weight: 700;
        font-size: 9.5pt;
        padding: 6px 18px;
    }}

    QPushButton#TabBtn:checked {{
        background-color: {CLR_ACCENT};
        color: {CLR_ON_ACCENT};
        font-weight: 700;
        border: none;
    }}

    QPushButton#TabBtn:hover:!checked {{
        background-color: rgba({ACCENT_RGB}, 0.08);
        color: {CLR_TEXT_MAIN};
    }}

    QPushButton#TabBtn:focus {{
        border: 2px solid {CLR_ACCENT};
    }}

    QPushButton#TabBtn:checked:focus {{
        background-color: {CLR_ACCENT};
        border: 2px solid {CLR_TEXT_MAIN};
    }}

    /* --- TYPOGRAPHY (skala Design System §3) --- */
    QLabel {{
        background-color: transparent;
        font-size: 10.5pt;
    }}

    /* Judul besar (header aplikasi) — 23/800 */
    QLabel#AppTitle {{
        font-size: 17pt;
        font-weight: 800;
        color: {CLR_TEXT_MAIN};
        letter-spacing: -0.3px;
    }}

    QLabel#AppSubtitle {{
        font-size: 9.5pt;
        color: {CLR_TEXT_DIM};
        font-weight: 500;
    }}

    /* Judul halaman per-tab — 23/800 */
    QLabel#PageTitle {{
        font-size: 17pt;
        font-weight: 800;
        color: {CLR_TEXT_MAIN};
        letter-spacing: -0.3px;
    }}
    QLabel#PageSubtitle {{
        font-size: 9.5pt;
        color: {CLR_TEXT_DIM};
        font-weight: 500;
    }}

    /* Judul kartu — 16/800 */
    QLabel#CardTitle {{
        font-size: 12pt;
        font-weight: 800;
        color: {CLR_TEXT_MAIN};
        letter-spacing: 0.1px;
    }}

    QLabel#TargetHeaderTitle {{
        font-size: 12.5pt;
        font-weight: 800;
        color: {CLR_TEXT_MAIN};
        letter-spacing: 0.3px;
    }}

    QLabel#CardSubtitle {{
        font-size: 9.5pt;
        color: {CLR_TEXT_DIM};
        font-weight: 500;
    }}

    /* Label form & tombol — 13.5/600 */
    QLabel#SectionLabel {{
        font-size: 10pt;
        font-weight: 600;
        color: {CLR_TEXT_MUTED};
    }}

    /* --- CHECKLIST KEKUATAN PASSWORD --- */
    QLabel#ChecklistLabel {{
        font-size: 9pt;
        color: {CLR_TEXT_DIM};
        font-weight: 500;
    }}
    QLabel#ChecklistLabel[valid="true"] {{
        color: {CLR_TEXT_MAIN};
        font-weight: 600;
    }}

    QLabel#PwMatchLabel {{
        font-size: 9pt;
        font-weight: 600;
    }}

    QLabel#OptionDesc {{
        font-size: 9pt;
        color: {CLR_TEXT_DIM};
        font-weight: 500;
    }}

    QLabel#BodyText {{
        font-size: 10.5pt;
        color: {CLR_TEXT_MAIN};
    }}

    QLabel#MutedText {{
        font-size: 9.5pt;
        color: {CLR_TEXT_DIM};
        font-weight: 500;
    }}

    QLabel#AccentText {{
        font-size: 9.5pt;
        color: {CLR_ACCENT};
        font-weight: 700;
    }}

    /* Caption & meta — 12/500 */
    QLabel#CaptionText {{
        font-size: 9pt;
        color: {CLR_TEXT_FAINT};
        font-weight: 500;
    }}

    QLabel#TipText {{
        font-size: 9pt;
        color: {CLR_TEXT_DIM};
        font-weight: 500;
    }}

    QLabel#ErrorText {{
        font-size: 9.5pt;
        color: {CLR_DANGER};
        font-weight: 600;
    }}

    QLabel#SuccessText {{
        font-size: 9.5pt;
        color: {CLR_SUCCESS};
        font-weight: 600;
    }}

    QLabel#WarningText {{
        font-size: 9.5pt;
        color: {CLR_WARN};
        font-weight: 600;
    }}

    /* --- INPUTS (tinggi 54 · radius 15) --- */
    QFrame#InputBox {{
        background-color: {CLR_INSET};
        border: 1.5px solid {CLR_INPUT_BORDER};
        border-radius: 15px;
    }}

    QFrame#InputBox[focused="true"] {{
        background-color: {CLR_CANVAS};
        border: 1.5px solid {CLR_ACCENT};
    }}

    QLineEdit#InputInside {{
        background-color: transparent;
        border: none;
        padding: 0px 8px;
        color: {CLR_TEXT_MAIN};
        font-size: 11pt;
        font-family: {FONT_UI};
    }}

    QPushButton#BtnEye {{
        background-color: transparent;
        border: none;
        color: {CLR_TEXT_DIM};
        padding: 0px 6px;
        margin: 0px;
        border-radius: 11px;
    }}

    QPushButton#BtnEye:hover {{
        color: {CLR_TEXT_MAIN};
    }}

    QLabel#IconInside {{
        background-color: transparent;
        padding: 0px;
        margin: 0px;
    }}

    /* --- FOCUS & A11Y STATES --- */
    * {{ outline: none; }}
    QFrame#InputBox[focused="true"] {{ background-color: {CLR_CANVAS}; border: 1.5px solid {CLR_ACCENT}; }}
    QFrame[checked="true"]:focus, QFrame[checked="false"]:focus {{ border: 2px solid {CLR_TEXT_MAIN}; }}

    /* --- BUTTONS (tombol sekunder/ghost — 46 · radius 13) --- */
    QPushButton {{
        background-color: {CLR_INSET};
        color: {CLR_TEXT_MAIN};
        border: 1px solid {CLR_BTN_BORDER};
        border-radius: 13px;
        font-weight: 700;
        padding: 8px 18px;
        font-size: 9.5pt;
        font-family: {FONT_UI};
        letter-spacing: 0.2px;
    }}
    QPushButton:hover {{
        background-color: {CLR_HOVER_BG};
        border: 1px solid {CLR_HOVER_BORDER};
    }}
    QPushButton:pressed {{
        background-color: {CLR_PRESSED_BG};
    }}
    QPushButton:focus {{
        border: 2px solid {CLR_ACCENT};
        background-color: {CLR_INSET};
    }}
    QPushButton:disabled {{
        background-color: {CLR_ACCENT_DISABLED};
        color: {CLR_TEXT_FAINT};
        border: 1px solid {CLR_LINE};
    }}

    /* --- GHOST & EYE BUTTONS --- */
    QPushButton#BtnGhost {{
        background-color: transparent;
        border: none;
        color: {CLR_TEXT_DIM};
        padding: 4px 8px;
        border-radius: 11px;
    }}
    QPushButton#BtnGhost:hover {{
        background-color: {CLR_HOVER_BG};
        color: {CLR_TEXT_MAIN};
    }}
    QPushButton#BtnGhost:focus, QPushButton#BtnEye:focus {{
        border: 2px solid {CLR_ACCENT};
        background-color: transparent;
        border-radius: 11px;
    }}

    /* --- PRIMARY CTA (aksi utama — pill datar, aksen penuh) --- */
    QPushButton#BtnAksiBesar {{
        background-color: {CLR_ACCENT};
        border: none;
        border-radius: 29px;
        font-weight: 800;
        font-size: 11pt;
        letter-spacing: 0.3px;
        padding: 0px 34px;
        color: {CLR_ON_ACCENT};
    }}
    QPushButton#BtnAksiBesar:hover {{
        background-color: {CLR_ACCENT_HOVER};
    }}
    QPushButton#BtnAksiBesar:pressed {{
        background-color: {CLR_ACCENT_DK};
    }}
    QPushButton#BtnAksiBesar:focus {{
        border: 2px solid {CLR_TEXT_MAIN};
        background-color: {CLR_ACCENT};
    }}
    QPushButton#BtnAksiBesar:disabled {{
        background-color: {CLR_ACCENT_DISABLED};
        border: 1px solid {CLR_LINE};
    }}

    /* Text colors inside #BtnAksiBesar dikontrol di Python (BigActionBtn). */

    /* --- CUSTOM BUTTONS (Browse & Gen) --- */
    QPushButton#BtnBrowseLg {{
        background-color: {CLR_BTN_TRANSPARENT};
        border: 1px solid {CLR_BTN_BORDER};
        border-radius: 13px;
        color: {CLR_TEXT_MAIN};
        font-weight: 700;
        padding: 0 18px;
    }}
    QPushButton#BtnBrowseLg:hover {{
        background-color: {CLR_HOVER_BG};
        border: 1px solid {CLR_HOVER_BORDER};
    }}
    QPushButton#BtnBrowseLg:focus {{
        border: 2px solid {CLR_ACCENT};
        background-color: {CLR_BTN_TRANSPARENT};
    }}
    QPushButton#BtnBrowseLg::menu-indicator {{
        image: none;
        width: 0px;
    }}

    /* Tombol "Ganti File Brankas" */
    QPushButton#BtnGantiFile {{
        background-color: {CLR_INSET};
        border: 1px solid {CLR_BORDER};
        border-radius: 13px;
        color: {CLR_TEXT_MAIN};
        font-weight: 600;
        font-size: 9pt;
        padding: 0 16px;
    }}

    QPushButton#BtnGantiFile:hover {{
        background-color: {CLR_HOVER_BG};
        border-color: {CLR_HOVER_BORDER};
    }}

    QPushButton#BtnGantiFile:focus {{
        border: 1px solid {CLR_ACCENT};
        background-color: {CLR_INSET};
    }}

    QPushButton#BtnGen {{
        background-color: transparent;
        border: 1px solid {CLR_BTN_BORDER};
        border-radius: 11px;
        color: {CLR_TEXT_MAIN};
        font-weight: 700;
        padding: 0 12px;
        font-size: 9pt;
    }}
    QPushButton#BtnGen:hover {{
        background-color: {CLR_HOVER_BG};
        border: 1px solid {CLR_HOVER_BORDER};
    }}
    QPushButton#BtnGen:focus {{
        border: 2px solid {CLR_ACCENT};
        background-color: transparent;
    }}

    /* --- CUSTOM CHECKBOX (20x20 · radius 7) --- */
    QFrame#ChkHapus {{
        background: {CLR_INSET};
        border: 1.5px solid {CLR_INPUT_BORDER};
        border-radius: 7px;
    }}
    QFrame#ChkHapus:hover {{
        border-color: {CLR_ACCENT};
    }}
    QFrame#ChkHapus[checked="true"] {{
        background: {CLR_DANGER};
        border: 1.5px solid {CLR_DANGER};
    }}
    QFrame#ChkHapus:focus {{
        border: 2px solid {CLR_TEXT_MAIN};
    }}

    QFrame#ChkSecure {{
        background: {CLR_INSET};
        border: 1.5px solid {CLR_INPUT_BORDER};
        border-radius: 7px;
    }}
    QFrame#ChkSecure:hover {{
        border-color: {CLR_ACCENT};
    }}
    QFrame#ChkSecure[checked="true"] {{
        background: {CLR_WARN_DK};
        border: 1.5px solid {CLR_WARN_DK};
    }}
    QFrame#ChkSecure:focus {{
        border: 2px solid {CLR_TEXT_MAIN};
    }}

    /* --- MENU DROPDOWN (radius 10 · item radius 7) --- */
    QMenu {{ background-color: {CLR_CARD}; border: 1px solid {CLR_BORDER}; border-radius: 10px; padding: 5px; }}
    QMenu::item {{ border-radius: 7px; background: transparent; padding: 9px 12px; }}
    QMenu::item:selected {{ background-color: {CLR_CARD}; }}

    /* --- SCROLLBAR (w10 · radius 4 · handle 40) --- */
    QScrollBar:vertical {{ border: none; background: transparent; width: 10px; margin: 0px; }}
    QScrollBar::handle:vertical {{ background-color: {CLR_SCROLL_HANDLE}; min-height: 40px; border-radius: 4px; margin: 1px; }}
    QScrollBar::handle:vertical:hover {{ background-color: {CLR_SCROLL_HOVER}; }}
    QScrollBar::handle:vertical:pressed {{ background-color: {CLR_SCROLL_PRESSED}; }}
    QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {{ height: 0px; border: none; background: none; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

    QScrollBar:horizontal {{ border: none; background: transparent; height: 10px; margin: 0px; }}
    QScrollBar::handle:horizontal {{ background-color: {CLR_SCROLL_HANDLE}; min-width: 40px; border-radius: 4px; margin: 1px; }}
    QScrollBar::handle:horizontal:hover {{ background-color: {CLR_SCROLL_HOVER}; }}
    QScrollBar::handle:horizontal:pressed {{ background-color: {CLR_SCROLL_PRESSED}; }}
    QScrollBar::sub-line:horizontal, QScrollBar::add-line:horizontal {{ width: 0px; border: none; background: none; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

    /* --- DROP ZONE — Empty State (radius 16 · border dashed) --- */
    QFrame#DropArea[empty="true"] {{
        border: 1.5px dashed {CLR_BORDER};
        background-color: {CLR_CARD};
        border-radius: 16px;
    }}

    QFrame#DropArea[empty="true"][dragActive="true"] {{
        border: 1.5px dashed {CLR_ACCENT};
        background-color: rgba({ACCENT_RGB}, 0.08);
        border-radius: 16px;
    }}

    QFrame#DropArea[empty="false"] {{
        border: 1px solid {CLR_BORDER};
        background-color: {CLR_CARD};
        border-radius: 22px;
    }}

    QFrame#DropArea[empty="false"][dragActive="true"] {{
        border: 1.5px dashed {CLR_ACCENT};
        background-color: {CLR_INSET};
        border-radius: 22px;
    }}

    /* --- DROP ZONE FILLED STATE (Buka) — kartu file terpilih --- */
    QFrame#FileInfoCard {{
        background-color: {CLR_INSET};
        border: 1px solid {CLR_BORDER};
        border-radius: 16px;
    }}

    QLabel#SelectedFileIcon {{
        background-color: rgba({ACCENT_RGB}, 0.12);
        border: none;
        border-radius: 13px;
    }}

    QLabel#SelectedFileName {{
        color: {CLR_TEXT_MAIN};
        font-size: 10.5pt;
        font-weight: 700;
        letter-spacing: 0.05px;
    }}

    QLabel#FileReadySubtitle {{
        color: {CLR_TEXT_MUTED};
        font-size: 9pt;
        font-weight: 600;
    }}

    QLabel#SelectedFilePath {{
        color: {CLR_TEXT_FAINT};
        font-size: 8.5pt;
        font-weight: 500;
    }}

    QLabel#ValidBadge {{
        background-color: rgba({SUCCESS_RGB}, 0.14);
        color: {CLR_SUCCESS};
        border: 1px solid rgba({SUCCESS_RGB}, 0.28);
        font-size: 8pt;
        font-weight: 700;
        border-radius: 11px;
        padding: 0px 10px;
    }}

    QLabel#ValidBadge[state="ok"] {{
        background-color: rgba({SUCCESS_RGB}, 0.14);
        color: {CLR_SUCCESS};
        border: 1px solid rgba({SUCCESS_RGB}, 0.28);
    }}

    QLabel#ValidBadge[state="verified"] {{
        background-color: rgba({ACCENT_RGB}, 0.16);
        color: {CLR_ACCENT};
        border: 1px solid rgba({ACCENT_RGB}, 0.38);
    }}

    QLabel#ValidBadge[state="busy"] {{
        background-color: rgba({ACCENT_RGB}, 0.10);
        color: {CLR_ACCENT};
        border: 1px solid rgba({ACCENT_RGB}, 0.24);
    }}

    QLabel#ValidBadge[state="warn"], QLabel#ValidBadge[valid="false"] {{
        background-color: rgba({WARN_RGB}, 0.14);
        color: {CLR_WARN};
        border: 1px solid rgba({WARN_RGB}, 0.28);
    }}

    QLabel#ValidBadge[state="error"] {{
        background-color: rgba({DANGER_RGB}, 0.14);
        color: {CLR_DANGER};
        border: 1px solid rgba({DANGER_RGB}, 0.34);
    }}

    QFrame#FileCardDivider {{
        background-color: {CLR_LINE};
        border: none;
    }}

    QFrame#MetaItem {{
        background-color: transparent;
        border: none;
    }}

    QFrame#MetaSeparator {{
        background-color: {CLR_LINE};
        border: none;
    }}

    QLabel#MetaLabel {{
        color: {CLR_TEXT_FAINT};
        font-size: 7.5pt;
        font-weight: 600;
        letter-spacing: 0.4px;
    }}

    QLabel#MetaValue {{
        color: {CLR_TEXT_MAIN};
        font-size: 8.5pt;
        font-weight: 700;
    }}

    /* Valid banner (kompatibilitas) */
    QFrame#ValidBanner {{
        background-color: {CLR_SUCCESS_BG};
        border: 1px solid rgba({SUCCESS_RGB}, 0.24);
        border-radius: 14px;
    }}

    QLabel#BannerTitle {{
        color: {CLR_ACCENT};
        font-size: 9.5pt;
        font-weight: 700;
    }}

    QLabel#BannerDesc {{
        color: {CLR_TEXT_DIM};
        font-size: 8.5pt;
        font-weight: 500;
    }}

    /* INFORMASI ENKRIPSI — header section */
    QLabel#EncSectionTitle {{
        font-size: 10pt;
        font-weight: 700;
        color: {CLR_TEXT_MAIN};
        letter-spacing: 0.1px;
    }}

    QFrame#EncInfoSection {{
        background-color: {CLR_CANVAS};
        border: 1px solid {CLR_BORDER};
        border-radius: 14px;
    }}

    /* --- DROP ZONE EMPTY STATE — teks --- */
    QLabel#DropZoneMainText {{
        font-size: 13pt;
        font-weight: 700;
        color: {CLR_TEXT_MAIN};
        letter-spacing: 0.1px;
    }}

    QLabel#DropZoneSubText {{
        font-size: 10pt;
        color: {CLR_TEXT_DIM};
        font-weight: 500;
    }}

    QLabel#DropZoneFooter {{
        font-size: 8.5pt;
        color: {CLR_TEXT_FAINT};
        font-weight: 500;
    }}

    /* --- Open vault — process / error state --- */
    QFrame#ProcessStatusBox {{
        background-color: rgba({ACCENT_RGB}, 0.07);
        border: 1px solid rgba({ACCENT_RGB}, 0.24);
        border-radius: 14px;
    }}

    QLabel#ProcessText {{
        color: {CLR_TEXT_MUTED};
        font-size: 9pt;
        font-weight: 500;
    }}

    QLabel#ProcessLabel {{
        color: {CLR_TEXT_DIM};
        font-size: 8.5pt;
        font-weight: 600;
    }}

    QLabel#ProcessValue {{
        color: {CLR_TEXT_MAIN};
        font-size: 9pt;
        font-weight: 700;
    }}

    QFrame#OpenErrorBox {{
        background-color: rgba({DANGER_RGB}, 0.08);
        border: 1px solid rgba({DANGER_RGB}, 0.36);
        border-radius: 14px;
    }}

    QLabel#OpenErrorText {{
        color: {CLR_DANGER};
        font-size: 9pt;
        font-weight: 600;
    }}

    QPushButton#BtnInlinePrimary {{
        background-color: {CLR_ACCENT};
        color: {CLR_ON_ACCENT};
        border: none;
        border-radius: 11px;
        padding: 7px 14px;
        font-weight: 800;
    }}
    QPushButton#BtnInlinePrimary:hover {{
        background-color: {CLR_ACCENT_HOVER};
    }}
    QPushButton#BtnInlinePrimary:pressed {{
        background-color: {CLR_ACCENT_DK};
    }}

    QPushButton#BtnInlineSecondary {{
        background-color: transparent;
        color: {CLR_TEXT_MAIN};
        border: 1px solid {CLR_BTN_BORDER};
        border-radius: 11px;
        padding: 7px 14px;
        font-weight: 700;
    }}
    QPushButton#BtnInlineSecondary:hover {{
        border-color: {CLR_ACCENT};
        color: {CLR_ACCENT};
    }}

    /* --- TOOLTIPS & TITLE BAR --- */
    QLabel#CustomToolTip {{ background-color: {CLR_WINDOW}; color: {CLR_TEXT_MAIN}; border: 1px solid {CLR_BORDER}; border-radius: 8px; padding: 7px 12px; font-size: 9pt; font-family: {FONT_UI}; }}

    QToolTip {{
        background-color: {CLR_WINDOW};
        color: {CLR_TEXT_MAIN};
        border: 1px solid {CLR_BORDER};
        border-radius: 8px;
        padding: 7px 12px;
        font-size: 9pt;
        font-family: {FONT_UI};
    }}

    QPushButton#BtnAlertConfirm {{ background-color: {CLR_DANGER}; color: {CLR_ON_ACCENT}; border: 2px solid transparent; border-radius: 11px; font-weight: 800; }}
    QPushButton#BtnAlertConfirm:hover {{ background-color: {CLR_DANGER_HOVER}; }}
    QPushButton#BtnAlertConfirm:focus {{ border: 2px solid {CLR_TEXT_MAIN}; background-color: {CLR_DANGER_HOVER}; }}

    /* Dialog secondary button (Batal) */
    QPushButton#BtnDialogCancel {{
        background-color: transparent;
        border: 1px solid {CLR_BTN_BORDER};
        border-radius: 11px;
        color: {CLR_TEXT_MAIN};
        font-weight: 600;
    }}
    QPushButton#BtnDialogCancel:hover {{
        background-color: {CLR_INSET};
        border-color: {CLR_ACCENT};
    }}
    QPushButton#BtnDialogCancel:focus {{
        border: 2px solid {CLR_ACCENT};
    }}

    QPushButton#TitleMinBtn, QPushButton#TitleMaxBtn, QPushButton#TitleCloseBtn {{ background-color: transparent; border: none; border-radius: 0; }}
    QPushButton#TitleMinBtn:hover, QPushButton#TitleMaxBtn:hover {{ background-color: {CLR_HOVER_BG}; }}
    QPushButton#TitleCloseBtn:hover {{ background-color: {CLR_DANGER}; }}

    /* --- MAIN FOOTER --- */
    QFrame#MainFooter {{
        border-top: 1px solid {CLR_BORDER_SUBTLE};
        background-color: transparent;
    }}

    /* --- NOTIFICATION BARS (latar status pekat, radius 10) --- */
    QFrame#NotifBar[kind="ok"] {{ background-color: {CLR_SUCCESS_BG}; border-radius: 10px; border: none; }}
    QFrame#NotifBar[kind="ok"] QLabel {{ border: none; background: transparent; color: {CLR_SUCCESS}; font-weight: 700; font-size: 10pt; }}

    QFrame#NotifBar[kind="err"] {{ background-color: {CLR_DANGER_BG}; border-radius: 10px; border: none; }}
    QFrame#NotifBar[kind="err"] QLabel {{ border: none; background: transparent; color: {CLR_DANGER}; font-weight: 700; font-size: 10pt; }}

    QFrame#NotifBar[kind="warn"] {{ background-color: {CLR_WARN_BG}; border-radius: 10px; border: none; }}
    QFrame#NotifBar[kind="warn"] QLabel {{ border: none; background: transparent; color: {CLR_WARN}; font-weight: 700; font-size: 10pt; }}
    """


# =============================================================================
# STYLE HELPERS (Untuk mengurangi inline styles di komponen)
# =============================================================================


def body_style(size: str = "10.5pt") -> str:
    """Standard body text."""
    return f"font-size: {size}; color: {CLR_TEXT_MAIN};"


def muted_label_style(size: str = "9.5pt") -> str:
    """Style untuk teks sekunder / keterangan."""
    return f"font-size: {size}; color: {CLR_TEXT_DIM};"


def caption_style(size: str = "9pt") -> str:
    """Very small / footer text."""
    return f"font-size: {size}; color: {CLR_TEXT_FAINT};"


def small_footer_style() -> str:
    """Style untuk teks footer kecil. (Deprecated - use caption_style instead)"""
    return caption_style("9pt")


def error_text_style(size: str = "9.5pt") -> str:
    return f"font-size: {size}; color: {CLR_DANGER}; font-weight: 600;"


def success_text_style(size: str = "9.5pt") -> str:
    return f"font-size: {size}; color: {CLR_SUCCESS}; font-weight: 600;"


def warning_text_style(size: str = "9.5pt") -> str:
    return f"font-size: {size}; color: {CLR_WARN}; font-weight: 600;"


def section_title_style() -> str:
    """Style untuk judul section / card."""
    return f"font-size: 12pt; font-weight: 800; color: {CLR_TEXT_MAIN}; letter-spacing: 0.2px;"


def card_title_style() -> str:
    """Style untuk judul kartu (uppercase version)."""
    return f"font-size: 11pt; font-weight: 800; color: {CLR_TEXT_MAIN}; letter-spacing: 0.6px; text-transform: uppercase;"


def card_subtitle_style() -> str:
    """Style untuk sub-judul kartu."""
    return f"font-size: 9.5pt; color: {CLR_TEXT_DIM};"
