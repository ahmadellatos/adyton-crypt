; ─────────────────────────────────────────────────────────────────────────────
; INNO SETUP SCRIPT - ADYTON CRYPT INSTALLER CONFIGURATION
; ─────────────────────────────────────────────────────────────────────────────

[Setup]
AppId={{A3D9B5E6-7D42-4A21-B861-C3F982ADTN99}
AppName=Adyton Crypt
AppVersion=1.0.0
AppPublisher=Adyton Security
AppComments=Advanced AES-256-GCM Digital Vault
UninstallDisplayIcon={app}\AdytonCrypt.exe
DefaultDirName={autopf}\Adyton Crypt
DefaultGroupName=Adyton Crypt
AllowNoIcons=yes
PrivilegesRequired=admin

; Output file setup
OutputDir=release_build
OutputBaseFilename=Adyton_Crypt_Setup_v1.0.0

; Ikon untuk file installer .exe itu sendiri
SetupIconFile=assets\icon_adyton.ico

; Kompresi maksimal (LZMA2 Ultra) agar ukuran installer sekecil mungkin
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; --- CUSTOM INSTALLER IMAGES ---
WizardImageFile=assets\wizard_image.bmp
WizardSmallImageFile=assets\wizard_small.bmp
WizardImageStretch=no

; Beritahu Windows kalau aplikasi ini mendaftarkan ekstensi file custom
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 1. Aplikasi Utama (Kita rename main.exe hasil Nuitka menjadi AdytonCrypt.exe saat diinstall)
Source: "release_build\main.dist\main.exe"; DestDir: "{app}"; DestName: "AdytonCrypt.exe"; Flags: ignoreversion

; 2. Semua file dependency (.dll, pyd, dll) dari folder main.dist hasil kompilasi Nuitka
Source: "release_build\main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "main.exe"

; 3. File Ikon untuk kebutuhan registrasi file association di Windows Explorer
Source: "assets\icon_adyton.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Shortcut di Start Menu
Name: "{group}\Adyton Crypt"; Filename: "{app}\AdytonCrypt.exe"; IconFilename: "{app}\AdytonCrypt.exe"; AppUserModelID: "AdytonSecurity.AdytonCrypt.App.1"
; Shortcut di Desktop (opsional tergantung pilihan user saat install)
Name: "{autodesktop}\Adyton Crypt"; Filename: "{app}\AdytonCrypt.exe"; Tasks: desktopicon; AppUserModelID: "AdytonSecurity.AdytonCrypt.App.1"

[Run]
; Opsi untuk langsung menjalankan aplikasi setelah installer selesai
Filename: "{app}\AdytonCrypt.exe"; Description: "{cm:LaunchProgram,Adyton Crypt}"; Flags: nowait postinstall skipifsilent

; ─────────────────────────────────────────────────────────────────────────────
; REGISTRY REGISTRATION FOR FILE ASSOCIATION (.adtn -> Adyton Crypt File)
; ─────────────────────────────────────────────────────────────────────────────
[Registry]
; Daftarkan ekstensi .adtn ke Windows Classes
Root: HKA; Subkey: "Software\Classes\.adtn"; ValueType: string; ValueName: ""; ValueData: "AdytonCryptFile"; Flags: uninsdeletevalue

; Set tipe deskripsi file yang muncul di kolom "Type" File Explorer
Root: HKA; Subkey: "Software\Classes\AdytonCryptFile"; ValueType: string; ValueName: ""; ValueData: "Adyton Crypt File"; Flags: uninsdeletekey

; Pasang logo Adyton sebagai ikon default untuk SEMUA file ber-ekstensi .adtn
Root: HKA; Subkey: "Software\Classes\AdytonCryptFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\icon_adyton.ico"; Flags: uninsdeletekey

; Atur aksi open command: Jika file .adtn diklik ganda, buka lewat AdytonCrypt.exe
Root: HKA; Subkey: "Software\Classes\AdytonCryptFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\AdytonCrypt.exe"" ""%1"""; Flags: uninsdeletekey