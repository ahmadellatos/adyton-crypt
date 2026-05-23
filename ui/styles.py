"""
Modul: styles.py
Deskripsi: Mendefinisikan palet warna konstan dan stylesheet (QSS) utama untuk aplikasi.
           Menggunakan tema "Solid Dark Mode" (Cyber Teal/Cyan).
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
    QFrame#ListItem:hover {{ background-color: rgba(35, 43, 62, 0.5); }}
    
    QFrame#TipsBox {{ background-color: #0E1A24; border: 1px solid #142E3B; border-radius: 8px; }}
    
    /* --- HEADER & TABS --- */
    QFrame#TabContainer {{ background-color: {CLR_CARD}; border-radius: 10px; border: 1px solid {CLR_BORDER}; }}
    QPushButton#TabBtn {{ background-color: transparent; color: {CLR_TEXT_MUTED}; border: none; border-radius: 8px; font-weight: 500; font-size: 10pt; }}
    QPushButton#TabBtn:checked {{ background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00D2C8, stop:1 #008780); color: {CLR_TEXT_MAIN}; font-weight: 700; border: 1px solid #00EFE5; }}
    QPushButton#TabBtn:hover:!checked {{ background-color: {CLR_INNER}; color: {CLR_TEXT_MAIN}; }}
    
    QPushButton#TabBtn:focus {{
        border: 2px solid #00D2C8;
        background-color: transparent;
    }}
    QPushButton#TabBtn:checked:focus {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00D2C8, stop:1 #008780);
        border: 2px solid #FFFFFF;
    }}
    
    /* --- TYPOGRAPHY --- */
    QLabel {{ background-color: transparent; }}
    QLabel#AppTitle {{ font-size: 16pt; font-weight: 700; color: {CLR_TEXT_MAIN}; letter-spacing: -0.2px; }}
    QLabel#AppSubtitle {{ font-size: 9pt; color: {CLR_TEXT_MUTED}; font-weight: 400; }}
    QLabel#CardTitle {{ font-size: 11pt; font-weight: 600; color: {CLR_TEXT_MAIN}; letter-spacing: 0.8px; text-transform: uppercase; }}
    QLabel#CardSubtitle {{ font-size: 9pt; color: {CLR_TEXT_MUTED}; margin-bottom: 5px; }}
    
    /* --- INPUTS --- */
    QFrame#InputBox {{ background-color: {CLR_INNER}; border: 1px solid {CLR_BORDER}; border-radius: 8px; }}
    QLineEdit#InputInside {{ background-color: transparent; border: none; padding: 0px 5px; color: white; font-size: 10pt; font-family: 'IBM Plex Sans', sans-serif; }}
    QPushButton#BtnEye {{ background-color: transparent; border: none; color: {CLR_TEXT_MUTED}; padding: 0px; margin: 0px; }}
    QLabel#IconInside {{ background-color: transparent; padding: 0px; margin: 0px; }}
    
    /* --- FOCUS & A11Y STATES (THE MAGIC ANTI-DOTTED LINE) --- */
    * {{ outline: none; }}
    
    QFrame#InputBox[focused="true"] {{
        background-color: #0B101E;
        border: 1px solid #00D2C8;
    }}

    QFrame[checked="true"]:focus, 
    QFrame[checked="false"]:focus {{
        border: 2px solid #FFFFFF;
    }}

    /* --- BUTTONS (Standard) --- */
    QPushButton {{ background-color: {CLR_INNER}; color: {CLR_TEXT_MAIN}; border: 1px solid {CLR_BORDER}; border-radius: 8px; font-weight: 500; padding: 0 16px; font-size: 9pt; font-family: 'IBM Plex Sans', sans-serif; letter-spacing: 0.4px; }}
    
    /* HOVER: Background sedikit lebih terang (keabu-abuan) */
    QPushButton:hover {{ background-color: #232B3E; border: 1px solid #2A344A; }}
    
    /* FOCUS: Garis Cyan 2px, background tetap default (gelap) */
    QPushButton:focus {{ border: 2px solid {CLR_ACCENT}; background-color: {CLR_INNER}; }}
    
    
    /* --- GHOST & EYE BUTTONS --- */
    QPushButton#BtnGhost {{ background-color: transparent; border: none; color: {CLR_TEXT_MUTED}; padding: 0; }}
    QPushButton#BtnGhost:hover {{ background-color: {CLR_BORDER}; border-radius: 8px; }}
    QPushButton#BtnGhost:focus, QPushButton#BtnEye:focus {{ border: 2px solid {CLR_ACCENT}; background-color: transparent; border-radius: 6px; }}


    /* --- BIG ACTION BUTTON --- */
    QPushButton#BtnAksiBesar {{ background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT}, stop:1 {CLR_ACCENT_DK}); border: 1px solid #00EFE5; border-radius: 12px; letter-spacing: 0.7px; }}
    
    /* HOVER: Gradient menyala lebih terang */
    QPushButton#BtnAksiBesar:hover {{ background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00EFE5, stop:1 #00A69D); }}
    
    /* FOCUS: Muncul outline putih tebal, tapi gradient kembali ke normal (bukan hover gradient) */
    QPushButton#BtnAksiBesar:focus {{ border: 2px solid #FFFFFF; background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {CLR_ACCENT}, stop:1 {CLR_ACCENT_DK}); }}
    QPushButton#BtnAksiBesar:disabled {{ background-color: rgba(21, 28, 44, 0.8); border: 1px solid {CLR_BORDER}; }}

    /* --- CUSTOM BUTTONS (Browse & Gen) --- */
    QPushButton#BtnBrowseLg {{
        background-color: rgba(24, 31, 50, 0.5); border: 1px solid #232B3E; border-radius: 8px; color: white; font-weight: bold;
    }}
    QPushButton#BtnBrowseLg:hover {{ background-color: #181F32; border: 1px solid #2A344A; }}
    QPushButton#BtnBrowseLg:focus {{ border: 2px solid {CLR_ACCENT}; background-color: rgba(24, 31, 50, 0.5); }}
    QPushButton#BtnBrowseLg::menu-indicator {{ image: none; width: 0px; }}

    QPushButton#BtnGen {{
        background-color: transparent; border: 1px solid #232B3E; border-radius: 6px; color: white; font-weight: bold; padding: 0 10px;
    }}
    QPushButton#BtnGen:hover {{ background-color: #181F32; border: 1px solid #2A344A; }}
    QPushButton#BtnGen:focus {{ border: 2px solid {CLR_ACCENT}; background-color: transparent; }}

    /* --- CUSTOM CHECKBOX --- */
    QFrame#ChkHapus {{ background: #181F32; border: 1px solid #232B3E; border-radius: 4px; }}
    QFrame#ChkHapus[checked="true"] {{ background: #E74C3C; border: 1px solid #E74C3C; }}
    QFrame#ChkHapus:focus {{ border: 2px solid #FFFFFF; }}

    QFrame#ChkSecure {{ background: #181F32; border: 1px solid #232B3E; border-radius: 4px; }}
    QFrame#ChkSecure[checked="true"] {{ background: #E67E22; border: 1px solid #E67E22; }}
    QFrame#ChkSecure:focus {{ border: 2px solid #FFFFFF; }}

    /* --- SCROLL & MENUS --- */
    QMenu {{ 
        background-color: {CLR_CARD}; 
        border: 1px solid {CLR_BORDER}; 
        border-radius: 8px; 
        padding: 4px; 
    }}
    QMenu::item {{ 
        border-radius: 4px; 
        background: transparent;
    }}
    QMenu::item:selected {{ 
        background-color: {CLR_INNER}; 
    }}
    
    /* --- SCROLLBAR CUSTOMIZATION --- */
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {CLR_ACCENT_DK}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {CLR_ACCENT}; }}
    QScrollBar:add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; background: none; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

    /* --- CENTRALIZED REFACTOR FROM INLINE STYLES --- */
    QFrame#DropArea[empty="true"] {{ border: 2px dashed #232B3E; background-color: #0B101E; border-radius: 12px; }}
    QFrame#DropArea[empty="true"][dragActive="true"] {{ border: 2px dashed #00D2C8; background-color: #181F32; }}
    QFrame#DropArea[empty="false"] {{ border: 1px solid #232B3E; background-color: #111625; border-radius: 12px; }}
    QFrame#DropArea[empty="false"][dragActive="true"] {{ border: 2px dashed #00D2C8; background-color: #181F32; }}

    QLabel#CustomToolTip {{ background-color: #111625; color: #FFFFFF; border: 1px solid #232B3E; border-radius: 6px; padding: 6px 10px; font-size: 9pt; font-family: 'IBM Plex Sans', sans-serif; }}

    QPushButton#BtnAlertConfirm {{ background-color: #E74C3C; color: white; border: 2px solid transparent; border-radius: 8px; font-weight: bold; }}
    QPushButton#BtnAlertConfirm:hover {{ background-color: #C0392B; }}
    QPushButton#BtnAlertConfirm:focus {{ border: 2px solid #FFFFFF; background-color: #C0392B; }}

    QPushButton#TitleMinBtn, QPushButton#TitleMaxBtn, QPushButton#TitleCloseBtn {{ background-color: transparent; border: none; border-radius: 0; }}
    QPushButton#TitleMinBtn:hover, QPushButton#TitleMaxBtn:hover {{ background-color: #232B3E; }}
    QPushButton#TitleCloseBtn:hover {{ background-color: #E74C3C; }}

    QFrame#NotifBar[kind="ok"] {{ background-color: #0D2B1E; border-radius: 8px; border: none; }}
    QFrame#NotifBar[kind="ok"] QLabel {{ border: none; background: transparent; color: #00D2C8; font-weight: bold; font-size: 10pt; }}

    QFrame#NotifBar[kind="err"] {{ background-color: #2B0D0D; border-radius: 8px; border: none; }}
    QFrame#NotifBar[kind="err"] QLabel {{ border: none; background: transparent; color: #E74C3C; font-weight: bold; font-size: 10pt; }}

    QFrame#NotifBar[kind="warn"] {{ background-color: #2B1E0D; border-radius: 8px; border: none; }}
    QFrame#NotifBar[kind="warn"] QLabel {{ border: none; background: transparent; color: #F39C12; font-weight: bold; font-size: 10pt; }}
    """
