"""
ui/style.py
Definisi warna dan Qt Style Sheets (QSS) level mahir.
"""

# Warna Utama (Persis dengan CustomTkinter)
CLR_BG = "#12141F"
CLR_CARD = "#1E2235"
CLR_INNER = "#161824"
CLR_ACCENT = "#00C6BE"
CLR_ACCENT_HV = "#009E96"
CLR_DANGER = "#C0392B"
CLR_DANGER_HV = "#A93226"
CLR_MUTED = "#6B7280"
CLR_BORDER = "#2D3452"

# Warna Status Notifikasi
CLR_NOTIF_OK_BG = "#0D2B1E"
CLR_NOTIF_OK_FG = "#1DB954"
CLR_NOTIF_ERR_BG = "#2B0D0D"
CLR_NOTIF_ERR_FG = "#E74C3C"
CLR_NOTIF_WARN_BG = "#2B1E0D"
CLR_NOTIF_WARN_FG = "#F39C12"


def load_stylesheet() -> str:
    return f"""
    /* --- GLOBAL --- */
    QWidget {{ background-color: {CLR_BG}; color: white; font-family: 'Segoe UI', -apple-system, sans-serif; font-size: 10pt; }}
    
    /* --- CARDS & CONTAINERS --- */
    QFrame#Card {{ background-color: {CLR_CARD}; border-radius: 12px; }}
    QFrame#DropArea {{ background-color: {CLR_CARD}; border-radius: 12px; border: 2px solid transparent; }}
    QFrame#DropArea[dragActive="true"] {{ border: 2px dashed {CLR_ACCENT}; background-color: #252B42; }}
    QFrame#Inner {{ background-color: {CLR_INNER}; border-radius: 8px; border: 1px solid {CLR_BORDER}; }}
    
    /* --- TYPOGRAPHY --- */
    QLabel#AppTitle {{ font-size: 16pt; font-weight: 800; color: {CLR_ACCENT}; }}
    QLabel#AppSubtitle {{ font-size: 10pt; color: {CLR_MUTED}; font-weight: 600; margin-bottom: 2px; }}
    QLabel#CardTitle {{ font-size: 10pt; font-weight: 800; color: {CLR_MUTED}; letter-spacing: 1px; }}
    
    /* --- TABS (Mimicking CTk Segmented Button) --- */
    QTabWidget::pane {{ border: none; background: transparent; top: 10px; }}
    QTabWidget::tab-bar {{ alignment: left; }}
    QTabBar {{ background-color: {CLR_INNER}; border-radius: 8px; }}
    QTabBar::tab {{
        background: transparent; color: {CLR_MUTED};
        padding: 8px 30px; margin: 4px; border-radius: 6px; font-weight: 800; font-size: 10pt;
    }}
    QTabBar::tab:selected {{ background-color: {CLR_ACCENT}; color: #000000; }}
    QTabBar::tab:hover:!selected {{ background-color: {CLR_BORDER}; color: white; }}
    
    /* --- INPUTS --- */
    QLineEdit {{
        background-color: {CLR_INNER}; border: 1px solid {CLR_BORDER};
        border-radius: 8px; padding: 0px 14px; color: white; font-size: 10pt;
    }}
    QLineEdit:focus {{ border: 1px solid {CLR_ACCENT}; background-color: #1A1D2D; }}
    
    /* --- BUTTONS --- */
    QPushButton {{
        background-color: {CLR_ACCENT}; color: #000000;
        border: none; border-radius: 8px; font-weight: 800; padding: 0 16px; font-size: 10pt;
    }}
    QPushButton:hover {{ background-color: {CLR_ACCENT_HV}; }}
    QPushButton:disabled {{ background-color: {CLR_BORDER}; color: {CLR_MUTED}; }}
    
    QPushButton#BtnSecondary {{ background-color: {CLR_BORDER}; color: white; }}
    QPushButton#BtnSecondary:hover {{ background-color: #3D4562; }}
    
    QPushButton#BtnGhost {{ background-color: transparent; color: {CLR_MUTED}; font-size: 14pt; padding: 0; }}
    QPushButton#BtnGhost:hover {{ color: {CLR_DANGER}; background-color: #2B0D0D; border-radius: 8px; }}
    
    /* --- PROGRESS & SCROLL --- */
    QProgressBar {{ background-color: {CLR_INNER}; border: none; border-radius: 4px; color: transparent; }}
    QProgressBar::chunk {{ background-color: {CLR_ACCENT}; border-radius: 4px; }}
    
    QScrollArea {{ border: none; background-color: transparent; }}
    QScrollBar:vertical {{ background: {CLR_BG}; width: 8px; border-radius: 4px; margin: 0px; }}
    QScrollBar::handle:vertical {{ background: {CLR_BORDER}; border-radius: 4px; min-height: 20px; }}
    QScrollBar::handle:vertical:hover {{ background: {CLR_MUTED}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    
    /* --- MENUS & CHECKBOX --- */
    QMenu {{ background-color: {CLR_CARD}; border: 1px solid {CLR_BORDER}; border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 8px 24px; border-radius: 4px; color: white; }}
    QMenu::item:selected {{ background-color: {CLR_ACCENT}; color: black; }}
    
    QCheckBox {{ color: {CLR_MUTED}; font-weight: 600; spacing: 10px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; border: 1px solid {CLR_BORDER}; background-color: {CLR_INNER}; }}
    QCheckBox::indicator:checked {{ background-color: {CLR_DANGER}; border: 1px solid {CLR_DANGER}; }}
    """
