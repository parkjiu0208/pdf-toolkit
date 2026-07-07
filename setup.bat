@echo off
chcp 65001 >nul
echo ============================================
echo  PDF 도구 상자 - 최초 설치 (라이브러리 설치)
echo ============================================
pip install --user -r "%~dp0requirements.txt"
if %errorlevel% neq 0 (
    echo.
    echo [오류] 설치에 실패했습니다. 파이썬이 설치되어 있는지 확인하세요.
) else (
    echo.
    echo 설치 완료! run.bat 또는 바탕화면 바로가기로 실행하세요.
)
pause
