@echo off

:: ----------------------
:: KUDU Deployment Script
:: ----------------------

setlocal

:: Deployment
echo Handling Python deployment.

:: 1. Select Python version
call :SelectPythonVersion

:: 2. Create virtual environment
IF NOT EXIST "%DEPLOYMENT_TARGET%\env" (
  echo Creating Python virtual environment...
  python -m venv env
)

:: 3. Install packages
echo Installing dependencies...
cd /d "%DEPLOYMENT_TARGET%"
env\Scripts\pip install -r NEURO_RAG_BACKEND\requirements.txt

goto end

:SelectPythonVersion
SET PYTHON_EXE=%SYSTEMDRIVE%\Python39\python.exe
goto :EOF

:end