@echo off
REM Script para iniciar el sistema completo sin proxy
REM Evita el error ERR_UNEXPECTED_PROXY_AUTH

echo ===============================================
echo    INICIANDO SISTEMA NEURO RAG COMPLETO
echo ===============================================

REM Limpiar variables de proxy
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set NO_PROXY=localhost,127.0.0.1,*.local,0.0.0.0
set no_proxy=localhost,127.0.0.1,*.local,0.0.0.0

echo.
echo [1/3] Variables de proxy desactivadas
echo NO_PROXY=%NO_PROXY%
echo.

REM Verificar si el backend está corriendo
echo [2/3] Verificando si el backend FastAPI está activo...
netstat -an | findstr :8000 >nul
if %errorlevel% equ 0 (
    echo Backend FastAPI ya está ejecutándose en puerto 8000
) else (
    echo Iniciando Backend FastAPI...
    start "NEURO RAG Backend" cmd /k "cd NEURO_RAG_BACKEND\src && python backend.py --debug"
    echo Esperando que el backend inicie...
    timeout /t 5 /nobreak >nul
)

echo.
echo [3/3] Iniciando servidor Flask en http://127.0.0.1:5000
echo.
echo ================================================
echo   IMPORTANTE: Acceder via http://127.0.0.1:5000
echo   NO usar http://localhost:5000
echo ================================================
echo.

REM Iniciar Flask
python app.py

pause