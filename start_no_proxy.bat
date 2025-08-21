@echo off
REM Script para iniciar la aplicación sin proxy
REM Evita el error ERR_UNEXPECTED_PROXY_AUTH

echo ========================================
echo Iniciando aplicacion sin proxy...
echo ========================================

REM Limpiar variables de proxy
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=

REM Configurar NO_PROXY para localhost
set NO_PROXY=localhost,127.0.0.1,*.local,0.0.0.0
set no_proxy=localhost,127.0.0.1,*.local,0.0.0.0

echo.
echo Variables de proxy desactivadas:
echo NO_PROXY=%NO_PROXY%
echo.

REM Iniciar la aplicación
echo Iniciando servidor Flask en http://127.0.0.1:5000
echo.
echo IMPORTANTE: Usar http://127.0.0.1:5000 en lugar de http://localhost:5000
echo.

python app.py

pause