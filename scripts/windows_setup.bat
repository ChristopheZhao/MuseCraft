@echo off
REM ===================================================================
REM Windows Setup Script for Short Video Maker Platform
REM ===================================================================

echo.
echo ========================================================
echo   Short Video Maker Platform - Windows Setup
echo ========================================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [INFO] Running with administrator privileges
) else (
    echo [WARNING] Not running as administrator - some features may fail
    echo [INFO] Consider running as administrator for best results
)

echo.
echo [STEP 1/8] Checking system requirements...
echo --------------------------------------------------------

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! 
    echo [ACTION] Please install Python 3.11+ from: https://python.org
    echo [ACTION] Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%i in ('python --version') do echo [OK] Python %%i found
)

REM Check Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found!
    echo [ACTION] Please install Node.js 18+ from: https://nodejs.org
    pause
    exit /b 1
) else (
    for /f %%i in ('node --version') do echo [OK] Node.js %%i found
)

REM Check Git
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Git not found - you may need it for version control
) else (
    for /f "tokens=3" %%i in ('git --version') do echo [OK] Git %%i found
)

echo.
echo [STEP 2/8] Creating directories...
echo --------------------------------------------------------

if not exist "backend\storage\uploads" mkdir backend\storage\uploads
if not exist "backend\storage\generated" mkdir backend\storage\generated
if not exist "backend\storage\temp" mkdir backend\storage\temp
if not exist "backend\logs" mkdir backend\logs
if not exist "test_results" mkdir test_results

echo [OK] Created storage directories

echo.
echo [STEP 3/8] Setting up environment configuration...
echo --------------------------------------------------------

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] Created .env from .env.example
        echo [ACTION] Please edit .env and add your API keys!
    ) else (
        echo [ERROR] .env.example not found
    )
) else (
    echo [OK] .env already exists
)

echo.
echo [STEP 4/8] Installing Python dependencies...
echo --------------------------------------------------------

cd backend
echo [INFO] Installing Python packages (this may take a few minutes)...

REM Upgrade pip first
python -m pip install --upgrade pip

REM Install packages with Windows-specific handling
pip install wheel
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies
    echo [ACTION] Try installing with: conda install --file requirements.txt
    echo [ACTION] Or install problematic packages separately
    cd ..
    pause
    exit /b 1
)

echo [OK] Python dependencies installed successfully
cd ..

echo.
echo [STEP 5/8] Installing Node.js dependencies...
echo --------------------------------------------------------

echo [INFO] Installing Node.js packages...
call npm install

if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Node.js dependencies
    echo [ACTION] Try: npm install --legacy-peer-deps
    pause
    exit /b 1
)

echo [OK] Node.js dependencies installed successfully

echo.
echo [STEP 6/8] Checking for optional dependencies...
echo --------------------------------------------------------

REM Check PostgreSQL
psql --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] PostgreSQL not found
    echo [INFO] You can:
    echo [INFO] 1. Install PostgreSQL from: https://postgresql.org/download/windows
    echo [INFO] 2. Use Docker PostgreSQL (recommended)
    echo [INFO] 3. Use SQLite for development (modify settings)
) else (
    for /f "tokens=3" %%i in ('psql --version') do echo [OK] PostgreSQL %%i found
)

REM Check Redis
redis-server --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Redis not found
    echo [INFO] You can:
    echo [INFO] 1. Install Redis using Docker (recommended)
    echo [INFO] 2. Install Redis for Windows from GitHub
    echo [INFO] 3. Use in-memory caching for development
) else (
    echo [OK] Redis found
)

REM Check FFmpeg
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg not found
    echo [INFO] Video processing features may not work
    echo [INFO] Install FFmpeg from: https://ffmpeg.org/download.html#build-windows
    echo [INFO] Add FFmpeg to your system PATH
) else (
    echo [OK] FFmpeg found
)

echo.
echo [STEP 7/8] Creating Windows-specific startup scripts...
echo --------------------------------------------------------

REM Create backend startup script
(
echo @echo off
echo echo Starting Short Video Maker Backend...
echo cd backend
echo python -m app.main
echo pause
) > start_backend.bat

REM Create frontend startup script
(
echo @echo off
echo echo Starting Short Video Maker Frontend...
echo npm run dev
echo pause
) > start_frontend.bat

REM Create combined startup script  
(
echo @echo off
echo echo Starting Short Video Maker Platform...
echo start "Backend" cmd /c start_backend.bat
echo timeout /t 5 /nobreak
echo start "Frontend" cmd /c start_frontend.bat
echo echo.
echo echo Services are starting in separate windows...
echo echo Backend: http://localhost:8000
echo echo Frontend: http://localhost:3000
echo echo API Docs: http://localhost:8000/docs
echo echo.
echo echo Press any key to exit...
echo pause
) > start_platform.bat

echo [OK] Created startup scripts:
echo      - start_backend.bat   (Backend only)
echo      - start_frontend.bat  (Frontend only) 
echo      - start_platform.bat  (Both services)

echo.
echo [STEP 8/8] Running system validation...
echo --------------------------------------------------------

cd backend
python scripts\validate_system.py
set validation_result=%errorlevel%
cd ..

echo.
echo ========================================================
echo                SETUP COMPLETE!
echo ========================================================

if %validation_result% equ 0 (
    echo [SUCCESS] All validations passed!
    echo.
    echo Next steps:
    echo 1. Edit .env file and add your API keys
    echo    - OPENAI_API_KEY=sk-your-key-here
    echo    - DATABASE_URL=postgresql://user:pass@localhost:5432/db
    echo    - REDIS_URL=redis://localhost:6379/0
    echo.
    echo 2. Start the services:
    echo    Option A: start_platform.bat    (Both services)
    echo    Option B: Docker Desktop        (Recommended)
    echo              docker-compose up -d
    echo.
    echo 3. Access the application:
    echo    Frontend: http://localhost:3000
    echo    Backend:  http://localhost:8000
    echo    API Docs: http://localhost:8000/docs
    echo.
) else (
    echo [WARNING] Some validations failed
    echo Please review the validation output above and fix any issues
    echo.
    echo Common issues:
    echo - Missing API keys in .env file
    echo - PostgreSQL/Redis not running
    echo - Python packages not installed correctly
    echo.
)

echo ========================================================
echo.
pause