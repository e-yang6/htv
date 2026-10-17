@echo off
setlocal
echo ==============================================
echo Building and Running Robot Backtrack Unit Tests
echo ==============================================

call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Could not initialize MSVC environment.
    exit /b 1
)

cl /nologo /EHsc /std:c++14 "%~dp0test_main.cpp" "%~dp0..\robot_backtrack\StepInverter.cpp" /Fe:"%~dp0run_tests.exe" /Fo:"%~dp0\"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Compilation failed.
    exit /b 1
)

echo.
"%~dp0run_tests.exe"
set TEST_RESULT=%ERRORLEVEL%

rem Clean up intermediate build files
del "%~dp0*.obj" >nul 2>&1

exit /b %TEST_RESULT%
