@echo off
title Nuitka Compiler - Digital Locker
color 0B

echo ===================================================
echo   MEMULAI KOMPILASI DIGITAL LOCKER KE .EXE (NUITKA)
echo ===================================================
echo.
echo Pastikan koneksi internet aktif!
echo Jika kamu belum punya C Compiler, Nuitka akan mendownload MinGW64 secara otomatis.
echo.
echo Proses ini akan memakan komputasi CPU 100%% dan butuh waktu 5-15 menit.
echo Silakan tinggal ngopi dulu...
echo.

python -m nuitka ^
    --onefile ^
    --windows-disable-console ^
    --enable-plugin=pyside6 ^
    --include-package=core ^
    --include-package=ui ^
    --include-package=cryptography ^
    --assume-yes-for-downloads ^
    --output-filename="Digital Locker.exe" ^
    --output-dir=release_build ^
    main.py

echo.
if %ERRORLEVEL% == 0 (
    color 0A
    echo ===================================================
    echo   KOMPILASI BERHASIL!
    echo ===================================================
    echo File siap di: release_build\Digital Locker.exe
) else (
    color 0C
    echo ===================================================
    echo   KOMPILASI GAGAL! Cek error di atas.
    echo ===================================================
)
echo.
pause