"""
Modul: styles.py
Deskripsi: Mendefinisikan palet warna konstan dan stylesheet (QSS) utama untuk aplikasi.
           Semua nilai diekstrak menjadi token agar mudah dikelola dan menghindari hardcode.
"""

# =============================================================================
# TOKEN WARNA (COLOR PALETTE)
# =============================================================================

# --- TEMA UTAMA ---
CLR_BG = "#0B101E"
CLR_CARD = "#111625"
CLR_INNER = "#181F32"
CLR_BORDER = "#232B3E"

# --- TIPOGRAFI ---
CLR_TEXT_MAIN = "#FFFFFF"
CLR_TEXT_MUTED = "#8B95A5"

# --- AKSEN CYBER TEAL ---
CLR_ACCENT = "#00D2C8"
CLR_ACCENT_DK = "#008780"
CLR_ACCENT_HOVER = "#00EFE5"
CLR_ACCENT_DK_HOVER = "#00A69D"
CLR_ACCENT_DISABLED = "rgba(21, 28, 44, 0.8)"

# --- STATUS & ALERT ---
CLR_DANGER = "#E74C3C"  # Merah (Error / Hapus)
CLR_DANGER_HOVER = "#C0392B"
CLR_DANGER_BG = "#2B0D0D"

CLR_WARN = "#F39C12"  # Oranye/Kuning (Warning / Notif)
CLR_WARN_DK = "#E67E22"  # Oranye gelap (Secure Wipe Checkbox)
CLR_WARN_BG = "#2B1E0D"

CLR_SUCCESS_BG = "#0D2B1E"  # Hijau Gelap (Notif Sukses)
CLR_SUCCESS = "#28C75D"       # Hijau cerah untuk indikator sukses / match

# --- HOVER & INTERAKSI (TRANSPARANSI/STATE) ---
CLR_HOVER_BG = "#232B3E"
CLR_HOVER_BORDER = "#2A344A"
CLR_LIST_HOVER = "rgba(35, 43, 62, 0.5)"
CLR_BTN_TRANSPARENT = "rgba(24, 31, 50, 0.5)"

# --- SCROLLBAR ---
CLR_SCROLL_HANDLE = "#3A445C"
CLR_SCROLL_HOVER = "#4A5468"
CLR_SCROLL_PRESSED = "#5A667A"

# --- LAIN-LAIN ---
CLR_TIPS_BG = "#0E1A24"
CLR_TIPS_BORDER = "#142E3B"


# =============================================================================
# QSS STYLESHEET LOADER
# =============================================================================


def load_stylesheet() -> str:
    return f"""
    
    /* --- GLOBAL --- */
    QMainWindow {{ background-color: transparent; }}
    QWidget#CentralWidget {{ background-color: {CLR_BG}; }}
    QWidget {{ color: {CLR_TEXT_MAIN}; font-family: 'IBM Plex Sans', 'Segoe UI', sans-serif; font-size: 10pt; letter-spacing: 0.1px; }}
    
    QLabel#Icon {{ font-family: 'Segoe MDL2 Assets', 'Segoe Fluent Icons', sans-serif; background: transparent; }}
    
    /* --- CARDS & CONTAINERS --- */
    QFrame#Card {{ background-color: {CLR_CARD}; border-radius: 12px; border: 1px solid {CLR_BORDER}; }}
    #Inner {{ background-color: {CLR_INNER}; border-radius: 8px; border: 1px solid {CLR_BORDER}; }}
    
    QFrame#ListItem {{ background-color: transparent; border: none; border-bottom: 1px solid {CLR_BORDER}; border-radius: 0px; }}
    QFrame#ListItem:hover {{ background-color: {CLR_LIST_HOVER}; }}
    
    QFrame#TipsBox {{ background-color: {CLR_TIPS_BG}; border: 1px solid {CLR_TIPS_BORDER}; border-radius: 8px; }}
    
    /* --- HEADER & TABS --- */
    QFrame#TabContainer {{ background-color: {CLR_CARD}; border-radius: 10px; border: 1px solid {CLR_BORDER}; }}
    QPushButton#TabBtn {{ background-color: transparent; color: {CLR_TEXT_MUTED}; border: none; border-radius: 8px; font-weight: 500; font-size: 10pt; }}
    QPushButton#TabBtn:checked {{ background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT}, stop:1 {CLR_ACCENT_DK}); color: {CLR_TEXT_MAIN}; font-weight: 600; border: 1px solid {CLR_ACCENT_HOVER}; }}
    QPushButton#TabBtn:hover:!checked {{ background-color: {CLR_INNER}; color: {CLR_TEXT_MAIN}; }}
    
    QPushButton#TabBtn:focus {{ border: 2px solid {CLR_ACCENT}; background-color: transparent; }}
    QPushButton#TabBtn:checked:focus {{ background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT}, stop:1 {CLR_ACCENT_DK}); border: 2px solid {CLR_TEXT_MAIN}; }}
    
    /* --- TYPOGRAPHY --- */
    QLabel {{ background-color: transparent; }}
    QLabel#AppTitle {{ font-size: 16pt; font-weight: 600; color: {CLR_TEXT_MAIN}; letter-spacing: -0.2px; }}
    QLabel#AppSubtitle {{ font-size: 9pt; color: {CLR_TEXT_MUTED}; font-weight: 400; }}
    QLabel#CardTitle {{ font-size: 11pt; font-weight: 600; color: {CLR_TEXT_MAIN}; letter-spacing: 0.8px; text-transform: uppercase; }}
    QLabel#CardSubtitle {{ font-size: 9pt; color: {CLR_TEXT_MUTED}; margin-bottom: 5px; }}
    
    /* --- INPUTS --- */
    QFrame#InputBox {{ background-color: {CLR_INNER}; border: 1px solid {CLR_BORDER}; border-radius: 8px; }}
    QLineEdit#InputInside {{ background-color: transparent; border: none; padding: 0px 5px; color: {CLR_TEXT_MAIN}; font-size: 10pt; font-family: 'IBM Plex Sans', sans-serif; }}
    QPushButton#BtnEye {{ background-color: transparent; border: none; color: {CLR_TEXT_MUTED}; padding: 0px; margin: 0px; }}
    QLabel#IconInside {{ background-color: transparent; padding: 0px; margin: 0px; }}
    
    /* --- FOCUS & A11Y STATES --- */
    * {{ outline: none; }}
    QFrame#InputBox[focused="true"] {{ background-color: {CLR_BG}; border: 1px solid {CLR_ACCENT}; }}
    QFrame[checked="true"]:focus, QFrame[checked="false"]:focus {{ border: 2px solid {CLR_TEXT_MAIN}; }}

    /* --- BUTTONS (Standard) --- */
    QPushButton {{ background-color: {CLR_INNER}; color: {CLR_TEXT_MAIN}; border: 1px solid {CLR_BORDER}; border-radius: 8px; font-weight: 500; padding: 0 16px; font-size: 9pt; font-family: 'IBM Plex Sans', sans-serif; letter-spacing: 0.4px; }}
    QPushButton:hover {{ background-color: {CLR_HOVER_BG}; border: 1px solid {CLR_HOVER_BORDER}; }}
    QPushButton:focus {{ border: 2px solid {CLR_ACCENT}; background-color: {CLR_INNER}; }}
    
    /* --- GHOST & EYE BUTTONS --- */
    QPushButton#BtnGhost {{ background-color: transparent; border: none; color: {CLR_TEXT_MUTED}; padding: 0; }}
    QPushButton#BtnGhost:hover {{ background-color: {CLR_BORDER}; border-radius: 8px; }}
    QPushButton#BtnGhost:focus, QPushButton#BtnEye:focus {{ border: 2px solid {CLR_ACCENT}; background-color: transparent; border-radius: 6px; }}

    /* --- BIG ACTION BUTTON --- */
    QPushButton#BtnAksiBesar {{ background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT}, stop:1 {CLR_ACCENT_DK}); border: 1px solid {CLR_ACCENT_HOVER}; border-radius: 12px; letter-spacing: 0.7px; }}
    QPushButton#BtnAksiBesar:hover {{ background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT_HOVER}, stop:1 {CLR_ACCENT_DK_HOVER}); }}
    QPushButton#BtnAksiBesar:focus {{ border: 2px solid {CLR_TEXT_MAIN}; background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT}, stop:1 {CLR_ACCENT_DK}); }}
    QPushButton#BtnAksiBesar:disabled {{ background-color: {CLR_ACCENT_DISABLED}; border: 1px solid {CLR_BORDER}; }}

    /* --- CUSTOM BUTTONS (Browse & Gen) --- */
    QPushButton#BtnBrowseLg {{ background-color: {CLR_BTN_TRANSPARENT}; border: 1px solid {CLR_BORDER}; border-radius: 8px; color: {CLR_TEXT_MAIN}; font-weight: bold; }}
    QPushButton#BtnBrowseLg:hover {{ background-color: {CLR_INNER}; border: 1px solid {CLR_HOVER_BORDER}; }}
    QPushButton#BtnBrowseLg:focus {{ border: 2px solid {CLR_ACCENT}; background-color: {CLR_BTN_TRANSPARENT}; }}
    QPushButton#BtnBrowseLg::menu-indicator {{ image: none; width: 0px; }}

    QPushButton#BtnGen {{ background-color: transparent; border: 1px solid {CLR_BORDER}; border-radius: 6px; color: {CLR_TEXT_MAIN}; font-weight: bold; padding: 0 10px; }}
    QPushButton#BtnGen:hover {{ background-color: {CLR_INNER}; border: 1px solid {CLR_HOVER_BORDER}; }}
    QPushButton#BtnGen:focus {{ border: 2px solid {CLR_ACCENT}; background-color: transparent; }}

    /* --- CUSTOM CHECKBOX --- */
    QFrame#ChkHapus {{ background: {CLR_INNER}; border: 1px solid {CLR_BORDER}; border-radius: 4px; }}
    QFrame#ChkHapus[checked="true"] {{ background: {CLR_DANGER}; border: 1px solid {CLR_DANGER}; }}
    QFrame#ChkHapus:focus {{ border: 2px solid {CLR_TEXT_MAIN}; }}

    QFrame#ChkSecure {{ background: {CLR_INNER}; border: 1px solid {CLR_BORDER}; border-radius: 4px; }}
    QFrame#ChkSecure[checked="true"] {{ background: {CLR_WARN_DK}; border: 1px solid {CLR_WARN_DK}; }}
    QFrame#ChkSecure:focus {{ border: 2px solid {CLR_TEXT_MAIN}; }}

    /* --- SCROLL & MENUS --- */
    QMenu {{ background-color: {CLR_CARD}; border: 1px solid {CLR_BORDER}; border-radius: 8px; padding: 4px; }}
    QMenu::item {{ border-radius: 4px; background: transparent; }}
    QMenu::item:selected {{ background-color: {CLR_INNER}; }}
    
    /* --- SCROLLBAR MINIMALIS (10px TRACK PILL SHAPE) --- */
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

    /* --- DROP AREA (Drag & Drop) --- */
    QFrame#DropArea[empty="true"] {{ border: 2px dashed {CLR_BORDER}; background-color: {CLR_BG}; border-radius: 12px; }}
    QFrame#DropArea[empty="true"][dragActive="true"] {{ border: 2px dashed {CLR_ACCENT}; background-color: {CLR_INNER}; border-radius: 12px; }}
    QFrame#DropArea[empty="false"] {{ border: 1px solid {CLR_BORDER}; background-color: {CLR_CARD}; border-radius: 12px; }}
    QFrame#DropArea[empty="false"][dragActive="true"] {{ border: 2px dashed {CLR_ACCENT}; background-color: {CLR_INNER}; border-radius: 12px; }}

    /* --- TOOLTIPS, ALERTS, & TITLE BAR --- */
    QLabel#CustomToolTip {{ background-color: {CLR_CARD}; color: {CLR_TEXT_MAIN}; border: 1px solid {CLR_BORDER}; border-radius: 6px; padding: 6px 10px; font-size: 9pt; font-family: 'IBM Plex Sans', sans-serif; }}

    /* Native Qt tooltips (digunakan oleh QListView via ToolTipRole, setToolTip(), dll) */
    QToolTip {{
        background-color: {CLR_CARD};
        color: {CLR_TEXT_MAIN};
        border: 1px solid {CLR_BORDER};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 9pt;
        font-family: 'IBM Plex Sans', 'Segoe UI', sans-serif;
    }}

    QPushButton#BtnAlertConfirm {{ background-color: {CLR_DANGER}; color: {CLR_TEXT_MAIN}; border: 2px solid transparent; border-radius: 8px; font-weight: bold; }}
    QPushButton#BtnAlertConfirm:hover {{ background-color: {CLR_DANGER_HOVER}; }}
    QPushButton#BtnAlertConfirm:focus {{ border: 2px solid {CLR_TEXT_MAIN}; background-color: {CLR_DANGER_HOVER}; }}

    QPushButton#TitleMinBtn, QPushButton#TitleMaxBtn, QPushButton#TitleCloseBtn {{ background-color: transparent; border: none; border-radius: 0; }}
    QPushButton#TitleMinBtn:hover, QPushButton#TitleMaxBtn:hover {{ background-color: {CLR_HOVER_BG}; }}
    QPushButton#TitleCloseBtn:hover {{ background-color: {CLR_DANGER}; }}

    /* --- NOTIFICATION BARS --- */
    QFrame#NotifBar[kind="ok"] {{ background-color: {CLR_SUCCESS_BG}; border-radius: 8px; border: none; }}
    QFrame#NotifBar[kind="ok"] QLabel {{ border: none; background: transparent; color: {CLR_ACCENT}; font-weight: bold; font-size: 10pt; }}

    QFrame#NotifBar[kind="err"] {{ background-color: {CLR_DANGER_BG}; border-radius: 8px; border: none; }}
    QFrame#NotifBar[kind="err"] QLabel {{ border: none; background: transparent; color: {CLR_DANGER}; font-weight: bold; font-size: 10pt; }}

    QFrame#NotifBar[kind="warn"] {{ background-color: {CLR_WARN_BG}; border-radius: 8px; border: none; }}
    QFrame#NotifBar[kind="warn"] QLabel {{ border: none; background: transparent; color: {CLR_WARN}; font-weight: bold; font-size: 10pt; }}
    """


# =============================================================================
# STYLE HELPERS (Untuk mengurangi inline styles di komponen)
# =============================================================================

def muted_label_style(size: str = "9pt") -> str:
    """Style untuk teks sekunder / keterangan."""
    return f"font-size: {size}; color: {CLR_TEXT_MUTED};"


def card_title_style() -> str:
    """Style untuk judul kartu."""
    return f"font-size: 11pt; font-weight: 600; color: {CLR_TEXT_MAIN}; letter-spacing: 0.8px; text-transform: uppercase;"


def card_subtitle_style() -> str:
    """Style untuk sub-judul kartu."""
    return f"font-size: 9pt; color: {CLR_TEXT_MUTED};"


def small_footer_style() -> str:
    """Style untuk teks footer kecil."""
    return f"font-size: 9pt; color: {CLR_TEXT_MUTED};"
