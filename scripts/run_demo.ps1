# Chạy demo: Neo4j + API (:8000) + UI (:8501)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

docker compose up -d neo4j

Start-Process -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "hgr.api.main:app", "--host", "127.0.0.1", "--port", "8000"

& .\.venv\Scripts\python.exe -m streamlit run ui\app.py --server.port 8501
