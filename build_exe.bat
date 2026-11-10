@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto :fail
set "AMCAD_BUILD_CONSOLE=0"
if "%~1"=="" goto :arguments_ok
if /I "%~1"=="--console" (
    set "AMCAD_BUILD_CONSOLE=1"
    goto :arguments_ok
)
echo Usage: build_exe.bat [--console]
exit /b 2

:arguments_ok
if not "%~2"=="" (
    echo Usage: build_exe.bat [--console]
    exit /b 2
)
if exist ".venv-build\Scripts\python.exe" goto :environment_ready
if defined AMCAD_BUILD_PYTHON (
    "%AMCAD_BUILD_PYTHON%" -c "import sys,struct; assert sys.version_info[:3]==(3,14,4) and struct.calcsize('P')==8, 'Requires 64-bit Python 3.14.4'"
    if errorlevel 1 goto :fail
    "%AMCAD_BUILD_PYTHON%" -m venv .venv-build
) else (
    py -3.14 -c "import sys,struct; assert sys.version_info[:3]==(3,14,4) and struct.calcsize('P')==8, 'Requires 64-bit Python 3.14.4'"
    if errorlevel 1 goto :fail
    py -3.14 -m venv .venv-build
)
if errorlevel 1 goto :fail

:environment_ready
".venv-build\Scripts\python.exe" -c "import sys,struct; assert sys.version_info[:3]==(3,14,4) and struct.calcsize('P')==8 and sys.platform=='win32', 'Requires Windows x64 Python 3.14.4'"
if errorlevel 1 goto :fail
".venv-build\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-build.txt
if errorlevel 1 goto :fail
".venv-build\Scripts\python.exe" -m pip check
if errorlevel 1 goto :fail
".venv-build\Scripts\python.exe" -m PyInstaller --clean --noconfirm AMCAD.spec
if errorlevel 1 goto :fail
".venv-build\Scripts\python.exe" build_support\check_distribution.py dist\AMCAD
if errorlevel 1 goto :fail
".venv-build\Scripts\python.exe" -m pip freeze > build\AMCAD\build-environment.txt
if errorlevel 1 goto :fail
echo.
echo Build complete: dist\AMCAD\AMCAD.exe
echo Copy the ENTIRE dist\AMCAD folder, including _internal, to the target PC.
echo See docs\windows-build.md for validation and distribution instructions.
exit /b 0

:fail
echo.
echo BUILD FAILED. Review the error above. No project or user library was changed.
exit /b 1
