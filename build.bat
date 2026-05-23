@echo off
title Nuitka Compiler - Adyton Crypt
color 0B

echo ===================================================
echo   MEMULAI KOMPILASI ADYTON CRYPT (STANDALONE)
echo ===================================================
echo.
echo Mengkompilasi dalam mode Folder (Bukan OneFile) untuk startup instan...
echo.

:: Menggunakan Nuitka untuk meng-compile main.py menjadi native C
:: Ikon aplikasi akan langsung ditanamkan (embedded) ke dalam file .exe
python -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --windows-icon-from-ico=assets\icon_adyton.ico ^
    --enable-plugin=pyside6 ^
    --enable-plugin=anti-bloat ^
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
    echo Hasil build ada di: release_build\main.dist\
    echo.
    echo Langkah selanjutnya: Bundle folder main.dist menjadi installer
    echo menggunakan Inno Setup Compiler.
) else (
    color 0C
    echo ===================================================
    echo   KOMPILASI GAGAL! Cek error di atas.
    echo ===================================================
)
echo.
pause