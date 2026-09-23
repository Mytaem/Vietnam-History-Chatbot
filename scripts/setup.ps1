# Cài đặt môi trường: venv, dependency, model Ollama, Neo4j (PLAN.md Mục 6.1)
# Chạy từ thư mục gốc dự án:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
param([switch]$Rerank)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Đã tạo .env từ .env.example - hãy đổi NEO4J_PASSWORD." -ForegroundColor Yellow
}

if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e .
if ($Rerank) { & .\.venv\Scripts\python.exe -m pip install -r requirements-rerank.txt }

ollama pull qwen3:4b-instruct-2507
ollama pull bge-m3

docker compose up -d neo4j

& .\.venv\Scripts\hgr.exe doctor
