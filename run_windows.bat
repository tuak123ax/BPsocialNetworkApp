@echo off
REM Chay ung dung tren Windows - CHI CAN NHAN DUP (double-click) vao file nay.
REM Lan dau chay se tu tao moi truong ao (.venv) va cai thu vien can thiet
REM (co the mat khoang 1 phut); cac lan sau chay gan nhu ngay lap tuc.
cd /d "%~dp0"

if not exist ".venv" (
    echo Lan dau chay: dang thiet lap moi truong, vui long doi...
    python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
