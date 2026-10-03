# Chatbot Lịch sử Việt Nam – GraphRAG, 100% Local LLM

Chatbot hỏi đáp lịch sử Việt Nam **từ tiền sử đến hết năm 1945**. Nguồn tri thức là Wikipedia tiếng Việt và Wikidata. Kiến trúc là GraphRAG, kết hợp Knowledge Graph trong Neo4j với Vector Search. Toàn bộ LLM chạy local qua Ollama.

Kế hoạch chi tiết (kiến trúc, phân kỳ, workflow, milestone) nằm trong [PLAN.md](PLAN.md).

> **Trạng thái:** xong M1–M7 (hạ tầng, phân kỳ, thu thập/xử lý dữ liệu, trích xuất, resolve/load/embed, truy hồi + sinh câu trả lời, API + UI). Chạy được demo đầu-cuối thật trên profile `mini`. Còn lại: M8 (eval), build `core`/`full` đầy đủ (xem PLAN.md Mục 8).

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
| `mini` | 18 bài, rải đều 5 thời kỳ (~470 đoạn) | trích xuất ~1–1,5 giờ |
| `period:<id>` | Một giai đoạn (id lấy trong `configs/periods.yaml`) | 20 phút – 1,5 giờ |
| `era:<id>` | Một thời kỳ: `tiensu`, `dungnuoc`, `bacthuoc`, `songsong`, `phongkien`, `candai` | 1–6 giờ |
| `core` | ~256 bài Tier A | ~8–9 giờ |
| `full` | ~940 bài (~12.300 đoạn; ~4.350 đoạn tier A) | trích xuất tier A ~10–15 giờ, cả tier B ~14–21 giờ (chia nhiều đêm) |

## Chuẩn bị dữ liệu (M3)

```powershell
hgr periods --check                 # kiểm tra trục thời gian không bị hở
hgr ingest --profile full --fresh   # Wikipedia + Wikidata → data/raw/<giai đoạn>/articles.jsonl
hgr parse                           # → data/processed/articles.jsonl (mục, infobox, link, bảng, trích dẫn)
hgr chunk                           # → data/processed/chunks.jsonl (đầu vào cho bước trích xuất)
```

- `ingest` mặc định **gộp** với dữ liệu đã có; `--fresh` xóa dữ liệu các giai đoạn trước khi ghi.
- Phản hồi API được cache 7 ngày trong `data/cache/api/`: lần đầu `full` mất 15 phút đến vài giờ (tùy Wikidata có bận không, code tự chờ và thử lại), các lần sau chưa tới 1 phút.
- Báo cáo trong `data/reports/`: `missing_seeds.txt` (tiêu đề seed không tồn tại, phải rỗng), `rejected_p31.tsv` (bài bị bộ lọc loại, dùng để chỉnh `allowed_p31`).
- Seed, quota tier A, gợi ý prompt theo giai đoạn: `configs/periods.yaml`; bộ lọc bài mở rộng: `ingest` trong `configs/settings.yaml`.

## Chạy demo (M4–M7)

```powershell
hgr extract --structured            # Tier S: triplet từ backbone + Wikidata + infobox (không cần LLM)
hgr extract                         # Tier A/B: 2-pass LLM → data/extracted/extractions.jsonl
hgr resolve                         # Hợp nhất thực thể → data/resolved/{entities,relations,mentions}.jsonl
hgr load                            # Nạp Era/Period/backbone/Article/Chunk/Entity/Relation vào Neo4j
hgr embed                           # Embed Chunk + Entity bằng bge-m3

hgr ask "Trần Hưng Đạo là ai?"      # hỏi nhanh từ terminal, có trích dẫn [n]

powershell -File scripts\run_demo.ps1   # API (:8000) + UI (:8501)
```

- API: `POST /chat` (SSE: `plan` → nhiều `token` → `done{answer, citations, subgraph, timeline}`), `POST /retrieve` (debug, không stream), `GET /periods`, `GET /periods/{id}`, `GET /entity/{id}`, `GET /health`, `GET /stats`.
- UI (`ui/app.py`) gọi API thật qua SSE: cột chat trái; tab phải Đồ thị / Timeline / Nguồn / Khám phá giai đoạn / Debug; sidebar có `/health`, lọc giai đoạn, bật/tắt GraphRAG ↔ vector, câu hỏi mẫu.
- `configs/settings.yaml` → `llm.chat_model` mặc định `qwen3:4b-instruct` (ước lượng ban đầu ghi nhầm tag `-2507`, tag đó không tồn tại trên registry Ollama — đã sửa). Máy chưa pull được thì đổi tạm sang `qwen2.5:3b-instruct` (model dự phòng theo PLAN.md, đã test kỹ trong quá trình phát triển).

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
hgr doctor | periods | ingest | parse | chunk | extract | resolve | load | embed | build | stats | ask
```

`hgr eval` (M8, so sánh GraphRAG với baseline vector) chưa triển khai.
