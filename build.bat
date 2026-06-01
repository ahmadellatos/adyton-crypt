@echo off
title Nuitka Compiler - Adyton Crypt
color 0B

echo ===================================================
echo   MEMULAI KOMPILASI ADYTON CRYPT
echo ===================================================
echo.

:: ====================== PENGATURAN ======================
set BUILD_MODE=release
:: Untuk testing error, ubah sementara ke "debug"
:: set BUILD_MODE=debug
:: ========================================================

if "%BUILD_MODE%"=="debug" (
    echo [MODE] DEBUG - Console akan ditampilkan
    set CONSOLE_FLAG=--windows-console-mode=attach
) else (
    echo [MODE] RELEASE - Console dinonaktifkan
    set CONSOLE_FLAG=--windows-console-mode=disable
)

echo.
echo Kompilasi mode: %BUILD_MODE%
echo.

python -m nuitka ^
    --standalone ^
    %CONSOLE_FLAG% ^
    --output-filename=AdytonCrypt.exe ^
    --windows-icon-from-ico=assets\icon_adyton.ico ^
    --windows-company-name="Adyton Security" ^
    --windows-product-name="Adyton Crypt" ^
    --windows-product-version="1.0.0" ^
    --enable-plugin=pyside6 ^
    --include-qt-plugins=platforms,styles,iconengines,imageformats ^
    --noinclude-qt-translations ^
    --include-package=qframelesswindow ^
    --include-package=qtawesome ^
    --include-package=loguru ^
    --include-package=winotify ^
    --include-package=zxcvbn ^
    --include-package=core ^
    --include-package=ui ^
    --include-package=cryptography ^
    --include-data-dir=assets=assets ^
    --noinclude-pytest-mode=nofollow ^
    --nofollow-import-to=tests ^
    --assume-yes-for-downloads ^
    --output-dir=release_build ^
    main.py

echo.
if %ERRORLEVEL% == 0 (
    color 0A
    echo ===================================================
    echo   KOMPILASI BERHASIL!
    echo ===================================================
    echo.
    echo Hasil build ada di: release_build\main.dist\
    echo.
    echo Selanjutnya: Gunakan Inno Setup untuk membuat installer.
) else (
    color 0C
    echo ===================================================
    echo   KOMPILASI GAGAL!
    echo ===================================================
    echo Periksa error di atas.
)
echo.
pause