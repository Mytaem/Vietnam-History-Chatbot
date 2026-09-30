# Build index theo profile: mini | core | full | era:<id> | period:<id>  (PLAN.md Mục 2 - lịch build)
# Ví dụ:  powershell -File scripts\build_index.ps1 -Profile era:phongkien
param([string]$Profile = "mini")

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$env:OLLAMA_NUM_PARALLEL = "2"
& .\.venv\Scripts\hgr.exe build --profile $Profile
# Lệnh 'hgr stats' đang là TODO (M5), tạm thời chưa gọi để tránh dừng script do ErrorActionPreference = Stop
# & .\.venv\Scripts\hgr.exe stats --by-period

