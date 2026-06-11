; ═════════════════════════════════════════════════════════════════════════════
; ADYTON CRYPT - Inno Setup Installer (Improved Hybrid Version)
; ═════════════════════════════════════════════════════════════════════════════
;
; Fitur Utama:
;   ✓ Modern privilege selection (Per-User / All Users dialog)
;   ✓ Smart registry using HKA
;   ✓ Minimal Pascal code
;   ✓ Automatic VC++ Redistributable download (only when needed)
;   ✓ File association for .adtn
;   ✓ License Agreement
;   ✓ Previous version uninstall handling
;   ✓ 64-bit only
;
; ═════════════════════════════════════════════════════════════════════════════

[Setup]
AppId={{A3D9B5E6-7D42-4A21-B861-C3F982AD7999}
AppName=Adyton Crypt
AppVersion=1.0.0
AppPublisher=Adyton Security
AppPublisherURL=https://github.com/yourusername/adyton-crypt
AppSupportURL=https://github.com/yourusername/adyton-crypt/issues
AppUpdatesURL=https://github.com/yourusername/adyton-crypt/releases
AppComments=Advanced AES-256-GCM Digital Vault
VersionInfoVersion=1.0.0.0
VersionInfoCompany=Adyton Security
VersionInfoDescription=Adyton Crypt Installer
UninstallDisplayName=Adyton Crypt
UninstallDisplayIcon={app}\AdytonCrypt.exe

; --- 64-bit Only ---
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64compatible

; --- MODERN PRIVILEGE HANDLING ---
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Default ke LocalAppData (lebih ramah untuk user biasa)
DefaultDirName={localappdata}\Adyton Crypt
DefaultGroupName=Adyton Crypt
AllowNoIcons=yes

; Mencegah dua installer berjalan bersamaan.
; Catatan: aplikasi saat ini memakai Qt LocalServer untuk single-instance,
; bukan Win32 mutex, jadi proses aplikasi berjalan ditangani lewat [Code].
SetupMutex=AdytonCrypt_Setup_Mutex

; Jangan biarkan installer/uninstaller menutup aplikasi otomatis.
; Jika aplikasi sedang memproses vault, penutupan paksa bisa menyebabkan data hilang.
CloseApplications=no
RestartApplications=no

OutputDir=release_build
OutputBaseFilename=Adyton_Crypt_Setup_v1.0.0
SetupIconFile=assets\icon_adyton.ico

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; Custom wizard images
WizardImageFile=assets\wizard_image.bmp
WizardSmallImageFile=assets\wizard_small.bmp
WizardImageStretch=no

; License & Info
LicenseFile=license.txt
InfoAfterFile=readme_after_install.txt

ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Desktop shortcut - dicentang secara default
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

; VC++ hanya muncul jika diperlukan
Name: "vcredist"; Description: "Download and install Microsoft Visual C++ Redistributable 2015-2022 (recommended)"; GroupDescription: "System Requirements"; Check: NeedsVCRedist

[Files]
Source: "release_build\main.dist\AdytonCrypt.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release_build\main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "AdytonCrypt.exe"
Source: "assets\icon_adyton.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\Adyton Crypt"; Filename: "{app}\AdytonCrypt.exe"; WorkingDir: "{app}"; IconFilename: "{app}\AdytonCrypt.exe"; AppUserModelID: "AdytonSecurity.AdytonCrypt.App.1"
Name: "{autodesktop}\Adyton Crypt"; Filename: "{app}\AdytonCrypt.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "AdytonSecurity.AdytonCrypt.App.1"

[Run]
; Install VC++ (jika dicentang)
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; Tasks: vcredist; StatusMsg: "Installing Visual C++ Redistributable..."; Flags: waituntilterminated

; Launch aplikasi setelah install (dicentang secara default)
Filename: "{app}\AdytonCrypt.exe"; Description: "{cm:LaunchProgram,Adyton Crypt}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Registry]
; File association menggunakan HKA (otomatis mengikuti privilege)
Root: HKA; Subkey: "Software\Classes\.adtn"; ValueType: string; ValueName: ""; ValueData: "AdytonCryptFile"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\AdytonCryptFile"; ValueType: string; ValueName: ""; ValueData: "Adyton Crypt File"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AdytonCryptFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\assets\icon_adyton.ico"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AdytonCryptFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\AdytonCrypt.exe"" ""%1"""; Flags: uninsdeletekey

[UninstallDelete]
Type: filesandordirs; Name: "{app}\*"
Type: dirifempty; Name: "{app}"

; ═════════════════════════════════════════════════════════════════════════════
; PASCAL SCRIPT
; ═════════════════════════════════════════════════════════════════════════════
[Code]

// =============================================
// RUNNING APP DETECTION
// =============================================

function IsAdytonCryptRunning(): Boolean;
var
  ResultCode: Integer;
begin
  // Deteksi non-destruktif. Tidak memakai taskkill /F.
  if Exec(
    ExpandConstant('{cmd}'),
    '/C tasklist /FI "IMAGENAME eq AdytonCrypt.exe" /NH | find /I "AdytonCrypt.exe" >NUL',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
    Result := ResultCode = 0
  else
    Result := False;
end;

function BlockIfAdytonCryptRunning(ActionName: String): Boolean;
begin
  Result := True;

  if IsAdytonCryptRunning() then
  begin
    MsgBox(
      'Adyton Crypt masih berjalan.'#13#13 +
      'Sebelum ' + ActionName + ', tutup aplikasi Adyton Crypt secara manual dan pastikan tidak ada proses kunci/buka vault yang sedang berjalan.'#13#13 +
      'Installer tidak akan menutup aplikasi secara paksa agar data vault tidak berisiko rusak atau hilang.',
      mbError,
      MB_OK
    );
    Result := False;
  end;
end;

// =============================================
// VC++ REDISTRIBUTABLE DETECTION
// =============================================

function NeedsVCRedist(): Boolean;
begin
  Result := not RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64');
end;

// =============================================
// DOWNLOAD VC++ SEBELUM EKSTRAKSI
// =============================================

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';

  if WizardIsTaskSelected('vcredist') then
  begin
    try
      DownloadTemporaryFile(
        'https://aka.ms/vs/17/release/vc_redist.x64.exe',
        'vc_redist.x64.exe',
        '',
        nil
      );
    except
      Result := 'Gagal mengunduh Visual C++ Redistributable.'#13#13 +
                'Pastikan koneksi internet stabil, lalu coba lagi.'#13#13 +
                'Atau install secara manual dari:'#13 +
                'https://aka.ms/vs/17/release/vc_redist.x64.exe';
    end;
  end;
end;

// =============================================
// UNINSTALL PREVIOUS VERSION (ROBUST HYBRID FIX)
// =============================================

function QueryUninstallString(UninstallAppId: String): String;
var
  UninstallKey, UnInstPath: String;
begin
  UnInstPath := '';
  UninstallKey := 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\' + UninstallAppId;

  // Cek HKLM (All Users) lalu HKCU (Per-User)
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE, UninstallKey, 'QuietUninstallString', UnInstPath) then
  begin
    if not RegQueryStringValue(HKEY_CURRENT_USER, UninstallKey, 'QuietUninstallString', UnInstPath) then
    begin
      if not RegQueryStringValue(HKEY_LOCAL_MACHINE, UninstallKey, 'UninstallString', UnInstPath) then
        RegQueryStringValue(HKEY_CURRENT_USER, UninstallKey, 'UninstallString', UnInstPath);
    end;
  end;

  Result := UnInstPath;
end;

function GetPreviousUninstallString(): String;
begin
  // AppId baru memakai GUID valid.
  Result := QueryUninstallString('{A3D9B5E6-7D42-4A21-B861-C3F982AD7999}_is1');

  // Fallback untuk build lama yang memakai AppId non-GUID sebelum release publik.
  if Result = '' then
    Result := QueryUninstallString('{A3D9B5E6-7D42-4A21-B861-C3F982ADTN99}_is1');
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  UninstallString: String;
begin
  Result := True;

  if not BlockIfAdytonCryptRunning('melanjutkan instalasi atau update') then
  begin
    Result := False;
    Exit;
  end;

  UninstallString := GetPreviousUninstallString();

  if UninstallString <> '' then
  begin
    if MsgBox('Versi Adyton Crypt sebelumnya terdeteksi di sistem Anda.'#13#13 +
              'Dianjurkan untuk menghapus versi lama sebelum melanjutkan instalasi.'#13#13 +
              'Hapus versi lama sekarang?', mbConfirmation, MB_YESNO) = IDYES then
    begin
      if not Exec(ExpandConstant('{cmd}'), '/C ""' + UninstallString + '""', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      begin
        MsgBox('Gagal menghapus versi lama secara otomatis. ' +
               'Instalasi akan tetap dilanjutkan, namun disarankan untuk ' +
               'membersihkannya nanti via Control Panel.',
               mbError, MB_OK);
      end;
    end;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := BlockIfAdytonCryptRunning('menghapus aplikasi');
end;

// =============================================
// PENYESUAIAN DIREKTORI
// =============================================

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectDir then
  begin
    if IsAdminInstallMode then
    begin
      if Pos('LocalAppData', WizardDirValue) > 0 then
      begin
        WizardForm.DirEdit.Text := ExpandConstant('{autopf}\Adyton Crypt');
      end;
    end
    else
    begin
      if Pos('Program Files', WizardDirValue) > 0 then
      begin
        WizardForm.DirEdit.Text := ExpandConstant('{localappdata}\Adyton Crypt');
      end;
    end;
  end;
end;
