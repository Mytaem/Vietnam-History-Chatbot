# Chatbot Lịch sử Việt Nam – GraphRAG, 100% Local LLM

Chatbot hỏi đáp lịch sử Việt Nam **từ tiền sử đến hết năm 1945**. Nguồn tri thức là Wikipedia tiếng Việt và Wikidata. Kiến trúc là GraphRAG, kết hợp Knowledge Graph trong Neo4j với Vector Search. Toàn bộ LLM chạy local qua Ollama.

Kế hoạch chi tiết (kiến trúc, phân kỳ, workflow, milestone) nằm trong [PLAN.md](PLAN.md).

> **Trạng thái:** mới dựng khung dự án. Các module chưa có code, thân hàm đang để `NotImplementedError`. Thứ tự triển khai: M1 → M10 (xem PLAN.md Mục 8).

## Yêu cầu

- Windows 10/11, Python 3.11+, Docker Desktop, Ollama
- GPU ≥ 6 GB VRAM (khuyến nghị), RAM ≥ 16 GB

## Cài đặt và chạy

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1                  # venv, pip, model, Neo4j
powershell -ExecutionPolicy Bypass -File scripts\build_index.ps1 -Profile mini
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1               # http://localhost:8501
```

## Profile build

| Profile | Nội dung | Thời gian ước tính |
|---|---|---|
| `mini` | 16 bài, rải đều các thời kỳ | ~25 phút |
| `period:<id>` | Một giai đoạn (id lấy trong `configs/periods.yaml`) | 20 phút – 1,5 giờ |
| `era:<id>` | Một thời kỳ: `tiensu`, `dungnuoc`, `bacthuoc`, `songsong`, `phongkien`, `candai` | 1–6 giờ |
| `core` | ~256 bài Tier A | ~8–9 giờ |
| `full` | ~930 bài | ~13–14 giờ (chia nhiều đêm, dừng rồi chạy tiếp được) |

## Cấu trúc thư mục

```
configs/    settings, ontology, periods (5 thời kỳ / 29 giai đoạn + 3 nhánh song song), seeds, backbone/
data/       đầu ra từng bước pipeline (JSONL, cache LLM) - không commit
src/hgr/    llm · ingest · process · extract · resolve · graph · embed · retrieve · generate · api · cli
ui/         Streamlit
eval/       bộ câu hỏi, baseline RAG, script eval
scripts/    setup / build_index / run_demo (PowerShell)
tests/      pytest (test đánh dấu `todo` được tự động skip)
```

## Lệnh CLI

```
hgr doctor | periods | ingest | parse | chunk | extract | resolve | load | embed | build | stats | ask | eval
```
