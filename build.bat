@echo off
setlocal EnableExtensions EnableDelayedExpansion

title Nuitka Compiler - Adyton Crypt
color 0B

:: ═════════════════════════════════════════════════════════════════════════════
:: ADYTON CRYPT BUILD SCRIPT
:: ═════════════════════════════════════════════════════════════════════════════
:: Build standalone Windows executable with Nuitka.
:: This script intentionally cleans stale bytecode/build output first so the
:: installer does not accidentally package __pycache__ or old artifacts.
:: ═════════════════════════════════════════════════════════════════════════════

echo ===================================================
echo   MEMULAI KOMPILASI ADYTON CRYPT
echo ===================================================
echo.

:: ====================== PENGATURAN ======================
set "BUILD_MODE=debug"
set "APP_VERSION=1.0.0"
set "APP_EXE=AdytonCrypt.exe"
set "BUILD_DIR=release_build"
set "DIST_DIR=%BUILD_DIR%\main.dist"
:: Untuk testing error, ubah sementara ke "debug"
:: set "BUILD_MODE=debug"
:: ========================================================

if /I "%BUILD_MODE%"=="debug" (
    echo [MODE] DEBUG - Console akan ditampilkan
    set "CONSOLE_FLAG=--windows-console-mode=attach"
) else (
    echo [MODE] RELEASE - Console dinonaktifkan
    set "CONSOLE_FLAG=--windows-console-mode=disable"
)

echo.
echo Kompilasi mode: %BUILD_MODE%
echo Versi aplikasi: %APP_VERSION%
echo.

call :check_prerequisites
if errorlevel 1 goto :fail

call :clean_artifacts
if errorlevel 1 goto :fail

echo.
echo [BUILD] Menjalankan Nuitka...
echo.

python -m nuitka ^
    --standalone ^
    %CONSOLE_FLAG% ^
    --output-filename=%APP_EXE% ^
    --windows-icon-from-ico=assets\icon_adyton.ico ^
    --windows-company-name="Adyton Security" ^
    --windows-product-name="Adyton Crypt" ^
    --windows-product-version="%APP_VERSION%" ^
    --enable-plugin=pyside6 ^
    --include-qt-plugins=platforms,styles,iconengines,imageformats ^
    --noinclude-qt-translations ^
    --include-package=qframelesswindow ^
    --include-package=qtawesome ^
    --include-package=loguru ^
    --include-package=windows_toasts ^
    --include-package=zxcvbn ^
    --include-package=core ^
    --include-package=ui ^
    --include-package=cryptography ^
    --include-package=zstandard ^
    --include-module=cryptography.hazmat.primitives.kdf.argon2 ^
    --include-data-dir=assets=assets ^
    --noinclude-pytest-mode=nofollow ^
    --nofollow-import-to=tests ^
    --nofollow-import-to=pytest ^
    --assume-yes-for-downloads ^
    --output-dir=%BUILD_DIR% ^
    main.py

if errorlevel 1 goto :fail

if not exist "%DIST_DIR%\%APP_EXE%" (
    echo.
    echo [ERROR] Build selesai tetapi executable tidak ditemukan:
    echo         %DIST_DIR%\%APP_EXE%
    goto :fail
)

color 0A
echo.
echo ===================================================
echo   KOMPILASI BERHASIL!
echo ===================================================
echo.
echo Hasil build ada di: %DIST_DIR%\
echo Executable: %DIST_DIR%\%APP_EXE%
echo.
echo Selanjutnya: buka installer.iss dengan Inno Setup untuk membuat installer.
echo.
pause
exit /b 0

:check_prerequisites
echo [CHECK] Memeriksa Python dan dependency build...

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python tidak ditemukan di PATH.
    exit /b 1
)
echo [CHECK] Python ditemukan.

:: Cek nuitka via import — lebih ringan dari "--version" yang bisa trigger
:: download compiler dan hang tanpa output karena stdout/stderr di-redirect ke nul.
python -c "import nuitka" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Nuitka belum tersedia.
    echo         Jalankan: python -m pip install -r requirements.txt
    exit /b 1
)
echo [CHECK] Nuitka ditemukan.

if not exist "assets\icon_adyton.ico" (
    echo [ERROR] Icon aplikasi tidak ditemukan: assets\icon_adyton.ico
    exit /b 1
)
echo [CHECK] Assets ditemukan.

:: Cek dependency satu per satu supaya pesan error lebih jelas jika ada yang kurang.
python -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PySide6 tidak ditemukan. Jalankan: pip install -r requirements.txt
    exit /b 1
)

python -c "import qframelesswindow" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] qframelesswindow tidak ditemukan.
    echo         Jalankan: pip install PySideSix-Frameless-Window
    exit /b 1
)

python -c "import qtawesome, loguru, windows_toasts, zxcvbn, zstandard" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Satu atau lebih dependency tidak ditemukan: qtawesome, loguru, windows_toasts, zxcvbn, zstandard
    echo         Jalankan: pip install -r requirements.txt
    exit /b 1
)

python -c "from cryptography.hazmat.primitives.kdf.argon2 import Argon2id" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] cryptography belum mendukung Argon2id.
    echo         Jalankan: pip install "cryptography>=46.0.7,^<47.0.0"
    exit /b 1
)

echo [OK] Semua dependency siap.
exit /b 0

:clean_artifacts
echo [CLEAN] Membersihkan output build dan bytecode lama...

if exist "%BUILD_DIR%" (
    rmdir /s /q "%BUILD_DIR%"
    if exist "%BUILD_DIR%" (
        echo [ERROR] Gagal menghapus folder build lama: %BUILD_DIR%
        exit /b 1
    )
)

for /d /r %%D in (__pycache__) do (
    if exist "%%D" rmdir /s /q "%%D" >nul 2>nul
)

del /s /q *.pyc *.pyo >nul 2>nul

echo [OK] Cleanup selesai.
exit /b 0

:fail
color 0C
echo.
echo ===================================================
echo   KOMPILASI GAGAL!
echo ===================================================
echo Periksa error di atas.
echo.
pause
exit /b 1
