@echo off
cd /d "D:\Multi-Agent Orchestration System"
set PYTHONPATH=D:\Multi-Agent Orchestration System

for /f "tokens=1,2 delims==" %%A in (.env) do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
)

echo Starting Streamlit UI on http://localhost:8501 ...
python -m streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0
pause
