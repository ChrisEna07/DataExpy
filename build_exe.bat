@echo off
REM ============================================================
REM  DataExPY by ChrizDev - Build script
REM  Genera un .exe independiente en la carpeta dist/
REM ============================================================
title Building DataExPY by ChrizDev...

echo ============================================================
echo  Construyendo DataExPY by ChrizDev v1.0.0
echo ============================================================
echo.

REM Verificar que pyinstaller esta instalado
python -c "import PyInstaller" 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller no instalado. Ejecuta: pip install pyinstaller
    pause
    exit /b 1
)

echo [1/4] Limpiando builds anteriores...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

echo [2/4] Generando .exe...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "DataExPY" ^
    --noconfirm ^
    --add-data ".env;." ^
    --collect-all customtkinter ^
    --icon NONE ^
    main.py

if %errorlevel% neq 0 (
    echo [ERROR] La construccion fallo.
    pause
    exit /b 1
)

echo [3/4] Limpiando archivos temporales...
rmdir /s /q build 2>nul
del DataExPY.spec 2>nul

echo [4/4] Hecho!
echo.
echo ============================================================
echo  EJECUTABLE GENERADO:
echo    dist\DataExPY.exe
echo ============================================================
echo.
echo  IMPORTANTE: Copia el archivo .env junto al .exe
echo  o el programa no podra conectarse a Groq/Supabase.
echo.

pause
