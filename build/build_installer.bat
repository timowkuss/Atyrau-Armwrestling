@echo off
setlocal
rem =====================================================================
rem  Atyrau Armwrestling - сборка установщика
rem  Запустите двойным кликом (или из cmd):  build_installer.bat
rem
rem  Результат:
rem    build\AtyrauArmwrestlingSetup.exe        - установщик (главный)
rem    build\AtyrauArmwrestling_Portable.zip    - портативная версия
rem
rem  Требования на ЭТОМ (сборочном) ПК:
rem    - Python 3.12 с установленными: customtkinter, pillow, reportlab,
rem      flask, requests, python-dotenv, pyinstaller
rem      (одна команда: pip install -r desktop-app\requirements.txt pyinstaller)
rem    - Inno Setup 6 (https://jrsoftware.org/isdl.php)
rem  Ничего из этого НЕ нужно на целевых компьютерах.
rem =====================================================================

set "BAT_DIR=%~dp0"
set "ROOT=%BAT_DIR%.."
set "APP=%ROOT%\desktop-app"
set "DIST=%APP%\dist"
set "BUILD=%BAT_DIR%"

rem Определяем python (системный или из PATH)
set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)

echo [1/5] Генерация иконки из логотипа...
"%PY%" "%BUILD%build_icon.py"
if errorlevel 1 goto :fail

echo [2/5] Сборка AtyrauArmwrestling.exe (PyInstaller, one-file)...
pushd "%APP%"
"%PY%" -m PyInstaller --noconfirm --clean "%BUILD%AtyrauArmwrestling.spec"
popd
if errorlevel 1 goto :fail
if not exist "%DIST%\AtyrauArmwrestling.exe" goto :fail

echo [3/5] Сборка установщика AtyrauArmwrestlingSetup.exe (Inno Setup)...
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo ОШИБКА: Inno Setup 6 не найден. Установите с https://jrsoftware.org/isdl.php
    goto :fail
)
"%ISCC%" "%BUILD%setup.iss"
if errorlevel 1 goto :fail

echo [4/5] Портативная версия (zip)...
set "ZIP=%BUILD%AtyrauArmwrestling_Portable.zip"
if exist "%ZIP%" del /q "%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path '%DIST%\AtyrauArmwrestling.exe' -DestinationPath '%ZIP%' -Force"
if errorlevel 1 goto :fail

echo [5/5] Готово.
echo.
echo   Установщик:    %BUILD%AtyrauArmwrestlingSetup.exe
echo   Портативка:    %ZIP%
echo.
exit /b 0

:fail
echo.
echo СБОРКА ПРОВАЛИЛАСЬ. См. сообщения выше.
exit /b 1
