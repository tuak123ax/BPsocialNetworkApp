@echo off
REM Build a standalone Windows .exe using PyInstaller.
REM Usage: packaging\build_windows.bat  (chay tu thu muc goc du an, hoac nhan dup file nay)
cd /d "%~dp0.."

python -m pip install --quiet -r requirements.txt

pyinstaller --noconfirm --windowed --name "HieuSuatNhanVien" ^
    --add-data "sample_data;sample_data" ^
    --distpath dist --workpath build --specpath packaging ^
    main.py

echo.
echo Done. Executable at: dist\HieuSuatNhanVien\HieuSuatNhanVien.exe
