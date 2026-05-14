"""
Modul: styles.py
Deskripsi: Mendefinisikan palet warna konstan dan stylesheet (QSS) utama untuk aplikasi.
           Menggunakan tema "Solid Dark Mode" (Cyber Teal/Cyan).
           Hanya berisi string dan konstanta, TANPA logika widget.
"""

CLR_BG = "#0B101E"
CLR_CARD = "#111625"
CLR_INNER = "#181F32"
CLR_ACCENT = "#00D2C8"
CLR_ACCENT_DK = "#008780"
CLR_BORDER = "#232B3E"
CLR_TEXT_MAIN = "#FFFFFF"
CLR_TEXT_MUTED = "#8B95A5"


def load_stylesheet() -> str:
    """
    Menghasilkan string Qt Style Sheet (QSS) untuk di-apply ke QApplication.
    """
    return f"""
    /* --- GLOBAL --- */
    QMainWindow {{
        background-color: transparent; 
    }}
    
    QWidget#CentralWidget {{
        background-color: {CLR_BG}; 
    }}
    QWidget {{ 
        color: {CLR_TEXT_MAIN}; 
        font-family: 'Segoe UI', sans-serif; 
        font-size: 10pt; 
    }}
    
    /* --- FONT IKON KHUSUS --- */
    QLabel#Icon {{
        font-family: 'Segoe MDL2 Assets', 'Segoe Fluent Icons', sans-serif;
        background: transparent;
    }}
    
    /* --- CARDS & CONTAINERS --- */
    QFrame#Card {{ 
        background-color: {CLR_CARD}; 
        border-radius: 12px; 
        border: 1px solid {CLR_BORDER};
    }}
    QFrame#DropArea {{ 
        background-color: {CLR_CARD}; 
        border-radius: 12px; 
        border: 1px solid {CLR_BORDER}; 
    }}
    QFrame#DropArea[dragActive="true"] {{ 
        border: 2px dashed {CLR_ACCENT}; 
        background-color: {CLR_INNER}; 
    }}
    
    #Inner {{ 
        background-color: {CLR_INNER}; 
        border-radius: 8px; 
        border: 1px solid {CLR_BORDER}; 
    }}
    
    /* --- LIST ITEM (SEPARATOR) --- */
    QFrame#ListItem {{
        background-color: transparent;
        border: none;
        border-bottom: 1px solid {CLR_BORDER};
        border-radius: 0px;
    }}
    QFrame#ListItem:hover {{
        background-color: rgba(35, 43, 62, 0.5);
    }}
    
    QFrame#TipsBox {{
        background-color: #0E1A24;
        border: 1px solid #142E3B;
        border-radius: 8px;
    }}
    
    /* --- HEADER & TABS --- */
    QFrame#TabContainer {{
        background-color: {CLR_CARD};
        border-radius: 10px;
        border: 1px solid {CLR_BORDER};
    }}
    QPushButton#TabBtn {{
        background-color: transparent;
        color: {CLR_TEXT_MUTED};
        border: none;
        border-radius: 8px;
        font-weight: 600;
        font-size: 10pt;
    }}
    QPushButton#TabBtn:checked {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00D2C8, stop:1 #008780);
        color: {CLR_TEXT_MAIN};
        font-weight: 800;
        border: 1px solid #00EFE5;
    }}
    QPushButton#TabBtn:hover:!checked {{
        background-color: {CLR_INNER};
        color: {CLR_TEXT_MAIN};
    }}
    
    /* --- TYPOGRAPHY --- */
    QLabel {{ background-color: transparent; }}
    QLabel#AppTitle {{ font-size: 16pt; font-weight: 800; color: {CLR_TEXT_MAIN}; }}
    QLabel#AppSubtitle {{ font-size: 9pt; color: {CLR_TEXT_MUTED}; font-weight: 500; }}
    QLabel#CardTitle {{ font-size: 11pt; font-weight: 800; color: {CLR_TEXT_MAIN}; letter-spacing: 0.5px; text-transform: uppercase; }}
    QLabel#CardSubtitle {{ font-size: 9pt; color: {CLR_TEXT_MUTED}; margin-bottom: 5px; }}
    
    /* --- INPUTS --- */
    QFrame#InputBox {{
        background-color: {CLR_INNER}; 
        border: 1px solid {CLR_BORDER};
        border-radius: 8px; 
    }}
    QLineEdit#InputInside {{
        background-color: transparent; 
        border: none;
        padding: 0px 5px; 
        color: white; 
        font-size: 10pt;
    }}
    QPushButton#BtnEye {{
        background-color: transparent;
        border: none;
        color: {CLR_TEXT_MUTED};
        padding: 0px; 
        margin: 0px;
    }}
    QLabel#IconInside {{
        background-color: transparent;
        padding: 0px;
        margin: 0px;
    }}
    
    /* --- BUTTONS --- */
    QPushButton {{
        background-color: {CLR_INNER}; color: {CLR_TEXT_MAIN};
        border: 1px solid {CLR_BORDER}; border-radius: 8px; 
        font-weight: 600; padding: 0 16px; font-size: 9pt;
    }}
    QPushButton:hover {{ background-color: #232B3E; }}
    
    QPushButton#BtnGhost {{ 
        background-color: transparent; border: none; color: {CLR_TEXT_MUTED}; 
        padding: 0; 
    }}
    QPushButton#BtnGhost:hover {{ background-color: {CLR_BORDER}; border-radius: 8px; }}
    
    /* --- BIG ACTION BUTTON --- */
    QPushButton#BtnAksiBesar {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT}, stop:1 {CLR_ACCENT_DK});
        border: 1px solid #00EFE5;
        border-radius: 12px;
    }}
    QPushButton#BtnAksiBesar:hover {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00EFE5, stop:1 #00A69D);
    }}
    QPushButton#BtnAksiBesar:disabled {{
        background-color: rgba(21, 28, 44, 0.8);
        border: 1px solid {CLR_BORDER};
    }}
    
    /* --- SCROLL & MENUS --- */
    QMenu {{ background-color: {CLR_CARD}; border: 1px solid {CLR_BORDER}; border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 8px 24px; border-radius: 4px; color: white; }}
    QMenu::item:selected {{ background-color: {CLR_INNER}; }}
    
    QScrollArea {{ border: none; background-color: transparent; }}
    QAbstractScrollArea::viewport {{ background-color: transparent; }}
    
    /* --- SCROLLBAR CUSTOMIZATION --- */
    QScrollBar:vertical {{ 
        background: transparent; 
        width: 10px; 
        margin: 2px; 
    }}
    QScrollBar::handle:vertical {{ 
        background: {CLR_ACCENT_DK}; 
        border-radius: 4px; 
        min-height: 30px; 
    }}
    QScrollBar::handle:vertical:hover {{ 
        background: {CLR_ACCENT}; 
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ 
        height: 0px; 
        background: none; 
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ 
        background: transparent; 
    }}

    /* --- FIX BUG TOOLTIP --- */
    QToolTip {{
        background-color: {CLR_CARD};
        color: {CLR_TEXT_MAIN};
        border: 1px solid {CLR_BORDER};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 9pt;
    }}
    """
