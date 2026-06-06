@echo off
cd /d "D:\Multi-Agent Orchestration System"
set PYTHONPATH=D:\Multi-Agent Orchestration System

for /f "tokens=1,2 delims==" %%A in (.env) do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
)

echo Starting FastAPI on http://localhost:8000 ...
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
pause
