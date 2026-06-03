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
CLR_BORDER_SUBTLE = (
    "rgba(35, 43, 62, 0.28)"  # Lebih subtle untuk border halus seperti di footer
)

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
CLR_SUCCESS = "#28C75D"  # Hijau cerah untuk indikator sukses / match

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
    
    /* --- CARDS & CONTAINERS (Minimalist Premium) --- */
    QFrame#Card {{
        background-color: {CLR_CARD};
        border-radius: 14px;
        border: 1px solid rgba(35, 43, 62, 0.45);
    }}


    #Inner {{
        background-color: {CLR_INNER};
        border-radius: 10px;
        border: 1px solid rgba(35, 43, 62, 0.5);
    }}

    QFrame#ListItem {{
        background-color: transparent;
        border: none;
        border-bottom: 1px solid {CLR_BORDER};
        border-radius: 0px;
    }}
    QFrame#ListItem:hover {{
        background-color: {CLR_LIST_HOVER};
    }}

    QFrame#TipsBox {{
        background-color: {CLR_TIPS_BG};
        border: 1px solid {CLR_TIPS_BORDER};
        border-radius: 10px;
    }}
    
    /* --- HEADER (Minimalist Premium) --- */
    QFrame#HeaderWrapper {{
        background-color: transparent;
    }}

    /* --- TABS (Minimalist Premium) --- */
    QFrame#TabContainer {{
        background-color: {CLR_CARD};
        border-radius: 12px;
        border: 1px solid {CLR_BORDER};
    }}

    QPushButton#TabBtn {{
        background-color: transparent;
        color: {CLR_TEXT_MUTED};
        border: none;
        border-radius: 10px;
        font-weight: 500;
        font-size: 10pt;
        padding: 6px 18px;  /* lebih tipis vertikal */
    }}

    QPushButton#TabBtn:checked {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT}, stop:1 {CLR_ACCENT_DK});
        color: {CLR_TEXT_MAIN};
        font-weight: 600;
        border: 1px solid {CLR_ACCENT_HOVER};
    }}

    QPushButton#TabBtn:hover:!checked {{
        background-color: {CLR_INNER};
        color: {CLR_TEXT_MAIN};
    }}

    QPushButton#TabBtn:focus {{
        border: 2px solid {CLR_ACCENT};
        background-color: transparent;
    }}

    QPushButton#TabBtn:checked:focus {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT}, stop:1 {CLR_ACCENT_DK});
        border: 2px solid {CLR_TEXT_MAIN};
    }}
    
    /* --- TYPOGRAPHY (Improved Scale - Minimalist Premium) --- */
    QLabel {{
        background-color: transparent;
        font-size: 10pt;
    }}

    /* Large titles (app header) */
    QLabel#AppTitle {{
        font-size: 18pt;
        font-weight: 600;
        color: {CLR_TEXT_MAIN};
        letter-spacing: -0.3px;
    }}

    /* Subtle subtitles under big titles */
    QLabel#AppSubtitle {{
        font-size: 9pt;
        color: {CLR_TEXT_MUTED};
        font-weight: 400;
    }}

    /* Section / Card titles */
    QLabel#CardTitle {{
        font-size: 12pt;
        font-weight: 600;
        color: {CLR_TEXT_MAIN};
        letter-spacing: 0.1px;
    }}

    /* Specific bigger title for "DAFTAR TARGET" header (user request) */
    QLabel#TargetHeaderTitle {{
        font-size: 13pt;
        font-weight: 600;
        color: {CLR_TEXT_MAIN};
        letter-spacing: 0.6px;
    }}

    /* Card subtitles / descriptions */
    QLabel#CardSubtitle {{
        font-size: 9pt;
        color: {CLR_TEXT_MUTED};
    }}

    /* Section labels (e.g. "Password", "Ulangi Password") */
    QLabel#SectionLabel {{
        font-size: 10pt;
        font-weight: 600;
        color: {CLR_TEXT_MAIN};
    }}

    /* --- PASSWORD PANEL (Kunci) - Premium Typography & States --- */
    QLabel#ChecklistLabel {{
        font-size: 8.5pt;
        color: {CLR_TEXT_MUTED};
    }}
    QLabel#ChecklistLabel[valid="true"] {{
        color: #A8B2C1;
        font-weight: 500;
    }}

    QLabel#PwMatchLabel {{
        font-size: 8.5pt;
        font-weight: 500;
    }}

    /* Options Panel descriptions (premium secondary text) */
    QLabel#OptionDesc {{
        font-size: 8.5pt;
        color: {CLR_TEXT_MUTED};
        font-weight: 300;  /* Light weight for delicate secondary info */
    }}

    /* Standard body text */
    QLabel#BodyText {{
        font-size: 10pt;
        color: {CLR_TEXT_MAIN};
    }}

    /* Muted / secondary text */
    QLabel#MutedText {{
        font-size: 9pt;
        color: {CLR_TEXT_MUTED};
    }}

    /* Accent / highlight text (e.g. "Data Anda aman") */
    QLabel#AccentText {{
        font-size: 9pt;
        color: {CLR_ACCENT};
        font-weight: 600;
    }}

    /* Small captions / footers */
    QLabel#CaptionText {{
        font-size: 8pt;
        color: {CLR_TEXT_MUTED};
    }}

    /* Tips text di PasswordPanelOpen — lebih ringan & premium */
    QLabel#TipText {{
        font-size: 8.5pt;
        color: {CLR_TEXT_MUTED};
        font-weight: 300;
    }}

    /* Status colors for text */
    QLabel#ErrorText {{
        font-size: 9pt;
        color: {CLR_DANGER};
        font-weight: 500;
    }}

    QLabel#SuccessText {{
        font-size: 9pt;
        color: {CLR_SUCCESS};
        font-weight: 500;
    }}

    QLabel#WarningText {{
        font-size: 9pt;
        color: {CLR_WARN};
        font-weight: 500;
    }}
    
    /* --- INPUTS (Cleaner & More Premium) --- */
    QFrame#InputBox {{
        background-color: {CLR_INNER};
        border: 1px solid rgba(35, 43, 62, 0.7);
        border-radius: 10px;
    }}

    QFrame#InputBox[focused="true"] {{
        background-color: {CLR_BG};
        border: 1px solid {CLR_ACCENT};
    }}

    QLineEdit#InputInside {{
        background-color: transparent;
        border: none;
        padding: 0px 8px;
        color: {CLR_TEXT_MAIN};
        font-size: 10pt;
        font-family: 'IBM Plex Sans', sans-serif;
    }}

    QPushButton#BtnEye {{
        background-color: transparent;
        border: none;
        color: {CLR_TEXT_MUTED};
        padding: 0px 6px;
        margin: 0px;
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
    QFrame#InputBox[focused="true"] {{ background-color: {CLR_BG}; border: 1px solid {CLR_ACCENT}; }}
    QFrame[checked="true"]:focus, QFrame[checked="false"]:focus {{ border: 2px solid {CLR_TEXT_MAIN}; }}

    /* --- BUTTONS (Clean Minimalist Premium) --- */
    QPushButton {{
        background-color: {CLR_INNER};
        color: {CLR_TEXT_MAIN};
        border: 1px solid rgba(35, 43, 62, 0.35);
        border-radius: 10px;
        font-weight: 500;
        padding: 8px 20px;
        font-size: 9.5pt;
        font-family: 'IBM Plex Sans', sans-serif;
        letter-spacing: 0.3px;
    }}
    QPushButton:hover {{
        background-color: {CLR_HOVER_BG};
        border: 1px solid {CLR_HOVER_BORDER};
    }}
    QPushButton:focus {{
        border: 2px solid {CLR_ACCENT};
        background-color: {CLR_INNER};
    }}
    QPushButton:disabled {{
        background-color: rgba(24, 31, 50, 0.4);
        color: {CLR_TEXT_MUTED};
        border: 1px solid rgba(35, 43, 62, 0.2);
    }}
    
    /* --- GHOST & EYE BUTTONS --- */
    QPushButton#BtnGhost {{
        background-color: transparent;
        border: none;
        color: {CLR_TEXT_MUTED};
        padding: 4px 8px;
        border-radius: 6px;
    }}
    QPushButton#BtnGhost:hover {{
        background-color: {CLR_HOVER_BG};
        color: {CLR_TEXT_MAIN};
    }}
    QPushButton#BtnGhost:focus, QPushButton#BtnEye:focus {{
        border: 2px solid {CLR_ACCENT};
        background-color: transparent;
        border-radius: 6px;
    }}

    /* --- BIG ACTION BUTTON (Strong CTA) --- */
    QPushButton#BtnAksiBesar {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT}, stop:1 {CLR_ACCENT_DK});
        border: 1px solid {CLR_ACCENT_HOVER};
        border-radius: 12px;
        font-weight: 600;
        font-size: 10.5pt;
        letter-spacing: 0.4px;
        padding: 13px 34px;  /* Option B: lebih lega untuk tinggi 82px */
    }}
    QPushButton#BtnAksiBesar:hover {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT_HOVER}, stop:1 {CLR_ACCENT_DK_HOVER});
    }}
    QPushButton#BtnAksiBesar:focus {{
        border: 2px solid {CLR_TEXT_MAIN};
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT}, stop:1 {CLR_ACCENT_DK});
    }}
    QPushButton#BtnAksiBesar:disabled {{
        background-color: {CLR_ACCENT_DISABLED};
        border: 1px solid {CLR_BORDER};
        /* color is controlled per-label below to avoid inheritance issues */
    }}

    /* Note: Text colors for labels inside #BtnAksiBesar are controlled directly
       in Python (BigActionBtn.setEnabled) for reliable enabled/disabled behavior. */

    /* --- CUSTOM BUTTONS (Browse & Gen) - More Premium --- */
    QPushButton#BtnBrowseLg {{
        background-color: {CLR_BTN_TRANSPARENT};
        border: 1px solid rgba(35, 43, 62, 0.5);
        border-radius: 10px;
        color: {CLR_TEXT_MAIN};
        font-weight: 600;
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

    /* Tombol "Ganti File Brankas" — reference style (darker, solid presence) */
    QPushButton#BtnGantiFile {{
        background-color: #181F32;
        border: 1px solid #232B3E;
        border-radius: 9px;
        color: {CLR_TEXT_MAIN};
        font-weight: 500;
        font-size: 9pt;
        padding: 0 16px;
    }}

    QPushButton#BtnGantiFile:hover {{
        background-color: #1E2A40;
        border-color: #2A344A;
    }}

    QPushButton#BtnGantiFile:focus {{
        border: 1px solid {CLR_ACCENT};
        background-color: #181F32;
    }}

    QPushButton#BtnGen {{
        background-color: transparent;
        border: 1px solid rgba(35, 43, 62, 0.5);
        border-radius: 8px;
        color: {CLR_TEXT_MAIN};
        font-weight: 600;
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

    /* --- CUSTOM CHECKBOX --- */
    QFrame#ChkHapus {{
        background: {CLR_INNER};
        border: 1px solid {CLR_BORDER};
        border-radius: 4px;
    }}
    QFrame#ChkHapus:hover {{
        border-color: {CLR_ACCENT_HOVER};
    }}
    QFrame#ChkHapus[checked="true"] {{
        background: {CLR_DANGER};
        border: 1px solid {CLR_DANGER};
    }}
    QFrame#ChkHapus:focus {{
        border: 2px solid {CLR_TEXT_MAIN};
    }}

    QFrame#ChkSecure {{
        background: {CLR_INNER};
        border: 1px solid {CLR_BORDER};
        border-radius: 4px;
    }}
    QFrame#ChkSecure:hover {{
        border-color: {CLR_ACCENT_HOVER};
    }}
    QFrame#ChkSecure[checked="true"] {{
        background: {CLR_WARN_DK};
        border: 1px solid {CLR_WARN_DK};
    }}
    QFrame#ChkSecure:focus {{
        border: 2px solid {CLR_TEXT_MAIN};
    }}

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

    /* --- DROP AREA - Empty State (Minimalist Premium) --- */
    QFrame#DropArea[empty="true"] {{
        border: 1px solid rgba(35, 43, 62, 0.35);
        background-color: {CLR_CARD};
        border-radius: 16px;
    }}

    QFrame#DropArea[empty="true"][dragActive="true"] {{
        border: 2px solid {CLR_ACCENT};
        background-color: rgba(0, 210, 200, 0.08);
        border-radius: 16px;
    }}

    /* When there are files inside */
    QFrame#DropArea[empty="false"] {{
        border: 1px solid rgba(35, 43, 62, 0.5);
        background-color: {CLR_CARD};
        border-radius: 14px;
    }}

    QFrame#DropArea[empty="false"][dragActive="true"] {{
        border: 2px dashed {CLR_ACCENT};
        background-color: {CLR_INNER};
        border-radius: 14px;
    }}

    /* --- DROP ZONE FILLED STATE (Buka) - selected file card like reference --- */
    QFrame#FileInfoCard {{
        background-color: #181F32;
        border: 1px solid #232B3E;
        border-radius: 11px;
    }}

    QLabel#SelectedFileIcon {{
        background-color: rgba(0, 210, 200, 0.08);
        border: none;
        border-radius: 8px;
    }}

    QLabel#SelectedFileName {{
        color: {CLR_TEXT_MAIN};
        font-size: 10pt;
        font-weight: 700;
        letter-spacing: 0.05px;
    }}

    QLabel#FileReadySubtitle {{
        color: #D7DCE6;
        font-size: 8.5pt;
        font-weight: 500;
    }}

    QLabel#SelectedFilePath {{
        color: #8B95A5;
        font-size: 8pt;
        font-weight: 300;
    }}

    QLabel#ValidBadge {{
        background-color: rgba(40, 199, 93, 0.12);
        color: #28C75D;
        border: 1px solid rgba(40, 199, 93, 0.22);
        font-size: 7.5pt;
        font-weight: 700;
        border-radius: 5px;
        padding: 0px 8px;
    }}

    QLabel#ValidBadge[state="ok"] {{
        background-color: rgba(40, 199, 93, 0.12);
        color: #28C75D;
        border: 1px solid rgba(40, 199, 93, 0.22);
    }}

    QLabel#ValidBadge[state="verified"] {{
        background-color: rgba(0, 210, 200, 0.14);
        color: {CLR_ACCENT};
        border: 1px solid rgba(0, 210, 200, 0.36);
    }}

    QLabel#ValidBadge[state="busy"] {{
        background-color: rgba(0, 210, 200, 0.10);
        color: #8DEDE8;
        border: 1px solid rgba(0, 210, 200, 0.22);
    }}

    QLabel#ValidBadge[state="warn"], QLabel#ValidBadge[valid="false"] {{
        background-color: rgba(243, 156, 18, 0.12);
        color: {CLR_WARN};
        border: 1px solid rgba(243, 156, 18, 0.24);
    }}

    QLabel#ValidBadge[state="error"] {{
        background-color: rgba(231, 76, 60, 0.12);
        color: #FF8A80;
        border: 1px solid rgba(231, 76, 60, 0.32);
    }}

    QFrame#FileCardDivider {{
        background-color: #232B3E;
        border: none;
    }}

    QFrame#MetaItem {{
        background-color: transparent;
        border: none;
    }}

    QFrame#MetaSeparator {{
        background-color: rgba(35, 43, 62, 0.75);
        border: none;
    }}

    QLabel#MetaLabel {{
        color: #8B95A5;
        font-size: 7.5pt;
        font-weight: 400;
    }}

    QLabel#MetaValue {{
        color: #E8ECF3;
        font-size: 8.2pt;
        font-weight: 600;
    }}

    /* Valid banner "File brankas valid dan siap untuk dibuka" — kept for compatibility but not primary anymore */
    QFrame#ValidBanner {{
        background-color: #0A1F18;
        border: 1px solid #142E26;
        border-radius: 10px;
    }}

    QLabel#BannerTitle {{
        color: {CLR_ACCENT};
        font-size: 9.5pt;
        font-weight: 600;
    }}

    QLabel#BannerDesc {{
        color: {CLR_TEXT_MUTED};
        font-size: 8.5pt;
        font-weight: 300;
    }}

    /* Encryption info section header — more presence */
    QLabel#EncSectionTitle {{
        font-size: 10pt;
        font-weight: 600;
        color: #D7DCE6;
        letter-spacing: 0.1px;
    }}

    /* Bordered container for INFORMASI ENKRIPSI section */
    QFrame#EncInfoSection {{
        background-color: #0F141F;
        border: 1px solid #232B3E;
        border-radius: 8px;
    }}

    /* --- DROP ZONE EMPTY STATE (Premium) --- */
    QLabel#DropZoneMainText {{
        font-size: 14pt;
        font-weight: 600;
        color: {CLR_TEXT_MAIN};
        letter-spacing: 0.1px;
    }}

    QLabel#DropZoneSubText {{
        font-size: 10pt;
        color: {CLR_TEXT_MUTED};
    }}

    QLabel#DropZoneFooter {{
        font-size: 8pt;
        color: {CLR_TEXT_MUTED};
        opacity: 0.65;
    }}



    /* Open vault process / error state */
    QFrame#ProcessStatusBox {{
        background-color: #0B1F25;
        border: 1px solid rgba(0, 210, 200, 0.22);
        border-radius: 10px;
    }}

    QLabel#ProcessText {{
        color: #A8B2C1;
        font-size: 9pt;
        font-weight: 400;
    }}

    QLabel#ProcessLabel {{
        color: #8B95A5;
        font-size: 8.5pt;
        font-weight: 500;
    }}

    QLabel#ProcessValue {{
        color: #E8ECF3;
        font-size: 9pt;
        font-weight: 600;
    }}

    QFrame#OpenErrorBox {{
        background-color: rgba(231, 76, 60, 0.08);
        border: 1px solid rgba(231, 76, 60, 0.35);
        border-radius: 10px;
    }}

    QLabel#OpenErrorText {{
        color: #F2B8B5;
        font-size: 9pt;
        font-weight: 500;
    }}

    QPushButton#BtnInlinePrimary {{
        background-color: {CLR_ACCENT};
        color: #071015;
        border: none;
        border-radius: 7px;
        padding: 7px 14px;
        font-weight: 700;
    }}
    QPushButton#BtnInlinePrimary:hover {{
        background-color: {CLR_ACCENT_HOVER};
    }}

    QPushButton#BtnInlineSecondary {{
        background-color: transparent;
        color: {CLR_TEXT_MAIN};
        border: 1px solid {CLR_BORDER};
        border-radius: 7px;
        padding: 7px 14px;
        font-weight: 600;
    }}
    QPushButton#BtnInlineSecondary:hover {{
        border-color: {CLR_ACCENT};
        color: {CLR_ACCENT};
    }}

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

    /* Dialog secondary button (Batal) */
    QPushButton#BtnDialogCancel {{
        background-color: transparent;
        border: 1px solid rgba(35, 43, 62, 0.5);
        border-radius: 8px;
        color: {CLR_TEXT_MAIN};
        font-weight: 500;
    }}
    QPushButton#BtnDialogCancel:hover {{
        background-color: {CLR_INNER};
        border-color: {CLR_ACCENT_HOVER};
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


def body_style(size: str = "10pt") -> str:
    """Standard body text."""
    return f"font-size: {size}; color: {CLR_TEXT_MAIN};"


def muted_label_style(size: str = "9pt") -> str:
    """Style untuk teks sekunder / keterangan."""
    return f"font-size: {size}; color: {CLR_TEXT_MUTED};"


def caption_style(size: str = "8pt") -> str:
    """Very small / footer text."""
    return f"font-size: {size}; color: {CLR_TEXT_MUTED};"


def small_footer_style() -> str:
    """Style untuk teks footer kecil. (Deprecated - use caption_style instead)"""
    return caption_style("9pt")


def error_text_style(size: str = "9pt") -> str:
    return f"font-size: {size}; color: {CLR_DANGER}; font-weight: 500;"


def success_text_style(size: str = "9pt") -> str:
    return f"font-size: {size}; color: {CLR_SUCCESS}; font-weight: 500;"


def warning_text_style(size: str = "9pt") -> str:
    return f"font-size: {size}; color: {CLR_WARN}; font-weight: 500;"


def section_title_style() -> str:
    """Style untuk judul section / card."""
    return f"font-size: 12pt; font-weight: 600; color: {CLR_TEXT_MAIN}; letter-spacing: 0.5px;"


def card_title_style() -> str:
    """Style untuk judul kartu (uppercase version)."""
    return f"font-size: 11pt; font-weight: 600; color: {CLR_TEXT_MAIN}; letter-spacing: 0.6px; text-transform: uppercase;"


def card_subtitle_style() -> str:
    """Style untuk sub-judul kartu."""
    return f"font-size: 9pt; color: {CLR_TEXT_MUTED};"
