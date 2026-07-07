@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  PDF 도구 상자 - exe 빌드
echo ============================================

REM 1) Tesseract 포터블 복사본 준비 (없으면 로컬 설치본에서 복사)
if not exist "vendor\tesseract\tesseract.exe" (
    if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
        echo Tesseract 바이너리를 vendor 폴더로 복사하는 중...
        mkdir vendor\tesseract 2>nul
        copy "C:\Program Files\Tesseract-OCR\tesseract.exe" vendor\tesseract\ >nul
        copy "C:\Program Files\Tesseract-OCR\*.dll" vendor\tesseract\ >nul
        xcopy "C:\Program Files\Tesseract-OCR\tessdata" vendor\tesseract\tessdata\ /E /I /Q >nul
    ) else (
        echo [오류] Tesseract가 설치되어 있지 않습니다.
        echo https://github.com/UB-Mannheim/tesseract/wiki 에서 설치하세요 ^(Korean 체크^)
        pause
        exit /b 1
    )
)

REM 2) 빌드 도구 설치 + PyInstaller 실행
pip install --user -r requirements.txt pyinstaller

python -m PyInstaller --noconfirm --onefile --windowed --name "PDF도구상자" --icon icon.ico ^
  --add-data "vendor/tesseract;vendor/tesseract" ^
  --collect-all tkinterdnd2 ^
  --exclude-module PySide6 --exclude-module shiboken6 --exclude-module matplotlib ^
  --exclude-module pandas --exclude-module numpy --exclude-module scipy ^
  --exclude-module IPython --exclude-module jedi --exclude-module parso ^
  --exclude-module pygments --exclude-module sqlalchemy --exclude-module psycopg2 ^
  --exclude-module zmq --exclude-module tornado --exclude-module nbformat ^
  --exclude-module jsonschema --exclude-module openpyxl --exclude-module pytz ^
  --exclude-module cryptography --exclude-module bcrypt --exclude-module psutil ^
  --exclude-module fsspec --exclude-module pyarrow --exclude-module astroid ^
  app.py

if %errorlevel% equ 0 (
    echo.
    echo 빌드 완료! dist\PDF도구상자.exe
) else (
    echo.
    echo [오류] 빌드에 실패했습니다.
)
pause
