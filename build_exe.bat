@echo off
REM ============================================================
REM  DataExPY by ChrizDev - Build script
REM  Genera un .exe independiente en la carpeta dist/
REM  Cada usuario debe crear su propio .env junto al .exe
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
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/4] Generando .exe...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "DataExPY" ^
    --noconfirm ^
    --collect-all customtkinter ^
    --add-data "llm_client.py;." ^
    --hidden-import pypdf ^
    --hidden-import docx ^
    --hidden-import PIL._tkinter_finder ^
    --hidden-import fitz ^
    main.py

if %errorlevel% neq 0 (
    echo [ERROR] La construccion fallo.
    pause
    exit /b 1
)

echo [3/4] Limpiando archivos temporales...
if exist build rmdir /s /q build
if exist DataExPY.spec del DataExPY.spec

echo [4/4] Hecho!
echo.
echo ============================================================
echo  EJECUTABLE GENERADO:
echo    dist\DataExPY.exe
echo ============================================================
echo.
echo  IMPORTANTE: Copia el archivo .env junto al .exe:
echo.
echo    GROQ_API_KEY="gsk_tu_key"
echo    GEMINI_API_KEY="AIza_tu_key"
echo    SUPABASE_URL="https://tu-proyecto.supabase.co"
echo    SUPABASE_KEY="sb_secret_tu_key"
echo    LOG_LEVEL="INFO"
echo.
pause
