@echo off
REM Build ban Windows tren may Windows (can Python 3.10+; Inno Setup 6 la tuy chon).
setlocal
cd /d "%~dp0"

if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller || goto :error

pyinstaller packaging\ZaloMarketing.spec --noconfirm --clean || goto :error
echo.
echo Da build xong: dist\ZaloMarketing\ZaloMarketing.exe

where iscc >nul 2>nul
if %errorlevel%==0 (
    iscc packaging\installer.iss || goto :error
    echo Bo cai: dist\ZaloMarketing-Setup-1.0.0.exe
) else if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" packaging\installer.iss || goto :error
    echo Bo cai: dist\ZaloMarketing-Setup-1.0.0.exe
) else (
    echo Khong tim thay Inno Setup - bo qua buoc tao bo cai.
)
exit /b 0

:error
echo Build that bai.
exit /b 1
