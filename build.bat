@echo off
title Nuitka Compiler - Digital Locker
color 0B

echo ===================================================
echo   MEMULAI KOMPILASI DIGITAL LOCKER (STANDALONE)
echo ===================================================
echo.
echo Mengkompilasi dalam mode Folder (Bukan OneFile) untuk startup instan...
echo.

:: Catatan Senior: 
:: Kita matikan onefile, gunakan standalone murni.
:: Jangan lupa, kalau lu punya file icon.ico, tambahkan: --windows-icon-from-ico=app_icon.ico

python -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --enable-plugin=pyside6 ^
    --enable-plugin=anti-bloat ^
    --include-package=core ^
    --include-package=ui ^
    --include-package=cryptography ^
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