@echo off
echo Starting Multi-Agent Orchestration System...

REM Check for .env file
if not exist .env (
    echo ERROR: .env file not found. Copy .env.example to .env and add your API keys.
    pause
    exit /b 1
)

REM Start Redis + API + UI via docker-compose
docker-compose up --build
