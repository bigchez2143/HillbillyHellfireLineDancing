@echo off
setlocal
title Line Dance Creator
cd /d "%~dp0"
set "DANCE_ROOT=%~dp0.."
set "DANCE_PYTHON=%DANCE_ROOT%\.venv\Scripts\python.exe"
set "DANCE_LOCK=%DANCE_ROOT%\requirements\core-win-py312.lock.txt"
if exist "%DANCE_PYTHON%" goto :check_environment
if "%~1"=="--check" goto :incomplete

rem Initial source setup installs core only, never optional speech/stem models.
set "DANCE_UV="
where uv >nul 2>nul
if not errorlevel 1 set "DANCE_UV=uv"
if not defined DANCE_UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "DANCE_UV=%USERPROFILE%\.local\bin\uv.exe"
if defined DANCE_UV goto :setup_uv
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 goto :setup_py_launcher
python -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>nul
if not errorlevel 1 goto :setup_python
echo Python 3.12 or uv is needed to run this source copy.
echo Use the portable release for an application with its own Python runtime.
goto :failed

:setup_uv
echo Preparing the local core environment. First setup requires internet.
"%DANCE_UV%" venv --cache-dir "%DANCE_ROOT%\.uv-cache" --python 3.12 "%DANCE_ROOT%\.venv"
if errorlevel 1 goto :failed
"%DANCE_UV%" pip install --cache-dir "%DANCE_ROOT%\.uv-cache" --python "%DANCE_PYTHON%" -r "%DANCE_LOCK%"
if errorlevel 1 goto :failed
goto :check_environment

:setup_py_launcher
py -3.12 -m venv "%DANCE_ROOT%\.venv"
if errorlevel 1 goto :failed
goto :install_core

:setup_python
python -m venv "%DANCE_ROOT%\.venv"
if errorlevel 1 goto :failed

:install_core
echo Installing core dependencies. First setup requires internet.
"%DANCE_PYTHON%" -m pip install -r "%DANCE_LOCK%"
if errorlevel 1 goto :failed

:check_environment
"%DANCE_PYTHON%" -c "import sys; assert sys.version_info[:2] == (3, 12); import fastapi, uvicorn, multipart, librosa, numpy, soundfile, reportlab, pypdf, docx, openpyxl, icalendar, tzdata" >nul 2>nul
if errorlevel 1 goto :incomplete
if "%~1"=="--check" (
  echo Core Python 3.12 environment is ready. Optional models were not loaded.
  exit /b 0
)
echo Starting Line Dance Creator at http://127.0.0.1:8766/dance ...
"%DANCE_PYTHON%" server.py
if errorlevel 1 goto :failed
exit /b 0

:incomplete
echo The existing local environment is incomplete or uses a different Python version.
echo Restore Windows Python 3.12 core dependencies from requirements\core-win-py312.lock.txt.
echo The existing environment and optional tools have been preserved.
:failed
echo Line Dance Creator could not start. Review the message above.
if "%~1"=="--check" exit /b 1
pause
exit /b 1
